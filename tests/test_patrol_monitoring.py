import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import transform, unary_union

from core.aerial_data import FWD, INV
from core.patrol import simulate,validate_polygon
from core.patrol_events import generate
from core.patrol_monitoring import catalogue, resolve, record, progress, metric_area
from tests.test_patrol import fixture, FlatTerrain


class MonitoringTests(unittest.TestCase):
    def test_partition_covers_whole_polygon_including_holes_and_components(self):
        model,*_=fixture();x,y=FWD(-71.65,-33.1)
        metric=Polygon(box(x,y,x+1400,y+1000).exterior.coords,[box(x+420,y+200,x+610,y+500).exterior.coords])
        metric=metric.union(box(x+1800,y,x+1900,y+150))
        model['study_geometry']=mapping(transform(INV,metric))
        with tempfile.TemporaryDirectory() as folder,patch('core.patrol_monitoring.DIRECTORY',Path(folder)):
            catalog=catalogue(model)
        parts=[transform(FWD,shape(s['target_polygon'])) for s in catalog['sectors']]
        self.assertTrue(catalog['partition_complete'])
        geographic_union=unary_union([shape(s['target_polygon']) for s in catalog['sectors']])
        self.assertLess(metric_area(shape(model['study_geometry']).symmetric_difference(geographic_union)),.01)
        self.assertLess(abs(sum(p.area for p in parts)-metric.area)/metric.area,.0001)
        self.assertEqual(catalog['progress']['percent'],0)
        self.assertTrue(all(shape(model['study_geometry']).buffer(1e-10).covers(shape(s['target_polygon'])) for s in catalog['sectors']))
        for sector in catalog['sectors']:
            if sector['area_m2']>=1:validate_polygon(sector,shape(model['study_geometry']))
        self.assertEqual(catalogue(model)['sha256'],catalog['sha256'])

    def test_server_resolves_route_and_owns_persistence_keys(self):
        model,*_=fixture();catalog=catalogue(model);sector=next(s for s in catalog['sectors'] if s['area_m2']>=1)
        req=resolve(model,dict(patrol_id=sector['id'],target_polygon={},monitoring_catalogue_sha256='../../outside'))
        self.assertEqual(req['target_polygon'],sector['target_polygon'])
        self.assertEqual(req['monitoring_catalogue_sha256'],catalog['sha256'])
        self.assertNotIn('monitoring_catalogue_sha256',resolve(model,dict(monitoring_catalogue_sha256='bad')))
        with self.assertRaises(ValueError): resolve(model,dict(patrol_id='stale'))

    def result(self):
        model,request,*_=fixture();x,y=FWD(*request['origin'])
        position=lambda dx:[*INV(x+dx,y),60.]
        edges=[dict(id='1',source='h',target='a',time_s=20,cost=20,distance_m=200,probability=0,hazard_ids=[],coordinates=[position(v) for v in (0,50,100,150,200)]),
               dict(id='2',source='a',target='h',time_s=20,cost=20,distance_m=200,probability=0,hazard_ids=[],coordinates=[position(v) for v in (200,150,100,50,0)])]
        from core.patrol import defaults
        p=defaults();p.update(solver_seconds=1,annealing_iterations=5)
        result=dict(sha256='monitor-fixture',request=request,time=model['reference_time'],effective_profile=p,weather=model['records']['M4'][0],
                    target_polygon=mapping(transform(INV,box(x+160,y-20,x+200,y+20))),threats=[],stations=[],failure_probabilities={'nodes':[]},
                    graph=dict(nodes=[dict(id='h',coordinates=position(0)),dict(id='a',coordinates=position(200))],edges=edges,home='h'),
                    routes=dict(dijkstra_distance=dict(status='ready',edge_ids=['1','2'],stops=[],time_s=60)))
        return result,list(INV(x+180,y))

    def test_automatic_detection_cannot_precede_appearance(self):
        result,fire=self.result()
        event=dict(mode='automatic',occurs=True,coordinates=fire,surface_m=0,appeared_at_s=27,state='active')
        with patch('core.patrol_events.generate',return_value=copy.deepcopy(event)):
            sim=simulate(result,dict(scenario='nominal'),FlatTerrain())
        self.assertGreaterEqual(sim['detection']['detected_at_s'],27)
        self.assertEqual(sim['fire_event']['state'],'reported')
        self.assertEqual(sim['status'],'detected_and_returned')
        self.assertFalse(sim['patrol_completed'])
        self.assertEqual(len(sim['recovery']['candidates']),4)
        self.assertLessEqual(sim['time_s'],result['effective_profile']['mission_budget_s'])

    def test_not_observed_is_distinct_from_no_fire_and_no_visibility(self):
        result,fire=self.result()
        class Blind(FlatTerrain):
            def visible(self,a,b): return False
        for appearance,terrain in [(100,FlatTerrain()),(15,Blind())]:
            event=dict(mode='automatic',occurs=True,coordinates=fire,surface_m=0,appeared_at_s=appearance,state='active')
            with patch('core.patrol_events.generate',return_value=event): sim=simulate(result,{},terrain)
            self.assertIsNone(sim['detection'])
            self.assertEqual(sim['fire_event']['state'],'not_yet_active_at_end' if appearance>sim['time_s'] else 'not_observed')
        with self.assertRaises(ValueError): simulate(result,dict(fire_probability_pct=100),FlatTerrain())

    def test_uniform_location_inside_target_and_missing_elevation_is_not_resampled(self):
        _,_,area,*_=fixture()
        class Unknown(FlatTerrain):
            def at(self,x,y): return None
        with patch('core.patrol_events.arrival',return_value=dict(occurs=True,coordinates=None,state='active',baseline=dict(sha256='fixture'))):
            event=generate(1,2,area,0,100,Unknown())
        self.assertTrue(area.covers(transform(FWD,shape(dict(type='Point',coordinates=event['coordinates'])))))
        self.assertEqual(event['state'],'unknown_elevation')

    def test_different_sectors_do_not_share_one_correlated_fire_draw(self):
        _,_,area,*_=fixture()
        from shapely.affinity import translate
        first=generate(123,0,area,10,1e12,FlatTerrain())
        again=generate(123,0,area,10,1e12,FlatTerrain())
        other=generate(123,0,translate(area,xoff=400),10,1e12,FlatTerrain())
        self.assertEqual(first,again)
        self.assertNotEqual(first['draw'],other['draw'])
        self.assertNotEqual(first['id'],other['id'])

    def test_only_observed_cells_accumulate_and_replaying_is_idempotent(self):
        result,_=self.result();model,*_=fixture();catalog=catalogue(model);sector=catalog['sectors'][0]
        result['request']=dict(patrol_id=sector['id'],monitoring_catalogue_sha256=catalog['sha256'])
        result['target_polygon']=sector['target_polygon']
        sim=simulate(result,dict(scenario='nominal'),FlatTerrain())
        with tempfile.TemporaryDirectory() as folder,patch('core.patrol_monitoring.DIRECTORY',Path(folder)):
            one=record(result,sim,FlatTerrain());two=record(result,sim,FlatTerrain())
            self.assertEqual(one['sector_percent'],two['sector_percent'])
            total=progress(catalog['sha256'],transform(FWD,shape(model['study_geometry'])))
            self.assertFalse(total['complete'])
            self.assertLess(total['percent'],100)


if __name__=='__main__': unittest.main()
