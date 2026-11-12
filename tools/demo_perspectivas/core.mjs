export function shiftedZone(demo,dx=120,dy=170){
 if(!demo?.coordinates?.[0])throw new Error('El mapa no tiene un área de referencia.');
 const r=demo.coordinates[0],lon=r.reduce((s,p)=>s+p[0],0)/r.length,lat=r.reduce((s,p)=>s+p[1],0)/r.length;
 const x=lon+dx/(111320*Math.cos(lat*Math.PI/180)),y=lat+dy/111320;
 const pts=[[-100,-75],[60,-95],[115,5],[40,90],[-110,55]].map(([a,b])=>[x+a/(111320*Math.cos(lat*Math.PI/180)),y+b/111320]);
 return {type:'Polygon',coordinates:[[...pts,pts[0]]]};
}
export function sameGeometry(a,b){return JSON.stringify(a)===JSON.stringify(b);}
export function concatText(rows){
 if(!rows.length)throw new Error('La grabación no produjo fotogramas.');
 const quote=s=>s.replaceAll("'","'\\''");
 return 'ffconcat version 1.0\n'+rows.map((r,i)=>`file '${quote(r.file)}'\nduration ${Math.max(.0167,(rows[i+1]?.time??r.time+.12)-r.time).toFixed(6)}\n`).join('')+`file '${quote(rows.at(-1).file)}'\n`;
}
export function readyRoute(result){
 return Object.entries(result?.routes||{}).find(([k,r])=>r.status==='ready'&&r.coverage?.complete&&r.coordinates?.length>2);
}
