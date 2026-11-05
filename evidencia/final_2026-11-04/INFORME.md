# Evidencia de fase final

Aplicación: http://127.0.0.1:18083. Fecha: 4 de noviembre de 2026.

Snapshot publicado: `2e6808a3-a8c3-5543-a051-cf5f4ac1c5d0`. Huella de código: `7718cc930788c47d325d5f407f2daf7f2f4249ca7864e4a31b07a5d3c1b599e7`.

Navegador: 16 comprobaciones correctas, sin errores JavaScript. Recarga: 5 comprobaciones.

Regresión: 136 pruebas, correctas.
Módulo de patrullaje actualizado: 10 pruebas aprobadas en Docker. Los conteos incluyen pruebas solapadas.

| Técnica | Estado | Misión (s) | Cómputo incremental (s) | R sintética |
|---|---|---:|---:|---:|
| Dijkstra · metros | ready | 146.973 | 2.668 | 81.6 % |
| Dijkstra · parámetros | ready | 146.973 | 2.352 | 81.6 % |
| Gurobi MILP | ready | 147.948 | 0.031 | 81.6 % |
| Recocido simulado | ready | 146.973 | 0.228 | 81.6 % |

Las cuatro técnicas empatan en resiliencia en el caso mostrado. El 81,6 % observado
corresponde al modelo de escenarios, incluido el supuesto del 20 % para historia
sin cobertura. No estima confiabilidad real ni demuestra superioridad estadística.

Lote `patrol-batch-2`: 6 casos predefinidos, 0 rechazados antes del cálculo.
Cada caso conserva los cuatro resultados y 1.000 escenarios comunes. En las áreas
mayores Gurobi y recocido reducen tiempo de recorrido; las probabilidades comunes
producen empate de resiliencia. `evaluacion/` conserva plan, resúmenes y JSON comprimidos.

## Casos comprobados

- `alternativa_amenaza.png` y `alternative_case.json`: cierre activado y circuito que lo evita.
- `deteccion_regreso.png` y `simulation.json`: detección, reporte y retorno.
- `recarga.png` y `charging_checks.json`: presupuesto de batería reducido a 130 s para forzar un cambio en base; es una restricción experimental.
- `terreno_3d.png` y `movil.png`: terreno local y disposición móvil.

## Límites y reproducción

Producción del video pospuesta por indicación del usuario. No se han publicado commits ni subido archivos a Canvas.
La licencia pip de Gurobi permitió estos modelos pequeños; la activación académica
para modelos mayores sigue siendo una configuración del equipo.
El DSM es aproximado; estaciones, radio visual y probabilidades son supuestos declarados.

Consultar `docs/FASE_FINAL.md` y `presentacion/MATRIZ_FASE_FINAL.md` desde la raíz del repositorio.
