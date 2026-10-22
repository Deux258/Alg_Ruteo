"""Adquisición atómica de obstáculos OSM y meteorología IFS HRES."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import Point, LineString, Polygon, mapping, shape
from shapely import make_valid
from shapely.ops import transform

from core.contracts import ROOT, canonical, sha256, write_json
from core.aerial_data import FWD, INV


def profile():
    return validate_profile(json.loads((ROOT/'config/vigilancia.json').read_text()))


def validate_profile(p):
    import math
    for key in ['grid_m','refined_grid_m','refine_relief_m','max_link_m','corridor_radius_m','sample_step_m','minimum_clearance_m','air_speed_ms','climb_ms','descent_ms','flight_minutes','observation_s','wind_limit_ms','precipitation_limit_mm','visibility_min_m','climb_factor','sector_radius_m','maximum_gsd_m','observation_cell_m']:
        value=p.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or value<=0:raise ValueError('Perfil inválido: '+key)
    if p['grid_m']!=2*p['refined_grid_m'] or type(p['grid_m']) is not int or type(p['refined_grid_m']) is not int:raise ValueError('Malla requiere dos resoluciones enteras con relación 2:1')
    for key in ['max_objectives','candidates_per_leg','beam_width']:
        if type(p.get(key)) is not int or p[key]<1:raise ValueError('Perfil inválido: '+key)
    if p['max_objectives']>3 or not 0<=p['reserve_fraction']<1 or not 0<p['minimum_coverage']<=1:raise ValueError('Presupuesto o cobertura inválidos')
    for key,maximum in [('levels_m',None),('camera_fov_deg',180),('camera_pixels',None)]:
        values=p.get(key)
        if not isinstance(values,list) or not values or any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 or (maximum and v>=maximum) for v in values):raise ValueError('Perfil inválido: '+key)
    if len(p['camera_fov_deg'])!=2 or len(p['camera_pixels'])!=2 or p['levels_m']!=sorted(set(p['levels_m'])):raise ValueError('Cámara o niveles inválidos')
    return p


def obstacle_rows(document, area, config):
    if not isinstance(document.get('elements'), list) or document.get('remark'):
        raise ValueError('OSM incompleto o respuesta inválida')
    rows = []
    for element in document['elements']:
        tags = element.get('tags', {})
        geometry_quality='provider_geometry'
        kind = 'building' if tags.get('building') not in (None, 'no') else 'power_line' if tags.get('power') in ('line', 'minor_line', 'cable') else 'antenna' if tags.get('man_made') in ('antenna', 'communications_tower', 'mast') else 'tower' if tags.get('power') in ('tower', 'pole') or tags.get('man_made') == 'tower' else None
        if not kind:
            continue
        if element['type'] == 'node':
            geom = Point(element['lon'], element['lat'])
        elif element['type'] == 'way':
            coords = [(p['lon'], p['lat']) for p in element.get('geometry', [])]
            if len(coords) < 2: raise ValueError('Obstáculo sin geometría completa')
            geom = Polygon(coords) if kind == 'building' and coords[0] == coords[-1] and len(coords) >= 4 else LineString(coords)
        elif element['type'] == 'relation':
            # No omitir multipolígonos: ensamblar anillos exteriores e interiores.
            from shapely.ops import polygonize, unary_union
            outer, inner = [], []
            for member in element.get('members', []):
                coords = [(p['lon'], p['lat']) for p in member.get('geometry', [])]
                if len(coords) >= 2: (inner if member.get('role') == 'inner' else outer).append(LineString(coords))
            if kind == 'power_line' and outer:
                geom = unary_union(outer)
            else:
                polygons = list(polygonize(unary_union(outer)))
                if not polygons:
                    # Algunas relaciones publicadas solo tienen anillos inner. Conservar
                    # una envolvente de sus miembros, identificada como exclusión derivada.
                    if not outer and not inner:raise ValueError('Relación OSM sin geometría: '+str(element['id']))
                    geom=unary_union(outer+inner).convex_hull
                    geometry_quality='invalid_relation_conservative_hull'
                else:
                    geom = unary_union(polygons).difference(unary_union(list(polygonize(unary_union(inner)))))
        else: continue
        geom = transform(FWD, make_valid(geom))
        exclusion = geom.buffer(config['obstacle_buffers_m'][kind])
        if not exclusion.intersects(area): continue
        value = tags.get('height'); height = None
        if value is not None:
            try:
                text = str(value).strip()
                height = float(text[:-2].strip())*0.3048 if text.endswith('ft') else float(text.removesuffix(' m'))
                import math
                if not math.isfinite(height) or height <= 0: height = None
            except ValueError: pass
        rows.append(dict(provider_id=f"{element['type']}/{element['id']}", kind=kind, height_m=height,
                         quality='height_declared' if height is not None else 'height_unknown', original_tags=tags,
                         geometry_quality=geometry_quality,
                         geometry=mapping(geom), exclusion=mapping(exclusion)))
    ids = [r['provider_id'] for r in rows]
    if len(ids) != len(set(ids)): raise ValueError('OSM contiene identificadores duplicados')
    return sorted(rows, key=lambda r:r['provider_id'])


def weather_rows(document):
    fields = dict(temperature_c='temperature_2m', relative_humidity_pct='relative_humidity_2m',
                  wind_speed_ms='wind_speed_10m', wind_direction_deg='wind_direction_10m', wind_gust_ms='wind_gusts_10m',
                  wind_100_ms='wind_speed_100m', direction_100_deg='wind_direction_100m',
                  precipitation_mm='precipitation', visibility_m='visibility')
    hourly, units = document['hourly'], document['hourly_units']
    if document['utc_offset_seconds'] != 0: raise ValueError('Pronóstico requiere UTC')
    for key in ('wind_speed_10m','wind_speed_100m','wind_gusts_10m'):
        if units.get(key) != 'm/s': raise ValueError('Viento requiere m/s')
    for key, unit in [('temperature_2m','°C'),('precipitation','mm'),('visibility','m'),('wind_direction_10m','°'),('wind_direction_100m','°')]:
        if units.get(key) != unit: raise ValueError('Unidades meteorológicas incompatibles: '+key)
    times = hourly['time']
    if not times or len(times) != len(set(times)): raise ValueError('Horas meteorológicas vacías o duplicadas')
    if any(len(hourly.get(key, [])) != len(times) for key in fields.values()): raise ValueError('Serie meteorológica incompleta')
    return [dict(valid_at=t+':00+00:00', cell=[document['longitude'],document['latitude']],
                 **{key:hourly[source][i] for key,source in fields.items()}) for i,t in enumerate(times)]


def download(area):
    p = profile(); folder = ROOT/p['raw_directory']; folder.mkdir(parents=True, exist_ok=True)
    bbox = transform(INV, area.buffer(100)).bounds
    west,south,east,north = bbox
    query = f'[out:json][timeout:180];(nwr["building"]({south},{west},{north},{east});nwr["power"~"^(line|minor_line|cable|tower|pole)$"]({south},{west},{north},{east});nwr["man_made"~"^(tower|mast|antenna|communications_tower)$"]({south},{west},{north},{east}););out meta geom;'
    center = transform(INV, area.centroid)
    hourly = 'temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,wind_gusts_10m,wind_speed_100m,wind_direction_100m,precipitation,visibility'
    url = p['weather_url']+'?'+urlencode(dict(latitude=center.y,longitude=center.x,models=p['weather_model'],hourly=hourly,timezone='UTC',wind_speed_unit='ms',forecast_days=7))
    report = dict(version='patrol-sources-1', vertical_datum='EGM2008', bbox_wgs84=list(bbox), sources={}, errors={}, fetched_at_utc=datetime.now(timezone.utc).isoformat())
    for key, target, body in [('S4H',url,None),('S8',p['overpass_url'],urlencode({'data':query}).encode())]:
        try:
            from time import sleep
            for attempt in range(3):
                try:
                    with urlopen(Request(target,data=body,headers={'User-Agent':'Valparaiso-Vigilancia/1.0'}),timeout=220) as response:
                        raw=response.read(); status=response.status
                    break
                except Exception:
                    if attempt == 2: raise
                    sleep(1+attempt)
            digest = hashlib.sha256(raw).hexdigest(); file=key+'_'+digest[:16]+'.json'
            (folder/file).write_bytes(raw)
            doc = json.loads(raw)
            rows = weather_rows(doc) if key == 'S4H' else obstacle_rows(doc,area,p)
            report['sources'][key] = dict(file=file,sha256=digest,url=target,http_status=status,record_count=len(rows),
                query=query if key == 'S8' else None,model=p['weather_model'] if key == 'S4H' else None,
                license='ODbL 1.0; © OpenStreetMap contributors' if key == 'S8' else 'Proveedor Open-Meteo / ECMWF; conservar atribución',
                fetched_at_utc=datetime.now(timezone.utc).isoformat())
        except Exception as exc: report['errors'][key]=str(exc)
    target=folder/('adquisicion_incompleta.json' if report['errors'] else 'manifest.json')
    tmp=target.with_suffix('.tmp');write_json(tmp,report);tmp.replace(target)
    if report['errors']: raise RuntimeError('Adquisición incompleta: '+json.dumps(report['errors']))
    return report


def load_raw(area):
    p=profile(); folder=ROOT/p['raw_directory']; manifest=json.loads((folder/'manifest.json').read_text())
    if manifest.get('errors') or set(manifest['sources']) != {'S4H','S8'} or manifest.get('vertical_datum') != 'EGM2008':
        raise ValueError('Manifiesto de vigilancia incompleto o datum incompatible')
    from shapely.geometry import box
    if not box(*manifest['bbox_wgs84']).covers(transform(INV,area)):
        raise ValueError('Originales no cubren tránsito')
    raw={}
    for key, entry in manifest['sources'].items():
        file=(folder/entry['file']).resolve()
        if not file.is_relative_to(folder.resolve()) or sha256(file) != entry['sha256']: raise ValueError('Original alterado '+key)
        raw[key]=json.loads(file.read_text())
    return manifest, obstacle_rows(raw['S8'],area,p), weather_rows(raw['S4H'])
