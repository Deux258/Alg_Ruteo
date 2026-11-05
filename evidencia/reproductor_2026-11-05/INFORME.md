# Circuitos distintos y reproductor — evidencia

Fecha local: 5 de noviembre de 2026. Aplicación: http://127.0.0.1:18083.

El ejemplo devuelve cuatro circuitos espacialmente distintos, con cobertura completa y autonomía validada. El selector conserva, aparte, los resultados originales de las cuatro técnicas; su coincidencia no se modifica ni se presenta como diversidad.

| Circuito | Duración (s) | Distancia (m) | Tránsito compartido máximo con anteriores |
|---|---:|---:|---:|
| Circuito 1 | 146.63 | 1242.88 | — |
| Circuito 2 | 158.35 | 1340.57 | 45.3 % |
| Circuito 3 | 169.94 | 1456.38 | 22.7 % |
| Circuito 4 | 236.16 | 2100.42 | 40.5 % |

La comparación espacial excluye el objetivo con margen de 5 m y los primeros 20 m alrededor de la base, con tolerancia de 12 m. Invertir el sentido o remuestrear la misma línea no crea otra alternativa. El barrido de vigilancia puede ser compartido. Los umbrales, restricciones y límite de búsqueda se describen en `docs/ALTERNATIVAS_REPRODUCTOR.md`.

El reproductor añade inicio desde tierra, pausa, reanudación, barra temporal, salto al final, repetición, seguimiento y vista en perspectiva desde el dron. El centrado del último objetivo funciona en 2D/3D. La edición permite deshacer/cancelar y al cambiar el objetivo se retira la simulación anterior.

Validación: 33 pruebas Python en Docker, 4 pruebas puras del reproductor y 44 comprobaciones de navegador, sin errores JavaScript. Incluye comparación por técnicas, diversidad geométrica, cobertura, detección/reporte/regreso, alternativa frente a cierre y cambio de batería. La recarga se fuerza con 130 s de batería útil y estación 104; es una restricción experimental.

- `circuitos_distintos.png`: geometrías diferentes en el ejemplo.
- `vista_dron.png`: cámara en perspectiva, desde una posición interpolada del vuelo.
- `objetivo_3d.png`: centrado del objetivo y salida de la vista del dron.
- `regresion/`: cuatro técnicas, detección y cierre con replanificación.
- `recarga/`: parada y cambio de batería en tierra.
- `movil.png`: reproductor y mapa en pantalla estrecha.

Escena geográfica: `d89e9f14df2e66166d4d20f1a273e592f5d7571f1a6904535ce72439e3b762ea`. Resultado: `6483ac2e54c684598d48f50351ee7b858d1fa1501952e260506abca1f4009044`.
Código del cálculo: `b565d6feb8e753149f24a438ea392ab65a7f11679cb429c3d6e9ed8784dc29ab`.

Los JSON grandes se conservan comprimidos. La cámara es una visualización sintética del DSM y las capas locales, no una transmisión de video. Las alturas, copas y estaciones mantienen los supuestos declarados del proyecto. Si no se encuentran cuatro circuitos viables distintos, se informa una cantidad menor en lugar de duplicar recorridos.

No se produjo video ni se publicaron commits o archivos en servicios externos.
