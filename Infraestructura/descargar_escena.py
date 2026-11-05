"""One bounded Overpass snapshot; runtime maps do not query Overpass."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.ops import transform
from core.aerial_data import FWD, INV
from core.area import load_area
from core.contracts import ROOT


def download(folder=None):
    config=json.loads((ROOT/'config/proyecto.json').read_text(encoding='utf-8'))
    scene=json.loads((ROOT/'config/escena.json').read_text(encoding='utf-8'))
    folder=Path(folder or ROOT/scene['directory'])
    folder.mkdir(parents=True,exist_ok=True)
    area=load_area(ROOT/config['aoi_geojson'])
    area=transform(INV,transform(FWD,area).buffer(config['transit_buffer_m']+150))
    w,s,e,n=area.bounds
    bbox=f'{s},{w},{n},{e}'
    query=f'''[out:json][timeout:180];(
      nwr["building"]({bbox});nwr["building:part"]({bbox});
      nwr["natural"~"^(water|wood|tree|tree_row|scrub|grassland|wetland|sand|bare_rock|coastline)$"]({bbox});
      nwr["landuse"]({bbox});nwr["landcover"]({bbox});
      nwr["waterway"]({bbox});nwr["leisure"="park"]({bbox});
      way["highway"]({bbox});
    );out meta geom;'''
    errors=[]
    for url in ['https://overpass.private.coffee/api/interpreter','https://overpass-api.de/api/interpreter']:
        try:
            request=Request(url,data=urlencode({'data':query}).encode(),headers={
                'User-Agent':'UDP-Valparaiso-Routing/1.1 (academic geographic scene; local snapshot)',
                'Accept':'application/json'})
            with urlopen(request,timeout=220) as response:
                body=response.read();status=response.status
            doc=json.loads(body)
            if doc.get('remark') or doc.get('error') or not doc.get('elements'):
                raise ValueError('Overpass returned incomplete or empty data: '+str(doc.get('remark',doc.get('error'))))
            digest=hashlib.sha256(body).hexdigest()
            name=f'osm_{digest[:16]}.json'
            (folder/name).write_bytes(body)
            report=dict(schema_version='scene-acquisition-1',bbox_wgs84=[w,s,e,n],file=name,
                        sha256=digest,bytes=len(body),http_status=status,url=url,query=query,
                        timestamp_osm_base=doc.get('osm3s',{}).get('timestamp_osm_base'),
                        fetched_at_utc=datetime.now(timezone.utc).isoformat(),
                        license='ODbL 1.0',attribution='© OpenStreetMap contributors',
                        attribution_url='https://www.openstreetmap.org/copyright',fallback_errors=errors)
            temporary=folder/'manifest.json.tmp'
            temporary.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
            temporary.replace(folder/'manifest.json')
            return dict(file=name,elements=len(doc['elements']),bytes=len(body),sha256=digest)
        except Exception as exc:
            errors.append(dict(url=url,error=str(exc)))
    raise RuntimeError('Snapshot not changed: '+json.dumps(errors))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    print(json.dumps(download(parser.parse_args().output)))
