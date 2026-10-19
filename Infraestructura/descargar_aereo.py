"""Adquisición de S1-S7 del informe; conserva respuestas HTTP sin alterar."""
import argparse
import csv
import hashlib
import io
import json
import time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,urlunsplit,urlencode
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]


def fetch(url,folder,label):
    error=None
    for attempt in range(3):
        try:
            with urlopen(Request(url,headers={'User-Agent':'UDP-Ruteo-Academico/3.0'}),timeout=180) as r:
                raw=r.read();status=r.status
            digest=hashlib.sha256(raw).hexdigest()
            suffix='.pdf' if raw.startswith(b'%PDF') else '.tif' if raw[:2] in (b'II',b'MM') else '.json' if raw.lstrip()[:1] in (b'{',b'[') else '.csv'
            name=f'{label}_{digest[:16]}{suffix}';(folder/name).write_bytes(raw)
            return dict(file=name,sha256=digest,bytes=len(raw),url=url,http_status=status,
                        fetched_at_utc=datetime.now(timezone.utc).isoformat()),raw
        except Exception as exc:
            error=exc
            if attempt<2:time.sleep(1+attempt)
    raise RuntimeError(f'{label}: {error}')


def download_legacy(config):
    folder=ROOT/config['aerial_raw_directory'];folder.mkdir(parents=True,exist_ok=True)
    originals=json.loads((ROOT/'datos/entrada/fase1/manifest_fuentes.json').read_text(encoding='utf-8'))['fuentes']
    sources={};errors={};bbox=config['bbox_wgs84']
    for source in originals:
        key=source['id'];url=source['url'];print(f'Adquiriendo {key}: {source["product"]}',flush=True)
        try:
            parts=urlsplit(url);query=parse_qs(parts.query)
            if key in ['S1','S2','S7']:
                query.update(geometry=[','.join(map(str,bbox))],outFields=['*'],resultRecordCount=['500'],resultOffset=['0'])
                query.pop('orderByFields',None)
                # Consultar IDs primero: la descarga se valida contra este conjunto.
                idsquery={k:v[0] for k,v in query.items() if k not in ['outFields','resultRecordCount','resultOffset']}
                idsquery.update(f='json',returnIdsOnly='true')
                idsmeta,idsraw=fetch(urlunsplit(parts._replace(query=urlencode(idsquery))),folder,key+'_ids')
                idsdoc=json.loads(idsraw)
                if 'error' in idsdoc or 'objectIds' not in idsdoc:raise ValueError(f'Respuesta de IDs inválida: {idsdoc}')
                ids=sorted(idsdoc['objectIds'] or []);pages=[];features=[];field=idsdoc['objectIdFieldName']
                # objectIds evita depender del soporte de paginación/orden del servidor.
                for start in range(0,len(ids),200):
                    pageq={k:v[0] for k,v in query.items() if k not in ['resultOffset','resultRecordCount']}
                    pageq['objectIds']=','.join(map(str,ids[start:start+200]))
                    meta,raw=fetch(urlunsplit(parts._replace(query=urlencode(pageq))),folder,key+f'_{start}')
                    doc=json.loads(raw)
                    if doc.get('error') or doc.get('exceededTransferLimit') or 'features' not in doc:raise ValueError('Página incompleta '+key)
                    pages.append(meta);features.extend(doc['features'])
                actual=[f['properties'][field] for f in features]
                if len(actual)!=len(set(actual)) or set(actual)!=set(ids):raise ValueError('IDs/conteos no reconciliados '+key)
                sources[key]=dict(product=source['product'],pages=pages,ids=idsmeta,record_count=len(features),id_field=field)
            else:
                if key=='S4':
                    query.update(latitude=[str((bbox[1]+bbox[3])/2)],longitude=[str((bbox[0]+bbox[2])/2)])
                    url=urlunsplit(parts._replace(query=urlencode({k:v[0] for k,v in query.items()})))
                meta,raw=fetch(url,folder,key)
                if key=='S4' and ('hourly' not in json.loads(raw)):raise ValueError('Pronóstico inválido')
                if key=='S5':
                    fields=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))).fieldnames
                    if not fields or not {'latitude','longitude','acq_date','acq_time'}<=set(fields):raise ValueError('CSV FIRMS inválido')
                if key=='S6' and not raw.startswith(b'%PDF'):raise ValueError('AIP no es PDF')
                sources[key]=dict(product=source['product'],**meta)
        except Exception as exc:errors[key]=str(exc);print(f'ERROR {key}: {exc}',flush=True)
    report=dict(version=1,bbox_wgs84=bbox,sources=sources,errors=errors,
                fetched_at_utc=datetime.now(timezone.utc).isoformat())
    target=folder/('adquisicion_incompleta.json' if errors else 'manifest.json')
    temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.replace(target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    (folder/(target.stem+'_'+digest[:16]+'.json')).write_bytes(target.read_bytes())
    if errors:raise RuntimeError('Fuentes incompletas: '+json.dumps(errors,ensure_ascii=False))
    return report


def download(config, selected=None, reuse=None):
    if not config.get('transit_buffer_m'):
        return download_legacy(config)
    import shutil
    from urllib.parse import quote
    from core.area import load_area
    from core.aerial_data import FWD, INV
    from shapely.ops import transform
    folder=ROOT/config['aerial_raw_directory'];folder.mkdir(parents=True,exist_ok=True)
    keys={f'S{i}' for i in range(1,8)}|{'S1H'}
    selected=set(selected) if selected is not None else keys
    reuse=set(reuse or [])
    if selected & reuse or selected | reuse != keys:
        raise ValueError('Descargar o reutilizar explícitamente cada fuente S1–S7 y S1H, sin solapamientos')
    area=load_area(ROOT/config['aoi_geojson'])
    bbox=list(transform(INV,transform(FWD,area).buffer(config['transit_buffer_m'],quad_segs=16)).bounds)
    previous_folder=ROOT/config.get('reuse_raw_directory','datos/entrada/aereo')
    if (folder/'manifest.json').exists():previous_folder=folder
    previous=json.loads((previous_folder/'manifest.json').read_text(encoding='utf-8')) if reuse else {}
    specs={s['id']:s for s in json.loads((ROOT/'datos/entrada/fase1/manifest_fuentes.json').read_text(encoding='utf-8'))['fuentes']}
    sources={};errors={}
    for key in sorted(keys):
        print('Adquiriendo '+key,flush=True)
        try:
            if key in reuse:
                if key in ['S1','S1H','S2','S7'] and previous.get('acquisition_bbox_wgs84')!=bbox:
                    raise ValueError('Fuente espacial reutilizada no cubre la nueva área; descargar '+key)
                entry=json.loads(json.dumps(previous['sources'][key]))
                files=[entry['ids']]+entry['pages'] if 'pages' in entry else [entry]
                if 'catalogue' in entry:files=files+[entry['catalogue']]
                for file in files:
                    original=previous_folder/file['file']
                    if hashlib.sha256(original.read_bytes()).hexdigest()!=file['sha256']:raise ValueError('Original reutilizado alterado')
                    target=folder/file['file']
                    if original.resolve()!=target.resolve():shutil.copyfile(original,target)
                entry['reuse']=dict(explicit=True,manifest_sha256=hashlib.sha256((previous_folder/'manifest.json').read_bytes()).hexdigest())
                sources[key]=entry;continue
            catalogue=None
            if key=='S1H':
                catalogue,body=fetch('https://www.arcgis.com/sharing/rest/content/items/ac7929a4d40e4879afd09b0c04b12fd3?f=json',folder,'S1H_catalogue')
                item=json.loads(body)
                url=quote(item['url'].rstrip('/')+'/0',safe=':/')+'/query'
                product='Junta Nacional de Bomberos / IDE CHILE; republicación ArcGIS TerrenoIII'
            else:url=specs[key]['url'];product=specs[key]['product']
            if key in ['S1','S1H','S2','S7']:
                parts=urlsplit(url);q={k:v[0] for k,v in parse_qs(parts.query).items()}
                q.update(where='1=1',geometry=','.join(map(str,bbox)),geometryType='esriGeometryEnvelope',inSR='4326',outSR='4326',spatialRel='esriSpatialRelIntersects',outFields='*',f='json',returnIdsOnly='true')
                idsmeta,body=fetch(urlunsplit(parts._replace(query=urlencode(q))),folder,key+'_ids')
                idsdoc=json.loads(body)
                if 'error' in idsdoc or 'objectIds' not in idsdoc:raise ValueError('IDs ArcGIS inválidos')
                ids=sorted(idsdoc['objectIds'] or []);field=idsdoc['objectIdFieldName'];pages=[];features=[]
                for offset in range(0,len(ids),200):
                    query={k:v for k,v in q.items() if k!='returnIdsOnly'};query.update(f='geojson',objectIds=','.join(map(str,ids[offset:offset+200])))
                    meta,body=fetch(urlunsplit(parts._replace(query=urlencode(query))),folder,key+'_'+str(offset));doc=json.loads(body)
                    if doc.get('error') or doc.get('exceededTransferLimit') or 'features' not in doc:raise ValueError('Página incompleta')
                    pages.append(meta);features.extend(doc['features'])
                got=[f['properties'][field] for f in features]
                if len(got)!=len(set(got)) or set(got)!=set(ids):raise ValueError('IDs/conteos no reconciliados')
                sources[key]=dict(product=product,ids=idsmeta,pages=pages,record_count=len(features),id_field=field)
                if catalogue:sources[key]['catalogue']=catalogue
            else:
                if key=='S4':
                    parts=urlsplit(url);q={k:v[0] for k,v in parse_qs(parts.query).items()}
                    q.update(latitude=str(area.centroid.y),longitude=str(area.centroid.x),models='ecmwf_ifs025',timezone='UTC',wind_speed_unit='ms')
                    url=urlunsplit(parts._replace(query=urlencode(q)))
                meta,body=fetch(url,folder,key)
                if key=='S4' and 'hourly' not in json.loads(body):raise ValueError('Pronóstico inválido')
                if key=='S5' and not {'latitude','longitude','acq_date','acq_time','confidence','frp'}<=set(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))).fieldnames or []):raise ValueError('CSV FIRMS inválido')
                if key=='S6' and not body.startswith(b'%PDF'):raise ValueError('AIP no es PDF')
                sources[key]=dict(product=product,**meta)
        except Exception as exc:errors[key]=str(exc);print('ERROR '+key+': '+str(exc),flush=True)
    report=dict(version=2,bbox_wgs84=config['bbox_wgs84'],acquisition_bbox_wgs84=bbox,transit_buffer_m=config['transit_buffer_m'],sources=sources,errors=errors,fetched_at_utc=datetime.now(timezone.utc).isoformat())
    target=folder/('adquisicion_incompleta.json' if errors else 'manifest.json')
    temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.replace(target)
    digest=hashlib.sha256(target.read_bytes()).hexdigest();(folder/(target.stem+'_'+digest[:16]+'.json')).write_bytes(target.read_bytes())
    if errors:raise RuntimeError('Fuentes incompletas: '+json.dumps(errors,ensure_ascii=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'config/proyecto.json')
    parser.add_argument('--sources',help='IDs separados por coma; las demás fuentes deben declararse con --reuse')
    parser.add_argument('--reuse',default='',help='Reutilización explícita de originales verificados')
    args=parser.parse_args()
    download(json.loads(args.config.read_text(encoding='utf-8')),args.sources.split(',') if args.sources else None,args.reuse.split(',') if args.reuse else [])
