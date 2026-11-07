"""Acquire BCN commune boundaries; preserve the source ZIP and publish WGS84 CUT geometry."""
import argparse
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen

from pyproj import CRS,Transformer
from shapely import make_valid
from shapely.geometry import mapping,shape
from shapely.ops import transform
from core.area import load_area
from core.aerial_data import FWD,INV,polygonal
from core.contracts import ROOT,canonical,sha256

CATALOGUE='https://www.bcn.cl/siit/mapas_vectoriales/index_html'
SOURCE='https://obtienearchivo.bcn.cl/obtienearchivo?id=repositorio/10221/10396/5/comunas_final.zip'
LICENSE='Uso libre señalando como fuente a la Biblioteca del Congreso Nacional de Chile; cartografía referencial'


def convert(original,folder,config):
    import shapefile
    area=load_area(ROOT/config['aoi_geojson'])
    scope=transform(INV,transform(FWD,area).buffer(config.get('transit_buffer_m',1100)+150))
    features=[]
    with zipfile.ZipFile(original) as archive:
        names={Path(name).suffix.lower():name for name in archive.namelist() if '/' not in name.rstrip('/')}
        if not {'.shp','.dbf','.prj','.shx'}<=names.keys():raise ValueError('BCN ZIP incompleto')
        projection=archive.read(names['.prj']).decode('utf-8-sig')
        crs=CRS.from_wkt(projection)
        if crs.to_epsg()!=3857:raise ValueError('CRS BCN inesperado; no se infiere una proyección')
        encoding=archive.read(names['.cpg']).decode('ascii').strip() if '.cpg' in names else None
        if not encoding:raise ValueError('BCN debe declarar codificación DBF')
        convert_xy=Transformer.from_crs(crs,4326,always_xy=True).transform
        reader=shapefile.Reader(shp=io.BytesIO(archive.read(names['.shp'])),
            shx=io.BytesIO(archive.read(names['.shx'])),dbf=io.BytesIO(archive.read(names['.dbf'])),encoding=encoding)
        total=len(reader)
        for record in reader.iterShapeRecords():
            properties=record.record.as_dict()
            geom=polygonal(make_valid(transform(convert_xy,shape(record.shape.__geo_interface__))))
            if geom.is_empty or not geom.intersects(scope):continue
            cut=str(int(properties['cod_comuna'])).zfill(5)
            features.append(dict(type='Feature',geometry=mapping(geom),properties=dict(
                id=cut,cut=cut,name=properties['Comuna'],province=properties['Provincia'],region=properties['Region'],
                source='Biblioteca del Congreso Nacional de Chile',original_attributes=properties)))
        xml=archive.read(names['.xml']).decode('utf-8',errors='replace') if '.xml' in names else ''
        created=re.search(r'<CreaDate>(\d{8})</CreaDate>',xml)
    if not features:raise ValueError('La fuente BCN no contiene comunas para el área de estudio')
    features.sort(key=lambda f:f['properties']['id'])
    doc=dict(type='FeatureCollection',features=features,metadata=dict(crs='EPSG:4326',source_crs='EPSG:3857',
        source=CATALOGUE,license=LICENSE,scope_bbox_wgs84=list(scope.bounds),original_count=total,
        edition='comunas_final.zip; metadatos ESRI creados '+(created[1] if created else 'sin fecha'),
        catalogue_temporal_notice='BCN indica ediciones de 2014, 2017 y diciembre de 2018; no se presenta como límite geodésico actual'))
    content=canonical(doc);digest=hashlib.sha256(content).hexdigest();name=f'communes_{digest[:16]}.geojson'
    (folder/name).write_bytes(content)
    return dict(file=name,sha256=digest,record_count=len(features),original_count=total,crs='EPSG:4326',
        source_crs='EPSG:3857',dbf_encoding=encoding,scope_bbox_wgs84=list(scope.bounds),edition=doc['metadata']['edition'])


def download(folder=None,original=None):
    folder=Path(folder or ROOT/'datos/entrada/comunas');folder.mkdir(parents=True,exist_ok=True)
    if original is None:
        request=Request(SOURCE,headers={'User-Agent':'UDP-Valparaiso-Routing/1.3 (academic reproducible cartography)'})
        with urlopen(request,timeout=240) as response:body=response.read();http_status=response.status
        digest=hashlib.sha256(body).hexdigest();path=folder/f'bcn_comunas_{digest[:16]}.zip';path.write_bytes(body)
    else:
        path=Path(original).resolve();body=path.read_bytes();digest=hashlib.sha256(body).hexdigest();http_status=None
        target=folder/f'bcn_comunas_{digest[:16]}.zip'
        if target.resolve()!=path:target.write_bytes(body)
        path=target
    config=json.loads((ROOT/'config/proyecto.json').read_text(encoding='utf-8'))
    derived=convert(path,folder,config)
    report=dict(schema_version='commune-acquisition-1',source=SOURCE,catalogue_url=CATALOGUE,
        original=dict(file=path.name,sha256=digest,bytes=len(body),http_status=http_status),derived=derived,
        license=LICENSE,attribution='Biblioteca del Congreso Nacional de Chile',
        fetched_at_utc=datetime.now(timezone.utc).isoformat(),producer=dict(pyshp='2.3.1',pyshp_wheel_sha256='67024c0ccdc352ba5db777c4e968483782dfa78f8e200672a90d2d30fd8b7b49'))
    temporary=folder/'manifest.json.tmp';temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.replace(folder/'manifest.json')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output');parser.add_argument('--original')
    args=parser.parse_args();print(json.dumps(download(args.output,args.original),ensure_ascii=False))
