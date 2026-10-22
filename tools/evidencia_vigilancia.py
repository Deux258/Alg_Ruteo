"""Consolida conteos, versiones y hashes de una publicación realmente activa."""
import argparse
from pathlib import Path
from datetime import datetime, timezone
from core.contracts import ROOT,write_json
from core.db import connect
from core.provenance import software_manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'evidencia/vigilancia_2026-10-22')
    args=parser.parse_args()
    with connect() as conn:
        row=conn.execute('SELECT r.* FROM routing.patrol_runs r JOIN routing.patrol_publication p ON p.run_id=r.id WHERE p.singleton').fetchone()
        if not row:raise ValueError('No hay publicación de vigilancia')
        rid=str(row['id']);datasets=[]
        for d in conn.execute('SELECT key,document FROM routing.patrol_datasets WHERE run_id=%s ORDER BY key',(rid,)):
            doc=d['document'];records=doc.get('records');datasets.append(dict(key=d['key'],records=len(records) if isinstance(records,list) else doc.get('records_summary'),records_sha256=doc['records_sha256']))
        obstacles=conn.execute('SELECT count(*) AS count,count(height_m) AS with_height FROM routing.flight_obstacles WHERE run_id=%s',(rid,)).fetchone()
        versions=conn.execute('SELECT version() AS postgres,postgis_full_version() AS postgis,pgr_version() AS pgrouting').fetchone()
        schema=conn.execute("SELECT count(*) AS n FROM information_schema.tables WHERE table_schema='routing' AND table_type='BASE TABLE'").fetchone()['n']
        legacy=str(conn.execute('SELECT run_id FROM routing.publication WHERE singleton').fetchone()['run_id'])
    report=dict(run_id=rid,base_run_id=str(row['base_run_id']),legacy_publication=legacy,status=row['status'],
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),input_hash=row['input_hash'],counts=row['context']['counts'],
        profile=row['profile'],datasets=datasets,obstacles=obstacles,database_versions=versions,schema_tables=schema,
        source_manifest=row['context']['source_manifest'],construction_code=row['context']['construction_code'],software=software_manifest())
    args.output.mkdir(parents=True,exist_ok=True);write_json(args.output/'publicacion.json',report)
    print({k:v for k,v in report.items() if k in ['run_id','counts','obstacles','schema_tables','status']})


if __name__=='__main__':main()
