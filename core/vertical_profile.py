"""Canonical levelled flight geometry and a conservative horizontal target overlay.

Flight levels are metres EGM2008 above the existing DSM/obstacle envelope.
The target overlay uses the original DSM, independently of flight clearance.
"""
from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache

import numpy as np
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.ops import transform

from core.aerial_data import FWD, INV
from core.contracts import ROOT, canonical

VERSION = 'banded-ramp-1'
BAND_M = 10.0
OFFSET_M = 30.0


def profile_metadata():
    return dict(version=VERSION, band_m=BAND_M, minimum_plateau_fraction=1/3,
                vertical_datum='EGM2008', clearance_basis='DSM and obstacle envelope',
                clearance_semantics='minimum', observation_radius_basis='horizontal')


def level(height, clearance):
    if height is None or not math.isfinite(height):
        return None
    return float(BAND_M * math.ceil((height + clearance) / BAND_M))


def ramp_profile(a, b, samples, clearance):
    """A shared-endpoint ramp/plateau/ramp majorant of sampled safety floors.

    Samples include terrain and obstacle breakpoints. Retaining their XY positions
    keeps observation and detection sampling as dense as the original graph.
    """
    distance = math.dist(a[:2], b[:2])
    if distance <= 0 or not samples:
        return None
    floors = []
    for x, y, height in samples:
        floor = level(height, clearance)
        if floor is None:
            return None
        t = min(1., max(0., math.dist(a[:2], (x, y)) / distance))
        floors.append((t, floor))
    start, end = float(a[2]), float(b[2])
    if any((t <= 1e-12 and z > start+1e-7) or (t >= 1-1e-12 and z > end+1e-7) for t,z in floors):
        return None
    peak = max(start, end, *(z for _, z in floors))
    rise = 0. if start == peak else min([1/3, *[t*(peak-start)/(z-start) for t,z in floors if z > start]])
    fall = 1. if end == peak else max([2/3, *[1-(1-t)*(peak-end)/(z-end) for t,z in floors if z > end]])
    def altitude(t):
        if rise > 0 and t < rise:
            return start + (peak-start)*t/rise
        if fall < 1 and t > fall:
            return peak + (end-peak)*(t-fall)/(1-fall)
        return peak
    if any(altitude(t) < z-1e-7 for t,z in floors):
        raise RuntimeError('Perfil vertical no satisface su envolvente de seguridad')
    values = sorted(set([0., 1., rise, fall, *(t for t,_ in floors)]))
    points = [(float(a[0]+(b[0]-a[0])*t), float(a[1]+(b[1]-a[1])*t), float(altitude(t))) for t in values]
    points[0] = tuple(map(float, a)); points[-1] = tuple(map(float, b))
    return tuple(points)


def _raster_max(raw, target):
    """Every touched original DSM pixel, not just the polygon boundary."""
    from affine import Affine
    from rasterio.features import geometry_mask
    geographic = transform(INV, target)
    coordinates = [raw.affine * (x,y) for x,y in geographic.exterior.coords]
    cols, rows = zip(*coordinates)
    # Keep the cells on both sides of an exact pixel boundary; the mask selects
    # actual touches. Padding is not itself an out-of-coverage diagnostic.
    outside=min(cols)<0 or min(rows)<0 or max(cols)>raw.array.shape[1] or max(rows)>raw.array.shape[0]
    c0,r0,c1,r1=math.floor(min(cols))-1,math.floor(min(rows))-1,math.ceil(max(cols))+1,math.ceil(max(rows))+1
    height, width = raw.array.shape
    unknown = outside
    c0,r0,c1,r1 = max(0,c0),max(0,r0),min(width,c1),min(height,r1)
    if c1 <= c0 or r1 <= r0:
        return None, True, 0
    footprint = geometry_mask([mapping(geographic.buffer(1e-12))], out_shape=(r1-r0,c1-c0),
        transform=(~raw.affine)*Affine.translation(c0,r0), all_touched=True, invert=True)
    data = raw.array[r0:r1,c0:c1]
    values = np.asarray(np.ma.getdata(data), dtype=float)*raw.scale+raw.offset
    valid = ~np.ma.getmaskarray(data) & np.isfinite(values)
    unknown = unknown or bool(np.any(footprint & ~valid))
    selected = values[footprint & valid]
    return (float(selected.max()) if selected.size else None), unknown or not selected.size, int(footprint.sum())


@lru_cache(maxsize=2)
def _visual_mesh(raw, flight_geometry, step):
    return raw.mesh(transform(FWD,shape(json.loads(flight_geometry))),step=step)


def target_display(model, target_geojson, raw):
    """Horizontal visual level above all touched raw cells and display triangles."""
    geometry=target_geojson.get('geometry') if target_geojson.get('type')=='Feature' else target_geojson
    original = shape(geometry)
    original = transform(lambda x,y,z=None:(x,y),original)
    if original.geom_type != 'Polygon' or original.is_empty or not original.is_valid:
        raise ValueError('El objetivo visual requiere un polígono válido')
    target = transform(FWD, original)
    digest = hashlib.sha256(canonical(mapping(original))).hexdigest()
    source = getattr(raw, 'source_sha256', 'fixture')
    maximum, unknown, count = None, False, 0
    if all(hasattr(raw, name) for name in ('array','affine','scale','offset')):
        maximum, unknown, count = _raster_max(raw, target)
    else:
        # Fixtures and alternative surfaces must sample interior as well as edges.
        w,s,e,n=target.bounds
        for x in np.arange(w,e+15,15):
            for y in np.arange(s,n+15,15):
                if target.covers(Point(x,y)):
                    z=raw.at(float(x),float(y)); count+=1
                    if z is None or not math.isfinite(z): unknown=True
                    else: maximum=z if maximum is None else max(maximum,z)
        for ring in [target.exterior,*target.interiors]:
            for a,b in zip(ring.coords, list(ring.coords)[1:]):
                for f in np.linspace(0,1,max(2,math.ceil(math.dist(a,b)/15)+1)):
                    z=raw.at(a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f); count+=1
                    if z is None or not math.isfinite(z): unknown=True
                    else: maximum=z if maximum is None else max(maximum,z)
    if hasattr(raw, 'mesh'):
        config=json.loads((ROOT/'config/escena.json').read_text(encoding='utf-8'))
        step=config['mesh_step_m']
        try:mesh=_visual_mesh(raw,canonical(model['flight_geometry']),step)
        except TypeError:mesh=raw.mesh(transform(FWD,shape(model['flight_geometry'])),step=step)
        ox,oy=mesh['origin_utm']; width=mesh['width']
        def vertex(i,j): return (ox+mesh['x'][i],oy+mesh['y'][j],mesh['elevations'][j*width+i])
        w,s,e,n=target.bounds
        i0=max(0,int(np.searchsorted(mesh['x'],w-ox,side='left'))-1)
        i1=min(width-2,int(np.searchsorted(mesh['x'],e-ox,side='right'))-1)
        j0=max(0,int(np.searchsorted(mesh['y'],s-oy,side='left'))-1)
        j1=min(mesh['height']-2,int(np.searchsorted(mesh['y'],n-oy,side='right'))-1)
        for j in range(j0,j1+1):
            for i in range(i0,i1+1):
                a,b,c,d=vertex(i,j),vertex(i+1,j),vertex(i,j+1),vertex(i+1,j+1)
                for triangle in ((a,b,c),(b,d,c)):
                    if not Polygon([p[:2] for p in triangle]).intersects(target): continue
                    for _,_,z in triangle:
                        if z is None or not math.isfinite(z): unknown=True
                        else: maximum=z if maximum is None else max(maximum,z)
    known = maximum is not None and not unknown
    return dict(status='known' if known else 'unknown_elevation',
        level_m_egm2008=float(maximum+OFFSET_M) if known else None,
        maximum_surface_m_egm2008=float(maximum) if maximum is not None else None,
        offset_m=OFFSET_M,polygon_sha256=digest,terrain_sha256=source,
        sampling='all touched DSM pixels and intersecting display triangles',sample_count=count,
        visual_only=True,vertical_datum='EGM2008')


def target_display_summary(model, target_geojson):
    from core.patrol import terrain
    raw=terrain()
    config=(ROOT/'config/escena.json').read_bytes()
    return dict(_cached_display(canonical(target_geojson),canonical(model['flight_geometry']),raw.source_sha256,config))


@lru_cache(maxsize=128)
def _cached_display(target,flight_geometry,source,config):
    from core.patrol import terrain
    raw=terrain()
    if raw.source_sha256!=source:raise ValueError('La fuente DSM cambió durante la consulta del objetivo')
    return target_display(dict(flight_geometry=json.loads(flight_geometry)),json.loads(target),raw)
