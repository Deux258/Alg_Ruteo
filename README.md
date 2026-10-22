# Vigilancia forestal con drones en Valparaíso

Planificador de misiones con observación y regreso, para uno a tres sectores elegidos en el mapa.
La red adapta su densidad al relieve, los obstáculos y la interfaz urbana y forestal.

## Ejecutar

El host necesita Bash y Docker Compose v2. Desde la raíz:

```bash
./main
```

Abrir [el planificador local](http://127.0.0.1:8080). Los originales nuevos están conservados;
`main` reconstruye las dos publicaciones, verifica los datos y habilita la interfaz.
La primera construcción de la red adaptativa tarda varios minutos. Repetirla sin cambios
reutiliza el run. El comando no elimina volúmenes.

Para actualizar explícitamente el pronóstico y los obstáculos:

```bash
./main vigilancia adquirir
./main vigilancia preparar
./main
```

## Uso

1. Seleccionar una instalación de referencia y marcar un punto de lanzamiento compatible con el mapa.
2. Elegir uno a tres sectores. Todos son obligatorios; el orden se calcula automáticamente.
3. Seleccionar hora UTC y, si hace falta, ajustar presupuesto, viento, cobertura o factor de ascenso.
4. Planificar o comparar Dijkstra y la propuesta. Examinar ida, observación, regreso y perfil vertical.
5. Mostrar u ocultar D1/D2/P1/P2 y descargar la solicitud, geometrías, comprobaciones y hashes.

El perfil inicial usa malla de 250/125 m, tres niveles sobre superficie, corredores comprobados
contra el DSM y obstáculos, consumo equivalente con reserva y visibilidad de cada sector.
Los supuestos del equipo, sensor, fuentes y condiciones pendientes están concentrados en el
panel técnico y en [el contrato de vigilancia](docs/VIGILANCIA.md).

## Pruebas y evidencia

```bash
./main probar
./main vigilancia evaluar --request evidencia/vigilancia_2026-10-22/solicitud_1.json
./main vigilancia evaluar --experiment config/evaluacion_vigilancia.json
```

- [Contrato, defaults, algoritmos y API](docs/VIGILANCIA.md).
- [Diagrama de las nuevas relaciones](BD/diagrama_vigilancia.svg) y [migración SQL](BD/migraciones/005_vigilancia.sql).
- [M5 Obstáculos](Metadata/m5_obstaculos.md) y [A5 Interferencia física](Amenazas/a5_obstaculos.md).
- [Evidencia y reproducción](evidencia/vigilancia_2026-10-22/INFORME.md).
- [Matriz de los 60 puntos](presentacion/MATRIZ_VIGILANCIA.md).
- [Presentación editable](presentacion/vigilancia_valparaiso_2026-10-22_final.pptx).

La versión anterior permanece en `/anterior`; sus APIs e instantáneas conservan sus contratos.
La referencia original se reproduce con 128 pruebas y 120/120 solicitudes sin diferencias.
[Documentación histórica de fase 2](docs/REFERENCIA_FASE2.md).

La publicación en Git queda a cargo del usuario.
