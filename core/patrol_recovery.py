"""Four real recovery techniques on one directed, resource-constrained graph.

No recharging en route: each candidate is a landing at origin or the next
eligible station. Distances, directed wind times and residual edges are shared.
"""
import heapq
import math
import random
import time

METHODS = ('dijkstra_distance', 'dijkstra_weighted', 'gurobi', 'annealing')


def path_search(edges, adjacency, start, goal, limit, metric, banned=frozenset()):
    # Resource-constrained Dijkstra: retain nondominated (objective,time) labels.
    serial = 0
    queue = [(0., serial, start, 0., [])]
    labels = {}
    while queue:
        cost, _, node, seconds, path = heapq.heappop(queue)
        previous = labels.setdefault(node, [])
        if any(c <= cost+1e-9 and s <= seconds+1e-9 for c, s in previous):
            continue
        labels[node] = [(c,s) for c,s in previous if not (cost <= c and seconds <= s)] + [(cost,seconds)]
        if node == goal:
            return path
        for ident in adjacency.get(node, []):
            e = edges[ident]
            if e['target'] in banned or seconds+e['time_s'] > limit+1e-9:
                continue
            serial += 1
            heapq.heappush(queue, (cost+metric(ident,e), serial, e['target'], seconds+e['time_s'], path+[ident]))
    return None


def milp(edges, adjacency, start, goal, limit, seconds):
    if start == goal:
        return [], dict(status='optimal', scope='directed graph')
    try:
        import gurobipy as gp
        with gp.Env(empty=True) as env:
            env.setParam('OutputFlag', 0); env.start()
            with gp.Model(env=env) as model:
                model.Params.TimeLimit = min(seconds, 10)
                ids = [i for values in adjacency.values() for i in values]
                x = model.addVars(ids, vtype=gp.GRB.BINARY)
                incoming = {}
                for i in ids: incoming.setdefault(edges[i]['target'], []).append(i)
                for node in {n for n,ids in adjacency.items() if ids} | set(incoming) | {start,goal}:
                    model.addConstr(gp.quicksum(x[i] for i in adjacency.get(node, [])) -
                                    gp.quicksum(x[i] for i in incoming.get(node, [])) == (1 if node == start else -1 if node == goal else 0))
                model.addConstr(gp.quicksum(edges[i]['time_s']*x[i] for i in ids) <= limit)
                model.setObjective(gp.quicksum(max(1e-6, edges[i]['cost'])*x[i] for i in ids))
                model.optimize()
                meta = dict(status=str(model.Status), scope='shared candidate corridor graph; no en-route recharge', variables=len(ids),constraints=model.NumConstrs)
                if not model.SolCount: return None, meta
                meta['gap'] = model.MIPGap
                chosen = {i for i in ids if x[i].X > .5}
                node = start; path = []; visited = set()
                while node != goal:
                    if node in visited: return None, dict(status='invalid_cycle')
                    visited.add(node)
                    ident = next((i for i in adjacency.get(node, []) if i in chosen), None)
                    if ident is None: return None, dict(status='invalid_flow')
                    path.append(ident); node = edges[ident]['target']
                return path, meta
    except (ImportError, RuntimeError) as exc:
        return None, dict(status='unavailable', reason=str(exc))
    except Exception as exc:
        # License size limits and solver errors remain visible; no fallback.
        return None, dict(status='solver_error', reason=str(exc))


def anneal(edges, adjacency, start, goal, limit, seed, iterations):
    rng = random.Random(seed)
    current = path_search(edges, adjacency, start, goal, limit, lambda i,e:e['time_s'])
    if current is None: return None, dict(status='no_initial_feasible_path', iterations=0)
    score = lambda path: sum(edges[i]['cost'] for i in path)
    best = current; best_cost = current_cost = score(current)
    attempts = accepted = 0
    for k in range(iterations):
        if not current: break
        # Mutate a local subpath rather than repeatedly exploring the entire
        # 70k-edge city graph with random global weights.
        cut = rng.randrange(len(current))
        end = min(len(current),cut+rng.randint(1,6))
        prefix = current[:cut]
        tail = current[end:]
        node = edges[current[cut]]['source']
        local_goal=edges[current[end-1]]['target']
        banned = {edges[i]['source'] for i in prefix}|{edges[i]['target'] for i in tail}
        left = limit - sum(edges[i]['time_s'] for i in prefix+tail)
        penalties = {i:rng.uniform(.1,4) for values in adjacency.values() for i in values}
        suffix = path_search(edges, adjacency, node, local_goal, left, lambda i,e:e['cost']*penalties[i], banned)
        attempts += 1
        if suffix is None: continue
        candidate = prefix+suffix+tail; cost = score(candidate)
        temperature = max(.001, max(1,best_cost)*.3*(1-k/iterations))
        if cost <= current_cost or rng.random() < math.exp(min(0,(current_cost-cost)/temperature)):
            current, current_cost = candidate,cost; accepted += 1
        if cost < best_cost: best,best_cost = candidate,cost
    return best, dict(status='heuristic', iterations=attempts, accepted=accepted, seed=seed)


def compare(edges, adjacency, start, home, stations, battery, elapsed, profile,
            landing, failed_nodes=frozenset(), seed=0, preferred_station=None,
            destination='auto', selected_method='dijkstra_weighted'):
    preparation_started=time.monotonic()
    if destination not in ('auto','origin','station') or selected_method not in METHODS:
        raise ValueError('Política de recuperación desconocida')
    adjacency = {n:[i for i in ids if edges[i]['target'] not in failed_nodes] for n,ids in adjacency.items() if n not in failed_nodes}
    def budget(node): return min(battery-landing(node), profile['mission_budget_s']-elapsed-landing(node))
    # Next itinerary station if feasible; otherwise first reachable by directed
    # flight duration. The origin is never duplicated as an alternate station.
    reachable = []
    for station in stations:
        node = str(station['node'])
        if node == home or node in failed_nodes: continue
        path = path_search(edges, adjacency, start, node, budget(node), lambda i,e:e['time_s'])
        if path is not None:
            reachable.append((station['id'] != preferred_station, sum(edges[i]['time_s'] for i in path), station['id'], node))
    targets = [('origin',home)] if home not in failed_nodes else []
    if reachable:
        _,_,ident,node = min(reachable); targets.append((ident,node))
    # Build ONE shared corridor graph before timing techniques. Preserve the
    # feasible best distance, weighted and time paths for each destination,
    # plus links between their nodes. This keeps the actual MILP usable with
    # the project's restricted academic license, without solver substitution.
    corridor=set();corridor_nodes={start}
    original_edges=sum(len(ids) for ids in adjacency.values())
    for _,node in targets:
        for metric in ('distance_m','cost','time_s'):
            path=path_search(edges,adjacency,start,node,budget(node),lambda i,e:e[metric])
            if path is not None:
                corridor.update(path)
                corridor_nodes.update(edges[i]['source'] for i in path)
                corridor_nodes.update(edges[i]['target'] for i in path)
    internal={i for n in corridor_nodes for i in adjacency.get(n,[]) if edges[i]['target'] in corridor_nodes}
    max_edges=profile.get('recovery_max_edges',1800)
    shared=corridor|internal if len(corridor|internal)<=max_edges else corridor
    bounded=len(shared)<=max_edges
    if bounded:adjacency={n:[i for i in ids if i in shared] for n,ids in adjacency.items() if n in corridor_nodes}
    graph_scope=dict(kind='shared_candidate_corridors' if bounded else 'full_admissible_graph',
                     full_edges=original_edges,candidate_edges=sum(len(ids) for ids in adjacency.values()),
                     max_edges=max_edges,preparation_s=time.monotonic()-preparation_started,
                     policy='union of feasible best distance, weighted and time paths to both destinations; internal links when within limit',
                     optimality_scope='candidate graph; not continuous airspace')
    candidates = []; recommendations = {}
    for method in METHODS:
        for ident,node in targets:
            begin = time.monotonic(); limit = budget(node); meta = {}
            if limit < 0: path = None; meta = dict(status='resource_limit')
            elif method == 'gurobi':
                path,meta = milp(edges,adjacency,start,node,limit,profile.get('solver_seconds',10))
            elif method == 'annealing':
                path,meta = anneal(edges,adjacency,start,node,limit,seed,min(64,profile.get('annealing_iterations',64)))
            else:
                metric = 'distance_m' if method == 'dijkstra_distance' else 'cost'
                path = path_search(edges,adjacency,start,node,limit,lambda i,e:e[metric])
                meta = dict(status='optimal_on_graph' if path is not None else 'no_feasible_path')
            row = dict(method=method,destination_id=ident,destination_kind='origin' if ident=='origin' else 'station',
                       node=node,status='ready' if path is not None else 'unavailable',solver=meta,compute_s=time.monotonic()-begin,
                       edge_ids=path or [],coordinates=[])
            if path is not None:
                # Validate solver output with the identical physical evaluator.
                current = start
                for i in path:
                    if edges[i]['source'] != current: raise ValueError('Retorno discontinuo')
                    current = edges[i]['target']
                flight = sum(edges[i]['time_s'] for i in path)
                if current != node or flight > limit+1e-6: raise ValueError('Retorno fuera del presupuesto')
                row.update(flight_s=flight,landing_s=landing(node),time_s=flight+landing(node),
                           distance_m=sum(edges[i]['distance_m'] for i in path),cost=sum(edges[i]['cost'] for i in path),
                           battery_remaining_s=battery-flight-landing(node))
            candidates.append(row)
        eligible = [r for r in candidates if r['method']==method and r['status']=='ready' and (destination=='auto' or r['destination_kind']==destination)]
        if eligible: recommendations[method] = min(eligible,key=lambda r:(r['cost'],r['time_s'],r['destination_id']))
    chosen = recommendations.get(selected_method)
    # Honor an explicitly requested technique; do not silently substitute it.
    return dict(schema_version='recovery-1',candidates=candidates,recommendations=recommendations,selected=chosen,
                graph_scope=graph_scope,
                selected_method=selected_method,destination_policy=destination,
                snapshot=dict(node=start,battery_remaining_s=battery,elapsed_s=elapsed),
                station_policy='next feasible itinerary station, else least directed flight time',
                recharge_en_route=False)
