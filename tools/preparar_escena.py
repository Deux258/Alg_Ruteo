"""Preprocess the geographic scene once, outside interactive HTTP requests."""
import argparse
import json
import sys
from core.patrol import snapshot_context,terrain
from core.geographic_scene import prepare

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context',required=False,help='Existing context.json belonging to this repository')
    parser.add_argument('--if-aerial',action='store_true',help='Skip a road publication without changing its service')
    args=parser.parse_args()
    if args.context:model=snapshot_context(args.context)
    else:
        from core.db import connect
        with connect() as conn:
            row=conn.execute('SELECT run_id FROM routing.publication WHERE singleton').fetchone()
            record=conn.execute('SELECT context FROM routing.aerial_models WHERE run_id=%s',(row['run_id'],)).fetchone() if row else None
            if record is None:
                if args.if_aerial:
                    print(json.dumps(dict(skipped=True,reason='La publicación actual no es aérea')))
                    raise SystemExit(0)
                raise ValueError('No existe una publicación aérea; ejecutar main iniciar primero')
            raw=record['context']
            model=dict(raw,_run_id=str(row['run_id']))
    print('Preparando cartografía y terreno...',file=sys.stderr,flush=True)
    prepared=prepare(model,terrain())
    from core.geo_transport import map_summary
    from core.communes import commune_index
    from shapely.geometry import shape
    from core.contracts import canonical
    resources=[]
    for cut in [None,*[c['id'] for c in commune_index().catalogue(shape(model['flight_geometry']))]]:
        print('Preparando vista '+(cut or 'completa')+'...',file=sys.stderr,flush=True)
        summary=map_summary(model,'prepared snapshot',cut)
        resources.append(dict(commune_id=cut,summary_bytes=len(canonical(summary)),resources=summary['resources']))
    print(json.dumps(dict(scene=prepared,prepared_resources=resources)))
