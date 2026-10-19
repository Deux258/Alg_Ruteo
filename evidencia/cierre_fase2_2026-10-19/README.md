# Índice de evidencia de cierre

- INFORME.md: cambios, resultados, autocrítica y límites.
- ENTREGA_MANUAL.md: pasos pendientes de GitLab/Canvas con la cuenta universitaria.
- baseline.json y baseline_pre_msys/: referencia anterior, no validación final.
- pruebas.json/log: suite final y versiones; main_limpio.log y arranque_limpio.json: volumen nuevo.
- repeticion.json: repetición idempotente de la publicación; lote_repeticion.json: SHA repetido del lote.
- software.json: commit de base, archivos y huella exacta del código.
- experiment_447e0e6a023159ae/: plan previo, 120 comparaciones y sus escenarios, resumen total y por perfil.
- json_examples.json: proyecciones de nueve paquetes reales y SHA de cada original íntegro.
- dijkstra.sql y dijkstra_result.json: consulta ejecutable por longitud y resultado real.
- segment_examples.json: fixture sintético separado de las fuentes; no son incidentes reales.
- schema.json y diagnostico.json: 29 tablas, claves, topología y conteos del run.
- dgac_dns.json y aip_http.json: comprobaciones independientes; DNS intermitente, descarga no acreditada.
- mapa.json, solicitud.json y comparison/scenarios: demostración individual posterior a adquisición.
- interfaz/: 13 acciones reales, DOM, capturas, respuestas y exportación de política.
- presentacion_validacion.json: integridad y render; no acredita ejecución nativa de PowerPoint.
- manifest_entrega.json: hashes, sin .env, credenciales o directorios privados.

Productores/cargadores y unidades: docs/FASE2_METADATA_TRANSITO.md y diccionarios por fuente.
Las antiguas evidencias en fase2_2026-10-19 se conservan y no se atribuyen a esta versión.

- verificacion_final.json: cero duplicados y segmentos exteriores, consultado con rol de lectura.
- salud_final.json e imagen.json: servicio listo y SHA de la imagen Docker entregada.
- dgac_dns_inicial.log: consulta previa que resolvió DNS; HTTP posterior no disponible.

La presentación se genera con tools/presentacion_cierre.mjs y el runtime de Presentations
de Codex (artifact-tool). Requiere RUNTIME_NODE_MODULES, RUNTIME_PYTHON y
PRESENTATIONS_SKILL_DIR del runtime, y utiliza la presentación anterior como referencia.
El generador rechaza sobrescribir el archivo final: conservar una copia o elegir otra
salida al revisar. La ejecución de ETL, BD, ruteo, pruebas y web permanece en Docker.
