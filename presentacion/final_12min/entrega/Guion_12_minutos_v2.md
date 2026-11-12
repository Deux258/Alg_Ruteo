# Guion de presentación · 12:00 · Alg_Ruteo (v2)

Este guion reemplaza la secuencia del guion anterior para adaptarse a la estructura solicitada:
tráiler de 15 s, cuatro pilares (infraestructura, metadata, amenazas y ruteo), ficha del dron,
demostración y cierre. Conserva los datos reales de la versión verificada y distingue los
supuestos académicos de las mediciones.

**Duración total:** 12:00 · **Tráiler:** 00:00–00:15 · **Voz:** ~1.480 palabras.
**Regla de oro:** las fórmulas y tablas se muestran, no se leen completas. El texto de pantalla
no se narra palabra por palabra.

## Reparto sugerido

| Bloque | Tiempo | Integrante | Contenido |
|---|---:|---|---|
| 1 | 00:00–03:10 | Diego Muñoz | Tráiler, problema, plataforma, infraestructura y dron |
| 2 | 03:10–06:40 | Ignacio Pastén | Metadata, amenazas, cargas y presupuesto |
| 3 | 06:40–09:35 | Diego Hidalgo | Cuatro algoritmos y demostración |
| 4 | 09:35–12:00 | Eduardo Escalona | Evaluación global, límites y conclusión |

Si el equipo decide una sola voz, el guion funciona igual: solo cambian los cortes de cámara.

## Mapa de tiempos

| Tiempo | Bloque | Pantalla principal |
|---|---|---|
| 00:00–00:15 | Tráiler | Montaje de 15 s |
| 00:15–00:55 | Problema y área de estudio | Portada + mapa de Valparaíso |
| 00:55–01:35 | Plataforma, pipeline y base | Esquema de arquitectura + SQL |
| 01:35–02:25 | Infraestructura y malla 3D | Vista 3D + malla + GeoJSON |
| 02:25–03:10 | Dron y radio de 100 m | Ficha del Mavic 3T + cobertura |
| 03:10–04:10 | Metadata M1–M4 | Panel de capas + popups |
| 04:10–05:10 | Amenazas A1–A4 | Capas de amenazas + estados |
| 05:10–05:55 | Carga y estados | Pipeline + tablas SQL |
| 05:55–06:40 | Costos, presupuesto y parámetros | Panel de misión |
| 06:40–08:20 | Ruteo: cuatro algoritmos | Tabla comparativa |
| 08:20–09:35 | Ruteo: vuelo, amenaza y alternativa | Reproducción 2D/3D |
| 09:35–10:35 | Evaluación global | Tabla de resultados |
| 10:35–11:20 | Limitaciones y futuro | Lámina de límites |
| 11:20–12:00 | Conclusión | Cierre |

---

## 00:00–00:15 · Tráiler

**Pantalla:** tráiler de 15 s. Sin narración encima; solo música y textos. Si se necesita una
versión con voz, usar las cinco frases cortas de la tabla.

| Tiempo | Imagen | Texto en pantalla | Voz opcional |
|---:|---|---|---|
| 0–3 s | Relieve 3D de Valparaíso y silueta de dron | **VALPARAÍSO · DESDE OTRA ALTURA** | «Valparaíso, once por ocho kilómetros de terreno crítico.» |
| 3–6 s | Polígono dibujado sobre el mapa | **TRAZA EL OBJETIVO** | «Un objetivo poligonal, no un punto.» |
| 6–9 s | Cuatro rutas de colores | **4 TÉCNICAS · UNA MISIÓN** | «Cuatro técnicas, una misma misión.» |
| 9–12 s | Amenaza roja y ruta que la rodea | **EL RIESGO APARECE · LA RUTA RESPONDE** | «Y una ruta que responde.» |
| 12–15 s | Logo y mapa | **ALG_RUTEO · CADA RUTA ES UNA DECISIÓN** | «Alg_Ruteo: cada ruta es una decisión.» |

**Control:** 15 s · música con corte seco al segundo 15. No alargar el logo.

---

## 00:15–00:55 · Bloque 1 · Problema y área de estudio

**Pantalla:** portada. Fondo: mapa de Valparaíso con el polígono de estudio y el buffer de
tránsito. Primer plano del título y los cuatro pilares.

**Texto en pantalla:** `Valparaíso · interfaz urbano-forestal` · `Cubrir, no solo llegar` ·
`4 pilares: Infraestructura · Metadata · Amenazas · Ruteo`.

**Narración:**

Valparaíso combina cerros, quebradas, vegetación y viviendas. Es un interfaz urbano-forestal
donde un incendio encuentra combustible y pendiente en muy pocos metros. Solo en la temporada
2025–2026, CONAF informó 575 incendios en la Región de Valparaíso. Nuestro problema no es
llegar a un punto: es cubrir un área, con batería limitada, terreno y restricciones. El área de
adquisición mide unos once por ocho kilómetros; la malla de vuelo se extiende 1.100 metros
alrededor. La pregunta que guía el proyecto es simple: ¿cómo planificar un patrullaje seguro,
comparable y reproducible?

**Control:** 40 s · ~95 palabras. Pausa breve después de «575 incendios».

---

## 00:55–01:35 · Bloque 1 · Plataforma, pipeline y base de datos

**Pantalla:** diagrama de arquitectura en tres capas: fuentes S1–S7 → ETL y PostgreSQL/PostGIS →
web 2D/3D. A la derecha, captura del esquema SQL y del diagrama relacional.

**Texto en pantalla:** `./main` · `PostgreSQL 16 + PostGIS + pgRouting` · `BD/crear_bd.sql` ·
`29 tablas` · `EPSG:32719` · `GeoJSON WGS84`.

**Narración:**

La respuesta es Alg_Ruteo: una plataforma de planificación 2D y 3D, un pipeline ejecutable y
una base geoespacial. Con `./main` se levantan los contenedores, se ejecuta el ETL de las
fuentes, se publica el snapshot y se abre la web. El modelo final es relacional y geoespacial:
PostgreSQL 16 con PostGIS y pgRouting, esquema `routing`, 29 tablas, índices GiST, claves
foráneas y disparadores que congelan lo publicado. Los nodos y enlaces se calculan en
EPSG:32719; la API y las exportaciones hablan GeoJSON WGS84. Todo queda versionado por `run`,
con hashes y estados. Cuatro pilares ordenan la explicación: infraestructura, metadata,
amenazas y ruteo.

**Control:** 40 s · ~95 palabras. Señalar el diagrama, no leer cada tabla.

---

## 01:35–02:25 · Bloque 1 · Infraestructura: malla aérea en 3D

**Pantalla:** vista 3D. Alternar terreno, edificios y vegetación. Acercar un tramo de la malla
hasta ver nodos y enlaces. Abrir un popup de nodo y mostrar un fragmento GeoJSON.

**Texto en pantalla:** `9.788 nodos` · `70.932 enlaces dirigidos` · `enlace máximo 163 m` ·
`malla 100 m` · `muestreo vertical 15 m` · `JSON / GeoJSON`.

**Narración:**

Infraestructura. La malla tiene 100 metros y hasta ocho vecinos; ningún enlace supera los 200
metros. En la publicación real hay 9.788 nodos y 70.932 enlaces dirigidos; el enlace más largo
mide 163 metros. No unimos puntos en línea recta: cada tramo se muestrea cada 15 metros y en
los obstáculos, se compara con el DSM y con edificios y árboles, y se calcula un perfil
vertical. La altura inicial es 60 metros sobre la superficie modelada. El resultado se ve en
2D y en 3D: relieve, 25.148 edificios, agua, vegetación, árboles y curvas. La red se guarda en
JSON y se exporta como GeoJSON. Es una malla 2,5D: posiciones con cota, no un espacio
volumétrico completo.

**Control:** 50 s · ~115 palabras. El cierre «2,5D» evita prometer un modelo 3D volumétrico.

---

## 02:25–03:10 · Bloque 1 · Dron y radio de 100 metros

**Pantalla:** ficha del DJI Mavic 3T con los parámetros en tarjetas. A la derecha, círculo de
100 m sobre una ruta y el texto «cobertura + línea de vista».

**Texto en pantalla:** `DJI Mavic 3T` · `10 m/s` · `6 m/s vertical` · `25 min` ·
`reserva 20 %` · `1.200 s útiles` · `60 s reporte` · `viento ≤ 8 m/s` · `−5 a 40 °C`.

**Narración:**

El dron es un DJI Mavic 3T. Usamos 10 m/s de crucero, 6 m/s de ascenso y descenso, 25 minutos
nominales, 20 % de reserva, 1.200 segundos útiles por batería y 60 segundos para reporte. El
viento se corta a 8 m/s y la temperatura debe quedar entre −5 y 40 °C. El radio de observación
es de 100 metros, pero es un supuesto académico, no una especificación del dron. Ese radio se
usa para evaluar cobertura con línea de vista y para detectar un foco sintético. Las amenazas
A1–A4 no se «detectan» a 100 metros: vienen de capas de datos y afectan el ruteo.

**Control:** 45 s · ~110 palabras. Esta es la respuesta directa a la pregunta sobre el radio.

---

## 03:10–04:10 · Bloque 2 · Metadata M1–M4

**Pantalla:** panel **04 · Cartografía y entorno**. Encender y apagar capas. Abrir un popup de
base (M1), un polígono de vegetación (M2), un nodo con elevación (M3) y la hora del clima (M4).

**Texto en pantalla:** `M1 · Catálogo de bases` · `M2 · Vegetación` · `M3 · Elevación` ·
`M4 · Clima`.

**Narración:**

Metadata. **M1** es el catálogo de bases: 16 registros, de los cuales 5 son bases candidatas
dentro del área, incluida la 104.
**M2** es la cobertura vegetal CONAF 2019: 653 polígonos en la adquisición, con uso, subtipo y
estructura; sus clases no se convierten en alturas métricas certificadas. **M3** es la elevación: Copernicus
GLO-30, celda S34/W072, aproximadamente 30 metros, EGM2008, un valor por nodo. **M4** es el
clima: Open-Meteo con ECMWF IFS 0,25 grados, seis variables horarias en UTC. Cada salida
conserva fuente, fechas, CRS, hashes y linaje. En la web se encienden y apagan como capas, y
los popups muestran sus atributos. No son adornos: M1 define salidas y estaciones; M3 cambia
alturas y visibilidad; M2 y M4 alimentan restricciones y riesgos.

**Control:** 60 s · ~140 palabras. Alternar al menos una capa mientras se habla.

---

## 04:10–05:10 · Bloque 2 · Amenazas A1–A4

**Pantalla:** capas de amenazas. Mostrar A1 en el selector de clima, A2 en FIRMS, A3 en AIP y
A4 en recurrencia. Abrir un popup con probabilidad y estado.

**Texto en pantalla:** `A1 · Meteorología` · `A2 · FIRMS` · `A3 · AIP` · `A4 · Recurrencia`.

**Narración:**

Amenazas. **A1** es meteorología fuera de perfil: deriva de M4; si el viento o la racha llegan
a 8 m/s, la temperatura sale de rango o falta un dato, la misión se cierra globalmente.
**A2** son focos térmicos FIRMS VIIRS NOAA-20: buffer de 250 metros, confianza n/h y ventana de
24 horas; si no hay focos, se declara vacío, no se inventa uno. **A3** son zonas AIP ENR 5.1 de
la DGAC: en este snapshot, SC-P29 y SC-P50; exclusión 2D dura con margen de selección de 300
metros, sin usar aún los límites verticales. **A4** es recurrencia histórica SENAPRED
2020–2024, clases 1 a 5 con supuestos de 1, 3, 5, 10 y 20 %; no bloquea por sí sola: pondera
exposición. La falta de cobertura histórica se declara aparte con 20 %, no se convierte en
cero.

**Control:** 60 s · ~145 palabras. No afirmar que A3 certifica todas las restricciones aéreas.

---

## 05:10–05:55 · Bloque 2 · Carga de infraestructura, amenazas y estados

**Pantalla:** pipeline con los nueve datasets (`I`, `M1–M4`, `A1–A4`), tabla `datasets` y
estados. Mostrar un caso `valid` y uno `empty`. Abrir una tarjeta de resultado con estado.

**Texto en pantalla:** `valid / empty` · `active / unknown / historical` ·
`ready / no_route / not_feasible / interrupted` · `sin ruta ficticia`.

**Narración:**

La carga es transaccional e idempotente. Infraestructura, M1–M4 y A1–A4 se publican como
datasets con estado `valid` o `empty`; los conteos se reconcilian y se auditan topología y
área. La web solo lee. Una amenaza puede quedar `active`, `unknown`, `historical` o ser un
evento sintético. En una misión, el resultado puede ser `ready`, `no_route`, `not_feasible`,
`unknown` o `interrupted`. Si no hay ruta, el sistema lo dice y conserva la causa: no dibuja
una línea ficticia. Esa honestidad es parte del diseño.

**Control:** 45 s · ~95 palabras. Enfatizar «no se sustituye un error por un vacío».

---

## 05:55–06:40 · Bloque 2 · Costos, presupuesto y parámetros

**Pantalla:** panel **01 · Misión**, desplegar **Perfil de vuelo · Mavic 3T** y **Estaciones
hipotéticas**. Mover un parámetro y mostrar cómo cambia el resumen.

**Texto en pantalla:** `1.200 = 1.140 + 60 s` · `3.600 = 3.540 + 60 s` ·
`190 = 130 + 60 s` · `estación: 120 s + 1 batería`.

**Narración:**

Costos y presupuesto. La batería útil de 1.200 segundos se separa en 1.140 planificables y 60
de reporte. El presupuesto de misión de 3.600 segundos deja 3.540 planificables. El tiempo de
cada tramo depende de la longitud, la velocidad sobre el suelo y el viento; el ascenso y el
descenso usan 6 m/s. Una estación cuesta 120 segundos de servicio y una batería, con inventario
de un uso. El usuario ajusta altura, viento, batería, presupuesto, peso de riesgo, recurrencia
y estaciones. Si el presupuesto no alcanza, se informa la inviabilidad. Ejemplo: 190 segundos
útiles son 130 de vuelo más 60 de reporte.

**Control:** 45 s · ~115 palabras. No confundir batería útil con presupuesto de misión.

---

## 06:40–08:20 · Bloque 3 · Ruteo: cuatro algoritmos

**Pantalla:** tabla de cuatro filas. Columnas: técnica, qué optimiza, ventaja, límite. Resaltar
cada fila al nombrarla. Al final, captura de las cuatro tarjetas de la web.

**Texto en pantalla:**

| Técnica | Optimiza | Ventaja | Límite |
|---|---|---|---|
| Dijkstra metros | Distancia | Rápido, simple, auditable | No incorpora riesgo ni cobertura global |
| Dijkstra ponderado | Tiempo + riesgo | Usa probabilidad y viento | Búsqueda de estaciones limitada (haz 16) |
| Gurobi MILP | Secuencia y restricciones | Óptimo de la red, restricciones acopladas | Licencia, tamaño, red precomputada |
| Recocido simulado | Secuencia y orientación | Flexible y rápido | Sin garantía de óptimo, depende de semilla |

**Narración:**

**Dijkstra por metros** usa `pgr_dijkstra` y minimiza distancia. Es rápido, simple y auditable;
sirve de referencia. Pero no incorpora por sí solo tiempo, riesgo ni cobertura global.
**Dijkstra ponderado** mantiene el orden serpenteante y usa un costo que combina tiempo y
riesgo: tiempo por uno más el peso del riesgo por la probabilidad, con peso igual a uno. Considera tiempo y riesgo, pero la búsqueda de
estaciones se limita a un haz de 16 estados: no es un óptimo global. **Gurobi** formula un
MILP sobre estados de pasadas y estaciones: transiciones, orientación, orden, batería, flujo,
presupuesto e inventario. En el caso demo resolvió 99 variables y 25 restricciones en 0,03
segundos, con estado `optimal` y brecha de 0,7 %. Su ventaja es el rigor y las restricciones
acopladas; su límite es la licencia, el tamaño y que el óptimo es sobre la red precomputada, no
sobre todo el espacio continuo. **Recocido simulado** intercambia pasadas y cambia
orientaciones, acepta empeoramientos según la temperatura, baja T de 100 a 0,01 y se detiene a
las 10.000 iteraciones o 30 segundos. Es flexible y rápido —0,23 segundos
en el caso—, pero no garantiza óptimo y depende de semilla y ajuste. La tabla en pantalla
resume ventajas y desventajas.

**Control:** 100 s · ~225 palabras. Hacer una pausa de un segundo entre algoritmos.

---

## 08:20–09:35 · Bloque 3 · Ruteo: vuelo, amenaza y ruta alternativa

**Pantalla:** `Cargar ejemplo` → `Comparar las cuatro técnicas` → reproducir. Luego `Añadir
amenaza` y `Sortear y reproducir`; mostrar interrupción y `Replanificar evitando amenazas
activadas`. Alternar 2D/3D y vista del dron.

**Texto en pantalla:** `63 celdas de 30 m` · `R = 81,6 %` · `semilla 20261104` ·
`A4:684 → 0,65 < 10 %` · `R = 82,2 %` · `cobertura + retorno`.

**Narración:**

Pasemos a la simulación. Cargamos el objetivo de 63 celdas de 30 metros, la base 104, una hora
UTC y la semilla 20261104. Las cuatro técnicas cubren el 100 % y regresan; en el caso archivado
todas empatan con una resiliencia de 81,6 % sobre 1.000 escenarios. La semilla hace que
A4:684 saque 0,65 frente a una probabilidad de 10 %: la amenaza se activa. Ahora añadimos un
cierre sintético de 80 % sobre un conector. La misión original se interrumpe y retorna: volver
no es haber completado el patrullaje. Replanificamos evitando la amenaza activada. La nueva
ruta rodea el cierre, mantiene la cobertura y el retorno, y la resiliencia sube de 81,6 a
82,2 %. También mostramos un foco sintético: el dron lo detecta dentro de 100 metros con línea
de vista, verifica 60 segundos de reporte y vuelve. En 3D se ve el terreno, la ruta y la cámara
del dron.

**Control:** 75 s · ~175 palabras. Si la grabación tarda, acelerar solo las esperas y mantener
el comando y el estado final visibles.

---

## 09:35–10:35 · Bloque 4 · Evaluación global

**Pantalla:** tabla de resultados: cuatro técnicas, tiempo de misión, cómputo y R. Luego
captura del lote de seis casos y del benchmark de preparación.

**Texto en pantalla:** `188 Python` · `30 Node` · `121 navegador` · `6 casos` ·
`R = 81,6 %` · `323,9 s vs 334,1 s` · `caché 65,99 → 6,35 s`.

**Narración:**

Evaluación global. Pasamos 188 pruebas Python, 30 de Node y 121 comprobaciones de navegador,
sin fallos. El lote fija seis casos antes de calcular, conserva los rechazos y usa 1.000
escenarios comunes. En los seis, la resiliencia fue 81,6 % para las cuatro técnicas: no hay un
ganador único. En áreas mayores, Gurobi y recocido reducen el tiempo de recorrido: 323,9
segundos frente a 334,1 de Dijkstra. El cómputo es otra historia: 0,03 segundos de Gurobi, 0,23
de recocido y entre 2,3 y 4,7 de Dijkstra. La preparación con caché bajó de 65,99 a 6,35
segundos, un 90,4 % menos. Son mediciones de esta versión, no una promesa de rendimiento
universal.

**Control:** 60 s · ~135 palabras. Decir «empate» sin convertirlo en derrota de un algoritmo.

---

## 10:35–11:20 · Bloque 4 · Limitaciones y trabajo futuro

**Pantalla:** lámina de límites con iconos: probabilidades, DSM, radio, estaciones, modelo
2,5D, licencia. A la derecha, líneas de trabajo futuro.

**Texto en pantalla:** `Supuestos académicos` · `DSM 30 m` · `radio 100 m` ·
`estaciones hipotéticas` · `2,5D` · `A3 sin límites verticales` · `A2 sin propagación`.

**Narración:**

Limitaciones y trabajo futuro. Es un simulador académico: probabilidades supuestas, DSM de 30
metros, radio visual de 100 metros, estaciones hipotéticas y un modelo 2,5D, no un vuelo
certificado. A3 aún no aplica límites verticales; A2 no modela propagación; Gurobi usa licencia
limitada. El siguiente paso es calibrar sensores y probabilidades con datos locales, incorporar
obstáculos verticales y cables, perfiles de viento en altura, validación en terreno y una
licencia académica completa. También integrar datos en vivo y más estaciones reales.

**Control:** 45 s · ~95 palabras. No prometer vuelo real ni certificación.

---

## 11:20–12:00 · Bloque 4 · Conclusión

**Pantalla:** cierre limpio con las cuatro palabras clave y el logo. Sin nuevas funciones.

**Texto en pantalla:** `INFRAESTRUCTURA · METADATA · AMENAZAS · RUTEO` ·
`Cubrir · Regresar · Explicar`.

**Narración:**

Conclusión. Alg_Ruteo convierte un problema territorial en una misión verificable:
infraestructura, metadata, amenazas y ruteo sobre una misma base. Permite comparar cuatro
técnicas, reproducir fallas y mostrar una alternativa que conserva el objetivo. No promete un
vuelo real ni un ganador estadístico: entrega trazabilidad, estados honestos y exportaciones
para repetir cada decisión. En Valparaíso, donde cada segundo y cada metro cuentan, planificar
no es solo llegar: es cubrir, regresar y poder explicar por qué. Gracias.

**Control:** 40 s · ~90 palabras. Terminar sin cortar la voz.

---

## Ficha de datos verificados

Usar estas cifras solo si coinciden con la pantalla de la grabación. Si se ejecuta una misión
nueva, reemplazar por los valores de esa ejecución.

| Dato | Valor | Fuente |
|---|---|---|
| Red publicada | 9.788 nodos; 70.932 enlaces dirigidos; enlace máximo 163,13 m | `evidencia/final_2026-11-04/summary.json` |
| Malla | 100 m; 8 vecinos; enlace máximo 200 m; muestreo vertical 15 m | `config/patrullaje.json`, `docs/FASE_FINAL.md` |
| Cobertura | celdas de 30 m; radio visual supuesto de 100 m; línea de vista | `config/patrullaje.json`, `core/patrol.py` |
| Dron | Mavic 3T; 10 m/s; 6 m/s vertical; 25 min; reserva 20 %; 1.200 s; 60 s reporte | `config/patrullaje.json`, `README.md` |
| Caso demo | 63 celdas; 146,97 s; R = 81,6 % (816/1000) | `evidencia/final_2026-11-04/summary.json` |
| Gurobi | 99 variables; 25 restricciones; `optimal`; brecha 0,72 %; 0,03 s | `evidencia/final_2026-11-04/summary.json` |
| Recocido | 10.000 iteraciones; 0,23 s; semilla 20261104 | `evidencia/final_2026-11-04/summary.json` |
| Alternativa | cierre 80 %; `interrupted_and_returned`; R 81,6 → 82,2 % | `evidencia/final_2026-11-04/summary.json`, `presentacion/final_12min/entrega/caso_demo/verificacion_archivada.json` |
| Lote | 6 casos; 0 inválidos; R 81,6 %; 323,9 s vs 334,1 s en áreas mayores | `evidencia/final_2026-11-04/summary.json` |
| Caché | 65,99 → 6,35 s; 90,4 % menos | `docs/RESULTADOS_MEJORAS_3D.md` |
| Pruebas | 188 Python; 30 Node; 121 navegador; 0 fallos | `docs/RESULTADOS_MEJORAS_3D.md` |
| Área de adquisición | bbox ≈ 11 × 8 km; buffer de tránsito 1.100 m | `datos/entrada/aereo/manifest.json`, `docs/FASE2_METADATA_TRANSITO.md` |
| Incendios regionales | 575 en 2025–2026, corte 2026-06-01; no tasa comunal | `config/incendios_valparaiso.json` |
| Escena 3D | 25.148 edificios; +400 cuerpos de agua; 789 árboles/hileras; 7.171 tramos de calles | `docs/ENTORNO_3D.md` |
| Base de datos | PostgreSQL 16; PostGIS; pgRouting 3.8; esquema `routing`; 29 tablas | `BD/crear_bd.sql`, `compose.yaml` |

## Correspondencia con las ideas solicitadas

| Idea | Dónde aparece |
|---|---|
| Tráiler de 15 s | 00:00–00:15 |
| Cuatro ítems principales | 00:55–01:35 y capítulos 01–04 |
| Dron y parámetros | 02:25–03:10 |
| Radio de 100 m para detectar amenazas | 02:25–03:10 (aclaración: cobertura y foco sintético, no A1–A4) |
| Área de estudio y problemática | 00:15–00:55 |
| Plataforma 2D y 3D | 00:55–01:35 y 08:20–09:35 |
| Pipeline ejecutable | 00:55–01:35 |
| Modelo relacional y geoespacial | 00:55–01:35 |
| Base de datos y esquema SQL | 00:55–01:35 y 05:10–05:55 |
| Malla aérea en 3D; JSON y GeoJSON | 01:35–02:25 |
| Metadata M1–M4 | 03:10–04:10 |
| Amenazas A1–A4 | 04:10–05:10 |
| Carga de amenazas/infraestructura y estados | 05:10–05:55 |
| Costos, presupuesto y parámetros | 05:55–06:40 |
| Cuatro algoritmos con ventajas y desventajas | 06:40–08:20 |
| Vuelo, amenazas y rutas alternativas | 08:20–09:35 |
| Evaluación global | 09:35–10:35 |
| Limitaciones y futuro | 10:35–11:20 |
| Conclusión | 11:20–12:00 |

## Notas de producción

1. **Tráiler:** usar la música original de `presentacion/trailer_hyperframes/assets/score-original.wav`.
   Cortar a 15 s con los cinco planos de la tabla. No poner voz si la música ya tiene impactos.
2. **Transiciones:** cada bloque entra con un rótulo numerado (`01 · INFRAESTRUCTURA`,
   `02 · METADATA`, `03 · AMENAZAS`, `04 · RUTEO`). Mantener el mismo tipo de letra y color.
3. **Cifras:** no leer todas. Dejar en pantalla la tabla y decir solo la conclusión.
4. **Ritmo:** 140 palabras por minuto. Si el ensayo se pasa de 12:00, recortar primero los
   conectores («Ahora veamos», «Como podemos observar») antes de acelerar la voz.
5. **Honestidad:** decir «supuesto» cuando corresponda. No afirmar que el 100 m es una
   especificación del dron, que A3 cubre todas las restricciones aéreas ni que Gurobi resuelve
   todo el espacio continuo.
