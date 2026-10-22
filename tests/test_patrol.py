import copy
import json
import hashlib
import math
import os
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, LineString, box, mapping
from shapely.ops import transform

from core.aerial_data import FWD, INV, iso
from core.patrol_sources import profile, obstacle_rows, weather_rows, validate_profile
from core.patrol_data import build, Obstacles, make_edge
from core.patrol_routing import effective_profile, weather_at, weather_window, weather_problem, duration, check_edge, normalize_request, plan, overlay, compose, enrich
from core.surface import Surface, observation
from core.contracts import canonical


def weather(hour=0, **extra):
    return dict(valid_at=f'2026-10-22T{hour:02d}:00:00+00:00',cell=[-71.62,-33.08],temperature_c=20,
                relative_humidity_pct=50,wind_speed_ms=1,wind_direction_deg=0,wind_100_ms=1,direction_100_deg=0,
                wind_gust_ms=2,precipitation_mm=0,visibility_m=10000,**extra)


class SurfaceFixture:
    def __enter__(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'dsm.tif'
        self.transform=from_origin(-71.64,-33.06,0.0001,0.0001)
        self.array=np.full((400,400),100,dtype='float32');self.write()
        self.center=FWD(-71.62,-33.08)
        return self

    def write(self):
        with rasterio.open(self.path,'w',driver='GTiff',width=400,height=400,count=1,dtype='float32',crs='EPSG:4326',
                           transform=self.transform,nodata=-9999) as target:target.write(self.array,1)

    def __exit__(self,*args):self.tmp.cleanup()


class PatrolRules(unittest.TestCase):
    def setUp(self):
        warnings.filterwarnings('ignore',category=PendingDeprecationWarning,module='rasterio.*')
        self.p=profile()

    def test_profile_defaults_and_stricter_preferences(self):
        self.assertEqual(effective_profile(self.p,{})['budget_eq_s'],1200)
        self.assertEqual(effective_profile(self.p,{'minimum_coverage':.8})['minimum_coverage'],.8)
        for value in [True,float('nan'),1300,0]:
            with self.assertRaises(ValueError):effective_profile(self.p,{'budget_eq_s':value})
        with self.assertRaises(ValueError):effective_profile(self.p,{'unknown':1})

    def test_direction_interpolation_crosses_zero_not_south(self):
        a,b=weather(0),weather(1)
        a['wind_direction_deg']=a['direction_100_deg']=350
        b['wind_direction_deg']=b['direction_100_deg']=10
        w=weather_at([a,b],iso('2026-10-22T00:30:00Z'))
        self.assertAlmostEqual(min(w['wind_direction_deg'],360-w['wind_direction_deg']),0,places=8)

    def test_window_includes_weather_change_and_missing_hour(self):
        p=effective_profile(self.p,{})
        a,b=weather(0),weather(1);b['wind_gust_ms']=9
        _,problem=weather_window([a,b],iso('2026-10-22T00:50:00Z'),p)
        self.assertEqual(problem,'wind_outside_profile')
        self.assertIsNone(weather_at([weather(0),weather(2)],iso('2026-10-22T00:30:00Z')))

    def test_missing_data_and_thresholds(self):
        for key,value,cause in [('visibility_m',999,'visibility_outside_profile'),('precipitation_mm',1,'precipitation_outside_profile'),('wind_gust_ms',8,'wind_outside_profile'),('wind_100_ms',None,'unknown_weather')]:
            w=weather();w[key]=value;self.assertEqual(weather_problem(w,self.p),cause)

    def test_wind_direction_and_vertical_energy(self):
        w=weather();w['wind_speed_ms']=w['wind_100_ms']=5;w['wind_direction_deg']=w['direction_100_deg']=270
        e=dict(coordinates=[[0,0,100],[100,0,100]],horizontal_km=.1)
        east=duration(e,w,self.p);e['coordinates'].reverse();west=duration(e,w,self.p)
        self.assertLess(east[0],west[0])
        e=dict(coordinates=[[0,0,100],[0,0,190]],horizontal_km=0)
        t,eq=duration(e,w,self.p);self.assertEqual((t,eq),(30,45))
        for factor in [1.25,1.5,2]:self.assertEqual(duration(e,w,dict(self.p,climb_factor=factor))[1],30*factor)

    def test_obstacle_height_is_not_fabricated_from_levels(self):
        area=box(*FWD(-71.64,-33.10),*FWD(-71.60,-33.06))
        doc={'elements':[dict(type='node',id=1,lon=-71.62,lat=-33.08,tags={'man_made':'tower','building:levels':'10'})]}
        row=obstacle_rows(doc,area,self.p)[0]
        self.assertIsNone(row['height_m']);self.assertEqual(row['quality'],'height_unknown')

    def test_invalid_osm_relation_is_conservative_and_traceable(self):
        coords=[dict(lon=-71.62,lat=-33.08),dict(lon=-71.619,lat=-33.08),dict(lon=-71.619,lat=-33.079),dict(lon=-71.62,lat=-33.08)]
        doc={'elements':[dict(type='relation',id=1,tags={'building':'yes'},members=[dict(role='inner',geometry=coords)])]}
        x,y=FWD(-71.62,-33.08);rows=obstacle_rows(doc,box(x-500,y-500,x+500,y+500),self.p)
        self.assertEqual(rows[0]['geometry_quality'],'invalid_relation_conservative_hull')
        with self.assertRaises(ValueError):obstacle_rows(dict(doc,remark='timeout'),box(x-500,y-500,x+500,y+500),self.p)

    def test_request_objectives_are_required_distinct_and_in_area(self):
        x,y=FWD(-71.62,-33.08);geom=mapping(transform(INV,box(x-500,y-500,x+500,y+500)))
        context=dict(study_geometry=geom,flight_geometry=geom)
        req=dict(origin=[-71.62,-33.08],objectives=[[-71.619,-33.08]],time='2026-10-22T00:00:00Z')
        self.assertEqual(len(normalize_request(req,self.p,context)[1]),1)
        for goals in [[],req['objectives']*2,req['objectives']*4]:
            with self.assertRaises(ValueError):normalize_request(dict(req,objectives=goals),self.p,context)

    def test_complete_corridor_detects_intermediate_crest(self):
        with SurfaceFixture() as f:
            f.array[:,199:202]=190;f.write();surface=Surface(f.path)
            try:
                x,y=f.center;a=[x-250,y,200];b=[x+250,y,200]
                corridor=surface.corridor(a,b,self.p)
                self.assertLess(corridor['clearance_m'],40)
                self.assertTrue(corridor['surface_known'])
            finally:surface.close()

    def test_nodata_inside_buffer_is_unknown(self):
        with SurfaceFixture() as f:
            f.array[199:202,199:202]=-9999;f.write();surface=Surface(f.path)
            try:
                x,y=f.center;result=surface.corridor([x-200,y,190],[x+200,y,190],self.p)
                self.assertFalse(result['surface_known']);self.assertIsNone(result['clearance_m'])
            finally:surface.close()

    def test_camera_coverage_and_ridge_occlusion(self):
        with SurfaceFixture() as f:
            x,y=f.center;surface=Surface(f.path)
            try:flat=observation(surface,[x-120,y,220],Point(x,y).buffer(30),dict(self.p,camera_fov_deg=[120,120],maximum_gsd_m=2))
            finally:surface.close()
            f.array[:,193:196]=205;f.write();surface=Surface(f.path)
            try:ridge=observation(surface,[x-120,y,220],Point(x,y).buffer(30),dict(self.p,camera_fov_deg=[120,120],maximum_gsd_m=2))
            finally:surface.close()
            self.assertGreater(flat['coverage'],ridge['coverage'])

    def test_obstacle_blocks_temporary_segment(self):
        with SurfaceFixture() as f:
            x,y=f.center;surface=Surface(f.path)
            try:
                obstacles=Obstacles([dict(exclusion=mapping(box(x-10,y-50,x+10,y+50)))])
                e=make_edge(1,1,2,[x-100,y,190],[x+100,y,190],surface,obstacles,self.p)
                self.assertEqual(check_edge(e,self.p,Point().buffer(1)),'obstacle_intersection')
            finally:surface.close()

    def test_builder_is_deterministic_and_has_vertical_distance(self):
        with SurfaceFixture() as f:
            x,y=f.center;area=box(x-200,y-200,x+200,y+200);surface=Surface(f.path)
            try:
                a=build(area,area,[],[],surface,self.p);b=build(area,area,[],[],surface,self.p)
                self.assertEqual(a,b)
                vertical=[e for e in a[1] if e['horizontal_km']==0]
                self.assertTrue(vertical);self.assertTrue(all(e['flight_km']>0 for e in vertical))
            finally:surface.close()

    def test_unknown_units_are_rejected(self):
        doc=dict(utc_offset_seconds=0,hourly={'time':['2026-10-22T00:00']},hourly_units={'wind_speed_10m':'km/h'})
        with self.assertRaises(ValueError):weather_rows(doc)

    def test_invalid_profile_rejected_before_build(self):
        for key,value in [('climb_ms',0),('grid_m',251),('camera_fov_deg',[180,45]),('levels_m',[90,60])]:
            with self.assertRaises(ValueError):validate_profile(dict(self.p,**{key:value}))

    def test_refined_nodes_explain_the_obstacle_reason(self):
        with SurfaceFixture() as f:
            x,y=f.center;area=box(x-200,y-200,x+200,y+200);surface=Surface(f.path)
            rows=[dict(exclusion=mapping(box(x-20,y-20,x+20,y+20)))]
            try:states,_,_=build(area,area,[],rows,surface,self.p)
            finally:surface.close()
            self.assertTrue(any('known_obstacles' in n['refinement_reasons'] for n in states.values()))

    def test_cached_costs_match_individual_directed_physics(self):
        es=[]
        for i,dz in enumerate([0,30,-30]):
            es.append(dict(id=i,source=i,target=i+1,coordinates=[[0,0,100],[100,0,100+dz]],horizontal_km=.1,
                flight_km=math.hypot(100,dz)/1000,blocked_obstacle=False,obstacle_distance_m=80,surface_known=True,clearance_m=60))
        result,causes=enrich(es,self.p,[weather()],Point().buffer(0))
        self.assertEqual(causes,{})
        for e in result:
            t,eq=duration(e,weather(),self.p)
            self.assertEqual(e['time_s'],t);self.assertEqual(e['eq_s'],eq);self.assertGreaterEqual(e['cost'],eq)

    def test_patrol_uses_another_order_when_first_exceeds_budget(self):
        from types import SimpleNamespace
        edges={};costs={(0,1):50,(1,2):500,(2,0):50,(0,2):50,(2,1):50,(1,0):50}
        def get(s,t):
            ident=s*10+t;edges[ident]=dict(eq_s=costs[s,t])
            return [dict(node_ids=[s,t],edge_ids=[ident],cost=costs[s,t],length_km=1)]
        paths=SimpleNamespace(reference=False,edges=edges,get=get,limited=False)
        states={i:dict(coordinates=[i,0,100]) for i in [0,1,2]}
        views={i:dict(admissible=True,known=True,coverage=1) for i in [1,2]}
        candidates,_,_=compose(paths,[dict(id='a'),dict(id='b')],{'a':[1],'b':[2]},0,views,states,dict(self.p,budget_eq_s=300))
        self.assertEqual([r['order'] for r in candidates],[['b','a']])

    def test_unknown_empty_comparison_preserves_common_catalogue(self):
        from core.patrol_evaluation import compare
        x,y=FWD(-71.62,-33.08);geom=mapping(transform(INV,box(x-500,y-500,x+500,y+500)))
        context=dict(study_geometry=geom,flight_geometry=geom,weather=[weather(0),weather(1)])
        req=dict(origin=[-71.62,-33.08],objectives=[[-71.619,-33.08]],time='2026-10-22T00:00:00Z')
        empty=dict(status='unknown',alternatives=[],features=[])
        with patch('core.patrol_evaluation.plan',return_value=empty),patch('core.patrol_evaluation.graph',return_value=(self.p,context,{},[],[])):
            result=compare(None,'fixture',req)
        self.assertEqual(len(result['results']),104)
        self.assertEqual(result['metrics']['valid_scenarios'],0)
        self.assertIsNone(result['metrics']['delta_percentage_points'])


class PatrolIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (os.getenv('DATABASE_URL') or os.getenv('DB_HOST')):
            if os.getenv('REQUIRE_DB_TESTS')=='1':raise RuntimeError('Se requiere pgRouting')
            raise unittest.SkipTest('Ejecutar ./main probar')
        from core.db import connect
        cls.conn=connect()

    @classmethod
    def tearDownClass(cls):cls.conn.close()

    def setUp(self):
        warnings.filterwarnings('ignore',category=PendingDeprecationWarning,module='rasterio.*')
        self.fixture=SurfaceFixture().__enter__();f=self.fixture;self.p=profile();x,y=f.center
        self.area=box(x-500,y-500,x+500,y+500);s=Surface(f.path)
        try:self.states,self.edges,_=build(self.area,self.area,[],[],s,self.p)
        finally:s.close()
        geom=mapping(transform(INV,self.area));self.context=dict(study_geometry=geom,flight_geometry=geom,
            weather=[weather(h) for h in range(5)],dsm_file=str(f.path),records=dict(A2=[],A3=[],A4=[]))
        self.request=dict(origin=list(INV(x,y)),objectives=[list(INV(x+160,y+50))],time='2026-10-22T00:00:00Z')
        self.mock=patch('core.patrol_routing.graph',return_value=(self.p,self.context,self.states,self.edges,[]));self.mock.start()

    def tearDown(self):self.mock.stop();self.fixture.__exit__()

    def test_single_objective_observation_return_and_reserve(self):
        result=plan(self.conn,'fixture',self.request)
        self.assertEqual(result['status'],'ready',result)
        self.assertGreaterEqual(len(result['alternatives']),1)
        for item in result['alternatives']:
            e=item['evaluation'];self.assertTrue(e['admissible']);self.assertGreaterEqual(e['final_reserve_fraction'],.2)
            self.assertEqual(len(e['timeline']),1);self.assertGreaterEqual(e['minimum_coverage'],.6)
            self.assertEqual(len(item['legs']),2)
        json.dumps(result,allow_nan=False)
        self.assertEqual(result['sha256'],hashlib.sha256(canonical({k:v for k,v in result.items() if k!='sha256'})).hexdigest())
        self.assertTrue(all(isinstance(i,str) for item in result['alternatives'] for leg in item['legs'] for i in leg['edge_ids']))
        signatures=[tuple((round(c[0],6),round(c[1],6)) for c in item['legs'][0]['coordinates']) for item in result['alternatives']]
        self.assertEqual(len(signatures),len(set(signatures)))

    def test_three_objectives_all_observed_and_ordered(self):
        x,y=self.fixture.center;req=dict(self.request,objectives=[list(INV(x+100,y+20)),list(INV(x-100,y+40)),list(INV(x,y+150))])
        result=plan(self.conn,'fixture',req)
        self.assertEqual(result['status'],'ready',result)
        for item in result['alternatives']:
            self.assertEqual(len(item['order']),3);self.assertEqual(len(item['evaluation']['timeline']),3)
            self.assertEqual(len(item['legs']),4)

    def test_impossible_patrol_is_not_partial_success(self):
        req=dict(self.request,preferences={'budget_eq_s':10})
        result=plan(self.conn,'fixture',req)
        self.assertNotEqual(result['status'],'ready');self.assertEqual(result['alternatives'],[])

    def test_dijkstra_unchanged_by_threats_or_preferences(self):
        a=plan(self.conn,'fixture',self.request,'reference')
        event=dict(id='all',geometry=self.context['flight_geometry'],observed_at=self.request['time'],state='blocked')
        b=plan(self.conn,'fixture',dict(self.request,events=[event],preferences={'wind_limit_ms':.5}),'reference')
        self.assertEqual([[leg['edge_ids'] for leg in m['legs']] for m in a['alternatives']],[[leg['edge_ids'] for leg in m['legs']] for m in b['alternatives']])
        self.assertEqual([m['length_km'] for m in a['alternatives']],[m['length_km'] for m in b['alternatives']])

    def test_same_launch_and_objective_has_no_zero_cost_edges(self):
        req=dict(self.request,objectives=[self.request['origin']])
        result=plan(self.conn,'fixture',req)
        self.assertEqual(result['status'],'ready',result)
        self.assertTrue(result['alternatives'][0]['evaluation']['admissible'])

    def test_dijkstra_altitude_duplicates_do_not_hide_horizontal_detour(self):
        from core.patrol_routing import Paths,path_signature
        coordinates=[[0,0,0],[100,0,0],[0,0,1],[100,0,1],[50,100,0]]
        states={i+1:dict(coordinates=c) for i,c in enumerate(coordinates)}
        pairs=[(1,2),(1,3),(3,4),(4,2),(1,5),(5,2)]
        edges=[dict(id=i+1,source=a,target=b,flight_km=math.dist(states[a]['coordinates'],states[b]['coordinates'])/1000) for i,(a,b) in enumerate(pairs)]
        result=Paths(self.conn,edges,states,True,self.p,'fixture').get(1,2)
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['node_ids'],[1,2])
        self.assertEqual(result[1]['node_ids'],[1,5,2])
        self.assertNotEqual(path_signature(result[0],states),path_signature(result[1],states))

    def test_comparison_freezes_missions_before_common_scenarios(self):
        from core.patrol_evaluation import compare
        payload=(self.p,self.context,self.states,self.edges,[])
        with patch('core.patrol_evaluation.graph',return_value=payload),patch('core.patrol_evaluation.plan',wraps=plan) as planner:
            result=compare(self.conn,'fixture',self.request)
        self.assertEqual(planner.call_count,2)
        self.assertEqual(len(result['results']),104)
        self.assertEqual(result['metrics']['total_scenarios'],104)


if __name__=='__main__':unittest.main()
