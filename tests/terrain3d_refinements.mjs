import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
const source=readFileSync(new URL('../Sitio Web/terrain3d.js',import.meta.url),'utf8');
const {TerrainView,terrainGridColors,terrainLighting,routeArrowAnchors,projectTerrainPoint}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
globalThis.ResizeObserver=class{observe(){}disconnect(){}};
globalThis.devicePixelRatio=1;
const mesh={width:2,height:2,x:[0,100],y:[0,100],origin_utm:[100,200],elevations:[20,20,20,20]};
function canvas(){
 const uploads=[],deleted=[],uniforms=[],listeners=[];let id=0;
 const gl=new Proxy({uploads,deleted,uniforms,bufferData:(...v)=>uploads.push(v),deleteBuffer:b=>deleted.push(b),
  createBuffer:()=>({id:++id}),getShaderParameter:()=>true,getProgramParameter:()=>true,
  getAttribLocation:(_,name)=>({position:0,color:1,routeStart:0,routeEnd:1,corner:2})[name],getUniformLocation:(_,name)=>name,
  uniform1f:(name,value)=>uniforms.push([name,value])},
  {get:(t,k)=>k in t?t[k]:k.toUpperCase()===k?1:()=>({})});
 return{gl,dataset:{},clientWidth:400,clientHeight:300,hidden:false,getContext:()=>gl,addEventListener:(...v)=>listeners.push(v),listeners};
}
test('Terrain lighting shares vertex colors across faces, preserves XYZ/palette, and never bridges NoData',()=>{
 const tilted={...mesh,elevations:[0,10,0,10]},snapshot=JSON.stringify(tilted),colors=terrainGridColors(tilted);
 const shade=.68+.32*Math.abs((.035+.87)/Math.hypot(.1,1));
 assert.ok(Math.abs(colors[0][0]-Math.round(.59*shade*255)/255)<1e-12);
 assert.equal(JSON.stringify(tilted),snapshot);
 assert.equal(colors[0][2],colors[1][2]);
 const categorical=terrainLighting(tilted).colorsAt([50,25,5],[.2,.5,.3]);
 assert.ok(Math.abs(categorical[0]-Math.round(.2*shade*255)/255)<1e-12);
 assert.equal(terrainGridColors({...mesh,elevations:[20,null,20,20]})[1],null);
 const view=new TerrainView(canvas(),{...mesh,elevations:[20,20,20,null]},null);
 assert.equal(view.terrain.count,3);view.dispose();
});
test('Screen ribbons keep 6/3px widths and direction anchors on canonical geometry without per-frame rebuilds',()=>{
 const points=[[100,200,50],[350,200,75]],anchors=routeArrowAnchors(points);
 assert.deepEqual(anchors.map(a=>a.distance_m),[25,100,200]);
 assert.equal(anchors[1].position[2],60);assert.ok(anchors[1].ahead[0]>anchors[1].position[0]);
 assert.deepEqual(routeArrowAnchors([[0,0,0],[0,0,50]]),[]);
 const c=canvas(),view=new TerrainView(c,mesh,null);
 view.setRoutes([{points,color:[0,1,0],selected:true},{points,color:[1,0,0],selected:false},{points,color:[1,1,0],target:true}]);
 assert.deepEqual(view.routeBuffers.filter(i=>!i.symbol).map(i=>i.widthPx),[6,3,3]);
 assert.equal(view.canvas.dataset.routeArrows,'6');
 const buffers=view.routeBuffers.map(i=>i.buffer),before=c.gl.uploads.length;
 for(let i=0;i<20;i++)view.setFlightPose([150+i,250,60],[160+i,250,60]);
 assert.deepEqual(view.routeBuffers.map(i=>i.buffer),buffers);
 assert.equal(c.gl.uploads.length-before,20); // headless fallback marker only
 view.dispose();assert.ok(buffers.every(b=>c.gl.deleted.includes(b)));
});
test('CPU labels mirror orbital/POV projection and hide behind-camera or offscreen points',()=>{
 const orbit={origin:[0,0],center:[0,0,0],yaw:0,pitch:Math.PI/2,scale:.01,aspect:4/3,width:400,height:300,fpv:false};
 assert.deepEqual(projectTerrainPoint([0,0,0],orbit),{x:200,y:150,depth:0,visible:true});
 assert.equal(projectTerrainPoint([1000,0,0],orbit).visible,false);
 const fpv={...orbit,fpv:true,eye:[0,0,0],forward:[1,0,0],right:[0,-1,0],up:[0,0,1],focal:1};
 assert.equal(projectTerrainPoint([-10,0,0],fpv).visible,false);
 const center=projectTerrainPoint([10,0,0],fpv);assert.equal(center.x,200);assert.equal(center.y,150);assert.equal(center.visible,true);
});
test('Button and wheel zoom share bounded orbit/FOV behavior',()=>{
 const c=canvas(),view=new TerrainView(c,mesh,null);
 view.zoom=2;view.zoomBy(1.25);assert.equal(view.zoom,2.5);
 view.zoomBy(1e10);assert.equal(view.zoom,60);view.zoomBy(1e-20);assert.equal(view.zoom,.3);
 view.setFirstPerson(true);view.fov=70;view.zoomBy(1.25);assert.equal(view.fov,56);
 view.zoomBy(1e10);assert.equal(view.fov,40);view.zoomBy(1e-20);assert.equal(view.fov,100);
 const wheel=c.listeners.find(([name])=>name==='wheel')[1];view.fov=70;
 wheel({deltaY:-Math.log(1.25)*1000,preventDefault(){}});assert.ok(Math.abs(view.fov-56)<1e-12);
 view.dispose();
});
test('Recognizable annotations retain labels, move the drone without rebuilding DOM/buffers, hide in 2D and release on dispose',()=>{
 class Element{
  constructor(){this.style={};this.dataset={};this.children=[];this.writes=0;this.textContent='';}
  append(...items){for(const item of items){item.parentElement=this;this.children.push(item);}}
  setAttribute(){}
  set innerHTML(value){this.html=value;this.writes++;}
  get innerHTML(){return this.html;}
  remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this);}
 }
 const oldDocument=globalThis.document;globalThis.document={createElement:()=>new Element()};
 const c=canvas();c.parentElement=new Element();const view=new TerrainView(c,mesh,null);
 try{
  view.setAnnotations([{id:'base:1',kind:'base',position_utm:[150,250,20],label:'Base <norte>',selected:true}]);
  const base=view.annotationNodes.get('base:1');assert.equal(base.label.textContent,'Base <norte>');assert.equal(base.element.hidden,false);
  const longName='Base de salida en el sector norte de Valparaiso con nombre completo';
  view.setAnnotations([{id:'base:1',kind:'base',position_utm:[150,250,30],label:longName,selected:true},{id:'base:2',kind:'base',position_utm:[150,250,30],label:'Base secundaria'},{id:'station:1',kind:'station',position_utm:[150,250,33],label:'Recarga'}]);
  view.setFlightPose([150,250,30],[150,260,30]);const drone=view.annotationNodes.get('__flight_drone');
  assert.equal(base.label.textContent,longName);assert.equal(base.label.style.whiteSpace,'normal');assert.equal(base.label.style.textOverflow,'clip');
  assert.equal(base.label.hidden,false);assert.equal(drone.label.hidden,false);
  assert.equal(view.annotationNodes.get('base:2').label.hidden,true);
  const badge=view.annotationNodes.get('station:1');assert.equal(badge.element.dataset.badge,'true');assert.equal(badge.icon.style.width,'20px');
  const writes=drone.icon.writes,uploads=c.gl.uploads.length;
  for(let i=0;i<10;i++)view.setFlightPose([150+i,250,30],[150+i,260,30]);
  assert.equal(drone.icon.writes,writes);assert.equal(c.gl.uploads.length,uploads);
  view.setFirstPerson(true);assert.equal(drone.element.hidden,true);
  c.hidden=true;view.draw();assert.equal(view.annotationLayer.hidden,true);
  view.setAnnotations([]);assert.equal(view.annotationNodes.has('base:1'),false);
  view.dispose();assert.equal(c.parentElement.children.length,0);
 }finally{globalThis.document=oldDocument;}
});
