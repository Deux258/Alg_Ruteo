// Display formatting uses DOM text, never HTML from external metadata.
export function metadataPopup(title, obj) {
  const root = document.createElement("div"),
    heading = document.createElement("b");
  heading.textContent = title;
  root.append(heading);
  for (const [key, value] of Object.entries(obj)) {
    const row = document.createElement("div");
    row.className = "popup-row";
    row.textContent = `${key}: ${typeof value === "object" ? JSON.stringify(value) : (value ?? "sin dato")}`;
    root.append(row);
  }
  return root;
}

export function stationVisibleInCommune(station, bases, cut) {
  return (
    !cut ||
    (bases || []).some(
      (base) =>
        String(base.provider_id) === String(station.provider_id ?? station.id),
    )
  );
}

export function threatDisplayPosition(threat, project, height) {
  if (threat.display_anchor) {
    if (
      !Array.isArray(threat.display_anchor) ||
      threat.display_anchor.length !== 2 ||
      !threat.display_anchor.every(Number.isFinite)
    )
      return null;
    try {
      const [x, y] = project(threat.display_anchor),
        z = height(x, y);
      return Number.isFinite(z) ? [x, y, z + 10] : null;
    } catch {
      return null;
    }
  }
  const point = threat.position_utm;
  return Array.isArray(point) &&
    point.length === 3 &&
    point.every(Number.isFinite)
    ? point
    : null;
}
