"""M1 - Compañías de Bomberos, Región de Valparaíso (ArcGIS Hub/Online) -> m01_bases.json
Fuente: dataset "Compañías de bomberos, Región de Valparaíso, sector sur"
(item ac7929a4d40e4879afd09b0c04b12fd3, capa 0). Es un servicio de ArcGIS Online; la URL del
servicio se resuelve en ejecución a partir del item. Datos originales: Junta Nacional de Bomberos.
Uso: python Metadata/m01_bases_et.py   (opcional: URL_BASES para forzar otra capa)"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raíz del repo: permite 'from core.util import ...'
import math
from shapely.geometry import shape
from shapely.ops import transform
from core.util import load_aoi, arcgis_query, url_capa_desde_item, pick, write_json

ITEM_ID = "ac7929a4d40e4879afd09b0c04b12fd3"
MAX_DIST_KM = 1.1  # se conservan las compañías a esta distancia (o menos) del borde de la zona
BUFFER_KM = float(os.environ.get("BASES_BUFFER_KM", "10"))  # se buscan compañías hasta ~10 km alrededor de la zona
# Nombres de campo candidatos (no verificados): revisar 'atributos_originales' en la primera salida y ajustar.
# Decisión del equipo: además de la que está dentro de la zona, estas compañías cercanas al borde se aceptan como
# orígenes. Se guardan todas las compañías a <= MAX_DIST_KM del borde de la zona (las demás se descartan);
# de ellas, solo la de dentro y estas quedan marcadas como candidatas a origen. Se comparan por nombre, sin tildes ni mayúsculas.
SELECCIONADAS = ["Decima de Valparaiso", "Decima Quinta de Valparaiso", "Decima Segunda de Valparaiso",
                 "Decima Tercera de Valparaiso"]


def _norm(t):
    t = (t or "").lower().strip()
    for a, b in zip("áéíóú", "aeiou"):
        t = t.replace(a, b)
    return t


CAMPOS = {
    "nombre": ["nombre", "name", "compania", "compañia", "cuerpo", "NOM_CIA", "NOMBRE_CBS"],
    "direccion": ["direccion", "dirección", "address", "calle", "DIR"],
    "comuna": ["comuna", "nom_comuna", "NOM_COM", "NOM_COMUNA"],
}


def _a_metros(lat0):
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    return lambda x, y, z=None: (x * kx, y * ky)


def main():
    url = os.environ.get("URL_BASES") or url_capa_desde_item(ITEM_ID, 0)
    print("Capa:", url)
    aoi = load_aoi()
    xmin, ymin, xmax, ymax = aoi.bounds
    dlat = BUFFER_KM / 110.54
    dlon = BUFFER_KM / (111.32 * math.cos(math.radians(aoi.centroid.y)))
    feats = arcgis_query(url, (xmin - dlon, ymin - dlat, xmax + dlon, ymax + dlat))
    registros, todos = [], []
    m = _a_metros(aoi.centroid.y)
    aoi_m = transform(m, aoi)
    for i, f in enumerate(feats):
        if not f.get("geometry"):
            continue
        pt = shape(f["geometry"])
        dentro = aoi.intersects(pt)
        dist_km = 0.0 if dentro else round(aoi_m.distance(transform(m, pt)) / 1000, 2)  # aproximado
        p = f.get("properties", {})
        nombre = pick(p, CAMPOS["nombre"])
        elegida = _norm(nombre) in [_norm(x) for x in SELECCIONADAS]
        todos.append(nombre)
        if not (dentro or elegida or dist_km <= MAX_DIST_KM):
            continue  # decisión del equipo: solo se conservan las compañías a <= 1,1 km del borde
        registros.append({
            "id": f.get("id", i),
            "nombre": nombre,
            "direccion": pick(p, CAMPOS["direccion"]),
            "comuna": pick(p, CAMPOS["comuna"]),
            "lon": pt.x, "lat": pt.y,
            "dentro_aoi": dentro,
            "distancia_aoi_km": dist_km,
            "candidata_origen": bool(dentro or elegida),
            "motivo_candidata": "dentro_aoi" if dentro else ("seleccionada_por_equipo" if elegida else None),
            "atributos_originales": p,
        })
    n_dentro = sum(r["dentro_aoi"] for r in registros)
    print(f"En la caja ampliada ({BUFFER_KM:g} km): {len(feats)} | dentro del AOI: {n_dentro}")
    hallados = {_norm(r["nombre"]) for r in registros}
    for sel in SELECCIONADAS:
        if _norm(sel) not in hallados:
            parecidos = sorted({t for t in todos if t and _norm(sel).split()[1] in _norm(t)})
            print(f"AVISO: no se encontró '{sel}' en la fuente. Nombres parecidos: {parecidos or 'ninguno'}")
    print(f"Compañías conservadas (<= {MAX_DIST_KM} km del borde): {len(registros)}")
    print("Candidatas a origen:", [r["nombre"] for r in registros if r["candidata_origen"]])
    if sum(r["candidata_origen"] for r in registros) < 2:
        print("AVISO: menos de 2 candidatas a origen.")
    write_json("m01_bases.json", "m01_bases", "Compañías de Bomberos - Valparaíso (ArcGIS Hub)",
               url, registros, {"descargados_bbox": len(feats),
                "buffer_km": BUFFER_KM,
                "nota": "Se conservan las compañías a 1,1 km o menos del borde de la zona; candidata_origen marca la de dentro y las elegidas por el equipo. distancia_aoi_km es aproximada."})


if __name__ == "__main__":
    main()