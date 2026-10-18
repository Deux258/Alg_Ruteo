# M1 · Compañías de Bomberos (`m01_bases.json`)

## En una frase
Lista de compañías de bomberos cerca de la zona de estudio, que usamos como **posibles puntos de partida** de los drones.

## De dónde sale
- **Fuente:** dataset público de ArcGIS Hub «Compañías de bomberos, Región de Valparaíso, sector sur». Los datos originales son de la Junta Nacional de Bomberos de Chile.
- **Script:** `Metadata/m01_bases_et.py`

## Qué hace el script
1. Pide a la fuente las compañías que caen en el rectángulo que rodea la zona, ampliado en 10 km.
2. Se queda con las compañías que están **dentro del polígono o a 1,1 km o menos de su borde**, y para cada una calcula a qué distancia queda. Marca como `candidata_origen` la de dentro y las cuatro elegidas por el equipo.
3. Guarda todo en un JSON.

## Cómo es un registro
Cada compañía es un bloque con estos datos:

| Campo | Qué es | Ejemplo | Si falta |
|---|---|---|---|
| `id` | Número que identifica a la compañía en la fuente | — | — |
| `nombre` | Nombre de la compañía | "Decima Sexta de Valparaíso" | queda `null` |
| `direccion` | Dirección (puede que la fuente no la traiga) | — | queda `null` |
| `comuna` | Comuna | "Valparaíso" | queda `null` |
| `lon`, `lat` | Ubicación en grados (longitud y latitud) | — | — |
| `dentro_aoi` | `true` si está dentro de la zona, `false` si no | `true` | — |
| `distancia_aoi_km` | Distancia en km hasta el borde de la zona (0 si está dentro; es aproximada) | 0.57 | — |
| `candidata_origen` | `true` si la compañía se acepta como punto de partida (dentro de la zona, o elegida por el equipo) | `true` | — |
| `motivo_candidata` | Por qué es candidata: `"dentro_aoi"`, `"seleccionada_por_equipo"` o `null` | "dentro_aoi" | `null` |
| `atributos_originales` | Todos los datos tal como vienen de la fuente, por si hace falta revisarlos | — | — |

## La cabecera del archivo
Antes de la lista, el JSON trae datos del archivo en sí: `schema_version` (versión del formato), `dataset_id` (nombre del conjunto, aquí "m01_bases"), `fuente` y `fuente_url` (de dónde se bajó), `obtenido_utc` (cuándo se bajó), `crs` (sistema de coordenadas, siempre `EPSG:4326`, es decir, latitud/longitud normal), `cantidad` (cuántos registros hay) y `descargados_bbox` (cuántos devolvió la fuente antes de filtrar). Todos los JSON de metadata usan esta misma cabecera.

## Resultado de la última ejecución
Con la caja sin ampliar: 16 compañías cerca de la zona, **1 dentro** y 15 a entre 0,17 y 1,03 km del borde. Con la caja ampliada a 10 km el total es mayor.

## Qué compañías se usan como origen
La de dentro de la zona (Décima Sexta) y cuatro elegidas por el equipo: Décima, Décima Tercera, Décima Quinta y Décima Segunda de Valparaíso. Las demás compañías a 1,1 km o menos del borde se conservan, pero no se marcan como candidatas. La selección es una **decisión del equipo**, no un dato de la fuente. Como quedan fuera del polígono, el grafo necesita un tramo de acceso desde cada una hasta el nodo más cercano de la zona.
