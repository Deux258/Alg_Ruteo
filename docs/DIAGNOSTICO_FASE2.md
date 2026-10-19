# Adquisición verificable y diagnóstico de misiones

El incremento conserva áreas, bases, malla, tres idas × tres regresos y parámetros
del perfil. No modifica el costo ni las restricciones para aumentar factibilidad.

## Adquisición AIP

Desde Bash, con Docker disponible:

```bash
./main diagnosticar-fuentes --source S6
./main adquirir --sources S6 --reuse S1,S1H,S2,S3,S4,S5,S7
./main adquirir
./main iniciar --mode snapshot --scope completo
```

El diagnóstico no necesita una BD iniciada ni modifica el manifiesto activo. Conserva
su informe en `datos/runs/diagnosticos_fuentes/` y devuelve código 1 si falla. No declara
éxito porque funcione el snapshot. Descubre ENR 5.1 desde el índice oficial HTTPS:
https://aipchile.dgac.gob.cl/aip/vol1/seccion/enr . Cada recurso tiene tres intentos,
timeout de socket de 20 s y esperas de 1 y 3 s. Mantiene TLS verificado, redirecciones,
URL inicial/final, fecha, tamaño y SHA-256. Distingue DNS, TLS, timeout, HTTP, contenido
y parser. Una redirección a HTTP se rechaza.

Antes de activar un manifiesto candidato, el parser A3 debe validar el PDF completo
y seleccionar las zonas sobre tránsito con el margen existente. No se exige que una
descarga futura conserve exactamente dos zonas. El informe registra fechas y enmiendas
por página, y señala las páginas relevantes. Son textos del PDF, no una certificación
de vigencia operacional. Compara identificadores, igualdad topológica de geometrías y
atributos con el PDF anterior verificado. Un documento anterior corrupto impide la
comparación y activación. El índice, PDF y validación quedan conservados por hash;
`load_sources` verifica también los dos adjuntos nuevos.

La adquisición escribe primero originales con nombres por hash. Si alguna fuente
falla, escribe `adquisicion_incompleta.json` y conserva `manifest.json`. El último
intento S6 queda en `S6_ultimo_intento.json`. Reutilizar exige `--reuse`, verifica hashes
y cobertura espacial, y deja `state=reused_explicitly`; descargar deja `downloaded`
o `downloaded_validated`. Descargar no publica automáticamente una ejecución en BD.
Después de una adquisición satisfactoria se ejecuta `main` para ETL, carga y publicación.

## Contrato aditivo de diagnóstico

Las respuestas de rutas y replanificación conservan sus campos y añaden `diagnostics`:

| Campo | Significado |
|---|---|
| `primary_reason` | Motivo principal original, sin cambiar precedencia |
| `causes` | Hechos comprobados simultáneamente, con zonas AIP y extremos implicados |
| `other_causes` | Códigos distintos del motivo principal |
| `not_tested` | Comprobaciones imposibles, por ejemplo tiempo sin meteorología válida |
| `excluded_edges_by_cause` | Arcos por restricción; un arco puede contar en varias |
| `unique_excluded_edges` | Unión de arcos excluidos, sin sumarlos varias veces |
| `aip_edge_intersections` | Identificadores AIP y arcos intersectados |
| `independent_oracle` | Tiempo mínimo obtenido con Dijkstra dirigido de Python/heapq |

La comparación conserva diagnósticos de ambos métodos en `sets` y los expone también
en su objeto superior `diagnostics`. La interfaz presenta causas y zonas con texto
seguro, muestra el contraste temporal y conserva el objeto íntegro al exportar. Cambiar
los puntos, perfil o escenario invalida el diagnóstico y la exportación anterior.

El oráculo reconstruye los mismos extremos temporales y arcos admitidos, con el mismo
modelo de viento y las mismas restricciones. Calcula ida + observación + regreso para
una misión nueva, o solo el trayecto restante en regreso/emergencia; descuenta el tiempo
consumido. Admite igualdad con el presupuesto con tolerancia de 1e-9 s. Su algoritmo de
caminos no utiliza pgRouting ni sus resultados. Por diseño comparte la admisión y la
física del costo: el contraste no constituye una validación independiente de esas dos
modelizaciones. `routing_minimum_matches` contrasta mínimos cuando ambos existen.

`proposed_rejection_contradiction=true` identifica un posible defecto: el oráculo halla
una misión dentro del presupuesto pero el generador propuesto la rechaza, con extremos
permitidos y datos vigentes. Se limita a esta malla y hora; no demuestra imposibilidad
en espacio continuo ni inexistencia global de otra alternativa. Si no hay datos,
`state=not_tested` evita presentar una conclusión de inviabilidad.

`/health` mantiene compatibilidad de `mission_ready` como disponibilidad del servicio
y añade `mission_feasibility=requires_specific_request`. La salud no decide ninguna
solicitud concreta. La referencia genera por distancia y puede estar `ready` aunque
sus misiones no sean admisibles en la evaluación común.

## Repetición y evidencia

`tools/repetir_diagnostico.py` lee el `plan.json` conservado y repite sus solicitudes
exactas contra el `run_id` original. Compara estados, razones, alternativas completas,
geometrías, costos, escenarios y métricas, excluyendo únicamente el diagnóstico nuevo
y la identificación del software. No escribe evaluaciones en BD ni cambia publicación.
Conserva cada respuesta, el plan, causas por solicitud, contradicciones y hashes.

```bash
docker compose run --rm --no-deps etl python tools/repetir_diagnostico.py \
  --baseline evidencia/cierre_fase2_2026-10-19/experiment_447e0e6a023159ae \
  --output datos/runs/diagnostico_replay
docker compose run --rm --no-deps etl python tools/evidencia_diagnostico.py \
  --output datos/runs/evidencia_diagnostico
```

Los caminos de salida son relativos al contenedor para evitar conversiones de rutas
Linux por Git Bash. Los escenarios A4 de la segunda herramienta son fixtures métricos
sintéticos: política desactivada, clase permitida, clase superior y cobertura ausente.
No constituyen incendios observados. La evidencia de esta entrega se conserva en
`evidencia/diagnostico_fase2_2026-10-19/`.
