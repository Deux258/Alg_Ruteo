"""Evidencia local de fuentes, publicación y misiones reales reproducibles."""
import argparse
import json
import time
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import transform

from core.contracts import ROOT, write_json
from core.aerial_data import FWD, INV, iso
from core.db import connect
from core.patrol_data import graph, Obstacles
from core.patrol_routing import plan, weather_problem
from core.patrol_evaluation import compare
from core.surface import Surface


def select_request(rid):
    p,c,states,edges,rows=graph(rid);obstacles=Obstacles(rows)
    area=transform(FWD,shape(c['study_geometry']))
    aip=[transform(FWD,shape(r['geometry'])) for r in c['records']['A3']]
    base=next(b for b in c['records']['M1'] if b.get('provider_id')=='104')
    base_point=transform(FWD,shape(base['geometry']))
    anchors={n['anchor_id']:n for n in states.values()}
    surface=Surface(ROOT/c['dsm_file'],transform(FWD,shape(c['flight_geometry'])).bounds)
    launch=None
    try:
        for n in sorted(anchors.values(),key=lambda n:Point(n['coordinates'][:2]).distance(base_point)):
            point=Point(n['coordinates'][:2])
            if not area.covers(point) or obstacles.check(point)[0] or any(g.intersects(point) for g in aip):continue
            values,known=surface.pixels(point.buffer(p['corridor_radius_m']))
            if known and max(values)<=n['surface_m']+10:launch=point;break
    finally:surface.close()
    if launch is None:raise ValueError('No hay punto de lanzamiento de demostración compatible con las capas')
    targets=[]
    for n in sorted(anchors.values(),key=lambda n:Point(n['coordinates'][:2]).distance(launch)):
        point=Point(n['coordinates'][:2])
        if n['kind']!='observation' or point.distance(launch)<100 or obstacles.check(point)[0] or any(g.intersects(point) for g in aip):continue
        if any(point.distance(other)<75 for other in targets):continue
        targets.append(point)
        if len(targets)==3:break
    hours=[w for w in c['weather'] if iso(w['valid_at'])>=iso(c['weather_fetched_at']) and not weather_problem(w,p)]
    if not hours:raise ValueError('Sin hora admisible para la demostración; conservar lote sin filtrar por clima')
    return dict(origin=list(INV(launch.x,launch.y)),objectives=[list(INV(point.x,point.y)) for point in targets],time=hours[0]['valid_at']),dict(
        reference_installation=base['geometry']['coordinates'],launch_offset_m=launch.distance(base_point),
        selection='Demostración: posición de malla próxima a la instalación, sin intersecciones y con superficie local compatible; hora admisible. No es el lote de evaluación.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'evidencia/vigilancia_2026-10-22')
    parser.add_argument('--select-only',action='store_true');parser.add_argument('--request',type=Path);parser.add_argument('--count',type=int,choices=[1,2,3],default=1);parser.add_argument('--compare',action='store_true')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    with connect() as conn:
        rid=str(conn.execute('SELECT run_id FROM routing.patrol_publication WHERE singleton').fetchone()['run_id'])
        request,selection=select_request(rid)
        if args.request:request=json.loads(args.request.read_text())
        request=dict(request,objectives=request['objectives'][:args.count])
        write_json(args.output/f'solicitud_{args.count}.json',request);write_json(args.output/'seleccion_demostracion.json',selection)
        if args.select_only:print(json.dumps(dict(run_id=rid,request=request,selection=selection)));return
        start=time.monotonic();result=compare(conn,rid,request) if args.compare else plan(conn,rid,request)
        write_json(args.output/f'{"comparacion" if args.compare else "mision"}_{args.count}.json',result)
        report=dict(run_id=rid,duration_s=time.monotonic()-start)
        if args.compare:report['metrics']=result['metrics']
        else:report.update(status=result['status'],alternatives=len(result['alternatives']),reasons=result.get('failure_causes'),evaluations=[{k:v for k,v in r['evaluation'].items() if k not in ['profile']} for r in result['alternatives']])
        print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
