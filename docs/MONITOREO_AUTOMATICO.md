# Monitoreo automático de incendios

## Rutas principales y jornada

El panel inicial ofrece un programa por base y una fecha. **Ver rutas del día** prepara automáticamente dos vuelos completos con Dijkstra ponderado, verifica terreno/cobertura y guarda sus trayectorias. Las jornadas ya preparadas aparecen dibujadas al abrir la página. Se puede pulsar un vuelo para inspeccionarlo o **Simular jornada** para reproducir ambos en orden, con 120 s simulados de cambio de batería en la misma base. El reproductor permite pausar y cambiar perspectiva; **Detener jornada** cancela la secuencia. Una detección o un regreso interrumpido detiene la jornada para revisar el incidente. No se traslada el dron entre bases por teletransporte.

La fecha organiza una rotación determinista por todos los sectores asignados a esa base; dos vuelos no se presentan como vigilancia diaria del territorio completo. El clima sigue siendo el del snapshot seleccionado. La planificación individual queda en un panel desplegable. Las cuatro técnicas de recuperación siguen disponibles al detectar un foco. La API es `POST /api/aereo/patrullaje/jornada` con `operation=plan|prepare`, `programme_id`, `date` y el perfil habitual; las rutas se guardan en `datos/runs/monitoreo/daily/` y se invalidan al cambiar datos, perfil o código del planificador.

Seleccionar un sector en **Monitoreo de toda la zona** y pulsar **Planificar e iniciar sector**. El servidor resuelve su base y polígono, calcula las técnicas, comprueba recursos/cobertura y reproduce el vuelo. **Siguiente sector** omite los sectores ya observados completamente en la campaña simulada. Los objetivos dibujados/importados siguen disponibles.

## Base empírica y significado de la probabilidad

CONAF publicó el **1 de junio de 2026** un acumulado de **575 incendios en la Región de Valparaíso**, desde el **1 de julio de 2025**. La noticia todavía no cerraba la temporada ni precisaba el día exacto de extracción del conteo: se usa la fecha de publicación como corte conservador de exposición (**335 días**). El Ministerio de Agricultura publica una superficie regional de **16.396,1 km²**, incluido territorio insular.

- [CONAF: balance regional 2025–2026](https://www.conaf.cl/conaf-valparaiso-reconoce-la-labor-de-su-personal-en-el-periodo-de-mayor-riesgo-de-incendios-forestales-2025-2026/).
- [Ministerio de Agricultura: Región de Valparaíso](https://minagri.gob.cl/region-de-valparaiso/).
- [Datos fijados y trazabilidad](../config/incendios_valparaiso.json).

La intensidad estimada es `λ = 575 / (335 × 16.396,1) = 0,0001046845 incendios/(km²·día)`. Para un objetivo de área A y exposición T: `p = 1 − exp(−λAT)`, convirtiendo A a km² y T a días. Por ejemplo, 0,16 km² y 20 minutos dan aproximadamente **0,0000233 %**. No se aumenta esa probabilidad para que haya un incendio en cada demostración.

Es una **estimación regional extrapolada**, no una probabilidad observada directamente para la ciudad/comuna ni un pronóstico de incendios. El modelo homogéneo promedia estacionalidad, vegetación y heterogeneidad urbana/rural/insular. Solo modela incendios nuevos durante la exposición, no focos existentes antes del vuelo. Los porcentajes ordinales A4 de fallas de infraestructura se mantienen separados y no calibran esta tasa.

## Aparición, detección y notificación interna

El generador usa U uniforme reproducible por semilla/escenario/objetivo, con un espacio de nombres independiente de las amenazas. Los sectores distintos tienen sorteos independientes aunque compartan semilla e índice; las cuatro técnicas sobre un mismo objetivo conservan el mismo evento. El primer arribo sigue la transformación exponencial del proceso de Poisson; cambiar el horizonte conserva el mismo reloj de primer arribo. La ubicación es uniforme por superficie dentro del objetivo en EPSG:32719, respetando huecos. Un punto sin elevación permanece desconocido: no se vuelve a sortear en una ubicación favorable.

El dron no conoce la posición del foco al planificar. El detector solo lo descubre después de su aparición, dentro del radio del perfil y con línea de vista sobre el terreno/obstáculos. Puede no aparecer ningún foco, aparecer después de interrumpir el vuelo, quedar sin observación o ser detectado y reportado. Pausa, velocidad, perspectivas y reinicio de reproducción usan el escenario congelado.

La bitácora registra detección, verificación y reporte; es una notificación **dentro del simulador**. No envía mensajes a Bomberos ni representa un sensor térmico real integrado. El modo manual permanece dentro de **Diagnóstico de detección manual**. «Sin fallas» desactiva las fallas de infraestructura, no el proceso automático de incendios.

## Cobertura de toda el área

El catálogo particiona la geometría completa de estudio mediante una grilla de aproximadamente **400 × 400 m**. Se recorta en el CRS de origen con bordes compartidos, comprueba la unión e informa explícitamente cualquier residuo. Las áreas se miden en UTM; las geometrías de residuos se densifican antes de reproyectar para no transformar errores de redondeo en áreas espurias. El certificado usa una tolerancia numérica de **0,01 m²**.

En el snapshot disponible se comprobaron **405 sectores / 54,920709 km² / 100 % de partición**. Se validaron todos sus polígonos contra el área de estudio y se comprobó un sector real próximo a la base 104 con las cuatro técnicas: 140/140 celdas observables, sin celdas desconocidas. Esto no certifica que los otros 404 vuelos ya sean factibles: sus trayectorias se calculan y validan al seleccionarlos, o con el lote `--plan-all`.

La cobertura se acumula después de simular vuelos, en celdas de 30 m ponderadas por área y verificadas con radio/visibilidad/elevación. Atender un foco y volver no completa el barrido. Zonas inaccesibles, celdas desconocidas y sectores inviables permanecen pendientes. El progreso corresponde a simulaciones, no a vuelos físicos, y cambia de campaña al cambiar el contexto fuente.

El backend calcula y guarda la trayectoria simulada completa al prepararla; el reproductor permite inspeccionar ese resultado. La cobertura acumulada corresponde a esas trayectorias calculadas, no al avance de la barra de reproducción ni a telemetría real. Detener o retroceder la reproducción no borra una simulación ya calculada.

```bash
docker compose --env-file .env run --rm --no-deps etl \
  python -m core.patrol_monitoring --context datos/runs/ID_DEL_RUN/context.json

# Para calcular y exportar cada sector con las cuatro técnicas; puede demorar:
docker compose --env-file .env run --rm --no-deps etl \
  python -m core.patrol_monitoring --context datos/runs/ID_DEL_RUN/context.json --plan-all
```

## Recuperación desde la detección

Se divide el enlace en la posición observada, conservando cotas, distancias, amenazas y tiempos dirigidos por viento. Desde ese estado se comparan origen y próxima estación viable del itinerario; sin una estación ordenada, se elige la alcanzable con menor tiempo de vuelo dirigido. El origen no se duplica como estación alternativa.

Para cada destino se ejecutan Dijkstra por distancia con etiquetas de recursos, Dijkstra con tiempo/riesgo, un MILP de flujo Gurobi y recocido con vecindarios de sufijos y aceptación de Metropolis. Todas las candidatas respetan batería restante, misión y aterrizaje. El costo ponderado integra el riesgo de enlaces; no se interpreta como una probabilidad independiente de éxito de la ruta.

La interfaz muestra cuatro técnicas y el detalle de ambos destinos, hasta ocho candidatas, con tiempo de cálculo, vuelo/aterrizaje, distancia y batería final. Las geometrías coincidentes se declaran. El usuario puede inspeccionarlas en 2D/3D y continuar con una opción; el escenario se conserva al reconstruir la simulación desde el mismo punto. El modo automático recomienda por factibilidad y costo ponderado.

La reserva de reporte solo se gasta si queda un regreso viable con la técnica/política elegida. Si no alcanza, se prioriza el regreso y el reporte queda incompleto. Si otra técnica tiene solución pero la elegida no está disponible, se informa `no_selected_recovery`; no se simula un aterrizaje que no ocurrió. No se incluye recarga intermedia en estas candidatas de aterrizaje. Las estaciones conservan su carácter de apoyos hipotéticos del proyecto.

Las cuatro técnicas usan un mismo grafo de corredores candidatos: unión de los caminos factibles de menor distancia, costo ponderado y tiempo hacia ambos destinos, más conexiones internas cuando caben en el límite de 1.800 enlaces. La preparación común se mide por separado y se exporta en `graph_scope`. Así el MILP puede ejecutarse con la licencia restringida del proyecto. Se declara el alcance sobre los corredores candidatos, sin afirmar optimalidad continua del espacio aéreo. Si los caminos esenciales exceden el límite se conserva el grafo completo y se informa ese alcance.

Gurobi tiene un límite de 10 s por candidata. Licencia ausente, límite de tamaño o falta de incumbente quedan explícitos; no se sustituye por otra técnica bajo su nombre. El recocido usa hasta 64 iteraciones reproducibles sobre subcaminos locales.

## API, archivos y comprobación

[Contrato HTTP](API_MONITOREO.md). Las respuestas y exportaciones incluyen modelo, fuentes, exposición, sorteo, ID de evento, estado, detección, comparación de recuperación y línea temporal. Las coordenadas y regresos no se dibujan antes de la detección. Los JSON completos de auditoría sí contienen el escenario completo.

Las simulaciones se guardan en `datos/runs/monitoreo/<hash>.json`; la cobertura de campaña queda en `datos/runs/monitoreo/<hash_catalogo>/coverage.json`. Estos archivos están excluidos de Git por la política existente de `datos/runs/`.

Las pruebas nuevas cubren tasa/exposición, frecuencia del generador, estabilidad del reloj, ubicación uniforme, falta de elevación, partición con huecos y componentes, rechazo de IDs obsoletos y probabilidad del cliente, detección posterior a la aparición, visibilidad, recursos y cuatro algoritmos. `tools/verificar_monitoreo.py` prueba los controles nuevos con navegador real y conserva capturas y reporte. La suite histórica conserva pruebas de batería, perfiles verticales, patrullaje y exportación.

Comprobación local de esta entrega: **63 pruebas de backend**, **7 archivos de pruebas JavaScript**, **15 casos de interfaz con respuestas controladas** y **23 comprobaciones de navegador con la API real**, incluyendo cambio de alternativa desde detección y vista 3D, aprobados. El caso real de recuperación resolvió los dos destinos mediante Gurobi sobre 279 enlaces y 90 restricciones, con brecha cero dentro del grafo candidato. El reporte y las capturas están en `evidencia/local/monitoreo_browser/`. La comprobación nueva queda incorporada a `tools.ci_acceptance`; el pipeline completo con BD desechable no se ejecutó en esta sesión.
