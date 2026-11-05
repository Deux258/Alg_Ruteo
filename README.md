# Patrullaje aéreo de drones en Valparaíso · fase final

Simulador académico con PostgreSQL/PostGIS, pgRouting, Gurobi, recocido simulado y
mapas 2D/3D locales. Planifica un barrido poligonal, compara cuatro técnicas y
simula detección de fuego, fallas y retorno con batería limitada.

## Ejecutar

Con Docker activo, desde Git Bash o WSL:

```bash
./main
```

Abrir http://127.0.0.1:8080. La instancia aislada utilizada para comprobar esta
fase está en http://127.0.0.1:18083, proyecto Compose `udp-ruteo-final`.
`./main detener` conserva los volúmenes. Los snapshots anteriores permanecen
identificados por su run; no se reemplaza una publicación hasta terminar las cargas.

## Flujo principal

1. Elegir base, hora UTC y un polígono dibujado o importado como GeoJSON.
2. Ajustar altura AGL, viento, batería, presupuesto, riesgo y estaciones virtuales.
3. Comparar Dijkstra por metros, Dijkstra con parámetros, Gurobi y recocido.
4. Activar las cuatro rutas por separado y revisar cobertura, resiliencia y cómputo.
5. Sortear amenazas con semilla, filtrar las activadas y replanificar.
6. Marcar un foco sintético y reproducir detección, reporte y regreso.
7. Ver edificios, agua, cobertura, árboles y curvas en 3D; exportar misión y capas.

OpenStreetMap vuelve como mapa base 2D, con calles y nombres. El panel **Cartografía
y entorno** permite alternar al mapa vectorial local y controlar seis capas tanto
en 2D como en 3D. Edificios y vegetación también afectan altura de vuelo y visibilidad.
Las fuentes y alturas estimadas se detallan en [Entorno 3D](docs/ENTORNO_3D.md).

La red usa malla de 100 m y enlaces de hasta 200 m. El DSM y los obstáculos se
muestrean dentro de los tramos; la altura inicial es 60 m sobre la superficie modelada.
La cobertura es una evaluación por celdas
de 30 m con alcance horizontal supuesto de 100 m y línea de vista.

El perfil Mavic 3T conserva parámetros conservadores del proyecto: 10 m/s, 25 min,
reserva 20 % y 1.200 s útiles por batería. Las estaciones son escenarios de cambio
de batería, una batería por estación y 120 s de servicio. No se acredita que los
cuarteles tengan cargadores. Los datos meteorológicos son snapshots históricos.

## Reproducción y pruebas

```bash
./main probar
./main patrullar --request datos/runs/solicitud_poligono.json
./main patrullar --experiment config/evaluacion_patrullaje.json
```

El lote fija seis casos antes del cálculo y conserva también los rechazados.
Las rutas se congelan antes de 1.000 escenarios compartidos por las cuatro técnicas.
Se guarda el aporte de cada amenaza a nodos/enlaces, todos los sorteos, semillas,
perfil y hashes. Las probabilidades A4 y las estaciones son supuestos académicos;
la falta de cobertura histórica se identifica y usa un supuesto explícito del 20 %.

Gurobi 13.0.3 se instala desde un wheel con hash fijo. La licencia limitada de pip
permite modelos pequeños. Para usar una licencia académica propia, definir
`GUROBI_LICENSE_PATH` y añadir `compose.gurobi.yaml` al comando Compose. No guardar
licencias ni credenciales en Git. Un error de licencia se muestra, sin sustituir el solver.

## Documentación y evidencia

- [Modelo matemático, API, supuestos y reproducción](docs/FASE_FINAL.md).
- [Matriz de la nueva rúbrica y guion](presentacion/MATRIZ_FASE_FINAL.md).
- [Evidencia de la fase final](evidencia/final_2026-11-04/).
- [Contratos y fuentes de fase 2](docs/FASE2_METADATA_TRANSITO.md).
- [SQL inicial y migraciones](BD/crear_bd.sql).

La página `/fase2` conserva las consultas puntuales Dijkstra/Yen y sus endpoints.
La nueva entrada principal es `/`; no se trasladan sus métricas antiguas a las
misiones poligonales. Se informa cuando hay empate, menos alternativas o falta de
factibilidad. El video queda pospuesto por indicación del usuario. GitHub y Canvas
requieren la publicación del equipo.
