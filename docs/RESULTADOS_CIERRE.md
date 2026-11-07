# Resultados del cierre

La aceptación completa terminó correctamente sobre una base desechable
`dbtest/ruteo_test`. La huella del código del host, la imagen probada, el
benchmark y la aplicación local coincide:

`e680545237470e577938c664860b18defb1cf741a00581c988852047fb589b13`

La base Git es `4f0c35f538956a55df305e58bf5448d71cffcce5`; los cambios de implementación
permanecen en el árbol de trabajo, sin commit ni push automático. La huella
identifica esta versión con mayor precisión que el commit base.

| Verificación | Resultado |
|---|---:|
| Python, incluyendo integración PostgreSQL/PostGIS/pgRouting | 175 pruebas |
| Node | 15 pruebas |
| Playwright: estados, patrullaje, recarga, entorno, reproductor y cierre | 89 comprobaciones |
| Fallos, errores y pruebas omitidas | 0 |
| Lote local prefijado | 6 casos conservados, 0 inválidos |

La [matriz literal](MATRIZ_RUBRICA.md) relaciona cada criterio con su implementación
y evidencia. El [manifiesto](../evidencia/cierre_validado/manifest.json) conserva
hashes de los resultados; [aceptación](../evidencia/cierre_validado/acceptance.json)
incluye etapas, tiempos y archivos de código. Los logs, exportaciones completas
y capturas de esa ejecución permanecen en `evidencia/local/`.

## Transporte y preparación

El benchmark fue secuencial, con un proceso nuevo, la misma escena y perfil y
tres objetivos trasladados 0/5/10 metros, sin solvers concurrentes. La preparación
pasó de **64.87 s** en frío a una mediana de
**5.85 s** al reutilizar la geometría:
**91.0 % menos**, frente al objetivo
del 50 %. Esta medición corresponde a preparación; no es una reducción equivalente
del tiempo total de todos los algoritmos ni una garantía en otro equipo.

| Respuesta resumida | Bytes sin compresión |
|---|---:|
| Mapa inicial | 51,557 |
| Misión calculada | 195,316 |
| Diagnóstico de misión bloqueada | 32,347 |
| Capas de Valparaíso | 350,051 |
| Capas de Viña del Mar | 50,837 |

Todas quedan bajo 1 MiB. Se comprobaron ETag/304 y recursos por hash; las APIs
completas siguen disponibles para exportación. Las comprobaciones incluyen el
recorte visual de capas y objetos 3D, conservando originales para planificación.

## Amenazas, energía y algoritmos

Se verificaron el rechazo del presupuesto útil de 60 s, el desglose
190 = 130 s de vuelo + 60 s de reporte, retorno seguro, reporte incompleto sin
hora final y diagnóstico A1=100 exportable cuando el clima impide volar.
Las carreras de foco, semilla, objetivo y cámara no restauran resultados antiguos.
También se comprobó el dibujo sobre capas interactivas, deshacer y arrastre sin
agregar vértices, reproducción y vista del dron.

El MILP se contrastó con enumeración independiente en una instancia pequeña con
orientaciones, orden y estación obligatoria. Gurobi 13.0.3 resolvió los seis casos
reales del lote; sus estados, brechas y comprobaciones de licencia/capacidad se
conservan en [protocol_exports.json](../evidencia/cierre_validado/protocol_exports.json).
Esto acredita los tamaños probados, sin afirmar capacidad para cualquier misión.

El protocolo local fijó antes del cálculo dos tamaños de polígono y tres casos:
base, amenaza central de 30 % y amenaza oeste de 80 %, con semilla 20261106 y
1.000 escenarios comunes. En ambos tamaños las cuatro técnicas empataron en
resiliencia estimada: 0,790 / 0,554 / 0,154 respectivamente. Se conservan los
intervalos Wilson al 95 %, todos los resultados y el desempate temporal por
separado. Estos datos no permiten declarar una técnica más resiliente en ese
ejemplo. La replanificación frente a un cierre sí produjo una alternativa
admisible que evita el segmento afectado y mantiene cobertura y retorno.

El [plan exacto](../evidencia/cierre_validado/protocol_plan.json) y el
[resumen completo](../evidencia/cierre_validado/protocol_summary.json) permiten
repetir el lote. Sus exportaciones comprimidas están en
`datos/runs/patrullaje_cierre/batch_556f8f9384e869f2/`, con hashes en el manifiesto.

## Entrega y límites

La aplicación actualizada responde en http://127.0.0.1:18083 y conserva la
publicación `2e6808a3-a8c3-5543-a051-cf5f4ac1c5d0`. La regresión que publica
fixtures se ejecutó únicamente sobre `dbtest`; la publicación local y el lote
se consultaron con el rol de solo lectura, sin recargarla. Salud, mapa resumido
y `/fase2` respondieron HTTP 200.
La imagen de producción pasó `pip check`; libexpat1 se instala desde el paquete
oficial Debian conservado y verificado por SHA-256.

GitHub Actions está configurado con Python, Node y Playwright, pero esta
implementación todavía no se ha publicado y no tiene ejecución remota acreditada.
La rama remota `parte3` seguía en el commit base al verificarla por lectura.
El video continúa fuera del alcance por la instrucción del usuario.

Se conservan las limitaciones académicas declaradas en la matriz: probabilidades
hipotéticas, discretización y cobertura aproximada, alturas estimadas y estaciones
hipotéticas. La evidencia respalda los requisitos comprobados y no promete una
calificación perfecta ni autoriza operaciones reales de vuelo.
