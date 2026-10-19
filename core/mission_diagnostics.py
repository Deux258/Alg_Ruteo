"""Diagnóstico aditivo y oráculo independiente de pgRouting sobre el mismo grafo.

No decide ni amplía la búsqueda. Inviabilidad solo se refiere a esta malla y hora.
Los conteos por causa pueden solaparse; nunca se suman como casos distintos.
"""
import heapq
import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from shapely.geometry import Point, LineString, shape
from shapely.ops import transform

from core.aerial_data import FWD, iso


def shortest_time(edges, source, target):
    """Dijkstra dirigido con heapq, sin pgRouting ni reutilización de sus caminos."""
    if source == target: return 0.0
    graph={}
    for edge in edges:
        cost=edge['time_s']
        if not math.isfinite(cost) or cost < 0: raise ValueError('Costo temporal inválido')
        graph.setdefault(edge['source'],[]).append((edge['target'],cost))
    distances={source:0.0}; queue=[(0.0,source)]
    while queue:
        cost,node=heapq.heappop(queue)
        if cost > distances[node]: continue
        if node == target: return cost
        for other,weight in graph.get(node,[]):
            candidate=cost+weight
            if candidate < distances.get(other,math.inf):
                distances[other]=candidate; heapq.heappush(queue,(candidate,other))
    return None


def minimum_mission(edges, source, target, home, observation_s, remaining_s, need_return):
    outward=shortest_time(edges,source,target)
    backward=shortest_time(edges,target,home) if need_return else 0.0
    minimum=outward+backward+observation_s if outward is not None and backward is not None else None
    return dict(state='computed',implementation='heapq_dijkstra',outbound_s=outward,return_s=backward,
                observation_s=observation_s,remaining_s=remaining_s,minimum_remaining_s=minimum,
                feasible=minimum is not None and minimum <= remaining_s+1e-9,
                scope='Mismo grafo dirigido admitido, malla y condiciones estáticas; no espacio continuo')


def diagnose(conn, rid, request, result):
    from core.aerial_routing import (data, effective_profile, overlay, available, restrictions,
                                    events_geometry, historical_policy, edge_time)
    model,area,nodes,edges=data(conn,rid)
    profile=effective_profile(model['profile'],request.get('preferences')); model=dict(model,profile=profile)
    clock=iso(result['time']); mode=result['mode']; phase=result['phase']
    details=[]; not_tested=[]
    def cause(code, **extra):
        item=dict(code=code,**extra)
        if item not in details: details.append(item)
    points=dict(home=result['origin'],target=result['destination'],current=result['position'])
    relevant=['current','target','home'] if mode=='mission' and phase=='outbound' else ['current','home'] if phase!='outbound' else ['current','target']
    endpoints={key:Point(FWD(*points[key])) for key in relevant}
    blocked,_,stale=restrictions(model,clock,request.get('events',[]))
    aip=[]
    for row in model['records']['A3']:
        polygon=transform(FWD,shape(row['geometry']))
        hits=[key for key,point in endpoints.items() if polygon.intersects(point)]
        if hits: aip.append(dict(id=row.get('provider_id',row.get('code')),endpoints=hits))
    if aip: cause('aip_endpoint_restriction',zones=aip)
    if any(blocked.intersects(p) for p in endpoints.values()): cause('endpoint_blocked')
    thermal=[]
    for row in model['records']['A2']:
        if iso(row['acquired_at'])>clock or row.get('state')=='resolved': continue
        if profile.get('builder')!='aerial-grid-v2' and clock-iso(row['acquired_at'])>timedelta(hours=profile['thermal_window_hours']): continue
        polygon=transform(FWD,shape(row['geometry']))
        hits=[key for key,point in endpoints.items() if polygon.intersects(point)]
        if hits: thermal.append(dict(id=row.get('provider_id'),endpoints=hits))
    if thermal: cause('thermal_endpoint_restriction',detections=thermal)
    for key,point in endpoints.items():
        problem=historical_policy(point,model)
        if problem: cause(problem,endpoint=key,policy='preventive_optional')
    if stale: cause('unresolved_thermal_exclusions',ids=stale,state='unknown_not_resolved')
    weather,problem=available(model,clock)
    if problem:
        cause(problem)
        not_tested.append(dict(check='time_and_budget_oracle',reason=problem))
    if result['remaining_s'] < 0: cause('budget_exhausted',remaining_s=result['remaining_s'])
    run=conn.execute('SELECT mode FROM routing.runs WHERE run_id=%s',(rid,)).fetchone()
    online_problem=False
    if run and run['mode']=='online':
        now=datetime.now(timezone.utc)
        if now-iso(model['weather_fetched_at']) > timedelta(minutes=profile['weather_max_age_minutes']):
            cause('stale_weather_acquisition'); online_problem=True
        if abs((clock-now).total_seconds()) > 3600:
            cause('online_time_must_be_current'); online_problem=True
    oracle=dict(state='not_tested',reason=problem or 'interrupted_during_segment')
    counts=Counter(); zone_counts=Counter(); excluded=set()
    if request.get('on_edge'):
        not_tested.append(dict(check='graph_oracle',reason='closure_during_segment_no_escape_modelled'))
    elif weather:
        nodes,edges,ids=overlay(conn,nodes,edges,points,area,profile)
        admitted=[]
        aip_shapes=[(r.get('provider_id',r.get('code')),transform(FWD,shape(r['geometry']))) for r in model['records']['A3']]
        for edge in edges:
            line=transform(FWD,LineString(edge['coordinates'])); reasons=[]
            if blocked.intersects(line): reasons.append('restricted')
            for zone,polygon in aip_shapes:
                if polygon.intersects(line): zone_counts[zone]+=1
            history=historical_policy(line,model)
            if history: reasons.append(history)
            duration=edge_time(line,weather,profile)
            if duration is None: reasons.append('wind_infeasible')
            if reasons:
                counts.update(reasons); excluded.add(edge['id'])
            else: admitted.append(dict(edge,time_s=duration))
        start=ids['current']; target=ids['target'] if phase=='outbound' else ids['home']
        need_return=mode=='mission' and phase=='outbound'
        observation=profile['observation_s'] if need_return else 0
        oracle=minimum_mission(admitted,start,target,ids['home'],observation,result['remaining_s'],need_return)
        oracle.update(admitted_edges=len(admitted),total_edges=len(edges),elapsed_s=result['elapsed_s'])
        if oracle['outbound_s'] is None: cause('no_outbound_on_admitted_graph')
        if need_return and oracle['return_s'] is None: cause('missing_return_on_admitted_graph')
        if oracle['minimum_remaining_s'] is not None and not oracle['feasible']:
            cause('insufficient_return_budget',minimum_s=oracle['minimum_remaining_s'],remaining_s=result['remaining_s'])
        computed=result.get('minimum_remaining_mission_s')
        oracle['routing_minimum_matches']=math.isclose(computed,oracle['minimum_remaining_s'],rel_tol=1e-9,abs_tol=1e-7) if computed is not None and oracle['minimum_remaining_s'] is not None else None
        endpoint_failure=any(d['code']=='endpoint_blocked' or ('endpoint' in d and d['code'].startswith('historical_class_')) for d in details)
        oracle['proposed_rejection_contradiction']=bool(result['method']=='proposed' and not result['alternatives'] and oracle['feasible'] and not endpoint_failure and not online_problem)
    if result['reason'] and result['reason'] not in {d['code'] for d in details}: cause(result['reason'])
    codes=sorted({d['code'] for d in details})
    return dict(version='mission-diagnostics-v1',primary_reason=result['reason'],causes=details,
                other_causes=[code for code in codes if code!=result['reason']],not_tested=not_tested,
                independent_oracle=oracle,excluded_edges_by_cause=dict(counts),unique_excluded_edges=len(excluded),
                aip_edge_intersections=dict(zone_counts),counting='Causas simultáneas y arcos por causa pueden solaparse; no sumarlos como casos',
                service_health_is_not_mission_feasibility=True,
                alternative_search='Hasta tres idas × tres retornos; ausencia de segunda opción no demuestra inexistencia')
