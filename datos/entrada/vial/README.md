# Originales viales y de instalaciones

Los archivos con SHA en el nombre conservan respuestas originales sin alterar.
`manifest.json` apunta a la instantánea activa y contiene `sources`,
`bbox_wgs84`, fecha UTC y errores de endpoints alternativos. Cada fuente incluye
`file`, `sha256`, `bytes`, `url`, `http_status` y fecha de obtención. OSM incluye
además la consulta Overpass y `timestamp_osm_base`.

| Clave | Proveedor y estructura |
|---|---|
| `osm` | OpenStreetMap vía Overpass. `elements` contiene nodos (`id/lon/lat`), vías (`id/nodes/tags`) y relaciones (`id/members/tags`). `nodes` es la secuencia ordenada de vértices. `members` usa `type/ref/role`. `version/timestamp/changeset` identifican la revisión cartográfica. Objetos repetidos idénticos se deduplican por `(type,id)`; versiones contradictorias abortan. |
| `senapred` | SENAPRED Servicios_2024, capa 1 BOMBEROS, GeoJSON. `objectid_1` identifica el registro; `nombre/direccion/comuna` describen la instalación. Se conserva para documentar el descarte de Bomberos 104 por desconexión territorial. |
| `senapred_carabineros` | SENAPRED Servicios_2024, capa 3 CARABINEROS, GeoJSON. `objectid` identifica la unidad; `nombre_uni/tipo_de_un/nombre_de/numero/comuna` la describen. Se seleccionó `objectid=2872`. `hecho=2014` es un atributo del catálogo, no una fecha de visita en terreno. |

Las geometrías usan WGS84 `[longitud,latitud]` en grados. `point_x/point_y` son
atributos redundantes; no reemplazan la geometría. Los demás atributos originales
se conservan para trazabilidad y no se usan para cambiar costos o autorizaciones.

El corte online de validación conserva además `osm_0cebf8a03042ae41.json` y el
nombre de descarga `senapred_carabineros_deae518a3d64c6c2.json`. Este último tiene
los mismos bytes/hash que `carabineros_deae518a3d64c6c2.json`, usado por el corte
inicial; se conserva el alias para resolver ambos manifiestos originales.
El manifiesto de esa segunda adquisición está archivado en la carpeta de
evidencias. El manifiesto activo no se cambia al cerrar la prueba online.

`corroboracion_municipal.html` conserva la página municipal *Valpo Seguro*, que
identifica la 8.ª Comisaría Florida y su dirección. Su JSON asociado documenta
URL, hash y fecha. `corroboracion_bomberos.*` conserva evidencia institucional de
la alternativa descartada. Los HTML son evidencia; no se sirven ni ejecutan.

OSM se utiliza bajo **ODbL 1.0**, con atribución a sus colaboradores:
https://www.openstreetmap.org/copyright . SENAPRED conserva atribución de origen;
no se le atribuye una licencia no declarada por el servicio.

## Regenerar

`./main` reconstruye desde los originales conservados sin consultar proveedores.
`./main iniciar --mode online` actualiza OSM y ambas capas SENAPRED antes de
reconstruir. Las respuestas se guardan con nombres derivados de su hash y el
manifiesto cambia solo al recibir todos los insumos completos. Un error no se
transforma en un dataset vacío ni permite sustituir la publicación vigente.

Dentro del contenedor también puede ejecutarse
`python -m Infraestructura.descargar_vial`. La carga y publicación se hacen con
`main`, que registra el run staging, fuentes, SQL y migraciones y realiza auditoría.
