import copy
import heapq
import json
import unittest
from collections import defaultdict

from shapely.geometry import Polygon

from core.roads import directions,road_segments,blocked_node
from core.turns import state_graph


class RoadRules(unittest.TestCase):
    def test_oneway_reverse_and_roundabout(self):
        for tags,expected in [({'highway':'residential'}, {1,-1}),
            ({'highway':'residential','oneway':'yes'},{1}),
            ({'highway':'residential','oneway':'-1'},{-1}),
            ({'highway':'residential','junction':'roundabout'},{1}),
            ({'highway':'residential','oneway':'yes','oneway:motorcar':'no'},{1,-1})]:
            self.assertEqual(directions(tags)[0],expected)

    def test_steps_private_and_unknown_conditional_are_excluded(self):
        for tags in [{'highway':'steps'},{'highway':'footway'},
                     {'highway':'service','access':'private'},
                     {'highway':'residential','motor_vehicle':'no'},
                     {'highway':'residential','access:conditional':'no @ (Mo-Fr)'},
                     {'highway':'residential','oneway':'reversible'},
                     {'highway':'residential','maxheight':'2.0'}]:
            self.assertFalse(directions(tags)[0],tags)

    def test_access_hierarchy_and_directional_prohibition(self):
        self.assertEqual(directions({'highway':'residential','access':'no','motorcar':'yes'})[0],{1,-1})
        self.assertEqual(directions({'highway':'residential','motor_vehicle:backward':'no'})[0],{1})
        self.assertTrue(blocked_node({'barrier':'gate'}))
        self.assertFalse(blocked_node({'barrier':'gate','motorcar':'yes'}))

    def fixture(self):
        nodes=[dict(type='node',id=i+1,lon=p[0],lat=p[1]) for i,p in enumerate([[0,1],[2,1],[1,0],[1,2]])]
        ways=[dict(type='way',id=10,nodes=[1,2],tags={'highway':'residential'}),
              dict(type='way',id=11,nodes=[3,4],tags={'highway':'residential'})]
        return dict(elements=nodes+ways),Polygon([[-1,-1],[3,-1],[3,3],[-1,3]])

    def test_crossing_lines_do_not_create_an_intersection(self):
        osm,area=self.fixture();_,_,_,segments,_,_=road_segments(osm,area)
        self.assertEqual(set(segments),{(1,2),(3,4)})
        self.assertFalse(set((1,2)) & set((3,4)))

    def test_repeated_osm_element_and_duplicate_way_do_not_duplicate_arcs(self):
        osm,area=self.fixture();osm['elements'].append(copy.deepcopy(osm['elements'][-1]))
        alias=copy.deepcopy(osm['elements'][-1]);alias['id']=12;osm['elements'].append(alias)
        _,_,_,segments,_,aliases=road_segments(osm,area)
        self.assertEqual(len(segments),2);self.assertEqual(aliases,1)
        self.assertEqual(len(segments[(3,4)]['provenance']),2)

    def test_partial_boundary_segments_are_excluded_without_fabricated_endpoints(self):
        osm,_=self.fixture();area=Polygon([[-1,-1],[1.5,-1],[1.5,3],[-1,3]])
        _,_,_,segments,excluded,_=road_segments(osm,area)
        self.assertNotIn((1,2),segments);self.assertIn((3,4),segments)
        self.assertEqual(excluded['boundary_segment'],1)

    def test_barrier_does_not_allow_a_through_connection(self):
        osm,area=self.fixture();osm['elements'][0]['tags']={'barrier':'bollard'}
        _,_,_,segments,excluded,_=road_segments(osm,area)
        self.assertNotIn((1,2),segments);self.assertEqual(excluded['barrier_segment'],1)

    def test_conflicting_duplicate_element_is_an_error(self):
        osm,area=self.fixture();node=copy.deepcopy(osm['elements'][0]);node['lon']=3;osm['elements'].append(node)
        with self.assertRaisesRegex(ValueError,'versiones incompatibles'):road_segments(osm,area)

    def test_via_way_automaton_remembers_the_entry_but_does_not_overblock(self):
        edges=[dict(id=1,source=10,target=20),dict(id=2,source=20,target=30),
               dict(id=3,source=30,target=40),dict(id=4,source=20,target=50),dict(id=5,source=50,target=30)]
        states,transitions=state_graph(edges,[[1,2,3]])
        states={s['id']:s for s in states}
        next1=[t for t in transitions if t['source']==1 and t['edge_id']==2]
        self.assertEqual(len(next1),1)
        special=next1[0]['target']
        self.assertNotEqual(special,2)
        self.assertFalse(any(t['source']==special and t['edge_id']==3 for t in transitions))
        self.assertTrue(any(t['source']==2 and t['edge_id']==3 for t in transitions))
        self.assertTrue(any(t['source']==1 and t['edge_id']==4 for t in transitions))

    def test_node_turn_restriction_removes_only_the_forbidden_transition(self):
        edges=[dict(id=1,source=10,target=20),dict(id=2,source=20,target=30),dict(id=3,source=20,target=40)]
        _,transitions=state_graph(edges,[[1,2]])
        self.assertFalse(any(t['source']==1 and t['edge_id']==2 for t in transitions))
        self.assertTrue(any(t['source']==1 and t['edge_id']==3 for t in transitions))
