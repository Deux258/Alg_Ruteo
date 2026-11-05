# Circuitos distintos y reproducción del vuelo

El selector **Mostrar rutas** tiene dos opciones:

- **Circuitos diferentes**, la vista inicial: hasta cuatro recorridos con corredores
  de tránsito distintos. El barrido dentro del objetivo puede ser compartido.
- **Comparación de las cuatro técnicas**: los resultados originales de Dijkstra por
  distancia, Dijkstra ponderado, Gurobi y recocido. Pueden coincidir legítimamente.
  Esta coincidencia se explica en pantalla y no se modifica para aparentar diversidad.

Las tarjetas seleccionan el recorrido a reproducir. **Solo la seleccionada** permite
inspeccionarlo sin superponer las demás; **Mostrar todas** recupera la comparación visual.
Al terminar un cálculo se encuadran los circuitos completos. **Centrar objetivo** acerca
el último polígono agregado en la vista actual, tanto 2D como 3D, y sale de la cámara
del dron o del seguimiento para mantener el encuadre solicitado.

## Diversidad espacial

`routes` conserva las cuatro técnicas originales; `route_alternatives` contiene los
circuitos operativos `alt_1` a `alt_4`. El circuito de referencia proviene de una técnica
viable. Se aprovechan otros resultados originales si sus corredores son distintos.
Las opciones adicionales se buscan con Dijkstra penalizando el uso de corredores ya
seleccionados y variando el orden/orientación de las pasadas. Se identifican como
**corredores diversificados**, sin atribuir esos resultados a Gurobi o al recocido.

Cada candidato respeta el grafo dirigido, amenazas, elevación, autonomía, inventario
de baterías, presupuesto de misión y cobertura completa. La búsqueda nunca inventa
desplazamientos en el dibujo ni modifica los costos físicos para presentarlos como reales.

Se compara la unión de los corredores, ignorando dirección y densidad de muestreo.
Invertir el sentido o remuestrear la misma geometría no produce una alternativa nueva.
La medida es el máximo de las dos fracciones de longitud dentro de un buffer de 12 m
del otro corredor. Se excluyen el objetivo con margen de 5 m y los primeros 20 m alrededor
de la base, pues necesariamente se comparten para vigilar la misma zona y despegar.

El umbral central admite como máximo 80 % de tránsito compartido con **cada** circuito
anterior. La duración se limita al menor valor entre el presupuesto de misión y
`1,8 × tiempo de referencia + 60 s`. Estos umbrales y el límite de búsqueda de 15 s están
en `config/patrullaje.json`. Si hay un único corredor o la búsqueda no encuentra cuatro
opciones dentro de los límites, se informa una cantidad menor, sin duplicar rutas ni
afirmar que la búsqueda limitada demuestra inviabilidad.

Las métricas de cobertura y resiliencia de los circuitos se vuelven a evaluar. Las
técnicas y alternativas utilizan los mismos escenarios de amenaza. Los tiempos de
cómputo originales se conservan en la comparación; la vista de circuitos informa la
generación acumulada de alternativas desde los resultados originales. `diversity`
guarda parámetros, rechazos, intentos y tiempo de búsqueda.

## Reproductor y cámara

La barra sobre el mapa funciona en ambas vistas:

- **Reproducir** prepara un recorrido nominal sin sortear fallas y lo inicia desde tierra.
- **Pausar**, **Inicio**, **Fin** y la barra temporal permiten explorar la misión.
  Al terminar, **Repetir** vuelve al comienzo. Se puede cambiar la velocidad.
- **Seguir dron** centra la vista externa mientras avanza.
- **Vista del dron** abre una cámara en perspectiva en la posición interpolada del dron,
  orientada hacia el próximo tramo. Arrastrar permite mirar alrededor y la rueda cambia
  el campo de visión. Es una vista sintética de los datos 3D, no una transmisión de cámara.

**Preparar sin sorteo** carga el vuelo nominal en pausa. **Sortear y reproducir** conserva
el caso con amenazas aleatorias y permite replanificar. El foco sintético, si está marcado,
sigue provocando detección, reporte y regreso. La reproducción nominal no cambia las
probabilidades ni las métricas estadísticas de las tarjetas.

La animación usa segundos físicos e interpolación entre muestras, incluyendo despegue,
ascensos y descensos, aterrizajes y cambios de batería en tierra. El reparto temporal
de subtramos considera viento y velocidad vertical. Los puntos de cambio de batería
se identifican por aristas completadas; su posición no depende del remuestreo visual.

La barra espaciadora reproduce/pausa cuando el mapa tiene el foco. Al ocultar la pestaña,
el reproductor se pausa. Al cambiar la configuración o el objetivo se retira el vuelo
anterior y se exige recalcular; una respuesta que llegue para una configuración anterior
no se presenta como resultado de la nueva.

## Edición y reproducción

El dibujo permite **Deshacer vértice**, Ctrl/Cmd + Z y **Cancelar** o Escape. Se indica
el número de vértices y solo se habilita cerrar con tres o más. Cancelar restaura el
objetivo anterior. Los controles de capas están recogidos inicialmente para facilitar
la lectura de las rutas.

Comprobaciones reproducibles:

```bash
python -m unittest tests.test_patrol tests.test_patrol_alternatives tests.test_geographic_scene -v
node --test tests/flight_player.mjs
python -m tools.verificar_reproductor --chrome "<ruta a Chrome>"
```

El flujo de cuatro técnicas y la recarga siguen comprobándose con
`tools/verificar_patrullaje.py` y `tools/verificar_recarga.py`, que eligen explícitamente
la vista de comparación. Todas las verificaciones se ejecutan sin video por defecto.
