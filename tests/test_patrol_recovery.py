import unittest

from core.patrol_recovery import compare, path_search, milp


def graph():
    edges={}
    for ident,a,b,d,t in [('sa','s','a',1,9),('ah','a','h',1,9),('sb','s','b',4,2),('bh','b','h',4,2),('sc','s','c',5,3)]:
        edges[ident]=dict(source=a,target=b,distance_m=d,time_s=t,cost=t)
    adj={n:[i for i,e in edges.items() if e['source']==n] for n in ('s','a','b','c','h')}
    return edges,adj


class RecoveryTests(unittest.TestCase):
    def compare(self,battery=30,failed=frozenset(),**kwargs):
        edges,adj=graph()
        return compare(edges,adj,'s','h',[dict(id='same-origin',node='h'),dict(id='station',node='c')],battery,5,
                       dict(mission_budget_s=100,solver_seconds=1,annealing_iterations=12),lambda n:1.,failed,seed=123,**kwargs)

    def test_distance_and_parameters_are_different_real_objectives(self):
        result=self.compare(destination='origin')
        self.assertEqual(result['recommendations']['dijkstra_distance']['edge_ids'],['sa','ah'])
        self.assertEqual(result['recommendations']['dijkstra_weighted']['edge_ids'],['sb','bh'])
        self.assertEqual(result['selected']['destination_id'],'origin')

    def test_resource_constrained_distance_keeps_nondominated_labels(self):
        result=self.compare(battery=10,destination='origin')
        self.assertEqual(result['recommendations']['dijkstra_distance']['edge_ids'],['sb','bh'])
        self.assertTrue(all(r['battery_remaining_s']>=0 for r in result['candidates'] if r['status']=='ready'))

    def test_four_techniques_two_destinations_and_no_duplicate_origin(self):
        result=self.compare()
        self.assertEqual(len(result['candidates']),8)
        self.assertFalse(any(r['destination_id']=='same-origin' for r in result['candidates']))
        self.assertEqual(result['selected']['destination_id'],'station')
        annealing=result['recommendations']['annealing']
        self.assertGreater(annealing['solver']['iterations'],0)
        again=self.compare()
        self.assertEqual(annealing['edge_ids'],again['recommendations']['annealing']['edge_ids'])

    def test_gurobi_matches_small_exhaustive_oracle_or_declares_unavailable(self):
        result=self.compare(destination='origin')
        row=next(r for r in result['candidates'] if r['method']=='gurobi' and r['destination_id']=='origin')
        if row['status']=='ready':
            self.assertEqual(row['edge_ids'],['sb','bh'])
            self.assertEqual(row['cost'],min(9+9,2+2))
        else:
            self.assertIn(row['solver']['status'],('unavailable','solver_error'))
            self.assertEqual(row['edge_ids'],[])

    def test_failed_destinations_and_no_safe_return(self):
        self.assertIsNone(self.compare(battery=.5)['selected'])
        blocked=self.compare(failed={'c'},destination='station')
        self.assertIsNone(blocked['selected'])
        self.assertTrue(blocked['recommendations']=={})

    def test_milp_omits_empty_nodes_after_corridor_restriction(self):
        edges,adj=graph();adj.update({f'isolated:{i}':[] for i in range(5000)})
        path,meta=milp(edges,adj,'s','h',20,1)
        if path is not None:
            self.assertEqual(path,['sb','bh'])
            self.assertLess(meta['constraints'],10)
        else:self.assertIn(meta['status'],('unavailable','solver_error'))


if __name__=='__main__': unittest.main()
