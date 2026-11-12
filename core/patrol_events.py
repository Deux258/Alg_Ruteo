"""Fixed empirical baseline. No frame-dependent draws or client probability."""
import hashlib
import json
import math
from datetime import date
from pathlib import Path

BASELINE = Path(__file__).resolve().parents[1] / 'config/incendios_valparaiso.json'


def uniform(seed, scenario, label):
    digest = hashlib.sha256(f'fire-v1:{seed}:{scenario}:{label}'.encode()).digest()
    return (int.from_bytes(digest[:8], 'big') >> 11) / 2**53


def baseline():
    raw = BASELINE.read_bytes()
    row = json.loads(raw)
    days = (date.fromisoformat(row['observation_end']) - date.fromisoformat(row['observation_start'])).days
    row['observation_days'] = days
    row['rate_per_km2_day'] = row['count'] / (days * row['region_area_km2'])
    row['sha256'] = hashlib.sha256(raw).hexdigest()
    return row


def probability(area_m2, seconds):
    if not math.isfinite(area_m2) or not math.isfinite(seconds) or min(area_m2, seconds) < 0:
        raise ValueError('Área y exposición deben ser finitas y no negativas')
    expected = baseline()['rate_per_km2_day'] * area_m2 / 1e6 * seconds / 86400
    return -math.expm1(-expected)


def arrival(seed, scenario, area_m2, start_s, duration_s, namespace=''):
    """First arrival of a homogeneous Poisson process, independent of route/camera.

    Keeping the first exponential arrival (rather than a conditional resampling
    within each route) preserves the same event when a mission horizon changes.
    """
    rate = baseline()['rate_per_km2_day'] * area_m2 / 1e6 / 86400
    u = uniform(seed, scenario, f'{namespace}:arrival')
    wait = -math.log1p(-u) / rate if rate > 0 else math.inf
    return dict(schema_version='fire-event-1', mode='automatic', baseline=baseline(),
                probability=probability(area_m2, duration_s), draw=u,
                area_m2=area_m2, exposure_s=duration_s,
                occurs=duration_s>0 and wait <= duration_s, appeared_at_s=start_s+wait if duration_s>0 and wait <= duration_s else None,
                state='active' if duration_s>0 and wait <= duration_s else 'no_fire', coordinates=None,
                protocol='sha256/53-bit; exponential first arrival; uniform UTM area')


def generate(seed, scenario, target, start_s, duration_s, terrain):
    from shapely.geometry import Point
    from core.aerial_data import INV
    namespace=hashlib.sha256(target.wkb).hexdigest()
    event = arrival(seed, scenario, target.area, start_s, duration_s, namespace)
    event['namespace']=namespace
    event['id'] = hashlib.sha256(f"fire-v2:{event['baseline']['sha256']}:{seed}:{scenario}:{namespace}".encode()).hexdigest()
    if not event['occurs']:
        return event
    # Rejection sampling on the entire polygon, including disconnected support
    # and holes. Unknown elevation is not silently removed from the fire model.
    west, south, east, north = target.bounds
    for attempt in range(100000):
        x = west + (east-west)*uniform(seed, scenario, f'{namespace}:x:{attempt}')
        y = south + (north-south)*uniform(seed, scenario, f'{namespace}:y:{attempt}')
        if target.covers(Point(x, y)):
            event['coordinates'] = list(INV(x, y))
            event['surface_m'] = terrain.at(x, y)
            event['state'] = 'active' if event['surface_m'] is not None else 'unknown_elevation'
            return event
    raise ValueError('No se pudo muestrear el soporte espacial del foco; revisar geometría')
