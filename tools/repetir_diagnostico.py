"""Repite solicitudes EXACTAS del lote conservado y compara decisiones/geometrías.

Uso Docker: python tools/repetir_diagnostico.py --baseline ... --output datos/runs/...
No publica, no inserta evaluaciones y no selecciona extremos nuevos.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from core.contracts import canonical,write_json
from core.db import connect
from core.mission_evaluation import compare
from core.provenance import software_manifest


def decision(result):
    return dict(metrics=result['metrics'],results=result['results'],features=result['features'],
                scenario_sha256=result['scenario_sha256'],
                sets={method:{k:v for k,v in row.items() if k!='diagnostics'} for method,row in result['sets'].items()})


def replay(baseline,output):
    plan=json.loads((baseline/'plan.json').read_text(encoding='utf-8'));output.mkdir(parents=True,exist_ok=True)
    write_json(output/'plan.json',plan)
    cases=[]; counts=Counter();primary=Counter();contradictions=[];differences=[]
    with connect() as conn:
        publication_before=str(conn.execute('SELECT run_id FROM routing.publication WHERE singleton').fetchone()['run_id'])
        for item in plan['requests']:
            original=json.loads(next((baseline/item['id']).glob('comparison_*.json')).read_text(encoding='utf-8'))
            current=compare(conn,plan['run_id'],item['request'])
            unchanged=decision(current)==decision(original)
            diagnostics=current['sets']['proposed']['diagnostics']
            codes=sorted({c['code'] for c in diagnostics['causes']})
            counts.update(codes);primary[current['sets']['proposed']['reason'] or 'none']+=1
            if not unchanged: differences.append(item['id'])
            if diagnostics['independent_oracle'].get('proposed_rejection_contradiction'):contradictions.append(item['id'])
            write_json(output/(item['id']+'.json'),current)
            cases.append(dict(id=item['id'],profile=item['profile'],unchanged=unchanged,causes=codes,
                              diagnostics=diagnostics,status=current['sets']['proposed']['status']))
            print(item['id']+' unchanged='+str(unchanged),flush=True)
        publication_after=str(conn.execute('SELECT run_id FROM routing.publication WHERE singleton').fetchone()['run_id'])
    report=dict(run_id=plan['run_id'],baseline_plan_sha256=hashlib.sha256((baseline/'plan.json').read_bytes()).hexdigest(),
                total=len(cases),unchanged=len(cases)-len(differences),differences=differences,contradictions=contradictions,
                primary_reasons=dict(primary),simultaneous_case_counts=dict(counts),cases=cases,
                count_note='Cada causa cuenta una vez por solicitud; una solicitud puede tener varias causas. No sumar como casos distintos.',
                publication_before=publication_before,publication_after=publication_after,
                publication_unchanged=publication_before==publication_after,software=software_manifest())
    write_json(output/'summary.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--baseline',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=replay(args.baseline,args.output)
    print(json.dumps({k:v for k,v in report.items() if k not in ['cases','software']}))
    raise SystemExit(0 if not report['differences'] and not report['contradictions'] else 1)
