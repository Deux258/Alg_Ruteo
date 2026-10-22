"""Red adaptativa, once salidas JSON y publicación transaccional."""
import hashlib
import json
import math
from functools import lru_cache
from uuid import NAMESPACE_URL, uuid5

from psycopg.types.json import Jsonb
from shapely.geometry import Point, LineString, box, shape, mapping
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from core.contracts import ROOT, canonical, stable_id, sha256, write_json
from core.aerial_data import FWD, INV
from core.patrol_sources import profile, load_raw
from core.surface import Surface


def base_context(conn):
    row=conn.execute('''SELECT m.run_id,m.context,d.lineage FROM routing.publication p
        JOIN routing.aerial_models m USING(run_id) JOIN routing.datasets d ON d.run_id=p.run_id AND d.dataset_key='I'
        WHERE p.singleton''').fetchone()
    if not row: raise ValueError('Preparar primero la instantánea aérea con ./main iniciar')
    context=row['context']; area=transform(FWD,shape(context['flight_geometry']))
    entry=row['lineage']['sources']['S3']; config=json.loads((ROOT/'config/proyecto.json').read_text())
    file=(ROOT/config['aerial_raw_directory']/entry['file']).resolve()
    if sha256(file)!=entry['sha256']: raise ValueError('DSM original alterado')
    if 'EGM2008' not in context['raster'].get('vertical_datum','') or context['raster'].get('vertical_units') != 'm':
        raise ValueError('Referencia vertical DSM incompatible')
    return str(row['run_id']),context,area,row['lineage'],file


class Obstacles:
    def __init__(self, rows):
        self.rows=rows; self.geometries=[shape(r['exclusion']) for r in rows]
        self.tree=STRtree(self.geometries)
        self.union=unary_union(self.geometries)
        from shapely import prepare
        prepare(self.union)

    def check(self, geometry):
        indices=self.tree.query(geometry,predicate='dwithin',distance=100)
        if not len(indices): return False,100.0
        distance=min(geometry.distance(self.geometries[int(i)]) for i in indices)
        return any(geometry.intersects(self.geometries[int(i)]) for i in indices),distance


def make_edge(ident, source, target, a, b, surface, obstacles, p, corridor=None, obstacle_result=None):
    line=LineString([a[:2],b[:2]])
    blocked,distance=obstacle_result if obstacle_result is not None else obstacles.check(line if line.length else Point(a[:2]))
    sample=corridor or surface.corridor(a,b,p)
    return dict(id=ident,source=source,target=target,coordinates=[a,b],horizontal_km=line.length/1000,
                flight_km=math.dist(a,b)/1000,blocked_obstacle=blocked,obstacle_distance_m=distance,**sample)


def build(area, study, landcover, obstacle_rows, surface, p):
    forest=unary_union([transform(FWD,shape(r['geometry'])) for r in landcover if r['category'] in ('Bosques','Praderas y Matorrales')])
    urban=unary_union([transform(FWD,shape(r['geometry'])) for r in landcover if 'urban' in r['category'].lower()])
    interface=forest.boundary.intersection(urban.buffer(1)).buffer(p['interface_buffer_m']) if not forest.is_empty and not urban.is_empty else Point().buffer(0)
    obstacles=Obstacles(obstacle_rows)
    grid=p['grid_m']; small=p['refined_grid_m']; bounds=area.bounds; cells=[]; anchors=[]; skipped=0
    for x in range(math.floor(bounds[0]/grid)*grid,math.ceil(bounds[2]/grid)*grid,grid):
        for y in range(math.floor(bounds[1]/grid)*grid,math.ceil(bounds[3]/grid)*grid,grid):
            cell=box(x,y,x+grid,y+grid)
            if not area.intersects(cell):continue
            values,known=surface.pixels(cell)
            reasons=[]
            if len(values)>0 and max(values)-min(values)>p['refine_relief_m']:reasons.append('relief_variation')
            if obstacles.union.intersects(cell):reasons.append('known_obstacles')
            if interface.intersects(cell):reasons.append('urban_forest_interface')
            refine=bool(reasons)
            size=small if refine else grid
            for dx in range(0,grid,size):
                for dy in range(0,grid,size):
                    xx,yy=x+dx+size/2,y+dy+size/2; point=Point(xx,yy)
                    if not area.covers(point):continue
                    z=surface.height(xx,yy)
                    if z is None:skipped+=1;continue
                    key=f"{p['builder']}:{size}:{xx}:{yy}"
                    anchors.append(dict(id=key,x=xx,y=yy,surface_m=z,resolution_m=size,refinement_reasons=reasons,
                                        kind='observation' if study.covers(point) and forest.covers(point) else 'navigation'))
                    cells.append(box(x+dx,y+dy,x+dx+size,y+dy+size))
    tree=STRtree(cells); states={}; by_anchor={}
    for a in anchors:
        by_anchor[a['id']]=[]
        for level in p['levels_m']:
            ident=stable_id(a['id']+':'+str(level))
            if ident in states:raise ValueError('Colisión de identificadores')
            states[ident]=dict(id=ident,anchor_id=a['id'],kind=a['kind'],resolution_m=a['resolution_m'],refinement_reasons=a['refinement_reasons'],
                              surface_m=a['surface_m'],surface_offset_m=level,coordinates=[a['x'],a['y'],a['surface_m']+level])
            by_anchor[a['id']].append(ident)
    edges=[]
    def add(s,t,sample=None,obstacle_result=None):
        a,b=states[s]['coordinates'],states[t]['coordinates']
        key=f"{p['builder']}:edge:{s}:{t}"
        edge=make_edge(stable_id(key),s,t,a,b,surface,obstacles,p,sample,obstacle_result)
        edges.append(edge)
    for a in anchors:
        ids=by_anchor[a['id']]
        point=Point(a['x'],a['y']);obstacle_result=obstacles.check(point)
        first=surface.corridor([a['x'],a['y'],a['surface_m']],[a['x'],a['y'],a['surface_m']],p)
        for s,t in zip(ids,ids[1:]):
            sample=dict(first,clearance_m=first['clearance_m']+min(states[s]['surface_offset_m'],states[t]['surface_offset_m']) if first['surface_known'] else None)
            add(s,t,sample,obstacle_result);add(t,s,sample,obstacle_result)
    print(f'Anclas {len(anchors)}; estados {len(states)}. Construyendo corredores…',flush=True)
    for i,a in enumerate(anchors):
        if i and i%500==0:print(f'Corredores: {i}/{len(anchors)} anclas; {len(edges)} arcos',flush=True)
        for j in tree.query(cells[i].buffer(0.01)):
            j=int(j)
            if j<=i:continue
            b=anchors[j]; line=LineString([(a['x'],a['y']),(b['x'],b['y'])])
            if line.length>p['max_link_m'] or not area.covers(line):continue
            first=surface.corridor([a['x'],a['y'],a['surface_m']],[b['x'],b['y'],b['surface_m']],p)
            obstacle_result=obstacles.check(line)
            backward=[[1-r[0],r[1]] for r in reversed(first['profile_samples'])]
            maximum=min(a['surface_m'],b['surface_m'])-first['clearance_m'] if first['surface_known'] else None
            for ia,s in enumerate(by_anchor[a['id']]):
                for ib,t in enumerate(by_anchor[b['id']]):
                    if abs(ia-ib)>1:continue
                    ca,cb=states[s]['coordinates'],states[t]['coordinates']
                    sample=dict(surface_known=first['surface_known'],clearance_m=min(ca[2],cb[2])-maximum if maximum is not None else None,
                                profile_samples=first['profile_samples'])
                    add(s,t,sample,obstacle_result)
                    reverse=dict(sample,profile_samples=backward)
                    add(t,s,reverse,obstacle_result)
    if not states or not edges:raise ValueError('Red adaptativa vacía')
    return states,edges,dict(anchors=len(anchors),states=len(states),directed_edges=len(edges),nodata_anchors=skipped,
        refined_anchors=sum(a['resolution_m']==small for a in anchors),
        terrain_admitted=sum(e['surface_known'] and e['clearance_m']>=p['minimum_clearance_m'] and not e['blocked_obstacle'] for e in edges))


def digest_json(value):
    digest=hashlib.sha256()
    for chunk in json.JSONEncoder(sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).iterencode(value):digest.update(chunk.encode())
    return digest.hexdigest()


def store_document(conn,doc):
    # I se materializa en tablas tipadas; evitar una segunda copia JSONB del grafo.
    stored=doc
    if doc['dataset_key']=='I':
        stored={k:v for k,v in doc.items() if k!='records'}
        stored['records_summary']={k:len(v) for k,v in doc['records'].items()}
        stored['materialized_tables']=['flight_states','flight_edges']
    old=conn.execute('SELECT document FROM routing.patrol_datasets WHERE run_id=%s AND key=%s',(doc['run_id'],doc['dataset_key'])).fetchone()
    if old:
        if old['document']!=stored:raise ValueError('Dataset existente incompatible')
        return
    if doc['dataset_key']=='M5':
        for o in doc['records']:
            conn.execute('INSERT INTO routing.flight_obstacles VALUES(%s,%s,%s,%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),32719),ST_SetSRID(ST_GeomFromGeoJSON(%s),32719)) ON CONFLICT DO NOTHING',
                (doc['run_id'],o['provider_id'],o['kind'],o['height_m'],Jsonb(o['original_tags']),json.dumps(o['geometry']),json.dumps(o['exclusion'])))
    conn.execute('INSERT INTO routing.patrol_datasets VALUES(%s,%s,%s)',(doc['run_id'],doc['dataset_key'],Jsonb(stored)))


def load_dataset(conn, path):
    doc=json.loads(path.read_text()); rid=doc['run_id']; key=doc['dataset_key']
    if key not in ['I']+['M'+str(i) for i in range(1,6)]+['A'+str(i) for i in range(1,6)]:raise ValueError('Dataset desconocido')
    if doc.get('schema_version')!='patrol-dataset-1' or digest_json(doc['records'])!=doc['records_sha256']:
        raise ValueError('Contrato de dataset alterado')
    store_document(conn,doc)


def prepare(conn):
    from core.db import apply_schema,create_reader
    apply_schema(conn);create_reader(conn)
    base,context,area,lineage,dsm=base_context(conn); p=profile()
    manifest,obstacles,weather=load_raw(area)
    construction_code={name:sha256(ROOT/name) for name in ['core/patrol_data.py','core/surface.py','core/patrol_sources.py']}
    digest=digest_json(dict(base=base,lineage=lineage,manifest=manifest,profile=p,construction_code=construction_code))
    rid=str(uuid5(NAMESPACE_URL,'vigilancia:'+digest));folder=ROOT/'datos/runs'/rid
    existing=conn.execute('SELECT status FROM routing.patrol_runs WHERE id=%s',(rid,)).fetchone()
    if existing and existing['status']=='ready':
        conn.execute('INSERT INTO routing.patrol_publication VALUES(true,%s) ON CONFLICT(singleton) DO UPDATE SET run_id=EXCLUDED.run_id',(rid,))
        return dict(run_id=rid,idempotent=True)
    folder.mkdir(parents=True,exist_ok=True)
    surface=Surface(dsm,area.bounds)
    try:states,edges,counts=build(area,transform(FWD,shape(context['study_geometry'])),context['records']['M2'],obstacles,surface,p)
    finally:surface.close()
    ctx=dict(base_run_id=base,study_geometry=context['study_geometry'],flight_geometry=context['flight_geometry'],
             weather=weather,weather_fetched_at=manifest['sources']['S4H']['fetched_at_utc'],
             records={k:context['records'][k] for k in ['M1','M2','A2','A3','A4']},
             source_manifest=manifest,base_lineage=lineage,dsm_file=str(dsm.relative_to(ROOT)),dsm_sha256=sha256(dsm),
             vertical_datum='EGM2008',counts=counts,construction_code=construction_code,
             refinement_by_anchor={n['anchor_id']:n['refinement_reasons'] for n in states.values()})
    from core.patrol_routing import weather_problem
    outputs=dict(I=dict(states=list(states.values()),edges=edges),M1=context['records']['M1'],M2=context['records']['M2'],
                 M3=[dict(state_id=str(i),surface_m=n['surface_m'],flight_m=n['coordinates'][2],vertical_datum='EGM2008') for i,n in states.items()],
                 M4=weather,M5=obstacles,A1=[dict(valid_at=w['valid_at'],source='M4',rule_profile=p['version'],state='unknown' if weather_problem(w,p).startswith(('missing','unknown')) else 'active',reason=weather_problem(w,p)) for w in weather if weather_problem(w,p)],
                 A2=context['records']['A2'],A3=context['records']['A3'],A4=context['records']['A4'],
                 A5=[dict(provider_id=r['provider_id'],kind=r['kind'],geometry=r['exclusion'],height_m=r['height_m'],state='excluded_2d') for r in obstacles])
    documents={}
    for key,records in outputs.items():
        doc=dict(schema_version='patrol-dataset-1',run_id=rid,dataset_key=key,records=records,
                 geometry_crs='EPSG:32719' if key in ['I','M3','M5','A5'] else 'EPSG:4326',vertical_datum='EGM2008' if key in ['I','M3'] else None,
                 records_sha256=digest_json(records),lineage=dict(input_hash=digest,source_manifest=manifest,base_run_id=base))
        documents[key]=doc
        target=folder/(key+'.json');temporary=target.with_suffix('.tmp')
        with temporary.open('w') as stream:json.dump(doc,stream,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
        temporary.replace(target)
        print(f'JSON {key} escrito',flush=True)
    with conn.transaction():
        conn.execute('INSERT INTO routing.patrol_runs(id,base_run_id,input_hash,profile,context,status) VALUES(%s,%s,%s,%s,%s,%s)',(rid,base,digest,Jsonb(p),Jsonb(ctx),'staging'))
        with conn.cursor().copy('COPY routing.flight_states(run_id,id,anchor_id,kind,resolution_m,surface_m,surface_offset_m,geom) FROM STDIN') as copy:
            for n in states.values():copy.write_row((rid,n['id'],n['anchor_id'],n['kind'],n['resolution_m'],n['surface_m'],n['surface_offset_m'],'SRID=32719;'+Point(n['coordinates']).wkt))
        with conn.cursor().copy('COPY routing.flight_edges(run_id,id,source,target,geom,horizontal_km,flight_km,clearance_m,surface_known,obstacle_distance_m,blocked_obstacle,profile_samples) FROM STDIN') as copy:
            for e in edges:copy.write_row((rid,e['id'],e['source'],e['target'],'SRID=32719;'+LineString(e['coordinates']).wkt,e['horizontal_km'],e['flight_km'],e['clearance_m'],e['surface_known'],e['obstacle_distance_m'],e['blocked_obstacle'],json.dumps(e['profile_samples'])))
        for key,doc in documents.items():store_document(conn,doc)
        # La nueva instantánea todavía no es visible a autovacuum. Sin estas
        # estadísticas, un JOIN estimado en una fila puede ejecutar miles de
        # millones de comparaciones antes de publicar.
        conn.execute('ANALYZE routing.flight_states; ANALYZE routing.flight_edges; ANALYZE routing.flight_obstacles',prepare=False)
        invalid=conn.execute('''SELECT count(*) AS n FROM routing.flight_edges WHERE run_id=%s AND
            abs(flight_km-ST_3DLength(geom)/1000)>1e-8''',(rid,)).fetchone()['n']
        if invalid:raise ValueError('Longitudes tridimensionales inconsistentes')
        spatial=conn.execute('''WITH area AS (SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),32719) AS geom)
            SELECT (SELECT count(*) FROM routing.flight_states n,area WHERE n.run_id=%s AND NOT ST_Covers(area.geom,n.geom)) AS outside_states,
            (SELECT count(*) FROM routing.flight_edges e,area WHERE e.run_id=%s AND NOT ST_Covers(area.geom,e.geom)) AS outside_edges,
            (SELECT count(*) FROM routing.flight_edges e JOIN routing.flight_states a ON a.run_id=e.run_id AND a.id=e.source
              JOIN routing.flight_states b ON b.run_id=e.run_id AND b.id=e.target WHERE e.run_id=%s AND
              (ST_3DDistance(ST_StartPoint(e.geom),a.geom)>1e-8 OR ST_3DDistance(ST_EndPoint(e.geom),b.geom)>1e-8)) AS inconsistent_endpoints''',
              (json.dumps(context['flight_geometry']),rid,rid,rid)).fetchone()
        if any(spatial.values()):raise ValueError('Auditoría espacial falló: '+str(spatial))
        from psycopg import sql
        literal=sql.Literal(rid).as_string(conn)
        query=f'SELECT id,source,target,flight_km AS cost,-1::float8 AS reverse_cost FROM routing.flight_edges WHERE run_id={literal}::uuid'
        counts['strong_components']=conn.execute('SELECT count(DISTINCT component) AS n FROM pgr_strongComponents(%s)',(query,)).fetchone()['n']
        if counts['strong_components']<1:raise ValueError('Sin componentes en la red')
        counts['spatial_audit']=dict(spatial)
        conn.execute('UPDATE routing.patrol_runs SET context=%s WHERE id=%s',(Jsonb(ctx),rid))
        conn.execute("UPDATE routing.patrol_runs SET status='ready' WHERE id=%s",(rid,))
        conn.execute('INSERT INTO routing.patrol_publication VALUES(true,%s) ON CONFLICT(singleton) DO UPDATE SET run_id=EXCLUDED.run_id',(rid,))
    report=dict(run_id=rid,base_run_id=base,schema_version='patrol-graph-1',status='ready',counts=counts,datasets=list(outputs),input_hash=digest)
    write_json(folder/'resumen.json',report)
    return report


@lru_cache(maxsize=2)
def graph(rid):
    from core.db import connect
    with connect() as conn:
        row=conn.execute("SELECT * FROM routing.patrol_runs WHERE id=%s AND status='ready'",(rid,)).fetchone()
        if not row:raise ValueError('Publicación de vigilancia no disponible')
        states={r['id']:dict(r,coordinates=r['coordinates']) for r in conn.execute('SELECT id,anchor_id,kind,resolution_m,surface_m,surface_offset_m,ST_X(geom) AS x,ST_Y(geom) AS y,ST_Z(geom) AS z,ARRAY[ST_X(geom),ST_Y(geom),ST_Z(geom)] AS coordinates FROM routing.flight_states WHERE run_id=%s ORDER BY id',(rid,))}
        edges=[dict(r,coordinates=[states[r['source']]['coordinates'],states[r['target']]['coordinates']]) for r in conn.execute('SELECT id,source,target,horizontal_km,flight_km,clearance_m,surface_known,obstacle_distance_m,blocked_obstacle FROM routing.flight_edges WHERE run_id=%s ORDER BY id',(rid,))]
        obstacles=conn.execute("SELECT document->'records' AS records FROM routing.patrol_datasets WHERE run_id=%s AND key='M5'",(rid,)).fetchone()['records']
    file=ROOT/row['context']['dsm_file']
    if sha256(file)!=row['context']['dsm_sha256']:raise ValueError('DSM alterado')
    return row['profile'],row['context'],states,edges,obstacles
