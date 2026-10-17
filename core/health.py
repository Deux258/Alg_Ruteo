"""Comprobación usada por main y por el healthcheck del contenedor web."""
import argparse,json,sys,urllib.request

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url",default="http://127.0.0.1:8000/health")
    p.add_argument("--scope",choices=["base","completo"],default="base")
    args=p.parse_args()
    try:
        data=json.load(urllib.request.urlopen(args.url,timeout=5))
        if data.get("status")!="ready" or (args.scope=="completo" and not data.get("phase2_complete")):
            raise ValueError("Aplicación no acredita el alcance solicitado")
        print(json.dumps(data));return 0
    except Exception as exc:
        print(f"Healthcheck falló: {exc}",file=sys.stderr);return 1

if __name__=="__main__":
    raise SystemExit(main())
