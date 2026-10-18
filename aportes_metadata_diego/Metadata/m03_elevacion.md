# M3 · Elevación del terreno (`m03_elevacion.json`)

## En una frase
La altura sobre el nivel del mar del terreno en cada nodo (punto) de la red de drones.

## De dónde sale
- **Fuente:** modelo de elevación Copernicus GLO-30 (una imagen de alturas con un dato cada ~30 m, pública en AWS).
- **Script:** `Metadata/m03_elevacion_et.py`

## Qué hace el script
1. Lee `infraestructura.json`, que trae la lista de nodos con su longitud y latitud.
2. Descarga la imagen de alturas que cubre la zona.
3. Para cada nodo, lee la altura en su posición. Si ahí no hay dato, deja el valor vacío (`null`) en vez de inventarlo.

## Cómo es un registro
Una fila por nodo:

| Campo | Qué es | Ejemplo | Si falta |
|---|---|---|---|
| `nodo_id` | Identificador del nodo (el mismo de `infraestructura.json`) | 1 | — |
| `lon`, `lat` | Ubicación del nodo, en grados | -71.60, -33.08 | — |
| `elevacion_m` | Altura sobre el nivel del mar, en metros (redondeada a 0,1) | 385.5 | `null` |
| `estado` | `"ok"` si hay altura; `"sin_dato"` si no | "ok" | — |

Ejemplo real:
```json
{"nodo_id": 1, "lon": -71.6, "lat": -33.08, "elevacion_m": 385.5, "estado": "ok"}
```
La cabecera del archivo es la misma que en M1, más `unidad` ("metros sobre el nivel del mar") y `nodata` (explica que vacío = sin dato).

