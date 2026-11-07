"""Sequential cold/warm preparation comparison on an isolated database."""
import argparse
import json
import os
import statistics
import time
from pathlib import Path
from shapely.affinity import translate
from shapely.geometry import shape, mapping
from shapely.ops import transform

from core.aerial_data import FWD, INV
from core.contracts import write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='evidencia/local/benchmark.json')
    args=parser.parse_args()
    if os.getenv('DB_HOST')!='dbtest' or os.getenv('DB_NAME')!='ruteo_test' or os.getenv('DATABASE_URL'):
        raise RuntimeError('Benchmark requiere base desechable dbtest/ruteo_test')
    from core.db import connect
    from core.patrol import map_data, calculate
    from core.provenance import software_manifest
    with connect() as conn:
        row=conn.execute('SELECT run_id FROM routing.publication WHERE singleton').fetchone()
        model=conn.execute('SELECT context FROM routing.aerial_models WHERE run_id=%s',(row['run_id'],)).fetchone()['context']
        model=dict(model,_run_id=str(row['run_id']))
        view=map_data(model)
        base=dict(target_polygon=view['demo_polygon'],origin=view['default_origin'],
                  time=view['validation']['default_time'],scenarios=1000)
        target=transform(FWD,shape(base['target_polygon']));study=transform(FWD,shape(model['study_geometry']))
        results=[]
        for offset in (0,5,10):
            moved=translate(target,xoff=offset)
            if not study.covers(moved):raise RuntimeError('Objetivo de benchmark fuera del área')
            request=dict(base,target_polygon=mapping(transform(INV,moved)))
            started=time.monotonic();result=calculate(model,request,conn)
            results.append(dict(offset_m=offset,result_sha256=result['sha256'],status=result['status'],
                timings=result['timings'],wall_s=time.monotonic()-started,
                methods={k:dict(status=v['status'],timings=v['timings']) for k,v in result['routes'].items()}))
    cold=results[0]['timings']['setup_s'];warm=statistics.median(row['timings']['setup_s'] for row in results[1:])
    reduction=1-warm/cold if cold else 0
    report=dict(software=software_manifest(),conditions='Sequential; same snapshot/profile; translated target; fresh Python process; no concurrent solvers',
        measurements=results,cold_preparation_s=cold,median_warm_preparation_s=warm,
        preparation_reduction_fraction=reduction,target=.5,target_met=reduction>=.5)
    write_json(Path(args.output),report)
    print(json.dumps(report,ensure_ascii=False))
    if not report['target_met']:raise SystemExit(1)


if __name__=='__main__':main()
