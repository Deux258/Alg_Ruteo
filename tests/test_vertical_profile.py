import copy
import math
import itertools
import unittest
from unittest.mock import patch

import numpy as np
from affine import Affine
from shapely.geometry import box, mapping
from shapely.ops import transform

from core.aerial_data import FWD, INV, iso
from core.mission_constraints import assess_constraints
from core.patrol import Graph, Hazards, calculate, defaults, simulate, gurobi_route, oriented_tasks
from core.vertical_profile import level, ramp_profile, target_display
from tests.test_patrol import FlatTerrain, fixture


class Constant93(FlatTerrain):
    source_sha256='constant-93'
    def at(self,x,y): return 93.


class VerticalProfileTests(unittest.TestCase):
    def test_levels_share_bands_and_plateau_clears_an_interior_peak(self):
        self.assertEqual(level(1,60),level(9,60))
        a,b=(0,0,60),(100,0,80)
        samples=[(0,0,0),(20,0,70),(50,0,30),(80,0,10),(100,0,20)]
        points=ramp_profile(a,b,samples,60)
        self.assertEqual(points[0],a);self.assertEqual(points[-1],b)
        by_x={p[0]:p[2] for p in points}
        for x,_,h in samples:self.assertGreaterEqual(by_x[x],level(h,60)-1e-8)
        peak=max(p[2] for p in points)
        plateau=[p for p in points if p[2]==peak]
        self.assertGreaterEqual(plateau[-1][0]-plateau[0][0],100/3-1e-8)
        self.assertIsNone(ramp_profile(a,b,[(0,0,0),(50,0,None),(100,0,20)],60))

    def test_graph_access_and_reverse_geometry_use_banded_levels(self):
        model,request,area,_,w=fixture();p=defaults();surface=Constant93()
        graph=Graph(area,surface,Hazards(model,iso(model['reference_time']),p,[]),w,p)
        home=graph.point(request['origin'])
        self.assertEqual(graph.nodes[home][2],160)
        self.assertAlmostEqual(graph.ascent(home),67/6)
        edge=next(iter(graph.edges.values()))
        reverse=next(e for e in graph.edges.values() if e['source']==edge['target'] and e['target']==edge['source'])
        self.assertEqual(list(reversed(edge['coordinates'])),list(reverse['coordinates']))
        self.assertTrue(all(c[2]==160 for c in edge['coordinates']))

    def test_shared_energy_assessment_rejects_quantized_access_near_boundary(self):
        model,request,*_=fixture();request['preferences']={'battery_budget_s':82}
        assessed=assess_constraints(model,request,_surface=Constant93())
        self.assertFalse(assessed['admissible'])
        self.assertEqual(assessed['vertical_access_basis'],'exact_banded_origin')
        self.assertAlmostEqual(assessed['origin_access_height_m'],67)
        result=calculate(model,request,terrain_override=Constant93())
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['constraints']['origin_vertical_flight_s'],assessed['origin_vertical_flight_s'])

    def test_new_simulation_reuses_canonical_geometry_and_actual_support(self):
        model,request,*_=fixture();p=defaults()
        p.update(solver_seconds=1,annealing_iterations=10,alternative_search_seconds=.2)
        p['historical_probabilities_pct']=[0]*5
        with patch('core.patrol.defaults',return_value=p):
            result=calculate(model,request,terrain_override=Constant93())
        method='dijkstra_weighted';route=result['routes'][method]
        self.assertEqual(route['status'],'ready')
        self.assertTrue(result['graph']['geometry'])
        self.assertLess(len(result['graph']['geometry']),len(result['graph']['edges']))
        self.assertNotIn('coordinates',result['graph']['edges'][0])
        sim=simulate(result,dict(method=method,scenario='nominal'),Constant93())
        self.assertEqual(sim['status'],'completed')
        self.assertAlmostEqual(sim['timeline'][0]['coordinates'][2],93)
        self.assertAlmostEqual(sim['timeline'][-1]['coordinates'][2],93)
        self.assertAlmostEqual(sim['time_s'],route['time_s'],places=7)
        flown=[f['coordinates'] for f in sim['timeline'] if f['phase']=='patrol']
        self.assertTrue(all(c[2]==160 for c in flown))
        missing=copy.deepcopy(result);missing['graph']['geometry']={}
        with self.assertRaisesRegex(ValueError,'canónica'):
            simulate(missing,dict(method=method,scenario='nominal'),Constant93())
        legacy=copy.deepcopy(result);legacy.pop('vertical_profile')
        for edge in legacy['graph']['edges']:
            edge.pop('geometry_id');edge.pop('geometry_reversed')
        old=simulate(legacy,dict(method=method,scenario='nominal'),Constant93())
        self.assertEqual(old['status'],'completed')

    def test_uneven_support_milp_matches_independent_station_enumeration(self):
        model,request,area,_,w=fixture();x,y=FWD(*request['origin'])
        class Slope(FlatTerrain):
            def at(self,east,north):return 93.+.07*(east-x)
        p=defaults();p.update(battery_budget_s=95,solver_seconds=3,solver_gap=0)
        graph=Graph(area,Slope(),Hazards(model,iso(model['reference_time']),p,[]),w,p)
        home=graph.point(request['origin'])
        nodes=[graph.point(list(INV(x+dx,y+dy))) for dx,dy in [(150,0),(250,0),(150,150),(250,150),(200,70)]]
        states=oriented_tasks([dict(nodes=nodes[:2]),dict(nodes=nodes[2:4])],graph,'cost')
        station=nodes[4];best=math.inf
        for order in itertools.permutations(range(2)):
            for directions in itertools.product(range(2),repeat=2):
                selected=[next(s for s in states if s['group']==g and s['direction']==d) for g,d in zip(order,directions)]
                for position in (None,0,1,2):
                    actions=selected[:]
                    if position is not None:actions.insert(position,dict(kind='swap',start=station,end=station,time_s=0,cost=0))
                    actions.append(dict(kind='end',start=home,end=home,time_s=0,cost=0))
                    node=home;energy=graph.ascent(home);elapsed=energy;cost=energy;valid=True
                    for action in actions:
                        leg=graph.totals(graph.path(node,action['start'],'cost'))
                        energy+=leg['time_s'];elapsed+=leg['time_s'];cost+=leg['cost']
                        kind=action.get('kind')
                        if kind in ('swap','end'):
                            descent=graph.landing(action['start'])
                            if energy+descent>p['battery_budget_s']:valid=False;break
                            duration=descent
                            if kind=='swap':
                                energy=graph.ascent(station)
                                duration+=p['station_service_s']+energy
                        else:
                            energy+=action['time_s'];duration=action['time_s']
                            if energy>p['battery_budget_s']:valid=False;break
                        elapsed+=duration;cost+=duration if kind else action['cost'];node=action['end']
                    if valid and elapsed<=p['mission_budget_s']:best=min(best,cost)
        answer,metadata=gurobi_route(states,graph,home,[dict(id='swap',node=station)])
        self.assertTrue(math.isfinite(best))
        self.assertIsNotNone(answer,metadata)
        self.assertAlmostEqual(answer['cost'],best,places=6)
        self.assertTrue(answer['stops'])
        self.assertNotEqual(graph.ascent(home),graph.ascent(station))

    def test_ramped_mission_replay_preserves_profile_rates_and_safe_detection_return(self):
        model,request,*_=fixture();x,y=FWD(*request['origin'])
        class Hills(FlatTerrain):
            def at(self,east,north):return 93.+20*math.sin((east-x)/70)
        p=defaults();p.update(solver_seconds=1,annealing_iterations=10,alternative_search_seconds=.1)
        p['historical_probabilities_pct']=[0]*5
        with patch('core.patrol.defaults',return_value=p):
            result=calculate(model,request,terrain_override=Hills())
        route=result['routes']['dijkstra_weighted']
        self.assertEqual(route['status'],'ready')
        self.assertGreater(len({c[2] for c in route['coordinates']}),1)
        replay=simulate(result,dict(method='dijkstra_weighted',scenario='nominal'),Hills())
        self.assertAlmostEqual(replay['time_s'],route['time_s'],places=6)
        for a,b in zip(replay['timeline'],replay['timeline'][1:]):
            dt=b['time_s']-a['time_s'];dz=b['coordinates'][2]-a['coordinates'][2]
            self.assertLessEqual(abs(dz),6*dt+1e-5)
        detected=simulate(result,dict(method='dijkstra_weighted',scenario='nominal',fire=list(INV(x+240,y))),Hills())
        self.assertEqual(detected['status'],'detected_and_returned')
        self.assertTrue(detected['detection']['report_completed'])
        self.assertGreaterEqual(detected['timeline'][-1]['battery_pct'],0)

    def test_target_uses_interior_original_pixels_and_unknown_is_explicit(self):
        class Raster:
            source_sha256='fixture-raster'
            scale=1.;offset=0.
            affine=~Affine(.0001,0,-71.65,0,-.0001,-33.1)
            array=np.ma.array(np.full((5,5),10.),mask=False)
        raw=Raster();raw.array[2,2]=200
        polygon=mapping(box(-71.65+.00001,-33.1-.00049,-71.65+.00049,-33.1-.00001))
        result=target_display({},polygon,raw)
        self.assertEqual(result['status'],'known')
        self.assertEqual(result['level_m_egm2008'],230)
        feature=dict(type='Feature',properties=dict(name='uploaded'),geometry=copy.deepcopy(polygon))
        feature['geometry']['coordinates']=[[[*c,999] for c in ring] for ring in polygon['coordinates']]
        imported=target_display({},feature,raw)
        self.assertEqual(imported['level_m_egm2008'],result['level_m_egm2008'])
        self.assertEqual(imported['polygon_sha256'],result['polygon_sha256'])
        raw.array.mask[2,2]=True
        result=target_display({},polygon,raw)
        self.assertEqual(result['status'],'unknown_elevation')
        self.assertIsNone(result['level_m_egm2008'])

    def test_target_also_clears_intersecting_visual_mesh_triangle(self):
        x,y=FWD(-71.65,-33.1)
        area=box(x,y,x+100,y+100)
        class Mesh(FlatTerrain):
            def mesh(self,area,step=30):
                self.step=step
                return dict(origin_utm=[x,y],width=2,height=2,x=[0,100],y=[0,100],elevations=[120,0,0,0])
        raw=Mesh();target=box(x+20,y+20,x+30,y+30)
        result=target_display(dict(flight_geometry=mapping(transform(INV,area))),mapping(transform(INV,target)),raw)
        self.assertEqual(raw.step,30)
        self.assertEqual(result['level_m_egm2008'],150)


if __name__=='__main__':unittest.main()
