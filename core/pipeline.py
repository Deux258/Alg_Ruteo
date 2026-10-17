"""Orquestación interna del contenedor ETL; ningún paso usa shell=True."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from core.contracts import ROOT, prepare_snapshot, write_json, validate_infrastructure
from core.db import apply_schema, connect, create_reader
from core.topology import audit

EXPECTED = ("I","M1","M2","M3","M4","A1","A2","A3","A4")
TABLES = {"M1":"base_metadata","M2":"landcover","M3":"node_elevation","M4":"weather",
          "A1":"weather_hazards","A2":"thermal_events","A3":"airspace_zones","A4":"historical_risk"}


def preflight(scope, mode, manifest=None):
    manifest = manifest or json.loads((ROOT/"config/pipeline.json").read_text())
    steps=manifest["steps"]
    keys=[s["key"] for s in steps]
    if len(keys)!=len(set(keys)) or set(keys)!=set(EXPECTED):
        raise ValueError("El manifiesto debe declarar I y M1..M4/A1..A4 una sola vez")
    needed=set(EXPECTED if scope=="completo" else ["I"])
    selected=[]
    for step in steps:
        if step["key"] not in needed:
            continue
        if not step["enabled"] or not step["extract"] or not step["load"]:
            continue
        if mode not in step["modes"]:
            raise ValueError(f"{step['key']}: modo {mode} aún no implementado")
        doc=(ROOT/step["dictionary"]).resolve()
        if not doc.is_relative_to(ROOT) or not doc.is_file():
            raise ValueError(f"Falta diccionario de {step['key']}")
        target=Path(step["output"])
        if target.is_absolute() or '..' in target.parts:
            raise ValueError("Salida debe permanecer dentro de la carpeta del run")
        for cmd in [step["extract"],step["load"]]:
            if not isinstance(cmd,list) or not all(isinstance(a,str) for a in cmd):
                raise ValueError("Comando debe ser una lista de argumentos")
        selected.append(step)
    missing=needed-{s["key"] for s in selected}
    if missing:
        raise ValueError("Alcance no implementado; faltan ET/cargadores: "+", ".join(sorted(missing)))
    ordered=[]
    pending=selected[:]
    while pending:
        available=[s for s in pending if set(s["depends_on"])<={v["key"] for v in ordered}]
        if not available:
            raise ValueError("Dependencia ausente o ciclo en pipeline")
        for step in available:
            ordered.append(step);pending.remove(step)
    return ordered


def execute_step(command, values, log_path):
    args=[arg.format(**values) for arg in command]
    started=time.monotonic()
    env=os.environ.copy()
    env["PYTHONPATH"]=str(ROOT)+os.pathsep+env.get("PYTHONPATH", "")
    env["RUN_ID"]=values["run_id"]
    env["RUN_DIRECTORY"]=str(Path(values["output"]).parents[0])
    with log_path.open("w") as log:
        result=subprocess.run(args,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600,check=False)
    if result.returncode:
        raise RuntimeError(f"Paso falló (exit {result.returncode}); revisar {log_path.relative_to(ROOT)}")
    return round(time.monotonic()-started,3)


def verify_counts(conn,rid,scope):
    rows=conn.execute("SELECT dataset_key,record_count FROM routing.datasets WHERE run_id=%s",(rid,)).fetchall()
    counts={}
    for row in rows:
        key=row["dataset_key"]
        if key=="I":
            actual=conn.execute("SELECT (SELECT count(*) FROM routing.nodes WHERE run_id=%s)+(SELECT count(*) FROM routing.edges WHERE run_id=%s) AS n",(rid,rid)).fetchone()["n"]
        else:
            # TABLES es una lista interna cerrada, nunca un nombre recibido del usuario.
            actual=conn.execute(f"SELECT count(*) AS n FROM routing.{TABLES[key]} WHERE run_id=%s",(rid,)).fetchone()["n"]
        if actual!=row["record_count"]:
            raise ValueError(f"Conteo de {key}: JSON={row['record_count']}, BD={actual}")
        counts[key]=actual
    expected=set(EXPECTED if scope=="completo" else ["I"])
    if not expected<=set(counts):
        raise ValueError("Faltan cargas registradas")
    if scope=="completo":
        nn=conn.execute("SELECT count(*) AS n FROM routing.nodes WHERE run_id=%s",(rid,)).fetchone()["n"]
        if counts["M3"]!=nn or any(counts[k]==0 for k in ["M1","M2","M4"]):
            raise ValueError("Metadata insuficiente: M3 debe cubrir nodos y M1/M2/M4 no pueden estar vacíos")
    return counts


def run(scope="base",mode="snapshot",run_id=None):
    steps=preflight(scope,mode)
    config=json.loads((ROOT/"config/proyecto.json").read_text())
    if config["analysis_srid"]!=32719:
        raise ValueError("Esta versión de SQL requiere EPSG:32719")
    # En completo los ET externos pueden cambiar: una actualización usa nuevo run.
    rid=str(UUID(run_id)) if run_id else (prepare_snapshot(config)["run_id"] if scope=="base" and mode=="snapshot" else str(uuid4()))
    initial=prepare_snapshot(config,rid) if mode=="snapshot" else None
    input_hash=initial["input_hash"] if initial else __import__('hashlib').sha256(rid.encode()).hexdigest()
    folder=ROOT/"datos/runs"/rid;folder.mkdir(parents=True,exist_ok=True)
    report={"run_id":rid,"scope":scope,"mode":mode,"steps":[],"phase2_complete":False}
    started=time.monotonic()
    with connect() as conn:
        conn.execute("SELECT pg_advisory_lock(74260103)")
        try:
            report["versions"]=apply_schema(conn)
            create_reader(conn)
            existing=conn.execute("SELECT input_hash,status,scope,mode FROM routing.runs WHERE run_id=%s",(rid,)).fetchone()
            if existing and ((initial is not None and existing["input_hash"]!=input_hash) or existing["scope"]!=scope or existing["mode"]!=mode):
                raise ValueError("run_id ya existe con otra entrada, alcance o modo")
            if existing and existing["status"]=="ready":
                if scope!="base" or mode!="snapshot":
                    raise ValueError("Run ya publicado: usar nuevo run para actualizar fuentes")
                report["idempotent"]=True
            else:
                with conn.transaction():
                    if existing:
                        # Solo staging/failed, nunca un snapshot listo ni la publicación anterior.
                        conn.execute("DELETE FROM routing.runs WHERE run_id=%s AND status<>'ready'",(rid,))
                    conn.execute("""INSERT INTO routing.runs(run_id,input_hash,scope,mode,configuration)
                        VALUES(%s,%s,%s,%s,%s)""",(rid,input_hash,scope,mode,Jsonb(config)))
                    manifest=json.loads((ROOT/"datos/entrada/fase1/manifest_fuentes.json").read_text())
                    for s in manifest["fuentes"]:
                        conn.execute("INSERT INTO routing.sources(source_id,product,url) VALUES(%s,%s,%s) ON CONFLICT(source_id) DO NOTHING",(s["id"],s["product"],s["url"]))
                    conn.execute("""INSERT INTO routing.sources(source_id,product,description)
                        VALUES('DERIVED_GRAPH','Red académica fase 1','Malla derivada S1/S2, adaptada sin pesos ni amenazas') ON CONFLICT DO NOTHING""")
                for step in steps:
                    output=folder/step["output"];output.parent.mkdir(parents=True,exist_ok=True)
                    values=dict(run_id=rid,output=str(output),root=str(ROOT),mode=mode)
                    timings={"key":step["key"]}
                    for kind in ["extract","load"]:
                        timings[kind+"_s"]=execute_step(step[kind],values,folder/f"{step['key']}_{kind}.log")
                        if kind=="extract":
                            data=json.loads(output.read_text())
                            envelope=data.get("etl",data)
                            if envelope.get("run_id")!=rid or envelope.get("dataset_key")!=step["key"]:
                                raise ValueError("Salida no identifica el run/dataset esperado")
                            if step["key"]=="I":
                                validate_infrastructure(data)
                                if mode=="online":
                                    conn.execute("UPDATE routing.runs SET input_hash=%s WHERE run_id=%s AND status='staging'",(data["input_hash"],rid))
                    report["steps"].append(timings)
            report["counts"]=verify_counts(conn,rid,scope)
            report["topology"]=audit(conn,rid)
            with conn.transaction():
                conn.execute("SELECT routing.publish_run(%s,%s)",(rid,scope))
            report["status"]="ready"
        except Exception as exc:
            report["status"]="failed";report["error"]=str(exc)
            if conn.execute("SELECT to_regclass('routing.runs') AS t").fetchone()["t"]:
                conn.execute("UPDATE routing.runs SET status='failed',finished_at=now(),error=%s WHERE run_id=%s AND status='staging'",(str(exc)[:2000],rid))
            raise
        finally:
            report["duration_s"]=round(time.monotonic()-started,3)
            report["recorded_at_utc"]=datetime.now(timezone.utc).isoformat()
            write_json(folder/"resumen.json",report)
            conn.execute("SELECT pg_advisory_unlock(74260103)")
    print(json.dumps(report,ensure_ascii=False,default=str))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["run","preflight"])
    parser.add_argument("--scope",choices=["base","completo"],default="base")
    parser.add_argument("--mode",choices=["snapshot","online"],default="snapshot")
    parser.add_argument("--run-id")
    args=parser.parse_args()
    try:
        if args.action=="preflight":
            print(json.dumps({"steps":[s["key"] for s in preflight(args.scope,args.mode)]}))
        else:
            run(args.scope,args.mode,args.run_id)
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
