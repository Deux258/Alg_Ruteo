"""Captura verificaciones de la BD publicada; ejecutar en el contenedor ETL.

python -m tools.capturar_evidencia_vial --output evidencia/local
No modifica ni publica datos. Los IDs de evidencia se serializan como texto.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from core.contracts import write_json
from core.db import connect
from core.routing import base_info, reachable_nodes, route, map_data
from core.web import safe_numbers
from core.roads import read_sources
from psycopg.types.json import Jsonb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        rid = conn.execute(
            "SELECT run_id FROM routing.publication WHERE singleton"
        ).fetchone()["run_id"]
        dataset = conn.execute(
            "SELECT file_sha256,lineage,validation FROM routing.datasets WHERE run_id=%s AND dataset_key='I'",
            (rid,),
        ).fetchone()
        b = base_info(conn, rid)
        reachable = {r["id"] for r in reachable_nodes(conn, rid, b["node_id"])}
        target = next(
            r["id"]
            for r in conn.execute(
                "SELECT id FROM routing.nodes WHERE run_id=%s ORDER BY id", (rid,)
            )
            if r["id"] not in reachable
        )
        try:
            route(conn, rid, target)
        except ValueError as exc:
            rejection = str(exc)
        else:
            raise RuntimeError("Se aceptó un destino inalcanzable")
        report = dict(
            recorded_at_utc=datetime.now(timezone.utc).isoformat(),
            run_id=str(rid),
            dataset_sha256=dataset["file_sha256"],
            versions=conn.execute(
                "SELECT version() AS postgres,postgis_full_version() AS postgis,pgr_version() AS pgrouting"
            ).fetchone(),
            table_count=conn.execute(
                "SELECT count(*) AS n FROM information_schema.tables WHERE table_schema='routing' AND table_type='BASE TABLE'"
            ).fetchone()["n"],
            duplicates=conn.execute(
                """SELECT count(*)-count(DISTINCT id) AS node_ids,
                count(*)-count(DISTINCT natural_key) AS node_keys FROM routing.nodes WHERE run_id=%s""",
                (rid,),
            ).fetchone(),
            duplicate_arcs=conn.execute(
                """SELECT count(*)-count(DISTINCT id) AS ids,
                count(*)-count(DISTINCT(source,target)) AS pairs FROM routing.edges WHERE run_id=%s""",
                (rid,),
            ).fetchone(),
            turn_restrictions=dataset["lineage"]["turn_restrictions"],
            spatial_filter=dataset["lineage"]["spatial_filter"],
            validation=dataset["validation"],
            unreachable_example=dict(target=str(target), message=rejection),
            base=b,
        )
        config = conn.execute(
            "SELECT configuration FROM routing.runs WHERE run_id=%s", (rid,)
        ).fetchone()["configuration"]
        manifest, originals, _ = read_sources(config)
        candidates = []
        for source, id_field, name_field in [
            ("senapred", "objectid_1", "nombre"),
            ("senapred_carabineros", "objectid", "nombre_uni"),
        ]:
            for f in originals[source]["features"]:
                inside = conn.execute(
                    """SELECT ST_Covers(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),
                    ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)) AS yes""",
                    (
                        Jsonb(dataset["lineage"]["aoi"]["geometry"]),
                        Jsonb(f["geometry"]),
                    ),
                ).fetchone()["yes"]
                if not inside:
                    continue
                nearest = conn.execute(
                    """WITH p AS (SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32719) AS geom)
                    SELECT n.id,ST_Distance(n.geom,p.geom) AS offset_m FROM routing.nodes n CROSS JOIN p
                    WHERE run_id=%s ORDER BY n.geom<->p.geom,n.id LIMIT 1""",
                    (Jsonb(f["geometry"]), rid),
                ).fetchone()
                reached = (
                    reachable_nodes(conn, rid, nearest["id"])
                    if nearest["offset_m"] <= 30
                    else []
                )
                candidates.append(
                    dict(
                        source=source,
                        provider_id=str(f["properties"][id_field]),
                        name=f["properties"][name_field],
                        geometry=f["geometry"],
                        inside=True,
                        road_node_id=str(nearest["id"]),
                        offset_m=nearest["offset_m"],
                        reachable_nodes=len(reached),
                        maximum_distance_km=max(
                            (r["distance_km"] for r in reached), default=0
                        ),
                        selected=source == dataset["lineage"]["base"]["raw_source"]
                        and str(f["properties"][id_field]) == b["provider_id"],
                        source_sha256=manifest["sources"][source]["sha256"],
                    )
                )
        write_json(
            args.output / "evaluacion_bases.json",
            safe_numbers(
                dict(
                    run_id=str(rid),
                    candidates=candidates,
                    criterion="inside AOI; existing road node <=30 m; >=1000 reachable nodes; identity corroborated separately",
                )
            ),
        )
        write_json(args.output / "validacion_bd.json", safe_numbers(report))
        for number, example in enumerate(
            dataset["validation"]["road_routing"]["examples"], 1
        ):
            path = route(conn, rid, int(example["target"]))
            path["properties"]["label"] = example["label"]
            write_json(args.output / f"ruta_{number}.geojson", safe_numbers(path))
        write_json(
            args.output / "mapa_datos.geojson", safe_numbers(map_data(conn, rid))
        )
        write_json(
            args.output / "base.geojson",
            dict(
                type="FeatureCollection",
                features=[
                    dict(
                        type="Feature",
                        geometry=b["geometry"],
                        properties=dict(
                            role="real_facility",
                            provider_id=b["provider_id"],
                            name=b["name"],
                            source="SENAPRED CARABINEROS",
                        ),
                    ),
                    dict(
                        type="Feature",
                        geometry=b["road_origin"],
                        properties=dict(
                            role="routing_origin",
                            osm_node_id=str(b["provenance"]["osm_node_id"]),
                            node_id=str(b["node_id"]),
                            offset_m=b["road_offset_m"],
                            access_modelled=False,
                        ),
                    ),
                ],
            ),
        )
    print(f"Evidencia capturada en {args.output}; run {rid}")


if __name__ == "__main__":
    main()
