"""Versioned OSM/CONAF scene, DSM contours and conservative obstacle envelope.

All computation uses metres in EPSG:32719. Estimated heights are labeled; OSM
coverage is incomplete and the DSM is a surface model, not surveyed ground.
"""
from __future__ import annotations

import hashlib
import gzip
import json
import math
import re
import sys
import threading
from collections import Counter,OrderedDict
from functools import lru_cache
from pathlib import Path

import numpy as np
from shapely import make_valid, set_precision
from shapely.geometry import Point, LineString, Polygon, box, shape, mapping
from shapely.ops import transform, unary_union, polygonize, linemerge, triangulate
from shapely.strtree import STRtree

from core.aerial_data import FWD, INV, polygonal
from core.contracts import ROOT, canonical, sha256

COLORS={'buildings':[.72,.68,.60],'water':[.24,.56,.71],
        'wood':[.23,.43,.27],'forest':[.23,.43,.27],'Bosques':[.23,.43,.27],
        'scrub':[.49,.57,.32],'Praderas y Matorrales':[.49,.57,.32],
        'grassland':[.60,.68,.42],'grass':[.60,.68,.42],'meadow':[.60,.68,.42],
        'residential':[.69,.68,.62],'industrial':[.63,.64,.64],
        'sand':[.83,.77,.57],'bare_rock':[.65,.64,.59],'trees':[.20,.41,.25],
        'roads':[.86,.83,.73],'contours':[.40,.36,.27]}
_CACHE=OrderedDict()
_LOCK=threading.Lock()
_PAYLOAD={}
_PAYLOAD_LOCK=threading.RLock()
SCENE_CACHE_BYTES=256*1024*1024


def retained_size(value):
    """Estimate owned Python buffers, counting shared objects once."""
    seen=set()
    def measure(item):
        ident=id(item)
        if ident in seen:return 0
        seen.add(ident);size=sys.getsizeof(item)
        if isinstance(item,dict):size+=sum(measure(k)+measure(v) for k,v in item.items())
        elif isinstance(item,(list,tuple)):size+=sum(measure(v) for v in item)
        return size
    return measure(value)


def scene_config():
    return json.loads((ROOT/'config/escena.json').read_text(encoding='utf-8'))


def height_metres(value):
    """OSM default unit is m; recognize explicit feet, never silently strip units."""
    match=re.fullmatch(r'\s*(\d+(?:[.,]\d+)?)\s*(m|metres?|meters?|ft|feet|\')?\s*',str(value or ''),re.I)
    if not match:return None
    v=float(match[1].replace(',','.'))*(.3048 if (match[2] or '').lower() in ('ft','feet',"'") else 1)
    return v if 0<v<=600 else None


def feature_height(tags,kind,config):
    explicit=height_metres(tags.get('height'))
    if explicit is not None:return explicit,'osm:height',False
    if kind=='buildings':
        levels=height_metres(tags.get('building:levels'))
        if levels and levels<=150:return levels*config['floor_height_m'],'osm:building:levels × assumed floor height',True
        return config['building_default_height_m'],'assumed building height',True
    return config['tree_default_height_m'],'assumed tree height',True


def geometry_from_osm(element):
    def line(points):
        coords=[(p['lon'],p['lat']) for p in points if p and 'lon' in p and 'lat' in p]
        return LineString(coords) if len(coords)>=2 else None
    if element['type']=='node':return Point(element['lon'],element['lat'])
    if element['type']=='way':
        g=line(element.get('geometry',[]))
        if g is None:return None
        tags=element.get('tags',{})
        area=any(k in tags for k in ('building','building:part','landuse','landcover')) or tags.get('natural') in ('water','wood','scrub','grassland','wetland','sand','bare_rock') or tags.get('leisure')=='park' or tags.get('area')=='yes'
        return make_valid(Polygon(g.coords)) if area and g.is_ring else g
    outer=[];inner=[]
    for member in element.get('members',[]):
        if member.get('type')!='way':continue
        g=line(member.get('geometry',[]))
        if g is not None:(inner if member.get('role')=='inner' else outer).append(g)
    if not outer:return None
    # Joining member ways preserves courtyard holes and never closes missing rings.
    shells=list(polygonize(unary_union(outer)))
    if not shells:return None
    g=unary_union(shells)
    holes=list(polygonize(unary_union(inner))) if inner else []
    return make_valid(g.difference(unary_union(holes))) if holes else g


def classify(tags,geom):
    if any(tags.get(k) not in (None,'no') for k in ('building','building:part')):return 'buildings'
    if tags.get('natural') in ('tree','tree_row'):return 'trees'
    if tags.get('natural')=='water' or tags.get('waterway') or tags.get('landuse') in ('reservoir','basin'):return 'water'
    if tags.get('natural')=='coastline':return 'coastline'
    if tags.get('highway'):return 'roads'
    if any(k in tags for k in ('landuse','landcover','natural')) or tags.get('leisure')=='park':return 'landcover'
    return None


def normalized_features(doc,area,config):
    groups={k:[] for k in ('buildings','water','landcover','trees','roads','coastline')}
    rejected=Counter()
    seen=set()
    for element in doc['elements']:
        ident=f"{element['type']}/{element['id']}"
        if ident in seen:continue
        seen.add(ident)
        tags=element.get('tags',{})
        g=geometry_from_osm(element)
        if g is None:rejected['incomplete_geometry']+=1;continue
        kind=classify(tags,g)
        if kind is None:continue
        g=transform(FWD,g)
        extent=area.envelope if kind=='coastline' else area
        if not g.intersects(extent):continue
        g=make_valid(g).intersection(extent)
        if g.is_empty:continue
        if kind in ('landcover','water','roads'):
            g=g.simplify(1,preserve_topology=True)
        if kind in ('buildings','landcover'):
            g=polygonal(g)
            if g.is_empty:rejected['nonpolygon_'+kind]+=1;continue
        if kind=='water' and g.geom_type in ('LineString','MultiLineString'):
            # Tagged width if present, otherwise a labeled cartographic assumption.
            width=height_metres(tags.get('width')) or 3
            g=g.buffer(width/2,cap_style='flat')
        category=tags.get('landcover') or tags.get('natural') or tags.get('landuse') or tags.get('leisure') or kind
        props=dict(id='osm:'+ident,source='OpenStreetMap',osm_url='https://www.openstreetmap.org/'+ident,
                   name=tags.get('name',''),category=category,tags=tags,
                   version=element.get('version'),timestamp=element.get('timestamp'))
        if kind in ('buildings','trees'):
            h,basis,assumed=feature_height(tags,kind,config)
            props.update(height_m=h,height_basis=basis,height_estimated=assumed)
        if kind=='water' and tags.get('waterway'):
            props['width_basis']='osm:width' if height_metres(tags.get('width')) else 'assumed 3 m channel width'
        groups[kind].append(dict(geometry=g,properties=props))
    return groups,dict(rejected)


def coastal_water(coasts,area):
    """Only closed subdivisions; OSM coastline direction places water on the right."""
    lines=[g for row in coasts for g in getattr(row['geometry'],'geoms',[row['geometry']]) if g.geom_type=='LineString']
    if not lines:return []
    segments=[(a,b) for g in lines for a,b in zip(list(g.coords),list(g.coords)[1:]) if a!=b]
    edges=STRtree([LineString([a,b]) for a,b in segments])
    # Clipping introduces subnanometre endpoint differences. Snap in metric space
    # before noding so a coast reaching the AOI boundary really partitions it.
    network=unary_union([set_precision(area.boundary,.01),*[set_precision(g,.01) for g in lines]])
    faces=list(polygonize(network))
    water=[]
    for face in faces:
        p=face.representative_point()
        if not area.covers(p):continue
        a,b=segments[int(edges.nearest(p))]
        if (b[0]-a[0])*(p.y-a[1])-(b[1]-a[1])*(p.x-a[0])<0:water.append(face.intersection(area))
    return water


def _values(base,geom):
    p=geom.representative_point()
    samples=[base.at(p.x,p.y)]
    w,s,e,n=geom.bounds
    for x,y in [(w,s),(w,n),(e,s),(e,n)]:samples.append(base.at(x,y))
    return [v for v in samples if v is not None]


class SceneSurface:
    """max(DSM, nearby DSM base + tagged/assumed object height), never DSM+height."""
    def __init__(self,base,groups,config,source_hash):
        self.base,self.groups,self.config=base,groups,config
        self.source_sha256=hashlib.sha256((base.source_sha256+source_hash).encode()).hexdigest()
        self.obstacles=[]
        for kind in ('buildings','trees','landcover'):
            for item in groups[kind]:
                geom,props=item['geometry'],item['properties']
                if kind=='landcover':
                    if props['category'] not in ('wood','forest','Bosques'):continue
                    height=config['woodland_default_height_m']
                    props.update(height_m=height,height_estimated=True,height_basis='assumed woodland canopy height')
                else:height=props['height_m']
                if kind=='trees':
                    radius=(height_metres(props.get('tags',{}).get('diameter_crown')) or config['tree_default_crown_m'])/2
                    geom=geom.buffer(radius)
                sample=_values(base,geom)
                # Neighbor surface minimum is an approximation, not a DTM observation.
                p=geom.representative_point()
                neighbors=[base.at(p.x+dx,p.y+dy) for dx,dy in [(-30,0),(30,0),(0,-30),(0,30)]]
                valid=sample+[v for v in neighbors if v is not None]
                if not valid:continue
                bottom=min(valid)
                top=max(max(sample or valid),bottom+height)
                props.update(base_elevation_m=round(bottom,2),top_elevation_m=round(top,2),
                             vertical_basis='max(DSM, nearby DSM minimum + object height); EGM2008',
                             ground_estimated=True)
                self.obstacles.append((geom,bottom,top,props['id'],kind,height))
        self.tree=STRtree([o[0] for o in self.obstacles])
        self.water=STRtree([r['geometry'] for r in groups['water']])
        # Instance-local cache: expelling a scene releases its sampling memory.
        self.at=lru_cache(maxsize=150000)(self._sample)

    def can_land(self,x,y):
        return not len(self.water.query(Point(x,y),predicate='intersects'))

    def _sample(self,x,y):
        raw=self.base.at(x,y)
        if raw is None:return None
        point=Point(x,y)
        ids=self.tree.query(point,predicate='intersects')
        tops=[raw]
        for i in ids:
            geom,bottom,top,_,kind,height=self.obstacles[int(i)]
            if kind=='landcover':
                neighbors=[self.base.at(x+dx,y+dy) for dx,dy in [(-30,0),(30,0),(0,-30),(0,30)]]
                top=min([raw]+[h for h in neighbors if h is not None])+height
            tops.append(top)
        return max(tops)

    def fractions(self,a,b):
        distance=math.dist(a[:2],b[:2])
        values=set(float(f) for f in np.linspace(0,1,max(2,math.ceil(distance/15)+1)))
        if distance==0:return sorted(values)
        line=LineString([a[:2],b[:2]])
        for i in self.tree.query(line,predicate='intersects'):
            intersection=line.intersection(self.obstacles[int(i)][0])
            for part in getattr(intersection,'geoms',[intersection]):
                coords=list(part.coords) if hasattr(part,'coords') else []
                for xy in coords:
                    f=line.project(Point(xy))/distance
                    for delta in (-.05/distance,0,.05/distance):values.add(max(0,min(1,f+delta)))
        ordered=sorted(values);clean=[0.]
        for f in ordered[1:-1]:
            if (f-clean[-1])*distance>=.0001 and (1-f)*distance>=.0001:clean.append(f)
        return [*clean,1.]

    def visible(self,observer,target):
        a,b=np.array(observer[:2]),np.array(target[:2])
        for f in self.fractions(observer,target)[1:-1]:
            x,y=a+(b-a)*f
            h=self.at(float(x),float(y))
            if h is None or h>observer[2]+(target[2]-observer[2])*f+.01:return False
        return True


def contour_features(mesh,interval):
    """Piecewise-linear contours of exactly the displayed DSM triangles, no nodata bridging."""
    width,height=mesh['width'],mesh['height']
    x,y=mesh['x'],mesh['y'];z=mesh['elevations'];ox,oy=mesh['origin_utm']
    segments={}
    for j in range(height-1):
        for i in range(width-1):
            for inds in [(j*width+i,j*width+i+1,(j+1)*width+i),(j*width+i+1,(j+1)*width+i+1,(j+1)*width+i)]:
                if any(z[k] is None for k in inds):continue
                points=[(x[k%width]+ox,y[k//width]+oy,z[k]) for k in inds]
                low,high=min(p[2] for p in points),max(p[2] for p in points)
                for level in range(math.ceil(low/interval)*interval,math.floor(high/interval)*interval+1,interval):
                    hits=[]
                    for a,b in zip(points,points[1:]+points[:1]):
                        if a[2]==b[2]:continue
                        if min(a[2],b[2])<=level<max(a[2],b[2]):
                            f=(level-a[2])/(b[2]-a[2]);hits.append((a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1])))
                    if len(hits)==2 and hits[0]!=hits[1]:segments.setdefault(level,[]).append(LineString(hits))
    features=[]
    for level,lines in sorted(segments.items()):
        merged=linemerge(lines) if len(lines)>1 else lines[0]
        for i,g in enumerate(getattr(merged,'geoms',[merged])):
            if g.length<2:continue
            features.append(dict(geometry=g.simplify(.3,preserve_topology=True),properties=dict(id=f'contour:{level}:{i}',source='Copernicus DSM GLO-30',
                elevation_m=level,index=level%(interval*5)==0,interval_m=interval,vertical_datum='EGM2008',
                description='Surface contour derived from DSM; not surveyed bare-earth terrain')))
    return features


class GeographicScene:
    def __init__(self,model,base,manifest,config,source_hash):
        folder=ROOT/config['directory']
        raw=(folder/manifest['file']).resolve()
        if not raw.is_relative_to(folder.resolve()) or sha256(raw)!=manifest['sha256']:
            raise ValueError('Instantánea OSM alterada o fuera del directorio')
        area=transform(FWD,shape(model['flight_geometry']))
        self.groups,self.rejected=normalized_features(json.loads(raw.read_text(encoding='utf-8')),area,config)
        # Marine context covers the rectangular DSM view, including outside the
        # flight polygon. This does not expand the permissible routing area.
        for i,g in enumerate(coastal_water(self.groups['coastline'],area.envelope)):
            self.groups['water'].append(dict(geometry=g,properties=dict(id=f'osm:coastal-water:{i}',
                source='OpenStreetMap coastline',category='sea',name='Océano Pacífico',
                level_m=0,vertical_basis='Approximate mean sea level 0 m EGM2008 for display; does not fill DSM nodata for flight',
                geometry_basis='Closed polygons from OSM coastline direction: water to right')))
        # Fill gaps with the existing land-use catalogue, retaining its provider/year.
        for row in model['records']['M2']:
            g=polygonal(make_valid(transform(FWD,shape(row['geometry']))).intersection(area)).simplify(1,preserve_topology=True)
            if g.is_empty:continue
            self.groups['landcover'].insert(0,dict(geometry=g,properties=dict(
                id='conaf:'+str(row['provider_id']),source='CONAF / Catastro uso del suelo',
                category=row.get('category','sin clase'),source_year=row.get('source_year',2019),
                attributes={k:v for k,v in row.items() if k not in ('geometry','original_record')})))
        self.surface=SceneSurface(base,self.groups,config,source_hash)
        self.manifest,self.config,self.area,self.base=manifest,config,area,base
        self.source_hash=source_hash
        self._payload=None
        self.cache_weight=retained_size(self.groups)+sum(len(r['geometry'].wkb)*2 for rows in self.groups.values() for r in rows)+150000*192

    def payload(self):
        if self._payload is not None:return self._payload
        mesh=self.base.mesh(self.area,step=self.config['mesh_step_m'])
        self.groups['contours']=contour_features(mesh,self.config['contour_interval_m'])
        layers={};render={};ox,oy=mesh['origin_utm']
        def local(x,y,z):return [round(x-ox,2),round(y-oy,2),round(z,2)]
        def surfaces(geom,height=None,offset=1):
            out=[]
            for poly in getattr(polygonal(geom),'geoms',[]):
                for tri in triangulate(poly):
                    # covers rejects triangles crossing holes or concave exterior.
                    if not poly.covers(tri):continue
                    coords=list(tri.exterior.coords)[:3]
                    for x,y in coords:
                        z=height if height is not None else self.base.at(x,y)
                        if z is None:break
                    else:
                        out.extend(v for x,y in coords for v in local(x,y,(height if height is not None else self.base.at(x,y))+offset))
            return out
        for kind,rows in self.groups.items():
            if kind=='coastline':continue
            features=[];batches=[]
            for row in rows:
                g,props=row['geometry'],row['properties']
                features.append(dict(type='Feature',geometry=mapping(transform(INV,g)),properties=props))
                color=COLORS.get(props.get('category'),COLORS.get(kind,[.67,.68,.52]))
                vertices=[];mode='triangles'
                if kind=='buildings' and 'top_elevation_m' in props:
                    top,bottom=props['top_elevation_m'],props['base_elevation_m']
                    vertices=surfaces(g,top,0)
                    for poly in polygonal(g).geoms:
                        for ring in [poly.exterior,*poly.interiors]:
                            for a,b in zip(list(ring.coords),list(ring.coords)[1:]):
                                for x,y,z in [(a[0],a[1],bottom),(b[0],b[1],bottom),(a[0],a[1],top),(a[0],a[1],top),(b[0],b[1],bottom),(b[0],b[1],top)]:vertices.extend(local(x,y,z))
                elif kind=='trees' and 'top_elevation_m' in props:
                    points=[g] if g.geom_type=='Point' else [g.interpolate(i) for i in np.arange(0,g.length,10)] if g.geom_type=='LineString' else [g.representative_point()]
                    radius=(height_metres(props.get('tags',{}).get('diameter_crown')) or self.config['tree_default_crown_m'])/2
                    for p in points:
                        bottom,top=props['base_elevation_m'],props['top_elevation_m']
                        for i in range(8):
                            a,b=i*math.pi/4,(i+1)*math.pi/4
                            for x,y,z in [(p.x+radius*math.cos(a),p.y+radius*math.sin(a),bottom+(top-bottom)*.35),(p.x+radius*math.cos(b),p.y+radius*math.sin(b),bottom+(top-bottom)*.35),(p.x,p.y,top)]:vertices.extend(local(x,y,z))
                        vertices.extend(surfaces(p.buffer(.22,quad_segs=2),bottom+(top-bottom)*.4))
                elif kind in ('landcover','water'):
                    # Subdivide long polygons against the terrain grid: no floating flat lakes/forests.
                    w,s,e,n=g.bounds;step=120
                    for x in np.arange(math.floor(w/step)*step,e,step):
                        for y in np.arange(math.floor(s/step)*step,n,step):
                            part=g.intersection(box(x,y,x+step,y+step))
                            if not part.is_empty:vertices.extend(surfaces(part,height=0 if props.get('category')=='sea' else None,offset=1.2 if kind=='water' else .7))
                elif kind in ('roads','contours'):
                    mode='lines'
                    for line in getattr(g,'geoms',[g]):
                        if line.geom_type!='LineString':continue
                        points=list(line.segmentize(15).coords)
                        for a,b in zip(points,points[1:]):
                            za,zb=self.base.at(*a),self.base.at(*b)
                            if za is None or zb is None:continue
                            if kind=='contours':za=zb=props['elevation_m']
                            vertices.extend(local(*a,za+1.8));vertices.extend(local(*b,zb+1.8))
                if vertices:batches.append(dict(vertices=vertices,color=color,mode=mode))
            layers[kind]=dict(type='FeatureCollection',features=features)
            render[kind]=batches
        # Representative crowns in mapped woods are visual symbols, not invented tree observations.
        crowns=[];symbols=0
        woods=unary_union([r['geometry'] for r in self.groups['landcover'] if r['properties']['category'] in ('wood','forest','Bosques')])
        if not woods.is_empty:
            w,s,e,n=woods.bounds
            for x in np.arange(math.ceil(w/65)*65,e,65):
                for y in np.arange(math.ceil(s/65)*65,n,65):
                    p=Point(x,y)
                    z=self.base.at(x,y)
                    if z is None or not woods.covers(p):continue
                    symbols+=1
                    for i in range(6):
                        a,b=i*math.pi/3,(i+1)*math.pi/3
                        for px,py,pz in [(x+5*math.cos(a),y+5*math.sin(a),z+3),(x+5*math.cos(b),y+5*math.sin(b),z+3),(x,y,z+self.config['woodland_default_height_m'])]:crowns.extend(local(px,py,pz))
            render['trees'].append(dict(vertices=crowns,color=COLORS['trees'],mode='triangles'))
        estimated=sum(r['properties'].get('height_estimated',False) for rows in self.groups.values() for r in rows)
        self._payload=dict(schema_version='geographic-scene-1',sha256=self.source_hash,
            crs='EPSG:32719',vertical_datum='EGM2008',origin_utm=[ox,oy],
            layers=layers,render=render,counts={k:len(v['features']) for k,v in layers.items()},
            rejected=self.rejected,height_estimates=estimated,contour_interval_m=self.config['contour_interval_m'],
            woodland_symbols=symbols,woodland_symbol_basis='Representative symbols on mapped woodland; not an individual-tree inventory',
            source=dict(self.manifest,query=None),tile_url=self.config['osm_tile_url'],
            surface_sha256=self.surface.source_sha256,
            assumptions=['OSM coverage is incomplete; absence does not establish obstacle clearance',
                         'Heights and nearby DSM minimum ground are estimates unless tagged; DSM already contains surface objects',
                         'Obstacle envelope uses max(DSM, estimated base + height), not DSM + height',
                         'CONAF 2019 land use and OSM describe mapped cover, not a current satellite classification',
                         'Contours are DSM surface contours, not surveyed bare-earth contours',
                         'Water, roads and land cover generalized by 1 m for display; contour lines by 0.3 m'])
        return self._payload


def scene_identity(model,base):
    config=scene_config();folder=ROOT/config['directory']
    path=folder/'manifest.json'
    if not path.exists():raise ValueError('Falta instantánea geográfica: ejecutar python -m Infraestructura.descargar_escena')
    manifest=json.loads(path.read_text(encoding='utf-8'))
    data=dict(manifest=manifest,config=config,area=model['flight_geometry'],
              landcover=model['records']['M2'],terrain=base.source_sha256,code_sha256=sha256(Path(__file__)))
    key=hashlib.sha256(canonical(data)).hexdigest()
    return key,manifest,config


def get_scene(model,base):
    key,manifest,config=scene_identity(model,base)
    with _LOCK:
        if key not in _CACHE:
            scene=GeographicScene(model,base,manifest,config,key)
            if scene.cache_weight>SCENE_CACHE_BYTES:raise ValueError('La escena supera el presupuesto de memoria del servidor')
            _CACHE[key]=scene
            while len(_CACHE)>2 or (len(_CACHE)>1 and sum(s.cache_weight for s in _CACHE.values())>SCENE_CACHE_BYTES):
                _,removed=_CACHE.popitem(last=False)
                removed.surface.at.cache_clear();removed._payload=None
        _CACHE.move_to_end(key)
        return _CACHE[key]


def surface_by_hash(key):
    with _LOCK:
        scene=_CACHE.get(key)
    if scene is None:raise ValueError('Escena geográfica no disponible; recalcular la misión')
    return scene.surface


def prepared_scene(model,base):
    # Loading/preparing one large scene is single-flight, not one copy per HTTP request.
    with _PAYLOAD_LOCK:return _prepared_scene(model,base)


def _prepared_scene(model,base):
    key,_,config=scene_identity(model,base)
    if key in _PAYLOAD:return _PAYLOAD[key]
    folder=ROOT/config['directory'];meta=folder/f'scene_{key[:16]}.manifest.json'
    if meta.exists():
        report=json.loads(meta.read_text(encoding='utf-8'))
        path=(folder/report['file']).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256(path)!=report['sha256'] or report['scene_sha256']!=key:
            raise ValueError('Escena preprocesada alterada')
        with gzip.open(path,'rt',encoding='utf-8') as stream:payload=json.load(stream)
        if payload['geography']['sha256']!=key:raise ValueError('Escena preprocesada de otra instantánea')
    else:
        scene=get_scene(model,base)
        payload=dict(terrain=base.mesh(scene.area,step=config['mesh_step_m']),geography=scene.payload())
    _PAYLOAD.clear()
    # The render lists are retained in exactly one place and only within the budget.
    with _LOCK:
        for cached in _CACHE.values():cached._payload=None
    if retained_size(payload)<=SCENE_CACHE_BYTES:_PAYLOAD[key]=payload
    return payload


def prepare(model,base):
    key,_,config=scene_identity(model,base)
    payload=prepared_scene(model,base)
    folder=ROOT/config['directory'];filename=f'scene_{key[:16]}.json.gz'
    target=folder/filename;temporary=target.with_suffix('.tmp')
    with gzip.open(temporary,'wt',encoding='utf-8',compresslevel=6) as stream:
        json.dump(payload,stream,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    temporary.replace(target)
    report=dict(schema_version='scene-artifact-1',file=filename,sha256=sha256(target),
                scene_sha256=key,code_sha256=sha256(Path(__file__)),counts=payload['geography']['counts'],
                source_osm_sha256=payload['geography']['source']['sha256'])
    (folder/f'scene_{key[:16]}.manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
