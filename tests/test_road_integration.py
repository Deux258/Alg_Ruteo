"""Una carga vial real compartida; no replica el gran grafo por cada aserción."""
import copy
import heapq
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from collections import defaultdict
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from core.contracts import ROOT,prepare_snapshot,write_json,validate_infrastructure
from core.db import connect,apply_schema,create_reader
from core.topology import load_infrastructure,audit
from core.routing import route,base_info,map_data,reachable_nodes
from core.web import Handler


class RealRoadIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (os.getenv('DATABASE_URL') or os.getenv('DB_HOST')):
            if os.getenv('REQUIRE_DB_TESTS')=='1':raise RuntimeError('Se requiere una BD Docker real')
            raise unittest.SkipTest('Ejecutar main probar para la red vial real')
        cls.conn=connect();apply_schema(cls.conn);create_reader(cls.conn)
        cls.config=json.loads((ROOT/'config/proyecto_vial.json').read_text())
        cls.rid=uuid4();cls.doc=prepare_snapshot(cls.config,str(cls.rid))
        for source in ['DERIVED_ROADS','SENAPRED_BOMBEROS','SENAPRED_CARABINEROS']:
            cls.conn.execute('INSERT INTO routing.sources(source_id,product) VALUES(%s,%s) ON CONFLICT DO NOTHING',(source,source))
        cls.conn.execute("INSERT INTO routing.runs(run_id,input_hash,scope,mode,configuration) VALUES(%s,%s,'base','snapshot',%s)",
                         (cls.rid,cls.doc['input_hash'],Jsonb(cls.config)))
        cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name)/'roads.json';write_json(cls.path,cls.doc)
        load_infrastructure(cls.conn,cls.path);cls.report=audit(cls.conn,cls.rid)
        cls.conn.execute("UPDATE routing.datasets SET validation=%s WHERE run_id=%s",(Jsonb(cls.report),cls.rid))
        with cls.conn.transaction():cls.conn.execute("SELECT routing.publish_run(%s,'base')",(cls.rid,))

    @classmethod
    def tearDownClass(cls):
        cls.conn.close();cls.temp.cleanup()

    def test_real_base_and_osm_origin_have_separate_verified_coordinates(self):
        b=base_info(self.conn,self.rid)
        self.assertEqual(b['provider_id'],'2872')
        self.assertEqual(self.doc['lineage']['base']['geometry']['coordinates'],[-71.621817,-33.0531369999999])
        self.assertTrue(self.report['road_routing']['checks']['base_inside'])
        self.assertGreater(b['road_offset_m'],0);self.assertLess(b['road_offset_m'],30)
        self.assertEqual(self.doc['lineage']['base']['osm_node_id'],13049981860)

    def test_full_real_road_graph_has_no_outside_or_unsupported_arcs(self):
        self.assertGreater(self.report['nodes'],10000);self.assertGreater(self.report['directed_edges'],20000)
        self.assertEqual(self.report['spatial']['outside_nodes'],0);self.assertEqual(self.report['spatial']['outside_edges'],0)
        self.assertEqual(self.report['road_routing']['checks']['arcs_without_osm'],0)
        self.assertEqual(self.report['road_routing']['checks']['invalid_transitions'],0)
        self.assertEqual(self.report['invalid_edges'],0)

    def test_duplicate_ids_and_osm_pairs_do_not_exist(self):
        row=self.conn.execute('''SELECT count(*)-count(DISTINCT id) AS duplicate_ids,
            count(*)-count(DISTINCT (source,target)) AS duplicate_arcs FROM routing.edges WHERE run_id=%s''',(self.rid,)).fetchone()
        self.assertEqual(row,dict(duplicate_ids=0,duplicate_arcs=0))
        self.assertTrue(load_infrastructure(self.conn,self.path)['idempotent'])

    def test_costs_match_independent_python_dijkstra_on_the_real_turn_graph(self):
        adjacency=defaultdict(list)
        for row in self.conn.execute('''SELECT t.source,t.target,e.length_km FROM routing.road_transitions t
            JOIN routing.edges e ON (e.run_id,e.id)=(t.run_id,t.edge_id) WHERE t.run_id=%s''',(self.rid,)):
            adjacency[row['source']].append((row['target'],row['length_km']))
        origin=self.doc['lineage']['base']['routing_node_id']
        for row in self.conn.execute('SELECT id,length_km FROM routing.edges WHERE run_id=%s AND source=%s',(self.rid,origin)):
            adjacency[0].append((row['id'],row['length_km']))
        distances={0:0.0};queue=[(0.0,0)]
        while queue:
            cost,node=heapq.heappop(queue)
            if cost!=distances[node]:continue
            for nxt,weight in adjacency[node]:
                candidate=cost+weight
                if candidate<distances.get(nxt,float('inf')):
                    distances[nxt]=candidate;heapq.heappush(queue,(candidate,nxt))
        for sample in self.report['road_routing']['examples']:
            actual=route(self.conn,self.rid,int(sample['target']))
            arrival=[r['id'] for r in self.conn.execute('''SELECT s.id FROM routing.road_states s JOIN routing.edges e
                ON (e.run_id,e.id)=(s.run_id,s.edge_id) WHERE s.run_id=%s AND e.target=%s''',(self.rid,int(sample['target'])))]
            expected=min(distances.get(n,float('inf')) for n in arrival)
            self.assertAlmostEqual(actual['properties']['distance_km'],expected,places=9)

    def test_three_real_routes_follow_streets_and_turns_and_distance_lower_bound(self):
        examples=self.report['road_routing']['examples'];self.assertEqual(len({e['target'] for e in examples}),3)
        for example in examples:
            target=int(example['target']);real=route(self.conn,self.rid,target);reference=route(self.conn,self.rid,target,respect_turns=False)
            self.assertTrue(real['properties']['respects_turns']);self.assertFalse(real['properties']['facility_to_road_included'])
            self.assertGreaterEqual(real['properties']['distance_km']+1e-9,reference['properties']['distance_km'])
            self.assertGreater(real['properties']['distance_km'],.5)
            self.assertEqual(real['properties']['target'],example['target'])

    def test_base_cannot_be_moved_or_relabelled_by_editing_the_json(self):
        d=copy.deepcopy(self.doc);d['lineage']['base']['geometry']['coordinates'][0]+=.00001
        with self.assertRaisesRegex(ValueError,'base alterados'):validate_infrastructure(d)

    def test_giro_cannot_be_silently_removed(self):
        d=copy.deepcopy(self.doc);d['lineage']['turn_restrictions']['forbidden_paths'].pop()
        with self.assertRaisesRegex(ValueError,'giro incompletas'):validate_infrastructure(d)

    def test_unreachable_real_destination_is_rejected_without_connectors(self):
        reachable={r['id'] for r in reachable_nodes(self.conn,self.rid,base_info(self.conn,self.rid)['node_id'])}
        target=next(r['id'] for r in self.conn.execute('SELECT id FROM routing.nodes WHERE run_id=%s ORDER BY id',(self.rid,)) if r['id'] not in reachable)
        with self.assertRaisesRegex(ValueError,'No existe una ruta permitida'):
            route(self.conn,self.rid,target)

    def test_click_on_the_real_osm_origin_returns_the_same_node(self):
        with self.conn.transaction():self.conn.execute("SELECT routing.publish_run(%s,'base')",(self.rid,))
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/nodo?lon=-71.6217814&lat=-33.0531793') as r:data=json.load(r)
            self.assertEqual(data['id'],str(self.doc['lineage']['base']['routing_node_id']))
            self.assertLess(data['offset_m'],0.001)
        finally:server.shutdown();server.server_close();thread.join(timeout=5)

    def test_real_web_map_route_and_outside_click(self):
        with self.conn.transaction():self.conn.execute("SELECT routing.publish_run(%s,'base')",(self.rid,))
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(url+'/health') as r:health=json.load(r)
            self.assertTrue(health['routing_ready']);self.assertEqual(health['application'],'road_routing')
            with urllib.request.urlopen(url+'/api/mapa') as r:data=json.load(r)
            self.assertGreater(len(data['features']),10000)
            with urllib.request.urlopen(url+'/api/ruta?destino='+data['examples'][0]['target']) as r:path=json.load(r)
            self.assertTrue(path['properties']['respects_turns'])
            for endpoint in ['/api/ruta?destino=abc','/api/nodo?lon=-71.5&lat=-33.05']:
                with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(url+endpoint)
                self.assertEqual(ctx.exception.code,422)
            with urllib.request.urlopen(url+'/') as r:self.assertIn('Ruteo por calles',r.read().decode())
            with urllib.request.urlopen(url+'/vendor/leaflet.js') as r:self.assertEqual(r.status,200)
        finally:server.shutdown();server.server_close();thread.join(timeout=5)
