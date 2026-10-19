"""Simulación aérea: consultas de solo lectura con extremos temporales exactos."""
import json
import math
from datetime import datetime,timedelta,timezone
from functools import lru_cache
from itertools import product

from psycopg import sql
from shapely.geometry import shape,Point,LineString,mapping
from shapely.ops import transform,unary_union

from core.aerial_data import FWD,INV,iso
from core.contracts import canonical


@lru_cache(maxsize=4)
def model_from_text(text):
    model=json.loads(text)
    model['history']=sorted([(transform(FWD,shape(r['geometry'])),(r['ordinal_class']-1)/4) for r in model['records']['A4']],key=lambda p:-p[1])
    return model


def data(conn,rid):
    row=conn.execute('''SELECT m.context #- '{records,M2}' AS context,d.lineage FROM routing.aerial_models m JOIN routing.datasets d ON d.run_id=m.run_id AND d.dataset_key='I'
        WHERE m.run_id=%s''',(rid,)).fetchone()
    if not row:raise ValueError('La publicación no contiene una red aérea')
    model=model_from_text(json.dumps(row['context'],sort_keys=True));area=shape(row['lineage'].get('flight_area',row['lineage']['aoi'])['geometry'])
    nodes={str(r['id']):r['coordinates'] for r in conn.execute('SELECT id,ST_AsGeoJSON(ST_Transform(geom,4326),15)::jsonb->\'coordinates\' AS coordinates FROM routing.nodes WHERE run_id=%s',(rid,))}
    edges=[dict(id=r['id'],source=str(r['source']),target=str(r['target']),length_km=r['length_km'],coordinates=[nodes[str(r['source'])],nodes[str(r['target'])]])
        for r in conn.execute('SELECT id,source,target,length_km FROM routing.edges WHERE run_id=%s ORDER BY id',(rid,))]
    return model,area,nodes,edges


def coordinate(value,area):
    if not isinstance(value,list) or len(value)!=2 or any(type(v) not in [int,float] or not math.isfinite(v) for v in value):raise ValueError('Coordenadas requieren [longitud, latitud] finitas')
    if not -180<=value[0]<=180 or not -90<=value[1]<=90 or not area.covers(Point(value)):raise ValueError('El punto debe estar dentro del polígono de Valparaíso')
    return value


def overlay(conn,nodes,edges,points,area,profile):
    nodes=dict(nodes);edges=list(edges);ids={};next_edge=-100;existing={(e['source'],e['target']) for e in edges}
    metric={i:Point(FWD(*c)) for i,c in nodes.items()}
    def add(s,t):
        nonlocal next_edge
        if s==t or (s,t) in existing:return
        coords=[nodes[s],nodes[t]]
        if profile.get('builder')=='aerial-grid-v2' and Point(FWD(*coords[0])).distance(Point(FWD(*coords[1])))>profile['max_link_m']+1e-6:return
        if not area.covers(LineString(coords)):return
        value=conn.execute('SELECT ST_Length(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32719))/1000 AS km',(json.dumps(dict(type='LineString',coordinates=coords)),)).fetchone()['km']
        if value<=0:return
        edges.append(dict(id=next_edge,source=s,target=t,length_km=value,coordinates=coords));next_edge-=1;existing.add((s,t))
    for name,coords in points.items():
        p=Point(FWD(*coords));near=sorted((p.distance(g),i) for i,g in metric.items())
        if near and near[0][0]<=.001:ident=near[0][1]
        else:
            ident=str(-10-len(ids));nodes[ident]=coords
            for distance,target in near[:profile['neighbours']]:
                if distance<=profile['max_link_m']:add(ident,target);add(target,ident)
            metric[ident]=p
        ids[name]=ident
    # Enlaces entre extremos de consulta: directos, verificados y no persistentes.
    for s,t in product(ids.values(),repeat=2):add(s,t)
    return nodes,edges,ids


def exposure(line,history):
    covered=LineString();value=0
    for polygon,risk in history:
        part=line.intersection(polygon).difference(covered)
        value+=part.length*risk
        covered=unary_union([covered,part])
    unknown=max(0,line.length-covered.length)
    return value+unknown,unknown


@lru_cache(maxsize=16)
def historical_coverage(polygons):
    return unary_union(polygons)


def historical_policy(geometry,model):
    """Política preventiva en metros; nunca interpreta recurrencia como fuego actual."""
    limit=model['profile'].get('max_historical_class')
    if limit is None:return None
    history=model['history']
    if any(risk>(limit-1)/4 and polygon.intersects(geometry) for polygon,risk in history):
        return 'historical_class_exceeded'
    coverage=historical_coverage(tuple(polygon for polygon,_ in history))
    if not coverage.covers(geometry):return 'historical_class_unknown'
    return None


def events_geometry(events,clock=None):
    if not isinstance(events,list) or len(events)>20:raise ValueError('Máximo 20 eventos por escenario')
    ledger={}
    for event in events:
        if not isinstance(event,dict) or not isinstance(event.get('id'),str) or not 1<=len(event['id'])<=100:raise ValueError('Evento sin ID válido')
        state=event.get('state','blocked')
        if state not in ['blocked','unknown','resolved']:raise ValueError('Estado de evento inválido')
        stamp=iso(event.get('observed_at',''))
        if stamp.utcoffset() is None:raise ValueError('Evento sin zona horaria')
        if clock is not None and stamp>clock:continue
        old=ledger.get(event['id'])
        if old and iso(old['observed_at'])>=stamp:continue
        ledger[event['id']]=dict(event,synthetic=True)
    result=[]
    for event in ledger.values():
        if event.get('state','blocked')=='resolved':continue
        geom=shape(event['geometry'])
        if geom.is_empty or not geom.is_valid or geom.geom_type not in ['Point','Polygon','MultiPolygon'] or not all(math.isfinite(v) for v in geom.bounds):raise ValueError('Geometría de evento inválida')
        west,south,east,north=geom.bounds
        if not -72<=west<=east<=-71 or not -34<=south<=north<=-33:raise ValueError('Evento fuera del entorno de estudio')
        projected=transform(FWD,geom)
        if geom.geom_type=='Point':
            radius=event.get('radius_m',250)
            if type(radius) not in [int,float] or not math.isfinite(radius) or not 0<radius<=10000:raise ValueError('Radio entre 0 y 10000 m')
            projected=projected.buffer(radius)
        result.append(projected)
    return result,list(ledger.values())


def available(model,clock,online=False):
    profile=model['profile'];rows=[w for w in model['records']['M4'] if iso(w['valid_at'])<=clock<iso(w['valid_at'])+timedelta(hours=1)]
    if not rows:return None,'missing_weather_time'
    weather=rows[0]
    if any(weather.get(k) is None for k in ['wind_speed_ms','wind_gust_ms','wind_direction_deg','temperature_c']):return None,'unknown_weather'
    if max(weather['wind_speed_ms'],weather['wind_gust_ms'])>=profile['wind_limit_ms'] or not profile['temperature_min_c']<=weather['temperature_c']<=profile['temperature_max_c']:
        return None,'weather_outside_profile'
    return weather,None


def effective_profile(base,preferences):
    if preferences is None:preferences={}
    if not isinstance(preferences,dict) or set(preferences)-{'budget_s','wind_limit_ms','detour_factor','max_historical_class'}:raise ValueError('Preferencias desconocidas')
    profile=dict(base);profile['budget_s']=base['flight_minutes']*60*(1-base['reserve_fraction'])
    limit=preferences.get('max_historical_class')
    if limit is not None and (type(limit) is not int or not 1<=limit<=5):raise ValueError('Clase histórica máxima requiere un entero entre 1 y 5 o null')
    profile['max_historical_class']=limit
    for key,limit,minimum in [('budget_s',profile['budget_s'],0),('wind_limit_ms',base['wind_limit_ms'],0),('detour_factor',base['detour_factor'],1)]:
        if key not in preferences:continue
        value=preferences[key]
        if type(value) not in [int,float] or not math.isfinite(value) or value>limit or value<minimum or (minimum==0 and value==0):raise ValueError('Preferencia fuera del rango permitido: '+key)
        profile[key]=value
    return profile


def restrictions(model,clock,events):
    closed,ledger=events_geometry(events,clock)
    closed.extend(transform(FWD,shape(r['geometry'])) for r in model['records']['A3'])
    unknown=[]
    for r in model['records']['A2']:
        age=clock-iso(r['acquired_at'])
        if age<timedelta(0) or r.get('state')=='resolved':continue
        if model['profile'].get('builder')=='aerial-grid-v2' or age<=timedelta(hours=model['profile']['thermal_window_hours']):
            closed.append(transform(FWD,shape(r['geometry'])))
            if age>timedelta(hours=model['profile']['thermal_window_hours']):unknown.append(r.get('provider_id'))
    return unary_union(closed),ledger,unknown


def edge_time(line,weather,profile):
    a,b=line.coords[0],line.coords[-1];dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
    if length==0:return 0
    angle=math.radians(weather['wind_direction_deg']);wx=-weather['wind_speed_ms']*math.sin(angle);wy=-weather['wind_speed_ms']*math.cos(angle)
    parallel=(wx*dx+wy*dy)/length;cross2=max(0,wx*wx+wy*wy-parallel*parallel)
    if cross2>=profile['air_speed_ms']**2:return None
    speed=math.sqrt(profile['air_speed_ms']**2-cross2)+parallel
    return line.length/speed if speed>0 else None


def graph_query(conn,edges,cost_key):
    payload=[dict(id=e['id'],source=int(e['source']),target=int(e['target']),cost=e[cost_key]) for e in edges]
    if any(not math.isfinite(e['cost']) or e['cost']<=0 for e in payload):raise ValueError('Costo de arco inválido')
    literal=sql.Literal(json.dumps(payload,allow_nan=False)).as_string(conn)
    return f'SELECT id,source,target,cost,-1::float8 AS reverse_cost FROM jsonb_to_recordset({literal}::jsonb) AS e(id bigint,source bigint,target bigint,cost float8)'


def paths(conn,edges,source,target,k=3,reference=False):
    if source==target:return [dict(edge_ids=[],node_ids=[source],length_km=0,time_s=0,exposure_m=0,unknown_m=0,coordinates=[])]
    if not edges:return []
    query=graph_query(conn,edges,'length_km' if reference else 'time_s');by_id={e['id']:e for e in edges}
    if reference:
        def dijkstra(excluded=None):
            q=query if excluded is None else graph_query(conn,[e for e in edges if e['id']!=excluded],'length_km')
            return conn.execute('SELECT edge,agg_cost FROM pgr_dijkstra(%s,%s::bigint,%s::bigint,true) ORDER BY path_seq',(q,int(source),int(target))).fetchall()
        first=dijkstra();sequences=[]
        if first:
            sequence=[r['edge'] for r in first if r['edge']!=-1];sequences.append((sequence,first[-1]['agg_cost']))
            alternatives=[]
            for edge in sequence:
                candidate=dijkstra(edge)
                if candidate:alternatives.append(([r['edge'] for r in candidate if r['edge']!=-1],candidate[-1]['agg_cost']))
            if alternatives:
                best=min(alternatives,key=lambda p:(p[1],p[0]));sequences.append(best)
    else:
        rows=conn.execute('SELECT path_id,edge,agg_cost FROM pgr_ksp(%s,%s::bigint,%s::bigint,%s,true) ORDER BY path_id,path_seq',(query,int(source),int(target),k)).fetchall()
        grouped={}
        for r in rows:
            entry=grouped.setdefault(r['path_id'],[[],0]);entry[1]=r['agg_cost']
            if r['edge']!=-1:entry[0].append(r['edge'])
        sequences=list(grouped.values())
    result=[];seen=set()
    for sequence,agg in sequences:
        if not sequence or tuple(sequence) in seen:continue
        seen.add(tuple(sequence));steps=[by_id[i] for i in sequence]
        if steps[0]['source']!=source or steps[-1]['target']!=target or any(a['target']!=b['source'] for a,b in zip(steps,steps[1:])):raise RuntimeError('Cadena aérea discontinua')
        cost=sum(e['length_km'] if reference else e['time_s'] for e in steps)
        if not math.isclose(cost,agg,abs_tol=1e-8,rel_tol=1e-10):raise RuntimeError('Costo pgRouting inconsistente')
        coords=[]
        for e in steps:coords.extend(e['coordinates'][0 if not coords else 1:])
        result.append(dict(edge_ids=[str(e['id']) for e in steps],node_ids=[source]+[e['target'] for e in steps],coordinates=coords,
            length_km=sum(e['length_km'] for e in steps),time_s=sum(e.get('time_s',0) for e in steps),
            exposure_m=sum(e.get('exposure_m',0) for e in steps),unknown_m=sum(e.get('unknown_m',0) for e in steps)))
    return result


def calculate(conn,rid,request):
    if not isinstance(request,dict):raise ValueError('Solicitud JSON inválida')
    model,area,nodes,edges=data(conn,rid);profile=effective_profile(model['profile'],request.get('preferences'))
    model=dict(model,profile=profile)
    study=shape(model.get('study_geometry',mapping(area)));v2=profile.get('builder')=='aerial-grid-v2'
    origin=coordinate(request.get('origin'),area);target=coordinate(request.get('destination'),study)
    if not study.covers(Point(origin)) and not any(b.get('candidate',True) and Point(FWD(*origin)).distance(transform(FWD,shape(b['geometry'])))<=.001 for b in model['records']['M1']):raise ValueError('Origen externo permitido solo en las cuatro bases aprobadas')
    mode=request.get('mode','mission');method=request.get('method','proposed');phase=request.get('phase','outbound')
    if mode not in ['mission','trip'] or method not in ['proposed','reference'] or phase not in ['outbound','return','emergency_return']:raise ValueError('Modo/método/fase inválido')
    if mode=='trip' and phase!='outbound':raise ValueError('Las fases de regreso requieren modo misión')
    elapsed=request.get('elapsed_s',0)
    if type(elapsed) not in [int,float] or not math.isfinite(elapsed) or elapsed<0:raise ValueError('Tiempo consumido inválido')
    clock=iso(request.get('time') or model['reference_time'])
    if clock.utcoffset() is None:raise ValueError('La hora requiere zona horaria')
    closed,ledger=events_geometry(request.get('events',[]),clock)
    position=coordinate(request.get('position',origin),area)
    known=list(nodes.values())+[origin,target]
    if 'position' in request and not any(Point(FWD(*position)).distance(Point(FWD(*p)))<=.001 for p in known):raise ValueError('La replanificación discreta requiere un nodo o extremo de la misión')
    remaining=profile['budget_s']-elapsed
    response=dict(type='FeatureCollection',features=[],run_id=str(rid),status='no_route',reason=None,alternatives=[],
        origin=origin,destination=target,position=position,mode=mode,method=method,phase=phase,time=clock.isoformat(),elapsed_s=elapsed,
        remaining_s=remaining,events=ledger,clearance_verified=False,operationally_certified=False,
        effective_profile=profile,temporal_model='static_at_selected_hour',
        warnings=['Simulación académica; despeje vertical no verificado','AIP ENR 5.1: selección espacial; ver reporte de formas y excepciones','El viento a 10 m es una aproximación, no una medición a altura de vuelo'])
    if request.get('on_edge'):
        response.update(status='interrupted',reason='closure_during_segment_no_escape_modelled');return response
    nodes,edges,ids=overlay(conn,nodes,edges,dict(home=origin,target=target,current=position),area,profile)
    s=ids['current'];t=ids['home'] if phase!='outbound' else ids['target'];home=ids['home']
    refs=paths(conn,edges,s,t,reference=True)
    response['reference']=[dict(length_km=p['length_km'],edge_ids=p['edge_ids'],coordinates=p['coordinates']) for p in refs]
    if method=='reference':
        response['warnings'].append('Referencia matemática por distancia: no filtra amenazas ni autonomía al generar; misión incluye regreso')
        backs=paths(conn,edges,t,home,reference=True) if v2 and mode=='mission' and phase=='outbound' else [None]
        pairs=sorted([(p,q) for p,q in product(refs,backs)],key=lambda pair:(pair[0]['length_km']+(pair[1]['length_km'] if pair[1] else 0),pair[0]['edge_ids'],pair[1]['edge_ids'] if pair[1] else []))
        seen=set()
        for p,q in pairs:
            sig=tuple(p['edge_ids'])
            if sig in seen:continue
            seen.add(sig);response['alternatives'].append(dict(rank=len(seen),outbound=p,return_path=q,length_km=p['length_km']+(q['length_km'] if q else 0),time_s=None,exposure_m=None,observation_s=profile['observation_s'] if q else 0,mission_completed=False))
            if len(seen)==2:break
        response['status']='ready' if refs else 'no_route';response['reason']=None if refs else 'disconnected'
        return finish(response,nodes)
    if remaining<0:response.update(status='not_feasible',reason='budget_exhausted');return response
    run=conn.execute('SELECT mode FROM routing.runs WHERE run_id=%s',(rid,)).fetchone()
    if run and run['mode']=='online':
        fetched=iso(model['weather_fetched_at'])
        now=datetime.now(timezone.utc)
        if now-fetched>timedelta(minutes=profile['weather_max_age_minutes']):response.update(status='unknown',reason='stale_weather_acquisition');return response
        if abs((clock-now).total_seconds())>3600:response.update(status='unknown',reason='online_time_must_be_current');return response
    weather,problem=available(model,clock)
    if problem:response.update(status='unknown' if problem.startswith(('missing','unknown')) else 'not_feasible',reason=problem);return response
    blocked,ledger,stale_thermal=restrictions(model,clock,request.get('events',[]));eligible=[]
    response['thermal_unknown_ids']=stale_thermal
    if any(blocked.intersects(Point(FWD(*nodes[i]))) for i in {s,t,home} if mode=='mission' or i in {s,t}):
        response.update(reason='endpoint_blocked');return response
    for ident in {s,t,home} if mode=='mission' else {s,t}:
        problem=historical_policy(Point(FWD(*nodes[ident])),model)
        if problem:response.update(reason=problem);return response
    response['excluded_edges_by_reason']={}
    for e in edges:
        line=transform(FWD,LineString(e['coordinates']))
        if blocked.intersects(line):continue
        problem=historical_policy(line,model)
        if problem:
            counts=response['excluded_edges_by_reason'];counts[problem]=counts.get(problem,0)+1
            continue
        time_s=edge_time(line,weather,profile)
        if time_s is None:continue
        risk,unknown=exposure(line,model['history'])
        eligible.append(dict(**e,time_s=time_s,exposure_m=risk,unknown_m=unknown))
    out=paths(conn,eligible,s,t,k=profile['alternatives'])
    back=paths(conn,eligible,t,home,k=profile['alternatives']) if mode=='mission' and phase=='outbound' else [None]
    if not out or not back:response.update(reason='no_outbound_or_return');return response
    observation=profile['observation_s'] if mode=='mission' and phase=='outbound' else 0
    candidates=[]
    for p,q in product(out,back):
        candidates.append(dict(outbound=p,return_path=q,length_km=p['length_km']+(q['length_km'] if q else 0),
            time_s=p['time_s']+(q['time_s'] if q else 0)+observation,observation_s=observation,
            exposure_m=p['exposure_m']+(q['exposure_m'] if q else 0),unknown_m=p['unknown_m']+(q['unknown_m'] if q else 0),
            mission_completed=mode=='mission' and phase!='emergency_return'))
    shortest=min(p['time_s'] for p in candidates);response['minimum_remaining_mission_s']=shortest
    allowed=[p for p in candidates if p['time_s']<=remaining+1e-9 and p['time_s']<=profile['detour_factor']*shortest+1e-9]
    allowed.sort(key=lambda p:(p['exposure_m'],p['time_s'],p['outbound']['edge_ids'],p['return_path']['edge_ids'] if p['return_path'] else []))
    chosen=[];seen=set()
    for p in allowed:
        signature=tuple(p['outbound']['edge_ids']) if v2 else (tuple(p['outbound']['edge_ids']),tuple(p['return_path']['edge_ids']) if p['return_path'] else ())
        if signature not in seen:seen.add(signature);chosen.append(dict(p,rank=len(chosen)+1))
        if len(chosen)==(2 if v2 else profile['alternatives']):break
    response['alternatives']=chosen;response['status']='ready' if chosen else 'not_feasible'
    response['reason']=None if chosen else 'insufficient_return_budget'
    response['weather']=weather;response['candidate_pairs_examined']=len(candidates)
    response['search_limited']=True
    response['alternative_count_note']='Menos de dos idas distintas entre los candidatos examinados' if len(chosen)<2 else None
    response['diversity_note']='Alternativas distintas; no se garantiza independencia geográfica ni óptimo global de exposición'
    return finish(response,nodes)


def finish(response,nodes):
    alternatives=response['alternatives']
    for option in alternatives:
        for role,path in [('outbound',option['outbound']),('return',option.get('return_path'))]:
            if path and len(path['coordinates'])>=2:
                response['features'].append(dict(type='Feature',geometry=dict(type='LineString',coordinates=path['coordinates']),properties=dict(rank=option['rank'],role=role,length_km=path['length_km'])))
        if alternatives:
            first=LineString(alternatives[0]['outbound']['coordinates']) if len(alternatives[0]['outbound']['coordinates'])>=2 else LineString()
            current=LineString(option['outbound']['coordinates']) if len(option['outbound']['coordinates'])>=2 else LineString()
            metric=transform(FWD,current);shared=metric.intersection(transform(FWD,first).buffer(50)).length
            option['within_50m_of_first_fraction']=min(1,shared/metric.length) if metric.length else 0
    response['waypoints']=[dict(id=i,coordinates=nodes[i]) for i in dict.fromkeys(n for p in alternatives for path in [p['outbound'],p.get('return_path')] if path for n in path['node_ids'])]
    return response


def map_data(conn,rid):
    model,area,nodes,edges=data(conn,rid)
    node_rows=conn.execute('SELECT id,kind FROM routing.nodes WHERE run_id=%s ORDER BY id',(rid,)).fetchall()
    features=[dict(type='Feature',geometry=dict(type='Point',coordinates=nodes[str(r['id'])]),properties=dict(id=str(r['id']),kind=r['kind'])) for r in node_rows]
    features.extend(dict(type='Feature',geometry=dict(type='LineString',coordinates=e['coordinates']),properties=dict(id=str(e['id']),kind='corridor')) for e in edges if int(e['source'])<int(e['target']))
    catalogue=model['records']['M1'];bases=[b for b in catalogue if b.get('candidate',True)];chosen=next((b for b in bases if b['provider_id']=='104'),bases[0])
    # Ejemplos cercanos a la base, ordenados por distancia; no prometen admisibilidad.
    goals=sorted([r for r in features if r['geometry']['type']=='Point' and r['properties']['kind']=='vigilancia'],key=lambda r:Point(FWD(*r['geometry']['coordinates'])).distance(Point(FWD(*chosen['geometry']['coordinates']))))
    layers={key:[dict(type='Feature',geometry=r['geometry'],properties={k:v for k,v in r.items() if k not in ['geometry','original_record','conditions']}) for r in model['records'][key]] for key in ['A2','A3','A4']}
    layers['M2']=[dict(type='Feature',geometry=r['geometry'],properties=dict(provider_id=r['provider_id'],category=r['category'],attributes=r['attributes'],clipped_area_ha=r['clipped_area_ha'],display_simplification_m=3)) for r in conn.execute('''SELECT provider_id,category,attributes,clipped_area_ha,
        ST_AsGeoJSON(ST_Transform(ST_SimplifyPreserveTopology(geom,3),4326))::jsonb AS geometry FROM routing.landcover WHERE run_id=%s''',(rid,))]
    return dict(type='FeatureCollection',features=features,area=model.get('study_geometry',mapping(area)),flight_area=mapping(area),base_catalogue=catalogue,bases=bases,default_origin=chosen['geometry']['coordinates'],
        examples=[dict(coordinates=f['geometry']['coordinates'],id=f['properties']['id']) for f in goals[:8]],reference_time=model['reference_time'],profile=model['profile'],layers=layers,
        elevation=model['records']['M3'],weather=model['records']['M4'],weather_hazards=model['records']['A1'],sources=['S1','S2','S3','S4','S5','S6','S7'],clearance_verified=False)


def audit_aerial(conn,rid):
    model,area,nodes,edges=data(conn,rid);bases=[b for b in model['records']['M1'] if b.get('candidate',True)]
    if any(not area.covers(Point(c)) for c in nodes.values()) or any(not area.covers(LineString(e['coordinates'])) for e in edges):raise ValueError('Red aérea fuera del AOI')
    if any(not area.covers(shape(b['geometry'])) for b in bases):raise ValueError('Base aérea fuera del AOI')
    origin=next((b for b in bases if b['provider_id']=='104'),bases[0])['geometry']['coordinates'];examples=[]
    goals=map_data(conn,rid)['examples']
    for goal in goals[:3]:
        result=calculate(conn,rid,dict(origin=origin,destination=goal['coordinates'],mode='mission'))
        examples.append(dict(destination=goal['coordinates'],status=result['status'],reason=result['reason'],alternatives=len(result['alternatives']),
            length_km=result['alternatives'][0]['length_km'] if result['alternatives'] else None))
    counts={k:len(v) for k,v in model['records'].items()}
    counts['M2']=conn.execute('SELECT count(*) AS n FROM routing.landcover WHERE run_id=%s',(rid,)).fetchone()['n']
    return dict(nodes=len(nodes),directed_edges=len(edges),bases=len(bases),base_inside=True,clearance_verified=False,examples=examples,
                routing_ready=True,source_counts=counts)
