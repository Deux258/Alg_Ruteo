# Matriz literal de rúbrica y aceptación

La rúbrica suministrada omite el número 6. Esta matriz conserva su numeración.
El video está pospuesto por instrucción del usuario. La implementación y sus pruebas
no equivalen a una garantía de calificación ni acreditan una publicación en GitHub.

| Criterio literal | Implementación | Comprobación reproducible |
|---|---|---|
| 1. «La infraestructura a utilizar deberá permitir generar rutas realistas, es decir, no debe generar líneas rectas entre dos puntos que no se puedan sobrevolar ya sea por altitud o por bloqueos.» | Malla métrica, enlaces ≤200 m, muestras DSM/obstáculos, exclusiones, batería y retorno. | `test_patrol`, `test_geographic_scene`, `test_patrol_closure`; aceptación real de vuelo y recarga. |
| 2. «La interfaz web deberá poder recibir los parámetros de consulta del usuario (restricciones del usuario impuestas por su aplicación).» | Polígono, base, hora, altura, viento, batería, presupuesto, riesgo y estaciones; evaluación común backend. | `test_patrol_closure`; `verificar_patrullaje`, `verificar_recarga`, `verificar_cierre`. |
| 3. «La interfaz web deberá ser capaz de cargar todos los metadatos y amenazas detectados en las comunas filtradas (utilizar popups o algún otro mecanismo para desplegar la información que no se pueda visualizar como un polígono). Para habilitar o deshabilitar la información mostrada, puede utilizar un panel de control que posea checkboxes.» | CUT BCN, recorte espacial visual de catálogo/capas/nodos/amenazas/contexto 3D; popups y controles. Clima compartido identificado. | `test_geo_transport`; `verificar_entorno`; `verificar_cierre` comprueba todas las capas de Valparaíso y Viña del Mar. |
| 4. «A partir de los datos obtenidos como amenaza, cada uno debe ser modelado como una probabilidad de falla en su sistema. Para esto, deberá crear un archivo que genere la probabilidad de fallo de cada enlace y nodo a partir de cada amenaza considerada en su trabajo.» | Exportación marginal combinada y aporte por amenaza; nodos/enlaces excluidos; A1=100 exportable incluso bloqueada la misión. | `test_patrol_closure`, `test_geo_transport`; diagnóstico meteorológico y descarga en `verificar_cierre`. |
| 5. «Deberá mostrar como solución la mejor ruta que satisfaga su problemática, utilizando y detallando el funcionamiento de las siguientes técnicas». | Cuatro métodos con funciones objetivo y restricciones declaradas; recomendaciones y estados inviables. | Modelo en `FASE_FINAL.md`; cuatro checkboxes y comparación en navegador. |
| 5a. «Pgr_dijkstra usando como peso solo la distancia en metros.» | pgRouting sobre distancias métricas; orden de barrido declarado. | Backend PostGIS en base desechable; `verificar_patrullaje` comprueba engine `pgr_dijkstra`. |
| 5b. «Utilizando CPLEX o GUROBI, a partir del modelamiento formal de su problema de optimización, considere las variables de los metadatos y amenazas, y las condiciones del usuario como restricciones.» | MILP de orientaciones, estaciones, batería, presupuesto y conectores admisibles. | Enumeración independiente de pequeñas instancias con estación obligatoria; estado, licencia y capacidad del solver en los resultados reales. |
| 5c. «Pgr_dijkstra utilizando los parámetros y condiciones propuestas en el punto anterior.» | Costo dirigido por viento y riesgo; mismas restricciones físicas y de energía. | `test_patrol`, oracle/aislamiento de cachés y aceptación real. |
| 5d. «Una metaheurística que considere viable para solucionar su problemática.» | Recocido simulado con semilla, iteraciones/límite de tiempo y factibilidad común. | `test_patrol`; resultados, costo y estados exportados; límites declarados. |
| 5, control. «Las 4 rutas generadas deben ser posibles de habilitar o deshabilitar desde su panel de control.» | Selector de comparación original y cuatro controles independientes. Los circuitos diversos son una vista adicional. | `verificar_patrullaje`, `verificar_reproductor`. |
| 7. «A partir de las probabilidades asignadas, deberá habilitar una opción que permita, a partir de números aleatorios entre 0 y 100, determinar si ocurrirá o no la falla (a partir de si supera o no el umbral de falla).» | Uniforme [0,100), regla U<p, semillas/escenarios/IDs estables; sorteos exportados. | `test_patrol_closure`, `verificar_patrullaje`. |
| 8. «Deberá habilitar un checkbox que permita mostrar solo las amenazas que podrían ocurrir.» | Solo amenazas activadas en el escenario sorteado, con probabilidades visibles. | `verificar_patrullaje`; filtro espacial del recurso de amenazas. |
| 9. «Utilizar una métrica de resiliencia para su servicio, para cada una de las técnicas de ruteo utilizadas e indicar cuál de ellas fue la más resiliente frente a las amenazas detectadas en su infraestructura. Este valor debe ser desplegado junto a la leyenda que indica el algoritmo y tiempo de cómputo de cada ruta.» | R sobre escenarios comunes, Wilson 95 %, ganador o empate explícito; cómputo desglosado y desempate temporal separado. | `test_patrol_closure`, pruebas JS de empate y `verificar_cierre`. |
| 10. «Realizar un ejemplo de caso en donde se pueda evidenciar que su solución provee una ruta alternativa frente a una amenaza (mitigando lo más posible las amenazas), y que evidencie que se logra cumplir sus objetivos iniciales.» | Cierre ilustrativo de un conector, replanificación, cobertura y retorno; protocolo adicional prefijado de amenazas locales sin seleccionar resultados favorables. | `verificar_patrullaje`; lote `config/evaluacion_patrullaje_local.json` conserva todos los estados y empates. |

## Evidencia de la versión

La aceptación local del cierre pasó **175 pruebas Python, 15 Node y 89
comprobaciones Playwright**, sin errores ni omisiones. El
[informe de resultados](RESULTADOS_CIERRE.md) y el
[manifiesto versionado](../evidencia/cierre_validado/manifest.json) identifican
la huella exacta del código, el benchmark y los seis casos locales conservados.
La ejecución remota de GitHub Actions continúa pendiente de publicación.

La aceptación genera `evidencia/local/acceptance.json`, `pruebas.json`, logs Node,
JSON de comprobaciones del navegador, capturas y `benchmark.json`. Es regenerable,
queda fuera de Git y se sube como artifact en GitHub Actions. Cada archivo de
código/configuración se identifica en la huella `software.code_sha256`.

El archivo `acceptance.json` solo marca `successful=true` después de Python sin
omisiones, Node, Playwright y benchmark. Una configuración de CI por sí sola no
demuestra que haya corrido en GitHub. Las evidencias históricas permanecen
archivadas y no sustituyen estas comprobaciones.

## Límites declarados

Es un simulador académico: probabilidades hipotéticas, muestras de cobertura de
30 m, radio visual supuesto de 100 m, DSM de superficie aproximado, alturas OSM
estimadas y datos históricos. El filtro de comuna es visual. Las estaciones son
hipotéticas y no acreditan cargadores reales. El óptimo MILP corresponde a su red
de conectores y discretización; no a toda trayectoria física continua. Las otras
búsquedas tienen límites explícitos. La licencia limitada de Gurobi puede resolver
los casos pequeños comprobados, sin acreditar una licencia académica completa.
