# M2 · Cobertura y uso del suelo (`m02_cobertura.json`)

## En una frase
Un mapa de «qué hay en el suelo» dentro de la zona: bosque, matorral, ciudad, agua, etc., dividido en polígonos.

## De dónde sale
- **Fuente:** catastro de recursos vegetacionales de CONAF (año 2019), publicado por CIREN como servicio ArcGIS REST. Capa «REGIÓN VALPARAÍSO (CONAF 2019)».
- **Script:** `Metadata/m02_cobertura_et.py`

## Qué hace el script
1. Pide a la fuente todos los polígonos que tocan el rectángulo que rodea la zona (en varias tandas, porque el servidor entrega máximo 2000 por vez).
2. **Recorta** cada polígono para dejar solo la parte que cae dentro de la zona.
3. Se queda solo con los datos útiles y guarda el resultado en un JSON.

## Cómo es un registro
Cada polígono tiene:

| Campo | Qué es | Ejemplo | Si falta |
|---|---|---|---|
| `id` | Número del polígono en la fuente | — | — |
| `uso_tierra`, `uso` | Categoría general (bosque, urbano, pradera…) | "Bosques" | `null` |
| `subuso` | Detalle dentro de la categoría | — | `null` |
| `estructura` | Estado o madurez de la vegetación | "Adulto" | `null` |
| `cobertura` | Clase de cobertura de la vegetación, según CONAF | — | `null` |
| `altura` | Clase de altura de la vegetación, según CONAF | — | `null` |
| `tipo_forestal`, `subtipo_forestal` | Tipo de bosque | — | `null` (fuera de bosque) |
| `comuna` | Comuna | "Valparaíso" | `null` |
| `superficie_original_ha` | Superficie del polígono **completo** en hectáreas (no la parte recortada) | — | `null` |
| `anio` | Año del catastro | 2019 | — |
| `geometry` | El contorno del polígono, ya recortado a la zona (en latitud/longitud) | — | — |

La cabecera del archivo es la misma que en M1 (versión, fuente, fecha de descarga, etc.).

## Resultado de la última ejecución
454 polígonos que **cubren el 100 % de la zona**. Por uso: 311 bosques, 74 áreas urbanas e industriales, 53 praderas y matorrales, 9 áreas sin vegetación, 4 terrenos agrícolas y 3 cuerpos de agua.

