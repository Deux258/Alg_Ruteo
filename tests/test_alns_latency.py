"""Unit and integration tests for core.alns (Etapa 4)."""
import math
import unittest

from core.alns import (
    LatencyConfig,
    alns_risk,
    detect_gurobi_license,
    evaluate_task_sequence,
    gurobi_latency_route,
)
from core.patrol import calculate
from tests.test_baseline_regression import FlatTerrain, _regression_fixture


def _synthetic_tasks(n: int = 8):
    tasks = []
    for i in range(n):
        angle = 2.0 * math.pi * i / n
        x = 500.0 + 350.0 * math.cos(angle)
        y = 500.0 + 350.0 * math.sin(angle)
        # Higher prize on later indices so initial order isn't optimal
        prize = float(1 + (i * 3) % 7)
        tasks.append({'id': i, 'centroid_utm': [x, y], 'prize': prize, 'service_s': 20.0})
    return tasks


class AlnsLatencyTests(unittest.TestCase):
    def test_license_detection_and_alns_vs_gurobi_gap(self):
        lic = detect_gurobi_license()
        self.assertIn(lic['tier'], ('restricted', 'full', 'none'))
        tasks = _synthetic_tasks(8)
        stations = [{'id': '104', 'name': 'Base', 'xy': (0.0, 0.0)}]
        dist_fn = lambda a, b: (math.hypot(a[0] - b[0], a[1] - b[1]), 0.01)

        cfg = LatencyConfig(alns_iterations=120, alns_time_limit_s=3.0)
        res1 = alns_risk(tasks, stations, (0.0, 0.0), dist_fn, seed=20261104, config=cfg, station_inventory=20)
        res2 = alns_risk(tasks, stations, (0.0, 0.0), dist_fn, seed=20261104, config=cfg, station_inventory=20)

        self.assertEqual(res1['status'], 'ready')
        self.assertEqual(res1['order'], res2['order'])
        self.assertLessEqual(res1['best_objective'], res1['initial_objective'])

        if lic['available']:
            grb = gurobi_latency_route(tasks, (0.0, 0.0), dist_fn, config=cfg)
            self.assertEqual(grb['status'], 'ready')
            gap = (res1['eval'].weighted_latency + cfg.lambda1_risk * res1['eval'].hazard_cost - grb['objective']) / max(1.0, grb['objective'])
            self.assertGreaterEqual(gap, -0.05)

    def test_station_inventory_1_triggers_recharge_wait(self):
        tasks = _synthetic_tasks(6)
        stations = [{'id': '104', 'name': 'Base', 'xy': (500.0, 500.0)}]
        dist_fn = lambda a, b: (math.hypot(a[0] - b[0], a[1] - b[1]), 0.0)
        cfg = LatencyConfig()
        # Tight battery forces multiple station visits
        ev1 = evaluate_task_sequence(list(range(6)), tasks, stations, (500.0, 500.0), dist_fn, 10.0, 180.0, 1.0, 30.0, 1, 10800.0, cfg)
        ev20 = evaluate_task_sequence(list(range(6)), tasks, stations, (500.0, 500.0), dist_fn, 10.0, 180.0, 1.0, 30.0, 20, 10800.0, cfg)
        self.assertTrue(ev1.feasible)
        self.assertTrue(ev20.feasible)
        self.assertGreater(ev1.recharges, 1)
        self.assertGreater(ev1.total_time_s, ev20.total_time_s + 10000.0)

    def test_patrol_calculate_risk_adaptive_mode(self):
        model, request = _regression_fixture()
        request = dict(request, mode='risk_adaptive')
        res = calculate(model, request, terrain_override=FlatTerrain())
        self.assertIn('alns_risk', res['routes'])
        self.assertEqual(res['routes']['alns_risk']['status'], 'ready')
        self.assertIn('risk_field_summary', res)
        self.assertIn('adaptive_tasks_summary', res)


if __name__ == '__main__':
    unittest.main()
