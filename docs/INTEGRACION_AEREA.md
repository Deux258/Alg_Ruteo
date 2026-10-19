> Versión anterior / antecedente: el contrato activo 4.0 y sus cambios están en [FASE2_METADATA_TRANSITO.md](FASE2_METADATA_TRANSITO.md).

# Integración aérea vigente

La configuración activa es `network_type=aerial_candidate`. `main` usa
`config/pipeline_aereo.json`, con I y M1-M4/A1-A4 habilitados. `config/pipeline.json`
continúa como contrato legado. El modelo y pruebas viales se conservan por separado.

Orden: adquirir S1-S7 → preparar infraestructura y contexto verificado → cargar I
→ extraer/cargar M1-M4 y A2-A4 → A1 dependiente de M4 → reconciliar conteos →
auditar topología, área y consultas aéreas → publicar atómicamente → habilitar web.
Las operaciones de adquisición y carga se ejecutan dentro de contenedores.
Un fallo mantiene la publicación anterior. La repetición del mismo snapshot,
incluido scope=completo, no duplica entidades ni sustituye sus bytes.

Los ocho módulos de Metadata/Amenazas delegan el contrato y carga común a
`core.aerial_etl`; cada uno tiene su entrada independiente y diccionario. Las
tablas tipadas del diseño anterior se usan efectivamente. No se cuentan como
fuentes distintas las variables meteorológicas ni el contexto interno derivado.

`core.aerial_data` comprueba originales, genera la malla y prepara registros.
`core.aerial_routing` incorpora extremos temporales en consultas de solo lectura,
calcula referencias y alternativas, verifica restricciones y presupuesto.
`core.web` sirve el frontend aéreo y los endpoints separados; conserva la API
vial para publicaciones viales. Las entradas de la consulta no escriben en las
tablas de snapshots ni precisan ampliar los permisos de `routing_web`.

`003_red_aerea.sql` añade el tipo de nodo y `aerial_models`; las versiones SQL 1 y
2 permanecen intactas. La imagen Linux amd64 y los requisitos Python/native se
fijan para que el host solo necesite Docker y Bash. Playwright se usa como
herramienta de prueba externa sobre la aplicación Docker, no como dependencia
del servicio web.

Los estados de salud indican disponibilidad del planificador y cargas, no la
admisibilidad de una misión concreta. Esta se evalúa en cada POST. Se distingue
`etl_complete` de la rúbrica completa (`phase2_complete=false`). Las métricas
comparativas de supervivencia, evaluación estadística y presentación grupal no
quedan acreditadas por esta ampliación.

Para ampliar el sistema, conservar el polígono original, trazabilidad, unidades,
tipos de salida, política de desconocidos y separación entre restricciones duras
y exposición. Ver [contratos aéreos](DATOS_AEREOS.md) para campos y API.
