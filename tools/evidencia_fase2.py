"""Exporta evidencia real de PostgreSQL, fuentes y comparación de fase 2."""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from shapely.geometry import shape, Point, LineString
from shapely.ops import transform

from core.db import connect
from core.contracts import ROOT, write_json, sha256
from core.aerial_data import FWD, iso, load_sources
from core.aerial_routing import data, map_data, calculate, available
from core.mission_evaluation import compare, save
from core.topology import audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evidencia/local/fase2")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        rid = conn.execute(
            "SELECT run_id FROM routing.publication WHERE singleton"
        ).fetchone()["run_id"]
        model, flight, nodes, edges = data(conn, rid)
        view = map_data(conn, rid)
        clock = next(
            w["valid_at"]
            for w in view["weather"]
            if available(model, iso(w["valid_at"]))[1] is None
        )
        request = dict(
            origin=view["default_origin"],
            destination=view["examples"][1]["coordinates"],
            mode="mission",
            time=clock,
            preferences=dict(budget_s=1200, wind_limit_ms=8, detour_factor=1.2),
        )
        result = compare(conn, rid, request)
        save(conn, result, args.output)
        write_json(args.output / "solicitud.json", request)
        write_json(ROOT / "datos/runs/solicitud_demo.json", request)
        write_json(args.output / "mapa.json", view)
        report = dict(
            run_id=str(rid),
            recorded_at_utc=datetime.now(timezone.utc).isoformat(),
            topology=audit(conn, rid),
            metrics=result["metrics"],
            evaluation_sha256=result["evaluation_sha256"],
            scenario_sha256=result["scenario_sha256"],
            study_area_km2=transform(FWD, shape(view["area"])).area / 1e6,
            transit_area_km2=transform(FWD, flight).area / 1e6,
            candidate_bases=view["bases"],
            catalogue_count=len(view["base_catalogue"]),
            retrospective_example=iso(clock) < iso(model["weather_fetched_at"]),
            weather_fetched_at=model["weather_fetched_at"],
            example_time=clock,
        )
        report["sql"] = conn.execute(
            """SELECT
            (SELECT count(*) FROM routing.nodes a JOIN routing.nodes b ON a.run_id=b.run_id AND a.id<b.id AND ST_Equals(a.geom,b.geom) WHERE a.run_id=%s) AS duplicate_node_geometries,
            (SELECT count(*) FROM (SELECT source,target FROM routing.edges WHERE run_id=%s GROUP BY source,target HAVING count(*)>1) t) AS duplicate_edge_pairs,
            (SELECT count(*) FROM routing.node_elevation WHERE run_id=%s) AS elevations,
            (SELECT count(*) FROM routing.base_catalogue WHERE run_id=%s AND candidate AND NOT inside_study) AS approved_external_bases,
            (SELECT count(*) FROM information_schema.tables WHERE table_schema='routing' AND table_type='BASE TABLE') AS table_count""",
            (rid, rid, rid, rid),
        ).fetchone()
        report["bases_routing"] = []
        goals = [
            n
            for n in view["features"]
            if n["geometry"]["type"] == "Point"
            and n["properties"]["kind"] == "vigilancia"
        ]
        for base in view["bases"]:
            coords = base["geometry"]["coordinates"]
            closest = min(
                goals,
                key=lambda g: Point(FWD(*coords)).distance(
                    transform(FWD, shape(g["geometry"]))
                ),
            )
            req = dict(
                request, origin=coords, destination=closest["geometry"]["coordinates"]
            )
            proposed = calculate(conn, rid, req)
            reference = calculate(conn, rid, dict(req, method="reference"))
            report["bases_routing"].append(
                dict(
                    provider_id=base["provider_id"],
                    destination=req["destination"],
                    reference=reference["status"],
                    proposed=proposed["status"],
                    reason=proposed["reason"],
                    alternatives=len(proposed["alternatives"]),
                )
            )
        config = json.loads((ROOT / "config/proyecto.json").read_text())
        manifest, _ = load_sources(config)
        report["sources"] = manifest
        report["ddl_sha256"] = {
            p.relative_to(ROOT).as_posix(): sha256(p)
            for p in [
                ROOT / "BD/crear_bd.sql",
                *sorted((ROOT / "BD/migraciones").glob("*.sql")),
            ]
        }
        report["schema"] = conn.execute(
            "SELECT table_name,column_name,data_type,udt_name FROM information_schema.columns WHERE table_schema='routing' ORDER BY table_name,ordinal_position"
        ).fetchall()
        report["constraints"] = conn.execute(
            "SELECT t.relname AS source,rt.relname AS target,co.contype AS kind,pg_get_constraintdef(co.oid) AS definition FROM pg_constraint co JOIN pg_class t ON t.oid=co.conrelid LEFT JOIN pg_class rt ON rt.oid=co.confrelid WHERE co.connamespace='routing'::regnamespace AND co.contype IN ('p','f') ORDER BY t.relname,co.conname"
        ).fetchall()
        write_json(args.output / "diagnostico.json", report)
        write_json(args.output / "software.json", result["software"])
    print(
        json.dumps(
            dict(
                run_id=str(rid),
                metrics=result["metrics"],
                sql=report["sql"],
                bases=report["bases_routing"],
            )
        )
    )


if __name__ == "__main__":
    main()
