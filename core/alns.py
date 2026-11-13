"""Risk-weighted latency optimization via ALNS and Gurobi MILP (Etapa 4).

Minimizes expected fire-detection delay (weighted by task prize r_i = ∫ R dA)
plus drone hazard cost and recharge penalties, subject to battery autonomy,
M1 station inventory / recharge waits, and A3 hard airspace blocks:

    min  Σ_i r_i * a_i  +  λ1 * Σ_{(i,j)} P_ij * t_ij * x_ij  +  λ2 * N_recargas

where a_i is the first-visit arrival time of task i (including departure,
service, and any M1 battery swap/recharge wait). Also supports discounted
objective: max Σ_i r_i * exp(-κ * a_i).
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any

import numpy as np


@dataclass(frozen=True)
class LatencyConfig:
    """Central configuration for ALNS and Gurobi latency routing."""

    lambda1_risk: float = 1.0
    lambda2_recharge: float = 120.0
    objective_mode: str = 'linear'  # 'linear' (Σ r_i a_i) | 'discounted' (-Σ r_i exp(-κ a_i))
    kappa_discount: float = 0.001
    alns_iterations: int = 250
    alns_time_limit_s: float = 5.0
    destroy_min_frac: float = 0.15
    destroy_max_frac: float = 0.40
    segment_size: int = 25
    sa_t0: float = 0.05
    sa_cooling: float = 0.985
    gurobi_time_limit_s: float = 10.0
    gurobi_gap: float = 0.02
    gurobi_restricted_max_tasks: int = 28
    gurobi_full_max_tasks: int = 120


def detect_gurobi_license() -> dict[str, Any]:
    """Detect Gurobi availability and whether license is restricted (~2000 vars)."""
    try:
        import gurobipy as gp
        m = gp.Model('license_probe')
        m.setParam('OutputFlag', 0)
        # Probe if >2100 vars triggers restricted license error
        xs = m.addVars(2100, vtype=gp.GRB.BINARY, name='p')
        m.update()
        try:
            m.optimize()
            return {'available': True, 'tier': 'full', 'max_tasks': 120}
        except gp.GurobiError as exc:
            if 'Model too large' in str(exc) or 'size-limited' in str(exc).lower():
                return {'available': True, 'tier': 'restricted', 'max_tasks': 28}
            return {'available': True, 'tier': 'restricted', 'max_tasks': 28}
    except Exception as exc:
        return {'available': False, 'tier': 'none', 'max_tasks': 0, 'reason': str(exc)}


@dataclass
class RouteEval:
    """Evaluated sequence of task indices with M1 recharge stops."""

    order: list[int]
    objective: float
    weighted_latency: float
    hazard_cost: float
    recharges: int
    arrival_times: dict[int, float]
    stops: list[dict[str, Any]]
    total_time_s: float
    total_distance_m: float
    feasible: bool
    landing_base_idx: int = 0


def evaluate_task_sequence(
    order: list[int],
    tasks: list[dict[str, Any]],
    stations: list[dict[str, Any]],
    origin_xy: tuple[float, float],
    dist_fn: Any,
    cruise_ms: float,
    battery_budget_s: float,
    mu_drain: float,
    station_service_s: float,
    station_inventory: int,
    recharge_s: float,
    cfg: LatencyConfig,
    wind_profile: Any = None,
    agl_m: float = 60.0,
) -> RouteEval:
    """Simulate a task permutation with greedy M1 recharge insertion and exact a_i."""
    eff_budget = max(60.0, float(battery_budget_s) / max(0.2, float(mu_drain)))
    inv = {s['id']: int(station_inventory) for s in stations}
    cur_xy = origin_xy
    cur_t = 0.0
    bat_rem = eff_budget
    total_dist = 0.0
    hazard_cost = 0.0
    weighted_latency = 0.0
    recharges = 0
    arrivals: dict[int, float] = {}
    stops: list[dict[str, Any]] = []

    def _travel(a: tuple[float, float], b: tuple[float, float], t_dep: float) -> tuple[float, float, float]:
        d, p_haz = dist_fn(a, b)
        if wind_profile is not None:
            t_seg = wind_profile.edge_travel_time((a[0], a[1], agl_m), (b[0], b[1], agl_m), t_dep, cruise_ms, 5.0, 5.0, agl_m=agl_m)
        else:
            t_seg = d / max(1.0, float(cruise_ms))
        return d, t_seg, p_haz

    def _nearest_station(xy: tuple[float, float]) -> dict[str, Any]:
        if not stations:
            return {'id': 'origin', 'xy': origin_xy, 'name': 'Origen'}
        return min(stations, key=lambda s: math.hypot(s['xy'][0] - xy[0], s['xy'][1] - xy[1]))

    for tid in order:
        task = tasks[tid]
        txy = (float(task['centroid_utm'][0]), float(task['centroid_utm'][1]))
        svc_s = float(task.get('service_s', 15.0))
        d_to, t_to, p_to = _travel(cur_xy, txy, cur_t)
        st_after = _nearest_station(txy)
        _, t_ret, _ = _travel(txy, st_after['xy'], cur_t + t_to + svc_s)

        if t_to + svc_s + t_ret > bat_rem:
            # Must visit nearest M1 station before this task
            st = _nearest_station(cur_xy)
            d_st, t_st, p_st = _travel(cur_xy, st['xy'], cur_t)
            if t_st > bat_rem + 1e-6:
                return RouteEval(order=order, objective=1e18, weighted_latency=1e18, hazard_cost=1e18, recharges=recharges, arrival_times=arrivals, stops=stops, total_time_s=cur_t, total_distance_m=total_dist, feasible=False)
            cur_t += t_st
            total_dist += d_st
            hazard_cost += p_st * t_st
            sid = st['id']
            rem_inv = inv.get(sid, 0)
            wait_s = float(station_service_s) if rem_inv > 0 else float(recharge_s)
            if rem_inv > 0:
                inv[sid] = rem_inv - 1
            cur_t += wait_s
            bat_rem = eff_budget
            recharges += 1
            stops.append({'station_id': sid, 'arrival_s': cur_t - wait_s, 'wait_s': wait_s, 'recharged': rem_inv <= 0})
            cur_xy = st['xy']
            d_to, t_to, p_to = _travel(cur_xy, txy, cur_t)

        if t_to + svc_s > bat_rem + 1e-6:
            return RouteEval(order=order, objective=1e18, weighted_latency=1e18, hazard_cost=1e18, recharges=recharges, arrival_times=arrivals, stops=stops, total_time_s=cur_t, total_distance_m=total_dist, feasible=False)

        cur_t += t_to
        total_dist += d_to
        hazard_cost += p_to * t_to
        bat_rem -= t_to

        arrivals[tid] = cur_t
        prize = float(task.get('prize', 1.0))
        if cfg.objective_mode == 'discounted':
            weighted_latency -= prize * math.exp(-cfg.kappa_discount * cur_t)
        else:
            weighted_latency += prize * cur_t

        cur_t += svc_s
        bat_rem -= svc_s
        total_dist += svc_s * cruise_ms * 0.5
        cur_xy = txy

    # Return to nearest station (or origin)
    st_end = _nearest_station(cur_xy)
    d_end, t_end, p_end = _travel(cur_xy, st_end['xy'], cur_t)
    cur_t += t_end
    total_dist += d_end
    hazard_cost += p_end * t_end
    landing_idx = next((i for i, s in enumerate(stations) if s['id'] == st_end['id']), 0)

    obj = weighted_latency + cfg.lambda1_risk * hazard_cost + cfg.lambda2_recharge * recharges
    return RouteEval(
        order=list(order),
        objective=float(obj),
        weighted_latency=float(weighted_latency),
        hazard_cost=float(hazard_cost),
        recharges=recharges,
        arrival_times=arrivals,
        stops=stops,
        total_time_s=float(cur_t),
        total_distance_m=float(total_dist),
        feasible=True,
        landing_base_idx=landing_idx,
    )


def _nearest_neighbor_init(tasks: list[dict[str, Any]], origin_xy: tuple[float, float]) -> list[int]:
    remaining = set(range(len(tasks)))
    order: list[int] = []
    cur = origin_xy
    while remaining:
        nxt = min(remaining, key=lambda i: math.hypot(tasks[i]['centroid_utm'][0] - cur[0], tasks[i]['centroid_utm'][1] - cur[1]) / max(1e-3, float(tasks[i].get('prize', 1.0)) + 0.1))
        order.append(nxt)
        remaining.remove(nxt)
        cur = tuple(tasks[nxt]['centroid_utm'])
    return order


def alns_risk(
    tasks: list[dict[str, Any]],
    stations: list[dict[str, Any]],
    origin_xy: tuple[float, float],
    dist_fn: Any,
    cruise_ms: float = 10.0,
    battery_budget_s: float = 1200.0,
    mu_drain: float = 1.0,
    station_service_s: float = 120.0,
    station_inventory: int = 1,
    recharge_s: float = 10800.0,
    seed: int = 20261104,
    config: LatencyConfig | None = None,
    wind_profile: Any = None,
    agl_m: float = 60.0,
    initial_order: list[int] | None = None,
) -> dict[str, Any]:
    """Adaptive Large Neighborhood Search for risk-weighted patrol latency."""
    t0 = time.perf_counter()
    cfg = config or LatencyConfig()
    n = len(tasks)
    if n == 0:
        return {'status': 'empty', 'order': [], 'eval': None, 'compute_s': 0.0, 'initial_objective': 0.0, 'best_objective': 0.0}

    rng = np.random.default_rng(seed)
    init_ord = list(initial_order) if initial_order is not None else _nearest_neighbor_init(tasks, origin_xy)

    def _eval(seq: list[int]) -> RouteEval:
        return evaluate_task_sequence(
            seq, tasks, stations, origin_xy, dist_fn, cruise_ms,
            battery_budget_s, mu_drain, station_service_s, station_inventory,
            recharge_s, cfg, wind_profile=wind_profile, agl_m=agl_m,
        )

    cur_eval = _eval(init_ord)
    best_eval = cur_eval
    init_obj = cur_eval.objective

    # Adaptive weights for 3 destroy x 3 repair operators
    d_weights = np.ones(3, dtype=float)
    r_weights = np.ones(3, dtype=float)
    d_scores = np.zeros(3, dtype=float)
    r_scores = np.zeros(3, dtype=float)
    d_counts = np.zeros(3, dtype=float)
    r_counts = np.zeros(3, dtype=float)

    temp = max(1e-3, abs(cur_eval.objective) * cfg.sa_t0)

    for it in range(1, cfg.alns_iterations + 1):
        if time.perf_counter() - t0 >= cfg.alns_time_limit_s:
            break
        q = max(1, min(n - 1, int(rng.uniform(cfg.destroy_min_frac, cfg.destroy_max_frac) * n))) if n > 1 else 0
        if q == 0:
            break

        # Roulette selection
        d_op = int(rng.choice(3, p=d_weights / np.sum(d_weights)))
        r_op = int(rng.choice(3, p=r_weights / np.sum(r_weights)))

        seq = list(cur_eval.order)
        if d_op == 0:
            # Random removal
            rem_idx = sorted(rng.choice(len(seq), size=q, replace=False).tolist(), reverse=True)
            removed = [seq.pop(idx) for idx in rem_idx]
        elif d_op == 1:
            # Worst prize * arrival_time removal
            scored = sorted(seq, key=lambda tid: float(tasks[tid].get('prize', 1.0)) * cur_eval.arrival_times.get(tid, 1e6), reverse=True)
            rem_set = set(scored[:q])
            removed = [tid for tid in seq if tid in rem_set]
            seq = [tid for tid in seq if tid not in rem_set]
        else:
            # Geographic cluster removal around a random seed
            seed_tid = int(rng.choice(seq))
            sx, sy = tasks[seed_tid]['centroid_utm']
            by_dist = sorted(seq, key=lambda tid: math.hypot(tasks[tid]['centroid_utm'][0] - sx, tasks[tid]['centroid_utm'][1] - sy))
            rem_set = set(by_dist[:q])
            removed = [tid for tid in seq if tid in rem_set]
            seq = [tid for tid in seq if tid not in rem_set]

        # Repair operators (0: greedy, 1: regret-2, 2: regret-3)
        k_regret = 1 if r_op == 0 else (2 if r_op == 1 else 3)
        while removed:
            best_tid = removed[0]
            best_pos = 0
            best_score = -1e18
            greedy_best_obj = 1e18
            for tid in removed:
                # Sample up to 12 insertion positions for O(1) bounded speed on large n
                m_pos = len(seq) + 1
                positions = list(range(m_pos)) if m_pos <= 14 else sorted(set([0, m_pos - 1] + rng.choice(m_pos, size=10, replace=False).tolist()))
                cand_objs: list[tuple[float, int]] = []
                for pos in positions:
                    cand_seq = seq[:pos] + [tid] + seq[pos:]
                    c_ev = _eval(cand_seq)
                    cand_objs.append((c_ev.objective, pos))
                cand_objs.sort(key=lambda item: item[0])
                prize_w = max(1e-3, float(tasks[tid].get('prize', 1.0)))
                if k_regret == 1 or len(cand_objs) == 1:
                    if cand_objs[0][0] < greedy_best_obj:
                        greedy_best_obj = cand_objs[0][0]
                        best_tid, best_pos = tid, cand_objs[0][1]
                else:
                    k_idx = min(k_regret, len(cand_objs) - 1)
                    regret = (cand_objs[k_idx][0] - cand_objs[0][0]) * prize_w
                    if regret > best_score:
                        best_score = regret
                        best_tid, best_pos = tid, cand_objs[0][1]
            seq.insert(best_pos, best_tid)
            removed.remove(best_tid)

        cand_eval = _eval(seq)
        d_counts[d_op] += 1
        r_counts[r_op] += 1

        delta = cand_eval.objective - cur_eval.objective
        if cand_eval.feasible and (delta <= 0 or float(rng.random()) < math.exp(-delta / max(1e-6, temp))):
            cur_eval = cand_eval
            if cand_eval.objective < best_eval.objective:
                best_eval = cand_eval
                d_scores[d_op] += 5.0
                r_scores[r_op] += 5.0
            elif delta <= 0:
                d_scores[d_op] += 2.0
                r_scores[r_op] += 2.0
            else:
                d_scores[d_op] += 0.5
                r_scores[r_op] += 0.5

        temp *= cfg.sa_cooling
        if it % cfg.segment_size == 0:
            for k in range(3):
                if d_counts[k] > 0:
                    d_weights[k] = 0.7 * d_weights[k] + 0.3 * (d_scores[k] / d_counts[k] + 0.1)
                if r_counts[k] > 0:
                    r_weights[k] = 0.7 * r_weights[k] + 0.3 * (r_scores[k] / r_counts[k] + 0.1)
            d_scores[:] = 0.0
            r_scores[:] = 0.0
            d_counts[:] = 0.0
            r_counts[:] = 0.0

    return {
        'status': 'ready' if best_eval.feasible else 'infeasible',
        'order': best_eval.order,
        'eval': best_eval,
        'initial_objective': float(init_obj),
        'best_objective': float(best_eval.objective),
        'improvement_pct': round(100.0 * (init_obj - best_eval.objective) / max(1e-9, abs(init_obj)), 2) if init_obj != 0 else 0.0,
        'compute_s': round(time.perf_counter() - t0, 4),
    }


def gurobi_latency_route(
    tasks: list[dict[str, Any]],
    origin_xy: tuple[float, float],
    dist_fn: Any,
    cruise_ms: float = 10.0,
    config: LatencyConfig | None = None,
) -> dict[str, Any]:
    """Exact/reference MILP (MTZ latency formulation) via Gurobi with license detection."""
    t0 = time.perf_counter()
    cfg = config or LatencyConfig()
    lic = detect_gurobi_license()
    if not lic['available']:
        return {'status': 'skipped', 'reason': lic.get('reason', 'Gurobi no disponible'), 'license': lic, 'compute_s': 0.0}

    n = len(tasks)
    if n == 0:
        return {'status': 'empty', 'order': [], 'objective': 0.0, 'license': lic, 'compute_s': 0.0}
    if n > lic['max_tasks']:
        return {
            'status': 'skipped_license_cap',
            'reason': f'{n} tareas exceden límite MILP ({lic["max_tasks"]} para licencia {lic["tier"]}); ALNS es el motor principal.',
            'license': lic,
            'compute_s': 0.0,
        }

    import gurobipy as gp
    m = gp.Model('rrpp_latency')
    m.setParam('OutputFlag', 0)
    m.setParam('TimeLimit', float(cfg.gurobi_time_limit_s))
    m.setParam('MIPGap', float(cfg.gurobi_gap))

    # Node 0 = origin, nodes 1..n = tasks
    coords = [origin_xy] + [(float(t['centroid_utm'][0]), float(t['centroid_utm'][1])) for t in tasks]
    prizes = [0.0] + [float(t.get('prize', 1.0)) for t in tasks]
    svc = [0.0] + [float(t.get('service_s', 15.0)) for t in tasks]

    N = n + 1
    t_ij = {}
    p_ij = {}
    for i in range(N):
        for j in range(N):
            if i == j:
                continue
            d, p_haz = dist_fn(coords[i], coords[j])
            t_ij[i, j] = d / max(1.0, float(cruise_ms))
            p_ij[i, j] = p_haz

    big_m = sum(max(t_ij[i, j] for j in range(N) if j != i) + svc[i] for i in range(N)) + 100.0
    x = m.addVars([(i, j) for i in range(N) for j in range(N) if i != j], vtype=gp.GRB.BINARY, name='x')
    a = m.addVars(range(N), lb=0.0, ub=big_m, vtype=gp.GRB.CONTINUOUS, name='a')

    # Degree constraints
    for i in range(N):
        m.addConstr(gp.quicksum(x[i, j] for j in range(N) if j != i) == 1)
        m.addConstr(gp.quicksum(x[j, i] for j in range(N) if j != i) == 1)

    m.addConstr(a[0] == 0.0)
    # Time propagation & MTZ subtour elimination
    for i in range(N):
        for j in range(1, N):
            if i == j:
                continue
            m.addConstr(a[j] >= a[i] + svc[i] + t_ij[i, j] - big_m * (1.0 - x[i, j]))

    obj = gp.quicksum(prizes[i] * a[i] for i in range(1, N)) + cfg.lambda1_risk * gp.quicksum(
        p_ij[i, j] * t_ij[i, j] * x[i, j] for i in range(N) for j in range(N) if i != j
    )
    m.setObjective(obj, gp.GRB.MINIMIZE)
    m.optimize()

    if m.SolCount == 0:
        return {'status': 'no_solution', 'license': lic, 'compute_s': round(time.perf_counter() - t0, 4)}

    order: list[int] = []
    cur = 0
    seen = {0}
    for _ in range(n):
        nxt = next((j for j in range(N) if j != cur and x[cur, j].X > 0.5), None)
        if nxt is None or nxt in seen:
            break
        seen.add(nxt)
        order.append(nxt - 1)
        cur = nxt

    return {
        'status': 'ready',
        'order': order,
        'objective': float(m.ObjVal),
        'mip_gap': float(m.MIPGap),
        'license': lic,
        'compute_s': round(time.perf_counter() - t0, 4),
    }
