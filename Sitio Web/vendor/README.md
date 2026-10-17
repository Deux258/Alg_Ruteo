# Leaflet local

Leaflet 1.9.4 se conserva localmente para no depender de un CDN. `manifest.json`
documenta URL, SHA-256 y tamaño de cada archivo; `LICENSE` conserva su licencia
BSD. Los archivos originales no se modificaron.

La interfaz utiliza `circleMarker`, sin imágenes externas de marcadores. Las
calles, límites, base y rutas proceden del backend local. Solo la capa opcional
de imágenes OSM requiere internet; no es necesaria para visualizar ni calcular
rutas sobre la instantánea conservada.
