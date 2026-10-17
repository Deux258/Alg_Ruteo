"""Servicio de diagnóstico. La interfaz Leaflet corresponde a Diego Hidalgo."""
import json
import logging
import os
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

from core.db import connect


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
    return row


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path=="/":
            body=("<!doctype html><html lang='es'><meta charset='utf-8'><title>Base de ruteo</title>"
                  "<h1>Base SQL y topología</h1><p>Servicio de diagnóstico de la parte de Diego Muñoz.</p>"
                  "<p>La interfaz Leaflet y la comparación de algoritmos se integran en los módulos del equipo.</p>"
                  "<ul><li><a href='/health'>Estado</a></li><li><a href='/api/topologia'>Auditoría topológica</a></li></ul></html>").encode()
            return self.reply(200,body,"text/html; charset=utf-8")
        if self.path not in ("/health","/api/topologia"):
            return self.reply(404,b'{"error":"not_found"}')
        try:
            with connect() as conn:
                current=status(conn)
                if not current:
                    return self.reply(503,b'{"status":"not_ready"}')
                if self.path=="/api/topologia":
                    current["topology"]=conn.execute("SELECT routing.topology_report(%s) AS report",(current["run_id"],)).fetchone()["report"]
            return self.reply(200,json.dumps(safe_numbers(current),ensure_ascii=False,default=str).encode())
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
