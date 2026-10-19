"""Comparación de misiones congeladas; supervivencia sintética, no probabilidad.

La web calcula en modo lectura. El CLI ETL conserva los resultados con un usuario
de escritura, sin alterar las tablas de nodos/rutas de los snapshots publicados.
"""
import argparse
import hashlib
import json
import random
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point,LineString,shape,mapping
from shapely.ops import transform,unary_union

from core.aerial_data import FWD,INV,iso
from core.aerial_routing import calculate,data,effective_profile,available,restrictions,edge_time,exposure,historical_policy
from core.contracts import canonical,write_json


@lru_cache(maxsize=4)
def scenario_catalogue(geometry_text):
    flight=transform(FWD,shape(json.loads(geometry_text)))
    rng=random.Random(20261018);west,south,east,north=flight.bounds
    scenarios=[dict(id='control',synthetic=True,geometry=None,radius_m=0)]
    for i in range(99):
        while True:
            point=Point(rng.uniform(west,east),rng.uniform(south,north))
            if flight.covers(point):break
        scenarios.append(dict(id=f'closure-{i+1:03d}',synthetic=True,geometry=mapping(transform(INV,point)),radius_m=[100,250,500][i%3]))
    return dict(version='mission-survival-v1',seed=20261018,selection='Uniforme por rechazo en el área de tránsito; independiente del método',scenarios=scenarios)


def summarise(rows,methods):
    valid=[r for r in rows if r['known']]
    output=dict(total_scenarios=len(rows),valid_scenarios=len(valid),unknown_scenarios=len(rows)-len(valid),methods={})
    for method,count in methods.items():
        output['methods'][method]=dict(mission_count=count,
            individual=[sum(r['survives'][method][i] for r in valid)/len(valid) if valid else None for i in range(count)],
            set_survival=sum(any(r['survives'][method]) for r in valid)/len(valid) if valid else None)
    a=output['methods']['reference']['set_survival'];b=output['methods']['proposed']['set_survival']
    output['delta_percentage_points']=100*(b-a) if a is not None and b is not None else None
    return output


def assess(option,model,clock,events,remaining,endpoints=()):
    weather,problem=available(model,clock)
    if problem:return dict(known=not problem.startswith(('missing','unknown')),admissible=False,reason=problem,time_s=None,geometry=None)
    blocked,_,stale=restrictions(model,clock,events)
    lines=[];time_s=option.get('observation_s',model['profile']['observation_s']);weighted=unknown=0
    for path in [option['outbound'],option.get('return_path')]:
        if path is None:return dict(known=True,admissible=False,reason='missing_return',time_s=None,geometry=None)
        coords=path['coordinates']
        if len(coords)<2:continue
        line=transform(FWD,LineString(coords));lines.append(line)
        for a,b in zip(line.coords,line.coords[1:]):
            duration=edge_time(LineString([a,b]),weather,model['profile'])
            if duration is None:return dict(known=True,admissible=False,reason='wind_infeasible',time_s=None,geometry=None)
            time_s+=duration
        value,missing=exposure(line,model['history']);weighted+=value;unknown+=missing
    geometry=unary_union(lines+[Point(FWD(*point)) for point in endpoints])
    intersects=blocked.intersects(geometry)
    policy=historical_policy(geometry,model)
    allowed=not intersects and policy is None and time_s<=remaining+1e-8
    return dict(known=True,admissible=allowed,reason='restricted' if intersects else policy or ('insufficient_budget' if not allowed else None),
        time_s=time_s,exposure_m=weighted,unknown_m=unknown,thermal_unknown_ids=stale,geometry=geometry)


def compare(conn,rid,request):
    if not isinstance(request,dict):raise ValueError('Solicitud JSON inválida')
    if request.get('mode','mission')!='mission' or request.get('phase','outbound')!='outbound' or request.get('elapsed_s',0)!=0 or request.get('on_edge') or 'position' in request:
        raise ValueError('La comparación requiere una misión nueva completa, sin posición ni tiempo consumido')
    frozen={method:calculate(conn,rid,dict(request,mode='mission',method=method)) for method in ['reference','proposed']}
    model,area,_,_=data(conn,rid);profile=effective_profile(model['profile'],request.get('preferences'));model=dict(model,profile=profile)
    clock=iso(frozen['proposed']['time'])
    catalogue=scenario_catalogue(canonical(mapping(area)).decode())
    assessments={}
    for method,result in frozen.items():
        assessments[method]=[assess(option,model,clock,request.get('events',[]),profile['budget_s'],[result['origin'],result['destination']]) for option in result['alternatives']]
        for option,assessment in zip(result['alternatives'],assessments[method]):
            option['evaluation']={k:v for k,v in assessment.items() if k!='geometry'}
    weather,problem=available(model,clock)
    known=not (problem and problem.startswith(('missing','unknown'))) and frozen['proposed']['status']!='unknown'
    rows=[]
    for scenario in catalogue['scenarios']:
        closure=transform(FWD,shape(scenario['geometry'])).buffer(scenario['radius_m']) if scenario['geometry'] else None
        survives={method:[bool(a['admissible'] and (closure is None or not closure.intersects(a['geometry']))) for a in checks] for method,checks in assessments.items()}
        rows.append(dict(id=scenario['id'],known=known,survives=survives))
    metrics=summarise(rows,{k:len(v) for k,v in assessments.items()})
    features=[]
    for method,result in frozen.items():
        features.extend(dict(f,properties=dict(f['properties'],method=method)) for f in result['features'])
    response=dict(type='FeatureCollection',features=features,run_id=str(rid),status='ready',sets=frozen,evaluation_version='mission-comparison-v2',
        effective_profile=profile,scenario_catalogue=catalogue,scenario_sha256=hashlib.sha256(canonical(catalogue)).hexdigest(),
        results=rows,metrics=metrics,request=request,temporal_model='static_at_selected_hour',
        warnings=['Misiones fijadas antes de aplicar escenarios; no se recalculan rutas en esta métrica',
            'Supervivencia ante cierres sintéticos, no probabilidad real de éxito',
            'La referencia ignora amenazas al generar rutas; ambos métodos se evalúan con las mismas restricciones',
            'Sin despeje vertical verificado ni independencia geográfica garantizada'])
    from core.provenance import software_manifest
    response['software']=software_manifest()
    response['evaluation_sha256']=hashlib.sha256(canonical(response)).hexdigest()
    return response


def save(conn,result,output):
    from psycopg.types.json import Jsonb
    digest=result['evaluation_sha256']
    conn.execute('''INSERT INTO routing.mission_evaluations(run_id,evaluation_sha256,scenario_sha256,request,result)
        VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',(result['run_id'],digest,result['scenario_sha256'],Jsonb(result['request']),Jsonb(result)))
    output.mkdir(parents=True,exist_ok=True)
    write_json(output/('comparison_'+digest[:16]+'.json'),result)
    write_json(output/('scenarios_'+result['scenario_sha256'][:16]+'.json'),result['scenario_catalogue'])


def main():
    from core.db import connect
    parser=argparse.ArgumentParser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True);inputs.add_argument('--request',type=Path);inputs.add_argument('--experiment',type=Path)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--run-id')
    args=parser.parse_args()
    with connect() as conn:
        rid=args.run_id or conn.execute('SELECT run_id FROM routing.publication WHERE singleton').fetchone()['run_id']
        if args.experiment:
            from core.experiments import run_experiment
            result=run_experiment(conn,rid,json.loads(args.experiment.read_text(encoding='utf-8')),args.output)
            print(json.dumps(dict(run_id=str(rid),experiment_sha256=result['experiment_sha256'],summary=result['summary'])))
        else:
            result=compare(conn,rid,json.loads(args.request.read_text(encoding='utf-8')));save(conn,result,args.output)
            print(json.dumps(dict(run_id=str(rid),sha256=result['evaluation_sha256'],metrics=result['metrics'])))


if __name__=='__main__':main()
