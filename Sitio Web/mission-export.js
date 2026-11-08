// GeoJSON uses WGS84 longitude/latitude. Orthometric heights stay in properties:
// RFC 7946's optional third ordinate is ellipsoidal, unlike the source EGM2008 Z.
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const height = (value) => (finite(value) ? value : null);
const xy = (point) =>
  Array.isArray(point) &&
  finite(point[0]) && finite(point[1]) &&
  Math.abs(point[0]) <= 180 && Math.abs(point[1]) <= 90;

function copy(value) {
  if (typeof value === "number") return height(value);
  if (Array.isArray(value)) return value.map(copy);
  if (value && typeof value === "object")
    return Object.fromEntries(Object.entries(value)
      .filter(([, item]) => item !== undefined)
      .map(([key, item]) => [key, copy(item)]));
  return value;
}

function orient(ring, outer) {
  if (!Array.isArray(ring) || ring.length < 4 || !ring.every(xy)) return null;
  const points = ring.map((point) => point.slice(0, 2));
  if (points[0][0] !== points.at(-1)[0] || points[0][1] !== points.at(-1)[1]) return null;
  const area = points.slice(1).reduce((sum, p, i) => sum + points[i][0] * p[1] - p[0] * points[i][1], 0);
  return (area > 0) === outer ? points : points.reverse();
}

function geometry2d(geometry) {
  if (!geometry || typeof geometry !== "object") return null;
  const coordinates = geometry.coordinates;
  switch (geometry.type) {
    case "Point":
      return xy(coordinates) ? { type: "Point", coordinates: coordinates.slice(0, 2) } : null;
    case "MultiPoint":
    case "LineString": {
      if (!Array.isArray(coordinates) || !coordinates.every(xy) ||
          (geometry.type === "LineString" && coordinates.length < 2)) return null;
      return { type: geometry.type, coordinates: coordinates.map((p) => p.slice(0, 2)) };
    }
    case "Polygon": {
      if (!Array.isArray(coordinates) || !coordinates.length) return null;
      const rings = coordinates.map((ring, i) => orient(ring, i === 0));
      return rings.every(Boolean) ? { type: "Polygon", coordinates: rings } : null;
    }
    case "MultiLineString":
    case "MultiPolygon": {
      if (!Array.isArray(coordinates)) return null;
      const parts = coordinates.map((part) => geometry2d({
        type: geometry.type === "MultiPolygon" ? "Polygon" : "LineString", coordinates: part,
      }));
      return parts.every(Boolean) ? { type: geometry.type, coordinates: parts.map((p) => p.coordinates) } : null;
    }
    case "GeometryCollection": {
      if (!Array.isArray(geometry.geometries)) return null;
      const geometries = geometry.geometries.map(geometry2d);
      return geometries.every(Boolean) ? { type: "GeometryCollection", geometries } : null;
    }
    default: return null;
  }
}

// Unknown XY breaks a line; it must never draw an invented connector across a gap.
function linePayload(coordinates) {
  const parts = [];
  let current = [];
  const flush = () => { if (current.length >= 2) parts.push(current); current = []; };
  for (const [index, point] of (Array.isArray(coordinates) ? coordinates : []).entries()) {
    if (xy(point)) current.push(index);
    else flush();
  }
  flush();
  if (!parts.length) return { geometry: null, aligned: () => [] };
  const multi = parts.length > 1;
  const aligned = (get) => multi ? parts.map((part) => part.map(get)) : parts[0].map(get);
  return {
    geometry: {
      type: multi ? "MultiLineString" : "LineString",
      coordinates: aligned((i) => coordinates[i].slice(0, 2)),
    },
    aligned,
  };
}

function utc(base, seconds) {
  if (!finite(seconds) || typeof base !== "string" || !/(?:Z|[+-]\d\d:\d\d)$/i.test(base)) return null;
  const start = Date.parse(base), time = start + seconds * 1000;
  return finite(start) && finite(time) && Math.abs(time) <= 8.64e15 ? new Date(time).toISOString() : null;
}

function pointOf(row, node) {
  const point = row?.geometry?.type === "Point" ? row.geometry.coordinates : row?.coordinates;
  return xy(point) ? point : xy(node?.coordinates) ? node.coordinates : null;
}

export function buildMissionGeoJSON(bundle) {
  const result = bundle?.result;
  if (!result || typeof result !== "object") throw new TypeError("La exportación requiere una misión completa.");
  const simulation = bundle.simulation || null;
  if (simulation?.result_sha256 && simulation.result_sha256 !== result.sha256)
    throw new Error("La simulación corresponde a otra misión.");
  const features = [], nodes = new Map((result.graph?.nodes || []).map((node) => [String(node.id), node]));
  const add = (id, kind, geometry, properties = {}) => features.push({
    type: "Feature", id, geometry, properties: copy({ kind, result_sha256: result.sha256, ...properties }),
  });

  if (result.target_polygon) add("mission:target", "target", geometry2d(result.target_polygon), {
    name: "Objetivo de vigilancia", target_display: result.target_display || null,
    display_level_m_egm2008: height(result.target_display?.level_m_egm2008),
    visual_only: true,
  });
  const base = result.origin_base || {}, home = nodes.get(String(result.graph?.home));
  const origin = pointOf(base, { coordinates: result.origin });
  if (origin || result.origin_base) add("mission:origin", "base", geometry2d({ type: "Point", coordinates: origin }), {
    id: base.id ?? base.provider_id ?? null, provider_id: base.provider_id ?? base.id ?? null,
    name: base.name || "Base de salida",
    altitude_m_egm2008: height(base.surface_m_egm2008 ?? home?.surface_m_egm2008),
    planned_flight_altitude_m_egm2008: height(home?.coordinates?.[2]),
  });
  for (const [i, station] of (result.stations || []).entries()) {
    const node = nodes.get(String(station.node)), point = pointOf(station, node);
    add(`mission:station:${station.id ?? station.provider_id ?? i}`, "station", geometry2d({ type: "Point", coordinates: point }), {
      ...station, name: station.name || "Estación de recambio",
      altitude_m_egm2008: height(station.surface_m_egm2008 ?? node?.surface_m_egm2008),
      planned_flight_altitude_m_egm2008: height(node?.coordinates?.[2]),
    });
  }
  for (const [i, threat] of (result.threats || []).entries()) {
    const { geometry, ...properties } = threat;
    add(`mission:threat:${threat.id ?? i}`, "threat", geometry2d(geometry), {
      ...properties,
      ...(geometry?.type === "Point" ? { altitude_m_egm2008: height(geometry.coordinates?.[2]) } : {}),
    });
  }
  for (const [set, field] of [["comparison", "routes"], ["alternatives", "route_alternatives"]]) {
    for (const [method, route] of Object.entries(result[field] || {})) {
      const coordinates = route.coordinates || [], payload = linePayload(coordinates);
      add(`route:${set}:${method}`, "route", payload.geometry, {
        route_set: set, method, name: route.label || method, status: route.status,
        distance_m: route.distance_m, time_s: route.time_s, compute_s: route.compute_s,
        coverage: route.coverage, resilience: route.resilience, solver: route.solver, timings: route.timings,
        altitudes_m_egm2008: payload.aligned((i) => height(coordinates[i][2])),
        edge_ids: route.edge_ids || [], stops: route.stops || [],
      });
    }
  }
  if (simulation) {
    const timeline = simulation.timeline || [], coordinates = timeline.map((frame) => frame.coordinates);
    const payload = linePayload(coordinates);
    const common = { method: simulation.method, route_set: simulation.route_set, scenario: simulation.scenario };
    add("simulation:trajectory", "simulation_trajectory", payload.geometry, {
      ...common, status: simulation.status,
      altitudes_m_egm2008: payload.aligned((i) => height(coordinates[i][2])),
      times_s: payload.aligned((i) => height(timeline[i].time_s)),
      timestamps_utc: payload.aligned((i) => utc(result.time, timeline[i].time_s)),
    });
    for (const [i, frame] of timeline.entries()) add(`simulation:frame:${i}`, "simulation_frame", geometry2d({ type: "Point", coordinates: frame.coordinates }), {
      ...common, index: i, time_s: frame.time_s, timestamp_utc: utc(result.time, frame.time_s),
      phase: frame.phase, battery_pct: frame.battery_pct, altitude_m_egm2008: height(frame.coordinates?.[2]),
    });
    const detection = simulation.detection;
    if (detection) {
      add("simulation:fire", "detected_fire", geometry2d({ type: "Point", coordinates: detection.fire_coordinates }), {
        ...common, detected_at_s: detection.detected_at_s, detected_at_utc: detection.detected_at_utc ?? utc(result.time, detection.detected_at_s),
      });
      const point = geometry2d({ type: "Point", coordinates: detection.observer_coordinates });
      add("simulation:detection", "detection", point, {
        ...common, time_s: detection.detected_at_s, timestamp_utc: detection.detected_at_utc ?? utc(result.time, detection.detected_at_s),
        altitude_m_egm2008: height(detection.observer_coordinates?.[2]), report_status: detection.report_status,
      });
      if ((detection.report_completed === true || detection.report_status === "completed") && finite(detection.reported_at_s))
        add("simulation:report", "completed_report", point, {
          ...common, time_s: detection.reported_at_s,
          timestamp_utc: detection.reported_at_utc ?? utc(result.time, detection.reported_at_s),
          altitude_m_egm2008: height(detection.observer_coordinates?.[2]),
        });
    }
  }
  return {
    type: "FeatureCollection", features,
    metadata: copy({
      schema_version: "patrol-geojson-1", result_sha256: result.sha256, status: result.status,
      coordinate_order: "longitude,latitude", horizontal_reference: "WGS84 / OGC:CRS84",
      vertical_reference: "EGM2008 orthometric metres; stored in properties, not GeoJSON geometry Z",
      export_scope: "original_snapshot_unclipped", time: result.time ?? null,
      target_display: result.target_display || null, profile: result.effective_profile || null,
      planning_profile: result.planning_profile || null, vertical_profile: result.vertical_profile || null,
      diagnostic: result.diagnostic || null, geographic_scene: result.geographic_scene || null,
      evaluation: result.evaluation ? Object.fromEntries(Object.entries(result.evaluation)
        .filter(([key]) => key !== "scenarios" && key !== "first_scenario")) : null,
      simulation: simulation ? Object.fromEntries(Object.entries(simulation).filter(([key]) => key !== "timeline")) : null,
      comparison_history: bundle.comparison_history || [],
    }),
  };
}
