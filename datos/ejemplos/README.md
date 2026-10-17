# Salida I de ejemplo

`infraestructura.json` es una copia de la salida efectivamente cargada y validada
durante la suite de integración. Conserva su run_id, IDs, linaje y 565 entidades
(85 nodos y 480 arcos); no representa una fuente o dataset adicional.

Diccionario asociado: `Infraestructura/DICCIONARIO.md`.
Esquema asociado: `Infraestructura/infraestructura.schema.json`.
Cargador asociado: `Infraestructura/cargar.py`.
Resultado de esa ejecución: `evidencia/topologia_validada.json`.

Para repetir el flujo, ejecutar main: registra el run, genera de nuevo la salida,
invoca su cargador y publica después de validar. No ejecutar el cargador aislado
en una BD sin SQL, catálogo ni fila staging del run.
