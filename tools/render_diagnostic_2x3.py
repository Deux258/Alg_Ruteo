"""Render 2x3 diagnostic PNG of R(x, y, t) and its 4 factors over Valparaiso."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import zlib

import numpy as np
from shapely.geometry import shape
from shapely.ops import transform

from core.aerial_data import FWD
from core.db import connect
from core.patrol import forest_zone_utm, terrain
from core.risk_field import RiskConfig, compute_risk_field, normalize_risk_array
from core.web import patrol_model

# Minimal 5x7 uppercase/ASCII bitmap font for crisp dependency-free labels
_FONT: dict[str, tuple[str, ...]] = {
    'A': ('01110', '10001', '10001', '11111', '10001', '10001', '10001'),
    'B': ('11110', '10001', '10001', '11110', '10001', '10001', '11110'),
    'C': ('01111', '10000', '10000', '10000', '10000', '10000', '01111'),
    'D': ('11110', '10001', '10001', '10001', '10001', '10001', '11110'),
    'E': ('11111', '10000', '10000', '11110', '10000', '10000', '11111'),
    'F': ('11111', '10000', '10000', '11110', '10000', '10000', '10000'),
    'G': ('01111', '10000', '10000', '10111', '10001', '10001', '01110'),
    'H': ('10001', '10001', '10001', '11111', '10001', '10001', '10001'),
    'I': ('11111', '00100', '00100', '00100', '00100', '00100', '11111'),
    'K': ('10001', '10010', '10100', '11000', '10100', '10010', '10001'),
    'L': ('10000', '10000', '10000', '10000', '10000', '10000', '11111'),
    'M': ('10001', '11011', '10101', '10101', '10001', '10001', '10001'),
    'N': ('10001', '11001', '10101', '10011', '10001', '10001', '10001'),
    'O': ('01110', '10001', '10001', '10001', '10001', '10001', '01110'),
    'P': ('11110', '10001', '10001', '11110', '10000', '10000', '10000'),
    'Q': ('01110', '10001', '10001', '10001', '10101', '10010', '01101'),
    'R': ('11110', '10001', '10001', '11110', '10100', '10010', '10001'),
    'S': ('01111', '10000', '10000', '01110', '00001', '00001', '11110'),
    'T': ('11111', '00100', '00100', '00100', '00100', '00100', '00100'),
    'U': ('10001', '10001', '10001', '10001', '10001', '10001', '01110'),
    'V': ('10001', '10001', '10001', '10001', '10001', '01010', '00100'),
    'W': ('10001', '10001', '10001', '10101', '10101', '11011', '10001'),
    'X': ('10001', '10001', '01010', '00100', '01010', '10001', '10001'),
    'Y': ('10001', '10001', '01010', '00100', '00100', '00100', '00100'),
    'Z': ('11111', '00001', '00010', '00100', '01000', '10000', '11111'),
    '0': ('01110', '10011', '10101', '10101', '11001', '10001', '01110'),
    '1': ('00100', '01100', '00100', '00100', '00100', '00100', '01110'),
    '2': ('01110', '10001', '00001', '00110', '01000', '10000', '11111'),
    '3': ('11110', '00001', '00001', '01110', '00001', '00001', '11110'),
    '4': ('00010', '00110', '01010', '10010', '11111', '00010', '00010'),
    '5': ('11111', '10000', '10000', '11110', '00001', '00001', '11110'),
    '6': ('01110', '10000', '10000', '11110', '10001', '10001', '01110'),
    '7': ('11111', '00001', '00010', '00100', '01000', '01000', '01000'),
    '8': ('01110', '10001', '10001', '01110', '10001', '10001', '01110'),
    '9': ('01110', '10001', '10001', '01111', '00001', '00001', '01110'),
    '.': ('00000', '00000', '00000', '00000', '00000', '01100', '01100'),
    ':': ('00000', '01100', '01100', '00000', '01100', '01100', '00000'),
    '-': ('00000', '00000', '00000', '11111', '00000', '00000', '00000'),
    '+': ('00000', '00100', '00100', '11111', '00100', '00100', '00000'),
    '/': ('00001', '00010', '00010', '00100', '01000', '01000', '10000'),
    '(': ('00010', '00100', '01000', '01000', '01000', '00100', '00010'),
    ')': ('01000', '00100', '00010', '00010', '00010', '00100', '01000'),
    '%': ('11001', '11010', '00010', '00100', '01000', '01011', '10011'),
    ' ': ('00000', '00000', '00000', '00000', '00000', '00000', '00000'),
}


def _draw_text(canvas: np.ndarray, x: int, y: int, text: str, color=(241, 245, 249), scale: int = 2) -> None:
    cx = x
    for ch in text.upper():
        glyph = _FONT.get(ch, _FONT[' '])
        for ry, row in enumerate(glyph):
            for rx, bit in enumerate(row):
                if bit == '1':
                    y0, y1 = y + ry * scale, y + (ry + 1) * scale
                    x0, x1 = cx + rx * scale, cx + (rx + 1) * scale
                    if 0 <= y0 and y1 <= canvas.shape[0] and 0 <= x0 and x1 <= canvas.shape[1]:
                        canvas[y0:y1, x0:x1, :3] = color
        cx += 6 * scale


def _write_png(path: Path, rgba: np.ndarray) -> None:
    h, w, _ = rgba.shape
    raw_rows = b''.join(b'\x00' + rgba[y].tobytes() for y in range(h))
    compressed = zlib.compress(raw_rows, level=6)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def _colormap(v: np.ndarray, palette: str = 'inferno') -> np.ndarray:
    stops = np.array([0.0, 0.25, 0.55, 0.80, 1.0])
    if palette == 'viridis':
        colors = np.array([[22, 34, 64], [33, 145, 140], [94, 201, 98], [216, 226, 25], [253, 231, 37]], dtype=float)
    else:
        colors = np.array([[20, 30, 58], [22, 118, 128], [234, 179, 8], [249, 115, 22], [220, 38, 38]], dtype=float)
    out = np.zeros((*v.shape, 3), dtype=np.uint8)
    vc = np.clip(v, 0.0, 1.0)
    for c in range(3):
        out[..., c] = np.interp(vc, stops, colors[:, c]).astype(np.uint8)
    return out


def _render_panel(
    grid: np.ndarray,
    forest_mask: np.ndarray,
    title: str,
    vmin: float,
    vmax: float,
    bounds_utm: tuple[float, float, float, float],
    scale: int = 2,
    palette: str = 'inferno',
    highlight_mask: np.ndarray | None = None,
    highlight_rgb: tuple[int, int, int] = (232, 121, 249),
) -> np.ndarray:
    ny, nx = grid.shape
    h, w = ny * scale, nx * scale
    top_pad, right_pad, bot_pad = 36, 72, 26
    panel = np.zeros((h + top_pad + bot_pad, w + right_pad, 4), dtype=np.uint8)
    panel[:, :, :3] = [15, 23, 42]
    panel[:, :, 3] = 255

    norm = np.zeros_like(grid, dtype=float)
    if vmax > vmin:
        norm = np.clip((grid - vmin) / (vmax - vmin), 0.0, 1.0)
    rgb = _colormap(norm[::-1, :], palette=palette)
    f_up = np.repeat(np.repeat(forest_mask[::-1, :], scale, axis=0), scale, axis=1)
    rgb_up = np.repeat(np.repeat(rgb, scale, axis=0), scale, axis=1)
    map_area = panel[top_pad:top_pad + h, :w, :3]
    map_area[f_up] = rgb_up[f_up]

    if highlight_mask is not None:
        hl_up = np.repeat(np.repeat(highlight_mask[::-1, :], scale, axis=0), scale, axis=1)
        map_area[hl_up] = highlight_rgb

    # Toponyms (Playa Ancha NW, Placilla SE, Laguna Verde SW)
    minx, miny, maxx, maxy = bounds_utm
    toponyms = [
        ('PLAYA ANCHA', -71.645, -33.038),
        ('PLACILLA', -71.568, -33.112),
        ('LAGUNA VERDE', -71.662, -33.105),
    ]
    for name, lon, lat in toponyms:
        tx, ty = FWD(lon, lat)
        px = int((tx - minx) / max(1.0, maxx - minx) * w)
        py = int((maxy - ty) / max(1.0, maxy - miny) * h)
        px = max(4, min(w - len(name) * 7 - 4, px))
        py = max(4, min(h - 12, py))
        _draw_text(panel, px, top_pad + py, name, color=(248, 250, 252), scale=1)

    # 1 km scale bar at bottom-left
    bar_px = max(10, int(1000.0 / max(1.0, maxx - minx) * w))
    panel[top_pad + h + 8:top_pad + h + 12, 10:10 + bar_px, :3] = (248, 250, 252)
    _draw_text(panel, 14 + bar_px, top_pad + h + 6, '1 KM', color=(203, 213, 225), scale=1)

    # Title
    _draw_text(panel, 8, 10, title, color=(248, 250, 252), scale=2)

    # Colorbar with min/max labels
    grad = np.linspace(1.0, 0.0, h)[:, None]
    bar = _colormap(np.repeat(grad, 14, axis=1), palette=palette)
    panel[top_pad:top_pad + h, w + 10:w + 24, :3] = bar
    _draw_text(panel, w + 28, top_pad, f'{vmax:.2f}', color=(226, 232, 240), scale=1)
    _draw_text(panel, w + 28, top_pad + h - 8, f'{vmin:.2f}', color=(226, 232, 240), scale=1)
    return panel


def main() -> None:
    conn = connect()
    cur = conn.execute('SELECT run_id FROM routing.aerial_models ORDER BY run_id DESC LIMIT 1').fetchone()
    model = patrol_model(conn, cur)
    surf = terrain()
    area_utm = transform(FWD, shape(model['flight_geometry']))
    fzone = forest_zone_utm(model)

    cfg_max = RiskConfig(grid_cell_m=45.0, normalization_mode='max')
    f_max = compute_risk_field(model, area_utm, terrain=surf, config=cfg_max, forest_zone_utm=fzone)
    f_quant = normalize_risk_array(f_max.raw_values, f_max.forest_mask, mode='quantile')

    # Diagnostics on both normalizations
    diag_max = f_max.diagnostics()
    f_q_obj = compute_risk_field(model, area_utm, terrain=surf, config=RiskConfig(grid_cell_m=45.0, normalization_mode='quantile'), forest_zone_utm=fzone)
    diag_q = f_q_obj.diagnostics()

    p_a4 = f_max.components['p_a4']
    f_m2 = f_max.components['f_m2']
    s_grid = f_max.components['s']
    u_grid = f_max.components['u']
    unk_mask = (f_max.a4_class_grid == 0) & f_max.forest_mask
    pine_euc = (f_max.pine_euc_mask) & f_max.forest_mask

    t_label = str((model.get('records') or {}).get('M4', [{}])[0].get('valid_at', model.get('reference_time', '')))[:16]
    sc = 2
    p1 = _render_panel(p_a4, f_max.forest_mask, f'A) P_A4 (SIN COB {f_max.a4_class_pct.get("unknown", 0)}% MAGENTA)', 0.01, 0.20, f_max.bounds_utm, sc, 'inferno', unk_mask, (232, 121, 249))
    p2 = _render_panel(f_m2, f_max.forest_mask, 'B) F_M2 (PINO/EUCALIPTO EN CIAN)', 0.0, 1.0, f_max.bounds_utm, sc, 'viridis', pine_euc, (34, 211, 238))
    p3 = _render_panel(s_grid, f_max.forest_mask, f'C) S(PENDIENTE+VIENTO) T={t_label}', float(np.min(s_grid[f_max.forest_mask])), float(np.max(s_grid[f_max.forest_mask])), f_max.bounds_utm, sc, 'inferno')
    p4 = _render_panel(u_grid, f_max.forest_mask, 'D) U INTERFAZ URBANO-FORESTAL', 0.0, 1.0, f_max.bounds_utm, sc, 'viridis')
    p5 = _render_panel(f_max.values, f_max.forest_mask, 'E) R NORM MAX [0..1]', 0.0, 1.0, f_max.bounds_utm, sc, 'inferno')
    p6 = _render_panel(f_quant, f_max.forest_mask, 'F) R NORM CUANTILES [0..1]', 0.0, 1.0, f_max.bounds_utm, sc, 'inferno')

    row1 = np.concatenate([p1, p2, p3], axis=1)
    row2 = np.concatenate([p4, p5, p6], axis=1)
    grid_img = np.concatenate([row1, row2], axis=0)

    out_png = Path('evidencia/fase1a_diagnostico_2x3.png')
    _write_png(out_png, grid_img)

    m4_first = (model.get('records') or {}).get('M4', [{}])[0]
    print(json.dumps({
        'run_id': str(cur['run_id']),
        'png_path': str(out_png),
        'png_px': [int(grid_img.shape[1]), int(grid_img.shape[0])],
        'm4_sample': m4_first,
        'diag_max': diag_max,
        'diag_quantile': diag_q,
        'a4_class_pct': f_max.a4_class_pct,
        'unobservable_risk_pct': round(f_max.unobservable_risk_pct, 2),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
