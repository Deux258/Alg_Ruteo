"""Robust ignition simulation, CVaR_95 evaluation, and frozen protocol runner (Etapa 5).

Reuses the exact IR cone + LOS detection rule from ``core/patrol.py``
(``math.dist(xy, fire_xy) <= effective_view_r and terrain.visible(...)``)
across N=1000 reproducible ignitions sampled from R(x, y).

CLI:
    python -m core.ignition_sim --compare
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib
from typing import Any

import numpy as np

from core.aerial_data import FWD
from core.risk_field import RiskConfig, RiskField, compute_risk_field
from core.wind_profile import WindConfig, WindProfile, sample_wind_perturbation


@dataclass(frozen=True)
class IgnitionEvent:
    """Single stochastic ignition scenario."""

    id: int
    x_utm: float
    y_utm: float
    z_m: float
    t_ign_s: float
    wind_speed_ms: float
    wind_direction_deg: float
    observable: bool


def wilson_ci95(successes: int, total: int) -> tuple[float, float]:
    """95% Wilson score confidence interval for binomial proportion (in [0, 1])."""
    if total <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = successes / total
    denom = 1.0 + (z * z) / total
    center = (p + (z * z) / (2.0 * total)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * total)) / total)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def sample_ignitions(
    field: RiskField,
    terrain: Any = None,
    n_ignitions: int = 1000,
    seed: int = 20261104,
    wind_profile: WindProfile | None = None,
    wind_config: WindConfig | None = None,
    max_ign_time_s: float = 1800.0,
) -> list[IgnitionEvent]:
    """Sample ``n_ignitions`` locations ~ R(x,y) inside ``forest_mask`` with perturbed wind."""
    rng = np.random.default_rng(seed)
    iy_idx, ix_idx = np.where(field.forest_mask)
    if len(iy_idx) == 0:
        return []
    weights = np.maximum(0.0, field.values[iy_idx, ix_idx])
    w_sum = float(np.sum(weights))
    probs = (weights / w_sum) if w_sum > 0.0 else (np.ones(len(weights)) / len(weights))

    chosen = rng.choice(len(iy_idx), size=n_ignitions, replace=True, p=probs)
    half_cell = 0.5 * field.cell_m
    events: list[IgnitionEvent] = []
    for eid, k in enumerate(chosen):
        iy, ix = int(iy_idx[k]), int(ix_idx[k])
        x = float(field.xs[ix] + rng.uniform(-half_cell, half_cell))
        y = float(field.ys[iy] + rng.uniform(-half_cell, half_cell))
        z = float(terrain.at(x, y) or 0.0) if terrain is not None else 0.0
        t_ign = float(rng.uniform(0.0, max_ign_time_s))
        base_w = wind_profile.at(t_ign) if wind_profile is not None else {'wind_speed_ms': 2.0, 'wind_direction_deg': 270.0}
        ws, wd = sample_wind_perturbation(rng, base_w['wind_speed_ms'], base_w['wind_direction_deg'], config=wind_config)
        obs = bool(field.observable[iy, ix])
        events.append(IgnitionEvent(eid, x, y, z, t_ign, ws, wd, obs))
    return events


def route_timeline_utm(route: dict[str, Any], cruise_ms: float = 10.0) -> list[tuple[float, float, float, float]]:
    """Build [(x_utm, y_utm, z_m, time_s), ...] from a route's UTM coordinates & stops."""
    coords = route.get('coordinates_utm') or []
    if not coords and route.get('coordinates'):
        coords = [[*FWD(c[0], c[1]), c[2] if len(c) > 2 else 60.0] for c in route['coordinates']]
    if not coords:
        return []
    total_time = float(route.get('time_s') or 0.0)
    dists = [0.0]
    for a, b in zip(coords, coords[1:]):
        dists.append(dists[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    total_dist = max(1e-6, dists[-1])
    if total_time <= 0.0:
        total_time = total_dist / max(1.0, cruise_ms)
    return [(float(c[0]), float(c[1]), float(c[2] if len(c) > 2 else 60.0), total_time * (d / total_dist)) for c, d in zip(coords, dists)]


def detect_fire_along_trajectory(
    timeline_utm: list[tuple[float, float, float, float]],
    fire_xyz: tuple[float, float, float],
    effective_view_r: float,
    terrain: Any,
    t_ign_s: float = 0.0,
) -> float | None:
    """Reuse simulate()'s IR cone + LOS check: returns first detection time >= t_ign_s or None."""
    fx, fy, fz = fire_xyz
    for x, y, z, t_s in timeline_utm:
        if t_s < t_ign_s:
            continue
        if math.hypot(x - fx, y - fy) <= effective_view_r:
            if terrain is None or terrain.visible([x, y, z], [fx, fy, fz]):
                return t_s
    return None


def evaluate_route_robustness(
    route: dict[str, Any],
    ignitions: list[IgnitionEvent],
    field: RiskField,
    terrain: Any = None,
    effective_view_r: float = 100.0,
    cruise_ms: float = 10.0,
    battery_wh: float = 77.0,
    battery_budget_s: float = 1200.0,
    missed_penalty_s: float = 14400.0,
    gamma_cvar: float = 0.0,
    cvar_alpha: float = 0.95,
) -> dict[str, Any]:
    """Evaluate E[D], CVaR_95(D), risk-covered curves, energy, and Wilson survival CI."""
    tl = route_timeline_utm(route, cruise_ms=cruise_ms)
    delays: list[float] = []
    detected_count = 0

    for ign in ignitions:
        if not ign.observable:
            delays.append(missed_penalty_s)
            continue
        t_det = detect_fire_along_trajectory(tl, (ign.x_utm, ign.y_utm, ign.z_m), effective_view_r, terrain, t_ign_s=ign.t_ign_s)
        if t_det is None:
            delays.append(missed_penalty_s)
        else:
            detected_count += 1
            delays.append(max(0.0, t_det - ign.t_ign_s))

    arr = np.sort(np.array(delays, dtype=float)) if delays else np.array([missed_penalty_s])
    e_d = float(np.mean(arr))
    tail_start = min(len(arr) - 1, int(math.floor(cvar_alpha * len(arr))))
    cvar_95 = float(np.mean(arr[tail_start:]))

    # Cumulative risk-covered vs flight time (grid cells covered within effective_view_r)
    obs_y, obs_x = np.where(field.forest_mask & field.observable)
    cell_x = field.xs[obs_x]
    cell_y = field.ys[obs_y]
    cell_r = field.values[obs_y, obs_x]
    total_obs_r = float(np.sum(cell_r)) or 1.0
    first_seen = np.full(len(cell_r), math.inf, dtype=float)
    r2 = effective_view_r * effective_view_r
    for x, y, _, t_s in tl:
        d2 = (cell_x - x) ** 2 + (cell_y - y) ** 2
        hit = (d2 <= r2) & (t_s < first_seen)
        first_seen[hit] = t_s

    def _cov_at(t_limit: float) -> float:
        return round(100.0 * float(np.sum(cell_r[first_seen <= t_limit])) / total_obs_r, 2)

    curve = [{'t_min': m, 'risk_covered_pct': _cov_at(m * 60.0)} for m in (5, 10, 15, 20, 30, 45, 60)]
    time_s = float(route.get('time_s') or 0.0)
    stops = route.get('stops') or []
    recharges = len(stops)
    energy_wh = round((time_s / max(1.0, battery_budget_s)) * battery_wh, 2)

    resil = (route.get('resilience') or {}).get('value')
    surv_p = float(resil) if resil is not None else 0.98
    ci_lo, ci_hi = wilson_ci95(int(round(surv_p * 1000)), 1000)

    return {
        'method': route.get('method', 'unknown'),
        'status': route.get('status', 'unknown'),
        'E_D_s': round(e_d, 2),
        'CVaR_95_s': round(cvar_95, 2),
        'robust_obj_s': round(e_d + gamma_cvar * cvar_95, 2),
        'detected_pct': round(100.0 * detected_count / max(1, len(ignitions)), 2),
        'risk_covered_T15_pct': _cov_at(900.0),
        'risk_covered_T30_pct': _cov_at(1800.0),
        'risk_curve': curve,
        'recharges': recharges,
        'energy_wh': energy_wh,
        'time_s': round(time_s, 2),
        'distance_m': round(float(route.get('distance_m') or 0.0), 2),
        'drone_survival_pct': round(100.0 * surv_p, 2),
        'survival_wilson_ci95': [round(100.0 * ci_lo, 2), round(100.0 * ci_hi, 2)],
        'unobservable_risk_pct': round(field.unobservable_risk_pct, 2),
        'compute_s': round(float(route.get('compute_s') or 0.0), 4),
    }


def _write_curve_png(curves_by_method: dict[str, list[dict[str, float]]], out_path: Path) -> None:
    """Render a clean cumulative risk-covered vs time PNG without external plotting libs."""
    w, h = 640, 360
    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[:, :, :3] = [15, 23, 42]
    img[:, :, 3] = 255
    pad_l, pad_r, pad_t, pad_b = 50, 30, 30, 40
    pw, ph = w - pad_l - pad_r, h - pad_t - pad_b
    img[pad_t:pad_t + ph, pad_l:pad_l + 2, :3] = [148, 163, 184]
    img[pad_t + ph - 2:pad_t + ph, pad_l:pad_l + pw, :3] = [148, 163, 184]

    palette = {
        'dijkstra_distance': (148, 163, 184),
        'dijkstra_weighted': (56, 189, 248),
        'gurobi': (168, 85, 247),
        'annealing': (234, 179, 8),
        'alns_risk': (34, 197, 94),
    }
    for method, pts in curves_by_method.items():
        rgb = palette.get(method, (244, 63, 94))
        coords = [(pad_l + int((p['t_min'] / 60.0) * pw), pad_t + ph - int((p['risk_covered_pct'] / 100.0) * ph)) for p in pts]
        for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            for s in range(steps + 1):
                px = int(round(x0 + (x1 - x0) * s / steps))
                py = int(round(y0 + (y1 - y0) * s / steps))
                if 0 <= py < h and 0 <= px < w:
                    img[max(0, py - 1):min(h, py + 2), max(0, px - 1):min(w, px + 2), :3] = rgb

    raw_rows = b''.join(b'\x00' + img[y].tobytes() for y in range(h))
    compressed = zlib.compress(raw_rows, level=6)
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(png)


def run_compare_cli(protocol_path: Path = Path('experiments/protocolo_congelado.json')) -> dict[str, Any]:
    """Execute the frozen comparison protocol and export CSVs + curve PNG."""
    from shapely.geometry import box, shape
    from shapely.ops import transform
    from core.db import connect
    from core.patrol import calculate, defaults, forest_zone_utm, terrain
    from core.web import patrol_model

    proto_bytes = protocol_path.read_bytes()
    proto_hash = hashlib.sha256(proto_bytes).hexdigest()
    proto = json.loads(proto_bytes.decode('utf-8'))

    conn = connect()
    cur = conn.execute('SELECT run_id FROM routing.aerial_models ORDER BY run_id DESC LIMIT 1').fetchone()
    model = patrol_model(conn, cur)
    model['_run_id'] = str(cur['run_id'])
    surf = terrain()
    fzone = forest_zone_utm(model)

    # Select a representative ~1.2 km^2 Valparaiso urban-forest interface sector inside flight_geometry
    from core.patrol import map_data
    mdata = map_data(model)
    target_poly = mdata['demo_polygon']
    target_utm = transform(FWD, shape(target_poly))
    b0 = mdata['bases'][0]
    origin = b0.get('coordinates') or (b0.get('geometry') or {}).get('coordinates') or model['records']['M1'][0]['geometry']['coordinates']

    field = compute_risk_field(model, target_utm.buffer(200.0), terrain=surf, config=RiskConfig(grid_cell_m=45.0, wind_layer_mode='ecmwf_profile'), forest_zone_utm=fzone)
    w_prof = WindProfile(model.get('records', {}).get('M4', []), reference_time=proto['hours_utc'][0])
    ignitions = sample_ignitions(field, terrain=surf, n_ignitions=proto['n_ignitions'], seed=proto['seed'], wind_profile=w_prof)

    rows_out: list[dict[str, Any]] = []
    curves_v1: dict[str, list[dict[str, float]]] = {}

    for inv in proto['station_inventory_variants']:
        req_grid = {
            'origin': origin,
            'target_polygon': target_poly,
            'time': proto['hours_utc'][0],
            'station_ids': [b.get('id') or b['provider_id'] for b in mdata['bases'][:3]],
            'seed': proto['seed'],
            'scenarios': 50,
            'preferences': {'drone': proto['default_drone'], 'station_inventory': inv},
        }
        res_grid = calculate(model, req_grid, terrain_override=surf)
        req_rrpp = dict(req_grid, mode='risk_adaptive')
        res_rrpp = calculate(model, req_rrpp, terrain_override=surf)

        all_routes = dict(res_grid['routes'])
        if 'alns_risk' in res_rrpp['routes']:
            all_routes['alns_risk'] = res_rrpp['routes']['alns_risk']

        eff_p = res_rrpp['effective_profile']
        eff_r = float(res_rrpp['constraints'].get('effective_view_radius_m') or eff_p['view_radius_m'])
        for method in proto['methods']:
            if method not in all_routes:
                continue
            ev = evaluate_route_robustness(
                all_routes[method],
                ignitions,
                field,
                terrain=surf,
                effective_view_r=eff_r,
                cruise_ms=eff_p['cruise_ms'],
                battery_wh=eff_p.get('battery_wh', 77.0),
                battery_budget_s=eff_p['battery_budget_s'],
                missed_penalty_s=proto['missed_ignition_penalty_s'],
                cvar_alpha=proto['cvar_alpha'],
            )
            ev['station_inventory'] = inv
            ev['run_id'] = str(cur['run_id'])
            ev['protocol_sha256'] = proto_hash[:16]
            rows_out.append(ev)
            if inv == 1:
                curves_v1[method] = ev['risk_curve']

    Path('results').mkdir(parents=True, exist_ok=True)
    csv_path = Path('results/comparison.csv')
    fields = ['station_inventory', 'method', 'status', 'E_D_s', 'CVaR_95_s', 'detected_pct', 'risk_covered_T15_pct', 'risk_covered_T30_pct', 'recharges', 'energy_wh', 'time_s', 'distance_m', 'drone_survival_pct', 'survival_wilson_ci95', 'unobservable_risk_pct', 'compute_s', 'run_id', 'protocol_sha256']
    with csv_path.open('w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows_out)

    _write_curve_png(curves_v1, Path('evidencia/fase5_risk_curve.png'))
    summary = {'protocol_sha256': proto_hash, 'run_id': str(cur['run_id']), 'n_ignitions': len(ignitions), 'rows': rows_out}
    Path('results/comparison_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RRPP Robust Ignition Simulation (Etapa 5)')
    parser.add_argument('--compare', action='store_true', help='Run frozen protocol comparison and export results/comparison.csv')
    args = parser.parse_args()
    if args.compare:
        out = run_compare_cli()
        print(json.dumps(out, ensure_ascii=False, indent=2))
