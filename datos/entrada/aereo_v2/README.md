# Originales activos de fase 2

Respuestas HTTP conservadas sin modificar, nombres por SHA-256 y manifiesto versionado. El manifest
activo registra ocho IDs S1–S7+S1H. S1H añade item, IDs y páginas. S3 y S6 declaran reutilización explícita
con hash del manifiesto anterior, no descarga fresca. No se copiaron JSON procesados sin procedencia
como si fueran originales. El AOI original permanece separado y sin normalizar bytes.

Regenerar dentro de Docker: `./main adquirir --sources S1,S1H,S2,S4,S5,S7 --reuse S3,S6`, luego
`./main iniciar --mode snapshot`. Un fallo conserva manifest.json y escribe adquisicion_incompleta.json.
No se supone autorización aeronáutica ni licencia más amplia que la declarada por cada proveedor.
Diccionario de fuentes/salidas y reutilización: docs/FASE2_METADATA_TRANSITO.md.
