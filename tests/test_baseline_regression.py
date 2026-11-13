"""Regression test freezing the 4 baseline routing methods with a fixed seed.

Compares against the frozen snapshot in
``tests/fixtures/baseline_regression_expected.json`` generated from the
untouched ``core/patrol.py`` before any risk-adaptive changes.
"""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from shapely.geometry import box, mapping
from shapely.ops import transform

from core.aerial_data import FWD, INV
from core.patrol import calculate, defaults


class FlatTerrain:
    source_sha256 = 'flat-regression-only'

    def at(self, x, y):
        return 0.0

    def visible(self, a, b):
        return True


def _regression_fixture():
    x, y = FWD(-71.65, -33.1)
    area = box(x - 500, y - 500, x + 700, y + 500)
    target = box(x + 150, y - 100, x + 350, y + 100)
    weather = dict(
        valid_at='2026-11-04T12:00:00+00:00',
        wind_speed_ms=2.0,
        wind_gust_ms=3.0,
        wind_direction_deg=180.0,
        temperature_c=20.0,
    )
    model = dict(
        study_geometry=mapping(transform(INV, area)),
        flight_geometry=mapping(transform(INV, area)),
        reference_time=weather['valid_at'],
        records=dict(
            M1=[dict(
                provider_id='104',
                name='Base Regresion',
                candidate=True,
                geometry=dict(type='Point', coordinates=[-71.65, -33.1]),
            )],
            M2=[],
            M3=[],
            M4=[weather],
            A1=[],
            A2=[],
            A3=[],
            A4=[dict(
                provider_id='reg-a4-1',
                geometry=mapping(transform(INV, area)),
                ordinal_class=2,
            )],
        ),
    )
    request = dict(
        target_polygon=mapping(transform(INV, target)),
        origin=[-71.65, -33.1],
        station_ids=['104'],
        seed=20261104,
        scenarios=50,
    )
    return model, request


class BaselineRegressionTests(unittest.TestCase):
    def test_four_baselines_frozen_with_fixed_seed(self):
        model, request = _regression_fixture()
        p = defaults()
        p.update(solver_seconds=2, annealing_iterations=200)
        with patch('core.patrol.defaults', return_value=p):
            res1 = calculate(model, request, terrain_override=FlatTerrain())
            res2 = calculate(model, request, terrain_override=FlatTerrain())

        expected_methods = ('dijkstra_distance', 'dijkstra_weighted', 'gurobi', 'annealing')
        self.assertEqual(set(res1['routes'].keys()), set(expected_methods))

        fixture_path = Path(__file__).resolve().parent / 'fixtures' / 'baseline_regression_expected.json'
        frozen = json.loads(fixture_path.read_text(encoding='utf-8'))

        for method in expected_methods:
            r1 = res1['routes'][method]
            r2 = res2['routes'][method]
            expected = frozen[method]
            self.assertEqual(r1['status'], expected['status'], f'{method} status mismatch')
            self.assertEqual(r1['status'], r2['status'])
            self.assertAlmostEqual(r1['coverage']['percent'], expected['coverage_percent'], places=2)
            self.assertTrue(r1['coverage']['complete'])
            self.assertGreater(len(r1['coordinates']), 2)
            if method == 'gurobi':
                # Gurobi may pick an alternate optimum with identical/close cost and coverage
                self.assertAlmostEqual(r1['cost'], expected['cost'], delta=max(0.5, 0.01 * expected['cost']))
                self.assertAlmostEqual(r1['coverage']['percent'], r2['coverage']['percent'], places=2)
            else:
                self.assertEqual(r1['edge_ids'], expected['edge_ids'], f'{method} edge_ids drifted')
                self.assertEqual(r1['edge_ids'], r2['edge_ids'], f'{method} must be deterministic')
                self.assertAlmostEqual(r1['time_s'], expected['time_s'], places=4)
                self.assertAlmostEqual(r1['distance_m'], expected['distance_m'], places=4)
                self.assertAlmostEqual(r1['cost'], expected['cost'], places=4)


if __name__ == '__main__':
    unittest.main()
