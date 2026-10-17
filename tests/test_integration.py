"""Estas pruebas necesitan PostgreSQL + PostGIS + pgRouting reales.

main probar y GitLab CI las exigen. Sin DB configurada, unittest las omite y
lo declara; esto no se presenta como una prueba de integración aprobada.
"""
import copy
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from pathlib import Path
from uuid import UUID,uuid4

import psycopg
from psycopg import errors
from psycopg.types.json import Jsonb

from core.contracts import ROOT,prepare_snapshot,write_json
from core.db import connect,apply_schema,create_reader,apply_migrations
from core.pipeline import run,verify_counts
from core.pipeline import execute_step as real_execute_step
from core.topology import load_infrastructure,audit
from core.web import Handler


class DatabaseIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        configured=bool(os.getenv('DATABASE_URL') or os.getenv('DB_HOST'))
        if not configured:
            if os.getenv('REQUIRE_DB_TESTS')=='1':
                raise RuntimeError('Se exige una BD real y no está configurada')
            raise unittest.SkipTest('BD no configurada; ejecutar ./main probar para integración real')
        cls.conn=connect()
        cls.versions=apply_schema(cls.conn)
        cls.config=json.loads((ROOT/'config/proyecto.json').read_text())
        cls.conn.execute("INSERT INTO routing.sources(source_id,product) VALUES('DERIVED_GRAPH','fixture fase1') ON CONFLICT DO NOTHING")
        os.environ.setdefault('WEB_DB_PASSWORD','test-reader-ephemeral-only')
        create_reader(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def setUp(self):
        self.rid=uuid4();self.doc=prepare_snapshot(self.config,str(self.rid))
        self.temp=tempfile.TemporaryDirectory()
        self.file=Path(self.temp.name)/'infraestructura.json';write_json(self.file,self.doc)
        self.conn.execute("""INSERT INTO routing.runs(run_id,input_hash,scope,mode,configuration)
            VALUES(%s,%s,'base','snapshot',%s)""",(self.rid,self.doc['input_hash'],Jsonb(self.config)))

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        return load_infrastructure(self.conn,self.file)

    def publish(self):
        with self.conn.transaction():
            self.conn.execute('SELECT routing.publish_run(%s,\'base\')',(self.rid,))

    def current(self):
        row=self.conn.execute('SELECT run_id FROM routing.publication').fetchone()
        return row['run_id'] if row else None

    def test_schema_can_be_reapplied(self):
        self.assertEqual(apply_schema(self.conn)['pgrouting'],self.versions['pgrouting'])

    def test_direct_sql_can_be_applied_twice_to_empty_schema(self):
        # DDL directo también es repetible, además del control de migraciones Python.
        self.conn.execute((ROOT/'BD/crear_bd.sql').read_text(),prepare=False)
        self.conn.execute((ROOT/'BD/crear_bd.sql').read_text(),prepare=False)
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM routing.schema_migrations WHERE version=1').fetchone()['n'],1)

    def test_additional_migration_is_applied_once_and_protected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'002_prueba.sql'
            path.write_text('CREATE TABLE routing.migration_test_owned_by_test(id integer);')
            try:
                apply_migrations(self.conn,Path(folder));apply_migrations(self.conn,Path(folder))
                self.assertIsNotNone(self.conn.execute("SELECT to_regclass('routing.migration_test_owned_by_test') AS t").fetchone()['t'])
                path.write_text('SELECT 1;')
                with self.assertRaisesRegex(ValueError,'cambió'):apply_migrations(self.conn,Path(folder))
            finally:
                self.conn.execute('DROP TABLE IF EXISTS routing.migration_test_owned_by_test')
                self.conn.execute('DELETE FROM routing.schema_migrations WHERE version=2')

    def test_load_and_repeated_load(self):
        self.assertFalse(self.load()['idempotent'])
        self.assertTrue(self.load()['idempotent'])
        self.assertEqual(verify_counts(self.conn,self.rid,'base'),{'I':75})

    def test_real_geometry_and_length_in_km(self):
        self.load()
        row=self.conn.execute('''SELECT min(ST_SRID(geom)) AS srid,
            max(abs(length_km-ST_Length(geom)/1000)) AS error,min(length_km) AS min_km
            FROM routing.edges WHERE run_id=%s''',(self.rid,)).fetchone()
        self.assertEqual(row['srid'],32719);self.assertEqual(row['error'],0)
        self.assertGreater(row['min_km'],0);self.assertLess(row['min_km'],1)

    def test_generated_length_cannot_be_overwritten(self):
        self.load()
        with self.assertRaises(errors.GeneratedAlways):
            with self.conn.transaction():
                self.conn.execute('UPDATE routing.edges SET length_km=999 WHERE run_id=%s',(self.rid,))

    def test_geometry_endpoint_guard(self):
        self.load();edge=self.doc['edges'][0]
        with self.assertRaisesRegex(errors.RaiseException,'coincide'):
            with self.conn.transaction():
                self.conn.execute('UPDATE routing.edges SET geom=ST_Reverse(geom) WHERE run_id=%s AND id=%s',(self.rid,edge['id']))
                self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_node_move_invalidating_edges_is_rolled_back(self):
        self.load();node=self.doc['edges'][0]['source']
        with self.assertRaisesRegex(errors.RaiseException,'invalida'):
            with self.conn.transaction():
                self.conn.execute('UPDATE routing.nodes SET geom=ST_Translate(geom,100,0) WHERE run_id=%s AND id=%s',(self.rid,node))
                self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
        self.assertEqual(audit(self.conn,self.rid)['invalid_edges'],0)

    def test_polygon_snapshot_has_one_component_and_no_outside_geometry(self):
        self.load();report=audit(self.conn,self.rid)
        self.assertEqual((report['nodes'],report['directed_edges'],report['strong_count']),(13,62,1))
        self.assertEqual(sorted(x['size'] for x in report['strong_components']),[13])
        self.assertEqual(report['spatial']['outside_nodes'],0)
        self.assertEqual(report['spatial']['outside_edges'],0)
        self.assertEqual(report['spatial']['candidate_bases'],0)
        self.assertTrue(report['warnings'])
        self.assertEqual(report['isolated_nodes'],0)

    def test_no_dijkstra_path_after_isolating_a_source(self):
        self.load()
        source,target=self.doc['edges'][0]['source'],self.doc['edges'][0]['target']
        from psycopg import sql
        query=sql.SQL('SELECT id,source,target,length_km AS cost FROM routing.edges WHERE run_id={} AND source<>{} AND target<>{}').format(
            sql.Literal(self.rid),sql.Literal(source),sql.Literal(source)).as_string(self.conn)
        result=self.conn.execute('SELECT * FROM pgr_dijkstra(%s,%s::bigint,%s::bigint,true)',
            (query,source,target)).fetchall()
        self.assertEqual(result,[])

    def test_dijkstra_cost_equals_sum_of_lengths(self):
        self.load();report=audit(self.conn,self.rid);d=report['dijkstra_smoke']
        row=self.conn.execute('''SELECT sum(e.length_km) AS km FROM
            pgr_dijkstra(routing.edge_sql(%s),%s::bigint,%s::bigint,true) p
            JOIN routing.edges e ON e.run_id=%s AND e.id=p.edge''',
            (self.rid,d['source'],d['target'],self.rid)).fetchone()
        self.assertAlmostEqual(row['km'],d['distance_km'],places=9)

    def test_failed_complete_publication_keeps_previous_snapshot(self):
        self.load();self.publish();before=self.current()
        missing=uuid4();doc=prepare_snapshot(self.config,str(missing));path=Path(self.temp.name)/'full.json';write_json(path,doc)
        self.conn.execute("INSERT INTO routing.runs(run_id,input_hash,scope,mode,configuration) VALUES(%s,%s,'completo','snapshot','{}')",(missing,doc['input_hash']))
        load_infrastructure(self.conn,path)
        with self.assertRaisesRegex(errors.RaiseException,'faltantes'):
            with self.conn.transaction():self.conn.execute("SELECT routing.publish_run(%s,'completo')",(missing,))
        self.assertEqual(before,self.current())

    def test_failed_loader_keeps_previous_snapshot_and_marks_run_failed(self):
        self.load();self.publish();before=self.current();failed=str(uuid4())
        def fail_load(command,values,log_path):
            if 'Infraestructura.cargar' in command:
                raise RuntimeError('fallo de cargador inyectado para prueba')
            return real_execute_step(command,values,log_path)
        with patch('core.pipeline.execute_step',side_effect=fail_load):
            with self.assertRaisesRegex(RuntimeError,'inyectado'):run('base','snapshot',failed)
        self.assertEqual(before,self.current())
        row=self.conn.execute('SELECT status FROM routing.runs WHERE run_id=%s',(failed,)).fetchone()
        self.assertEqual(row['status'],'failed')

    def test_published_graph_and_run_are_immutable(self):
        self.load();self.publish()
        for statement in ["UPDATE routing.edges SET geom=ST_Translate(geom,1,0) WHERE run_id=%s",
                          "UPDATE routing.runs SET status='staging' WHERE run_id=%s",
                          "DELETE FROM routing.runs WHERE run_id=%s"]:
            with self.assertRaises(errors.RaiseException):
                with self.conn.transaction():self.conn.execute(statement,(self.rid,))

    def test_view_exposes_only_the_published_snapshot(self):
        self.load();self.publish()
        self.assertEqual(self.conn.execute('SELECT count(*) AS n FROM routing.graph_base_edges').fetchone()['n'],62)
        self.assertEqual(self.conn.execute('SELECT DISTINCT run_id FROM routing.graph_base_edges').fetchone()['run_id'],self.rid)

    def test_cross_run_references_fail(self):
        self.load();other=uuid4()
        self.conn.execute("INSERT INTO routing.runs(run_id,input_hash,scope,mode,configuration) VALUES(%s,%s,'base','snapshot','{}')",(other,'a'*64))
        self.conn.execute('''INSERT INTO routing.datasets VALUES(%s,%s,'I','DERIVED_GRAPH','1.0',now(),now(),%s,0,'empty','{}')''',(uuid4(),other,'a'*64))
        with self.assertRaises(psycopg.Error) as ctx:
            with self.conn.transaction():
                self.conn.execute('''INSERT INTO routing.edges(run_id,id,natural_key,source,target,physical_key,geom)
                    SELECT %s,id,natural_key,source,target,physical_key,geom FROM routing.edges WHERE run_id=%s LIMIT 1''',(other,self.rid))
                self.conn.execute('SET CONSTRAINTS ALL IMMEDIATE')
        self.assertIn(ctx.exception.sqlstate,('23503','P0001'))

    def test_changed_json_cannot_replace_loaded_dataset(self):
        self.load();modified=copy.deepcopy(self.doc);modified['lineage']['extra']='cambio'
        write_json(self.file,modified)
        with self.assertRaises(ValueError):load_infrastructure(self.conn,self.file)
        self.assertEqual(verify_counts(self.conn,self.rid,'base')['I'],75)

    def test_web_database_role_is_read_only(self):
        info=self.conn.info
        with psycopg.connect(host=info.host,port=info.port,dbname=info.dbname,user='routing_web',
                password=os.environ['WEB_DB_PASSWORD'],autocommit=True) as reader:
            reader.execute('SELECT count(*) FROM routing.runs').fetchone()
            with self.assertRaises(psycopg.Error) as ctx:
                reader.execute("INSERT INTO routing.sources VALUES('forbidden','x',NULL,'')")
            self.assertIn(ctx.exception.sqlstate,('25006','42501'))

    def test_full_pipeline_repeat_is_idempotent(self):
        # Dos ejecuciones completas del alcance base, incluyendo procesos ET/carga.
        a=run('base','snapshot');b=run('base','snapshot')
        self.assertEqual(a['run_id'],b['run_id']);self.assertTrue(b['idempotent'])
        self.assertEqual(b['counts'],{'I':75})

    def test_http_health_and_topology_use_published_data(self):
        self.load();self.publish()
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            root=f'http://127.0.0.1:{server.server_port}'
            with urllib.request.urlopen(root+'/health') as r:data=json.load(r)
            self.assertEqual(data['status'],'ready');self.assertFalse(data['phase2_complete'])
            with urllib.request.urlopen(root+'/api/topologia') as r:data=json.load(r)
            self.assertEqual(data['topology']['directed_edges'],62)
            self.assertFalse(data['mission_ready'])
            self.assertTrue(data['warnings'])
            with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(root+'/no-existe')
            self.assertEqual(ctx.exception.code,404)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)


if __name__=='__main__':unittest.main()
