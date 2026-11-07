"""Independent oracles and resource-boundary regressions for final rubric closure."""
import copy
import itertools
import math
import unittest
from unittest.mock import patch

from shapely.geometry import Point, box, mapping
from shapely.ops import transform
from core.aerial_data import FWD, INV, iso
from core.contracts import canonical
from core.mission_constraints import assess_constraints
from core.patrol import (Graph, Hazards, calculate, defaults, gurobi_route, oriented_tasks,
                         simulate, threat_uniform, wilson_interval, _GEOMETRY_CACHE)
from tests.test_patrol import fixture, FlatTerrain


class PatrolClosureTests(unittest.TestCase):
    def quick_calculate(self,model,request):
        p=defaults();p.update(annealing_iterations=10,solver_seconds=1,alternative_search_seconds=.1)
        with patch('core.patrol.defaults',return_value=p):
            return calculate(model,request,terrain_override=FlatTerrain())

    def test_sixty_seconds_rejected_and_actual_190_is_130_plus_report(self):
        model,request,*_=fixture()
        request['preferences']={'battery_budget_s':60}
        result=self.quick_calculate(model,request)
        self.assertEqual(result['status'],'blocked')
        self.assertFalse(result['diagnostic']['routing_attempted'])
        self.assertTrue(all(r['status']=='blocked' and not r['coordinates'] for r in result['routes'].values()))
        request['preferences']['battery_budget_s']=190
        assessment=assess_constraints(model,request)
        self.assertEqual(assessment['battery_budget_s'],190)
        self.assertEqual(assessment['flight_budget_s'],130)
        self.assertEqual(assessment['report_reserve_s'],60)
        self.assertEqual(assessment['mission_flight_budget_s'],defaults()['mission_budget_s']-60)

    def test_blocked_weather_preserves_exportable_probabilities(self):
        model,request,*_=fixture();model['records']['M4'][0]['wind_gust_ms']=20
        result=self.quick_calculate(model,request)
        self.assertEqual(result['status'],'blocked')
        probabilities=result['failure_probabilities']
        self.assertTrue(probabilities['nodes']);self.assertTrue(probabilities['edges'])
        self.assertTrue(all(r['probability_pct']==100 and r['by_threat']['A1:weather']==100 for r in probabilities['nodes']+probabilities['edges']))
        self.assertFalse(result['recommended'])
        self.assertTrue(all(not r['coordinates'] for r in result['routes'].values()))
        canonical(result)  # diagnostic stays JSON-exportable

    def test_report_is_not_completed_when_physical_budget_cannot_pay_report_and_return(self):
        # A legacy frozen route with only 60 physical seconds recreates the original
        # over-budget defect independently of the new planner's upfront rejection.
        model,request,*_=fixture();x,y=FWD(*request['origin']);p=defaults();p['battery_budget_s']=60
        position=lambda dx:[*INV(x+dx,y),60.]
        target=mapping(transform(INV,box(x+160,y-20,x+200,y+20)))
        edges=[dict(id='1',source='h',target='a',time_s=20,hazard_ids=[],coordinates=[position(v) for v in (0,50,100,150,200)]),
               dict(id='2',source='a',target='h',time_s=20,hazard_ids=[],coordinates=[position(v) for v in (200,150,100,50,0)])]
        result=dict(sha256='legacy-fixture',time=model['reference_time'],effective_profile=p,weather=model['records']['M4'][0],
                    target_polygon=target,threats=[],stations=[],failure_probabilities={'nodes':[]},
                    graph=dict(nodes=[dict(id='h',coordinates=position(0)),dict(id='a',coordinates=position(200))],edges=edges,home='h'),
                    routes=dict(dijkstra_distance=dict(status='ready',edge_ids=['1','2'],stops=[])))
        replay=simulate(result,dict(method='dijkstra_distance',scenario='nominal',fire=list(INV(x+180,y))),FlatTerrain())
        self.assertEqual(replay['status'],'detected_report_incomplete_and_returned')
        self.assertEqual(replay['detection']['reported_at_s'],None)
        self.assertEqual(replay['detection']['reported_at_utc'],None)
        self.assertFalse(replay['detection']['report_completed'])
        self.assertFalse(replay['mission_completed'])
        self.assertLessEqual(replay['time_s'],60)
        self.assertEqual(replay['timeline'][-1]['phase'],'landed')

    def test_uniforms_are_id_stable_with_catalogue_reordering_and_wilson_is_not_point_estimate(self):
        first={ident:threat_uniform(12,4,ident) for ident in ['A4:a','synthetic:0']}
        second={ident:threat_uniform(12,4,ident) for ident in ['added','synthetic:0','A4:a']}
        self.assertEqual(first,{key:second[key] for key in first})
        self.assertNotEqual(first['A4:a'],threat_uniform(12,5,'A4:a'))
        self.assertTrue(all(0<=v<100 for v in second.values()))
        interval=wilson_interval(0,20)
        self.assertEqual(interval['low'],0);self.assertGreater(interval['high'],0)
        interval=wilson_interval(20,20)
        self.assertLess(interval['low'],1);self.assertEqual(interval['high'],1)

    def test_geometry_cache_reuses_only_physics_and_each_routing_session_is_independent(self):
        model,request,area,target,w=fixture();p=defaults();_GEOMETRY_CACHE.clear()
        hazards=Hazards(model,iso(model['reference_time']),p,[])
        one=Graph(area,FlatTerrain(),hazards,w,p,cache_geometry=True)
        changed=dict(w,wind_speed_ms=3)
        two=Graph(area,FlatTerrain(),hazards,changed,p,cache_geometry=True)
        self.assertFalse(one.geometry_cache['hit']);self.assertTrue(two.geometry_cache['hit'])
        self.assertNotEqual(one.edges[1]['time_s'],two.edges[1]['time_s'])
        self.assertLessEqual(two.geometry_cache['cache_bytes'],two.geometry_cache['cache_max_bytes'])
        first,second=two.routing_session(),two.routing_session()
        first.path(1,2)
        self.assertTrue(first.cache);self.assertEqual(second.cache,{})
        original=len(one.nodes);two.point(request['origin'])
        self.assertEqual(len(one.nodes),original)

    def test_activated_threats_keep_original_ids_and_geometry(self):
        model,request,area,target,w=fixture();p=defaults()
        event=dict(geometry=mapping(transform(INV,target)),probability_pct=80)
        original=Hazards(model,iso(model['reference_time']),p,[event])
        active=Hazards(model,iso(model['reference_time']),p,[event],['synthetic:0'])
        self.assertEqual(active.rows[-1]['geometry'],original.rows[-1]['geometry'])
        self.assertEqual(active.rows[-1]['probability_pct'],100)
        self.assertEqual(active.rows[-1]['attributes']['original_probability_pct'],80)
        with self.assertRaises(ValueError):Hazards(model,iso(model['reference_time']),p,[event],['unknown'])

    def test_all_four_tie_is_explicit_and_time_is_separate(self):
        model,request,*_=fixture();p=defaults();p['historical_probabilities_pct']=[0]*5
        p.update(annealing_iterations=10,solver_seconds=1,alternative_search_seconds=.1)
        with patch('core.patrol.defaults',return_value=p):result=calculate(model,request,terrain_override=FlatTerrain())
        self.assertEqual(result['ranking']['message'],'Empate entre las cuatro técnicas')
        self.assertEqual(result['ranking']['tie_break'],'compute_s')
        self.assertEqual(len(result['resilience_leaders']),4)
        self.assertTrue(all(r['timings']['cache_policy']=='independent_per_technique' for r in result['routes'].values()))


class IndependentMILPOracleTests(unittest.TestCase):
    def test_enumeration_of_orientations_permutations_and_optional_station_matches_milp(self):
        # Complete directed metric graph. Oracle enumerates physical action sequences
        # and resources directly, without fixed_route, MILP variables or beam labels.
        model,request,area,target,w=fixture();p=defaults();p.update(battery_budget_s=95,solver_seconds=3,solver_gap=0)
        graph=Graph(area,FlatTerrain(),Hazards(model,iso(model['reference_time']),p,[]),w,p)
        x,y=FWD(*request['origin']);home=graph.point(request['origin'])
        nodes=[graph.point(list(INV(x+dx,y+dy))) for dx,dy in [(150,0),(250,0),(150,150),(250,150),(200,70)]]
        states=oriented_tasks([dict(nodes=nodes[:2]),dict(nodes=nodes[2:4])],graph,'cost')
        stations=[dict(id='swap',node=nodes[4])]
        best=math.inf
        for group_order in itertools.permutations(range(2)):
            for orientations in itertools.product(range(2),repeat=2):
                chosen=[next(s for s in states if s['group']==g and s['direction']==direction) for g,direction in zip(group_order,orientations)]
                for insert in (None,0,1,2):
                    sequence=chosen[:]
                    if insert is not None:sequence.insert(insert,dict(kind='station',start=nodes[4],end=nodes[4],time_s=140,cost=140,path=[]))
                    current=home;energy=10.;elapsed=10.;cost=10.;valid=True
                    for action in sequence+[dict(kind='end',start=home,end=home,time_s=10,cost=10,path=[])]:
                        path=graph.path(current,action['start'],'cost')
                        if path is None:valid=False;break
                        leg=graph.totals(path);elapsed+=leg['time_s']+action['time_s'];cost+=leg['cost']+action['cost']
                        energy+=leg['time_s']
                        if action.get('kind')=='station':
                            if energy+10>95:valid=False;break
                            energy=10.
                        else:energy+=action['time_s']
                        if energy>95 or elapsed>p['mission_budget_s']:valid=False;break
                        current=action['end']
                    if valid:best=min(best,cost)
        answer,metadata=gurobi_route(states,graph,home,stations)
        self.assertIsNotNone(answer,metadata)
        self.assertTrue(math.isfinite(best))
        self.assertAlmostEqual(answer['cost'],best,places=6)
        self.assertEqual(metadata['status'],'optimal')
        self.assertTrue(metadata['preflight']['capacity_checked'])
        self.assertTrue(metadata['preflight']['license_checked'])


if __name__=='__main__':unittest.main()
