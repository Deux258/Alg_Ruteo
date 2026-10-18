"""Utilidades compartidas por los ET de Metadata (y reutilizables por Amenazas)."""
import datetime as dt
import json
import os
import time
from pathlib import Path

import requests
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
AOI_PATH = os.environ.get("AOI_PATH", str(ROOT / "datos" / "aoi.geojson"))
OUT_DIR = Path(os.environ.get("OUT_DIR", str(ROOT / "datos" / "procesados")))
SCHEMA_VERSION = "1.0"


def utc_now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_aoi(path=None):
    """Devuelve la geometría shapely del AOI (WGS84, lon/lat)."""
    with open(path or AOI_PATH, encoding="utf-8") as f:
        gj = json.load(f)
    aoi = unary_union([shape(ft["geometry"]) for ft in gj["features"]])
    return aoi if aoi.is_valid else aoi.buffer(0)


def http_get(url, params=None, retries=3, timeout=60, stream=False):
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout, stream=stream)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"Fallo al consultar {url}: {last}")


def arcgis_query(layer_url, bbox, page=1000, max_pages=200, out_fields="*"):
    """Consulta paginada a una capa ArcGIS REST. bbox = (xmin, ymin, xmax, ymax) en 4326.
    Un HTTP 200 no prueba descarga completa: se pagina hasta agotar resultados."""
    feats_all, offset = [], 0
    for _ in range(max_pages):
        r = http_get(layer_url.rstrip("/") + "/query", params={
            "where": "1=1", "geometry": ",".join(map(str, bbox)),
            "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": out_fields,
            "outSR": 4326, "f": "geojson",
            "resultOffset": offset, "resultRecordCount": page})
        d = r.json()
        if "error" in d:
            raise RuntimeError(f"Error ArcGIS: {d['error']}")
        feats = d.get("features", [])
        feats_all += feats
        more = d.get("exceededTransferLimit")
        if more is None:
            more = d.get("properties", {}).get("exceededTransferLimit")
        if not feats or not (more or (more is None and len(feats) == page)):
            return feats_all
        offset += len(feats)
    raise RuntimeError("Paginación excedió max_pages; resultado posiblemente incompleto")


def url_capa_desde_item(item_id, capa=0):
    """Resuelve la URL del servicio de un item público de ArcGIS Online/Hub y devuelve la URL de la capa."""
    d = http_get(f"https://www.arcgis.com/sharing/rest/content/items/{item_id}", params={"f": "json"}).json()
    if not d.get("url"):
        raise RuntimeError(f"El item {item_id} no expone una URL de servicio: {d.get('error', d)}")
    return f"{d['url'].rstrip('/')}/{capa}"


def pick(props, candidates):
    """Primer atributo existente (sin distinguir mayúsculas) entre los nombres candidatos."""
    low = {k.lower(): v for k, v in props.items()}
    for c in candidates:
        if c.lower() in low and low[c.lower()] not in (None, ""):
            return low[c.lower()]
    return None


def write_json(filename, dataset_id, source, source_url, records, extra=None):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "fuente": source,
        "fuente_url": source_url,
        "obtenido_utc": utc_now(),
        "crs": "EPSG:4326",
        "cantidad": len(records),
        **(extra or {}),
        "registros": records,
    }
    path = OUT_DIR / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"[ok] {path}  ({len(records)} registros)")
    return path
