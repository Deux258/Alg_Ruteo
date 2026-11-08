"""Shared weather and usable-energy policy for validation, routing and diagnostics.

Budgets supplied by the user remain the real usable budgets. Planning additionally
keeps one verification/report reserve per battery and once per whole mission.
"""
import math

from core.aerial_data import iso


def assess_constraints(model, request, _profile=None, _surface=None, _access_height=None):
    from core.patrol import profile_for, flight_terrain, number
    from core.vertical_profile import level
    if not isinstance(request, dict):
        raise ValueError('Solicitud JSON debe ser un objeto')
    profile = profile_for(request) if _profile is None else dict(_profile)
    clock = iso(request.get('time', model['reference_time']))
    if clock.tzinfo is None:
        raise ValueError('Hora requiere zona UTC explícita')
    reasons = []
    hour=clock.replace(minute=0,second=0,microsecond=0)
    weather = next((row for row in model['records']['M4'] if iso(row['valid_at']) == hour), None)
    fields = ('wind_speed_ms', 'wind_gust_ms', 'wind_direction_deg', 'temperature_c')
    known = weather is not None and all(
        type(weather.get(key)) in (int, float) and math.isfinite(weather[key]) for key in fields
    )
    probability = 0.0 if known else None
    if not known:
        reasons.append(dict(code='weather_unknown', source='A1',
                            message='Meteorología desconocida para la hora UTC solicitada'))
    if weather is not None:
        speeds = [weather.get(key) for key in ('wind_speed_ms', 'wind_gust_ms')]
        if all(type(v) in (int, float) and math.isfinite(v) for v in speeds) and max(speeds) >= profile['wind_limit_ms']:
            probability = 100.0
            reasons.append(dict(code='wind_limit', source='A1',
                message=f"Viento o ráfaga de {max(speeds):g} m/s alcanza el límite de {profile['wind_limit_ms']:g} m/s"))
        temperature = weather.get('temperature_c')
        if type(temperature) in (int, float) and math.isfinite(temperature) and not profile['temperature_min_c'] <= temperature <= profile['temperature_max_c']:
            probability = 100.0
            reasons.append(dict(code='temperature_limit', source='A1',
                message=f"Temperatura de {temperature:g} °C fuera del intervalo {profile['temperature_min_c']:g}–{profile['temperature_max_c']:g} °C"))
    reserve = float(profile['verification_s'])
    battery = float(profile['battery_budget_s'])
    mission = float(profile['mission_budget_s'])
    flight = battery - reserve
    mission_flight = mission - reserve
    access_height = _access_height
    access_basis = 'exact_banded_origin' if access_height is not None else 'minimum_clearance_bound'
    origin=request.get('origin')
    if 'origin' in request:
        if not isinstance(origin,(list,tuple)) or len(origin)!=2:raise ValueError('Coordenadas WGS84 [longitud, latitud]')
        number(origin[0],'longitud',-180,180);number(origin[1],'latitud',-90,90)
    if access_height is None and isinstance(origin,(list,tuple)) and len(origin)==2 and (_surface is not None or model.get('raster')):
        from core.aerial_data import FWD
        if all(type(v) in (int,float) and math.isfinite(v) for v in origin):
            surface=_surface if _surface is not None else flight_terrain(model)
            height=surface.at(*FWD(*origin))
            if height is not None:
                access_height=level(height,profile['altitude_agl_m'])-height
                access_basis='exact_banded_origin'
            else:access_basis='unknown_origin_elevation_bound'
    if access_height is None:access_height=profile['altitude_agl_m']
    vertical = access_height / profile['climb_ms'] + access_height / profile['descent_ms']
    if flight <= vertical:
        reasons.append(dict(code='battery_report_reserve', source='energy',
            message=f'La batería útil de {battery:g} s no permite despegue, aterrizaje y reserva de reporte de {reserve:g} s'))
    if mission_flight <= vertical:
        reasons.append(dict(code='mission_report_reserve', source='energy',
            message=f'El presupuesto total de {mission:g} s no permite despegue, aterrizaje y reserva de reporte de {reserve:g} s'))
    return dict(admissible=not reasons, reasons=reasons, weather=weather,
                probability_pct=probability, weather_admissible=known and probability == 0,
                battery_budget_s=battery, flight_budget_s=max(0.0, flight), report_reserve_s=reserve,
                verification_reserve_s=reserve, mission_budget_s=mission,
                mission_flight_budget_s=max(0.0, mission_flight), time=clock.isoformat(),
                origin_access_height_m=access_height,origin_vertical_flight_s=vertical,vertical_access_basis=access_basis,
                effective_profile=profile)
