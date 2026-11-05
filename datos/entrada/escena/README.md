# Cartografía del entorno

`manifest.json` identifica la respuesta original de Overpass, con URL, consulta,
extensión WGS84, fecha de la base OSM, fecha de descarga, hash SHA-256 y licencia
ODbL 1.0. El archivo `osm_<hash>.json` conserva exactamente la respuesta recibida.
La consulta cubre el área de vuelo más un margen; no se consulta Overpass durante
la navegación o el cálculo de rutas.

Los archivos `scene_<hash>.json.gz` son derivados reproducibles: geometría OSM,
catastro CONAF ya adquirido, malla y curvas del DSM Copernicus GLO-30. Cada derivado
incluye su manifiesto con hash de contenido, código y fuentes. El servidor comprueba
que corresponda a los insumos actuales antes de reutilizarlo.

Regenerar desde la raíz del proyecto, con sus dependencias instaladas:

```bash
python -m Infraestructura.descargar_escena
python -m tools.preparar_escena --context datos/runs/<run>/context.json
```

La segunda instrucción trabaja sin conexión. El contexto se obtiene de una ejecución
del ETL existente. El procesamiento previo evita triangular miles de objetos durante
la apertura interactiva. Una nueva descarga solo reemplaza el manifiesto si la respuesta
es completa. No se descargan ni almacenan teselas de OpenStreetMap en este directorio.

© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL 1.0.
Catastro de uso del suelo CONAF 2019 y Copernicus GLO-30 conservan la procedencia de
sus manifiestos aéreos originales. Ver [documentación](../../../docs/ENTORNO_3D.md).
