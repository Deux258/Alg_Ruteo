# Adquisición, diagnóstico y cierre crítico de fase 2

19 de octubre de 2026. Aplicación comprobada en http://127.0.0.1:18081 .
Git conectado según lo confirmado por el equipo; no se modificaron remotos ni se publicó.

## Versión y alcance

Commit de base: `c72310c99455b084d4a89feaeab8326946312881`. Los cambios locales se
identifican por `013800182c2acb7a8ad73d5c1447709203493e3637974eb0eae507089107dc4d`.
La suite, arranque vacío, repetición y replay acreditan esa misma huella. Los scripts
de evidencia, documentos y presentación se identifican adicionalmente mediante el
manifiesto final de entrega; no se afirma que el commit de base contenga estos cambios.

Se conservan áreas, cinco bases reales, malla de 800 m, enlaces hasta 1500 m y nueve
salidas ETL. Red de 154 nodos y 1114 arcos dirigidos, en tránsito de 97,716233 km².
Vigilancia original: 54,920709 km². Sin modificaciones de migraciones ni restricciones.
Perfil: 10 m/s, 25 minutos, reserva del 20 %, observación de 60 s y 1200 s utilizables.

## Adquisición realmente ejecutada

Se implementó `./main diagnosticar-fuentes --source S6` en Docker. Comprueba DNS,
intenta HTTPS, descubre ENR 5.1 desde el índice oficial, conserva índice/PDF por hash,
valida el parser antes de activar un candidato, registra fechas/enmiendas por página
y compara identificadores, geometrías y atributos con el PDF previo. No impone dos
zonas en adquisiciones futuras. Tres intentos por recurso, timeout de socket de 20 s,
esperas de 1 y 3 s, TLS verificado y clasificación explícita de errores.

**Resultado externo: bloqueado por DNS, no actualización completa exitosa.**

| Ejecución | Resultado comprobado |
|---|---|
| Diagnóstico S6, incluido con imagen final | Tres intentos al índice fallan con `[Errno -2] Name or service not known` |
| Solo S6, reutilizando explícitamente las otras siete fuentes | Falla S6; se conserva el manifiesto activo |
| Adquisición completa | S1, S1H, S2, S3, S4, S5 y S7 se descargan; falla S6; candidato incompleto no activado |
| Snapshot conservado | Hash verificado; parser y nueve ETL/cargas funcionan |

El [índice oficial](https://aipchile.dgac.gob.cl/aip/vol1/seccion/enr) fue accesible
mediante el servicio de consulta web y mantiene su enlace ENR 5.1. Esa observación
es independiente del contenedor: no equivale a descargar el índice en Docker ni a
comparar bytes nuevos del PDF. No se usó una copia externa para eludir el fallo DNS,
no se deshabilitó TLS y no se alteró la configuración DNS del equipo.

El SHA-256 del manifiesto activo permaneció:
`12f8422edc7e4fea55dfa2f47a4344b55b30bef5dec72a200f9c6192f7ac76d0`.
La publicación se conservó en `b80f9b83-cad7-53b8-a8b8-34a2a17e614c`.
Los originales nuevos descargados quedan trazados por `adquisicion_completa_incompleta.json`
y permanecen fuera de esa publicación. No se evaluaron como datos actualizados.

El PDF conservado tiene SHA-256
`fd2d8e065ebd209832d2820abe3592b17f15fb84265f210a092d9df6fc77598d`.
Su inventario contiene 78 zonas; para esta extensión selecciona SC-P29 y SC-P50.
En las páginas PDF relevantes 6 y 7 se leen respectivamente `14 MAY 2026 / AMDT NR 66`
y `07 AUG 2025 / AMDT NR 64`. La primera página no determina la antigüedad de todas
las demás. `aip_snapshot.json` conserva las 24 páginas y el reporte del parser.
La comparación del snapshot consigo mismo no arroja cambios; la comparación con
un PDF nuevo no pudo ejecutarse y permanece expresamente pendiente.

## Diagnóstico sin cambiar el resultado del algoritmo

Rutas, replanificación y comparación incorporan `diagnostics`. Se preservan los
estados, razones principales, costos, alternativas y métricas existentes. Se muestran
las restricciones simultáneas, zonas AIP, exclusiones térmicas sin resolución, política
histórica, meteorología y presupuesto. Las comprobaciones sin datos se identifican
como no realizadas. La interfaz conserva el diagnóstico en la exportación y lo
invalida al modificar una solicitud o comenzar un cálculo nuevo.

Se añadió un Dijkstra dirigido independiente con Python/heapq, sobre el mismo grafo
admitido. Contrasta ida + observación + retorno, o el recorrido restante según fase,
con tiempo ya consumido y presupuesto restante. No utiliza los resultados pgRouting.
Comparte con el algoritmo principal la geometría de admisión y el modelo de viento;
por eso no es una validación independiente de la física o de las restricciones.

Se repitieron **las 120 solicitudes exactas** del plan conservado, contra el snapshot
original: **120/120 sin diferencias** en estados, razones principales, caminos completos,
geometrías, costos, escenarios y métricas. Se detectaron **cero contradicciones** en
las que el oráculo encontrara una misión admisible rechazada por el método propuesto.
No fue necesario modificar la búsqueda ni corregir un defecto del generador.

| Comprobación | Motivo principal anterior | Casos con causa simultánea |
|---|---:|---:|
| Extremo AIP / extremo bloqueado | 32 | 48 |
| Sin cobertura histórica con política activa | 12 | 24 |
| Meteorología fuera de perfil | 40 | 40 |
| Presupuesto insuficiente comprobable | 23 | 23 |
| Control propuesto admisible | 13 | 13 |

**Las columnas de causas simultáneas no se suman como casos distintos.** Además,
44 solicitudes no tienen ida o retorno en el grafo admitido para la hora seleccionada;
ese hecho puede coincidir con un extremo excluido. Con meteorología no admisible
no se declara un tiempo mínimo calculado. Una falta de ruta en esta malla no prueba
imposibilidad de vuelo en espacio continuo. La ausencia de una segunda opción entre
los candidatos conserva la advertencia de búsqueda limitada.

Las métricas permanecen: 4 mejoras, 114 empates y 2 empeoramientos; diferencial medio
de 1,65 puntos porcentuales. Por perfil: predeterminado +0,03 pp y clase máxima 4
+3,27 pp. Solo 13/120 controles propuestos son admisibles y 12/120 tienen dos opciones.
Las rutas pueden compartir corredores. Estos resultados descriptivos de escenarios
sintéticos no constituyen probabilidad operacional ni superioridad estadística.

## Verificación

| Comprobación | Evidencia y resultado |
|---|---|
| Build Docker y dependencias | `build_final.log`, pins y hashes reconciliados, `pip check` correcto |
| Suite completa en BD desechable | `pruebas.json` y `pruebas.log`: **128 aprobadas, 0 errores, 0 fallos, 0 omisiones**, 350,043 s |
| Fallos AIP simulados | DNS, TLS, timeout, HTTP, HTML, PDF inválido y parser no reemplazan manifiesto activo |
| Oráculo | Costos conocidos, dirección, falta de retorno, igualdad con presupuesto y regreso sin repetir observación |
| Arranque con volumen vacío | `arranque_limpio.json`: nueve salidas cargadas, 99,812 s del pipeline, sin contar build/preflight/inicio de servicios |
| Repetición | `repeticion.json`: idempotente, 3,681 s, mismo run y conteos |
| Geografía e integridad | Suite espacial y `publication.json`: cero duplicados de nodos y pares dirigidos |
| Lote conservado | `replay/`: plan, 120 respuestas, causas y contraste sin diferencias |
| Interfaz real | `interfaz/resultado.json`: **16 comprobaciones**, Chrome headless, cero errores de página |
| A4 reproducible | `a4_examples.json`: desactivada, clase admitida, superior y sin cobertura; fixtures identificados |
| Presentación | 36 láminas conservadas, paquete/layout validados y revisión visual individual de los 36 renders |

Se corrigieron errores de orden en las nuevas comprobaciones Playwright durante su
desarrollo; la evidencia final de interfaz corresponde a la ejecución completa exitosa.
Las primeras ejecuciones focalizadas fallidas no se presentan como aprobadas. No se
detectó un defecto equivalente en las rutas existentes.

## Presentación y aceptación de rúbrica

Entrega: `presentacion/fase2_valparaiso_diagnostico.pptx`. Las láminas 3, 14, 21, 22,
35 y 36 incorporan la evidencia nueva, manteniendo tablas editables, diseño y 36
láminas. Las anteriores permanecen como antecedentes. El diagrama y SQL existentes
se conservan porque el incremento no modifica el esquema. La matriz distingue
implementación, evidencia disponible y aceptación docente, sin autoasignar puntaje.

La revisión automática y visual de renders **no acredita revisión nativa en PowerPoint**.
PowerPoint está instalado y se inició, pero Computer Use no pudo capturar su ventana:
primero `FrameArrived timed out`, y tras recuperación `window capture timed out`.
No se abrió ni se inspeccionó este archivo dentro de PowerPoint. Se registra ese
pendiente separado de los controles automáticos; no se declara una revisión nativa exitosa.
La [instrucción de Computer Use](C:/Users/diego/.codex/plugins/cache/openai-bundled/computer-use/26.1013.40934/skills/computer-use/SKILL.md)
remite a la regla de recuperación: «report the exact error if recovery fails».
No se continuó con entradas a una ventana sin observación válida.

`CONSULTA_DOCENTE.md` contiene una consulta breve del criterio 5.1; **no se envió**.
A4 sigue siendo una política preventiva opcional sobre recurrencia 2020–2024,
separada de fuego activo y bloqueos sintéticos. Si se exige otra amenaza activa,
hará falta un incremento independiente con fuente verificada.

Pendientes externos concretos: conectividad DNS de DGAC, aceptación docente de A4,
revisión nativa del archivo para exponer y carga manual en Canvas. Se mantienen
las limitaciones de DSM sin despeje vertical, viento a 10 m, condiciones estáticas,
antigüedad desigual de datos y escenarios sintéticos. No se acredita uso operacional.
