"""Time-varying wind profile, AGL power-law correction, anisotropic fire spread,
and stochastic wind perturbations (Etapa 2).

Data limitations (ECMWF IFS 0.25 deg snapshot):
    - Single grid cell returned at (-33.0, -71.5) for requested (-33.0784, -71.6163).
    - No sub-grid canyon/quebrada channeling.
    - 48-hour retrospective horizon (October 2026), not a live operational forecast.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any

import numpy as np

from core.aerial_data import iso
from core.risk_field import wind_vector_xy


@dataclass(frozen=True)
class WindConfig:
    """Central configuration for wind modeling and uncertainty."""

    mode: str = 'ecmwf_profile'  # 'uniform_m4' (baseline fijo) | 'ecmwf_profile' (interpolado 48h)
    ref_height_m: float = 10.0
    power_law_alpha: float = 1.0 / 7.0  # Hellmann/power-law exponent (1/7 neutral)
    # Rothermel-like ellipse: length/width ratio L_B = 1 + lw_coeff * wind_ms
    rothermel_lw_coeff: float = 0.25
    rothermel_max_lw: float = 4.0
    # Stochastic perturbations for Fase 5 (lognormal speed, von Mises direction)
    lognormal_sigma: float = 0.20
    von_mises_kappa: float = 6.0
    # Optional flags
    headwind_swath_orientation: bool = False
    smoke_plume_max_m: float = 350.0


def wind_at_agl(
    wind_10m_ms: float,
    agl_m: float,
    ref_height_m: float = 10.0,
    alpha: float = 1.0 / 7.0,
) -> float:
    """Scale 10 m wind speed to drone AGL altitude via power law: U(z) = U_ref * (z / z_ref)^alpha."""
    u = max(0.0, float(wind_10m_ms))
    z = max(1.0, float(agl_m))
    z_ref = max(1.0, float(ref_height_m))
    return u * ((z / z_ref) ** float(alpha))


def rothermel_anisotropic_factor(
    wind_speed_ms: float,
    wind_direction_deg: float,
    dz_dx: float,
    dz_dy: float,
    beta1_slope: float = 0.50,
    beta2_wind: float = 0.08,
    max_tan_slope: float = 2.0,
    lw_coeff: float = 0.25,
    max_lw: float = 4.0,
) -> float:
    """Simplified Rothermel elliptical spread factor S_aniso(slope, wind_t).

    - Length-to-width ratio L/W = min(max_lw, 1 + lw_coeff * wind_speed_ms).
    - Eccentricity e = sqrt(1 - 1 / (L/W)^2).
    - Combines upslope bias ``1 + beta1 * tan(slope)`` with elliptical wind-slope
      alignment ``(1 + e) / (1 - e * cos(theta_w - theta_a))`` scaled by ``beta2``.
    """
    tan_slope = min(float(max_tan_slope), math.hypot(dz_dx, dz_dy))
    base_slope = 1.0 + float(beta1_slope) * tan_slope

    w = max(0.0, float(wind_speed_ms))
    if w <= 1e-6:
        return base_slope

    lw = min(float(max_lw), 1.0 + float(lw_coeff) * w)
    ecc = math.sqrt(max(0.0, 1.0 - 1.0 / (lw * lw))) if lw > 1.0 else 0.0

    cos_align = 0.0
    if tan_slope > 1e-6:
        vx, vy = wind_vector_xy(1.0, wind_direction_deg)
        ux, uy = dz_dx / tan_slope, dz_dy / tan_slope
        cos_align = max(-1.0, min(1.0, vx * ux + vy * uy))

    # Elliptical directional multiplier: max when wind blows upslope (cos_align = +1)
    ellipse_gain = (1.0 + ecc) / max(0.25, 1.0 - ecc * max(0.0, cos_align))
    return base_slope + float(beta2_wind) * w * max(0.0, ellipse_gain - 1.0 + max(0.0, cos_align))


class WindProfile:
    """Interpolated 48-hour M4 ECMWF IFS 0.25 deg wind & weather series."""

    def __init__(
        self,
        records_m4: list[dict[str, Any]],
        reference_time: str | None = None,
        config: WindConfig | None = None,
    ):
        self.config = config or WindConfig()
        self.records = list(records_m4 or [])
        self.requested_coords = (-33.078420, -71.616327)
        self.ecmwf_cell_coords = None

        parsed: list[tuple[float, dict[str, Any]]] = []
        ref_dt: datetime | None = None
        if reference_time:
            try:
                ref_dt = iso(reference_time)
            except Exception:
                ref_dt = None

        for rec in self.records:
            if self.ecmwf_cell_coords is None and rec.get('cell'):
                c = rec['cell']
                self.ecmwf_cell_coords = (float(c[1]), float(c[0]))  # (lat, lon)
            dt: datetime | None = None
            if rec.get('valid_at'):
                try:
                    dt = iso(rec['valid_at'])
                except Exception:
                    dt = None
            if ref_dt is None and dt is not None:
                ref_dt = dt
            t_s = (dt - ref_dt).total_seconds() if (dt is not None and ref_dt is not None) else float(len(parsed) * 3600)
            parsed.append((t_s, rec))

        parsed.sort(key=lambda item: item[0])
        self._times = np.array([p[0] for p in parsed], dtype=float) if parsed else np.array([0.0])
        if parsed:
            self._speeds = np.array([float(p[1].get('wind_speed_ms') or 0.0) for p in parsed], dtype=float)
            self._gusts = np.array([float(p[1].get('wind_gust_ms') or p[1].get('wind_speed_ms') or 0.0) for p in parsed], dtype=float)
            self._temps = np.array([float(p[1].get('temperature_c') or 20.0) for p in parsed], dtype=float)
            vecs = [wind_vector_xy(1.0, float(p[1].get('wind_direction_deg') or 0.0)) for p in parsed]
            self._vx = np.array([v[0] for v in vecs], dtype=float)
            self._vy = np.array([v[1] for v in vecs], dtype=float)
        else:
            self._speeds = np.array([0.0])
            self._gusts = np.array([0.0])
            self._temps = np.array([20.0])
            self._vx = np.array([0.0])
            self._vy = np.array([-1.0])

    def at(self, t_s: float, agl_m: float | None = None) -> dict[str, float]:
        """Return interpolated weather at ``t_s`` seconds, optionally scaled to ``agl_m``."""
        if self.config.mode == 'uniform_m4' or len(self._times) <= 1:
            t_q = float(self._times[0])
        else:
            t_q = max(float(self._times[0]), min(float(self._times[-1]), float(t_s)))

        speed_10 = float(np.interp(t_q, self._times, self._speeds))
        gust_10 = float(np.interp(t_q, self._times, self._gusts))
        temp_c = float(np.interp(t_q, self._times, self._temps))
        vx = float(np.interp(t_q, self._times, self._vx))
        vy = float(np.interp(t_q, self._times, self._vy))
        # Recover meteorological direction FROM which wind blows
        if math.hypot(vx, vy) > 1e-9:
            dir_deg = (math.degrees(math.atan2(-vx, -vy)) + 360.0) % 360.0
        else:
            dir_deg = 0.0

        speed_agl = wind_at_agl(speed_10, agl_m, self.config.ref_height_m, self.config.power_law_alpha) if agl_m is not None else speed_10
        gust_agl = wind_at_agl(gust_10, agl_m, self.config.ref_height_m, self.config.power_law_alpha) if agl_m is not None else gust_10
        return {
            'wind_speed_10m_ms': speed_10,
            'wind_speed_ms': speed_agl,
            'wind_gust_ms': gust_agl,
            'wind_direction_deg': dir_deg,
            'temperature_c': temp_c,
        }

    def edge_travel_time(
        self,
        a_utm: tuple[float, float, float],
        b_utm: tuple[float, float, float],
        t_depart_s: float,
        cruise_ms: float,
        climb_ms: float,
        descent_ms: float,
        agl_m: float = 60.0,
    ) -> float:
        """Compute flight time t_ij(t_depart_s) using AGL-corrected wind at departure time."""
        dx = float(b_utm[0] - a_utm[0])
        dy = float(b_utm[1] - a_utm[1])
        dz = float(b_utm[2] - a_utm[2])
        horiz = math.hypot(dx, dy)
        if horiz < 1e-6 and abs(dz) < 1e-6:
            return 0.0
        w = self.at(t_depart_s, agl_m=agl_m)
        wx, wy = wind_vector_xy(w['wind_speed_ms'], w['wind_direction_deg'])
        if horiz > 1e-6:
            ux, uy = dx / horiz, dy / horiz
            w_along = wx * ux + wy * uy
            w_cross = abs(wx * (-uy) + wy * ux)
            air_sq = max(1.0, float(cruise_ms) ** 2 - w_cross ** 2)
            v_ground = max(1.0, math.sqrt(air_sq) + w_along)
            t_h = horiz / v_ground
        else:
            t_h = 0.0
        t_v = (dz / max(0.5, climb_ms)) if dz > 0 else (-dz / max(0.5, descent_ms))
        return max(t_h, t_v)

    def hourly_windows(self, horizon_h: int = 48, agl_m: float = 60.0) -> list[dict[str, float]]:
        """Discrete hourly wind summary for MILP time-window formulations."""
        return [dict(hour=float(h), **self.at(h * 3600.0, agl_m=agl_m)) for h in range(max(1, int(horizon_h)))]


def sample_wind_perturbation(
    rng: np.random.Generator,
    wind_speed_ms: float,
    wind_direction_deg: float,
    config: WindConfig | None = None,
) -> tuple[float, float]:
    """Sample perturbed (speed_ms, direction_deg) using lognormal + von Mises."""
    cfg = config or WindConfig()
    sigma = max(0.0, float(cfg.lognormal_sigma))
    if sigma > 0.0:
        # Mean-1 lognormal multiplier: exp(N(-0.5*sigma^2, sigma^2))
        mult = float(rng.lognormal(mean=-0.5 * sigma * sigma, sigma=sigma))
    else:
        mult = 1.0
    speed_p = max(0.0, float(wind_speed_ms) * mult)

    kappa = max(0.0, float(cfg.von_mises_kappa))
    if kappa > 0.0:
        delta_rad = float(rng.vonmises(mu=0.0, kappa=kappa))
        dir_p = (float(wind_direction_deg) + math.degrees(delta_rad) + 360.0) % 360.0
    else:
        dir_p = float(wind_direction_deg) % 360.0
    return speed_p, dir_p


def smoke_plume_visible(
    fire_xy: tuple[float, float],
    drone_xy: tuple[float, float],
    wind_speed_ms: float,
    wind_direction_deg: float,
    ir_radius_m: float,
    plume_max_m: float = 350.0,
    plume_half_angle_deg: float = 22.5,
) -> bool:
    """Return True if drone observes fire via IR cone OR leeward smoke plume (2D check; LOS checked by caller)."""
    dx = drone_xy[0] - fire_xy[0]
    dy = drone_xy[1] - fire_xy[1]
    dist = math.hypot(dx, dy)
    if dist <= ir_radius_m:
        return True
    if wind_speed_ms < 1.5 or dist > plume_max_m or dist <= 1e-6:
        return False
    # Smoke drifts leeward in direction of wind_vector_xy
    wx, wy = wind_vector_xy(1.0, wind_direction_deg)
    cos_ang = (dx * wx + dy * wy) / dist
    return cos_ang >= math.cos(math.radians(plume_half_angle_deg))
