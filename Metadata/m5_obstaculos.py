"""M5: obstáculos originales normalizados. CLI compartido con contrato propio."""
import argparse
from pathlib import Path
from core.contracts import write_json
from core.db import connect


def main(key='M5'):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--load',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    with connect() as conn:
        if args.load:
            import json
            from core.patrol_data import load_dataset
            if json.loads(args.load.read_text())['dataset_key']!=key:raise ValueError('Dataset incompatible')
            with conn.transaction():load_dataset(conn,args.load)
        else:
            if not args.output:parser.error('Indicar --output o --load')
            row=conn.execute('SELECT document FROM routing.patrol_datasets d JOIN routing.patrol_publication p USING(run_id) WHERE d.key=%s',(key,)).fetchone()
            if not row:raise ValueError('Preparar vigilancia antes de extraer')
            write_json(args.output,row['document'])


if __name__=='__main__':main()
