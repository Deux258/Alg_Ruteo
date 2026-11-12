"""Complete AOI partition and persistent, terrain-verified simulated coverage."""
import hashlib
import json
import math
from pathlib import Path

from shapely.geometry import Point, shape, mapping, box
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from core.aerial_data import FWD, INV
from core.contracts import ROOT, canonical, write_json

DIRECTORY = ROOT / 'datos/runs/monitoreo'


def metric_area(geometry):
    # Densify source segments before nonlinear reprojection. Otherwise even a
    # roundoff-width geographic sliver acquires metres of artificial area.
    return transform(FWD,geometry.segmentize(.0001)).area if not geometry.is_empty else 0.


def polygons(geometry):
    if geometry.geom_type == 'Polygon':
        yield geometry
    elif hasattr(geometry,'geoms'):
        for item in geometry.geoms: yield from polygons(item)


def catalogue(model, step=400):
    study = shape(model['study_geometry'])
    metric = transform(FWD,study)
    digest = hashlib.sha256(canonical(dict(schema='monitoring-catalogue-1',step=step,
                                         source_context={k:v for k,v in model.items() if not k.startswith('_')}))).hexdigest()
    bases = [(s,transform(FWD,shape(s['geometry']))) for s in model['records']['M1'] if s.get('candidate',True)]
    sectors = []; pieces = []
    west,south,east,north = metric.bounds
    for ix in range(math.floor(west/step)-1,math.ceil(east/step)+1):
        for iy in range(math.floor(south/step)-1,math.ceil(north/step)+1):
            # Shared grid corners produce exactly shared geographic edges.
            # Clip in the source CRS: clipping in UTM then transforming newly
            # created boundary vertices leaves thin gaps along source edges.
            geographic = transform(INV,box(ix*step,iy*step,(ix+1)*step,(iy+1)*step)).intersection(study)
            for part,geo in enumerate(polygons(geographic)):
                polygon=transform(FWD,geo)
                if polygon.area <= 0: continue
                area = polygon.area
                base = min(bases,key=lambda b:polygon.distance(b[1]))[0] if bases else None
                ident = f'{digest[:12]}:{ix}:{iy}:{part}:0'
                sectors.append(dict(id=ident,name=f'Sector {len(sectors)+1:03d}',target_polygon=mapping(geo),area_m2=area,
                                    origin=base['geometry']['coordinates'] if base else None,base_id=base['provider_id'] if base else None,
                                    status='requires_planning' if area>=1 and base else 'pending_support',
                                    reason=None if area>=1 and base else 'Fragmento menor de 1 m² o sin base; no se elimina de pendientes'))
                pieces.append(geo)
    union = unary_union(pieces)
    missing = study.difference(union)
    gap_area=metric_area(missing)
    return dict(schema_version='monitoring-catalogue-1',sha256=digest,crs='EPSG:32719',sector_size_m=step,
                sectors=sectors,area_m2=metric.area,partition_area_m2=metric.area-gap_area,
                partition_percent=min(100,100*(metric.area-gap_area)/metric.area),partition_gap_m2=gap_area,
                partition_complete=gap_area<.01,unassigned_geometry=mapping(missing),
                coverage_note='Sectorización completa no implica vuelo factible ni cobertura observada. Se requiere calcular y simular cada sector.',
                progress=progress(digest,metric))


def resolve(model, request):
    # Lineage is server-owned, never trust a client-supplied filesystem key.
    request={k:v for k,v in request.items() if k!='monitoring_catalogue_sha256'}
    if not request.get('patrol_id'): return request
    catalog = catalogue(model)
    sector = next((r for r in catalog['sectors'] if r['id']==request['patrol_id']),None)
    if sector is None: raise ValueError('Recorrido desconocido u obsoleto: recargar catálogo')
    if sector['status']=='pending_support': raise ValueError(sector['reason'])
    return dict(request,target_polygon=sector['target_polygon'],origin=sector['origin'],
                monitoring_catalogue_sha256=catalog['sha256'])


def progress(digest, study):
    path = DIRECTORY / digest / 'coverage.json'
    observations = json.loads(path.read_text()) if path.exists() else {}
    covered = unary_union([shape(g) for g in observations.values()]).intersection(study)
    pending = study.difference(covered)
    return dict(simulated=True,covered_area_m2=covered.area,pending_area_m2=pending.area,
                percent=min(100,100*covered.area/study.area),complete=pending.area<.01,
                sector_covered_area_m2={ident:shape(geometry).area for ident,geometry in observations.items()},
                sectors_with_observations=len(observations),pending_geometry=mapping(transform(INV,pending)))


def record(result, simulation, terrain):
    """Audit every simulation; only visible, known-elevation cells add coverage."""
    from core.patrol import coverage_cells
    digest = result['request'].get('monitoring_catalogue_sha256')
    sector = result['request'].get('patrol_id')
    payload = dict(simulation)
    simulation_id = hashlib.sha256(canonical(payload)).hexdigest()
    DIRECTORY.mkdir(parents=True,exist_ok=True)
    write_json(DIRECTORY/f'{simulation_id}.json',payload)
    if not digest or not sector: return None
    target = transform(FWD,shape(result['target_polygon']))
    frames = [f for f in simulation['timeline'] if f['phase'] in ('patrol','return','detection')]
    tree = STRtree([Point(f['position_utm'][:2]) for f in frames])
    covered = []
    radius = result['effective_profile']['view_radius_m']
    # Match the existing 30 m area-weighted coverage convention.
    for cell in coverage_cells(target,result['effective_profile']['coverage_cell_m']):
        c = cell.representative_point(); z = terrain.at(c.x,c.y)
        if z is None: continue
        candidates = tree.query(c,predicate='dwithin',distance=radius)
        if any(terrain.visible(frames[int(k)]['position_utm'],[c.x,c.y,z]) for k in candidates): covered.append(cell)
    folder = DIRECTORY/digest; folder.mkdir(exist_ok=True)
    path = folder/'coverage.json'
    observations = json.loads(path.read_text()) if path.exists() else {}
    previous = shape(observations[sector]) if sector in observations else None
    union = unary_union(covered)
    if previous is not None: union = union.union(previous)
    observations[sector] = mapping(union)
    temporary = folder/'coverage.tmp'
    write_json(temporary,observations); temporary.replace(path)
    return dict(simulation_id=simulation_id,sector_id=sector,sector_covered_area_m2=union.area,
                sector_area_m2=target.area,sector_percent=min(100,100*union.area/target.area),
                sector_complete=target.difference(union).area<.01,
                note='Cobertura de esta simulación, acumulada por sector; no vuelo físico.')


def main():
    import argparse
    from core.patrol import snapshot_context, calculate
    parser=argparse.ArgumentParser(description='Planificar todos los sectores; nunca declarar cobertura por solo particionar')
    parser.add_argument('--context',required=True)
    parser.add_argument('--output',default='datos/runs/monitoreo/catalogo')
    parser.add_argument('--plan-all',action='store_true',help='Calcular cada sector con las cuatro técnicas; puede demorar')
    args=parser.parse_args(); model=snapshot_context(args.context); catalog=catalogue(model)
    folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    write_json(folder/'catalogue.json',catalog)
    if args.plan_all:
        for sector in catalog['sectors']:
            try:
                request=resolve(model,dict(patrol_id=sector['id'],scenarios=100))
                result=calculate(model,request)
                write_json(folder/f"{sector['name'].replace(' ','_')}.json",result)
                sector['planning']={m:dict(status=r['status'],coverage=r.get('coverage')) for m,r in result['routes'].items()}
            except ValueError as exc: sector['planning_error']=str(exc)
        write_json(folder/'catalogue.json',catalog)
    print(json.dumps(dict(sectors=len(catalog['sectors']),partition_percent=catalog['partition_percent'],output=str(folder))))


if __name__ == '__main__': main()
