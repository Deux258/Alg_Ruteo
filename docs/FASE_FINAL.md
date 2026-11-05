# Fase final: patrullaje poligonal

La entrada principal es `/`. `/fase2` conserva las consultas puntuales. La fase final
compara cuatro métodos sobre la misma misión y devuelve todas las rutas, incluso
los estados sin solución. No se asigna una nota ni se garantiza una mejora positiva.

## Ejecutar y reproducir

Con Docker activo, `./main` reconstruye la malla de 100 m, publica las nueve cargas
y abre la web. La publicación usa otro run: no reemplaza snapshots antiguos.
`./main probar` ejecuta las pruebas en una base desechable.

1. Cargar el ejemplo o dibujar/importar un Polygon GeoJSON WGS84.
2. Seleccionar hora UTC, base, altura y estaciones hipotéticas.
3. Comparar las cuatro técnicas y revisar cobertura, estado, resiliencia y cómputo.
4. Marcar un foco sintético dentro del objetivo y sortear/reproducir.
5. Descargar misión y probabilidades; activar la vista 3D.

`./main patrullar --request datos/runs/solicitud_poligono.json` genera una carpeta
por SHA con `comparison.json`, `request.json`, `failure_probabilities.json` y
`scenarios.json`. La solicitud mínima contiene `target_polygon` (geometría Polygon)
y puede indicar `origin`, `time`, `station_ids`, `seed`, `scenarios`, `events` y
`preferences`. Los valores predeterminados están en `config/patrullaje.json`.

`./main patrullar --experiment config/evaluacion_patrullaje.json` fija seis casos:
dos escalas geométricas y tres multiplicadores históricos, en la primera hora
admisible posterior a la adquisición. Guarda `plan.json` antes de ejecutar, resultados
comprimidos por caso y un resumen que incluye rechazos; no selecciona casos por éxito.
El protocolo v2 recorta las geometrías escaladas al área de estudio con margen interior
de 1 m antes de fijar el plan. V1 conserva sus objetivos originales, incluidos los que
quedan fuera. Esta preparación geométrica no depende de los resultados del ruteo.

El modo local explícito es `python -m core.patrol --context datos/runs/<run>/context.json
--request <solicitud>`. Para servir ese contexto: definir `PATROL_CONTEXT` y ejecutar
`python -m core.web`. Este modo identifica su motor como Dijkstra Python sin pgRouting.

## Modelo de misión y terreno

Las distancias se calculan en EPSG:32719. La malla usa 100 m y ocho vecinos; ningún
enlace persistente o de consulta puede superar 200 m horizontales. STRtree evita
comparar todos los pares de nodos al reconstruir la infraestructura.

El barrido divide el polígono en pasadas de hasta 150 m de separación y crea puntos
de conexión separados por hasta 100 m. Cada pasada admite dos orientaciones. Las
conexiones completas respetan el área de tránsito y las exclusiones conocidas.
La cobertura evalúa una muestra por celda recortada de 30 m, ponderada por superficie,
con radio horizontal supuesto de 100 m y línea de vista contra el DSM y los obstáculos. Es cobertura
muestreada, no una prueba de visibilidad de cada punto continuo del terreno. Los
sectores pendientes se exportan en `pending_geometry` y no califican como misión lista.

Se verifica el hash y CRS del Copernicus GLO-30 conservado. Los tramos se muestrean
cada 15 m y en los cortes de obstáculos. Su altura es `superficie modelada + AGL`, inicialmente 60 m. Z se expresa en metros EGM2008,
no altura elipsoidal GNSS. NoData impide utilizar el punto o enlace. El tiempo de cada
subtramo es el máximo entre tiempo horizontal dirigido por viento y tiempo de ascenso
o descenso, usando 6 m/s como límite vertical del perfil Mavic 3T. La meteorología
queda congelada en la hora elegida; una celda no se presenta como un campo de viento.
El viento de la fuente a 10 m se aplica uniformemente a la altura de vuelo como
aproximación académica; no se ha adquirido un perfil meteorológico vertical.

El perfil de planificación usa 10 m/s, 25 min y reserva 20 %: 1.200 s útiles por
batería. El total de misión predeterminado es 3.600 s. Despegue y aterrizaje consumen
tiempo de batería. Las cinco bases candidatas pueden representar estaciones virtuales,
una batería por estación, un solo uso y 120 s de cambio, más aterrizaje/despegue.
No se afirma que los cuarteles tengan cargadores ni se simula una curva electroquímica.

La detección usa un foco sintético inicialmente desconocido. Al entrar en alcance
con línea de vista, consume 60 s de verificación/reporte y busca retorno con la batería
restante. La posición dentro del enlace se divide en dos arcos residuales, conservando
los tiempos dirigidos por viento. Si no existe retorno, `no_safe_return` conserva el
hallazgo pero no declara servicio cumplido. Un bloqueo aleatorio conocido durante el
recorrido inicia retorno desde el nodo anterior; `interrupted_and_returned` no cuenta
como patrullaje completado.
La recuperación admite el origen o una de las bases seleccionadas como estaciones,
si su nodo sigue operativo. Reporta la base de aterrizaje y horas UTC del hallazgo y
del reporte; la última posición representa la superficie al finalizar el descenso.

## Algoritmos y modelo matemático

El grafo admisible es común. Dijkstra por metros conecta tareas en orden serpenteante
usando `pgr_dijkstra`; no se afirma que Dijkstra resuelva el problema de cobertura.
Dijkstra ponderado conserva ese orden y utiliza `c_e = t_e (1 + λ p_e)`, λ inicial 1.
Las estaciones en esos métodos se buscan con etiquetas de batería e inventario y un
haz de 16 estados: la búsqueda se declara limitada.

Gurobi optimiza una red de estados orientados de pasadas y estaciones. Cada conexión
es un camino mínimo ponderado del grafo. Variables binarias `x_ij` eligen transiciones;
`v_i` selecciona estados; variables continuas `u_i` y `b_i` representan orden y batería
consumida al llegar. Minimiza suma de costos de conexiones y servicios, sujeto a:

- Una orientación por pasada y conservación de flujo; salida y regreso únicos.
- `x_ij = 1 => u_j >= u_i + 1`, para impedir subcircuitos.
- Propagación de batería por conexión y servicio; reinicio únicamente tras un cambio.
- Límite de batería por tramo entre estaciones, inventario de un uso y presupuesto total.

El óptimo se refiere a esta red de conexiones precomputadas. Un estado `optimal` no
certifica un óptimo de todas las trayectorias físicas posibles. El límite es 30 s,
brecha objetivo 1 %, una hebra y semilla conservada. Se exportan estado, soluciones,
brecha y tamaño del modelo. Los errores de licencia se muestran como tales.

El recocido simulado intercambia pasadas y cambia orientaciones. Evalúa la misma
función y restricciones, utiliza la búsqueda de estaciones con haz de 16 etiquetas y
acepta empeoramientos con `exp(-Δ/T)`. T comienza en 100 y desciende linealmente hasta
0,01. Se detiene en 10.000 iteraciones o 30 s; se registran semilla e iteraciones.
La memoria de evaluaciones evita recalcular el costo de una misma secuencia. Los
tiempos por técnica son incrementales y las conexiones ya calculadas se reutilizan;
la preparación del grafo queda incluida en el tiempo total de la solicitud.

## Fallas, distribución y resiliencia

Las probabilidades son hipótesis de escenario por misión. AIP, meteorología fuera
de perfil y buffers FIRMS conocidos son exclusiones de 100 %. A4 asigna inicialmente
1, 3, 5, 10 y 20 % a clases 1–5; no se interpretan como tasas observadas. Las amenazas
sintéticas admiten 0–100 %. Los datos desconocidos no se transforman en probabilidad 0.
Fuera de la cobertura A4 se conserva una capa `A4_unknown` con probabilidad supuesta
del 20 % por misión, separada de las clases observadas. Esta es una política conservadora
configurable, no una estimación estadística de las zonas sin información.

Para cada elemento se conserva el aporte de cada amenaza. La probabilidad marginal
combinada es `1 - producto(1-p_h)`, suponiendo independencia entre objetos de amenaza.
Una misma amenaza afecta conjuntamente a todos los nodos y enlaces intersectados.
Los elementos excluidos se incluyen en el archivo de probabilidades con su causa.

Se sortean valores `Uniforme[0,100)` y ocurre falla si `U < p_h`. Las cuatro rutas se
congelan antes de los mismos 1.000 escenarios. R es la fracción de escenarios donde
la ruta completa es viable, cubre el objetivo y retorna. Un método sin misión viable
obtiene 0. La replanificación ilustrativa se informa aparte de R. Se exportan todos
los sorteos, la semilla, hashes, perfil y huella de software. La sensibilidad mantiene
las rutas congeladas y repite los umbrales A4 con multiplicadores 0,5, 1 y 2.

## API y visualización

La vista inicial ofrece circuitos espacialmente distintos. El selector de comparación
conserva los cuatro resultados originales, que pueden coincidir. El reproductor incluye
pausa, barra temporal, inicio/fin, seguimiento, cámara del dron y centrado del objetivo
en ambas vistas. Ver [modelo y reproducción](ALTERNATIVAS_REPRODUCTOR.md).

- `GET /api/aereo/patrullaje/mapa`: áreas, catálogo, metadata, amenazas, clima y malla DSM.
- `POST /api/aereo/patrullaje`: polígono y perfil; cuatro rutas y evaluación común.
- Los endpoints existentes de rutas/comparación también aceptan `target_polygon`.
- `POST /api/aereo/patrullaje/simular`: `sha256`, `method`, `seed`, `fire` opcional.
  El SHA debe corresponder a uno de los últimos tres resultados del servidor.

La web utiliza solo lectura de BD; exporta archivos mediante descarga. Solo se admite
un cálculo pesado simultáneo; otros reciben 429. Un reinicio descarta la caché y exige
recalcular antes de simular. Se comprimen las respuestas JSON grandes.

Hay controles independientes para las cuatro técnicas y hasta tres candidatas viables
destacadas. Popups usan texto DOM para evitar interpretar datos como HTML. El checkbox
de amenazas activadas filtra el escenario sorteado, conservando sus probabilidades.
El terreno WebGL se genera localmente desde el DSM, con edificios, agua, cobertura,
árboles, caminos y curvas. OpenStreetMap está disponible como base 2D, además del
mapa vectorial local. La envolvente de obstáculos modifica alturas y visibilidad.
Ver [fuentes, estimaciones y reproducción](ENTORNO_3D.md). No requiere Maps3D.
Maps3D puede servir como referencia externa; su GeoJSON en planta no se da por válido
como raster de elevación. La precisión DSM ~30 m no incluye un inventario certificado
de cables u obstáculos pequeños.

## Gurobi académico y entrega

La imagen incluye gurobipy 13.0.3 con hash fijo. La licencia limitada que acompaña pip
permite comprobar modelos pequeños; no demuestra activación académica. Para una licencia
propia, definir `GUROBI_LICENSE_PATH` y usar `compose.gurobi.yaml` junto a `compose.yaml`.
El archivo se monta solo lectura; no se incorpora su contenido al repositorio.

La producción del video queda pospuesta por indicación del usuario. Las herramientas
de comprobación del navegador funcionan sin grabación por defecto; `--video` permite
activarla posteriormente. GitHub y Canvas no se publican automáticamente.

Referencias: [DJI](https://enterprise.dji.com/mavic-3-enterprise/specs),
[Gurobi Python](https://docs.gurobi.com/projects/optimizer/en/current/reference/python.html),
[instalación y licencia limitada](https://support.gurobi.com/hc/en-us/articles/360044290292-How-do-I-install-Gurobi-for-Python),
[Maps3D](https://beta.maps3d.io/for-agents). El procedimiento GIS sigue la guía geomaster
ya citada en `FASE2_METADATA_TRANSITO.md`.
