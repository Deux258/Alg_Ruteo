import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shapely.geometry import Point,LineString,shape,mapping
from shapely.ops import transform

from core.aerial_data import FWD,INV,iso
from core.aerial_routing import calculate,effective_profile,restrictions,overlay
from core.mission_evaluation import compare,summarise,scenario_catalogue,save
from core.contracts import ROOT,canonical
from tests import test_aerial as aerial_tests


class EvaluationRules(unittest.TestCase):
    def test_partial_acquisition_preserves_previous_manifest(self):
        import hashlib
        from Infraestructura import descargar_aereo as acquisition
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'raw';raw.mkdir();(root/'aoi.geojson').write_bytes((ROOT/'datos/entrada/aoi/Zona_Delimitada_Valpo.geojson').read_bytes())
            specs=root/'datos/entrada/fase1';specs.mkdir(parents=True);(specs/'manifest_fuentes.json').write_bytes((ROOT/'datos/entrada/fase1/manifest_fuentes.json').read_bytes())
            sources={}
            for key in ['S3','S6']:
                payload=key.encode();(raw/(key+'.bin')).write_bytes(payload);sources[key]=dict(product=key,file=key+'.bin',sha256=hashlib.sha256(payload).hexdigest())
            original=json.dumps(dict(version=2,sources=sources)).encode();(raw/'manifest.json').write_bytes(original)
            config=dict(aoi_geojson='aoi.geojson',aerial_raw_directory='raw',transit_buffer_m=1100,bbox_wgs84=[-71.7,-33.12,-71.5,-33.03])
            with patch.object(acquisition,'ROOT',root),patch.object(acquisition,'fetch',side_effect=RuntimeError('simulated outage')):
                with self.assertRaisesRegex(RuntimeError,'Fuentes incompletas'):
                    acquisition.download(config,{'S1','S1H','S2','S4','S5','S7'},{'S3','S6'})
            self.assertEqual((raw/'manifest.json').read_bytes(),original)
            self.assertEqual(len(json.loads((raw/'adquisicion_incompleta.json').read_text())['errors']),6)

    def test_known_survival_and_common_denominator_positive_zero_negative(self):
        methods={'reference':2,'proposed':2}
        positive=[dict(known=True,survives={'reference':[False,False],'proposed':[True,False]}),dict(known=True,survives={'reference':[True,False],'proposed':[False,True]}),dict(known=False,survives={'reference':[True,True],'proposed':[False,False]})]
        m=summarise(positive,methods)
        self.assertEqual(m['valid_scenarios'],2);self.assertEqual(m['unknown_scenarios'],1)
        self.assertEqual(m['methods']['reference']['individual'],[.5,0]);self.assertEqual(m['methods']['proposed']['set_survival'],1)
        self.assertEqual(m['delta_percentage_points'],50)
        swapped=[dict(r,survives={'reference':r['survives']['proposed'],'proposed':r['survives']['reference']}) for r in positive]
        self.assertEqual(summarise(swapped,methods)['delta_percentage_points'],-50)
        self.assertEqual(summarise([positive[1]],methods)['delta_percentage_points'],0)
        self.assertIsNone(summarise([positive[2]],methods)['delta_percentage_points'])

    def test_preferences_only_tighten_and_do_not_mutate_defaults(self):
        base=json.loads((ROOT/'config/aereo.json').read_text());before=copy.deepcopy(base)
        p=effective_profile(base,dict(budget_s=800,wind_limit_ms=6,detour_factor=1.1))
        self.assertEqual(p['budget_s'],800);self.assertEqual(base,before)
        for preferences in [dict(budget_s=1201),dict(wind_limit_ms=8.1),dict(detour_factor=.9),dict(budget_s=True),dict(wind_limit_ms=float('nan')),dict(speed=99)]:
            with self.assertRaises(ValueError):effective_profile(base,preferences)

    def test_firms_outside_center_but_intersecting_buffer_is_included(self):
        from Amenazas.a2_firms import transformar
        from shapely.geometry import Polygon
        area_m=Polygon([(250000,6330000),(250200,6330000),(250200,6330200),(250000,6330200)])
        area=transform(INV,area_m);lon,lat=INV(249950,6330100)
        csv_text='latitude,longitude,acq_date,acq_time,confidence,frp\n'+f'{lat},{lon},2026-10-19,0100,h,5\n'
        records=transformar(csv_text,area,100)
        self.assertEqual(len(records),1);self.assertFalse(area.covers(Point(records[0]['point']['coordinates'])))
        self.assertTrue(area.intersects(shape(records[0]['geometry'])))


class Phase2Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):aerial_tests.AerialIntegration.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):cls.conn.close()

    def test_study_unchanged_transit_and_catalogue_have_separate_roles(self):
        study=shape(self.model['study_geometry']);flight=shape(self.model['flight_geometry'])
        self.assertAlmostEqual(transform(FWD,study).area/1e6,54.92070918534,places=6)
        self.assertAlmostEqual(transform(FWD,flight).area/1e6,97.7162332977,places=5)
        self.assertEqual(len(self.view['bases']),5);self.assertEqual(len(self.view['base_catalogue']),16)
        self.assertEqual(sum(b['inside_study'] for b in self.view['bases']),1)
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM routing.base_metadata WHERE run_id=%s',(self.rid,)).fetchone()['n'],5)
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM routing.run_areas WHERE run_id=%s',(self.rid,)).fetchone()['n'],2)
        self.assertEqual(len({b['provider_id'] for b in self.view['base_catalogue']}),16)

    def test_four_external_origins_route_without_accepting_arbitrary_external_points(self):
        study=shape(self.model['study_geometry'])
        for base in self.view['bases']:
            coords=base['geometry']['coordinates']
            r=calculate(self.conn,self.rid,dict(self.request,origin=coords,method='reference'))
            self.assertEqual(r['status'],'ready');self.assertTrue(r['alternatives'][0]['return_path'])
        external=next(b for b in self.view['bases'] if not b['inside_study'])['geometry']['coordinates']
        with self.assertRaisesRegex(ValueError,'Origen externo'):
            calculate(self.conn,self.rid,dict(self.request,origin=[external[0]+.00001,external[1]]))
        with self.assertRaises(ValueError):calculate(self.conn,self.rid,dict(self.request,destination=external))

    def test_temporary_links_obey_radius_and_nodes_are_not_duplicated(self):
        nodes,edges,ids=overlay(self.conn,self.nodes,self.edges,dict(home=self.request['origin'],target=self.request['destination']),self.area,self.model['profile'])
        self.assertEqual(len({(e['source'],e['target']) for e in edges}),len(edges))
        for e in edges:
            self.assertLessEqual(transform(FWD,LineString(e['coordinates'])).length,1500.000001)

    def test_m3_matches_real_nodes_and_m2_retains_original_attributes(self):
        rows=self.conn.execute('SELECT node_id FROM routing.node_elevation WHERE run_id=%s',(self.rid,)).fetchall()
        self.assertEqual({str(r['node_id']) for r in rows},set(self.nodes))
        row=self.conn.execute('SELECT attributes,original_record,clipped_area_ha FROM routing.landcover WHERE run_id=%s LIMIT 1',(self.rid,)).fetchone()
        self.assertIn('subuse',row['attributes']);self.assertIn('altura',row['original_record']);self.assertGreater(row['clipped_area_ha'],0)
        self.assertEqual(self.model['weather_model'],'ecmwf_ifs025')

    def test_comparison_freezes_distinct_outbound_missions_and_is_repeatable(self):
        result=compare(self.conn,self.rid,self.request);repeat=compare(self.conn,self.rid,self.request)
        self.assertEqual(result['evaluation_sha256'],repeat['evaluation_sha256'])
        self.assertEqual(result['scenario_sha256'],repeat['scenario_sha256'])
        self.assertEqual(result['metrics']['total_scenarios'],100);self.assertEqual(result['metrics']['valid_scenarios'],100)
        for method in ['reference','proposed']:
            missions=result['sets'][method]['alternatives'];self.assertEqual(len(missions),2)
            self.assertNotEqual(missions[0]['outbound']['edge_ids'],missions[1]['outbound']['edge_ids'])
            self.assertTrue(all(p['return_path'] for p in missions))
        counts={r:sum(s['radius_m']==r for s in result['scenario_catalogue']['scenarios']) for r in [100,250,500]}
        self.assertEqual(counts,{100:33,250:33,500:33})
        with tempfile.TemporaryDirectory() as tmp:
            save(self.conn,result,Path(tmp));save(self.conn,result,Path(tmp))
            self.assertEqual(len(list(Path(tmp).glob('comparison_*.json'))),1)
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM routing.mission_evaluations WHERE run_id=%s AND evaluation_sha256=%s',(self.rid,result['evaluation_sha256'])).fetchone()['n'],1)

    def test_metric_does_not_replan_under_each_closure(self):
        import core.mission_evaluation as evaluation
        with patch.object(evaluation,'calculate',wraps=calculate) as calls:
            result=evaluation.compare(self.conn,self.rid,self.request)
        self.assertEqual(calls.call_count,2)
        unknown=compare(self.conn,self.rid,dict(self.request,time='2000-01-01T00:00:00Z'))
        self.assertEqual(unknown['metrics']['valid_scenarios'],0);self.assertIsNone(unknown['metrics']['delta_percentage_points'])

    def test_user_budget_and_wind_preferences_are_applied(self):
        too_short=calculate(self.conn,self.rid,dict(self.request,preferences=dict(budget_s=1)))
        self.assertEqual(too_short['status'],'not_feasible');self.assertEqual(too_short['remaining_s'],1)
        strict=calculate(self.conn,self.rid,dict(self.request,preferences=dict(wind_limit_ms=.01)))
        self.assertEqual(strict['reason'],'weather_outside_profile')

    def test_loader_rejects_forged_supplemental_source_lineage(self):
        from core.aerial_etl import load
        from core.contracts import write_json
        packet=json.loads((ROOT/'datos/runs'/self.rid/'metadata/bases.json').read_text())
        packet['lineage']['supporting_sources']['S1H']['product']='inventado'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.json';write_json(p,packet)
            with self.assertRaises(ValueError):load(self.conn,p)
