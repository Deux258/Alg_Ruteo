import unittest
from unittest.mock import patch
from shapely.geometry import box,LineString,mapping
from shapely.ops import transform
from tests.test_patrol import fixture,FlatTerrain
from core.aerial_data import FWD,INV
from core.patrol import calculate,defaults,simulate
from core.patrol_alternatives import corridor_overlap


class DistinctCircuitTests(unittest.TestCase):
    def calculate_fixture(self,model,request):
        profile=defaults();profile.update(annealing_iterations=10,solver_seconds=1,scenarios=20)
        with patch('core.patrol.defaults',return_value=profile):return calculate(model,request,terrain_override=FlatTerrain())

    def test_four_spatial_circuits_and_original_comparison_preserved(self):
        model,request,*_=fixture();result=self.calculate_fixture(model,request)
        self.assertEqual(set(result['routes']),{'dijkstra_distance','dijkstra_weighted','gurobi','annealing'})
        self.assertEqual(len(result['route_alternatives']),4)
        self.assertTrue(result['diversity']['comparison_unchanged'])
        self.assertEqual(result['routes']['dijkstra_distance']['edge_ids'],result['route_alternatives']['alt_1']['edge_ids'])
        for key,row in result['route_alternatives'].items():
            self.assertTrue(row['coverage']['complete'])
            self.assertLessEqual(row['diversity']['max_shared_transit'],.8)
            simulation=simulate(result,dict(route_set='alternatives',method=key,scenario='nominal'),FlatTerrain())
            self.assertEqual(simulation['status'],'completed')
            self.assertTrue(all(f['battery_pct']>=0 for f in simulation['timeline']))
            self.assertEqual(simulation['timeline'][0]['time_s'],0)
            self.assertEqual(simulation['timeline'][0]['coordinates'][2],0)
            self.assertEqual(simulation['timeline'][-1]['coordinates'][2],0)
            self.assertAlmostEqual(simulation['time_s'],row['time_s'],places=6)

    def test_reverse_resampling_and_near_coincidence_are_not_diversity(self):
        a=LineString([(0,0),(100,0)])
        self.assertAlmostEqual(corridor_overlap(a,LineString([(100,0),(70,0),(0,0)])),1)
        self.assertAlmostEqual(corridor_overlap(a,LineString([(0,8),(100,8)])),1)
        self.assertEqual(corridor_overlap(a,LineString([(0,100),(100,100)])),0)

    def test_single_corridor_returns_one_circuit_instead_of_duplicates(self):
        model,request,*_=fixture();x,y=FWD(*request['origin']);x=round(x/100)*100;y=round(y/100)*100
        area=box(x-5,y-5,x+405,y+5);target=box(x+200,y-4,x+400,y+4)
        model['study_geometry']=model['flight_geometry']=mapping(transform(INV,area))
        request['target_polygon']=mapping(transform(INV,target));request['origin']=list(INV(x,y))
        model['records']['M1'][0]['geometry']['coordinates']=request['origin']
        result=self.calculate_fixture(model,request)
        self.assertEqual(len(result['route_alternatives']),1)
        self.assertEqual(result['diversity']['status'],'limited')

    def test_nominal_replay_is_separate_from_sampled_failures(self):
        model,request,*_=fixture();result=self.calculate_fixture(model,request)
        simulation=simulate(result,dict(scenario='nominal'),FlatTerrain())
        self.assertEqual(simulation['active_threat_ids'],[])
        self.assertEqual(simulation['scenario'],'nominal')
        for invalid in [dict(route_set='invented'),dict(scenario='invented'),dict(route_set='alternatives',method='unknown')]:
            with self.assertRaises(ValueError):simulate(result,invalid,FlatTerrain())

    def test_swap_is_on_ground_and_uses_edges_instead_of_sample_indices(self):
        model,request,*_=fixture();x,y=FWD(*request['origin'])
        model['records']['M1'].append(dict(provider_id='105',name='Swap fixture',candidate=True,
            geometry=dict(type='Point',coordinates=list(INV(x+300,y)))))
        request['station_ids']=['105'];request['preferences']={'battery_budget_s':80}
        result=self.calculate_fixture(model,request);route=result['routes']['dijkstra_distance']
        self.assertEqual(len(route['stops']),1)
        route['stops'][0]['coordinate_index']+=1000  # Sampling density must not move a swap.
        simulation=simulate(result,dict(method='dijkstra_distance',scenario='nominal'),FlatTerrain())
        self.assertEqual(simulation['status'],'completed')
        swaps=[f for f in simulation['timeline'] if f['phase']=='battery_swap']
        self.assertEqual(len(swaps),1);self.assertEqual(swaps[0]['coordinates'][2],0)
        self.assertAlmostEqual(simulation['time_s'],route['time_s'])
        self.assertTrue(all(f['battery_pct']>=0 for f in simulation['timeline']))

    def test_replay_respects_vertical_speed_between_samples(self):
        model,request,*_=fixture()
        class Ridge(FlatTerrain):
            def at(self,x,y):return 80. if int(x)%100 in range(30,65) else 0.
        p=defaults();p.update(annealing_iterations=10,solver_seconds=1,scenarios=10)
        with patch('core.patrol.defaults',return_value=p):result=calculate(model,request,terrain_override=Ridge())
        simulation=simulate(result,dict(method='dijkstra_distance',scenario='nominal'),Ridge())
        steep=[(abs(b['coordinates'][2]-a['coordinates'][2]),b['time_s']-a['time_s']) for a,b in zip(simulation['timeline'],simulation['timeline'][1:]) if abs(b['coordinates'][2]-a['coordinates'][2])>50]
        self.assertTrue(steep)
        self.assertTrue(all(dt>=dz/6-1e-5 for dz,dt in steep))


if __name__=='__main__':unittest.main()
