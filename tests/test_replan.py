"""Unit tests for core.replan (Etapa 6)."""
import math
import unittest

from shapely.geometry import Point, box, mapping
from shapely.ops import transform

from core.aerial_data import FWD, INV, iso
from core.patrol import Graph, Hazards, defaults
from core.replan import ReplanTrigger, redundant_return_corridors, replan_mission


class FlatTerrain:
    def at(self, x, y):
        return 0.0

    def visible(self, a, b):
        return True


class ReplanTests(unittest.TestCase):
    def test_mid_mission_synthetic_firms_and_wind_gust_under_1s(self):
        tasks = [
            {'id': i, 'centroid_utm': [200.0 + 90.0 * i, 300.0 + (i % 2) * 100.0], 'prize': 1.0, 'service_s': 15.0}
            for i in range(12)
        ]
        stations = [{'id': '104', 'name': 'Base 1', 'xy': (0.0, 0.0)}, {'id': '105', 'name': 'Base 2', 'xy': (1100.0, 300.0)}]
        dist_fn = lambda a, b: (math.hypot(a[0] - b[0], a[1] - b[1]), 0.01)

        trig = ReplanTrigger(
            kind='new_a2_firms',
            elapsed_s=300.0,
            current_xy=(500.0, 300.0),
            remaining_battery_s=900.0,
            synthetic_firms_xy=(1700.0, 420.0),
            wind_speed_ms=7.0,
            wind_direction_deg=270.0,
        )
        rep = replan_mission(tasks, stations, trig, dist_fn, time_limit_s=0.6)
        self.assertEqual(rep['status'], 'ready')
        self.assertLess(rep['compute_s'], 1.0)
        self.assertEqual(len(rep['order']), 12)

    def test_redundant_k2_return_corridors_on_graph(self):
        x0, y0 = FWD(-71.65, -33.1)
        area = box(x0 - 300, y0 - 300, x0 + 300, y0 + 300)
        weather = dict(valid_at='2026-10-19T00:00:00+00:00', wind_speed_ms=0.0, wind_gust_ms=0.0, wind_direction_deg=0.0, temperature_c=20.0)
        model = dict(
            study_geometry=mapping(transform(INV, area)),
            flight_geometry=mapping(transform(INV, area)),
            reference_time=weather['valid_at'],
            records=dict(M1=[dict(provider_id='104', name='B1', candidate=True, geometry=mapping(transform(INV, Point(x0, y0))))], M2=[], M3=[], M4=[weather], A1=[], A2=[], A3=[], A4=[]),
        )
        p = defaults()
        g = Graph(area, FlatTerrain(), Hazards(model, iso(weather['valid_at']), p, []), weather, p)
        s_node = g.point([*INV(x0, y0)])
        src_node = g.point([*INV(x0 + 150, y0 + 150)])
        res = redundant_return_corridors(g, src_node, [s_node], k=2)
        self.assertGreaterEqual(res['edge_disjoint_paths'], 2)
        self.assertTrue(res['resilient_k2'])


if __name__ == '__main__':
    unittest.main()
