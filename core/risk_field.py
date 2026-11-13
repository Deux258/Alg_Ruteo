"""Fire risk field R(x, y, t) for risk-weighted forest patrol routing (Fase 1a).

Separates *fire ignition/propagation risk* R(x, y, t) (used as a prize in
latency-minimizing patrol objectives) from *drone hazard risk* (A1 wind, A3
restricted airspace, synthetic threats, FIRMS hazard cost on edges).

Data sources & epochs (Valparaiso snapshot):
    - M2: CONAF / CIREN (S2, 2019) vegetation & land cover
    - M3: Copernicus GLO-30 (S3, cell S34 W072, derived from TanDEM-X) DSM (~30.9 m N-S, ~25.9 m E-W)
    - M4: Open-Meteo / ECMWF IFS 0.25° (single cell -33.078, -71.616; 48 h, 10 m wind, retrospective)
    - A2: NASA FIRMS VIIRS NOAA-20 C2 (0 detections in snapshot -> status "empty")
    - A3: DGAC AIP ENR 5.1 restricted airspace (unobservable for drone, R > 0 preserved)
    - A4: SENAPRED (S7, "Amenaza por incendio forestal 2024", densidad 2020-2024), ordinal classes 1-5

Formula:
    R_raw(x, y, t) = w_A4(x, y) * F_M2(x, y) * S(slope, wind_t) * U(x, y)
                     + FIRMS_A2(x, y, t)
    R(x, y, t)     = normalize_01(R_raw(x, y, t))   inside forest_zone_utm (0 outside)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import math
from typing import Any

import numpy as np
from shapely import STRtree
from shapely.geometry import Point, Polygon, shape
from shapely.ops import transform, unary_union

from core.aerial_data import FWD, iso


@dataclass(frozen=True)
class RiskConfig:
    """Central configuration for R(x, y, t) and adaptive task discretization.

    All tunable weights live here so sensitivity analyses (Fase 4) can vary
    them without touching core logic.
    """

    # Spatial resolution (Copernicus GLO-30 native ~30.9 m N-S, ~25.9 m E-W at -33.05 deg)
    grid_cell_m: float = 30.0
    min_cell_m: float = 30.0  # Quadtree minimum cell >= native DSM resolution
    dsm_dx_m: float = 25.9    # E-W spacing in meters for DSM finite difference
    dsm_dy_m: float = 30.9    # N-S spacing in meters for DSM finite difference

    # A4 SENAPRED ordinal classes 1..5: "peso supuesto" (NOT calibrated probability)
    a4_assumed_weights_pct: tuple[float, ...] = (1.0, 3.0, 5.0, 10.0, 20.0)
    a4_unknown_pct: float = 20.0

    # F_M2: Fuel coefficient by CONAF/CIREN (2019) species / subuse / category
    fuel_by_species: dict[str, float] = field(default_factory=lambda: {
        'eucalipto': 1.00,
        'pino insigne': 1.00,
        'pino': 1.00,
        'espino': 0.75,
        'boldo': 0.80,
        'litre': 0.80,
        'peumo': 0.80,
        'quillay': 0.80,
    })
    fuel_by_subuse: dict[str, float] = field(default_factory=lambda: {
        'Plantación': 1.00,
        'Bosque Mixto': 0.90,
        'Bosque Nativo': 0.80,
        'Matorral Arborescente': 0.75,
        'Matorral': 0.70,
        'Matorral con Suculentas': 0.60,
        'Matorral-Pradera': 0.55,
        'Praderas': 0.40,
        'Rotación Cultivo-Pradera': 0.30,
        'Terreno de Uso Agrícola': 0.25,
        'Otros sin Vegetación': 0.10,
        'Ciudades, Pueblos, Zonas Industriales': 0.05,
        'Minería Industrial': 0.05,
        'Lagos, Lagunas, Embalses, Tranques': 0.0,
    })
    fuel_by_category: dict[str, float] = field(default_factory=lambda: {
        'Bosques': 0.90,
        'forest': 0.90,
        'wood': 0.90,
        'Praderas y Matorrales': 0.65,
        'scrub': 0.70,
        'grassland': 0.40,
        'grass': 0.40,
        'meadow': 0.40,
        'Terrenos Agrícolas': 0.25,
        'Áreas Desprovistas de Vegetación': 0.10,
        'Áreas Urbanas e Industriales': 0.05,
        'Cuerpos de Agua': 0.0,
    })
    fuel_default: float = 0.40

    # S(slope, wind_t) = 1 + beta1 * tan(slope) + beta2 * max(0, cos(theta_w - theta_a)) * w
    beta1_slope: float = 0.50
    beta2_wind: float = 0.08
    max_tan_slope: float = 2.00

    # U(x, y) = exp(-d_urbano / L)
    urban_decay_m: float = 300.0
    urban_fallback: float = 0.50

    # FIRMS_A2 Gaussian kernel (only active when A2 has detections or synthetic foci)
    firms_sigma_m: float = 250.0
    firms_weight: float = 0.35
    firms_half_life_h: float = 24.0

    # Normalization: 'max' (linear [0,1]), 'log' (log1p compressed [0,1]), 'quantile' (rank [0,1]), 'none'
    normalize: bool = True
    normalization_mode: str = 'max'

    # Wind model mode (Fase 1a-bis will add 'ecmwf_profile')
    wind_layer_mode: str = 'uniform_m4'


def wind_vector_xy(wind_speed_ms: float, wind_direction_deg: float) -> tuple[float, float]:
    """Convert meteorological wind (speed, direction FROM in deg) to UTM (vx, vy).

    Matches ``core/patrol.py`` (Graph.edge_kinematics): 0 deg = from North
    (blows South, vy < 0), 90 deg = from East (blows West, vx < 0).
    """
    angle = math.radians(float(wind_direction_deg))
    speed = max(0.0, float(wind_speed_ms))
    return (-speed * math.sin(angle), -speed * math.cos(angle))


def _to_utm_geom(geojson_geom: dict[str, Any]) -> Any:
    return transform(FWD, shape(geojson_geom))


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return iso(value)
    except Exception:
        return None


def _layer_status(records: dict[str, Any], key: str) -> str:
    """Distinguish missing ('unknown'), empty list ('empty'), and 'populated'."""
    if key not in records or records[key] is None:
        return 'unknown'
    return 'populated' if len(records[key]) > 0 else 'empty'


def fuel_coefficient(record: dict[str, Any], config: RiskConfig) -> float:
    """Return fuel factor F_M2 in [0, 1] from a CONAF/CIREN (2019) M2 record."""
    orig = record.get('original_record') or {}
    species = str(orig.get('especi1_co') or '').strip().lower()
    if species and species in config.fuel_by_species:
        return float(config.fuel_by_species[species])
    attrs = record.get('attributes') or {}
    subuse = str(attrs.get('subuse') or orig.get('subuso') or '').strip()
    if subuse and subuse in config.fuel_by_subuse:
        return float(config.fuel_by_subuse[subuse])
    category = str(record.get('category') or '').strip()
    if category and category in config.fuel_by_category:
        return float(config.fuel_by_category[category])
    return float(config.fuel_default)


def slope_wind_factor(
    terrain: Any,
    x_utm: float,
    y_utm: float,
    wind_speed_ms: float,
    wind_direction_deg: float,
    config: RiskConfig,
) -> float:
    """Compute S(slope, wind_t) = 1 + beta1*tan(slope) + beta2*max(0, cos(dtheta))*w.

    Uses real Copernicus GLO-30 DSM spacing in meters (``dsm_dx_m`` ≈ 25.9 m E-W,
    ``dsm_dy_m`` ≈ 30.9 m N-S) and reuses ``wind_vector_xy()`` meteorological
    convention (direction FROM which wind blows).
    """
    if terrain is None:
        return 1.0
    dx = max(5.0, float(config.dsm_dx_m))
    dy = max(5.0, float(config.dsm_dy_m))
    zc = terrain.at(x_utm, y_utm)
    if zc is None:
        return 1.0
    zx_p = terrain.at(x_utm + dx, y_utm)
    zx_m = terrain.at(x_utm - dx, y_utm)
    zy_p = terrain.at(x_utm, y_utm + dy)
    zy_m = terrain.at(x_utm, y_utm - dy)

    span_x = (dx if zx_p is not None else 0.0) + (dx if zx_m is not None else 0.0)
    span_y = (dy if zy_p is not None else 0.0) + (dy if zy_m is not None else 0.0)
    dz_dx = (((zx_p if zx_p is not None else zc) - (zx_m if zx_m is not None else zc)) / span_x) if span_x > 0 else 0.0
    dz_dy = (((zy_p if zy_p is not None else zc) - (zy_m if zy_m is not None else zc)) / span_y) if span_y > 0 else 0.0
    tan_slope = min(float(config.max_tan_slope), math.hypot(dz_dx, dz_dy))

    wind_align = 0.0
    if cfg_mode := getattr(config, 'wind_layer_mode', 'uniform_m4') == 'ecmwf_profile':
        from core.wind_profile import rothermel_anisotropic_factor
        return rothermel_anisotropic_factor(
            wind_speed_ms=wind_speed_ms,
            wind_direction_deg=wind_direction_deg,
            dz_dx=dz_dx,
            dz_dy=dz_dy,
            beta1_slope=config.beta1_slope,
            beta2_wind=config.beta2_wind,
            max_tan_slope=config.max_tan_slope,
        )

    if wind_speed_ms > 0.0 and tan_slope > 1e-6:
        vx, vy = wind_vector_xy(1.0, wind_direction_deg)
        ux = dz_dx / tan_slope
        uy = dz_dy / tan_slope
        wind_align = max(0.0, vx * ux + vy * uy)

    return 1.0 + config.beta1_slope * tan_slope + config.beta2_wind * wind_align * max(0.0, float(wind_speed_ms))


@dataclass
class RiskField:
    """Evaluated 2D fire risk field R(x, y, t) on an EPSG:32719 grid."""

    xs: np.ndarray  # shape (nx,)
    ys: np.ndarray  # shape (ny,)
    values: np.ndarray  # shape (ny, nx), normalized in [0, 1]; 0 outside forest_zone
    raw_values: np.ndarray  # shape (ny, nx), unnormalized
    observable: np.ndarray  # bool shape (ny, nx): False in A3, urban, or outside forest_zone
    forest_mask: np.ndarray  # bool shape (ny, nx)
    bounds_utm: tuple[float, float, float, float]
    cell_m: float
    config: RiskConfig
    layer_status: dict[str, str] = field(default_factory=dict)
    a4_class_pct: dict[str, float] = field(default_factory=dict)
    unobservable_risk_pct: float = 0.0
    warnings: list[str] = field(default_factory=list)
    components: dict[str, np.ndarray] = field(default_factory=dict)
    a4_class_grid: np.ndarray | None = None
    pine_euc_mask: np.ndarray | None = None

    def diagnostics(self) -> dict[str, Any]:
        """Compute Spearman correlations of R with factors and top-5%/10% risk concentration."""
        mask = self.forest_mask
        if not np.any(mask):
            return {'spearman': {}, 'top5_risk_pct': 0.0, 'top10_risk_pct': 0.0}

        r_vals = self.values[mask]
        total_r = float(np.sum(r_vals))
        sorted_r = np.sort(r_vals)[::-1]
        n = len(sorted_r)
        k5 = max(1, int(math.ceil(0.05 * n)))
        k10 = max(1, int(math.ceil(0.10 * n)))
        top5 = (100.0 * float(np.sum(sorted_r[:k5])) / total_r) if total_r > 0 else 0.0
        top10 = (100.0 * float(np.sum(sorted_r[:k10])) / total_r) if total_r > 0 else 0.0

        def _spearman(a: np.ndarray, b: np.ndarray) -> float:
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

        spearman = {}
        for name in ('p_a4', 'f_m2', 's', 'u'):
            comp = self.components.get(name)
            if comp is not None:
                spearman[name] = round(_spearman(r_vals, comp[mask]), 4)

        return {
            'spearman': spearman,
            'top5_risk_pct': round(top5, 2),
            'top10_risk_pct': round(top10, 2),
            'forest_cells': int(n),
        }

    def at(self, x_utm: float, y_utm: float) -> float:
        """Bilinear interpolation of R(x, y, t) in EPSG:32719."""
        if self.values.size == 0:
            return 0.0
        ix = (x_utm - float(self.xs[0])) / self.cell_m
        iy = (y_utm - float(self.ys[0])) / self.cell_m
        ix = max(0.0, min(float(len(self.xs) - 1), ix))
        iy = max(0.0, min(float(len(self.ys) - 1), iy))
        x0 = int(math.floor(ix))
        y0 = int(math.floor(iy))
        x1 = min(x0 + 1, len(self.xs) - 1)
        y1 = min(y0 + 1, len(self.ys) - 1)
        fx = ix - x0
        fy = iy - y0
        v00 = float(self.values[y0, x0])
        v10 = float(self.values[y0, x1])
        v01 = float(self.values[y1, x0])
        v11 = float(self.values[y1, x1])
        return (
            v00 * (1.0 - fx) * (1.0 - fy)
            + v10 * fx * (1.0 - fy)
            + v01 * (1.0 - fx) * fy
            + v11 * fx * fy
        )

    def integrate(self, geom_utm: Any) -> float:
        """Approximate integral ∫_A R(x, y, t) dA over a UTM polygon."""
        if geom_utm is None or geom_utm.is_empty or self.values.size == 0:
            return 0.0
        minx, miny, maxx, maxy = geom_utm.bounds
        ix0 = max(0, int(math.floor((minx - float(self.xs[0])) / self.cell_m)))
        ix1 = min(len(self.xs) - 1, int(math.ceil((maxx - float(self.xs[0])) / self.cell_m)))
        iy0 = max(0, int(math.floor((miny - float(self.ys[0])) / self.cell_m)))
        iy1 = min(len(self.ys) - 1, int(math.ceil((maxy - float(self.ys[0])) / self.cell_m)))
        cell_area = self.cell_m * self.cell_m
        total = 0.0
        for iy in range(iy0, iy1 + 1):
            cy = float(self.ys[iy])
            for ix in range(ix0, ix1 + 1):
                cx = float(self.xs[ix])
                if geom_utm.contains(Point(cx, cy)):
                    total += float(self.values[iy, ix]) * cell_area
        if total == 0.0:
            c = geom_utm.centroid
            total = self.at(c.x, c.y) * float(geom_utm.area)
        return total

    def summary(self) -> dict[str, Any]:
        """Compact metadata for API summary responses (respecting 1 MiB limit)."""
        vals = self.values[self.forest_mask] if np.any(self.forest_mask) else self.values
        return dict(
            cell_m=self.cell_m,
            shape=[int(self.values.shape[0]), int(self.values.shape[1])],
            min=float(np.min(vals)) if vals.size else 0.0,
            max=float(np.max(vals)) if vals.size else 0.0,
            mean=float(np.mean(vals)) if vals.size else 0.0,
            p95=float(np.percentile(vals, 95)) if vals.size else 0.0,
            layer_status=dict(self.layer_status),
            a4_class_pct=dict(self.a4_class_pct),
            unobservable_risk_pct=round(float(self.unobservable_risk_pct), 2),
            layer_epochs={
                'M2': 'CONAF/CIREN 2019 (S2)',
                'M3': 'Copernicus GLO-30 S34 W072 (TanDEM-X)',
                'M4': 'ECMWF IFS 0.25 deg (2026-10 retrospectivo, 1 celda)',
                'A2': 'NASA FIRMS VIIRS NOAA-20 C2',
                'A4': 'SENAPRED Amenaza Incendio 2024 (densidad 2020-2024)',
            },
            warnings=list(self.warnings),
        )


def _extract_urban_geoms(
    model: dict[str, Any],
    terrain: Any,
    buildings_utm: list[Any] | None,
    warnings: list[str],
) -> list[Any]:
    if buildings_utm is not None:
        return [g for g in buildings_utm if g is not None and not g.is_empty]
    try:
        from core.geographic_scene import prepared_scene
        if terrain is not None and model.get('study_geometry'):
            scene = prepared_scene(model, terrain)
            features = ((scene.get('geography') or {}).get('layers') or {}).get('buildings', {}).get('features', [])
            if features:
                geoms = [_to_utm_geom(f['geometry']) for f in features if f.get('geometry')]
                if geoms:
                    return geoms
    except Exception:
        pass
    m2_urban = [
        _to_utm_geom(r['geometry'])
        for r in (model.get('records') or {}).get('M2', [])
        if r.get('geometry') and r.get('category') == 'Áreas Urbanas e Industriales'
    ]
    if m2_urban:
        warnings.append('Edificios OSM no disponibles; se usa M2 Áreas Urbanas como proxy urbano.')
        return m2_urban
    warnings.append('Sin capa urbana OSM ni M2 urbana; U(x,y) usa valor de respaldo.')
    return []


def _derive_forest_zone(model: dict[str, Any], area_utm: Polygon, forest_zone_utm: Any) -> Any:
    if forest_zone_utm is not None:
        return forest_zone_utm
    m2 = (model.get('records') or {}).get('M2') or []
    forest_geoms = [
        _to_utm_geom(r['geometry'])
        for r in m2
        if r.get('geometry') and r.get('category') in ('Bosques', 'wood', 'forest', 'Praderas y Matorrales')
    ]
    if forest_geoms:
        return unary_union(forest_geoms).intersection(area_utm)
    return area_utm


def compute_risk_field(
    model: dict[str, Any],
    area_utm: Polygon,
    terrain: Any = None,
    weather: dict[str, Any] | None = None,
    config: RiskConfig | None = None,
    buildings_utm: list[Any] | None = None,
    forest_zone_utm: Any = None,
    reference_time: str | None = None,
    wind_profile: Any = None,
    evaluation_time_s: float = 0.0,
) -> RiskField:
    """Compute fire risk field R(x, y, t) over ``area_utm`` (EPSG:32719).

    - Inside ``A3`` restricted airspace, R is preserved (fire risk exists),
      while ``observable`` is set to ``False``.
    - Outside ``forest_zone_utm``, R is set to 0 and ``observable`` is ``False``.
    """
    cfg = config or RiskConfig()
    warnings: list[str] = []
    records = model.get('records') or {}

    layer_status = {
        'M2': _layer_status(records, 'M2'),
        'M4': _layer_status(records, 'M4'),
        'A2': _layer_status(records, 'A2'),
        'A3': _layer_status(records, 'A3'),
        'A4': _layer_status(records, 'A4'),
    }

    if weather is None:
        if wind_profile is not None:
            weather = wind_profile.at(evaluation_time_s)
        else:
            m4 = records.get('M4') or []
            if cfg.wind_layer_mode == 'ecmwf_profile' and len(m4) > 1:
                from core.wind_profile import WindProfile
                weather = WindProfile(m4, reference_time=reference_time or model.get('reference_time')).at(evaluation_time_s)
            else:
                weather = m4[0] if m4 else {}
                if not m4:
                    warnings.append('M4 clima ausente/vacío; viento asumido en 0 m/s.')

    wind_speed = float(weather.get('wind_speed_ms') or 0.0)
    wind_dir = float(weather.get('wind_direction_deg') or 0.0)

    # A4 SENAPRED polygons (peso supuesto, NO probabilidad calibrada)
    unknown_w = float(cfg.a4_unknown_pct) / 100.0
    a4_items: list[tuple[Any, float, int]] = []
    for rec in records.get('A4') or []:
        if not rec.get('geometry'):
            continue
        cls = int(rec.get('ordinal_class') or 0)
        if 1 <= cls <= len(cfg.a4_assumed_weights_pct):
            prob = float(cfg.a4_assumed_weights_pct[cls - 1]) / 100.0
        else:
            prob = unknown_w
            cls = 0
        a4_items.append((_to_utm_geom(rec['geometry']), prob, cls))
    if not a4_items:
        warnings.append(f'A4 SENAPRED ({layer_status["A4"]}): peso supuesto por defecto {cfg.a4_unknown_pct}%.')
    a4_tree = STRtree([g for g, _, _ in a4_items]) if a4_items else None

    # M2 CONAF/CIREN 2019 vegetation polygons
    m2_items: list[tuple[Any, float, bool]] = []
    for rec in records.get('M2') or []:
        if not rec.get('geometry'):
            continue
        sp = str((rec.get('original_record') or {}).get('especi1_co') or '').strip().lower()
        is_pine_euc = ('eucalipto' in sp) or ('pino' in sp)
        m2_items.append((_to_utm_geom(rec['geometry']), fuel_coefficient(rec, cfg), is_pine_euc))
    if not m2_items:
        warnings.append(f'M2 vegetación ({layer_status["M2"]}): F_M2 usa fuel_default={cfg.fuel_default}.')
    m2_tree = STRtree([g for g, _, _ in m2_items]) if m2_items else None

    # A3 DGAC AIP restricted airspace (blocks drone observation, NOT fire risk)
    a3_geoms = [_to_utm_geom(r['geometry']) for r in (records.get('A3') or []) if r.get('geometry')]
    a3_tree = STRtree(a3_geoms) if a3_geoms else None

    # Urban buildings (OSM or fallback)
    urban_geoms = _extract_urban_geoms(model, terrain, buildings_utm, warnings)
    urban_tree = STRtree(urban_geoms) if urban_geoms else None

    # Forest zone (R = 0 only outside forest_zone_utm)
    fzone = _derive_forest_zone(model, area_utm, forest_zone_utm)

    # A2 FIRMS points (distinguish 'empty' vs 'unknown')
    if layer_status['A2'] == 'unknown':
        warnings.append('A2 FIRMS desconocido (clave ausente); término FIRMS=0.')
    ref_dt = _parse_iso(reference_time or model.get('reference_time'))
    firms_pts: list[tuple[float, float, float]] = []
    for rec in records.get('A2') or []:
        if not rec.get('geometry'):
            continue
        g = _to_utm_geom(rec['geometry'])
        c = g.centroid
        decay = 1.0
        acq_dt = _parse_iso(rec.get('acquired_at'))
        if ref_dt is not None and acq_dt is not None and cfg.firms_half_life_h > 0:
            age_h = max(0.0, (ref_dt - acq_dt).total_seconds() / 3600.0)
            decay = math.exp(-math.log(2.0) * age_h / cfg.firms_half_life_h)
        firms_pts.append((c.x, c.y, decay))

    # Build grid in EPSG:32719
    minx, miny, maxx, maxy = area_utm.bounds
    step = max(float(cfg.min_cell_m), float(cfg.grid_cell_m))
    nx = max(2, int(math.ceil((maxx - minx) / step)) + 1)
    ny = max(2, int(math.ceil((maxy - miny) / step)) + 1)
    xs = np.linspace(minx, maxx, nx)
    ys = np.linspace(miny, maxy, ny)

    raw = np.zeros((ny, nx), dtype=float)
    p_a4_grid = np.zeros((ny, nx), dtype=float)
    f_m2_grid = np.zeros((ny, nx), dtype=float)
    s_grid = np.zeros((ny, nx), dtype=float)
    u_grid = np.zeros((ny, nx), dtype=float)
    a4_class_grid = np.full((ny, nx), -1, dtype=np.int8)  # -1 outside forest, 0 unknown, 1..5 class
    pine_euc_mask = np.zeros((ny, nx), dtype=bool)
    forest_mask = np.zeros((ny, nx), dtype=bool)
    observable = np.zeros((ny, nx), dtype=bool)
    a4_counts = {str(i): 0 for i in range(1, 6)}
    a4_counts['unknown'] = 0

    two_sigma2 = 2.0 * (float(cfg.firms_sigma_m) ** 2)
    L_urb = max(1.0, float(cfg.urban_decay_m))

    for iy, y_val in enumerate(ys):
        yf = float(y_val)
        for ix, x_val in enumerate(xs):
            xf = float(x_val)
            pt = Point(xf, yf)

            in_forest = bool(fzone.contains(pt) or fzone.intersects(pt))
            forest_mask[iy, ix] = in_forest
            if not in_forest:
                continue  # R = 0 outside forest_zone_utm

            in_a3 = bool(a3_tree is not None and len(a3_tree.query(pt, predicate='intersects')) > 0)
            in_urban = False

            # w_A4 (SENAPRED)
            if a4_tree is not None:
                idxs = a4_tree.query(pt, predicate='intersects')
                if len(idxs) > 0:
                    best_i = max(idxs, key=lambda idx: a4_items[int(idx)][1])
                    p_a4 = a4_items[int(best_i)][1]
                    cls_num = a4_items[int(best_i)][2]
                    a4_class_grid[iy, ix] = cls_num if cls_num in (1, 2, 3, 4, 5) else 0
                    a4_counts[str(cls_num) if cls_num in (1, 2, 3, 4, 5) else 'unknown'] += 1
                else:
                    p_a4 = unknown_w
                    a4_class_grid[iy, ix] = 0
                    a4_counts['unknown'] += 1
            else:
                p_a4 = unknown_w
                a4_class_grid[iy, ix] = 0
                a4_counts['unknown'] += 1

            # F_M2 (CONAF/CIREN 2019)
            if m2_tree is not None:
                idxs = m2_tree.query(pt, predicate='intersects')
                if len(idxs) > 0:
                    f_m2 = max(m2_items[int(i)][1] for i in idxs)
                    pine_euc_mask[iy, ix] = any(m2_items[int(i)][2] for i in idxs)
                else:
                    f_m2 = cfg.fuel_default
            else:
                f_m2 = cfg.fuel_default

            # S(slope, wind_t)
            s_val = slope_wind_factor(terrain, xf, yf, wind_speed, wind_dir, cfg)

            # U(x, y)
            if urban_tree is not None:
                nearest_idx = urban_tree.nearest(pt)
                d_urb = float(pt.distance(urban_geoms[int(nearest_idx)]))
                in_urban = d_urb == 0.0
                u_val = math.exp(-d_urb / L_urb)
            else:
                u_val = cfg.urban_fallback

            observable[iy, ix] = (not in_a3) and (not in_urban)

            # FIRMS_A2 Gaussian kernel
            firms_val = 0.0
            if firms_pts and two_sigma2 > 0:
                for fx, fy, decay in firms_pts:
                    d2 = (xf - fx) ** 2 + (yf - fy) ** 2
                    firms_val += decay * math.exp(-d2 / two_sigma2)
                firms_val *= cfg.firms_weight

            p_a4_grid[iy, ix] = p_a4
            f_m2_grid[iy, ix] = f_m2
            s_grid[iy, ix] = s_val
            u_grid[iy, ix] = u_val
            raw[iy, ix] = p_a4 * f_m2 * s_val * u_val + firms_val

    norm = normalize_risk_array(raw, forest_mask, cfg.normalization_mode if cfg.normalize else 'none')

    total_forest_cells = max(1, int(np.sum(forest_mask)))
    a4_class_pct = {k: round(100.0 * v / total_forest_cells, 2) for k, v in a4_counts.items()}

    total_r = float(np.sum(norm[forest_mask]))
    unobs_r = float(np.sum(norm[forest_mask & (~observable)]))
    unobservable_risk_pct = (100.0 * unobs_r / total_r) if total_r > 0.0 else 0.0

    return RiskField(
        xs=xs,
        ys=ys,
        values=norm,
        raw_values=raw,
        observable=observable,
        forest_mask=forest_mask,
        bounds_utm=(minx, miny, maxx, maxy),
        cell_m=float(xs[1] - xs[0]) if len(xs) > 1 else step,
        config=cfg,
        layer_status=layer_status,
        a4_class_pct=a4_class_pct,
        unobservable_risk_pct=unobservable_risk_pct,
        warnings=warnings,
        components={'p_a4': p_a4_grid, 'f_m2': f_m2_grid, 's': s_grid, 'u': u_grid},
        a4_class_grid=a4_class_grid,
        pine_euc_mask=pine_euc_mask,
    )


def normalize_risk_array(raw: np.ndarray, forest_mask: np.ndarray, mode: str = 'max') -> np.ndarray:
    """Normalize raw risk array inside ``forest_mask`` using 'max', 'log', 'quantile', or 'none'."""
    if mode == 'none' or not np.any(forest_mask):
        return raw.copy()
    f_raw = raw[forest_mask]
    out = np.zeros_like(raw)
    if mode == 'log':
        scale = float(np.percentile(f_raw, 95)) or float(np.max(f_raw)) or 1.0
        logged = np.log1p(f_raw / max(scale * 0.1, 1e-9))
        l_min, l_max = float(np.min(logged)), float(np.max(logged))
        if l_max - l_min > 1e-12:
            out[forest_mask] = (logged - l_min) / (l_max - l_min)
        elif l_max > 0:
            out[forest_mask] = 1.0
        return out
    if mode == 'quantile':
        n = len(f_raw)
        if n <= 1 or float(np.max(f_raw)) == float(np.min(f_raw)):
            out[forest_mask] = 1.0 if float(np.max(f_raw)) > 0 else 0.0
            return out
        ranks = np.argsort(np.argsort(f_raw, kind='mergesort')).astype(float)
        out[forest_mask] = ranks / float(n - 1)
        return out
    # Default: 'max' linear min-max
    r_min = float(np.min(f_raw))
    r_max = float(np.max(f_raw))
    if r_max - r_min > 1e-12:
        out[forest_mask] = (f_raw - r_min) / (r_max - r_min)
    elif r_max > 0.0:
        out[forest_mask] = 1.0
    return out
