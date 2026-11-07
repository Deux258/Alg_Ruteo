import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
const source=readFileSync(new URL('../Sitio Web/flight-player.js',import.meta.url),'utf8');
const {sampleFlight,projectUTM,clockLabel,createRequestCoordinator,detectionProgress,resilienceSummary}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const frame=(time,x,z,phase='patrol',battery=100)=>({time_s:time,position_utm:[x,0,z],coordinates:[x,0,z],phase,battery_pct:battery});
test('Continuous interpolation follows physical seconds and clamps both ends',()=>{
 const frames=[frame(0,0,0,'takeoff'),frame(10,0,60),frame(30,100,60),frame(40,100,0,'landed')];
 assert.equal(sampleFlight(frames,5).position_utm[2],30);
 assert.equal(sampleFlight(frames,20).position_utm[0],50);
 assert.equal(sampleFlight(frames,35).phase,'landing');
 assert.equal(sampleFlight(frames,-50).time_s,0);
 assert.equal(sampleFlight(frames,99).time_s,40);
 assert.equal(sampleFlight(frames,99).ended,true);
});
test('Battery swap holds on the ground and resets at the swap endpoint',()=>{
 const frames=[frame(0,0,0,'battery_swap',25),frame(120,0,0,'takeoff',100),frame(130,0,60,'patrol',99)];
 assert.equal(sampleFlight(frames,60).battery_pct,25);
 assert.equal(sampleFlight(frames,60).position_utm[2],0);
 assert.equal(sampleFlight(frames,120).battery_pct,100);
 assert.equal(sampleFlight(frames,125).position_utm[2],30);
});
test('UTM target centering matches EPSG:32719 reference at the origin',()=>{
 const p=projectUTM([-71.65,-33.1]);
 assert.ok(Math.abs(p[0]-252691.8203693233)<.005);
 assert.ok(Math.abs(p[1]-6334502.364932891)<.005);
 assert.throws(()=>projectUTM([Infinity,0]));
});
test('Return heading remains defined at the end and stationary frames',()=>{
 const p=sampleFlight([frame(0,0,60),frame(10,100,60),frame(20,100,0,'landed')],20);
 assert.ok(p.look_ahead[0]>p.position_utm[0]);
 assert.equal(clockLabel(65.8),'01:05');
 assert.equal(sampleFlight([],0),null);
});

test('Removing a focus prevents a delayed detection response from committing',async()=>{
 const tasks=createRequestCoordinator();let release,simulation=null;
 const token=tasks.start('simulation','focus-A');
 const pending=new Promise(resolve=>{release=resolve;}).then(value=>{
   if(tasks.current(token))simulation=value;
   tasks.finish(token);
 });
 tasks.cancel('simulation');
 assert.ok(token.signal.aborted);
 release({detection:{fire:'focus-A'}});await pending;
 assert.equal(simulation,null);
});

test('Replacing a route invalidates the old FPV load without clearing another busy task',()=>{
 const tasks=createRequestCoordinator();
 const calculation=tasks.start('calculation','mission-A');
 const camera=tasks.start('fpv','route-A');
 tasks.cancel('fpv');
 assert.ok(!tasks.current(camera));assert.ok(tasks.current(calculation));
 assert.ok(tasks.pending('calculation'));
 const newer=tasks.start('fpv','route-B');
 assert.equal(tasks.finish(camera),false);assert.ok(tasks.current(newer));
});

test('Overlapping map responses only let the latest commune own the display',async()=>{
 const tasks=createRequestCoordinator();let releaseOld,releaseNew,display;
 const run=(token,setRelease)=>new Promise(resolve=>setRelease(resolve)).then(value=>{if(tasks.current(token))display=value;tasks.finish(token);});
 const first=tasks.start('map','05101'),old=run(first,resolve=>releaseOld=resolve);
 const second=tasks.start('map','05109'),newer=run(second,resolve=>releaseNew=resolve);
 releaseNew('Viña del Mar');await newer;releaseOld('Valparaíso');await old;
 assert.equal(display,'Viña del Mar');assert.ok(first.signal.aborted);assert.equal(tasks.pending('map'),false);
});

test('An incomplete report with a null timestamp is never displayed as completed',()=>{
 const detection={detected_at_s:12,reported_at_s:null,report_status:'incomplete',report_completed:false};
 assert.deepEqual(detectionProgress(detection,0),{detected:false,reported:false,incomplete:true});
 assert.deepEqual(detectionProgress(detection,200),{detected:true,reported:false,incomplete:true});
 assert.ok(detectionProgress({...detection,reported_at_s:72,report_status:'completed',report_completed:true},72).reported);
});

test('The four-way resilience tie is explicit and computation breaks it separately',()=>{
 const rows={a:{label:'A',compute_s:8},b:{label:'B',compute_s:1},c:{label:'C',compute_s:3},d:{label:'D',compute_s:2}};
 const text=resilienceSummary({routes:rows,resilience_leaders:['a','b','c','d']});
 assert.match(text,/Empate entre las cuatro técnicas/);
 assert.match(text,/Desempate por tiempo de cómputo: B \(1.00 s\)/);
 assert.match(resilienceSummary({routes:rows,resilience_leaders:['c']}),/Mayor resiliencia estimada: C/);
});
