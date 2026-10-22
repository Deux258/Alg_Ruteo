# Originales de vigilancia

S4H contiene el pronóstico IFS HRES obtenido mediante Open-Meteo: viento a 10/100 m,
rachas a 10 m, temperatura, humedad, precipitación y visibilidad. S8 conserva las
respuestas Overpass con edificios, tendidos, torres y antenas. Los bytes se guardan
sin modificar y sus nombres incluyen el SHA-256. `manifest.json` identifica los
originales activos, consulta, cobertura, hora UTC, conteos y atribución.

Productor: `./main vigilancia adquirir`. La construcción y carga se realizan mediante
`./main vigilancia preparar`; los once JSON procesados quedan en `datos/runs/<run>`.
La adquisición fallida registra `adquisicion_incompleta.json` y conserva el manifiesto
activo. Los originales no activos pueden archivarse en `datos/runs` sin afectar el run.

El DSM, cobertura, bases, FIRMS, AIP e historial conservan su procedencia del run aéreo
de base. Una fuente reutilizada no se presenta como descarga reciente. © OpenStreetMap
contributors, ODbL 1.0. Open-Meteo/ECMWF: conservar condiciones y atribución del proveedor.
