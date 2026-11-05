# Entorno geográfico 2D/3D — evidencia

Aplicación: http://127.0.0.1:18083. Fecha local: 4 de noviembre de 2026.

Se incorporaron edificios, agua, cobertura del suelo, árboles y curvas, además de caminos. OpenStreetMap vuelve como base 2D con una alternativa vectorial local. Los controles de capas se comparten con 3D y se exportan como GeoJSON.

| Capa | Geometrías |
|---|---:|
| Edificios | 25,148 |
| Agua | 413 |
| Cobertura del suelo | 1,153 |
| Árboles e hileras OSM | 789 |
| Calles/caminos | 7,171 |
| Curvas de superficie | 500 |

Escena: `d89e9f14df2e66166d4d20f1a273e592f5d7571f1a6904535ce72439e3b762ea`.

Validación: 27 pruebas de cartografía, patrullaje y adquisición aprobadas en Docker; 37 verificaciones de interfaz aprobadas, sin errores JavaScript. Se comprobó la misma escena para las cuatro técnicas, cobertura completa del ejemplo, detección y regreso, alternativa ante un cierre y un cambio de batería con presupuesto experimental de 130 s.

La última corrección conserva la atribución OSM en el mapa local: su comprobación independiente se guarda en `attribution_checks.json`. No modifica el cálculo de las rutas.

Capturas: `openstreetmap_capas.png`, `cartografia_local.png`, `entorno_3d_general.png`, `entorno_3d_detalle.png`, `mision_3d.png`, `regresion/alternativa_amenaza.png` y `recarga/recarga.png`.

Los JSON/GeoJSON grandes se conservan comprimidos, con sus bytes verificados. `mission.json.gz` y `regresion/` contienen las rutas y simulaciones; `entorno.geojson.gz`, las capas exportadas. Los originales OSM y el derivado de la escena están en `datos/entrada/escena/`.

Las alturas faltantes, las bases de objetos y las copas de bosque son estimaciones declaradas. Los símbolos de copas no representan un inventario individual de árboles. Las curvas de 20 m se derivan de un DSM de aproximadamente 30 m, no de un levantamiento de suelo desnudo. El mar utiliza nivel medio aproximado para visualización; no se rellenan vacíos DSM para volar.

La producción de video continúa pospuesta. Véase `docs/ENTORNO_3D.md` para fuentes, modelo y reproducción.
