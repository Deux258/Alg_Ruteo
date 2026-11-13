"""Unit tests for core.adaptive_tasks (Etapa 3)."""
import unittest

from shapely.geometry import Point, box, mapping
from shapely.ops import transform, unary_union

from core.aerial_data import FWD, INV, iso
from core.adaptive_tasks import AdaptiveTaskConfig, build_adaptive_tasks
from core.patrol import Graph, Hazards, defaults, oriented_tasks
from core.risk_field import RiskConfig, compute_risk_field


class FlatTerrain:
    source_sha256 = 'flat-adaptive-test'

    def at(self, x, y):
        return 0.0

    def visible(self, a, b):
        return True


class AdaptiveTasksTests(unittest.TestCase):
    def test_quadtree_coverage_a3_exclusion_and_density_spearman(self):
        x0, y0 = FWD(-71.65, -33.1)
        area = box(x0 - 200, y0 - 200, x0 + 1000, y0 + 1000)
        target = box(x0, y0, x0 + 800, y0 + 800)
        forest = box(x0, y0, x0 + 700, y0 + 800)  # excludes x in [700, 800] (non-forest)
        a3 = box(x0 + 50, y0 + 50, x0 + 200, y0 + 200)  # restricted A3 inside target
        high_risk_zone = box(x0 + 400, y0 + 400, x0 + 700, y0 + 800)
        building = box(x0 + 680, y0 + 680, x0 + 720, y0 + 720)

        weather = dict(valid_at='2026-10-19T00:00:00+00:00', wind_speed_ms=3.0, wind_gust_ms=4.0, wind_direction_deg=270.0, temperature_c=18.0)
        model = dict(
            study_geometry=mapping(transform(INV, area)),
            flight_geometry=mapping(transform(INV, area)),
            reference_time=weather['valid_at'],
            records=dict(
                M1=[dict(provider_id='104', name='Base', candidate=True, geometry=mapping(transform(INV, Point(x0 - 50, y0 + 400))))],
                M2=[dict(category='Bosques', attributes={'subuse': 'Plantación'}, original_record={'especi1_co': 'eucalipto'}, geometry=mapping(transform(INV, forest)))],
                M3=[],
                M4=[weather],
                A1=[],
                A2=[],
                A3=[dict(provider_id='a3-1', geometry=mapping(transform(INV, a3)))],
                A4=[
                    dict(provider_id='a4-1', ordinal_class=1, geometry=mapping(transform(INV, forest))),
                    dict(provider_id='a4-5', ordinal_class=5, geometry=mapping(transform(INV, high_risk_zone))),
                ],
            ),
        )
        p = defaults()
        graph = Graph(area, FlatTerrain(), Hazards(model, iso(model['reference_time']), p, []), weather, p)
        field = compute_risk_field(model, area, terrain=FlatTerrain(), buildings_utm=[building], forest_zone_utm=forest, config=RiskConfig(grid_cell_m=30.0))

        tset = build_adaptive_tasks(
            graph=graph,
            target_utm=target,
            field=field,
            swath_m=p['swath_m'],
            a3_geoms_utm=[a3],
            forest_zone_utm=forest,
            terrain=FlatTerrain(),
            risk_config=field.config,
            task_config=AdaptiveTaskConfig(min_cell_m=30.0, max_depth=3),
        )

        self.assertGreater(len(tset.tasks), 1)
        self.assertGreater(tset.unobservable_risk, 0.0)
        self.assertGreater(tset.track_density_spearman, 0.0)

        # No task centroid inside A3 or outside forest
        for t in tset.tasks:
            cx, cy = t['centroid_utm']
            self.assertFalse(a3.contains(Point(cx, cy)))
            self.assertTrue(forest.buffer(1.0).contains(Point(cx, cy)))

        # Union of cells covers allowed forested area (target ∩ forest \ a3)
        allowed = target.intersection(forest).difference(a3)
        cells_union = unary_union([box(*c['bounds']) for c in tset.cells])
        self.assertGreater(cells_union.intersection(allowed).area / allowed.area, 0.99)

        # Minimum cell size >= 30 m
        for c in tset.cells:
            bx0, by0, bx1, by1 = c['bounds']
            self.assertGreaterEqual(min(bx1 - bx0, by1 - by0), 30.0 - 1e-6)

        # Directly consumable by core.patrol.oriented_tasks
        ot = oriented_tasks(tset.tasks, graph, 'cost')
        self.assertGreaterEqual(len(ot), len(tset.tasks))


if __name__ == '__main__':
    unittest.main()
