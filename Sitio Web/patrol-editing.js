// Geometry editing has no dependency on the map, playback, or network state.
export function normalizeTarget(value) {
  let geometry = value;
  if (geometry?.type === "FeatureCollection") {
    if (geometry.features?.length !== 1)
      throw new Error("Carga una sola área por misión.");
    geometry = geometry.features[0];
  }
  if (geometry?.type === "Feature") geometry = geometry.geometry;
  if (geometry?.type !== "Polygon")
    throw new Error("Importa un Polygon GeoJSON.");
  if (
    !Array.isArray(geometry.coordinates) ||
    !geometry.coordinates.length ||
    geometry.coordinates.some(
      (ring) =>
        !Array.isArray(ring) ||
        ring.length < 4 ||
        ring.some(
          (point) =>
            !Array.isArray(point) ||
            point.length < 2 ||
            !Number.isFinite(point[0]) ||
            !Number.isFinite(point[1]) ||
            Math.abs(point[0]) > 180 ||
            Math.abs(point[1]) > 90,
        ) ||
        ring[0][0] !== ring.at(-1)[0] ||
        ring[0][1] !== ring.at(-1)[1],
    )
  )
    throw new Error(
      "El polígono debe tener anillos cerrados y coordenadas WGS84 válidas.",
    );
  return structuredClone(geometry);
}

export function circlePolygon(lon, lat, radius) {
  if (
    !Number.isFinite(lon) ||
    !Number.isFinite(lat) ||
    Math.abs(lon) > 180 ||
    Math.abs(lat) >= 90 ||
    !Number.isFinite(radius) ||
    radius <= 0 ||
    radius > 500
  )
    throw new Error("Revisa coordenadas y radio de la amenaza.");
  const ring = Array.from({ length: 64 }, (_, i) => {
    const angle = (2 * Math.PI * i) / 64;
    return [
      lon +
        (radius * Math.cos(angle)) / (111320 * Math.cos((lat * Math.PI) / 180)),
      lat + (radius * Math.sin(angle)) / 111320,
    ];
  });
  ring.push([...ring[0]]);
  return { type: "Polygon", coordinates: [ring] };
}
