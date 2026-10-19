# ImplementaciÃ³n de fase 2 y evidencia de cierre

19 de octubre de 2026. Estado: simulador acadÃ©mico Docker. Despeje vertical no verificado.

Run publicado: `b80f9b83-cad7-53b8-a8b8-34a2a17e614c`. Commit de base: `0e5d902ff786811797fdb9f7cb9c476976e3343c`. Los cambios locales no se atribuyen a ese commit: su versiÃ³n exacta es la huella de cÃ³digo `1a776e492ed2f40a074f4911e48f6923c4ec7561233f05960a45aa00f978dbc5` en software.json. No se ha publicado en GitLab UDP ni Canvas.

## Resultado implementado

- IntegraciÃ³n de M1â€“M4 de Diego Hidalgo sin ejecutar el grafo ficticio de tres nodos ni la capa adicional de riesgo sin semÃ¡ntica verificada.
- Contrato 4.0 y dos Ã¡reas; 154 nodos, 1.114 arcos dirigidos, una componente fuerte y una dÃ©bil.
- CatÃ¡logo de 16 instalaciones reales: cinco candidatas, once de contexto. Cuatro orÃ­genes externos aprobados.
- Preferencias de presupuesto, viento y desvÃ­o; validaciÃ³n server-side, perfil efectivo en exportaciones.
- Dos opciones con idas distintas por mÃ©todo, ida/observaciÃ³n/regreso, cierre y replanificaciÃ³n con autonomÃ­a restante.
- ComparaciÃ³n de 100 escenarios con misiones congeladas, persistencia por SHA, diccionarios y CLI asociados.

## GeografÃ­a y fuentes

Vigilancia: 54.920709185 kmÂ². TrÃ¡nsito: 97.716233298 kmÂ², buffer de 1.100 m en EPSG:32719, quad_segs16. GeoJSON original SHA-256: `7d3a0472f2e7fdde88d6316f89c31d6da50914e06cabb6bf8bd270ce54c905b7`.

La base inicial es DÃ©cima Sexta de ValparaÃ­so, Laguna Verde, en **longitud âˆ’71.657239211, latitud âˆ’33.101901690**. ConciliaciÃ³n explÃ­cita S1:104/S1H:19, con coordenada histÃ³rica conservada. La selecciÃ³n no confirma capacidad aeronÃ¡utica ni permiso.

| Base | ID canÃ³nico | SituaciÃ³n | Distancia al polÃ­gono m |
|---|---|---|---|
| Decima Sexta de ValparaÃ­so | 104 | Interior | 0.000 |
| Decima Tercera de ValparaÃ­so | S1H:18 | Externa aprobada | 643.427 |
| Decima Quinta de ValparaÃ­so | S1H:20 | Externa aprobada | 566.489 |
| Decima de ValparaÃ­so | S1H:23 | Externa aprobada | 236.715 |
| Decima Segunda de ValparaÃ­so | S1H:31 | Externa aprobada | 168.739 |

La DÃ©cima Segunda (S1H:31) cae dentro de **SC-P50**. Dijkstra entrega referencia matemÃ¡tica, pero el mÃ©todo propuesto devuelve `endpoint_blocked`. No se elimina esa restricciÃ³n para habilitar la base. Las otras cuatro bases dieron dos opciones propuestas hacia sus objetivos cercanos en la hora de ejemplo; ver bases_routing en diagnostico.json.

Las fuentes son S1â€“S7 del informe y S1H, catÃ¡logo complementario ArcGIS de Bomberos: item ac7929a4d40e4879afd09b0c04b12fd3, publicador TerrenoIII, atribuciÃ³n Junta Nacional de Bomberos/IDE CHILE, licencia declarada Dato Abierto. El catÃ¡logo republicado no garantiza actualidad operativa. Los metadatos originales del item se conservan con hash.

S1/S1H/S2/S4/S5/S7 se adquirieron para esta versiÃ³n. S3 y S6 se reutilizaron expresamente tras verificar sus originales. El manifiesto conserva fechas originales de obtenciÃ³n y hash del manifiesto reutilizado. La adquisiciÃ³n no equivale a obtener todas las fuentes frescas. DGAC continÃºa fallando en DNS, comprobaciÃ³n de hoy en dgac_dns.json.

## Cargas reconciliadas

| Dataset | Registros | Tabla principal / detalle |
|---|---:|---|
| I | 1268 | 154 nodes + 1114 edges |
| M1 | 16 | base_catalogue; 5 filas en base_metadata |
| M2 | 679 | landcover, atributos y superficies original/recortada |
| M3 | 154 | node_elevation, una por nodo real |
| M4 | 48 | weather, seis variables UTC |
| A1 | 16 | weather_hazards + hazards |
| A2 | 0 | thermal_events empty; sin focos inventados |
| A3 | 2 | SC-P29 y SC-P50, airspace_zones |
| A4 | 26 | historical_risk, clases originales1â€“5 |

Originales y manifiesto: datos/entrada/aereo_v2. Los anteriores se conservan. Las alturas de vegetaciÃ³n M2 son clases. M3 es DSM GLO-30 en metros EGM2008 con NoData, escala y offset; los tres nodos de prueba no se cargan. M4 fija ECMWF IFS0.25 y no sustituye la serie con best_match del aporte.

## ComparaciÃ³n reproducible

Hora elegida: **2026-10-19T00:00:00+00:00 UTC**. ObtenciÃ³n de M4: 2026-10-19T03:07:06.516683+00:00. El ejemplo es **retrospectivo**, no acredita uso causal del pronÃ³stico ni condiciones actuales de vuelo.

| MÃ©todo | MisiÃ³n | Longitud total km | Tiempo con observaciÃ³n s | ExposiciÃ³n m ponderados |
|---|---|---:|---:|---:|
| reference | 1 | 1.851807 | 247.312 | 1305.900 |
| reference | 2 | 1.853366 | 247.469 | 1307.532 |
| proposed | 1 | 1.851807 | 247.312 | 1305.900 |
| proposed | 2 | 1.853366 | 247.469 | 1307.532 |

Ambos mÃ©todos producen las mismas opciones en este caso. No se modificaron escenarios, radio ni selecciÃ³n de datos para favorecer a la propuesta. Las dos idas tienen secuencias distintas, pero estÃ¡n geogrÃ¡ficamente prÃ³ximas. Esto no acredita independencia ante fallas correlacionadas.

CatÃ¡logo: un control mÃ¡s99 cÃ­rculos,33 de100m,33 de250m y33 de500m. Centros uniformes en trÃ¡nsito con semilla20261018, fijados sin mirar rutas. No se recalcula ninguna ruta dentro del bucle de escenarios.

| MÃ©todo | Individual1 | Individual2 | Conjunto |
|---|---:|---:|---:|
| Dijkstra | 99% | 99% | 99% |
| Propuesto | 99% | 99% | 99% |

**100 escenarios vÃ¡lidos, 0 desconocidos; Î”R = 0 puntos porcentuales.** Es supervivencia sintÃ©tica para este caso. No es una probabilidad de Ã©xito de vuelo ni una demostraciÃ³n estadÃ­stica de superioridad.

SHA del catÃ¡logo: `ebb780792ceac66f001f5627287bd8d9e4733386e05d007e00c5cca89af9251c`. SHA de evaluaciÃ³n: `58bbb240f9102cec366041eb71bd278274a56c0b31c22b270c8b74af9b98b1f3`. Se conservan las filas por escenario, las cuatro geometrÃ­as, el perfil y la solicitud. La tabla mission_evaluations permite inserciÃ³n idempotente; la web mantiene permisos de lectura.

## Verificaciones ejecutadas

- Build reparado: pglast7.20, hashes reales y pip check. Hito inicial:99 pruebas. Cierre: **111 pruebas,0 fallos,0 errores,0 omisiones**, 293.380s. Versiones instaladas reconciliadas con ambos locks.
- PostgreSQL16.9, PostGIS3.5.2, pgRouting3.8.0 y Python3.12.12 reales en Docker.
- 11 comprobaciones Playwright en Chrome: extremos, bloqueos, resoluciÃ³n, invalidez exterior, preferencias, comparaciÃ³n, cuatro bases externas, origen externo libre rechazado, retorno de emergencia y mÃ³vil. Sin errores de pÃ¡gina.
- main desde un volumen vacÃ­o, snapshot completo: **84.945s** de pipeline (excluye construir imagen y arrancar servicios), registro main_limpio.log.
- RepeticiÃ³n del mismo snapshot: idempotent=true, **84.945s** de pipeline, sin duplicados.
- SQL:0 geometrÃ­as de nodo duplicadas,0 pares de arcos duplicados,154 elevaciones,4 candidatas externas y29 tablas.
- Se comprueban segmentos completos, radio de enlaces temporales, costos Dijkstra mediante implementaciÃ³n independiente y costos geomÃ©tricos PostGIS.
- Pruebas adicionales: adquisiciÃ³n parcial conserva manifiesto, linaje complementario falsificado se rechaza, mÃ©tricas calculables a mano y denominador comÃºn.

## Uso y reproducciÃ³n

```bash
./main probar
./main
./main adquirir --sources S1,S1H,S2,S4,S5,S7 --reuse S3,S6
./main iniciar --mode snapshot
./main evaluar --request datos/runs/solicitud_demo.json
```

Para esta instancia: COMPOSE_PROJECT_NAME=udp-ruteo-fase2-entrega WEB_PORT=18081. main evaluar requiere la BD ya iniciada y la solicitud dentro de datos/runs, montado en el contenedor. La solicitud demo se conserva tambiÃ©n en esta carpeta y puede copiarse a datos/runs/solicitud_demo.json. La adquisiciÃ³n selectiva no publica automÃ¡ticamente.

Figuras: mapa_comparativo.svg/png, BD/diagrama_fase2.svg/png (catÃ¡logo), BD/diagrama_fase2_relaciones.svg/png (29 tablas y FK reales), capturas interfaz y mapas de cada mÃ©todo. Diccionario: docs/FASE2_METADATA_TRANSITO.md. PresentaciÃ³n y matriz: presentacion/.

## Limitaciones y entrega externa

- No hay despeje vertical verificado, energÃ­a vertical ni maniobras durante un tramo. DSM y viento10m no certifican trayectorias reales.
- Escenarios con meteorologÃ­a congelada y bÃºsqueda limitada de candidatos. No hay simulaciÃ³n de condiciones que cambian durante el vuelo ni garantÃ­a de rutas disjuntas.
- VegetaciÃ³n2019, recurrencia2020â€“2024 y catÃ¡logo republicado no acreditan actualidad del territorio o de instalaciones.
- FIRMS vacÃ­o no demuestra ausencia de incendios. Focos antiguos sin resoluciÃ³n conservan exclusiÃ³n como desconocidos; no se infiere extinciÃ³n.
- AIP es una exclusiÃ³n conservadora2D con excepciones del parser. No sustituye revisiÃ³n aeronÃ¡utica, NOTAM o permisos. La base12 bloqueada se conserva como resultado.
- riesgo_clases.geojson sigue excluido por falta de raster/CRS/semÃ¡ntica de clases verificables.
- DNS DGAC impide afirmar una actualizaciÃ³n online completa. Snapshot y reutilizaciÃ³n explÃ­cita funcionan.
- CI quedÃ³ configurado, pero no se ejecutÃ³ en un runner GitLab UDP. El remoto actual es GitHub; no se publicÃ³ ni se subiÃ³ a Canvas.
- phase2_complete sigue false: cargas y evidencia no equivalen a nota mÃ¡xima, aceptaciÃ³n docente ni seguridad de vuelo.

## Software y referencias

Geomaster, webapp-testing y Presentations se aplicaron a esta entrega. Referencia de software: Kassis,T., Agarwal,V., He,Y., Patel,D. y Brueckner,A.M.(2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. https://doi.org/10.48550/arXiv.2609.00065 . Registro arXiv verificado(v2). La referencia no valida los resultados fÃ­sicos de ruteo.

Yen,J.Y.(1971). Finding the K Shortest Loopless Paths in a Network. Management Science17(11),712â€“716. https://doi.org/10.1287/mnsc.17.11.712 . ParÃ¡metros y fuentes originales en manifiesto, documentos del proyecto y diccionario ampliado.
