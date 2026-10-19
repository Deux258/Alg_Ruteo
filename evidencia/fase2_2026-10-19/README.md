# Evidencia de fase2, 19-10-2026

- INFORME.md: cambios, hallazgos y lÃ­mites.
- pruebas_p0.json/log: 99 pruebas al reparar el build.
- pruebas.json/log: cierre de 111 pruebas y versiones/huella reales.
- arranque_limpio.json y main_limpio.log: nueve cargas desde volumen nuevo.
- repeticion.json: idempotencia sobre la publicaciÃ³n existente.
- diagnostico.json: Ã¡reas, topologÃ­a, catÃ¡logo, fuentes, SQL, esquema y PK/FK.
- constraints.json: restricciones inspeccionadas en PostgreSQL.
- software.json: commit de base, hash del cÃ³digo y versiones efectivas.
- dgac_dns.json: fallo actual de resoluciÃ³n del servidor DGAC.
- solicitud.json: caso de misiÃ³n nuevo reproducible.
- comparison_<sha>.json: resultados de ambas colecciones congeladas y mÃ©tricas.
- scenarios_<sha>.json: catÃ¡logo fijo de 100 escenarios.
- mapa.json: capas del mapa del mismo run, sin ser nueva fuente de datos.
- mapa_comparativo.svg/png: contexto espacial y rutas con escala comÃºn.
- rutas_reference/proposed.json y mapas PNG: dos opciones por mÃ©todo.
- interfaz/: capturas, DOM y respuestas de 11 comprobaciones reales.

Contratos, unidades, productores/cargadores de evaluaciÃ³n y significado de vacÃ­os:
docs/FASE2_METADATA_TRANSITO.md. Scripts: tools/evidencia_fase2.py,
figuras_fase2.py, diagrama_fase2.py y probar_interfaz_aerea.py.

- verificar.sql y verificacion_sql.jsonl: consultas de lectura y resultados de PostgreSQL.
- salud_final.json: comprobación del servicio entregado en 18081.
- presentacion_validacion.json: integridad, estructura y renderizado de 22 diapositivas; no acredita ejecución nativa en PowerPoint.
