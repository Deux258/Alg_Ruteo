"""Unit tests for core.risk_field (Fase 1a)."""
import unittest

import numpy as np
from shapely.geometry import Point, box, mapping
from shapely.ops import transform

from core.aerial_data import FWD, INV
from core.risk_field import (
    RiskConfig,
    compute_risk_field,
    fuel_coefficient,
    slope_wind_factor,
    wind_vector_xy,
)


class SlopedTerrain:
    """Synthetic hill rising toward +x (East): z(x, y) = 0.2 * (x - x0)."""

    def __init__(self, x0: float):
        self.x0 = x0

    def at(self, x: float, y: float) -> float:
        return 0.2 * (x - self.x0)


class RiskFieldTests(unittest.TestCase):
    def test_config_min_cell_respects_dsm_resolution(self):
        cfg = RiskConfig()
        self.assertGreaterEqual(cfg.min_cell_m, 30.0)
        self.assertEqual(cfg.urban_decay_m, 300.0)
        self.assertEqual(cfg.a4_unknown_pct, 20.0)
        self.assertAlmostEqual(cfg.dsm_dx_m, 25.9, places=1)
        self.assertAlmostEqual(cfg.dsm_dy_m, 30.9, places=1)

    def test_fuel_coefficient_hierarchy(self):
        cfg = RiskConfig()
        eucalipto = {
            'category': 'Bosques',
            'attributes': {'subuse': 'Plantación'},
            'original_record': {'especi1_co': 'eucalipto'},
        }
        nativo = {
            'category': 'Bosques',
            'attributes': {'subuse': 'Bosque Nativo'},
            'original_record': {'especi1_co': 'boldo'},
        }
        matorral = {
            'category': 'Praderas y Matorrales',
            'attributes': {'subuse': 'Matorral'},
        }
        pradera = {
            'category': 'Praderas y Matorrales',
            'attributes': {'subuse': 'Praderas'},
        }
        self.assertGreater(fuel_coefficient(eucalipto, cfg), fuel_coefficient(nativo, cfg))
        self.assertGreater(fuel_coefficient(nativo, cfg), fuel_coefficient(matorral, cfg))
        self.assertGreater(fuel_coefficient(matorral, cfg), fuel_coefficient(pradera, cfg))

    def test_wind_convention_from_direction_and_upslope_risk(self):
        cfg = RiskConfig()
        # 0 deg = wind FROM North -> blows South (vy < 0)
        vx0, vy0 = wind_vector_xy(10.0, 0.0)
        self.assertAlmostEqual(vx0, 0.0, places=6)
        self.assertAlmostEqual(vy0, -10.0, places=6)
        # 270 deg = wind FROM West -> blows East (+x)
        vx270, vy270 = wind_vector_xy(10.0, 270.0)
        self.assertAlmostEqual(vx270, 10.0, places=6)
        self.assertAlmostEqual(vy270, 0.0, places=6)

        x0, y0 = FWD(-71.65, -33.1)
        terrain = SlopedTerrain(x0)
        # Hill rises toward +x (East): wind FROM West (270) pushes fire upslope (+x)
        s_upslope = slope_wind_factor(terrain, x0 + 100, y0, wind_speed_ms=10.0, wind_direction_deg=270.0, config=cfg)
        # Wind FROM East (90) pushes downslope (-x)
        s_downslope = slope_wind_factor(terrain, x0 + 100, y0, wind_speed_ms=10.0, wind_direction_deg=90.0, config=cfg)
        self.assertGreater(s_upslope, s_downslope)

    def test_a3_unobservable_preserves_risk_and_non_forest_is_zero(self):
        x0, y0 = FWD(-71.65, -33.1)
        area_utm = box(x0, y0, x0 + 600, y0 + 300)
        forest_utm = box(x0, y0, x0 + 420, y0 + 300)
        a3_utm = box(x0 + 60, y0 + 60, x0 + 210, y0 + 240)

        model = {
            'reference_time': '2026-11-04T12:00:00+00:00',
            'records': {
                'M2': [{'category': 'Bosques', 'attributes': {'subuse': 'Plantación'}, 'geometry': mapping(transform(INV, forest_utm))}],
                'A4': [{'ordinal_class': 4, 'geometry': mapping(transform(INV, forest_utm))}],
                'A3': [{'provider_id': 'a3-test', 'geometry': mapping(transform(INV, a3_utm))}],
                'A2': [],
                'M4': [{'wind_speed_ms': 4.0, 'wind_direction_deg': 270.0}],
            },
        }
        field = compute_risk_field(
            model,
            area_utm,
            terrain=SlopedTerrain(x0),
            buildings_utm=[],
            forest_zone_utm=forest_utm,
        )
        # Inside A3: R > 0 preserved, observable == False
        self.assertGreater(field.at(x0 + 135, y0 + 150), 0.0)
        in_a3_mask = np.zeros_like(field.observable)
        for iy, yv in enumerate(field.ys):
            for ix, xv in enumerate(field.xs):
                if a3_utm.contains(Point(float(xv), float(yv))):
                    in_a3_mask[iy, ix] = True
        self.assertTrue(np.any(in_a3_mask))
        self.assertFalse(np.any(field.observable[in_a3_mask]))
        self.assertTrue(np.all(field.raw_values[in_a3_mask] > 0.0))
        self.assertGreater(field.unobservable_risk_pct, 0.0)

        # Outside forest_zone_utm: R == 0 and observable == False
        outside_mask = ~field.forest_mask
        self.assertTrue(np.any(outside_mask))
        self.assertTrue(np.all(field.values[outside_mask] == 0.0))
        self.assertFalse(np.any(field.observable[outside_mask]))

    def test_a4_unknown_pct_sensitivity_5_10_20(self):
        x0, y0 = FWD(-71.65, -33.1)
        area_utm = box(x0, y0, x0 + 600, y0 + 300)
        known_utm = box(x0, y0, x0 + 300, y0 + 300)
        model = {
            'reference_time': '2026-11-04T12:00:00+00:00',
            'records': {
                'M2': [{'category': 'Bosques', 'attributes': {'subuse': 'Bosque Nativo'}, 'geometry': mapping(transform(INV, area_utm))}],
                'A4': [{'ordinal_class': 2, 'geometry': mapping(transform(INV, known_utm))}],
                'A2': [],
                'A3': [],
                'M4': [{'wind_speed_ms': 3.0, 'wind_direction_deg': 270.0}],
            },
        }
        means = {}
        for pct in (5.0, 10.0, 20.0):
            f = compute_risk_field(model, area_utm, terrain=SlopedTerrain(x0), buildings_utm=[], forest_zone_utm=area_utm, config=RiskConfig(a4_unknown_pct=pct))
            means[pct] = float(np.mean(f.raw_values))
            self.assertIn('unknown', f.a4_class_pct)
            self.assertGreater(f.a4_class_pct['unknown'], 40.0)
        self.assertLess(means[5.0], means[10.0])
        self.assertLess(means[10.0], means[20.0])

    def test_firms_empty_vs_unknown_and_synthetic_hotspot(self):
        x0, y0 = FWD(-71.65, -33.1)
        area_utm = box(x0, y0, x0 + 300, y0 + 300)
        base_records = {
            'M2': [{'category': 'Bosques', 'geometry': mapping(transform(INV, area_utm))}],
            'A4': [{'ordinal_class': 3, 'geometry': mapping(transform(INV, area_utm))}],
            'A3': [],
            'M4': [{'wind_speed_ms': 0.0, 'wind_direction_deg': 0.0}],
        }
        # Empty A2
        f_empty = compute_risk_field({'records': dict(base_records, A2=[])}, area_utm, buildings_utm=[])
        self.assertEqual(f_empty.layer_status['A2'], 'empty')

        # Unknown A2 (key missing)
        f_unknown = compute_risk_field({'records': dict(base_records)}, area_utm, buildings_utm=[])
        self.assertEqual(f_unknown.layer_status['A2'], 'unknown')

        # Synthetic FIRMS hotspot (explicitly labeled synthetic)
        firms_pt = Point(x0 + 150, y0 + 150)
        f_syn = compute_risk_field(
            {'reference_time': '2026-11-04T12:00:00+00:00', 'records': dict(base_records, A2=[{'acquired_at': '2026-11-04T11:30:00+00:00', 'synthetic': True, 'geometry': mapping(transform(INV, firms_pt))}])},
            area_utm,
            buildings_utm=[],
        )
        self.assertEqual(f_syn.layer_status['A2'], 'populated')
        self.assertGreater(f_syn.at(x0 + 150, y0 + 150), f_syn.at(x0 + 10, y0 + 10))


if __name__ == '__main__':
    unittest.main()
