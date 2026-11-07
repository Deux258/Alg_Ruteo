import { TerrainView } from "./terrain3d.js";
import {
  sampleFlight,
  projectUTM,
  clockLabel,
  createRequestCoordinator,
  detectionProgress,
  resilienceSummary,
} from "./flight-player.js";
import { normalizeTarget, circlePolygon } from "./patrol-editing.js";
import {
  metadataPopup as popup,
  stationVisibleInCommune,
  threatDisplayPosition,
} from "./patrol-presentation.js";
const $ = (id) => document.getElementById(id);
const colors = {
  dijkstra_distance: "#326b99",
  dijkstra_weighted: "#237c55",
  gurobi: "#b17724",
  annealing: "#90508d",
  alt_1: "#326b99",
  alt_2: "#237c55",
  alt_3: "#b17724",
  alt_4: "#90508d",
};
const rgb = (hex) =>
  [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
const map = L.map("map", { preferCanvas: true }).setView([-33.085, -71.63], 13);
const localBase = L.layerGroup();
let osmBase;
const geographicLayers = {},
  geographicVisibility = {};
const geographicNames = {
  buildings: "Edificios",
  water: "Agua y cursos",
  landcover: "Cobertura del suelo",
  trees: "Árboles y copas",
  roads: "Calles y caminos",
  contours: "Curvas de nivel · 20 m",
};
const geographicColors = {
  buildings: "#998772",
  water: "#3d8fb5",
  landcover: "#799557",
  trees: "#3b6d45",
  roads: "#817967",
  contours: "#83704c",
};
const uncertaintyLayer = L.layerGroup(),
  metadataNodes = L.layerGroup(),
  catalogueLayer = L.layerGroup(),
  weatherLayer = L.layerGroup().addTo(map);
const selection = L.layerGroup().addTo(map),
  eventsLayer = L.layerGroup().addTo(map),
  fireLayer = L.layerGroup().addTo(map),
  flightLayer = L.layerGroup().addTo(map);
let fresh = false;
let model,
  result,
  simulation,
  target,
  fire,
  mode = "",
  vertices = [],
  events = [],
  routes = {},
  visible = {},
  view3d,
  terrainView,
  drone,
  clock = 0,
  lastFrame = 0,
  playing = false;
let sourceLayers = {},
  activeIds = new Set(),
  comparisonHistory = [];
let calculating = false,
  simulationLoading = false,
  configurationRevision = 0,
  lastRender = 0,
  lastFollow = 0,
  lastLog = "";
let displayModel,
  constraintAssessment = null,
  validationTimer,
  nodesLoadedFor = "",
  geographyReady = false,
  simulationRevision = 0,
  visibleThreats = [],
  viewDesired = false,
  sceneKey = "";
const candidateBasesLayer = L.layerGroup().addTo(map);
const requests = createRequestCoordinator();
const displayedRoutes = () =>
  !result
    ? {}
    : $("route-mode").value === "comparison"
      ? result.routes
      : result.route_alternatives || {};
const displayedRecommended = () =>
  $("route-mode").value === "comparison"
    ? result?.recommended || []
    : result?.alternative_recommended || [];
const message = (text, error = false) => {
  $("message").textContent = text;
  $("message").classList.toggle("error", error);
};
async function api(url, body, options = {}) {
  const r = await fetch(
    url,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: options.signal,
        }
      : { signal: options.signal },
  );
  const value = await r.json();
  if (!r.ok) {
    const error = new Error(value.error || "Servicio no disponible");
    error.status = r.status;
    throw error;
  }
  return value;
}
const aborted = (error) => error?.name === "AbortError";
const resourceUrl = (resource) =>
  typeof resource === "string" ? resource : resource?.url;
const communeId = () => $("commune").value;
function filteredUrl(url) {
  if (!communeId()) return url;
  const target = new URL(url, location.href);
  target.searchParams.set("commune_id", communeId());
  return target.pathname + target.search;
}
function cancelSimulation() {
  simulationRevision++;
  requests.cancel("simulation", "fpv");
  simulationLoading = false;
  playing = false;
  simulation = null;
  flightLayer.clearLayers();
  drone = null;
  clock = 0;
  lastFrame = 0;
  lastLog = "";
  exitDroneView();
  terrainView?.setMarker(null);
  $("log").replaceChildren();
  $("progress").value = 0;
  $("replan").disabled = true;
  refreshPlaybackControls();
}
function simulationChanged() {
  cancelSimulation();
}
function updateBudgetNote(assessment = constraintAssessment?.constraints) {
  const p = assessment?.effective_profile || model?.profile;
  if (!p) return;
  const useful =
    assessment?.battery_budget_s ??
    Number($("battery").value || p.battery_budget_s);
  const reserve =
    assessment?.report_reserve_s ??
    assessment?.verification_reserve_s ??
    p.verification_s;
  const flight = assessment?.flight_budget_s ?? Math.max(0, useful - reserve);
  const total =
    assessment?.mission_budget_s ??
    Number($("budget").value || p.mission_budget_s);
  const missionFlight =
    assessment?.mission_flight_budget_s ?? Math.max(0, total - reserve);
  $("budget-note").textContent =
    `Batería útil: ${useful} s = ${flight} s de vuelo + ${reserve} s de reporte por batería. Misión: ${total} s = ${missionFlight} s planificables + ${reserve} s de reporte, reservados una vez.`;
}
async function validateCurrent() {
  if (!model) return null;
  clearTimeout(validationTimer);
  const token = requests.start("validation", configurationRevision),
    revision = configurationRevision;
  try {
    const value = await api("/api/aereo/patrullaje/validar", request(), {
      signal: token.signal,
    });
    if (!requests.current(token) || revision !== configurationRevision)
      return null;
    constraintAssessment = value;
    updateBudgetNote(value.constraints);
    wind();
    const reasons = value.violations || value.constraints?.reasons || [];
    $("constraint-status").textContent = value.valid
      ? "Perfil y hora admitidos."
      : reasons.map((r) => r.message).join(" ");
    $("constraint-status").classList.toggle("error", !value.valid);
    return value;
  } catch (error) {
    if (!aborted(error) && requests.current(token)) {
      $("constraint-status").textContent = error.message;
      constraintAssessment = null;
    }
    return null;
  } finally {
    if (requests.finish(token)) refreshPlaybackControls();
  }
}
function scheduleValidation() {
  clearTimeout(validationTimer);
  constraintAssessment = null;
  updateBudgetNote();
  validationTimer = setTimeout(() => validateCurrent(), 200);
}
function loadGeography() {
  const geo = (displayModel || model)?.geography;
  if (!geo) return;
  if (!osmBase) {
    osmBase = L.tileLayer(geo.tile_url, {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      crossOrigin: true,
    }).addTo(map);
    let tileErrors = 0;
    osmBase.on("loading", () => (tileErrors = 0));
    osmBase.on("tileerror", () => {
      tileErrors++;
      $("tile-status").textContent =
        "Tesela OSM no disponible. Las capas vectoriales locales siguen disponibles.";
    });
    osmBase.on("load", () => {
      $("tile-status").textContent = tileErrors
        ? "Carga parcial de OpenStreetMap. Las capas locales siguen disponibles."
        : "OpenStreetMap · calles, nombres y lugares. Capas locales superpuestas.";
    });
    map.attributionControl.addAttribution(
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    );
    map.attributionControl.addAttribution("CONAF · Copernicus GLO-30");
  }
  for (const [key, title] of Object.entries(geographicNames)) {
    if (!geographicLayers[key]) {
      geographicLayers[key] = L.geoJSON(null, {
        style: (f) => ({
          color: geographicColors[key],
          weight:
            key === "roads"
              ? 1.3
              : key === "contours"
                ? f.properties.index
                  ? 1
                  : 0.5
                : 0.7,
          fillColor: geographicColors[key],
          fillOpacity:
            key === "water" ? 0.55 : key === "landcover" ? 0.17 : 0.45,
          opacity: key === "contours" ? 0.5 : 0.8,
        }),
        pointToLayer: (_, c) =>
          L.circleMarker(c, {
            radius: 3,
            color: geographicColors[key],
            weight: 1,
            fillOpacity: 0.8,
          }),
        onEachFeature: (f, layer) =>
          layer.bindPopup(() =>
            popup(
              `${title}${f.properties.name ? " · " + f.properties.name : ""}`,
              {
                ...f.properties,
                height_note: f.properties.height_estimated
                  ? "Altura estimada; consultar height_basis"
                  : f.properties.height_m
                    ? "Altura etiquetada en OSM"
                    : undefined,
              },
            ),
          ),
      }).addTo(map);
      geographicVisibility[key] = true;
      const label = document.createElement("label");
      label.className = "check geography-check";
      const check = document.createElement("input");
      check.type = "checkbox";
      check.id = `geo-${key}`;
      check.checked = true;
      const swatch = document.createElement("i");
      swatch.style.background = geographicColors[key];
      const text = document.createElement("span");
      text.textContent = title;
      const count = document.createElement("small");
      count.id = `count-${key}`;
      label.append(check, swatch, text, count);
      $("geography-controls").append(label);
      check.onchange = () => {
        geographicVisibility[key] = check.checked;
        check.checked
          ? geographicLayers[key].addTo(map)
          : map.removeLayer(geographicLayers[key]);
        terrainView?.setLayer(key, check.checked);
      };
    }
    geographicLayers[key].clearLayers();
    $("count-" + key).textContent = (geo.counts?.[key] ?? 0).toLocaleString();
  }
  $("geography-status").textContent =
    `${(geo.counts?.buildings ?? 0).toLocaleString()} edificios · ${(geo.counts?.water ?? 0).toLocaleString()} áreas/cursos de agua · ${(geo.counts?.landcover ?? 0).toLocaleString()} coberturas · ${(geo.counts?.trees ?? 0).toLocaleString()} árboles o hileras mapeados.`;
  $("geography-source").textContent =
    `OSM: ${geo.source?.timestamp_osm_base || geo.source?.fetched_at_utc || "fecha no disponible"}. Catastro CONAF 2019 y DSM Copernicus ≈30 m. ${(geo.height_estimates ?? 0).toLocaleString()} alturas estimadas; ${(geo.woodland_symbols ?? 0).toLocaleString()} símbolos de copas en bosques. La ausencia de objetos no garantiza despeje.`;
  $("export-geography").disabled = true;
}
async function layerData(manifest, key, signal) {
  const url = resourceUrl(manifest.resources?.layers?.[key]);
  if (url) return api(url, undefined, { signal });
  if (manifest.geography?.layers?.[key]) return manifest.geography.layers[key];
  const rows = key === "M1" ? manifest.base_catalogue : manifest.layers?.[key];
  return {
    type: "FeatureCollection",
    features: (rows || []).map((row) => ({
      type: "Feature",
      geometry: row.geometry,
      properties: Object.fromEntries(
        Object.entries(row).filter(([k]) => k !== "geometry"),
      ),
    })),
  };
}
function applyCatalogue(rows) {
  catalogueLayer.clearLayers();
  candidateBasesLayer.clearLayers();
  for (const b of rows) {
    const coordinate = b.geometry.coordinates;
    L.circleMarker([coordinate[1], coordinate[0]], {
      radius: 4,
      color: "#7b7056",
    })
      .bindPopup(() => popup("Catálogo M1", b))
      .addTo(catalogueLayer);
    if (b.candidate !== false)
      L.circleMarker([coordinate[1], coordinate[0]], {
        radius: 6,
        color: "#ae791c",
        fillOpacity: 0.8,
      })
        .bindPopup(() => popup(b.name, { ...b, hypothetical_station: true }))
        .addTo(candidateBasesLayer);
  }
}
async function refreshMapVisuals() {
  const cut = communeId(),
    token = requests.start("map", cut);
  requests.cancel("nodes");
  nodesLoadedFor = "";
  metadataNodes.clearLayers();
  $("geography-status").setAttribute("aria-busy", "true");
  for (const layer of Object.values(sourceLayers)) layer.clearLayers();
  catalogueLayer.clearLayers();
  candidateBasesLayer.clearLayers();
  visibleThreats = [];
  refreshUnknown();
  try {
    const manifest = cut
      ? await api(
          "/api/aereo/patrullaje/mapa?view=summary&commune_id=" +
            encodeURIComponent(cut),
          undefined,
          { signal: token.signal },
        )
      : model;
    if (!requests.current(token) || cut !== communeId()) return;
    displayModel = { ...manifest, layers: {} };
    loadGeography();
    const keys = [
      "M1",
      "M2",
      "A2",
      "A3",
      "A4",
      ...Object.keys(geographicNames),
    ];
    const loaded = await Promise.allSettled(
      keys.map(async (key) => {
        const data = await layerData(manifest, key, token.signal);
        if (!requests.current(token) || cut !== communeId()) return;
        if (geographicLayers[key])
          geographicLayers[key].clearLayers().addData(data);
        else {
          const rows = (data.features || []).map((f) => ({
            ...f.properties,
            geometry: f.geometry,
          }));
          displayModel.layers[key] = rows;
          if (key === "M1") applyCatalogue(rows);
          else refreshSources();
        }
      }),
    );
    if (!requests.current(token)) return;
    const failures = loaded.filter(
      (r) => r.status === "rejected" && !aborted(r.reason),
    );
    if (failures.length)
      message(
        "Algunas capas no se pudieron cargar. Vuelve a seleccionar la comuna para reintentarlo.",
        true,
      );
    geographyReady = !failures.length;
    $("export-geography").disabled = !geographyReady;
    if (viewDesired) await setView3d(true, true);
    if (map.hasLayer(metadataNodes)) loadNodes();
    refreshSources();
  } catch (error) {
    if (!aborted(error)) message(error.message, true);
  } finally {
    if (requests.finish(token))
      $("geography-status").setAttribute("aria-busy", "false");
  }
}
$("base-style").onchange = () => {
  if (!osmBase) return;
  if ($("base-style").value === "osm") {
    map.removeLayer(localBase);
    osmBase.addTo(map);
    $("tile-status").textContent = "Cargando OpenStreetMap…";
  } else {
    map.removeLayer(osmBase);
    localBase.addTo(map);
    $("tile-status").textContent =
      "Cartografía local activa: calles, edificios y entorno disponibles sin teselas externas.";
  }
};
$("export-geography").onclick = async () => {
  if (!displayModel) return;
  const token = requests.start("export-map", communeId());
  $("export-geography").disabled = true;
  try {
    const layers = await Promise.all(
      [...Object.keys(geographicNames)].map((key) =>
        layerData(model, key, token.signal),
      ),
    );
    if (requests.current(token))
      download("entorno_geografico_original.geojson", {
        type: "FeatureCollection",
        features: layers.flatMap((layer) => layer.features),
        metadata: {
          sha256: model.geography.sha256,
          source: model.geography.source,
          display_commune_id: communeId(),
          export_scope: "original_snapshot_unclipped",
          assumptions: model.geography.assumptions,
        },
      });
  } catch (error) {
    if (!aborted(error)) message(error.message, true);
  } finally {
    if (requests.finish(token))
      $("export-geography").disabled = !geographyReady;
  }
};
$("terrain-reset").onclick = () => {
  exitDroneView();
  $("follow-drone").checked = false;
  terrainView?.reset();
};
$("terrain-mission").onclick = () => {
  exitDroneView();
  $("follow-drone").checked = false;
  terrainView?.focusRoutes();
};
function invalidate() {
  configurationRevision++;
  constraintAssessment = null;
  clearTimeout(validationTimer);
  requests.cancel(
    "validation",
    "nodes",
    "export",
    "probabilities",
    "threats",
    "import",
  );
  nodesLoadedFor = "";
  visibleThreats = [];
  activeIds.clear();
  cancelSimulation();
  fresh = false;
  Object.values(routes).forEach((layer) => map.removeLayer(layer));
  routes = {};
  metadataNodes.clearLayers();
  $("results").replaceChildren();
  $("chosen").replaceChildren();
  $("flight").textContent = "Sin vuelo activo.";
  $("export").disabled = true;
  $("failures").disabled = true;
  refreshSources();
  update3d();
  refreshPlaybackControls();
  scheduleValidation();
  message(
    calculating
      ? "La configuración cambió. El cálculo en curso terminará sin sustituir el nuevo objetivo."
      : "Configuración cambiada. Vuelve a comparar las técnicas.",
  );
}
function setTarget(geo) {
  const g = normalizeTarget(geo);
  target = g;
  mode = "";
  $("finish").disabled = true;
  $("draw-tools").hidden = true;
  fire = null;
  fireLayer.clearLayers();
  $("fire-status").textContent = "Sin foco sintético.";
  $("focus-target").disabled = false;
  selection.clearLayers();
  L.geoJSON(g, {
    style: {
      color: "#255e40",
      weight: 2,
      fillColor: "#78a96b",
      fillOpacity: 0.15,
    },
  }).addTo(selection);
  $("area-status").textContent =
    "Objetivo poligonal listo · barrido completo con radio de 100 m.";
  invalidate();
  focusTarget();
}
$("draw").onclick = () => {
  if (view3d) setView3d(false);
  map.stop();
  map.closePopup();
  mode = "polygon";
  vertices = [];
  selection.clearLayers();
  configurationRevision++;
  requests.cancel("import");
  cancelSimulation();
  refreshPlaybackControls();
  $("finish").disabled = true;
  $("draw-tools").dataset.vertices = "0";
  $("draw-tools").hidden = false;
  message("Marca los vértices del objetivo y pulsa Cerrar polígono.");
};
$("finish").onclick = () => {
  if (vertices.length < 3)
    return message("Se necesitan al menos tres vértices.", true);
  try {
    setTarget({ type: "Polygon", coordinates: [[...vertices, vertices[0]]] });
    mode = "";
    $("finish").disabled = true;
  } catch (e) {
    message(e.message, true);
  }
};
$("import").onchange = async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const token = requests.start("import");
  try {
    let g = JSON.parse(await file.text());
    if (!requests.current(token)) return;
    setTarget(g);
    map.fitBounds(selection.getBounds?.() || L.geoJSON(target).getBounds());
  } catch (err) {
    if (requests.current(token)) message(err.message, true);
  } finally {
    requests.finish(token);
    e.target.value = "";
  }
};
$("demo").onclick = () => {
  if (!model?.demo_polygon)
    return message(
      "No hay un ejemplo geométrico disponible; dibuja un objetivo.",
      true,
    );
  setTarget(model.demo_polygon);
  map.fitBounds(L.geoJSON(target).getBounds().pad(1), { animate: false });
};
$("fire").onclick = () => {
  if (view3d) setView3d(false);
  mode = "fire";
  message("Marca un foco sintético dentro del polígono objetivo.");
};
$("clear-fire").onclick = () => {
  fire = null;
  fireLayer.clearLayers();
  simulationChanged();
  update3d();
  $("fire-status").textContent = "Sin foco sintético.";
};
$("hazard").onclick = () => {
  if (view3d) setView3d(false);
  mode = "hazard";
  message(
    "Marca el centro de una amenaza sintética; luego recalcula las rutas.",
  );
};
$("clear-hazards").onclick = () => {
  events = [];
  eventsLayer.clearLayers();
  invalidate();
};
$("hazard-coordinate-add").onclick = () => {
  const c = $("hazard-coordinates").value.split(",").map(Number),
    r = Number($("radius").value),
    p = Number($("probability").value);
  if (
    c.length !== 2 ||
    c.some((v) => !Number.isFinite(v)) ||
    Math.abs(c[0]) > 180 ||
    Math.abs(c[1]) >= 90 ||
    !(r > 0 && r <= 500 && p >= 0 && p <= 100)
  )
    return message("Revisa coordenadas, radio y probabilidad.", true);
  events.push({ geometry: circlePolygon(...c, r), probability_pct: p });
  drawEvents();
  invalidate();
};
function editMapAt(e) {
  const c = [e.latlng.lng, e.latlng.lat];
  if (mode === "polygon") {
    vertices.push(c);
    redrawVertices();
  } else if (mode === "fire") {
    fire = c;
    fireLayer.clearLayers();
    L.marker(e.latlng, {
      icon: L.divIcon({
        className: "drone-icon",
        html: "♨",
        iconSize: [25, 25],
      }),
    })
      .addTo(fireLayer)
      .bindPopup(popup("Foco sintético", { coordinates: c }));
    $("fire-status").textContent =
      `Foco de demostración: ${c.map((v) => v.toFixed(5)).join(", ")}`;
    mode = "";
    simulationChanged();
    update3d();
  } else if (mode === "hazard") {
    const radius = Number($("radius").value),
      probability = Number($("probability").value);
    if (
      !(radius > 0 && radius <= 500 && probability >= 0 && probability <= 100)
    )
      return message("Revisa radio y probabilidad.", true);
    events.push({
      geometry: circlePolygon(...c, radius),
      probability_pct: probability,
    });
    mode = "";
    drawEvents();
    invalidate();
  }
}
map.on("click", editMapAt);
// Interactive geographic layers consume Leaflet clicks to open their popups.
// Editing receives native clicks first, while controls and dragging keep working.
let editPointer = null;
const mapContainer = map.getContainer(),
  editingMap = () => ["polygon", "fire", "hazard"].includes(mode);
mapContainer.addEventListener(
  "pointerdown",
  (event) => {
    if (!editingMap() || event.button !== 0) return;
    editPointer = { x: event.clientX, y: event.clientY, moved: false };
  },
  true,
);
mapContainer.addEventListener(
  "pointermove",
  (event) => {
    if (
      editPointer &&
      Math.hypot(event.clientX - editPointer.x, event.clientY - editPointer.y) >
        5
    )
      editPointer.moved = true;
  },
  true,
);
mapContainer.addEventListener(
  "pointercancel",
  () => (editPointer = null),
  true,
);
mapContainer.addEventListener(
  "click",
  (event) => {
    const pointer = editPointer;
    editPointer = null;
    if (
      !editingMap() ||
      event.button !== 0 ||
      event.target.closest(".leaflet-control,.leaflet-popup")
    )
      return;
    L.DomEvent.stop(event);
    map.closePopup();
    if (pointer?.moved) return;
    editMapAt({ latlng: map.mouseEventToLatLng(event) });
  },
  true,
);
function drawEvents() {
  eventsLayer.clearLayers();
  const displayed =
    fresh && result
      ? visibleThreats.filter((row) => row.id.startsWith("synthetic:"))
      : events.map((event, i) => ({ ...event, id: `synthetic:${i}` }));
  displayed.forEach((event) => {
    if ($("active-only").checked && !activeIds.has(event.id)) return;
    L.geoJSON(event.geometry, {
      style: {
        color: "#a5572b",
        weight: 2,
        dashArray: "4 3",
        fillOpacity: 0.2,
      },
    })
      .bindPopup(
        popup("Amenaza sintética", {
          id: event.id,
          probability_pct: event.probability_pct,
        }),
      )
      .addTo(eventsLayer);
  });
}
function stationIds() {
  return [...document.querySelectorAll("#stations input:checked")].map(
    (i) => i.value,
  );
}
function request() {
  return {
    origin: model.bases[Number($("base").value)].geometry.coordinates,
    target_polygon: target,
    time: $("weather").value,
    station_ids: stationIds(),
    events,
    seed: Number($("seed").value),
    scenarios: 1000,
    preferences: {
      altitude_agl_m: Number($("altitude").value),
      wind_limit_ms: Number($("wind").value),
      battery_budget_s: Number($("battery").value),
      mission_budget_s: Number($("budget").value),
      risk_weight: Number($("risk").value),
      historical_multiplier: Number($("history").value),
    },
  };
}
function busy(value) {
  calculating = value;
  $("calculate").textContent = value
    ? "Calculando técnicas y corredores diferentes…"
    : "Comparar las cuatro técnicas";
  refreshPlaybackControls();
}
async function resolveRouteGeometry(answer, signal) {
  const groups = {
    comparison: answer.routes || {},
    alternatives: answer.route_alternatives || {},
  };
  await Promise.all(
    Object.entries(groups).flatMap(([group, rows]) =>
      Object.entries(rows).map(async ([key, row]) => {
        if (!row.geometry_deferred) return;
        const url = resourceUrl(answer.resources?.routes?.[group]?.[key]);
        if (!url)
          throw new Error(
            "La geometría de una ruta no está disponible. Vuelve a calcular.",
          );
        Object.assign(row, await api(url, undefined, { signal }));
      }),
    ),
  );
}
async function calculate(overrides = null) {
  if (
    !model ||
    !target ||
    calculating ||
    simulationLoading ||
    mode === "polygon"
  )
    return;
  const revision = configurationRevision,
    token = requests.start("calculation", revision);
  cancelSimulation();
  fresh = false;
  busy(true);
  message("Verificando restricciones y preparando la misión…");
  try {
    const assessment = await validateCurrent();
    if (!requests.current(token) || revision !== configurationRevision) return;
    if (!assessment) {
      message("No se pudieron comprobar las restricciones. Reintenta.", true);
      return;
    }
    // The backend returns a blocked result with probabilities and diagnostics.
    // Weather/energy failures must remain reviewable and exportable.
    if (result)
      comparisonHistory.push({
        sha256: result.sha256,
        routes: Object.fromEntries(
          Object.entries(result.routes).map(([key, row]) => [
            key,
            {
              status: row.status,
              resilience: row.resilience,
              time_s: row.time_s,
            },
          ]),
        ),
      });
    message(
      "Construyendo grafo, comparando técnicas y evaluando cobertura. Puede tardar unos minutos.",
    );
    const answer = await api(
      "/api/aereo/patrullaje?view=summary",
      { ...request(), ...(overrides || {}) },
      { signal: token.signal },
    );
    if (!requests.current(token) || revision !== configurationRevision) return;
    await resolveRouteGeometry(answer, token.signal);
    if (!requests.current(token) || revision !== configurationRevision) {
      message("La configuración cambió durante el cálculo. Vuelve a comparar.");
      return;
    }
    result = answer;
    fresh = true;
    activeIds.clear();
    if (result.status === "blocked") $("route-mode").value = "comparison";
    renderResults();
    refreshPlaybackControls();
    message(
      result.status === "blocked"
        ? "Misión bloqueada: " +
            (result.diagnostic?.reasons || result.constraints?.reasons || [])
              .map((reason) =>
                typeof reason === "string" ? reason : reason.message,
              )
              .join(" ") +
            ". Puedes exportar las probabilidades y el diagnóstico."
        : `${result.network.nodes.toLocaleString()} nodos · ${result.network.directed_edges.toLocaleString()} arcos · ${result.diversity.count} circuitos distintos validados.`,
      result.status === "blocked",
    );
    refreshSources();
    refreshThreats();
    if (map.hasLayer(metadataNodes)) loadNodes();
  } catch (error) {
    if (!aborted(error)) message(error.message, true);
  } finally {
    if (requests.finish(token)) busy(false);
  }
}
$("calculate").onclick = () => calculate();
function renderResults() {
  Object.values(routes).forEach((l) => map.removeLayer(l));
  routes = {};
  $("results").replaceChildren();
  const previousChoice = $("chosen").value;
  $("chosen").replaceChildren();
  const available = displayedRoutes();
  const timed = Object.entries(available).filter(
    ([, row]) => row.status === "ready" && Number.isFinite(row.time_s),
  );
  for (const [key, r] of Object.entries(available)) {
    const card = document.createElement("div");
    card.className = "route-card";
    card.style.setProperty("--route", colors[key]);
    const title = document.createElement("div");
    title.className = "route-title";
    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = true;
    check.id = `show-${key}`;
    visible[key] = true;
    const label = document.createElement("button");
    label.type = "button";
    label.className = "route-choice";
    label.textContent = r.label;
    label.onclick = () => {
      if (r.status !== "ready") return;
      $("chosen").value = key;
      changeRoute();
    };
    title.append(check, label);
    const rank =
      r.status === "ready"
        ? 1 +
          timed.filter(([, other]) => other.time_s < r.time_s - 0.001).length
        : 0;
    if (rank > 0) {
      const b = document.createElement("span");
      b.className = "rank";
      b.textContent = `TIEMPO #${rank}`;
      title.append(b);
    }
    card.dataset.route = key;
    card.append(title);
    if (r.coordinates.length) {
      routes[key] = L.polyline(
        r.coordinates.map((c) => [c[1], c[0]]),
        {
          color: colors[key],
          weight: 3 + (3 - Object.keys(available).indexOf(key)),
          opacity: 0.8,
          dashArray:
            key === "dijkstra_distance"
              ? "8 5"
              : key === "annealing"
                ? "3 5"
                : null,
        },
      )
        .addTo(map)
        .bindPopup(
          popup(r.label, {
            status: r.status,
            compute_s: r.compute_s,
            coverage: r.coverage,
            resilience: r.resilience,
            solver: r.solver,
          }),
        );
    }
    check.onchange = () => {
      visible[key] = check.checked;
      if (routes[key])
        check.checked ? routes[key].addTo(map) : map.removeLayer(routes[key]);
      update3d();
    };
    const metrics = document.createElement("div");
    metrics.className = "metrics";
    for (const [value, caption] of [
      [
        r.resilience ? (100 * r.resilience.value).toFixed(1) + " %" : "—",
        `Resiliencia · ${r.resilience?.scenarios ?? result.evaluation?.count ?? 1000} escenarios`,
      ],
      [
        r.time_s === null ? "—" : (r.time_s / 60).toFixed(1) + " min",
        "Tiempo de misión",
      ],
      [
        r.compute_s.toFixed(2) + " s",
        $("route-mode").value === "alternatives"
          ? "Generación acumulada"
          : "Cómputo",
      ],
      [
        r.coverage ? r.coverage.percent.toFixed(1) + " %" : "—",
        "Cobertura de celdas",
      ],
    ]) {
      const cell = document.createElement("div");
      const b = document.createElement("b");
      b.textContent = value;
      const s = document.createElement("span");
      s.textContent = caption;
      cell.append(b, s);
      metrics.append(cell);
    }
    card.append(metrics);
    const leaders = result.resilience_leaders || [];
    if ($("route-mode").value === "comparison" && leaders.includes(key)) {
      const leader = document.createElement("p");
      leader.className = "resilience-leader";
      leader.textContent =
        leaders.length > 1 ? "Mayor resiliencia · empate" : "Mayor resiliencia";
      card.append(leader);
    }
    if (r.resilience?.confidence_interval) {
      const interval = document.createElement("p");
      interval.className = "muted";
      interval.textContent = `IC 95 %: ${(100 * r.resilience.confidence_interval.low).toFixed(1)}–${(100 * r.resilience.confidence_interval.high).toFixed(1)} %`;
      card.append(interval);
    }
    if (r.timings && $("route-mode").value === "comparison") {
      const timing = document.createElement("p");
      timing.className = "muted";
      timing.textContent = `Conectores: ${Number(r.timings.connectors_s || 0).toFixed(2)} s · resolución: ${Number(r.timings.solve_s || 0).toFixed(2)} s · validación: ${Number(r.timings.validation_s || 0).toFixed(2)} s. Caché de conectores independiente.`;
      card.append(timing);
    }

    const note = document.createElement("p");
    const engineLabel =
      r.solver.engine === "comparison_result"
        ? "Referencia"
        : r.solver.engine === "diverse_dijkstra"
          ? "Corredor diversificado"
          : r.solver.engine;
    note.textContent = `${r.status} · ${r.distance_m === null ? "sin recorrido" : (r.distance_m / 1000).toFixed(2) + " km"} · ${r.stops.length} recargas${engineLabel ? " · " + engineLabel : ""}${r.solver.status ? " · solver " + r.solver.status : ""}${r.solver.gap != null ? " · gap " + (100 * r.solver.gap).toFixed(2) + " %" : ""}`;
    card.append(note);
    if (r.diversity) {
      const shared = document.createElement("p");
      shared.textContent =
        r.solver.engine === "comparison_result"
          ? "Circuito de referencia · resultado original de la técnica."
          : `Corredor alternativo · hasta ${(100 * r.diversity.max_shared_transit).toFixed(0)} % de tránsito compartido con los anteriores.`;
      card.append(shared);
    }
    if (r.solver.reason) {
      const error = document.createElement("p");
      error.textContent = r.solver.reason;
      card.append(error);
    }
    $("results").append(card);
    if (r.status === "ready") $("chosen").append(new Option(r.label, key));
  }
  const recommended = displayedRecommended();
  $("chosen").value =
    available[previousChoice]?.status === "ready"
      ? previousChoice
      : recommended[0] || "";
  $("diversity-note").textContent =
    $("route-mode").value === "alternatives"
      ? `${result.diversity.count} circuitos diferentes. Comparten el barrido del objetivo; el tránsito se compara con tolerancia de ${result.diversity.tolerance_m ?? 12} m.${result.diversity.reason ? " " + result.diversity.reason : ""}`
      : "Resultados originales por técnica. Si coinciden en el óptimo, pueden compartir exactamente el mismo recorrido.";
  renderResilienceSummary();
  markSelection();
  refreshPlaybackControls();
  if (view3d) terrainView?.focusRoutes();
  else if (Object.keys(routes).length)
    map.fitBounds(L.featureGroup(Object.values(routes)).getBounds().pad(0.15), {
      maxZoom: 17,
    });
  $("network").textContent =
    `≤ ${result.network.max_horizontal_link_m.toFixed(0)} m`;
  update3d();
}
function renderResilienceSummary() {
  $("resilience-summary").textContent =
    resilienceSummary(result) +
    (Number.isFinite(result?.timings?.setup_s)
      ? ` Preparación común: ${result.timings.setup_s.toFixed(2)} s.`
      : "");
}
function meshHeight(x, y) {
  const m = model?.terrain;
  if (!m) return null;
  const ix = (x - m.origin_utm[0]) / (m.x[1] - m.x[0]),
    iy = (y - m.origin_utm[1]) / (m.y[1] - m.y[0]);
  if (ix < 0 || iy < 0 || ix > m.width - 1 || iy > m.height - 1) return null;
  return m.elevations[Math.round(iy) * m.width + Math.round(ix)] ?? null;
}
function targetPoints() {
  if (!target) return [];
  return target.coordinates[0]
    .map((c) => {
      const [x, y] = projectUTM(c);
      return [x, y, meshHeight(x, y)];
    })
    .filter((p) => p[2] !== null);
}
function update3d() {
  if (!terrainView) return;
  const lines = [];
  if (fresh && result) {
    for (const [key, r] of Object.entries(displayedRoutes()))
      if (visible[key] && r.coordinates_utm?.length)
        lines.push({
          points: r.coordinates_utm,
          color: rgb(colors[key]),
          width: key === $("chosen").value ? 4 : 2,
        });
    for (const station of result.stations || []) {
      const p = station.position_utm;
      if (
        p &&
        stationVisibleInCommune(station, displayModel?.bases, communeId())
      )
        lines.push({ points: [p], color: [0.9, 0.65, 0.1], point: true });
    }
    for (const threat of visibleThreats) {
      const p = threatDisplayPosition(threat, projectUTM, meshHeight);
      if (p && (!$("active-only").checked || activeIds.has(threat.id)))
        lines.push({ points: [p], color: [0.8, 0.25, 0.15], point: true });
    }
  }
  if (target) {
    const ring = target.coordinates[0].map(projectUTM);
    let outline = [];
    const flush = () => {
      if (outline.length > 1)
        lines.push({
          points: outline,
          color: [0.85, 0.35, 0.08],
          width: 3,
          target: true,
        });
      outline = [];
    };
    for (let i = 1; i < ring.length; i++) {
      const a = ring[i - 1],
        b = ring[i],
        count = Math.max(
          1,
          Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / 15),
        );
      for (let j = 0; j <= count; j++) {
        const t = j / count,
          x = a[0] + (b[0] - a[0]) * t,
          y = a[1] + (b[1] - a[1]) * t,
          z = meshHeight(x, y);
        if (z === null) {
          flush();
          continue;
        }
        outline.push([x, y, z + 3]);
      }
    }
    flush();
  }
  if (fire) {
    const [x, y] = projectUTM(fire),
      z = meshHeight(x, y);
    if (z !== null)
      lines.push({
        points: [[x, y, z + 8]],
        color: [1, 0.2, 0.05],
        point: true,
      });
  }
  terrainView.setRoutes(lines);
}
async function refreshThreats() {
  requests.cancel("threats");
  visibleThreats = [];
  refreshUnknown();
  if (!fresh || !result) return;
  const previous = result,
    cut = communeId(),
    token = requests.start("threats", previous.sha256 + cut);
  try {
    const url = resourceUrl(previous.resources?.amenazas);
    const value = url
      ? await api(
          filteredUrl(
            `/api/aereo/patrullaje/resultados/${previous.sha256}/amenazas`,
          ),
          undefined,
          { signal: token.signal },
        )
      : { threats: previous.threats || [] };
    if (!requests.current(token) || result !== previous || cut !== communeId())
      return;
    visibleThreats = value.threats || [];
    refreshUnknown();
    drawEvents();
    update3d();
  } catch (error) {
    if (!aborted(error)) message(error.message, true);
  } finally {
    requests.finish(token);
  }
}
async function loadNodes() {
  if (!fresh || !result || !map.hasLayer(metadataNodes)) return;
  const previous = result,
    cut = communeId(),
    key = previous.sha256 + ":" + cut;
  if (nodesLoadedFor === key) return;
  const token = requests.start("nodes", key);
  try {
    const url = resourceUrl(previous.resources?.nodos);
    const data = url
      ? await api(
          filteredUrl(
            `/api/aereo/patrullaje/resultados/${previous.sha256}/nodos`,
          ),
          undefined,
          { signal: token.signal },
        )
      : previous.graph;
    if (
      !requests.current(token) ||
      result !== previous ||
      cut !== communeId() ||
      !map.hasLayer(metadataNodes)
    )
      return;
    metadataNodes.clearLayers();
    for (const n of data?.nodes || [])
      L.circleMarker([n.coordinates[1], n.coordinates[0]], {
        radius: 2,
        color: "#637963",
        weight: 1,
      })
        .bindPopup(() =>
          popup("Superficie · DSM y obstáculos", {
            node_id: n.id,
            modeled_surface_elevation_m:
              n.coordinates[2] - previous.effective_profile.altitude_agl_m,
            flight_height_egm2008_m: n.coordinates[2],
            altitude_agl_m: previous.effective_profile.altitude_agl_m,
          }),
        )
        .addTo(metadataNodes);
    nodesLoadedFor = key;
  } catch (error) {
    if (!aborted(error)) message(error.message, true);
  } finally {
    requests.finish(token);
  }
}
map.on("overlayadd", (event) => {
  if (event.layer === metadataNodes) loadNodes();
});
map.on("overlayremove", (event) => {
  if (event.layer === metadataNodes) requests.cancel("nodes");
});
function exitDroneView() {
  requests.cancel("fpv");
  terrainView?.setFirstPerson(false);
  $("drone-view").setAttribute("aria-pressed", "false");
  $("fpv-hud").hidden = true;
}
function focusTarget() {
  if (!target) return;
  exitDroneView();
  $("follow-drone").checked = false;
  if (view3d && terrainView) terrainView.focusPoints(targetPoints(), "target");
  else
    map.fitBounds(L.geoJSON(target).getBounds().pad(0.4), {
      maxZoom: 18,
      animate: false,
    });
  $("focus-target").dataset.view = view3d ? "3d" : "2d";
}
$("focus-target").onclick = focusTarget;
function markSelection() {
  for (const card of document.querySelectorAll(".route-card"))
    card.classList.toggle("selected", card.dataset.route === $("chosen").value);
  for (const [key, line] of Object.entries(routes)) {
    line.setStyle({
      weight: key === $("chosen").value ? 6 : 3,
      opacity: key === $("chosen").value ? 1 : 0.65,
    });
    if (key === $("chosen").value) line.bringToFront();
  }
  update3d();
}
function changeRoute() {
  cancelSimulation();
  markSelection();
  refreshPlaybackControls();
  $("flight").textContent =
    "Ruta seleccionada. Pulsa Reproducir para iniciar desde la base.";
}
$("chosen").onchange = changeRoute;
$("route-mode").onchange = () => {
  if (!result || !fresh) return;
  changeRoute();
  renderResults();
};
function setRouteVisibility(all) {
  for (const [key, layer] of Object.entries(routes)) {
    const show = all || key === $("chosen").value;
    visible[key] = show;
    const input = $(`show-${key}`);
    if (input) input.checked = show;
    show ? layer.addTo(map) : map.removeLayer(layer);
  }
  update3d();
}
$("show-selected").onclick = () => setRouteVisibility(false);
$("show-all").onclick = () => setRouteVisibility(true);
function refreshUnknown() {
  uncertaintyLayer.clearLayers();
  for (const threat of visibleThreats)
    if (
      threat.source === "A4_unknown" &&
      (!$("active-only").checked || activeIds.has(threat.id))
    )
      L.geoJSON(threat.geometry, {
        style: {
          color: "#767b73",
          weight: 1,
          dashArray: "4 6",
          fillOpacity: 0.05,
        },
      })
        .bindPopup(() =>
          popup("Recurrencia sin cobertura", {
            ...threat,
            explanation:
              "Probabilidad conservadora supuesta; no es una clase observada.",
          }),
        )
        .addTo(uncertaintyLayer);
}
let windMarker;
function wind() {
  const w = model.weather.find((w) => w.valid_at === $("weather").value);
  if (!w) return;
  $("wind-label").textContent =
    `Clima global del área de vuelo · viento ${w.wind_speed_ms} m/s · ráfaga ${w.wind_gust_ms} m/s · desde ${w.wind_direction_deg}° · una celda meteorológica, snapshot.`;
  if (windMarker) map.removeLayer(windMarker);
  windMarker = L.marker(L.geoJSON(model.area).getBounds().getNorthEast(), {
    icon: L.divIcon({
      className: "wind-icon",
      html: `<span style="display:block;transform:rotate(${Number(w.wind_direction_deg) + 180}deg)">↑</span>`,
      iconSize: [30, 30],
    }),
  })
    .bindPopup(
      popup("Meteorología M4 / A1", {
        ...w,
        failure_probability_pct:
          constraintAssessment?.constraints?.probability_pct ?? null,
      }),
    )
    .addTo(weatherLayer);
}
function refreshSources() {
  for (const [key, layer] of Object.entries(sourceLayers)) {
    layer.clearLayers();
    for (const row of displayModel?.layers?.[key] || []) {
      // The server already clipped this layer spatially by CUT, including unnamed records.
      const id = `${key}:${row.provider_id}`;
      if ($("active-only").checked && key.startsWith("A") && !activeIds.has(id))
        continue;
      let probability =
        key === "A4"
          ? [1, 3, 5, 10, 20][row.ordinal_class - 1] *
            Number($("history").value)
          : key.startsWith("A")
            ? 100
            : null;
      L.geoJSON(row.geometry, {
        style: {
          color: { M2: "#739559", A2: "#d25d32", A3: "#b84e43", A4: "#b69447" }[
            key
          ],
          weight: 1,
          fillOpacity: 0.1,
        },
        pointToLayer: (_, c) => L.circleMarker(c, { radius: 5 }),
      })
        .bindPopup(
          popup(key, {
            ...row,
            probability_pct: probability,
            probability_basis:
              key === "A4"
                ? "Hipótesis académica por misión"
                : "Bloqueo conocido cuando aplica",
          }),
        )
        .addTo(layer);
    }
  }
  drawEvents();
  refreshUnknown();
  update3d();
}
$("active-only").onchange = refreshSources;
$("commune").onchange = () => {
  requests.cancel("view", "fpv", "export-map");
  if (!view3d) $("terrain").hidden = true;
  $("view-toggle").disabled = false;
  refreshMapVisuals();
  refreshThreats();
};
async function setView3d(enabled, force = false) {
  viewDesired = !!enabled;
  if (!enabled) {
    requests.cancel("view", "fpv");
    $("view-toggle").disabled = false;
    view3d = false;
    $("terrain").hidden = true;
    $("map").hidden = false;
    for (const id of ["terrain-help", "terrain-legend", "terrain-credit"])
      $(id).hidden = true;
    exitDroneView();
    map.invalidateSize();
    $("view-label").textContent = "MAPA 2D · OPENSTREETMAP + CAPAS LOCALES";
    $("view-toggle").textContent = "Ver terreno 3D";
    return true;
  }
  if (!model) return false;
  const manifest = displayModel || model,
    key = manifest.geography?.sha256 + ":" + communeId();
  if (view3d && terrainView && sceneKey === key && !force) return true;
  const token = requests.start("view", key);
  $("view-toggle").disabled = true;
  message("Cargando geometría 3D local…");
  let created;
  try {
    if (!model.terrain) {
      const url = resourceUrl(model.resources?.terrain);
      if (!url) throw new Error("Malla de terreno no disponible.");
      const mesh = await api(url, undefined, { signal: token.signal });
      if (!requests.current(token)) return false;
      model.terrain = mesh.terrain || mesh;
    }
    const renderUrl =
      resourceUrl(manifest.resources?.render) ||
      filteredUrl("/api/aereo/patrullaje/escena3d");
    const scene = await api(renderUrl, undefined, { signal: token.signal });
    if (
      !requests.current(token) ||
      !viewDesired ||
      key !== (displayModel || model).geography.sha256 + ":" + communeId()
    )
      return false;
    if (scene.sha256 !== manifest.geography.sha256)
      throw new Error("La cartografía cambió. Recarga la página.");
    $("terrain").hidden = false;
    if (!terrainView) {
      created = TerrainView.create
        ? await TerrainView.create($("terrain"), model.terrain, scene, {
            signal: token.signal,
          })
        : new TerrainView($("terrain"), model.terrain, scene);
      if (!requests.current(token)) {
        created?.dispose?.();
        return false;
      }
      terrainView = created;
    } else if (sceneKey !== key || force) {
      if (terrainView.setScene)
        await terrainView.setScene(scene, { signal: token.signal });
      else
        throw new Error(
          "Actualiza el visor 3D para cambiar las capas por comuna.",
        );
    }
    if (!requests.current(token) || !viewDesired) return false;
    sceneKey = key;
    view3d = true;
    $("map").hidden = true;
    for (const id of ["terrain-help", "terrain-legend", "terrain-credit"])
      $(id).hidden = false;
    $("view-label").textContent = "ENTORNO 3D · DSM + OSM + CONAF";
    $("view-toggle").textContent = "Ver mapa 2D";
    for (const [key, visible] of Object.entries(geographicVisibility))
      terrainView.setLayer(key, visible);
    update3d();
    if (target && !fresh) focusTarget();
    if (simulation) renderFlight(true);
    else terrainView.draw();
    message("Entorno 3D listo.");
    return true;
  } catch (error) {
    if (!aborted(error) && requests.current(token)) {
      view3d = false;
      viewDesired = false;
      $("terrain").hidden = true;
      $("map").hidden = false;
      for (const id of ["terrain-help", "terrain-legend", "terrain-credit"])
        $(id).hidden = true;
      exitDroneView();
      map.invalidateSize();
      message(error.message, true);
    }
    return false;
  } finally {
    if (requests.finish(token)) {
      $("view-toggle").disabled = false;
      if (!view3d) $("terrain").hidden = true;
    }
  }
}
$("view-toggle").onclick = () => setView3d(!view3d);
const phaseNames = {
  takeoff: "Despegue",
  patrol: "Vigilancia",
  report: "Reporte del foco",
  return: "Regreso",
  landing: "Aterrizaje",
  landed: "En tierra",
  battery_swap: "Cambio de batería",
};
function refreshPlaybackControls() {
  const busy = calculating || simulationLoading;
  const editing = mode === "polygon";
  const ready =
    fresh &&
    displayedRoutes()[$("chosen").value]?.status === "ready" &&
    !busy &&
    !editing;
  $("calculate").disabled = !model || !target || busy || editing;
  if (!calculating)
    $("calculate").textContent =
      constraintAssessment?.valid === false
        ? "Obtener diagnóstico y probabilidades"
        : "Comparar las cuatro técnicas";
  $("play").disabled = !ready;
  $("simulate").disabled = !ready;
  $("replay-nominal").disabled = !ready;
  for (const id of ["restart", "finish-playback", "seek", "drone-view"])
    $(id).disabled = !simulation || busy;
  $("pause").disabled = !simulation || !playing;
  $("play").textContent =
    simulation && clock >= simulation.time_s ? "↻ Repetir" : "▶ Reproducir";
  $("show-selected").disabled = !ready;
  $("show-all").disabled = !ready;
  $("export").disabled = !fresh || busy || requests.pending("export");
  $("failures").disabled = !fresh || busy || requests.pending("probabilities");
  $("replan").disabled =
    !simulation ||
    busy ||
    simulation.scenario === "nominal" ||
    !simulation.active_threat_ids.length;
  if (!simulation) {
    $("seek").value = 0;
    $("seek").max = 1;
    $("playback-time").textContent = "00:00 / 00:00";
    $("playback-state").textContent = ready
      ? "Lista para despegar"
      : "Selecciona una ruta";
    $("player").dataset.time = "0";
    $("player").dataset.phase = "idle";
    $("player").dataset.playing = "false";
  }
}
function updateFlightLog(sample) {
  const progress = detectionProgress(simulation.detection, sample.time_s);
  const signature = `${progress.detected}:${progress.reported}:${sample.ended}`;
  if (signature === lastLog) return;
  lastLog = signature;
  $("log").replaceChildren();
  const add = (text) => {
    const li = document.createElement("li");
    li.textContent = text;
    $("log").append(li);
  };
  add(
    simulation.scenario === "nominal"
      ? "Recorrido nominal sin sorteo de fallas."
      : `Semilla ${simulation.seed}: ${simulation.active_threat_ids.length} amenazas activadas. Distribución uniforme [0,100).`,
  );
  if (progress.detected)
    add(
      `Foco detectado: ${simulation.detection.fire_coordinates.map((v) => v.toFixed(5)).join(", ")}. ${progress.incomplete ? "Reporte incompleto; se prioriza el regreso seguro." : `Verificando durante ${result?.effective_profile?.verification_s ?? 60} s.`}`,
    );
  if (progress.reported) add("Foco reportado. Regreso iniciado.");
  if (
    progress.detected &&
    progress.incomplete &&
    simulation.detection.report_incomplete_reason
  )
    add(simulation.detection.report_incomplete_reason);
  if (sample.ended)
    add(
      `Fin: ${simulation.status} · servicio ${simulation.mission_completed ? "cumplido" : "interrumpido"}.`,
    );
}
function renderFlight(force = false, now = performance.now()) {
  if (!simulation) return;
  const sample = sampleFlight(simulation.timeline, clock);
  if (!sample) return;
  drone?.setLatLng([sample.coordinates[1], sample.coordinates[0]]);
  if (view3d && (force || now - lastRender >= 70)) {
    terrainView?.setFlightPose(
      sample.position_utm,
      sample.look_ahead,
      $("follow-drone").checked,
    );
    lastRender = now;
  }
  if (
    !view3d &&
    $("follow-drone").checked &&
    (force || now - lastFollow > 250)
  ) {
    map.panTo([sample.coordinates[1], sample.coordinates[0]], {
      animate: false,
    });
    lastFollow = now;
  }
  $("flight").textContent =
    `${phaseNames[sample.phase] || sample.phase} · ${clockLabel(sample.time_s)} / ${clockLabel(simulation.time_s)}\nBatería útil ${sample.battery_pct.toFixed(1)} % · cota ${sample.coordinates[2].toFixed(1)} m EGM2008`;
  $("progress").value = (100 * sample.time_s) / Math.max(1, simulation.time_s);
  $("seek").max = simulation.time_s;
  $("seek").value = sample.time_s;
  $("playback-time").textContent =
    `${clockLabel(sample.time_s)} / ${clockLabel(simulation.time_s)}`;
  $("playback-state").textContent = phaseNames[sample.phase] || sample.phase;
  const dx = sample.look_ahead[0] - sample.position_utm[0],
    dy = sample.look_ahead[1] - sample.position_utm[1];
  $("fpv-heading").textContent =
    `Rumbo ${(((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360).toFixed(0)}°`;
  $("fpv-height").textContent = `Cota ${sample.coordinates[2].toFixed(0)} m`;
  $("fpv-battery").textContent = `Batería ${sample.battery_pct.toFixed(0)} %`;
  $("fpv-hud").hidden =
    !view3d || $("drone-view").getAttribute("aria-pressed") !== "true";
  updateFlightLog(sample);
  $("player").dataset.time = sample.time_s.toFixed(2);
  $("player").dataset.phase = sample.phase;
  $("player").dataset.playing = String(playing);
}
async function preparePlayback(scenario, autoplay = true) {
  if (simulationLoading || calculating || !fresh) return;
  cancelSimulation();
  const revision = simulationRevision,
    configuration = configurationRevision,
    previous = result,
    chosen = $("chosen").value,
    set = $("route-mode").value;
  const token = requests.start(
    "simulation",
    `${previous.sha256}:${set}:${chosen}:${revision}`,
  );
  simulationLoading = true;
  refreshPlaybackControls();
  message(
    scenario === "nominal"
      ? "Preparando el recorrido desde la base…"
      : "Sorteando amenazas y verificando retorno…",
  );
  try {
    const answer = await api(
      "/api/aereo/patrullaje/simular",
      {
        sha256: previous.sha256,
        method: chosen,
        route_set: set,
        scenario,
        seed: Number($("seed").value),
        fire: fire ? [...fire] : null,
      },
      { signal: token.signal },
    );
    if (
      !requests.current(token) ||
      revision !== simulationRevision ||
      configuration !== configurationRevision ||
      result !== previous ||
      chosen !== $("chosen").value ||
      set !== $("route-mode").value
    )
      return;
    simulation = answer;
    activeIds = new Set(simulation.active_threat_ids);
    refreshSources();
    flightLayer.clearLayers();
    const first = simulation.timeline[0];
    drone = L.marker([first.coordinates[1], first.coordinates[0]], {
      icon: L.divIcon({
        className: "drone-icon",
        html: "✥",
        iconSize: [28, 28],
        iconAnchor: [14, 14],
      }),
    }).addTo(flightLayer);
    const returns = simulation.timeline.filter((f) => f.phase === "return");
    if (returns.length)
      L.polyline(
        returns.map((f) => [f.coordinates[1], f.coordinates[0]]),
        { color: "#d45732", weight: 3, dashArray: "6 4" },
      ).addTo(flightLayer);
    clock = 0;
    lastFrame = 0;
    lastLog = "";
    playing = autoplay;
    renderFlight(true);
    message(
      scenario === "nominal"
        ? "Recorrido listo: despegue, vigilancia y aterrizaje."
        : `Simulación lista: ${simulation.status}.`,
    );
  } catch (error) {
    if (!aborted(error) && requests.current(token)) {
      if (error.status === 410) {
        fresh = false;
        cancelSimulation();
      }
      message(error.message, true);
    }
  } finally {
    if (requests.finish(token)) {
      simulationLoading = false;
      refreshPlaybackControls();
    }
  }
}
$("simulate").onclick = () => preparePlayback("sampled");
$("replay-nominal").onclick = () => preparePlayback("nominal", false);
$("play").onclick = async () => {
  if (!simulation) return preparePlayback("nominal");
  if (clock >= simulation.time_s) clock = 0;
  playing = true;
  lastFrame = 0;
  refreshPlaybackControls();
  renderFlight(true);
};
$("pause").onclick = () => {
  playing = false;
  lastFrame = 0;
  refreshPlaybackControls();
  renderFlight(true);
};
function seekFlight(seconds) {
  if (!simulation) return;
  clock = Math.max(0, Math.min(seconds, simulation.time_s));
  playing = false;
  lastFrame = 0;
  refreshPlaybackControls();
  renderFlight(true);
}
$("restart").onclick = () => seekFlight(0);
$("finish-playback").onclick = () => seekFlight(simulation?.time_s || 0);
$("seek").oninput = () => seekFlight(Number($("seek").value));
$("follow-drone").onchange = () => renderFlight(true);
async function toggleDroneView() {
  if (!simulation) return;
  if ($("drone-view").getAttribute("aria-pressed") === "true") {
    requests.cancel("fpv");
    exitDroneView();
    return;
  }
  const flight = simulation,
    revision = simulationRevision,
    token = requests.start("fpv", flight.result_sha256);
  try {
    if (
      !(await setView3d(true)) ||
      !requests.current(token) ||
      simulation !== flight ||
      revision !== simulationRevision
    )
      return;
    const sample = sampleFlight(flight.timeline, clock);
    if (!sample) return;
    terrainView.setFlightPose(sample.position_utm, sample.look_ahead, false);
    terrainView.setFirstPerson(true);
    $("drone-view").setAttribute("aria-pressed", "true");
    renderFlight(true);
  } catch (error) {
    if (!aborted(error) && requests.current(token))
      message(error.message, true);
  } finally {
    requests.finish(token);
  }
}
$("drone-view").onclick = toggleDroneView;
function animate(now) {
  requestAnimationFrame(animate);
  if (!simulation || !playing) return;
  if (lastFrame)
    clock = Math.min(
      simulation.time_s,
      clock + ((now - lastFrame) / 1000) * Number($("speed").value),
    );
  lastFrame = now;
  if (clock >= simulation.time_s) {
    playing = false;
    refreshPlaybackControls();
    renderFlight(true, now);
  } else renderFlight(false, now);
}
requestAnimationFrame(animate);
document.addEventListener("visibilitychange", () => {
  if (document.hidden && playing) {
    playing = false;
    lastFrame = 0;
    refreshPlaybackControls();
  }
});
function redrawVertices() {
  $("finish").disabled = vertices.length < 3;
  $("draw-tools").dataset.vertices = vertices.length;
  $("area-status").textContent =
    `${vertices.length} vértices · cierra el polígono al terminar.`;
  selection.clearLayers();
  L.polyline(
    vertices.map((p) => [p[1], p[0]]),
    { color: "#31683d" },
  ).addTo(selection);
  for (const v of vertices)
    L.circleMarker([v[1], v[0]], { radius: 4 }).addTo(selection);
}
$("undo-vertex").onclick = () => {
  if (mode === "polygon") {
    vertices.pop();
    redrawVertices();
  }
};
$("cancel-draw").onclick = () => {
  mode = "";
  vertices = [];
  $("finish").disabled = true;
  $("draw-tools").hidden = true;
  selection.clearLayers();
  if (target)
    L.geoJSON(target, {
      style: { color: "#255e40", weight: 2, fillOpacity: 0.15 },
    }).addTo(selection);
  $("area-status").textContent = target
    ? "Se conserva el objetivo anterior."
    : "Dibuja un polígono dentro de vigilancia.";
  refreshPlaybackControls();
  message("Edición cancelada.");
};
document.addEventListener("keydown", (e) => {
  if (
    ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(
      document.activeElement.tagName,
    )
  )
    return;
  if (e.key === "Escape") {
    if (mode) $("cancel-draw").click();
    else exitDroneView();
  }
  if (
    mode === "polygon" &&
    (e.ctrlKey || e.metaKey) &&
    e.key.toLowerCase() === "z"
  ) {
    e.preventDefault();
    $("undo-vertex").click();
  }
  if (e.code === "Space" && fresh && !mode) {
    e.preventDefault();
    playing ? $("pause").click() : $("play").click();
  }
});
$("replan").onclick = async () => {
  if (!simulation || !fresh) return;
  const previous = result.sha256,
    activated = [...simulation.active_threat_ids];
  await calculate({
    previous_sha256: previous,
    activated_threat_ids: activated,
  });
};
function download(name, value) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
async function exportResult(kind) {
  if (!result || !fresh) return;
  const previous = result,
    token = requests.start(kind, previous.sha256);
  refreshPlaybackControls();
  try {
    const url = resourceUrl(
      previous.resources?.[kind === "export" ? "exportar" : "probabilidades"],
    );
    const value = url
      ? await api(url, undefined, { signal: token.signal })
      : kind === "export"
        ? previous
        : previous.failure_probabilities;
    if (!requests.current(token) || result !== previous || !fresh) return;
    if (kind === "export")
      download("patrullaje.json", {
        result: value,
        simulation,
        comparison_history: comparisonHistory,
      });
    else download("failure_probabilities.json", value);
  } catch (error) {
    if (!aborted(error) && requests.current(token)) {
      if (error.status === 410) {
        fresh = false;
        cancelSimulation();
      }
      message(error.message, true);
    }
  } finally {
    if (requests.finish(token)) refreshPlaybackControls();
  }
}
$("export").onclick = () => exportResult("export");
$("failures").onclick = () => exportResult("probabilities");
$("seed").onchange = invalidate;
$("seed").oninput = invalidate;
for (const id of [
  "base",
  "weather",
  "altitude",
  "wind",
  "battery",
  "budget",
  "risk",
  "history",
])
  $(id).addEventListener("change", () => {
    invalidate();
    if (id === "weather") wind();
    if (id === "history") refreshSources();
  });
(async () => {
  try {
    model = await api("/api/aereo/patrullaje/mapa?view=summary");
    displayModel = model;
    loadGeography();
    L.geoJSON(model.flight_area, {
      style: {
        color: "#9b9e7c",
        dashArray: "6 5",
        weight: 1,
        fillOpacity: 0.02,
      },
    }).addTo(map);
    const area = L.geoJSON(model.area, {
      style: { color: "#3c8555", weight: 2, fillOpacity: 0.03 },
    }).addTo(map);
    map.fitBounds(area.getBounds());
    model.bases.forEach((b, i) => {
      $("base").append(new Option(b.name, String(i)));
      const label = document.createElement("label");
      label.className = "check";
      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = true;
      check.value = b.provider_id;
      check.onchange = invalidate;
      label.append(check, document.createTextNode(b.name));
      $("stations").append(label);
    });
    $("base").value = String(
      Math.max(
        0,
        model.bases.findIndex((b) => b.provider_id === "104"),
      ),
    );
    for (const w of model.weather)
      $("weather").append(
        new Option(
          `${w.valid_at.slice(0, 16)} · ${w.wind_speed_ms} / ${w.wind_gust_ms} m/s`,
          w.valid_at,
        ),
      );
    $("weather").value = model.validation?.default_time || model.reference_time;
    for (const key of ["M2", "A2", "A3", "A4"])
      sourceLayers[key] = L.layerGroup();
    sourceLayers.A3.addTo(map);
    L.control
      .layers(
        {},
        {
          "Recurrencia desconocida (supuesto)": uncertaintyLayer,
          "Catálogo M1": catalogueLayer,
          "Elevación M3": metadataNodes,
          "Clima M4 / A1": weatherLayer,
          "Vegetación M2": sourceLayers.M2,
          "FIRMS A2": sourceLayers.A2,
          "AIP A3": sourceLayers.A3,
          "Recurrencia A4": sourceLayers.A4,
          "Amenazas sintéticas": eventsLayer,
        },
        { collapsed: true },
      )
      .addTo(map);
    for (const commune of model.communes || [])
      $("commune").append(new Option(commune.name, String(commune.id)));
    refreshMapVisuals();
    refreshSources();
    wind();
    updateBudgetNote();
    scheduleValidation();
    $("engine").textContent = model.engine;
    message("Selecciona un polígono o carga el ejemplo para comenzar.");
  } catch (e) {
    message(e.message, true);
  }
})();
