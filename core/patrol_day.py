"""Reusable daily patrols: one drone/base, independent sorties and no teleporting."""
import hashlib
import math
from datetime import date,timedelta

from shapely.geometry import shape,Point
from shapely.ops import transform

from core.aerial_data import FWD
from core.contracts import ROOT,canonical,write_json,sha256
from core.patrol_monitoring import catalogue,DIRECTORY

FLIGHTS_PER_DAY=2
ANCHOR=date(2026,11,12)


def programmes(catalog,model):
    names={b['provider_id']:b.get('name',b['provider_id']) for b in model['records']['M1']}
    groups={}
    for sector in catalog['sectors']:
        if sector['status']!='pending_support':groups.setdefault(sector['base_id'],[]).append(sector)
    return [dict(id=base,name=f"Monitoreo · {names.get(base,base)}",base_id=base,
                 sectors=len(rows),flights_per_day=FLIGHTS_PER_DAY,cycle_days=math.ceil(len(rows)/FLIGHTS_PER_DAY))
            for base,rows in sorted(groups.items())]


def schedule(catalog,programme,day):
    if not isinstance(day,str):raise ValueError('Fecha de jornada requerida: YYYY-MM-DD')
    try:chosen=date.fromisoformat(day)
    except ValueError:raise ValueError('Fecha de jornada inválida: YYYY-MM-DD') from None
    rows=[s for s in catalog['sectors'] if s['base_id']==programme and s['status']!='pending_support']
    if not rows:raise ValueError('Programa de monitoreo desconocido')
    # Start close to home, then advance deterministically through the complete
    # assigned territory across days; never silently limit the catalogue to demos.
    rows.sort(key=lambda s:(transform(FWD,shape(s['target_polygon'])).representative_point().distance(Point(FWD(*s['origin']))),s['id']))
    cycle=math.ceil(len(rows)/FLIGHTS_PER_DAY)
    start=((chosen-ANCHOR).days%cycle)*FLIGHTS_PER_DAY
    return rows[start:min(start+FLIGHTS_PER_DAY,len(rows))]


def daily(model,request,conn=None,on_result=None):
    from core.patrol import calculate
    catalog=catalogue(model)
    programmes_list=programmes(catalog,model)
    programme=request.get('programme_id','104')
    if programme not in {p['id'] for p in programmes_list}:raise ValueError('Programa de monitoreo desconocido')
    day=request.get('date',date.today().isoformat())
    sectors=schedule(catalog,programme,day)
    operation=request.get('operation','plan')
    if operation not in ('plan','prepare'):raise ValueError('Operación de jornada desconocida')
    settings={k:request[k] for k in ('time','preferences','station_ids','seed') if k in request}
    identity=dict(catalog=catalog['sha256'],programme=programme,date=day,settings=settings,
                  code={p:sha256(ROOT/p) for p in ('core/patrol.py','core/patrol_day.py','core/vertical_profile.py','config/patrullaje.json')})
    key=hashlib.sha256(canonical(identity)).hexdigest()
    folder=DIRECTORY/'daily';path=folder/f'{key}.json'
    if path.exists():
        import json
        return json.loads(path.read_text())
    plan=dict(schema_version='patrol-day-1',id=key,date=day,programme_id=programme,
              name=next(p['name'] for p in programmes_list if p['id']==programme),
              status='requires_preparation',flights=[],pending_sectors=[],total_time_s=0,base_id=programme,
              service_between_flights_s=120,
              weather_policy='Hora del snapshot elegida; la fecha organiza la rotación, no descarga un pronóstico nuevo')
    candidates=list(sectors)
    if operation=='prepare':
        for offset in (1,2):
            for sector in schedule(catalog,programme,(date.fromisoformat(day)+timedelta(days=offset)).isoformat()):
                if sector['id'] not in {s['id'] for s in candidates}:candidates.append(sector)
    for order,sector in enumerate(candidates,1):
        row=dict(order=order,patrol_id=sector['id'],name=f"Vuelo {order} · {sector['name']}",
                 status='pending',coordinates=[],time_s=None)
        if operation=='prepare':
            result=calculate(model,dict(settings,patrol_id=sector['id'],scenarios=20),conn,primary_only=True)
            if on_result:on_result(result)
            route=result['routes'].get('dijkstra_weighted',{})
            row.update(status=route.get('status','blocked'),result_sha256=result['sha256'],method='dijkstra_weighted',
                       coordinates=route.get('coordinates',[]),time_s=route.get('time_s'),
                       distance_m=route.get('distance_m'),coverage=route.get('coverage'),
                       reason=route.get('solver',{}).get('reason'))
            if row['status']=='ready' and route.get('stops'):
                row.update(status='needs_recharge_support',reason='Requiere recarga intermedia; queda pendiente para no reutilizar inventario entre vuelos')
            if row['status']!='ready':
                plan['pending_sectors'].append(dict(patrol_id=sector['id'],name=sector['name'],status=row['status'],reason=row['reason']))
                continue
            row.update(order=len(plan['flights'])+1,name=f"Vuelo {len(plan['flights'])+1} · {sector['name']}")
        plan['flights'].append(row)
        if operation=='prepare' and len(plan['flights'])>=len(sectors):break
    if operation=='prepare':
        ready=[f for f in plan['flights'] if f['status']=='ready']
        plan['status']='ready' if len(ready)==len(sectors) else 'partial' if ready else 'blocked'
        plan['total_time_s']=sum(f['time_s'] for f in ready)+max(0,len(ready)-1)*plan['service_between_flights_s']
        folder.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix('.tmp');write_json(temporary,plan);temporary.replace(path)
    return plan
