"""Transport contracts, spatial clipping and HTTP cache behavior without a database."""
import copy
import gzip
import hashlib
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import numpy as np
from shapely import is_prepared
from shapely.geometry import Point,Polygon,box,mapping,shape
from shapely.ops import transform

from core.aerial_data import FWD,INV
from core.communes import Communes,commune_index
from core.contracts import ROOT,canonical,sha256
from core.geo_transport import ResourceStore,clip_triangle,typed_assets,result_summary,publish_result,filtered_result_resource,_map_key,_clip_vertices
from core.web import Handler
from core import web


class TransportTests(unittest.TestCase):
    def test_clip_skips_intersections_for_inside_and_outside_triangles(self):
        vertices=np.array([[1,1,10],[2,1,10],[1,2,10],[-3,1,10],[-2,1,10],[-3,2,10],[-1,1,10],[1,1,10],[1,2,10]],dtype=np.float32)
        with patch('core.geo_transport.clip_triangle',wraps=clip_triangle) as intersect:
            clipped=_clip_vertices(vertices,'triangles',box(0,0,5,5))
            self.assertEqual(intersect.call_count,1)
            self.assertTrue(np.all(clipped[:,0]>=0));self.assertGreater(len(clipped),3)

    def test_map_key_invalidates_all_source_layers_and_default_profile_without_scene_change(self):
        model=dict(records={key:[dict(value=1)] for key in ('M1','M2','M4','A2','A3','A4')},reference_time='2026-01-01T00:00:00+00:00',_run_id='first')
        profile=dict(battery_budget_s=1200,wind_limit_ms=8)
        with patch('core.geographic_scene.scene_identity',return_value=('unchanged-scene',{},{})),patch('core.patrol.terrain',return_value=None),patch('core.patrol.defaults',return_value=profile) as defaults,patch('core.geo_transport.commune_index') as index:
            index.return_value.identity_sha256='unchanged-boundaries'
            baseline=_map_key(model,None)
            for key in model['records']:
                changed=copy.deepcopy(model);changed['records'][key][0]['value']=2
                with self.subTest(source=key):self.assertNotEqual(_map_key(changed,None),baseline)
            defaults.return_value=dict(profile,wind_limit_ms=6)
            self.assertNotEqual(_map_key(model,None),baseline)
            defaults.return_value=profile
            self.assertNotEqual(_map_key(model,'05109'),baseline)
            self.assertEqual(_map_key(dict(model,_run_id='second'),None),baseline)

    def test_parallel_stores_never_expose_partial_metadata_or_colliding_temporary_files(self):
        with tempfile.TemporaryDirectory() as folder:
            # Distinct instances exercise the CLI/server case, not only one Python lock.
            stores=[ResourceStore(folder) for _ in range(4)];body=b'concurrent immutable resource'*1024
            digest=hashlib.sha256(body).hexdigest()
            def task(i):
                resource=stores[i%4]
                for _ in range(15):
                    resource.put(body);self.assertEqual(resource.get(digest)['sha256'],digest)
                return True
            with ThreadPoolExecutor(max_workers=8) as pool:self.assertTrue(all(pool.map(task,range(8))))
            self.assertEqual((Path(folder)/(digest+'.data')).read_bytes(),body)
            self.assertEqual(list(Path(folder).glob('*.tmp')),[])

    def test_result_evicted_by_python_memory_stays_exportable(self):
        result=dict(sha256='b'*64,routes={},graph=dict(nodes=[],edges=[]),threats=[],failure_probabilities={},payload=['value'+str(i) for i in range(100)])
        with tempfile.TemporaryDirectory() as folder,patch('core.geo_transport.store',return_value=ResourceStore(folder)),patch.dict(web.PATROL_RESULTS,{},clear=True),patch.dict(web.PATROL_RESULT_BYTES,{},clear=True),patch('core.web.PATROL_MEMORY_LIMIT',100):
            web.remember_patrol(result)
            self.assertNotIn(result['sha256'],web.PATROL_RESULTS)
            self.assertEqual(web.previous_patrol(result['sha256']),result)

    def test_single_flight_and_bounded_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            resources=ResourceStore(folder,memory_limit=2048);calls=[]
            def produce():calls.append(1);time.sleep(.03);return dict(value=5)
            with ThreadPoolExecutor(max_workers=8) as pool:
                values=list(pool.map(lambda _:resources.memo('shared-key',produce),range(8)))
            self.assertEqual(len(calls),1);self.assertTrue(all(v==dict(value=5) for v in values))
            for i in range(10):resources.put(bytes([i])*1024)
            self.assertLessEqual(resources.memory_bytes,2048)
            self.assertIsNone(resources.get('../invalid'))

    def test_triangle_clipping_interpolates_z_and_keeps_vertical_walls(self):
        clipped=clip_triangle(np.array([[-2,0,0],[2,0,4],[0,2,2]],dtype=np.float32),box(0,-1,5,5))
        self.assertGreater(len(clipped),0)
        self.assertTrue(np.all(clipped[:,0]>=0))
        self.assertTrue(np.allclose(clipped[:,2],clipped[:,0]+2))
        wall=clip_triangle(np.array([[-2,0,0],[2,0,0],[-2,0,10]],dtype=np.float32),box(0,-1,5,1))
        self.assertGreater(len(wall),0);self.assertTrue(np.all(wall[:,0]>=0));self.assertGreater(wall[:,2].max(),0)

    def test_cut_clips_objects_without_commune_attributes_and_preserves_original(self):
        index=Communes.__new__(Communes)
        index.rows={'left':dict(metric=box(0,0,10,10),geometry=transform(INV,box(0,0,10,10)),properties=dict(name='Left'))}
        original=dict(type='Feature',geometry=mapping(transform(INV,box(5,2,15,8))),properties=dict(id='unnamed',position_utm=[12,5,40]))
        saved=copy.deepcopy(original);result=index.clip_feature(original,'left')
        clipped=transform(FWD,shape(result['geometry']))
        self.assertAlmostEqual(clipped.area,30,places=4)
        self.assertEqual(original,saved);self.assertEqual(result['properties']['position_utm'],original['properties']['position_utm'])
        self.assertTrue(index.metric('left').covers(Point(FWD(*result['properties']['display_anchor']))))
        self.assertTrue(clipped.covers(Point(FWD(*result['properties']['display_anchor']))))
        self.assertNotIn('display_anchor',original['properties'])
        self.assertIsNone(index.clip_feature(dict(type='Feature',geometry=mapping(transform(INV,box(11,2,15,8))),properties={}), 'left'))
        with self.assertRaisesRegex(ValueError,'CUT'):index.clip_features([], 'unknown')

    def test_real_snapshot_has_both_cut_codes_and_versioned_hashes(self):
        index=commune_index()
        self.assertEqual({c['id'] for c in index.catalogue()},{'05101','05109'})
        original=index.manifest['original']
        self.assertEqual(sha256(ROOT/'datos/entrada/comunas'/original['file']),original['sha256'])
        self.assertEqual(index.manifest['derived']['source_crs'],'EPSG:3857')
        self.assertIn('Biblioteca',index.manifest['attribution'])
        self.assertTrue(all(is_prepared(index.metric(c['id'])) for c in index.catalogue()))

    def test_typed_assets_clip_ground_and_skip_unknown_elevation(self):
        scene=dict(origin_utm=[100,200],render={'buildings':[dict(vertices=[-2,0,10,2,0,10,0,2,10],mode='triangles',color=[.7,.6,.5])]})
        mesh=dict(width=2,height=2,origin_utm=[100,200],x=[0,10],y=[0,10],elevations=[None,10,10,10])
        with tempfile.TemporaryDirectory() as folder,patch('core.geo_transport.store',return_value=ResourceStore(folder)) as store_mock,patch('core.geo_transport.commune_index') as index:
            index.return_value.metric.return_value=box(100,200,110,210)
            data=typed_assets(scene,'left',mesh)
            self.assertEqual(data['schema_version'],'typed-scene-1')
            self.assertEqual(data['groups']['terrain'][0]['count'],3) # one of two mesh triangles contains NoData
            for batches in data['groups'].values():
                for batch in batches:
                    spec=batch['positions'];path=Path(folder)/(spec['sha256']+'.data')
                    vertices=np.frombuffer(path.read_bytes(),dtype='<f4').reshape((-1,3))
                    self.assertTrue(np.all(vertices[:,0]>=0));self.assertTrue(np.all(vertices[:,2]>0))
                    self.assertEqual(sha256(path),spec['sha256']);self.assertEqual(len(vertices),batch['count'])

    def test_summary_defers_large_geometry_and_exports_unmodified_result(self):
        coordinates=[[i*.000001,-33.05,40] for i in range(16000)]
        routes={k:dict(status='ready',coordinates=coordinates,coordinates_utm=coordinates,edge_ids=['1'],coverage={'complete':True}) for k in ('a','b','c','d')}
        result=dict(sha256='a'*64,routes=routes,route_alternatives={},graph=dict(nodes=[dict(id='1',coordinates=[-71.6,-33.05,40])],edges=[dict(id='1')]),
                    threats=[dict(id='threat',geometry=mapping(box(-72,-34,-71,-33)),probability_pct=80)],failure_probabilities=dict(nodes=[1]),evaluation=dict(scenarios=[{'i':i} for i in range(1000)],count=1000))
        with tempfile.TemporaryDirectory() as folder,patch('core.geo_transport.store',return_value=ResourceStore(folder)) as resources:
            summary=result_summary(result)
            self.assertLessEqual(len(canonical(summary)),1048576)
            self.assertNotIn('graph',summary);self.assertNotIn('geometry',summary['threats'][0]);self.assertTrue(summary['routes']['a']['geometry_deferred'])
            exported=resources.return_value.read_json(summary['resources']['exportar'])
            self.assertEqual(exported['routes']['a']['coordinates'],coordinates)
            self.assertEqual(len(result['routes']['a']['coordinates']),16000)

    def test_http_hash_resource_etag_gzip_and_validation_endpoint(self):
        with tempfile.TemporaryDirectory() as folder:
            resources=ResourceStore(folder);ref=resources.json({'text':'á'*1000})
            with patch('core.geo_transport.store',return_value=resources),patch.dict('os.environ',{'PATROL_CONTEXT':'fixture'}),patch('core.web.patrol_model',return_value={}),patch('core.mission_constraints.assess_constraints',return_value=dict(admissible=False,reasons=[dict(code='wind')])):
                server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    root=f'http://127.0.0.1:{server.server_port}'
                    with urllib.request.urlopen(urllib.request.Request(root+ref['url'],headers={'Accept-Encoding':'gzip'})) as response:
                        body=gzip.decompress(response.read());etag=response.headers['ETag']
                        self.assertEqual(hashlib.sha256(body).hexdigest(),ref['sha256']);self.assertIn('immutable',response.headers['Cache-Control'])
                    with self.assertRaises(urllib.error.HTTPError) as cached:urllib.request.urlopen(urllib.request.Request(root+ref['url'],headers={'If-None-Match':etag}))
                    self.assertEqual(cached.exception.code,304)
                    with urllib.request.urlopen(urllib.request.Request(root+'/api/aereo/patrullaje/validar',data=b'{}',headers={'Content-Type':'application/json'})) as response:
                        value=json.load(response);self.assertFalse(value['valid']);self.assertEqual(value['violations'][0]['code'],'wind');self.assertEqual(response.headers['Cache-Control'],'no-store')
                finally:server.shutdown();server.server_close();thread.join(timeout=5)
