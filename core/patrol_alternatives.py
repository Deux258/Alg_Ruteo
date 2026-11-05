"""Spatially distinct circuits, separate from the unmodified four-method comparison.

Reversing a circuit or changing its sampling does not make a new corridor. Every
candidate keeps the common surveillance tasks and the real battery constraints.
"""
import heapq
import itertools
import math
import time

from shapely.geometry import LineString, Point
from shapely.ops import unary_union


class CorridorGraph:
    def __init__(self,base,usage,strength,outside,deadline=math.inf):
        self.base=base
        self.deadline=deadline
        self.cache={}
        self.weights={i:e['cost']*(1+strength*usage.get(tuple(sorted((e['source'],e['target']))),0)*outside[i])
                      for i,e in base.edges.items()}

    def __getattr__(self,key):return getattr(self.base,key)

    def path(self,source,target,metric='cost'):
        if time.monotonic()>self.deadline:return None
        if (source,target) in self.cache:return self.cache[source,target]
        targets=set(self.base.routing_targets or [target]);targets.add(target)
        distance={source:0.};previous={};queue=[(0.,source)];pending=set(targets)
        iterations=0
        while queue and pending:
            iterations+=1
            if iterations%512==0 and time.monotonic()>self.deadline:return None
            cost,node=heapq.heappop(queue)
            if cost!=distance[node]:continue
            pending.discard(node)
            for ident in self.base.adj[node]:
                edge=self.base.edges[ident];nxt=edge['target'];value=cost+self.weights[ident]
                if value<distance.get(nxt,math.inf):
                    distance[nxt]=value;previous[nxt]=ident;heapq.heappush(queue,(value,nxt))
        for dest in targets:
            path=None
            if dest in distance and dest not in pending:
                path=[];node=dest
                while node!=source:
                    ident=previous[node];path.append(ident);node=self.base.edges[ident]['source']
                path.reverse()
            self.cache[source,dest]=self.base.check_path(path,source,dest)
        return self.cache[source,target]


def corridor_geometry(path,graph,target,home):
    lines=[LineString([graph.nodes[graph.edges[i]['source']][:2],graph.nodes[graph.edges[i]['target']][:2]]) for i in set(path)]
    whole=unary_union(lines)
    outside=whole.difference(target.buffer(5)).difference(Point(graph.nodes[home][:2]).buffer(20))
    return outside if outside.length>20 else whole


def corridor_overlap(a,b,tolerance=12):
    if a.is_empty or b.is_empty:return 1.
    # A 12 m tolerance also rejects resampled or almost coincident geometry.
    return min(1.,max(a.intersection(b.buffer(tolerance)).length/a.length,
                     b.intersection(a.buffer(tolerance)).length/b.length))


def distinct_circuits(graph,tasks,home,stations,target,comparison):
    from core.patrol import coverage, fixed_route, oriented_tasks
    start=time.monotonic();accepted=[];geometries=[];rejected=0
    overlap_limit=graph.p.get('alternative_max_shared_transit',.8)
    tolerance=graph.p.get('alternative_corridor_tolerance_m',12)
    raw=[r for r in comparison.values() if r['status']=='ready']
    if not raw:return {},dict(count=0,requested=4,reason='Sin misión viable',compute_s=0,status='limited',comparison_unchanged=True)
    reference=comparison.get('dijkstra_distance')
    if not reference or reference['status']!='ready':reference=min(raw,key=lambda r:r['time_s'])
    max_time=min(graph.p['mission_budget_s'],reference['time_s']*graph.p.get('alternative_max_time_factor',1.8)+graph.p.get('alternative_max_time_slack_s',60))

    def accept(answer,origin,solver):
        nonlocal rejected
        path=answer['path']
        geom=corridor_geometry(path,graph,target,home)
        overlaps=[corridor_overlap(geom,g,tolerance) for g in geometries]
        if overlaps and max(overlaps)>overlap_limit:
            rejected+=1;return False
        cov=answer.get('coverage') or coverage(path,graph,target)
        if not cov['complete'] or answer['time_s']>max_time:return False
        coordinates=graph.coordinates(path)
        from core.aerial_data import INV
        ident=f'alt_{len(accepted)+1}'
        row=dict(method=ident,label=f'Circuito {len(accepted)+1}',status='ready',
            solver=solver,origin_method=origin,edge_ids=[str(i) for i in path],
            coordinates=[[*INV(c[0],c[1]),c[2]] for c in coordinates],coordinates_utm=coordinates,
            coverage=cov,stops=answer['stops'],time_s=answer['time_s'],cost=answer.get('cost'),
            distance_m=graph.totals(path)['distance_m'],compute_s=time.monotonic()-start,
            diversity=dict(max_shared_transit=max(overlaps,default=0),compared_with=[r['method'] for r in accepted],
                           tolerance_m=tolerance,excludes='surveillance polygon + 5 m and first 20 m around base'))
        accepted.append(row);geometries.append(geom);return True

    for row in [reference,*[r for r in raw if r is not reference]]:
        accept(dict(path=[int(i) for i in row['edge_ids']],stops=row['stops'],time_s=row['time_s'],cost=row.get('cost'),coverage=row['coverage']),
               row['method'],dict(engine='comparison_result',method=row['method'],description='Resultado original de la técnica'))
    outside={};expanded_target=target.buffer(5)
    for i,e in graph.edges.items():
        line=LineString([graph.nodes[e['source']][:2],graph.nodes[e['target']][:2]])
        outside[i]=line.difference(expanded_target).length/max(line.length,1e-9)
    attempts=0
    deadline=start+graph.p.get('alternative_search_seconds',15)
    for strength in (1.,2.,4.,8.,16.,32.):
        if len(accepted)>=4 or time.monotonic()>deadline:break
        usage={}
        for row in accepted:
            for i in set(int(v) for v in row['edge_ids']):
                e=graph.edges[i];key=tuple(sorted((e['source'],e['target'])))
                usage[key]=usage.get(key,0)+1
        overlay=CorridorGraph(graph,usage,strength,outside,deadline)
        states=oriented_tasks(tasks,overlay,'cost')
        by_group={g:[i for i,s in enumerate(states) if s['group']==g] for g in range(len(tasks))}
        if any(not v for v in by_group.values()):continue
        orders=[]
        # Deterministic bounded exploration: preserve coverage, vary strip order/orientation.
        groups=list(by_group)
        permutations=[groups,list(reversed(groups))]
        if len(groups)<=4:permutations=list(itertools.permutations(groups))[:24]
        for order in permutations:
            options=[by_group[g] for g in order]
            for orientation in itertools.islice(itertools.product(*options),16):orders.append(list(orientation))
        candidates=[]
        for order in orders[:64]:
            if time.monotonic()>deadline:break
            answer=fixed_route(order,states,overlay,home,stations,'cost');attempts+=1
            if answer is None or answer['time_s']>max_time:continue
            geom=corridor_geometry(answer['path'],graph,target,home)
            overlap=max((corridor_overlap(geom,g,tolerance) for g in geometries),default=0)
            if overlap<=overlap_limit:candidates.append((overlap,answer['time_s'],answer))
        for _,_,answer in sorted(candidates,key=lambda v:(v[0],v[1])):
            if accept(answer,None,dict(engine='diverse_dijkstra',description='Búsqueda de conectores con penalización de corredores usados',
                                      reuse_penalty=strength,comparison_preserved=True)):
                break
    return {r['method']:r for r in accepted},dict(count=len(accepted),requested=4,max_shared_transit=overlap_limit,
        tolerance_m=tolerance,rejected_duplicates=rejected,search_attempts=attempts,compute_s=time.monotonic()-start,
        status='complete' if len(accepted)==4 else 'limited',
        time_limit_s=graph.p.get('alternative_search_seconds',15),
        reason=None if len(accepted)==4 else 'No se encontraron cuatro corredores viables suficientemente separados; no se duplican rutas',
        comparison_unchanged=True,maximum_time_s=max_time)
