"""Contrato de infraestructura; IDs independientes del orden del GeoJSON."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from uuid import UUID, NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_id(key: str) -> int:
    value = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") & ((1 << 63) - 1)
    if value == 0:
        raise ValueError("Hash produce ID cero; cambiar versión del contrato")
    return value


def validate_timestamp(text: str) -> None:
    t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if t.utcoffset() is None:
        raise ValueError("Las fechas requieren zona horaria explícita")


def point(coords):
    if not isinstance(coords, list) or len(coords) != 2:
        raise ValueError("Coordenadas requieren [longitud, latitud]")
    if any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in coords):
        raise ValueError("Coordenadas no numéricas o no finitas")
    if not (-180 <= coords[0] <= 180 and -90 <= coords[1] <= 90):
        raise ValueError("Coordenadas fuera de WGS84")
    return coords


def validate_infrastructure(doc):
    from jsonschema import Draft202012Validator
    schema = json.loads((ROOT / "Infraestructura/infraestructura.schema.json").read_text())
    Draft202012Validator(schema).validate(doc)
    UUID(doc["run_id"])
    if doc["dataset_id"] != str(uuid5(UUID(doc["run_id"]), "I")):
        raise ValueError("dataset_id no corresponde al run y a I")
    validate_timestamp(doc["observed_at"])
    validate_timestamp(doc["extracted_at"])
    ids, keys = {}, set()
    for node in doc["nodes"]:
        if node["id"] in ids or node["natural_key"] in keys:
            raise ValueError("Nodos duplicados o colisión de IDs")
        if node["id"] != stable_id(node["natural_key"]):
            raise ValueError("ID de nodo no corresponde a su clave natural")
        ids[node["id"]] = point(node["geometry"]["coordinates"])
        keys.add(node["natural_key"])
    edge_ids, pairs = set(), set()
    node_keys = {n["id"]: n["natural_key"] for n in doc["nodes"]}
    for edge in doc["edges"]:
        s, t = edge["source"], edge["target"]
        if s not in ids or t not in ids or s == t:
            raise ValueError("Arco huérfano o bucle")
        key = f"arc:{node_keys[s]}->{node_keys[t]}"
        physical = "corridor:" + "|".join(sorted([node_keys[s], node_keys[t]]))
        if edge["natural_key"] != key or edge["id"] != stable_id(key) or edge["physical_key"] != physical:
            raise ValueError("Identidad de arco/corredor inconsistente")
        if edge["id"] in edge_ids or (s, t) in pairs:
            raise ValueError("Arco duplicado o paralelo")
        coords = edge["geometry"]["coordinates"]
        for c in coords:
            point(c)
        if any(abs(a - b) > 1e-9 for a, b in zip(coords[0], ids[s])) or any(
            abs(a - b) > 1e-9 for a, b in zip(coords[-1], ids[t])
        ):
            raise ValueError("Geometría del arco no coincide con origen/destino")
        if all(c == coords[0] for c in coords):
            raise ValueError("Arco de longitud cero")
        edge_ids.add(edge["id"])
        pairs.add((s, t))
    semantic = dict(nodes=doc["nodes"], edges=doc["edges"], crs=doc["crs"],
                    analysis_srid=doc["analysis_srid"], lineage=doc["lineage"],
                    observed_at=doc["observed_at"], extracted_at=doc["extracted_at"], builder="fase1-adapter-v1")
    if hashlib.sha256(canonical(semantic)).hexdigest() != doc["input_hash"]:
        raise ValueError("El contenido no corresponde a input_hash")
    return doc


def prepare_snapshot(config: dict, run_id: str | None = None):
    if config["analysis_srid"] != 32719:
        raise ValueError("El contrato versión 1 requiere EPSG:32719")
    folder = ROOT / config["snapshot_directory"]
    paths = {k: folder / v for k, v in {"nodes": "nodos.geojson", "edges": "aristas.geojson"}.items()}
    raw = {k: json.loads(p.read_text()) for k, p in paths.items()}
    for value in raw.values():
        if value.get("type") != "FeatureCollection":
            raise ValueError("Se esperaba FeatureCollection")
        crs = value.get("crs", {}).get("properties", {}).get("name", "EPSG:4326")
        if crs not in ("EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84", "urn:ogc:def:crs:EPSG::4326"):
            raise ValueError("El adaptador de fase 1 requiere WGS84")
    nodes, old_to_new, node_keys = [], {}, {}
    for f in raw["nodes"]["features"]:
        p, geom = f["properties"], f["geometry"]
        if geom["type"] != "Point":
            raise ValueError("Nodo no es Point")
        coords = point(geom["coordinates"])
        west,south,east,north = config["bbox_wgs84"]
        if not (west-1e-9 <= coords[0] <= east+1e-9 and south-1e-9 <= coords[1] <= north+1e-9):
            raise ValueError("Nodo fuera del AOI configurado; el snapshot no corresponde al proyecto")
        old = p["id"]
        if isinstance(old, bool) or not isinstance(old, int) or old in old_to_new:
            raise ValueError("ID legado inválido o duplicado")
        kind = p["tipo"]
        if kind == "base_candidata":
            if p.get("id_fuente") is None:
                raise ValueError("Base candidata sin ID del proveedor")
            key = f"base:S1:{p['id_fuente']}"
        elif kind == "vigilancia":
            # Coordenadas de la malla original: identidad estable aunque cambie el orden.
            for v in [p["x"], p["y"]]:
                if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v):
                    raise ValueError("Coordenada UTM de malla inválida")
            key = f"grid:32719:{p['x']:.3f}:{p['y']:.3f}"
        else:
            raise ValueError("Tipo de nodo no reconocido")
        ident = stable_id(key)
        old_to_new[old] = ident
        node_keys[ident] = key
        nodes.append(dict(id=ident, natural_key=key, kind=kind,
                          source_record_id=str(p["id_fuente"]) if p.get("id_fuente") is not None else None,
                          geometry={"type": "Point", "coordinates": coords}))
    edges = []
    for f in raw["edges"]["features"]:
        p, geom = f["properties"], f["geometry"]
        s, t = old_to_new[p["origen"]], old_to_new[p["destino"]]
        key = f"arc:{node_keys[s]}->{node_keys[t]}"
        physical = "corridor:" + "|".join(sorted([node_keys[s], node_keys[t]]))
        edges.append(dict(id=stable_id(key), natural_key=key, source=s, target=t,
                          physical_key=physical, geometry=geom))
    nodes.sort(key=lambda n: n["id"])
    edges.sort(key=lambda e: e["id"])
    lineage = {k: {"file": str(p.relative_to(ROOT)), "sha256": sha256(p)} for k, p in paths.items()}
    lineage["configuration_sha256"] = hashlib.sha256(canonical(config)).hexdigest()
    observed = config["snapshot_observed_at"]
    semantic = dict(nodes=nodes, edges=edges, crs="EPSG:4326", analysis_srid=config["analysis_srid"],
                    lineage=lineage, observed_at=observed, extracted_at=observed, builder="fase1-adapter-v1")
    input_hash = hashlib.sha256(canonical(semantic)).hexdigest()
    rid = str(UUID(run_id)) if run_id else str(uuid5(NAMESPACE_URL, "udp:infra-v1:" + input_hash))
    doc = dict(schema_version="1.0", run_id=rid,
               dataset_id=str(uuid5(UUID(rid), "I")), dataset_key="I", source_id="DERIVED_GRAPH",
               observed_at=observed, extracted_at=observed, crs="EPSG:4326", analysis_srid=32719,
               input_hash=input_hash, lineage=lineage,
               extraction_mode="snapshot", nodes=nodes, edges=edges)
    return validate_infrastructure(doc)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)
