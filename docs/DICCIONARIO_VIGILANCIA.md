# Diccionario de vigilancia

Los once productos usan el sobre `patrol-dataset-1`, con `run_id`, `dataset_key`,
`geometry_crs`, `vertical_datum`, `records_sha256`, `lineage` y `records`.
`lineage` vincula el perfil, las fuentes y el constructor de la publicación. El hash
usa JSON canónico UTF-8, claves ordenadas, sin espacios y sin NaN. Las fechas llevan
zona horaria. El archivo completo está en `datos/runs/<run_id>/<clave>.json`.

El constructor, extractor y cargador común son `core.patrol_data.prepare`,
`core.patrol extraer` y `core.patrol cargar`. La carga no consulta proveedores y
reconciliará el contenido con la publicación correspondiente antes de aceptarlo.

| Producto | CRS | Campos principales y significado | Destino |
|---|---|---|---|
| I | EPSG:32719 | `states`: `id`, `anchor_id`, `kind` (navigation/observation), `resolution_m`, `refinement_reasons`, `surface_m`, `surface_offset_m`, `coordinates` X/Y/Z. `edges`: `id`, `source`, `target`, `coordinates`, `horizontal_km`, `flight_km`, `clearance_m`, `surface_known`, `blocked_obstacle`, `obstacle_distance_m`, `profile_samples`. | `flight_states`, `flight_edges`. El catálogo guarda resumen, tablas y hash sin duplicar el grafo completo. |
| M1 | EPSG:4326 | `provider_id`, `name`, `address`, `commune`, `geometry`, `candidate`, `inside_study`, `distance_to_study_m`, `selection_reason`, `source_refs`, `original_record`, `node_id` heredado. Instalación de referencia, sin desplazarla. | `patrol_datasets`; contexto de lanzamiento explícito. |
| M2 | EPSG:4326 | `provider_id`, `geometry`, `category`, `clipped_area_ha`, `attributes` (uso, subuso, estructura, cobertura, tipo/subtipo forestal y clase de altura originales), atributos de procedencia conservados. | `patrol_datasets`; refinamiento y sectores vegetados. |
| M3 | EPSG:32719 | `state_id` como texto, `surface_m`, `flight_m`, `vertical_datum=EGM2008`. Son cotas en metros, no alturas AGL. | `patrol_datasets`; relación con `flight_states`. |
| M4 | EPSG:4326 | `valid_at` UTC, `cell` [lon,lat] del proveedor, `temperature_c`, `relative_humidity_pct`, `wind_speed_ms` y `wind_direction_deg` a 10 m, `wind_100_ms`, `direction_100_deg`, `wind_gust_ms` a 10 m, `precipitation_mm` acumulada del intervalo horario y `visibility_m`. Ausentes se conservan como null. | `patrol_datasets`; tránsito y evaluación temporal. |
| M5 | EPSG:32719 | `provider_id`, `kind`, `height_m` o null, `quality`, `geometry_quality`, `original_tags`, `geometry`, `exclusion`. [Detalle](../Metadata/m5_obstaculos.md). | `flight_obstacles`, `patrol_datasets`. |
| A1 | EPSG:4326 | `valid_at`, `source=M4`, `rule_profile`, `state` active/unknown, `reason`. Una fila por hora fuera del perfil o sin datos críticos. | `patrol_datasets`; reglas meteorológicas. |
| A2 | EPSG:4326 | Detecciones FIRMS con coordenada, fecha/hora, confianza y atributos originales. La geometría de detección y su buffer son una aproximación de exclusión, sin afirmar perímetro del incendio. El archivo conserva vacío válido y linaje cuando no hay detecciones. | `patrol_datasets`; exclusiones temporales. |
| A3 | EPSG:4326 | `code`, `center`, `geometry`, `conditions`, `document_page`, límites y vigencia/procedencia extraídos del AIP. Conserva el significado y las unidades originales del documento. | `patrol_datasets`; exclusión conservadora. |
| A4 | EPSG:4326 | `provider_id`, `geometry`, `ordinal_class`, `class_label`, `period_start`, `period_end`, `repaired`. Clase ordinal histórica, sin interpretar frecuencia como probabilidad. | `patrol_datasets`; ponderación de cobertura. |
| A5 | EPSG:32719 | `provider_id`, `kind`, `geometry` de exclusión, `height_m` o null, `state=excluded_2d`. [Detalle](../Amenazas/a5_obstaculos.md). | `patrol_datasets`; exclusión materializada por M5. |

`profile_samples` contiene pares `[fracción_del_segmento, cota_DSM_m]`, con fracción
en [0,1]. La cota de vuelo interpola Z entre extremos. `obstacle_distance_m` mide
la distancia a la exclusión, truncada a 100 m para el costo. `clearance_m` conserva
la comprobación conservadora de toda la franja. `surface_known=false` impide dar
por verificado un corredor. Una distancia desconocida o altura ausente no es cero.

Los productos heredados M1, M2, A2, A3 y A4 conservan el contenido de la instantánea
anterior, por lo que sus fechas de observación no se reemplazan por la fecha de
construcción. Sus diccionarios originales están en `Metadata/` y `Amenazas/`.
