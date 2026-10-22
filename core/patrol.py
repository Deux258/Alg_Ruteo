"""CLI de vigilancia: adquisición, preparación, cargas y evaluación."""
import argparse
import json
from pathlib import Path

from core.db import connect, apply_schema
from core.contracts import ROOT, write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['adquirir','preparar','evaluar','cargar','extraer'])
    parser.add_argument('--request',type=Path)
    parser.add_argument('--experiment',type=Path)
    parser.add_argument('--file',type=Path)
    parser.add_argument('--dataset',choices=['I']+[role+str(i) for role in ['M','A'] for i in range(1,6)])
    parser.add_argument('--output',type=Path,default=ROOT/'datos/runs/vigilancia_evaluaciones')
    args=parser.parse_args()
    with connect() as conn:
        if args.action=='adquirir':
            from core.patrol_data import base_context
            from core.patrol_sources import download
            _,_,area,_,_=base_context(conn);result=download(area)
        elif args.action=='preparar':
            from core.patrol_data import prepare
            result=prepare(conn)
        elif args.action=='extraer':
            if not args.dataset:parser.error('extraer requiere --dataset')
            row=conn.execute('SELECT run_id FROM routing.patrol_publication WHERE singleton').fetchone()
            if not row:raise ValueError('Preparar vigilancia antes de extraer')
            source=ROOT/'datos/runs'/str(row['run_id'])/(args.dataset+'.json')
            args.output.mkdir(parents=True,exist_ok=True)
            import shutil
            target=args.output/(args.dataset+'.json')
            if source.resolve()!=target.resolve():shutil.copyfile(source,target)
            result=dict(dataset=args.dataset,file=str(target))
        elif args.action=='cargar':
            from core.patrol_data import load_dataset
            if not args.file:parser.error('cargar requiere --file')
            with conn.transaction():load_dataset(conn,args.file)
            result=dict(loaded=str(args.file))
        else:
            from core.patrol_evaluation import compare, experiment
            if bool(args.request)==bool(args.experiment):parser.error('evaluar requiere --request o --experiment')
            rid=str(conn.execute('SELECT run_id FROM routing.patrol_publication WHERE singleton').fetchone()['run_id'])
            result=experiment(conn,rid,json.loads(args.experiment.read_text()),args.output) if args.experiment else compare(conn,rid,json.loads(args.request.read_text()))
            if args.request:
                from psycopg.types.json import Jsonb
                conn.execute('INSERT INTO routing.patrol_evaluations VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(rid,result['sha256'],Jsonb(result)))
                args.output.mkdir(parents=True,exist_ok=True);write_json(args.output/('comparison_'+result['sha256'][:16]+'.json'),result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['features','sets','results','scenarios','software']},ensure_ascii=False,default=str))


if __name__=='__main__':main()
