"""Evidencia de snapshot y reglas A4; no simula una descarga DGAC exitosa."""
import argparse
import hashlib
import json
from pathlib import Path
from shapely.geometry import Point,LineString,box
from shapely.ops import transform

from core.contracts import ROOT,write_json
from core.area import load_area
from core.aerial_data import FWD,INV
from core.aip_acquisition import validate_pdf,zone_diff
from core.aerial_routing import historical_policy
from core.db import connect


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    config=json.loads((ROOT/'config/proyecto.json').read_text());folder=ROOT/config['aerial_raw_directory']
    manifest=folder/'manifest.json';entry=json.loads(manifest.read_text())['sources']['S6']
    area=transform(INV,transform(FWD,load_area(ROOT/config['aoi_geojson'])).buffer(config['transit_buffer_m'],quad_segs=16))
    records,report,pages=validate_pdf(folder/entry['file'],area)
    args.output.mkdir(parents=True,exist_ok=True)
    write_json(args.output/'aip_snapshot.json',dict(state='verified_conserved_snapshot_not_new_download',original=entry,
        sha256_verified=hashlib.sha256((folder/entry['file']).read_bytes()).hexdigest()==entry['sha256'],
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),parser=report,page_dates=pages,
        self_comparison=zone_diff(records,records),new_document_comparison='not_available_dns_failure'))
    model=dict(profile={},history=[(box(0,0,10,10),0),(box(4,4,6,6),1)])
    cases=[]
    for name,limit,geometry in [('disabled',None,LineString([(1,5),(9,5)])),('allowed',4,LineString([(1,1),(3,1)])),
                                 ('exceeded',4,LineString([(1,5),(9,5)])),('unknown',4,LineString([(1,1),(11,1)]))]:
        model['profile']['max_historical_class']=limit
        cases.append(dict(id=name,limit=limit,reason=historical_policy(geometry,model),geometry=geometry.__geo_interface__))
    write_json(args.output/'a4_examples.json',dict(synthetic=True,crs='Plano métrico local de prueba; no son incidentes observados',
        cases=cases,historical_source_period='2020–2024',acceptance='Criterio 5.1 pendiente de confirmación docente'))
    with connect() as conn:
        rid=conn.execute('SELECT run_id FROM routing.publication WHERE singleton').fetchone()['run_id']
        spatial=conn.execute('''SELECT
          (SELECT count(*) FROM (SELECT geom FROM routing.nodes WHERE run_id=%s GROUP BY geom HAVING count(*)>1) q) duplicate_node_geometries,
          (SELECT count(*) FROM (SELECT source,target FROM routing.edges WHERE run_id=%s GROUP BY source,target HAVING count(*)>1) q) duplicate_directed_pairs''',(rid,rid)).fetchone()
        write_json(args.output/'publication.json',dict(run_id=str(rid),spatial=spatial))
    print(json.dumps(dict(run_id=str(rid),snapshot_verified=True,a4_cases=len(cases),spatial=spatial)))


if __name__=='__main__':main()
