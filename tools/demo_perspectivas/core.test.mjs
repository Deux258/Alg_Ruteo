import test from 'node:test';
import assert from 'node:assert/strict';
import {shiftedZone,concatText,readyRoute} from './core.mjs';
test('long stationary shots retain the complete pause in the encoded timeline',()=>{
 const text=concatText([{file:'/tmp/a.jpg',time:100},{file:'/tmp/b.jpg',time:108.5}]);
 assert.match(text,/duration 8\.500000/);
});
test('empty capture cannot be presented as a video',()=>assert.throws(()=>concatText([])));
test('infeasible or incomplete routes are excluded from the filming choice',()=>{
 assert.equal(readyRoute({routes:{a:{status:'blocked'},b:{status:'ready',coverage:{complete:false},coordinates:[[1,1],[2,2],[3,3]]}}}),undefined);
 const r=readyRoute({routes:{a:{status:'ready',coverage:{complete:true},coordinates:[[1,1],[2,2],[3,3]]}}});assert.equal(r[0],'a');
});
test('new zone is closed, valid geographic coordinates, and does not mutate the reference',()=>{
 const original={type:'Polygon',coordinates:[[[-71.66,-33.11],[-71.65,-33.11],[-71.65,-33.10],[-71.66,-33.11]]]};const saved=JSON.stringify(original),zone=shiftedZone(original);
 assert.equal(JSON.stringify(original),saved);assert.notDeepEqual(zone,original);assert.deepEqual(zone.coordinates[0][0],zone.coordinates[0].at(-1));assert.equal(zone.coordinates[0].length,6);
 assert.ok(zone.coordinates[0].every(([x,y])=>Math.abs(x)<=180&&Math.abs(y)<=90));
});
