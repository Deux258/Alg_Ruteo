"""Descarga y conserva originales OSM/Overpass y SENAPRED, sin credenciales."""
import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from core.contracts import ROOT, write_json

OVERPASS_ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
FIRE_ENDPOINT = "https://services5.arcgis.com/i7S5PSnIJAUcWvSE/arcgis/rest/services/Servicios_2024/FeatureServer/1/query"
AGENT = "UDP-Valparaiso-Routing/1.0 (academic reproducible geographic ETL)"


def fetch(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(req, timeout=240) as response:
        content = response.read()
        status = response.status
    doc = json.loads(content)
    if doc.get("error") or doc.get("remark"):
        raise ValueError("El proveedor devolvió error o resultado parcial: " + str(doc.get("error", doc.get("remark"))))
    return content, doc, status


def download(config, folder=None):
    folder = folder or ROOT / config.get("road_raw_directory", "datos/entrada/vial")
    folder.mkdir(parents=True, exist_ok=True)
    west, south, east, north = config["bbox_wgs84"]
    bbox = f"{south},{west},{north},{east}"
    query = f'''[out:json][timeout:180];
way["highway"]({bbox})->.roads;
rel(bw.roads)["type"="restriction"]->.restrictions;
(.roads;.restrictions;nwr["amenity"="fire_station"]({bbox}););
out meta;
>;
out meta;
'''
    errors = []
    for endpoint in config.get("overpass_endpoints", OVERPASS_ENDPOINTS):
        try:
            print("Consultando " + endpoint, flush=True)
            osm_bytes, osm, osm_status = fetch(endpoint, urllib.parse.urlencode({"data": query}).encode())
            if not osm.get("elements") or not any(e.get("type")=="way" for e in osm["elements"]):
                raise ValueError("Overpass no entregó vías")
            break
        except Exception as exc:
            errors.append(f"{endpoint}: {exc}")
    else:
        raise RuntimeError("No se obtuvo la red OSM: " + " | ".join(errors))
    params = dict(where="1=1", geometry=f"{west},{south},{east},{north}",
                  geometryType="esriGeometryEnvelope", inSR=4326, spatialRel="esriSpatialRelIntersects",
                  outFields="*", outSR=4326, f="geojson", resultRecordCount=2000)
    url = FIRE_ENDPOINT + "?" + urllib.parse.urlencode(params)
    print("Consultando instalaciones SENAPRED", flush=True)
    fire_bytes, fire, fire_status = fetch(url)
    if fire.get("type") != "FeatureCollection" or fire.get("exceededTransferLimit") or not fire.get("features"):
        raise ValueError("SENAPRED no entregó instalaciones completas")
    police_url=url.replace('/FeatureServer/1/query','/FeatureServer/3/query')
    police_bytes,police,police_status=fetch(police_url)
    if police.get('type')!='FeatureCollection' or police.get('exceededTransferLimit') or not police.get('features'):
        raise ValueError('SENAPRED no entregó instalaciones policiales completas')
    now = datetime.now(timezone.utc).isoformat()
    records = {}
    for key, content, status, source_url in [
        ("osm", osm_bytes, osm_status, endpoint), ("senapred", fire_bytes, fire_status, url),
        ('senapred_carabineros',police_bytes,police_status,police_url)]:
        digest = hashlib.sha256(content).hexdigest()
        name = f"{key}_{digest[:16]}.json"
        path = folder/name
        if path.exists() and path.read_bytes() != content:
            raise ValueError("Colisión de nombre de original")
        path.write_bytes(content)
        records[key] = dict(file=name, sha256=digest, bytes=len(content), url=source_url,
                            http_status=status, fetched_at_utc=now)
    records["osm"]["query"] = query
    records["osm"]["timestamp_osm_base"] = osm.get("osm3s", {}).get("timestamp_osm_base")
    records["osm"]["license"] = "ODbL 1.0; © OpenStreetMap contributors; https://www.openstreetmap.org/copyright"
    records["senapred"]["product"] = "SENAPRED Servicios_2024 / BOMBEROS"
    records['senapred_carabineros']['product']='SENAPRED Servicios_2024 / CARABINEROS'
    manifest = dict(version=1, bbox_wgs84=config["bbox_wgs84"], fetched_at_utc=now, sources=records,
                    fallback_errors=errors)
    write_json(folder/"manifest.json", manifest)
    print(json.dumps({"originals": records, "manifest": str(folder/"manifest.json")}, ensure_ascii=False), flush=True)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path)
    args = parser.parse_args()
    config = json.loads((ROOT/"config/proyecto.json").read_text(encoding="utf-8"))
    download(config, args.output_directory)
