# M4 · Clima (`m04_clima.json`)

## En una frase
El pronóstico del tiempo, hora por hora, para el centro de la zona.

## De dónde sale
- **Fuente:** API de Open-Meteo (pronóstico), consultada en el momento de ejecutar el script.
- **Script:** `Metadata/m04_clima_et.py`

## Qué hace el script
1. Calcula el punto central de la zona.
2. Pide el pronóstico de 2 días con seis variables, con las horas en UTC y el viento en metros por segundo.
3. Reordena la respuesta: en vez de una lista por variable, deja **una fila por hora** con todos los valores.

## Cómo es un registro
Una fila por hora (48 en total):

| Campo | Qué es | Unidad | Ejemplo |
|---|---|---|---|
| `hora_utc` | Hora del pronóstico (hora UTC, no la de Chile) | — | "2026-10-18T00:00:00Z" |
| `temperatura_c` | Temperatura del aire | °C | 12.4 |
| `humedad_pct` | Humedad relativa | % | 86 |
| `viento_ms` | Velocidad del viento | m/s | 5.3 |
| `viento_dir_grados` | Dirección **desde donde** sopla (0 = norte, 180 = sur) | grados | 181 |
| `rafaga_ms` | Ráfaga máxima | m/s | 11.9 |
| `precipitacion_mm` | Lluvia acumulada en esa hora | mm | 0.0 |

Si la API no entrega un valor, queda `null`.

Además de la cabecera común (igual que en M1), este archivo trae `celda_devuelta` (el punto consultado y su elevación en el modelo), `unidades_originales` (las unidades que devolvió la API) y una `nota` de advertencia.

## Resultado de la última ejecución
48 horas, del 18 al 19 de octubre de 2026; temperatura entre 10,0 y 19,8 °C; viento entre 0,28 y 5,3 m/s.

