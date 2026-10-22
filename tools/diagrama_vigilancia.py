"""Diagrama editable SVG de las relaciones añadidas, validado con pg_catalog."""
from html import escape
from core.contracts import ROOT
from core.db import connect


def main():
    tables={
        'runs':(30,100,['PK run_id','status / scope / mode']),
        'patrol_runs':(370,100,['PK id','FK base_run_id → runs','input_hash UNIQUE','profile / context / status']),
        'patrol_publication':(710,100,['PK singleton=true','FK run_id → patrol_runs']),
        'flight_states':(30,350,['PK run_id, id','anchor_id / resolution_m','surface_m / surface_offset_m','geom PointZ 32719']),
        'flight_edges':(370,350,['PK run_id, id','FK run_id, source → states','FK run_id, target → states','flight_km / horizontal_km','clearance / surface_known','profile_samples / geom Z']),
        'flight_obstacles':(710,350,['PK run_id, provider_id','FK run_id → patrol_runs','kind / height_m nullable','original_tags / geom / exclusion']),
        'patrol_datasets':(30,650,['PK run_id, key','FK run_id → patrol_runs','document / records hash']),
        'patrol_evaluations':(370,650,['PK run_id, sha256','FK run_id → patrol_runs','result / request / scenarios'])}
    with connect() as conn:
        found={r['table_name'] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='routing'")}
    if not set(tables)<=found:raise ValueError('El diagrama nombra tablas inexistentes')
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="890" viewBox="0 0 1080 890">',
         '<rect width="1080" height="890" fill="#f6f8f3"/><style>text{font-family:DejaVu Sans,sans-serif;fill:#183b30}.link{fill:none;stroke:#719183;stroke-width:2}</style>',
         '<text x="30" y="42" font-size="25">Vigilancia · publicación y grafo tridimensional</text>',
         '<text x="30" y="70" font-size="14">SQL inicial y migraciones 002–005 · relaciones nuevas sin modificar las instantáneas previas</text>']
    for line in ['M330 145H370','M670 145H710','M520 290V325H180V350','M520 290V350','M520 290V325H860V350','M180 570V650','M520 590V650','M330 430H370']:
        svg.append(f'<path d="{line}" class="link"/>')
    for name,(x,y,fields) in tables.items():
        height=70+len(fields)*25
        svg.append(f'<rect x="{x}" y="{y}" width="300" height="{height}" rx="4" fill="white" stroke="#719183"/>')
        svg.append(f'<text x="{x+15}" y="{y+32}" font-size="19" font-weight="bold">{name}</text>')
        for i,field in enumerate(fields):svg.append(f'<text x="{x+15}" y="{y+65+i*25}" font-size="13">{escape(field)}</text>')
    svg.append('<text x="710" y="730" font-size="14">X/Y: UTM 19S, metros</text><text x="710" y="755" font-size="14">Z: metros EGM2008</text><text x="710" y="780" font-size="14">Datos ready: inmutables</text></svg>')
    (ROOT/'BD/diagrama_vigilancia.svg').write_text('\n'.join(svg))


if __name__=='__main__':main()
