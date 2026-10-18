"""Polígono de estudio compartido por el adaptador y sus validaciones."""
import json

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.validation import explain_validity


def load_area(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    crs = doc.get("crs", {}).get("properties", {}).get("name", "EPSG:4326")
    if crs not in ("EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84", "urn:ogc:def:crs:EPSG::4326"):
        raise ValueError("El AOI debe estar en WGS84 [longitud, latitud]")
    if doc.get("type") != "FeatureCollection" or not doc.get("features"):
        raise ValueError("AOI debe ser una FeatureCollection no vacía")
    geometries = []
    for feature in doc["features"]:
        geom = feature.get("geometry")
        if not geom or geom.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("AOI solo admite Polygon/MultiPolygon")
        value = shape(geom)
        if value.is_empty or not value.is_valid:
            raise ValueError("AOI inválido: " + explain_validity(value))
        west, south, east, north = value.bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("AOI fuera de WGS84")
        geometries.append(value)
    return unary_union(geometries)
