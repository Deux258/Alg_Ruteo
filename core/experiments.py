"""Lote fijado por geografía y fechas, sin consultar resultados para seleccionar casos."""
import hashlib
from collections import Counter
from statistics import mean

from core.aerial_data import FWD,iso
from core.aerial_routing import data
from core.contracts import canonical,write_json
from core.mission_evaluation import compare,save


def select_targets(goals,directions):
    remaining=sorted(goals,key=lambda n:int(n['id']));selected=[]
    axes={'north':(1,1),'south':(1,-1),'east':(0,1),'west':(0,-1)}
    for direction in directions:
        if not remaining:break
        axis,sign=axes[direction]
        goal=min(remaining,key=lambda n:(-sign*FWD(*n['coordinates'])[axis],int(n['id'])))
        selected.append(dict(goal,direction=direction));remaining.remove(goal)
    return selected


def select_hours(weather,fetched_at):
    hours=sorted({w['valid_at'] for w in weather if iso(w['valid_at'])>=iso(fetched_at)},key=iso)
    return [hours[i] for i in sorted({0,len(hours)//2,len(hours)-1})] if hours else []


def aggregate(cases):
    valid=[c for c in cases if c['metrics']['valid_scenarios']>0]
    deltas=[c['metrics']['delta_percentage_points'] for c in valid]
    methods={}
    for method in ['reference','proposed']:
        methods[method]=dict(mean_set_survival=mean(c['metrics']['methods'][method]['set_survival'] for c in valid) if valid else None,
            two_options=sum(c['metrics']['methods'][method]['mission_count']==2 for c in cases),
            control_admissible=sum(c['control'][method] for c in cases),
            statuses=dict(Counter(c['status'][method] for c in cases)),
            reasons=dict(Counter(c['reason'][method] or 'none' for c in cases)),
            mean_shared_50m_fraction=mean(c['overlap'][method] for c in cases if c['overlap'][method] is not None) if any(c['overlap'][method] is not None for c in cases) else None)
    return dict(total_cases=len(cases),valid_cases=len(valid),unknown_cases=len(cases)-len(valid),
        valid_case_scenarios=sum(c['metrics']['valid_scenarios'] for c in cases),methods=methods,
        mean_delta_pp=mean(deltas) if deltas else None,min_delta_pp=min(deltas) if deltas else None,max_delta_pp=max(deltas) if deltas else None,
        improvements=sum(d>1e-9 for d in deltas),ties=sum(abs(d)<=1e-9 for d in deltas),worsenings=sum(d< -1e-9 for d in deltas))


def run_experiment(conn,rid,config,output):
    expected={'version':'fase2-batch-v1','directions':['north','south','east','west'],'hours':'first-middle-last-after-acquisition',
        'profiles':[{'id':'default','preferences':{}},{'id':'history4','preferences':{'max_historical_class':4}}]}
    if config!=expected:raise ValueError('La configuración debe corresponder al protocolo fijo fase2-batch-v1')
    model,area,nodes,_=data(conn,rid)
    goals=[dict(id=str(r['id']),coordinates=nodes[str(r['id'])]) for r in conn.execute("SELECT id FROM routing.nodes WHERE run_id=%s AND kind='vigilancia' ORDER BY id",(rid,))]
    targets=select_targets(goals,config['directions']);hours=select_hours(model['records']['M4'],model['weather_fetched_at'])
    bases=sorted([b for b in model['records']['M1'] if b.get('candidate',True)],key=lambda b:b['provider_id'])
    requests=[]
    for base in bases:
        for goal in targets:
            for clock in hours:
                for profile in config['profiles']:
                    requests.append(dict(id=f'case-{len(requests)+1:03d}',base=base['provider_id'],target_id=goal['id'],direction=goal['direction'],profile=profile['id'],
                        request=dict(origin=base['geometry']['coordinates'],destination=goal['coordinates'],time=clock,mode='mission',preferences=profile['preferences'])))
    from core.provenance import software_manifest
    software=software_manifest()
    plan=dict(version=config['version'],run_id=str(rid),config=config,requests=requests,software=software,
        reductions=dict(bases=len(bases),targets=len(targets),hours=len(hours),expected_cases=120,actual_cases=len(requests)),
        selection='Extremos UTM y horas posteriores a adquisición; sin seleccionar por factibilidad o resultado')
    digest=hashlib.sha256(canonical(plan)).hexdigest();folder=output/('experiment_'+digest[:16]);folder.mkdir(parents=True,exist_ok=True)
    write_json(folder/'plan.json',plan)  # Se fija antes de ejecutar cualquier algoritmo.
    cases=[]
    for item in requests:
        result=compare(conn,rid,item['request']);save(conn,result,folder/item['id'])
        cases.append(dict(id=item['id'],base=item['base'],profile=item['profile'],metrics=result['metrics'],
            evaluation_sha256=result['evaluation_sha256'],scenario_sha256=result['scenario_sha256'],
            status={m:r['status'] for m,r in result['sets'].items()},reason={m:r['reason'] for m,r in result['sets'].items()},
            control={m:any(result['results'][0]['survives'][m]) for m in result['sets']},
            overlap={m:r['alternatives'][1].get('within_50m_of_first_fraction') if len(r['alternatives'])>1 else None for m,r in result['sets'].items()}))
        print(f"{item['id']} / {len(requests)}: {result['metrics']['delta_percentage_points']} pp",flush=True)
    report=dict(experiment_sha256=digest,plan_sha256=hashlib.sha256(canonical(plan)).hexdigest(),run_id=str(rid),summary=aggregate(cases),
        by_profile={p['id']:aggregate([c for c in cases if c['profile']==p['id']]) for p in config['profiles']},cases=cases,
        warnings=['Casos sin alternativas cuentan como supervivencia cero si las condiciones son conocidas','Media descriptiva por caso; no prueba de superioridad estadística','Ninguna hora se selecciona por viento favorable'])
    report['result_sha256']=hashlib.sha256(canonical(report)).hexdigest()
    write_json(folder/'summary.json',report);return report
