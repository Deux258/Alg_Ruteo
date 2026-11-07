// Pure interpolation and local WGS84 / UTM 19S projection helpers.
export function sampleFlight(timeline, seconds) {
  if (!timeline?.length) return null;
  const time = Math.max(
    timeline[0].time_s,
    Math.min(seconds, timeline.at(-1).time_s),
  );
  let low = 0,
    high = timeline.length - 1;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (timeline[mid].time_s <= time) low = mid;
    else high = mid - 1;
  }
  const a = timeline[low],
    b = timeline[Math.min(low + 1, timeline.length - 1)];
  const f = b.time_s > a.time_s ? (time - a.time_s) / (b.time_s - a.time_s) : 0;
  const mix = (x, y) => x.map((v, i) => v + (y[i] - v) * f);
  const position = mix(a.position_utm, b.position_utm);
  let ahead;
  for (let i = low + 1; i < timeline.length; i++) {
    const p = timeline[i].position_utm;
    if (Math.hypot(p[0] - position[0], p[1] - position[1]) > 8) {
      ahead = p;
      break;
    }
  }
  if (!ahead)
    for (let i = low; i >= 0; i--) {
      const p = timeline[i].position_utm;
      if (Math.hypot(p[0] - position[0], p[1] - position[1]) > 2) {
        ahead = [2 * position[0] - p[0], 2 * position[1] - p[1], position[2]];
        break;
      }
    }
  ahead ??= [position[0], position[1] + 10, position[2]];
  const phase = b.phase === "landed" && time < b.time_s ? "landing" : a.phase;
  const battery =
    a.phase === "battery_swap"
      ? a.battery_pct
      : a.battery_pct + (b.battery_pct - a.battery_pct) * f;
  return {
    time_s: time,
    coordinates: mix(a.coordinates, b.coordinates),
    position_utm: position,
    battery_pct: battery,
    phase,
    look_ahead: ahead,
    index: low,
    ended: time >= timeline.at(-1).time_s,
  };
}

export function projectUTM([lon, lat]) {
  if (
    !Number.isFinite(lon) ||
    !Number.isFinite(lat) ||
    lon < -72 ||
    lon > -66 ||
    lat < -80 ||
    lat > 0
  )
    throw new Error("Coordenadas fuera de UTM 19S");
  const a = 6378137,
    e2 = 0.0066943799901413165,
    k = 0.9996,
    r = Math.PI / 180,
    p = lat * r,
    l = (lon + 69) * r;
  const ep = e2 / (1 - e2),
    sin = Math.sin(p),
    cos = Math.cos(p),
    tan = Math.tan(p),
    n = a / Math.sqrt(1 - e2 * sin * sin),
    t = tan * tan,
    c = ep * cos * cos,
    A = cos * l;
  const e4 = e2 * e2,
    e6 = e4 * e2;
  const m =
    a *
    ((1 - e2 / 4 - (3 * e4) / 64 - (5 * e6) / 256) * p -
      ((3 * e2) / 8 + (3 * e4) / 32 + (45 * e6) / 1024) * Math.sin(2 * p) +
      ((15 * e4) / 256 + (45 * e6) / 1024) * Math.sin(4 * p) -
      ((35 * e6) / 3072) * Math.sin(6 * p));
  return [
    500000 +
      k *
        n *
        (A +
          ((1 - t + c) * A ** 3) / 6 +
          ((5 - 18 * t + t * t + 72 * c - 58 * ep) * A ** 5) / 120),
    10000000 +
      k *
        (m +
          n *
            tan *
            ((A * A) / 2 +
              ((5 - t + 9 * c + 4 * c * c) * A ** 4) / 24 +
              ((61 - 58 * t + t * t + 600 * c - 330 * ep) * A ** 6) / 720)),
  ];
}

export function clockLabel(seconds) {
  const n = Math.max(0, Math.floor(seconds));
  return `${Math.floor(n / 60)
    .toString()
    .padStart(2, "0")}:${(n % 60).toString().padStart(2, "0")}`;
}

// A missing report timestamp is unknown, never the beginning of the flight.
export function detectionProgress(detection, seconds) {
  return {
    detected:
      Number.isFinite(detection?.detected_at_s) &&
      seconds >= detection.detected_at_s,
    reported:
      detection?.report_completed !== false &&
      Number.isFinite(detection?.reported_at_s) &&
      seconds >= detection.reported_at_s,
    incomplete:
      detection?.report_status === "incomplete" ||
      detection?.report_completed === false,
  };
}

export function resilienceSummary(result) {
  const routes = result?.routes || {},
    leaders = result?.resilience_leaders || [];
  if (!leaders.length)
    return "Ninguna técnica tiene una misión viable para comparar resiliencia.";
  const labels = leaders.map((key) => routes[key]?.label || key);
  const four = leaders.length === 4 && Object.keys(routes).length === 4;
  const finding = four
    ? "Empate entre las cuatro técnicas"
    : leaders.length === 1
      ? `Mayor resiliencia estimada: ${labels[0]}`
      : `Empate de mayor resiliencia estimada: ${labels.join(", ")}`;
  const quickest = leaders
    .filter((key) => Number.isFinite(routes[key]?.compute_s))
    .sort((a, b) => routes[a].compute_s - routes[b].compute_s)[0];
  return (
    finding +
    "." +
    (quickest
      ? ` Desempate por tiempo de cómputo: ${routes[quickest].label || quickest} (${routes[quickest].compute_s.toFixed(2)} s).`
      : "") +
    " El orden por duración de misión se muestra por separado."
  );
}

// A response may commit only while its token still owns the corresponding UI task.
// Invalidating a simulation never releases an unrelated long-running calculation.
export function createRequestCoordinator() {
  const tasks = new Map();
  let sequence = 0;
  return {
    start(scope, key = "") {
      tasks.get(scope)?.controller.abort();
      const controller = new AbortController();
      const token = {
        scope,
        key,
        id: ++sequence,
        controller,
        signal: controller.signal,
      };
      tasks.set(scope, token);
      return token;
    },
    current(token) {
      return (
        !!token && tasks.get(token.scope) === token && !token.signal.aborted
      );
    },
    finish(token) {
      if (tasks.get(token.scope) !== token) return false;
      tasks.delete(token.scope);
      return true;
    },
    cancel(...scopes) {
      for (const scope of scopes) {
        tasks.get(scope)?.controller.abort();
        tasks.delete(scope);
      }
    },
    pending(scope) {
      return tasks.has(scope);
    },
  };
}
