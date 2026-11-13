"""Unit tests for core.ignition_sim (Etapa 5)."""
import unittest

from shapely.geometry import box, mapping
from shapely.ops import transform

from core.aerial_data import FWD, INV
from core.ignition_sim import (
    detect_fire_along_trajectory,
    evaluate_route_robustness,
    sample_ignitions,
    wilson_ci95,
)
from core.risk_field import RiskConfig, compute_risk_field


class FlatTerrain:
    def at(self, x, y):
        return 0.0

    def visible(self, a, b):
        return True


class IgnitionSimTests(unittest.TestCase):
    def test_wilson_ci_and_reproducible_ignitions(self):
        lo, hi = wilson_ci95(950, 1000)
        self.assertGreater(lo, 0.93)
        self.assertLess(hi, 0.97)

        x0, y0 = FWD(-71.65, -33.1)
        area = box(x0, y0, x0 + 300, y0 + 300)
        model = {
            'records': {
                'M2': [{'category': 'Bosques', 'geometry': mapping(transform(INV, area))}],
                'A4': [{'ordinal_class': 3, 'geometry': mapping(transform(INV, area))}],
                'A2': [],
                'A3': [],
                'M4': [{'wind_speed_ms': 3.0, 'wind_direction_deg': 270.0}],
            }
        }
        field = compute_risk_field(model, area, buildings_utm=[], config=RiskConfig(grid_cell_m=30.0))
        ign1 = sample_ignitions(field, terrain=FlatTerrain(), n_ignitions=100, seed=20261104)
        ign2 = sample_ignitions(field, terrain=FlatTerrain(), n_ignitions=100, seed=20261104)
        self.assertEqual(len(ign1), 100)
        self.assertEqual([(e.x_utm, e.y_utm, e.t_ign_s) for e in ign1], [(e.x_utm, e.y_utm, e.t_ign_s) for e in ign2])

        # Trajectory passing near center detects earlier than one far away
        tl_near = [(x0, y0, 60.0, 0.0), (x0 + 150, y0 + 150, 60.0, 30.0), (x0 + 300, y0 + 300, 60.0, 60.0)]
        t_det = detect_fire_along_trajectory(tl_near, (x0 + 155, y0 + 155, 0.0), effective_view_r=100.0, terrain=FlatTerrain(), t_ign_s=10.0)
        self.assertEqual(t_det, 30.0)

        route = {'method': 'test_route', 'status': 'ready', 'coordinates_utm': [[x0, y0, 60.0], [x0 + 150, y0 + 150, 60.0], [x0 + 300, y0 + 300, 60.0]], 'time_s': 60.0, 'distance_m': 424.0, 'stops': []}
        ev = evaluate_route_robustness(route, ign1, field, terrain=FlatTerrain(), effective_view_r=120.0)
        self.assertGreaterEqual(ev['CVaR_95_s'], ev['E_D_s'])
        self.assertEqual(len(ev['risk_curve']), 7)


if __name__ == '__main__':
    unittest.main()
