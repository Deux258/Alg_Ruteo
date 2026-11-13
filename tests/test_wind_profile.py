"""Unit and monotonicity tests for core.wind_profile (Etapa 2)."""
import unittest

import numpy as np

from core.wind_profile import (
    WindConfig,
    WindProfile,
    rothermel_anisotropic_factor,
    sample_wind_perturbation,
    smoke_plume_visible,
    wind_at_agl,
)


class WindProfileTests(unittest.TestCase):
    def test_power_law_agl_monotonic_with_altitude(self):
        u10 = 6.0
        u30 = wind_at_agl(u10, 30.0)
        u60 = wind_at_agl(u10, 60.0)
        u120 = wind_at_agl(u10, 120.0)
        self.assertAlmostEqual(wind_at_agl(u10, 10.0), u10, places=6)
        self.assertLess(u10, u30)
        self.assertLess(u30, u60)
        self.assertLess(u60, u120)

    def test_circular_interpolation_and_uniform_baseline(self):
        records = [
            {'valid_at': '2026-10-19T00:00:00+00:00', 'wind_speed_ms': 4.0, 'wind_direction_deg': 350.0, 'temperature_c': 14.0},
            {'valid_at': '2026-10-19T01:00:00+00:00', 'wind_speed_ms': 8.0, 'wind_direction_deg': 10.0, 'temperature_c': 16.0},
        ]
        wp = WindProfile(records, reference_time='2026-10-19T00:00:00+00:00')
        mid = wp.at(1800.0)
        self.assertAlmostEqual(mid['wind_speed_10m_ms'], 6.0, places=4)
        # Circular midpoint between 350 and 10 is ~0 deg (not 180)
        self.assertTrue(mid['wind_direction_deg'] < 5.0 or mid['wind_direction_deg'] > 355.0)

        # Uniform baseline ignores t=1800s and keeps t=0
        wp_fixed = WindProfile(records, reference_time='2026-10-19T00:00:00+00:00', config=WindConfig(mode='uniform_m4'))
        self.assertAlmostEqual(wp_fixed.at(1800.0)['wind_speed_10m_ms'], 4.0, places=4)

    def test_headwind_vs_tailwind_edge_travel_time(self):
        # Wind FROM West (270 deg) blows toward +x (East)
        records = [{'valid_at': '2026-10-19T00:00:00+00:00', 'wind_speed_ms': 5.0, 'wind_direction_deg': 270.0}]
        wp = WindProfile(records)
        t_tailwind = wp.edge_travel_time((0.0, 0.0, 60.0), (500.0, 0.0, 60.0), 0.0, cruise_ms=10.0, climb_ms=5.0, descent_ms=5.0, agl_m=60.0)
        t_headwind = wp.edge_travel_time((500.0, 0.0, 60.0), (0.0, 0.0, 60.0), 0.0, cruise_ms=10.0, climb_ms=5.0, descent_ms=5.0, agl_m=60.0)
        self.assertLess(t_tailwind, t_headwind)

    def test_rothermel_anisotropic_monotonicity(self):
        # Slope rising toward +x (dz_dx = 0.2). Wind FROM West (270) pushes upslope (+x).
        s_upslope = rothermel_anisotropic_factor(8.0, 270.0, dz_dx=0.2, dz_dy=0.0)
        s_calm = rothermel_anisotropic_factor(0.0, 270.0, dz_dx=0.2, dz_dy=0.0)
        s_downslope = rothermel_anisotropic_factor(8.0, 90.0, dz_dx=0.2, dz_dy=0.0)
        self.assertGreater(s_upslope, s_downslope)
        self.assertGreater(s_upslope, s_calm)

    def test_wind_perturbation_reproducible_and_smoke_plume(self):
        rng1 = np.random.default_rng(20261104)
        rng2 = np.random.default_rng(20261104)
        s1, d1 = sample_wind_perturbation(rng1, 6.0, 225.0)
        s2, d2 = sample_wind_perturbation(rng2, 6.0, 225.0)
        self.assertEqual(s1, s2)
        self.assertEqual(d1, d2)
        self.assertGreater(s1, 0.0)

        # Wind FROM West (270) blows smoke toward +x (East)
        self.assertTrue(smoke_plume_visible((0.0, 0.0), (250.0, 0.0), wind_speed_ms=5.0, wind_direction_deg=270.0, ir_radius_m=100.0))
        self.assertFalse(smoke_plume_visible((0.0, 0.0), (-250.0, 0.0), wind_speed_ms=5.0, wind_direction_deg=270.0, ir_radius_m=100.0))


if __name__ == '__main__':
    unittest.main()
