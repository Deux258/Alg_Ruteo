"use strict";
const $ = (id) => document.getElementById(id),
  result = $("result");
const map = L.map("map", { preferCanvas: true }).setView([-33.075, -71.61], 13);
const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "© OpenStreetMap contributors",
});
$("tiles").addEventListener("change", (e) =>
  e.target.checked ? tiles.addTo(map) : map.removeLayer(tiles),
);
let routeLayer,
  targetMarker,
  requested = 0;
async function api(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "El servicio no está disponible");
  return data;
}
function plain(text) {
  const p = document.createElement("span");
  p.textContent = text;
  return p;
}
async function calculate(id) {
  const request = ++requested;
  result.className = "";
  result.textContent = "Calculando ruta por calles…";
  $("calculate").disabled = true;
  try {
    const data = await api("/api/ruta?destino=" + encodeURIComponent(id));
    if (request !== requested) return;
    if (routeLayer) map.removeLayer(routeLayer);
    routeLayer = L.geoJSON(data, {
      style: { color: "#1766b1", weight: 5, opacity: 0.95 },
    }).addTo(map);
    result.replaceChildren();
    const distance = document.createElement("strong");
    distance.className = "distance";
    distance.textContent = data.properties.distance_km.toFixed(3) + " km";
    result.append(distance);
    const details = document.createElement("p");
    details.textContent =
      (data.properties.edge_count || 0) +
      " arcos · sentidos y giros respetados";
    result.append(details);
    const streets = document.createElement("p");
    streets.className = "route-streets";
    streets.textContent = (data.properties.streets || []).join(" → ");
    result.append(streets);
    if (data.features.length) {
      map.fitBounds(routeLayer.getBounds(), { padding: [35, 35], maxZoom: 16 });
      const c = data.features[0].geometry.coordinates.at(-1);
      markDestination([c[1], c[0]]);
    }
  } catch (e) {
    if (request !== requested) return;
    if (routeLayer) {
      map.removeLayer(routeLayer);
      routeLayer = null;
    }
    result.className = "error";
    result.textContent = e.message;
  } finally {
    if (request === requested) $("calculate").disabled = false;
  }
}
function markDestination(latlng) {
  if (targetMarker) map.removeLayer(targetMarker);
  targetMarker = L.circleMarker(latlng, {
    radius: 6,
    color: "#fff",
    weight: 2,
    fillColor: "#1766b1",
    fillOpacity: 1,
  })
    .addTo(map)
    .bindTooltip("Destino");
}
$("calculate").addEventListener("click", () => {
  if ($("destinations").value) calculate($("destinations").value);
});
$("destinations").addEventListener("change", () => {
  $("calculate").disabled = !$("destinations").value;
});
map.on("click", async (e) => {
  try {
    const point = await api(
      "/api/nodo?lon=" + e.latlng.lng + "&lat=" + e.latlng.lat,
    );
    $("destinations").value = "";
    await calculate(point.id);
  } catch (error) {
    ++requested;
    if (routeLayer) {
      map.removeLayer(routeLayer);
      routeLayer = null;
    }
    if (targetMarker) {
      map.removeLayer(targetMarker);
      targetMarker = null;
    }
    $("calculate").disabled = !$("destinations").value;
    result.className = "error";
    result.textContent = error.message;
  }
});
(async () => {
  try {
    const [data, health] = await Promise.all([
      api("/api/mapa"),
      api("/health"),
    ]);
    const area = L.geoJSON(data.area, {
      style: {
        color: "#3e8d64",
        weight: 2,
        fillColor: "#a6c9b3",
        fillOpacity: 0.08,
      },
    }).addTo(map);
    map.fitBounds(area.getBounds(), { padding: [16, 16] });
    L.geoJSON(data, {
      style: { color: "#91a2a8", weight: 1.5, opacity: 0.8 },
      onEachFeature: (f, l) => l.bindTooltip(plain(f.properties.name)),
    }).addTo(map);
    if (!data.base)
      throw Error("Esta instantánea no contiene una base vial configurada");
    const b = data.base,
      c = b.geometry.coordinates,
      r = b.road_origin.coordinates;
    L.circleMarker([c[1], c[0]], {
      radius: 8,
      color: "#fff",
      weight: 2,
      fillColor: "#ce6d23",
      fillOpacity: 1,
    })
      .addTo(map)
      .bindTooltip(plain(b.name));
    L.circleMarker([r[1], r[0]], {
      radius: 5,
      color: "#fff",
      weight: 1,
      fillColor: "#1766b1",
      fillOpacity: 1,
    })
      .addTo(map)
      .bindTooltip("Inicio del cálculo vial");
    $("base-name").textContent = b.name;
    $("base-address").textContent = b.address;
    $("base-position").textContent =
      "Cuartel: " +
      c[1].toFixed(8) +
      ", " +
      c[0].toFixed(8) +
      " · SENAPRED " +
      b.provider_id;
    $("base-offset").textContent =
      "El cálculo empieza en una calle OSM a " +
      b.road_offset_m.toFixed(2) +
      " m del punto del catálogo. Ese acceso no se suma a la distancia vial.";
    for (const example of data.examples) {
      const option = document.createElement("option");
      option.value = example.target;
      option.textContent =
        example.label + " · " + example.distance_km.toFixed(2) + " km";
      $("destinations").append(option);
    }
    $("network-counts").textContent =
      health.network.nodes.toLocaleString("es-CL") +
      " nodos · " +
      health.network.directed_edges.toLocaleString("es-CL") +
      " arcos dirigidos";
    result.textContent =
      "Selecciona un destino o haz clic en una calle para calcular.";
  } catch (error) {
    result.className = "error";
    result.textContent = error.message;
  }
})();
