"""Comparación de misiones congeladas y lotes separados por nº de objetivos."""
import copy
import hashlib
import json
from datetime import timedelta

from shapely.geometry import LineString, Point, shape, mapping
from shapely.ops import transform, unary_union

from core.contracts import ROOT, canonical, write_json
from core.aerial_data import FWD, INV, iso
from core.mission_evaluation import scenario_catalogue, summarise
from core.patrol_routing import plan, effective_profile, normalize_request, weather_window, restriction_geometry, overlay, enrich, reverse_distances, assess
from core.patrol_data import graph, Obstacles
from core.surface import Surface


def compare(conn,rid,request):
    frozen={method:plan(conn,rid,request,method) for method in ['reference','proposed']}
    base,context,states,edges,obstacles=graph(str(rid));p=effective_profile(base,request.get('preferences'))
    origin,goals,clock=normalize_request(request,p,context)
    catalogue=scenario_catalogue(canonical(context['flight_geometry']).decode())
    geometries={}
    for method,result in frozen.items():
        geometries[method]=[]
        for item in result['alternatives']:
            lines=[transform(FWD,LineString([c[:2] for c in leg['coordinates']])) for leg in item['legs'] if len(leg['coordinates'])>1]
            geometries[method].append(unary_union(lines+[origin]+[g['point'] for g in goals]))
    _,weather_problem=weather_window(context['weather'],clock,p)
    unknown=bool(weather_problem and weather_problem.startswith(('missing','unknown'))) or any(r['status']=='unknown' for r in frozen.values())
    rows=[];scenarios=[]
    for scenario in catalogue['scenarios']:
        closure=transform(FWD,shape(scenario['geometry'])).buffer(scenario['radius_m']) if scenario['geometry'] else None
        survives={method:[bool(item['evaluation']['admissible'] and (closure is None or not closure.intersects(geometry))) for item,geometry in zip(result['alternatives'],geometries[method])] for method,result in frozen.items()}
        known=not unknown and all(item['evaluation']['known'] for result in frozen.values() for item in result['alternatives'])
        rows.append(dict(id=scenario['id'],family='spatial',known=known,survives=survives));scenarios.append(dict(scenario,family='spatial'))
    if all(not r['alternatives'] for r in frozen.values()):
        for label,wind_factor,budget_factor in [('wind-125',1.25,1),('wind-150',1.5,1),('budget-090',1,.9),('budget-075',1,.75)]:
            rows.append(dict(id=label,family='environment',known=not unknown,survives={method:[] for method in frozen}))
            scenarios.append(dict(id=label,family='environment',synthetic=True,wind_factor=wind_factor,budget_factor=budget_factor))
        metrics=summarise(rows,{k:0 for k in frozen})
        metrics['by_family']={family:summarise([r for r in rows if r['family']==family],{k:0 for k in frozen}) for family in ['spatial','environment']}
        result=dict(type='FeatureCollection',schema_version='patrol-comparison-1',run_id=str(rid),request=request,
                    objective_count=len(goals),sets=frozen,metrics=metrics,results=rows,scenarios=scenarios,features=[],
                    scenario_sha256=hashlib.sha256(canonical(scenarios)).hexdigest())
        result['sha256']=hashlib.sha256(canonical(result)).hexdigest()
        return result
    surface=Surface(ROOT/context['dsm_file'],transform(FWD,shape(context['flight_geometry'])).bounds)
    try:all_states,all_edges,home,terminal=overlay(states,edges,origin,goals,surface,Obstacles(obstacles),p,transform(FWD,shape(context['flight_geometry'])))
    finally:surface.close()
    # Sensibilidad ambiental separada de los cierres; mismo escenario para ambos métodos.
    for label,wind_factor,budget_factor in [('wind-125',1.25,1),('wind-150',1.5,1),('budget-090',1,0.9),('budget-075',1,0.75)]:
        ctx=copy.deepcopy(context);pp=dict(p,budget_eq_s=p['budget_eq_s']*budget_factor)
        for w in ctx['weather']:
            for key in ['wind_speed_ms','wind_100_ms','wind_gust_ms']:
                if w[key] is not None:w[key]*=wind_factor
        weather,problem=weather_window(ctx['weather'],clock,pp)
        blocked,_,_=restriction_geometry(ctx,clock,request.get('events',[]))
        eligible,_=enrich(all_edges,pp,weather,blocked) if not problem else ([],{})
        lookup={e['id']:e for e in all_edges};lookup.update({e['id']:e for e in eligible});returns=reverse_distances(eligible,home,pp['turn_s'])
        survives={};known=not (problem and problem.startswith(('missing','unknown')))
        for method,result in frozen.items():
            survives[method]=[]
            for item in result['alternatives']:
                views={int(v['state_id']):v for v in item['observations']}
                evaluation=assess(item,lookup,all_states,ctx,pp,clock,blocked,returns,views)
                known=known and evaluation['known'];survives[method].append(evaluation['admissible'])
        rows.append(dict(id=label,family='environment',known=known,survives=survives))
        scenarios.append(dict(id=label,family='environment',synthetic=True,wind_factor=wind_factor,budget_factor=budget_factor))
    metrics=summarise(rows,{k:len(v['alternatives']) for k,v in frozen.items()})
    metrics['by_family']={family:summarise([r for r in rows if r['family']==family],{k:len(v['alternatives']) for k,v in frozen.items()}) for family in ['spatial','environment']}
    result=dict(type='FeatureCollection',schema_version='patrol-comparison-1',run_id=str(rid),request=request,
                objective_count=len(goals),sets=frozen,metrics=metrics,results=rows,scenarios=scenarios,
                features=[f for item in frozen.values() for f in item['features']],
                scenario_sha256=hashlib.sha256(canonical(scenarios)).hexdigest())
    result['sha256']=hashlib.sha256(canonical(result)).hexdigest()
    return result


def experiment(conn,rid,config,output):
    """Fijar todas las solicitudes antes de planificar, sin seleccionar por resultado."""
    from core.patrol_routing import map_data
    view=map_data(rid);p,context,states,edges,obstacles=graph(str(rid))
    bases=[b for b in context['records']['M1'] if b.get('candidate')]
    if not bases:raise ValueError('Sin instalaciones de referencia')
    origin=config.get('origin',bases[0]['geometry']['coordinates'])
    examples=sorted(view['examples'],key=lambda row:(Point(FWD(*row['coordinates'])).distance(Point(FWD(*origin))),row['coordinates']))
    if len(examples)<3:raise ValueError('Faltan tres objetivos para el lote')
    hours=[w['valid_at'] for w in view['weather'] if iso(w['valid_at'])>=iso(context['weather_fetched_at'])]
    if len(hours)<2:raise ValueError('Faltan horas posteriores a adquisición')
    selected=[hours[i] for i in sorted({0,len(hours)//2,len(hours)-2})]
    requests=[]
    for count in [1,2,3]:
        for i,hour in enumerate(selected):
            requests.append(dict(id=f'n{count}-h{i}',objective_count=count,request=dict(origin=origin,
                objectives=[row['coordinates'] for row in examples[:count]],time=hour)))
    specification=dict(version='patrol-batch-1',run_id=str(rid),requests=requests,
                       selection='Instalación y proximidad geométrica; horas primera, central y penúltima, sin filtrar por viabilidad')
    digest=hashlib.sha256(canonical(specification)).hexdigest();folder=output/('experiment_'+digest[:16]);folder.mkdir(parents=True,exist_ok=True)
    write_json(folder/'plan.json',specification)
    results=[]
    from psycopg.types.json import Jsonb
    for item in requests:
        result=compare(conn,rid,item['request']);write_json(folder/(item['id']+'.json'),result)
        conn.execute('INSERT INTO routing.patrol_evaluations VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(rid,result['sha256'],Jsonb(result)))
        results.append(dict(id=item['id'],objective_count=item['objective_count'],metrics=result['metrics'],
                            alternatives={k:len(v['alternatives']) for k,v in result['sets'].items()}))
        print(item['id']+' terminado',flush=True)
    summary={}
    for n in [1,2,3]:
        cases=[r for r in results if r['objective_count']==n];values=[r['metrics']['delta_percentage_points'] for r in cases if r['metrics']['delta_percentage_points'] is not None]
        summary[str(n)]=dict(cases=len(cases),valid=len(values),mean_delta_pp=sum(values)/len(values) if values else None,
                             with_two_proposed=sum(r['alternatives']['proposed']==2 for r in cases))
    result=dict(schema_version='patrol-experiment-1',run_id=str(rid),sha256=digest,by_objective_count=summary,cases=results)
    write_json(folder/'summary.json',result);return result
