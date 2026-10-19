"""Mapa comparativo a partir de evidencia capturada, sin cartografía inventada.

Python estándar genera SVG. --png requiere Pillow solo para la figura opcional;
no es una dependencia del servicio. No descarga teselas ni usa servicios web.
"""

import argparse
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "evidencia/red_vial_2026-10-17"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--png", action="store_true")
    args = parser.parse_args()
    data = read(FOLDER / "mapa_datos.geojson")
    old = read(ROOT / "datos/ejemplos/infraestructura.json")
    routes = [read(FOLDER / f"ruta_{n}.geojson") for n in range(1, 4)]
    bbox = read(ROOT / "config/proyecto.json")["bbox_wgs84"]
    polygons = (
        [data["area"]["coordinates"]]
        if data["area"]["type"] == "Polygon"
        else data["area"]["coordinates"]
    )
    rings = [ring for polygon in polygons for ring in polygon]
    width, height = 1600, 1060
    elements = []
    drawing = None
    if args.png:
        from PIL import Image, ImageDraw, ImageFont

        bitmap = Image.new("RGB", (width, height), "#f8faf8")
        drawing = ImageDraw.Draw(bitmap)

        def font(size):
            for path in [
                "C:/Windows/Fonts/arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]:
                if Path(path).exists():
                    return ImageFont.truetype(path, size)
            return ImageFont.load_default(size=size)

    def text(x, y, value, size=20, color="#233f41"):
        elements.append(
            f'<text x="{x}" y="{y+size}" fill="{color}" font-family="Arial,sans-serif" font-size="{size}">{html.escape(value)}</text>'
        )
        if drawing:
            drawing.text((x, y), value, fill=color, font=font(size))

    def line(coords, color, stroke=1):
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
        elements.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{stroke}"/>'
        )
        if drawing:
            drawing.line(coords, fill=color, width=max(1, round(stroke)))

    def circle(x, y, r, color):
        elements.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{color}" stroke="white" stroke-width="1.5"/>'
        )
        if drawing:
            drawing.ellipse(
                (x - r, y - r, x + r, y + r), fill=color, outline="white", width=2
            )

    text(48, 25, "Valparaíso · del recorte anterior a una red vial real", 32)
    text(
        48,
        72,
        "Mismo polígono suministrado · 54,92 km² · WGS84 · sin conexiones artificiales",
        20,
    )
    pw, ph = 720, 680
    cosine = math.cos(math.radians((bbox[1] + bbox[3]) / 2))
    dx = (bbox[2] - bbox[0]) * cosine
    dy = bbox[3] - bbox[1]
    scale = min(pw / dx, ph / dy)

    def project(c, left):
        return (
            left + (pw - dx * scale) / 2 + (c[0] - bbox[0]) * cosine * scale,
            175 + (ph - dy * scale) / 2 + (bbox[3] - c[1]) * scale,
        )

    text(48, 118, "ANTES · 13 nodos / 62 arcos / ninguna base", 22)
    text(832, 118, "AHORA · 15.499 nodos / 28.974 arcos", 22)
    for left in [48, 832]:
        for ring in rings:
            line([project(c, left) for c in ring], "#3e8d64", 2)
        text(left + pw - 23, 173, "N", 20)
        line([(left + pw - 17, 220), (left + pw - 17, 202)], "#233f41", 2)
        # Escala aproximada para visualización; costos reales se miden en UTM.
        bar = scale / 111.195
        line([(left + 15, 830), (left + 15 + bar, 830)], "#233f41", 3)
        text(left + 15, 835, "≈ 1 km", 15)
    for e in old["edges"]:
        line([project(c, 48) for c in e["geometry"]["coordinates"]], "#b87c72", 1)
    for n in old["nodes"]:
        circle(*project(n["geometry"]["coordinates"], 48), 3, "#934c40")
    for f in data["features"]:
        line([project(c, 832) for c in f["geometry"]["coordinates"]], "#a7b1b5", 1)
    colors = ["#1766b1", "#b84873", "#a57114"]
    for index, (route, color) in enumerate(zip(routes, colors)):
        for f in route["features"]:
            line([project(c, 832) for c in f["geometry"]["coordinates"]], color, 2)
            circle(*project(f["geometry"]["coordinates"][-1], 832), 4, color)
        text(
            832,
            903 + index * 29,
            f"{route['properties']['label']}: {route['properties']['distance_km']:.3f} km",
            19,
            color,
        )
    circle(*project(data["base"]["geometry"]["coordinates"], 832), 7, "#ce6d23")
    text(48, 903, "La malla anterior no representa conexiones de calles.", 19)
    text(48, 932, "El recorte conservó datos, pero eliminó todas sus bases.", 19)
    text(48, 961, "Fuente del panel: snapshot legado conservado.", 18)
    text(832, 990, "● Base real: 8.ª Comisaría Florida · SENAPRED 2872", 18, "#9a501e")
    text(
        48,
        1024,
        "Fuentes: © OpenStreetMap contributors (ODbL) · SENAPRED · polígono del usuario. No acredita tráfico ni acceso al recinto.",
        17,
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#f8faf8"/>'
        + "".join(elements)
        + "</svg>"
    )
    (FOLDER / "mapa_comparativo.svg").write_text(svg, encoding="utf-8")
    if drawing:
        bitmap.save(FOLDER / "mapa_comparativo.png")
    print("Mapa generado desde geometrías de evidencia, con escala geográfica común.")


if __name__ == "__main__":
    main()
