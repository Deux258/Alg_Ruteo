"""Imagen SVG del modelo ampliado: núcleo vial y las 18 tablas conservadas."""

import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1320" height="1120" viewBox="0 0 1320 1120">',
        '<rect width="1320" height="1120" fill="#f8faf8"/>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="none" stroke="#567875"/></marker></defs>',
    ]

    def text(x, y, value, size=18, color="#233f41"):
        parts.append(
            f'<text x="{x}" y="{y}" font-family="Arial,sans-serif" font-size="{size}" fill="{color}">{html.escape(value)}</text>'
        )

    def box(x, y, title, rows, new=False, width=340):
        height = 48 + 24 * len(rows)
        parts.append(
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="6" fill="{chr(35)+("e6f2e8" if new else "ffffff")}" stroke="#689581"/>'
        )
        text(x + 15, y + 29, title + (" · nueva" if new else ""), 20)
        for i, row in enumerate(rows):
            text(x + 15, y + 57 + 24 * i, row, 16)

    def arrow(points, label=None, labelxy=None):
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="#567875" stroke-width="1.8" marker-end="url(#arrow)"/>'
        )
        if label:
            text(*labelxy, label, 14)

    text(40, 43, "Valparaíso · esquema ampliado a 25 tablas", 30)
    text(
        40,
        76,
        "Núcleo vial y claves principales. Las FK incluyen run_id: no mezclan instantáneas.",
        19,
    )
    # Relaciones dibujadas antes de las cajas para que sus etiquetas sigan legibles.
    arrow("380,170 460,170", "1:N", (402, 157))
    arrow("630,244 630,310", "I / 1:N", (640, 280))
    arrow("500,244 500,270 210,270 210,310", "I / 1:N", (240, 260))
    arrow("380,360 460,360", "2 FK", (397, 348))
    arrow(
        "380,420 410,420 410,510 850,510 850,380 880,380",
        "nodo de incorporación",
        (580, 499),
    )
    arrow("630,478 630,560", "arco de llegada", (640, 544))
    arrow("460,610 380,610", "2 FK", (397, 596))
    arrow("460,455 425,455 425,690 380,690", "arco entrante", (250, 725))
    arrow("210,120 210,103 1050,103 1050,310", "run / 1:0..1", (1070, 230))
    box(
        40,
        120,
        "runs",
        ["PK run_id UUID", "input_hash / scope / mode", "status / configuration"],
    )
    box(
        460,
        120,
        "datasets",
        [
            "PK dataset_id; UQ run + key",
            "FK run_id / source_id",
            "file_sha256 / lineage / validation",
        ],
    )
    box(
        40,
        310,
        "nodes",
        [
            "PK (run_id, id BIGINT)",
            "UQ (run_id, natural_key)",
            "vial / base_candidata / legado",
            "geom Point, EPSG:32719",
        ],
    )
    box(
        460,
        310,
        "edges",
        [
            "PK (run_id, id BIGINT)",
            "FK source, target → nodes",
            "UQ (run_id, source, target)",
            "geom LineString / road_origin",
            "length_km = ST_Length / 1000",
        ],
    )
    box(
        880,
        310,
        "base_locations",
        [
            "PK/FK run_id → runs",
            "FK node_id → nodes",
            "FK source_id → sources",
            "geom real / name / provenance",
        ],
        True,
    )
    box(
        460,
        560,
        "road_states",
        ["PK (run_id, id)", "FK edge_id → edges", "context BIGINT[] de giros"],
        True,
    )
    box(
        40,
        560,
        "road_transitions",
        [
            "PK (run_id, id)",
            "FK source, target → states",
            "FK edge_id → edges",
            "UQ run + source + target",
        ],
        True,
    )
    text(
        40,
        786,
        "Las 18 tablas anteriores restantes se conservan sin sustituir sus funciones:",
        20,
    )
    box(
        40,
        810,
        "Procedencia (3)",
        ["schema_migrations", "sources", "publication"],
        width=270,
    )
    box(
        340,
        810,
        "Metadata (4)",
        ["base_metadata", "landcover", "node_elevation", "weather"],
        width=270,
    )
    box(
        640,
        810,
        "Amenazas (6)",
        [
            "hazards / weather_hazards",
            "thermal_events / airspace_zones",
            "historical_risk / edge_hazard",
        ],
        width=300,
    )
    box(
        970,
        810,
        "Rutas y evaluación (5)",
        ["profiles / route_sets", "routes / route_edges", "evaluations"],
        width=310,
    )
    text(
        40,
        1030,
        "El autómata recuerda giros; sus estados no son calles ni nodos físicos nuevos.",
        19,
    )
    text(
        40,
        1064,
        "Creación desde cero: BD/crear_bd.sql + BD/migraciones/002_red_vial.sql, aplicados por main.",
        18,
    )
    text(
        40,
        1095,
        "DDL completo y relaciones adicionales: crear_bd.sql y diagrama.dot (modelo inicial de 22 tablas).",
        17,
    )
    parts.append("</svg>")
    (ROOT / "BD/diagrama_vial.svg").write_text("".join(parts), encoding="utf-8")
    print("Diagrama vial SVG generado.")


if __name__ == "__main__":
    main()
