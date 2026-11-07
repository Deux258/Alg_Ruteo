import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
const source=readFileSync(new URL('../Sitio Web/patrol-editing.js',import.meta.url),'utf8');
const {normalizeTarget,circlePolygon}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));

test('A GeoJSON import validates a single closed WGS84 polygon and isolates its mutable source',()=>{
 const geometry={type:'Polygon',coordinates:[[[-71.6,-33.1],[-71.59,-33.1],[-71.59,-33.09],[-71.6,-33.1]]]};
 const imported={type:'FeatureCollection',features:[{type:'Feature',geometry}]};
 const target=normalizeTarget(imported);imported.features[0].geometry.coordinates[0][0][0]=0;
 assert.equal(target.coordinates[0][0][0],-71.6);
 assert.throws(()=>normalizeTarget({type:'FeatureCollection',features:[]}),/sola área/);
 assert.throws(()=>normalizeTarget({type:'Point',coordinates:[-71.6,-33.1]}),/Polygon/);
 assert.throws(()=>normalizeTarget({type:'Polygon',coordinates:[[[-71.6,-33.1],[-71.59,-33.1],[-71.59,-33.09],[-71.6,-33.09]]]}),/cerrados/);
});

test('A synthetic threat always has a closed finite ring, including the equator',()=>{
 for(const lat of [-33.1,0]){
  const geometry=circlePolygon(-71.6,lat,100),ring=geometry.coordinates[0];
  assert.deepEqual(ring[0],ring.at(-1));assert.equal(ring.length,65);assert.ok(normalizeTarget(geometry));
 }
 assert.throws(()=>circlePolygon(0,90,100));assert.throws(()=>circlePolygon(0,0,501));
});
