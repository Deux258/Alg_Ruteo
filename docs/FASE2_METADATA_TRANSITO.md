# Contrato activo de fase 2 · metadata y tránsito

## Versiones y autoría

Contrato de infraestructura 4.0, builder `aerial-grid-v2`. Las publicaciones anteriores permanecen
inmutables y las APIs conservan lectura de su área única. Se mantienen el DDL inicial y migraciones
002 y 003 sin cambios; 004 añade `run_areas`, `base_catalogue`, `mission_evaluations` y atributos M2.
El esquema tiene 29 tablas. Los campos de `profiles` del diseño inicial son legado; el perfil
activo se conserva en `aerial_models.profile` por ejecución y la respuesta incluye el perfil efectivo.

M1–M4 integran los scripts y diccionarios de Diego Hidalgo mediante `core.metadata_hidalgo` y el
pipeline común. `aportes_metadata_diego` permanece intacto como antecedente. Su infraestructura
con tres nodos inventados es una prueba y no se incorpora. Tampoco se incorpora `riesgo_clases.geojson`:
faltan raster original, CRS documentado y significado autorizado de clases 0–4. Las clases 1–5 de S7
son otro producto con semántica conservada; no se equiparan ambos mapas.

## Áreas y geometrías

`lineage.aoi` conserva archivo original, SHA-256 y geometría exacta de vigilancia. `flight_area`
contiene buffer derivado de 1100 m, CRS de análisis 32719 y `quad_segs=16`. GeoJSON siempre WGS84
[longitud,latitud]. `run_areas` guarda ambas áreas en MultiPolygon EPSG:32719. `ST_Covers` incluye
el borde y comprueba segmentos completos. No se toleran conexiones de extremos dentro con tramos fuera.

La malla ocupa tránsito. Solo los puntos dentro de vigilancia y en bosque/pradera/matorral reciben
kind `vigilancia`; el resto son navegación. Los nodos originales son persistentes; los extremos
libres y arcos de consultas son temporales, con IDs negativos que excluyen -1. Distancia máxima
1500 m también para extremos temporales. Las consultas no modifican los nodos publicados.

## Fuentes y tiempo

S1–S7 mantienen los productos del informe. S1H añade el item ArcGIS
`ac7929a4d40e4879afd09b0c04b12fd3`, capa 0, ID FID. Catálogo: autor Junta Nacional de Cuerpos
de Bomberos, fuente IDE CHILE, publicador TerrenoIII, licencia declarada Dato Abierto. Esto no acredita
actualización operativa ni autorización de uso. Se conservan item, IDs y páginas HTTP y sus hashes.

S1/S1H/S2/S7 se adquieren para la caja del área ampliada. FIRMS regional cubre tránsito y se retienen
centros externos si su buffer lo intersecta. DSM GLO-30 S34 W072 cubre la extensión. AIP se analiza
sobre tránsito y margen de selección 300 m. El reporte del parser inventaría formas y excepciones;
no se afirma conocer todas las restricciones aeronáuticas ni sustituir NOTAM/permisos.

M4 fija `models=ecmwf_ifs025`, `timezone=UTC`, `wind_speed_unit=ms`, seis variables y celda devuelta.
La serie automática aportada se conserva como antecedente y no se sustituye silenciosamente.
`valid_at` es validez, `fetched_at_utc` obtención y `issued_at` queda nulo al no exponerse en la respuesta.
Los ejemplos que preceden a la obtención son retrospectivos, no un experimento causal de pronóstico.

La adquisición selectiva exige partición explícita de ocho IDs entre descarga y reutilización.
Verifica hashes antes de reutilizar y rechaza reutilización espacial que no cubra la nueva extensión.
Un fallo escribe `adquisicion_incompleta.json`, preserva manifiesto y publicación anteriores. No se
cuenta la reutilización de S6 como descarga fresca. Una actualización crea otro run; repetir exactamente
el mismo snapshot conserva IDs y no duplica registros.

## Diccionario de salidas

Las ocho salidas metadata/amenazas conservan `schema_version=aerial-dataset-1`, run_id UUID,
dataset_id UUID determinista, dataset_key, source_id, observed_at, extracted_at, records y lineage.
Lineage incluye source, AOI y hash del contexto. M1 añade supporting_sources.S1H; A3 incluye
parser_report. Las cargas comparan registros y linaje con el contexto verificado antes de insertar.
No vuelven a consultar servicios externos. Estados: valid o empty; un error no se convierte en vacío.

| Salida | Campos principales del registro | Tabla y sentido |
|---|---|---|
| M1 | provider_id, name, commune, address, geometry, inside_study, distance_to_study_m, candidate, selection_reason, source_refs, original_record, node_id solo si candidata | base_catalogue:16; base_metadata:5, FK a nodos |
| M2 | provider_id, geometry, category, source_year, repaired, attributes, original_area_ha, clipped_area_ha, original_record | landcover: polígonos recortados a tránsito |
| M3 | node_id, elevation_m, quality | node_elevation: una fila por nodo real |
| M4 | valid_at, cell, temperature_c, relative_humidity_pct, wind_speed_ms, wind_direction_deg, wind_gust_ms, precipitation_mm | weather: una fila por hora UTC |
| A1 | provider_id, geometry, valid_at, state, reason | hazards + weather_hazards, FK M4 |
| A2 | provider_id, point, geometry, acquired_at, confidence, fire_radiative_power_mw, buffer_m | hazards + thermal_events |
| A3 | provider_id/code, geometry, lower_limit, upper_limit, conditions, document_page, original_record y forma | hazards + airspace_zones |
| A4 | provider_id, geometry, ordinal_class, class_label, period_start, period_end, repaired | hazards + historical_risk |

En M1 los source_refs evitan confundir IDs de proveedores. S1:104 y S1H:19 representan la misma
Décima Sexta; se comprueba diferencia <=1 m y se mantiene la coordenada histórica exacta. Los cuatro
externos se seleccionan por IDs 18,20,23,31, no por parecido de nombre. Las distancias son metros UTM,
sin redondear para decidir inclusión. Instalar un punto catalogado no demuestra capacidad aeronáutica.

M2.attributes conserva land_use_code, subuse, structure, cover_class, height_class, forest_type,
forest_subtype y commune. Son categorías de la fuente, no alturas métricas certificadas.
original_area_ha conserva superficie publicada del polígono completo; clipped_area_ha calcula la
superficie del recorte en UTM. Un atributo ausente conserva null, no cero inventado.

M3 representa superficie DSM en metros EGM2008, aproximadamente 30 m, muestreo con máscara,
escala/offset aplicados una vez y calidad valid/nodata. No elimina cotas negativas ni convierte NoData
en terreno plano. No modela altura AGL, cables, energía vertical ni autorización aeronáutica.

## Costos, preferencias y estados

Defaults: velocidad aire10 m/s,25 min,reserva20 %,observación60 s,presupuesto1200 s;
viento o racha >=8 m/s excluye y temperatura debe permanecer en [-5,40] °C. Tiempo de arco = longitud
métrica / velocidad sobre suelo dirigida, con componente transversal y signo meteorológico correctos.
Longitud km no se suma a segundos ni exposición. A4 usa (clase-1)/4, solapes con máximo y penalización
1 para metros sin cobertura, sin convertirlo en probabilidad. El dato desconocido se informa aparte.

`preferences` opcional acepta budget_s en (0,1200], wind_limit_ms en (0,8], detour_factor en [1,1.2].
También acepta `max_historical_class`: entero 1–5 o null, predeterminado null. Al activarlo
excluye clases históricas superiores y tramos sin cobertura, con causas diferenciadas.
Es una política preventiva académica, no un cierre observado ni un incendio actual.
Se aplica a segmentos completos y extremos UTM, tanto al generar la propuesta como al
evaluar ambos métodos. Dijkstra conserva su generación por distancia. Las evaluaciones
nuevas declaran `evaluation_version=mission-comparison-v2`; las anteriores se conservan.
No acepta claves ajenas, booleanos ni números no finitos. Omitir usa defaults. La capa A1 precalculada
muestra defaults; el ruteador recalcula la meteorología con el perfil efectivo solicitado.

FIRMS n/h se acepta, l se descarta. Antes de observación no se anticipa la detección. Un foco de
hasta24h conserva cierre; uno más antiguo sin resolución pasa a desconocido y sigue excluido.
No se infiere extinción por edad o ausencia de otra detección. AIP permanece exclusión 2D. Los eventos
recibidos por web son siempre sintéticos; resolver uno no rehabilita otro superpuesto ni AIP.

## API

GET /api/aereo/mapa devuelve vigilancia en area y tránsito en flight_area, catálogo y cinco bases,
red, ejemplos, perfil, metadata y amenazas. M2 simplifica solo dibujo a3m y expone atributos descriptivos.
POST /api/aereo/rutas y /api/aereo/replanificar conservan sus campos y añaden preferences y
response.effective_profile. El destino debe estar en vigilancia. El origen externo debe coincidir
con una de las cuatro bases aprobadas (tolerancia1mm). position puede ser nodo de tránsito o extremo
original; phase=return/emergency_return conserva hogar y tiempo consumido. on_edge devuelve interrupted.

POST /api/aereo/comparar recibe una misión nueva: origin,destination,time,events opcionales y preferences.
Rechaza trayecto simple, fases de retorno, position y tiempo consumido. Devuelve sets.reference y
sets.proposed, features con method/rank/role, perfil, escenario, métricas, hashes y huella de software.
IDs BIGINT se transmiten como texto. Máximo256KiB y20eventos por solicitud. HTTP422 para entrada
inválida,503 para indisponibilidad. Los fallos de factibilidad normales conservan estado y causa.

Dijkstra obtiene D1/D2 para ida y retorno y combina hasta4 pares, seleccionando2 por longitud total
con idas distintas. Genera sin filtrar amenazas/autonomía para conservar la referencia obligatoria.
La propuesta examina hasta3×3 pares y elige hasta2 idas distintas por exposición/tiempo con retorno,
presupuesto restante y1.2Tmin. search_limited declara el límite: no es un óptimo global de exposición.
La respuesta informa menos de2alternativas y no fabrica caminos.

## Métrica de misión congelada

Un control y99círculos:33con radio100m,33de250m,33de500m. Centros uniformes por rechazo en tránsito,
semilla20261018, mismo catálogo para ambos métodos e independiente de sus rutas. Primero se fijan
las opciones y después se comprueba cada misión completa contra cada escenario. No se invoca el
ruteador dentro del bucle. Se suman ida+60s+regreso con condiciones estáticas de la hora seleccionada.

I(P,w)=1 si geometría, restricciones y presupuesto siguen admitiendo toda la misión. R_individual es
su media; R_conjunto es la media de max(I) entre las opciones del método. Delta=100(Rp-Rd), en pp.
Los escenarios de información crítica desconocida se excluyen de ambos denominadores y se cuentan.
Si no hay válidos, porcentajes y delta son null. Sin opciones, un método no sobrevive.

La web opera solo con usuario de lectura. main evaluar persiste con rol ETL en mission_evaluations,
solo inserción e idempotencia por SHA. No fuerza nodos temporales en route_sets/route_edges. Guarda
comparison_<sha>.json y scenarios_<sha>.json con solicitud, geometrías, escenarios y perfil. Ambos
archivos quedan documentados aquí; el CLI es su productor y cargador asociado. mapa.json/diagnostico.json
son evidencias derivadas del mismo run, no nuevas fuentes ETL.

## Evaluación por lote

`./main evaluar --experiment config/evaluacion_fase2.json` es excluyente con `--request`.
El protocolo fijo fase2-batch-v1 utiliza cinco bases, cuatro objetivos extremos UTM
(norte, sur, este, oeste; sin repetir, empates por ID), tres horas disponibles posteriores
a adquisición (primera, central y última, sin filtrar por viento), y dos perfiles:
predeterminado y clase histórica máxima 4. Las reducciones por falta de datos quedan
registradas. `plan.json` se escribe antes de ejecutar los algoritmos.

Salida `experiment_<sha>/`: plan, summary y una carpeta por caso con comparison/scenarios.
Productor/cargador: core.mission_evaluation, invocado por main con rol ETL; las comparaciones
se insertan en mission_evaluations y el resumen se conserva en archivo. No se añaden
tablas ni se reemplazan instantáneas. Los errores inesperados interrumpen el comando;
el plan y las comparaciones ya producidas permanecen, sin resumen de éxito falso.

`summary.json` incluye total/valid/unknown_cases, denominador caso-escenario común,
media de supervivencia por caso, diferencial medio/mínimo/máximo y conteos de mejoras,
empates y empeoramientos. También disponibilidad de dos opciones, factibilidad en control,
estados, causas y fracción de la segunda ida a 50 m de la primera. Una misión sin opciones
cuenta como cero con condiciones conocidas; los desconocidos se excluyen de ambos métodos.
`by_profile` separa los dos perfiles. No se seleccionan casos por sus resultados y no se
interpreta la media como estimación estadística de éxito real. Plan y resultado tienen SHA.

## Reproducibilidad y software

El diagnóstico aditivo de adquisición y misiones se describe en
[DIAGNOSTICO_FASE2.md](DIAGNOSTICO_FASE2.md). Mantiene los estados originales y
separa motivos principales, causas simultáneas y comprobaciones no realizadas.
La repetición exacta de 120 solicitudes conserva rutas, costos y métricas.

requirements.lock pglast7.20 fija el wheel CPython3.12 Linuxamd64 verificado; los demás pins se conservan.
Docker y CI instalan con --require-hashes y ejecutan pip check. Las pruebas informan versiones instaladas
y discrepancias de locks. software.json conserva commit de base y hashes de código/SQL/configuración;
el trabajo local no comprometido se identifica por code_sha256, sin afirmar que el commit incluya los cambios.

Se aplicaron geomaster y webapp-testing. Referencia verificada: Kassis,T., Agarwal,V., He,Y., Patel,D.
y Brueckner,A.M.(2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents.
https://doi.org/10.48550/arXiv.2609.00065 (registro revisado v2, sin sufijo en DOI).
Referencias técnicas: https://pypi.org/project/pglast/7.20/ ; https://open-meteo.com/en/docs ;
https://doi.org/10.1287/mnsc.17.11.712 ; https://postgis.net/docs/ST_Covers.html .
