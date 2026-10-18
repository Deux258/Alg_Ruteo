"""M3 - Elevación Copernicus GLO-30 (GeoTIFF/COG público) muestreada en los nodos -> m03_elevacion.json
Requiere infraestructura.json con {"nodos": [{"id":..., "lon":..., "lat":...}, ...]} (supuesto: acordar con quien arma el grafo).
Uso: python Metadata/m03_elevacion_et.py [ruta/infraestructura.json]
La URL sigue el patrón del bucket público de AWS; verificar con una descarga real."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raíz del repo: permite 'from core.util import ...'
import json
import math
import sys
import rasterio
from core.util import load_aoi, write_json, OUT_DIR

BASE = "https://copernicus-dem-30m.s3.amazonaws.com"


def tile_url(lat_floor, lon_floor):
    ns = "N" if lat_floor >= 0 else "S"
    ew = "E" if lon_floor >= 0 else "W"
    name = f"Copernicus_DSM_COG_10_{ns}{abs(lat_floor):02d}_00_{ew}{abs(lon_floor):03d}_00_DEM"
    return f"{BASE}/{name}/{name}.tif"


def main():
    ruta = sys.argv[1] if len(sys.argv) > 1 else str(OUT_DIR / "infraestructura.json")
    with open(ruta, encoding="utf-8") as f:
        nodos = json.load(f)["nodos"]
    xmin, ymin, xmax, ymax = load_aoi().bounds
    tiles = {(math.floor(lat), math.floor(lon))
             for lat in (ymin, ymax) for lon in (xmin, xmax)}
    registros = {n["id"]: {"nodo_id": n["id"], "lon": n["lon"], "lat": n["lat"],
                           "elevacion_m": None, "estado": "sin_dato"} for n in nodos}
    urls = []
    for lat_f, lon_f in sorted(tiles):
        url = tile_url(lat_f, lon_f)
        urls.append(url)
        with rasterio.open(url) as src:
            for n in nodos:
                if not (lon_f <= n["lon"] < lon_f + 1 and lat_f <= n["lat"] < lat_f + 1):
                    continue
                v = float(next(src.sample([(n["lon"], n["lat"])]))[0])
                if (src.nodata is not None and v == src.nodata) or math.isnan(v):
                    continue  # queda NoData explícito
                registros[n["id"]].update(elevacion_m=round(v, 1), estado="ok")
    write_json("m03_elevacion.json", "m03_elevacion", "Copernicus GLO-30 DEM",
               ", ".join(urls), list(registros.values()),
               {"unidad": "metros sobre el nivel del mar", "nodata": "elevacion_m = null"})


if __name__ == "__main__":
    main()
