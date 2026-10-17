import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import ValidationError

from core.contracts import ROOT,prepare_snapshot,validate_infrastructure,stable_id,write_json
from core.pipeline import preflight
from core.web import safe_numbers


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((ROOT/'config/proyecto.json').read_text())
        cls.doc=prepare_snapshot(cls.config)

    def test_real_snapshot_counts(self):
        self.assertEqual((len(self.doc['nodes']),len(self.doc['edges'])),(85,480))

    def test_repeated_snapshot_is_deterministic(self):
        self.assertEqual(self.doc,prepare_snapshot(self.config))

    def test_order_does_not_change_ids(self):
        original=json.loads
        def reversed_features(text,*args,**kwargs):
            obj=original(text,*args,**kwargs)
            if isinstance(obj,dict) and obj.get('type')=='FeatureCollection':
                obj['features'].reverse()
            return obj
        with patch('core.contracts.json.loads',side_effect=reversed_features):
            reordered=prepare_snapshot(self.config)
        self.assertEqual(self.doc['nodes'],reordered['nodes'])
        self.assertEqual(self.doc['edges'],reordered['edges'])

    def test_legacy_weights_removed(self):
        self.assertFalse(any('tiempo' in str(x) or 'exposicion' in str(x) for x in self.doc['edges']))

    def test_orphan_is_rejected(self):
        d=copy.deepcopy(self.doc);d['edges'][0]['source']=123
        with self.assertRaises(ValueError):validate_infrastructure(d)

    def test_reversed_geometry_is_rejected(self):
        d=copy.deepcopy(self.doc);d['edges'][0]['geometry']['coordinates'].reverse()
        with self.assertRaises(ValueError):validate_infrastructure(d)

    def test_duplicate_nodes_rejected(self):
        d=copy.deepcopy(self.doc);d['nodes'].append(copy.deepcopy(d['nodes'][0]))
        with self.assertRaises(ValueError):validate_infrastructure(d)

    def test_parallel_edges_rejected(self):
        d=copy.deepcopy(self.doc);d['edges'].append(copy.deepcopy(d['edges'][0]))
        with self.assertRaises(ValueError):validate_infrastructure(d)

    def test_invalid_coordinate_rejected(self):
        d=copy.deepcopy(self.doc);d['nodes'][0]['geometry']['coordinates'][0]=float('nan')
        with self.assertRaises(ValueError):validate_infrastructure(d)

    def test_wrong_crs_rejected(self):
        d=copy.deepcopy(self.doc);d['crs']='EPSG:32719'
        with self.assertRaises(ValidationError):validate_infrastructure(d)

    def test_timestamp_needs_zone(self):
        d=copy.deepcopy(self.doc);d['observed_at']='2026-10-16T10:00:00'
        with self.assertRaises(ValueError):validate_infrastructure(d)

    def test_arc_identity_not_reassignable(self):
        d=copy.deepcopy(self.doc);d['edges'][0]['id']=123
        with self.assertRaises(ValueError):validate_infrastructure(d)

    def test_ids_fit_postgres_bigint(self):
        for n in self.doc['nodes']+self.doc['edges']:
            self.assertGreater(n['id'],0);self.assertLess(n['id'],2**63)

    def test_web_preserves_bigint_precision(self):
        ident=self.doc['nodes'][0]['id']
        value=safe_numbers({'id':ident,'count':85})
        self.assertEqual(int(value['id']),ident)
        self.assertIsInstance(value['id'],str)
        self.assertEqual(value['count'],85)

    def test_snapshot_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'infra.json';write_json(path,self.doc)
            self.assertEqual(validate_infrastructure(json.loads(path.read_text())),self.doc)

    def test_full_preflight_does_not_hide_missing_etl(self):
        with self.assertRaisesRegex(ValueError,'M1'):
            preflight('completo','snapshot')

    def test_online_preflight_is_explicitly_unavailable(self):
        with self.assertRaisesRegex(ValueError,'online'):
            preflight('base','online')

    def test_dependencies_cannot_cycle(self):
        m=json.loads((ROOT/'config/pipeline.json').read_text());m['steps'][0]['depends_on']=['I']
        with self.assertRaisesRegex(ValueError,'ciclo'):
            preflight('base','snapshot',m)


if __name__=='__main__':unittest.main()
