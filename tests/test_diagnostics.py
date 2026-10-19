import copy
import io
import json
import socket
import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from shapely.geometry import box

from core import aip_acquisition as aip
from core.contracts import ROOT
from core.mission_diagnostics import minimum_mission, shortest_time


class Response(io.BytesIO):
    status=200
    headers={'Content-Type':'application/pdf'}
    def geturl(self): return aip.INDEX


class Transport:
    def __init__(self, values): self.values=iter(values)
    def open(self,*args,**kwargs):
        value=next(self.values)
        if isinstance(value,Exception): raise value
        return Response(value)


class AcquisitionTests(unittest.TestCase):
    def test_transport_errors_classified_and_three_attempts_with_1_3_waits(self):
        errors=[(URLError(socket.gaierror(-2,'dns')),'dns'),(URLError(ssl.SSLError('tls')),'tls'),
                (TimeoutError('timeout'),'timeout'),(HTTPError(aip.INDEX,503,'failed',{},None),'http')]
        for error,kind in errors:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as tmp:
                attempts=[]; waits=[]
                with self.assertRaises(aip.AcquisitionError) as raised:
                    aip.retrieve(aip.INDEX,Path(tmp),'S6',attempts,Transport([error]*3),waits.append)
                self.assertEqual(raised.exception.kind,kind)
                self.assertEqual(waits,[1,3]); self.assertEqual(len(attempts),3)
                self.assertTrue(all(r['timeout_s']==20 for r in attempts))

    def test_html_instead_of_pdf_is_not_a_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempts=[]
            with self.assertRaises(aip.AcquisitionError) as raised:
                aip.retrieve(aip.INDEX,Path(tmp),'S6',attempts,Transport([b'<html>error</html>']*3),lambda _:None)
            self.assertEqual(raised.exception.kind,'content'); self.assertEqual(list(Path(tmp).iterdir()),[])

    def test_official_link_discovery_and_https_redirect_policy(self):
        html=b'<a href="/official.pdf"> ENR 5.1 Zonas P, R, D </a>'
        self.assertEqual(aip.pdf_link(html,aip.INDEX),'https://aipchile.dgac.gob.cl/official.pdf')
        with self.assertRaises(aip.AcquisitionError): aip.pdf_link(html.replace(b'/official.pdf',b'https://other.cl/f.pdf'),aip.INDEX)
        with self.assertRaises(aip.AcquisitionError): aip.pdf_link(b'<a href="/f.pdf">ENR 5.2</a>',aip.INDEX)
        from urllib.request import Request
        log=[]; handler=aip.Redirects(log)
        redirected=handler.redirect_request(Request(aip.INDEX),None,302,'',{},aip.INDEX+'?redirected=1')
        self.assertEqual(redirected.full_url,aip.INDEX+'?redirected=1');self.assertEqual(len(log),1)
        with self.assertRaises(aip.AcquisitionError):handler.redirect_request(Request(aip.INDEX),None,302,'',{},'http://aipchile.dgac.gob.cl/a.pdf')

    def test_invalid_pdf_and_parser_failure_never_activate_manifest(self):
        from Infraestructura import descargar_aereo as acquisition
        import hashlib
        config=json.loads((ROOT/'config/proyecto.json').read_text())
        original=(ROOT/config['aerial_raw_directory']/'manifest.json').read_bytes()
        for payload in [b'%PDF-invalid',b'%PDF-test-parser-error']:
            with self.subTest(payload=payload),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);(folder/'manifest.json').write_bytes(original)
                cfg=dict(config,aerial_raw_directory=str(folder))
                report={}
                with self.assertRaises(aip.AcquisitionError) as raised:
                    aip.acquire(folder,box(-71.7,-33.2,-71.5,-33),report=report,
                                opener=Transport([b'<html><a href="/enr.pdf">ENR 5.1</a></html>',payload]),sleep=lambda _:None)
                self.assertEqual(raised.exception.kind,'parser');self.assertEqual(report['state'],'failed')
                self.assertEqual((folder/'manifest.json').read_bytes(),original)
        # La integración rechaza cada clase antes del reemplazo atómico, no solo el módulo aislado.
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'manifest.json').write_bytes(original)
            cfg=dict(config,aerial_raw_directory=str(folder),reuse_raw_directory=config['aerial_raw_directory'])
            # Copiar originales para la comparación contra la publicación anterior.
            import shutil
            for path in (ROOT/config['aerial_raw_directory']).iterdir():
                if path.is_file():shutil.copyfile(path,folder/path.name)
            for kind in ['dns','tls','timeout','http','content','parser']:
                with self.subTest(kind=kind),patch.object(aip,'acquire',side_effect=aip.AcquisitionError(kind,'simulated')):
                    with self.assertRaisesRegex(RuntimeError,'Fuentes incompletas'):
                        acquisition.download(cfg,{'S6'},{'S1','S1H','S2','S3','S4','S5','S7'})
                self.assertEqual(hashlib.sha256((folder/'manifest.json').read_bytes()).digest(),hashlib.sha256(original).digest())

    def test_zone_diff_additions_removals_geometry_and_attributes(self):
        from shapely.geometry import mapping
        a=dict(provider_id='A',geometry=mapping(box(0,0,1,1)),name='old')
        b=dict(a,geometry=mapping(box(0,0,2,2)),name='new')
        report=aip.zone_diff([a,dict(a,provider_id='removed')],[b,dict(b,provider_id='added')])
        self.assertEqual(report['added'],['added']);self.assertEqual(report['removed'],['removed'])
        self.assertTrue(report['changed'][0]['geometry_changed']);self.assertEqual(report['changed'][0]['attributes'],['name'])

    def test_conserved_real_pdf_validates_and_dates_are_per_page(self):
        from core.area import load_area
        from core.aerial_data import FWD, INV
        from shapely.ops import transform
        config=json.loads((ROOT/'config/proyecto.json').read_text())
        folder=ROOT/config['aerial_raw_directory']; entry=json.loads((folder/'manifest.json').read_text())['sources']['S6']
        area=transform(INV,transform(FWD,load_area(ROOT/config['aoi_geojson'])).buffer(1100,quad_segs=16))
        records,parser,pages=aip.validate_pdf(folder/entry['file'],area)
        self.assertTrue(records);self.assertEqual(len(pages),24)
        self.assertTrue(all(p['dates'] and p['amendments'] for p in pages if p['relevant']))
        self.assertGreater(len({date for page in pages for date in page['dates']}),1)
        self.assertEqual(aip.zone_diff(records,records),dict(added=[],removed=[],changed=[]))


class OracleTests(unittest.TestCase):
    def test_directed_minimum_return_equality_elapsed_and_disconnection(self):
        edges=[dict(source='a',target='b',time_s=50),dict(source='b',target='a',time_s=70),
               dict(source='a',target='c',time_s=10),dict(source='c',target='b',time_s=15)]
        self.assertEqual(shortest_time(edges,'a','b'),25)
        exact=minimum_mission(edges,'a','b','a',60,155,True)
        self.assertTrue(exact['feasible']);self.assertEqual(exact['minimum_remaining_s'],155)
        self.assertFalse(minimum_mission(edges,'a','b','a',60,154.99,True)['feasible'])
        self.assertEqual(minimum_mission(edges,'b','a','a',0,70,False)['minimum_remaining_s'],70)
        missing=minimum_mission(edges[:1],'a','b','a',60,1200,True)
        self.assertFalse(missing['feasible']);self.assertIsNone(missing['return_s'])


class DiagnosticsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_aerial import AerialIntegration
        AerialIntegration.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls): cls.conn.close()

    def test_known_minimum_matches_routing_and_remaining_budget(self):
        from core.aerial_routing import calculate
        result=calculate(self.conn,self.rid,self.request);oracle=result['diagnostics']['independent_oracle']
        self.assertTrue(oracle['routing_minimum_matches']);self.assertFalse(oracle['proposed_rejection_contradiction'])
        back=calculate(self.conn,self.rid,dict(self.request,phase='return',position=self.request['destination'],elapsed_s=300))
        oracle=back['diagnostics']['independent_oracle']
        self.assertEqual(oracle['observation_s'],0);self.assertEqual(oracle['remaining_s'],900)
        self.assertTrue(oracle['routing_minimum_matches'])

    def test_simultaneous_aip_weather_history_and_budget_are_reported(self):
        from core.aerial_routing import calculate
        base=next(b for b in self.model['records']['M1'] if b['provider_id']=='S1H:31')
        storm=next(w['valid_at'] for w in self.model['records']['M4'] if max(w['wind_speed_ms'],w['wind_gust_ms'])>=8)
        result=calculate(self.conn,self.rid,dict(self.request,origin=base['geometry']['coordinates'],time=storm,elapsed_s=1300,preferences={'max_historical_class':1}))
        codes={c['code'] for c in result['diagnostics']['causes']}
        self.assertTrue({'aip_endpoint_restriction','weather_outside_profile','budget_exhausted'}<=codes)
        self.assertEqual(result['reason'],'budget_exhausted')
        self.assertEqual(result['diagnostics']['independent_oracle']['state'],'not_tested')

    def test_missing_weather_not_claimed_infeasible_oracle(self):
        from core.aerial_routing import calculate
        result=calculate(self.conn,self.rid,dict(self.request,time='2000-01-01T00:00:00Z'))
        self.assertEqual(result['status'],'unknown')
        self.assertEqual(result['diagnostics']['independent_oracle']['state'],'not_tested')
        self.assertTrue(result['diagnostics']['not_tested'])
