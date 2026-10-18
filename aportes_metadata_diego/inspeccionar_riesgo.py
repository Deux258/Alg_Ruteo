"""Inspecciona un ráster de riesgo (GeoTIFF) y lo compara con la zona de estudio.
Uso:  python inspeccionar_riesgo.py "datos/raw/05_Valparaiso/5_riesgo.tif" [--crs EPSG:32719]
--crs solo si el archivo NO trae sistema de coordenadas (un .tfw por sí solo no lo define).
Si el ráster tiene pocas clases, escribe datos/procesados/riesgo_clases.geojson (un polígono por clase)."""
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import geometry_mask, shapes
from rasterio.mask import mask
from rasterio.warp import transform_bounds, transform_geom
from shapely.geometry import mapping, shape
from shapely.ops import unary_union
from core.dbf import leer_dbf, resumen_xml

ROOT = Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("tif")
ap.add_argument("--crs", default=None, help="CRS a asumir si el archivo no lo trae, p. ej. EPSG:32719")
args = ap.parse_args()

aoi = json.load(open(ROOT / "datos" / "aoi.geojson", encoding="utf-8"))
aoi_geom = unary_union([shape(f["geometry"]) for f in aoi["features"]])

etiquetas = {}
vat = Path(str(args.tif) + ".vat.dbf")
if vat.exists():
    campos, filas = leer_dbf(vat)
    print(f"Tabla de atributos del ráster ({vat.name}), campos: {campos}")
    for fila in filas:
        print("  ", fila)
    txt = [c for c in campos if c.lower() not in ("value", "count", "oid", "rowid") and filas and isinstance(filas[0][c], str)]
    if txt and "Value" in campos:
        etiquetas = {f["Value"]: f[txt[0]] for f in filas}
xml = Path(str(args.tif) + ".xml")
if xml.exists():
    desc = resumen_xml(xml)
    if desc:
        print(f"\nMetadatos ({xml.name}):")
        print("\n".join(desc))
print()

with rasterio.open(args.tif) as src:
    print(f"Archivo: {args.tif}")
    print(f"Tamaño: {src.width} x {src.height} píxeles, {src.count} banda(s), tipo {src.dtypes[0]}, nodata = {src.nodata}")
    crs = src.crs or (rasterio.crs.CRS.from_string(args.crs) if args.crs else None)
    print(f"CRS: {src.crs}" + ("" if src.crs else "   <-- el archivo NO trae CRS"))
    if crs is None:
        raise SystemExit("\nSin CRS no se puede ubicar el ráster. Vuelve a ejecutar con --crs EPSG:XXXX "
                         "(revisa el .prj o los metadatos de la fuente; no lo adivines).")
    print(f"Resolución del píxel: {src.res[0]:.6g} x {src.res[1]:.6g} (unidades del CRS)")
    b = transform_bounds(crs, "EPSG:4326", *src.bounds)
    print(f"Cobertura en lon/lat: {b[0]:.3f}..{b[2]:.3f} , {b[1]:.3f}..{b[3]:.3f}")

    geom = transform_geom("EPSG:4326", crs, mapping(aoi_geom))
    try:
        datos, tr = mask(src, [geom], crop=True, filled=False)
    except ValueError:
        raise SystemExit("\nLa zona NO intersecta el ráster: este archivo no sirve para tu zona (o el CRS es incorrecto).")
    a = datos[0]
    dentro = geometry_mask([geom], out_shape=a.shape, transform=tr, invert=True)
    validos = ~np.ma.getmaskarray(a) & dentro
    print(f"\nPíxeles dentro de la zona: {int(dentro.sum())} | con dato: {int(validos.sum())} "
          f"({100*validos.sum()/max(dentro.sum(),1):.0f}% de la zona)")
    vals = np.asarray(a.data)[validos]
    if vals.size == 0:
        raise SystemExit("Sin datos válidos dentro de la zona.")
    clases, cuentas = np.unique(vals, return_counts=True)
    if len(clases) <= 30:
        print("\nValores presentes en la zona:")
        for c, n in zip(clases, cuentas):
            print(f"   valor {c:>8}: {n:8d} píxeles  ({100*n/vals.size:5.1f}%)")
    else:
        print(f"\n{len(clases)} valores distintos (parece continuo): min {vals.min()}, "
              f"mediana {np.median(vals)}, media {vals.mean():.3f}, máx {vals.max()}")

    if len(clases) <= 20 and np.issubdtype(vals.dtype, np.number):
        por_clase = {}
        for g, v in shapes(np.asarray(a.data).astype("float64"), mask=validos, transform=tr):
            por_clase.setdefault(v, []).append(shape(transform_geom(crs, "EPSG:4326", g)))
        feats = []
        for v, gs in sorted(por_clase.items()):
            u = unary_union(gs).intersection(aoi_geom).simplify(0.00003)
            feats.append({"type": "Feature", "geometry": mapping(u), "properties": {
                "clase": float(v), "etiqueta": etiquetas.get(int(v)) if float(v).is_integer() else None, "pixeles": int(cuentas[list(clases).index(v)])}})
        out = ROOT / "datos" / "procesados" / "riesgo_clases.geojson"
        out.parent.mkdir(parents=True, exist_ok=True)
        json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w", encoding="utf-8"))
        print(f"\n[ok] {out}  ({len(feats)} clases como polígonos)")
    else:
        print("\nNo se vectorizó (demasiadas clases o no numérico).")