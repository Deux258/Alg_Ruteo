"""Dibuja un mapa (HTML + Leaflet) con la zona y las compañías de bomberos de m01_bases.json.
Uso: python mapa_bases.py   ->  abre datos/procesados/mapa_bases.html en el navegador (necesita internet para el mapa de fondo)."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "datos" / "procesados"
aoi = json.load(open(ROOT / "datos" / "aoi.geojson", encoding="utf-8"))
bases = json.load(open(OUT / "m01_bases.json", encoding="utf-8"))["registros"]

# centro aproximado de la zona (promedio de vértices) para describir direcciones
pts = []
for ft in aoi["features"]:
    g = ft["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    pts += [p for poly in polys for p in poly[0]]
cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
NOMBRES = ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]


def desde_centro(lon, lat):
    dx = (lon - cx) * 111.32 * math.cos(math.radians(cy))
    dy = (lat - cy) * 110.54
    ang = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    return NOMBRES[int((ang + 22.5) // 45) % 8], math.hypot(dx, dy)


print(f"{'dentro':7} {'al borde':>9}  {'desde el centro':22} nombre")
for b in sorted(bases, key=lambda r: r["distancia_aoi_km"]):
    d, km = desde_centro(b["lon"], b["lat"])
    b["_dir"], b["_km"] = d, round(km, 1)
    print(f"{'SI' if b['dentro_aoi'] else 'no':7} {b['distancia_aoi_km']:7.2f} km  {km:5.1f} km al {d:12} {b['nombre']}")

html = """<!doctype html><html><head><meta charset="utf-8"><title>Bases y zona</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>html,body,#m{height:100%;margin:0}</style></head><body><div id="m"></div><script>
const AOI=__AOI__, BASES=__BASES__;
const map=L.map('m');
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:18,attribution:'Tiles &copy; Esri'}).addTo(map);
const z=L.geoJSON(AOI,{style:{color:'#1a7f37',weight:3,fillOpacity:0.08}});
map.fitBounds(z.getBounds().pad(0.15));  // fijar la vista ANTES de agregar capas vectoriales
z.addTo(map);
BASES.forEach(b=>{
  const c=L.circleMarker([b.lat,b.lon],{radius:8,color:'#fff',weight:2,fillOpacity:1,fillColor:b.dentro_aoi?'#d1242f':(b.candidata_origen?'#fb8500':'#0969da')}).addTo(map);
  const t=document.createElement('div');
  t.textContent=b.nombre+' - '+(b.dentro_aoi?'DENTRO de la zona':b.distancia_aoi_km+' km fuera del borde');
  c.bindPopup(t);
  if(b.candidata_origen){c.bindTooltip(b.nombre,{permanent:true,direction:'top'});}
});
</script></body></html>"""
esc = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
html = html.replace("__AOI__", esc(aoi)).replace("__BASES__", esc(bases))
(OUT / "mapa_bases.html").write_text(html, encoding="utf-8")
cand = [b for b in bases if b.get("candidata_origen")]
if len(cand) > 1:
    print("\nDistancias entre candidatas a origen (km, en línea recta):")
    for a in cand:
        fila = []
        for b in cand:
            dx = (a["lon"] - b["lon"]) * 111.32 * math.cos(math.radians(cy)); dy = (a["lat"] - b["lat"]) * 110.54
            fila.append(f"{math.hypot(dx, dy):5.2f}")
        print("  ", " ".join(fila), " ", a["nombre"])
print("\nMapa:", OUT / "mapa_bases.html", " (rojo = dentro de la zona, naranja = candidata fuera de la zona, azul = otras)")