"""M2 - Catastro de recursos vegetacionales y uso de la tierra, Región de Valparaíso (CONAF 2019,
publicado por CIREN en ArcGIS REST) -> m02_cobertura.json
Capa: REGIÓN VALPARAÍSO (CONAF 2019), id 5 del servicio RECURSOS_VEGETACIONALES_Y_USOS_DE_LA_TIERRA_1.
Uso: python Metadata/m02_cobertura_et.py"""
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # raíz del repo: permite 'from core.util import ...'
from shapely.geometry import shape, mapping
from core.util import load_aoi, arcgis_query, write_json

URL = os.environ.get("URL_COBERTURA",
    "https://esri.ciren.cl/server/rest/services/RECURSOS_VEGETACIONALES_Y_USOS_DE_LA_TIERRA_1/FeatureServer/5")
ANIO = 2019  # año del catastro según el nombre de la capa
CAMPOS = ["uso_tierra", "uso", "subuso", "estructura", "cobertura", "altura",
          "tipo_fores", "subtipofor", "nom_com", "superf_ha"]


def main():
    aoi = load_aoi()
    feats = arcgis_query(URL, aoi.bounds, out_fields=",".join(CAMPOS))
    registros = []
    for i, f in enumerate(feats):
        if not f.get("geometry"):
            continue
        g = shape(f["geometry"])
        if not g.is_valid:
            g = g.buffer(0)
        recorte = g.intersection(aoi)
        if recorte.is_empty:
            continue
        p = f.get("properties", {})
        registros.append({
            "id": f.get("id", i),
            "uso_tierra": p.get("uso_tierra"),
            "uso": p.get("uso"),
            "subuso": p.get("subuso"),
            "estructura": p.get("estructura"),
            "cobertura": p.get("cobertura"),
            "altura": p.get("altura"),
            "tipo_forestal": p.get("tipo_fores"),
            "subtipo_forestal": p.get("subtipofor"),
            "comuna": p.get("nom_com"),
            "superficie_original_ha": p.get("superf_ha"),
            "anio": ANIO,
            "geometry": mapping(recorte),
        })
    print(f"Dentro de la caja envolvente: {len(feats)} | con recorte en el AOI: {len(registros)}")
    write_json("m02_cobertura.json", "m02_cobertura", "CONAF 2019 vía CIREN (ArcGIS REST)",
               URL, registros, {"descargados_bbox": len(feats),
                                "nota": "Geometrías recortadas al AOI; superficie_original_ha es la del polígono completo, no la recortada."})


if __name__ == "__main__":
    main()
