"""Contrasta el snapshot legado con un AOI real usando PostGIS, sin modificarlo."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from core.contracts import ROOT, sha256, write_json
from core.db import connect


def read_aoi(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    crs = doc.get("crs", {}).get("properties", {}).get("name", "EPSG:4326")
    if crs not in ("EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84", "urn:ogc:def:crs:EPSG::4326"):
        raise ValueError("El AOI debe estar en WGS84 [longitud, latitud]")
    if doc.get("type") != "FeatureCollection" or not doc.get("features"):
        raise ValueError("El AOI debe ser una FeatureCollection no vacía")
    geometries = [f.get("geometry") for f in doc["features"]]
    if any(not g or g.get("type") not in ("Polygon", "MultiPolygon") for g in geometries):
        raise ValueError("El AOI solo admite Polygon/MultiPolygon")
    return {"type": "GeometryCollection", "geometries": geometries}


def spatial_report(conn, aoi, nodes, edges, bbox):
    """Covers incluye el borde; evalúa cada LineString completa, sin buffers."""
    geometry = json.dumps(aoi)
    validity = conn.execute("""SELECT ST_IsValid(g) AS valid, ST_IsValidReason(g) AS reason,
        ST_IsEmpty(g) AS empty FROM (SELECT ST_SetSRID(ST_GeomFromGeoJSON(%s),4326) AS g) s""",
        (geometry,)).fetchone()
    if not validity["valid"] or validity["empty"]:
        raise ValueError("AOI inválido o vacío: " + validity["reason"])
    report = conn.execute("""
        WITH a AS (SELECT ST_UnaryUnion(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)) AS geom),
        b AS (SELECT ST_MakeEnvelope(%s,%s,%s,%s,4326) AS geom),
        n AS (SELECT (f#>>'{properties,id}')::bigint AS id,
                     f#>>'{properties,tipo}' AS kind,
                     ST_SetSRID(ST_GeomFromGeoJSON((f->'geometry')::text),4326) AS geom
              FROM jsonb_array_elements(%s::jsonb->'features') f),
        e AS (SELECT (f#>>'{properties,origen}') || '->' || (f#>>'{properties,destino}') AS id,
                     (f#>>'{properties,origen}')::bigint AS source,
                     (f#>>'{properties,destino}')::bigint AS target,
                     ST_SetSRID(ST_GeomFromGeoJSON((f->'geometry')::text),4326) AS geom
              FROM jsonb_array_elements(%s::jsonb->'features') f),
        nc AS (SELECT n.*,ST_Covers(a.geom,n.geom) AS covered FROM n CROSS JOIN a),
        ec AS (SELECT e.*,ST_Covers(a.geom,e.geom) AS covered,
                      s.covered AND t.covered AS endpoints_covered
               FROM e CROSS JOIN a JOIN nc s ON s.id=e.source JOIN nc t ON t.id=e.target)
        SELECT jsonb_build_object(
          'aoi',jsonb_build_object('valid',true,'srid',4326,
              'bounds',jsonb_build_array(ST_XMin(a.geom),ST_YMin(a.geom),ST_XMax(a.geom),ST_YMax(a.geom)),
              'area_km2',ST_Area(ST_Transform(a.geom,32719))/1e6,
              'legacy_bbox_area_km2',ST_Area(ST_Transform(b.geom,32719))/1e6,
              'intersection_km2',ST_Area(ST_Intersection(ST_Transform(a.geom,32719),ST_Transform(b.geom,32719)))/1e6),
          'nodes',jsonb_build_object('total',(SELECT count(*) FROM nc),
              'inside',(SELECT count(*) FROM nc WHERE covered),
              'outside',(SELECT count(*) FROM nc WHERE NOT covered),
              'bases_total',(SELECT count(*) FROM nc WHERE kind='base_candidata'),
              'bases_inside',(SELECT count(*) FROM nc WHERE covered AND kind='base_candidata'),
              'outside_ids',COALESCE((SELECT jsonb_agg(id ORDER BY id) FROM nc WHERE NOT covered),'[]')),
          'edges',jsonb_build_object('total',(SELECT count(*) FROM ec),
              'fully_inside',(SELECT count(*) FROM ec WHERE covered),
              'not_fully_inside',(SELECT count(*) FROM ec WHERE NOT covered),
              'both_endpoints_inside',(SELECT count(*) FROM ec WHERE endpoints_covered),
              'exit_with_endpoints_inside',(SELECT count(*) FROM ec WHERE endpoints_covered AND NOT covered),
              'outside_ids',COALESCE((SELECT jsonb_agg(id ORDER BY id) FROM ec WHERE NOT covered),'[]'))
        ) AS report FROM a CROSS JOIN b
        """, (geometry, *bbox, json.dumps(nodes), json.dumps(edges))).fetchone()["report"]
    report["delimitation_matches"] = report["nodes"]["outside"] == 0 and report["edges"]["not_fully_inside"] == 0
    report["warnings"] = []
    if not report["delimitation_matches"]:
        report["warnings"].append("El snapshot no respeta el polígono suministrado")
    if not report["nodes"]["bases_inside"]:
        report["warnings"].append("No queda ninguna base candidata: recortar no permite demostrar una misión desde una base")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", type=Path, default=ROOT/"datos/entrada/aoi/Zona_Delimitada_Valpo.geojson")
    parser.add_argument("--output", type=Path, default=ROOT/"evidencia/local/delimitacion.json")
    parser.add_argument("--require-match", action="store_true", help="Retorna 2 si hay datos fuera del polígono")
    parser.add_argument("--dataset", type=Path, help="Audita infraestructura.json en vez de los originales de fase 1")
    args = parser.parse_args()
    config = json.loads((ROOT/"config/proyecto.json").read_text(encoding="utf-8"))
    folder = ROOT/config["snapshot_directory"]
    paths = {"nodes": folder/"nodos.geojson", "edges": folder/"aristas.geojson", "aoi": args.aoi}
    nodes = json.loads(paths["nodes"].read_text(encoding="utf-8"))
    edges = json.loads(paths["edges"].read_text(encoding="utf-8"))
    if args.dataset:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        nodes = {"features": [{"geometry": n["geometry"], "properties": {"id": n["id"], "tipo": n["kind"]}}
                              for n in dataset["nodes"]]}
        edges = {"features": [{"geometry": e["geometry"], "properties": {"origen": e["source"], "destino": e["target"]}}
                              for e in dataset["edges"]]}
        paths = {"dataset": args.dataset, "aoi": args.aoi}
    aoi = read_aoi(args.aoi)
    with connect() as conn:
        report = spatial_report(conn, aoi, nodes, edges, config.get("legacy_bbox_wgs84", config["bbox_wgs84"]))
        report["postgis_version"] = conn.execute("SELECT postgis_full_version() AS version").fetchone()["version"]
    report["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["files_sha256"] = {k: sha256(p) for k, p in paths.items()}
    report["predicate"] = "ST_Covers(AOI, geometry) en EPSG:4326, borde incluido, sin buffer"
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False))
    return 2 if args.require_match and not report["delimitation_matches"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
