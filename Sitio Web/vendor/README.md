# Leaflet local

Leaflet 1.9.4 se conserva localmente para no depender de un CDN. `manifest.json`
documenta URL, SHA-256 y tamaño de cada archivo; `LICENSE` conserva su licencia
BSD. Los archivos originales no se modificaron.

Las imágenes de controles de capas y marcadores de Leaflet también se conservan
localmente en `images/`, con hashes y URL en el manifiesto. La interfaz utiliza
`circleMarker`; los iconos de controles no dependen de un CDN. Corredores, límites,
bases y rutas proceden del backend local. Solo la capa opcional
de imágenes OSM requiere internet; no es necesaria para visualizar ni calcular
rutas sobre la instantánea conservada.
