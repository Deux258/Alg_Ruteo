import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';
const source = readFileSync(new URL('../Sitio Web/flight-player.js', import.meta.url), 'utf8');
const { smoothFollow, mapPaneOffset, flightTelemetry, targetPlaneRings } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));

test('Projected follow damping is frame-rate independent without overshoot', () => {
  const follow = (frames) => {
    let p = [0, 200];
    for (let i = 0; i < frames; i++) p = smoothFollow(p, [100, 100], 180 / frames);
    return p;
  };
  const a = follow(6), b = follow(18);
  for (let i = 0; i < 2; i++) assert.ok(Math.abs(a[i] - b[i]) < 1e-10);
  assert.ok(a[0] > 60 && a[0] < 100);
  assert.ok(a[1] > 100 && a[1] < 140);
  assert.deepEqual(smoothFollow(null, [20, 30], 16), [20, 30]);
  assert.deepEqual(smoothFollow([2, 3], [9, 10], 0), [2, 3]);
  assert.deepEqual(smoothFollow([2, 3], [NaN, 10], 50), [2, 3]);
});

test('Compositor translation keeps geographic positions aligned before and after a view reset', () => {
  const size = [1024, 768], desired = [300000.25, 500000.75];
  const landmark = [desired[0] + 75, desired[1] - 32];
  for (const origin of [[299000, 499000], [299488.25, 499616.75]]) {
    const offset = mapPaneOffset(desired, origin, size);
    const displayed = landmark.map((coordinate, i) => coordinate - origin[i] + offset[i]);
    assert.deepEqual(displayed, [587, 352]);
    const actualCenter = origin.map((coordinate, i) => coordinate + size[i] / 2 - offset[i]);
    assert.deepEqual(actualCenter, desired);
  }
});

test('Telemetry labels latitude/longitude explicitly and preserves negative signs and EGM2008', () => {
  assert.equal(flightTelemetry({ coordinates: [-71.65324567, -33.10123456, 493.26] }),
    'Lat -33.101235° · Lon -71.653246° · Cota 493.3 m EGM2008');
  assert.equal(flightTelemetry({ coordinates: [-71, -33, null] }), 'Lat — · Lon — · Cota —');
});

test('Horizontal target rings preserve holes and closure at one authoritative altitude', () => {
  const outer = [[-71.65, -33.1], [-71.649, -33.1], [-71.649, -33.099], [-71.65, -33.1]];
  const hole = [[-71.6498, -33.0998], [-71.6496, -33.0998], [-71.6497, -33.0996], [-71.6498, -33.0998]];
  const target = { type: 'Polygon', coordinates: [outer, hole] };
  const before = JSON.stringify(target), rings = targetPlaneRings(target, 510.5);
  assert.equal(rings.length, 2);
  for (const ring of rings) {
    assert.deepEqual(ring[0], ring.at(-1));
    assert.ok(ring.every((point) => point[2] === 510.5));
  }
  assert.deepEqual(targetPlaneRings(target, null), []);
  assert.equal(JSON.stringify(target), before);
});
