# Pauta para grabar la presentación final

Duración final: 12:00. Diapositivas 1–12; anexos 13–16 solo para preguntas o respaldo. El guion completo también está en las notas del PowerPoint. Cuatro voces en bloques de 3:00. El arranque se graba después de publicar manualmente el repositorio en GitLab.

## Preparación del caso y la pantalla

1. Abrir la presentación y el proyecto en ventanas separadas. Grabar pantalla a 1920 × 1080, 30 fps; texto de terminal/editor al menos 24 px. Mantener los controles que se están usando legibles al hacer el cambio a la aplicación. Cerrar notificaciones y ocultar credenciales; no abrir `.env` ni licencias.
2. Después del traslado a GitLab, abrir la página real del repositorio y seleccionar la rama de entrega. Mostrar URL y rama. En terminal, dentro de su clon local, ejecutar `git branch --show-current` y luego `./main iniciar --mode snapshot --scope completo`. No cambiar remotos ni publicar desde este material.
3. Capturar el comando completo y el estado final. Si la carga tarda varios minutos, acelerar solo esa espera, rotulada «Carga acelerada». Abrir la URL que realmente imprima el comando; no asumir que siempre será 8080 o 18083.
4. Importar `caso_demo/objetivo.geojson`. Elegir base **104**, hora **2026-10-19 00:00 UTC**, altura **60 m AGL**, viento límite **8 m/s**, batería útil **1.200 s**, misión **3.600 s**, riesgo **1**, recurrencia **1** y semilla **20261104**. Mantener las estaciones de `solicitud_base.json`: `104`, `S1H:18`, `S1H:20`, `S1H:23`, `S1H:31`. Las estaciones son virtuales. Establecer semilla y preferencias antes de calcular; cambiarlas después puede invalidar el resultado.
5. Elegir «Mostrar rutas → Comparación de las cuatro técnicas». Calcular y esperar el estado final. Conservar la solicitud y exportar el resultado **de la corrida que se grabará**. Revisar los cuatro estados, cobertura, retorno y la leyenda de resiliencia/cómputo. Una coincidencia espacial o un empate es un resultado válido.
6. Si el snapshot ya no tiene esa hora o base, usar una hora válida y un escenario compatible y guardar su nueva solicitud antes de grabar. No presentar la corrida nueva como idéntica a la archivada. Si cambian cifras, actualizar la tabla de la lámina 10 y las frases correspondientes en el guion.

## Tomas y montaje

| Tiempo de montaje | Toma | Qué debe quedar visible |
|---|---|---|
| 00:00–00:30 | PPT 1 | Título y equipo; voz Diego Muñoz |
| 00:30–00:42 | PPT 2 | Comando y flujo reproducible |
| 00:42–01:15 | Terminal/GitLab | URL, rama, comando y final de carga; espera acelerada señalada |
| 01:15–01:30 | Web | Página disponible en la URL impresa |
| 01:30–01:55 | PPT 3 | Malla, enlaces y perfil vertical |
| 01:55–02:45 | Web 3D | Centrar objetivo; acercar ruta/relieve; alternar edificios y vegetación |
| 02:45–03:00 | PPT 3 | Límite académico y transición a Ignacio |
| 03:00–03:12 | PPT 4 | Objetivo y perfil |
| 03:12–04:00 | Web | Importar objetivo; base/hora; parámetros; comparar |
| 04:00–04:12 | PPT 5 | Metadata y amenazas |
| 04:12–05:00 | Web | Capas M1–A4, checkboxes, popup/atributos y hora del clima |
| 05:00–05:25 | PPT 6 | Probabilidad por elemento y combinación |
| 05:25–06:00 | Web/editor | Descargar Probabilidades JSON; mostrar nodo, enlace y by_threat |
| 06:00–06:45 | PPT 7 | Dijkstra distancia y parámetros; voz Diego Hidalgo |
| 06:45–07:45 | PPT 8 | Variables, objetivo, restricciones de Gurobi |
| 07:45–08:00 | Web | Tarjeta Gurobi y estado del solver |
| 08:00–08:30 | PPT 9 | Vecinos, aceptación y enfriamiento |
| 08:30–09:00 | Web | Comparación original; cuatro controles on/off independientes |
| 09:00–09:15 | PPT 10 | Regla U<p; voz Eduardo Escalona |
| 09:15–09:50 | Web/editor | Semilla; sortear; filtro de amenazas activadas; registro real |
| 09:50–10:30 | PPT/web | R junto al método y cómputo; distinguir vuelo de cómputo |
| 10:30–10:40 | PPT 11 | Misma misión, amenaza y ruta alternativa |
| 10:40–11:30 | Web, clips A/B | Amenaza, interrupción, replanificación y comprobación del resultado |
| 11:30–12:00 | PPT 12 | Conclusiones y límites; cierre |

Las capturas incluidas en el PPTX son evidencia archivada, no videos de una nueva ejecución. Para mostrar funcionamiento, grabar las acciones anteriores sobre la aplicación real. Puede grabarse una toma larga y recortarla después; no eliminar del montaje las decisiones ni los resultados que justifican el criterio evaluado.

## Caso alternativo: secuencia exacta para clips A y B

Preparar y ensayar esta parte antes de la toma final. El objetivo, origen, hora, presupuesto y semilla deben conservarse a lo largo de ambos clips.

**Clip A — activar el cierre**

1. Quitar un foco sintético si se hubiera añadido. Mantener la misión del objetivo de referencia.
2. Abrir «Amenaza por coordenadas».
3. Introducir longitud y latitud: `-71.6558717239513, -33.102491411280944`.
4. Configurar radio `15` m y probabilidad `80` %. Añadir por coordenadas. Usar semilla `20261104`.
5. Recalcular con «Comparar cuatro técnicas». Seleccionar Dijkstra distancia para la reproducción.
6. Pulsar «Sortear y reproducir». Mostrar que `synthetic:0` se activó y el estado de interrupción/retorno. Un retorno seguro de una misión interrumpida no prueba cobertura completa.

**Clip B — replanificar y verificar**

7. Pulsar «Replanificar evitando amenazas activadas» (la etiqueta exacta puede ocupar dos líneas).
8. Esperar el cálculo con la misma solicitud. El cierre activado queda como exclusión conocida. Mostrar la zona y el desvío a un zoom legible.
9. Comprobar `ready`, cobertura completa y retorno factible, sin exceder batería/presupuesto. Exportar y conservar el resultado posterior.
10. Mostrar los archivos antes/después si es necesario para justificar que el objetivo y el origen se mantienen, que cambian las coordenadas y que no se atraviesa el cierre.

Este escenario fue exitoso en la evidencia archivada de 05/11/2026. El archivo `caso_demo/verificacion_archivada.json` identifica los resultados originales. Sus cuatro rutas cambian y conservan cobertura. Si un cambio de snapshot altera el conector, elegir y documentar uno que realmente interrumpa la salida, y verificar el desvío antes de grabar; no dibujar una trayectoria decorativa ni atribuirle una salida del solver.

## Preparación de las voces

- Diego Muñoz: 00:00–03:00, láminas 1–3.
- Ignacio Pastén: 03:00–06:00, láminas 4–6.
- Diego Hidalgo: 06:00–09:00, láminas 7–9.
- Eduardo Escalona: 09:00–12:00, láminas 10–12.

Narración aproximada: 1.488 palabras, entre 111 y 135 palabras/minuto según el bloque. Las acciones pueden realizarse mientras se narra. Dejar una pequeña pausa tras cada fórmula. Conservar las tres transiciones de voz en 03:00, 06:00 y 09:00. No aumentar la velocidad de lectura para compensar esperas del solver; recortar/acelerar las esperas identificadas.

## Comprobación final del montaje

- Dura 12:00; se oyen cuatro integrantes con reparto de 3:00.
- Se ve GitLab/rama, el arranque desde main y la aplicación disponible.
- El usuario introduce área y restricciones.
- Se ven capas, atributos y descarga de probabilidades.
- Las cuatro técnicas están explicadas y sus controles se manipulan por separado.
- Se ve un sorteo y se explica correctamente el umbral.
- R y cómputo se muestran por técnica; se declara un empate si existe.
- La alternativa conserva el objetivo y comprueba cobertura y regreso.
- Las cifras narradas coinciden con la pantalla o están identificadas como referencia archivada.
- El final no corta una palabra; los anexos quedan fuera del tiempo principal.
