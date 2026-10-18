"""Resumen de control de los 4 JSON de metadata. Uso: python verificar_metadata.py"""
import collections
import json
import math
from shapely.geometry import shape
from shapely.ops import transform, unary_union
from core.util import OUT_DIR, load_aoi


def cargar(nombre):
    p = OUT_DIR / nombre
    if not p.exists():
        print(f"[falta] {nombre}\n")
        return None
    return json.load(open(p, encoding="utf-8"))


aoi = load_aoi()
lat0 = aoi.centroid.y
kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
m = lambda x, y, z=None: (x * kx, y * ky)
aoi_km2 = transform(m, aoi).area / 1e6
print(f"AOI: {aoi_km2:.1f} km2 (aprox.)\n")

d = cargar("m01_bases.json")
if d:
    r = d["registros"]
    print(f"M1 bases: {len(r)} compañías en la caja; {sum(x['dentro_aoi'] for x in r)} dentro del AOI; "
          f"distancia máx. al AOI de las de fuera: {max(x['distancia_aoi_km'] for x in r):.2f} km\n")

d = cargar("m02_cobertura.json")
if d:
    r = d["registros"]
    cub = transform(m, unary_union([shape(x["geometry"]) for x in r])).area / 1e6
    print(f"M2 cobertura: {len(r)} polígonos; cubren {cub:.1f} km2 = {100*cub/aoi_km2:.0f}% del AOI")
    for k, v in collections.Counter(x["uso"] for x in r).most_common():
        print(f"   {v:4d}  {k}")
    print("   (lo no cubierto suele ser mar o zonas sin dato)\n")

d = cargar("m03_elevacion.json")
if d:
    r = d["registros"]
    ok = [x["elevacion_m"] for x in r if x["estado"] == "ok"]
    print(f"M3 elevación: {len(r)} nodos, {len(ok)} con dato" + (f"; rango {min(ok)}-{max(ok)} m" if ok else "") + "\n")

d = cargar("m04_clima.json")
if d:
    r = d["registros"]
    t = [x["temperatura_c"] for x in r]; v = [x["viento_ms"] for x in r]
    print(f"M4 clima: {len(r)} horas, {r[0]['hora_utc']} a {r[-1]['hora_utc']}; "
          f"temp {min(t)}..{max(t)} C; viento {min(v)}..{max(v)} m/s")
