# Vigilancia forestal de Valparaíso

## Ejecución y compatibilidad

El planificador versionado conserva la red anterior y sus endpoints. La instalación de
referencia mantiene su coordenada original; el lanzamiento es una selección explícita.
La publicación nueva solo se activa después de crear y verificar estados, enlaces,
obstáculos y once datasets. La web utiliza el rol de lectura existente.

```bash
./main                         # reconstruye primero la instantánea anterior
./main vigilancia adquirir     # S4H: IFS HRES; S8: OpenStreetMap
./main vigilancia preparar     # produce/carga I, M1–M5 y A1–A5
./main                         # habilita la nueva interfaz en http://127.0.0.1:8080
./main probar
```

Con originales ya disponibles, `./main` reconstruye también vigilancia sin descargarlos
de nuevo. Una actualización de fuentes requiere `vigilancia adquirir`. Una adquisición
incompleta conserva el manifiesto activo y los originales descargados para diagnóstico.
Las migraciones anteriores permanecen intactas. `005_vigilancia.sql` añade la publicación,
los estados PointZ, enlaces LineStringZ, obstáculos, datasets y evaluaciones.

```bash
./main vigilancia extraer --dataset M5 --output datos/runs/exportados
./main vigilancia cargar --file datos/runs/exportados/M5.json
./main vigilancia evaluar --request evidencia/vigilancia_2026-10-22/solicitud_1.json
./main vigilancia evaluar --experiment config/evaluacion_vigilancia.json
```

El [diccionario de los once productos](DICCIONARIO_VIGILANCIA.md) detalla los campos.
El productor común es `core.patrol_data.prepare`; ejecuta extracción, validación y carga
en una transacción antes de publicar. M5 y A5 también tienen entradas independientes:
`python -m Metadata.m5_obstaculos --output RUTA` y
`python -m Amenazas.a5_obstaculos --output RUTA`; ambas aceptan `--load RUTA`.
La carga lee el archivo, verifica su hash semántico y no vuelve a consultar proveedores.
Una repetición idéntica no duplica entidades. El dataset I se conserva completo en JSON
y se materializa en tablas tipadas; su catálogo SQL guarda el hash y los conteos.

## Red y variables

La malla de 250 m se divide en celdas de 125 m si presenta variación superficial
mayor que 30 m, obstáculos o proximidad a la interfaz entre suelo urbano y vegetación.
Se conectan celdas vecinas con segmentos de hasta 400 m, completamente dentro de
tránsito. Cada ancla tiene niveles de 60, 90 y 120 m sobre el DSM. Las conexiones
incluyen cambios a niveles vecinos y movimientos verticales. La identidad depende
del constructor, la resolución, las coordenadas y el nivel. El run incorpora los
hashes de fuentes, perfil y código de construcción.

Cada corredor verifica las celdas tocadas por una franja lateral de 20 m y un perfil
central cada 15 m. El despeje compara la menor altitud del segmento con la mayor
cota de la franja: es una cota conservadora. NoData invalida esa comprobación.
Los perfiles se almacenan como pares `[fracción, cota_superficie_m]`; la altitud de
vuelo se interpola entre los extremos. Las unidades horizontales son metros UTM 19S
(EPSG:32719), las cotas se expresan en metros EGM2008 y la API transforma X/Y a WGS84.
No se interpreta altura sobre DSM como AGL ni se suma vegetación dos veces.

Edificios y tendidos conocidos tienen exclusión horizontal de 20 m; torres y antenas,
de 30 m. No se sobrevuela un objeto alegando una altura no disponible. Las relaciones
OSM incompletas con geometría de miembros utilizable reciben una envolvente conservadora
identificada mediante `geometry_quality`; los originales se conservan. Una respuesta
Overpass con `remark` de error no se acepta como inventario vacío.

Los extremos de consulta son exactos y temporales; no modifican tablas publicadas.
Los extremos se conectan con hasta doce anclas cercanas dentro de 400 m y entre sí.
Esta elección también limita la búsqueda. Los segmentos temporales cumplen las mismas
comprobaciones. El ascenso y aterrizaje
en lanzamiento tienen una comprobación local diferenciada: ausencia de obstáculos
y máximo superficial de la franja no superior en más de 10 m a la cota elegida.

## Perfil, observación y consumo

`config/vigilancia.json` es el perfil versionado. Defaults: crucero 10 m/s, ascenso
3 m/s, descenso 2 m/s, 25 minutos nominales, reserva 20 %, observación de 60 s por
objetivo y detención de 3 s en cambios de dirección. El consumo es tiempo equivalente:
duración por factor 1,5 en ascenso y por factor 1 en las otras fases. El presupuesto
utilizable es 1200 s equivalentes. La duración de segmento es el máximo de sus tiempos
horizontal y vertical. La sensibilidad admite factores de ascenso 1,25, 1,5 y 2.

Se excluyen viento o rachas >=8 m/s, precipitación >=1 mm/h, visibilidad <1000 m y
temperatura fuera de [-5,40] °C. Se comprueba la ventana completa del presupuesto y
los tiempos de paso. Se interpolan componentes vectoriales del viento. El tránsito
considera los niveles meteorológicos disponibles de 10 y 100 m, conservando el más
exigente. No se genera variación entre cerros a partir de una misma celda de pronóstico.

Cada sector tiene radio inicial de 50 m, recortado al área de vigilancia. Se calcula
una cámara nadiral de 60°×45°, 640×512 píxeles, sobre una cuadrícula de integración
de 5 m. La cobertura descuenta superficie oculta y resolución >0,25 m/píxel; el
objetivo requiere al menos 60 % visible. Se exportan huella nominal, visible, oculta
y desconocida. La recurrencia histórica pondera la cobertura con peso `1+(clase-1)/4`,
usando el máximo en solapes. No modifica por defecto el costo de acercarse al objetivo.

## Algoritmos y retorno

Dijkstra utiliza exclusivamente distancia 3D en km. D2 se obtiene excluyendo por
separado arcos de D1, conservando el candidato distinto más corto. Si esas exclusiones solo cambian la
altitud, se repite Dijkstra excluyendo las copias de cada corredor horizontal de D1
para buscar una desviación física. Todas las llamadas conservan distancia como único
costo. No se crea una alternativa si la geometría no permite encontrarla. Los filtros de
amenazas y las preferencias no modifican su generación; sí su evaluación posterior.
La propuesta utiliza Yen (`pgr_KSP`) sobre los arcos admitidos y costo positivo:

`coste = segundos_equivalentes × (1 + max(riesgo_obstáculo, riesgo_despeje))`.

La proximidad a exclusiones se penaliza linealmente de 1 a 0 entre 0 y 100 m.
El despeje se penaliza de 1 a 0 entre 40 y 80 m. Cada tramo exporta sus variables,
costos y perfil. Los IDs públicos son estables; dentro de pgRouting se remapean a
enteros positivos compactos para evitar problemas con extremos temporales negativos.

Se enumeran hasta seis órdenes para tres objetivos. Cada tramo examina hasta diez
caminos y cada orden conserva hasta cincuenta estados parciales. Todos los objetivos
son obligatorios. La selección prefiere mayor cobertura mínima, menor costo y rutas
físicamente distintas. Las alternativas que solo cambian de altura se deduplican.
El filtro de desvío es 1,2 respecto del consumo mínimo entre candidatos completos.
Se declara búsqueda limitada, sin atribuir óptimo global ni imposibilidad continua.

En cada estado se comprueba consumo acumulado más regreso disponible. El regreso
usa costos conservadores y una provisión de 3 s por enlace para cubrir detenciones.
El retorno final debe conservar la reserva. Una misión que solo logra algunos
objetivos no se informa como completada.

### Secuencia de planificación

```text
validar solicitud, fuentes, unidades y perfil
crear lanzamiento y objetivos exactos temporales
calcular observación por nivel y verificar ventana meteorológica
si propuesta: filtrar arcos y asignar tiempo equivalente penalizado
si referencia: conservar grafo geométrico con costo exclusivo de distancia
para cada permutación de objetivos:
    extender estados parciales con caminos de cada tramo
    descartar dominados y conservar hasta 50 estados
    completar regreso y evaluar observación, consumo y retorno de emergencia
filtrar desvío entre candidatos completos admitidos de la propuesta
seleccionar hasta dos patrullas con distinta trayectoria horizontal
exportar geometrías, comprobaciones, límites de búsqueda y hashes
```

## API y evaluación

* `GET /api/v1/vigilancia/mapa`: áreas, bases, malla, obstáculos, capas y fuentes.
* `POST /api/v1/vigilancia/planificar`: `origin`, `objectives`, `time`, `preferences`
  y `events` opcionales. Los objetivos son coordenadas o `{id,center,radius_m}`.
* `POST /api/v1/vigilancia/comparar`: fija las misiones de ambos métodos antes de
  evaluar escenarios comunes. No replanifica dentro de la métrica.

Preferencias admitidas: `budget_eq_s`, `wind_limit_ms`, `detour_factor`,
`minimum_coverage` y `climb_factor`. Las restricciones se pueden hacer más exigentes;
el factor de ascenso admite el rango de sensibilidad. Se rechazan claves desconocidas,
booleanos, números no finitos, objetivos duplicados y fechas sin zona horaria.
HTTP 422 indica entrada inválida y 503 indisponibilidad. Las respuestas de planificación
incluyen estado, razones, comprobaciones pendientes, perfil efectivo y geometrías.
Los BIGINT se envían como texto a JavaScript. La exportación coincide con la solicitud
visible y se invalida cuando cambia el formulario.

La resiliencia es la fracción de escenarios válidos en que al menos una alternativa
completa observación y retorno. El diferencial es `100 × (R_propuesta − R_Dijkstra)`
en puntos porcentuales. Los desconocidos usan un denominador común y se cuentan aparte.
Se conservan 100 escenarios espaciales y cuatro sensibilidades ambientales separadas
por familia. El lote fija nueve solicitudes antes de ejecutar: 1/2/3 objetivos por
tres horas sin filtrar por viabilidad. Los resultados se agrupan por cantidad de objetivos.

## Supuestos técnicos y fuentes

No hay un equipo caracterizado: factores de consumo y parámetros del sensor son
supuestos configurables. La cobertura geométrica no mide la sensibilidad de detección.
GLO-30 no resuelve todos los obstáculos; OSM puede tener omisiones. Las clases de
cobertura y recurrencia conservan sus años originales. AIP reutilizado no sustituye
una revisión de restricciones vigentes; comunicaciones y condiciones de terreno no
se verifican. Estos límites se presentan en el panel técnico de la interfaz.

Fuentes primarias: [Copernicus DSM](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM),
[Open-Meteo ECMWF](https://open-meteo.com/en/docs/ecmwf-api),
[OpenStreetMap height](https://wiki.openstreetmap.org/wiki/Key:height),
[DGAC drones](https://www.dgac.gob.cl/drones),
[Yen 1971](https://doi.org/10.1287/mnsc.17.11.712),
[pgRouting](https://docs.pgrouting.org/latest/en/) y
[PostGIS ST_3DLength](https://postgis.net/docs/ST_3DLength.html).

Procedimiento geoespacial: GeoMaster, parte de Scientific Agent Skills.
Kassis, T., Agarwal, V., He, Y., Patel, D. y Brueckner, A. M. (2026).
*Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*.
[DOI](https://doi.org/10.48550/arXiv.2609.00065), registro v2 verificado el 22 de octubre de 2026.
