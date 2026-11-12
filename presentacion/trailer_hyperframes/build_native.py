"""Write an independent native HTML/GSAP HyperFrames composition; no baked MP4 input."""
from pathlib import Path
import json, html, math
P=Path(__file__).resolve().parent
scenes=json.loads((P/'scenes.json').read_text())
ids=['desafio','territorio','planificar','comparar','terreno','amenazas','retorno','evidencia','cierre']
colors=['#56e7d5','#5ea5ff','#c989ff','#ff9a4d']
css='''
@font-face{font-family:TrailerTitle;src:url('assets/fonts/titles.ttf') format('truetype');font-weight:700}
@font-face{font-family:TrailerMono;src:url('assets/fonts/mono.ttf') format('truetype')}
#root{position:absolute;inset:0;color:#edf4f0;font-family:TrailerTitle;background:#060d17}
.native-ground{position:absolute;inset:0;background:radial-gradient(ellipse at 75% 40%,#102c36,#060d17 76%)}
.native-grid{position:absolute;inset:0;background-image:linear-gradient(#56e7d509 1px,transparent 1px),linear-gradient(90deg,#56e7d509 1px,transparent 1px);background-size:80px 80px}
.native-frame{position:absolute;left:110px;right:110px;top:65px;display:flex;justify-content:space-between;border-bottom:1px solid #28464e;padding-bottom:30px;font:21px TrailerMono;color:#8ba3ac}
.native-frame b{color:#56e7d5}.native-footer{position:absolute;left:110px;right:110px;bottom:65px;border-top:1px solid #28464e;padding-top:22px;display:flex;justify-content:space-between;font:19px TrailerMono;color:#8ba3ac}
.native-copy{position:absolute;left:195px;top:230px;width:750px;z-index:3}
.native-eyebrow{font:23px TrailerMono;color:#ff9a4d;margin:0 0 38px}
.native-title{font-size:83px;line-height:1.04;margin:0 0 24px;letter-spacing:-2px}
.native-subtitle{font-size:49px;line-height:1.16;margin:0;color:#56e7d5}
.native-desc{font-size:28px;line-height:1.65;color:#a6bac2;margin-top:58px}
.native-art{position:absolute;left:1020px;top:220px;width:740px;height:650px;overflow:hidden}
.native-art svg{width:100%;height:100%;overflow:visible}.native-shot{width:100%;height:100%;object-fit:cover;object-position:75% 50%}
.native-shutter{position:absolute;inset:0;background:#102e38;z-index:10;border-right:10px solid #ff9a4d}
.native-label{position:absolute;left:1020px;top:900px;color:#8ba3ac;font:17px TrailerMono}
.native-algos{list-style:none;padding:0;margin-top:48px;font-size:32px;line-height:1.85}
.native-algos li{border-left:7px solid var(--c);padding-left:23px;margin-bottom:8px}
.native-metrics{display:grid;grid-template-columns:1fr 1fr;gap:24px;height:100%}.native-metric{padding:25px;border:1px solid #285b61;background:#0d222c}
.native-metric b{display:block;color:#56e7d5;font-size:90px}.native-metric span{font:19px TrailerMono;color:#a6bac2}
.native-cta{display:inline-block;padding:25px 28px;background:#56e7d5;color:#060d17;font-size:31px;margin-top:60px;white-space:nowrap}
.native-phase{font:25px TrailerMono;color:#56e7d5;margin-top:30px}.native-status{color:#ff9a4d;font:22px TrailerMono;margin-top:30px}
'''
def drone(prefix):
 out=['<g class="flying-drone">']
 for x,y in [(-65,-37),(65,-37),(-65,37),(65,37)]:
  out.append(f'<path d="M0 0 L{x} {y}" stroke="#edf4f0" stroke-width="6"/>')
  out.append(f'<g transform="translate({x} {y})"><ellipse rx="34" ry="14" fill="#102e38" stroke="#56e7d5" stroke-width="2"/><g class="rotor"><path d="M-29 0 H29" stroke="#edf4f0" stroke-width="3"/></g></g>')
 out.append('<path d="M-26-18 L20-20 33 0 20 20 -26 18Z" fill="#183a48" stroke="#edf4f0" stroke-width="3"/><circle cx="14" r="7" fill="#ff9a4d"/></g>')
 return ''.join(out)
def graphic(i,id):
 svg=['<svg viewBox="0 0 740 650" role="img" aria-label="Animación ilustrativa de la misión">']
 if i in [0,8]:
  for r in [110,180,250]:svg.append(f'<circle class="radar-ring" cx="370" cy="320" r="{r}" stroke="#285b61" fill="none" stroke-width="2"/>')
  svg.append('<g class="radar-sweep"><path d="M370 60 A260 260 0 0 1 630 320" fill="none" stroke="#ff9a4d" stroke-width="7"/></g>')
  svg.append('<g transform="translate(370 320) scale(1.5)">'+drone(id)+'</g>')
 else:
  for j in range(22):
   pts=[]
   for k in range(30):
    x=60+k*21;y=140+j*15-35*math.sin(k*.28)*math.cos(j*.28)
    pts.append(f'{x:.2f},{y:.2f}')
   svg.append(f'<polyline points="{" ".join(pts)}" stroke="#23555d" fill="none" stroke-width="1.5"/>')
  for j in range(30):
   pts=[]
   for k in range(22):pts.append(f'{60+j*21:.2f},{140+k*15-35*math.sin(j*.28)*math.cos(k*.28):.2f}')
   svg.append(f'<polyline points="{" ".join(pts)}" stroke="#23555d" fill="none" stroke-width="1.5"/>')
  for n in range(4 if i==3 else 1):
   route=[(90,475)]
   for k in range(10):route.append((140+(k%2)*450,420-k*26+n*10))
   route.append((90,475))
   pts=' '.join(f'{x},{y}' for x,y in route)
   svg.append(f'<polyline class="native-route route-{n}" points="{pts}" stroke="{colors[n]}" fill="none" stroke-width="4" stroke-dasharray="6000"/>')
  svg.append(drone(id))
  if i==5:
   svg.append('<g class="threat"><circle cx="430" cy="255" r="46" fill="#ff515f22" stroke="#ff515f" stroke-width="3"/><circle class="threat-pulse" cx="430" cy="255" r="46" fill="none" stroke="#ff515f" stroke-width="2"/><text x="420" y="268" fill="#ff515f" font-size="38">!</text></g>')
   svg.append('<path class="reroute" d="M90 475 L65 365 L85 130 L590 186" stroke="#ff9a4d" stroke-width="6" fill="none" stroke-dasharray="1500"/>')
 svg.append('</svg>');return ''.join(svg)
details=[
 'Patrullaje aéreo. Decisiones bajo presión.',
 'Simulación de patrullaje con drones<br>en un territorio que exige anticiparse.',
 'Polígono · base · altura · viento<br>Batería · presupuesto · riesgo',
 '', 'Edificios. Vegetación. Relieve.<br>Planificación y reproducción 2D / 3D.',
 'Sortea amenazas con semilla.<br>Evalúa alternativas y factibilidad.',
 'Focos sintéticos y reserva de batería.<br>Una misión también debe volver.',
 'Mismos escenarios. Comparación trazable.<br>Resultados en JSON y GeoJSON.',
 'Patrullaje aéreo de drones en Valparaíso<br>Explora el código. Reproduce la misión.'
]
for i,(id,s) in enumerate(zip(ids,scenes)):
 dur=s['end']-s['start']; art=graphic(i,id);extra=''; label='GRÁFICA ILUSTRATIVA · NO ES UNA RUTA CALCULADA'
 if i in (4,6):
  src='simulador-terreno.png' if i==4 else 'simulador-pov.png'
  art=f'<img id="{id}-image" class="native-shot" src="assets/{src}" alt="Captura real del simulador"/>'
  label='CAPTURA REAL DEL SIMULADOR · EVIDENCIA LOCAL'
 if i==3:
  extra='<ul class="native-algos">'+''.join(f'<li style="--c:{c}">{v}</li>' for c,v in zip(colors,['Dijkstra · distancia','Dijkstra · parámetros','Gurobi','Recocido simulado']))+'</ul>'
 if i==2: extra='<p class="native-phase">60 m INICIALES / 20 % RESERVA</p>'
 if i==5:extra='<p class="native-status">AMENAZAS SINTÉTICAS / REPLANIFICAR</p>'
 if i==6:extra='<p class="native-phase">01 DETECTAR<br>02 REPORTAR<br>03 REGRESAR</p>'
 if i==7:
  art='<div class="native-metrics">'+''.join(f'<div class="native-metric"><b>{v}</b><span>{l}</span></div>' for v,l in [('1.000','ESCENARIOS COMPARTIDOS'),('4','TÉCNICAS COMPARADAS'),('JSON','MISIONES Y GEOJSON'),('SEED','SIMULACIÓN TRAZABLE')])+'</div>'
  label='PROTOCOLO EXPERIMENTAL DOCUMENTADO'
 if i==8:extra='<div class="native-cta">github.com/Deux258/Alg_Ruteo</div>'
 size=64 if i in [2,4,5,6,7] else (104 if i==8 else 83)
 script=f'''
(() => {{
 const root = document.querySelector('[data-composition-id="{id}"]:not([data-composition-src])');
 if (!root) throw new Error('Scene root missing: {id}');
 const q = (sel) => root.querySelectorAll(sel);
 const tl = gsap.timeline({{ paused:true }});
 tl.fromTo(q('.native-copy'),{{y:80,opacity:0}},{{y:0,opacity:1,duration:.65,ease:'power3.out'}},.08);
 tl.fromTo(q('.native-subtitle'),{{y:35,opacity:0}},{{y:0,opacity:1,duration:.55,ease:'power3.out'}},.28);
 tl.fromTo(q('.native-shutter'),{{x:0}},{{x:1940,duration:.42,ease:'power3.inOut'}},0);
 tl.fromTo(q('.native-art'),{{scale:.92,opacity:0}},{{scale:1,opacity:1,duration:.8,ease:'power3.out'}},.22);
 if(q('.radar-sweep').length)tl.fromTo(q('.radar-sweep'),{{rotation:0,svgOrigin:'370 320'}},{{rotation:720,svgOrigin:'370 320',duration:{dur-.2},ease:'none'}},.1);
 if(q('.rotor').length)tl.fromTo(q('.rotor'),{{rotation:0,transformOrigin:'50% 50%'}},{{rotation:2880,transformOrigin:'50% 50%',duration:{dur-.2},ease:'none'}},.1);
 if(q('.native-route').length)tl.fromTo(q('.native-route'),{{attr:{{'stroke-dashoffset':6000}}}},{{attr:{{'stroke-dashoffset':0}},duration:3.5,stagger:.22,ease:'power1.inOut'}},.8);
 if(q('.reroute').length)tl.fromTo(q('.reroute'),{{attr:{{'stroke-dashoffset':1500}}}},{{attr:{{'stroke-dashoffset':0}},duration:1.2,ease:'power2.inOut'}},3.4);
 if(q('.threat-pulse').length)tl.fromTo(q('.threat-pulse'),{{scale:.6,opacity:1,svgOrigin:'430 255'}},{{scale:2.1,opacity:0,svgOrigin:'430 255',duration:.8,repeat:7,ease:'power1.out'}},.7);
 if(q('.native-shot').length)tl.fromTo(q('.native-shot'),{{scale:1}},{{scale:1.08,duration:{dur-.4},ease:'none'}},.2);
 if(q('.native-algos li').length)tl.fromTo(q('.native-algos li'),{{x:-45,opacity:0}},{{x:0,opacity:1,duration:.4,stagger:.25}},.7);
 if(q('.native-metric').length)tl.fromTo(q('.native-metric'),{{y:35,opacity:0}},{{y:0,opacity:1,duration:.5,stagger:.2}},.5);
 if(q('.flying-drone').length && {i}!==0 && {i}!==8) {{
   const pts=[{{x:90,y:475}},{{x:140,y:420}},{{x:590,y:394}},{{x:140,y:368}},{{x:590,y:342}},{{x:140,y:316}},{{x:590,y:290}},{{x:140,y:264}},{{x:590,y:238}},{{x:140,y:212}},{{x:590,y:186}},{{x:90,y:475}}];
   tl.set(q('.flying-drone'),pts[0],0);
   pts.slice(1).forEach((p,k)=>tl.to(q('.flying-drone'),{{...p,duration:{(dur-1)/11},ease:'none'}},.5+k*{(dur-1)/11}));
 }}
 tl.to({{}},{{duration:.01}},{dur-.02});
 window.__timelines=window.__timelines||{{}};
 window.__timelines['{id}']=tl;
}})();
'''
 markup=f'''<template>
<style>{css}</style>
<div id="root" data-composition-id="{id}" data-width="1920" data-height="1080" data-duration="{dur}">
 <div class="native-ground"></div><div class="native-grid"></div>
 <div class="native-frame"><b>A / R</b><span>ALG_RUTEO / VALPARAÍSO</span><span>TRÁILER DEL PROYECTO</span></div>
 <div class="native-copy">
  <p id="{id}-eyebrow" class="native-eyebrow">{html.escape(s['label'])}</p>
  <h1 id="{id}-title" class="native-title" style="font-size:{size}px">{html.escape(s['title'])}</h1>
  <h2 id="{id}-subtitle" class="native-subtitle">{html.escape(s['subtitle'])}</h2>
  <p id="{id}-description" class="native-desc">{details[i]}</p>{extra}
 </div>
 <div id="{id}-art" class="native-art" data-layout-allow-overflow="true">{art}</div>
 <div class="native-label">{label}</div>
 <div class="native-footer"><span>SIMULACIÓN ACADÉMICA · ESCENARIOS ILUSTRATIVOS</span><span>{i+1:02d} / 09</span></div>
 <div class="native-shutter" data-layout-ignore="true"></div>
</div>
<script>{script}</script>
</template>'''
 (P/'compositions'/f'{id}.html').write_text(markup)
hosts='\n'.join(f'<div id="{id}" class="clip" data-composition-id="{id}" data-composition-src="compositions/{id}.html" data-start="{s["start"]}" data-duration="{s["end"]-s["start"]}" data-track-index="1" data-track-kind="graphics" data-width="1920" data-height="1080"></div>' for id,s in zip(ids,scenes))
(P/'index.html').write_text(f'''<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>ALG_RUTEO · HyperFrames nativo</title>
<style>html,body{{margin:0;background:#060d17;width:1920px;height:1080px;overflow:hidden}}#root{{position:relative;width:1920px;height:1080px}}#root>.clip{{position:absolute;inset:0}}</style>
<script src="assets/gsap.min.js"></script></head>
<body><div id="root" data-composition-id="main" data-start="0" data-duration="60" data-width="1920" data-height="1080">
{hosts}
<audio id="score-original" class="clip" src="assets/score-original.wav" data-start="0" data-duration="60" data-volume="1" data-track-index="2"></audio>
</div><script>window.__timelines=window.__timelines||{{}};const main=gsap.timeline({{paused:true}});main.to({{}},{{duration:60}});window.__timelines.main=main;</script></body></html>''')
print('Native HyperFrames composition written: 9 independent scenes, no MP4 input.')
