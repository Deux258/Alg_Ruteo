# Entradas conservadas de fase 1

Estas respuestas son entradas del adaptador, no nueve ETL nuevos. Se conservaron
los GeoJSON existentes para que la capa SQL se pueda probar sin depender de APIs.
Su transformación produce `infraestructura.json`, documentado en
`Infraestructura/DICCIONARIO.md`, y se carga con `Infraestructura/cargar.py`.

Ambos GeoJSON son FeatureCollection con geometría WGS84. `nodos.geojson` usa Point
y `aristas.geojson` LineString; la envoltura de cada entidad tiene `type`,
`geometry` y `properties`.

## nodos.geojson: propiedades legadas

| Campo | Tipo / unidad | Significado y uso en esta entrega |
|---|---|---|
| id | entero | Índice del piloto anterior; se traduce a ID estable y no se conserva como PK. |
| x / y | número, m | Coordenadas UTM 19S del punto de malla; forman su clave natural. |
| lon / lat | número, grados | Coordenadas redundantes; se usa la geometría del nodo. |
| tipo | texto | `vigilancia` o `base_candidata`; se conserva como kind. |
| fuente | texto | Descripción del origen anterior. |
| id_fuente | entero o null | ID de SENAPRED en bases; null en malla. Forma la clave natural de bases. |
| nombre | texto opcional | Nombre de la base; no se importa como M1. |
| elevacion_m | número, m | Muestreo DSM previo; no se importa como M3. |
| cobertura | texto | Clase territorial previa; no se importa como M2. |
| meteo_celda_lon / meteo_celda_lat | número, grados | Celda del pronóstico previo; no se importa como M4. |

## aristas.geojson: propiedades legadas

| Campo | Tipo / unidad | Significado y uso |
|---|---|---|
| origen / destino | entero | IDs legados de los extremos; se traducen a BIGINT estable. |
| longitud_m | número, m | Longitud informada por fase 1; se descarta y recalcula en PostGIS. |
| tiempo_s | número, s | Tiempo simulado anterior; se descarta en la referencia base. |
| exposicion_m | número, m ponderados | Exposición ordinal previa; no se usa como costo. |
| fraccion_dato_recurrencia | número, 0..1 | Cobertura del dato histórico; no se importa como A4. |
| tiempo_pronostico_s | número, s | Tiempo direccional estimado con viento; se descarta. |
| estado | texto | Estado del modelo previo; no filtra el grafo base. |
| meteo_momento | texto fecha/hora | Validez del dato meteorológico previo; no se usa como condición actual. |
| meteo_admisible | booleano | Chequeo previo; no bloquea enlaces en la referencia. |

## manifest_fuentes.json

`bbox_wgs84` es `[oeste,sur,este,norte]` en grados; `fuentes` es la lista de los
siete productos S1..S7 efectivamente obtenidos en fase 1. Cada elemento conserva
`id` (identificador), `product` (producto), `file` (nombre original), `url`
(consulta), `sha256` (huella), `bytes` (tamaño), `observado_utc` (obtención),
`http_status` (estado) y `verificacion` (resultado). S3 contiene además `recorte`
con `file`, `sha256` y `bytes` del GeoTIFF recortado.

No se incluyen aquí los originales de todas esas fuentes: el manifiesto se usa
para registrar el catálogo y conservar trazabilidad; no afirma que esos siete
datasets estén cargados en la BD de fase 2. Los nombres de archivo del manifiesto
son referencias al proyecto anterior y no rutas a resolver en este paquete.

El nuevo adaptador guarda sus propios hashes de nodos/aristas y configuración
en el linaje. Las bases son ubicaciones candidatas, no instalaciones habilitadas
para drones. La red es un modelo 2D y no acredita operación de vuelo.
