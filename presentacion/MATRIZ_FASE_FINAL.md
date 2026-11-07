# Matriz de fase final y guion del video

La matriz vigente y sus criterios de aceptación están en
[Matriz literal de rúbrica](../docs/MATRIZ_RUBRICA.md). Este guion se conserva como
material histórico; producir el video permanece pospuesto.

La numeración respeta la rúbrica adjunta, que omite el número 6.

| Criterio | Función y evidencia para mostrar |
|---|---|
| 1 · Rutas realistas | Malla de 100 m, enlaces ≤200 m, muestreo DSM y bloqueos completos; vista 3D. |
| 2 · Parámetros del usuario | Base, polígono, hora, altura, viento, batería, presupuesto, peso de riesgo y estaciones. |
| 3 · Metadata y amenazas | Popups, catálogo M1, cobertura M2, DSM M3, clima M4 y amenazas A1–A4; capas con controles. |
| 4 · Archivo de probabilidades | Descargar `failure_probabilities.json`: nodos, enlaces, aportes por amenaza y elementos excluidos. |
| 5 · Cuatro técnicas | Dijkstra metros, Dijkstra parámetros, Gurobi y recocido; cuatro controles independientes. |
| 7 · Fallas aleatorias | Semilla visible; uniforme [0,100), regla U<p y sorteo exportado. |
| 8 · Checkbox | Activar “Solo amenazas activadas en esta simulación”. |
| 9 · Resiliencia | Cada tarjeta muestra R sobre escenarios comunes y tiempo de cómputo; exportar sensibilidad. |
| 10 · Alternativa | Añadir amenaza al conector de salida y replanificar; comprobar cobertura y regreso, o informar inviabilidad. |

Secuencia sugerida: definir misión y perfil; explicar sensores/supuestos; activar capas
y popups; calcular; comparar las cuatro tarjetas; alternar rutas; mostrar 3D; sortear
amenazas; activar el filtro; demostrar alternativa; marcar foco; reproducir reporte y
regreso; descargar resultados. Explicar los estados sin solución y las estaciones virtuales.

Los resultados anteriores de fase 2 no se usan como evidencia numérica de las misiones
poligonales. La evidencia nueva está en `evidencia/final_2026-11-04/`.
