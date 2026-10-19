"""Integración de M1–M4 de Diego Hidalgo al contrato del pipeline principal.

Adaptado de aportes_metadata_diego/Metadata; conserva ese aporte como antecedente.
Las adquisiciones, hashes y cargas se centralizan en el pipeline principal.
"""
from shapely.geometry import shape, mapping
from shapely.ops import transform

EXTERNAL_IDS = {'18', '20', '23', '31'}


def bases(features, original, study, flight, to_metric):
    """IDs del catálogo ArcGIS, nunca selección por parecido de nombres."""
    original_base = next(f for f in original if str(f['properties']['objectid_1']) == '104')
    study_m = transform(to_metric, study)
    records = []
    for feature in features:
        original_properties = feature['properties']
        p = {k.lower():v for k,v in original_properties.items()}; provider_id = str(p['fid']); geometry = feature['geometry']
        inside = study.covers(shape(geometry))
        distance = study_m.distance(transform(to_metric, shape(geometry)))
        if distance > 1100: continue
        candidate = inside or provider_id in EXTERNAL_IDS
        refs = [dict(source_id='S1H', provider_id=provider_id)]
        canonical_id = 'S1H:' + provider_id
        if provider_id == '19':
            if transform(to_metric, shape(geometry)).distance(transform(to_metric, shape(original_base['geometry']))) > 1:
                raise ValueError('Conciliación S1:104 / S1H:19 excede 1 m')
            geometry = original_base['geometry']; canonical_id = '104'
            refs.append(dict(source_id='S1', provider_id='104'))
        if candidate and not flight.covers(shape(geometry)):
            raise ValueError('Base seleccionada fuera del área de tránsito: ' + provider_id)
        records.append(dict(provider_id=canonical_id, name=p.get('nombre'), address=p.get('direccion'),
            commune=p.get('comuna'), geometry=geometry, inside_study=inside, distance_to_study_m=distance,
            candidate=candidate, selection_reason='inside_study' if inside else 'team_approved' if candidate else 'context_only',
            source_refs=refs, original_record=original_properties))
    if sum(r['candidate'] for r in records) != 5 or not EXTERNAL_IDS <= {r['source_refs'][0]['provider_id'] for r in records if r['candidate']}:
        raise ValueError('El catálogo no contiene las cinco bases seleccionadas')
    return records


def landcover(properties, clipped, to_metric):
    """Atributos M2: clases nominales, sin convertir altura de vegetación a metros."""
    names = {'uso_tierra':'land_use_code', 'subuso':'subuse', 'estructura':'structure',
        'cobertura':'cover_class', 'altura':'height_class', 'tipo_fores':'forest_type', 'subtipofor':'forest_subtype', 'nom_com':'commune'}
    return dict(attributes={target:properties.get(source) for source,target in names.items()},
        original_area_ha=properties.get('superf_ha'), clipped_area_ha=transform(to_metric, clipped).area / 10000,
        original_record=properties)


def weather_rows(weather):
    """Normalización de las seis variables del aporte, con contrato UTC y m/s."""
    hourly=weather['hourly'];units=weather['hourly_units']
    if weather['utc_offset_seconds'] != 0 or any(units[k] != 'm/s' for k in ['wind_speed_10m','wind_gusts_10m']):
        raise ValueError('Unidades/tiempo meteorológico inesperado')
    fields={'temperature_c':'temperature_2m','relative_humidity_pct':'relative_humidity_2m',
        'wind_speed_ms':'wind_speed_10m','wind_direction_deg':'wind_direction_10m','wind_gust_ms':'wind_gusts_10m','precipitation_mm':'precipitation'}
    if any(len(hourly[k]) != len(hourly['time']) for k in fields.values()):
        raise ValueError('Serie meteorológica incompleta')
    result=[]
    for i,date in enumerate(hourly['time']):
        row={k:hourly[v][i] for k,v in fields.items()}
        row.update(valid_at=date+':00+00:00',cell=[weather['longitude'],weather['latitude']])
        if row['wind_direction_deg'] is not None:row['wind_direction_deg']%=360
        result.append(row)
    return result
