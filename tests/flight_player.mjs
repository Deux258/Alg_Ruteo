import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
const source=readFileSync(new URL('../Sitio Web/flight-player.js',import.meta.url),'utf8');
const {sampleFlight,projectUTM,clockLabel}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
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
