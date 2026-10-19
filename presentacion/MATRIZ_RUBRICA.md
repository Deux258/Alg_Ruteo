# Matriz de cobertura de fase2

Presentación: fase2_valparaiso.pptx, 22 diapositivas editables con notas de fuentes.
Es una matriz de evidencias, no una autoasignación de60 puntos. Se usa el mismo run
b80f9b83-cad7-53b8-a8b8-34a2a17e614c y los hashes en evidencia/fase2_2026-10-19.

| ID | Pts | Criterio | Diapositiva | Evidencia / implementación |
|---|---:|---|---|---|
|1|2|Docker y extensiones|3|main_limpio.log; pruebas.json; Compose e imágenes fijadas|
|2|2|Diagrama y SQL|4–5|Diagrama editable resumido; BD/diagrama_fase2_relaciones.png; DDL y migraciones002–004|
|3.1|6|Cuatro ET metadata|8–9|Metadata/m1_bases a m4_clima; fuente y transformación|
|3.2|2|Cuatro cargas metadata|10|Módulos --load; tablas y conteos reales|
|4.1|6|Cuatro ET amenazas|11–12|Amenazas/a1_meteorologia a a4_historial|
|4.2|2|Cuatro cargas amenazas|13|Cargadores, hazards y tablas tipadas; A2 vacío válido|
|5.1|3|Cuatro modelos de falla|14|Meteorología, bufferFIRMS, AIP2D y exposición histórica|
|5.2|2|Costos y exclusiones|15|Segundos con viento; filtros duros; exposición ordinal separada|
|6.1|3|Preferencias|15|budget_s, wind_limit_ms y detour_factor efectivos; captura y pruebas|
|6.2|2|Defaults|15|1200s utilizables,8m/s y1.20; perfil del informe|
|7.1|4|Algoritmo y artículo|16|Yen1971, pgr_KSP; adaptación y límites explícitos|
|7.2|6|Funcionamiento|17|Filtros,9 pares, retorno y ausencia de candidatos|
|8|4|Dos rutas Dijkstra|18|D1/D2 de ida y retorno; longitudes; mapa y pruebas independientes|
|9|4|Dos opciones propuestas|19|Dos idas distintas con misión completa y perfil|
|10|6|Métrica implementada|20|Catálogo, fórmula, bucle sin replanificar y escenarios desconocidos|
|11.1|4|Comparación en mapa|18–21|Mapas separados, mismo OD y condiciones; cuatro opciones|
|11.2|2|Diferencial|21|99% frente a99%; delta0pp, sin ocultar ausencia de mejora|

Consigna adicional: infraestructura y contrato en6–7, main/Docker en3/22, fuentes/
diccionarios/cargadores en8–15, webLeaflet y evidencia de uso en las capturas vinculadas.
Los archivos originales conservan SHA y se explican los JSON derivados de evaluación.

## Antes de entregar

Revisar la presentación como equipo, confirmar plazo y formato aceptado por el docente.
Verificar el repositorio GitLab UDP y subir el archivo a Canvas. Esta implementación no
publicó en esas plataformas. El PDF del informe y plan originales contiene una referencia
al área previa: no mezclar sus85 nodos/93,28km² con los154 nodos/54,92km² de vigilancia
actual y97,72km² de tránsito. El retorno se incluye en las métricas de esta versión.

La comparación es estática, retrospectiva y con fallas sintéticas. No certifica vuelo,
disjunción geográfica, superioridad estadística ni toda la hipótesis temporal de fase1.
