"""Misiones 3D con Yen, referencia Dijkstra y patrullas de 1–3 objetivos."""
import heapq
import hashlib
import itertools
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from shapely.geometry import Point, LineString, shape, mapping
from shapely.ops import transform, unary_union

from core.contracts import canonical
from core.aerial_data import FWD, INV, iso
from core.aerial_routing import edge_time, events_geometry, graph_query
from core.patrol_data import graph, Obstacles, make_edge
from core.surface import Surface, observation


def effective_profile(base, preferences):
    if preferences is None:preferences={}
    rules={'budget_eq_s':(0,base['flight_minutes']*60*(1-base['reserve_fraction'])),
           'wind_limit_ms':(0,base['wind_limit_ms']),'detour_factor':(1,base['detour_factor']),
           'minimum_coverage':(base['minimum_coverage'],1),'climb_factor':(1.25,2)}
    if not isinstance(preferences,dict) or set(preferences)-set(rules):raise ValueError('Preferencias desconocidas')
    p=dict(base,budget_eq_s=rules['budget_eq_s'][1])
    for k,v in preferences.items():
        low,high=rules[k]
        if type(v) not in (int,float) or not math.isfinite(v) or not low<=v<=high or v==0:raise ValueError('Preferencia fuera de rango: '+k)
        p[k]=v
    return p


def weather_at(rows, clock):
    ordered=sorted(rows,key=lambda w:iso(w['valid_at']))
    before=[w for w in ordered if iso(w['valid_at'])<=clock]
    if not before or clock>=iso(ordered[-1]['valid_at'])+timedelta(hours=1):return None
    a=before[-1]; after=next((w for w in ordered if iso(w['valid_at'])>clock),None)
    if clock>=iso(a['valid_at'])+timedelta(hours=1) and after is None:return None
    if after is None:return dict(a)
    if iso(after['valid_at'])-iso(a['valid_at'])!=timedelta(hours=1):
        return dict(a) if clock==iso(a['valid_at']) else None
    f=(clock-iso(a['valid_at'])).total_seconds()/3600
    result=dict(a)
    for speed,direction in [('wind_speed_ms','wind_direction_deg'),('wind_100_ms','direction_100_deg')]:
        if any(w.get(k) is None for w in (a,after) for k in (speed,direction)):
            result[speed]=result[direction]=None;continue
        vectors=[(-w[speed]*math.sin(math.radians(w[direction])),-w[speed]*math.cos(math.radians(w[direction]))) for w in (a,after)]
        x,y=[(1-f)*vectors[0][i]+f*vectors[1][i] for i in range(2)]
        result[speed]=math.hypot(x,y);result[direction]=math.degrees(math.atan2(-x,-y))%360
    for k in ['temperature_c','relative_humidity_pct','precipitation_mm','visibility_m']:
        result[k]=None if a.get(k) is None or after.get(k) is None else (1-f)*a[k]+f*after[k]
    result['wind_gust_ms']=max(a['wind_gust_ms'],after['wind_gust_ms']) if all(w.get('wind_gust_ms') is not None for w in (a,after)) else None
    return result


def weather_problem(w,p):
    keys=['wind_speed_ms','wind_direction_deg','wind_100_ms','direction_100_deg','wind_gust_ms','temperature_c','precipitation_mm','visibility_m']
    if w is None:return 'missing_weather_time'
    if any(type(w.get(k)) not in (float,int) or not math.isfinite(w[k]) for k in keys):return 'unknown_weather'
    if max(w['wind_speed_ms'],w['wind_100_ms'],w['wind_gust_ms'])>=p['wind_limit_ms']:return 'wind_outside_profile'
    if not p['temperature_min_c']<=w['temperature_c']<=p['temperature_max_c']:return 'temperature_outside_profile'
    if w['precipitation_mm']>=p['precipitation_limit_mm']:return 'precipitation_outside_profile'
    if w['visibility_m']<p['visibility_min_m']:return 'visibility_outside_profile'
    return None


def weather_window(rows,clock,p):
    end=clock+timedelta(seconds=p['budget_eq_s'])
    stamps={clock,end};cursor=clock.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
    while cursor<end:stamps.add(cursor);cursor+=timedelta(hours=1)
    result=[weather_at(rows,t) for t in sorted(stamps)]
    problem=next((weather_problem(w,p) for w in result if weather_problem(w,p)),None)
    # Conservar también extremos de pronóstico para una envolvente conservadora de vectores.
    hours=[w for w in rows if clock.replace(minute=0,second=0,microsecond=0)<=iso(w['valid_at'])<=end.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)]
    return result+hours,problem


def duration(edge,weather,p):
    a,b=edge['coordinates'];dz=b[2]-a[2]
    horizontal=0.0
    if edge['horizontal_km']:
        # Evaluar ambos niveles disponibles, sin inventar una medición local.
        times=[];dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
        for speed,direction in [('wind_speed_ms','wind_direction_deg'),('wind_100_ms','direction_100_deg')]:
            angle=math.radians(weather[direction]);wx=-weather[speed]*math.sin(angle);wy=-weather[speed]*math.cos(angle)
            parallel=(wx*dx+wy*dy)/length;cross2=max(0,wx*wx+wy*wy-parallel*parallel)
            if cross2>=p['air_speed_ms']**2:return None
            ground_speed=math.sqrt(p['air_speed_ms']**2-cross2)+parallel
            if ground_speed<=0:return None
            times.append(length/ground_speed)
        horizontal=max(times)
    vertical=abs(dz)/(p['climb_ms'] if dz>0 else p['descent_ms'])
    seconds=max(horizontal,vertical)
    return seconds,seconds*(p['climb_factor'] if dz>0 else 1)


def restriction_geometry(context,clock,events):
    closed,ledger=events_geometry(events,clock)
    closed.extend(transform(FWD,shape(r['geometry'])) for r in context['records']['A3'])
    unknown=[]
    for r in context['records']['A2']:
        age=clock-iso(r['acquired_at'])
        if age<timedelta(0) or r.get('state')=='resolved':continue
        closed.append(transform(FWD,shape(r['geometry'])))
        if age>timedelta(hours=24):unknown.append(r.get('provider_id'))
    return unary_union(closed),ledger,unknown


def check_edge(edge,p,blocked,cache=None):
    if edge['blocked_obstacle']:return 'obstacle_intersection'
    if not edge['surface_known']:return 'surface_unknown'
    if not edge.get('terminal_vertical') and edge['clearance_m']<p['minimum_clearance_m']:return 'surface_clearance'
    key=tuple(sorted(tuple(x[:2]) for x in edge['coordinates']))
    if cache is not None and key in cache:intersects=cache[key]
    else:
        geometry=LineString([x[:2] for x in edge['coordinates']]) if edge['horizontal_km'] else Point(edge['coordinates'][0][:2])
        intersects=blocked.intersects(geometry)
        if cache is not None:cache[key]=intersects
    if intersects:return 'restricted_airspace_or_event'
    return None


def enrich(edges,p,weather,blocked):
    eligible=[];causes=Counter();block_cache={};horizontal_cache={}
    for e in edges:
        problem=check_edge(e,p,blocked,block_cache)
        if problem:causes[problem]+=1;continue
        a,b=e['coordinates'];key=(tuple(a[:2]),tuple(b[:2]))
        if key not in horizontal_cache:
            flat=dict(e,coordinates=[a[:2]+[0],b[:2]+[0]])
            times=[duration(flat,w,p) for w in weather]
            horizontal_cache[key]=None if any(t is None for t in times) else max(t[0] for t in times)
        horizontal=horizontal_cache[key]
        if horizontal is None:causes['wind_infeasible']+=1;continue
        dz=b[2]-a[2];seconds=max(horizontal,abs(dz)/(p['climb_ms'] if dz>0 else p['descent_ms']))
        eq=seconds*(p['climb_factor'] if dz>0 else 1)
        obstacle_risk=max(0,1-e['obstacle_distance_m']/100)
        surface_risk=0 if e.get('terminal_vertical') else min(1,max(0,(80-e['clearance_m'])/40))
        risk=max(obstacle_risk,surface_risk)
        eligible.append(dict(e,time_s=seconds,eq_s=eq,risk=risk,cost=eq*(1+risk)))
    return eligible,dict(causes)


def normalize_request(request,p,context):
    if not isinstance(request,dict) or set(request)-{'origin','objectives','time','preferences','events','method'}:raise ValueError('Campos de misión desconocidos')
    study=transform(FWD,shape(context['study_geometry']));area=transform(FWD,shape(context['flight_geometry']))
    def coord(value,geometry):
        if not isinstance(value,list) or len(value)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in value):raise ValueError('Coordenadas requieren [longitud,latitud]')
        if not -180<=value[0]<=180 or not -90<=value[1]<=90:raise ValueError('Coordenadas fuera de WGS84')
        point=Point(FWD(*value))
        if not geometry.covers(point):raise ValueError('Punto fuera del área permitida')
        return point
    origin=coord(request.get('origin'),area)
    objectives=request.get('objectives')
    if not isinstance(objectives,list) or not 1<=len(objectives)<=p['max_objectives']:raise ValueError('Seleccionar entre uno y tres objetivos')
    goals=[]
    for i,goal in enumerate(objectives):
        if isinstance(goal,list):goal={'center':goal}
        if not isinstance(goal,dict) or set(goal)-{'id','center','radius_m'}:raise ValueError('Objetivo inválido')
        point=coord(goal.get('center'),study);radius=goal.get('radius_m',p['sector_radius_m'])
        if type(radius) not in (int,float) or not math.isfinite(radius) or not 10<=radius<=250:raise ValueError('Radio de objetivo entre 10 y 250 m')
        name=goal.get('id',str(i+1))
        if not isinstance(name,str) or not 1<=len(name)<=80 or name in ('home','launch'):raise ValueError('ID de objetivo inválido')
        goals.append(dict(id=name,point=point,sector=point.buffer(radius).intersection(study),center=goal['center'],radius_m=radius))
    if len({g['id'] for g in goals})!=len(goals) or len({(g['point'].x,g['point'].y) for g in goals})!=len(goals):raise ValueError('Objetivos duplicados')
    clock=iso(request.get('time',''))
    if clock.utcoffset() is None:raise ValueError('Fecha requiere zona horaria')
    return origin,goals,clock.astimezone(timezone.utc)


def overlay(states,edges,origin,goals,surface,obstacles,p,area):
    states=dict(states);extra=[];terminal={};next_id=-10
    coordinates_to_state={tuple(round(v,6) for v in n['coordinates']):ident for ident,n in states.items()}
    level_order={level:i for i,level in enumerate(p['levels_m'])}
    anchors={}
    for n in states.values():anchors.setdefault(n['anchor_id'],[]).append(n['id'])
    def add(s,t,terminal_vertical=False):
        a,b=states[s]['coordinates'],states[t]['coordinates']
        if s==t or math.dist(a,b)<=1e-9:return
        line=LineString([a[:2],b[:2]])
        if line.length>p['max_link_m'] or not area.covers(line):return
        e=make_edge(-100-len(extra),s,t,a,b,surface,obstacles,p)
        if terminal_vertical:
            # Ascenso/aterrizaje local: no aplicar el despeje de crucero al suelo.
            vals,known=surface.pixels(Point(a[:2]).buffer(p['corridor_radius_m']))
            ground=min(a[2],b[2]);e.update(terminal_vertical=True,surface_known=bool(known),
                clearance_m=0,blocked_obstacle=bool(e['blocked_obstacle'] or (known and max(vals)>ground+10)))
        extra.append(e)
    for name,point in [('home',origin)]+[(g['id'],g['point']) for g in goals]:
        z=surface.height(point.x,point.y)
        if z is None:raise ValueError('Superficie desconocida en '+name)
        ids=[]
        for level in p['levels_m']:
            coordinate_key=tuple(round(v,6) for v in [point.x,point.y,z+level])
            if coordinate_key in coordinates_to_state:
                ids.append(coordinates_to_state[coordinate_key]);continue
            ident=next_id;next_id-=1;ids.append(ident)
            states[ident]=dict(id=ident,anchor_id='temporary:'+name,kind='observation' if name!='home' else 'navigation',
                              surface_m=z,surface_offset_m=level,coordinates=[point.x,point.y,z+level])
            coordinates_to_state[coordinate_key]=ident
        terminal[name]=ids
        near=sorted(anchors,key=lambda key:math.dist(states[anchors[key][0]]['coordinates'][:2],(point.x,point.y)))[:8]
        for s in ids:
            for key in near:
                for t in anchors[key]:
                    if abs(level_order[states[s]['surface_offset_m']]-level_order[states[t]['surface_offset_m']])<=1:add(s,t);add(t,s)
        for s,t in zip(ids,ids[1:]):add(s,t);add(t,s)
    homes=terminal.pop('home');home=next_id
    z=surface.height(origin.x,origin.y)
    states[home]=dict(id=home,anchor_id='launch',kind='launch',surface_m=z,surface_offset_m=0,coordinates=[origin.x,origin.y,z])
    for s in homes:add(home,s,True);add(s,home,True)
    # Conexiones directas entre extremos temporales, sujetas a las mismas reglas.
    groups=[homes]+list(terminal.values())
    for a,b in itertools.combinations(groups,2):
        for s in a:
            for t in b:
                if abs(level_order[states[s]['surface_offset_m']]-level_order[states[t]['surface_offset_m']])<=1:add(s,t);add(t,s)
    return states,list(edges)+extra,home,terminal


def reverse_distances(edges,home,turn_s=0):
    adjacency={}
    for e in edges:adjacency.setdefault(e['target'],[]).append((e['source'],e['eq_s']+turn_s))
    distance={home:0};queue=[(0,home)]
    while queue:
        cost,n=heapq.heappop(queue)
        if cost!=distance[n]:continue
        for target,w in adjacency.get(n,[]):
            value=cost+w
            if value<distance.get(target,float('inf')):distance[target]=value;heapq.heappush(queue,(value,target))
    return distance


def path_signature(path,states):
    return tuple(k for k,_ in itertools.groupby(tuple(round(v,3) for v in states[n]['coordinates'][:2]) for n in path['node_ids']))


class Paths:
    def __init__(self,conn,edges,states,reference,p,rid=None):
        self.conn=conn;self.edges={e['id']:e for e in edges};self.states=states;self.reference=reference;self.p=p;self.cache={}
        # IDs positivos compactos solo dentro de pgRouting. Algunos caminos KSP con
        # ambos extremos negativos se devuelven rotados en pgRouting 3.8.
        self.vertices={ident:i+1 for i,ident in enumerate(sorted(states))}
        self.edge_ids={i+1:e['id'] for i,e in enumerate(edges)}
        self.reverse_edge_ids={v:k for k,v in self.edge_ids.items()}
        # La referencia usa directamente las tablas indexadas. Repetir Dijkstra
        # para D2 no debe volver a serializar/cargar todo el grafo en JSON.
        from uuid import UUID
        try:UUID(str(rid));persisted=True
        except ValueError:persisted=False
        self.query=None
        if not (reference and persisted):
            payload=[dict(id=i+1,source=self.vertices[e['source']],target=self.vertices[e['target']],
                          value=e['flight_km'] if reference else e['cost']) for i,e in enumerate(edges)]
            self.query=graph_query(conn,payload,'value') if edges else None
        if reference and persisted:
            from psycopg import sql
            used=set(states);candidate=2**63-1
            self.vertices={n:n for n in states if n>0}
            for n in sorted(n for n in states if n<0):
                while candidate in used:candidate-=1
                self.vertices[n]=candidate;used.add(candidate);candidate-=1
            used=set(self.edges);candidate=2**63-1;self.edge_ids={ident:ident for ident in self.edges if ident>0}
            extra=[]
            for e in edges:
                if e['id']>0:continue
                while candidate in used:candidate-=1
                self.edge_ids[candidate]=e['id'];used.add(candidate)
                extra.append(dict(id=candidate,source=self.vertices[e['source']],target=self.vertices[e['target']],value=e['flight_km']));candidate-=1
            self.reverse_edge_ids={v:k for k,v in self.edge_ids.items()}
            literal=sql.Literal(str(rid)).as_string(conn)
            self.query=f'SELECT id,source,target,flight_km AS cost,-1::float8 AS reverse_cost FROM routing.flight_edges WHERE run_id={literal}::uuid'
            if extra:self.query+=' UNION ALL '+graph_query(conn,extra,'value')
        self.limited=False
        self.physical_edges={}
        if reference:
            for e in edges:
                key=tuple(tuple(round(v,3) for v in states[n]['coordinates'][:2]) for n in (e['source'],e['target']))
                self.physical_edges.setdefault(key,[]).append(self.reverse_edge_ids[e['id']])

    def get(self,s,t):
        if (s,t) in self.cache:return self.cache[s,t]
        if s==t:return [dict(edge_ids=[],node_ids=[s],length_km=0,cost=0)]
        if not self.query:return []
        def dijkstra(excluded=None):
            query=self.query if excluded is None else 'SELECT * FROM ('+self.query+') q WHERE id NOT IN ('+','.join(str(i) for i in excluded)+')'
            rows=self.conn.execute('SELECT edge,agg_cost FROM pgr_dijkstra(%s,%s::bigint,%s::bigint,true) ORDER BY path_seq',(query,self.vertices[s],self.vertices[t])).fetchall()
            return [self.edge_ids[r['edge']] for r in rows if r['edge']!=-1]
        if self.reference:
            first=dijkstra();sequences=[first] if first else []
            for edge in first:
                candidate=dijkstra([self.reverse_edge_ids[edge]])
                if candidate:sequences.append(candidate)
            def physical(sequence):
                return path_signature(dict(node_ids=[s]+[self.edges[i]['target'] for i in sequence]),self.states)
            if first and len({physical(sequence) for sequence in sequences})<2:
                # Una exclusión de arco 3D puede cambiar solo de altura. Buscar
                # entonces desvíos excluyendo sus copias del mismo corredor XY.
                # El único costo de todas las llamadas sigue siendo distancia.
                keys=set()
                for ident in first:
                    e=self.edges[ident]
                    key=tuple(tuple(round(v,3) for v in self.states[n]['coordinates'][:2]) for n in (e['source'],e['target']))
                    if key[0]!=key[1]:keys.add(key)
                for key in sorted(keys):
                    candidate=dijkstra(self.physical_edges[key])
                    if candidate:sequences.append(candidate)
        else:
            grouped={}
            from psycopg.errors import QueryCanceled
            try:
                rows=self.conn.execute('SELECT path_id,edge FROM pgr_ksp(%s,%s::bigint,%s::bigint,%s,true) ORDER BY path_id,path_seq',
                    (self.query,self.vertices[s],self.vertices[t],self.p['candidates_per_leg'])).fetchall()
            except QueryCanceled:
                self.limited=True;self.cache[s,t]=[];return []
            for r in rows:
                if r['edge']!=-1:grouped.setdefault(r['path_id'],[]).append(self.edge_ids[r['edge']])
            sequences=list(grouped.values())
            if len(sequences)==self.p['candidates_per_leg']:self.limited=True
        result=[];seen=set()
        for sequence in sequences:
            if tuple(sequence) in seen:continue
            seen.add(tuple(sequence));es=[self.edges[i] for i in sequence]
            if not es or es[0]['source']!=s or es[-1]['target']!=t or any(a['target']!=b['source'] for a,b in zip(es,es[1:])):
                raise RuntimeError(f'Ruta discontinua {s}->{t}: {[(e["id"],e["source"],e["target"]) for e in es]}')
            result.append(dict(edge_ids=sequence,node_ids=[s]+[e['target'] for e in es],length_km=sum(e['flight_km'] for e in es),
                               cost=sum(e['flight_km'] if self.reference else e['cost'] for e in es)))
        result.sort(key=lambda r:(r['cost'],r['edge_ids']))
        physical=[];seen=set()
        for r in result:
            sig=path_signature(r,self.states)
            if sig in seen:continue
            seen.add(sig);physical.append(r)
            if len(physical)>=(2 if self.reference else self.p['candidates_per_leg']):break
        self.cache[s,t]=physical
        return physical


def compose(paths,goals,terminal,home,observations,states,p):
    completed=[];limited=False;failed=Counter()
    for order in itertools.permutations([g['id'] for g in goals]):
        partial=[dict(current=home,legs=[],observations=[],rank_cost=0,eq_s=0,order=list(order))]
        for name in list(order)+[None]:
            choices=[home] if name is None else terminal[name]
            expanded=[]
            for prior in partial:
                for target in choices:
                    view=observations.get(target)
                    if not paths.reference and name is not None and (not view or not view['admissible']):
                        failed[(view or {}).get('reason','observation_unknown')]+=1;continue
                    for path in paths.get(prior['current'],target):
                        eq=sum(paths.edges[i].get('eq_s',0) for i in path['edge_ids'])+(p['observation_s'] if name else 0)
                        if not paths.reference and prior['eq_s']+eq>p['budget_eq_s']:failed['insufficient_budget']+=1;continue
                        expanded.append(dict(current=target,legs=prior['legs']+[dict(path,objective_id=name)],
                            observations=prior['observations']+([dict(state_id=target,objective_id=name,**view)] if name and view else []),
                            rank_cost=prior['rank_cost']+path['cost'],eq_s=prior['eq_s']+eq,order=list(order)))
            expanded.sort(key=lambda r:(-min([o.get('coverage',0) for o in r['observations']] or [0]) if not paths.reference else 0,r['rank_cost'],tuple(r['legs'][-1]['edge_ids'])))
            # Dominancia solo para mismo estado y misma historia física; no borrar alternativas válidas.
            seen={};kept=[]
            for item in expanded:
                signature=(item['current'],tuple(path_signature(leg,states) for leg in item['legs']))
                coverage=min([o.get('coverage',0) for o in item['observations']] or [0])
                front=seen.setdefault(signature,[])
                if any(old['eq_s']<=item['eq_s'] and old['rank_cost']<=item['rank_cost'] and old['coverage']>=coverage for old in front):continue
                front.append(dict(eq_s=item['eq_s'],rank_cost=item['rank_cost'],coverage=coverage));kept.append(item)
            if len(kept)>p['beam_width']:limited=True
            partial=kept[:p['beam_width']]
            if not partial:break
        completed.extend(partial if partial and len(partial[0]['legs'])==len(order)+1 else [])
    return completed,limited or paths.limited,dict(failed)


def is_turn(a,b):
    u=[a[1][i]-a[0][i] for i in range(3)];v=[b[1][i]-b[0][i] for i in range(3)]
    norms=math.sqrt(sum(x*x for x in u)*sum(x*x for x in v))
    return bool(norms and sum(x*y for x,y in zip(u,v))/norms<1-1e-8)


def weight_observation(view,sector,context):
    """Recurrencia como prioridad de observación, sin penalizar el acercamiento."""
    covered=Point().buffer(0);total=visible=0.;seen=shape(view.get('visible',mapping(Point().buffer(0))))
    for r in sorted(context['records'].get('A4',[]),key=lambda r:-r['ordinal_class']):
        part=sector.intersection(transform(FWD,shape(r['geometry']))).difference(covered)
        if part.is_empty:continue
        weight=1+(r['ordinal_class']-1)/4
        total+=part.area*weight;visible+=part.intersection(seen).area*weight;covered=unary_union([covered,part])
    rest=sector.difference(covered);total+=rest.area;visible+=rest.intersection(seen).area
    view['weighted_coverage']=visible/total if total else 0
    view['priority_score']=total/sector.area if sector.area else 1
    view['historical_unknown_area_m2']=rest.area
    return view


def assess(mission,edge_by_id,states,context,p,clock,blocked,returns,observations):
    elapsed=eq=0.;minimum_reserve=1.;timeline=[];profile=[];geometry=[];known=True;reason=None
    previous=None
    for index,leg in enumerate(mission['legs']):
        for ident in leg['edge_ids']:
            ident=int(ident)
            e=edge_by_id[ident];problem=check_edge(e,p,blocked)
            weather=weather_at(context['weather'],clock+timedelta(seconds=elapsed));wp=weather_problem(weather,p)
            if wp:
                return dict(known=not wp.startswith(('missing','unknown')),admissible=False,reason=wp)
            if problem:
                return dict(known=problem!='surface_unknown',admissible=False,reason=problem)
            if previous is not None and is_turn(previous,e['coordinates']):elapsed+=p['turn_s'];eq+=p['turn_s']
            times=duration(e,weather,p)
            if times is None:return dict(known=True,admissible=False,reason='wind_infeasible')
            # Comprobar también las horas atravesadas por el segmento, sin reiniciar el reloj.
            finish=clock+timedelta(seconds=elapsed+times[0])
            checkpoints=[weather_at(context['weather'],finish)]
            hour=(clock+timedelta(seconds=elapsed)).replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
            while hour<finish:checkpoints.append(weather_at(context['weather'],hour));hour+=timedelta(hours=1)
            for w in checkpoints:
                wp=weather_problem(w,p)
                if wp:return dict(known=not wp.startswith(('missing','unknown')),admissible=False,reason=wp)
            # Los costos de planificación usan la envolvente; evitar consumir menos que esa cota.
            seconds=max(times[0],e.get('time_s',times[0]));consume=max(times[1],e.get('eq_s',times[1]))
            elapsed+=seconds;eq+=consume
            reserve=1-eq/(p['flight_minutes']*60);minimum_reserve=min(minimum_reserve,reserve)
            if eq+returns.get(e['target'],float('inf'))>p['budget_eq_s']+1e-8:reason='insufficient_emergency_return';break
            a,b=e['coordinates'];geometry.extend([a,b] if not geometry else [b])
            samples=e.get('profile_samples') or [[0,states[e['source']]['surface_m']],[1,states[e['target']]['surface_m']]]
            profile.extend(dict(elapsed_s=elapsed-seconds+seconds*f,surface_m=z,flight_m=a[2]+(b[2]-a[2])*f,clearance_m=e['clearance_m']) for f,z in samples)
            previous=e['coordinates']
        if reason:break
        name=leg.get('objective_id')
        if name is not None:
            state=int(leg['node_ids'][-1]);view=observations.get(state)
            if not view or not view['admissible']:return dict(known=bool(view and view['known']),admissible=False,reason=(view or {}).get('reason','observation_unknown'))
            arrival=clock+timedelta(seconds=elapsed)
            for stamp in [arrival,arrival+timedelta(seconds=p['observation_s'])]:
                wp=weather_problem(weather_at(context['weather'],stamp),p)
                if wp:return dict(known=not wp.startswith(('missing','unknown')),admissible=False,reason=wp)
            elapsed+=p['observation_s'];eq+=p['observation_s'];previous=None
            timeline.append(dict(objective_id=name,arrival_utc=arrival.isoformat(),departure_utc=(clock+timedelta(seconds=elapsed)).isoformat(),coverage=view['coverage']))
            if eq+returns.get(state,float('inf'))>p['budget_eq_s']+1e-8:reason='insufficient_emergency_return';break
    if eq>p['budget_eq_s']+1e-8:reason='insufficient_budget'
    return dict(known=known,admissible=reason is None,reason=reason,time_s=elapsed,consumption_eq_s=eq,
        final_reserve_fraction=1-eq/(p['flight_minutes']*60),minimum_reserve_fraction=min(minimum_reserve,1-eq/(p['flight_minutes']*60)),
        return_utc=(clock+timedelta(seconds=elapsed)).isoformat(),timeline=timeline,profile=profile,
        coordinates=geometry,minimum_coverage=min([v['coverage'] for v in mission.get('observations',[])] or [0]))


def plan(conn,rid,request,method=None):
    from core.contracts import ROOT
    base,context,original_states,original_edges,obstacle_rows=graph(str(rid));p=effective_profile(base,request.get('preferences') if isinstance(request,dict) else None)
    origin,goals,clock=normalize_request(request,p,context)
    method=method or request.get('method','proposed')
    if method not in ('reference','proposed'):raise ValueError('Método desconocido')
    result=dict(type='FeatureCollection',features=[],run_id=str(rid),schema_version='patrol-plan-1',method=method,
        status='no_route',alternatives=[],effective_profile=p,request=request,objective_count=len(goals),
        objectives=[dict(id=g['id'],center=g['center'],radius_m=g['radius_m'],geometry=mapping(transform(INV,g['sector']))) for g in goals],
        vertical_datum='EGM2008',checks_pending=[],search_limited=False)
    result['provenance']=dict(request_sha256=hashlib.sha256(canonical(request)).hexdigest(),
        source_manifest_sha256=hashlib.sha256(canonical(context.get('source_manifest',{}))).hexdigest(),
        dsm_sha256=context.get('dsm_sha256'),construction_code=context.get('construction_code',{}),
        engine_sha256=hashlib.sha256((ROOT/'core/patrol_routing.py').read_bytes()).hexdigest())
    def seal():
        def ids(value):
            if isinstance(value,list):return [ids(v) for v in value]
            if not isinstance(value,dict):return value
            return {key:str(v) if key in ('id','state_id') and type(v) is int else [str(i) for i in v] if key in ('edge_ids','node_ids') else ids(v) for key,v in value.items()}
        public=ids(result)
        public['sha256']=hashlib.sha256(canonical(public)).hexdigest()
        return public
    weather,problem=weather_window(context['weather'],clock,p)
    if method=='proposed' and problem:
        result.update(status='unknown' if problem.startswith(('missing','unknown')) else 'not_feasible',reason=problem)
        result['checks_pending']=['routes','observation','return'];return seal()
    blocked,ledger,thermal_unknown=restriction_geometry(context,clock,request.get('events',[]))
    # Eventos que entran en la ventana también se consideran, sin adelantar datos externos.
    future_blocked,_,_=restriction_geometry(context,clock+timedelta(seconds=p['budget_eq_s']),request.get('events',[]))
    blocked=unary_union([blocked,future_blocked]);result['thermal_unknown_ids']=thermal_unknown
    surface=Surface(ROOT/context['dsm_file'],transform(FWD,shape(context['flight_geometry'])).bounds);obstacles=Obstacles(obstacle_rows)
    try:
        try:
            states,edges,home,terminal=overlay(original_states,original_edges,origin,goals,surface,obstacles,p,transform(FWD,shape(context['flight_geometry'])))
        except ValueError as exc:
            if not str(exc).startswith('Superficie desconocida'):raise
            result.update(status='unknown',reason='endpoint_surface_unknown',checks_pending=['routes','observation','return'])
            return seal()
        observations={}
        for g in goals:
            for ident in terminal[g['id']]:observations[ident]=weight_observation(observation(surface,states[ident]['coordinates'],g['sector'],p,obstacles.union),g['sector'],context)
    finally:surface.close()
    if problem:
        eligible=[];causes={problem:1}
    else:eligible,causes=enrich(edges,p,weather,blocked)
    result['excluded_edges_by_reason']=causes
    returns=reverse_distances(eligible,home,p['turn_s'])
    paths=Paths(conn,edges if method=='reference' else eligible,states,method=='reference',p,rid)
    candidates,limited,failures=compose(paths,goals,terminal,home,observations,states,p)
    by_id={e['id']:e for e in edges};by_id.update({e['id']:e for e in eligible})
    assessed=[]
    for item in candidates:
        evaluation=assess(item,by_id,states,context,p,clock,blocked,returns,observations)
        if method=='reference' or evaluation['admissible']:
            assessed.append(dict(item,evaluation=evaluation))
        else:failures[evaluation['reason']]=failures.get(evaluation['reason'],0)+1
    if method=='proposed' and assessed:
        shortest=min(x['evaluation']['consumption_eq_s'] for x in assessed)
        result['minimum_candidate_consumption_eq_s']=shortest
        assessed=[x for x in assessed if x['evaluation']['consumption_eq_s']<=p['detour_factor']*shortest+1e-8]
        assessed.sort(key=lambda x:(-x['evaluation']['minimum_coverage'],x['rank_cost']))
    else:assessed.sort(key=lambda x:x['rank_cost'])
    seen=set();chosen=[]
    for item in assessed:
        # Para acreditar k rutas de vigilancia, la ida/patrulla debe cambiar;
        # variar únicamente el regreso no crea una segunda ruta al objetivo.
        signature=tuple(path_signature(leg,states) for leg in item['legs'][:-1])
        if signature in seen:continue
        seen.add(signature);chosen.append(item)
        if len(chosen)==2:break
    # Recuperar perfiles densos solo de las misiones elegidas, sin cargar los
    # cientos de miles de perfiles durante cada consulta del grafo.
    from uuid import UUID
    try:UUID(str(rid));persisted=True
    except ValueError:persisted=False
    if persisted and chosen:
        selected_ids=sorted({ident for item in chosen for leg in item['legs'] for ident in leg['edge_ids'] if ident>0})
        if selected_ids:
            for row in conn.execute('SELECT id,profile_samples FROM routing.flight_edges WHERE run_id=%s AND id=ANY(%s::bigint[])',(rid,selected_ids)):
                by_id[row['id']]['profile_samples']=row['profile_samples']
        for item in chosen:item['evaluation']=assess(item,by_id,states,context,p,clock,blocked,returns,observations)
    for rank,item in enumerate(chosen,1):
        item.pop('current',None);item.pop('eq_s',None);item['rank']=rank
        item['length_km']=sum(x['length_km'] for x in item['legs'])
        for leg in item['legs']:
            leg['segments']=[{key:by_id[i].get(key) for key in ['id','flight_km','horizontal_km','time_s','eq_s','risk','cost','clearance_m','surface_known','obstacle_distance_m','blocked_obstacle','profile_samples']} for i in leg['edge_ids']]
            coords=[states[n]['coordinates'] for n in leg['node_ids']]
            wgs=[[*INV(*c[:2]),c[2]] for c in coords];leg['coordinates']=wgs
            if len(wgs)>1:result['features'].append(dict(type='Feature',geometry=dict(type='LineString',coordinates=wgs),properties=dict(method=method,rank=rank,role='return' if leg['objective_id'] is None else 'outbound',objective_id=leg['objective_id'])))
        for view in item['observations']:
            for kind in ['footprint','visible','hidden','unknown']:
                geom=view.get(kind)
                if geom:
                    wgs=mapping(transform(INV,shape(geom)));view[kind]=wgs
                    if kind in ('visible','hidden','footprint') and not shape(wgs).is_empty:result['features'].append(dict(type='Feature',geometry=wgs,properties=dict(method=method,rank=rank,role=kind,objective_id=view['objective_id'])))
        # Geometrías internas no se duplican en coordenadas métricas.
        item['evaluation'].pop('coordinates',None)
    if len(chosen)>1:
        def geom(item):return unary_union([LineString([c[:2] for c in leg['coordinates']]) for leg in item['legs'] if len(leg['coordinates'])>1])
        a,b=transform(FWD,geom(chosen[0])),transform(FWD,geom(chosen[1]))
        chosen[1]['within_50m_of_first_fraction']=min(1,b.intersection(a.buffer(50)).length/b.length) if b.length else 1
    result.update(alternatives=chosen,status='ready' if chosen else 'search_limited' if limited else 'not_feasible',
                  reason=None if chosen else 'no_complete_mission_in_candidates',search_limited=limited or method=='proposed',
                  candidate_missions=len(candidates),failure_causes=failures,
                  objective_failures={g['id']:sorted({observations[i]['reason'] for i in terminal[g['id']] if observations[i]['reason']}) for g in goals})
    if any(not o['known'] for o in observations.values()):result['checks_pending'].append('observation_surface')
    return seal()


def map_data(rid):
    p,c,states,edges,obstacles=graph(str(rid));features=[]
    # Dibujo por ancla: evitar tres símbolos superpuestos por altitud.
    anchors={n['anchor_id']:n for n in states.values()}
    for n in anchors.values():
        features.append(dict(type='Feature',geometry=dict(type='Point',coordinates=list(INV(*n['coordinates'][:2]))),
            properties=dict(kind=n['kind'],resolution_m=n['resolution_m'],surface_m=n['surface_m'],anchor_id=n['anchor_id'],refinement_reasons=c.get('refinement_by_anchor',{}).get(n['anchor_id'],[]))))
    for e in edges:
        a,b=states[e['source']],states[e['target']]
        if a['anchor_id']>=b['anchor_id'] or a['surface_offset_m']!=p['levels_m'][0] or b['surface_offset_m']!=p['levels_m'][0]:continue
        features.append(dict(type='Feature',geometry=dict(type='LineString',coordinates=[list(INV(*a['coordinates'][:2])),list(INV(*b['coordinates'][:2]))]),properties=dict(kind='corridor',horizontal_km=e['horizontal_km'])))
    for o in obstacles:features.append(dict(type='Feature',geometry=mapping(transform(INV,shape(o['exclusion']))),properties=dict(kind='obstacle',obstacle_kind=o['kind'],height_m=o['height_m'],provider_id=o['provider_id'],geometry_quality=o.get('geometry_quality'))))
    examples=[dict(coordinates=list(INV(*n['coordinates'][:2])),surface_m=n['surface_m']) for n in sorted(anchors.values(),key=lambda n:n['anchor_id']) if n['kind']=='observation']
    return dict(type='FeatureCollection',schema_version='patrol-map-1',vertical_datum='EGM2008',features=features,run_id=str(rid),profile=p,counts=c['counts'],
                area=c['study_geometry'],flight_area=c['flight_geometry'],bases=c['records']['M1'],weather=c['weather'],
                weather_fetched_at=c['weather_fetched_at'],examples=examples,source_manifest=c['source_manifest'],
                layers={k:[dict(type='Feature',geometry=r['geometry'],properties={j:v for j,v in r.items() if j not in ('geometry','original_record')}) for r in c['records'][k]] for k in ['M2','A2','A3','A4']})
