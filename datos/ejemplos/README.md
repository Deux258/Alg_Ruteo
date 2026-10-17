# Salida I de ejemplo

`infraestructura.json` es una copia de la salida efectivamente cargada y validada
durante la revisión Docker del 17 de octubre. Conserva su run_id, IDs, linaje y
75 entidades (13 nodos y 62 arcos), recortadas al polígono aportado por el usuario;
no representa una fuente o dataset adicional. No contiene bases candidatas.

Diccionario asociado: `Infraestructura/DICCIONARIO.md`.
Esquema asociado: `Infraestructura/infraestructura.schema.json`.
Cargador asociado: `Infraestructura/cargar.py`.
Resultado de esa ejecución: `evidencia/revision_2026-10-17/ejecucion_inicial.json`.

Para repetir el flujo, ejecutar main: registra el run, genera de nuevo la salida,
invoca su cargador y publica después de validar. No ejecutar el cargador aislado
en una BD sin SQL, catálogo ni fila staging del run.
