"use strict";
const $ = (id) => document.getElementById(id);
const map = L.map("map", { preferCanvas: true }).setView([-33.08, -71.61], 13);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "© OpenStreetMap contributors",
  maxZoom: 19,
}).addTo(map);
const selection = L.layerGroup().addTo(map),
  routes = L.layerGroup().addTo(map);
let data = null,
  objectives = [],
  pick = null,
  result = null,
  rawResult = null,
  busy = false,
  revision = 0;
const colors = {
  reference: ["#53789f", "#9e667a"],
  proposed: ["#087753", "#dd8524"],
};
const names = { reference: "Dijkstra", proposed: "Propuesta" };
const reasons = {
  wind_outside_profile: "El viento supera el perfil.",
  temperature_outside_profile: "Temperatura fuera del perfil.",
  precipitation_outside_profile: "La precipitación supera el perfil.",
  visibility_outside_profile: "Visibilidad insuficiente.",
  missing_weather_time: "Faltan datos para la ventana completa de la misión.",
  unknown_weather: "Hay variables meteorológicas sin datos.",
  no_complete_mission_in_candidates:
    "No se encontró una misión completa entre los candidatos.",
  obstacle_intersection: "El recorrido intersecta un obstáculo.",
  insufficient_observation: "Cobertura de observación insuficiente.",
  insufficient_emergency_return:
    "El presupuesto no permite conservar el regreso.",
  insufficient_budget: "Presupuesto insuficiente.",
  surface_clearance: "Separación superficial insuficiente.",
};
const text = (tag, value, cls) => {
  const el = document.createElement(tag);
  el.textContent = value;
  if (cls) el.className = cls;
  return el;
};
const format = (n, d = 1) => (Number.isFinite(n) ? n.toFixed(d) : "—");
const percent = (n) => (Number.isFinite(n) ? n * 100 : null);
function coordinates(value) {
  const values = value.split(",").map((v) => Number(v.trim()));
  if (values.length !== 2 || values.some((v) => !Number.isFinite(v)))
    throw new Error("Escribe longitud, latitud.");
  return values;
}
function invalidate() {
  revision++;
  result = null;
  rawResult = null;
  $("export").disabled = true;
  routes.clearLayers();
  $("route-controls").replaceChildren();
  $("route-detail").replaceChildren();
  $("profile").style.display = "none";
  $("result").textContent = "Solicitud modificada. Calcula de nuevo.";
}
function renderSelection() {
  selection.clearLayers();
  try {
    const c = coordinates($("origin").value);
    L.marker([c[1], c[0]]).bindTooltip("Lanzamiento").addTo(selection);
  } catch (e) {}
  $("targets").replaceChildren();
  objectives.forEach((c, i) => {
    const li = text("li", `${i + 1}. ${c[0].toFixed(5)}, ${c[1].toFixed(5)}`);
    const b = text("button", "Quitar");
    b.type = "button";
    b.onclick = () => {
      objectives.splice(i, 1);
      invalidate();
      renderSelection();
    };
    li.append(b);
    $("targets").append(li);
    L.circle([c[1], c[0]], {
      radius: 50,
      color: "#008666",
      weight: 2,
      fillOpacity: 0.15,
    })
      .bindTooltip(`Objetivo ${i + 1}`)
      .addTo(selection);
  });
}
function addTarget(c) {
  if (objectives.length >= 3)
    throw new Error("La patrulla admite hasta tres objetivos.");
  if (objectives.some((v) => Math.hypot(v[0] - c[0], v[1] - c[1]) < 1e-8))
    throw new Error("Ese objetivo ya está seleccionado.");
  objectives.push(c);
  pick = null;
  invalidate();
  renderSelection();
  $("pick-status").textContent =
    `${objectives.length} objetivo(s) seleccionado(s).`;
}
map.on("click", (e) => {
  if (busy) return;
  const c = [e.latlng.lng, e.latlng.lat];
  if (pick === "origin") {
    $("origin").value = c.map((v) => v.toFixed(8)).join(", ");
    pick = null;
    invalidate();
    renderSelection();
  } else if (pick === "target") {
    try {
      addTarget(c);
    } catch (err) {
      $("pick-status").textContent = err.message;
    }
  }
});
$("pick-origin").onclick = () => {
  pick = "origin";
  $("pick-status").textContent = "Marca el punto de lanzamiento en el mapa.";
};
$("pick-target").onclick = () => {
  pick = "target";
  $("pick-status").textContent = "Marca un sector de observación en el mapa.";
};
$("add-target").onclick = () => {
  try {
    addTarget(coordinates($("target-coordinates").value));
    $("target-coordinates").value = "";
  } catch (e) {
    $("pick-status").textContent = e.message;
  }
};
$("clear").onclick = () => {
  objectives = [];
  invalidate();
  renderSelection();
};
$("base").onchange = () => {
  const b = data.bases[Number($("base").value)];
  $("origin").value = b.geometry.coordinates.join(", ");
  invalidate();
  renderSelection();
};
$("examples").onchange = () => {
  if ($("examples").value === "") return;
  try {
    addTarget(data.examples[Number($("examples").value)].coordinates);
  } catch (e) {
    $("pick-status").textContent = e.message;
  }
  $("examples").value = "";
};
for (const id of ["origin", "time", "budget", "wind", "coverage", "climb"])
  $(id).addEventListener("change", () => {
    invalidate();
    if (id === "origin") renderSelection();
  });
function request() {
  if (!objectives.length) throw new Error("Selecciona al menos un objetivo.");
  const preferences = { climb_factor: Number($("climb").value) };
  for (const [id, key] of [
    ["budget", "budget_eq_s"],
    ["wind", "wind_limit_ms"],
    ["coverage", "minimum_coverage"],
  ])
    if ($(id).value !== "")
      preferences[key] = Number($(id).value) / (id === "coverage" ? 100 : 1);
  return {
    origin: coordinates($("origin").value),
    objectives: objectives.map((c) => [...c]),
    time: $("time").value,
    preferences,
  };
}
function drawProfile(option) {
  const rows = option.evaluation.profile || [];
  const svg = $("profile");
  svg.replaceChildren();
  if (!rows.length) {
    svg.style.display = "none";
    return;
  }
  svg.style.display = "block";
  const ns = "http://www.w3.org/2000/svg";
  const maxT = Math.max(...rows.map((r) => r.elapsed_s), 1),
    minZ = Math.min(...rows.map((r) => r.surface_m)) - 10,
    maxZ = Math.max(...rows.map((r) => r.flight_m)) + 10;
  const xy = (t, z) => [
    35 + (t / maxT) * 305,
    125 - ((z - minZ) / (maxZ - minZ)) * 100,
  ];
  for (const [key, color] of [
    ["surface_m", "#a3ad8c"],
    ["flight_m", "#087753"],
  ]) {
    const line = document.createElementNS(ns, "polyline");
    line.setAttribute(
      "points",
      rows.map((r) => xy(r.elapsed_s, r[key]).join(",")).join(" "),
    );
    line.setAttribute("fill", "none");
    line.setAttribute("stroke", color);
    line.setAttribute("stroke-width", "2");
    svg.append(line);
  }
  const label = document.createElementNS(ns, "text");
  label.setAttribute("x", "10");
  label.setAttribute("y", "14");
  label.setAttribute("font-size", "10");
  label.textContent = `Altitud EGM2008 (m) · ${format(minZ, 0)}–${format(maxZ, 0)}`;
  svg.append(label);
  const time = document.createElementNS(ns, "text");
  time.setAttribute("x", "35");
  time.setAttribute("y", "145");
  time.setAttribute("font-size", "10");
  time.textContent = `Superficie y vuelo · ${format(maxT / 60)} min`;
  svg.append(time);
}
function details(method, option) {
  const area = $("route-detail");
  area.replaceChildren();
  area.append(
    text(
      "strong",
      `${names[method]} ${option.rank} · orden ${option.order.join(" → ")}`,
    ),
  );
  const e = option.evaluation;
  area.append(
    text(
      "div",
      `${format(option.length_km, 2)} km · ${format(e.time_s / 60)} min · ${format(e.consumption_eq_s, 0)} s equivalentes`,
    ),
  );
  area.append(
    text(
      "div",
      `Reserva final: ${format(e.final_reserve_fraction * 100)} % · cobertura mínima: ${format(e.minimum_coverage * 100)} %`,
    ),
  );
  if (!e.admissible)
    area.append(text("div", reasons[e.reason] || e.reason, "failure"));
  for (const t of e.timeline || [])
    area.append(
      text(
        "div",
        `Objetivo ${t.objective_id}: ${new Date(t.arrival_utc).toISOString().slice(11, 19)} UTC · ${format(t.coverage * 100)} % visible`,
      ),
    );
  drawProfile(option);
}
function renderResult(output) {
  routes.clearLayers();
  $("route-controls").replaceChildren();
  $("route-detail").replaceChildren();
  const sets = output.sets || { [output.method]: output };
  const area = $("result");
  area.replaceChildren();
  if (output.metrics) {
    area.append(
      text(
        "p",
        `Resiliencia del conjunto: Dijkstra ${format(percent(output.metrics.methods.reference.set_survival))} % · Propuesta ${format(percent(output.metrics.methods.proposed.set_survival))} %`,
      ),
    );
    area.append(
      text(
        "p",
        `Diferencial: ${format(output.metrics.delta_percentage_points, 2)} puntos porcentuales · ${output.metrics.valid_scenarios} escenarios válidos.`,
      ),
    );
  }
  let first = null;
  for (const [method, set] of Object.entries(sets)) {
    if (!set.alternatives.length) {
      area.append(
        text(
          "p",
          `${names[method]}: ${reasons[set.reason] || set.reason || set.status}`,
          "failure",
        ),
      );
      const causes = Object.entries(set.failure_causes || {});
      if (causes.length)
        area.append(
          text(
            "p",
            causes.map(([k, v]) => `${reasons[k] || k} (${v})`).join(" "),
            "hint",
          ),
        );
    } else {
      area.append(
        text(
          "p",
          `${names[method]}: ${set.alternatives.length} alternativa(s).`,
          "success",
        ),
      );
    }
    if (set.search_limited)
      area.append(
        text(
          "p",
          `${names[method]}: búsqueda acotada a los candidatos del perfil.`,
          "hint",
        ),
      );
    for (const option of set.alternatives) {
      const color = colors[method][option.rank - 1];
      const layer = L.geoJSON(
        set.features.filter((f) => f.properties.rank === option.rank),
        {
          style: (f) => ({
            color,
            weight: f.geometry.type === "LineString" ? 4 : 1,
            dashArray: f.properties.role === "return" ? "7 6" : null,
            fillColor: f.properties.role === "hidden" ? "#ad4838" : color,
            fillOpacity: f.properties.role === "footprint" ? 0 : 0.18,
          }),
        },
      );
      layer.addTo(routes);
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.onchange = () => {
        if (checkbox.checked) routes.addLayer(layer);
        else routes.removeLayer(layer);
      };
      const button = text(
        "button",
        `${method === "reference" ? "D" : "P"}${option.rank}`,
      );
      button.type = "button";
      button.className = "secondary";
      button.style.color = color;
      button.onclick = () => details(method, option);
      label.append(checkbox, button);
      $("route-controls").append(label);
      if (!first) first = [method, option];
    }
  }
  if (first) details(...first);
  else $("profile").style.display = "none";
  const flightFeatures=output.features.filter(f=>f.geometry.type==='LineString');
  if(flightFeatures.length){const bounds=L.geoJSON(flightFeatures).getBounds();if(bounds.isValid())map.fitBounds(bounds.pad(.35),{maxZoom:16});}
}
async function calculate(comparison) {
  if (busy) return;
  let body;
  try {
    body = request();
  } catch (e) {
    $("result").textContent = e.message;
    return;
  }
  invalidate();
  const submitted = revision;
  busy = true;
  for (const id of ["calculate", "compare"]) $(id).disabled = true;
  $("result").textContent = "Calculando corredores, observación y retorno…";
  try {
    const response = await fetch(
      "/api/v1/vigilancia/" + (comparison ? "comparar" : "planificar"),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
    const raw = await response.text();
    const output = JSON.parse(raw);
    if (submitted !== revision) return;
    if (!response.ok) throw new Error(output.error || "No se pudo calcular.");
    result = output;
    rawResult = raw;
    renderResult(output);
    $("export").disabled = false;
  } catch (e) {
    if (submitted === revision) $("result").textContent = e.message;
  } finally {
    busy = false;
    for (const id of ["calculate", "compare"]) $(id).disabled = false;
  }
}
$("calculate").onclick = () => calculate(false);
$("compare").onclick = () => calculate(true);
$("export").onclick = () => {
  if (!result) return;
  const blob = new Blob([rawResult], {
    type: "application/json",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "vigilancia-resultado.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
};
async function init() {
  try {
    const response = await fetch("/api/v1/vigilancia/mapa");
    data = await response.json();
    if (!response.ok) throw new Error(data.error || "Datos no disponibles.");
    const area = L.geoJSON(data.area, {
      style: { color: "#397257", fillOpacity: 0.04, weight: 2 },
    }).addTo(map);
    map.fitBounds(area.getBounds());
    const refinementNames = {relief_variation: 'variación del relieve', known_obstacles: 'obstáculos conocidos', urban_forest_interface: 'interfaz urbana y vegetación'};
    const nodes = L.geoJSON(
      data.features.filter((f) => f.geometry.type === "Point"),
      {
        pointToLayer: (f, ll) =>
          L.circleMarker(ll, {
            radius: f.properties.resolution_m === 125 ? 2 : 3,
            color: f.properties.kind === "observation" ? "#21835e" : "#738b84",
            weight: 1,
            fillOpacity: 0.5,
          }),
        onEachFeature: (f, layer) => {
          const p=f.properties;const popup=document.createElement('div');
          popup.append(text('strong',p.kind==='observation'?'Punto de observación candidato':'Nodo de navegación'));
          popup.append(text('div',`Superficie: ${format(p.surface_m)} m EGM2008 · celda ${p.resolution_m} m`));
          popup.append(text('div',`Ubicación: ${(p.refinement_reasons||[]).map(r=>refinementNames[r]||r).join(', ')||'malla de cobertura territorial'}.`));
          layer.bindPopup(popup);
        },
      },
    );
    const corridors = L.geoJSON(
      data.features.filter((f) => f.properties.kind === "corridor"),
      { style: { color: "#94aaa2", weight: 1, opacity: 0.4 } },
    );
    const obstacles = L.geoJSON(
      data.features.filter((f) => f.properties.kind === "obstacle"),
      { style: { color: "#b85540", weight: 1, fillOpacity: 0.2 },onEachFeature:(f,layer)=>{
        const p=f.properties;const popup=document.createElement('div');
        popup.append(text('strong',`${p.obstacle_kind} · OSM ${p.provider_id}`));
        popup.append(text('div',`Altura declarada: ${Number.isFinite(p.height_m)?format(p.height_m)+' m':'desconocida'}`));
        if(p.geometry_quality==='invalid_relation_conservative_hull')popup.append(text('div','Relación incompleta: envolvente conservadora de sus miembros.'));
        layer.bindPopup(popup);
      } },
    ).addTo(map);
    const aip = L.geoJSON(data.layers.A3, {
      style: { color: "#8956a4", weight: 2, fillOpacity: 0.1 },
    }).addTo(map);
    const history = L.geoJSON(data.layers.A4, {
      style: { color: "#bc7a23", weight: 1, fillOpacity: 0.15 },
    });
    const vegetation = L.geoJSON(data.layers.M2, {
      style: { color: "#538b59", weight: 0.4, fillOpacity: 0.12 },
    });
    L.control
      .layers(null, {
        "Nodos adaptativos": nodes,
        Enlaces: corridors,
        Obstáculos: obstacles,
        "Espacio aéreo": aip,
        "Recurrencia histórica": history,
        "Cobertura de suelo": vegetation,
      })
      .addTo(map);
    $("base").replaceChildren();
    data.bases
      .filter((b) => b.candidate)
      .forEach((b) => {
        const i = data.bases.indexOf(b);
        const o = text("option", b.name);
        o.value = i;
        $("base").append(o);
      });
    $("origin").value =
      data.bases[Number($("base").value)].geometry.coordinates.join(", ");
    data.examples.slice(0, 400).forEach((r, i) => {
      const o = text(
        "option",
        `${i + 1} · superficie ${format(r.surface_m, 0)} m`,
      );
      o.value = i;
      $("examples").append(o);
    });
    $("time").replaceChildren();
    const fetched = new Date(data.weather_fetched_at);
    for (const w of data.weather) {
      const o = text(
        "option",
        `${w.valid_at.slice(0, 16).replace("T", " ")} · viento ${format(w.wind_100_ms)} m/s`,
      );
      o.value = w.valid_at;
      $("time").append(o);
    }
    const next = data.weather.find((w) => new Date(w.valid_at) >= fetched);
    if (next) $("time").value = next.valid_at;
    $("technical").append(text("p", data.profile.technical_assumptions));
    $("technical").append(
      text(
        "p",
        `Malla: 250/125 m · ${data.counts.states} estados · ${data.counts.directed_edges} arcos. Niveles: 60/90/120 m sobre superficie. Separación mínima: 40 m. Consumo nominal: 1500 s equivalentes, reserva 20 %. Observación: 60 s por sector.`,
      ),
    );
    $("technical").append(
      text(
        "p",
        `Fuentes: Copernicus GLO-30, CONAF/CIREN, SENAPRED, NASA FIRMS, DGAC AIP, Open-Meteo ECMWF y © OpenStreetMap contributors (ODbL). Meteorología obtenida: ${data.weather_fetched_at}.`,
      ),
    );
    $("result").textContent =
      "Elige el lanzamiento y los sectores de observación.";
    renderSelection();
  } catch (e) {
    $("result").textContent = e.message;
    $("calculate").disabled = true;
    $("compare").disabled = true;
  }
}
init();
