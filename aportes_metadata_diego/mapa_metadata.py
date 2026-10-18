"""Mapa HTML (Leaflet) con la zona, la cobertura del suelo (M2) por polígonos y las bases de Bomberos (M1).
Uso: python mapa_metadata.py   ->  abre datos/procesados/mapa_metadata.html en el navegador (necesita internet para el fondo).
Reemplaza a mapa_bases.py: hace lo mismo y suma la cobertura."""
import collections
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "datos" / "procesados"
aoi = json.load(open(ROOT / "datos" / "aoi.geojson", encoding="utf-8"))
bases = json.load(open(OUT / "m01_bases.json", encoding="utf-8"))["registros"]
# Respaldo: si el JSON es de una versión anterior (sin 'candidata_origen'), se decide por nombre.
SELECCIONADAS = ["decima de valparaiso", "decima quinta de valparaiso", "decima segunda de valparaiso", "decima tercera de valparaiso"]
_n = lambda t: (t or "").lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u").strip()
for b in bases:
    if "candidata_origen" not in b:
        b["candidata_origen"] = bool(b["dentro_aoi"] or _n(b["nombre"]) in SELECCIONADAS)
cob_path = OUT / "m02_cobertura.json"
cobertura = json.load(open(cob_path, encoding="utf-8"))["registros"] if cob_path.exists() else []
if not cobertura:
    print("AVISO: no hay m02_cobertura.json; el mapa saldrá sin polígonos de cobertura.")

riesgo_path = OUT / "riesgo_clases.geojson"
riesgo = json.load(open(riesgo_path, encoding="utf-8")) if riesgo_path.exists() else {"type": "FeatureCollection", "features": []}
# Etiquetas SUPUESTAS (el .vat.dbf del ráster no las trae): 4 coincide con la cifra publicada por CONAF de 'muy alta' en la región.
ETIQ_RIESGO = {0: "0 (sin categoría)", 1: "1 (Bajo?)", 2: "2 (Medio?)", 3: "3 (Alto?)", 4: "4 (Muy alto?)"}
for ft in riesgo["features"]:
    ft["properties"]["texto"] = ETIQ_RIESGO.get(int(ft["properties"]["clase"]), str(ft["properties"]["clase"]))

# --- resumen por consola (bases)
pts = []
for ft in aoi["features"]:
    g = ft["geometry"]
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    pts += [p for poly in polys for p in poly[0]]
cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
NOMBRES = ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]


def km(a, b):
    dx = (a["lon"] - b["lon"]) * 111.32 * math.cos(math.radians(cy))
    return math.hypot(dx, (a["lat"] - b["lat"]) * 110.54)


print(f"{'dentro':7} {'al borde':>9}  {'desde el centro':22} nombre")
for b in sorted(bases, key=lambda r: r["distancia_aoi_km"]):
    k = km(b, {"lon": cx, "lat": cy})
    ang = (math.degrees(math.atan2((b["lon"] - cx) * math.cos(math.radians(cy)), b["lat"] - cy)) + 360) % 360
    print(f"{'SI' if b['dentro_aoi'] else 'no':7} {b['distancia_aoi_km']:7.2f} km  {k:5.1f} km al {NOMBRES[int((ang + 22.5) // 45) % 8]:12} {b['nombre']}")
bandas = [(1, "hasta 1 km"), (3, "1 a 3 km"), (5, "3 a 5 km"), (10, "5 a 10 km"), (1e9, "más de 10 km")]
print("\nCompañías por distancia al borde de la zona (0 = dentro):")
previo = -1
for lim, nom in bandas:
    n = sum(1 for b in bases if (b["distancia_aoi_km"] > previo or (previo < 0 and b["distancia_aoi_km"] >= 0)) and b["distancia_aoi_km"] <= lim)
    print(f"   {nom:14} {n}")
    previo = lim
cand = [b for b in bases if b.get("candidata_origen")]
if len(cand) > 1:
    print("\nDistancias entre candidatas a origen (km, en línea recta):")
    for a in cand:
        print("  ", " ".join(f"{km(a, b):5.2f}" for b in cand), " ", a["nombre"])

# --- cobertura: colores y conteo por uso
COLORES = {"Bosques": "#2da44e", "Áreas Urbanas e Industriales": "#6e7781",
           "Praderas y Matorrales": "#d4a72c", "Áreas Desprovistas de Vegetación": "#bf8700",
           "Terrenos Agrícolas": "#fb8500", "Cuerpos de Agua": "#0969da"}
cuenta = collections.Counter(r.get("uso") or "Sin dato" for r in cobertura)
leyenda = [{"uso": u, "n": n, "color": COLORES.get(u, "#8250df")} for u, n in cuenta.most_common()]
cob_gj = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": r["geometry"], "properties": {
        "uso": r.get("uso") or "Sin dato", "subuso": r.get("subuso"), "estructura": r.get("estructura"),
        "color": COLORES.get(r.get("uso"), "#8250df")}} for r in cobertura]}

html = """<!doctype html><html><head><meta charset="utf-8"><title>Zona, cobertura y bases</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>html,body,#m{height:100%;margin:0}
.leyenda{background:#fff;padding:8px 10px;border-radius:6px;font:12px sans-serif;line-height:1.5;box-shadow:0 1px 5px rgba(0,0,0,.4)}
.leyenda i{display:inline-block;width:12px;height:12px;margin-right:6px;vertical-align:middle;border:1px solid #555}
.leyenda .pt{border-radius:50%}</style></head><body><div id="m"></div><script>
const AOI=__AOI__, BASES=__BASES__, COB=__COB__, LEY=__LEY__, RIESGO=__RIESGO__;
const map=L.map('m',{preferCanvas:true});
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:18,attribution:'Tiles &copy; Esri'}).addTo(map);
const z=L.geoJSON(AOI,{style:{color:'#000',weight:3,fill:false}});
const bb=z.getBounds(); BASES.forEach(b=>bb.extend([b.lat,b.lon]));
map.fitBounds(bb.pad(0.05));  // fijar la vista ANTES de agregar capas vectoriales
const txt=(...l)=>{const d=document.createElement('div');d.innerHTML='';l.filter(Boolean).forEach((s,i)=>{const e=document.createElement(i?'div':'b');e.textContent=s;d.appendChild(e);});return d;};
const cob=L.geoJSON(COB,{style:f=>({color:'#111',weight:1.8,opacity:0.95,fillColor:f.properties.color,fillOpacity:0.45}),
  onEachFeature:(f,l)=>{l.on('mouseover',()=>l.setStyle({weight:3.5,fillOpacity:0.75}));l.on('mouseout',()=>cob.resetStyle(l));l.bindPopup(txt(f.properties.uso,f.properties.subuso&&('Subuso: '+f.properties.subuso),f.properties.estructura&&('Estructura: '+f.properties.estructura)));}}).addTo(map);
z.addTo(map);
const bg=L.layerGroup().addTo(map);
BASES.forEach(b=>{
  const c=L.circleMarker([b.lat,b.lon],{radius:8,color:'#fff',weight:2,fillOpacity:1,fillColor:b.dentro_aoi?'#d1242f':(b.candidata_origen?'#fb8500':'#0969da')}).addTo(bg);
  c.bindPopup(txt(b.nombre,b.dentro_aoi?'DENTRO de la zona':(b.distancia_aoi_km+' km fuera del borde')));
  if(b.candidata_origen){c.bindTooltip(b.nombre,{permanent:true,direction:'top'});}
});
const COLR=['#8c959f','#2da4a8','#f2e04a','#fb8500','#d1242f'];
const rie=L.geoJSON(RIESGO,{style:f=>({color:'#111',weight:0.5,fillColor:COLR[f.properties.clase],fillOpacity:0.6}),
  onEachFeature:(f,l)=>l.bindPopup(txt('Riesgo CONAF 2024',f.properties.texto))});
const capas={'Cobertura del suelo (M2)':cob,'Bases de Bomberos (M1)':bg,'Zona':z};
if(RIESGO.features.length){capas['Riesgo CONAF 2024 (clases 0-4)']=rie;}
L.control.layers(null,capas,{collapsed:false}).addTo(map);
const lg=L.control({position:'bottomleft'});
lg.onAdd=()=>{const d=L.DomUtil.create('div','leyenda');
  const t=document.createElement('b');t.textContent='Cobertura (n.º de polígonos)';d.appendChild(t);
  LEY.forEach(x=>{const r=document.createElement('div');const i=document.createElement('i');i.style.background=x.color;r.appendChild(i);r.appendChild(document.createTextNode(x.uso+' ('+x.n+')'));d.appendChild(r);});
  [['#d1242f','Base dentro de la zona'],['#fb8500','Base candidata fuera de la zona'],['#0969da','Otras compañías a ≤ 1,1 km']].forEach(([c,n])=>{const r=document.createElement('div');const i=document.createElement('i');i.className='pt';i.style.background=c;r.appendChild(i);r.appendChild(document.createTextNode(n));d.appendChild(r);});
  return d;};
lg.addTo(map);
</script></body></html>"""
esc = lambda o: json.dumps(o, ensure_ascii=False).replace("</", "<\\/")
html = (html.replace("__AOI__", esc(aoi)).replace("__BASES__", esc(bases))
            .replace("__RIESGO__", esc(riesgo)).replace("__COB__", esc(cob_gj)).replace("__LEY__", esc(leyenda)))
salida = OUT / "mapa_metadata.html"
salida.write_text(html, encoding="utf-8")
print(f"\nMapa: {salida}  ({salida.stat().st_size/1e6:.1f} MB)")