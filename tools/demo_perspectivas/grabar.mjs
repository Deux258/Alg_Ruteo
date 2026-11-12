import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {spawnSync} from 'node:child_process';
import {shiftedZone,sameGeometry,concatText,readyRoute} from './core.mjs';
const REPO=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const args=process.argv.slice(2);
if(args.includes('--help')){console.log('Uso: node tools/demo_perspectivas/grabar.mjs [--url http://127.0.0.1:18083] [--chrome /ruta/chrome] [--no-fire] [--headed]\nSalida: presentacion/demo_perspectivas/renders/<fecha>/Demo_dron_perspectivas.mp4\nSe usa el backend real. No instala, publica ni modifica código del simulador.');process.exit(0);}
const option=(key,def)=>{const i=args.indexOf(key);if(i<0)return def;if(!args[i+1]||args[i+1].startsWith('--'))throw new Error(`Falta valor de ${key}`);return args[i+1];};
const configured=option('--url',null), requestedChrome=option('--chrome',process.env.CHROME_PATH);
const stamp=new Date().toISOString().replaceAll(':','-').replaceAll('.','-');
const OUT=path.join(REPO,'presentacion/demo_perspectivas/renders',stamp);await fs.mkdir(OUT,{recursive:true});
const report={successful:false,output:OUT,recording:'actual application UI with small chapter labels',new_zone:true,nominal_perspectives:true,fire_probability_implemented:false,clips:[],attempts:[],browser_errors:[]};
const write=async(name,data)=>fs.writeFile(path.join(OUT,name),JSON.stringify(data,null,2));
const require=createRequire(import.meta.url);let pp;
for(const base of [path.join(REPO,'presentacion/trailer_hyperframes'),REPO]){try{pp=(await import(pathToFileURL(require.resolve('puppeteer-core',{paths:[base]})).href)).default;break;}catch{}}
if(!pp)throw new Error('Falta puppeteer-core. Instálalo desde npm o usa las dependencias del proyecto de Hyperframes.');
function run(bin,a){const r=spawnSync(bin,a,{encoding:'utf8',maxBuffer:10*1024*1024});if(r.status!==0)throw new Error(`${bin}: ${r.stderr||r.error?.message||r.status}`);return r.stdout;}
run('ffmpeg',['-version']);run('ffprobe',['-version']);
let chrome=requestedChrome;
for(const p of ['/opt/google/chrome/chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium','/usr/bin/chromium-browser',...(await fs.readdir(path.join(process.env.HOME,'.cache/ms-playwright')).catch(()=>[])).filter(n=>n.startsWith('chromium-')).map(n=>path.join(process.env.HOME,'.cache/ms-playwright',n,'chrome-linux64/chrome'))]){if(chrome)break;try{await fs.access(p);chrome=p;}catch{}}
if(!chrome)throw new Error('No se encontró Chrome. Indica --chrome /ruta/al/ejecutable.');
let browser,page,active;
const hold=ms=>new Promise(r=>setTimeout(r,ms));
try{
 browser=await pp.launch({executablePath:chrome,headless:!args.includes('--headed'),args:['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader','--disable-dev-shm-usage'],defaultViewport:{width:1920,height:1080,deviceScaleFactor:1}});
 page=await browser.newPage();page.setDefaultTimeout(45000);page.setDefaultNavigationTimeout(60000);
 page.on('pageerror',e=>report.browser_errors.push(e.message));
 let url;
 for(const u of configured?[configured]:['http://127.0.0.1:18083','http://127.0.0.1:8080']){try{const r=await page.goto(u,{waitUntil:'domcontentloaded',timeout:15000});if(r?.ok()&&await page.$('#draw')){url=u;break;}}catch{}}
 if(!url)throw new Error('La web no responde. Inicia ./main en otra terminal y pasa su URL con --url.');
 report.url=url;
 await page.waitForFunction(()=>document.querySelector('#base')?.options.length>0&&document.querySelector('#geography-status')?.getAttribute('aria-busy')==='false'&&!document.querySelector('#export-geography')?.disabled,{timeout:300000});
 async function api(p,body){return page.evaluate(async({p,body})=>{const r=await fetch(p,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const v=await r.json();if(!r.ok())throw new Error(JSON.stringify(v));return v;},{p,body});}
 const map=await api('/api/aereo/patrullaje/mapa?view=summary');await write('mapa_referencia.json',{demo_polygon:map.demo_polygon,origin:map.default_origin,profile:map.profile});
 const waitReady=()=>page.waitForFunction(()=>!document.querySelector('#calculate').disabled,{timeout:300000});
 const fill=async(sel,value)=>{await page.locator(sel).fill(String(value));await page.$eval(sel,e=>e.dispatchEvent(new Event('change',{bubbles:true})));};
 const snap=async(name)=>page.screenshot({path:path.join(OUT,name+'.png')});
 await page.select('#base-style','local');await fill('#seed',20261112);await page.select('#route-mode','comparison');
 await page.evaluate(()=>{const el=document.createElement('div');el.id='recording-chapter';Object.assign(el.style,{position:'fixed',top:'16px',left:'620px',maxWidth:'900px',padding:'10px 18px',background:'#102431',color:'#e7f4ef',font:'600 24px system-ui',zIndex:'99999',pointerEvents:'none'});document.body.append(el);});
 const label=async text=>page.$eval('#recording-chapter',(el,t)=>{el.textContent=t;},text);
 async function clipStart(name,title){
  if(active)throw new Error('La toma anterior sigue abierta');
  await label(title);const dir=path.join(OUT,'raw',name);await fs.mkdir(dir,{recursive:true});
  const cdp=await page.createCDPSession();const rows=[];let pending=Promise.resolve(),accept=true,counter=0;
  const handler=ev=>{cdp.send('Page.screencastFrameAck',{sessionId:ev.sessionId}).catch(()=>{});if(!accept)return;const n=counter++,file=path.join(dir,`${String(n).padStart(6,'0')}.jpg`);rows.push({file,time:Number.isFinite(ev.metadata.timestamp)?ev.metadata.timestamp:performance.now()/1000});pending=pending.then(()=>fs.writeFile(file,Buffer.from(ev.data,'base64')));};
  cdp.on('Page.screencastFrame',handler);await cdp.send('Page.startScreencast',{format:'jpeg',quality:85,maxWidth:1920,maxHeight:1080,everyNthFrame:1});
  active={name,dir,rows,cdp,handler,started:performance.now()/1000,stopAccept:()=>{accept=false;},pending:()=>pending};
  // Force an initial compositor update; the browser's cursor is rendered separately below.
  await page.mouse.move(1500,900);console.log('Grabando:',title);
 }
 async function clipStop(){
  const a=active;if(!a)return;
  await hold(200);await a.cdp.send('Page.stopScreencast');a.stopAccept();await a.pending();if(a.rows.length){const tail=path.join(a.dir,'last.jpg');await page.screenshot({path:tail,type:'jpeg',quality:85});a.rows.push({file:tail,time:Math.max(a.rows.at(-1).time+.0167,a.rows[0].time+performance.now()/1000-a.started)});}a.cdp.off('Page.screencastFrame',a.handler);await a.cdp.detach();active=null;
  const list=path.join(a.dir,'frames.ffconcat');await fs.writeFile(list,concatText(a.rows));const output=path.join(OUT,a.name+'.mp4');
  run('ffmpeg',['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',list,'-vf','scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2','-r','30','-c:v','libx264','-crf','20','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',output]);
  report.clips.push({name:a.name,file:output,frames:a.rows.length,duration_s:Number(run('ffprobe',['-v','error','-show_entries','format=duration','-of','csv=p=0',output]).trim())});await write('manifest.json',report);
 }
 async function click(sel){await page.waitForSelector(sel,{visible:true});await page.waitForFunction(s=>{const e=document.querySelector(s);return e&&!e.disabled;},{timeout:300000},sel);await page.$eval(sel,e=>e.scrollIntoView({block:'center',behavior:'instant'}));await hold(180);await page.click(sel);}
 async function seek(time){await page.$eval('#seek',(e,t)=>{e.value=t;e.dispatchEvent(new Event('input',{bubbles:true}));},time);await hold(350);}
 const is3d=()=>page.$eval('#terrain',e=>!e.hidden&&getComputedStyle(e).display!=='none');
 async function view(three){if(await is3d()!==three)await click('#view-toggle');if(three)await page.waitForFunction(()=>Number(document.querySelector('#terrain').dataset.sceneVertices)>10000,{timeout:180000});}
 async function calculate(){await waitReady();const reply=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/aereo/patrullaje'&&r.request().method()==='POST',{timeout:420000});await click('#calculate');const r=await reply;let v=await r.json();if(!r.ok())throw new Error(JSON.stringify(v));if(v.resources?.exportar?.url){v=await api(v.resources.exportar.url);v=v.result||v;}if(readyRoute(v))await page.waitForFunction(()=>!document.querySelector('#export').disabled,{timeout:180000});else await page.waitForFunction(()=>!document.querySelector('#calculate').disabled,{timeout:180000});return v;}
 // Import only for positioning, then visibly draw the final target by mouse.
 // Each rejected mission is kept in the manifest rather than silently called successful.
 let result,chosen;
 for(const [index,offset] of [[120,170],[-160,110],[180,-130]].entries()){
  const zone=shiftedZone(map.demo_polygon,...offset),file=path.join(OUT,`encuadre-${index+1}.geojson`);await fs.writeFile(file,JSON.stringify(zone));
  const input=await page.$('#import');await input.uploadFile(file);await page.waitForFunction(()=>!document.querySelector('#focus-target').disabled);await hold(1500);
  await clipStart(`01-zona-${index+1}`,'01 · Dibujar una zona nueva: marcar vértices y cerrar polígono');
  await click('#draw');const el=await page.$('#map'),box=await el.boundingBox();
  if(!box||box.width<400)throw new Error('Mapa sin tamaño suficiente para dibujar.');
  for(const [x,y] of [[.40,.36],[.57,.32],[.64,.51],[.53,.66],[.36,.57]]){await page.mouse.move(box.x+box.width*x,box.y+box.height*y,{steps:30});await page.mouse.click(box.x+box.width*x,box.y+box.height*y);await hold(900);}
  await page.waitForFunction(()=>document.querySelector('#draw-tools').dataset.vertices==='5');await click('#finish');await hold(2200);await snap(`zona-${index+1}`);await clipStop();
  await page.select('#route-mode','comparison');result=await calculate();chosen=readyRoute(result);
  const record={index:index+1,status:result.status,sha256:result.sha256,ready_methods:Object.entries(result.routes).filter(([,r])=>r.status==='ready').map(([k])=>k),polygon:result.target_polygon};report.attempts.push(record);await write(`resultado-${index+1}.json`,result);
  if(chosen&&!sameGeometry(result.target_polygon,map.demo_polygon)){report.selected_attempt=index+1;break;}chosen=null;
 }
 if(!chosen)throw new Error('Las zonas nuevas no produjeron misión viable. Se conservaron intentos y capturas; no se exportó un video engañoso.');
 await write('solicitud_nueva.json',result.request);await write('zona_recorrida.geojson',result.target_polygon);
 await page.select('#chosen',chosen[0]);await click('#show-selected');await click('#focus-target');
 const nominalReply=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/simular')&&r.request().method()==='POST',{timeout:180000});await click('#play');const nominal=await(await nominalReply).json();await page.waitForFunction(()=>!document.querySelector('#pause').disabled,{timeout:180000});await click('#pause');
 if(nominal.status!=='completed'||nominal.timeline?.at(-1)?.phase!=='landed')throw new Error('La misión nominal no termina en aterrizaje.');
 await write('simulacion_nominal.json',nominal);report.nominal_status=nominal.status;report.nominal_end=nominal.timeline.at(-1);report.result_sha256=result.sha256;report.method=chosen[0];
 await page.select('#speed','1');
 const phase=nominal.timeline.find(f=>f.phase==='patrol'&&f.time_s>12)?.time_s??15;
 await seek(phase);await clipStart('02-ruta-2d','02 · Ruta calculada sobre la zona nueva · reproducción 1×');await click('#play');await hold(14000);await click('#pause');await snap('ruta-2d');await clipStop();
 await seek(Math.min(nominal.time_s*.33,nominal.time_s-20));await clipStart('03-seguimiento-2d','03 · Seguir dron en el mapa · reproducción 1×');if(!await page.$eval('#follow-drone',e=>e.checked))await click('#follow-drone');await click('#play');await hold(15000);await click('#pause');await snap('seguimiento-2d');await clipStop();
 await view(true);await click('#terrain-mission');await clipStart('04-orbita-3d','04 · Terreno 3D y ruta · órbita de cámara');
 const terrain=await page.$('#terrain'),b=await terrain.boundingBox();await page.mouse.move(b.x+b.width*.55,b.y+b.height*.5);await page.mouse.down();await page.mouse.move(b.x+b.width*.72,b.y+b.height*.57,{steps:100});await page.mouse.up();await hold(5000);await snap('orbita-3d');await clipStop();
 await seek(nominal.time_s*.4);await clipStart('05-seguimiento-3d','05 · Seguimiento del dron sobre el relieve');if(!await page.$eval('#follow-drone',e=>e.checked))await click('#follow-drone');await click('#play');await hold(16000);await click('#pause');await snap('seguimiento-3d');await clipStop();
 await seek(nominal.time_s*.5);await clipStart('06-pov','06 · POV: cámara a bordo, rumbo, altura y batería');await click('#drone-view');await page.waitForFunction(()=>document.querySelector('#terrain').dataset.camera==='drone');await click('#play');await hold(18000);await click('#pause');await snap('pov');report.pov_verified=await page.$eval('#fpv-hud',e=>!e.hidden);await clipStop();
 await clipStart('07-pov-mirada','07 · Mirar desde el dron: giro lateral de la cámara');const bb=await(await page.$('#terrain')).boundingBox();await page.mouse.move(bb.x+bb.width*.55,bb.y+bb.height*.45);await page.mouse.down();await page.mouse.move(bb.x+bb.width*.62,bb.y+bb.height*.5,{steps:75});await page.mouse.up();await click('#play');await hold(10000);await click('#pause');await clipStop();
 await click('#focus-target');await view(false);await seek(nominal.time_s*.7);await clipStart('08-regreso','08 · Vista general: final del recorrido y aterrizaje');await page.select('#speed','20');await click('#play');await page.waitForFunction(()=>document.querySelector('#player').dataset.phase==='landed',{timeout:90000});await hold(3500);await snap('aterrizaje');await clipStop();
 if(!args.includes('--no-fire')){
  await click('#focus-target');await clipStart('09-foco','09 · Foco sintético: colocación, detección, reporte y regreso · 20×');await click('#fire');const mb=await(await page.$('#map')).boundingBox();await page.mouse.click(mb.x+mb.width*.5,mb.y+mb.height*.5);await hold(1500);
  const reply=page.waitForResponse(r=>new URL(r.url()).pathname.endsWith('/simular')&&r.request().method()==='POST',{timeout:180000});await click('#replay-nominal');const fireSim=await(await reply).json();await write('simulacion_foco.json',fireSim);
  await page.waitForFunction(()=>!document.querySelector('#play').disabled,{timeout:180000});await click('#play');
  await page.waitForFunction(()=>document.querySelector('#player').dataset.phase==='landed',{timeout:120000});await page.$eval('#log',e=>e.scrollIntoView({block:'center',behavior:'instant'}));await hold(4500);await snap('foco-reportado');report.fire_status=fireSim.status;report.detection=fireSim.detection;await clipStop();if(fireSim.status!=='detected_and_returned'){report.fire_warning='El foco no completó detección, reporte y regreso; toma 09 excluida. Revisar simulacion_foco.json.';console.warn(report.fire_warning);}
 }
 // Select only the successful drawn-zone take; failed attempts remain as evidence.
 const selected=report.clips.filter(c=>(!c.name.startsWith('01-')||c.name===`01-zona-${report.selected_attempt}`)&&(c.name!=='09-foco'||report.fire_status==='detected_and_returned'));
 report.included_clips=selected.map(c=>c.name);
 const list=path.join(OUT,'clips.ffconcat');await fs.writeFile(list,'ffconcat version 1.0\n'+selected.map(c=>`file '${c.file.replaceAll("'","'\\''")}'\n`).join(''));
 const output=path.join(OUT,'Demo_dron_perspectivas.mp4');run('ffmpeg',['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',list,'-c','copy','-movflags','+faststart',output]);
 const probe=JSON.parse(run('ffprobe',['-v','error','-show_streams','-show_format','-of','json',output]));await write('ffprobe.json',probe);run('ffmpeg',['-hide_banner','-v','error','-i',output,'-f','null','-']);
 report.successful=Boolean(report.pov_verified&&selected.length>=8);report.final_video=output;report.duration_s=Number(probe.format.duration);await write('manifest.json',report);
 console.log('\nVIDEO LOCAL:',output);console.log('Duración:',report.duration_s.toFixed(1),'s. Sin audio ni subida a servicios externos.');
}catch(error){report.error=error.message;console.error('\nNo se completó la grabación:',error.message);try{if(active)await active.cdp.send('Page.stopScreencast');if(page)await page.screenshot({path:path.join(OUT,'error.png')});}catch{}await write('manifest.json',report);process.exitCode=1;}
finally{if(browser)await browser.close();}
