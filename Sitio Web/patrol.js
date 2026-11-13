import { TerrainView } from "./terrain3d.js";
import {
  sampleFlight,
  projectUTM,
  clockLabel,
  createRequestCoordinator,
  detectionProgress,
  resilienceSummary,
  smoothFollow,
  mapPaneOffset,
  flightTelemetry,
  targetPlaneRings,
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
  followCenter = null,
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
let targetDisplay = null,
  targetDisplayFor = "";
let followSession = null;
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
  const fetchOptions = body
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: options.signal,
      }
    : { signal: options.signal };
  let r;
  try {
    r = await fetch(url, fetchOptions);
  } catch (err) {
    if (err?.name === "AbortError" || options.signal?.aborted) throw err;
    await new Promise((resolve) => setTimeout(resolve, 350));
    try {
      r = await fetch(url, fetchOptions);
    } catch (retryErr) {
      if (retryErr?.name === "AbortError" || options.signal?.aborted)
        throw retryErr;
      throw new Error(
        "No se pudo conectar con el servidor (Failed to fetch). Verifica que el contenedor 'web' esté activo y actualizado.",
      );
    }
  }
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
  finishMapFollow();
  simulationRevision++;
  requests.cancel("simulation", "fpv", "export");
  simulationLoading = false;
  playing = false;
  simulation = null;
  flightLayer.clearLayers();
  droneVision2d = null;
  droneSwept2d = null;
  droneScanBeam2d = null;
  droneScanTarget2d = null;
  drone = null;
  clock = 0;
  lastFrame = 0;
  lastLog = "";
  lastFollow = 0;
  followCenter = null;
  exitDroneView();
  terrainView?.setMarker(null);
  terrainView?.setDroneNote?.("");
  if ($("fire-emergency-alert")) $("fire-emergency-alert").hidden = true;
  terrainView?.setCoverageTrail?.(
    [],
    fresh && result ? displayedRoutes()[$("chosen").value]?.coordinates_utm || [] : [],
  );
  $("log").replaceChildren();
  $("progress").value = 0;
  $("replan").disabled = true;
  $("drone-coordinates").textContent = "Lat — · Lon — · Cota —";
  $("fpv-propellers").hidden = true;
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
  if (typeof refreshClimateImpactCard === "function") refreshClimateImpactCard();
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
  finishMapFollow();
  exitDroneView();
  $("follow-drone").checked = false;
  terrainView?.reset();
};
$("terrain-mission").onclick = () => {
  finishMapFollow();
  exitDroneView();
  $("follow-drone").checked = false;
  terrainView?.focusRoutes();
};
$("terrain-zoom-in").onclick = () => terrainView?.zoomBy(1.25);
$("terrain-zoom-out").onclick = () => terrainView?.zoomBy(1 / 1.25);
function targetDisplayKey() {
  return target
    ? `${model?.geography?.sha256 || ""}:${JSON.stringify(target)}`
    : "";
}
function showTargetLevel() {
  const known = targetDisplay?.status === "known" &&
    Number.isFinite(targetDisplay.level_m_egm2008);
  $("target-height").textContent = !target
    ? "El objetivo 3D se mostrará sobre un plano horizontal."
    : known
      ? `Plano objetivo: ${targetDisplay.level_m_egm2008.toFixed(1)} m EGM2008 · mínimo 30 m sobre el terreno modelado.`
      : requests.pending("target-display")
        ? "Comprobando la altura del objetivo…"
        : "Altura del objetivo no verificable: faltan elevaciones completas.";
  $("target-height").dataset.status = known ? "known" : "unknown_elevation";
}
async function refreshTargetDisplay() {
  requests.cancel("target-display");
  const previous = target, key = targetDisplayKey();
  if (!previous) return;
  if (targetDisplayFor === key && targetDisplay) return;
  targetDisplay = null;
  targetDisplayFor = "";
  const token = requests.start("target-display", key);
  showTargetLevel();
  update3d();
  try {
    const answer = await api("/api/aereo/patrullaje/objetivo", {
      target_polygon: previous,
    }, { signal: token.signal });
    if (!requests.current(token) || target !== previous || key !== targetDisplayKey()) return;
    targetDisplay = answer.target_display;
    targetDisplayFor = key;
    update3d();
    if (view3d && !fresh) terrainView?.focusPoints(targetPoints(), "target");
  } catch (error) {
    if (!aborted(error) && requests.current(token)) {
      targetDisplay = { status: "unknown_elevation" };
      $("target-height").textContent = "No se pudo comprobar la altura del objetivo. Vuelve a seleccionar el objetivo para reintentar.";
    }
  } finally {
    if (requests.finish(token)) showTargetLevel();
  }
}
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
  if ($("player-route")) {
    $("player-route").replaceChildren(new Option("Sin ruta calculada", ""));
  }
  if ($("route-criteria-modal")) $("route-criteria-modal").hidden = true;
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
  requests.cancel("target-display");
  targetDisplay = null;
  targetDisplayFor = "";
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
  refreshTargetDisplay();
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
if ($("full-area")) {
  $("full-area").onclick = () => {
    const poly = model?.full_permitted_polygon || model?.area;
    if (!poly)
      return message(
        "Aún no se ha cargado el área permitida del modelo.",
        true,
      );
    document
      .querySelectorAll("#stations input[type='checkbox']")
      .forEach((cb) => {
        cb.checked = true;
      });
    if ($("station-inventory")) $("station-inventory").value = "20";
    if (Number($("budget").value) < 36000) $("budget").value = "36000";
    setTarget(poly);
    map.fitBounds(L.geoJSON(target).getBounds().pad(0.08), { animate: false });
    $("area-status").textContent =
      "Área permitida completa cargada · 5 compañías de bomberos activadas para recarga múltiple.";
    message(
      "Área permitida cargada con recarga en estaciones de bomberos habilitada. Pulsa «Generar rutas».",
    );
  };
}
$("fire").onclick = () => {
  if (view3d) setView3d(false);
  mode = "fire";
  message("Marca un foco sintético dentro del polígono objetivo.");
};
if ($("random-fire")) {
  $("random-fire").onclick = () => {
    const activeRoute = selectedRoute();
    const coords = activeRoute?.coordinates || [];
    if (!coords.length && !target) {
      return message("Primero genera una ruta o define un polígono para ubicar un foco.", true);
    }
    let pick = null;
    if (coords.length >= 4) {
      const minIdx = Math.max(1, Math.floor(coords.length * 0.22));
      const maxIdx = Math.max(minIdx + 1, Math.floor(coords.length * 0.68));
      for (let attempt = 0; attempt < 25; attempt++) {
        const idx = minIdx + Math.floor(Math.random() * (maxIdx - minIdx));
        const pt = [coords[idx][0], coords[idx][1]];
        if (!target || pointInPolygon(pt, target)) {
          pick = pt;
          break;
        }
      }
    }
    if (!pick && target?.coordinates?.[0]?.length) {
      const ring = target.coordinates[0];
      const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length;
      const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length;
      pick = [cx, cy];
    }
    if (!pick) return message("No se pudo colocar un foco en la ruta.", true);
    fire = pick;
    fireLayer.clearLayers();
    L.marker([pick[1], pick[0]], {
      icon: L.divIcon({
        className: "drone-icon",
        html: "🔥",
        iconSize: [26, 26],
      }),
    })
      .addTo(fireLayer)
      .bindPopup(popup("Foco de incendio en ruta", { coordinates: pick }));
    $("fire-status").textContent =
      `🔥 Foco activo en ruta: ${pick.map((v) => v.toFixed(5)).join(", ")} (el dron lo sondeará en vuelo)`;
    simulationChanged();
    update3d();
    if (fresh) preparePlayback("nominal", true);
  };
}
$("clear-fire").onclick = () => {
  fire = null;
  fireLayer.clearLayers();
  simulationChanged();
  update3d();
  $("fire-status").textContent = "Sin foco sintético marcado (sondeo preventivo activo).";
};
function resetHazardMode() {
  if ($("hazard")) {
    $("hazard").textContent = "Añadir amenaza";
    $("hazard").classList.remove("primary");
  }
  map.getContainer().style.cursor = "";
}
function onSyntheticHazardsChanged() {
  update3d();
  refreshPlaybackControls();
  updateStepSummaries();
}
$("hazard").onclick = () => {
  if (mode === "hazard") {
    mode = "";
    resetHazardMode();
    if ($("hazard-status"))
      $("hazard-status").textContent = events.length
        ? `⚠️ ${events.length} amenaza(s) sintética(s) activa(s). Pulsa «Generar rutas» para recalcular.`
        : "Sin amenazas sintéticas extra. Pulsa «Añadir amenaza» y haz clic en el mapa para crear una zona de riesgo.";
    return;
  }
  if (view3d) setView3d(false);
  mode = "hazard";
  const r = Number($("radius")?.value || 60);
  const p = Number($("probability")?.value || 80);
  $("hazard").textContent = "📍 Clic en el mapa (Cancelar)";
  $("hazard").classList.add("primary");
  map.getContainer().style.cursor = "crosshair";
  if ($("hazard-status"))
    $("hazard-status").textContent =
      `🎯 Modo amenaza activo: haz clic en cualquier punto del mapa para ubicar una amenaza (radio ${r} m · prob. ${p} %).`;
  message(
    "Modo amenaza activo: haz clic en el mapa para ubicar la amenaza sintética.",
  );
};
$("clear-hazards").onclick = () => {
  events = [];
  eventsLayer.clearLayers();
  if (mode === "hazard") mode = "";
  resetHazardMode();
  if ($("hazard-status"))
    $("hazard-status").textContent =
      "Amenazas sintéticas eliminadas. La ruta seleccionada del Paso 2 se mantiene lista para simular.";
  onSyntheticHazardsChanged();
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
  if ($("hazard-status"))
    $("hazard-status").textContent =
      `⚠️ ${events.length} amenaza(s) sintética(s) en mapa. Puedes simular la ruta actual o pulsar «Replanificar ruta» para esquivarla(s).`;
  onSyntheticHazardsChanged();
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
    resetHazardMode();
    if ($("hazard-status"))
      $("hazard-status").textContent =
        `⚠️ ${events.length} amenaza(s) sintética(s) agregada(s) (radio ${radius} m · prob. ${probability} %). Puedes simular la ruta actual o pulsar «Replanificar ruta».`;
    drawEvents();
    onSyntheticHazardsChanged();
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
const DRONE_PRESETS = {
  mavic3t: {
    drone: "DJI Mavic 3T Enterprise",
    shortName: "Mavic 3T",
    altitude_agl_m: 60,
    wind_limit_ms: 8,
    battery_budget_s: 1200,
    mission_budget_s: 3600,
    cruise_ms: 10,
    climb_ms: 6,
    descent_ms: 6,
    swath_m: 150,
    view_radius_m: 100,
    station_service_s: 120,
    battery_wh: 77,
    charger_w: 30,
    recharge_s: 10800,
    summary:
      "📡 Sensor térmico VOx 640×512 px · Crucero 10 m/s · Bat. 77 Wh (cargador 30 W → recarga 3 h 00 min) · Franja 150 m · Radio IR 100 m",
  },
  matrice30t: {
    drone: "DJI Matrice 30T (IP55)",
    shortName: "Matrice 30T",
    altitude_agl_m: 70,
    wind_limit_ms: 12,
    battery_budget_s: 1680,
    mission_budget_s: 7200,
    cruise_ms: 12,
    climb_ms: 6,
    descent_ms: 5,
    swath_m: 165,
    view_radius_m: 115,
    station_service_s: 90,
    battery_wh: 263,
    charger_w: 110,
    recharge_s: 9900,
    summary:
      "📡 Sensor VOx 640×512 + LRF 1200 m (IP55) · Crucero 12 m/s · Bat. dual TB30 263 Wh (110 W → recarga 2 h 45 min) · Franja 165 m",
  },
  matrice350: {
    drone: "DJI Matrice 350 RTK + Zenmuse H20T",
    shortName: "Matrice 350 RTK",
    altitude_agl_m: 80,
    wind_limit_ms: 12,
    battery_budget_s: 2160,
    mission_budget_s: 10800,
    cruise_ms: 14,
    climb_ms: 6,
    descent_ms: 5,
    swath_m: 185,
    view_radius_m: 135,
    station_service_s: 60,
    battery_wh: 526,
    charger_w: 190,
    recharge_s: 11160,
    summary:
      "📡 Cardán Zenmuse H20T + LRF 1200 m (IP55) · Crucero 14 m/s · Bat. dual TB65 526 Wh (190 W → recarga 3 h 06 min) · Franja 185 m",
  },
};

function currentDroneSpec() {
  const key = $("drone-preset")?.value || "mavic3t";
  return DRONE_PRESETS[key] || DRONE_PRESETS.mavic3t;
}

if ($("drone-preset")) {
  $("drone-preset").addEventListener("change", () => {
    const spec = currentDroneSpec();
    if ($("altitude")) $("altitude").value = String(spec.altitude_agl_m);
    if ($("wind")) $("wind").value = String(spec.wind_limit_ms);
    if ($("battery")) $("battery").value = String(spec.battery_budget_s);
    if ($("budget")) $("budget").value = String(spec.mission_budget_s);
    if ($("drone-spec-summary")) $("drone-spec-summary").textContent = spec.summary;
    if ($("drone-profile-title"))
      $("drone-profile-title").textContent = `Perfil de vuelo · ${spec.shortName}`;
    invalidate();
    updateBudgetNote();
    refreshClimateImpactCard();
    wind();
  });
}

function request() {
  const spec = currentDroneSpec();
  return {
    origin: model.bases[Number($("base").value)].geometry.coordinates,
    target_polygon: target,
    time: $("weather").value,
    station_ids: stationIds(),
    events,
    seed: Number($("seed").value),
    mode: $("patrol-mode")?.value || "grid",
    scenarios: 1000,
    preferences: {
      drone: spec.drone,
      altitude_agl_m: Number($("altitude").value),
      wind_limit_ms: Number($("wind").value),
      battery_budget_s: Number($("battery").value),
      mission_budget_s: Number($("budget").value),
      risk_weight: Number($("risk").value),
      historical_multiplier: Number($("history").value),
      station_inventory: Number($("station-inventory")?.value || 1),
      cruise_ms: spec.cruise_ms,
      climb_ms: spec.climb_ms,
      descent_ms: spec.descent_ms,
      swath_m: spec.swath_m,
      view_radius_m: spec.view_radius_m,
      station_service_s: spec.station_service_s,
      battery_wh: spec.battery_wh,
      charger_w: spec.charger_w,
      recharge_s: spec.recharge_s,
    },
  };
}
function busy(value) {
  calculating = value;
  $("calculate").textContent = value
    ? "Calculando rutas y alternativas…"
    : "Generar rutas";
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
    if (answer.target_display) {
      requests.cancel("target-display");
      targetDisplay = answer.target_display;
      targetDisplayFor = targetDisplayKey();
      showTargetLevel();
    }
    fresh = true;
    activeIds.clear();
    if (result.status === "blocked") $("route-mode").value = "comparison";
    renderResults();
    refreshPlaybackControls();
    openStep(2);
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

function describeRouteMethod(key, r) {
  const isAlt = $("route-mode").value === "alternatives" || key.startsWith("alt_");
  const baseKey = r.base_method || r.method || key;
  const p = result?.effective_profile || model?.profile || {};
  const riskW = Number($("risk")?.value ?? p.risk_weight ?? 240);
  const histM = Number($("history")?.value ?? p.historical_multiplier ?? 1);
  const swath = Number(p.swath_m ?? 200);
  const agl = Number($("altitude")?.value ?? p.altitude_agl_m ?? 100);
  const batS = Number($("battery")?.value ?? p.battery_budget_s ?? 1200);
  const specs = {
    dijkstra_distance: {
      algo: "PostgreSQL / PostGIS · pgr_dijkstra (Solo Distancia)",
      shortBadge: "pgr_dijkstra · Distancia 3D pura",
      formula: "min Σ d_e   (peso arista w_e = distancia geométrica 3D en metros)",
      summary:
        "Calcula el camino más corto puramente geométrico sobre el grafo aéreo 3D usando el algoritmo de Dijkstra en PostgreSQL/pgRouting, sin penalizar la probabilidad de falla por amenazas.",
      criteria: [
        "Criterio primario: Minimización exclusiva de la distancia euclidiana 3D (metros) entre barridos y estaciones.",
        "Amenazas: Ignora probabilidades graduales (A1/A4) en el peso de las aristas; solo respeta exclusiones físicas duras (zona prohibida AIP SC-P50 y límites del grafo).",
        `Cobertura de cámara: Barrido en franjas de ${swath} m de ancho a ${agl} m AGL con verificación de línea de vista sobre DSM Copernicus GLO-30.`,
        `Autonomía y recarga: Límite de ${batS} s por batería (${batS - 60} s de vuelo + 60 s de reserva), insertando paradas en las Compañías de Bomberos (M1) cuando se requiere.`,
      ],
    },
    dijkstra_weighted: {
      algo: "PostgreSQL / PostGIS · pgr_dijkstra Multicriterio (Tiempo + Riesgo)",
      shortBadge: "pgr_dijkstra · Tiempo + Riesgo",
      formula: `min Σ [ t_e + ${riskW} · (−ln(1 − p_e)) ]   donde p_e = P(falla en arco e)`,
      summary:
        "Optimiza simultáneamente el tiempo de vuelo y la supervivencia ante amenazas mediante Dijkstra ponderado en pgRouting, penalizando logarítmicamente los corredores con riesgo climático, térmico o histórico.",
      criteria: [
        `Criterio multicriterio: Combina el tiempo de travesía t_e (s) con el término de confiabilidad −ln(1 − p_e) ponderado por ρ = ${riskW} s.`,
        `Modelo de amenazas en p_e: Integra viento/ráfagas (M4/A1), focos térmicos FIRMS (A2), restricciones aéreas DGAC (A3), amenaza por incendio forestal SENAPRED (A4, densidad 2020-2024 × ${histM}) y amenazas sintéticas.`,
        `Cobertura visual: Franjas de barrido de ${swath} m de ancho para maximizar las celdas de 30×30 m observadas en línea de vista.`,
        `Gestión de energía: Planificación multi-batería (${batS} s útiles) con recarga en estaciones de bomberos habilitadas (${r.stops?.length ?? 0} recargas ejecutadas).`,
      ],
    },
    gurobi: {
      algo: "Gurobi Optimizer · Programación Lineal Entera Mixta (MILP)",
      shortBadge: "Gurobi MILP · Optimización Exacta",
      formula: `min Σ_a c_a y_a + Σ_(i,j) [ t_(i,j) + ${riskW}·(−ln(1 − p_(i,j))) ] x_(i,j)   s.a. Subciclos, Batería ≤ ${batS - 60} s, Cobertura ≥ 90 %`,
      summary:
        "Formula y resuelve el problema formal de optimización combinatoria (MILP) en Gurobi, decidiendo simultáneamente el orden de los sectores de barrido, el sentido de entrada/salida y las visitas a estaciones de bomberos.",
      criteria: [
        "Modelamiento formal MILP: Variables binarias de selección de orientación de barrido y variables de flujo entero para eliminación de subtours y control de inventario de baterías.",
        `Función objetivo: Minimiza el costo compuesto de tiempo de misión más riesgo acumulado de falla (peso ρ = ${riskW}) en conectores y barridos.`,
        `Restricciones duras: Presupuesto por batería (${batS - 60} s de vuelo efectivo), inventario por estación de bomberos y cobertura mínima del polígono (lograda: ${r.coverage ? r.coverage.percent.toFixed(1) + " %" : "—"}).`,
        `Estado del solver: ${r.solver?.engine || "gurobi"} · estado ${r.solver?.status || "optimal"}${r.solver?.gap != null ? ` · gap ${(100 * r.solver.gap).toFixed(2)} %` : ""}.`,
      ],
    },
    annealing: {
      algo: "Metaheurística · Recocido Simulado (Simulated Annealing)",
      shortBadge: "Simulated Annealing · Metaheurística",
      formula: "P(aceptar ΔE > 0) = exp(−ΔE / T_k),   T_(k+1) = α · T_k   con vecindarios 2-opt, swap e inversión de barrido",
      summary:
        "Explora el espacio de permutaciones y orientaciones de barrido mediante enfriamiento estadístico de Boltzmann, permitiendo escapar de óptimos locales en misiones de gran escala con múltiples recargas.",
      criteria: [
        "Operadores de vecindad: Intercambio de sectores (swap), inversión de sub-secuencias (2-opt) y cambio de sentido de barrido en cada polígono/sector.",
        `Evaluación de energía E(S): Tiempo total de vuelo + penalización por probabilidad de falla de enlaces (ρ = ${riskW}) + inserción óptima de recargas en estaciones M1.`,
        `Criterio de parada: Enfriamiento geométrico multi-iteración con retención de la mejor solución factible (${r.stops?.length ?? 0} recargas, ${(r.distance_m / 1000).toFixed(2)} km).`,
      ],
    },
    alns_risk: {
      algo: "RRPP · Adaptive Large Neighborhood Search (ALNS) por Latencia Ponderada",
      shortBadge: "ALNS RRPP · Latencia Ponderada por R(x,y,t)",
      formula: "min Σ r_i · a_i + λ1 · Σ P_ij · t_ij · x_ij + λ2 · N_recargas",
      summary:
        "Prioriza la detección temprana en celdas quadtree de alto riesgo de incendio R(x,y,t) (SENAPRED A4 × CONAF M2 × Rothermel S × interfaz urbana U + FIRMS A2), minimizando el retraso ponderado de primera visita a_i con recargas reales en M1 y bloqueo duro A3.",
      criteria: [
        "Separación de riesgos: el riesgo de incendio R(x,y,t) actúa como premio r_i en la latencia ponderada, mientras que el riesgo para el dron (A1 viento AGL, A3, sintéticas) penaliza o bloquea los arcos.",
        "Operadores Destroy/Repair adaptativos: remoción aleatoria, peor r_i·a_i y cluster geográfico; inserción greedy, regret-2 y regret-3 ponderada por r_i.",
        `Cobertura y energía: preserva cobertura total permitida (${r.coverage ? r.coverage.percent.toFixed(1) + " %" : "—"}), excluye A3 (riesgo inobservable reportado aparte) y respeta inventario de baterías M1 (${r.stops?.length ?? 0} recargas).`,
      ],
    },
  };
  const baseSpec = specs[baseKey] || specs.dijkstra_weighted;
  if (!isAlt) return baseSpec;
  const isRef = r.solver?.engine === "comparison_result";
  return {
    algo: isRef
      ? `${baseSpec.algo} (Circuito de Referencia)`
      : `Generador de Circuitos Disjuntos · ${r.solver?.engine === "diverse_dijkstra" ? "pgr_dijkstra con Penalización de Corredor" : baseSpec.algo}`,
    shortBadge: isRef
      ? `Referencia · ${baseSpec.shortBadge}`
      : `Alternativa diversificada · ${r.solver?.engine || "multicriterio"}`,
    formula: isRef
      ? baseSpec.formula
      : `w'_e = w_e · (1 + λ · uso_previo_e)   con separación espacial ≥ ${result?.diversity?.tolerance_m ?? 12} m y tránsito compartido ≤ 85 %`,
    summary: isRef
      ? `Este es el circuito principal de referencia. ${baseSpec.summary}`
      : "Genera una ruta alternativa físicamente separada penalizando los corredores de tránsito ya utilizados por los circuitos anteriores y variando el orden/sentido de barrido.",
    criteria: [
      ...baseSpec.criteria,
      isRef
        ? "Diversidad: Circuito base #1 contra el cual se mide la separación de los corredores alternativos."
        : `Diversidad de corredor: Comparte como máximo ${(100 * (r.diversity?.max_shared_transit ?? 0)).toFixed(0)} % del tránsito con los circuitos previos.`,
    ],
  };
}

function openCriteriaModal(key) {
  const available = displayedRoutes();
  const targetKey = key || $("chosen").value;
  const r = available?.[targetKey];
  const modal = $("route-criteria-modal");
  if (!r || !modal) return;
  const info = describeRouteMethod(targetKey, r);
  const p = result?.effective_profile || model?.profile || {};
  $("criteria-modal-kicker").textContent =
    $("route-mode").value === "alternatives"
      ? "MODO: CIRCUITOS ALTERNATIVOS DIVERSIFICADOS"
      : "MODO: COMPARACIÓN DE LAS 4 TÉCNICAS DE OPTIMIZACIÓN";
  $("criteria-modal-title").textContent = `${r.label} — ${info.algo}`;
  const stopsNames = (r.stops || [])
    .map((s) => s.name || s.station_id || "Estación M1")
    .join(" → ");
  $("criteria-modal-body").innerHTML = `
    <div class="criteria-section">
      <h4>1. ¿Con qué técnica y motor fue calculada?</h4>
      <p><strong>${info.algo}</strong></p>
      <p>${info.summary}</p>
      <div class="criteria-formula">${info.formula}</div>
    </div>
    <div class="criteria-section">
      <h4>2. Criterios de optimización y restricciones aplicadas</h4>
      <ul class="criteria-list">
        ${info.criteria.map((c) => `<li>${c}</li>`).join("")}
      </ul>
    </div>
    <div class="criteria-section">
      <h4>3. Métricas resultantes y operación del dron (${p.drone || currentDroneSpec().drone})</h4>
      <div class="criteria-kv-grid">
        <div class="criteria-kv"><span>Resiliencia Monte Carlo</span><b>${r.resilience ? (100 * r.resilience.value).toFixed(1) + " %" : "—"} (${r.resilience?.scenarios ?? 1000} sorteos)</b></div>
        <div class="criteria-kv"><span>Cobertura visual del área</span><b>${r.coverage ? r.coverage.percent.toFixed(1) + " %" : "—"} (ancho ${p.swath_m ?? 200} m)</b></div>
        <div class="criteria-kv"><span>Tiempo total de misión</span><b>${r.time_s ? (r.time_s / 60).toFixed(1) + " min (" + r.time_s.toFixed(0) + " s)" : "—"}</b></div>
        <div class="criteria-kv"><span>Distancia 3D recorrida</span><b>${r.distance_m ? (r.distance_m / 1000).toFixed(2) + " km" : "—"}</b></div>
        <div class="criteria-kv"><span>Recargas en Bomberos (M1)</span><b>${r.stops?.length ?? 0} parada(s)${stopsNames ? ": " + stopsNames : ""}</b></div>
        <div class="criteria-kv"><span>Tiempo de cálculo CPU</span><b>${r.compute_s?.toFixed(2) ?? "—"} s (${r.solver?.engine || "motor activo"})</b></div>
      </div>
    </div>
    <div class="criteria-section" style="border-color:rgba(217,155,62,0.5);background:rgba(255,249,235,0.9)">
      <h4 style="color:#7c4d0f">4. ⚠️ Alcance del Escenario (100 % Simulación)</h4>
      <p>Este escenario corresponde íntegramente a una <strong>simulación académica</strong>: el ruteo evita zonas sin permiso de vuelo (AIP Chile SC-P50 · DGAC y zonas urbanas), y los cuarteles de <strong>Bomberos (M1) se consideran puntos de recarga únicamente como supuesto de simulación</strong>, sin que exista confirmación ni consulta oficial con la institución.</p>
    </div>
  `;
  modal.hidden = false;
}

if ($("criteria-modal-close")) {
  $("criteria-modal-close").onclick = () => {
    $("route-criteria-modal").hidden = true;
  };
}
if ($("route-criteria-modal")) {
  $("route-criteria-modal").addEventListener("click", (e) => {
    if (e.target === $("route-criteria-modal")) {
      $("route-criteria-modal").hidden = true;
    }
  });
}
if ($("chosen-info-btn")) {
  $("chosen-info-btn").onclick = () => openCriteriaModal($("chosen").value);
}
if ($("player-route-info")) {
  $("player-route-info").onclick = () => openCriteriaModal($("chosen").value);
}

function renderResults() {
  Object.values(routes).forEach((l) => map.removeLayer(l));
  routes = {};
  $("results").replaceChildren();
  const previousChoice = $("chosen").value;
  $("chosen").replaceChildren();
  if ($("player-route")) $("player-route").replaceChildren();
  const available = displayedRoutes();
  const recommended = displayedRecommended();
  const selectedKey =
    available[previousChoice]?.status === "ready"
      ? previousChoice
      : recommended[0] ||
        Object.keys(available).find((k) => available[k]?.status === "ready") ||
        "";
  const timed = Object.entries(available).filter(
    ([, row]) => row.status === "ready" && Number.isFinite(row.time_s),
  );
  for (const [key, r] of Object.entries(available)) {
    const isSelected = key === selectedKey;
    const methodInfo = describeRouteMethod(key, r);
    const card = document.createElement("div");
    card.className = "route-card";
    card.style.setProperty("--route", colors[key]);
    const title = document.createElement("div");
    title.className = "route-title";
    const check = document.createElement("input");
    check.type = "checkbox";
    check.checked = isSelected;
    check.id = `show-${key}`;
    check.title = "Mostrar u ocultar esta ruta en el mapa";
    visible[key] = isSelected;
    const label = document.createElement("button");
    label.type = "button";
    label.className = "route-choice";
    label.textContent = r.label;
    label.onclick = () => {
      if (r.status !== "ready") return;
      $("chosen").value = key;
      if ($("player-route")) $("player-route").value = key;
      setRouteVisibility(false);
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

    // Fila con el algoritmo empleado y botón (i) para abrir el popup de criterios
    const algoRow = document.createElement("div");
    algoRow.className = "route-algo-row";
    const algoBadge = document.createElement("span");
    algoBadge.className = "route-algo-badge";
    algoBadge.textContent = methodInfo.shortBadge;
    algoBadge.title = methodInfo.algo;
    const algoActions = document.createElement("div");
    algoActions.style.display = "inline-flex";
    algoActions.style.alignItems = "center";
    algoActions.style.gap = "5px";
    const tipIcon = document.createElement("span");
    tipIcon.className = "info-tip";
    tipIcon.tabIndex = 0;
    tipIcon.textContent = "i";
    tipIcon.setAttribute(
      "data-tooltip",
      `${methodInfo.algo}: ${methodInfo.summary}`,
    );
    const criteriaBtn = document.createElement("button");
    criteriaBtn.type = "button";
    criteriaBtn.className = "route-info-pill";
    criteriaBtn.textContent = "ⓘ Criterios";
    criteriaBtn.onclick = (e) => {
      e.stopPropagation();
      openCriteriaModal(key);
    };
    algoActions.append(tipIcon, criteriaBtn);
    algoRow.append(algoBadge, algoActions);
    card.append(algoRow);

    if (r.coordinates.length) {
      routes[key] = L.polyline(
        r.coordinates.map((c) => [c[1], c[0]]),
        {
          color: colors[key],
          weight: isSelected ? 6 : 3,
          opacity: isSelected ? 1 : 0.75,
          dashArray:
            key === "dijkstra_distance"
              ? "8 5"
              : key === "annealing"
                ? "3 5"
                : null,
        },
      ).bindPopup(
        popup(`${r.label} · ${methodInfo.shortBadge}`, {
          algoritmo: methodInfo.algo,
          funcion_objetivo: methodInfo.formula,
          status: r.status,
          compute_s: r.compute_s,
          coverage: r.coverage,
          resilience: r.resilience,
          solver: r.solver,
        }),
      );
      if (isSelected) routes[key].addTo(map);
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
    if (r.status === "ready") {
      const optLabel = `${key === recommended ? "★ " : ""}${r.label} (${r.distance_m ? (r.distance_m / 1000).toFixed(1) + " km" : "—"} · ${r.coverage ? r.coverage.percent.toFixed(0) + "% cob." : "—"})`;
      $("chosen").append(new Option(optLabel, key));
      if ($("player-route")) $("player-route").append(new Option(optLabel, key));
    }
  }
  if (!$("chosen").options.length) {
    $("chosen").append(new Option("— Sin rutas viables para este escenario —", ""));
  }
  $("chosen").value = selectedKey;
  if ($("player-route")) $("player-route").value = selectedKey;
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
  const level = targetDisplay?.status === "known" && Number.isFinite(targetDisplay.level_m_egm2008)
    ? targetDisplay.level_m_egm2008 : null;
  if (level !== null) return targetPlaneRings(target, level).flat();
  return target.coordinates.flat()
    .map((c) => {
      const [x, y] = projectUTM(c);
      return [x, y, level ?? meshHeight(x, y)];
    })
    .filter((p) => p[2] !== null);
}
function update3d() {
  if (!terrainView) return;
  const lines = [], annotations = [];
  const selectedBase = model?.bases?.[Number($("base").value)];
  for (const base of (displayModel || model)?.bases || []) {
    const coordinate = base.geometry?.coordinates;
    if (!coordinate || base.candidate === false) continue;
    const [x, y] = projectUTM(coordinate), z = meshHeight(x, y);
    if (z === null) continue;
    annotations.push({
      id: `base:${base.provider_id}`, kind: "base", position_utm: [x, y, z + 5],
      label: base.name || `Base ${base.provider_id}`,
      selected: String(base.provider_id) === String(selectedBase?.provider_id),
    });
  }
  if (fresh && result) {
    for (const [key, r] of Object.entries(displayedRoutes()))
      if (visible[key] && r.coordinates_utm?.length)
        lines.push({
          points: r.coordinates_utm,
          color: rgb(colors[key]),
          key,
          selected: key === $("chosen").value,
          width: key === $("chosen").value ? 6 : 3,
        });
    for (const station of result.stations || []) {
      const p = station.position_utm;
      if (
        p &&
        stationVisibleInCommune(station, displayModel?.bases, communeId())
      ) {
        const ground = Number.isFinite(station.surface_m_egm2008)
          ? station.surface_m_egm2008 : meshHeight(p[0], p[1]);
        if (ground !== null) annotations.push({ id: `station:${station.id}`, kind: "station", position_utm: [p[0], p[1], ground + 8],
          label: station.name || `Recarga ${station.provider_id || station.id}` });
      }
    }
    for (const threat of visibleThreats) {
      const p = threatDisplayPosition(threat, projectUTM, meshHeight);
      if (p && (!$("active-only").checked || activeIds.has(threat.id)))
        annotations.push({ id: `threat:${threat.id}`, kind: "threat", position_utm: p,
          label: threat.name || threat.label || `Amenaza ${threat.id}` });
    }
  }
  if (target && targetDisplay?.status === "known")
    for (const ring of targetPlaneRings(target, targetDisplay.level_m_egm2008))
      lines.push({ points: ring, color: [0.85, 0.35, 0.08], width: 3, target: true });
  if (fire) {
    const [x, y] = projectUTM(fire),
      z = meshHeight(x, y);
    if (z !== null) {
      annotations.push({ id: "fire", kind: "fire", position_utm: [x, y, z + 18], label: "🔥 Foco de incendio" });
      terrainView.setFire?.([x, y, z]);
    } else {
      terrainView.setFire?.(null);
    }
  } else {
    terrainView.setFire?.(null);
  }
  terrainView.setSwath?.(
    Number(result?.effective_profile?.swath_m ?? model?.profile?.swath_m ?? 200),
  );
  const chosenRoute = fresh && result ? displayedRoutes()[$("chosen").value] : null;
  terrainView.setCoverageTrail?.(
    simulation ? currentSweptTrailUtm(clock) : [],
    chosenRoute?.coordinates_utm || [],
  );
  const forbiddenZones = [];
  const collectGeoRings = (geom) => {
    if (!geom) return [];
    if (geom.type === "Polygon") return [geom.coordinates[0].map((c) => projectUTM(c))];
    if (geom.type === "MultiPolygon") return geom.coordinates.map((p) => p[0].map((c) => projectUTM(c)));
    return [];
  };
  const layerSource = (displayModel || model)?.layers || {};
  for (const [lKey, color, wallH, labelPrefix] of [
    ["A3", [0.84, 0.16, 0.14], 55, "⛔ Zona prohibida AIP"],
    ["A2", [0.88, 0.38, 0.14], 38, "🔥 Anomalía FIRMS"],
  ]) {
    for (const row of layerSource[lKey] || []) {
      const rings = collectGeoRings(row.geometry);
      if (!rings.length) continue;
      forbiddenZones.push({ rings, color, heightM: wallH });
      if (lKey === "A3") {
        const ring = rings[0];
        const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length;
        const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length;
        const cz = meshHeight(cx, cy);
        if (cz !== null) {
          annotations.push({
            id: `a3:${row.provider_id || cx.toFixed(0)}`,
            kind: "threat",
            position_utm: [cx, cy, cz + 25],
            label: `${labelPrefix}${row.name ? " · " + row.name : ""}`,
          });
        }
      }
    }
  }
  for (const ev of events || []) {
    const rings = collectGeoRings(ev.geometry);
    if (rings.length) forbiddenZones.push({ rings, color: [0.80, 0.24, 0.14], heightM: 42 });
  }
  terrainView.setForbiddenZones?.(forbiddenZones);
  terrainView.setAnnotations?.(annotations);
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
              n.surface_m_egm2008 ?? null,
            flight_height_egm2008_m: n.coordinates[2],
            minimum_clearance_m: previous.effective_profile.altitude_agl_m,
            actual_clearance_m: Number.isFinite(n.surface_m_egm2008)
              ? n.coordinates[2] - n.surface_m_egm2008 : null,
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
  $("fpv-propellers").hidden = true;
}
function focusTarget() {
  if (!target) return;
  finishMapFollow();
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
function finishMapFollow() {
  if (!followSession) return;
  const session = followSession;
  followSession = null;
  const center = map.getCenter(), zoom = map.getZoom();
  session.renderer.options.padding = session.padding;
  map.getContainer().setAttribute("aria-busy", "false");
  // Reset through the public API once per interaction, rather than reprojecting
  // every geographic path on each animation frame.
  map.setView(center, zoom, { reset: true, animate: false });
  refreshPlaybackControls();
}
function prepareMapFollow() {
  if (followSession || view3d || !$("follow-drone").checked) return;
  const renderer = map.getRenderer(L.polyline([]));
  followSession = { renderer, padding: renderer.options.padding,
    checkpoint: null, needsCoverage: true };
  renderer.options.padding = Math.max(0.5, renderer.options.padding);
  map.fire("movestart");
}
function followCoveragePainted(session) {
  if (!session) return;
  session.preparing = true;
  const revision = session.paintRevision = (session.paintRevision || 0) + 1;
  map.getContainer().setAttribute("aria-busy", "true");
  refreshPlaybackControls();
  // Canvas queued its draw during moveend. Let that draw and the browser paint
  // finish before a paused user starts playback; no timer or artificial delay.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (followSession !== session || session.paintRevision !== revision) return;
    session.preparing = false;
    map.getContainer().setAttribute("aria-busy", "false");
    refreshPlaybackControls();
  }));
}
function stopMapFollow() {
  finishMapFollow();
  $("follow-drone").checked = false;
  followCenter = null;
  lastFollow = 0;
}
map.on("dragstart zoomstart", stopMapFollow);
// Finish before Leaflet's draggable/zoom handlers capture their start offsets.
for (const event of ["pointerdown", "mousedown", "touchstart", "wheel"])
  map.getContainer().addEventListener(event, stopMapFollow, { capture: true, passive: true });
map.getContainer().addEventListener("keydown", (event) => {
  if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "+", "-", "="].includes(event.key)) stopMapFollow();
}, { capture: true });

function moveMapFollow(center, force) {
  prepareMapFollow();
  if (!followSession) return;
  const origin = map.getPixelOrigin(), size = map.getSize();
  const position = mapPaneOffset(center, [origin.x, origin.y], [size.x, size.y]);
  const pane = map.getPane("mapPane"), old = L.DomUtil.getPosition(pane);
  const moved = !old || Math.hypot(position[0] - old.x, position[1] - old.y) >= 0.5;
  if (moved) {
    L.DomUtil.setPosition(pane, L.point(position[0], position[1]));
    map.fire("move");
  }
  // A padded Canvas can be composited for many frames. Repaint only to refresh
  // its geographic coverage, before the viewport reaches that padded boundary.
  if (followSession.needsCoverage || (force && moved) || !followSession.checkpoint ||
      Math.hypot(center[0] - followSession.checkpoint[0], center[1] - followSession.checkpoint[1]) >
        0.4 * Math.min(size.x, size.y)) {
    followSession.checkpoint = [...center];
    followSession.needsCoverage = false;
    map.fire("moveend");
    followCoveragePainted(followSession);
  }
}
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
  if ($("player-route") && $("player-route").value !== $("chosen").value) {
    $("player-route").value = $("chosen").value;
  }
  setRouteVisibility(false);
  cancelSimulation();
  markSelection();
  refreshPlaybackControls();
  $("flight").textContent =
    "Ruta seleccionada. Pulsa Reproducir para iniciar desde la base.";
}
$("chosen").onchange = changeRoute;
if ($("player-route")) {
  $("player-route").onchange = () => {
    $("chosen").value = $("player-route").value;
    changeRoute();
  };
}
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
  finishMapFollow();
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
    if (simulation && $("follow-drone").checked) renderFlight(true);
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
        : "Generar rutas";
  if ($("go-to-step-3")) $("go-to-step-3").disabled = !ready;
  if ($("go-to-step-4")) $("go-to-step-4").disabled = !fresh || busy;
  if ($("chosen")) {
    $("chosen").disabled = !ready;
    if (!ready && !$("chosen").options.length) {
      $("chosen").append(new Option("— Primero genera las rutas en el Paso 1 —", ""));
    }
  }
  if ($("player-route")) $("player-route").disabled = !ready;
  if ($("player-route-info")) $("player-route-info").disabled = !ready;
  if ($("chosen-info-btn")) $("chosen-info-btn").disabled = !ready;
  $("play").disabled = !ready || !!followSession?.preparing;
  $("simulate").disabled = !ready;
  $("replay-nominal").disabled = !ready;
  $("drone-view").disabled = (!simulation && !ready) || busy;
  for (const id of ["restart", "finish-playback", "seek"])
    $(id).disabled = !simulation || busy;
  $("pause").disabled = !simulation || !playing;
  $("play").textContent =
    simulation && clock >= simulation.time_s ? "↻ Repetir" : "▶ Reproducir";
  $("show-selected").disabled = !ready;
  $("show-all").disabled = !ready;
  $("export").disabled = !fresh || busy || requests.pending("export");
  $("export-format").disabled = $("export").disabled;
  $("failures").disabled = !fresh || busy || requests.pending("probabilities");
  $("replan").disabled =
    !fresh ||
    busy ||
    !(
      events.length > 0 ||
      (simulation &&
        simulation.scenario !== "nominal" &&
        simulation.active_threat_ids.length > 0)
    );
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
  updateStepSummaries();
}
function openStep(stepNumber) {
  for (let i = 1; i <= 4; i++) {
    const card = $(`step-${i}`);
    if (!card) continue;
    const isTarget = i === stepNumber;
    card.classList.toggle("is-open", isTarget);
    const header = card.querySelector(".step-header");
    if (header) header.setAttribute("aria-expanded", String(isTarget));
  }
  updateStepSummaries();
}
function toggleStep(stepNumber) {
  const card = $(`step-${stepNumber}`);
  if (!card) return;
  const willOpen = !card.classList.contains("is-open");
  if (willOpen) {
    openStep(stepNumber);
  } else {
    card.classList.remove("is-open");
    card.querySelector(".step-header")?.setAttribute("aria-expanded", "false");
    updateStepSummaries();
  }
}
function updateStepSummaries() {
  const baseSelect = $("base");
  const baseName =
    baseSelect?.options?.[baseSelect.selectedIndex]?.text || "Valparaíso";
  const shortBase = baseName.replace(/^Decima Sexta de\s*/i, "");
  const step1Done = Boolean(target && fresh);
  if ($("step-summary-1")) {
    $("step-summary-1").textContent = `${step1Done ? "✓ " : ""}Base: ${shortBase} | Dron: ${currentDroneSpec().shortName}${target ? " | Polígono listo" : ""}`;
  }
  if ($("step-badge-1")) $("step-badge-1").textContent = step1Done ? "✓" : "01";
  $("step-1")?.classList.toggle("is-done", step1Done);

  const chosenSelect = $("chosen");
  const chosenLabel =
    chosenSelect?.options?.[chosenSelect.selectedIndex]?.text || "Sin selección";
  const step2Done = Boolean(fresh && result);
  if ($("step-summary-2")) {
    $("step-summary-2").textContent = step2Done
      ? `✓ Activa: ${chosenLabel} | ${result?.diversity?.count ?? 4} circuitos`
      : "Genera las rutas en el Paso 1 para comparar";
  }
  if ($("step-badge-2")) $("step-badge-2").textContent = step2Done ? "✓" : "02";
  $("step-2")?.classList.toggle("is-done", step2Done);

  const speedSelect = $("speed");
  const speedText =
    speedSelect?.options?.[speedSelect.selectedIndex]?.text || "20×";
  const threatCount = (events?.length || 0) + (fire ? 1 : 0);
  const step3Done = Boolean(simulation);
  if ($("step-summary-3")) {
    $("step-summary-3").textContent = `${step3Done ? "✓ " : ""}Velocidad: ${speedText} | ${threatCount ? `${threatCount} amenaza(s)` : "Sin amenazas extra"}`;
  }
  if ($("step-badge-3")) $("step-badge-3").textContent = step3Done ? "✓" : "03";
  $("step-3")?.classList.toggle("is-done", step3Done);

  const fmtSelect = $("export-format");
  const fmtText = fmtSelect?.value === "geojson" ? "GeoJSON 2D" : "JSON 3D";
  if ($("step-summary-4")) {
    $("step-summary-4").textContent = `${fresh ? "✓ Listo" : "Pendiente"} | Formato: ${fmtText}`;
  }
  if ($("step-badge-4")) $("step-badge-4").textContent = fresh ? "✓" : "04";
  $("step-4")?.classList.toggle("is-done", Boolean(fresh));
}
document.querySelectorAll("[data-step-toggle]").forEach((header) => {
  const num = Number(header.getAttribute("data-step-toggle"));
  header.addEventListener("click", (e) => {
    if (e.target.closest("button, a, input, select")) return;
    toggleStep(num);
  });
  header.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggleStep(num);
    }
  });
});
if ($("go-to-step-3")) {
  $("go-to-step-3").onclick = () => openStep(3);
}
if ($("go-to-step-4")) {
  $("go-to-step-4").onclick = () => openStep(4);
}
if ($("map-layers-trigger") && $("map-layers-floating")) {
  $("map-layers-trigger").onclick = (e) => {
    e.stopPropagation();
    const wrap = $("map-layers-floating");
    const nextOpen = wrap.dataset.open !== "true";
    wrap.dataset.open = String(nextOpen);
    $("map-layers-trigger").setAttribute("aria-expanded", String(nextOpen));
  };
  document.addEventListener("click", (e) => {
    const wrap = $("map-layers-floating");
    if (wrap?.dataset.open === "true" && !wrap.contains(e.target)) {
      wrap.dataset.open = "false";
      $("map-layers-trigger")?.setAttribute("aria-expanded", "false");
    }
  });
}
const CLIMATE_PRESETS = {
  optimal: { temp: 18, wind: 2.5 },
  warm_breeze: { temp: 28, wind: 5.5 },
  heatwave: { temp: 36, wind: 6.8 },
  extreme_wind: { temp: 22, wind: 7.6 },
  cold_coastal: { temp: 6, wind: 4.5 },
};

function snapshotThermalProfile(w) {
  if (!w) return { simTempC: 18, windMs: 3.0, gustMs: 4.5, clHourStr: "12:00", label: "Templado" };
  const utcHour = Number((w.valid_at || "").slice(11, 13)) || 0;
  const clHour = (utcHour - 3 + 24) % 24;
  const clHourStr = `${String(clHour).padStart(2, "0")}:00`;
  const rawTemp = Number(w.temperature_c ?? 15);
  // Diurnal forest thermal curve affiliated to the local Chile hour of the snapshot
  const diurnalDelta = {
    0: -4, 1: -5, 2: -6, 3: -6, 4: -7, 5: -7, 6: -5,
    7: -2, 8: 1, 9: 4, 10: 7, 11: 10, 12: 13, 13: 15,
    14: 17, 15: 18, 16: 17, 17: 15, 18: 11, 19: 6,
    20: 2, 21: -1, 22: -2, 23: -3,
  }[clHour] ?? 0;
  const simTempC = Math.round(Math.max(5, Math.min(38, rawTemp + diurnalDelta)));
  let label = "Templado";
  if (simTempC >= 30) label = "Calor alto";
  else if (simTempC >= 24) label = "Cálido";
  else if (simTempC <= 10) label = "Frío";
  return {
    simTempC,
    rawTempC: rawTemp,
    windMs: Number(w.wind_speed_ms ?? 3.0),
    gustMs: Number(w.wind_gust_ms ?? 4.5),
    windDir: Number(w.wind_direction_deg ?? 225),
    clHourStr,
    label,
  };
}

function currentClimateOverride() {
  const preset = $("climate-preset")?.value || "snapshot";
  const snapW =
    model?.weather?.find((w) => w.valid_at === $("weather")?.value) ||
    result?.weather ||
    null;
  const prof = snapshotThermalProfile(snapW);
  const temp =
    preset === "snapshot"
      ? prof.simTempC
      : Number($("climate-temp")?.value ?? prof.simTempC);
  const wind =
    preset === "snapshot"
      ? prof.windMs
      : Number($("climate-wind")?.value ?? prof.windMs);
  return {
    preset,
    temperature_c: temp,
    wind_speed_ms: wind,
    wind_direction_deg: prof.windDir ?? 225,
    clHourStr: prof.clHourStr,
    label: prof.label,
  };
}

function refreshClimateImpactCard() {
  const clim = currentClimateOverride();
  const isSnap = clim.preset === "snapshot";
  if (isSnap && $("climate-temp") && $("climate-wind")) {
    $("climate-temp").value = String(Math.round(clim.temperature_c));
    $("climate-wind").value = String(Number(clim.wind_speed_ms).toFixed(1));
  }
  const T = clim.temperature_c;
  const W = clim.wind_speed_ms;
  const heatLoss =
    0.0075 * Math.max(0, T - 22) + 0.00045 * Math.pow(Math.max(0, T - 28), 2);
  const coldLoss = 0.011 * Math.max(0, 15 - T);
  const capFactor = Math.max(0.52, 1.0 - heatLoss - coldLoss);
  const windDrain = 1.0 + 0.022 * Math.pow(Math.max(0, W - 2.0), 1.35);
  const drainMult = windDrain / capFactor;
  const baseBatS = Number($("battery")?.value || 1200);
  const effBatS = Math.round(baseBatS / drainMult);
  const effCapPct = Math.round((100 / drainMult) * 10) / 10;
  const irContrast = Math.max(
    0.76,
    Math.min(
      1.12,
      1.0 - 0.011 * Math.max(0, T - 25) + 0.006 * Math.max(0, 15 - T),
    ),
  );
  const baseViewR = Number(
    result?.effective_profile?.view_radius_m ??
      model?.profile?.view_radius_m ??
      180,
  );
  const effViewR = Math.round(baseViewR * irContrast);
  const thermalRisk = Math.max(
    0.5,
    1.0 + 0.04 * (T - 20) + 0.03 * Math.max(0, W - 4.0),
  );

  if ($("weather-live-summary")) {
    $("weather-live-summary").textContent =
      `🔗 Clima afiliado (${clim.clHourStr} CL · ${clim.label}): 🌡️ ${T.toFixed(0)} °C · 💨 ${W.toFixed(1)} m/s → Capacidad dron ${effCapPct.toFixed(0)} % (${(effBatS / 60).toFixed(1)} min · consumo ×${drainMult.toFixed(2)})`;
  }

  const card = $("climate-impact-card");
  if (!card) return;
  let severity = "optimal";
  if (T >= 32 || W >= 6.5 || effCapPct < 75) severity = "severe";
  else if (T >= 25 || W >= 4.8 || effCapPct < 88) severity = "warm";
  else if (T <= 10) severity = "cold";
  card.dataset.severity = severity;

  if ($("climate-impact-badge")) {
    $("climate-impact-badge").textContent =
      `Capacidad efectiva: ${effCapPct.toFixed(0)} % (${(effBatS / 60).toFixed(1)} min)`;
  }
  if ($("climate-impact-drain")) {
    $("climate-impact-drain").textContent =
      `T° ${T.toFixed(0)} °C · Viento ${W.toFixed(1)} m/s · Consumo ×${drainMult.toFixed(2)}`;
  }
  if ($("climate-bar-fill")) {
    $("climate-bar-fill").style.width = `${Math.max(15, Math.min(100, effCapPct))}%`;
  }
  if ($("climate-impact-desc")) {
    const reasons = [];
    if (T >= 26)
      reasons.push(
        `Calor (${T} °C): menor densidad del aire y estrés LiPo (−${Math.round(heatLoss * 100)} % bat.)`,
      );
    else if (T <= 12)
      reasons.push(
        `Frío (${T} °C): mayor resistencia interna LiPo (−${Math.round(coldLoss * 100)} % bat.)`,
      );
    if (W >= 3.5)
      reasons.push(
        `Viento (${W.toFixed(1)} m/s): compensación aerodinámica (+${Math.round((windDrain - 1) * 100)} % consumo)`,
      );
    const reasonStr = reasons.length
      ? reasons.join(" · ") + " · "
      : "Condición templada óptima · ";
    $("climate-impact-desc").textContent =
      `${reasonStr}Alcance sondeo IR: ${effViewR} m · Riesgo ignición ×${thermalRisk.toFixed(2)}`;
  }
}

if ($("climate-preset")) {
  $("climate-preset").addEventListener("change", () => {
    const p = $("climate-preset").value;
    if (CLIMATE_PRESETS[p]) {
      if ($("climate-temp")) $("climate-temp").value = String(CLIMATE_PRESETS[p].temp);
      if ($("climate-wind")) $("climate-wind").value = String(CLIMATE_PRESETS[p].wind);
    }
    refreshClimateImpactCard();
    updateStepSummaries();
    if (fresh && !calculating && !simulationLoading) {
      preparePlayback(simulation?.scenario || "nominal", playing);
    }
  });
}
["climate-temp", "climate-wind"].forEach((id) => {
  $(id)?.addEventListener("input", () => {
    if ($("climate-preset") && $("climate-preset").value !== "custom") {
      $("climate-preset").value = "custom";
    }
    refreshClimateImpactCard();
  });
  $(id)?.addEventListener("change", () => {
    refreshClimateImpactCard();
    if (fresh && !calculating && !simulationLoading) {
      preparePlayback(simulation?.scenario || "nominal", playing);
    }
  });
});

["base", "weather", "chosen", "speed", "export-format"].forEach((id) => {
  $(id)?.addEventListener("change", () => {
    refreshClimateImpactCard();
    updateStepSummaries();
  });
});
function updateFlightLog(sample) {
  const progress = detectionProgress(simulation.detection, sample.time_s);
  const climEff = simulation.climate_effects;
  const signature = `${progress.detected}:${progress.reported}:${sample.ended}:${climEff?.preset || "snap"}:${climEff?.temperature_c}:${climEff?.wind_speed_ms}`;
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
      ? "Recorrido nominal con sondeo térmico IR continuo sobre el corredor forestal."
      : `Semilla ${simulation.seed}: ${simulation.active_threat_ids.length} amenazas activadas. Distribución uniforme [0,100).`,
  );
  if (climEff?.active) {
    add(
      `🌡️ Impacto climático activo (${climEff.temperature_c} °C · viento ${climEff.wind_speed_ms} m/s): Capacidad efectiva ${climEff.battery_capacity_pct} % (${climEff.effective_battery_s} s útiles) · consumo ×${climEff.drain_multiplier} · alcance IR ${climEff.effective_view_radius_m} m.`,
    );
    if (climEff.extra_recharges?.length) {
      add(
        `⚡ El mayor desgaste por calor/viento obligó a ${climEff.extra_recharges.length} recarga(s) adicional(es) de emergencia en estaciones de bomberos (${climEff.extra_recharges.map((r) => r.name).join(", ")}).`,
      );
    }
  }
  if (progress.detected)
    add(
      `🔥 ¡Foco de incendio detectado por sondeo térmico!: ${simulation.detection.fire_coordinates.map((v) => v.toFixed(5)).join(", ")}. ${progress.incomplete ? "Reporte incompleto; se prioriza el regreso seguro." : `Fijando objetivo (Target Lock) y verificando durante ${result?.effective_profile?.verification_s ?? 60} s.`}`,
    );
  if (progress.reported) add("✅ Foco confirmado y reportado a central. Regreso a base iniciado.");
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
let droneVision2d = null;
let droneSwept2d = null;
let droneScanBeam2d = null;
let droneScanTarget2d = null;

function currentSweptTrailUtm(timeS) {
  if (!simulation?.timeline?.length) return [];
  const trail = [];
  for (const frame of simulation.timeline) {
    if (frame.time_s <= timeS && frame.position_utm) {
      trail.push(frame.position_utm);
    } else if (frame.time_s > timeS) {
      break;
    }
  }
  const sample = sampleFlight(simulation.timeline, timeS);
  if (sample?.position_utm) trail.push(sample.position_utm);
  return trail;
}

function selectedRoute() {
  if (!fresh || !result) return null;
  const routesMap = displayedRoutes();
  return routesMap?.[$("chosen")?.value] || null;
}

function updateDroneVision2d(sample) {
  if (!sample || view3d) {
    for (const lyr of [droneVision2d, droneSwept2d, droneScanBeam2d, droneScanTarget2d]) {
      if (lyr) flightLayer.removeLayer(lyr);
    }
    droneVision2d = null;
    droneSwept2d = null;
    droneScanBeam2d = null;
    droneScanTarget2d = null;
    return;
  }
  const [lon, lat] = sample.coordinates;
  const dx = sample.look_ahead[0] - sample.position_utm[0];
  const dy = sample.look_ahead[1] - sample.position_utm[1];
  const heading = Math.atan2(dy, dx);
  const fx = Math.cos(heading), fy = Math.sin(heading);
  const rx = Math.sin(heading), ry = -Math.cos(heading);
  const swath = Number(result?.effective_profile?.swath_m ?? model?.profile?.swath_m ?? 200);
  const halfW = swath * 0.5;
  const mPerDegLat = 111132.0;
  const mPerDegLon = 111320.0 * Math.cos((lat * Math.PI) / 180);
  const toLatLng = (vFwd, uRight) => [
    lat + (fy * vFwd + ry * uRight) / mPerDegLat,
    lon + (fx * vFwd + rx * uRight) / mPerDegLon,
  ];
  const corners = [
    toLatLng(-35, -halfW),
    toLatLng(145, -halfW),
    toLatLng(145, halfW),
    toLatLng(-35, halfW),
  ];
  const sweptLatLngs = [];
  for (const frame of simulation?.timeline || []) {
    if (frame.time_s <= sample.time_s && frame.coordinates) {
      sweptLatLngs.push([frame.coordinates[1], frame.coordinates[0]]);
    } else if (frame.time_s > sample.time_s) {
      break;
    }
  }
  sweptLatLngs.push([lat, lon]);
  if (!droneSwept2d) {
    droneSwept2d = L.polyline(sweptLatLngs, {
      color: "#00d4b2",
      weight: 18,
      opacity: 0.25,
      lineCap: "round",
      lineJoin: "round",
      interactive: false,
    }).addTo(flightLayer);
  } else {
    droneSwept2d.setLatLngs(sweptLatLngs);
    if (!flightLayer.hasLayer(droneSwept2d)) droneSwept2d.addTo(flightLayer);
  }
  const isFireLock = sample.phase === "detection" || sample.phase === "report";
  if (!droneVision2d) {
    droneVision2d = L.polygon(corners, {
      color: isFireLock ? "#ff3b14" : "#00d4b2",
      weight: 2,
      fillColor: isFireLock ? "#ff6224" : "#00f5d4",
      fillOpacity: 0.28,
      dashArray: "5 4",
      interactive: false,
    }).addTo(flightLayer);
  } else {
    droneVision2d.setLatLngs(corners);
    droneVision2d.setStyle({
      color: isFireLock ? "#ff3b14" : "#00d4b2",
      fillColor: isFireLock ? "#ff6224" : "#00f5d4",
    });
    if (!flightLayer.hasLayer(droneVision2d)) droneVision2d.addTo(flightLayer);
  }
  // 2D Active Thermal Scan Beam (sondeo oscilante en busca de focos)
  const animSec = performance.now() * 0.001 + (sample.time_s || 0) * 0.18;
  const scanU = Math.sin(animSec * 3.2) * (halfW * 0.85);
  const scanV = 55 + Math.cos(animSec * 2.1) * 55;
  const targetLatLng =
    isFireLock && fire ? [fire[1], fire[0]] : toLatLng(scanV, scanU);
  const beamColor = isFireLock ? "#ff2a00" : "#ff9f1c";
  const beamPoints = [[lat, lon], targetLatLng];
  if (!droneScanBeam2d) {
    droneScanBeam2d = L.polyline(beamPoints, {
      color: beamColor,
      weight: 3,
      opacity: 0.9,
      dashArray: isFireLock ? null : "6 4",
      interactive: false,
    }).addTo(flightLayer);
  } else {
    droneScanBeam2d.setLatLngs(beamPoints);
    droneScanBeam2d.setStyle({ color: beamColor, dashArray: isFireLock ? null : "6 4" });
    if (!flightLayer.hasLayer(droneScanBeam2d)) droneScanBeam2d.addTo(flightLayer);
  }
  if (!droneScanTarget2d) {
    droneScanTarget2d = L.circleMarker(targetLatLng, {
      radius: isFireLock ? 11 : 7,
      color: beamColor,
      weight: 2.5,
      fillColor: beamColor,
      fillOpacity: 0.35,
      interactive: false,
    }).addTo(flightLayer);
  } else {
    droneScanTarget2d.setLatLng(targetLatLng);
    droneScanTarget2d.setRadius(isFireLock ? 11 : 7);
    droneScanTarget2d.setStyle({ color: beamColor, fillColor: beamColor });
    if (!flightLayer.hasLayer(droneScanTarget2d)) droneScanTarget2d.addTo(flightLayer);
  }
}

function renderFlight(force = false, now = performance.now()) {
  if (!simulation) return;
  const sample = sampleFlight(simulation.timeline, clock);
  if (!sample) return;
  drone?.setLatLng([sample.coordinates[1], sample.coordinates[0]]);
  updateDroneVision2d(sample);
  const curFrame =
    simulation.timeline.find((f) => f.time_s >= sample.time_s) ||
    simulation.timeline[simulation.timeline.length - 1];
  const det = simulation.detection;
  const fireDetectedNow = Boolean(
    simulation.fire_found && det && sample.time_s >= (det.detected_at_s ?? 0),
  );
  if ($("fire-emergency-alert")) {
    $("fire-emergency-alert").hidden = !fireDetectedNow;
    if (fireDetectedNow && $("fire-emergency-text")) {
      const [lon, lat, alt] = det.fire_coordinates || sample.coordinates;
      $("fire-emergency-text").textContent =
        `Foco térmico detectado en Lat ${lat.toFixed(5)}, Lon ${lon.toFixed(5)} (${(alt ?? sample.coordinates[2]).toFixed(0)} m EGM2008) a las ${clockLabel(det.detected_at_s)}. Mensaje de emergencia simulado enviado a Central de Bomberos y CONAF.`;
    }
  }
  let droneNote = "";
  if (sample.phase === "battery_swap" || curFrame?.phase === "battery_swap") {
    const remS = Math.max(
      0,
      Number(curFrame?.recharge_remaining_s ?? currentDroneSpec().recharge_s ?? 10800),
    );
    const hrs = Math.floor(remS / 3600);
    const mins = Math.floor((remS % 3600) / 60);
    const wh = curFrame?.battery_wh ?? currentDroneSpec().battery_wh ?? 77;
    const cw = curFrame?.charger_w ?? currentDroneSpec().charger_w ?? 30;
    droneNote = curFrame?.waiting_for_charge
      ? `🔌 Cargando batería (${wh} Wh / ${cw} W): faltan ${hrs} h ${String(mins).padStart(2, "0")} min para carga completa`
      : `🔋 1 batería de estación usada · Cargando repuesto (${wh} Wh / ${cw} W · faltan ${hrs} h ${String(mins).padStart(2, "0")} min)`;
  } else if (fireDetectedNow && (sample.phase === "detection" || sample.phase === "report" || sample.time_s <= (det?.detected_at_s ?? 0) + 70)) {
    droneNote = "🚨 ¡EMERGENCIA DE INCENDIO! Enviando alerta simulada a Bomberos/CONAF";
  } else if (simulation.return_base_id && simulation.return_base_id !== "origin") {
    const inFinalLeg =
      sample.phase === "landed" ||
      sample.phase === "return" ||
      sample.time_s >= simulation.time_s * 0.85;
    if (inFinalLeg) {
      const stName =
        simulation.return_base_name || `Estación ${simulation.return_base_id}`;
      droneNote =
        sample.phase === "landed"
          ? `⚡ Estacionado en estación más cercana (${stName}): más rápido que volver a la base de origen`
          : `⚡ Dirigiéndose a estación más cercana (${stName}): retorno más rápido tras completar el barrido`;
    }
  }
  terrainView?.setDroneNote?.(droneNote);
  if (drone) {
    if (droneNote) {
      if (drone.getTooltip()?.getContent() !== droneNote) {
        drone.unbindTooltip();
        drone
          .bindTooltip(droneNote, {
            permanent: true,
            direction: "top",
            offset: [0, -14],
          })
          .openTooltip();
      }
    } else if (drone.getTooltip()) {
      drone.unbindTooltip();
    }
  }
  const climEff = simulation.climate_effects;
  if (view3d && (force || now - lastRender >= 1000 / 60)) {
    terrainView?.setSwath?.(
      Number(result?.effective_profile?.swath_m ?? model?.profile?.swath_m ?? 200),
    );
    const fireUtm =
      simulation.detection?.fire_coordinates && sample.position_utm
        ? (() => {
            const fc = simulation.detection.fire_coordinates;
            const dLon = fc[0] - sample.coordinates[0];
            const dLat = fc[1] - sample.coordinates[1];
            const mLon = 111320.0 * Math.cos((sample.coordinates[1] * Math.PI) / 180);
            return [
              sample.position_utm[0] + dLon * mLon,
              sample.position_utm[1] + dLat * 111132.0,
            ];
          })()
        : null;
    terrainView?.setThermalContext?.({
      fireUtm,
      threatsUtm: [],
      temperatureC: climEff?.temperature_c ?? 18,
      windSpeedMs: climEff?.wind_speed_ms ?? 3,
      phase: sample.phase,
      timeS: sample.time_s,
    });
    terrainView?.setCoverageTrail?.(currentSweptTrailUtm(sample.time_s));
    terrainView?.setFlightPose(
      sample.position_utm,
      sample.look_ahead,
      $("follow-drone").checked,
    );
    lastRender = now;
  }
  if (
    !view3d &&
    $("follow-drone").checked
  ) {
    const destination = map.project([sample.coordinates[1], sample.coordinates[0]], map.getZoom());
    const current = map.project(map.getCenter(), map.getZoom());
    followCenter = force ? [destination.x, destination.y] : smoothFollow(
      followCenter || [current.x, current.y], [destination.x, destination.y],
      Math.min(100, lastFollow ? now - lastFollow : 1000 / 30),
    );
    if (force || Math.hypot(current.x - followCenter[0], current.y - followCenter[1]) >= 0.5)
      moveMapFollow(followCenter, force);
    lastFollow = now;
  }
  const activeRoute = selectedRoute();
  const maxCov = Number(activeRoute?.coverage?.percent ?? activeRoute?.coverage?.pct ?? 100);
  const sweptRatio = Math.min(1, sample.time_s / Math.max(1, simulation.time_s));
  const sweptCovPct = (maxCov * sweptRatio).toFixed(1);
  const isFireLock = sample.phase === "detection" || sample.phase === "report";
  const scanLabel = isFireLock
    ? "🔥 ¡OBJETIVO TÉRMICO FIJADO!"
    : "🔍 Sondeo IR: buscando focos";
  const climLine = climEff?.active
    ? `\n🌡️ Clima: ${climEff.temperature_c} °C · Viento ${climEff.wind_speed_ms} m/s · Cap. dron ${climEff.battery_capacity_pct} % (consumo ×${climEff.drain_multiplier})`
    : "";
  $("flight").textContent =
    `${phaseNames[sample.phase] || sample.phase} · ${scanLabel} · ${clockLabel(sample.time_s)} / ${clockLabel(simulation.time_s)}\nBatería útil ${sample.battery_pct.toFixed(1)} % · Cobertura barrida ${sweptCovPct} % / ${maxCov.toFixed(1)} % · cota ${sample.coordinates[2].toFixed(1)} m EGM2008${climLine}`;
  $("progress").value = (100 * sample.time_s) / Math.max(1, simulation.time_s);
  $("seek").max = simulation.time_s;
  $("seek").value = sample.time_s;
  $("playback-time").textContent =
    `${clockLabel(sample.time_s)} / ${clockLabel(simulation.time_s)}`;
  $("playback-state").textContent = `${phaseNames[sample.phase] || sample.phase} · ${isFireLock ? "🔥 Foco fijado" : "Sondeo IR"} · Cob. ${sweptCovPct} %`;
  const dx = sample.look_ahead[0] - sample.position_utm[0],
    dy = sample.look_ahead[1] - sample.position_utm[1];
  $("fpv-heading").textContent =
    `Rumbo ${(((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360).toFixed(0)}°`;
  $("fpv-height").textContent = `Cota ${sample.coordinates[2].toFixed(0)} m`;
  $("fpv-battery").textContent = `Batería ${sample.battery_pct.toFixed(0)} % · Barrido ${sweptCovPct} % · ${isFireLock ? "🔥 FOCO" : "IR OK"}`;
  $("drone-coordinates").textContent = flightTelemetry(sample);
  $("drone-coordinates").dataset.latitude = sample.coordinates[1];
  $("drone-coordinates").dataset.longitude = sample.coordinates[0];
  $("drone-coordinates").dataset.altitude = sample.coordinates[2];
  $("fpv-coordinates").textContent = flightTelemetry(sample);
  $("fpv-hud").hidden =
    !view3d || $("drone-view").getAttribute("aria-pressed") !== "true";
  const propellers = $("fpv-propellers");
  propellers.hidden = $("fpv-hud").hidden;
  propellers.dataset.spinning = String(playing && !["landed", "battery_swap"].includes(sample.phase));
  updateFlightLog(sample);
  if (sample.ended && !playing) finishMapFollow();
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
        climate_override: currentClimateOverride(),
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
  prepareMapFollow();
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
$("follow-drone").onchange = () => {
  if (!$("follow-drone").checked) finishMapFollow();
  else prepareMapFollow();
  followCenter = null;
  lastFollow = 0;
  renderFlight(true);
};
async function toggleDroneView() {
  if (!simulation && fresh && $("chosen").value) {
    await preparePlayback("nominal", true);
  }
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
    terrainView.setSwath?.(
      Number(result?.effective_profile?.swath_m ?? model?.profile?.swath_m ?? 200),
    );
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

function syncSpeedPills() {
  const current = String($("speed")?.value || "20");
  document.querySelectorAll(".speed-pill").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.speed === current);
  });
}
document.querySelectorAll(".speed-pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    const val = btn.dataset.speed;
    if ($("speed") && val) {
      $("speed").value = val;
      syncSpeedPills();
      updateStepSummaries();
    }
  });
});
$("speed")?.addEventListener("change", syncSpeedPills);
function animate(now) {
  requestAnimationFrame(animate);
  if (view3d && terrainView?.fireUtm && (!simulation || !playing) && now - lastRender >= 1000 / 30) {
    terrainView.draw();
    lastRender = now;
  }
  if (!simulation) return;
  if (!playing) {
    if (view3d && terrainView?.flightPose && now - lastRender >= 1000 / 30) {
      terrainView.draw();
      lastRender = now;
    }
    return;
  }
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
    if ($("route-criteria-modal") && !$("route-criteria-modal").hidden) {
      $("route-criteria-modal").hidden = true;
    } else if (mode) $("cancel-draw").click();
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
  if (!fresh) return;
  if (simulation && simulation.active_threat_ids?.length) {
    await calculate({
      previous_sha256: result.sha256,
      activated_threat_ids: [...simulation.active_threat_ids],
    });
  } else {
    await calculate();
  }
};
function download(name, value, contentType = "application/json") {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: contentType }),
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
    flight = simulation,
    flightRevision = simulationRevision,
    format = $("export-format").value,
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
    if (!requests.current(token) || result !== previous || !fresh ||
        (kind === "export" && (simulation !== flight || simulationRevision !== flightRevision))) return;
    if (kind === "export") {
      const bundle = {
        result: value,
        simulation: flight,
        comparison_history: [...comparisonHistory],
      };
      if (format === "geojson") {
        const { buildMissionGeoJSON } = await import("./mission-export.js");
        if (!requests.current(token) || result !== previous || simulation !== flight ||
            simulationRevision !== flightRevision || !fresh) return;
        download("patrullaje.geojson", buildMissionGeoJSON(bundle), "application/geo+json");
      } else download("patrullaje.json", bundle);
    } else download("failure_probabilities.json", value);
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
  "station-inventory",
])
  $(id)?.addEventListener("change", () => {
    invalidate();
    if (id === "weather") {
      if ($("climate-preset")) $("climate-preset").value = "snapshot";
      refreshClimateImpactCard();
      wind();
    }
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
    for (const w of model.weather) {
      const prof = snapshotThermalProfile(w);
      $("weather").append(
        new Option(
          `${w.valid_at.slice(0, 16)} (${prof.clHourStr} CL) · 🌡️ ${prof.simTempC} °C (${prof.label}) · 💨 ${w.wind_speed_ms}/${w.wind_gust_ms} m/s`,
          w.valid_at,
        ),
      );
    }
    $("weather").value = model.validation?.default_time || model.reference_time;
    refreshClimateImpactCard();
    const riskFieldLayer = L.layerGroup();
    let riskFieldLoaded = false;
    map.on("overlayadd", async (ev) => {
      if (ev.layer !== riskFieldLayer || riskFieldLoaded) return;
      try {
        const meta = await fetch("/api/aereo/patrullaje/riesgo?norm=max&cell_m=90").then((r) => r.json());
        const geo = await fetch(meta.resource.url).then((r) => r.json());
        L.geoJSON(geo, {
          style: (f) => {
            const v = f.properties?.r ?? 0;
            const color = v > 0.65 ? "#dc2626" : v > 0.35 ? "#f97316" : v > 0.15 ? "#eab308" : "#0ea5e9";
            return { color, weight: 0, fillColor: color, fillOpacity: Math.min(0.75, 0.15 + 0.6 * v) };
          },
          onEachFeature: (f, l) => l.bindTooltip(`R=${(f.properties?.r ?? 0).toFixed(3)} · ${f.properties?.obs ? "Observable" : "No observable (A3/Urbano)"}`),
        }).addTo(riskFieldLayer);
        riskFieldLoaded = true;
      } catch (err) {
        message(`No se pudo cargar R(x,y,t): ${err.message}`, true);
      }
    });
    for (const key of ["M2", "A2", "A3", "A4"])
      sourceLayers[key] = L.layerGroup();
    sourceLayers.A3.addTo(map);
    L.control
      .layers(
        {},
        {
          "Campo de riesgo R(x,y,t)": riskFieldLayer,
          "Recurrencia desconocida (supuesto)": uncertaintyLayer,
          "Catálogo M1": catalogueLayer,
          "Elevación M3": metadataNodes,
          "Clima M4 / A1": weatherLayer,
          "Vegetación M2 (CONAF)": sourceLayers.M2,
          "FIRMS A2": sourceLayers.A2,
          "AIP A3": sourceLayers.A3,
          "Amenaza incendio A4 (SENAPRED)": sourceLayers.A4,
          "Amenazas sintéticas": eventsLayer,
        },
        { collapsed: true },
      )
      .addTo(map);
    for (const commune of model.communes || [])
      $("commune").append(new Option(commune.name, String(commune.id)));
    refreshMapVisuals();
    if (
      new URLSearchParams(location.search).get("view") === "3d" ||
      location.hash === "#3d"
    ) {
      setView3d(true);
    }
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
