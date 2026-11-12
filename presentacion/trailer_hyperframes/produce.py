"""Original offline motion design and sound. No remote assets or credentials.
Exports a YouTube master and editable HyperFrames composition posters/WAAPI.
The official HyperFrames CLI must be used separately to validate native export.
"""
from PIL import Image, ImageDraw, ImageFont, ImageOps
import math, json, random, wave, array, subprocess, pathlib, argparse, os
P=pathlib.Path(__file__).resolve().parent
REPO=P.parents[1]
W,H,FPS,DURATION=1920,1080,30,60
BG=(6,13,23); WHITE=(237,244,240); MUTE=(139,163,172)
CYAN=(86,231,213); ORANGE=(255,154,77); RED=(255,81,95)
COLORS=[CYAN,(94,165,255),(201,137,255),ORANGE]
FONT=str(P/'assets/fonts/titles.ttf')
MONO=str(P/'assets/fonts/mono.ttf')
fonts={}
def font(n,mono=False):
 k=(n,mono)
 if k not in fonts: fonts[k]=ImageFont.truetype(MONO if mono else FONT,n)
 return fonts[k]
def clamp(x): return max(0,min(1,x))
def ease(x): return 1-(1-clamp(x))**3
def mix(a,b,t): return tuple(int(a[i]+(b[i]-a[i])*t) for i in range(3))
def text(d,pos,s,size=36,color=WHITE,mono=False): d.text(pos,s,font=font(size,mono),fill=color)
def line(d,points,color=CYAN,width=3): d.line(points,fill=color,width=width,joint='curve')
SCENES=[
 (0,4,'CADA SEGUNDO','DEFINE UNA MISIÓN.','01 / EL DESAFÍO'),
 (4,10,'VALPARAÍSO.','DESDE OTRA ALTURA.','02 / EL TERRITORIO'),
 (10,16,'TRAZA EL OBJETIVO.','DEFINE LOS LÍMITES.','03 / PLANIFICAR'),
 (16,24,'4 TÉCNICAS.','UNA MISIÓN.','04 / COMPARAR'),
 (24,32,'EL TERRENO','CAMBIA LAS REGLAS.','05 / EXPLORAR EN 3D'),
 (32,40,'EL RIESGO APARECE.','LA RUTA RESPONDE.','06 / SIMULAR Y REPLANIFICAR'),
 (40,46,'DETECTAR. REPORTAR.','REGRESAR.','07 / CERRAR EL CIRCUITO'),
 (46,52,'NO SOLO SE VE.','SE PUEDE REPRODUCIR.','08 / EVIDENCIA'),
 (52,60,'ALG_RUTEO','CADA RUTA ES UNA DECISIÓN.','09 / EXPLORA EL PROYECTO')]
random.seed(258)
STARS=[(random.randrange(W),random.randrange(H),random.uniform(.2,1)) for _ in range(100)]
# Use real AOI coordinates. The decorative elevation below is explicitly illustrative.
aoi=json.loads((P/'assets/area-estudio.geojson').read_text())['features'][0]['geometry']['coordinates'][0][0]
xs=[c[0] for c in aoi]; ys=[c[1] for c in aoi]
MAP=[((x-min(xs))/(max(xs)-min(xs)),(max(ys)-y)/(max(ys)-min(ys))) for x,y,*_ in aoi]
shots={
4:('assets/simulador-terreno.png',(390,88,1500,840)),
6:('assets/simulador-pov.png',None)}
IMAGES={}
for k,(f,crop) in shots.items():
 im=Image.open(P/f).convert('RGB')
 if crop: im=im.crop(crop)
 IMAGES[k]=im
# Cache background; typography and animated shapes remain independently drawn.
BASE=Image.new('RGB',(W,H),BG); bd=ImageDraw.Draw(BASE)
for y in range(H):
 c=mix((9,23,34),BG,y/H); bd.line((0,y,W,y),fill=c)
for x in range(0,W,80): bd.line((x,0,x,H),fill=(12,30,41))
for y in range(0,H,80): bd.line((0,y,W,y),fill=(12,30,41))
for x,y,b in STARS: bd.ellipse((x,y,x+2,y+2),fill=mix(BG,MUTE,b*.4))
def drone(d,cx,cy,scale,t):
 def p(x,y): return (cx+x*scale,cy+y*scale)
 for x,y in [(-95,-55),(95,-55),(-95,55),(95,55)]:
  line(d,[p(0,0),p(x,y)],WHITE,max(2,int(scale*5)))
  r=39*scale; px,py=p(x,y)
  d.ellipse((px-r,py-r*.38,px+r,py+r*.38),outline=CYAN,width=max(2,int(2*scale)))
  a=t*70+x; line(d,[p(x-36*math.cos(a),y-13*math.sin(a)),p(x+36*math.cos(a),y+13*math.sin(a))],CYAN,3)
 d.polygon([p(-32,-20),p(22,-25),p(39,0),p(22,25),p(-32,20)],fill=(20,48,59),outline=WHITE,width=3)
 d.ellipse((*p(6,-9),*p(24,9)),fill=ORANGE)
def terrain(d,t,risk=False,compare=False):
 # Projected design mesh. AOI boundary comes from actual project GeoJSON.
 theta=-.22+.05*math.sin(t*.2)
 def project(x,y,z=0):
  x,y=x-.5,y-.5
  return (1330+570*(x*math.cos(theta)-y*math.sin(theta)),540+300*(x*math.sin(theta)+y*math.cos(theta))-z)
 def z(x,y): return 35+48*math.sin(x*9)*math.cos(y*7)+22*math.sin(y*16+x*3)
 for j in range(23):
  y=j/22; line(d,[project(i/30,y,z(i/30,y)) for i in range(31)],(28,72,77),2)
 for i in range(31):
  x=i/30; line(d,[project(x,j/22,z(x,j/22)) for j in range(23)],(28,72,77),2)
 boundary=[project(x,y,18) for x,y in MAP]
 if len(boundary)>2: line(d,boundary+[boundary[0]],mix(BG,CYAN,.65),3)
 paths=[]
 for n,col in enumerate(COLORS if compare else [CYAN]):
  path=[project(.15,.83,95)]
  for k in range(10): path.append(project(.18+(k%2)*.65,.78-k*.063+n*.012,95+12*math.sin(k+n)))
  path.append(project(.15,.83,95)); paths.append(path)
  progress=clamp((t-1-n*.35)/3); count=max(2,int(progress*len(path)))
  line(d,path[:count],col,4)
  for x,y in path[:count]: d.ellipse((x-4,y-4,x+4,y+4),fill=WHITE)
 path=paths[0]; u=(t*.17)%1*(len(path)-1); k=int(u); f=u-k
 x=path[k][0]*(1-f)+path[k+1][0]*f; y=path[k][1]*(1-f)+path[k+1][1]*f
 drone(d,x,y,.35,t)
 if risk:
  cx,cy=project(.6,.43,100)
  for j in range(3):
   r=20+((t*40+j*35)%110); d.ellipse((cx-r,cy-r*.45,cx+r,cy+r*.45),outline=mix(BG,RED,1-r/155),width=3)
  text(d,(cx+30,cy-50),'AMENAZA SINTÉTICA',19,RED,True)
  if t>3:
   line(d,[path[0],project(.03,.65,110),project(.05,.15,110),path[-3]],ORANGE,6)
   text(d,(1100,840),'↳ REPLANIFICACIÓN',26,ORANGE,True)
 return project

def frame(t):
 idx=next((i for i,(a,b,*_) in enumerate(SCENES) if a<=t<b),len(SCENES)-1)
 a,b,title,sub,kicker=SCENES[idx]; q=t-a; dur=b-a
 im=BASE.copy(); d=ImageDraw.Draw(im)
 # Floating reference lines.
 scan=int((t*90)%W); d.line((scan,150,scan,920),fill=(17,43,51),width=2)
 if idx in (1,2,3,5): terrain(d,q,risk=idx==5,compare=idx==3)
 if idx==0:
  cx,cy=1430,545
  for r in (145,225,310):
   d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=(29,68,74),width=2)
  d.arc((cx-310,cy-310,cx+310,cy+310),int(t*85),int(t*85+100),fill=ORANGE,width=7)
  drone(d,cx,cy+10*math.sin(t),1.7,t)
  text(d,(1275,905),'MISIÓN / EN ESPERA',22,ORANGE,True)
 if idx in IMAGES:
  box=(970,230,1835,840) if idx==4 else (970,245,1835,850)
  w,h=box[2]-box[0],box[3]-box[1]
  img=ImageOps.fit(IMAGES[idx],(int(w*(1+.045*q/dur)),int(h*(1+.045*q/dur))))
  img=ImageOps.fit(img,(w,h),centering=(.5+.06*q/dur,.5))
  im.paste(img,box[:2]); d=ImageDraw.Draw(im)
  d.rectangle((box[0]-2,box[1]-2,box[2]+2,box[3]+2),outline=CYAN,width=2)
  for xx,yy,sx,sy in [(box[0],box[1],1,1),(box[2],box[1],-1,1),(box[0],box[3],1,-1),(box[2],box[3],-1,-1)]:
   line(d,[(xx,yy+25*sy),(xx,yy),(xx+25*sx,yy)],WHITE,5)
  text(d,(box[0],box[3]+20),'CAPTURA REAL DEL SIMULADOR · EVIDENCIA LOCAL',18,MUTE,True)
 if idx==7:
  for j,(n,label) in enumerate([('1.000','ESCENARIOS COMPARTIDOS'),('4','TÉCNICAS COMPARADAS'),('JSON','MISIONES Y GEOJSON')]):
   x=970+(j%2)*440; y=295+(j//2)*270
   d.rectangle((x,y,x+400,y+220),fill=(13,34,44),outline=(36,77,82),width=2)
   text(d,(x+28,y+16),n,92,CYAN);text(d,(x+28,y+146),label,18,MUTE,True)
  text(d,(970,855),'SEMILLAS · PARÁMETROS · TRAZABILIDAD',22,WHITE,True)
 if idx==8:
  # Expanding emblem and clean end card.
  cx,cy=1510,485
  for j in range(5):
   r=100+j*40+10*math.sin(q*.5+j)
   d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=mix(BG,CYAN,.15+j*.12),width=2)
  drone(d,cx,cy,1.4,q)
 # Left typography. Short 2-line sets, plenty of title-safe space.
 enter=ease(q/.65); yoff=int((1-enter)*65)
 text(d,(150,230+yoff),kicker,24,ORANGE,True)
 sizes={0:88,1:100,2:66,3:100,4:64,5:63,6:61,7:68,8:118}
 text(d,(143,312+yoff),title,sizes[idx],WHITE)
 text(d,(146,428+yoff),sub,47 if idx==4 else (54 if idx not in (0,1,8) else 60),CYAN if idx!=0 else ORANGE)
 details={
 0:['Patrullaje aéreo. Decisiones bajo presión.'],
 1:['Simulación de patrullaje con drones','en un territorio que exige anticiparse.'],
 2:['Polígono · base · altura · viento','Batería · presupuesto · riesgo'],
 3:[],4:['Edificios. Vegetación. Relieve.','Planificación y reproducción 2D / 3D.'],
 5:['Sortea amenazas con semilla.','Evalúa alternativas y factibilidad.'],
 6:['Focos sintéticos y reserva de batería.','Una misión también debe volver.'],
 7:['Mismos escenarios. Comparación trazable.','Misiones y resultados exportables.'],
 8:['Patrullaje aéreo de drones en Valparaíso','Explora el código. Reproduce la misión.']}
 for j,s in enumerate(details[idx]): text(d,(150,565+j*45),s,27,MUTE)
 if idx==1: text(d,(150,790),'33° S  /  71° O',24,ORANGE,True);text(d,(150,832),'CONTORNO DEL ÁREA DE ESTUDIO',18,MUTE,True)
 if idx==2:
  for j,(label,value) in enumerate([('ALTURA INICIAL','60 m'),('RESERVA','20 %'),('BASE','A ELECCIÓN')]):
   x=150+j*215;d.line((x,730,x+175,730),fill=CYAN,width=3)
   text(d,(x,751),label,17,MUTE,True);text(d,(x,788),value,30,WHITE)
 if idx==3:
  for j,s in enumerate(['Dijkstra · distancia','Dijkstra · parámetros','Gurobi','Recocido simulado']):
   y=570+j*70; d.rectangle((150,y+10,160,y+42),fill=COLORS[j]);text(d,(185,y),s,34,WHITE)
 if idx==5:
  state='AMENAZA ACTIVADA' if q<3 else 'ALTERNATIVAS BAJO EVALUACIÓN'
  d.rectangle((150,745,750,805),outline=RED if q<3 else ORANGE,width=2)
  text(d,(175,760),state,22,RED if q<3 else ORANGE,True)
 if idx==6:
  phases=['01  DETECCIÓN','02  REPORTE','03  RETORNO']
  for j,s in enumerate(phases):text(d,(150,720+j*49),s,26,CYAN if q>j*1.4 else (52,79,87),True)
 if idx==8:
  d.rectangle((150,735,1020,819),fill=CYAN)
  text(d,(181,752),'github.com/Deux258/Alg_Ruteo',35,BG)
  text(d,(150,861),'POSTGIS   /   PGROUTING   /   OPTIMIZACIÓN',21,MUTE,True)
 # Persistent editorial frame.
 d.line((100,126,1820,126),fill=(42,70,79),width=2)
 text(d,(105,70),'A / R',30,CYAN);text(d,(230,78),'ALG_RUTEO  /  VALPARAÍSO',21,WHITE,True)
 text(d,(1430,78),'TRÁILER DEL PROYECTO',19,MUTE,True)
 d.line((100,958,1820,958),fill=(42,70,79),width=2)
 d.line((100,958,100+1720*min(t/60,1),958),fill=CYAN,width=3)
 text(d,(105,986),'SIMULACIÓN ACADÉMICA  ·  ESCENARIOS ILUSTRATIVOS',19,MUTE,True)
 text(d,(1620,983),f'{idx+1:02d} / 09',23,CYAN,True)
 # Cinematic diagonal shutters on every cut; no blank title frames.
 if q<.28 and idx>0:
  p=1-ease(q/.28); off=int(W*p)
  d.polygon([(W-off-150,0),(W,0),(W,H),(W-off-500,H)],fill=(12,35,43))
  line(d,[(W-off-150,0),(W-off-500,H)],ORANGE,8)
 # Fade in/out.
 alpha=min(clamp(t/.35),clamp((60-t)/.65))
 if alpha<1: im=Image.blend(Image.new('RGB',(W,H),BG),im,alpha)
 return im

def audio():
 """60 s original synth score: 120 BPM, D minor, kick, pulse bass, hats, risers, impacts."""
 sr=48000; N=sr*60; buf=array.array('f',[0])*N
 def add(start,dur,fn,gain=1):
  start=int(start*sr); length=min(int(dur*sr),N-start)
  for k in range(max(0,length)):
   tt=k/sr; buf[start+k]+=gain*fn(tt,k)
 rng=random.Random(258)
 # Four minor chords, rhythmic harmonic pads.
 chords=[[146.832,174.614,220],[130.813,164.814,195.998],[116.541,146.832,174.614],[130.813,164.814,195.998]]
 for bar in range(15):
  tones=chords[bar%4]
  add(bar*4,4,lambda t,k,tones=tones: math.sin(math.pi*min(t/4,1))*.06*sum(math.sin(2*math.pi*f*t) for f in tones))
 for beat in range(120):
  at=beat*.5
  if at>=4 and at<58:
   add(at,.36,lambda t,k: .64*math.sin(2*math.pi*(48*t+12*(1-math.exp(-t*36))))*math.exp(-t*16))
   f=chords[(beat//8)%4][0]/2
   add(at+.02,.43,lambda t,k,f=f: (.23*math.sin(2*math.pi*f*t)+.06*math.sin(4*math.pi*f*t))*math.exp(-t*8)*min(t/.01,1))
   if beat%2: add(at,.14,lambda t,k: rng.uniform(-1,1)*math.exp(-t*35)*.2)
  if 10<=at<58:
   for off in [0,.25]:add(at+off,.05,lambda t,k: rng.uniform(-1,1)*math.exp(-t*95)*.095)
  if 16<=at<58:
   notes=[293.665,349.228,440,523.251,440,349.228,261.626,349.228]
   nf=notes[beat%8]
   add(at+.25,.4,lambda t,k,nf=nf: math.sin(2*math.pi*nf*t)*math.exp(-t*10)*.095)
 for cut in [0,4,10,16,24,32,40,46,52]:
  add(cut,1.5,lambda t,k: math.sin(2*math.pi*(34*t+4*(1-math.exp(-t*9))))*math.exp(-t*4)*.5)
  if cut:
   add(cut-.65,.65,lambda t,k: rng.uniform(-1,1)*(t/.65)**2*.24)
   add(cut,.55,lambda t,k: rng.uniform(-1,1)*math.exp(-t*9)*.14)
 # Radar pips and the simulated incident alert.
 for at in [1,2,3,33,33.5,34,41,42,43]:add(at,.17,lambda t,k: math.sin(2*math.pi*880*t)*math.sin(math.pi*t/.17)*.13)
 out=array.array('h')
 for k,x in enumerate(buf):
  t=k/sr; env=min(1,t/.3,max(0,(60-t)/1.8));v=int(math.tanh(x*1.15)*env*28000)
  # Subtle stereo spread via tiny deterministic delayed reflection.
  r=int(math.tanh((x*.92+(buf[k-731]*.08 if k>=731 else 0))*1.15)*env*28000)
  out.extend((v,r))
 with wave.open(str(P/'assets/score-original.wav'),'wb') as w:w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes(out.tobytes())
 print('Original score complete',flush=True)

def assets():
 for i,(a,b,*_) in enumerate(SCENES):frame(a+min(2.5,(b-a)/2)).save(P/f'assets/scene-{i+1:02d}.jpg',quality=95)
 thumbnail=BASE.copy(); td=ImageDraw.Draw(thumbnail)
 text(td,(145,125),'ALG_RUTEO / VALPARAÍSO',34,CYAN,True)
 text(td,(130,280),'CADA RUTA',140,WHITE)
 text(td,(130,450),'ES UNA',140,WHITE)
 text(td,(130,620),'DECISIÓN.',140,CYAN)
 drone(td,1470,505,2.0,0.15)
 text(td,(145,920),'DRONES  ×  OPTIMIZACIÓN  ×  SIMULACIÓN',30,ORANGE,True)
 thumbnail.resize((1280,720),Image.Resampling.LANCZOS).save(P/'renders/miniatura-youtube.png')
 thumbs=[]
 for i,(a,b,*_) in enumerate(SCENES):
  thumb=frame(a+2).resize((640,360)); thumbs.append(thumb)
 sheet=Image.new('RGB',(1920,1080));
 for i,thumb in enumerate(thumbs):sheet.paste(thumb,((i%3)*640,(i//3)*360))
 sheet.save(P/'renders/storyboard.jpg',quality=92)
 (P/'scenes.json').write_text(json.dumps([dict(start=a,end=b,title=c,subtitle=d,label=e) for a,b,c,d,e in SCENES],ensure_ascii=False,indent=2))

def render():
 target=P/'renders/Alg_Ruteo_Trailer_YouTube_1080p.mp4'
 cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-i',str(P/'assets/score-original.wav'),'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','320k','-ar','48000','-movflags','+faststart','-t','60','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',str(target)]
 proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
 try:
  for n in range(FPS*DURATION):
   proc.stdin.write(frame(n/FPS).tobytes())
   if n%150==0: print(f'Render {n//FPS:02d}/60 seconds',flush=True)
 finally: proc.stdin.close()
 if proc.wait():raise RuntimeError('FFmpeg failed')
 master=P/'assets/master.mp4'
 if not master.exists(): os.link(target,master)
 print(str(target),flush=True)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--assets',action='store_true');ap.add_argument('--audio',action='store_true');ap.add_argument('--render',action='store_true');args=ap.parse_args()
 if args.assets:assets()
 if args.audio:audio()
 if args.render:render()
