"""Orquesta nueve salidas sin alterar el orquestador vial legado."""
import json
import time
from datetime import datetime,timezone
from uuid import UUID,uuid5
from psycopg.types.json import Jsonb

from core.contracts import ROOT,write_json,prepare_snapshot
from core.db import connect,apply_schema,create_reader
from core.topology import audit


def run(scope,mode,run_id=None):
    from core import pipeline
    config=json.loads((ROOT/'config/proyecto.json').read_text())
    steps=pipeline.preflight(scope,mode,json.loads((ROOT/'config/pipeline_aereo.json').read_text()))
    if mode=='online':
        from Infraestructura.descargar_aereo import download
        download(config)
    initial=prepare_snapshot(config,extraction_mode=mode)
    rid=str(UUID(run_id)) if run_id else str(uuid5(UUID(initial['run_id']),scope))
    initial=prepare_snapshot(config,rid,mode)
    folder=ROOT/'datos/runs'/rid;folder.mkdir(parents=True,exist_ok=True)
    report=dict(run_id=rid,scope=scope,mode=mode,steps=[],phase2_complete=False,etl_complete=False);start=time.monotonic()
    with connect() as conn:
        conn.execute('SELECT pg_advisory_lock(74260103)')
        try:
            report['versions']=apply_schema(conn);create_reader(conn)
            existing=conn.execute('SELECT status,input_hash,scope,mode FROM routing.runs WHERE run_id=%s',(rid,)).fetchone()
            if existing and any(existing[k]!=v for k,v in [('input_hash',initial['input_hash']),('scope',scope),('mode',mode)]):raise ValueError('run_id incompatible')
            if existing and existing['status']=='ready':report['idempotent']=True
            else:
                with conn.transaction():
                    if existing:conn.execute("DELETE FROM routing.runs WHERE run_id=%s AND status<>'ready'",(rid,))
                    conn.execute('INSERT INTO routing.runs(run_id,input_hash,scope,mode,configuration) VALUES(%s,%s,%s,%s,%s)',(rid,initial['input_hash'],scope,mode,Jsonb(config)))
                    for key,s in initial['lineage']['sources'].items():
                        url=s.get('url',s.get('ids',{}).get('url'))
                        conn.execute('INSERT INTO routing.sources(source_id,product,url) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(key,s['product'],url))
                    conn.execute("INSERT INTO routing.sources(source_id,product) VALUES('DERIVED_AERIAL','Malla aérea académica derivada de S1-S7') ON CONFLICT DO NOTHING")
                for step in steps:
                    output=folder/step['output'];output.parent.mkdir(parents=True,exist_ok=True)
                    timing={'key':step['key']};values=dict(run_id=rid,output=str(output),root=str(ROOT),mode=mode)
                    for kind in ['extract','load']:timing[kind+'_s']=pipeline.execute_step(step[kind],values,folder/f"{step['key']}_{kind}.log")
                    report['steps'].append(timing)
            report['counts']=pipeline.verify_counts(conn,rid,scope);report['topology']=audit(conn,rid)
            from core.aerial_routing import audit_aerial
            report['aerial']=audit_aerial(conn,rid)
            with conn.transaction():
                conn.execute("UPDATE routing.datasets SET validation=%s WHERE run_id=%s AND dataset_key='I' AND EXISTS(SELECT 1 FROM routing.runs WHERE run_id=%s AND status='staging')",(Jsonb(dict(**report['topology'],aerial=report['aerial'])),rid,rid))
                conn.execute('SELECT routing.publish_run(%s,%s)',(rid,scope))
            report.update(status='ready',etl_complete=scope=='completo')
        except Exception as exc:
            report.update(status='failed',error=str(exc))
            conn.execute("UPDATE routing.runs SET status='failed',finished_at=now(),error=%s WHERE run_id=%s AND status='staging'",(str(exc)[:2000],rid));raise
        finally:
            report.update(duration_s=round(time.monotonic()-start,3),recorded_at_utc=datetime.now(timezone.utc).isoformat())
            write_json(folder/'resumen.json',report);conn.execute('SELECT pg_advisory_unlock(74260103)')
    print(json.dumps({k:v for k,v in report.items() if k not in ['versions','topology']},ensure_ascii=False));return report
