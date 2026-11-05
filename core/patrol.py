"""Polygon surveillance on a metric, terrain-aware graph.

No source layer is mutated. Distances use EPSG:32719, exported Z is DSM EGM2008
plus AGL (not ellipsoidal GNSS height). Failure probabilities are scenario inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import math
import os
import random
import time
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import rasterio
from shapely.geometry import Point, LineString, Polygon, MultiPolygon, shape, mapping, box
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from core.aerial_data import FWD, INV, iso
from core.contracts import ROOT, canonical, sha256, write_json

METHODS = ('dijkstra_distance', 'dijkstra_weighted', 'gurobi', 'annealing')
LABELS = dict(zip(METHODS, ('Dijkstra · metros', 'Dijkstra · parámetros', 'Gurobi MILP', 'Recocido simulado')))


def defaults():
    return json.loads((ROOT / 'config/patrullaje.json').read_text(encoding='utf-8'))


def number(value, name, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{name}: valor finito entre {low} y {high}')
    return value


def profile_for(request):
    p = defaults()
    prefs = request.get('preferences', {})
    if not isinstance(prefs, dict):
        raise ValueError('preferences debe ser un objeto')
    bounds = dict(altitude_agl_m=(20, 120), battery_budget_s=(1, 1200), mission_budget_s=(1, 14400),
                  wind_limit_ms=(0.01, 8), risk_weight=(0, 10), historical_multiplier=(0, 2))
    if set(prefs) - set(bounds):
        raise ValueError('Preferencias de patrullaje desconocidas')
    for k, v in prefs.items():
        p[k] = number(v, k, *bounds[k])
    p.setdefault('historical_multiplier', 1)
    for k, low, high in [('seed', 0, 2**31-1), ('scenarios', 1, 5000)]:
        v = request.get(k, p[k])
        if type(v) is not int or not low <= v <= high:
            raise ValueError(f'{k}: entero entre {low} y {high}')
        p[k] = v
    return p


def raster_path():
    config = json.loads((ROOT / 'config/proyecto.json').read_text(encoding='utf-8'))
    folder = ROOT / config['aerial_raw_directory']
    source = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))['sources']['S3']
    path = (folder / source['file']).resolve()
    if not path.is_relative_to(folder.resolve()) or sha256(path) != source['sha256']:
        raise ValueError('DSM alterado o fuera del directorio de originales')
    return path


class Terrain:
    def __init__(self, path):
        with rasterio.open(path) as src:
            if src.crs is None or src.crs.to_epsg() != 4326:
                raise ValueError('El DSM debe declarar EPSG:4326')
            self.array = src.read(1, masked=True)
            self.affine = ~src.transform
            self.scale, self.offset = src.scales[0], src.offsets[0]
        self.source_sha256 = sha256(Path(path))

    def at(self, x, y):
        lon, lat = INV(x, y)
        c, r = self.affine * (lon, lat)
        r, c = math.floor(r), math.floor(c)
        if not (0 <= r < self.array.shape[0] and 0 <= c < self.array.shape[1]):
            return None
        v = self.array[r, c]
        if np.ma.is_masked(v):
            return None
        v = float(v) * self.scale + self.offset
        return v if math.isfinite(v) else None

    def visible(self, observer, target):
        a, b = np.array(observer[:2]), np.array(target[:2])
        d = float(np.linalg.norm(a-b))
        for f in np.linspace(0, 1, max(2, math.ceil(d/15)+1))[1:-1]:
            x, y = a + (b-a)*f
            h = self.at(x, y)
            if h is None or h > observer[2] + (target[2]-observer[2])*f + 0.01:
                return False
        return True

    def mesh(self, area, step=150):
        w, s, e, n = area.bounds
        nx, ny = math.ceil((e-w)/step)+1, math.ceil((n-s)/step)+1
        xs, ys = np.linspace(w, e, nx), np.linspace(s, n, ny)
        return dict(origin_utm=[w, s], width=nx, height=ny,
                    x=[float(v-w) for v in xs], y=[float(v-s) for v in ys],
                    elevations=[self.at(float(x), float(y)) for y in ys for x in xs],
                    crs='EPSG:32719', vertical_datum='EGM2008', source_sha256=self.source_sha256)


@lru_cache(maxsize=1)
def terrain():
    return Terrain(raster_path())


class Hazards:
    def __init__(self, model, clock, p, events):
        self.rows = []
        self.unknown = []
        records = model['records']
        for key in ('A2', 'A3', 'A4'):
            for row in records[key]:
                if key == 'A2' and iso(row['acquired_at']) > clock:
                    continue
                probability = 100.0
                if key == 'A4':
                    probability = min(100, p['historical_probabilities_pct'][row['ordinal_class']-1] * p.get('historical_multiplier',1))
                if key == 'A2' and (clock-iso(row['acquired_at'])).total_seconds() > 86400:
                    self.unknown.append(str(row['provider_id']))
                self.rows.append(dict(id=f"{key}:{row['provider_id']}", source=key, probability_pct=probability,
                                      geometry=row['geometry'], attributes={k:v for k,v in row.items() if k not in ('geometry','original_record')}))
        covered=unary_union([transform(FWD,shape(r['geometry'])) for r in records['A4']])
        unknown=transform(FWD,shape(model['flight_geometry'])).difference(covered)
        if not unknown.is_empty:
            self.rows.append(dict(id='A4:unknown',source='A4_unknown',probability_pct=p.get('unknown_historical_probability_pct',20),
                                  geometry=mapping(transform(INV,unknown)),attributes=dict(unknown=True,
                                  assumption='Unmapped historical area: explicit conservative scenario probability, not zero risk')))
        if not isinstance(events, list) or len(events) > 20:
            raise ValueError('Máximo 20 amenazas sintéticas')
        for i, row in enumerate(events):
            g = shape(row['geometry'])
            if g.geom_type not in ('Polygon', 'MultiPolygon') or not g.is_valid or g.is_empty:
                raise ValueError('Amenaza sintética requiere un polígono válido')
            w,s,e,n=g.bounds
            if not (-180<=w<=e<=180 and -90<=s<=n<=90 and e-w<=2 and n-s<=2):
                raise ValueError('Amenaza sintética requiere coordenadas WGS84 locales válidas')
            prob = number(row.get('probability_pct', 80), 'probability_pct', 0, 100)
            self.rows.append(dict(id=f'synthetic:{i}', source='synthetic', probability_pct=prob,
                                  geometry=mapping(g), attributes=dict(synthetic=True)))
        self.geoms = [transform(FWD, shape(r['geometry'])) for r in self.rows]
        self.tree = STRtree(self.geoms)
        self.hard = unary_union([g for g, r in zip(self.geoms, self.rows) if r['probability_pct'] == 100])

    def ids(self, geom):
        return [int(i) for i in self.tree.query(geom, predicate='intersects')]

    def probability(self, ids):
        return 1-math.prod(1-self.rows[i]['probability_pct']/100 for i in ids)


class Graph:
    def __init__(self, area, terrain, hazards, weather, profile, conn=None):
        self.area, self.terrain, self.hazards, self.weather, self.p = area, terrain, hazards, weather, profile
        self.nodes, self.edges, self.adj = {}, {}, {}
        self.point_index,self.linked_pairs={},set()
        self.excluded_nodes, self.excluded_edges = [], []
        self.conn, self.cache = conn, {}
        self.sql_queries = {}
        self.routing_targets = None
        w, s, e, n = area.bounds
        grid = profile['grid_m']
        lattice = {}
        for x in range(math.ceil(w/grid)*grid, math.floor(e/grid)*grid+1, grid):
            for y in range(math.ceil(s/grid)*grid, math.floor(n/grid)*grid+1, grid):
                node = self.add_node(x, y)
                if node is not None:
                    lattice[x, y] = node
        for (x, y), a in lattice.items():
            for dx, dy in [(grid, 0), (0, grid), (grid, grid), (grid, -grid)]:
                b = lattice.get((x+dx, y+dy))
                if b is not None:
                    self.link(a, b)
        self.grid_ids = list(self.nodes)
        self.tree = STRtree([Point(self.nodes[i][:2]) for i in self.grid_ids])

    def add_node(self, x, y):
        point = Point(x, y)
        z = self.terrain.at(x, y)
        if not self.area.covers(point):
            return None
        if z is None:
            self.excluded_nodes.append(dict(coordinates=[*INV(x,y)],probability_pct=None,reason='unknown_elevation'))
            return None
        existing=self.find_point(x,y)
        if existing is not None:return existing
        i = len(self.nodes)+1
        self.nodes[i] = [float(x), float(y), z+self.p['altitude_agl_m']]
        self.adj[i] = []
        self.point_index.setdefault((round(x*1000),round(y*1000)),[]).append(i)
        return i

    def find_point(self,x,y):
        kx,ky=round(x*1000),round(y*1000)
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for i in self.point_index.get((kx+dx,ky+dy),[]):
                    if math.dist([x,y],self.nodes[i][:2])<=.001:return i
        return None

    def point(self, coords):
        if not isinstance(coords, (list, tuple)) or len(coords) != 2:
            raise ValueError('Coordenadas WGS84 [longitud, latitud]')
        lon = number(coords[0], 'longitud', -180, 180)
        lat = number(coords[1], 'latitud', -90, 90)
        x, y = FWD(lon, lat)
        if not self.area.covers(Point(x,y)) or self.hazards.hard.intersects(Point(x,y)):
            raise ValueError('Punto bloqueado por una amenaza conocida')
        existing=self.find_point(x,y)
        if existing is not None:return existing
        candidates = self.tree.query(Point(x, y), predicate='dwithin', distance=self.p['max_link_m'])
        for k in candidates:
            i = self.grid_ids[int(k)]
            if math.dist([x,y], self.nodes[i][:2]) < 0.001:
                return i
        i = self.add_node(x, y)
        if i is None:
            raise ValueError('Punto fuera de tránsito, bloqueado o sin elevación')
        for k in sorted(candidates, key=lambda k: math.dist([x,y], self.nodes[self.grid_ids[int(k)]][:2]))[:8]:
            self.link(i, self.grid_ids[int(k)])
        return i

    def link(self, a, b):
        pa, pb = self.nodes[a], self.nodes[b]
        d = math.dist(pa[:2], pb[:2])
        if d <= 0 or d > self.p['max_link_m']+1e-6:
            return
        pair=tuple(sorted((a,b)))
        if pair in self.linked_pairs:return
        self.linked_pairs.add(pair)
        line = LineString([pa[:2], pb[:2]])
        if not self.area.covers(line):
            return
        if self.hazards.hard.intersects(line):
            ids=self.hazards.ids(line)
            for source,target in [(a,b),(b,a)]:
                self.excluded_edges.append(dict(id=f'excluded:{source}:{target}',source=str(source),target=str(target),
                    probability_pct=100,by_threat={self.hazards.rows[i]['id']:self.hazards.rows[i]['probability_pct'] for i in ids},reason='hard_restriction'))
            return
        coords = []
        for f in np.linspace(0, 1, max(2, math.ceil(d/15)+1)):
            x, y = pa[0]+(pb[0]-pa[0])*f, pa[1]+(pb[1]-pa[1])*f
            h = self.terrain.at(x, y)
            if h is None:
                return
            coords.append([float(x), float(y), h+self.p['altitude_agl_m']])
        ids = self.hazards.ids(line)
        probability = self.hazards.probability(ids)
        angle = math.radians(self.weather['wind_direction_deg'])
        wx = -self.weather['wind_speed_ms']*math.sin(angle)
        wy = -self.weather['wind_speed_ms']*math.cos(angle)
        for source, target, points in [(a,b,coords), (b,a,list(reversed(coords)))]:
            seconds, length = 0, 0
            for c, q in zip(points, points[1:]):
                dx, dy, dz = q[0]-c[0], q[1]-c[1], q[2]-c[2]
                horizontal = math.hypot(dx,dy)
                along = (wx*dx+wy*dy)/horizontal
                cross = (wx*dy-wy*dx)/horizontal
                if abs(cross) >= self.p['cruise_ms']:
                    return
                ground = math.sqrt(self.p['cruise_ms']**2-cross**2)+along
                if ground <= 0:
                    return
                seconds += max(horizontal/ground, abs(dz)/(self.p['climb_ms'] if dz >= 0 else self.p['descent_ms']))
                length += math.sqrt(horizontal**2+dz**2)
            i = len(self.edges)+1
            row = dict(id=i, source=source, target=target, distance_m=length, time_s=seconds,
                       cost=seconds*(1+self.p['risk_weight']*probability), hazard_ids=ids,
                       probability=probability, coordinates=points, horizontal_m=d)
            self.edges[i] = row
            self.adj[source].append(i)

    def path(self, source, target, metric='cost'):
        key = (source, target, metric)
        if key in self.cache:
            return self.check_path(self.cache[key],source,target)
        if source == target:
            return []
        if self.conn is not None:
            from psycopg import sql
            if metric not in self.sql_queries:
                payload = [dict(id=e['id'],source=e['source'],target=e['target'],cost=e[metric]) for e in self.edges.values()]
                literal = sql.Literal(json.dumps(payload)).as_string(self.conn)
                self.sql_queries[metric] = f'SELECT id,source,target,cost,-1::float8 AS reverse_cost FROM jsonb_to_recordset({literal}::jsonb) AS e(id bigint,source bigint,target bigint,cost float8)'
            targets = self.routing_targets or [target]
            rows = self.conn.execute('SELECT end_vid,edge FROM pgr_dijkstra(%s,%s::bigint,%s::bigint[],true) ORDER BY end_vid,seq',
                                     (self.sql_queries[metric],source,targets)).fetchall()
            for t in targets:
                self.cache[source,t,metric] = [] if t==source else None
            for row in rows:
                k = (source,row['end_vid'],metric)
                if self.cache[k] is None:self.cache[k] = []
                if row['edge'] != -1:self.cache[k].append(row['edge'])
            result = self.cache[key]
        else:
            dist, prev, queue = {source:0}, {}, [(0,source)]
            while queue:
                score, node = heapq.heappop(queue)
                if score != dist[node]:
                    continue
                if node == target:
                    break
                for i in self.adj[node]:
                    edge = self.edges[i]
                    new = score+edge[metric]
                    nxt = edge['target']
                    if new < dist.get(nxt, math.inf):
                        dist[nxt], prev[nxt] = new, i
                        heapq.heappush(queue, (new,nxt))
            result = None
            if target in dist:
                result, node = [], target
                while node != source:
                    i = prev[node]
                    result.append(i)
                    node = self.edges[i]['source']
                result.reverse()
        self.cache[key] = result
        return self.check_path(result,source,target)

    def check_path(self,path,source,target):
        if path is None:return None
        node=source
        for ident in path:
            if ident not in self.edges or self.edges[ident]['source']!=node:
                raise RuntimeError('Cadena de vuelo discontinua en resultado del ruteador')
            node=self.edges[ident]['target']
        if node!=target:raise RuntimeError('La ruta no alcanza su extremo solicitado')
        return path

    def totals(self, path):
        return {k:sum(self.edges[i][k] for i in path) for k in ('distance_m','time_s','cost')}

    def coordinates(self, path):
        result = []
        for i in path:
            result.extend(self.edges[i]['coordinates'][0 if not result else 1:])
        return result

    def export_failures(self):
        def row(ident, ids):
            return dict(id=str(ident), by_threat={'A1:weather':0,**{self.hazards.rows[i]['id']:self.hazards.rows[i]['probability_pct'] for i in ids}},
                        probability_pct=100*self.hazards.probability(ids))
        return dict(schema_version='failure-probabilities-1', distribution='Uniform[0,100)',
                    independence='Independent threat objects; shared event across affected nodes and edges',
                    nodes=[row(i,self.hazards.ids(Point(v[:2]))) for i,v in self.nodes.items()],
                    edges=[dict(row(i,e['hazard_ids']), source=str(e['source']), target=str(e['target'])) for i,e in self.edges.items()],
                    excluded_nodes=self.excluded_nodes,excluded_edges=self.excluded_edges,
                    global_threats=[dict(id='A1:weather',probability_pct=0,reason='Selected weather within conservative profile')])


def sweep_tasks(target, graph):
    w,s,e,n = target.bounds
    count = max(1, math.ceil((n-s)/graph.p['swath_m']))
    tasks = []
    for row in range(count):
        y = s+(row+0.5)*(n-s)/count
        cut = target.intersection(LineString([(w-1,y),(e+1,y)]))
        parts = [cut] if cut.geom_type == 'LineString' else list(getattr(cut,'geoms',[]))
        for part in sorted(parts, key=lambda g:g.bounds[0]):
            if part.geom_type != 'LineString' or part.length < 0.01:
                continue
            points = [part.interpolate(f, normalized=True) for f in np.linspace(0,1,max(2,math.ceil(part.length/100)+1))]
            ids = [graph.point(list(INV(p.x,p.y))) for p in points]
            tasks.append(dict(nodes=ids if row%2 == 0 else list(reversed(ids))))
    if not tasks or len(tasks) > graph.p['max_tasks']:
        raise ValueError(f"Polígono requiere {len(tasks)} pasadas; límite explícito {graph.p['max_tasks']}. Dividir el área")
    return tasks


def oriented_tasks(tasks, graph, metric):
    result = []
    for group, task in enumerate(tasks):
        for direction in (0,1):
            ids = task['nodes'][::(-1 if direction else 1)]
            path = []
            for a,b in zip(ids,ids[1:]):
                part = graph.path(a,b,metric)
                if part is None:
                    path = None
                    break
                path.extend(part)
            if path is not None:
                result.append(dict(group=group,direction=direction,start=ids[0],end=ids[-1],path=path,**graph.totals(path)))
    return result


def fixed_route(order, states, graph, home, stations, metric):
    """Beam labels preserve battery and remaining station inventory; never reset in flight."""
    ascent = graph.p['altitude_agl_m']/graph.p['climb_ms']
    labels = [dict(node=home,energy=ascent,time_s=ascent,cost=ascent if metric=='cost' else 0,path=[],stops=[],mask=0)]
    actions = [states[i] for i in order]+[dict(start=home,end=home,path=[],time_s=graph.p['altitude_agl_m']/graph.p['descent_ms'],cost=0)]
    for action in actions:
        candidates = []
        for initial in labels:
            queue = [initial]
            # Stations can be visited proactively. At most one battery per station.
            for depth in range(len(stations)+1):
                next_queue = []
                for label in queue:
                    leg = graph.path(label['node'],action['start'],metric)
                    if leg is not None:
                        t = graph.totals(leg)
                        energy = label['energy']+t['time_s']+action['time_s']
                        total = label['time_s']+t['time_s']+action['time_s']
                        if energy <= graph.p['battery_budget_s']+1e-8 and total <= graph.p['mission_budget_s']+1e-8:
                            candidates.append(dict(node=action['end'],energy=energy,time_s=total,
                                cost=label['cost']+t[metric]+(action['distance_m'] if metric=='distance_m' and 'distance_m' in action else action['cost'] if metric=='cost' else 0),
                                path=label['path']+leg+action['path'],stops=label['stops'],mask=label['mask']))
                    for k, station in enumerate(stations):
                        if label['mask'] & (1<<k) or (station['node']==label['node'] and label['energy']<=graph.p['altitude_agl_m']/graph.p['climb_ms']+1e-8):
                            continue
                        leg = graph.path(label['node'],station['node'],metric)
                        if leg is None:
                            continue
                        t = graph.totals(leg)
                        landing = graph.p['altitude_agl_m']/graph.p['descent_ms']
                        takeoff = graph.p['altitude_agl_m']/graph.p['climb_ms']
                        if label['energy']+t['time_s']+landing > graph.p['battery_budget_s']:
                            continue
                        duration = t['time_s']+landing+graph.p['station_service_s']+takeoff
                        if label['time_s']+duration > graph.p['mission_budget_s']:
                            continue
                        stop = dict(station_id=station['id'],coordinate_index=max(0,len(graph.coordinates(label['path']+leg))-1),
                                    arrival_s=label['time_s']+t['time_s'],service_s=duration-t['time_s'])
                        next_queue.append(dict(node=station['node'],energy=takeoff,time_s=label['time_s']+duration,
                            cost=label['cost']+t[metric]+(duration-t['time_s'] if metric=='cost' else 0),
                            path=label['path']+leg,stops=label['stops']+[stop],mask=label['mask']|(1<<k)))
                queue = sorted(next_queue,key=lambda v:(v['cost'],v['time_s'],len(v['stops'])))[:16]
                if not queue:
                    break
        if not candidates:
            return None
        # Preserve distinct inventories, not only the cheapest exhausted battery.
        kept = {}
        for c in sorted(candidates,key=lambda v:(v['cost'],v['time_s'],len(v['stops']),v['energy'])):
            signature = (c['mask'],round(c['energy']/30))
            if signature not in kept:
                kept[signature] = c
        labels = list(kept.values())[:16]
    # Equal-distance candidates may include a zero-distance battery swap at home.
    # Resolve the tie by elapsed time so the reference never adds gratuitous service.
    best = min(labels,key=lambda v:(v['cost'],v['time_s'],len(v['stops'])))
    return best


def anneal(states, graph, home, stations, initial):
    rng = random.Random(graph.p['seed'])
    current = list(initial)
    best = fixed_route(current,states,graph,home,stations,'cost')
    value = best
    fitness_cache={tuple(current):best}
    started = time.monotonic()
    iterations = 0
    by_group = {s['group']:[i for i,t in enumerate(states) if t['group']==s['group']] for s in states}
    for k in range(graph.p['annealing_iterations']):
        if time.monotonic()-started >= graph.p['solver_seconds']:
            break
        trial = current[:]
        a,b = rng.randrange(len(trial)),rng.randrange(len(trial))
        if rng.random()<0.5:
            trial[a],trial[b] = trial[b],trial[a]
        else:
            trial[a] = rng.choice(by_group[states[trial[a]]['group']])
        signature=tuple(trial)
        if signature not in fitness_cache:
            fitness_cache[signature]=fixed_route(trial,states,graph,home,stations,'cost')
        candidate = fitness_cache[signature]
        iterations = k+1
        if candidate is None:
            continue
        temp = max(0.01, 100*(1-k/graph.p['annealing_iterations']))
        if value is None or candidate['cost'] <= value['cost'] or rng.random()<math.exp(min(0,(value['cost']-candidate['cost'])/temp)):
            current,value = trial,candidate
        if best is None or candidate['cost'] < best['cost']:
            best = candidate
    return best, dict(iterations=iterations,seed=graph.p['seed'],unique_fitness_evaluations=len(fitness_cache),search_limited=True)


def gurobi_route(states, graph, home, stations):
    """Generalized asymmetric TSP with directed strip states and resource resets."""
    try:
        import gurobipy as gp
    except ImportError:
        return None, dict(status='unavailable',reason='gurobipy no instalado; instalar requirements.patrol.lock')
    ascent = graph.p['altitude_agl_m']/graph.p['climb_ms']
    landing = graph.p['altitude_agl_m']/graph.p['descent_ms']
    actions = [dict(start=home,end=home,path=[],time_s=ascent,cost=ascent,kind='start')]
    actions += [dict(s,kind='task') for s in states]
    for s in stations:
        actions.append(dict(start=s['node'],end=s['node'],path=[],time_s=landing+graph.p['station_service_s']+ascent,
                            cost=landing+graph.p['station_service_s']+ascent,kind='station',station=s))
    actions.append(dict(start=home,end=home,path=[],time_s=landing,cost=landing,kind='end'))
    end = len(actions)-1
    links = {}
    for i,a in enumerate(actions[:-1]):
        for j,b in enumerate(actions[1:],1):
            if i == j or (a['kind']==b['kind']=='task' and a['group']==b['group']):
                continue
            path = graph.path(a['end'],b['start'],'cost')
            if path is not None:
                links[i,j] = dict(path=path,**graph.totals(path))
    try:
        with gp.Env(empty=True) as env:
            env.setParam('OutputFlag',0)
            env.start()
            with gp.Model('polygon_surveillance',env=env) as model:
                model.Params.TimeLimit = graph.p['solver_seconds']
                model.Params.MIPGap = graph.p['solver_gap']
                model.Params.Seed = graph.p['seed']
                model.Params.Threads = 1
                x = model.addVars(list(links),vtype=gp.GRB.BINARY,name='transition')
                visit = model.addVars(range(len(actions)),vtype=gp.GRB.BINARY,name='visit')
                energy = model.addVars(range(len(actions)),lb=0,ub=graph.p['battery_budget_s'],name='energy_used_s')
                order = model.addVars(range(len(actions)),lb=0,ub=len(actions),name='order')
                outgoing = {i:gp.quicksum(x[a,b] for a,b in links if a==i) for i in range(len(actions))}
                incoming = {i:gp.quicksum(x[a,b] for a,b in links if b==i) for i in range(len(actions))}
                model.addConstr(outgoing[0]==1)
                model.addConstr(incoming[end]==1)
                model.addConstr(energy[0]==0)
                model.addConstr(order[0]==0)
                model.addConstr(visit[0]==1)
                model.addConstr(visit[end]==1)
                for i in range(1,end):
                    model.addConstr(incoming[i]==visit[i])
                    model.addConstr(outgoing[i]==visit[i])
                for group in sorted({s['group'] for s in states}):
                    model.addConstr(gp.quicksum(visit[i] for i,a in enumerate(actions) if a.get('group')==group)==1)
                for i,a in enumerate(actions):
                    flight_service = landing if a['kind'] in ('station','end') else a['time_s']
                    model.addConstr((visit[i]==1) >> (energy[i]+flight_service <= graph.p['battery_budget_s']))
                for (i,j),link in links.items():
                    model.addConstr((x[i,j]==1) >> (order[j]>=order[i]+1))
                    used = ascent if actions[i]['kind']=='station' else energy[i]+actions[i]['time_s']
                    model.addConstr((x[i,j]==1) >> (energy[j]>=used+link['time_s']))
                elapsed = gp.quicksum(x[i,j]*v['time_s'] for (i,j),v in links.items()) + gp.quicksum(visit[i]*a['time_s'] for i,a in enumerate(actions))
                model.addConstr(elapsed<=graph.p['mission_budget_s'])
                model.setObjective(gp.quicksum(x[i,j]*v['cost'] for (i,j),v in links.items())+
                                   gp.quicksum(visit[i]*a['cost'] for i,a in enumerate(actions)),gp.GRB.MINIMIZE)
                model.optimize()
                metadata = dict(status='optimal' if model.Status==gp.GRB.OPTIMAL else 'time_limit' if model.Status==gp.GRB.TIME_LIMIT else str(model.Status),
                                license_checked=True,variables=model.NumVars,constraints=model.NumConstrs,
                                formulation='Directed strip states, flow, order, battery propagation, optional single-use stations',
                                gap=float(model.MIPGap) if model.SolCount else None,solutions=model.SolCount)
                if not model.SolCount:
                    metadata['reason']='Sin circuito factible para cobertura, batería y estaciones' if model.Status==gp.GRB.INFEASIBLE else 'Sin solución disponible dentro del límite del solver; no se acredita inviabilidad'
                    return None,metadata
                route,stops,node,seen,seconds = [],[],0,set(),ascent
                while node != end:
                    if node in seen:
                        raise RuntimeError('Subcircuito inesperado en solución Gurobi')
                    seen.add(node)
                    nxt = next(j for i,j in links if i==node and x[i,j].X>0.5)
                    link = links[node,nxt]
                    route.extend(link['path'])
                    seconds += link['time_s']
                    action = actions[nxt]
                    if action['kind']=='station':
                        stops.append(dict(station_id=action['station']['id'],coordinate_index=max(0,len(graph.coordinates(route))-1),
                                          arrival_s=seconds,service_s=action['time_s']))
                    route.extend(action['path'])
                    seconds += action['time_s']
                    node = nxt
                return dict(path=route,stops=stops,time_s=seconds,cost=float(model.ObjVal)),metadata
    except gp.GurobiError as exc:
        return None,dict(status='license_or_solver_error',code=exc.errno,reason=str(exc),license_checked=False)


def coverage_cells(target, step):
    w,s,e,n = target.bounds
    cells = []
    for x in np.arange(w,e,step):
        for y in np.arange(s,n,step):
            cell = target.intersection(box(x,y,min(e,x+step),min(n,y+step)))
            if not cell.is_empty and cell.area>0:
                cells.append(cell)
    return cells


def coverage(path, graph, target):
    coords = graph.coordinates(path)
    cells = coverage_cells(target,graph.p['coverage_cell_m'])
    tree = STRtree([Point(c[:2]) for c in coords])
    covered = []
    unknown = 0
    for i,cell in enumerate(cells):
        c = cell.representative_point()
        h = graph.terrain.at(c.x,c.y)
        if h is None:
            unknown += 1
            continue
        near = tree.query(c,predicate='dwithin',distance=graph.p['view_radius_m'])
        if any(graph.terrain.visible(coords[int(k)],[c.x,c.y,h]) for k in near):
            covered.append(i)
    area = sum(cells[i].area for i in covered)
    return dict(percent=100*area/target.area,complete=len(covered)==len(cells),cells=len(cells),covered_cells=len(covered),
                unknown_cells=unknown,support_m=graph.p['coverage_cell_m'],
                pending_geometry=mapping(transform(INV,unary_union([c for i,c in enumerate(cells) if i not in set(covered)]))))


def evaluate_failures(routes, graph):
    rng = random.Random(graph.p['seed'])
    survivors = {k:0 for k in METHODS}
    needed = {k:set(i for e in route.get('edge_ids',[]) for i in graph.edges[int(e)]['hazard_ids']) for k,route in routes.items()}
    # All draws are shared between algorithms; one event affects its whole footprint.
    sample, all_scenarios = [], []
    sensitivity={str(f):{k:0 for k in METHODS} for f in (0.5,1,2)}
    catalogue = hashlib.sha256()
    for scenario in range(graph.p['scenarios']):
        draws = [rng.random()*100 for _ in graph.hazards.rows]
        active = {i for i,r in enumerate(graph.hazards.rows) if draws[i]<r['probability_pct']}
        row = dict(id=scenario,draws=draws,active_threat_ids=[graph.hazards.rows[i]['id'] for i in sorted(active)])
        catalogue.update(canonical(row))
        all_scenarios.append(row)
        if scenario==0:
            sample = row
        for method,r in routes.items():
            if r['status']=='ready' and not (needed[method]&active):
                survivors[method] += 1
        for factor in (0.5,1,2):
            active_sensitivity=set()
            for i,threat in enumerate(graph.hazards.rows):
                prob=threat['probability_pct']
                if threat['source']=='A4':
                    prob=min(100,graph.p['historical_probabilities_pct'][threat['attributes']['ordinal_class']-1]*factor)
                if draws[i]<prob:active_sensitivity.add(i)
            for method,r in routes.items():
                if r['status']=='ready' and not needed[method]&active_sensitivity:
                    sensitivity[str(factor)][method]+=1
    for method,route in routes.items():
        route['resilience'] = dict(value=survivors[method]/graph.p['scenarios'],successes=survivors[method],
                                   scenarios=graph.p['scenarios'],known=True,definition='Frozen full-coverage mission and safe return under common threat events')
    return dict(seed=graph.p['seed'],count=graph.p['scenarios'],distribution='Uniform[0,100)',
                rule='U < probability_pct',scenario_sha256=catalogue.hexdigest(),first_scenario=sample,
                scenarios=all_scenarios,historical_sensitivity={f:{k:v/graph.p['scenarios'] for k,v in counts.items()} for f,counts in sensitivity.items()},
                sensitivity_protocol='Frozen routes; historical probability multiplier only; shared uniforms',unknown_thermal_ids=graph.hazards.unknown)


def validate_polygon(request, study):
    raw = request.get('target_polygon')
    if isinstance(raw,dict) and raw.get('type')=='Feature':
        raw = raw.get('geometry')
    target = shape(raw) if isinstance(raw,dict) else None
    if target is None or target.geom_type!='Polygon' or not target.is_valid or target.is_empty:
        raise ValueError('target_polygon requiere Polygon GeoJSON válido, con huecos permitidos')
    if len(target.exterior.coords)>1000 or sum(len(r.coords) for r in target.interiors)>1000:
        raise ValueError('Polígono demasiado complejo (máximo 1000 vértices)')
    if not study.covers(target):
        raise ValueError('Polígono objetivo fuera del área de vigilancia')
    target = transform(FWD,target)
    if not 1 <= target.area <= 4_000_000:
        raise ValueError('Área objetivo entre 1 m² y 4 km²; dividir objetivos mayores')
    return target


def selected_weather(model, clock, p):
    weather = next((w for w in model['records']['M4'] if iso(w['valid_at'])==clock.replace(minute=0,second=0,microsecond=0)),None)
    if weather is None or any(weather.get(k) is None for k in ('wind_speed_ms','wind_gust_ms','wind_direction_deg','temperature_c')):
        raise ValueError('Meteorología desconocida para la hora UTC solicitada')
    if max(weather['wind_speed_ms'],weather['wind_gust_ms'])>=p['wind_limit_ms'] or not p['temperature_min_c']<=weather['temperature_c']<=p['temperature_max_c']:
        raise ValueError('Meteorología fuera del perfil de vuelo: A1, probabilidad de falla 100 %')
    return weather


def calculate(model, request, conn=None, terrain_override=None):
    if not isinstance(request,dict):
        raise ValueError('Solicitud JSON debe ser un objeto')
    p = profile_for(request)
    clock = iso(request.get('time',model['reference_time']))
    if clock.tzinfo is None:
        raise ValueError('Hora requiere zona UTC explícita')
    study = shape(model['study_geometry'])
    target = validate_polygon(request,study)
    weather = selected_weather(model,clock,p)
    hazards = Hazards(model,clock,p,request.get('events',[]))
    area = transform(FWD,shape(model['flight_geometry']))
    started = time.monotonic()
    graph = Graph(area,terrain_override or terrain(),hazards,weather,p,conn)
    candidates = [s for s in model['records']['M1'] if s.get('candidate',True)]
    if not candidates:raise ValueError('El snapshot no contiene bases candidatas')
    base=next((s for s in candidates if s['provider_id']=='104'),candidates[0])
    origin = request.get('origin',base['geometry']['coordinates'])
    if not study.covers(Point(origin)) and not any(Point(origin).distance(Point(s['geometry']['coordinates']))<1e-9 for s in candidates):
        raise ValueError('Origen exterior debe coincidir con una base candidata')
    home = graph.point(origin)
    requested_stations = request.get('station_ids',[s['provider_id'] for s in candidates])
    if not isinstance(requested_stations,list) or any(not isinstance(i,str) for i in requested_stations):
        raise ValueError('station_ids debe ser una lista de IDs de bases')
    if set(requested_stations)-{s['provider_id'] for s in candidates}:
        raise ValueError('Estación desconocida')
    stations = []
    for s in candidates:
        if s['provider_id'] not in requested_stations:
            continue
        try:
            node = graph.point(s['geometry']['coordinates'])
        except ValueError:
            continue
        stations.append(dict(id=s['provider_id'],name=s['name'],node=node,hypothetical=True,position_utm=graph.nodes[node]))
    tasks = sweep_tasks(target,graph)
    graph.routing_targets=sorted({home}|{s['node'] for s in stations}|{i for task in tasks for i in task['nodes']})
    routes = {}
    for method in METHODS:
        begin = time.monotonic()
        metric = 'distance_m' if method=='dijkstra_distance' else 'cost'
        states = oriented_tasks(tasks,graph,metric)
        initial = [next((i for i,s in enumerate(states) if s['group']==g and s['direction']==0),
                        next((i for i,s in enumerate(states) if s['group']==g),-1)) for g in range(len(tasks))]
        metadata = {}
        if -1 in initial:
            answer = None
            metadata['reason'] = 'Pasada de vigilancia desconectada'
        elif method=='gurobi':
            answer,metadata = gurobi_route(states,graph,home,stations)
        elif method=='annealing':
            answer,metadata = anneal(states,graph,home,stations,initial)
        else:
            answer = fixed_route(initial,states,graph,home,stations,metric)
            metadata = dict(engine='pgr_dijkstra' if conn is not None else 'python_dijkstra_offline',
                            task_order='serpentine',station_search='beam16')
        if answer is None and 'reason' not in metadata:
            metadata['reason']='No se encontró circuito con batería y estaciones disponibles; búsqueda limitada'
        route = dict(method=method,label=LABELS[method],status='not_feasible',solver=metadata,edge_ids=[],
                     coordinates=[],coverage=None,stops=[],time_s=None,distance_m=None)
        if answer is not None:
            cov = coverage(answer['path'],graph,target)
            coords = graph.coordinates(answer['path'])
            route.update(status='ready' if cov['complete'] else 'incomplete_coverage',
                         edge_ids=[str(i) for i in answer['path']], coordinates=[[*INV(c[0],c[1]),c[2]] for c in coords],
                         coordinates_utm=coords,
                         coverage=cov,stops=answer['stops'],time_s=answer['time_s'],cost=answer['cost'],
                         distance_m=graph.totals(answer['path'])['distance_m'])
        route['compute_s'] = time.monotonic()-begin
        routes[method] = route
    evaluation = evaluate_failures(routes,graph)
    viable = sorted((r for r in routes.values() if r['status']=='ready'),key=lambda r:(-r['resilience']['value'],round(r['time_s'],3),r['method']))
    leaders=[r['method'] for r in viable if r['resilience']['value']==viable[0]['resilience']['value']] if viable else []
    # Geometry exported for replay and recovery, separate from route candidate generation.
    graph_rows = [dict(id=str(e['id']),source=str(e['source']),target=str(e['target']),time_s=e['time_s'],cost=e['cost'],
                       horizontal_m=e['horizontal_m'],hazard_ids=[hazards.rows[i]['id'] for i in e['hazard_ids']]) for e in graph.edges.values()]
    threat_rows=[]
    for row,geom in zip(hazards.rows,hazards.geoms):
        x,y=geom.centroid.x,geom.centroid.y
        h=graph.terrain.at(x,y)
        threat_rows.append(dict(row,position_utm=[x,y,h+10] if h is not None else None))
    result = dict(schema_version='patrol-result-1',request=request,effective_profile=p,time=clock.isoformat(),weather=weather,
                  run_id=model.get('_run_id'),source_context_sha256=hashlib.sha256(canonical({k:v for k,v in model.items() if not k.startswith('_')})).hexdigest(),
                  terrain_sha256=getattr(graph.terrain,'source_sha256','fixture'),target_polygon=mapping(transform(INV,target)),
                  origin=origin,stations=stations,routes=routes,recommended=[r['method'] for r in viable[:3]],resilience_leaders=leaders,evaluation=evaluation,
                  threats=threat_rows,failure_probabilities=graph.export_failures(),
                  graph=dict(nodes=[dict(id=str(i),coordinates=[*INV(c[0],c[1]),c[2]]) for i,c in graph.nodes.items()],edges=graph_rows,home=str(home)),
                  network=dict(nodes=len(graph.nodes),directed_edges=len(graph.edges),max_horizontal_link_m=max((e['horizontal_m'] for e in graph.edges.values()),default=0)),
                  coverage_tasks=len(tasks),compute_s=time.monotonic()-started,
                  assumptions=['100 m visual radius and class probabilities are academic assumptions',
                               'Hypothetical battery-swap stations; one battery each, no in-flight recharge',
                               'DSM ~30 m EGM2008; modeled clearance, no certified obstacle database',
                               'Weather is static during the mission; source forecasts are historical snapshots'])
    result['assumptions'].append('Unmapped historical recurrence: explicitly assumed 20% per mission; separate from observed classes')
    from core.provenance import software_manifest
    result['software']=software_manifest()
    result['sha256'] = hashlib.sha256(canonical(result)).hexdigest()
    return result


def map_data(model):
    p = defaults()
    study = shape(model['study_geometry'])
    area = transform(FWD,shape(model['flight_geometry']))
    bases = [s for s in model['records']['M1'] if s.get('candidate',True)]
    home = next((s for s in bases if s['provider_id']=='104'),bases[0])
    center = transform(FWD,shape(home['geometry']))
    hard = unary_union([transform(FWD,shape(r['geometry'])) for k in ('A2','A3') for r in model['records'][k]])
    demo = None
    # A small deterministic demonstration, selected geometrically rather than by results.
    for dx,dy in [(300,0),(0,300),(-300,0),(0,-300),(600,0)]:
        g = box(center.x+dx-120,center.y+dy-100,center.x+dx+120,center.y+dy+100)
        if transform(FWD,study).covers(g) and not hard.intersects(g):
            demo = mapping(transform(INV,g))
            break
    return dict(schema_version='patrol-map-1',area=model['study_geometry'],flight_area=model['flight_geometry'],
                bases=bases,base_catalogue=model['records']['M1'],default_origin=home['geometry']['coordinates'],demo_polygon=demo,
                weather=model['records']['M4'],reference_time=model['reference_time'],profile=p,
                layers={k:model['records'][k] for k in ('M2','A2','A3','A4')},
                terrain=terrain().mesh(area,step=60),sources=model.get('raster'),hypothetical_stations=True)


def simulate(result, request, terrain_override=None):
    """Replay a frozen route; turn at a split graph edge after thermal detection.

    A failed link detected ahead triggers safe return from its source. This is
    explicitly an interrupted patrol, never counted as completed surveillance.
    """
    method = request.get('method',result['recommended'][0] if result['recommended'] else '')
    if method not in result['routes'] or result['routes'][method]['status']!='ready':
        raise ValueError('Elegir una ruta viable para simular')
    p = result['effective_profile']
    seed=request.get('seed',p['seed'])
    if type(seed) is not int or not 0<=seed<2**31:
        raise ValueError('seed requiere un entero entre 0 y 2147483647')
    rng = random.Random(seed)
    active,draws = set(),[]
    for threat in result['threats']:
        value = rng.random()*100
        occurs = value<threat['probability_pct']
        draws.append(dict(id=threat['id'],draw=value,probability_pct=threat['probability_pct'],active=occurs))
        if occurs:
            active.add(threat['id'])
    fire = request.get('fire')
    if fire is not None:
        if not isinstance(fire,list) or len(fire)!=2:
            raise ValueError('fire requiere [longitud,latitud]')
        fire = [number(fire[0],'longitud',-180,180),number(fire[1],'latitud',-90,90)]
        if not shape(result['target_polygon']).covers(Point(fire)):
            raise ValueError('Foco simulado debe quedar dentro del polígono objetivo')
    t = terrain_override or terrain()
    fire_xy = FWD(*fire) if fire else None
    fire_z = t.at(*fire_xy) if fire else None
    if fire is not None and fire_z is None:
        raise ValueError('Foco sin elevación; detección desconocida')
    route = result['routes'][method]
    edges = {e['id']:dict(e) for e in result['graph']['edges']}
    nodes = {n['id']:n['coordinates'] for n in result['graph']['nodes']}
    def sample_edge(edge):
        if 'coordinates' in edge:return edge['coordinates']
        a,b=nodes[edge['source']],nodes[edge['target']]
        ax,ay=FWD(*a[:2]);bx,by=FWD(*b[:2])
        points=[]
        for f in np.linspace(0,1,max(2,math.ceil(math.hypot(bx-ax,by-ay)/15)+1)):
            x,y=ax+(bx-ax)*f,ay+(by-ay)*f
            z=t.at(x,y)
            if z is None:raise ValueError('Retorno con elevación desconocida')
            points.append([*INV(x,y),z+p['altitude_agl_m']])
        edge['coordinates']=points
        return points
    home = result['graph']['home']
    adjacency = {k:[] for k in nodes}
    for i,e in edges.items():
        if not active.intersection(e['hazard_ids']):
            adjacency[e['source']].append(i)
    initial_ascent = p['altitude_agl_m']/p['climb_ms']
    elapsed = initial_ascent
    remaining = p['battery_budget_s']-initial_ascent
    timeline = [dict(coordinates=nodes[home],time_s=elapsed,battery_pct=100*remaining/p['battery_budget_s'],phase='patrol')]
    current = home
    detection = None
    interrupted = False
    coordinate_index = 0
    station_stops = {s['coordinate_index']:s for s in route['stops']}
    used_stations = set()
    def append_points(points,seconds,phase):
        nonlocal elapsed,remaining
        lengths = [math.dist(FWD(*a[:2]),FWD(*b[:2])) for a,b in zip(points,points[1:])]
        total = sum(lengths)
        for c,length in zip(points[1:],lengths):
            dt = seconds*length/total if total else 0
            elapsed += dt
            remaining -= dt
            timeline.append(dict(coordinates=c,time_s=elapsed,battery_pct=max(0,100*remaining/p['battery_budget_s']),phase=phase))
    for ident in route['edge_ids']:
        e = edges[ident]
        if active.intersection(e['hazard_ids']):
            interrupted = True
            current = e['source']
            break
        points = sample_edge(e)
        hit = None
        if fire:
            for k,c in enumerate(points):
                xy = FWD(*c[:2])
                if math.dist(xy,fire_xy)<=p['view_radius_m'] and t.visible([*xy,c[2]],[*fire_xy,fire_z]):
                    hit = k
                    break
        if hit is not None:
            distances = [math.dist(FWD(*a[:2]),FWD(*b[:2])) for a,b in zip(points,points[1:])]
            fraction = sum(distances[:hit])/sum(distances) if sum(distances) else 0
            append_points(points[:hit+1],e['time_s']*fraction,'patrol')
            elapsed += p['verification_s']
            remaining -= p['verification_s']
            current = 'detection'
            nodes[current] = points[hit]
            adjacency[current] = []
            suffix = points[hit:]
            reverse = next((r for r in edges.values() if r['source']==e['target'] and r['target']==e['source']),None)
            # Both residual arcs preserve their original wind-dependent durations.
            for name,target,coords,duration in [('ahead',e['target'],suffix,e['time_s']*(1-fraction)),
                                               ('behind',e['source'],list(reversed(points[:hit+1])),reverse['time_s']*fraction if reverse else math.inf)]:
                if not math.isfinite(duration):
                    continue
                edge_id = f'split-{name}'
                edges[edge_id] = dict(source=current,target=target,coordinates=coords,time_s=duration,hazard_ids=[])
                adjacency[current].append(edge_id)
            detection = dict(synthetic=True,fire_coordinates=fire,observer_coordinates=nodes[current],detected_at_s=elapsed-p['verification_s'],
                             reported_at_s=elapsed,verification_s=p['verification_s'],
                             detected_at_utc=(iso(result['time'])+timedelta(seconds=elapsed-p['verification_s'])).isoformat(),
                             reported_at_utc=(iso(result['time'])+timedelta(seconds=elapsed)).isoformat())
            timeline.append(dict(coordinates=nodes[current],time_s=elapsed,battery_pct=max(0,100*remaining/p['battery_budget_s']),phase='report'))
            break
        append_points(points,e['time_s'],'patrol')
        coordinate_index += len(points)-1
        current = e['target']
        if coordinate_index in station_stops:
            stop = station_stops[coordinate_index]
            elapsed += stop['service_s']
            remaining = p['battery_budget_s']-initial_ascent
            used_stations.add(stop['station_id'])
            timeline.append(dict(coordinates=nodes[current],time_s=elapsed,battery_pct=100*remaining/p['battery_budget_s'],phase='battery_swap'))
    landing = p['altitude_agl_m']/p['descent_ms']
    state = 'completed'
    returned_to='origin'
    if detection or interrupted:
        # Dijkstra labels with remaining battery; optional single-use swap stations.
        failed_nodes={r['id'] for r in result['failure_probabilities']['nodes'] if active.intersection(r['by_threat'])}
        base_targets={home:'origin',**{str(s['node']):s['id'] for s in result['stations']}}
        base_targets={node:ident for node,ident in base_targets.items() if node not in failed_nodes}
        station_by_node = {str(s['node']):s for s in result['stations'] if s['id'] not in used_stations and str(s['node']) not in failed_nodes}
        queue = [(0,0,current,remaining,[],[],frozenset())]
        serial = 0
        best = {}
        recovery = None
        while queue:
            cost,_,node,battery,path,stops,mask = heapq.heappop(queue)
            key = (node,mask)
            labels=best.setdefault(key,[])
            if any(c<=cost+1e-9 and b>=battery-1e-9 for c,b in labels):
                continue
            best[key]=[(c,b) for c,b in labels if not (cost<=c+1e-9 and battery>=b-1e-9)]+[(cost,battery)]
            if elapsed+cost+landing>p['mission_budget_s']:
                continue
            if node in base_targets and battery>=landing:
                recovery = (path,stops,node)
                break
            if node in station_by_node and node not in mask and battery>=landing:
                serial += 1
                duration = landing+p['station_service_s']+initial_ascent
                heapq.heappush(queue,(cost+duration,serial,node,p['battery_budget_s']-initial_ascent,path,
                                      stops+[(len(path),duration,station_by_node[node]['id'])],mask|{node}))
            for i in adjacency.get(node,[]):
                edge = edges[i]
                if edge['time_s']<=battery:
                    serial += 1
                    heapq.heappush(queue,(cost+edge['time_s'],serial,edge['target'],battery-edge['time_s'],path+[i],stops,mask))
        if recovery is None:
            state = 'no_safe_return'
        else:
            path,stops,landing_node = recovery
            returned_to=base_targets[landing_node]
            stops = {i:(duration,ident) for i,duration,ident in stops}
            for j,i in enumerate(path):
                if j in stops:
                    elapsed += stops[j][0]
                    remaining = p['battery_budget_s']-initial_ascent
                    timeline.append(dict(coordinates=timeline[-1]['coordinates'],time_s=elapsed,battery_pct=100*remaining/p['battery_budget_s'],phase='battery_swap'))
                append_points(sample_edge(edges[i]),edges[i]['time_s'],'return')
            state = 'detected_and_returned' if detection else 'interrupted_and_returned'
    if state!='no_safe_return':
        elapsed += landing
        remaining -= landing
        last=timeline[-1]['coordinates']
        timeline.append(dict(coordinates=[last[0],last[1],last[2]-p['altitude_agl_m']],time_s=elapsed,battery_pct=max(0,100*remaining/p['battery_budget_s']),phase='landed'))
    for frame in timeline:
        frame['position_utm']=[*FWD(*frame['coordinates'][:2]),frame['coordinates'][2]]
    return dict(schema_version='patrol-simulation-1',result_sha256=result['sha256'],method=method,
                seed=request.get('seed',p['seed']),draws=draws,active_threat_ids=sorted(active),timeline=timeline,
                detection=detection,status=state,time_s=elapsed,mission_completed=state in ('completed','detected_and_returned'),
                fire_found=detection is not None,patrol_completed=state=='completed',return_base_id=returned_to if state!='no_safe_return' else None,hypothetical=True)


def snapshot_context(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('El snapshot debe pertenecer al proyecto')
    model = json.loads(path.read_text(encoding='utf-8'))
    for key in ('records','study_geometry','flight_geometry','reference_time'):
        if key not in model:
            raise ValueError(f'Snapshot de contexto incompleto: {key}')
    model['_run_id']=path.parent.name
    return model


def main():
    parser = argparse.ArgumentParser(description='Patrullaje reproducible; evaluación y exportación de fallas')
    parser.add_argument('--context',help='Snapshot context.json explícito; si se omite utiliza publicación PostGIS')
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--request')
    source.add_argument('--experiment',help='Protocolo de lote poligonal fijado antes de calcular')
    parser.add_argument('--output',default='datos/runs/patrullaje')
    args = parser.parse_args()
    request = json.loads(Path(args.request or args.experiment).read_text(encoding='utf-8'))
    def execute(model,conn=None):
        if args.experiment:
            from core.patrol_experiment import run
            return run(model,request,Path(args.output),conn)
        return calculate(model,request,conn)
    if args.context:
        result = execute(snapshot_context(args.context))
    else:
        from core.db import connect
        with connect() as conn:
            row = conn.execute('SELECT run_id FROM routing.publication WHERE singleton').fetchone()
            raw=conn.execute('SELECT context FROM routing.aerial_models WHERE run_id=%s',(row['run_id'],)).fetchone()['context']
            model = dict(raw,_run_id=str(row['run_id']))
            result = execute(model,conn)
    if args.experiment:
        print(json.dumps(result));return
    out = Path(args.output)/result['sha256'][:16]
    out.mkdir(parents=True,exist_ok=True)
    write_json(out/'comparison.json',result)
    write_json(out/'failure_probabilities.json',result['failure_probabilities'])
    write_json(out/'request.json',request)
    write_json(out/'scenarios.json',dict(result['evaluation'],threats=result['threats']))
    print(json.dumps(dict(output=str(out),recommended=result['recommended'],network=result['network'])))


if __name__=='__main__':
    main()
