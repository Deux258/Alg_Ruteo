"""Figuras SVG desde evidencia geográfica y esquema inspeccionado en PostgreSQL."""
import argparse
import json
import math
from html import escape
from pathlib import Path
from collections import defaultdict
from shapely.geometry import shape
from shapely.ops import transform
from core.aerial_data import FWD


def map_svg(folder):
    view=json.loads((folder/'mapa.json').read_text());comparison=json.loads(next(folder.glob('comparison_*.json')).read_text())
    flight=transform(FWD,shape(view['flight_area']));west,south,east,north=flight.bounds
    scale=min(1060/(east-west),650/(north-south))
    def xy(point):return 70+(point[0]-west)*scale,100+(north-point[1])*scale
    def path(g):
        geom=transform(FWD,shape(g));parts=[]
        for polygon in getattr(geom,'geoms',[geom]):
            for ring in [polygon.exterior,*polygon.interiors]:
                parts.append('M'+' L'.join(f'{x:.2f},{y:.2f}' for x,y in map(xy,ring.coords))+' Z')
        return ' '.join(parts)
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="880" viewBox="0 0 1200 880"><rect width="1200" height="880" fill="#f7faf8"/><style>text{font-family:Arial,sans-serif;fill:#233e43}</style>',
        '<text x="30" y="36" font-size="25">Valparaíso · vigilancia, tránsito y misiones completas</text>',
        '<text x="30" y="65" font-size="16">Verde: vigilancia original · ocre discontinuo: tránsito +1100 m · cinco bases reales candidatas</text>',
        f'<path d="{path(view["flight_area"])}" fill="#eee9dd" stroke="#927a4c" stroke-dasharray="8 5"/>',
        f'<path d="{path(view["area"])}" fill="#e4eee6" stroke="#3e8d64" stroke-width="2"/>']
    for f in view['features']:
        if f['geometry']['type']=='LineString':
            coords=transform(FWD,shape(f['geometry'])).coords
            svg.append('<polyline fill="none" stroke="#b5c3c7" stroke-width=".7" points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in map(xy,coords))+'"/>')
    colors={'reference':['#6d7985','#963d32'],'proposed':['#1766b1','#a46f12']}
    for f in comparison['features']:
        p=f['properties'];points=' '.join(f'{x:.2f},{y:.2f}' for x,y in map(xy,transform(FWD,shape(f['geometry'])).coords));dash=' stroke-dasharray="7 4"' if p['role']=='return' else ''
        svg.append(f'<polyline points="{points}" fill="none" stroke="{colors[p["method"]][p["rank"]-1]}" stroke-width="3"{dash}/>')
    for b in view['bases']:
        x,y=xy(transform(FWD,shape(b['geometry'])).coords[0]);label=escape(b['name'])
        svg.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#cf6c24"/><text x="{x+8}" y="{y-8}" font-size="12">{label}</text>')
    m=comparison['metrics'];svg.append(f'<text x="30" y="800" font-size="16">Dijkstra: gris / rojo · Propuesto: azul / ocre · ida continua / regreso discontinuo</text>')
    svg.append(f'<text x="30" y="826" font-size="16">100 escenarios · semilla 20261018 · ΔR = {m["delta_percentage_points"]:.1f} pp · sin despeje vertical verificado</text>')
    svg.append(f'<text x="30" y="852" font-size="13">Run {comparison["run_id"]} · condiciones estáticas · no representa vuelos observados</text></svg>')
    (folder/'mapa_comparativo.svg').write_text('\n'.join(svg),encoding='utf-8')


def diagram(folder,output):
    report=json.loads((folder/'diagnostico.json').read_text());tables=defaultdict(list)
    for row in report['schema']:tables[row['table_name']].append(row)
    # Los campos completos se conservan en diagnostico.json y el DDL.
    width=1500;cols=4;box_w=350;row_height=260;height=100+math.ceil(len(tables)/cols)*row_height
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="#f7faf8"/><style>text{{font-family:Arial,sans-serif;fill:#233e43}}</style>',f'<text x="25" y="40" font-size="28">Esquema inspeccionado en PostgreSQL · {len(tables)} tablas</text>','<text x="25" y="68" font-size="17">PK/FK y campos completos: DDL inicial + migraciones 002–004. Catálogo visual de capacidad por tabla.</text>']
    for i,(table,rows) in enumerate(sorted(tables.items())):
        x=25+(i%cols)*370;y=100+(i//cols)*row_height
        svg.append(f'<rect x="{x}" y="{y}" width="{box_w}" height="240" fill="white" stroke="#6b9586"/><text x="{x+12}" y="{y+26}" font-size="20">{escape(table)}</text>')
        for j,row in enumerate(rows[:9]):
            label=row['column_name']+' · '+(row['udt_name'] if row['data_type']=='USER-DEFINED' else row['data_type'])
            svg.append(f'<text x="{x+12}" y="{y+50+j*19}" font-size="14">{escape(label)}</text>')
        if len(rows)>9:svg.append(f'<text x="{x+12}" y="{y+225}" font-size="14">… {len(rows)} columnas; ver diagnóstico y SQL</text>')
    svg.append('</svg>');output.write_text('\n'.join(svg),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path);parser.add_argument('--diagram',type=Path,default=Path('BD/diagrama_fase2.svg'));args=parser.parse_args();map_svg(args.folder);diagram(args.folder,args.diagram)
