import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
const source=readFileSync(new URL('../Sitio Web/patrol-presentation.js',import.meta.url),'utf8');
const {stationVisibleInCommune,threatDisplayPosition}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));

test('A filtered 3D station matches motor id or provider_id without hiding all stations',()=>{
 const bases=[{provider_id:'104'},{provider_id:'105'}];
 assert.ok(stationVisibleInCommune({id:'104'},bases,'05101'));
 assert.ok(stationVisibleInCommune({id:104},bases,'05101'));
 assert.ok(stationVisibleInCommune({provider_id:'105'},bases,'05101'));
 assert.equal(stationVisibleInCommune({id:'106'},bases,'05101'),false);
 assert.ok(stationVisibleInCommune({id:'106'},bases,''));
});

test('A cross-commune threat uses its clipped display anchor and the local known elevation',()=>{
 const original=[100,200,300],threat={position_utm:original,display_anchor:[-71.65,-33.10]};
 const saved=structuredClone(threat);
 assert.deepEqual(threatDisplayPosition(threat,anchor=>{assert.deepEqual(anchor,[-71.65,-33.10]);return [1000,2000];},(x,y)=>{assert.deepEqual([x,y],[1000,2000]);return 45;}),[1000,2000,55]);
 assert.deepEqual(threat,saved);
 assert.equal(threatDisplayPosition(threat,()=>[1,2],()=>null),null);
 assert.equal(threatDisplayPosition(threat,()=>[1,2],()=>NaN),null);
 assert.deepEqual(threatDisplayPosition({position_utm:original},()=>{throw Error('unused');},()=>null),original);
});
