# Plan de presentación final: 12 minutos, 4 integrantes

Estado: implementado en entrega/. Guion, PPTX, PDF, pauta y matriz preparados. La grabación real y la publicación manual en GitLab corresponden a la etapa siguiente. Se verificó la evidencia archivada; no se ejecutó una misión nueva durante la preparación de estos materiales.

## Objetivo

Un video académico de 12:00 que combine explicaciones con la presentación y grabaciones reales de la aplicación. Cada uno de los nueve criterios de la rúbrica adjunta debe tener una explicación y una evidencia identificable. Cuatro intervenciones continuas de 3:00 facilitan el reparto y la edición.

## Referencia visual

Referencia: /home/diego/Escritorio/Universidad/Semestre 10/Algoritmos de Ruteo/Tarea 2/Ruteo_Aereo_Valparaiso.pdf

Se revisaron las 50 páginas: proporción 16:9, portada azul oscuro, interiores claros, títulos oscuros, acentos verde petróleo, tablas con encabezados verdes, numeración y marca UDP. El PPTX nuevo reconstruirá esa apariencia con texto y tablas editables; un PDF no conserva un patrón maestro de PowerPoint reutilizable.

Se proponen 12 láminas principales y hasta 4 anexos que no entran en los 12 minutos. Los contenidos y números de fase 2 no se trasladarán automáticamente a la fase final.

## Reparto y secuencia

Orden provisional según la portada anterior; puede redistribuirse sin alterar los tiempos.

| Tiempo | Integrante | Lámina | Contenido y evidencia | Rúbrica actual |
|---|---|---|---|---|
| 00:00–00:30 | Diego Muñoz | 1 | Problema, objetivo de patrullaje y presentación del equipo | Contexto |
| 00:30–01:30 | Diego Muñoz | 2 | Repositorio y rama; ejecutar ./main; arranque acelerado identificado; web disponible | 1 |
| 01:30–03:00 | Diego Muñoz | 3 | Infraestructura, malla y terreno; altura, bloqueos y retorno; mostrar 3D y una restricción física | 2 |
| 03:00–04:00 | Ignacio Pastén | 4 | Elegir base y polígono; altura, batería, presupuesto, viento y riesgo en la interfaz | 3 |
| 04:00–05:00 | Ignacio Pastén | 5 | Metadata M1–M4 y amenazas A1–A4; activar/desactivar capas y abrir atributos | 4 |
| 05:00–06:00 | Ignacio Pastén | 6 | Probabilidad por amenaza y combinación; descargar e inspeccionar nodo/enlace del JSON | 5 |
| 06:00–06:45 | Diego Hidalgo | 7 | pgr_dijkstra en metros y ponderado por tiempo/riesgo; mismo grafo admisible | 6 |
| 06:45–08:00 | Diego Hidalgo | 8 | Gurobi: variables, objetivo y restricciones de cobertura, flujo, batería y presupuesto | 6 |
| 08:00–09:00 | Diego Hidalgo | 9 | Recocido: vecinos, aceptación, enfriamiento y parada; cuatro controles de rutas originales | 6 |
| 09:00–10:30 | Eduardo Escalona | 10 | Sorteo U en [0,100), falla si U<p; semilla; R y tiempo de cómputo por técnica; ganador o empate real | 7 y 8 |
| 10:30–11:30 | Eduardo Escalona | 11 | Caso antes/después: amenaza sobre ruta, recalcular y comprobar cobertura, factibilidad y regreso | 9 |
| 11:30–12:00 | Eduardo Escalona | 12 | Conclusiones, alcance académico y cómo repetir el caso | Cierre |

## Fases de trabajo

1. Verificar el escenario de demostración. Elegir una misión reproducible, fijar polígono, base, hora, perfil y semilla. Comprobar los cuatro métodos, descargas, leyendas y un caso alternativo viable. Guardar solicitud y resultados de esa ejecución. Las rutas o métricas que coincidan se explicarán como coincidencia o empate. La diferencia de ruta más importante para el criterio 9 es la del caso antes/después de la amenaza.
2. Crear una matriz de cobertura de los nueve criterios de la imagen: lámina, frase, acción de interfaz, evidencia y duración. La numeración de la matriz histórica del repositorio es distinta y no se usará como rúbrica final.
3. Redactar el guion completo para cuatro voces: texto natural, tiempos parciales, transiciones, acciones y marcas de pantalla como [PPT], [TERMINAL], [WEB] y [PAUSA]. Apuntar a unas 1.300–1.450 palabras totales, ajustadas con ensayo real para dejar tiempo a las acciones visibles.
4. Crear el PPTX editable siguiendo el PDF de referencia. Usar poco texto en pantalla, capturas legibles y el desarrollo oral en las notas. Mantener la relación entre algoritmo, costo, restricciones y resultados del caso real. Llevar SQL completo, modelo ampliado, JSON y fuentes a los anexos.
5. Preparar una pauta de grabación: orden de clics, encuadre, nombres de archivos y segundos asignados. Grabar segmentos de terminal y aplicación; volver a la diapositiva correspondiente para la explicación. Acelerar esperas de instalación/cálculo con indicación visible; conservar el comando, el estado final y las decisiones del usuario.
6. Ensayar y verificar: sumar 720 segundos, revisar participación equilibrada, comprobar legibilidad del PPTX renderizado y contrastar cada cifra con la misión elegida. Hacer una última revisión criterio por criterio sobre el video previsto. Se entregan materiales locales; no se publica el video.

## Evidencia esencial de la demostración

- Repositorio/rama visibles, comando de arranque real y aplicación abierta.
- Objetivo y perfil introducidos por el usuario.
- Capas activadas/desactivadas y un popup o panel de atributos.
- Probabilidades descargadas con aportes de amenazas a nodos y enlaces.
- Cuatro técnicas originales activables por separado, con tiempos y resiliencia.
- Sorteo reproducible y resultado visible de una falla o no falla.
- Una alternativa tras una amenaza manteniendo el objetivo y verificando regreso; si el caso elegido es inviable, buscar otro caso documentado para cumplir la demostración solicitada, conservando y declarando el escenario de prueba.

## Dependencias antes de grabar

- Confirmar la URL y rama de GitLab que pide la rúbrica. El remoto local inspeccionado apunta a GitHub; eso no acredita una entrega en GitLab. Publicar o mover el repositorio sería una acción separada.
- Confirmar o redistribuir los nombres del reparto; se tomaron de la portada anterior.
- Las cifras finales y la recomendación se fijarán después de verificar el caso que se grabará. No se inventará un ganador ni se usarán estadísticas antiguas como si correspondieran a esta ejecución.

## Entregables previstos

- Guion completo cronometrado para los cuatro integrantes.
- Presentación PPTX editable con notas por lámina.
- PDF de respaldo de la presentación.
- Pauta de grabación con acciones concretas y tiempos.
- Matriz de correspondencia con los nueve criterios.

No se crea todavía el video final en esta etapa de planificación.
