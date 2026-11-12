# Grabación real del dron desde distintas perspectivas

Este grabador automatiza la interfaz existente y captura lo que dibuja Chrome. No utiliza imágenes del tráiler ni rutas inventadas, no publica contenido y no cambia el código del simulador. El video es silencioso, adecuado para añadir una explicación oral después.

## Ejecutar

Con la aplicación activa (`./main` si todavía no está iniciada), desde la raíz del repositorio:

```bash
./tools/grabar_demo_dron.sh
```

Prueba las direcciones locales 18083 y 8080. Para otra dirección, usar la URL que realmente haya impreso main:

```bash
./tools/grabar_demo_dron.sh --url http://127.0.0.1:18083
```

Opciones: `--chrome /ruta/chrome`, `--headed` para ver la automatización, y `--no-fire` para omitir la toma opcional de foco sintético. Se requiere Node.js, Chrome con WebGL, FFmpeg y FFprobe. Se reutiliza `puppeteer-core` del proyecto Hyperframes en `presentacion/trailer_hyperframes/node_modules`; si falta, el grabador lo comunica sin instalar nada automáticamente.

Cada ejecución crea una carpeta nueva:

```
presentacion/demo_perspectivas/renders/<fecha>/Demo_dron_perspectivas.mp4
```

Al finalizar imprime la ruta absoluta. `manifest.json` indica si terminó correctamente; si hay un error, conserva las tomas previas, solicitudes, respuestas y una captura para diagnosticarlo. El MP4 final solo se genera cuando existen las tomas nominales requeridas. No sustituye un fallo por una animación decorativa.

## Secuencia prevista

1. Encuadrar una zona desplazada respecto del ejemplo. Importar aquí solo sirve para localizar el área. Después se pulsa **Dibujar objetivo**, se marcan cinco vértices con el ratón y se pulsa **Cerrar polígono**: el video muestra la creación efectiva del objetivo utilizado para calcular.
2. Calcular la misión real para ese polígono y seleccionar una técnica con cobertura completa y estado ready. La espera de cálculo queda fuera del montaje; todas las respuestas se guardan.
3. Mostrar el recorrido calculado en 2D y el movimiento a velocidad 1×.
4. Activar **Seguir dron** en 2D.
5. Entrar al terreno 3D, centrar la misión y orbitar mediante arrastre real de la cámara.
6. Seguir al dron en 3D.
7. Activar **Vista del dron**: POV, rumbo, altura y batería.
8. Girar la cámara desde el POV.
9. Mostrar el final de la ruta y el aterrizaje a 20×, indicado en el rótulo.
10. Opcional: colocar un foco sintético en el objetivo y reproducir la secuencia de detección, reporte y regreso a 20×. Solo se incluye esta toma si el backend confirma `detected_and_returned`; de lo contrario queda fuera del montaje y el manifiesto explica la limitación.

Duración esperada: unos 2–3 minutos, variable según las tomas y la duración de la misión. El archivo usa H.264, 1920 × 1080 y 30 fps de salida. La cadencia real de captura depende del navegador y del equipo. Los rótulos son una ayuda de edición superpuesta y no se presentan como funciones de la interfaz del proyecto.

La geometría final se guarda en `zona_recorrida.geojson`, y se comprueba que sea distinta de `demo_polygon`. Si una zona resulta inviable se conservan sus datos y se prueba otro desplazamiento; no se afirma que los intentos rechazados fueran viables. Las vistas usan el modo nominal, sin sorteo de amenazas, para enseñar el vuelo y las cámaras sin interrupciones aleatorias.

## Detección de fuego: qué está implementado

Fuente: `core/patrol.py`, función `simulate`, y `Sitio Web/patrol.js`, función `updateFlightLog`.

- El usuario coloca un punto mediante **Marcar foco**, dentro del polígono. El foco es sintético y está presente desde el inicio de la simulación; no se genera un incendio nuevo a mitad del vuelo.
- Durante el recorrido se revisan muestras de los enlaces. Se detecta cuando el foco entra en el radio visual supuesto (100 m en el perfil de referencia) y hay línea de vista contra el terreno modelado.
- Se guardan la posición del foco, la del observador y la hora de detección. Se verifica primero si hay recursos para el reporte (60 s de referencia) y el regreso.
- Si alcanza, se registra el reporte completado y se calcula el regreso. Si no, se prioriza retornar y se declara el reporte incompleto. No se afirma que el patrullaje total haya terminado por haber encontrado un foco.
- La interfaz muestra «Foco detectado» y «Foco reportado. Regreso iniciado». Es una notificación dentro del simulador y su exportación, no un envío a bomberos, correo, SMS u otro servicio externo.
- Las probabilidades y la semilla actuales activan amenazas sobre la infraestructura. No existe una probabilidad independiente de aparición de incendio, ni una tasa probabilística de detección del sensor: la detección del punto colocado usa alcance y visibilidad.

La toma opcional hace visible el comportamiento que ya existe. No agrega esas probabilidades ni una integración de notificación externa.

## Estado de verificación en esta sesión

Se comprobó la sintaxis del grabador, su ayuda y las funciones de geometría, selección de ruta y composición temporal. Se contrastaron los selectores y las llamadas con el código de la aplicación. La ejecución completa no pudo probarse: el entorno bloquea el arranque de Chrome (`setsockopt: Operation not permitted`) y no dispone de conexión a un navegador del usuario. No se entrega un MP4 nuevo como si se hubiera grabado aquí. Ejecutar el comando en la terminal local permite completar la captura real; su éxito todavía requiere esa validación de extremo a extremo.

Referencia del controlador del navegador: [Puppeteer](https://pptr.dev/). El grabador utiliza CDP `Page.startScreencast` y conserva los intervalos temporales de los fotogramas para codificarlos con FFmpeg.
