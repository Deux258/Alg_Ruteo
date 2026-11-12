import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from core.patrol_day import ANCHOR,catalogue,programmes,schedule,daily
from core.patrol import calculate,defaults
from tests.test_patrol import fixture,FlatTerrain


class PatrolDayTests(unittest.TestCase):
    def test_rotation_visits_all_assigned_sectors_without_manual_selection(self):
        model,*_=fixture();catalog=catalogue(model)
        programmes_list=programmes(catalog,model)
        programme=programmes_list[0]
        visited=set()
        for i in range(programme['cycle_days']):
            rows=schedule(catalog,programme['id'],(ANCHOR+timedelta(days=i)).isoformat())
            self.assertLessEqual(len(rows),2)
            self.assertTrue(all(s['base_id']==programme['base_id'] for s in rows))
            visited.update(s['id'] for s in rows)
        self.assertEqual(visited,{s['id'] for s in catalog['sectors'] if s['base_id']==programme['base_id'] and s['status']!='pending_support'})

    def test_daily_cache_contains_real_routes_and_counts_service_time(self):
        model,*_=fixture();request=dict(programme_id='104',date=ANCHOR.isoformat(),operation='prepare')
        def fake(model,request,conn,primary_only):
            self.assertTrue(primary_only)
            return dict(sha256=request['patrol_id'],routes=dict(dijkstra_weighted=dict(status='ready',coordinates=[[1,2,60],[2,3,60]],time_s=100,distance_m=500,coverage=dict(complete=True),stops=[])))
        with tempfile.TemporaryDirectory() as folder,patch('core.patrol_day.DIRECTORY',Path(folder)),patch('core.patrol.calculate',side_effect=fake) as planner:
            pending=daily(model,dict(request,operation='plan'));self.assertEqual(pending['status'],'requires_preparation')
            ready=daily(model,request);self.assertEqual(ready['status'],'ready')
            self.assertEqual(ready['total_time_s'],320)
            again=daily(model,dict(request,operation='plan'));self.assertEqual(again,ready)
            self.assertEqual(planner.call_count,2)
            self.assertTrue(all(f['coordinates'] for f in ready['flights']))

    def test_primary_planner_keeps_physics_and_graph_for_recovery(self):
        model,request,*_=fixture();p=defaults();p.update(scenarios=2)
        with patch('core.patrol.defaults',return_value=p):
            result=calculate(model,dict(request,scenarios=2),terrain_override=FlatTerrain(),primary_only=True)
        self.assertEqual(set(result['routes']),{'dijkstra_weighted'})
        self.assertEqual(result['routes']['dijkstra_weighted']['status'],'ready')
        self.assertTrue(result['routes']['dijkstra_weighted']['coverage']['complete'])
        self.assertTrue(result['graph']['edges'])

    def test_invalid_programme_and_date_are_rejected(self):
        model,*_=fixture();catalog=catalogue(model)
        for programme,day in [('unknown',ANCHOR.isoformat()),('104','invalid')]:
            with self.assertRaises(ValueError):schedule(catalog,programme,day)
