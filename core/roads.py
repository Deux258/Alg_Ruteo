"""Red vial dirigida: solo segmentos originales OSM, sin unir cruces por cercanía."""
import hashlib
import json
import math
from collections import Counter, defaultdict
from uuid import UUID, NAMESPACE_URL, uuid5

from shapely.geometry import Point, LineString

from core.area import load_area

ROAD_CLASSES = {'motorway','trunk','primary','secondary','tertiary','unclassified',
                'residential','living_street','service','motorway_link','trunk_link',
                'primary_link','secondary_link','tertiary_link'}
ALLOWED_ACCESS = {'yes','permissive','designated','official'}


def distance_m(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, [*a,*b])
    value = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(value)))


def access(tags, suffix=''):
    for key in ['motorcar','motor_vehicle','vehicle','access']:
        value = tags.get(key + suffix)
        if value is not None:
            return value in ALLOWED_ACCESS
    return True


def directions(tags):
    if tags.get('highway') not in ROAD_CLASSES or tags.get('area') == 'yes':
        return set(), 'non_drivable_class'
    if any(k.endswith(':conditional') and k.split(':')[0] in {'access','motorcar','motor_vehicle','vehicle','oneway'} for k in tags):
        return set(), 'conditional_access_excluded'
    if not access(tags):
        return set(), 'restricted_access'
    if any(k in tags for k in ['maxheight','maxwidth','maxweight','maxlength']):
        # El perfil no tiene dimensiones verificadas: no presume que el vehículo cabe.
        return set(), 'dimension_restriction_excluded'
    value = next((tags[k] for k in ['oneway:motorcar','oneway:motor_vehicle','oneway:vehicle','oneway'] if k in tags), None)
    if value is None:
        value = 'yes' if tags.get('highway') == 'motorway' or tags.get('junction') in {'roundabout','circular'} else 'no'
    if value in {'yes','true','1'}:
        result = {1}
    elif value in {'-1','reverse'}:
        result = {-1}
    elif value in {'no','false','0'}:
        result = {1,-1}
    else:
        return set(), 'unsupported_oneway'
    for direction, suffix in [(1,':forward'),(-1,':backward')]:
        if not access(tags, suffix):
            result.discard(direction)
    return result, None


def blocked_node(tags):
    if not access(tags):
        return True
    return tags.get('barrier') not in (None, 'no', 'entrance', 'cattle_grid', 'toll_booth') and not any(
        tags.get(k) in ALLOWED_ACCESS for k in ['motorcar','motor_vehicle','vehicle','access'])


def read_sources(config):
    from core.contracts import ROOT, sha256
    folder = ROOT/config['road_raw_directory']
    manifest_path = folder/'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest['bbox_wgs84'] != config['bbox_wgs84']:
        raise ValueError('Los originales viales corresponden a otra envolvente; actualizar fuentes')
    docs = {}
    for key in sorted({'osm','senapred',config.get('selected_base',{}).get('raw_source','senapred')}):
        source = manifest['sources'][key]
        path = (folder/source['file']).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256(path) != source['sha256']:
            raise ValueError('Original modificado o ruta inválida: '+key)
        docs[key] = json.loads(path.read_text(encoding='utf-8'))
    if docs['osm'].get('remark') or docs['senapred'].get('exceededTransferLimit'):
        raise ValueError('Fuentes incompletas')
    return manifest, docs, manifest_path


def road_segments(osm, area):
    elements = {}
    for e in osm['elements']:
        key = (e['type'],e['id'])
        if key in elements and elements[key] != e:
            raise ValueError('OSM contiene versiones incompatibles del mismo objeto')
        elements[key] = e
    nodes = {i:e for (t,i),e in elements.items() if t=='node'}
    ways = {i:e for (t,i),e in elements.items() if t=='way'}
    inside = {i for i,n in nodes.items() if area.covers(Point(n['lon'],n['lat']))}
    blocked = {i for i,n in nodes.items() if blocked_node(n.get('tags',{}))}
    segments = {}; excluded = Counter(); aliases = 0
    for way in sorted(ways.values(),key=lambda w:w['id']):
        allowed, reason = directions(way.get('tags',{}))
        if not allowed:
            excluded[reason or 'no_allowed_direction'] += 1
            continue
        for index,(a,b) in enumerate(zip(way['nodes'],way['nodes'][1:])):
            if a not in nodes or b not in nodes:
                raise ValueError(f'Faltan nodos originales de la vía {way["id"]}')
            if a == b or (nodes[a]['lon'],nodes[a]['lat']) == (nodes[b]['lon'],nodes[b]['lat']):
                excluded['zero_length_segment'] += 1; continue
            if a not in inside or b not in inside:
                excluded['boundary_segment'] += 1; continue
            if a in blocked or b in blocked:
                excluded['barrier_segment'] += 1; continue
            coords = [[nodes[n]['lon'],nodes[n]['lat']] for n in [a,b]]
            if not area.covers(LineString(coords)):
                excluded['segment_exits_polygon'] += 1; continue
            pair = tuple(sorted([a,b]))
            oriented = {(a,b) if d==1 else (b,a) for d in allowed}
            provenance = dict(way_id=way['id'],segment_index=index,from_node=a,to_node=b,tags=way.get('tags',{}))
            if pair in segments:
                # El mismo segmento OSM no se duplica; ante desacuerdo se conserva
                # la intersección de sentidos permitidos, nunca se amplía el acceso.
                segments[pair]['directions'] &= oriented
                segments[pair]['provenance'].append(provenance); aliases += 1
            else:
                segments[pair] = dict(directions=oriented, provenance=[provenance])
    return nodes, ways, elements, segments, dict(excluded), aliases


def restrictions(elements, ways, edges):
    incoming = defaultdict(list); outgoing = defaultdict(list); by_way = defaultdict(list)
    for e in edges:
        incoming[e['target']].append(e); outgoing[e['source']].append(e)
        for p in e['osm']:
            by_way[p['way_id']].append(e)
    forbidden = set(); applied = []; excluded = []
    for relation in sorted((e for e in elements.values() if e['type']=='relation' and e.get('tags',{}).get('type')=='restriction'), key=lambda r:r['id']):
        tags = relation['tags']; members = relation['members']
        froms = {m['ref'] for m in members if m['role']=='from' and m['type']=='way'}
        tos = {m['ref'] for m in members if m['role']=='to' and m['type']=='way'}
        via = [m for m in members if m['role']=='via']
        if not any(w in by_way for w in froms) or not any(w in by_way for w in tos):
            excluded.append(dict(relation_id=relation['id'],reason='outside_or_excluded_ways')); continue
        if set(tags.get('except','').split(';')) & {'motorcar','motor_vehicle','vehicle'}:
            excluded.append(dict(relation_id=relation['id'],reason='profile_excepted')); continue
        kind = tags.get('restriction:motorcar',tags.get('restriction:motor_vehicle',tags.get('restriction')))
        if kind is None:
            excluded.append(dict(relation_id=relation['id'],reason='other_vehicle_type')); continue
        if not (kind.startswith('no_') or kind.startswith('only_')) or any('conditional' in k for k in tags):
            raise ValueError(f'Restricción de giro no soportada dentro de la red: {relation["id"]}')
        before = len(forbidden)
        if len(via)==1 and via[0]['type']=='node':
            from core.contracts import stable_id
            vid = stable_id(f'osm:node:{via[0]["ref"]}')
            for e in incoming[vid]:
                if not froms.intersection(p['way_id'] for p in e['osm']):continue
                for f in outgoing[vid]:
                    match = bool(tos.intersection(p['way_id'] for p in f['osm']))
                    if kind.endswith('u_turn') and froms == tos:
                        match = match and f['target'] == e['source']
                    if (kind.startswith('no_') and match) or (kind.startswith('only_') and not match):
                        forbidden.add((e['id'],f['id']))
        elif via and all(v['type']=='way' for v in via) and kind.startswith('no_'):
            # Secuencia dirigida from -> uno o varios tramos via -> to.
            # Se mantienen todos los vértices, por lo que un via puede requerir
            # más de un arco. No se sustituye por una prohibición más amplia.
            def walk(current, via_index, path, used):
                for nxt in outgoing[current['target']]:
                    ids = {p['way_id'] for p in nxt['osm']}
                    if via_index == len(via):
                        if ids & tos: forbidden.add(tuple(path+[nxt['id']]))
                        continue
                    if via[via_index]['ref'] not in ids or nxt['id'] in used:
                        continue
                    newpath=path+[nxt['id']]
                    walk(nxt,via_index+1,newpath,used|{nxt['id']})
                    walk(nxt,via_index,newpath,used|{nxt['id']})
            for wid in froms:
                for e in by_way[wid]:walk(e,0,[e['id']],{e['id']})
        else:
            raise ValueError(f'Estructura de giro no soportada en la red: {relation["id"]}')
        applied.append(dict(relation_id=relation['id'],restriction=kind,forbidden_sequences_added=len(forbidden)-before))
    return [list(p) for p in sorted(forbidden)], applied, excluded


def build_road_snapshot(config, run_id=None, extraction_mode='snapshot'):
    from core.contracts import ROOT, canonical, sha256, stable_id, validate_infrastructure
    manifest, docs, manifest_path = read_sources(config)
    area_path = ROOT/config['aoi_geojson']; area = load_area(area_path)
    raw_nodes, ways, elements, segments, excluded, aliases = road_segments(docs['osm'], area)
    edges = []; used = set()
    for pair,segment in sorted(segments.items()):
        for source,target in sorted(segment['directions']):
            s,t = [stable_id(f'osm:node:{n}') for n in [source,target]]
            key = f'arc:osm:node:{source}->osm:node:{target}'
            physical = 'corridor:'+'|'.join(sorted([f'osm:node:{source}',f'osm:node:{target}']))
            edges.append(dict(id=stable_id(key),natural_key=key,source=s,target=t,physical_key=physical,
                geometry=dict(type='LineString',coordinates=[[raw_nodes[n]['lon'],raw_nodes[n]['lat']] for n in [source,target]]),
                osm=segment['provenance']))
            used.update([source,target])
    selection=config['selected_base'];base_id = selection['provider_id']
    base_source=selection.get('raw_source','senapred');id_field=selection.get('provider_id_field','objectid_1')
    candidates = [f for f in docs[base_source]['features'] if str(f['properties'].get(id_field))==str(base_id)]
    if len(candidates)!=1 or not area.covers(Point(candidates[0]['geometry']['coordinates'])):
        raise ValueError('La base seleccionada falta o está fuera del polígono')
    feature = candidates[0]; coord = feature['geometry']['coordinates']
    anchor = min(used, key=lambda n:(distance_m(coord,[raw_nodes[n]['lon'],raw_nodes[n]['lat']]),n))
    offset = distance_m(coord,[raw_nodes[anchor]['lon'],raw_nodes[anchor]['lat']])
    if offset > config['selected_base']['max_road_offset_m']:
        raise ValueError('La base no tiene un nodo vial suficientemente próximo; no se inventa conexión')
    nodes = [dict(id=stable_id(f'osm:node:{n}'),natural_key=f'osm:node:{n}',
        kind='base_candidata' if n==anchor else 'vial',source_record_id=str(n),
        geometry=dict(type='Point',coordinates=[raw_nodes[n]['lon'],raw_nodes[n]['lat']])) for n in sorted(used)]
    nodes.sort(key=lambda n:n['id']); edges.sort(key=lambda e:e['id'])
    forbidden, applied, dropped = restrictions(elements,ways,edges)
    base = dict(provider_id=str(base_id),source_id=selection.get('source_id','SENAPRED_BOMBEROS'),
        raw_source=base_source,provider_id_field=id_field,name=feature['properties'][selection.get('name_field','nombre')],
        address=selection.get('confirmed_address',feature['properties'].get('direccion')),
        address_source=selection['corroboration_url'],commune=feature['properties'].get('comuna'),
        geometry=feature['geometry'],routing_node_id=stable_id(f'osm:node:{anchor}'),osm_node_id=anchor,
        road_offset_haversine_m=offset,access_model='existing_osm_node; facility_to_road_not_modelled',
        corroboration_url=config['selected_base']['corroboration_url'],source_properties=feature['properties'])
    lineage = dict(builder='osm-road-adapter-v1',configuration_sha256=hashlib.sha256(canonical(config)).hexdigest(),
        manifest=dict(file=manifest_path.relative_to(ROOT).as_posix(),sha256=sha256(manifest_path)),
        aoi=dict(file=area_path.relative_to(ROOT).as_posix(),sha256=sha256(area_path),geometry=json.loads(json.dumps(area.__geo_interface__)),predicate='covers'),
        sources=manifest['sources'],base=base,
        road_profile=dict(mode='motorcar',road_classes=sorted(ROAD_CLASSES),boundary_policy='discard_non_covered_original_segments',
                          conditional_policy='exclude_ways; reject_unhandled_turn_relations',artificial_connectors=0),
        spatial_filter=dict(raw_osm_nodes=len(raw_nodes),raw_osm_ways=len(ways),excluded=excluded,duplicate_segment_aliases=aliases),
        turn_restrictions=dict(forbidden_paths=forbidden,applied=applied,excluded=dropped))
    observed = manifest['sources']['osm']['timestamp_osm_base']
    semantic = dict(nodes=nodes,edges=edges,crs='EPSG:4326',analysis_srid=32719,lineage=lineage,
                    observed_at=observed,extracted_at=manifest['fetched_at_utc'],builder=lineage['builder'])
    digest=hashlib.sha256(canonical(semantic)).hexdigest()
    rid=str(UUID(run_id)) if run_id else str(uuid5(NAMESPACE_URL,'udp:roads-v1:'+extraction_mode+':'+digest))
    doc=dict(schema_version='2.0',run_id=rid,dataset_id=str(uuid5(UUID(rid),'I')),dataset_key='I',source_id='DERIVED_ROADS',
             observed_at=observed,extracted_at=manifest['fetched_at_utc'],crs='EPSG:4326',analysis_srid=32719,
             input_hash=digest,lineage=lineage,extraction_mode=extraction_mode,nodes=nodes,edges=edges)
    return validate_infrastructure(doc, config)


def validate_road_provenance(doc, config):
    from core.contracts import ROOT,stable_id
    if doc['source_id'] != 'DERIVED_ROADS' or doc['lineage'].get('builder') != 'osm-road-adapter-v1':
        raise ValueError('Identidad del constructor vial incorrecta')
    manifest, docs, _ = read_sources(config)
    if doc['lineage'].get('sources') != manifest['sources']:
        raise ValueError('El linaje no coincide con los originales viales')
    elements = {(e['type'],e['id']):e for e in docs['osm']['elements']}
    by_id = {n['id']:n for n in doc['nodes']}
    for node in doc['nodes']:
        osm_id = int(node['source_record_id'])
        original = elements.get(('node',osm_id))
        if not original or node['natural_key'] != f'osm:node:{osm_id}' or node['geometry']['coordinates'] != [original['lon'],original['lat']]:
            raise ValueError('Nodo vial no corresponde a un nodo OSM original')
        if node['kind'] not in {'vial','base_candidata'}:
            raise ValueError('Tipo de nodo incompatible con red vial')
        if blocked_node(original.get('tags',{})):
            raise ValueError('Nodo con barrera no transitable')
    for edge in doc['edges']:
        s = int(by_id[edge['source']]['source_record_id']); t = int(by_id[edge['target']]['source_record_id'])
        if len(edge['geometry']['coordinates']) != 2 or not edge.get('osm'):
            raise ValueError('Arco vial sin procedencia verificable')
        for p in edge['osm']:
            original = elements.get(('way',p['way_id']))
            if not original or p['tags'] != original.get('tags',{}):
                raise ValueError('Etiquetas viales alteradas')
            index = p['segment_index']; seq = original['nodes']
            if not 0 <= index < len(seq)-1 or [p['from_node'],p['to_node']] != seq[index:index+2]:
                raise ValueError('Segmento no existe en la vía OSM')
            directions_allowed,_ = directions(p['tags'])
            if not ((s,t)==tuple(seq[index:index+2]) and 1 in directions_allowed or
                    (t,s)==tuple(seq[index:index+2]) and -1 in directions_allowed):
                raise ValueError('Sentido contrario a OSM o acceso restringido')
    base = doc['lineage']['base']
    selection=config['selected_base']
    matches = [f for f in docs[selection.get('raw_source','senapred')]['features']
               if str(f['properties'].get(selection.get('provider_id_field','objectid_1')))==base['provider_id']]
    if len(matches)!=1 or base['provider_id']!=str(config['selected_base']['provider_id']):
        raise ValueError('Base no corresponde a la selección SENAPRED')
    if base['geometry'] != matches[0]['geometry'] or base['source_properties'] != matches[0]['properties']:
        raise ValueError('Coordenadas o atributos de base alterados')
    area = load_area(ROOT/config['aoi_geojson'])
    if not area.covers(Point(base['geometry']['coordinates'])):
        raise ValueError('Base real fuera del polígono')
    anchor = by_id.get(base['routing_node_id'])
    if not anchor or anchor['kind']!='base_candidata' or anchor['id']!=stable_id(f'osm:node:{base["osm_node_id"]}'):
        raise ValueError('Origen vial inválido')
    if distance_m(base['geometry']['coordinates'],anchor['geometry']['coordinates']) > config['selected_base']['max_road_offset_m']:
        raise ValueError('Incorporación vial demasiado alejada de la base')
    expected,_,_ = restrictions(elements,{i:e for (t,i),e in elements.items() if t=='way'},doc['edges'])
    if doc['lineage']['turn_restrictions']['forbidden_paths'] != expected:
        raise ValueError('Restricciones de giro incompletas o alteradas')
