"""Aplicación Leaflet y API de consulta de la instantánea vial publicada."""
import json
import logging
import os
import mimetypes
import gzip
import threading
from collections import OrderedDict
from urllib.parse import urlsplit,parse_qs
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

from core.db import connect
from core.contracts import ROOT

PATROL_LOCK = threading.Lock()
PATROL_RESULTS = OrderedDict()
PATROL_RESULT_BYTES = {}
PATROL_MEMORY_LIMIT = 64*1024*1024


def remember_patrol(result):
    """Keep a bounded hot set; immutable exports survive cache eviction/restart."""
    from core.geo_transport import publish_result
    from core.geographic_scene import retained_size
    refs=publish_result(result);digest=result['sha256']
    weight=retained_size(result)
    PATROL_RESULTS[digest]=result;PATROL_RESULTS.move_to_end(digest)
    PATROL_RESULT_BYTES[digest]=weight
    while len(PATROL_RESULTS)>3 or sum(PATROL_RESULT_BYTES.values())>PATROL_MEMORY_LIMIT:
        key,_=PATROL_RESULTS.popitem(last=False);PATROL_RESULT_BYTES.pop(key,None)
    return refs


def previous_patrol(digest):
    if digest in PATROL_RESULTS:
        PATROL_RESULTS.move_to_end(digest);return PATROL_RESULTS[digest]
    from core.geo_transport import result_refs,store
    refs=result_refs(digest) if isinstance(digest,str) else None
    if refs:return store().read_json(refs['exportar'])
    return None


def patrol_model(conn=None, current=None):
    from core.patrol import snapshot_context
    path = os.getenv('PATROL_CONTEXT')
    if path:
        return snapshot_context(path)
    model=conn.execute('SELECT context FROM routing.aerial_models WHERE run_id=%s',(current['run_id'],)).fetchone()['context']
    return dict(model,_run_id=current['run_id'])


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
        row.update(application='aerial_simulator',routing_ready=True,mission_ready=True,mission_feasibility='requires_specific_request',clearance_verified=False,
                   etl_complete=row['scope']=='completo',warnings=['Simulador académico; despeje vertical no verificado'])
        row['network']={k:dataset['validation'].get(k) for k in ['nodes','directed_edges','strong_count','weak_count']}
    return row


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        parsed=urlsplit(self.path);path=parsed.path;params=parse_qs(parsed.query)
        if path not in ['/api/aereo/rutas','/api/aereo/replanificar','/api/aereo/comparar','/api/aereo/patrullaje','/api/aereo/patrullaje/simular','/api/aereo/patrullaje/validar','/api/aereo/patrullaje/objetivo','/api/aereo/patrullaje/jornada']:
            return self.reply(404,b'{"error":"not_found"}')
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=262144:raise ValueError('Solicitud vacía o mayor de 256 KiB')
            request=json.loads(self.rfile.read(length))
            if not isinstance(request,dict):raise ValueError('Solicitud JSON debe ser un objeto')
            if path.endswith('/objetivo'):
                from core.patrol import validate_polygon
                from core.vertical_profile import target_display_summary
                from shapely.geometry import shape,mapping
                from shapely.ops import transform
                from core.aerial_data import INV
                if os.getenv('PATROL_CONTEXT'):model=patrol_model()
                else:
                    with connect() as conn:
                        current=status(conn)
                        if not current:return self.reply(503,b'{"status":"not_ready"}')
                        model=patrol_model(conn,current)
                target=validate_polygon(request,shape(model['study_geometry']))
                return self.json_reply(dict(target_display=target_display_summary(model,mapping(transform(INV,target)))))
            if path.endswith('/validar'):
                from core.mission_constraints import assess_constraints
                if os.getenv('PATROL_CONTEXT'):assessment=assess_constraints(patrol_model(),request)
                else:
                    with connect() as conn:
                        current=status(conn)
                        if not current:return self.reply(503,b'{"status":"not_ready"}')
                        assessment=assess_constraints(patrol_model(conn,current),request)
                return self.json_reply(dict(valid=assessment['admissible'],violations=assessment['reasons'],constraints=assessment))
            if path.startswith('/api/aereo/patrullaje') or 'target_polygon' in request:
                if not PATROL_LOCK.acquire(blocking=False):
                    return self.reply(429,b'{"error":"Hay un patrullaje en calculo. Reintentar al finalizar."}')
                try:
                    from core.patrol import calculate,simulate
                    if path.endswith('/jornada'):
                        from core.patrol_day import daily
                        if os.getenv('PATROL_CONTEXT'):result=daily(patrol_model(),request,on_result=remember_patrol)
                        else:
                            with connect() as conn:
                                current=status(conn)
                                if not current:return self.reply(503,b'{"status":"not_ready"}')
                                result=daily(patrol_model(conn,current),request,conn,remember_patrol)
                    elif path.endswith('/simular'):
                        previous=previous_patrol(request.get('sha256'))
                        if previous is None:raise ValueError('Resultado no disponible: recalcular la misión antes de simular')
                        if previous.get('geographic_scene'):
                            # Restore the identical surface after a process/cache restart.
                            from core.patrol import flight_terrain
                            model=patrol_model() if os.getenv('PATROL_CONTEXT') else None
                            if model is None:
                                with connect() as conn:
                                    current=status(conn)
                                    if not current:return self.reply(503,b'{"status":"not_ready"}')
                                    model=patrol_model(conn,current)
                            surface=flight_terrain(model)
                            if surface.source_sha256!=previous['geographic_scene']['surface_sha256']:
                                raise ValueError('Las fuentes de la escena cambiaron: recalcular antes de simular')
                        result=simulate(previous,request)
                        from core.patrol_monitoring import record
                        from core.geographic_scene import surface_by_hash
                        result['monitoring_progress']=record(previous,result,surface_by_hash(previous['geographic_scene']['sha256']))
                    else:
                        if 'previous_sha256' in request:
                            previous=previous_patrol(request['previous_sha256'])
                            if previous is None:raise ValueError('Misión anterior no disponible para replanificar')
                            activated=request.get('activated_threat_ids',[])
                            if not isinstance(activated,list) or any(not isinstance(i,str) for i in activated) or set(activated)-{r['id'] for r in previous['threats']}:
                                raise ValueError('Amenazas activadas desconocidas en la misión anterior')
                            request=dict(previous['request'],**{k:v for k,v in request.items() if k!='previous_sha256'})
                            request['activated_threat_ids']=activated
                        if os.getenv('PATROL_CONTEXT'):result=calculate(patrol_model(),request)
                        else:
                            with connect() as conn:
                                current=status(conn)
                                if not current:return self.reply(503,b'{"status":"not_ready"}')
                                result=calculate(patrol_model(conn,current),request,conn)
                    if 'routes' in result:
                        refs=remember_patrol(result)
                        if params.get('view')==['summary']:
                            from core.geo_transport import result_summary
                            result=result_summary(result,refs)
                    return self.json_reply(result)
                finally:
                    PATROL_LOCK.release()
            with connect() as conn:
                current=status(conn)
                if not current:return self.reply(503,b'{"status":"not_ready"}')
                from core.aerial_routing import calculate
                if urlsplit(self.path).path=='/api/aereo/comparar':
                    from core.mission_evaluation import compare
                    result=compare(conn,current['run_id'],request)
                else:result=calculate(conn,current['run_id'],request)
            return self.reply(200,json.dumps(safe_numbers(result),ensure_ascii=False,allow_nan=False).encode())
        except (ValueError,KeyError,TypeError) as exc:
            return self.reply(422,json.dumps({'error':str(exc)},ensure_ascii=False).encode())
        except Exception:
            logging.exception('Consulta aérea falló')
            return self.reply(503,b'{"error":"No se pudo calcular la ruta; revisar servicio y tiempo de consulta"}')

    def do_GET(self):
        parsed=urlsplit(self.path); path=parsed.path;params=parse_qs(parsed.query)
        if path.startswith('/api/aereo/patrullaje/recursos/'):
            from core.geo_transport import store
            resource=store().get(path.rsplit('/',1)[-1])
            if resource:return self.immutable_reply(resource)
            return self.reply(404,b'{"error":"resource_not_found"}')
        if path.startswith('/api/aereo/patrullaje/resultados/'):
            try:
                from core.geo_transport import filtered_result_resource
                parts=path.split('/')
                if len(parts)!=7:return self.reply(404,b'{"error":"not_found"}')
                resource=filtered_result_resource(parts[-2],parts[-1],params.get('commune_id',[None])[0])
                if resource:return self.immutable_reply(resource)
                return self.reply(404,b'{"error":"result_not_found"}')
            except (ValueError,KeyError,TypeError) as exc:return self.json_reply({'error':str(exc)},422)
        static={'/':'index.html','/app.js':'app.js','/aerial.js':'aerial.js','/vial.js':'vial.js','/style.css':'style.css',
                '/vendor/leaflet.js':'vendor/leaflet.js','/vendor/leaflet.css':'vendor/leaflet.css'}
        static.update({f'/vendor/images/{name}':f'vendor/images/{name}' for name in ['layers.png','layers-2x.png','marker-icon.png','marker-icon-2x.png','marker-shadow.png']})
        static.update({'/patrullaje':'patrol.html','/patrol.js':'patrol.js','/patrol.css':'patrol.css','/terrain3d.js':'terrain3d.js','/fase2':'aerial.html'})
        static['/flight-player.js']='flight-player.js'
        static['/patrol-editing.js']='patrol-editing.js'
        static['/patrol-presentation.js']='patrol-presentation.js'
        static['/mission-export.js']='mission-export.js'
        if os.getenv('PATROL_CONTEXT'):static['/']='patrol.html'
        if path in static:
            if path=='/' and not os.getenv('PATROL_CONTEXT'):
                with connect() as conn:
                    current=status(conn)
                    if current and current['application']=='road_routing':static['/']='index_vial.html'
                    if current and current['application']=='aerial_simulator':static['/']='patrol.html'
            file=ROOT/'Sitio Web'/static[path]
            if file.is_file():
                return self.reply(200,file.read_bytes(),mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
        if path in ('/api/aereo/patrullaje/mapa','/api/aereo/patrullaje/escena3d','/api/aereo/patrullaje/monitoreo'):
            try:
                from core.patrol import map_data,scene_data
                from core.geo_transport import map_summary,scene_summary,legacy_filtered_map
                commune_id=params.get('commune_id',[None])[0] or None
                summary=params.get('view')==['summary']
                def build(model,engine):
                    if path.endswith('/monitoreo'):
                        from core.patrol_monitoring import catalogue
                        from core.patrol_day import programmes
                        catalog=catalogue(model);catalog['programmes']=programmes(catalog,model)
                        return catalog
                    if path.endswith('/escena3d'):
                        result=scene_summary(model,commune_id) if summary or commune_id else scene_data(model)
                        return dict(result,engine=engine)
                    return map_summary(model,engine,commune_id) if summary else legacy_filtered_map(model,engine,commune_id)
                if os.getenv('PATROL_CONTEXT'):
                    result=build(patrol_model(),'snapshot local · Dijkstra Python (sin pgRouting)')
                else:
                    with connect() as conn:
                        current=status(conn)
                        if not current:return self.reply(503,b'{"status":"not_ready"}')
                        result=build(patrol_model(conn,current),'PostGIS + pgRouting')
                return self.reply(200,json.dumps(result,ensure_ascii=False,allow_nan=False).encode())
            except (ValueError,KeyError) as exc:
                return self.reply(422,json.dumps({'error':str(exc)},ensure_ascii=False).encode())
            except Exception:
                logging.exception('Mapa de patrullaje falló')
                return self.reply(503,b'{"error":"No se pudo cargar el snapshot de patrullaje"}')
        if path=='/health' and os.getenv('PATROL_CONTEXT'):
            return self.reply(200,b'{"status":"ready","mode":"patrol_snapshot","database":false}')
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

    def json_reply(self,value,code=200):
        return self.reply(code,json.dumps(safe_numbers(value),ensure_ascii=False,allow_nan=False).encode())

    def immutable_reply(self,resource):
        from core.geo_transport import store
        etag='"'+resource['sha256']+'"'
        if self.headers.get('If-None-Match')==etag:
            self.send_response(304);self.send_header('ETag',etag);self.send_header('Cache-Control','public, max-age=31536000, immutable');self.end_headers();return
        compressed='gzip' in self.headers.get('Accept-Encoding','')
        path=store().folder/(resource['sha256']+('.gz' if compressed else '.data'))
        self.send_response(200);self.send_header('Content-Type',resource['content_type']);self.send_header('Content-Length',str(path.stat().st_size))
        self.send_header('ETag',etag);self.send_header('Cache-Control','public, max-age=31536000, immutable');self.send_header('Vary','Accept-Encoding')
        self.send_header('X-Content-Type-Options','nosniff')
        if compressed:self.send_header('Content-Encoding','gzip')
        self.end_headers()
        with path.open('rb') as stream:
            while chunk:=stream.read(131072):self.wfile.write(chunk)

    def reply(self,code,body,content_type="application/json; charset=utf-8"):
        compressed=len(body)>1048576 and 'gzip' in self.headers.get('Accept-Encoding','') and content_type.startswith('application/json')
        if compressed:body=gzip.compress(body,compresslevel=1)
        self.send_response(code)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(body)))
        if compressed:self.send_header('Content-Encoding','gzip')
        self.send_header('Vary','Accept-Encoding')
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.end_headers();self.wfile.write(body)


if __name__=="__main__":
    ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","8000"))),Handler).serve_forever()
