"""Evidencia de fuentes, reglas y SQL real. Ejecutar con rol ETL dentro de Docker."""

import argparse
import hashlib
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from shapely.geometry import Point, LineString, box, mapping
from shapely.ops import transform

from core.aerial_data import FWD, INV, iso
from core.aerial_routing import (
    data,
    map_data,
    available,
    edge_time,
    historical_policy,
    model_from_text,
)
from core.contracts import ROOT, write_json, sha256
from core.db import connect
from core.mission_evaluation import compare, save
from core.provenance import software_manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        rid = conn.execute(
            "SELECT run_id FROM routing.publication WHERE singleton"
        ).fetchone()["run_id"]
        model, area, nodes, edges = data(conn, rid)
        view = map_data(conn, rid)
        clocks = [
            w["valid_at"]
            for w in model["records"]["M4"]
            if iso(w["valid_at"]) >= iso(model["weather_fetched_at"])
            and available(model, iso(w["valid_at"]))[1] is None
        ]
        if not clocks:
            raise ValueError(
                "No hay hora postadquisición admisible para demostración; no se inventa un pronóstico"
            )
        req = dict(
            origin=view["default_origin"],
            destination=view["examples"][1]["coordinates"],
            time=clocks[0],
            mode="mission",
        )
        comparison = compare(conn, rid, req)
        save(conn, comparison, out)
        write_json(out / "solicitud.json", req)
        write_json(out / "mapa.json", view)
        write_json(out / "software.json", software_manifest())
        examples = {}
        for step in json.loads((ROOT / "config/pipeline_aereo.json").read_text())[
            "steps"
        ]:
            path = ROOT / "datos/runs" / str(rid) / step["output"]
            doc = json.loads(path.read_text())
            sample = {
                k: doc[k]
                for k in [
                    "schema_version",
                    "dataset_key",
                    "run_id",
                    "source_id",
                    "observed_at",
                ]
            }
            if step["key"] == "I":
                sample.update(nodes=doc["nodes"][:1], edges=doc["edges"][:1])
            else:
                sample["records"] = doc["records"][:1]
            examples[step["key"]] = dict(
                sample=sample,
                original_packet_sha256=sha256(path),
                count=len(doc.get("records", doc.get("nodes", [])))
                + len(doc.get("edges", [])),
                extract=step["extract"],
                load=step["load"],
                dictionary=step["dictionary"],
                output=step["output"],
                lineage=doc["lineage"],
            )
        write_json(out / "json_examples.json", examples)
        schema = conn.execute(
            "SELECT table_name,column_name,data_type,udt_name FROM information_schema.columns WHERE table_schema='routing' AND table_name IN (SELECT table_name FROM information_schema.tables WHERE table_schema='routing' AND table_type='BASE TABLE') ORDER BY table_name,ordinal_position"
        ).fetchall()
        constraints = conn.execute(
            "SELECT t.relname AS source,rt.relname AS target,co.contype AS kind,pg_get_constraintdef(co.oid) AS definition FROM pg_constraint co JOIN pg_class t ON t.oid=co.conrelid LEFT JOIN pg_class rt ON rt.oid=co.confrelid WHERE co.connamespace='routing'::regnamespace AND co.contype IN ('p','f') ORDER BY t.relname,co.conname"
        ).fetchall()
        write_json(out / "schema.json", dict(schema=schema, constraints=constraints))
        # Consulta base sin filtros; SQL listo para ejecutar sobre el mismo snapshot.
        source = next(b["node_id"] for b in view["bases"] if b["provider_id"] == "104")
        target = view["examples"][1]["id"]
        edge_sql = f"SELECT id,source,target,length_km AS cost,-1::float8 AS reverse_cost FROM routing.edges WHERE run_id='{rid}'::uuid"
        sql = f"SELECT seq,path_seq,node,edge,cost,agg_cost FROM pgr_dijkstra('{edge_sql.replace(chr(39),chr(39)*2)}',{int(source)}::bigint,{int(target)}::bigint,true) ORDER BY path_seq;\n"
        (out / "dijkstra.sql").write_text(sql, encoding="utf-8")
        write_json(out / "dijkstra_result.json", conn.execute(sql).fetchall())
        # Ejemplo pedagógico aislado: no altera fuentes ni BD y se declara sintético.
        line = LineString([(300000, 6330000), (301000, 6330000)])
        calm = dict(wind_direction_deg=270, wind_speed_ms=0)
        head = dict(wind_direction_deg=90, wind_speed_ms=2)
        hmodel = dict(
            profile=dict(max_historical_class=4),
            history=[(box(299999, 6329999, 301001, 6330001), 1)],
        )
        write_json(
            out / "segment_examples.json",
            dict(
                synthetic=True,
                crs="EPSG:32719",
                line=mapping(line),
                length_m=line.length,
                weather=dict(
                    before_s=edge_time(line, calm, model["profile"]),
                    after_s=edge_time(line, head, model["profile"]),
                    excluded_when_gust_ms=8,
                ),
                firms=dict(
                    buffer_m=250,
                    before_intersects=False,
                    after_intersects=line.intersects(
                        Point(300500, 6330000).buffer(250)
                    ),
                ),
                aip=dict(
                    synthetic=True,
                    before_intersects=False,
                    after_intersects=line.intersects(
                        box(300400, 6329900, 300600, 6330100)
                    ),
                ),
                history=dict(
                    ordinal_class=5,
                    max_historical_class=4,
                    reason=historical_policy(line, hmodel),
                ),
                warning="Fixture sintético de reglas, separado de las cero detecciones FIRMS reales; no es un cierre observado",
            ),
        )
        manifest = json.loads(
            (ROOT / "datos/entrada/aereo_v2/manifest.json").read_text()
        )
        url = manifest["sources"]["S6"]["url"]
        host = urlsplit(url).hostname
        dns = dict(
            recorded_at_utc=datetime.now(timezone.utc).isoformat(),
            host=host,
            source_url=url,
        )
        try:
            dns.update(
                status="resolved",
                addresses=sorted({r[4][0] for r in socket.getaddrinfo(host, 443)}),
            )
        except OSError as exc:
            dns.update(status="dns_error", error=str(exc))
        write_json(out / "dgac_dns.json", dns)
        print(
            json.dumps(
                dict(
                    run_id=str(rid),
                    time=clocks[0],
                    metrics=comparison["metrics"],
                    dns=dns["status"],
                )
            )
        )


if __name__ == "__main__":
    main()
