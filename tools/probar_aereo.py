"""Evidencia real de rutas y bloqueos desde la publicación aérea vigente."""
from datetime import datetime,timezone
from shapely.geometry import LineString,Point,mapping
from core.contracts import ROOT,write_json
from core.db import connect
from core.aerial_routing import map_data,calculate,data,available


def main():
    with connect() as conn:
        rid=conn.execute('SELECT run_id FROM routing.publication WHERE singleton').fetchone()['run_id']
        view=map_data(conn,rid);model,area,_,_=data(conn,rid)
        valid=next(w['valid_at'] for w in view['weather'] if available(model,__import__('core.aerial_data',fromlist=['iso']).iso(w['valid_at']))[1] is None)
        req=dict(origin=view['default_origin'],destination=view['examples'][1]['coordinates'],time=valid,mode='mission')
        plain=calculate(conn,rid,req)
        folder=ROOT/'evidencia/local/aereo';folder.mkdir(parents=True,exist_ok=True)
        write_json(folder/'mapa.json',view);write_json(folder/'solicitud.json',req);write_json(folder/'ruta.json',plain)
        if plain['status']!='ready':raise RuntimeError('No se obtuvo misión admisible: '+str(plain['reason']))
        midpoint=LineString(plain['alternatives'][0]['outbound']['coordinates']).interpolate(.5,normalized=True)
        event=dict(id='prueba-bloqueo',state='blocked',observed_at=valid,geometry=mapping(midpoint),radius_m=80)
        blocked=calculate(conn,rid,dict(req,events=[event]));write_json(folder/'bloqueo.json',dict(request=dict(req,events=[event]),result=blocked))
        print(dict(run_id=str(rid),time=valid,status=plain['status'],alternatives=len(plain['alternatives']),lengths=[p['length_km'] for p in plain['alternatives']],blocked_status=blocked['status'],blocked_reason=blocked['reason']))


if __name__=='__main__':main()
