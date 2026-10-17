# Interfaz de ruteo vial

`core.web` sirve la interfaz Leaflet y las APIs de lectura: `/health`,
`/api/topologia`, `/api/mapa`, `/api/nodo?lon=...&lat=...` y
`/api/ruta?destino=ID`. Los IDs BIGINT viajan como texto. No se recibe SQL del
cliente. Un punto fuera del polígono o un destino sin ruta devuelve HTTP 422.

La interfaz permite seleccionar destinos de ejemplo o pulsar una calle. El
backend busca un nodo vial original a no más de 100 m del clic, dentro del área.
Se distinguen la instalación real SENAPRED y el nodo OSM donde comienza el
cálculo; la separación entre ambos no se representa como una calle ficticia ni
se suma al costo. La ruta respeta sentidos y giros; el costo es longitud en km.

Leaflet se sirve localmente. La capa de imágenes OSM es opcional y requiere
internet. La red y el cálculo de rutas funcionan sin ella.
