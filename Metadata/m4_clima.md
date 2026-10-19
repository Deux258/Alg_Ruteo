# M4 clima

Contrato activo y tabla de campos/unidades/nulos: [Diccionario ampliado](../docs/FASE2_METADATA_TRANSITO.md#diccionario-de-salidas).

Productor: `python -m Metadata.m4_clima --run-id UUID --output RUTA --mode snapshot`.
Cargador transaccional: `python -m Metadata.m4_clima --load RUTA`. No consulta fuentes al cargar.

Autoría M1–M4: adaptación del aporte de Diego Hidalgo, conservado en aportes_metadata_diego.
