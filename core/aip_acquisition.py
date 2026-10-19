"""Adquisición ENR 5.1 verificable. Nunca publica ni modifica manifiestos activos."""
import argparse
import hashlib
import json
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

INDEX = 'https://aipchile.dgac.gob.cl/aip/vol1/seccion/enr'


class AcquisitionError(RuntimeError):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def error_kind(exc):
    if isinstance(exc, AcquisitionError): return exc.kind
    if isinstance(exc, HTTPError): return 'http'
    reason = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(reason, socket.gaierror): return 'dns'
    if isinstance(reason, ssl.SSLError): return 'tls'
    if isinstance(reason, (TimeoutError, socket.timeout)): return 'timeout'
    return 'connection'


class Redirects(HTTPRedirectHandler):
    def __init__(self, log): self.log = log

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != 'https':
            raise AcquisitionError('tls', 'Redirección a un transporte sin TLS rechazada')
        self.log.append(dict(initial_url=req.full_url, final_url=newurl, status=code))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def retrieve(url, folder, label, attempts, opener=None, sleep=time.sleep):
    """Tres intentos por recurso. TLS verificado por urllib/contexto del sistema."""
    for i in range(3):
        redirects = []
        item = dict(resource=label, attempt=i+1, initial_url=url, timeout_s=20,
                    started_at_utc=datetime.now(timezone.utc).isoformat())
        attempts.append(item)
        try:
            client = opener or build_opener(Redirects(redirects))
            with client.open(Request(url, headers={'User-Agent': 'UDP-Ruteo-Academico/4.0'}), timeout=20) as response:
                raw = response.read()
                final = response.geturl()
                if urlsplit(final).scheme != 'https': raise AcquisitionError('tls', 'Respuesta sin HTTPS')
                status = response.status
                if status != 200: raise AcquisitionError('http', 'HTTP '+str(status))
                content_type = response.headers.get('Content-Type', '')
            if label == 'S6_index' and b'<html' not in raw.lower() and b'<a ' not in raw.lower():
                raise AcquisitionError('content', 'El índice no contiene HTML')
            if label == 'S6' and not raw.startswith(b'%PDF'):
                raise AcquisitionError('content', 'La respuesta ENR 5.1 no es PDF')
            digest = hashlib.sha256(raw).hexdigest()
            name = f'{label}_{digest[:16]}'+('.pdf' if label == 'S6' else '.html')
            (folder/name).write_bytes(raw)
            item.update(state='downloaded', final_url=final, redirects=redirects, http_status=status)
            return dict(file=name, sha256=digest, bytes=len(raw), url=url, final_url=final,
                        fetched_at_utc=item['started_at_utc'], http_status=status, content_type=content_type), raw
        except Exception as exc:
            item.update(state='failed', error_kind=error_kind(exc), error=str(exc), redirects=redirects)
            if i == 2: raise AcquisitionError(error_kind(exc), str(exc)) from exc
            sleep([1, 3][i])


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.href=None; self.label=[]
    def handle_starttag(self, tag, attrs):
        if tag == 'a': self.href=dict(attrs).get('href'); self.label=[]
    def handle_data(self, data):
        if self.href: self.label.append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self.href:
            self.links.append((self.href, ''.join(self.label))); self.href=None


def pdf_link(raw, base):
    parser=Links(); parser.feed(raw.decode('utf-8', errors='replace'))
    candidates={urljoin(base, href) for href, label in parser.links
                if re.search(r'ENR\s*5\.1(?:\D|$)', label, re.I) and '.pdf' in href.lower()}
    if len(candidates) != 1: raise AcquisitionError('content', f'Enlace ENR 5.1 ambiguo o ausente: {len(candidates)}')
    url=candidates.pop()
    if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != urlsplit(INDEX).hostname:
        raise AcquisitionError('content', 'El PDF enlazado no pertenece al origen oficial HTTPS')
    return url


def zone_diff(old, new):
    from shapely.geometry import shape
    before={r['provider_id']:r for r in old}; after={r['provider_id']:r for r in new}
    changed=[]
    for key in sorted(before.keys() & after.keys()):
        a,b=before[key],after[key]
        geometry=not shape(a['geometry']).equals(shape(b['geometry']))
        attrs={k for k in a.keys() | b.keys() if k != 'geometry' and a.get(k) != b.get(k)}
        if geometry or attrs: changed.append(dict(id=key, geometry_changed=geometry, attributes=sorted(attrs)))
    return dict(added=sorted(after.keys()-before.keys()), removed=sorted(before.keys()-after.keys()), changed=changed)


def validate_pdf(path,area,margin_m=300):
    from Amenazas.a3_aip import transformar
    from pypdf import PdfReader
    try:
        records,parsed=transformar(path,area,margin_m)
        pages=[]
        for i,page in enumerate(PdfReader(path).pages,1):
            text=page.extract_text() or ''
            pages.append(dict(page=i, relevant=any(r['document_page']==str(i) for r in records),
                              dates=sorted(set(re.findall(r'\b\d{1,2}\s+[A-ZÁÉÍÓÚ]{3,12}\s+\d{4}\b',text))),
                              amendments=sorted(set(re.findall(r'AMDT\s*[^\n]{0,45}',text)))))
        return records,parsed,pages
    except Exception as exc: raise AcquisitionError('parser',str(exc)) from exc


def acquire(folder, area, margin_m=300, previous=None, report=None, opener=None, sleep=time.sleep):
    folder=Path(folder); folder.mkdir(parents=True, exist_ok=True)
    report=report if report is not None else {}
    report.update(source='S6', state='failed', index_url=INDEX, attempts=[])
    try:
        index,raw=retrieve(INDEX,folder,'S6_index',report['attempts'],opener,sleep)
        report['index']=index
        url=pdf_link(raw,index['final_url'])
        pdf,_=retrieve(url,folder,'S6',report['attempts'],opener,sleep)
        report['pdf']=pdf
        records,parsed,pages=validate_pdf(folder/pdf['file'],area,margin_m)
        old=validate_pdf(previous,area,margin_m)[0] if previous else None
        report.update(state='downloaded_validated', parser=parsed, page_dates=pages,
                      zone_changes=zone_diff(old,records) if old is not None else dict(state='no_previous_document'))
        encoded=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode()
        name='S6_validation_'+hashlib.sha256(encoded).hexdigest()[:16]+'.json'
        (folder/name).write_bytes(encoded)
        return dict(**pdf, state='downloaded_validated', index=index,
                    validation=dict(file=name,sha256=hashlib.sha256(encoded).hexdigest(),bytes=len(encoded)))
    except Exception as exc:
        report.update(state='failed', error_kind=error_kind(exc), error=str(exc))
        raise


def main():
    from core.contracts import ROOT
    from core.area import load_area
    from core.aerial_data import FWD, INV
    from shapely.ops import transform
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=['S6'], required=True)
    parser.add_argument('--output',type=Path,default=Path('datos/runs/diagnosticos_fuentes'))
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    config=json.loads((ROOT/'config/proyecto.json').read_text())
    area=load_area(ROOT/config['aoi_geojson'])
    area=transform(INV,transform(FWD,area).buffer(config.get('transit_buffer_m',0),quad_segs=16))
    folder=ROOT/config['aerial_raw_directory']; manifest=folder/'manifest.json'
    before=hashlib.sha256(manifest.read_bytes()).hexdigest()
    previous=folder/json.loads(manifest.read_text())['sources']['S6']['file']
    report=dict(started_at_utc=datetime.now(timezone.utc).isoformat(),active_manifest_before=before)
    try:
        report['dns']=dict(host=urlsplit(INDEX).hostname, addresses=sorted({r[4][0] for r in socket.getaddrinfo(urlsplit(INDEX).hostname,443,type=socket.SOCK_STREAM)}),state='resolved')
    except OSError as exc: report['dns']=dict(state='failed',error=str(exc))
    try: acquire(args.output,area,previous=previous,report=report)
    except Exception: pass  # El informe es la evidencia, con salida no cero al fallar.
    report['active_manifest_after']=hashlib.sha256(manifest.read_bytes()).hexdigest()
    report['active_manifest_unchanged']=report['active_manifest_after']==before
    name='diagnostico_S6_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json'
    (args.output/name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(args.output/name),state=report['state'],error_kind=report.get('error_kind'),active_manifest_unchanged=report['active_manifest_unchanged'])))
    raise SystemExit(0 if report['state']=='downloaded_validated' else 1)


if __name__=='__main__': main()
