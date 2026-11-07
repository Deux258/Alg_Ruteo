import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
const source=readFileSync(new URL('../Sitio Web/terrain3d.js',import.meta.url),'utf8');
const {TerrainView}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
globalThis.ResizeObserver=class{observe(){} disconnect(){this.disconnected=true;}};
globalThis.devicePixelRatio=1;
globalThis.location={href:'http://localhost/',origin:'http://localhost'};
const mesh={width:2,height:2,x:[0,10],y:[0,10],origin_utm:[100,200],elevations:[null,null,null,null]};
function canvas(){
 const uploads=[],deleted=[],listeners=[];let id=0;
 const gl=new Proxy({uploads,deleted,bufferData:(...args)=>uploads.push(args),deleteBuffer:b=>deleted.push(b),
  createBuffer:()=>({id:++id}),getShaderParameter:()=>true,getProgramParameter:()=>true,getAttribLocation:()=>0},
  {get:(target,key)=>key in target?target[key]:key.toUpperCase()===key?1:()=>({})});
 return {gl,dataset:{},clientWidth:400,clientHeight:300,getContext:()=>gl,addEventListener:(...args)=>listeners.push(args),listeners};
}
test('NoData makes no ground triangles; marker frames reuse static route buffers and dispose frees them',()=>{
 const c=canvas(),view=new TerrainView(c,mesh,null);
 assert.equal(view.terrain.count,0);
 view.setRoutes([{points:[[100,200,20],[110,210,20]],color:[1,0,0]}]);
 const route=view.routeBuffers[0].buffer,uploads=c.gl.uploads.length;
 for(let i=0;i<20;i++)view.setMarker([100+i,200,20]);
 assert.equal(c.gl.uploads.length-uploads,20); // only the one moving marker
 assert.equal(view.routeBuffers[0].buffer,route);
 view.dispose();assert.ok(c.gl.deleted.includes(route));assert.ok(view.events.signal.aborted);
 assert.ok(c.listeners.every(l=>l[2].signal.aborted));
});
test('Typed scene verifies immutable bytes, preserves camera, and releases replaced buffers',async()=>{
 const c=canvas(),view=new TerrainView(c,mesh,null),oldFetch=globalThis.fetch;
 const positions=new Float32Array([0,0,20,1,0,20,0,1,20]),colors=new Uint8Array(9).fill(128);
 const spec=async(data,dtype,url)=>({url,components:3,dtype,sha256:Buffer.from(await webcrypto.subtle.digest('SHA-256',data)).toString('hex')});
 const scene={sha256:'fixture',typed_assets:{schema_version:'typed-scene-1',crs:'EPSG:32719',origin_utm:[100,200],groups:{buildings:[{count:3,mode:'triangles',positions:await spec(positions,'float32-le','/p'),colors:await spec(colors,'uint8','/c')}]}}};
 globalThis.fetch=async url=>({ok:true,arrayBuffer:async()=>url.pathname==='/p'?positions.buffer:colors.buffer});
 try{
  view.yaw=.8;await view.setScene(scene);const first=view.groups.buildings[0];
  view.setLayer('buildings',false);await view.setScene(scene);
  assert.equal(view.yaw,.8);assert.equal(view.visibility.buildings,false);assert.ok(c.gl.deleted.includes(first.buffer));assert.ok(c.gl.deleted.includes(first.colors));
  const controller=new AbortController();controller.abort();
  await assert.rejects(view.setScene(scene,{signal:controller.signal}),{name:'AbortError'});
  assert.equal(view.groups.buildings[0].count,3);
  scene.typed_assets.groups.buildings[0].positions.sha256='0'.repeat(64);
  await assert.rejects(view.setScene(scene),/Integridad/);
 }finally{globalThis.fetch=oldFetch;view.dispose();}
});
