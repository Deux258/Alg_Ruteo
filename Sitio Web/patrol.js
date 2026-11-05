import { TerrainView } from "./terrain3d.js";
import { sampleFlight, projectUTM, clockLabel } from "./flight-player.js";
const $ = (id) => document.getElementById(id);
const colors = {
  dijkstra_distance: "#326b99",
  dijkstra_weighted: "#237c55",
  gurobi: "#b17724",
  annealing: "#90508d",
  alt_1: "#326b99", alt_2: "#237c55", alt_3: "#b17724", alt_4: "#90508d",
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
  playing = false,
  frame = 0,
  logged = false;
let layerControl,
  sourceLayers = {},
  activeIds = new Set(),
  comparisonHistory = [];
let calculating=false,simulationLoading=false,configurationRevision=0,lastRender=0,lastFollow=0,lastLog='';
const displayedRoutes=()=>!result?{}:$("route-mode").value==='comparison'?result.routes:result.route_alternatives||{};
const displayedRecommended=()=>$("route-mode").value==='comparison'?result?.recommended||[]:result?.alternative_recommended||[];
const message = (text, error = false) => {
  $("message").textContent = text;
  $("message").classList.toggle("error", error);
};
async function api(url, body) {
  const r = await fetch(
    url,
    body
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }
      : {},
  );
  const value = await r.json();
  if (!r.ok) throw new Error(value.error || "Servicio no disponible");
  return value;
}
function popup(title, obj) {
  const root = document.createElement("div");
  const b = document.createElement("b");
  b.textContent = title;
  root.append(b);
  for (const [key, value] of Object.entries(obj)) {
    const row = document.createElement("div");
    row.className = "popup-row";
    row.textContent = `${key}: ${typeof value === "object" ? JSON.stringify(value) : (value ?? "sin dato")}`;
    root.append(row);
  }
  return root;
}
function loadGeography() {
  const geo = model.geography;
  if (!geo) return;
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
      "No se pudo cargar una tesela OSM. Las capas vectoriales locales siguen disponibles.";
  });
  osmBase.on("load", () => {
    $("tile-status").textContent = tileErrors
      ? "Carga parcial de OpenStreetMap. Las capas locales siguen disponibles."
      : "OpenStreetMap · calles, nombres y lugares. Capas locales superpuestas.";
  });
  // Vector OSM data remains visible when the remote tile layer is removed.
  map.attributionControl.addAttribution(
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  );
  map.attributionControl.addAttribution("CONAF · Copernicus GLO-30");
  for (const [key, title] of Object.entries(geographicNames)) {
    const data = geo.layers[key] || { type: "FeatureCollection", features: [] };
    const layer = L.geoJSON(data, {
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
        fillOpacity: key === "water" ? 0.55 : key === "landcover" ? 0.17 : 0.45,
        opacity: key === "contours" ? 0.5 : 0.8,
      }),
      pointToLayer: (_, c) =>
        L.circleMarker(c, {
          radius: 3,
          color: geographicColors[key],
          weight: 1,
          fillOpacity: 0.8,
        }),
      onEachFeature: (f, l) =>
        l.bindPopup(() =>
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
    });
    geographicLayers[key] = layer;
    geographicVisibility[key] = true;
    layer.addTo(map);
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
    count.textContent = data.features.length.toLocaleString();
    label.append(check, swatch, text, count);
    $("geography-controls").append(label);
    check.onchange = () => {
      geographicVisibility[key] = check.checked;
      if (check.checked) layer.addTo(map);
      else map.removeLayer(layer);
      terrainView?.setLayer(key, check.checked);
    };
  }
  $("geography-status").textContent =
    `${geo.counts.buildings.toLocaleString()} edificios · ${geo.counts.water.toLocaleString()} áreas/cursos de agua · ${geo.counts.landcover.toLocaleString()} coberturas · ${geo.counts.trees.toLocaleString()} árboles o hileras mapeados.`;
  $("geography-source").textContent =
    `OSM: ${geo.source.timestamp_osm_base || geo.source.fetched_at_utc}. Catastro CONAF 2019 y DSM Copernicus ≈30 m. ${geo.height_estimates.toLocaleString()} alturas estimadas; ${geo.woodland_symbols.toLocaleString()} símbolos de copas en bosques. La ausencia de objetos no garantiza despeje.`;
  $("export-geography").disabled = false;
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
$("export-geography").onclick = () => {
  const geo = model.geography;
  download("entorno_geografico.geojson", {
    type: "FeatureCollection",
    features: Object.values(geo.layers).flatMap((l) => l.features),
    metadata: {
      sha256: geo.sha256,
      source: geo.source,
      assumptions: geo.assumptions,
    },
  });
};
$("terrain-reset").onclick = () => {exitDroneView();$("follow-drone").checked=false;terrainView?.reset();};
$("terrain-mission").onclick = () => {exitDroneView();$("follow-drone").checked=false;terrainView?.focusRoutes();};
function invalidate() {
  configurationRevision++;
  playing = false;
  fresh = false;
  simulation = null;
  flightLayer.clearLayers();drone=null;exitDroneView();terrainView?.setMarker(null);
  Object.values(routes).forEach(layer=>map.removeLayer(layer));routes={};
  $("results").replaceChildren();$("chosen").replaceChildren();
  $("flight").textContent='Sin vuelo activo.';$("log").replaceChildren();$("progress").value=0;
  clock=0;update3d();refreshPlaybackControls();
  $("simulate").disabled = true;
  $("export").disabled = true;
  $("failures").disabled = true;
  $("calculate").disabled = !target;
  message("Configuración cambiada. Vuelve a comparar las técnicas.");
}
function setTarget(geo) {
  const g = geo.type === "Feature" ? geo.geometry : geo;
  if (g.type !== "Polygon") throw new Error("Importa un Polygon GeoJSON.");
  target = g;
  mode='';$("finish").disabled=true;$("draw-tools").hidden=true;
  fire=null;fireLayer.clearLayers();$("fire-status").textContent='Sin foco sintético.';
  $("focus-target").disabled=false;
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
  if(view3d)setView3d(false);
  mode = "polygon";
  vertices = [];
  selection.clearLayers();
  playing=false;refreshPlaybackControls();
  $("finish").disabled = true;
  $("draw-tools").dataset.vertices="0";$("draw-tools").hidden=false;
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
  try {
    let g = JSON.parse(await e.target.files[0].text());
    if (g.type === "FeatureCollection") {
      if (g.features.length !== 1)
        throw new Error("Carga una sola área por misión.");
      g = g.features[0];
    }
    setTarget(g);
    map.fitBounds(selection.getBounds?.() || L.geoJSON(target).getBounds());
  } catch (err) {
    message(err.message, true);
  }
};
$("demo").onclick = () => {
  if (!model?.demo_polygon)
    return message(
      "No hay un ejemplo geométrico disponible; dibuja un objetivo.",
      true,
    );
  setTarget(model.demo_polygon);
  map.fitBounds(L.geoJSON(target).getBounds().pad(1));
};
$("fire").onclick = () => {
  if(view3d)setView3d(false);
  mode = "fire";
  message("Marca un foco sintético dentro del polígono objetivo.");
};
$("clear-fire").onclick = () => {
  fire = null;
  fireLayer.clearLayers();
  playing=false;simulation=null;refreshPlaybackControls();update3d();
  $("fire-status").textContent = "Sin foco sintético.";
};
$("hazard").onclick = () => {
  if(view3d)setView3d(false);
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
    Math.abs(c[1]) > 90 ||
    !(r > 0 && r <= 500 && p >= 0 && p <= 100)
  )
    return message("Revisa coordenadas, radio y probabilidad.", true);
  events.push({ geometry: circlePolygon(...c, r), probability_pct: p });
  drawEvents();
  invalidate();
};
function circlePolygon(lon, lat, radius) {
  return {
    type: "Polygon",
    coordinates: [
      Array.from({ length: 65 }, (_, i) => {
        const a = (2 * Math.PI * i) / 64;
        return [
          lon +
            (radius * Math.cos(a)) / (111320 * Math.cos((lat * Math.PI) / 180)),
          lat + (radius * Math.sin(a)) / 111320,
        ];
      }),
    ],
  };
}
map.on("click", (e) => {
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
    mode = "";playing=false;simulation=null;refreshPlaybackControls();update3d();
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
});
function drawEvents() {
  eventsLayer.clearLayers();
  events.forEach((event, i) => {
    if ($("active-only").checked && !activeIds.has(`synthetic:${i}`)) return;
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
          id: `synthetic:${i}`,
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
 calculating=value;
 if(value){$('export').disabled=true;$('failures').disabled=true;}
 $('calculate').disabled=value||!target;
 $('simulate').disabled=value||!fresh||!displayedRecommended().length;
 $('replan').disabled=value||!simulation;
 $('calculate').textContent=value?'Calculando técnicas y corredores diferentes…':'Comparar las cuatro técnicas';
 refreshPlaybackControls();
}
async function calculate() {
  if (!target) return;
  playing = false;
  fresh = false;
  const revision=configurationRevision;
  busy(true);
  message(
    "Construyendo grafo, consultando algoritmos y evaluando cobertura. Puede tardar unos minutos.",
  );
  try {
    if (result)
      comparisonHistory.push({
        sha256: result.sha256,
        routes: Object.fromEntries(
          Object.entries(result.routes).map(([k, r]) => [
            k,
            { status: r.status, resilience: r.resilience, time_s: r.time_s },
          ]),
        ),
      });
    const answer = await api("/api/aereo/patrullaje", request());
    if(revision!==configurationRevision){message('La configuración cambió durante el cálculo. Vuelve a comparar.');return;}
    result=answer;
    fresh = true;
    simulation = null;
    activeIds.clear();
    $("replan").disabled = true;
    renderResults();
    $("export").disabled = false;
    $("failures").disabled = false;
    message(
      `${result.network.nodes.toLocaleString()} nodos · ${result.network.directed_edges.toLocaleString()} arcos · ${result.diversity.count} circuitos distintos validados. La comparación original de técnicas está disponible en el selector.`,
    );
    refreshSources();
  } catch (e) {
    message(e.message, true);
  } finally {
    busy(false);
  }
}
$("calculate").onclick = calculate;
function renderResults() {
  metadataNodes.clearLayers();
  for (const n of result.graph.nodes)
    L.circleMarker([n.coordinates[1], n.coordinates[0]], {
      radius: 2,
      color: "#637963",
      weight: 1,
    })
      .bindPopup(() =>
        popup("Superficie · DSM y obstáculos", {
          node_id: n.id,
          modeled_surface_elevation_m:
            n.coordinates[2] - result.effective_profile.altitude_agl_m,
          flight_height_egm2008_m: n.coordinates[2],
          altitude_agl_m: result.effective_profile.altitude_agl_m,
        }),
      )
      .addTo(metadataNodes);
  Object.values(routes).forEach((l) => map.removeLayer(l));
  routes = {};
  $("results").replaceChildren();
  const previousChoice=$("chosen").value;
  $("chosen").replaceChildren();
  const available=displayedRoutes();
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
    label.type="button";label.className="route-choice";
    label.textContent = r.label;label.onclick=()=>{if(r.status!=="ready")return;$("chosen").value=key;changeRoute();};
    title.append(check, label);
    const rank = displayedRecommended().indexOf(key);
    if (rank >= 0) {
      const b = document.createElement("span");
      b.className = "rank";
      b.textContent = `OPCIÓN ${rank + 1}`;
      title.append(b);
    }
    card.dataset.route=key;card.append(title);
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
        "Resiliencia · 1.000 escenarios",
      ],
      [
        r.time_s === null ? "—" : (r.time_s / 60).toFixed(1) + " min",
        "Tiempo de misión",
      ],
      [r.compute_s.toFixed(2) + " s", $("route-mode").value==='alternatives'?"Generación acumulada":"Cómputo"],
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
    const note = document.createElement("p");
    const engineLabel=r.solver.engine==='comparison_result'?'Referencia':r.solver.engine==='diverse_dijkstra'?'Corredor diversificado':r.solver.engine;
    note.textContent = `${r.status} · ${r.distance_m === null ? "sin recorrido" : (r.distance_m / 1000).toFixed(2) + " km"} · ${r.stops.length} recargas${engineLabel ? " · " + engineLabel : ""}${r.solver.status ? " · solver " + r.solver.status : ""}${r.solver.gap != null ? " · gap " + (100 * r.solver.gap).toFixed(2) + " %" : ""}`;
    card.append(note);
    if(r.diversity){const shared=document.createElement('p');shared.textContent=r.solver.engine==='comparison_result'?'Circuito de referencia · resultado original de la técnica.':`Corredor alternativo · hasta ${(100*r.diversity.max_shared_transit).toFixed(0)} % de tránsito compartido con los anteriores.`;card.append(shared);}
    if (r.solver.reason) {
      const error = document.createElement("p");
      error.textContent = r.solver.reason;
      card.append(error);
    }
    $("results").append(card);
    if (r.status === "ready") $("chosen").append(new Option(r.label, key));
  }
  const recommended=displayedRecommended();
  $('chosen').value=available[previousChoice]?.status==='ready'?previousChoice:recommended[0]||'';
  $('diversity-note').textContent=$('route-mode').value==='alternatives'?`${result.diversity.count} circuitos diferentes. Comparten el barrido del objetivo; el tránsito se compara con tolerancia de 12 m.${result.diversity.reason?' '+result.diversity.reason:''}`:'Resultados originales por técnica. Si coinciden en el óptimo, pueden compartir exactamente el mismo recorrido.';
  markSelection();refreshPlaybackControls();
  if(view3d)terrainView?.focusRoutes();else if(Object.keys(routes).length)map.fitBounds(L.featureGroup(Object.values(routes)).getBounds().pad(.15),{maxZoom:17});
  $("network").textContent =
    `≤ ${result.network.max_horizontal_link_m.toFixed(0)} m`;
  update3d();
}
function meshHeight(x,y){const m=model?.terrain;if(!m)return 0;const i=Math.max(0,Math.min(m.width-1,Math.round((x-m.origin_utm[0])/(m.x[1]-m.x[0])))),j=Math.max(0,Math.min(m.height-1,Math.round((y-m.origin_utm[1])/(m.y[1]-m.y[0]))));return m.elevations[j*m.width+i]??0;}
function targetPoints(){if(!target)return [];return target.coordinates[0].map(c=>{const [x,y]=projectUTM(c);return [x,y,meshHeight(x,y)];});}
function update3d(){
 if(!terrainView)return;const lines=[];
 if(fresh&&result){for(const [key,r] of Object.entries(displayedRoutes()))if(visible[key]&&r.coordinates_utm?.length)lines.push({points:r.coordinates_utm,color:rgb(colors[key]),width:key===$('chosen').value?4:2});
 for(const station of result.stations)lines.push({points:[station.position_utm],color:[.9,.65,.1],point:true});
 for(const threat of result.threats)if(threat.position_utm&&(!$('active-only').checked||activeIds.has(threat.id)))lines.push({points:[threat.position_utm],color:[.8,.25,.15],point:true});}
 if(target){const points=targetPoints(),outline=[];for(let i=1;i<points.length;i++){const a=points[i-1],b=points[i],count=Math.max(1,Math.ceil(Math.hypot(b[0]-a[0],b[1]-a[1])/15));for(let j=0;j<count;j++){const t=j/count,x=a[0]+(b[0]-a[0])*t,y=a[1]+(b[1]-a[1])*t;outline.push([x,y,meshHeight(x,y)+3]);}}outline.push(points.at(-1));lines.push({points:outline,color:[.85,.35,.08],width:3,target:true});}
 if(fire){const [x,y]=projectUTM(fire);lines.push({points:[[x,y,meshHeight(x,y)+8]],color:[1,.2,.05],point:true});}
 terrainView.setRoutes(lines);
}
function exitDroneView(){terrainView?.setFirstPerson(false);$('drone-view').setAttribute('aria-pressed','false');$('fpv-hud').hidden=true;}
function focusTarget(){if(!target)return;exitDroneView();$('follow-drone').checked=false;if(view3d&&terrainView)terrainView.focusPoints(targetPoints(),'target');else map.fitBounds(L.geoJSON(target).getBounds().pad(.4),{maxZoom:18});$('focus-target').dataset.view=view3d?'3d':'2d';}
$('focus-target').onclick=focusTarget;
function markSelection(){for(const card of document.querySelectorAll('.route-card'))card.classList.toggle('selected',card.dataset.route===$('chosen').value);for(const [key,line] of Object.entries(routes)){line.setStyle({weight:key===$('chosen').value?6:3,opacity:key===$('chosen').value?1:.65});if(key===$('chosen').value)line.bringToFront();}update3d();}
function changeRoute(){playing=false;simulation=null;flightLayer.clearLayers();drone=null;terrainView?.setMarker(null);exitDroneView();clock=0;markSelection();refreshPlaybackControls();$('flight').textContent='Ruta seleccionada. Pulsa Reproducir para iniciar desde la base.';}
$('chosen').onchange=changeRoute;
$('route-mode').onchange=()=>{if(!result||!fresh)return;changeRoute();renderResults();};
function setRouteVisibility(all){for(const [key,layer] of Object.entries(routes)){const show=all||key===$('chosen').value;visible[key]=show;const input=$(`show-${key}`);if(input)input.checked=show;show?layer.addTo(map):map.removeLayer(layer);}update3d();}
$('show-selected').onclick=()=>setRouteVisibility(false);$('show-all').onclick=()=>setRouteVisibility(true);
function refreshUnknown() {
  uncertaintyLayer.clearLayers();
  for (const threat of result?.threats || [])
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
    `Viento ${w.wind_speed_ms} m/s · ráfaga ${w.wind_gust_ms} m/s · desde ${w.wind_direction_deg}° · una celda meteorológica, snapshot.`;
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
          Math.max(w.wind_speed_ms, w.wind_gust_ms) >= Number($("wind").value)
            ? 100
            : 0,
      }),
    )
    .addTo(weatherLayer);
}
function refreshSources() {
  const commune = $("commune").value;
  for (const [key, layer] of Object.entries(sourceLayers)) {
    layer.clearLayers();
    for (const row of model.layers[key]) {
      const name = row.attributes?.commune || row.commune || "";
      if (commune && name && name !== commune) continue;
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
$("commune").onchange = refreshSources;
let loading3d = false,
  sceneRender;
async function setView3d(enabled) {
  if(enabled===!!view3d)return true;
  if (loading3d || !model) return;
  if (!view3d && !terrainView) {
    loading3d = true;
    $("view-toggle").disabled = true;
    message("Cargando geometría 3D local de edificios y entorno…");
    try {
      sceneRender = await api("/api/aereo/patrullaje/escena3d");
      if (sceneRender.sha256 !== model.geography.sha256)
        throw new Error("La cartografía cambió. Recarga la página.");
    } catch (e) {
      message(e.message, true);
      return;
    } finally {
      loading3d = false;
      $("view-toggle").disabled = false;
    }
  }
  view3d = enabled;
  $("terrain").hidden = !view3d;
  $("map").hidden = view3d;
  for (const id of ["terrain-help", "terrain-legend", "terrain-credit"])
    $(id).hidden = !view3d;
  $("view-label").textContent = view3d
    ? "ENTORNO 3D · DSM + OSM + CONAF"
    : "MAPA 2D · OPENSTREETMAP + CAPAS LOCALES";
  $("view-toggle").textContent = view3d ? "Ver mapa 2D" : "Ver terreno 3D";
  if (view3d) {
    try {
      terrainView ??= new TerrainView($("terrain"), model.terrain, {
        ...model.geography,
        render: sceneRender.render,
      });
      sceneRender = null;
      for (const [key, value] of Object.entries(geographicVisibility))
        terrainView.setLayer(key, value);
      update3d();
      terrainView.draw();
      message(
        "Entorno 3D listo. Activa las capas desde Cartografía y entorno.",
      );
    } catch (e) {
      message(e.message, true);
    }
  } else {exitDroneView();map.invalidateSize();}
  if(view3d&&target&&!fresh)focusTarget();
  if(simulation)renderFlight(true);
  return true;
}
$('view-toggle').onclick=()=>setView3d(!view3d);
const phaseNames={takeoff:'Despegue',patrol:'Vigilancia',report:'Reporte del foco',return:'Regreso',landing:'Aterrizaje',landed:'En tierra',battery_swap:'Cambio de batería'};
function refreshPlaybackControls(){
 const ready=fresh&&!!displayedRoutes()[$('chosen').value]&&!calculating&&!simulationLoading;
 $('play').disabled=!ready;$('simulate').disabled=!ready;$('replay-nominal').disabled=!ready;
 for(const id of ['restart','finish-playback','seek','drone-view'])$(id).disabled=!simulation||simulationLoading||calculating;
 $('pause').disabled=!simulation||!playing;$('play').textContent=simulation&&clock>=simulation.time_s?'↻ Repetir':'▶ Reproducir';
 $('show-selected').disabled=!ready;$('show-all').disabled=!ready;
 if(!simulation){$('seek').value=0;$('seek').max=1;$('playback-time').textContent='00:00 / 00:00';$('playback-state').textContent=ready?'Lista para despegar':'Selecciona una ruta';}
}
function updateFlightLog(sample){
 const signature=`${sample.time_s>= (simulation.detection?.detected_at_s??Infinity)}:${sample.time_s>= (simulation.detection?.reported_at_s??Infinity)}:${sample.ended}`;
 if(signature===lastLog)return;lastLog=signature;$('log').replaceChildren();
 const add=text=>{const li=document.createElement('li');li.textContent=text;$('log').append(li);};
 add(simulation.scenario==='nominal'?'Recorrido nominal sin sorteo de fallas.':`Semilla ${simulation.seed}: ${simulation.active_threat_ids.length} amenazas activadas. Distribución uniforme [0,100).`);
 if(simulation.detection&&sample.time_s>=simulation.detection.detected_at_s)add(`Foco detectado: ${simulation.detection.fire_coordinates.map(v=>v.toFixed(5)).join(', ')}. Verificando durante 60 s.`);
 if(simulation.detection&&sample.time_s>=simulation.detection.reported_at_s)add('Foco reportado. Regreso iniciado.');
 if(sample.ended)add(`Fin: ${simulation.status} · servicio ${simulation.mission_completed?'cumplido':'interrumpido'}.`);
}
function renderFlight(force=false,now=performance.now()){
 if(!simulation)return;const sample=sampleFlight(simulation.timeline,clock);if(!sample)return;
 drone?.setLatLng([sample.coordinates[1],sample.coordinates[0]]);
 if(view3d&&(force||now-lastRender>=70)){terrainView?.setFlightPose(sample.position_utm,sample.look_ahead,$('follow-drone').checked);lastRender=now;}
 if(!view3d&&$('follow-drone').checked&&(force||now-lastFollow>250)){map.panTo([sample.coordinates[1],sample.coordinates[0]],{animate:false});lastFollow=now;}
 $('flight').textContent=`${phaseNames[sample.phase]||sample.phase} · ${clockLabel(sample.time_s)} / ${clockLabel(simulation.time_s)}\nBatería útil ${sample.battery_pct.toFixed(1)} % · cota ${sample.coordinates[2].toFixed(1)} m EGM2008`;
 $('progress').value=100*sample.time_s/Math.max(1,simulation.time_s);$('seek').max=simulation.time_s;$('seek').value=sample.time_s;
 $('playback-time').textContent=`${clockLabel(sample.time_s)} / ${clockLabel(simulation.time_s)}`;$('playback-state').textContent=phaseNames[sample.phase]||sample.phase;
 const dx=sample.look_ahead[0]-sample.position_utm[0],dy=sample.look_ahead[1]-sample.position_utm[1];
 $('fpv-heading').textContent=`Rumbo ${((Math.atan2(dx,dy)*180/Math.PI+360)%360).toFixed(0)}°`;$('fpv-height').textContent=`Cota ${sample.coordinates[2].toFixed(0)} m`;$('fpv-battery').textContent=`Batería ${sample.battery_pct.toFixed(0)} %`;
 $('fpv-hud').hidden=!view3d||$('drone-view').getAttribute('aria-pressed')!=='true';updateFlightLog(sample);
 $('player').dataset.time=sample.time_s.toFixed(2);$('player').dataset.phase=sample.phase;$('player').dataset.playing=String(playing);
}
async function preparePlayback(scenario,autoplay=true){
 if(simulationLoading||calculating||!fresh)return;
 playing=false;simulationLoading=true;refreshPlaybackControls();message(scenario==='nominal'?'Preparando el recorrido desde la base…':'Sorteando amenazas y verificando retorno…');
 const revision=configurationRevision,chosen=$('chosen').value,set=$('route-mode').value;
 try{const answer=await api('/api/aereo/patrullaje/simular',{sha256:result.sha256,method:chosen,route_set:set,scenario,seed:Number($('seed').value),fire});
 if(revision!==configurationRevision||chosen!==$('chosen').value||set!==$('route-mode').value)return;
 simulation=answer;activeIds=new Set(simulation.active_threat_ids);refreshSources();flightLayer.clearLayers();
 const first=simulation.timeline[0];drone=L.marker([first.coordinates[1],first.coordinates[0]],{icon:L.divIcon({className:'drone-icon',html:'✥',iconSize:[28,28],iconAnchor:[14,14]})}).addTo(flightLayer);
 const returns=simulation.timeline.filter(f=>f.phase==='return');if(returns.length)L.polyline(returns.map(f=>[f.coordinates[1],f.coordinates[0]]),{color:'#d45732',weight:3,dashArray:'6 4'}).addTo(flightLayer);
 clock=0;lastFrame=0;lastLog='';playing=autoplay;$('replan').disabled=scenario==='nominal';renderFlight(true);
 message(scenario==='nominal'?'Recorrido listo: despegue, vigilancia y aterrizaje.':`Simulación lista: ${simulation.status}.`);
 }catch(e){message(e.message,true);}finally{simulationLoading=false;refreshPlaybackControls();}
}
$('simulate').onclick=()=>preparePlayback('sampled');$('replay-nominal').onclick=()=>preparePlayback('nominal',false);
$('play').onclick=async()=>{if(!simulation)return preparePlayback('nominal');if(clock>=simulation.time_s)clock=0;playing=true;lastFrame=0;refreshPlaybackControls();renderFlight(true);};
$('pause').onclick=()=>{playing=false;lastFrame=0;refreshPlaybackControls();renderFlight(true);};
function seekFlight(seconds){if(!simulation)return;clock=Math.max(0,Math.min(seconds,simulation.time_s));playing=false;lastFrame=0;refreshPlaybackControls();renderFlight(true);}
$('restart').onclick=()=>seekFlight(0);$('finish-playback').onclick=()=>seekFlight(simulation?.time_s||0);$('seek').oninput=()=>seekFlight(Number($('seek').value));
$('follow-drone').onchange=()=>renderFlight(true);
$('drone-view').onclick=async()=>{if(!simulation)return;if($('drone-view').getAttribute('aria-pressed')==='true'){exitDroneView();return;}if(!await setView3d(true))return;const sample=sampleFlight(simulation.timeline,clock);terrainView.setFlightPose(sample.position_utm,sample.look_ahead,false);terrainView.setFirstPerson(true);$('drone-view').setAttribute('aria-pressed','true');renderFlight(true);};
function animate(now){requestAnimationFrame(animate);if(!simulation||!playing)return;if(lastFrame)clock=Math.min(simulation.time_s,clock+(now-lastFrame)/1000*Number($('speed').value));lastFrame=now;
 if(clock>=simulation.time_s){playing=false;refreshPlaybackControls();renderFlight(true,now);}else renderFlight(false,now);
}
requestAnimationFrame(animate);
document.addEventListener('visibilitychange',()=>{if(document.hidden&&playing){playing=false;lastFrame=0;refreshPlaybackControls();}});
function redrawVertices(){$('finish').disabled=vertices.length<3;$('draw-tools').dataset.vertices=vertices.length;$('area-status').textContent=`${vertices.length} vértices · cierra el polígono al terminar.`;selection.clearLayers();L.polyline(vertices.map(p=>[p[1],p[0]]),{color:'#31683d'}).addTo(selection);for(const v of vertices)L.circleMarker([v[1],v[0]],{radius:4}).addTo(selection);}
$('undo-vertex').onclick=()=>{if(mode==='polygon'){vertices.pop();redrawVertices();}};
$('cancel-draw').onclick=()=>{mode='';vertices=[];$('finish').disabled=true;$('draw-tools').hidden=true;selection.clearLayers();if(target)L.geoJSON(target,{style:{color:'#255e40',weight:2,fillOpacity:.15}}).addTo(selection);$('area-status').textContent=target?'Se conserva el objetivo anterior.':'Dibuja un polígono dentro de vigilancia.';message('Edición cancelada.');};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','TEXTAREA','BUTTON'].includes(document.activeElement.tagName))return;if(e.key==='Escape'){if(mode)$('cancel-draw').click();else exitDroneView();}if(mode==='polygon'&&(e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();$('undo-vertex').click();}if(e.code==='Space'&&fresh&&!mode){e.preventDefault();playing?$('pause').click():$('play').click();}});
$("replan").onclick = async () => {
  if (!simulation) return;
  for (const threat of result.threats)
    if (activeIds.has(threat.id) && threat.probability_pct < 100)
      events.push({ geometry: threat.geometry, probability_pct: 100 });
  drawEvents();
  await calculate();
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
$("export").onclick = () =>
  download("patrullaje.json", {
    result,
    simulation,
    comparison_history: comparisonHistory,
  });
$("failures").onclick = () =>
  download("failure_probabilities.json", result.failure_probabilities);
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
    model = await api("/api/aereo/patrullaje/mapa");
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
      L.circleMarker([b.geometry.coordinates[1], b.geometry.coordinates[0]], {
        radius: 6,
        color: "#ae791c",
        fillOpacity: 0.8,
      })
        .bindPopup(
          popup(b.name, {
            ...b,
            hypothetical_station: true,
            battery_inventory: 1,
            service_s: 120,
          }),
        )
        .addTo(map);
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
    $("weather").value =
      model.weather.find((w) => Math.max(w.wind_speed_ms, w.wind_gust_ms) < 8)
        ?.valid_at || model.reference_time;
    for (const key of ["M2", "A2", "A3", "A4"])
      sourceLayers[key] = L.layerGroup();
    sourceLayers.A3.addTo(map);
    layerControl = L.control
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
    const communes = new Set(
      model.layers.M2.map((r) => r.attributes?.commune || r.commune).filter(
        Boolean,
      ),
    );
    [...communes].sort().forEach((c) => $("commune").append(new Option(c, c)));
    for (const b of model.base_catalogue)
      L.circleMarker([b.geometry.coordinates[1], b.geometry.coordinates[0]], {
        radius: 4,
        color: "#7b7056",
      })
        .bindPopup(() => popup("Catálogo M1", b))
        .addTo(catalogueLayer);
    refreshSources();
    wind();
    $("engine").textContent = model.engine;
    message("Selecciona un polígono o carga el ejemplo para comenzar.");
  } catch (e) {
    message(e.message, true);
  }
})();
