# Mejoras de objetivo, vuelo y presentación 3D

Implementación validada: **188 pruebas Python, 30 Node y 121 comprobaciones de
navegador**. El [informe de resultados](RESULTADOS_MEJORAS_3D.md) incluye huella,
capturas, mediciones y un GeoJSON para reproducir el ejemplo de recarga.

El objetivo visual y la trayectoria física tienen funciones distintas. El
contorno objetivo se dibuja en un plano horizontal situado 30 m sobre un máximo
conservador del DSM que toca el polígono, incluyendo su interior y los triángulos
de la malla visual que lo intersectan. La ruta utiliza el
despeje elegido por el usuario sobre la envolvente de terreno y obstáculos;
el plano del objetivo no obliga al dron a volar a esa cota.

## Comportamiento y contratos

- `POST /api/aereo/patrullaje/objetivo` recibe `target_polygon` y devuelve
  `target_display`: estado `known` o `unknown_elevation`, cota
  `level_m_egm2008`, `offset_m=30` y hashes de objetivo/terreno. Esta consulta
  no ejecuta solvers ni depende de que el clima permita una misión. NoData
  impide afirmar una cota segura; no se sustituye por cero.
- El perfil vertical real emplea niveles en bandas de 10 m, rampas rectas y
  mesetas. La geometría se prepara antes de comparar las técnicas y determina
  distancias, tiempos, batería, cobertura y retorno. La simulación reproduce
  esas coordenadas canónicas; no reconstruye una altura distinta en el visor.
- El resultado identifica la base de origen por nombre e ID. El visor añade
  iconos SVG de dron, bases, estaciones, focos y amenazas; las etiquetas se
  proyectan con la cámara y se ocultan cuando quedan fuera de vista. Las rutas
  usan anchos en píxeles y flechas de dirección que conservan su legibilidad
  al acercar o alejar.
- El sombreado suaviza la iluminación mediante normales de vértices,
  conservando la paleta y la geometría de elevación. No modifica el DSM, las
  alturas de edificios, los obstáculos ni los huecos NoData del modelo físico.
- La vista 3D incorpora botones de zoom. En POV se muestran dos hélices en las
  esquinas superiores, activas durante reproducción y detenidas al pausar,
  aterrizar o cambiar batería. La información incluye latitud, longitud con
  signo y cota EGM2008, también al buscar un instante en la barra de tiempo.
- El seguimiento 2D interpola el centro en coordenadas proyectadas con
  amortiguación dependiente del tiempo. Los saltos explícitos al inicio, al
  final o a un instante elegido siguen siendo inmediatos. El dron conserva
  siempre la posición exacta de la simulación, independientemente de la cámara.

Para evitar tirones, el seguimiento compone el desplazamiento del panel de mapa
en cada fotograma y conserva un Canvas con margen. Actualiza su cobertura por
lotes al aproximarse al borde, en lugar de redibujar todas las capas en cada
movimiento. Prepara ese Canvas antes de habilitar la reproducción, sin acumular
animaciones de cámara. La interacción manual desactiva el seguimiento y restaura
la vista mediante las APIs públicas de Leaflet.

## Exportaciones compatibles

“Exportar misión” permite elegir JSON o GeoJSON. El JSON mantiene el contrato
original `{result, simulation, comparison_history}`, con geometría y grafo
completos. Las APIs resumidas continúan descargando los datos pesados únicamente
cuando se necesitan. La exportación no cambia al ocultar una ruta o filtrar una
comuna: conserva el resultado y las geometrías originales, sin recortarlas.

El GeoJSON es una `FeatureCollection` con objetivo, base identificada,
estaciones, amenazas, rutas de comparación, alternativas y, si existe, la
simulación completa como recorrido y muestras temporales. Cada muestra incluye
fase, batería, tiempo transcurrido y UTC cuando hay una hora de misión válida.
La detección conserva el foco y la posición observadora; solo un reporte
completado genera un evento de finalización. Una misión bloqueada mantiene
su diagnóstico y geometrías de ruta nulas, sin inventar un recorrido.

Las geometrías GeoJSON contienen `[longitud, latitud]` WGS84. Las cotas
ortométricas se guardan en propiedades `altitudes_m_egm2008`, alineadas con los
vértices, o `altitude_m_egm2008` para puntos. En líneas partidas por XY
desconocidas, las alturas mantienen la misma estructura de partes. NoData
permanece como `null`; una cota conocida de cero permanece como cero.

Esta separación es deliberada: la tercera coordenada de GeoJSON estándar se
define sobre el elipsoide WGS84, mientras los datos del proyecto utilizan
EGM2008. No se presenta una cota ortométrica como altura elipsoidal sin una
transformación vertical. Véase [RFC 7946, sección 4](https://www.rfc-editor.org/rfc/rfc7946.html#section-4).

## División de implementación en cuatro agentes

| Agente | Objetivo y propiedad | Entrega |
|---|---|---|
| A — Motor vertical | Modelo, perfil de seguridad y simulación canónica. | Rampas/mesetas, plano objetivo autoritativo, costos y pruebas físicas. |
| B — Render | WebGL, símbolos, proyección de etiquetas e iluminación. | Rutas en píxeles con flechas, iconos, zoom y sombreado suave sin cambiar elevaciones. |
| C — Interfaz y reproducción | Controlador, HTML/CSS e instrumentos. | Consulta de plano con protección asíncrona, coordenadas, hélices, seguimiento y selección de formato. |
| D — Exportación y aceptación | Conversor puro, pruebas de exportación y QA de integración. | GeoJSON compatible, fixtures de respuestas retrasadas y comprobación visual/funcional en Chromium. |

El integrador conecta APIs y recursos comunes. Cada archivo tiene un único
propietario; con el límite de tres subagentes activos y un integrador, el agente
D ocupa la plaza liberada por C. No hay dos agentes modificando el controlador
o el motor simultáneamente.

## Comprobaciones y evidencia

Las pruebas del modelo cubren alturas interiores, NoData, rampas y mesetas,
continuidad entre enlaces, costos y reproducción de las coordenadas canónicas.
Las pruebas Node cubren instrumentos, proyección/renderizado y exportación,
incluyendo cotas nulas, tiempo UTC, reportes incompletos e inmutabilidad de los
datos originales.

`tools/verificar_estados_ui.py` incluye la respuesta retrasada de un objetivo
anterior. `tools/verificar_mejoras_3d.py --url URL --chrome CHROMIUM --output RUTA`
comprueba el circuito real, la igualdad de coordenadas entre planificación y
reproducción, controles 3D, iconos, POV con geometría visible, hélices,
instrumentos, ambas descargas y seguimiento 2D. Genera `checks.json` y capturas,
sin video. La aceptación completa se ejecuta mediante `./main probar` en la base
desechable; su informe y huella de código determinan qué versión está acreditada.

La aceptación espera que estén cargadas todas las capas propias y el catálogo
de bases, en vez de esperar inactividad global de red: una tesela externa de OSM
pendiente no debe bloquear pruebas de una aplicación ya lista. La comprobación
de cartografía conserva la verificación de teselas OSM cargadas y del modo local.

Los resultados históricos del cierre previo no acreditan automáticamente estas
modificaciones. El video sigue fuera de alcance. Los límites académicos del DSM,
las alturas estimadas, la cobertura y las probabilidades continúan vigentes.

El caso de aceptación de recarga conserva **190 s útiles = 130 s de vuelo +
60 s de reporte** y una batería de recambio en la base 104. El perfil con rampas
hace inviable el objetivo antiguo para ese presupuesto. El fixture nuevo
traslada ese polígono **50 m al oeste en UTM 19S**, mediante la importación visible
de GeoJSON; no modifica el algoritmo, la capacidad ni la reserva para obtener
una ruta. Se comprueba cobertura, un solo recambio y finalización segura.
