"""CUT-backed display clipping. Never replaces the original planning geometry."""
import json
import threading
from collections import OrderedDict
from pathlib import Path
from shapely import make_valid,prepare
from shapely.geometry import Point,shape,mapping
from shapely.ops import transform
from core.aerial_data import FWD,INV
from core.contracts import ROOT,sha256,canonical
import hashlib

_CACHE=OrderedDict();_LOCK=threading.Lock()


class Communes:
    def __init__(self,folder,manifest):
        path=(folder/manifest['derived']['file']).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256(path)!=manifest['derived']['sha256']:raise ValueError('Límites comunales alterados')
        doc=json.loads(path.read_text(encoding='utf-8'))
        self.manifest=manifest;self.sha256=manifest['derived']['sha256'];self.rows={}
        self.identity_sha256=hashlib.sha256(canonical(manifest)).hexdigest()
        for feature in doc['features']:
            props=feature['properties'];cut=props['id']
            metric=transform(FWD,shape(feature['geometry']));prepare(metric)
            self.rows[cut]=dict(properties=props,geometry=shape(feature['geometry']),metric=metric)

    def catalogue(self,area=None):
        return [dict(id=cut,name=r['properties']['name']) for cut,r in sorted(self.rows.items()) if area is None or r['geometry'].intersects(area)]

    def metric(self,cut):
        if cut not in self.rows:raise ValueError('Código CUT de comuna desconocido')
        return self.rows[cut]['metric']

    def clip_feature(self,feature,cut):
        if not cut:return feature
        geom=transform(FWD,shape(feature['geometry']));polygon=self.metric(cut)
        if not geom.is_valid:geom=make_valid(geom)
        if not polygon.intersects(geom):return None
        inside=polygon.covers(geom)
        clipped=geom if inside else geom.intersection(polygon)
        if clipped.is_empty:return None
        # Intersection can leave boundary-only fragments; keep the original dimensionality.
        if geom.geom_type in ('Polygon','MultiPolygon') and clipped.area<=1e-6:return None
        properties=dict(feature.get('properties',{}),commune_id=cut)
        marker=properties.get('position_utm')
        if marker is not None:
            anchor=transform(INV,clipped.representative_point())
            properties['display_anchor']=[anchor.x,anchor.y]
        return dict(feature,geometry=feature['geometry'] if inside else mapping(transform(INV,clipped)),properties=properties)

    def clip_features(self,features,cut):
        if not cut:return features
        self.metric(cut)
        return [value for feature in features if (value:=self.clip_feature(feature,cut)) is not None]

    def clip_rows(self,rows,cut):
        if not cut:return rows
        features=[dict(type='Feature',geometry=r['geometry'],properties={k:v for k,v in r.items() if k!='geometry'}) for r in rows]
        return [dict(f['properties'],geometry=f['geometry']) for f in self.clip_features(features,cut)]

    def clip_nodes(self,nodes,cut):
        if not cut:return nodes
        polygon=self.metric(cut)
        return [n for n in nodes if polygon.covers(Point(FWD(*n['coordinates'][:2])))]


def commune_index():
    folder=ROOT/'datos/entrada/comunas';path=folder/'manifest.json'
    if not path.exists():raise ValueError('Faltan límites comunales: ejecutar main adquirir-escena')
    manifest=json.loads(path.read_text(encoding='utf-8'));key=hashlib.sha256(canonical(manifest)).hexdigest()
    with _LOCK:
        if key not in _CACHE:
            _CACHE[key]=Communes(folder,manifest)
            while len(_CACHE)>2:_CACHE.popitem(last=False)
        _CACHE.move_to_end(key);return _CACHE[key]
