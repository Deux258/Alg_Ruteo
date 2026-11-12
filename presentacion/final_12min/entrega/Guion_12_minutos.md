# Guion de presentación: 12 minutos, 4 integrantes

Duración de montaje: 12:00. Cada integrante dispone de 3:00, incluyendo acciones y pausas. Las indicaciones de pantalla no se leen. El tiempo exacto se logra con ensayo y edición, no solo contando palabras.

La publicación en GitLab la hará el equipo manualmente. La secuencia de arranque debe grabarse después de esa publicación, mostrando URL y rama reales. Las cifras de ejemplo provienen de evidencia archivada y se identifican como referencia. Si se narran cifras nuevas, deben coincidir con la pantalla de esa grabación.

## 00:00–00:30 | Diego Muñoz | Lámina 1

**Patrullaje aéreo resiliente en Valparaíso**

**Pantalla y acciones:** PPT 1 durante los 30 s. Presentar al equipo sin leer individualmente los cuatro nombres de nuevo.

**Texto para decir:**

Somos Diego Muñoz, Ignacio Pastén, Diego Hidalgo y Eduardo Escalona. Nuestro proyecto simula el patrullaje de drones para vigilancia de incendios en Valparaíso. La misión no consiste solamente en llegar a un punto: debe cubrir un área, respetar restricciones y regresar con batería suficiente. Mostraremos cómo se ejecuta el sistema, cómo comparamos cuatro técnicas y cómo responde ante una amenaza.

Control: 30 s · 60 palabras · rúbrica Contexto.

## 00:30–01:30 | Diego Muñoz | Lámina 2

**Ejecución reproducible desde main**

**Pantalla y acciones:** 00:30–00:42 PPT 2. 00:42–01:15 TERMINAL: GitLab/rama, ./main iniciar --mode snapshot --scope completo, espera acelerada identificada. 01:15–01:30 WEB: abrir URL impresa. Grabar después del traslado manual a GitLab.

**Texto para decir:**

Para repetir el proyecto se necesita el repositorio, Bash y Docker con Compose. En pantalla mostramos la dirección de GitLab y la rama que entregamos. Desde la carpeta del proyecto ejecutamos main en modo snapshot y con alcance completo. Este modo reutiliza los datos originales conservados, por lo que la demostración no depende de que una fuente externa responda en ese momento. El comando prepara los contenedores, aplica la estructura de la base, procesa la infraestructura, carga los metadatos y las amenazas y valida la publicación. La espera está acelerada en el video. Al finalizar, usamos la dirección que imprime la terminal y abrimos la página. Así mostramos tanto el comando para reproducirlo como el resultado disponible en el navegador.

Control: 60 s · 120 palabras · rúbrica 1.

## 01:30–03:00 | Diego Muñoz | Lámina 3

**Una ruta debe respetar el terreno**

**Pantalla y acciones:** 01:30–01:55 PPT 3. 01:55–02:45 WEB: Ver terreno 3D; centrar objetivo; acercar trayectoria y relieve; alternar edificios/vegetación. 02:45–03:00 PPT 3 y traspaso. No afirmar una verificación certificada de vuelo.

**Texto para decir:**

La infraestructura es un grafo geolocalizado: los nodos representan posiciones posibles y los enlaces conectan posiciones admisibles. La versión final utiliza una malla de cien metros y enlaces horizontales de hasta doscientos metros. Pero la proximidad entre dos puntos no basta para aceptar una conexión. El sistema considera el área de tránsito, las exclusiones y la superficie modelada, incluyendo los obstáculos disponibles. Los tramos se muestrean para evaluar el perfil vertical; no se conectan solamente sus extremos ignorando lo que existe entre ellos. La altura inicial se define a sesenta metros sobre la superficie modelada, y el tiempo incorpora viento, ascenso y descenso. En la vista tridimensional podemos relacionar la trayectoria con el relieve, edificios y vegetación. También comprobamos que una misión tenga retorno y que respete su presupuesto de batería. El resultado sigue siendo una simulación académica: el modelo de elevación y las alturas estimadas no certifican todos los obstáculos pequeños de un vuelo real. Con esta infraestructura, Ignacio mostrará cómo se define una misión.

Control: 90 s · 166 palabras · rúbrica 2.

## 03:00–04:00 | Ignacio Pastén | Lámina 4

**La consulta define el área y las restricciones**

**Pantalla y acciones:** 03:00–03:12 PPT 4. 03:12–04:00 WEB: importar caso_demo/objetivo.geojson, base 104 y hora UTC 2026-10-19 00:00; revisar valores y estaciones; Comparar cuatro técnicas. Acelerar espera si corresponde.

**Texto para decir:**

Comenzamos cargando el objetivo de la demostración. También podríamos dibujar un polígono o importarlo como GeoJSON. Elegimos la base de salida y una hora del snapshot meteorológico. Después ajustamos altura, límite de viento, batería, presupuesto total y peso del riesgo. El perfil de referencia usa mil doscientos segundos útiles de batería y tres mil seiscientos segundos de presupuesto de misión. De la batería útil se reservan sesenta segundos para el reporte; no debemos confundir tiempo disponible con tiempo planificable. Las estaciones son escenarios hipotéticos de cambio de batería. Al calcular, estas condiciones se aplican al mismo objetivo para las cuatro técnicas. Si las restricciones impiden completar la misión, el sistema informa la inviabilidad; no dibuja una ruta ficticia para llenar el mapa.

Control: 60 s · 122 palabras · rúbrica 3.

## 04:00–05:00 | Ignacio Pastén | Lámina 5

**Las capas aportan datos y restricciones**

**Pantalla y acciones:** 04:00–04:12 PPT 5. 04:12–05:00 WEB: abrir controles M1–A4 y Cartografía y entorno; alternar dos capas, restaurarlas, abrir atributo de base/amenaza y mostrar hora del clima. No confundir capas geográficas con catálogo M1–A4.

**Texto para decir:**

Los metadatos se organizan en cuatro grupos: bases, cobertura territorial, elevación y clima. Las amenazas incluyen meteorología fuera de perfil, observaciones térmicas FIRMS, zonas aeronáuticas e historial de incendios. Mostramos estas fuentes desde el panel de capas, activando y desactivando su representación. Para los datos que no se explican mediante un polígono, abrimos sus atributos o el panel correspondiente. Esto permite conocer qué información se está utilizando y de dónde proviene. Es importante separar visibilidad y cálculo: ocultar una capa en el mapa no elimina automáticamente una restricción del modelo. El clima corresponde a un snapshot histórico, y la recurrencia de incendios representa un antecedente territorial, no una predicción de que hoy exista fuego. El foco que añadimos para demostrar detección se identifica como sintético.

Control: 60 s · 125 palabras · rúbrica 4.

## 05:00–06:00 | Ignacio Pastén | Lámina 6

**Las amenazas se convierten en probabilidades**

**Pantalla y acciones:** 05:00–05:25 PPT 6: fórmula y ejemplo marcado como hipotético. 05:25–06:00 WEB/EDITOR: Probabilidades JSON; buscar nodos, edges, by_threat y probability_pct. Puede usarse el extracto archivado, identificado como tal.

**Texto para decir:**

Cada amenaza aporta una probabilidad de falla a los nodos y enlaces que afecta. En el archivo exportado se conserva el identificador del elemento, el aporte de cada amenaza y la probabilidad combinada. La combinación utilizada es uno menos el producto de las probabilidades de no falla, bajo independencia entre objetos de amenaza. Por ejemplo, dos aportes hipotéticos de diez y veinte por ciento producirían veintiocho por ciento, no treinta. Una misma amenaza puede afectar conjuntamente varios enlaces; eso no significa sortear cada uno como si fuera independiente. Las probabilidades históricas son supuestos académicos, y la falta de información no se convierte silenciosamente en riesgo cero. Ahora descargamos Probabilidades JSON y abrimos un nodo y un enlace para comprobar que el resultado es inspeccionable y reproducible. Diego explicará cómo estos datos intervienen en los algoritmos.

Control: 60 s · 135 palabras · rúbrica 5.

## 06:00–06:45 | Diego Hidalgo | Lámina 7

**Dos costos para pgr_dijkstra**

**Pantalla y acciones:** PPT 7: señalar las dos expresiones de costo y el grafo común. El tiempo asignado incluye una pausa breve para leer la comparación.

**Texto para decir:**

Las dos primeras técnicas usan pgr_dijkstra sobre el grafo admisible. La referencia minimiza la distancia en metros. La segunda utiliza un costo que combina tiempo y riesgo: el tiempo del enlace se multiplica por uno más el peso del riesgo por su probabilidad de falla. Ambas conservan el orden serpenteante de las pasadas de cobertura y revisan las restricciones físicas y energéticas. Por eso no afirmamos que Dijkstra resuelva por sí solo todo el problema de cubrir un polígono. La diferencia principal entre estas referencias es qué costo utilizan para conectar las tareas de la misión.

Control: 45 s · 96 palabras · rúbrica 6a y 6c.

## 06:45–08:00 | Diego Hidalgo | Lámina 8

**Gurobi optimiza la secuencia de la misión**

**Pantalla y acciones:** 06:45–07:45 PPT 8: variables, objetivo y restricciones. 07:45–08:00 WEB: tarjeta Gurobi y estado del solver; no confundir ready de misión con optimal del solver. Modelo ampliado en anexo 13.

**Texto para decir:**

Gurobi trabaja sobre una red de estados de las pasadas y estaciones. La variable binaria equis indica si se toma una transición, y ve selecciona la orientación de una pasada. Las variables de orden impiden formar subcircuitos, mientras las de batería representan el consumo acumulado. El objetivo minimiza el costo de las conexiones y los servicios. Las restricciones exigen cubrir cada pasada con una orientación, conservar el flujo, salir y regresar, respetar el presupuesto total y mantener la batería dentro de sus límites. El consumo solo se reinicia cuando ocurre un cambio de batería permitido; las estaciones tienen inventario limitado. Los conectores ya consideran las exclusiones físicas y el costo de tiempo y riesgo. En la interfaz mostramos el estado del solver y, cuando corresponde, su brecha. Un resultado óptimo se refiere a esta red discretizada de conexiones, no a todas las trayectorias continuas posibles en el territorio. Tampoco se sustituye silenciosamente a Gurobi si existe un problema de licencia.

Control: 75 s · 160 palabras · rúbrica 6b.

## 08:00–09:00 | Diego Hidalgo | Lámina 9

**Recocido simulado y comparación visible**

**Pantalla y acciones:** 08:00–08:30 PPT 9. 08:30–09:00 WEB: Mostrar rutas → Comparación de las cuatro técnicas; alternar las cuatro casillas individualmente. Mantener el resultado calculado.

**Texto para decir:**

La cuarta técnica es recocido simulado. Parte de una secuencia de pasadas y genera vecinas intercambiando su orden o cambiando su orientación. Si la nueva solución mejora, se acepta; si empeora, puede aceptarse según la temperatura, lo que ayuda a salir de soluciones locales. La temperatura desciende y la búsqueda termina por el límite de iteraciones o de tiempo. La evaluación mantiene las restricciones de la misión y registra su semilla. En el selector usamos Comparación de las cuatro técnicas, porque Circuitos diferentes corresponde a otra vista. Ahora desactivamos y activamos cada ruta desde su control independiente. Si dos métodos coinciden espacialmente, eso es un resultado posible; la comparación se completa con costos, factibilidad, resiliencia y cómputo. Eduardo mostrará cómo evaluamos su respuesta ante fallas.

Control: 60 s · 125 palabras · rúbrica 6d y controles.

## 09:00–10:30 | Eduardo Escalona | Lámina 10

**Fallas reproducibles y resiliencia por técnica**

**Pantalla y acciones:** 09:00–09:15 PPT 10. 09:15–09:50 WEB: semilla 20261104; Sortear y reproducir; Solo amenazas activadas; editor con sorteos exportados. 09:50–10:30 PPT/WEB: tabla y leyendas con R/cómputo; comparar con referencia archivada sin afirmar igualdad si cambia.

**Texto para decir:**

Para decidir si una amenaza ocurre generamos un número uniforme entre cero y cien. Con nuestra convención, la amenaza se activa cuando el sorteo es menor que su probabilidad. Por ejemplo, en el registro archivado, la amenaza A4 seiscientos ochenta y cuatro tiene diez por ciento de probabilidad y obtuvo aproximadamente cero coma sesenta y cinco: queda activada. La semilla permite repetir el escenario. En pantalla mostramos el sorteo y filtramos las amenazas activadas. Para comparar técnicas congelamos sus rutas y las sometemos a los mismos mil escenarios. Definimos resiliencia como la fracción en que la misión conserva cobertura completa y retorno seguro. La tabla muestra una referencia archivada: las cuatro técnicas lograron ochocientos dieciséis éxitos y empataron en ochenta y uno coma seis por ciento. No hay un ganador único de resiliencia en ese caso. El tiempo de cómputo se presenta por separado del tiempo de vuelo, junto al nombre del algoritmo. Las mediciones que aparezcan al grabar corresponden a esa ejecución; los datos archivados sirven como referencia, no como una garantía de rendimiento. Ahora veremos una amenaza dirigida a un conector de salida.

Control: 90 s · 185 palabras · rúbrica 7 y 8.

## 10:30–11:30 | Eduardo Escalona | Lámina 11

**Una amenaza obliga a cambiar el recorrido**

**Pantalla y acciones:** 10:30–10:40 PPT 11. 10:40–11:30 WEB: quitar foco, introducir amenaza y recalcular; seleccionar Dijkstra distancia, sortear; mostrar interrupción; Replanificar evitando amenazas activadas; cobertura y retorno. Preparar dos clips encadenados, conservando la continuidad del caso; acelerar solo esperas.

**Texto para decir:**

Conservamos la misma base, el polígono y el presupuesto. Añadimos una amenaza sintética sobre un conector de salida, con quince metros de radio y ochenta por ciento de probabilidad. La semilla del ejemplo hace que se active. Primero mostramos que la misión original se interrumpe y retorna: volver de manera segura no equivale a haber completado el patrullaje. Después usamos Replanificar evitando amenazas activadas. La nueva solución debe rodear el bloqueo y mantener la cobertura del objetivo y un regreso factible. En la evidencia archivada se verificaron esas condiciones y cambiaron las coordenadas del recorrido. Al grabar confirmamos el estado y las métricas de la ejecución que vemos. Este caso muestra recuperación ante una amenaza concreta, sin convertirlo en una promesa de superioridad general de un algoritmo.

Control: 60 s · 127 palabras · rúbrica 9.

## 11:30–12:00 | Eduardo Escalona | Lámina 12

**Conclusiones y alcance**

**Pantalla y acciones:** PPT 12 durante los 30 s. Cierre limpio; no añadir nuevas funciones. Reservar los últimos segundos para terminar sin cortar la voz.

**Texto para decir:**

El proyecto integra datos geográficos, restricciones del usuario y cuatro técnicas sobre una misión comparable. La demostración muestra rutas inspeccionables, fallas reproducibles y una alternativa que conserva el objetivo. Sus límites siguen siendo académicos: probabilidades supuestas, fuentes históricas y obstáculos modelados. Entregamos código, parámetros y exportaciones para repetir el procedimiento y contrastar sus resultados. Con esto cerramos la presentación de nuestro simulador de patrullaje aéreo en Valparaíso.

Control: 30 s · 67 palabras · rúbrica Cierre.

## Ritmo de ensayo

Total narrado: 1488 palabras. Los bloques de 30 segundos requieren cerca de 140 palabras/minuto; ajustar pequeñas pausas al ensayar. Mantener el corte de cada expositor en 03:00, 06:00 y 09:00. Para ganar tiempo, recortar conectores del discurso antes de acelerar la explicación de una técnica.