from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.ops import transform

from core.adaptive_tasks import AdaptiveTaskConfig, build_adaptive_tasks
from core.alns import LatencyConfig, alns_risk
from core.db import connect
from core.ignition_sim import FWD, evaluate_route_robustness, sample_ignitions
from core.patrol import calculate, forest_zone_utm, map_data, terrain
from core.risk_field import RiskConfig, compute_risk_field
from core.web import patrol_model
from core.wind_profile import WindConfig, WindProfile


class _GridGraph:
    def __init__(self, target_utm: Any, surf: Any, cruise_ms: float, clearance_m: float, step_m: float = 30.0) -> None:
        self.p = {'cruise_ms': cruise_ms}
        self.nodes: dict[int, tuple[float, float, float]] = {}
        minx, miny, maxx, maxy = target_utm.buffer(120.0).bounds
        nid = 0
        y = miny
        while y <= maxy + 1e-6:
            x = minx
            while x <= maxx + 1e-6:
                z = float(surf.at(x, y) or 0.0) + clearance_m
                self.nodes[nid] = (float(x), float(y), z)
                nid += 1
                x += step_m
            y += step_m


def _run_adaptive_route(
    model: dict[str, Any],
    mdata: dict[str, Any],
    surf: Any,
    fzone: Any,
    target_poly: dict[str, Any],
    origin: list[float],
    hour_utc: str,
    seed: int,
    eff_p: dict[str, Any],
    graph: _GridGraph,
    *,
    risk_cfg: RiskConfig,
    latency_cfg: LatencyConfig,
    wind_mode: str = 'ecmwf_profile',
) -> dict[str, Any]:
    target_utm = transform(FWD, shape(target_poly))
    field = compute_risk_field(
        model,
        target_utm.buffer(200.0),
        terrain=surf,
        config=risk_cfg,
        forest_zone_utm=fzone,
    )
    w_prof = WindProfile(
        model.get('records', {}).get('M4', []),
        reference_time=hour_utc,
        config=WindConfig(mode=wind_mode),
    )
    clearance_m = float(eff_p.get('clearance_m', 70.0))
    swath_m = float(eff_p.get('swath_m', 90.0))
    task_set = build_adaptive_tasks(
        graph,
        target_utm,
        field,
        swath_m=swath_m,
        forest_zone_utm=fzone,
        terrain=surf,
        risk_config=risk_cfg,
        task_config=AdaptiveTaskConfig(min_cell_m=30.0, max_cell_m=max(120.0, swath_m * 1.5)),
    )
    origin_pt = transform(FWD, shape({'type': 'Point', 'coordinates': origin[:2]}))
    origin_xy = (origin_pt.x, origin_pt.y)
    st_list = []
    for idx, b in enumerate(mdata['bases'][:3]):
        coords = b.get('coordinates') or (b.get('geometry') or {}).get('coordinates')
        pt = transform(FWD, shape({'type': 'Point', 'coordinates': coords[:2]}))
        st_list.append({
            'id': b.get('id') or b.get('provider_id') or f'st-{idx}',
            'name': b.get('name', f'Station {idx}'),
            'xy': (pt.x, pt.y),
        })

    def _dist_fn(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
        return (math.hypot(a[0] - b[0], a[1] - b[1]), 0.0)

    alns_res = alns_risk(
        task_set.tasks,
        st_list,
        origin_xy,
        _dist_fn,
        cruise_ms=float(eff_p['cruise_ms']),
        battery_budget_s=float(eff_p['battery_budget_s']),
        mu_drain=1.0,
        station_service_s=float(eff_p.get('station_service_s', 120.0)),
        station_inventory=1,
        recharge_s=float(eff_p.get('recharge_s', 10800.0)),
        seed=seed,
        config=latency_cfg,
        wind_profile=w_prof,
        agl_m=float(eff_p.get('altitude_agl_m', clearance_m)),
    )

    coords_utm: list[list[float]] = [[origin_xy[0], origin_xy[1], float(surf.at(origin_xy[0], origin_xy[1]) or 0.0) + clearance_m]]
    dist_m = 0.0
    prev = coords_utm[0]
    for tidx in alns_res.get('order', []):
        t = task_set.tasks[tidx]
        for nid in t.get('nodes', []):
            x, y, z = graph.nodes[nid]
            cur_pt = [float(x), float(y), float(z)]
            dist_m += math.hypot(cur_pt[0] - prev[0], cur_pt[1] - prev[1])
            coords_utm.append(cur_pt)
            prev = cur_pt
    dist_m += math.hypot(coords_utm[0][0] - prev[0], coords_utm[0][1] - prev[1])
    coords_utm.append(list(coords_utm[0]))

    ev_obj = alns_res.get('eval')
    return {
        'method': 'alns_risk',
        'status': alns_res.get('status', 'ready'),
        'coordinates_utm': coords_utm,
        'distance_m': round(dist_m, 2),
        'time_s': round(float(ev_obj.total_time_s) if ev_obj else 0.0, 2),
        'recharges': int(ev_obj.recharges) if ev_obj else 0,
        'compute_s': round(float(alns_res.get('compute_s', 0.0)), 4),
    }


def main() -> None:
    proto = json.loads(Path('experiments/protocolo_congelado.json').read_text(encoding='utf-8'))
    conn = connect()
    cur = conn.execute('SELECT run_id FROM routing.aerial_models ORDER BY run_id DESC LIMIT 1').fetchone()
    model = patrol_model(conn, cur)
    model['_run_id'] = str(cur['run_id'])
    surf = terrain()
    fzone = forest_zone_utm(model)
    mdata = map_data(model)
    target_poly = mdata['demo_polygon']
    target_utm = transform(FWD, shape(target_poly))
    b0 = mdata['bases'][0]
    origin = b0.get('coordinates') or (b0.get('geometry') or {}).get('coordinates') or model['records']['M1'][0]['geometry']['coordinates']
    hour_utc = proto['hours_utc'][0]
    seed = int(proto['seed'])

    ref_field = compute_risk_field(
        model,
        target_utm.buffer(200.0),
        terrain=surf,
        config=RiskConfig(grid_cell_m=45.0, wind_layer_mode='ecmwf_profile'),
        forest_zone_utm=fzone,
    )
    ref_wind = WindProfile(model.get('records', {}).get('M4', []), reference_time=hour_utc)
    ignitions = sample_ignitions(ref_field, terrain=surf, n_ignitions=proto['n_ignitions'], seed=seed, wind_profile=ref_wind)

    req_grid = {
        'origin': origin,
        'target_polygon': target_poly,
        'time': hour_utc,
        'station_ids': [b.get('id') or b['provider_id'] for b in mdata['bases'][:3]],
        'seed': seed,
        'scenarios': 50,
        'preferences': {'drone': proto['default_drone'], 'station_inventory': 1},
    }
    res_grid = calculate(model, req_grid, terrain_override=surf)
    eff_p = res_grid['effective_profile']
    eff_r = float(res_grid['constraints'].get('effective_view_radius_m') or eff_p['view_radius_m'])
    graph = _GridGraph(target_utm, surf, float(eff_p['cruise_ms']), float(eff_p.get('clearance_m', 70.0)))

    def _eval(label: str, route: dict[str, Any]) -> dict[str, Any]:
        ev = evaluate_route_robustness(
            route,
            ignitions,
            ref_field,
            terrain=surf,
            effective_view_r=eff_r,
            cruise_ms=eff_p['cruise_ms'],
            battery_wh=eff_p.get('battery_wh', 77.0),
            battery_budget_s=eff_p['battery_budget_s'],
            missed_penalty_s=proto['missed_ignition_penalty_s'],
            cvar_alpha=proto['cvar_alpha'],
        )
        return {
            'step': label,
            'E_D_s': ev['E_D_s'],
            'CVaR_95_s': ev['CVaR_95_s'],
            'detected_pct': ev['detected_pct'],
            'risk_covered_T15_pct': ev['risk_covered_T15_pct'],
            'recharges': ev['recharges'],
            'energy_wh': ev['energy_wh'],
            'time_s': ev['time_s'],
            'compute_s': ev['compute_s'],
        }

    ablation_rows = [
        _eval('1_grid_uniform', res_grid['routes']['dijkstra_distance']),
        _eval('2_adaptive_tasks_nn', _run_adaptive_route(
            model, mdata, surf, fzone, target_poly, origin, hour_utc, seed, eff_p, graph,
            risk_cfg=RiskConfig(grid_cell_m=45.0, wind_layer_mode='uniform_m4'),
            latency_cfg=LatencyConfig(alns_iterations=0),
            wind_mode='uniform_m4',
        )),
        _eval('3_adaptive_plus_alns_latency', _run_adaptive_route(
            model, mdata, surf, fzone, target_poly, origin, hour_utc, seed, eff_p, graph,
            risk_cfg=RiskConfig(grid_cell_m=45.0, wind_layer_mode='uniform_m4'),
            latency_cfg=LatencyConfig(alns_iterations=120),
            wind_mode='uniform_m4',
        )),
        _eval('4_adaptive_plus_alns_plus_ecmwf_wind', _run_adaptive_route(
            model, mdata, surf, fzone, target_poly, origin, hour_utc, seed, eff_p, graph,
            risk_cfg=RiskConfig(grid_cell_m=45.0, wind_layer_mode='ecmwf_profile'),
            latency_cfg=LatencyConfig(alns_iterations=120),
            wind_mode='ecmwf_profile',
        )),
        _eval('5_adaptive_plus_alns_wind_discounted', _run_adaptive_route(
            model, mdata, surf, fzone, target_poly, origin, hour_utc, seed, eff_p, graph,
            risk_cfg=RiskConfig(grid_cell_m=45.0, wind_layer_mode='ecmwf_profile'),
            latency_cfg=LatencyConfig(alns_iterations=120, objective_mode='discounted', kappa_discount=0.001),
            wind_mode='ecmwf_profile',
        )),
    ]

    Path('results').mkdir(parents=True, exist_ok=True)
    with Path('results/ablation.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(ablation_rows[0].keys()))
        w.writeheader()
        w.writerows(ablation_rows)

    sens_grid = {
        'a4_unknown_pct': [5.0, 10.0, 20.0],
        'beta1_slope': [0.25, 0.50, 1.00],
        'beta2_wind': [0.04, 0.08, 0.16],
        'urban_decay_m': [150.0, 300.0, 600.0],
        'normalization_mode': ['max', 'log', 'quantile'],
        'lambda1_risk': [0.5, 1.0, 2.0],
        'lambda2_recharge': [60.0, 120.0, 240.0],
        'kappa_discount': [0.0, 0.001, 0.005],
    }
    sens_rows: list[dict[str, Any]] = []
    for param, values in sens_grid.items():
        for val in values:
            rc = RiskConfig(grid_cell_m=45.0, wind_layer_mode='ecmwf_profile')
            lc = LatencyConfig(alns_iterations=80)
            if param == 'a4_unknown_pct':
                rc = RiskConfig(grid_cell_m=45.0, wind_layer_mode='ecmwf_profile', a4_unknown_pct=float(val))
            elif param == 'beta1_slope':
                rc = RiskConfig(grid_cell_m=45.0, wind_layer_mode='ecmwf_profile', beta1_slope=float(val))
            elif param == 'beta2_wind':
                rc = RiskConfig(grid_cell_m=45.0, wind_layer_mode='ecmwf_profile', beta2_wind=float(val))
            elif param == 'urban_decay_m':
                rc = RiskConfig(grid_cell_m=45.0, wind_layer_mode='ecmwf_profile', urban_decay_m=float(val))
            elif param == 'normalization_mode':
                rc = RiskConfig(grid_cell_m=45.0, wind_layer_mode='ecmwf_profile', normalization_mode=str(val))
            elif param == 'lambda1_risk':
                lc = LatencyConfig(alns_iterations=80, lambda1_risk=float(val))
            elif param == 'lambda2_recharge':
                lc = LatencyConfig(alns_iterations=80, lambda2_recharge=float(val))
            elif param == 'kappa_discount':
                mode = 'discounted' if float(val) > 0.0 else 'linear'
                lc = LatencyConfig(alns_iterations=80, objective_mode=mode, kappa_discount=float(val))

            r_s = _run_adaptive_route(
                model, mdata, surf, fzone, target_poly, origin, hour_utc, seed, eff_p, graph,
                risk_cfg=rc, latency_cfg=lc, wind_mode='ecmwf_profile',
            )
            ev = evaluate_route_robustness(
                r_s,
                ignitions,
                ref_field,
                terrain=surf,
                effective_view_r=eff_r,
                cruise_ms=eff_p['cruise_ms'],
                battery_wh=eff_p.get('battery_wh', 77.0),
                battery_budget_s=eff_p['battery_budget_s'],
                missed_penalty_s=proto['missed_ignition_penalty_s'],
                cvar_alpha=proto['cvar_alpha'],
            )
            sens_rows.append({
                'parameter': param,
                'value': val,
                'E_D_s': ev['E_D_s'],
                'CVaR_95_s': ev['CVaR_95_s'],
                'detected_pct': ev['detected_pct'],
                'risk_covered_T15_pct': ev['risk_covered_T15_pct'],
                'energy_wh': ev['energy_wh'],
                'compute_s': ev['compute_s'],
            })

    with Path('results/sensitivity.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=list(sens_rows[0].keys()))
        w.writeheader()
        w.writerows(sens_rows)
    print(f'Wrote {len(ablation_rows)} ablation rows and {len(sens_rows)} sensitivity rows.')


if __name__ == '__main__':
    main()
