"""Rolling-horizon replanning and k=2 edge-disjoint return corridors (Etapa 6).

Supports mid-mission triggers:
    - 'new_a2_firms' (synthetic FIRMS hotspot, explicitly labeled synthetic)
    - 'wind_shift'   (updated wind speed/direction)
    - 'blocked_edge' (forbidden task/corridor exclusion)
    - 'drone_fault'  (immediate return to nearest reachable M1)
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import time
from typing import Any

from core.alns import LatencyConfig, alns_risk
from core.wind_profile import WindProfile


@dataclass(frozen=True)
class ReplanTrigger:
    """Mid-mission disturbance triggering rolling-horizon repair."""

    kind: str  # 'new_a2_firms' | 'wind_shift' | 'blocked_edge' | 'drone_fault'
    elapsed_s: float
    current_xy: tuple[float, float]
    remaining_battery_s: float
    synthetic_firms_xy: tuple[float, float] | None = None
    wind_speed_ms: float | None = None
    wind_direction_deg: float | None = None
    blocked_task_ids: tuple[int, ...] = ()


def replan_mission(
    remaining_tasks: list[dict[str, Any]],
    stations: list[dict[str, Any]],
    trigger: ReplanTrigger,
    dist_fn: Any,
    cruise_ms: float = 10.0,
    battery_budget_s: float = 1200.0,
    mu_drain: float = 1.0,
    station_service_s: float = 120.0,
    station_inventory: int = 1,
    recharge_s: float = 10800.0,
    seed: int = 20261104,
    time_limit_s: float = 0.8,
) -> dict[str, Any]:
    """Repair remaining patrol tasks in < 1 s from the active mission state."""
    t0 = time.perf_counter()

    if trigger.kind == 'drone_fault':
        nearest = min(
            stations,
            key=lambda s: math.hypot(s['xy'][0] - trigger.current_xy[0], s['xy'][1] - trigger.current_xy[1]),
        ) if stations else {'id': 'origin', 'xy': trigger.current_xy, 'name': 'Origen'}
        return {
            'status': 'abort_to_station',
            'trigger': trigger.kind,
            'target_station': nearest,
            'order': [],
            'compute_s': round(time.perf_counter() - t0, 4),
        }

    # Clone remaining tasks and apply trigger updates
    blocked = set(trigger.blocked_task_ids)
    updated: list[dict[str, Any]] = []
    for t in remaining_tasks:
        if t.get('id') in blocked:
            continue
        tc = dict(t)
        if trigger.kind == 'new_a2_firms' and trigger.synthetic_firms_xy is not None:
            fx, fy = trigger.synthetic_firms_xy
            cx, cy = tc['centroid_utm']
            d2 = (cx - fx) ** 2 + (cy - fy) ** 2
            boost = 0.5 * math.exp(-d2 / (2.0 * 250.0 * 250.0))
            tc['prize'] = float(tc.get('prize', 1.0)) * (1.0 + boost)
            tc['synthetic_firms_boost'] = True
        updated.append(tc)

    if not updated:
        return {'status': 'empty', 'trigger': trigger.kind, 'order': [], 'compute_s': round(time.perf_counter() - t0, 4)}

    wind_prof = None
    if trigger.wind_speed_ms is not None and trigger.wind_direction_deg is not None:
        wind_prof = WindProfile([{'valid_at': '2026-10-19T00:00:00+00:00', 'wind_speed_ms': trigger.wind_speed_ms, 'wind_direction_deg': trigger.wind_direction_deg}])

    cfg = LatencyConfig(alns_iterations=80, alns_time_limit_s=max(0.1, float(time_limit_s)))
    res = alns_risk(
        updated,
        stations,
        trigger.current_xy,
        dist_fn,
        cruise_ms=cruise_ms,
        battery_budget_s=max(120.0, float(battery_budget_s)),
        mu_drain=mu_drain,
        station_service_s=station_service_s,
        station_inventory=station_inventory,
        recharge_s=recharge_s,
        seed=seed,
        config=cfg,
        wind_profile=wind_prof,
    )
    return {
        'status': res['status'],
        'trigger': trigger.kind,
        'order': [updated[i].get('id', i) for i in res['order']],
        'objective': res['best_objective'],
        'initial_objective': res['initial_objective'],
        'improvement_pct': res['improvement_pct'],
        'compute_s': round(time.perf_counter() - t0, 4),
    }


def redundant_return_corridors(
    graph: Any,
    source_node: int,
    station_nodes: list[int],
    k: int = 2,
) -> dict[str, Any]:
    """Verify k=2 edge-disjoint return paths from ``source_node`` to M1 stations (Edmonds-Karp)."""
    if not station_nodes or source_node not in graph.nodes:
        return {'k_requested': k, 'edge_disjoint_paths': 0, 'resilient_k2': False}

    cap: dict[Any, dict[Any, int]] = {}
    for e in graph.edges.values():
        u, v = e['source'], e['target']
        cap.setdefault(u, {})[v] = cap.get(u, {}).get(v, 0) + 1
        cap.setdefault(v, {}).setdefault(u, 0)

    super_sink = '__M1_SINK__'
    cap.setdefault(super_sink, {})
    for sn in station_nodes:
        if sn in graph.nodes:
            cap.setdefault(sn, {})[super_sink] = k
            cap[super_sink].setdefault(sn, 0)

    flow = 0
    while flow < k:
        parent: dict[Any, Any] = {source_node: None}
        q = deque([source_node])
        found = False
        while q and not found:
            u = q.popleft()
            for v, c in cap.get(u, {}).items():
                if c > 0 and v not in parent:
                    parent[v] = u
                    if v == super_sink:
                        found = True
                        break
                    q.append(v)
        if not found:
            break
        flow += 1
        v = super_sink
        while v != source_node:
            u = parent[v]
            cap[u][v] -= 1
            cap[v][u] = cap[v].get(u, 0) + 1
            v = u

    return {
        'k_requested': k,
        'edge_disjoint_paths': flow,
        'resilient_k2': flow >= k,
    }
