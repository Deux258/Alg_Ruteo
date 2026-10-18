import copy
import json
import tempfile
import unittest
from pathlib import Path

from shapely.geometry import shape

from core.area import load_area
from core.contracts import ROOT, prepare_snapshot, validate_infrastructure


class StudyArea(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((ROOT/'config/proyecto_legacy.json').read_text(encoding='utf-8'))
        cls.area = load_area(ROOT/cls.config['aoi_geojson'])
        cls.doc = prepare_snapshot(cls.config)

    def test_all_output_points_and_full_lines_are_covered(self):
        for feature in self.doc['nodes'] + self.doc['edges']:
            self.assertTrue(self.area.covers(shape(feature['geometry'])))

    def test_original_files_are_preserved_and_exclusions_are_traceable(self):
        raw = json.loads((ROOT/'datos/entrada/fase1/nodos.geojson').read_text(encoding='utf-8'))
        self.assertEqual(len(raw['features']), 85)
        self.assertEqual(self.doc['lineage']['spatial_filter'],
            dict(input_nodes=85, input_edges=480, excluded_nodes=72, excluded_edges=418))
        self.assertFalse(any(n['kind']=='base_candidata' for n in self.doc['nodes']))

    def test_loader_contract_rejects_external_node_even_inside_legacy_bbox(self):
        doc = copy.deepcopy(self.doc)
        doc['nodes'][0]['geometry']['coordinates'] = [-71.50,-33.05]
        with self.assertRaisesRegex(ValueError, 'fuera del polígono'):
            validate_infrastructure(doc)

    def test_aoi_hash_cannot_be_replaced(self):
        doc = copy.deepcopy(self.doc)
        doc['lineage']['aoi']['sha256'] = 'a'*64
        with self.assertRaisesRegex(ValueError, 'linaje'):
            validate_infrastructure(doc)

    def fixture(self, directory, polygon, coordinates, pairs):
        folder = Path(directory)
        (folder/'aoi.geojson').write_text(json.dumps({'type':'FeatureCollection','features':[
            {'type':'Feature','properties':{},'geometry':polygon}]}),encoding='utf-8')
        nodes = [{'type':'Feature','geometry':{'type':'Point','coordinates':coords},
                  'properties':{'id':i,'tipo':'vigilancia','x':i*800,'y':0}}
                 for i,coords in enumerate(coordinates)]
        edges = [{'type':'Feature','geometry':{'type':'LineString','coordinates':[coordinates[s],coordinates[t]]},
                  'properties':{'origen':s,'destino':t}} for s,t in pairs]
        for name,features in [('nodos',nodes),('aristas',edges)]:
            (folder/(name+'.geojson')).write_text(json.dumps({'type':'FeatureCollection','features':features}),encoding='utf-8')
        return dict(self.config,snapshot_directory=str(folder),aoi_geojson=str(folder/'aoi.geojson'))

    def test_arc_exiting_concave_polygon_is_removed_despite_inside_endpoints(self):
        # U: el enlace horizontal cruza la abertura; el vertical permanece dentro.
        polygon={'type':'Polygon','coordinates':[[[0,0],[3,0],[3,3],[2,3],[2,1],[1,1],[1,3],[0,3],[0,0]]]}
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            cfg=self.fixture(folder,polygon,[[.5,2.5],[2.5,2.5],[.5,.5]],[(0,1),(0,2)])
            doc=prepare_snapshot(cfg)
        self.assertEqual(len(doc['nodes']),3)
        self.assertEqual(len(doc['edges']),1)
        self.assertEqual(doc['edges'][0]['geometry']['coordinates'],[[.5,2.5],[.5,.5]])

    def test_boundary_is_included(self):
        polygon={'type':'Polygon','coordinates':[[[0,0],[2,0],[2,2],[0,2],[0,0]]]}
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            doc=prepare_snapshot(self.fixture(folder,polygon,[[0,0],[2,0]],[(0,1)]))
        self.assertEqual((len(doc['nodes']),len(doc['edges'])),(2,1))

    def test_hole_is_respected(self):
        polygon={'type':'Polygon','coordinates':[
            [[0,0],[4,0],[4,4],[0,4],[0,0]], [[1,1],[1,3],[3,3],[3,1],[1,1]]]}
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            doc=prepare_snapshot(self.fixture(folder,polygon,[[.5,.5],[.5,3.5],[2,2]],[(0,1),(0,2)]))
        self.assertEqual((len(doc['nodes']),len(doc['edges'])),(2,1))

    def test_invalid_polygon_is_rejected_without_automatic_repair(self):
        polygon={'type':'Polygon','coordinates':[[[0,0],[2,2],[0,2],[2,0],[0,0]]]}
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            cfg=self.fixture(folder,polygon,[[0,0],[1,1]],[(0,1)])
            with self.assertRaisesRegex(ValueError,'inválido'):
                prepare_snapshot(cfg)


if __name__=='__main__':
    unittest.main()
