# Delimitación proporcionada por el usuario

`Zona_Delimitada_Valpo.geojson` conserva exactamente los bytes del archivo adjunto.
Es una `FeatureCollection` en WGS84/CRS84: coordenadas `[longitud, latitud]`
en grados. Contiene una `Feature` con geometría `MultiPolygon`.
`properties.id=1312` es el identificador original; no identifica un nodo de la red
ni demuestra que sea un código administrativo oficial.

Los anillos de `geometry.coordinates` representan el límite del área solicitada.
Se incluyen los puntos del borde mediante `ST_Covers`. Los arcos deben quedar
completamente cubiertos, no solo sus extremos. No se reemplaza el polígono por
su rectángulo envolvente ni se aplica un buffer para aceptar datos externos.

Esta zona **difiere** del rectángulo de fase 1. Incorporar el archivo permite
auditar esa discrepancia y recortar la infraestructura existente; no regenera
la malla ni obtiene bases, metadata o amenazas nuevas.
El comando de auditoría es `python -m core.spatial_audit` dentro del contenedor ETL
con PostGIS disponible. `--require-match` retorna código 2 ante discrepancias.
Sin `--dataset`, compara los originales de fase 1 y detecta el error original.
Con `--dataset datos/runs/<UUID>/infraestructura.json`, comprueba la salida recortada.

El resultado `delimitacion.json` contiene: `aoi` (validez, SRID, bounds y superficies
en km² calculadas en EPSG:32719), `nodes` y `edges` (conteos e IDs legados fuera),
Los IDs de arcos se expresan como `origen->destino`, pues el GeoJSON original
no contiene un ID de arco independiente.
`delimitation_matches` (conformidad espacial), `warnings` (limitaciones),
`files_sha256` (huellas de insumos), fecha UTC, predicado y versión PostGIS.
`fully_inside` incluye el borde; `exit_with_endpoints_inside` cuenta arcos que
salen del polígono pese a tener ambos extremos dentro.
