# Matriz de evidencia de vigilancia

Presentación: `vigilancia_valparaiso_2026-10-22_final.pptx`. La matriz localiza evidencia
para los 60 puntos de la rúbrica. La evaluación final corresponde al docente.
Los resultados principales comparan un origen y un objetivo. Las patrullas tienen
un bloque adicional y sus resultados no se mezclan con el caso de un objetivo.

| Criterio | Puntos | Diapositivas | Implementación y evidencia local |
|---|---:|---|---|
| 1 Base Docker | 2 | 3 | `compose.yaml`, `docker/Dockerfile.app`, `evidencia/vigilancia_2026-10-22/volumen_vacio/publicacion.json`. Versiones reales y reconstrucción en volumen nuevo. |
| 2 Explicar BD y SQL | 2 | 4–5 | `BD/crear_bd.sql`, migraciones 002–005, `BD/diagrama_vigilancia.svg`. Tipos espaciales, claves, relaciones e inmutabilidad. |
| 3.1 Obtención n-metadata | 6 | 6–10, 12 | `core/patrol_sources.py`, `core/patrol_data.py`, `Metadata/m5_obstaculos.py`, manifiesto y originales S4H/S8. Once JSON generados en `datos/runs/<run>`. |
| 3.2 Carga n-metadata | 2 | 12 | `core/patrol_data.py:load_dataset`, CLI `vigilancia cargar`. `publicacion.json` reconcilia M1–M5. Diccionarios en `docs/DICCIONARIO_VIGILANCIA.md` y `Metadata/`. |
| 4.1 Obtención n-fallas | 6 | 6, 11–12 | A1–A5 y scripts originales de `Amenazas/`, nuevo `a5_obstaculos.py`. A2 vacío válido conserva procedencia. |
| 4.2 Carga n-fallas | 2 | 12 | Cargador común, catálogos JSONB, exclusión espacial materializada. Conteos A1–A5 en `publicacion.json`. |
| 5.1 Modelos de falla | 3 | 9, 11, 13 | Cuatro familias explícitas: meteorología, detecciones térmicas, espacio aéreo y obstáculos. A4 histórico es contexto preventivo. |
| 5.2 Asignación de pesos | 2 | 14 | `core/patrol_routing.py:enrich`, `pesos.json`. Tiempo equivalente, proximidad y despeje. Ejemplos reales admitidos, penalizados y excluidos. |
| 6.1 Restricciones desde metadata | 3 | 13–15, 23 | Perfil, comprobaciones de corredor, viento, observación y retorno. Preferencias efectivas exportadas. |
| 6.2 Defaults | 2 | 13–15 | `config/vigilancia.json`, `docs/VIGILANCIA.md`, formulario y respuesta JSON. |
| 7.1 Nombre y paper | 4 | 16 | Yen (1971), *Finding the K Shortest Loopless Paths in a Network*, DOI 10.1287/mnsc.17.11.712. `pgr_KSP`. |
| 7.2 Explicar algoritmo | 6 | 14–17 | Pseudocódigo en `docs/VIGILANCIA.md`, `Paths`, `compose`, `assess`, `plan`. Límites K=10, beam=50, hasta seis órdenes. |
| 8 k≥2 con Dijkstra | 4 | 18–19 | `comparacion_1.json`: D1 y D2 físicamente distintas. `Paths.get` llama solo `pgr_dijkstra` con costo `flight_km`. Exclusiones geométricas para D2. |
| 9 k≥2 con propuesta | 4 | 16–17, 20 | `comparacion_1.json`: P1 y P2 distintas, observación y regreso evaluados. |
| 10 Métrica de resiliencia | 6 | 21 | `core/patrol_evaluation.py`, `core/mission_evaluation.py:summarise`, 104 escenarios comunes, rutas congeladas y ejemplo manual 3/4. |
| 11.1 Plataforma comparativa | 4 | 19–20, 23 | `Sitio Web/patrol.*`, endpoints `/api/v1/vigilancia/*`, `interfaz.json`, capturas reales y exportación exacta. |
| 11.2 Diferencial | 2 | 22–23 | JSON comparativos y `lote/summary.json`, puntos porcentuales con denominador y familias de escenarios. |
| **Total** | **60** | **24 diapositivas** | Informe de reproducción en `evidencia/vigilancia_2026-10-22/INFORME.md`. |

Los archivos de evidencia se refieren a la publicación indicada en `publicacion.json`.
Los conteos de rutas son resultados, no parámetros que se fuerzan: un caso sin dos
alternativas distintas conserva ese resultado. El ejemplo de la interfaz acredita las
cuatro trazas; el lote fija horas antes de evaluar y registra también las inviables.
La publicación en Git queda a cargo del usuario.
