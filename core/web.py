"""Aplicación Leaflet y API de consulta de la instantánea vial publicada."""
import json
import logging
import os
import mimetypes
from urllib.parse import urlsplit,parse_qs
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

from core.db import connect
from core.contracts import ROOT


def safe_numbers(value):
    """JS no representa todos los BIGINT: enviar IDs grandes como decimales de texto."""
    if isinstance(value,dict):return {k:safe_numbers(v) for k,v in value.items()}
    if isinstance(value,list):return [safe_numbers(v) for v in value]
    if isinstance(value,int) and abs(value)>2**53-1:return str(value)
    return value


def status(conn):
    row=conn.execute("""SELECT r.run_id,r.status,r.scope,r.mode FROM routing.publication p
        JOIN routing.runs r USING(run_id) WHERE p.singleton""").fetchone()
    if not row or row["status"]!="ready":
        return None
    row["run_id"]=str(row["run_id"])
    row["phase2_complete"]=False
    row["application"]="foundation"
    area=conn.execute("""SELECT lineage#>>'{aoi,file}' AS file, lineage#>>'{aoi,sha256}' AS sha256,
        (SELECT count(*) FROM routing.nodes WHERE run_id=%s AND kind='base_candidata') AS candidate_bases
        FROM routing.datasets WHERE run_id=%s AND dataset_key='I'""", (row["run_id"],row["run_id"])).fetchone()
    row["study_area"]=area
    row["mission_ready"]=bool(area and area["candidate_bases"])
    row["warnings"]=[] if row["mission_ready"] else ["Sin bases candidatas; regenerar infraestructura para el nuevo AOI"]
    dataset=conn.execute("SELECT source_id,validation FROM routing.datasets WHERE run_id=%s AND dataset_key='I'",(row['run_id'],)).fetchone()
    row['routing_ready']=bool(dataset and dataset['validation'].get('road_routing',{}).get('ready'))
    if dataset and dataset['source_id']=='DERIVED_ROADS':
        row['application']='road_routing'
        row['mission_ready']=row['routing_ready']
        row['warnings']=['Acceso entre el cuartel y el nodo vial no modelado; sin tráfico ni cierres actuales']
        row['network']={k:dataset['validation'].get(k) for k in ['nodes','directed_edges','strong_count','weak_count']}
        row['base']=dataset['validation'].get('road_routing',{}).get('base')
    if dataset and dataset['source_id']=='DERIVED_AERIAL':
        row.update(application='aerial_simulator',routing_ready=True,mission_ready=True,clearance_verified=False,
                   etl_complete=row['scope']=='completo',warnings=['Simulador académico; despeje vertical no verificado'])
        row['network']={k:dataset['validation'].get(k) for k in ['nodes','directed_edges','strong_count','weak_count']}
    return row


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if urlsplit(self.path).path not in ['/api/aereo/rutas','/api/aereo/replanificar']:
            return self.reply(404,b'{"error":"not_found"}')
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=262144:raise ValueError('Solicitud vacía o mayor de 256 KiB')
            request=json.loads(self.rfile.read(length))
            with connect() as conn:
                current=status(conn)
                if not current:return self.reply(503,b'{"status":"not_ready"}')
                from core.aerial_routing import calculate
                result=calculate(conn,current['run_id'],request)
            return self.reply(200,json.dumps(safe_numbers(result),ensure_ascii=False,allow_nan=False).encode())
        except (ValueError,KeyError,TypeError) as exc:
            return self.reply(422,json.dumps({'error':str(exc)},ensure_ascii=False).encode())
        except Exception:
            logging.exception('Consulta aérea falló')
            return self.reply(503,b'{"error":"No se pudo calcular la ruta; revisar servicio y tiempo de consulta"}')

    def do_GET(self):
        parsed=urlsplit(self.path); path=parsed.path
        static={'/':'index.html','/app.js':'app.js','/aerial.js':'aerial.js','/vial.js':'vial.js','/style.css':'style.css',
                '/vendor/leaflet.js':'vendor/leaflet.js','/vendor/leaflet.css':'vendor/leaflet.css'}
        static.update({f'/vendor/images/{name}':f'vendor/images/{name}' for name in ['layers.png','layers-2x.png','marker-icon.png','marker-icon-2x.png','marker-shadow.png']})
        if path in static:
            if path=='/':
                with connect() as conn:
                    current=status(conn)
                    if current and current['application']=='road_routing':static['/']='index_vial.html'
                    if current and current['application']=='aerial_simulator':static['/']='aerial.html'
            file=ROOT/'Sitio Web'/static[path]
            if file.is_file():
                return self.reply(200,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        if path not in ("/health","/api/topologia","/api/mapa","/api/ruta","/api/nodo","/api/aereo/mapa"):
            return self.reply(404,b'{"error":"not_found"}')
        try:
            with connect() as conn:
                current=status(conn)
                if not current:
                    return self.reply(503,b'{"status":"not_ready"}')
                if path=="/api/topologia":
                    current["topology"]=conn.execute("SELECT routing.topology_report(%s) AS report",(current["run_id"],)).fetchone()["report"]
                    current['validation']=conn.execute("SELECT validation FROM routing.datasets WHERE run_id=%s AND dataset_key='I'",(current['run_id'],)).fetchone()['validation']
                elif path in ['/api/mapa','/api/aereo/mapa']:
                    if current['application']=='aerial_simulator':
                        from core.aerial_routing import map_data
                    else:
                        from core.routing import map_data
                    current=map_data(conn,current['run_id'])
                elif path=='/api/ruta':
                    from core.routing import route
                    params=parse_qs(parsed.query)
                    text=params.get('destino',[''])[0]
                    if not text.isdecimal() or not 0<int(text)<2**63:raise ValueError('destino debe ser un ID vial válido')
                    current=route(conn,current['run_id'],int(text))
                elif path=='/api/nodo':
                    import math
                    params=parse_qs(parsed.query)
                    lon=float(params.get('lon',['nan'])[0]);lat=float(params.get('lat',['nan'])[0])
                    if not math.isfinite(lon) or not math.isfinite(lat) or not -180<=lon<=180 or not -90<=lat<=90:
                        raise ValueError('Coordenadas WGS84 inválidas')
                    current=conn.execute("""WITH p AS (SELECT ST_SetSRID(ST_MakePoint(%s,%s),4326) AS wgs),
                        a AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON((lineage#>'{aoi,geometry}')::text),4326) AS geom
                        FROM routing.datasets WHERE run_id=%s AND dataset_key='I')
                        SELECT n.id::text,ST_Distance(n.geom,ST_Transform(p.wgs,32719)) AS offset_m,
                        ST_AsGeoJSON(ST_Transform(n.geom,4326))::jsonb AS geometry
                        FROM routing.nodes n CROSS JOIN p CROSS JOIN a
                        WHERE n.run_id=%s AND ST_Covers(a.geom,p.wgs) AND ST_DWithin(n.geom,ST_Transform(p.wgs,32719),100)
                        ORDER BY n.geom<->ST_Transform(p.wgs,32719),n.id LIMIT 1""",(lon,lat,current['run_id'],current['run_id'])).fetchone()
                    if not current:raise ValueError('Selecciona un punto dentro del polígono y a menos de 100 m de una calle de la red')
            return self.reply(200,json.dumps(safe_numbers(current),ensure_ascii=False,default=str).encode())
        except ValueError as exc:
            return self.reply(422,json.dumps({'error':str(exc)},ensure_ascii=False).encode())
        except Exception:
            logging.exception("Consulta de diagnóstico falló")
            return self.reply(503,b'{"status":"database_unavailable"}')

    def reply(self,code,body,content_type="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers();self.wfile.write(body)


if __name__=="__main__":
    ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","8000"))),Handler).serve_forever()
