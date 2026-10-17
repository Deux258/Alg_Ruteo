# Evidencias y diccionario

El resultado vigente está explicado en [INFORME.md](INFORME.md). Los archivos se
generaron con BD PostGIS/pgRouting real; no son resultados simulados.

| Archivos | Estructura y significado |
|---|---|
| `arranque_limpio.json`, `arranque_online.json`, `repeticion.json`, `ejecucion_primera_vial.json` | Resumen del pipeline: `run_id` UUID, `mode` adquisición, `scope` alcance, `status` publicación, `counts.I` nodos+arcos, `duration_s` segundos, `steps` tiempos ET/carga, `recorded_at_utc` captura. `topology` es la auditoría descrita abajo. `idempotent=true` identifica una repetición sin nueva carga. |
| `validacion_bd.json` | `versions` motor real; `table_count` tablas; `dataset_sha256` salida cargada; `duplicates` y `duplicate_arcs` conteos de duplicados; `unreachable_example` destino real rechazado; `base` instalación y nodo vial; `validation` auditoría completa. `turn_restrictions` y `spatial_filter` conservan el linaje del constructor. |
| `validation` / `topology` | `nodes`, `directed_edges`, `isolated_nodes`, `weak_count`, `strong_count` conteos físicos; `weak_components`/`strong_components` listas de ID/tamaño; `invalid_edges` extremos incompatibles. `spatial` cuenta geometrías fuera y área en km². `road_routing` registra `ready`, base, `checks`, nodos alcanzables/no alcanzables y tres `examples` con `distance_km`, `edge_count`, coordenadas y calles. |
| `auditoria_espacial.json` | `aoi` validez, WGS84, envolvente y área UTM; `nodes` dentro/fuera/bases; `edges` segmentos completos y extremos cubiertos; `delimitation_matches` solo es true si no hay geometrías fuera; `predicate` ST_Covers sin buffer; `files_sha256` vincula salida y límite exactos. |
| `evaluacion_bases.json` | `candidates`: registros originales de instalaciones dentro, `source`, ID, nombre y geometría; `offset_m` separación al nodo vial, `road_node_id` ID interno, `reachable_nodes` cantidad alcanzable y `maximum_distance_km` costo máximo. `selected` es la elección configurada. `source_sha256` vincula el original. Umbrales en `criterion`. |
| `ruta_1.geojson` .. `ruta_3.geojson` | FeatureCollection WGS84, una LineString continua. `properties`: source/target/run_id, `distance_km` suma PostGIS, `dijkstra_cost_km` agregado pgRouting, `edge_count`, `edge_ids`, `node_ids` en orden, `streets`, `algorithm`, `respects_turns`, `facility_to_road_included=false`. `label` del ejemplo en propiedades de colección. IDs grandes como texto. |
| `base.geojson` | Dos puntos originales separados: `role=real_facility` (SENAPRED, ID/nombre) y `routing_origin` (nodo OSM existente, `offset_m`, `access_modelled=false`). No contiene un enlace entre ambos. |
| `mapa_datos.geojson` | Corredores físicos únicos para visualización; `id` arco representativo, `name`/`highway` etiquetas OSM y `osm_way_id` procedencia. `area` polígono, `base`, `examples`, `attribution` y `limitations`. No reemplaza la salida de infraestructura dirigida. |
| `http_snapshot.json`, `http_online.json` | URL, fecha UTC y `checks` con path, código HTTP y respuesta efectivamente observada. `successful` exige cumplir todos los códigos y validaciones del script. |
| `pruebas_finales.json` | `tests_run`, `failures`, `errors`, `skipped` conteos; `successful`, `omitted`, `duration_s`, Python y `database_versions`. Resultado vigente de 74 pruebas. `pruebas_finales.log` identifica cada prueba. |
| `pruebas_72.json` | Corrida anterior exitosa, conservada; no sustituye la final. |
| `intento_preliminar_base_descartada.json` | Corrida preliminar con errores, `successful=false`; no evidencia éxito actual. |
| `manifest_online.json` | Misma estructura de `datos/entrada/vial/manifest.json`; corte descargado para el arranque online limpio. Sus originales de contenido identificado por hash están conservados en esa carpeta. |
| `inspeccion_fuentes.json` | Inventario inicial: conteos por tipo/clase OSM, instalaciones consultadas y relaciones originales. Es diagnóstico de adquisición, no el conteo de la red final filtrada. |
| `*.log` de arranque/repetición | Salida de `main` y Compose, construcción, salud y resumen real. Los mensajes SQL esperados de rechazo durante pruebas no implican fallos si el resultado de la prueba es `ok`. |
| `mapa_comparativo.svg/png`, `interfaz_ruta.png`, `interfaz_mapa.png` | Comparación de geometrías a escala común, captura de la interfaz con su resultado y vista breve del mapa. No son imágenes generadas por IA ni sustituyen las auditorías numéricas. |

Todos los GeoJSON usan `[longitud, latitud]` en grados WGS84. Las distancias de
ruteo están en km y los desplazamientos al origen en metros UTM 19S. `null`
conserva un dato desconocido; no equivale a cero. Los JSON internos del pipeline
siguen el [contrato de infraestructura](../../Infraestructura/DICCIONARIO.md).

## Regenerar evidencia

Desde Bash en la raíz, con la aplicación habilitada (agregar el mismo
`COMPOSE_PROJECT_NAME` si se usa una instancia distinta de la predeterminada):

```bash
./main probar
docker compose run --rm --no-deps -v "$PWD/evidencia/local:/app/evidencia/exportada" etl python -m tools.capturar_evidencia_vial --output /app/evidencia/exportada
docker compose run --rm --no-deps -v "$PWD/evidencia/local:/app/evidencia/exportada" etl python -m core.spatial_audit --dataset /app/datos/runs/4718c905-d0bf-52bf-a82b-33525cc936fd/infraestructura.json --output /app/evidencia/exportada/auditoria_espacial.json --require-match
```

Usar el run indicado por `/health` si los originales cambian. El exportador lee
la publicación vigente sin escribir en la BD. Para regenerar la figura histórica,
los archivos de entrada son los conservados en esta carpeta:

```bash
docker compose run --rm --no-deps -v "$PWD/evidencia:/app/evidencia" etl python -m tools.generar_mapa_vial
docker compose run --rm --no-deps -v "$PWD/BD:/app/BD" etl python -m tools.generar_diagrama_vial
```

Ambos generadores SVG usan solo Python estándar. La opción adicional `--png`
del generador de mapa requiere Pillow en el entorno que genere esa copia; es
opcional y no participa en la ejecución del servicio.

El control HTTP también es independiente de librerías externas:

```bash
python tools/verificar_api_vial.py --url http://127.0.0.1:18081 --unreachable 2648934237786465 --output evidencia/local/http.json
```

Si se actualiza la red, obtener un destino inalcanzable del nuevo
`validacion_bd.json`; no asumir que ese ID conservará el mismo estado.
