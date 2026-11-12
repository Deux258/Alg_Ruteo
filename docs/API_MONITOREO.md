# Contrato de monitoreo, versión 1

`GET /api/aereo/patrullaje/mapa?view=summary` incluye `monitoring` (catálogo de sectores sobre toda el área, certificado geométrico y pendientes) y `fire_baseline` (datos oficiales, fórmula y limitaciones). Los sectores no se anuncian como vuelos factibles antes de calcularlos.

`GET /api/aereo/patrullaje/monitoreo` devuelve el catálogo y el progreso actual, sin reutilizar el progreso congelado del resumen cartográfico.

Incluye `programmes`, los programas principales por base. `POST /api/aereo/patrullaje/jornada` acepta `operation=plan|prepare`, `programme_id`, `date` ISO y el perfil habitual. Devuelve los vuelos completos ordenados con geometría, tiempos, referencias de misión, cambio de batería entre vuelos y sectores pendientes. `plan` reutiliza las jornadas guardadas; `prepare` las calcula y valida. Si un sector no permite cobertura completa, conserva su diagnóstico e intenta los siguientes sectores de la rotación hasta completar los dos vuelos o agotar las alternativas previstas. La reproducción encadena solo vuelos viables de la misma base y se detiene ante incidentes.

`POST /api/aereo/patrullaje` acepta `patrol_id` del catálogo vigente. El servidor resuelve objetivo y base, y calcula las cuatro técnicas existentes sobre la infraestructura vigente. Sin ID se conserva el objetivo personalizado. Ningún cliente puede configurar la tasa de incendios.

`POST /api/aereo/patrullaje/simular` conserva sha256, method, route_set, seed, scenario_index y scenario. `fire_mode=automatic` es el valor predeterminado; `fire_mode=manual` con `fire=[lon,lat]` solo sirve para diagnóstico. `scenario=nominal` desactiva fallas de infraestructura, pero mantiene el proceso de incendios. `recovery_method` permite elegir una técnica y `return_destination=auto|origin|station` fija la política de aterrizaje. Parámetros de probabilidad/ventana aportados por el cliente se rechazan.

La respuesta tiene esquema `patrol-simulation-3` y contiene `fire_event` auditable, `recovery` con cuatro técnicas y candidatos por destino, y `monitoring_progress` cuando se trata de un sector del catálogo. La interfaz no revela coordenadas ni candidatas antes de la detección. `detection` mantiene estados de reporte y sus tiempos. Sin solución de Gurobi no se etiqueta una ruta de Dijkstra como Gurobi. La ausencia de solución bajo una técnica no demuestra imposibilidad bajo las demás. `recovery.graph_scope` identifica el grafo de corredores compartido y su preparación común. `no_selected_recovery` distingue una técnica/política no disponible de la falta física de cualquier regreso.

Los resultados simulados se guardan en `datos/runs/monitoreo/`. El progreso acumula solo celdas realmente observadas en las trayectorias simuladas, con terreno conocido y línea de vista; no equipara sectorización con vigilancia realizada. No representa vuelos físicos ni notificaciones externas a Bomberos.
