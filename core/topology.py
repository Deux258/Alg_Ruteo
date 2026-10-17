"""Carga transaccional de la topología; las longitudes las calcula PostGIS."""
import json
from uuid import UUID

from psycopg.types.json import Jsonb

from core.contracts import canonical, sha256, validate_infrastructure


def load_infrastructure(conn, path):
    doc = validate_infrastructure(json.loads(path.read_text()))
    rid = UUID(doc["run_id"])
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(74260104)")
        run = conn.execute("SELECT status,input_hash,mode FROM routing.runs WHERE run_id=%s FOR UPDATE", (rid,)).fetchone()
        if not run or run["input_hash"] != doc["input_hash"]:
            raise ValueError("run no registrado o hash de entrada incompatible")
        if run["mode"] != doc["extraction_mode"]:
            raise ValueError("Modo de adquisición no corresponde al run")
        existing = conn.execute("SELECT file_sha256 FROM routing.datasets WHERE run_id=%s AND dataset_key='I'",(rid,)).fetchone()
        if existing:
            if existing["file_sha256"] != sha256(path):
                raise ValueError("No se permite reemplazar un dataset con bytes diferentes dentro del mismo run")
            return {"idempotent": True, "nodes":len(doc["nodes"]), "edges":len(doc["edges"])}
        if run["status"] != "staging":
            raise ValueError("La carga requiere run staging")
        conn.execute("""INSERT INTO routing.datasets(dataset_id,run_id,dataset_key,source_id,schema_version,
            observed_at,extracted_at,file_sha256,record_count,status,lineage)
            VALUES(%s,%s,'I',%s,%s,%s,%s,%s,%s,'valid',%s)""",
            (UUID(doc["dataset_id"]),rid,doc["source_id"],doc["schema_version"],doc["observed_at"],doc["extracted_at"],
             sha256(path),len(doc["nodes"])+len(doc["edges"]),Jsonb(doc["lineage"])))
        with conn.cursor() as cur:
            cur.executemany("""INSERT INTO routing.nodes(run_id,id,natural_key,kind,source_record_id,geom)
                VALUES(%s,%s,%s,%s,%s,ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32719))""",
                [(rid,n["id"],n["natural_key"],n["kind"],n["source_record_id"],json.dumps(n["geometry"])) for n in doc["nodes"]])
            cur.executemany("""INSERT INTO routing.edges(run_id,id,natural_key,source,target,physical_key,geom)
                VALUES(%s,%s,%s,%s,%s,%s,ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32719))""",
                [(rid,e["id"],e["natural_key"],e["source"],e["target"],e["physical_key"],json.dumps(e["geometry"])) for e in doc["edges"]])
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
    return {"idempotent": False, "nodes":len(doc["nodes"]), "edges":len(doc["edges"])}


def audit(conn, rid):
    report = conn.execute("SELECT routing.topology_report(%s) AS report",(UUID(str(rid)),)).fetchone()["report"]
    report["invalid_edges"] = conn.execute("""SELECT count(*) AS n FROM routing.edges e
        JOIN routing.nodes a ON (a.run_id,a.id)=(e.run_id,e.source)
        JOIN routing.nodes b ON (b.run_id,b.id)=(e.run_id,e.target)
        WHERE e.run_id=%s AND (NOT ST_DWithin(ST_StartPoint(e.geom),a.geom,0.001)
          OR NOT ST_DWithin(ST_EndPoint(e.geom),b.geom,0.001) OR e.length_km<=0)""",(rid,)).fetchone()["n"]
    if report["invalid_edges"] or report["isolated_nodes"]:
        raise ValueError("Auditoría topológica falló: " + json.dumps(report))
    sample = conn.execute("SELECT source,target,length_km FROM routing.edges WHERE run_id=%s ORDER BY id LIMIT 1",(rid,)).fetchone()
    if not sample:
        raise ValueError("No hay arcos para prueba de ruteo")
    result = conn.execute("""SELECT path_seq,node,edge,cost,agg_cost FROM pgr_dijkstra(routing.edge_sql(%s),%s::bigint,%s::bigint,true)
        ORDER BY path_seq""",(rid,sample["source"],sample["target"])).fetchall()
    if not result or result[-1]["edge"] != -1 or result[-1]["agg_cost"] <= 0:
        raise ValueError("Prueba pgr_dijkstra sin resultado válido")
    report["dijkstra_smoke"] = {"source":sample["source"],"target":sample["target"],
                                 "distance_km":result[-1]["agg_cost"],"steps":len(result)-1}
    return report
