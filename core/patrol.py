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
import threading
import sys
from collections import OrderedDict
from dataclasses import dataclass
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
from core.vertical_profile import level, ramp_profile, profile_metadata, target_display, target_display_summary

METHODS = ('dijkstra_distance', 'dijkstra_weighted', 'gurobi', 'annealing')
LABELS = dict(zip(METHODS, ('Dijkstra · metros', 'Dijkstra · parámetros', 'Gurobi MILP', 'Recocido simulado')))
_GEOMETRY_CACHE = OrderedDict()
_GEOMETRY_LOCK = threading.RLock()
_GEOMETRY_MAX_BYTES = 128 * 1024 * 1024


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
    if not path.is_relative_to(folder.resolve()):
        raise ValueError('DSM alterado o fuera del directorio de originales')
    from core.assets import resolve_asset
    return resolve_asset(path,source['sha256'])


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


def flight_terrain(model):
    from core.geographic_scene import get_scene
    return get_scene(model,terrain()).surface


def segment_fractions(surface,a,b):
    if hasattr(surface,'fractions'):
        return surface.fractions(a,b)
    return np.linspace(0,1,max(2,math.ceil(math.dist(a[:2],b[:2])/15)+1))


class Hazards:
    def __init__(self, model, clock, p, events, activated_threat_ids=None):
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
        activated = [] if activated_threat_ids is None else activated_threat_ids
        if not isinstance(activated,list) or any(not isinstance(v,str) for v in activated):
            raise ValueError('activated_threat_ids debe contener identificadores de amenaza')
        if set(activated)-{row['id'] for row in self.rows}:
            raise ValueError('Amenaza activada desconocida en el escenario original')
        for row in self.rows:
            if row['id'] in activated:
                row['attributes']=dict(row['attributes'],original_probability_pct=row['probability_pct'],activated_for_replanning=True)
                row['probability_pct']=100.
        self.geoms = [transform(FWD, shape(r['geometry'])) for r in self.rows]
        self.tree = STRtree(self.geoms)
        self.hard = unary_union([g for g, r in zip(self.geoms, self.rows) if r['probability_pct'] == 100])

    def ids(self, geom):
        return [int(i) for i in self.tree.query(geom, predicate='intersects')]

    def probability(self, ids):
        return 1-math.prod(1-self.rows[i]['probability_pct']/100 for i in ids)


@dataclass(frozen=True)
class BaseGeometry:
    """Only immutable physical coordinates; never probabilities, wind or path caches."""
    nodes: tuple
    segments: tuple
    unknown_nodes: tuple
    size_bytes: int


def geometry_key(area,surface,profile):
    return hashlib.sha256(canonical(dict(area_wkb=area.wkb_hex,crs='EPSG:32719',
        surface_sha256=surface.source_sha256,surface_type=type(surface).__module__+'.'+type(surface).__qualname__,
        altitude_agl_m=profile['altitude_agl_m'],grid_m=profile['grid_m'],max_link_m=profile['max_link_m'],
        sampling_m=15,vertical_profile=profile_metadata(),vertical_kernel_sha256=sha256(ROOT/'core/vertical_profile.py'),kernel_sha256=sha256(Path(__file__))))).hexdigest()


def build_geometry(area,surface,profile):
    nodes=[];unknown=[];lattice={};segments=[]
    w,s,e,n=area.bounds;grid=profile['grid_m']
    for x in range(math.ceil(w/grid)*grid,math.floor(e/grid)*grid+1,grid):
        for y in range(math.ceil(s/grid)*grid,math.floor(n/grid)*grid+1,grid):
            if not area.covers(Point(x,y)):continue
            h=surface.at(x,y)
            if h is None:unknown.append(tuple(INV(x,y)));continue
            ident=len(nodes)+1;coords=(float(x),float(y),level(h,profile['altitude_agl_m']))
            nodes.append((ident,coords));lattice[x,y]=(ident,coords)
    for (x,y),(a,pa) in lattice.items():
        for dx,dy in ((grid,0),(0,grid),(grid,grid),(grid,-grid)):
            value=lattice.get((x+dx,y+dy))
            if value is None:continue
            b,pb=value;d=math.dist(pa[:2],pb[:2])
            if d>profile['max_link_m']+1e-6 or not area.covers(LineString([pa[:2],pb[:2]])):continue
            points=[]
            for f in segment_fractions(surface,pa,pb):
                qx,qy=pa[0]+(pb[0]-pa[0])*f,pa[1]+(pb[1]-pa[1])*f
                h=surface.at(qx,qy)
                if h is None:break
                points.append((float(qx),float(qy),float(h)))
            else:
                profile_points=ramp_profile(pa,pb,points,profile['altitude_agl_m'])
                if profile_points is not None:segments.append((a,b,profile_points,float(d)))
    values=(tuple(nodes),tuple(segments),tuple(unknown))
    seen=set()
    def memory(value):
        ident=id(value)
        if ident in seen:return 0
        seen.add(ident)
        return sys.getsizeof(value)+(sum(memory(v) for v in value) if isinstance(value,tuple) else 0)
    size=memory(values)
    return BaseGeometry(*values,size)


class Graph:
    def __init__(self, area, terrain, hazards, weather, profile, conn=None, cache_geometry=None):
        self.area, self.terrain, self.hazards, self.weather, self.p = area, terrain, hazards, weather, profile
        self.nodes, self.edges, self.adj = {}, {}, {}
        self.point_index,self.linked_pairs={},set()
        self.excluded_nodes, self.excluded_edges = [], []
        self.conn, self.cache = conn, {}
        self.sql_queries = {}
        self.path_compute_s=0.;self.path_queries=0
        self.routing_targets = None
        cacheable=(type(terrain).__module__=='core.geographic_scene' or type(terrain) is Terrain) if cache_geometry is None else cache_geometry
        started=time.monotonic();key=geometry_key(area,terrain,profile) if cacheable else None;hit=False
        if cacheable:
            with _GEOMETRY_LOCK:
                base=_GEOMETRY_CACHE.get(key)
                if base is None:
                    base=build_geometry(area,terrain,profile)
                    if base.size_bytes<=_GEOMETRY_MAX_BYTES:_GEOMETRY_CACHE[key]=base
                    while len(_GEOMETRY_CACHE)>2 or sum(v.size_bytes for v in _GEOMETRY_CACHE.values())>_GEOMETRY_MAX_BYTES:
                        _GEOMETRY_CACHE.popitem(last=False)
                else:hit=True;_GEOMETRY_CACHE.move_to_end(key)
        else:base=build_geometry(area,terrain,profile)
        with _GEOMETRY_LOCK:cache_bytes=sum(v.size_bytes for v in _GEOMETRY_CACHE.values())
        self.geometry_cache=dict(hit=hit,key=key,physical_geometry_s=time.monotonic()-started,
            bytes=base.size_bytes,cache_max_bytes=_GEOMETRY_MAX_BYTES,
            cache_bytes=cache_bytes,policy='immutable_geometry_only_LRU_max2_memory_bounded')
        for ident,coords in base.nodes:
            self.nodes[ident]=list(coords);self.adj[ident]=[]
            self.point_index.setdefault((round(coords[0]*1000),round(coords[1]*1000)),[]).append(ident)
        self.excluded_nodes=[dict(coordinates=list(c),probability_pct=None,reason='unknown_elevation') for c in base.unknown_nodes]
        for a,b,points,d in base.segments:self._connect(a,b,points,d)
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
        self.nodes[i] = [float(x), float(y), level(z,self.p['altitude_agl_m'])]
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
        coords = []
        for f in segment_fractions(self.terrain,pa,pb):
            x, y = pa[0]+(pb[0]-pa[0])*f, pa[1]+(pb[1]-pa[1])*f
            h = self.terrain.at(x, y)
            if h is None:
                return
            coords.append([float(x), float(y), h])
        profile_points=ramp_profile(pa,pb,coords,self.p['altitude_agl_m'])
        if profile_points is not None:self._connect(a,b,profile_points,d,already_linked=True)

    def access_height(self,node):
        p=self.nodes[node];height=self.terrain.at(p[0],p[1])
        if height is None:raise ValueError('Base o estación sin elevación conocida')
        return max(0.,p[2]-height)

    def ascent(self,node):return self.access_height(node)/self.p['climb_ms']

    def landing(self,node):return self.access_height(node)/self.p['descent_ms']

    def _connect(self,a,b,coords,d,already_linked=False):
        if not already_linked:self.linked_pairs.add(tuple(sorted((a,b))))
        line=LineString([self.nodes[a][:2],self.nodes[b][:2]])
        if self.hazards.hard.intersects(line):
            ids=self.hazards.ids(line)
            for source,target in [(a,b),(b,a)]:
                self.excluded_edges.append(dict(id=f'excluded:{source}:{target}',source=str(source),target=str(target),
                    probability_pct=100,by_threat={self.hazards.rows[i]['id']:self.hazards.rows[i]['probability_pct'] for i in ids},reason='hard_restriction'))
            return
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
                if horizontal<1e-7:
                    seconds += abs(dz)/(self.p['climb_ms'] if dz>=0 else self.p['descent_ms'])
                    length += abs(dz)
                    continue
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
        started=time.monotonic();self.path_queries+=1
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
        self.path_compute_s+=time.monotonic()-started
        return self.check_path(result,source,target)

    def routing_session(self):
        """Independent caches ensure no technique borrows another's connector work."""
        from copy import copy
        result=copy(self);result.cache={};result.sql_queries={};result.path_compute_s=0.;result.path_queries=0
        return result

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

    def export_failures(self,weather_probability=0):
        def combined(base):
            if weather_probability==100 or base==100:return 100.
            if weather_probability is None or base is None:return None
            return 100*(1-(1-base/100)*(1-weather_probability/100))
        def row(ident, ids):
            return dict(id=str(ident), by_threat={'A1:weather':weather_probability,**{self.hazards.rows[i]['id']:self.hazards.rows[i]['probability_pct'] for i in ids}},
                        probability_pct=combined(100*self.hazards.probability(ids)))
        def excluded(rows):
            return [dict(r,by_threat={'A1:weather':weather_probability,**r.get('by_threat',{})},
                         probability_pct=combined(r.get('probability_pct'))) for r in rows]
        return dict(schema_version='failure-probabilities-1', distribution='Uniform[0,100)',
                    independence='Independent threat objects; shared event across affected nodes and edges',
                    nodes=[dict(row(i,self.hazards.ids(Point(v[:2]))),coordinates=[*INV(*v[:2]),v[2]]) for i,v in self.nodes.items()],
                    edges=[dict(row(i,e['hazard_ids']), source=str(e['source']), target=str(e['target'])) for i,e in self.edges.items()],
                    excluded_nodes=excluded(self.excluded_nodes),excluded_edges=excluded(self.excluded_edges),
                    global_threats=[dict(id='A1:weather',probability_pct=weather_probability,
                        reason='Selected weather within conservative profile' if weather_probability==0 else 'Weather blocked or unknown; see constraints')])


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
    ascent = graph.ascent(home)
    labels = [dict(node=home,energy=ascent,time_s=ascent,cost=ascent if metric=='cost' else 0,path=[],stops=[],mask=0)]
    landing = graph.landing(home)
    actions = [states[i] for i in order]+[dict(start=home,end=home,path=[],time_s=landing,cost=landing)]
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
                        if label['mask'] & (1<<k) or (station['node']==label['node'] and label['energy']<=graph.ascent(station['node'])+1e-8):
                            continue
                        leg = graph.path(label['node'],station['node'],metric)
                        if leg is None:
                            continue
                        t = graph.totals(leg)
                        station_landing = graph.landing(station['node'])
                        takeoff = graph.ascent(station['node'])
                        if label['energy']+t['time_s']+station_landing > graph.p['battery_budget_s']:
                            continue
                        duration = t['time_s']+station_landing+graph.p['station_service_s']+takeoff
                        if label['time_s']+duration > graph.p['mission_budget_s']:
                            continue
                        stop = dict(station_id=station['id'],coordinate_index=max(0,len(graph.coordinates(label['path']+leg))-1),
                                    after_edge_count=len(label['path'])+len(leg),
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
    preflight=dict(license_checked=False,capacity_checked=False)
    try:
        import gurobipy as gp
    except ImportError:
        return None, dict(status='unavailable',reason='gurobipy no instalado; instalar requirements.patrol.lock')
    ascent = graph.ascent(home)
    landing = graph.landing(home)
    actions = [dict(start=home,end=home,path=[],time_s=ascent,cost=ascent,kind='start')]
    actions += [dict(s,kind='task') for s in states]
    for s in stations:
        station_landing,station_ascent=graph.landing(s['node']),graph.ascent(s['node'])
        actions.append(dict(start=s['node'],end=s['node'],path=[],time_s=station_landing+graph.p['station_service_s']+station_ascent,
                            cost=station_landing+graph.p['station_service_s']+station_ascent,kind='station',station=s,
                            landing_s=station_landing,ascent_s=station_ascent))
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
                    flight_service = a['landing_s'] if a['kind']=='station' else a['time_s']
                    model.addConstr((visit[i]==1) >> (energy[i]+flight_service <= graph.p['battery_budget_s']))
                for (i,j),link in links.items():
                    model.addConstr((x[i,j]==1) >> (order[j]>=order[i]+1))
                    used = actions[i]['ascent_s'] if actions[i]['kind']=='station' else energy[i]+actions[i]['time_s']
                    model.addConstr((x[i,j]==1) >> (energy[j]>=used+link['time_s']))
                elapsed = gp.quicksum(x[i,j]*v['time_s'] for (i,j),v in links.items()) + gp.quicksum(visit[i]*a['time_s'] for i,a in enumerate(actions))
                model.addConstr(elapsed<=graph.p['mission_budget_s'])
                model.setObjective(gp.quicksum(x[i,j]*v['cost'] for (i,j),v in links.items())+
                                   gp.quicksum(visit[i]*a['cost'] for i,a in enumerate(actions)),gp.GRB.MINIMIZE)
                model.update()
                preflight.update(variables=model.NumVars,linear_constraints=model.NumConstrs,
                    general_constraints=model.NumGenConstrs,gurobi_version=list(gp.gurobi.version()),
                    license_checked=True,capacity_check='actual_delivery_model_optimization')
                model.optimize()
                preflight['capacity_checked']=True
                metadata = dict(status='optimal' if model.Status==gp.GRB.OPTIMAL else 'time_limit' if model.Status==gp.GRB.TIME_LIMIT else str(model.Status),
                                license_checked=True,variables=model.NumVars,constraints=model.NumConstrs,
                                preflight=preflight,
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
                                          after_edge_count=len(route),
                                          arrival_s=seconds,service_s=action['time_s']))
                    route.extend(action['path'])
                    seconds += action['time_s']
                    node = nxt
                return dict(path=route,stops=stops,time_s=seconds,cost=float(model.ObjVal)),metadata
    except gp.GurobiError as exc:
        return None,dict(status='model_capacity_exceeded' if exc.errno==10010 else 'license_or_solver_error',
                         code=exc.errno,reason=str(exc),license_checked=preflight['license_checked'],preflight=preflight)


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


def threat_uniform(seed,scenario,threat_id):
    """Counter-based 53-bit U[0,100): stable under catalogue additions/reordering."""
    digest=hashlib.sha256(canonical(['threat-uniform-v1',int(seed),int(scenario),str(threat_id)])).digest()
    return (int.from_bytes(digest[:8],'big')>>11)/(2**53)*100


def wilson_interval(successes,trials):
    if trials<=0:return dict(method='wilson',level=.95,low=0.,high=1.)
    z=1.959963984540054;ratio=successes/trials;denominator=1+z*z/trials
    center=(ratio+z*z/(2*trials))/denominator
    radius=z*math.sqrt(ratio*(1-ratio)/trials+z*z/(4*trials*trials))/denominator
    return dict(method='wilson',level=.95,low=max(0.,center-radius),high=min(1.,center+radius))


def evaluate_failures(routes, graph):
    survivors = {k:0 for k in routes}
    needed = {k:set(i for e in route.get('edge_ids',[]) for i in graph.edges[int(e)]['hazard_ids']) for k,route in routes.items()}
    # All draws are shared between algorithms; one event affects its whole footprint.
    sample, all_scenarios = [], []
    sensitivity={str(f):{k:0 for k in routes} for f in (0.5,1,2)}
    catalogue = hashlib.sha256()
    for scenario in range(graph.p['scenarios']):
        draws = [threat_uniform(graph.p['seed'],scenario,row['id']) for row in graph.hazards.rows]
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
                                   scenarios=graph.p['scenarios'],known=True,confidence_interval=wilson_interval(survivors[method],graph.p['scenarios']),
                                   definition='Frozen full-coverage mission and safe return under common threat events')
    return dict(seed=graph.p['seed'],count=graph.p['scenarios'],distribution='Uniform[0,100)',
                rule='U < probability_pct',scenario_sha256=catalogue.hexdigest(),first_scenario=sample,
                scenarios=all_scenarios,historical_sensitivity={f:{k:v/graph.p['scenarios'] for k,v in counts.items()} for f,counts in sensitivity.items()},
                rng_protocol='sha256/53-bit-uniform-v1; keyed by seed, scenario and threat id',
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
    from core.mission_constraints import assess_constraints
    assessment=assess_constraints(model,dict(time=clock.isoformat()),_profile=p)
    if not assessment['weather_admissible']:
        raise ValueError('; '.join(row['message'] for row in assessment['reasons'] if row['source']=='A1'))
    return assessment['weather']


def _route_row(method,status='not_feasible',solver=None):
    return dict(method=method,label=LABELS[method],status=status,solver=solver or {},edge_ids=[],
                coordinates=[],coordinates_utm=[],coverage=None,stops=[],time_s=None,distance_m=None,
                compute_s=0.,timings=dict(connectors_s=0.,solve_s=0.,validation_s=0.,total_s=0.,
                    connector_queries=0,cache_policy='independent_per_technique'))


def _scene_provenance(model,result,terrain_override):
    if terrain_override is not None:return
    from core.geographic_scene import get_scene
    scene=get_scene(model,terrain())
    result['geographic_scene']=dict(sha256=scene.source_hash,surface_sha256=scene.surface.source_sha256,
        osm_sha256=scene.manifest['sha256'],timestamp_osm_base=scene.manifest.get('timestamp_osm_base'),
        obstacle_count=len(scene.surface.obstacles),height_model='max(DSM, nearby DSM minimum + tagged/estimated height)')


def _finish_result(result,started):
    from core.provenance import software_manifest
    result['software']=software_manifest()
    result['compute_s']=time.monotonic()-started
    result['timings']['total_s']=result['compute_s']
    result['sha256']=hashlib.sha256(canonical(result)).hexdigest()
    return result


def calculate(model, request, conn=None, terrain_override=None):
    from core.mission_constraints import assess_constraints
    started=time.monotonic()
    if not isinstance(request,dict):raise ValueError('Solicitud JSON debe ser un objeto')
    constraints=assess_constraints(model,request,_surface=terrain_override)
    actual=constraints['effective_profile'];p=dict(actual)
    p['battery_budget_s']=constraints['flight_budget_s']
    p['mission_budget_s']=constraints['mission_flight_budget_s']
    clock=iso(constraints['time']);study=shape(model['study_geometry'])
    target=validate_polygon(request,study)
    candidates=[s for s in model['records']['M1'] if s.get('candidate',True)]
    if not candidates:raise ValueError('El snapshot no contiene bases candidatas')
    base=next((s for s in candidates if s['provider_id']=='104'),candidates[0])
    origin=request.get('origin',base['geometry']['coordinates'])
    if not isinstance(origin,(list,tuple)) or len(origin)!=2:raise ValueError('Coordenadas WGS84 [longitud, latitud]')
    number(origin[0],'longitud',-180,180);number(origin[1],'latitud',-90,90)
    if not study.covers(Point(origin)) and not any(Point(origin).distance(Point(s['geometry']['coordinates']))<1e-9 for s in candidates):
        raise ValueError('Origen exterior debe coincidir con una base candidata')
    origin_base=next((s for s in candidates if Point(origin).distance(Point(s['geometry']['coordinates']))<1e-9),None)
    origin_info=dict(id=origin_base['provider_id'],provider_id=origin_base['provider_id'],name=origin_base.get('name'),coordinates=list(origin)) if origin_base else dict(
        id='origin:'+hashlib.sha256(canonical(list(origin))).hexdigest()[:16],provider_id=None,name=None,coordinates=list(origin))
    requested_stations=request.get('station_ids',[s['provider_id'] for s in candidates])
    if not isinstance(requested_stations,list) or any(not isinstance(i,str) for i in requested_stations):raise ValueError('station_ids debe ser una lista de IDs de bases')
    if set(requested_stations)-{s['provider_id'] for s in candidates}:raise ValueError('Estación desconocida')
    hazards=Hazards(model,clock,actual,request.get('events',[]),request.get('activated_threat_ids'))
    area=transform(FWD,shape(model['flight_geometry']))
    surface=terrain_override or flight_terrain(model)
    # Resolve the default origin too; explicit UI origins use this same assessment.
    origin_surface=surface.at(*FWD(*origin))
    if origin_surface is not None:
        access_height=level(origin_surface,actual['altitude_agl_m'])-origin_surface
        constraints=assess_constraints(model,request,_profile=actual,_access_height=access_height)
    weather=constraints['weather']
    # Diagnostic topology does not pretend a blocked/unknown weather field is flyable.
    graph_weather=weather if constraints['admissible'] else dict(valid_at=clock.isoformat(),wind_speed_ms=0.,wind_gust_ms=0.,wind_direction_deg=0.,temperature_c=20.)
    graph=Graph(area,surface,hazards,graph_weather,p,conn)
    result=dict(schema_version='patrol-result-3',request=request,effective_profile=actual,planning_profile=p,vertical_profile=profile_metadata(),
        constraints=constraints,status='ready' if constraints['admissible'] else 'blocked',time=clock.isoformat(),weather=weather,
        run_id=model.get('_run_id'),source_context_sha256=hashlib.sha256(canonical({k:v for k,v in model.items() if not k.startswith('_')})).hexdigest(),
        terrain_sha256=getattr(surface,'source_sha256','fixture'),target_polygon=mapping(transform(INV,target)),origin=origin,origin_base=origin_info,
        target_display=(target_display(model,request['target_polygon'],terrain_override) if terrain_override is not None else target_display_summary(model,request['target_polygon'])),
        stations=[],routes={},route_alternatives={},recommended=[],alternative_recommended=[],resilience_leaders=[],
        evaluation={},threats=[],graph=dict(nodes=[],edges=[],home=None),coverage_tasks=0,
        network=dict(nodes=len(graph.nodes),directed_edges=len(graph.edges),max_horizontal_link_m=max((e['horizontal_m'] for e in graph.edges.values()),default=0)),
        timings=dict(setup_s=0.,comparison_s=0.,alternatives_s=0.,evaluation_s=0.,total_s=0.,geometry_cache=graph.geometry_cache),
        assumptions=['100 m visual radius and class probabilities are academic assumptions',
                     'Hypothetical battery-swap stations; one battery each, no in-flight recharge',
                     'DSM ~30 m EGM2008; modeled clearance, no certified obstacle database',
                     'Weather is static during the mission; source forecasts are historical snapshots',
                     'Unmapped historical recurrence: explicitly assumed 20% per mission; separate from observed classes',
                     'One report reserve per battery and once per mission; actual budgets remain available to simulation'])
    _scene_provenance(model,result,terrain_override)
    result['failure_probabilities']=graph.export_failures(constraints['probability_pct'])
    if not constraints['admissible']:
        reason='; '.join(row['message'] for row in constraints['reasons'])
        result['routes']={method:_route_row(method,'blocked',dict(status='blocked',reason=reason)) for method in METHODS}
        result['diversity']=dict(count=0,requested=4,status='blocked',reason=reason,comparison_unchanged=True,compute_s=0.)
        result['diagnostic']=dict(kind='mission_constraints',reasons=constraints['reasons'],weather_probability_pct=constraints['probability_pct'],
                                 routing_attempted=False,probabilities_exportable=True)
        result['threats']=list(hazards.rows)
        result['graph']['nodes']=[dict(id=str(i),coordinates=[*INV(*v[:2]),v[2]],surface_m_egm2008=surface.at(*v[:2])) for i,v in graph.nodes.items()]
        result['timings']['setup_s']=time.monotonic()-started
        return _finish_result(result,started)
    home=graph.point(origin)
    if hasattr(surface,'can_land') and not surface.can_land(*graph.nodes[home][:2]):raise ValueError('La base de salida está sobre agua cartografiada')
    stations=[]
    for station in candidates:
        if station['provider_id'] not in requested_stations:continue
        try:node=graph.point(station['geometry']['coordinates'])
        except ValueError:continue
        if hasattr(surface,'can_land') and not surface.can_land(*graph.nodes[node][:2]):continue
        stations.append(dict(id=station['provider_id'],name=station['name'],node=node,hypothetical=True,position_utm=graph.nodes[node],
                             surface_m_egm2008=surface.at(*graph.nodes[node][:2]),access_height_m=graph.access_height(node)))
    tasks=sweep_tasks(target,graph)
    graph.routing_targets=sorted({home}|{s['node'] for s in stations}|{i for task in tasks for i in task['nodes']})
    result['timings']['setup_s']=time.monotonic()-started
    routes={};comparison_started=time.monotonic()
    for method in METHODS:
        begin=time.monotonic();method_graph=graph.routing_session()
        metric='distance_m' if method=='dijkstra_distance' else 'cost'
        states=oriented_tasks(tasks,method_graph,metric)
        initial=[next((i for i,s in enumerate(states) if s['group']==g and s['direction']==0),
                      next((i for i,s in enumerate(states) if s['group']==g),-1)) for g in range(len(tasks))]
        metadata={}
        if -1 in initial:answer=None;metadata['reason']='Pasada de vigilancia desconectada'
        elif method=='gurobi':answer,metadata=gurobi_route(states,method_graph,home,stations)
        elif method=='annealing':answer,metadata=anneal(states,method_graph,home,stations,initial)
        else:
            answer=fixed_route(initial,states,method_graph,home,stations,metric)
            metadata=dict(engine='pgr_dijkstra' if conn is not None else 'python_dijkstra_offline',task_order='serpentine',station_search='beam16')
        if answer is None and 'reason' not in metadata:metadata['reason']='No se encontró circuito con batería, reserva de reporte y estaciones disponibles; búsqueda limitada'
        route=_route_row(method,solver=metadata);validation_started=time.monotonic()
        if answer is not None:
            cov=coverage(answer['path'],graph,target);coords=graph.coordinates(answer['path'])
            route.update(status='ready' if cov['complete'] else 'incomplete_coverage',
                         edge_ids=[str(i) for i in answer['path']],coordinates=[[*INV(c[0],c[1]),c[2]] for c in coords],coordinates_utm=coords,
                         coverage=cov,stops=answer['stops'],time_s=answer['time_s'],cost=answer['cost'],distance_m=graph.totals(answer['path'])['distance_m'])
        validation_s=time.monotonic()-validation_started;total=time.monotonic()-begin
        route['compute_s']=total
        route['timings']=dict(connectors_s=method_graph.path_compute_s,solve_s=max(0.,total-method_graph.path_compute_s-validation_s),
            validation_s=validation_s,total_s=total,connector_queries=method_graph.path_queries,cache_policy='independent_per_technique')
        routes[method]=route
    result['timings']['comparison_s']=time.monotonic()-comparison_started
    from core.patrol_alternatives import distinct_circuits
    begin=time.monotonic();alternatives,diversity=distinct_circuits(graph,tasks,home,stations,target,routes)
    result['timings']['alternatives_s']=time.monotonic()-begin
    begin=time.monotonic();evaluation=evaluate_failures({**routes,**alternatives},graph)
    result['timings']['evaluation_s']=time.monotonic()-begin
    viable=sorted((r for r in routes.values() if r['status']=='ready'),key=lambda r:(-r['resilience']['value'],r['compute_s'],r['time_s'],r['method']))
    leaders=[r['method'] for r in viable if r['resilience']['value']==viable[0]['resilience']['value']] if viable else []
    geometries={}
    for e in graph.edges.values():
        key=f"{min(e['source'],e['target'])}:{max(e['source'],e['target'])}"
        if key not in geometries:
            points=e['coordinates'] if e['source']<e['target'] else list(reversed(e['coordinates']))
            geometries[key]=[[*INV(c[0],c[1]),c[2]] for c in points]
    graph_rows=[dict(id=str(e['id']),source=str(e['source']),target=str(e['target']),time_s=e['time_s'],cost=e['cost'],horizontal_m=e['horizontal_m'],
                     geometry_id=f"{min(e['source'],e['target'])}:{max(e['source'],e['target'])}",geometry_reversed=e['source']>e['target'],
                     hazard_ids=[hazards.rows[i]['id'] for i in e['hazard_ids']]) for e in graph.edges.values()]
    threats=[]
    for row,geom in zip(hazards.rows,hazards.geoms):
        h=surface.at(geom.centroid.x,geom.centroid.y)
        threats.append(dict(row,position_utm=[geom.centroid.x,geom.centroid.y,h+10] if h is not None else None))
    result.update(stations=stations,routes=routes,route_alternatives=alternatives,diversity=diversity,
        alternative_recommended=[r['method'] for r in sorted(alternatives.values(),key=lambda r:(-r['resilience']['value'],r['time_s']))],
        recommended=[r['method'] for r in viable[:3]],resilience_leaders=leaders,
        ranking=dict(primary='estimated_resilience',tie_break='compute_s',then='flight_time_s',
            message='Empate entre las cuatro técnicas' if len(leaders)==4 else 'Empate en resiliencia estimada' if len(leaders)>1 else 'Mayor resiliencia estimada' if leaders else 'Sin misión viable',
            leaders=leaders),evaluation=evaluation,threats=threats,
        failure_probabilities=graph.export_failures(0),graph=dict(nodes=[dict(id=str(i),coordinates=[*INV(c[0],c[1]),c[2]],
            surface_m_egm2008=surface.at(*c[:2])) for i,c in graph.nodes.items()],edges=graph_rows,geometry=geometries,home=str(home)),
        network=dict(nodes=len(graph.nodes),directed_edges=len(graph.edges),max_horizontal_link_m=max((e['horizontal_m'] for e in graph.edges.values()),default=0)),coverage_tasks=len(tasks))
    return _finish_result(result,started)


def map_data(model):
    from core.geographic_scene import prepared_scene
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
    scene=prepared_scene(model,terrain())
    from core.mission_constraints import assess_constraints
    hourly=[assess_constraints(model,dict(time=row['valid_at']),_profile=p) for row in model['records']['M4']]
    admissible=[a for a in hourly if a['admissible']]
    observed=iso(model.get('weather_fetched_at',model['reference_time']))
    preferred=next((a for a in admissible if iso(a['time'])>=observed),next(iter(admissible),None))
    validation=dict(default_time=preferred['time'] if preferred else model['reference_time'],
        default_constraints=preferred,weather=[dict(time=a['time'],admissible=a['admissible'],reasons=a['reasons'],probability_pct=a['probability_pct']) for a in hourly])
    return dict(schema_version='patrol-map-2',area=model['study_geometry'],flight_area=model['flight_geometry'],
                bases=bases,base_catalogue=model['records']['M1'],default_origin=home['geometry']['coordinates'],demo_polygon=demo,
                weather=model['records']['M4'],reference_time=model['reference_time'],profile=p,validation=validation,
                layers={k:model['records'][k] for k in ('M2','A2','A3','A4')},
                terrain=scene['terrain'],geography={k:v for k,v in scene['geography'].items() if k!='render'},
                sources=model.get('raster'),hypothetical_stations=True)


def scene_data(model):
    from core.geographic_scene import prepared_scene
    scene=prepared_scene(model,terrain())['geography']
    return dict(schema_version='geographic-render-1',sha256=scene['sha256'],render=scene['render'])


def simulate(result, request, terrain_override=None):
    """Replay a frozen route; turn at a split graph edge after thermal detection.

    A failed link detected ahead triggers safe return from its source. This is
    explicitly an interrupted patrol, never counted as completed surveillance.
    """
    route_set=request.get('route_set','comparison')
    if route_set not in ('comparison','alternatives'):raise ValueError('route_set debe ser comparison o alternatives')
    available=result['routes'] if route_set=='comparison' else result.get('route_alternatives',{})
    method = request.get('method',next(iter(available),''))
    if method not in available or available[method]['status']!='ready':
        raise ValueError('Elegir una ruta viable para simular')
    p = result['effective_profile']
    seed=request.get('seed',p['seed'])
    if type(seed) is not int or not 0<=seed<2**31:
        raise ValueError('seed requiere un entero entre 0 y 2147483647')
    scenario=request.get('scenario','sampled')
    if scenario not in ('sampled','nominal'):raise ValueError('scenario debe ser sampled o nominal')
    scenario_index=request.get('scenario_index',0)
    if type(scenario_index) is not int or not 0<=scenario_index<2**31:raise ValueError('scenario_index requiere entero entre 0 y 2147483647')
    active,draws = set(),[]
    for threat in result['threats']:
        value = threat_uniform(seed,scenario_index,threat['id']) if scenario=='sampled' else None
        occurs = value is not None and value<threat['probability_pct']
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
    if terrain_override is None:
        # Recover exactly the scene used by this in-memory result, not a silently changed snapshot.
        from core.geographic_scene import surface_by_hash
        t=surface_by_hash(result.get('geographic_scene',{}).get('sha256'))
    else:t=terrain_override
    fire_xy = FWD(*fire) if fire else None
    fire_z = t.at(*fire_xy) if fire else None
    if fire is not None and fire_z is None:
        raise ValueError('Foco sin elevación; detección desconocida')
    route = available[method]
    edges = {e['id']:dict(e) for e in result['graph']['edges']}
    nodes = {n['id']:n['coordinates'] for n in result['graph']['nodes']}
    canonical_vertical=bool(result.get('vertical_profile'))
    support={n['id']:n.get('surface_m_egm2008') for n in result['graph']['nodes']}
    station_nodes={s['id']:str(s['node']) for s in result['stations']}
    def ground_at(node):
        if not canonical_vertical:return nodes[node][2]-p['altitude_agl_m']
        height=support.get(node)
        if height is None:raise ValueError('Geometría vertical canónica sin cota de apoyo')
        return height
    def ascent_at(node):return (nodes[node][2]-ground_at(node))/p['climb_ms']
    def landing_at(node):return (nodes[node][2]-ground_at(node))/p['descent_ms']
    def sample_edge(edge):
        if 'coordinates' in edge:return edge['coordinates']
        if edge.get('geometry_id') in result['graph'].get('geometry',{}):
            points=result['graph']['geometry'][edge['geometry_id']]
            return list(reversed(points)) if edge.get('geometry_reversed') else points
        if canonical_vertical:raise ValueError('Arista sin geometría vertical canónica; recalcular la misión')
        a,b=nodes[edge['source']],nodes[edge['target']]
        ax,ay=FWD(*a[:2]);bx,by=FWD(*b[:2])
        points=[]
        for f in segment_fractions(t,[ax,ay],[bx,by]):
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
    initial_ascent = ascent_at(home)
    elapsed = initial_ascent
    remaining = p['battery_budget_s']-initial_ascent
    ground=[*nodes[home][:2],ground_at(home)]
    timeline = [dict(coordinates=ground,time_s=0.,battery_pct=100.,phase='takeoff'),
                dict(coordinates=nodes[home],time_s=elapsed,battery_pct=100*remaining/p['battery_budget_s'],phase='patrol')]
    current = home
    detection = None
    interrupted = False
    coordinate_index = 0
    station_stops = {s['coordinate_index']:s for s in route['stops']}
    edge_stops={s['after_edge_count']:s for s in route['stops'] if 'after_edge_count' in s}
    used_stations = set()
    wind_angle=math.radians(result['weather']['wind_direction_deg'])
    wx=-result['weather']['wind_speed_ms']*math.sin(wind_angle)
    wy=-result['weather']['wind_speed_ms']*math.cos(wind_angle)
    def segment_times(points):
        values=[]
        for a,b in zip(points,points[1:]):
            ax,ay=FWD(*a[:2]);bx,by=FWD(*b[:2]);dx,dy=bx-ax,by-ay;horizontal=math.hypot(dx,dy);dz=b[2]-a[2]
            vertical=abs(dz)/(p['climb_ms'] if dz>=0 else p['descent_ms'])
            if horizontal<1e-7:values.append(vertical);continue
            along=(wx*dx+wy*dy)/horizontal;cross=(wx*dy-wy*dx)/horizontal
            speed=math.sqrt(max(0,p['cruise_ms']**2-cross**2))+along
            values.append(max(horizontal/max(speed,1e-9),vertical))
        return values
    def append_points(points,seconds,phase):
        nonlocal elapsed,remaining
        lengths = segment_times(points)
        total = sum(lengths)
        for c,length in zip(points[1:],lengths):
            dt = seconds*length/total if total else 0
            elapsed += dt
            remaining -= dt
            timeline.append(dict(coordinates=c,time_s=elapsed,battery_pct=max(0,100*remaining/p['battery_budget_s']),phase=phase))
    def battery_swap(duration,station_id):
        nonlocal elapsed,remaining
        node=station_nodes[station_id];takeoff=ascent_at(node)
        last=timeline[-1]['coordinates'];ground=[last[0],last[1],ground_at(node)]
        landing=landing_at(node);elapsed+=landing;remaining-=landing
        timeline.append(dict(coordinates=ground,time_s=elapsed,battery_pct=max(0,100*remaining/p['battery_budget_s']),phase='battery_swap'))
        elapsed+=max(0,duration-landing-takeoff)
        remaining=p['battery_budget_s']
        timeline.append(dict(coordinates=ground,time_s=elapsed,battery_pct=100.,phase='takeoff'))
        elapsed+=takeoff;remaining-=takeoff
        timeline.append(dict(coordinates=last,time_s=elapsed,battery_pct=100*remaining/p['battery_budget_s'],phase='patrol'))
    def find_recovery(battery_remaining,mission_elapsed):
        # Physical resources; report feasibility is checked BEFORE spending reserve.
        failed_nodes={r['id'] for r in result['failure_probabilities']['nodes'] if active.intersection(r['by_threat'])}
        base_targets={home:'origin',**{str(s['node']):s['id'] for s in result['stations']}}
        base_targets={node:ident for node,ident in base_targets.items() if node not in failed_nodes}
        minimum_landing=min((landing_at(node) for node in base_targets),default=math.inf)
        station_by_node = {str(s['node']):s for s in result['stations'] if s['id'] not in used_stations and str(s['node']) not in failed_nodes}
        queue = [(0,0,current,battery_remaining,[],[],frozenset())]
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
            if mission_elapsed+cost+minimum_landing>p['mission_budget_s']:
                continue
            if node in base_targets and battery>=landing_at(node) and mission_elapsed+cost+landing_at(node)<=p['mission_budget_s']:
                recovery = (path,stops,node)
                break
            if node in station_by_node and node not in mask and battery>=landing_at(node):
                serial += 1
                takeoff=ascent_at(node);duration = landing_at(node)+p['station_service_s']+takeoff
                heapq.heappush(queue,(cost+duration,serial,node,p['battery_budget_s']-takeoff,path,
                                      stops+[(len(path),duration,station_by_node[node]['id'])],mask|{node}))
            for i in adjacency.get(node,[]):
                edge = edges[i]
                if edge['time_s']<=battery:
                    serial += 1
                    heapq.heappush(queue,(cost+edge['time_s'],serial,edge['target'],battery-edge['time_s'],path+[i],stops,mask))
        return recovery,base_targets
    for completed_edges,ident in enumerate(route['edge_ids'],1):
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
            distances = segment_times(points)
            fraction = sum(distances[:hit])/sum(distances) if sum(distances) else 0
            append_points(points[:hit+1],e['time_s']*fraction,'patrol')
            current = 'detection'
            nodes[current] = points[hit]
            adjacency[current] = []
            suffix = points[hit:]
            reverse = next((r for r in edges.values() if r['source']==e['target'] and r['target']==e['source']),None)
            # Both residual arcs preserve their original wind-dependent durations.
            for name,target,coords,duration in [('ahead',e['target'],suffix,e['time_s']*(1-fraction)),
                                               ('behind',e['source'],list(reversed(points[:hit+1])),sum(segment_times(list(reversed(points[:hit+1])))) if reverse else math.inf)]:
                if not math.isfinite(duration):
                    continue
                edge_id = f'split-{name}'
                edges[edge_id] = dict(source=current,target=target,coordinates=coords,time_s=duration,hazard_ids=[])
                adjacency[current].append(edge_id)
            detection = dict(synthetic=True,fire_coordinates=fire,observer_coordinates=nodes[current],detected_at_s=elapsed,
                             reported_at_s=None,verification_s=p['verification_s'],report_status='incomplete',report_completed=False,
                             detected_at_utc=(iso(result['time'])+timedelta(seconds=elapsed)).isoformat(),reported_at_utc=None)
            timeline.append(dict(coordinates=nodes[current],time_s=elapsed,battery_pct=max(0,100*remaining/p['battery_budget_s']),phase='detection'))
            can_report,_=find_recovery(remaining-p['verification_s'],elapsed+p['verification_s'])
            if can_report is not None:
                elapsed += p['verification_s'];remaining -= p['verification_s']
                detection.update(reported_at_s=elapsed,reported_at_utc=(iso(result['time'])+timedelta(seconds=elapsed)).isoformat(),report_status='completed',report_completed=True)
                timeline.append(dict(coordinates=nodes[current],time_s=elapsed,battery_pct=max(0,100*remaining/p['battery_budget_s']),phase='report'))
            else:
                detection['report_incomplete_reason']='Unforeseen threat prevents report plus safe return within physical battery or mission budget; return takes priority'
            break
        append_points(points,e['time_s'],'patrol')
        coordinate_index += len(points)-1
        current = e['target']
        stop=edge_stops.get(completed_edges)
        if stop is None and not edge_stops:stop=station_stops.get(coordinate_index)
        if stop is not None:
            battery_swap(stop['service_s'],stop['station_id'])
            used_stations.add(stop['station_id'])
    landing_node=home
    state = 'completed'
    returned_to='origin'
    if detection or interrupted:
        recovery,base_targets = find_recovery(remaining,elapsed)
        if recovery is None:
            state = 'no_safe_return'
        else:
            path,stops,landing_node = recovery
            returned_to=base_targets[landing_node]
            stops = {i:(duration,ident) for i,duration,ident in stops}
            for j,i in enumerate(path):
                if j in stops:
                    battery_swap(stops[j][0],stops[j][1])
                append_points(sample_edge(edges[i]),edges[i]['time_s'],'return')
            state = ('detected_and_returned' if detection['report_status']=='completed' else 'detected_report_incomplete_and_returned') if detection else 'interrupted_and_returned'
    if state!='no_safe_return':
        landing=landing_at(landing_node)
        elapsed += landing
        remaining -= landing
        last=timeline[-1]['coordinates']
        timeline.append(dict(coordinates=[last[0],last[1],ground_at(landing_node)],time_s=elapsed,battery_pct=max(0,100*remaining/p['battery_budget_s']),phase='landed'))
    for frame in timeline:
        frame['position_utm']=[*FWD(*frame['coordinates'][:2]),frame['coordinates'][2]]
    return dict(schema_version='patrol-simulation-2',result_sha256=result['sha256'],method=method,route_set=route_set,scenario=scenario,
                seed=request.get('seed',p['seed']),scenario_index=scenario_index,rng_protocol='sha256/53-bit-uniform-v1',draws=draws,active_threat_ids=sorted(active),timeline=timeline,
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
