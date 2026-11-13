"""Risk-guided adaptive quadtree discretization and task generation (Etapa 3).

Replaces uniform boustrophedon grids under ``mode="risk_adaptive"`` while
preserving the exact ``list[dict(nodes=[...])]`` contract consumed by
``fixed_route()`` and ``oriented_tasks()`` in ``core/patrol.py``.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

from core.risk_field import RiskConfig, RiskField


@dataclass(frozen=True)
class AdaptiveTaskConfig:
    """Configuration for quadtree risk discretization and variable-density sweeps."""

    min_cell_m: float = 30.0          # >= Copernicus GLO-30 native resolution (~30 m)
    max_cell_m: float = 480.0
    max_depth: int = 4
    split_quantile: float = 0.65      # Subdivide cells whose max/mean R exceeds threshold
    min_cell_risk_to_split: float = 0.25
    tau0_s: float = 3600.0            # Base revisit period tau_0 (s)
    alpha_revisit: float = 2.0        # tau_i = tau_0 / (1 + alpha * r_i / r_mean)
    high_risk_quantile: float = 0.70  # Cells above this get denser strips & terrain/wind alignment
    min_spacing_factor: float = 0.45  # Densest strip spacing = min_spacing_factor * swath_m
    max_tasks_cap: int = 120          # Respect MILP/ALNS scalability


@dataclass
class AdaptiveTaskSet:
    """Container of adaptive patrol tasks plus spatial/observability diagnostics."""

    tasks: list[dict[str, Any]]
    cells: list[dict[str, Any]]
    unobservable_risk: float
    total_risk: float
    track_density_spearman: float
    warnings: list[str]


def _cell_risk_stats(field: RiskField, geom: Polygon) -> tuple[float, float, float]:
    """Return (integral_r, mean_r, max_r) of ``field`` inside ``geom``."""
    minx, miny, maxx, maxy = geom.bounds
    ix0 = max(0, int(math.floor((minx - float(field.xs[0])) / field.cell_m)))
    ix1 = min(len(field.xs) - 1, int(math.ceil((maxx - float(field.xs[0])) / field.cell_m)))
    iy0 = max(0, int(math.floor((miny - float(field.ys[0])) / field.cell_m)))
    iy1 = min(len(field.ys) - 1, int(math.ceil((maxy - float(field.ys[0])) / field.cell_m)))
    vals: list[float] = []
    for iy in range(iy0, iy1 + 1):
        cy = float(field.ys[iy])
        for ix in range(ix0, ix1 + 1):
            cx = float(field.xs[ix])
            if geom.contains(Point(cx, cy)) or geom.intersects(Point(cx, cy)):
                vals.append(float(field.values[iy, ix]))
    if not vals:
        c = geom.centroid
        v = field.at(c.x, c.y)
        return v * float(geom.area), v, v
    mean_v = float(np.mean(vals))
    max_v = float(np.max(vals))
    return mean_v * float(geom.area), mean_v, max_v


def _terrain_ridge_angle_deg(terrain: Any, x: float, y: float, step: float = 30.0) -> float:
    """Dominant contour/ridge orientation (degrees) from DSM gradient."""
    if terrain is None:
        return 0.0
    zc = terrain.at(x, y)
    zx_p = terrain.at(x + step, y)
    zx_m = terrain.at(x - step, y)
    zy_p = terrain.at(x, y + step)
    zy_m = terrain.at(x, y - step)
    if zc is None:
        return 0.0
    dz_dx = ((zx_p if zx_p is not None else zc) - (zx_m if zx_m is not None else zc)) / (2.0 * step)
    dz_dy = ((zy_p if zy_p is not None else zc) - (zy_m if zy_m is not None else zc)) / (2.0 * step)
    if math.hypot(dz_dx, dz_dy) < 1e-5:
        return 0.0
    # Contour direction perpendicular to gradient
    return math.degrees(math.atan2(dz_dx, -dz_dy))


def _boustrophedon_points_in_poly(
    poly: Polygon,
    spacing_m: float,
    angle_deg: float,
) -> list[tuple[float, float]]:
    """Generate clipped boustrophedon waypoints covering ``poly`` at ``angle_deg``."""
    from shapely.affinity import rotate

    c = poly.centroid
    rot_poly = rotate(poly, -angle_deg, origin=c)
    minx, miny, maxx, maxy = rot_poly.bounds
    step = max(15.0, float(spacing_m))
    ys = np.arange(miny + 0.5 * step, maxy, step)
    if len(ys) == 0:
        ys = np.array([0.5 * (miny + maxy)])

    pts_rot: list[tuple[float, float]] = []
    for idx, yv in enumerate(ys):
        line = LineString([(minx - 10.0, float(yv)), (maxx + 10.0, float(yv))])
        seg = rot_poly.intersection(line)
        if seg.is_empty:
            continue
        coords: list[tuple[float, float]] = []
        if seg.geom_type == 'LineString':
            coords = list(seg.coords)
        elif seg.geom_type == 'MultiLineString':
            for part in seg.geoms:
                coords.extend(part.coords)
        elif seg.geom_type == 'Point':
            coords = [(seg.x, seg.y)]
        if not coords:
            continue
        coords.sort(key=lambda p: p[0])
        if idx % 2 == 1:
            coords.reverse()
        pts_rot.extend([(coords[0][0], coords[0][1]), (coords[-1][0], coords[-1][1])])

    if not pts_rot:
        return [(c.x, c.y)]

    # Rotate back to EPSG:32719
    rad = math.radians(angle_deg)
    ca, sa = math.cos(rad), math.sin(rad)
    out: list[tuple[float, float]] = []
    for px, py in pts_rot:
        dx, dy = px - c.x, py - c.y
        out.append((c.x + dx * ca - dy * sa, c.y + dx * sa + dy * ca))
    return out


def _spearman_corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or np.std(a) == 0.0 or np.std(b) == 0.0:
        return 0.0
    try:
        from scipy.stats import spearmanr
        val = float(spearmanr(a, b).statistic)
        return val if math.isfinite(val) else 0.0
    except Exception:
        ra = np.argsort(np.argsort(a, kind='mergesort')).astype(float)
        rb = np.argsort(np.argsort(b, kind='mergesort')).astype(float)
        ra -= np.mean(ra)
        rb -= np.mean(rb)
        denom = float(np.sqrt(np.sum(ra * ra) * np.sum(rb * rb)))
        return float(np.sum(ra * rb) / denom) if denom > 0 else 0.0


def build_adaptive_tasks(
    graph: Any,
    target_utm: Polygon,
    field: RiskField,
    swath_m: float,
    a3_geoms_utm: list[Any] | None = None,
    forest_zone_utm: Any = None,
    terrain: Any = None,
    risk_config: RiskConfig | None = None,
    task_config: AdaptiveTaskConfig | None = None,
    wind_direction_deg: float | None = None,
    headwind_align: bool = False,
) -> AdaptiveTaskSet:
    """Build risk-adaptive quadtree patrol tasks clipped to allowed forest area.

    Each returned task dictionary includes ``nodes`` (compatible with
    ``core.patrol.fixed_route`` and ``oriented_tasks``) plus ``prize`` r_i,
    ``revisit_s`` tau_i, ``service_s`` s_i, and ``risk_density``.
    """
    rcfg = risk_config or field.config
    tcfg = task_config or AdaptiveTaskConfig(min_cell_m=max(30.0, float(rcfg.min_cell_m)))
    min_cell = max(30.0, float(rcfg.min_cell_m), float(tcfg.min_cell_m))
    warnings: list[str] = []

    allowed = target_utm
    if forest_zone_utm is not None and not forest_zone_utm.is_empty:
        clipped = allowed.intersection(forest_zone_utm)
        if not clipped.is_empty:
            allowed = clipped
        else:
            warnings.append('target_polygon no intersecta forest_zone_utm; se usa target completo.')

    a3_union = unary_union([g for g in (a3_geoms_utm or []) if g is not None and not g.is_empty]) if a3_geoms_utm else None
    unobs_risk = 0.0
    if a3_union is not None and not a3_union.is_empty:
        in_a3 = allowed.intersection(a3_union)
        if not in_a3.is_empty:
            unobs_risk = field.integrate(in_a3)
        allowed = allowed.difference(a3_union)

    if allowed.is_empty:
        return AdaptiveTaskSet(tasks=[], cells=[], unobservable_risk=unobs_risk, total_risk=unobs_risk, track_density_spearman=0.0, warnings=warnings + ['Área permitida vacía tras excluir A3/urbano.'])

    # Quadtree subdivision guided by R
    minx, miny, maxx, maxy = allowed.bounds
    span = max(maxx - minx, maxy - miny, min_cell)
    root = box(minx, miny, minx + span, miny + span)

    leaves: list[Polygon] = []
    queue: list[tuple[Polygon, int]] = [(root, 0)]
    while queue:
        cell, depth = queue.pop(0)
        inter = cell.intersection(allowed)
        if inter.is_empty or inter.area < 1.0:
            continue
        side = max(cell.bounds[2] - cell.bounds[0], cell.bounds[3] - cell.bounds[1])
        _, mean_r, max_r = _cell_risk_stats(field, inter)
        should_split = (
            depth < tcfg.max_depth
            and side * 0.5 >= min_cell
            and (max_r >= tcfg.min_cell_risk_to_split or mean_r >= 0.5 * tcfg.min_cell_risk_to_split)
            and (len(leaves) + len(queue) + 4 <= tcfg.max_tasks_cap)
        )
        if should_split:
            cx = 0.5 * (cell.bounds[0] + cell.bounds[2])
            cy = 0.5 * (cell.bounds[1] + cell.bounds[3])
            bx0, by0, bx1, by1 = cell.bounds
            for sub in (
                box(bx0, by0, cx, cy),
                box(cx, by0, bx1, cy),
                box(bx0, cy, cx, by1),
                box(cx, cy, bx1, by1),
            ):
                queue.append((sub, depth + 1))
        else:
            if inter.geom_type == 'Polygon':
                leaves.append(inter)
            elif inter.geom_type in ('MultiPolygon', 'GeometryCollection'):
                for g in inter.geoms:
                    if g.geom_type == 'Polygon' and g.area >= 1.0:
                        leaves.append(g)

    if not leaves:
        leaves = [allowed]

    # Compute prizes r_i and variable strip spacing
    cell_stats = [_cell_risk_stats(field, leaf) for leaf in leaves]
    prizes = [st[0] for st in cell_stats]
    mean_ris = [st[1] for st in cell_stats]
    r_bar = max(1e-9, float(np.mean(prizes)))
    q_hi = float(np.quantile(mean_ris, tcfg.high_risk_quantile)) if len(mean_ris) > 1 else 0.5

    tasks: list[dict[str, Any]] = []
    cells_meta: list[dict[str, Any]] = []
    densities: list[float] = []
    cell_mean_rs: list[float] = []

    cruise_ms = float(getattr(graph, 'p', {}).get('cruise_ms', 10.0))
    from shapely import STRtree as _STRtree
    node_ids = [
        nid for nid, coords in graph.nodes.items()
        if a3_union is None or not a3_union.contains(Point(float(coords[0]), float(coords[1])))
    ]
    node_pts = [Point(float(graph.nodes[nid][0]), float(graph.nodes[nid][1])) for nid in node_ids]
    node_tree = _STRtree(node_pts) if node_pts else None

    def _snap(px: float, py: float) -> int | None:
        if node_tree is None:
            return None
        return int(node_ids[int(node_tree.nearest(Point(px, py)))])

    for idx, (leaf, (r_i, mean_r, max_r)) in enumerate(zip(leaves, cell_stats)):
        # Variable strip spacing: denser in high-risk cells, up to swath_m in low-risk
        rel = max(0.0, min(1.0, mean_r / max(1e-6, max(mean_ris))))
        spacing = float(swath_m) * (1.0 - (1.0 - tcfg.min_spacing_factor) * rel)
        spacing = max(15.0, min(float(swath_m), spacing))

        # Orientation: wind-aligned if requested, else DSM ridge/contour in high-risk cells
        c = leaf.representative_point()
        if headwind_align and wind_direction_deg is not None and mean_r >= q_hi:
            angle = float(wind_direction_deg)
        elif mean_r >= q_hi:
            angle = _terrain_ridge_angle_deg(terrain, c.x, c.y)
        else:
            angle = 0.0

        pts = _boustrophedon_points_in_poly(leaf, spacing_m=spacing, angle_deg=angle)
        nodes: list[int] = []
        track_len = 0.0
        prev_pt = None
        for px, py in pts:
            nid = _snap(px, py)
            if nid is not None and (not nodes or nodes[-1] != nid):
                nodes.append(nid)
            if prev_pt is not None:
                track_len += math.hypot(px - prev_pt[0], py - prev_pt[1])
            prev_pt = (px, py)

        if not nodes:
            nid = _snap(c.x, c.y)
            if nid is not None:
                nodes = [nid]
        if not nodes:
            continue

        service_s = max(track_len / max(1.0, cruise_ms), 5.0)
        tau_i = float(tcfg.tau0_s) / (1.0 + float(tcfg.alpha_revisit) * (r_i / r_bar))
        density = track_len / max(1.0, float(leaf.area))
        densities.append(density)
        cell_mean_rs.append(mean_r)

        tasks.append({
            'id': idx,
            'nodes': nodes,
            'prize': float(r_i),
            'mean_risk': float(mean_r),
            'max_risk': float(max_r),
            'revisit_s': float(tau_i),
            'service_s': float(service_s),
            'spacing_m': float(spacing),
            'area_m2': float(leaf.area),
            'centroid_utm': [float(c.x), float(c.y)],
        })
        cells_meta.append({'id': idx, 'bounds': list(leaf.bounds), 'prize': float(r_i), 'mean_risk': float(mean_r), 'spacing_m': float(spacing)})

    rho = _spearman_corr(np.array(densities, dtype=float), np.array(cell_mean_rs, dtype=float))
    total_obs_risk = sum(t['prize'] for t in tasks)
    return AdaptiveTaskSet(
        tasks=tasks,
        cells=cells_meta,
        unobservable_risk=unobs_risk,
        total_risk=total_obs_risk + unobs_risk,
        track_density_spearman=round(rho, 4),
        warnings=warnings,
    )
