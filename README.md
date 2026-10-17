# Ruteo vial reproducible en Valparaíso

Aplicación Docker con PostgreSQL, PostGIS, pgRouting y Leaflet. Reconstruye calles
reales de OpenStreetMap dentro del polígono suministrado y calcula rutas desde una
instalación real del catálogo SENAPRED. Conserva el SQL y los snapshots anteriores;
las extensiones se aplican mediante una migración explícita.

**Origen geográfico:** 8.ª Comisaría Florida, Valparaíso, registro SENAPRED
CARABINEROS `2872`, coordenadas **[-71.621817, -33.053137]**. La municipalidad
corrobora la instalación y su domicilio Mariana Sarraeta 136, Cerro Florida.
El cálculo empieza en el nodo OSM `13049981860`, a **5,75 m** del punto del catálogo.
No se inventa un acceso entre ambos. La selección como origen de referencia no
implica operación ni autorización institucional para usar el recinto.

La instantánea genera **15.499 nodos y 28.974 arcos dirigidos**. El límite es
exactamente el GeoJSON adjunto de **54,92 km²**, no el límite administrativo completo
de la comuna. Desde la base se alcanzan **13.249 nodos**; otros 2.250 no son
alcanzables con este perfil y límite, y no se conectan artificialmente.

## Ejecutar

Requiere Docker Desktop/Engine activo y Docker Compose. En Windows usar Bash de
Git o WSL con Docker disponible. El host no necesita Python ni PostgreSQL.

```bash
chmod +x main
./main probar
./main
```

Abrir http://127.0.0.1:8080 . `main` crea `.env` con contraseñas aleatorias si no
existe. No versionar ese archivo. `WEB_PORT=18081 ./main` permite otro puerto.

```bash
./main iniciar --mode online  # descarga OSM y dos capas SENAPRED; reconstruye
./main                       # reconstruye desde originales, sin consultas externas
./main estado
./main detener               # conserva datos; nunca borra volúmenes
```

El arranque aplica SQL y migraciones, ejecuta ET/carga, valida geometrías,
conectividad y rutas desde la base, publica atómicamente y habilita la web. Un
error no sustituye el run publicado. Repetir el mismo snapshot conserva su run y
no duplica datos. Una actualización online conserva las respuestas originales,
consultas y hashes. Los fallos de proveedor se informan explícitamente.

`main probar` usa otra BD, efímera en `tmpfs`, y guarda los resultados en
`evidencia/local`. El [informe vial](evidencia/red_vial_2026-10-17/INFORME.md)
recoge las pruebas y el arranque desde una BD vacía.

## Representación y alcance

Cada arco corresponde a vértices consecutivos de una vía OSM. Se conservan todos
los vértices de forma y su procedencia. Las calles se conectan únicamente por
nodos OSM compartidos; un cruce visual a distinta cota no crea una intersección.

El perfil de **vehículo liviano** respeta sentidos, rotondas, accesos y barreras
conocidas. Excluye escaleras, sendas peatonales, accesos restringidos y condiciones
o dimensiones que no puede resolver. Se excluyen segmentos no completamente
cubiertos por el polígono, sin fabricar extremos para ampliar la red.

Las restricciones de giro OSM se convierten en secuencias de arcos prohibidas.
Un autómata conserva esa memoria, incluida la restricción con vía intermedia,
y `pgr_dijkstra` encuentra el mínimo sobre las transiciones permitidas. El costo
de cada paso es únicamente `ST_Length(geom_32719)/1000`. La consulta clásica de
Dijkstra sin giros se conserva como referencia interna.

El límite se verifica en **WGS84**; las longitudes se calculan en **EPSG:32719**.
Reproyectar un anillo de segmentos rectos cambia su interpolación entre vértices:
no se utiliza ese efecto ni un buffer para modificar el límite suministrado.

La aplicación no incluye tráfico, cierres actuales ni comprobación en terreno de
la señalización. Hay componentes no alcanzables por límites, sentidos y datos;
la aplicación lo informa y rechaza esas rutas.

## Fuentes y documentación

- [Originales, licencias y regeneración](datos/entrada/vial/README.md).
- [Polígono y diccionario espacial](datos/entrada/aoi/README.md).
- [Contrato de infraestructura y cargador](Infraestructura/DICCIONARIO.md).
- [SQL inicial](BD/crear_bd.sql) y [migración vial](BD/migraciones/002_red_vial.sql).
- [Modelo ampliado](BD/diagrama_vial.svg).
- [Interfaz y APIs](Sitio%20Web/README.md).
- [Informe, mapas, rutas y pruebas](evidencia/red_vial_2026-10-17/INFORME.md).

Bomberos 104, Laguna Verde, se investigó y descartó: el polígono interrumpe su
calle y solo deja unos 98 m de recorrido desde ella. No se relajó el límite para
aparentar conectividad.

`config/proyecto.json` selecciona la red vial. `config/proyecto_legacy.json`
conserva la malla anterior para regresiones. Los originales de fase 1 y sus
informes permanecen intactos. El DDL inicial no se reescribe: ahora hay **25 tablas**,
con tres nuevas para la base, los estados y las transiciones.

La entrega grupal completa continúa separada de esta aplicación vial: los ocho
ETL de metadata/amenazas y la evaluación resiliente de fase 3 siguen pendientes.
`phase2_complete=false` conserva esa distinción.
