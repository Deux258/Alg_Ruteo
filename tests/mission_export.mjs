import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
const source = readFileSync(new URL('../Sitio Web/mission-export.js', import.meta.url), 'utf8');
const { buildMissionGeoJSON } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

function fixture() {
  const coordinates = [[-71.65, -33.10, 70], [-71.649, -33.10, 80], [-71.65, -33.10, 70]];
  const route = { status: 'ready', coordinates, label: 'Ruta de prueba', edge_ids: ['1', '2'], time_s: 45 };
  return { result: {
    sha256: 'a'.repeat(64), status: 'ready', time: '2026-11-07T00:00:00-03:00',
    origin: coordinates[0].slice(0, 2), origin_base: { id: '104', name: 'Base Mirador', coordinates: coordinates[0].slice(0, 2) },
    target_polygon: { type: 'Polygon', coordinates: [[[-71.65, -33.10], [-71.65, -33.099], [-71.649, -33.099], [-71.65, -33.10]]] },
    target_display: { status: 'known', level_m_egm2008: 100, offset_m: 30 },
    evaluation: { seed: 7, count: 1000, scenario_sha256: 'scenario-hash', scenarios: [{ id: 0, draws: [1, 2] }], first_scenario: { id: 0 } },
    graph: { home: '1', nodes: [{ id: '1', coordinates: coordinates[0], surface_m_egm2008: 10 }, { id: '2', coordinates: coordinates[1], surface_m_egm2008: 20 }] },
    stations: [{ id: '105', name: 'Estación Lago', node: '2', position_utm: [252000, 6334000, 80], hypothetical: true }],
    threats: [{ id: 'A2:1', probability_pct: 30, geometry: { type: 'Point', coordinates: [-71.649, -33.099, 0] } }],
    routes: Object.fromEntries(['dijkstra_distance', 'dijkstra_weighted', 'gurobi', 'annealing'].map((k) => [k, structuredClone(route)])),
    route_alternatives: { alt_1: structuredClone(route) },
  }, simulation: null, comparison_history: [] };
}
const feature = (fc, id) => fc.features.find((row) => row.id === id);

test('GeoJSON preserves named originals and all route sets, keeps orthometric heights in properties, and never mutates input', () => {
  const bundle = fixture(), before = structuredClone(bundle), fc = buildMissionGeoJSON(bundle);
  assert.equal(fc.type, 'FeatureCollection');
  assert.equal(fc.features.filter((row) => row.properties.kind === 'route').length, 5);
  assert.deepEqual(feature(fc, 'mission:origin').geometry.coordinates, [-71.65, -33.10]);
  assert.equal(feature(fc, 'mission:origin').properties.name, 'Base Mirador');
  assert.equal(feature(fc, 'mission:origin').properties.altitude_m_egm2008, 10);
  assert.equal(feature(fc, 'mission:station:105').properties.name, 'Estación Lago');
  assert.deepEqual(feature(fc, 'mission:station:105').geometry.coordinates, [-71.649, -33.10]);
  assert.equal(feature(fc, 'mission:station:105').properties.altitude_m_egm2008, 20);
  assert.deepEqual(feature(fc, 'route:comparison:gurobi').properties.altitudes_m_egm2008, [70, 80, 70]);
  assert.equal(feature(fc, 'mission:target').properties.display_level_m_egm2008, 100);
  assert.equal(feature(fc, 'mission:target').properties.visual_only, true);
  for (const row of fc.features) {
    const visit = (coordinates) => typeof coordinates[0] === 'number'
      ? assert.equal(coordinates.length, 2)
      : coordinates.forEach(visit);
    if (row.geometry) visit(row.geometry.coordinates);
  }
  assert.equal(fc.metadata.export_scope, 'original_snapshot_unclipped');
  assert.equal(fc.metadata.evaluation.count, 1000);
  assert.equal(fc.metadata.evaluation.scenarios, undefined);
  assert.equal(fc.metadata.evaluation.scenario_sha256, 'scenario-hash');
  assert.deepEqual(bundle, before);
});

test('Unknown XY splits flight lines without bridges while unknown Z remains null and zero altitude remains zero', () => {
  const bundle = fixture();
  bundle.result.routes = { gurobi: { coordinates: [[-71.65, -33.10, 0], [-71.649, -33.10, null], null, [-71.648, -33.10, 50], [-71.647, -33.10, NaN]] } };
  const row = feature(buildMissionGeoJSON(bundle), 'route:comparison:gurobi');
  assert.equal(row.geometry.type, 'MultiLineString');
  assert.deepEqual(row.geometry.coordinates.map((part) => part.length), [2, 2]);
  assert.deepEqual(row.properties.altitudes_m_egm2008, [[0, null], [50, null]]);
  assert.doesNotThrow(() => JSON.stringify(buildMissionGeoJSON(bundle)));
});

test('Blocked mission retains four diagnostics with null geometries and never invents a path', () => {
  const bundle = fixture(); bundle.result.status = 'blocked'; bundle.result.route_alternatives = {};
  bundle.result.diagnostic = { reasons: [{ code: 'weather', probability_pct: 100 }] };
  for (const route of Object.values(bundle.result.routes)) Object.assign(route, { status: 'blocked', coordinates: [], time_s: null });
  const fc = buildMissionGeoJSON(bundle), routes = fc.features.filter((row) => row.properties.kind === 'route');
  assert.equal(routes.length, 4);
  assert.ok(routes.every((row) => row.geometry === null && row.properties.status === 'blocked'));
  assert.equal(fc.metadata.diagnostic.reasons[0].probability_pct, 100);
  assert.equal(fc.metadata.simulation, null);
});

test('Simulation samples preserve coordinates, elapsed time, UTC, phases and battery including vertical maneuvers', () => {
  const bundle = fixture();
  bundle.simulation = { result_sha256: bundle.result.sha256, method: 'gurobi', route_set: 'comparison', scenario: 'nominal', timeline: [
    { time_s: 0, coordinates: [-71.65, -33.10, 10], phase: 'takeoff', battery_pct: 100 },
    { time_s: 10.5, coordinates: [-71.65, -33.10, 70], phase: 'patrol', battery_pct: 99 },
    { time_s: 40, coordinates: [-71.649, -33.10, 80], phase: 'return', battery_pct: 90 },
  ] };
  const fc = buildMissionGeoJSON(bundle), row = feature(fc, 'simulation:frame:1');
  assert.deepEqual(row.geometry.coordinates, [-71.65, -33.10]);
  assert.equal(row.properties.altitude_m_egm2008, 70);
  assert.equal(row.properties.timestamp_utc, '2026-11-07T03:00:10.500Z');
  assert.equal(row.properties.phase, 'patrol'); assert.equal(row.properties.battery_pct, 99);
  const path = feature(fc, 'simulation:trajectory');
  assert.deepEqual(path.properties.times_s, [0, 10.5, 40]);
  assert.deepEqual(path.properties.altitudes_m_egm2008, [10, 70, 80]);
  assert.equal(fc.metadata.simulation.timeline, undefined);
});

test('Incomplete report preserves null completion and no completed-report feature; completed report carries its actual time', () => {
  const bundle = fixture();
  bundle.simulation = { timeline: [], detection: { fire_coordinates: [-71.649, -33.099], observer_coordinates: [-71.65, -33.10, 70], detected_at_s: 10, report_status: 'incomplete', report_completed: false, reported_at_s: null, reported_at_utc: null } };
  let fc = buildMissionGeoJSON(bundle);
  assert.equal(feature(fc, 'simulation:report'), undefined);
  assert.equal(fc.metadata.simulation.detection.reported_at_utc, null);
  assert.equal(feature(fc, 'simulation:detection').properties.timestamp_utc, '2026-11-07T03:00:10.000Z');
  Object.assign(bundle.simulation.detection, { report_status: 'completed', report_completed: true, reported_at_s: 70 });
  fc = buildMissionGeoJSON(bundle);
  assert.equal(feature(fc, 'simulation:report').properties.timestamp_utc, '2026-11-07T03:01:10.000Z');
});

test('Unknown time does not invent UTC and a stale simulation cannot be mixed with another mission', () => {
  const bundle = fixture(); delete bundle.result.time;
  bundle.simulation = { result_sha256: bundle.result.sha256, timeline: [{ coordinates: [-71.65, -33.10, null], time_s: 5, phase: 'takeoff' }] };
  assert.equal(feature(buildMissionGeoJSON(bundle), 'simulation:frame:0').properties.timestamp_utc, null);
  assert.equal(feature(buildMissionGeoJSON(bundle), 'simulation:frame:0').properties.altitude_m_egm2008, null);
  bundle.simulation.result_sha256 = 'b'.repeat(64);
  assert.throws(() => buildMissionGeoJSON(bundle), /otra misión/);
  assert.throws(() => buildMissionGeoJSON({}), /misión completa/);
});
