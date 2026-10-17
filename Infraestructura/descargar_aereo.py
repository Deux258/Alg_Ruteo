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


def download(config):
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


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    download(json.loads((ROOT/'config/proyecto.json').read_text(encoding='utf-8')))
