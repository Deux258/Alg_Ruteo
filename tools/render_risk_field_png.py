"""Render a georeferenced PNG + PGW worldfile of R(x, y, t) over Valparaiso."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import zlib

import numpy as np
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import transform

from core.aerial_data import FWD, INV
from core.db import connect
from core.patrol import forest_zone_utm, terrain
from core.risk_field import RiskConfig, compute_risk_field
from core.web import patrol_model


def _write_png(path: Path, rgba: np.ndarray) -> None:
    """Write an (H, W, 4) uint8 RGBA array as a valid PNG using stdlib zlib."""
    h, w, _ = rgba.shape
    raw_rows = b''.join(b'\x00' + rgba[y].tobytes() for y in range(h))
    compressed = zlib.compress(raw_rows, level=6)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _colormap_inferno(v: np.ndarray) -> np.ndarray:
    """Map [0, 1] float array to RGB uint8 (dark-indigo -> teal -> amber -> red)."""
    stops = np.array([0.0, 0.25, 0.55, 0.80, 1.0])
    colors = np.array([
        [20, 30, 58],
        [22, 118, 128],
        [234, 179, 8],
        [249, 115, 22],
        [220, 38, 38],
    ], dtype=float)
    out = np.zeros((*v.shape, 3), dtype=np.uint8)
    vc = np.clip(v, 0.0, 1.0)
    for c in range(3):
        out[..., c] = np.interp(vc, stops, colors[:, c]).astype(np.uint8)
    return out


def _draw_boundary(canvas: np.ndarray, mask: np.ndarray, rgb: tuple[int, int, int], thickness: int = 2) -> None:
    """Draw outer boundary of a boolean mask onto an (H, W, 4) RGBA canvas."""
    edge = np.zeros_like(mask)
    edge[1:, :] |= mask[1:, :] != mask[:-1, :]
    edge[:, 1:] |= mask[:, 1:] != mask[:, :-1]
    if thickness > 1:
        dilated = edge.copy()
        for dy in range(-thickness + 1, thickness):
            for dx in range(-thickness + 1, thickness):
                if dy == 0 and dx == 0:
                    continue
                ys = slice(max(0, dy), edge.shape[0] + min(0, dy))
                xs = slice(max(0, dx), edge.shape[1] + min(0, dx))
                ys0 = slice(max(0, -dy), edge.shape[0] + min(0, -dy))
                xs0 = slice(max(0, -dx), edge.shape[1] + min(0, -dx))
                dilated[ys, xs] |= edge[ys0, xs0]
        edge = dilated
    canvas[edge, 0] = rgb[0]
    canvas[edge, 1] = rgb[1]
    canvas[edge, 2] = rgb[2]
    canvas[edge, 3] = 255


def main() -> None:
    conn = connect()
    cur = conn.execute('SELECT run_id FROM routing.aerial_models ORDER BY run_id DESC LIMIT 1').fetchone()
    model = patrol_model(conn, cur)
    surf = terrain()
    area_utm = transform(FWD, shape(model['flight_geometry']))
    fzone = forest_zone_utm(model)

    cfg = RiskConfig(grid_cell_m=45.0)
    field = compute_risk_field(model, area_utm, terrain=surf, config=cfg, forest_zone_utm=fzone)

    # Sensitivity on real Valparaiso snapshot for a4_unknown_pct in (5, 10, 20)
    sens = {}
    for pct in (5.0, 10.0, 20.0):
        f_s = compute_risk_field(
            model,
            area_utm,
            terrain=surf,
            config=RiskConfig(grid_cell_m=60.0, a4_unknown_pct=pct),
            forest_zone_utm=fzone,
        )
        vals = f_s.raw_values[f_s.forest_mask]
        sens[str(int(pct))] = {
            'raw_mean': round(float(np.mean(vals)), 6),
            'raw_p95': round(float(np.percentile(vals, 95)), 6),
            'norm_mean': round(float(np.mean(f_s.values[f_s.forest_mask])), 4),
        }

    # Upsample field for crisp PNG (target ~900 px wide)
    ny, nx = field.values.shape
    scale = max(1, int(round(900 / nx)))
    h, w = ny * scale, nx * scale
    # Flip Y so North is up
    vals_up = np.repeat(np.repeat(field.values[::-1, :], scale, axis=0), scale, axis=1)
    fmask_up = np.repeat(np.repeat(field.forest_mask[::-1, :], scale, axis=0), scale, axis=1)

    canvas = np.zeros((h, w, 4), dtype=np.uint8)
    canvas[:, :, :3] = [15, 23, 42]  # dark slate background outside forest_zone_utm
    canvas[:, :, 3] = 255

    heat = _colormap_inferno(vals_up)
    canvas[fmask_up, :3] = heat[fmask_up]

    # Coordinate grid in UTM for vector overlays
    minx, miny, maxx, maxy = field.bounds_utm
    xs_hi = np.linspace(minx, maxx, w)
    ys_hi = np.linspace(maxy, miny, h)
    gx, gy = np.meshgrid(xs_hi, ys_hi)

    # M2 forest contour
    _draw_boundary(canvas, fmask_up, (34, 197, 94), thickness=2)

    # A4 SENAPRED polygons
    a4_mask = np.zeros((h, w), dtype=bool)
    for rec in (model.get('records') or {}).get('A4') or []:
        if rec.get('geometry'):
            g = transform(FWD, shape(rec['geometry']))
            a4_mask |= contains_xy(g, gx, gy)
    _draw_boundary(canvas, a4_mask, (56, 189, 248), thickness=2)

    # Buildings / M2 Urban
    from core.risk_field import _extract_urban_geoms
    urb_geoms = _extract_urban_geoms(model, surf, None, [])
    urb_mask = np.zeros((h, w), dtype=bool)
    for g in urb_geoms:
        if g.intersects(area_utm):
            urb_mask |= contains_xy(g, gx, gy)
    canvas[urb_mask, :3] = (0.55 * canvas[urb_mask, :3] + 0.45 * np.array([203, 213, 225])).astype(np.uint8)

    # A3 DGAC AIP (unobservable, hatch + magenta outline; R stays visible underneath)
    a3_mask = np.zeros((h, w), dtype=bool)
    for rec in (model.get('records') or {}).get('A3') or []:
        if rec.get('geometry'):
            g = transform(FWD, shape(rec['geometry']))
            a3_mask |= contains_xy(g, gx, gy)
    hatch = ((np.arange(h)[:, None] + np.arange(w)[None, :]) % 10) < 2
    a3_hatch = a3_mask & hatch
    canvas[a3_hatch, :3] = [244, 63, 94]
    _draw_boundary(canvas, a3_mask, (244, 63, 94), thickness=2)

    # Add colorbar strip on the right (36 px wide)
    bar_w = 36
    full = np.zeros((h, w + bar_w, 4), dtype=np.uint8)
    full[:, :w] = canvas
    full[:, w:, :3] = [15, 23, 42]
    full[:, w:, 3] = 255
    grad = np.linspace(1.0, 0.0, h)[:, None]
    bar_rgb = _colormap_inferno(np.repeat(grad, 18, axis=1))
    full[:, w + 9:w + 27, :3] = bar_rgb

    out_png = Path('evidencia/fase1a_R_valparaiso.png')
    _write_png(out_png, full)

    # PGW worldfile for georeferencing in EPSG:32719
    px_x = (maxx - minx) / w
    px_y = -(maxy - miny) / h
    pgw = f'{px_x:.6f}\n0.0\n0.0\n{px_y:.6f}\n{minx:.3f}\n{maxy:.3f}\n'
    out_png.with_suffix('.pgw').write_text(pgw, encoding='utf-8')

    report = {
        'run_id': str(cur['run_id']),
        'png_path': str(out_png),
        'png_size_px': [w + bar_w, h],
        'bounds_utm_32719': [round(minx, 2), round(miny, 2), round(maxx, 2), round(maxy, 2)],
        'bounds_wgs84': list(INV(minx, miny)) + list(INV(maxx, maxy)),
        'summary': field.summary(),
        'a4_unknown_sensitivity': sens,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
