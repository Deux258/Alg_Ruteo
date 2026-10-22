# M5: obstáculos

Fuente: S8, OpenStreetMap mediante Overpass. La consulta, fecha UTC, licencia,
respuestas originales y SHA-256 están en `datos/entrada/vigilancia/manifest.json`.
Extractor/cargador principal: `core.patrol_data.prepare`. Entrada independiente:
`python -m Metadata.m5_obstaculos --output RUTA` o `--load RUTA`.

Sobre `patrol-dataset-1`: `run_id`, `dataset_key=M5`, `geometry_crs=EPSG:32719`,
`records_sha256` y `lineage` con manifiesto e identidad de entradas. La extracción
produce `datos/runs/<run>/M5.json`; la carga usa transacción y no consulta la red.

| Campo | Tipo/unidad | Significado |
|---|---|---|
| provider_id | texto | Tipo OSM/ID original, por ejemplo way/123. |
| kind | categoría | building, power_line, tower o antenna. |
| height_m | número m o null | Altura declarada, normalizada; null no equivale a cero. |
| quality | categoría | height_declared o height_unknown. |
| geometry_quality | categoría | provider_geometry o invalid_relation_conservative_hull. |
| original_tags | objeto | Etiquetas conservadas, incluidas unidades y procedencia de alturas. |
| geometry | geometría métrica | Objeto observado o envolvente conservadora identificada. |
| exclusion | geometría métrica | Buffer de 20 o 30 m según tipo. |

Destino: `routing.flight_obstacles` y catálogo `routing.patrol_datasets`.
Se conservan las alturas ausentes y no se convierten pisos en alturas observadas.
Un `remark` Overpass de error invalida la adquisición; un inventario vacío validado
conserva su estado y procedencia. Repetir el JSON idéntico no duplica obstáculos.
Atribución: © OpenStreetMap contributors, ODbL 1.0.
