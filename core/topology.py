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
            cur.executemany("""INSERT INTO routing.edges(run_id,id,natural_key,source,target,physical_key,geom,road_origin)
                VALUES(%s,%s,%s,%s,%s,%s,ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32719),%s)""",
                [(rid,e["id"],e["natural_key"],e["source"],e["target"],e["physical_key"],json.dumps(e["geometry"]),Jsonb(e.get('osm',[]))) for e in doc["edges"]])
        if doc['schema_version']=='2.0':
            from core.turns import state_graph
            base=doc['lineage']['base']
            conn.execute("""INSERT INTO routing.base_locations(run_id,provider_id,source_id,node_id,name,address,geom,provenance)
                VALUES(%s,%s,%s,%s,%s,%s,ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32719),%s)""",
                (rid,base['provider_id'],base['source_id'],base['routing_node_id'],base['name'],base['address'],json.dumps(base['geometry']),Jsonb(base)))
            states,transitions=state_graph(doc['edges'],doc['lineage']['turn_restrictions']['forbidden_paths'])
            with conn.cursor() as cur:
                with cur.copy('COPY routing.road_states(run_id,id,edge_id,context) FROM STDIN') as stream:
                    for state in states:stream.write_row((rid,state['id'],state['edge_id'],state['context']))
                with cur.copy('COPY routing.road_transitions(run_id,id,source,target,edge_id) FROM STDIN') as stream:
                    for transition in transitions:stream.write_row((rid,transition['id'],transition['source'],transition['target'],transition['edge_id']))
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")
        if doc['schema_version']=='2.0':
            # El grafo crece varios órdenes de magnitud respecto de la malla
            # legada. Las consultas de validación necesitan estadísticas actuales.
            for table in ['nodes','edges','road_states','road_transitions']:
                conn.execute('ANALYZE routing.'+table)
        if doc['schema_version']=='3.0':
            from core.aerial_data import build
            config=conn.execute('SELECT configuration FROM routing.runs WHERE run_id=%s',(rid,)).fetchone()['configuration']
            context=build(config,str(rid),doc['extraction_mode'])[1]
            conn.execute('INSERT INTO routing.aerial_models(run_id,profile,context) VALUES(%s,%s,%s)',(rid,Jsonb(context['profile']),Jsonb(context)))
            conn.execute('ANALYZE routing.nodes');conn.execute('ANALYZE routing.edges')
    return {"idempotent": False, "nodes":len(doc["nodes"]), "edges":len(doc["edges"])}


def audit(conn, rid):
    report = conn.execute("SELECT routing.topology_report(%s) AS report",(UUID(str(rid)),)).fetchone()["report"]
    area = conn.execute("SELECT lineage#>'{aoi,geometry}' AS geometry FROM routing.datasets WHERE run_id=%s AND dataset_key='I'", (rid,)).fetchone()
    if not area or not area["geometry"]:
        raise ValueError("Falta el polígono de estudio en el linaje")
    report["spatial"] = conn.execute("""WITH a AS (
        SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) AS geom)
        SELECT (SELECT count(*) FROM routing.nodes n CROSS JOIN a
                WHERE run_id=%s AND NOT ST_Covers(a.geom,ST_Transform(n.geom,4326))) AS outside_nodes,
               (SELECT count(*) FROM routing.edges e CROSS JOIN a
                WHERE run_id=%s AND NOT ST_Covers(a.geom,ST_Transform(e.geom,4326))) AS outside_edges,
               (SELECT count(*) FROM routing.nodes WHERE run_id=%s AND kind='base_candidata') AS candidate_bases,
               ST_Area(ST_Transform(a.geom,32719))/1e6 AS area_km2 FROM a""",
        (json.dumps(area["geometry"]),rid,rid,rid)).fetchone()
    if report["spatial"]["outside_nodes"] or report["spatial"]["outside_edges"]:
        raise ValueError("Infraestructura fuera del polígono de estudio")
    report["warnings"] = [] if report["spatial"]["candidate_bases"] else [
        "Sin bases candidatas en el recorte; no permite demostrar una misión desde una base"]
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
    if conn.execute('SELECT 1 FROM routing.base_locations WHERE run_id=%s',(rid,)).fetchone():
        from core.routing import audit_roads
        report['road_routing']=audit_roads(conn,rid)
    return report
