"""Content-addressed lazy geographic transport. Planning data remains untouched."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
import os
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

import numpy as np
from shapely import contains_xy,prepare
from shapely.geometry import Point,LineString,Polygon,box,shape,mapping
from shapely.ops import transform,triangulate
from core.aerial_data import FWD,INV
from core.contracts import ROOT,canonical,sha256
from core.communes import commune_index

PREFIX='/api/aereo/patrullaje/recursos/'
SUMMARY_LIMIT=1048576
_FLIGHTS={};_FLIGHT_LOCK=threading.Lock()


def atomic_write(path,body):
    """Unique sibling files also make concurrent CLI/server producers safe."""
    temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_bytes(body)
        try:temporary.replace(path)
        except PermissionError:
            # Windows can deny replace while another process has the immutable
            # target open. An identical already-published file is sufficient.
            if not path.is_file() or path.read_bytes()!=body:raise
    finally:temporary.unlink(missing_ok=True)


class ResourceStore:
    def __init__(self,folder=None,memory_limit=16*1024*1024):
        self.folder=Path(folder or ROOT/'datos/runs/transport');self.folder.mkdir(parents=True,exist_ok=True)
        self.memory_limit=memory_limit;self.memory=OrderedDict();self.memory_bytes=0;self.lock=threading.RLock()

    def put(self,body,mime='application/json; charset=utf-8'):
        digest=hashlib.sha256(body).hexdigest();target=self.folder/(digest+'.data')
        with self.lock:
            if not target.exists():
                atomic_write(target,body)
            compressed=self.folder/(digest+'.gz')
            if not compressed.exists():
                atomic_write(compressed,gzip.compress(body,compresslevel=3,mtime=0))
            metadata=dict(sha256=digest,url=PREFIX+digest,bytes=len(body),content_type=mime,gzip_bytes=compressed.stat().st_size)
            meta=self.folder/(digest+'.meta.json')
            if not meta.exists():atomic_write(meta,canonical(metadata))
            if len(body)<=262144 and digest not in self.memory:
                self.memory[digest]=body;self.memory_bytes+=len(body)
                while self.memory_bytes>self.memory_limit and self.memory:
                    _,removed=self.memory.popitem(last=False);self.memory_bytes-=len(removed)
        return metadata

    def json(self,value):return self.put(canonical(value))

    def get(self,digest):
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):return None
        with self.lock:
            meta=self.folder/(digest+'.meta.json')
            if not meta.exists() or not (self.folder/(digest+'.data')).exists():return None
            return json.loads(meta.read_text(encoding='utf-8'))

    def read_json(self,ref):
        return json.loads((self.folder/(ref['sha256']+'.data')).read_text(encoding='utf-8'))

    def memo(self,key,producer):
        token=hashlib.sha256(key.encode()).hexdigest();index=self.folder/('index_'+token+'.json')
        with _FLIGHT_LOCK:
            entry=_FLIGHTS.setdefault(token,[threading.Lock(),0]);entry[1]+=1
        try:
            with entry[0]:
                if index.exists():return json.loads(index.read_text(encoding='utf-8'))
                value=producer();atomic_write(index,canonical(value));return value
        finally:
            with _FLIGHT_LOCK:
                entry[1]-=1
                if entry[1]==0:_FLIGHTS.pop(token,None)


_STORE=None;_STORE_LOCK=threading.Lock()
def store():
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:_STORE=ResourceStore()
    return _STORE


def ref_json(value):return store().json(value)


def _clip_plane(vertices,axis,threshold,greater):
    output=[]
    for previous,current in zip(vertices[-1:]+vertices[:-1],vertices):
        av=float(np.dot(previous[:2],axis));bv=float(np.dot(current[:2],axis))
        ain=av>=threshold-1e-8 if greater else av<=threshold+1e-8
        bin=bv>=threshold-1e-8 if greater else bv<=threshold+1e-8
        if ain!=bin:
            fraction=(threshold-av)/(bv-av);output.append(previous+(current-previous)*fraction)
        if bin:output.append(current)
    return output


def clip_triangle(triangle,polygon):
    """Exact XY clipping; interpolate Z, including vertical walls with zero XY area."""
    a,b,c=triangle
    u,v=b[:2]-a[:2],c[:2]-a[:2];area=u[0]*v[1]-u[1]*v[0]
    if abs(area)>1e-7:
        intersection=Polygon(triangle[:,:2]).intersection(polygon)
        answer=[]
        for part in getattr(intersection,'geoms',[intersection]):
            if part.geom_type!='Polygon' or part.area<1e-8:continue
            matrix=np.array([[a[0],b[0],c[0]],[a[1],b[1],c[1]],[1.,1.,1.]])
            for piece in triangulate(part):
                if not part.covers(piece):continue
                for x,y in list(piece.exterior.coords)[:3]:
                    weights=np.linalg.solve(matrix,np.array([x,y,1.]));answer.append([x,y,float(weights@triangle[:,2])])
        return np.asarray(answer,dtype=np.float32).reshape((-1,3))
    pairs=[(i,j,float(np.linalg.norm(triangle[i,:2]-triangle[j,:2]))) for i in range(3) for j in range(i+1,3)]
    i,j,distance=max(pairs,key=lambda v:v[2])
    if distance<1e-8:return triangle if polygon.covers(Point(a[:2])) else np.empty((0,3),dtype=np.float32)
    line=LineString([triangle[i,:2],triangle[j,:2]]);intersection=line.intersection(polygon)
    axis=(triangle[j,:2]-triangle[i,:2])/distance;answer=[]
    for piece in getattr(intersection,'geoms',[intersection]):
        if piece.geom_type!='LineString' or piece.length<1e-7:continue
        parameters=[float(np.dot(np.array(p),axis)) for p in piece.coords]
        vertices=_clip_plane(list(triangle),axis,min(parameters),True)
        if vertices:vertices=_clip_plane(vertices,axis,max(parameters),False)
        for k in range(1,len(vertices)-1):answer.extend([vertices[0],vertices[k],vertices[k+1]])
    return np.asarray(answer,dtype=np.float32).reshape((-1,3))


def _clip_vertices(vertices,mode,polygon):
    if polygon is None:return vertices
    stride=3 if mode=='triangles' else 2;items=vertices.reshape((-1,stride,3));parts=[]
    # Most feature batches are wholly inside/outside; exact intersections only at the boundary.
    bounds=box(float(vertices[:,0].min()),float(vertices[:,1].min()),float(vertices[:,0].max()),float(vertices[:,1].max()))
    if polygon.covers(bounds):return vertices
    if not polygon.intersects(bounds):return np.empty((0,3),dtype=np.float32)
    for item in items:
        if mode=='triangles':
            poly=Polygon(item[:,:2])
            footprint=poly if poly.area>1e-7 else LineString(item[:,:2])
            if not polygon.intersects(footprint):continue
            if polygon.covers(footprint):parts.append(item);continue
            clipped=clip_triangle(item,polygon)
            if len(clipped):parts.append(clipped)
        else:
            line=LineString(item[:,:2])
            if line.length<1e-9:continue
            if not polygon.intersects(line):continue
            if polygon.covers(line):parts.append(item);continue
            cut=line.intersection(polygon)
            for section in getattr(cut,'geoms',[cut]):
                if section.geom_type!='LineString' or section.length<1e-8:continue
                for start,end in zip(list(section.coords),list(section.coords)[1:]):
                    points=[]
                    for xy in (start,end):
                        fraction=line.project(Point(xy))/line.length;points.append([*xy,item[0,2]+fraction*(item[1,2]-item[0,2])])
                    parts.append(np.asarray(points,dtype=np.float32))
    return np.concatenate(parts).astype(np.float32,copy=False) if parts else np.empty((0,3),dtype=np.float32)


def typed_assets(scene,commune_id=None,mesh=None):
    from core.terrain_style import TerrainLighting
    lighting=TerrainLighting(mesh) if mesh is not None else None
    index=commune_index();origin=scene['origin_utm'];clip=None
    if commune_id:
        metric=index.metric(commune_id)
        clip=transform(lambda x,y,z=None:(np.asarray(x)-origin[0],np.asarray(y)-origin[1]),metric)
        prepare(clip)
    groups={}
    for key,batches in scene['render'].items():
        by_mode={'triangles':[], 'lines':[]};colors={'triangles':[],'lines':[]}
        for batch in batches:
            mode=batch.get('mode','triangles');positions=np.asarray(batch['vertices'],dtype=np.float32).reshape((-1,3))
            if not len(positions):continue
            positions=_clip_vertices(positions,mode,clip)
            if not len(positions):continue
            color=np.asarray(batch['color'],dtype=np.float32)
            if mode=='triangles' and key=='landcover' and mesh is not None:
                rgb=lighting.colors(positions,base_color=color)
            elif mode=='triangles':
                triangles=positions.reshape((-1,3,3));normal=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);length=np.linalg.norm(normal,axis=1)
                light=.68+.32*np.abs((normal@np.array([-.35,-.35,.87]))/np.where(length==0,1,length))
                rgb=np.repeat(np.clip(np.rint(light[:,None]*color*255),0,255).astype(np.uint8),3,axis=0)
            else:rgb=np.tile(np.clip(np.rint(color*255),0,255).astype(np.uint8),(len(positions),1))
            by_mode[mode].append(positions);colors[mode].append(rgb)
        groups[key]=[]
        for mode,parts in by_mode.items():
            if not parts:continue
            positions=np.concatenate(parts).astype('<f4',copy=False);rgb=np.concatenate(colors[mode]).astype(np.uint8,copy=False)
            p=store().put(positions.tobytes(),'application/octet-stream');c=store().put(rgb.tobytes(),'application/octet-stream')
            groups[key].append(dict(mode=mode,count=len(positions),positions=dict(p,dtype='float32-le',components=3),colors=dict(c,dtype='uint8',components=3,normalized=True)))
    if commune_id and mesh is not None:
        width,height=mesh['width'],mesh['height'];elevations=np.array([np.nan if z is None else z for z in mesh['elevations']])
        xs,ys=np.meshgrid(mesh['x'],mesh['y']);vertices=np.column_stack((xs.ravel(),ys.ravel(),elevations))
        indices=np.arange(width*height).reshape((height,width));a=indices[:-1,:-1].ravel();b=indices[:-1,1:].ravel();c=indices[1:,:-1].ravel();d=indices[1:,1:].ravel()
        triangles=vertices[np.concatenate((np.column_stack((a,b,c)),np.column_stack((b,d,c))))]
        triangles=triangles[np.isfinite(triangles).all(axis=(1,2))]
        positions=_clip_vertices(triangles.reshape((-1,3)).astype(np.float32),'triangles',clip)
        groups['terrain']=[]
        if len(positions):
            rgb=lighting.colors(positions)
            p=store().put(positions.astype('<f4',copy=False).tobytes(),'application/octet-stream');c=store().put(rgb.tobytes(),'application/octet-stream')
            groups['terrain']=[dict(mode='triangles',count=len(positions),positions=dict(p,dtype='float32-le',components=3),colors=dict(c,dtype='uint8',components=3,normalized=True))]
    return dict(schema_version='typed-scene-1',origin_utm=origin,crs='EPSG:32719',groups=groups)


def _features(rows):
    return [dict(type='Feature',geometry=r['geometry'],properties={k:v for k,v in r.items() if k!='geometry'}) for r in rows]


def _fc(features):return dict(type='FeatureCollection',features=features)


def _map_key(model,commune_id):
    from core.patrol import terrain,defaults
    from core.geographic_scene import scene_identity
    key,_,_=scene_identity(model,terrain());index=commune_index()
    # A physical scene can be unchanged while weather, bases or threats change.
    # Hash the entire public source context and effective defaults as well.
    identity=dict(scene=key,communes=index.identity_sha256,commune_id=commune_id,
        model={k:v for k,v in model.items() if not k.startswith('_')},profile=defaults(),
        code={name:sha256(ROOT/name) for name in ('core/patrol.py','core/patrol_events.py','core/patrol_monitoring.py','config/incendios_valparaiso.json','core/mission_constraints.py','core/communes.py','core/aerial_data.py','core/geo_transport.py','core/terrain_style.py','core/vertical_profile.py')},
        profile_config_sha256=sha256(ROOT/'config/patrullaje.json'))
    return 'map-summary-v3:'+hashlib.sha256(canonical(identity)).hexdigest()


def map_summary(model,engine,commune_id=None):
    def build():
        from core.patrol import map_data,terrain
        from core.geographic_scene import prepared_scene
        data=map_data(model);scene=prepared_scene(model,terrain())['geography'];index=commune_index()
        if commune_id:index.metric(commune_id)
        geography={k:v for k,v in data['geography'].items() if k not in ('layers','render')}
        resources=dict(terrain=ref_json(data['terrain']),layers={})
        for key in ('M1','M2','A2','A3','A4'):
            rows=data['base_catalogue'] if key=='M1' else data['layers'][key]
            features=index.clip_features(_features(rows),commune_id);ref=ref_json(_fc(features));ref['count']=len(features);resources['layers'][key]=ref
        counts={}
        for key,layer in scene['layers'].items():
            features=index.clip_features(layer['features'],commune_id);ref=ref_json(_fc(features));ref['count']=len(features);resources['layers'][key]=ref;counts[key]=len(features)
        geography['counts']=counts
        render=dict(schema_version='geographic-render-2',sha256=scene['sha256'],commune_id=commune_id,typed_assets=typed_assets(scene,commune_id,data['terrain']))
        resources['render']=ref_json(render)
        small={k:v for k,v in data.items() if k not in ('terrain','layers','geography','base_catalogue')}
        small['bases']=index.clip_rows(data['bases'],commune_id)
        small.update(schema_version='patrol-map-summary-2',geography=geography,resources=resources,
            communes=index.catalogue(shape(model['flight_geometry'])),commune_id=commune_id,
            commune_source=dict(sha256=index.sha256,manifest_sha256=index.identity_sha256,attribution=index.manifest['attribution'],license=index.manifest['license'],edition=index.manifest['derived']['edition']),
            global_layers=['M4','A1'],shared_data=['M3_original_DSM'],planning_scope='original_snapshot')
        if commune_id:small['display_area']=mapping(index.rows[commune_id]['geometry'].intersection(shape(model['flight_geometry'])))
        if len(canonical(small))>SUMMARY_LIMIT:raise ValueError('Resumen cartográfico excede 1 MiB')
        return small
    result=dict(store().memo(_map_key(model,commune_id),build));result['engine']=engine;return result


def scene_summary(model,commune_id=None):
    summary=map_summary(model,'geographic assets',commune_id)
    return store().read_json(summary['resources']['render'])


def legacy_filtered_map(model,engine,commune_id):
    from core.patrol import map_data
    data=map_data(model)
    if not commune_id:return dict(data,engine=engine)
    index=commune_index();index.metric(commune_id)
    geography=dict(data['geography'],layers={k:_fc(index.clip_features(v['features'],commune_id)) for k,v in data['geography']['layers'].items()})
    geography['counts']={k:len(v['features']) for k,v in geography['layers'].items()}
    return dict(data,engine=engine,commune_id=commune_id,communes=index.catalogue(shape(model['flight_geometry'])),
        bases=index.clip_rows(data['bases'],commune_id),base_catalogue=index.clip_rows(data['base_catalogue'],commune_id),geography=geography,
        layers={k:index.clip_rows(v,commune_id) for k,v in data['layers'].items()},global_layers=['M4','A1'])


def publish_result(result):
    digest=result['sha256']
    refs=dict(exportar=ref_json(result),probabilidades=ref_json(result.get('failure_probabilities',{})),
        nodos=ref_json(dict(nodes=result.get('graph',{}).get('nodes',[]),commune_id=None)),
        amenazas=ref_json(dict(threats=result.get('threats',[]),commune_id=None)),routes={'comparison':{},'alternatives':{}})
    for set_name,field in (('comparison','routes'),('alternatives','route_alternatives')):
        for key,row in result.get(field,{}).items():refs['routes'][set_name][key]=ref_json({k:row.get(k,[]) for k in ('coordinates','coordinates_utm','edge_ids')})
    path=store().folder/('result_'+digest+'.json');atomic_write(path,canonical(refs))
    return refs


def result_refs(digest):
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):return None
    path=store().folder/('result_'+digest+'.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def result_summary(result,refs=None):
    refs=refs or publish_result(result)
    summary={k:v for k,v in result.items() if k not in ('graph','failure_probabilities')}
    summary['evaluation']={k:v for k,v in result.get('evaluation',{}).items() if k not in ('scenarios','first_scenario')}
    summary['threats']=[{k:v for k,v in row.items() if k!='geometry'} for row in result.get('threats',[])]
    summary['resources']=refs;summary['response_view']='summary'
    if len(canonical(summary))>SUMMARY_LIMIT:
        for set_name,field in (('comparison','routes'),('alternatives','route_alternatives')):
            summary[field]={key:dict(row,coordinates=[],coordinates_utm=[],edge_ids=[],geometry_deferred=True) for key,row in result.get(field,{}).items()}
    if len(canonical(summary))>SUMMARY_LIMIT:raise ValueError('Resumen de misión excede 1 MiB')
    return summary


def filtered_result_resource(digest,kind,commune_id=None):
    refs=result_refs(digest)
    if not refs or kind not in ('exportar','probabilidades','nodos','amenazas'):return None
    ref=refs[kind]
    if not commune_id or kind not in ('nodos','amenazas'):return ref
    index=commune_index();index.metric(commune_id)
    key='result-filter-v2:'+digest+':'+kind+':'+commune_id+':'+index.sha256+':'+sha256(ROOT/'core/communes.py')
    def build():
        value=store().read_json(ref)
        if kind=='nodos':value=dict(nodes=index.clip_nodes(value['nodes'],commune_id),commune_id=commune_id)
        else:value=dict(threats=index.clip_rows(value['threats'],commune_id),commune_id=commune_id)
        return ref_json(value)
    return store().memo(key,build)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Prepare lazy map resources without an HTTP request')
    parser.add_argument('--context',required=True);args=parser.parse_args()
    from core.patrol import snapshot_context
    model=snapshot_context(args.context);index=commune_index();reports=[]
    for cut in [None,*[c['id'] for c in index.catalogue(shape(model['flight_geometry']))]]:
        data=map_summary(model,'prepared snapshot',cut);reports.append(dict(commune_id=cut,bytes=len(canonical(data)),resources=len(data['resources']['layers'])))
    print(json.dumps(reports))
