import copy
import unittest
from unittest.mock import patch

from shapely.geometry import box, mapping
from shapely.ops import transform

from core.aerial_data import FWD, INV, iso
from core.patrol import (Graph, Hazards, calculate, coverage, defaults, fixed_route,
                         oriented_tasks, simulate, sweep_tasks)


class FlatTerrain:
    source_sha256 = 'flat-test-only'
    def at(self,x,y): return 0.0
    def visible(self,a,b): return True


def fixture():
    x,y=FWD(-71.65,-33.1)
    area=box(x-500,y-500,x+700,y+500)
    target=box(x+150,y-100,x+350,y+100)
    weather=dict(valid_at='2026-11-04T12:00:00+00:00',wind_speed_ms=0,wind_gust_ms=0,wind_direction_deg=0,temperature_c=20)
    model=dict(study_geometry=mapping(transform(INV,area)),flight_geometry=mapping(transform(INV,area)),
               reference_time=weather['valid_at'],records=dict(M1=[dict(provider_id='104',name='Fixture',candidate=True,
               geometry=dict(type='Point',coordinates=[-71.65,-33.1]))],M2=[],M3=[],M4=[weather],A1=[],A2=[],A3=[],
               A4=[dict(provider_id='fixture',geometry=mapping(transform(INV,area)),ordinal_class=1)]))
    request=dict(target_polygon=mapping(transform(INV,target)),origin=[-71.65,-33.1],station_ids=[],scenarios=20)
    return model,request,area,target,weather


class PatrolTests(unittest.TestCase):
    def test_origin_and_station_share_one_physical_node(self):
        model,request,area,target,w=fixture();p=defaults()
        graph=Graph(area,FlatTerrain(),Hazards(model,iso(model['reference_time']),p,[]),w,p)
        a=graph.point(request['origin']);count=len(graph.nodes);edges=len(graph.edges)
        b=graph.point(request['origin'])
        self.assertEqual(a,b);self.assertEqual(count,len(graph.nodes));self.assertEqual(edges,len(graph.edges))
        other=graph.point(list(INV(*[v+200 for v in FWD(*request['origin'])])))
        path=graph.path(a,other)
        self.assertIsNotNone(path)
        with self.assertRaises(RuntimeError):graph.check_path(list(reversed(path)),a,other)

    def test_detection_can_return_to_a_selected_alternative_base(self):
        model,request,*_=fixture();x,y=FWD(*request['origin'])
        alternate=list(INV(x+160,y-50))
        model['records']['M1'].append(dict(provider_id='105',name='Alternate fixture',candidate=True,geometry=dict(type='Point',coordinates=alternate)))
        request['station_ids']=['105']
        p=defaults();p.update(solver_seconds=1,annealing_iterations=10);p['historical_probabilities_pct']=[0]*5
        with patch('core.patrol.defaults',return_value=p):result=calculate(model,request,terrain_override=FlatTerrain())
        sim=simulate(result,dict(method='dijkstra_weighted',fire=list(INV(x+250,y-50))),FlatTerrain())
        self.assertEqual(sim['status'],'detected_and_returned')
        self.assertEqual(sim['return_base_id'],'105')
        self.assertAlmostEqual(sim['timeline'][-1]['coordinates'][2],0)
        self.assertIn('reported_at_utc',sim['detection'])

    def test_indexed_history_preserves_exposure_and_policy(self):
        from core.aerial_routing import IndexedHistory,exposure,historical_policy
        from shapely.geometry import LineString
        rows=[(box(0,0,10,10),1),(box(5,0,20,10),.5),(box(100,100,110,110),.8)]
        indexed=IndexedHistory(rows)
        for line in [LineString([(-1,5),(25,5)]),LineString([(1,0),(15,0)]),LineString([(40,40),(50,50)])]:
            self.assertEqual(exposure(line,rows),exposure(line,indexed))
            model=dict(profile={'max_historical_class':4},history=rows)
            self.assertEqual(historical_policy(line,model),historical_policy(line,dict(model,history=indexed)))

    def test_unmapped_history_has_explicit_probability(self):
        model,r,area,target,w=fixture();model['records']['A4']=[]
        h=Hazards(model,iso(model['reference_time']),defaults(),[])
        self.assertEqual(h.rows[0]['source'],'A4_unknown')
        self.assertAlmostEqual(h.probability(h.ids(target.centroid)),.2)

    def test_uniform_zero_hundred_and_common_seed(self):
        from core.patrol import evaluate_failures
        model,r,area,target,w=fixture()
        p=defaults();p['scenarios']=1000;p['historical_probabilities_pct']=[0,0,0,0,0]
        h=Hazards(model,iso(model['reference_time']),p,[dict(geometry=mapping(transform(INV,target)),probability_pct=80)])
        g=Graph(area,FlatTerrain(),h,w,p)
        edge=next(e for e in g.edges.values() if any(h.rows[i]['source']=='synthetic' for i in e['hazard_ids']))
        a={m:dict(status='ready',edge_ids=[str(edge['id'])]) for m in ('dijkstra_distance','dijkstra_weighted','gurobi','annealing')}
        b=copy.deepcopy(a)
        first=evaluate_failures(a,g);second=evaluate_failures(b,g)
        self.assertEqual(first['scenario_sha256'],second['scenario_sha256'])
        self.assertEqual(a,b)
        self.assertLess(abs(a['gurobi']['resilience']['value']-.2),.05)
        for probability,expected in [(0,1),(100,0)]:
            h.rows[-1]['probability_pct']=probability
            evaluate_failures(a,g)
            self.assertEqual(a['gurobi']['resilience']['value'],expected)

    def test_full_mission_four_methods_and_replay(self):
        model,request,*_=fixture()
        request['station_ids']=['104']
        p=defaults();p.update(solver_seconds=1,annealing_iterations=10)
        p['historical_probabilities_pct']=[0,0,0,0,0]
        with patch('core.patrol.defaults',return_value=p):
            result=calculate(model,request,terrain_override=FlatTerrain())
        self.assertEqual(len(result['routes']),4)
        self.assertLessEqual(result['network']['max_horizontal_link_m'],200)
        for key in ('dijkstra_distance','dijkstra_weighted','annealing'):
            self.assertEqual(result['routes'][key]['status'],'ready')
            self.assertEqual(result['routes'][key]['resilience']['value'],1)
            self.assertEqual(result['routes'][key]['stops'],[])
        sim=simulate(result,dict(method='dijkstra_weighted'),FlatTerrain())
        self.assertEqual(sim['status'],'completed')
        self.assertTrue(all(r['battery_pct']>=0 for r in sim['timeline']))
        fire=list(transform(FWD,__import__('shapely').geometry.shape(request['target_polygon'])).centroid.coords)[0]
        detected=simulate(result,dict(method='dijkstra_weighted',fire=list(INV(*fire))),FlatTerrain())
        self.assertEqual(detected['status'],'detected_and_returned')
        self.assertIsNotNone(detected['detection'])
        self.assertAlmostEqual(detected['timeline'][-1]['coordinates'][0],request['origin'][0])

    def test_invalid_inputs_and_unknown_terrain(self):
        model,r,area,target,w=fixture()
        for change in [dict(target_polygon=mapping(box(0,0,1,1))),dict(seed=True),dict(preferences={'altitude_agl_m':float('nan')})]:
            with self.assertRaises(ValueError): calculate(model,dict(r,**change),terrain_override=FlatTerrain())
        class Missing(FlatTerrain):
            def at(self,x,y):return None
        g=Graph(area,Missing(),Hazards(model,iso(model['reference_time']),defaults(),[]),w,defaults())
        self.assertEqual(len(g.nodes),0)

    def test_hard_block_and_stochastic_marginal(self):
        model,r,area,target,w=fixture()
        hazard=mapping(transform(INV,target))
        h=Hazards(model,iso(model['reference_time']),defaults(),[dict(geometry=hazard,probability_pct=80)])
        ids=h.ids(target.centroid)
        self.assertAlmostEqual(h.probability(ids),1-(1-.8)*(1-.01))
        h=Hazards(model,iso(model['reference_time']),defaults(),[dict(geometry=hazard,probability_pct=100)])
        g=Graph(area,FlatTerrain(),h,w,defaults())
        self.assertTrue(all(not h.hard.intersects(__import__('shapely').geometry.LineString(e['coordinates'])) for e in g.edges.values()))

    def test_battery_swap_is_needed_and_inventory_is_finite(self):
        model,r,area,target,w=fixture()
        p=defaults();p['battery_budget_s']=70
        g=Graph(area,FlatTerrain(),Hazards(model,iso(model['reference_time']),p,[]),w,p)
        x,y=FWD(*r['origin'])
        home=g.point(r['origin'])
        a=g.point(list(INV(x+300,y)));b=g.point(list(INV(x+400,y)));station=g.point(list(INV(x+350,y)))
        states=oriented_tasks([dict(nodes=[a,b])],g,'cost')
        self.assertIsNone(fixed_route([0],states,g,home,[],'cost'))
        route=fixed_route([0],states,g,home,[dict(id='virtual',node=station)],'cost')
        self.assertIsNotNone(route)
        self.assertEqual(len(route['stops']),1)

    def test_intermediate_dsm_is_sampled(self):
        model,r,area,target,w=fixture()
        p=defaults()
        class Ridge(FlatTerrain):
            def at(self,x,y):return 80.0 if int(x)%100 in range(30,65) else 0.0
        g=Graph(area,Ridge(),Hazards(model,iso(model['reference_time']),p,[]),w,p)
        self.assertTrue(any(max(c[2] for c in e['coordinates'])>p['altitude_agl_m'] for e in g.edges.values()))


if __name__=='__main__':unittest.main()
