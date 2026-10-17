# Contratos para integrar el trabajo del equipo

## Alcance disponible

SQL, topología, Docker y main están implementados para `scope=base,mode=snapshot`.
El adaptador usa los GeoJSON auténticos de fase 1 y prueba su carga completa.
No se ha implementado el ET online, M1..M4/A1..A4, k alternativas, Yen, métricas
de resiliencia ni Leaflet. Las tablas para esas funciones ya están disponibles.

## Dar de alta un ET y un cargador

Editar la entrada correspondiente de `config/pipeline.json`:

```json
{
  "key": "M1",
  "enabled": true,
  "depends_on": ["I"],
  "modes": ["snapshot", "online"],
  "extract": ["python", "-m", "Metadata.m01_bases_et", "--run-id", "{run_id}", "--output", "{output}", "--mode", "{mode}"],
  "load": ["python", "-m", "Metadata.m01_bases_cargar", "{output}"],
  "output": "metadata/bases.json",
  "dictionary": "Metadata/m01_bases.md"
}
```

El ejemplo es configuración de integración, no un módulo ya construido. Se usan
listas de argumentos; no comandos shell. Las variables permitidas son `run_id`,
`output`, `root` y `mode`. Los procesos reciben `RUN_ID` y el entorno de conexión
`DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD`; no escribir contraseñas en los scripts.
Los módulos se ejecutan desde la raíz `/app` del contenedor, con `/app` en PYTHONPATH.

El orquestador ordena las dependencias, exige un diccionario y no publica un run
completo mientras falte algún dataset. El perfil base ejecuta solamente I, incluso
si se habilitan las otras entradas, para mantener una comprobación mínima aislada.
La publicación de `scope=completo` exige los nueve datasets y conteos reconciliados.

Para integrar el ET online de infraestructura, conservar los IDs y el contrato I,
habilitar `online` en su entrada y reemplazar su comando ET. El main crea un run
staging, toma `input_hash` de la salida I validada y luego llama su cargador. El
productor debe identificar `extraction_mode=online` y conservar los originales y su
linaje. No descargar datos nuevos para luego etiquetarlos como snapshot antiguo.

## Sobre JSON, GeoJSON y diccionarios

Los JSON tienen en su raíz, y los GeoJSON en un miembro `etl`, el sobre:

| Campo | Regla |
|---|---|
| schema_version | Versión del contrato de esa salida. |
| run_id | UUID recibido por el ET; todos los archivos del mismo flujo lo conservan. |
| dataset_id | `uuid5(UUID(run_id), dataset_key)`; estable para ese run/salida. |
| dataset_key | Una de I, M1..M4, A1..A4. |
| source_id | Producto real S1..S7 según la asignación; I usa DERIVED_GRAPH. |
| observed_at / extracted_at | Fechas con zona UTC. Documentar el significado de observación, adquisición y validez. |
| lineage | URL/consulta sin secretos, originales, hashes, parámetros, cobertura, paginación y transformaciones. |

Para JSON de datos, agregar `records` u otra estructura tipada documentada.
Para GeoJSON usar coordenadas WGS84 `[lon,lat]`; el cargador transforma a 32719.
Crear un diccionario `.md` por salida con tipos, unidades, nulos y ejemplos.
JSON Schema puede complementar el diccionario; no se cuenta como otra fuente.

## Responsabilidad del cargador

Usar `core.db.connect()` y `with conn.transaction():`. Registrar primero la fila
de `routing.datasets` y luego los datos tipados, en la misma transacción. Debe:

1. Validar run, contrato y calidad; cargar solo en `staging`. Consumir el JSON,
   sin volver a llamar a la API.
2. Registrar su SHA-256 con `core.contracts.sha256(path)` y la procedencia real.
3. Usar consultas parametrizadas y UUID/IDs consistentes. No referenciar otro run.
4. Conservar nulos: elevación desconocida no equivale a cero; pronóstico caducado
   no equivale a clima seguro. Convertir campos a tipos SQL, no esconderlos todos en JSON.
5. Registrar `status=empty,record_count=0` solo si una extracción exitosa produjo
   una colección legítimamente vacía. Ante error HTTP o parser, retornar error.
6. Al repetir el mismo archivo dentro del mismo run, comparar hash y devolver éxito
   sin duplicar. Ante bytes distintos en un run ya cargado, rechazar la sustitución.

`record_count` es el número de entidades principales: I suma nodos + arcos; M1
cuenta instalaciones; M2 polígonos; M3 filas por nodo, incluyendo NoData explícito;
M4 observaciones por hora; A1..A4 cuentan filas del subtipo correspondiente. Una
amenaza ocupa una fila de `hazards` y una del subtipo: **se cuenta una vez**, no dos.

Los campos comunes de una amenaza viven en `hazards`. Insertar `kind` correcto y
después su subtipo: `weather_hazards`, `thermal_events`, `airspace_zones` o
`historical_risk`. Las FK incluyen kind, por lo que un registro térmico no puede
convertirse accidentalmente en un subtipo histórico. El historial usa
`state=historical`; no se publica como incendio activo.

No llamar `publish_run` desde un cargador. El orquestador publica después de todas
las cargas y validaciones. Un fallo deja staging/failed sin cambiar la vista vigente.

## Ruteo y frontend

`routing.graph_base_edges` contiene id, source, target, cost, reverse_cost, geom,
run_id y length_km. Cost es longitud en km; reverse_cost es -1 porque cada sentido
es una fila. `routing.edge_sql(run_uuid)` produce una consulta controlada por run,
útil para pruebas de pgRouting y algoritmos. No recibe texto SQL arbitrario.

El cálculo de dos rutas distintas y su comparación corresponde a Eduardo. La
consulta de humo de esta entrega no satisface por sí sola el criterio k>=2.
Las preferencias y amenazas deben afectar consultas propuestas separadas, nunca
la columna generada de longitud ni la vista base.

Los IDs internos pueden superar `Number.MAX_SAFE_INTEGER` de JavaScript. En la
API enviarlos como **cadenas decimales**, conservarlos como texto en formularios y
convertirlos a BIGINT validado en el backend. `core.web.safe_numbers` protege los
IDs grandes del diagnóstico. No usar `parseInt` para convertirlos en Number.
Transformar geometrías web a EPSG:4326; no publicar coordenadas UTM como GeoJSON WGS84.

Para integrar el frontend/backend de Diego Hidalgo, cambiar `web.command` en
Compose, mantener el rol de lectura y entregar `/health` con run_id, status y
alcance real. El diagnóstico actual nunca afirma `phase2_complete=true`.

## Antes de declarar la fase completa

Habilitar y probar los nueve ET/cargadores, integrar Leaflet y los algoritmos,
ejecutar main en frío y repetido en Docker, verificar casos sin ruta y completar la
matriz de rúbrica en la presentación. La estructura preparada de tablas no acredita
por sí misma adquisición de fuentes ni implementación de los módulos pendientes.
