"""Consultas de rutas viales. Los costos provienen exclusivamente de PostGIS."""
import json
import math


def base_info(conn, rid):
    row = conn.execute("""SELECT b.provider_id,b.name,b.address,b.node_id,
        ST_AsGeoJSON(ST_Transform(b.geom,4326))::jsonb AS geometry,
        ST_AsGeoJSON(ST_Transform(n.geom,4326))::jsonb AS road_origin,
        ST_Distance(b.geom,n.geom) AS road_offset_m,b.provenance
        FROM routing.base_locations b JOIN routing.nodes n ON (n.run_id,n.id)=(b.run_id,b.node_id)
        WHERE b.run_id=%s""",(rid,)).fetchone()
    return row


def route(conn, rid, target, source=None, respect_turns=True):
    base = base_info(conn,rid)
    if source is None:
        if not base:raise ValueError('La instantánea no contiene una base vial')
        source = base['node_id']
    source,target = int(source),int(target)
    if conn.execute('SELECT count(*) AS n FROM routing.nodes WHERE run_id=%s AND id=ANY(%s::bigint[])',
                    (rid,list({source,target}))).fetchone()['n'] != len({source,target}):
        raise ValueError('Origen o destino no pertenece a la red publicada')
    if source == target:
        return dict(type='FeatureCollection',features=[],properties=dict(source=str(source),target=str(target),distance_km=0,status='at_origin'))
    if respect_turns:
        rows = conn.execute("""SELECT p.seq,p.edge_id,p.source,p.target,p.cost_km,
            ST_AsGeoJSON(ST_Transform(p.geom,4326),15)::jsonb AS geometry,e.road_origin
            FROM routing.road_path(%s,%s,%s) p
            JOIN routing.edges e ON e.run_id=%s AND e.id=p.edge_id ORDER BY p.seq""",(rid,source,target,rid)).fetchall()
        graph = conn.execute('SELECT routing.road_state_sql(%s,%s,%s) AS q',(rid,source,target)).fetchone()['q']
        cost = conn.execute('SELECT agg_cost FROM pgr_dijkstra(%s,0::bigint,-1::bigint,true) WHERE node=-1',(graph,)).fetchone()
    else:
        rows = conn.execute("""SELECT p.path_seq AS seq,e.id AS edge_id,e.source,e.target,e.length_km AS cost_km,
            ST_AsGeoJSON(ST_Transform(e.geom,4326),15)::jsonb AS geometry,e.road_origin
            FROM pgr_dijkstra(routing.edge_sql(%s),%s::bigint,%s::bigint,true) p
            JOIN routing.edges e ON e.run_id=%s AND e.id=p.edge ORDER BY p.path_seq""",(rid,source,target,rid)).fetchall()
        cost = {'agg_cost':sum(row['cost_km'] for row in rows)} if rows else None
    if not rows or not cost:
        raise ValueError('No existe una ruta permitida entre origen y destino dentro del polígono')
    if rows[0]['source'] != source or rows[-1]['target'] != target or any(a['target']!=b['source'] for a,b in zip(rows,rows[1:])):
        raise RuntimeError('La ruta no es una cadena vial continua')
    distance = sum(row['cost_km'] for row in rows)
    if not math.isclose(distance,cost['agg_cost'],rel_tol=1e-10,abs_tol=1e-9):
        raise RuntimeError('El costo Dijkstra no coincide con las longitudes de los arcos')
    lineage = conn.execute("SELECT lineage FROM routing.datasets WHERE run_id=%s AND dataset_key='I'",(rid,)).fetchone()['lineage']
    edge_ids = [r['edge_id'] for r in rows]
    if respect_turns:
        for forbidden in lineage.get('turn_restrictions',{}).get('forbidden_paths',[]):
            if any(edge_ids[i:i+len(forbidden)]==forbidden for i in range(len(edge_ids)-len(forbidden)+1)):
                raise RuntimeError('La ruta viola una restricción de giro')
    coords=[]; streets=[]
    for row in rows:
        coords.extend(row['geometry']['coordinates'][0 if not coords else 1:])
        name=(row['road_origin'][0]['tags'].get('name') or row['road_origin'][0]['tags'].get('ref') or 'Calle sin nombre en OSM') if row['road_origin'] else 'Enlace legado'
        if not streets or streets[-1]!=name:streets.append(name)
    properties=dict(run_id=str(rid),source=str(source),target=str(target),distance_km=distance,
        dijkstra_cost_km=cost['agg_cost'],edge_count=len(rows),edge_ids=[str(n) for n in edge_ids],
        node_ids=[str(rows[0]['source'])]+[str(r['target']) for r in rows],streets=streets,
        algorithm='pgr_dijkstra / turn-state graph' if respect_turns else 'pgr_dijkstra / distance reference',
        respects_turns=respect_turns,facility_to_road_included=False)
    return dict(type='FeatureCollection',features=[dict(type='Feature',geometry=dict(type='LineString',coordinates=coords),properties=properties)],properties=properties)


def reachable_nodes(conn,rid,source):
    return conn.execute("""SELECT e.target AS id,min(d.agg_cost) AS distance_km,
        ST_X(ST_Transform(n.geom,4326)) AS lon,ST_Y(ST_Transform(n.geom,4326)) AS lat
        FROM pgr_drivingDistance(routing.road_state_sql(%s,%s),0::bigint,1000::float8,true) d
        JOIN routing.road_states s ON s.run_id=%s AND s.id=d.node
        JOIN routing.edges e ON e.run_id=s.run_id AND e.id=s.edge_id
        JOIN routing.nodes n ON n.run_id=e.run_id AND n.id=e.target
        GROUP BY e.target,n.geom ORDER BY e.target""",(rid,source,rid)).fetchall()


def audit_roads(conn,rid):
    base=base_info(conn,rid)
    checks=conn.execute("""WITH a AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON((lineage#>'{aoi,geometry}')::text),4326) AS geom
        FROM routing.datasets WHERE run_id=%s AND dataset_key='I')
        SELECT (SELECT ST_Covers(a.geom,ST_Transform(b.geom,4326)) FROM routing.base_locations b WHERE b.run_id=%s) AS base_inside,
        (SELECT count(*) FROM routing.edges WHERE run_id=%s AND jsonb_array_length(road_origin)=0) AS arcs_without_osm,
        (SELECT count(*) FROM routing.road_transitions t
         JOIN routing.road_states s ON (s.run_id,s.id)=(t.run_id,t.source)
         JOIN routing.road_states d ON (d.run_id,d.id)=(t.run_id,t.target)
         JOIN routing.edges e ON (e.run_id,e.id)=(s.run_id,s.edge_id)
         JOIN routing.edges f ON (f.run_id,f.id)=(t.run_id,t.edge_id)
         WHERE t.run_id=%s AND (e.target<>f.source OR d.edge_id<>f.id)) AS invalid_transitions,
        (SELECT count(*) FROM routing.road_states WHERE run_id=%s) AS states,
        (SELECT count(*) FROM routing.road_transitions WHERE run_id=%s) AS transitions
        FROM a""",(rid,rid,rid,rid,rid,rid)).fetchone()
    if not checks['base_inside'] or checks['arcs_without_osm'] or checks['invalid_transitions'] or base['road_offset_m']>30:
        raise ValueError('Auditoría vial/base falló: '+json.dumps(checks))
    reachable=reachable_nodes(conn,rid,base['node_id'])
    config=conn.execute('SELECT configuration FROM routing.runs WHERE run_id=%s',(rid,)).fetchone()['configuration']
    minimum=config.get('selected_base',{}).get('min_reachable_nodes',1000)
    if len(reachable)<minimum:
        raise ValueError(f'La base solo alcanza {len(reachable)} nodos; mínimo de utilidad territorial: {minimum}')
    candidates=[r for r in reachable if r['id']!=base['node_id'] and r['distance_km']>.5]
    if len(candidates)<3:raise ValueError('No hay al menos tres destinos viales distintos a más de 500 m de la base')
    selectors=[('Norte',lambda r:r['lat']),('Este',lambda r:r['lon']),('Mayor distancia',lambda r:r['distance_km'])]
    chosen=set(); examples=[]
    for label,key in selectors:
        candidate=max((r for r in candidates if r['id'] not in chosen),key=key)
        chosen.add(candidate['id'])
        path=route(conn,rid,candidate['id'])
        p=path['properties']
        examples.append(dict(label=label,target=str(candidate['id']),coordinates=[candidate['lon'],candidate['lat']],
                             distance_km=p['distance_km'],edge_count=p['edge_count'],streets=p['streets']))
    return dict(ready=True,base={k:v for k,v in base.items() if k!='provenance'},
                checks=checks,reachable_nodes=len(reachable),unreachable_nodes=conn.execute(
                    'SELECT count(*) AS n FROM routing.nodes WHERE run_id=%s',(rid,)).fetchone()['n']-len(reachable),
                examples=examples,turn_restrictions_applied=True,facility_to_road_included=False)


def map_data(conn,rid):
    row=conn.execute("SELECT lineage,validation FROM routing.datasets WHERE run_id=%s AND dataset_key='I'",(rid,)).fetchone()
    features=conn.execute("""SELECT jsonb_build_object('type','Feature','geometry',ST_AsGeoJSON(ST_Transform(geom,4326))::jsonb,
        'properties',jsonb_build_object('id',id::text,'name',COALESCE(road_origin#>>'{0,tags,name}',road_origin#>>'{0,tags,ref}','Sin nombre'),
        'highway',road_origin#>>'{0,tags,highway}','osm_way_id',road_origin#>>'{0,way_id}')) AS feature
        FROM (SELECT DISTINCT ON(physical_key) * FROM routing.edges WHERE run_id=%s ORDER BY physical_key,id) e""",(rid,)).fetchall()
    return dict(type='FeatureCollection',features=[r['feature'] for r in features],
                area=row['lineage']['aoi']['geometry'],base=base_info(conn,rid),
                examples=row['validation'].get('road_routing',{}).get('examples',[]),
                attribution='© OpenStreetMap contributors (ODbL); base SENAPRED Servicios_2024',
                limitations=['Distancia vial; no tráfico ni cierres en tiempo real','El acceso interior del cuartel a la calle no está modelado'])
