# Ejemplo legado

`infraestructura.json` conserva el contrato 1.0 de la malla anterior recortada:
13 nodos, 62 arcos y ninguna base. Se mantiene para regresiones, no es la red vial
de la aplicación actual. Su estructura está documentada en
`Infraestructura/DICCIONARIO.md`, apartado 1.0.

La red vial 2.0 se genera con `./main` en
`datos/runs/<run_id>/infraestructura.json` (ver la ruta exacta en
`config/pipeline.json`). Los originales OSM y SENAPRED están en
`datos/entrada/vial`; el diccionario 2.0 y JSON Schema están en `Infraestructura`.
No se duplica la gran salida derivada dentro de esta carpeta de ejemplos.
