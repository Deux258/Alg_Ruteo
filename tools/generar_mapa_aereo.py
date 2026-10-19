"""Comparación geográfica reproducible; SVG sin dependencias, PNG opcional Pillow."""

import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evidencia/aereo_2026-10-17"


def main():
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--png", action="store_true")
    args = p.parse_args()

    def read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    roads = read(ROOT / "evidencia/red_vial_2026-10-17/mapa_datos.geojson")
    air = read(ROOT / "evidencia/local/aereo/mapa.json")
    result = read(ROOT / "evidencia/local/aereo/ruta.json")
    bbox = read(ROOT / "config/proyecto.json")["bbox_wgs84"]
    parts = []
    draw = None
    width, height = 1600, 1060
    if args.png:
        from PIL import Image, ImageDraw, ImageFont

        bitmap = Image.new("RGB", (width, height), "#f7faf8")
        draw = ImageDraw.Draw(bitmap)

        def font(size):
            for path in [
                "C:/Windows/Fonts/arial.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]:
                if Path(path).exists():
                    return ImageFont.truetype(path, size)
            return ImageFont.load_default(size=size)

    def text(x, y, value, size=20, color="#223d41"):
        parts.append(
            f'<text x="{x}" y="{y+size}" font-family="Arial,sans-serif" font-size="{size}" fill="{color}">{html.escape(value)}</text>'
        )
        if draw:
            draw.text((x, y), value, font=font(size), fill=color)

    def line(coords, color, stroke=1, dash=False):
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in coords)
        extra = ' stroke-dasharray="7 5"' if dash else ""
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{stroke}"{extra}/>'
        )
        if draw:
            draw.line(coords, fill=color, width=round(stroke))

    def circle(x, y, r, color):
        parts.append(
            f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}" stroke="white"/>'
        )
        if draw:
            draw.ellipse(
                (x - r, y - r, x + r, y + r), fill=color, outline="white", width=1
            )

    cos = math.cos(math.radians((bbox[1] + bbox[3]) / 2))
    dx = (bbox[2] - bbox[0]) * cos
    dy = bbox[3] - bbox[1]
    scale = min(720 / dx, 680 / dy)

    def project(c, left):
        return (
            left + (720 - dx * scale) / 2 + (c[0] - bbox[0]) * cos * scale,
            175 + (680 - dy * scale) / 2 + (bbox[3] - c[1]) * scale,
        )

    text(48, 25, "Valparaíso · de calles a corredores aéreos para drones", 32)
    text(
        48,
        73,
        "Mismo polígono de 54,92 km² · datos S1–S7 · despeje vertical no verificado",
        20,
    )
    text(48, 119, "ANTERIOR · red vial OSM", 23)
    text(832, 119, "ACTUAL · 87 nodos / 556 arcos aéreos", 23)
    area = air["area"]
    polygons = (
        [area["coordinates"]] if area["type"] == "Polygon" else area["coordinates"]
    )
    for left in [48, 832]:
        for polygon in polygons:
            for ring in polygon:
                line([project(c, left) for c in ring], "#3e8d64", 2)
        text(left + 695, 175, "N", 20)
    for f in roads["features"]:
        line([project(c, 48) for c in f["geometry"]["coordinates"]], "#9daeb3")
    for f in air["features"]:
        if f["geometry"]["type"] == "LineString":
            line([project(c, 832) for c in f["geometry"]["coordinates"]], "#aab8bc")
        else:
            circle(*project(f["geometry"]["coordinates"], 832), 3, "#657e85")
    colors = ["#1766b1", "#b24778", "#a46f12"]
    for f in result["features"]:
        line(
            [project(c, 832) for c in f["geometry"]["coordinates"]],
            colors[f["properties"]["rank"] - 1],
            3,
            f["properties"]["role"] == "return",
        )
    circle(*project(air["default_origin"], 832), 7, "#cf6c24")
    text(48, 889, "Las conexiones y sentidos de las calles ya no rigen el vuelo.", 19)
    text(48, 920, "OSM permanece disponible como fondo cartográfico opcional.", 19)
    text(48, 951, "Base real inicial: Bomberos Laguna Verde, SENAPRED 104.", 19)
    for i, p in enumerate(result["alternatives"]):
        text(
            832,
            887 + 32 * i,
            f"Misión {p['rank']}: {p['length_km']:.3f} km · {p['time_s']:.1f} s",
            19,
            colors[i],
        )
    text(
        48,
        1018,
        "Corredores derivados, no vuelos observados. Escenario histórico UTC: "
        + result["time"][:16]
        + ". © OSM contributors (panel izquierdo).",
        16,
    )
    OUT.mkdir(exist_ok=True, parents=True)
    (OUT / "comparacion.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="#f7faf8"/>'
        + "".join(parts)
        + "</svg>",
        encoding="utf-8",
    )
    if draw:
        bitmap.save(OUT / "comparacion.png")


if __name__ == "__main__":
    main()
