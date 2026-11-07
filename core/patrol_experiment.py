"""Fixed polygon batch, including failures; no favourable-result filtering."""
import gzip
import hashlib
from pathlib import Path
from shapely.affinity import scale
from shapely.geometry import shape, mapping, Point
from shapely.ops import transform
from core.contracts import canonical, write_json
from core.aerial_data import FWD, INV, iso
from core.patrol import map_data, defaults, selected_weather, calculate


def save_compressed(path,value):
    with gzip.GzipFile(filename=str(path),mode='wb',mtime=0) as f:f.write(canonical(value))


def run(model,protocol,output,conn=None):
    if protocol.get('protocol') not in ('patrol-batch-1','patrol-batch-2','patrol-batch-3'):raise ValueError('Protocolo no reconocido')
    info=map_data(model)
    if info['demo_polygon'] is None:raise ValueError('No existe objetivo de demostración geométrico')
    chosen=None
    for row in model['records']['M4']:
        if iso(row['valid_at'])<iso(model['weather_fetched_at']):continue
        try:selected_weather(model,iso(row['valid_at']),defaults())
        except ValueError:continue
        chosen=row['valid_at'];break
    if chosen is None:raise ValueError('Sin hora admisible posterior a adquisición')
    target=transform(FWD,shape(info['demo_polygon']))
    study=transform(FWD,shape(model['study_geometry'])).buffer(-1)
    requests=[]
    for factor in protocol['polygon_scales']:
        polygon=scale(target,xfact=factor,yfact=factor)
        if protocol['protocol'] in ('patrol-batch-2','patrol-batch-3'):polygon=polygon.intersection(study)
        for multiplier in protocol['historical_multipliers']:
            cases=protocol.get('local_threat_cases',[dict(id='none')]) if protocol['protocol']=='patrol-batch-3' else [dict(id='none')]
            if not isinstance(cases,list) or not cases:raise ValueError('Protocolo local requiere casos prefijados')
            for case in cases:
                events=[]
                if 'probability_pct' in case:
                    from core.patrol import number
                    probability=number(case['probability_pct'],'probability_pct',0,100)
                    radius=number(case['radius_m'],'radius_m',1,1000)
                    dx=number(case.get('offset_east_m',0),'offset_east_m',-2000,2000)
                    dy=number(case.get('offset_north_m',0),'offset_north_m',-2000,2000)
                    center=polygon.centroid
                    events=[dict(geometry=mapping(transform(INV,Point(center.x+dx,center.y+dy).buffer(radius))),probability_pct=probability)]
                requests.append(dict(origin=info['default_origin'],target_polygon=mapping(transform(INV,polygon)),events=events,
                                     time=chosen,seed=protocol['seed'],scenarios=protocol['scenarios'],preferences=dict(historical_multiplier=multiplier)))
    from core.provenance import software_manifest
    plan=dict(protocol=protocol,run_id=model.get('_run_id'),code_sha256=software_manifest()['code_sha256'],requests=requests)
    digest=hashlib.sha256(canonical(plan)).hexdigest()
    folder=Path(output)/('batch_'+digest[:16]);folder.mkdir(parents=True,exist_ok=True)
    write_json(folder/'plan.json',plan)
    rows=[]
    for i,request in enumerate(requests):
        case=folder/f'case-{i+1:03d}';case.mkdir(exist_ok=True)
        try:
            result=calculate(model,request,conn)
            save_compressed(case/'comparison.json.gz',result)
            save_compressed(case/'failure_probabilities.json.gz',result['failure_probabilities'])
            rows.append(dict(case=i+1,sha256=result['sha256'],status=result.get('status','ready'),recommended=result['recommended'],compute_s=result['compute_s'],
                             actual_budgets={k:result['effective_profile'][k] for k in ('battery_budget_s','mission_budget_s')},
                             planning_budgets={k:result['planning_profile'][k] for k in ('battery_budget_s','mission_budget_s')},
                             methods={k:dict(status=r['status'],resilience=(r.get('resilience') or {}).get('value'),
                                            confidence_interval=(r.get('resilience') or {}).get('confidence_interval'),
                                            time_s=r['time_s'],compute_s=r['compute_s']) for k,r in result['routes'].items()}))
        except ValueError as exc:
            rows.append(dict(case=i+1,status='invalid_or_unavailable',reason=str(exc),request=request))
        write_json(case/'summary.json',rows[-1])
    summary=dict(protocol=protocol['protocol'],plan_sha256=digest,cases=rows,total_cases=len(rows),
                 invalid_cases=sum('methods' not in r for r in rows),blocked_cases=sum(r.get('status')=='blocked' for r in rows),output=str(folder))
    write_json(folder/'summary.json',summary)
    return summary
