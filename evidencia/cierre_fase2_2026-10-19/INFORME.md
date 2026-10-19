# Cierre funcional y crítico de fase 2

19 de octubre de 2026. Aplicación: http://127.0.0.1:18081 . Simulador académico.

## Versión y alcance

Commit de base: `d5a7370e8e855872e02728591e94c742816dcff5`. Cambios locales identificados por
`486003263a4f1979e27904e03f1409257cd124d14a3c46db2e5e8558199262c3`. No se afirma que ese commit contenga los cambios posteriores.
Pruebas, interfaz, lote y arranque limpio acreditan la misma huella. La presentación
anterior y su evidencia se conservan como antecedentes. Las primeras ejecuciones
anteriores a corregir Git Bash no se usan como prueba de persistencia final.

Se conserva el área de vigilancia de 54,920709 km² y el tránsito de 97,716233 km²,
con buffer 1100 m en EPSG:32719. Red: 154 nodos y 1114 arcos, cinco bases reales.
No se alteraron las migraciones ni las fuentes originales; no hay tablas nuevas.
La base interior sigue siendo Décima Sexta, Laguna Verde, SENAPRED 104 conciliada
con S1H:19: longitud −71.657239211, latitud −33.101901690.

## Cambios y revisión crítica

- Preferencia `max_historical_class`, entero 1–5 o null. Desactivada conserva rutas y
  costos anteriores. Activada excluye clases superiores y segmentos sin cobertura
  histórica, con razones separadas. Se usa en extremos y segmentos completos UTM.
  Es una política preventiva simulada, no un incendio activo ni cierre observado.
- Un mismo evaluador aplica la política a ambos métodos; Dijkstra sigue generando
  exclusivamente por distancia. La exposición mantiene su función de ordenación.
  No se exige fabricar una cuarta amenaza natural para obtener puntaje.
- Controles individuales D1/D2/P1/P2 conservan coordenadas. Las rutas pueden compartir
  corredores; el porcentaje a 50 m es diagnóstico, no garantía de independencia.
- Protocolo por lote fijado antes de calcular: cinco bases, cuatro objetivos extremos
  UTM sin repetir, tres horas posteriores a adquisición sin filtrar viento, dos
  perfiles. El plan se escribió antes de ejecutar los algoritmos. Ningún caso se
  retiró por fallar o tener una sola alternativa.
- Se detectó y corrigió un fallo real de Git Bash: convertía la ruta absoluta de
  salida Linux a una ruta Windows dentro del contenedor. main utiliza ahora la
  ruta relativa datos/runs/evaluaciones. La persistencia final se verificó desde
  main y una prueba CLI verifica directorios con espacios y argumentos excluyentes.
- El catálogo gráfico anterior mezclaba dos vistas con tablas. El esquema actual
  excluye vistas y muestra las 29 tablas y sus claves reales. Los JSON de presentación
  conservan BIGINT como texto para evitar redondeo JavaScript.

## Resultados sin selección favorable

Experimento `447e0e6a023159ae28d9873df927ab3ca0a550620c01962db57c9b613e55e34c`.
120 casos, 100 escenarios por caso, 12000 evaluaciones caso-escenario válidas y
0 casos desconocidos según el protocolo. Los focos/valores no se inventaron.
Cada par de métodos comparte casos, cierres y denominador. Las misiones se congelan
antes de evaluar; no se replantean rutas dentro del bucle.

| Perfil | Casos | Dijkstra R medio | Propuesto R medio | Delta medio pp | Mejor / igual / peor |
|---|---:|---:|---:|---:|---|
| Predeterminado |60|14,5167 %|14,5500 %|+0,0333|2 / 56 / 2|
| Clase histórica máxima 4 |60|3,2667 %|6,5333 %|+3,2667|2 / 58 / 0|
| Total descriptivo |120|8,8917 %|10,5417 %|+1,6500|4 / 114 / 2|

El promedio combinado mezcla dos políticas y no sustituye la lectura separada.
La mejora del perfil predeterminado es pequeña; se observaron dos empeoramientos
(hasta −3 pp). El máximo +98 pp corresponde a un caso, no a todo el sistema.
No hay demostración estadística de superioridad ni probabilidad de éxito de vuelo.

Solo 13/120 casos propuestos son admisibles sin cierre sintético: 12 ofrecen dos
opciones y uno solo una. Rechazos: 32 por extremos restringidos, 40 por meteorología,
23 por autonomía y 12 por falta de cobertura histórica bajo la política activa.
El orden de validación determina la causa informada; no son conteos independientes
ni exhaustivos de todos los problemas simultáneos.

La cobertura histórica desconocida no equivale a datos completos. El protocolo puede
conocer que la política conservadora prohíbe un tramo sin cobertura: por ello esos
casos se cuentan como inadmisibles y no como éxito, aunque unknown_cases sea cero.
El ejemplo individual anterior de 99 % se conserva; no es comparable directamente
con el promedio de este lote territorial más exigente.

## Pruebas y reproducción ejecutadas

- Suite final: 118 pruebas, 0 fallos, 0 errores,
  0 omisiones, 304.632 s. PostgreSQL16.9/PostGIS3.5.2/pgRouting3.8.0 reales.
- Python3.12.12, locks reconciliados y pip check en la imagen reconstruida.
- 13 comprobaciones reales Playwright Chrome, sin errores de página:
  perfiles, política, exportación, capas, extremos, bloqueos, retorno, móvil.
- main desde volumen nuevo: 82.968 s de pipeline. Este tiempo excluye
  construir imagen y arrancar servicios. Publicación correcta con nueve datasets.
- Repetición idempotente: 3.182 s de pipeline; no se recargan duplicados.
- Lote repetido desde main corregido: mismo SHA de resultado
  `863b78cb4e6f448c75d5202bdfeedd2d577ed730123d4c169d9cc31c811eb6d9`.
  Archivos visibles en el host y cargas idempotentes por SHA.

```bash
./main probar
./main
./main evaluar --experiment config/evaluacion_fase2.json
```

La instancia activa usa COMPOSE_PROJECT_NAME=udp-ruteo-cierre-20261019 y WEB_PORT=18081.
El entorno limpio de verificación utiliza un proyecto y volumen separados; no se
eliminan volúmenes del usuario.

## Evidencia, rúbrica y pendientes

La presentación de cierre contiene 22 láminas principales y 14 anexos: ejemplos
JSON reales de nueve salidas, scripts y cargadores, esquema completo, SQL Dijkstra
ejecutado, fixtures sintéticos identificados y fallos. La matriz vincula los
17 criterios y 60 puntos posibles; no otorga una nota.

A4 como política preventiva necesita aceptación docente del criterio 5.1. Las imágenes
originales de rúbrica no están archivadas aquí; se utiliza su matriz en el plan PDF
aportado. La revisión literal final de esas imágenes sigue correspondiendo al equipo.

La resolución DNS de DGAC fue intermitente en la comprobación actual: una consulta
resolvió, pero el intento HTTP oficial volvió a fallar por DNS. Ver dgac_dns.json y
aip_http.json. No se declara descarga exitosa ni
actualización online completa. El manifiesto activo conserva el AIP reutilizado
explícitamente. Las otras fuentes siguen siendo las ya documentadas, sin nuevas
fuentes ni capas de riesgo de significado supuesto.

El usuario indicó carga manual con su cuenta universitaria. GitLab UDP y Canvas
siguen sin publicarse; CI está configurado pero no ejecutado allí. No se solicitaron
credenciales. ENTREGA_MANUAL.md describe clon, volumen vacío y comprobantes pendientes.

Persisten malla discreta, candidatos limitados, condiciones estáticas, DSM sin despeje
vertical, vegetación/recurrencia históricas y exclusiones AIP conservadoras 2D. No se
implementa control de drones, navegación 3D ni certificación operacional.
