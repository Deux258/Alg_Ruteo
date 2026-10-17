# Contrato I: infraestructura.json, versión 1.0

Productor: `python -m Infraestructura.preparar_snapshot`. Cargador asociado:
`python -m Infraestructura.cargar RUTA/infraestructura.json`.
Validación: `infraestructura.schema.json` + `core/contracts.py`; controles finales
en SQL. Es un JSON interno con dos listas, no una FeatureCollection mixta.

| Campo | Tipo / unidad | Significado |
|---|---|---|
| schema_version | texto `1.0` | Versión del contrato. |
| run_id | UUID | Instantánea; por defecto UUIDv5 del hash de entrada en modo base/snapshot. |
| dataset_id | UUID | UUIDv5 del run y la clave `I`. |
| dataset_key | texto `I` | Salida de infraestructura; no confundir con una fuente externa. |
| source_id | `DERIVED_GRAPH` | Producto derivado de fase 1, cuya procedencia S1/S2 se conserva en el manifiesto original. |
| observed_at | ISO 8601 con zona | Corte documentado de la instantánea de fase 1; no actualidad del territorio. |
| extracted_at | ISO 8601 con zona | Obtención original de esa instantánea. En este adaptador congelado se conserva la fecha; `resumen.json` registra la ejecución actual. |
| crs | `EPSG:4326` | Las geometrías del JSON usan `[longitud, latitud]` en grados. |
| analysis_srid | entero `32719` | CRS métrico de la BD, UTM 19S. La carga transforma, no solo cambia la etiqueta SRID. |
| input_hash | SHA-256 hexadecimal | Hash canónico de nodos, arcos, CRS, linaje y versión del adaptador. |
| lineage.nodes / lineage.edges | objeto | Archivo relativo y SHA-256 del GeoJSON de entrada conservado. |
| extraction_mode | `snapshot` | Reconstrucción de datos existentes. No se presenta como descarga online. |
| nodes | lista no vacía | Nodos que se cargan en `routing.nodes`. |
| edges | lista no vacía | Arcos dirigidos que se cargan en `routing.edges`. |

## Elementos de nodes

| Campo | Tipo | Significado |
|---|---|---|
| id | BIGINT positivo | Primeros 63 bits de SHA-256 de natural_key. Una colisión detectada aborta; nunca renumera silenciosamente. |
| natural_key | texto | Vigilancia: `grid:32719:X:Y` con coordenadas de malla a 0,001 m. Bases: `base:S1:ID_PROVEEDOR`. |
| kind | enum | `vigilancia` o `base_candidata`. No afirma permisos ni recarga. |
| source_record_id | texto o null | Identificador externo de la instalación; null para nodos de malla. |
| geometry | Point | Posición WGS84, finita y dentro de rangos válidos. |

## Elementos de edges

| Campo | Tipo | Significado |
|---|---|---|
| id / natural_key | BIGINT / texto | Clave `arc:CLAVE_ORIGEN->CLAVE_DESTINO`; hash estable. |
| source / target | BIGINT | FK a nodos **del mismo run**. Los bucles y arcos paralelos por par ordenado se rechazan. |
| physical_key | texto | Par de claves de nodos ordenadas: los dos sentidos comparten corredor. Distinción útil para futuras fallas comunes. |
| geometry | LineString | Geometría orientada source → target; extremos coinciden con nodos. |

`length_km` **no se acepta del archivo**: PostGIS la genera como
`ST_Length(geom_32719)/1000`. Enlaces inversos son filas explícitas;
`reverse_cost=-1` evita inventar otro sentido en pgRouting. Se descartan exposición,
clima, estado y tiempos del GeoJSON legado; no alteran el grafo base.

La validación compara extremos en WGS84 (1e-9 grados); SQL comprueba nuevamente
los extremos proyectados con tolerancia de 1 mm. No se hace snapping automático.
Un grafo con dos componentes se informa como tal: no se añaden puentes ficticios.

## Salidas y documentación operativa

El JSON de datos se escribe en `datos/runs/<run_id>/infraestructura.json`. Su
cargador escribe dataset + nodos + arcos en una transacción. `resumen.json` y logs
son evidencia de ejecución y no fuentes ETL adicionales. El esquema JSON es un
contrato de validación, no otro dataset que deba importarse como infraestructura.
