# Originales S1-S7 para el polígono de Valparaíso

Se conservan las respuestas públicas originales sin modificación, con nombres
derivados de su SHA-256. `manifest.json` relaciona producto, URL/consulta, fecha
UTC, código HTTP, tamaño y hash. Los JSON ArcGIS son FeatureCollection WGS84 con
`features[].geometry` y `properties` originales. `S*_ids_*.json` identifica el
campo y conjunto completo de IDs solicitado; no es otra fuente independiente.

S1/S2/S7 se descargan por IDs. S3 es el TIFF Copernicus completo de la celda;
no se hace pasar el recorte del rectángulo antiguo por cobertura del nuevo AOI.
S4 conserva valores y unidades originales; S5 es el CSV regional FIRMS; S6 el
PDF oficial AIP. Campos originales usados, unidades, tratamientos, condiciones y
salidas derivadas: [diccionario aéreo](../../../docs/DATOS_AEREOS.md).

No todos los puntos o polígonos originales de la envolvente pertenecen al área.
La transformación filtra con el polígono exacto. Los círculos AIP mantienen su
geometría completa para preservar significado y afectación espacial.

`python -m Infraestructura.descargar_aereo` actualiza fuentes. `main` ejecuta
adquisición online, ET, cargas y publicación. El modo snapshot usa estos bytes
sin consultar proveedores. Un error mantiene el manifiesto y publicación previos.
Los manifiestos y diccionarios no acreditan licencia de redistribución adicional;
se conserva la atribución de los proveedores y la versión histórica de sus datos.
