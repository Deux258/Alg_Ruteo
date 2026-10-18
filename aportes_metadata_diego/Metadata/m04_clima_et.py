"""M4 - Pronóstico horario Open-Meteo (API) en el centroide del AOI -> m04_clima.json
Uso: python Metadata/m04_clima_et.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raíz del repo: permite 'from core.util import ...'
from core.util import load_aoi, http_get, write_json

URL = "https://api.open-meteo.com/v1/forecast"
VARS = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m",
        "wind_direction_10m", "wind_gusts_10m", "precipitation"]
NOMBRES = {"temperature_2m": "temperatura_c", "relative_humidity_2m": "humedad_pct",
           "wind_speed_10m": "viento_ms", "wind_direction_10m": "viento_dir_grados",
           "wind_gusts_10m": "rafaga_ms", "precipitation": "precipitacion_mm"}


def main():
    c = load_aoi().centroid
    d = http_get(URL, params={
        "latitude": round(c.y, 4), "longitude": round(c.x, 4),
        "hourly": ",".join(VARS), "wind_speed_unit": "ms",
        "timezone": "UTC", "forecast_days": 2}).json()
    h = d["hourly"]
    registros = []
    for i, t in enumerate(h["time"]):
        fila = {"hora_utc": t + ":00Z"}
        for v in VARS:
            fila[NOMBRES[v]] = h[v][i]
        registros.append(fila)
    write_json("m04_clima.json", "m04_clima", "Open-Meteo (API)", URL, registros, {
        "celda_devuelta": {"lat": d.get("latitude"), "lon": d.get("longitude"),
                           "elevacion_modelo_m": d.get("elevation")},
        "unidades_originales": d.get("hourly_units"),
        "nota": "Una celda gruesa cubre todo el AOI; no representa microclima local."})


if __name__ == "__main__":
    main()
