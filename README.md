# Fase 2: SQL, topología, Docker y main — Diego Muñoz

Implementación de la base de integración del proyecto de vigilancia forestal.
Incluye el esquema completo de 22 tablas, imagen del modelo, carga topológica,
auditoría, contenedores y orquestador raíz. Desde la revisión del 17 de octubre,
usa el **polígono adjunto de Valparaíso (54,92 km²)** como límite obligatorio:
**13 nodos, 62 arcos dirigidos y una componente**. Conserva intacta la red de fase 1
(85 nodos y 480 arcos) y la recorta en cada extracción.

**Limitación territorial:** ninguna de las ocho bases originales cae dentro del
polígono. El recorte permite comprobar SQL, carga y Dijkstra entre nodos de
vigilancia, pero no una misión desde una base ni la cobertura del polígono completo.
El ET online de infraestructura debe regenerar la malla y obtener bases para la
nueva zona. No se inventan ubicaciones ni enlaces. Ver [revisión](evidencia/revision_2026-10-17/REVISION.md).

Esta entrega implementa el **alcance base de Diego Muñoz**. Los ocho ETL de
metadata/amenazas, las alternativas de ruteo y Leaflet se integran mediante los
contratos documentados; no se presentan como funcionalidades terminadas aquí.
`M1` y `A3` también quedan pendientes: aunque figuran como fuentes asignadas a Diego
en la distribución grupal, esta solicitud se limita a SQL, topología, Docker y main.

## Ejecutar desde cero

Requiere Docker Engine/Desktop activo y **Docker Compose v2.20 o posterior**.
En Windows usar Docker Desktop con WSL2 y abrir una terminal Bash de WSL en la
carpeta del proyecto. No se necesita instalar Python, PostGIS ni PostgreSQL en el host.

```bash
chmod +x main
./main
```

`main` genera `.env` con dos contraseñas aleatorias si no existe; no es necesario
copiar `.env.example`. Si se crea `.env` manualmente, completar los dos secretos.
No subir `.env` a Git. Para usar otro puerto, ajustar `WEB_PORT` antes de iniciar.

Al terminar:

- Sitio de diagnóstico: `http://127.0.0.1:8080`.
- Estado JSON: `http://127.0.0.1:8080/health`.
- Auditoría: `http://127.0.0.1:8080/api/topologia`.
- Resultado por ejecución: `datos/runs/<UUID>/resumen.json`, JSON y logs de cada paso.

El sitio de diagnóstico informa `application=foundation` y `phase2_complete=false`.
No reemplaza la interfaz Leaflet del equipo. No se expone el puerto PostgreSQL al host.

```bash
./main probar       # BD de prueba separada, efímera, e integración obligatoria
./main estado
./main logs
./main detener      # conserva la BD y los snapshots
```

`./main probar` produce `evidencia/local/pruebas.json` y `pruebas.log`. Para borrar
solamente los contenedores de prueba: `docker compose -f compose.test.yaml down`.
El proyecto de pruebas tiene otro nombre y usa tmpfs, sin volumen de datos persistente.
`main` nunca ejecuta `down -v` sobre la BD de trabajo.

## Qué hace main

1. Comprueba Docker/Compose y la configuración; construye la imagen Python fijada.
2. Valida el alcance solicitado **antes** de iniciar la BD. No acepta como completa
   una integración con ET/cargadores pendientes.
3. Inicia la BD y espera su healthcheck. Aplica SQL y migraciones con checksum.
4. Ejecuta cada ET y su cargador como procesos dentro del contenedor ETL.
5. Reconcilia conteos, valida topología y ejecuta una consulta real `pgr_dijkstra`
   cuyo único costo es la longitud en kilómetros.
6. Publica atómicamente el run validado. Una carga fallida conserva la publicación anterior.
7. Habilita el servicio web y comprueba `/health`. Un error retorna código distinto de cero.

El arranque normal usa `snapshot`: adapta datos auténticos ya construidos en fase 1.
**No descarga fuentes nuevas ni reconstruye la malla desde CONAF.** El ET online
de infraestructura corresponde a la integración con Ignacio. Los modos aún no
implementados fallan explícitamente:

```bash
./main iniciar --scope completo   # rechazado mientras falten M1..M4/A1..A4
./main iniciar --mode online      # rechazado hasta integrar el ET online
```

El mismo snapshot base produce el mismo run y no duplica filas. Un run explícito
se puede crear con `./main iniciar --run-id UUID`. En alcance completo futuro se
crea un run nuevo por actualización, porque la metadata dinámica puede cambiar.

## Base de datos y topología

- [Modelo en PNG](BD/diagrama.png), [SVG ampliable](BD/diagrama.svg) y [fuente DOT](BD/diagrama.dot).
- [SQL desde cero](BD/crear_bd.sql): extensiones, esquema, 22 tablas, índices, vistas,
  restricciones y funciones. Docker crea la base vacía mediante `POSTGRES_DB`.
- [Consultas de verificación](BD/consultas_verificacion.sql).
- [Migraciones](BD/migraciones/README.md): versiones aplicadas inmutables; el arranque
  no depende de scripts de `/docker-entrypoint-initdb.d` que solo corren con volumen vacío.

Las claves de datos son `(run_id,id)` y las FK compuestas impiden referenciar
nodos o enlaces de otra instantánea. Los IDs BIGINT se calculan desde claves
naturales, sin depender de la posición en el GeoJSON. Una colisión aborta la carga.
Los datos de un run listo son inmutables; rutas y evaluaciones nuevas se pueden
asociar a ese run sin cambiar la infraestructura.

Las geometrías se **transforman** de WGS84 a EPSG:32719. `length_km` es una columna
generada por PostGIS: no se importa ni se acepta un costo suministrado por el JSON.
Ambos sentidos son arcos explícitos y `reverse_cost=-1`. Los índices GiST cubren las
geometrías de infraestructura, cobertura y amenazas.

Las componentes no se conectan artificialmente. La auditoría conserva tamaños
y detecta nodos aislados, FK inválidas, extremos incoherentes y longitudes nulas.
La prueba Dijkstra incluida es una comprobación de disponibilidad y costo; **no es
la implementación de k rutas de Eduardo**.

`config/proyecto.json` referencia `datos/entrada/aoi/Zona_Delimitada_Valpo.geojson`.
Su `bbox_wgs84` es solo la envolvente para descargas: el adaptador y el cargador
comprueban el polígono completo, incluyendo bordes y respetando huecos. El hash
del GeoJSON y su geometría quedan en el linaje del dataset. PostGIS verifica
nuevamente la cobertura de los nodos y arcos cargados antes de publicar el run.
El cambio crea otro run; conserva las instantáneas publicadas anteriormente.

El rol `routing_web` solo tiene lectura y timeout de consulta; sus credenciales son
distintas de las de carga. No se recibe SQL desde formularios ni desde archivos de datos.

## Integración con el equipo

Leer [docs/INTEGRACION.md](docs/INTEGRACION.md). `config/pipeline.json` declara las
nueve salidas, sus dependencias, comandos ET, cargador, archivo de salida y diccionario.
Los ocho módulos pendientes están desactivados, sin scripts vacíos que simulen éxito.

| Módulo | Destino preparado |
|---|---|
| I | `nodes`, `edges` |
| M1 | `base_metadata` |
| M2 | `landcover` |
| M3 | `node_elevation` |
| M4 | `weather` |
| A1 | `hazards` + `weather_hazards` |
| A2 | `hazards` + `thermal_events` |
| A3 | `hazards` + `airspace_zones` |
| A4 | `hazards` + `historical_risk` |

Cada cargador debe registrar `routing.datasets` con el conteo real, fuente, SHA-256,
hora y linaje. El cargador consume el archivo guardado; no vuelve a llamar la API.
Una colección de amenazas vacía requiere una consulta exitosa documentada. Un error
HTTP o de parsing no se transforma en cero amenazas.

Los futuros cálculos propuestos usan otras consultas/vistas; `graph_base_edges` solo
depende de `edges` y `publication`, sin pesos, amenazas ni preferencias.
Para Leaflet y rutas comparadas, reemplazar la orden del servicio `web` en Compose
por el backend del equipo y conservar un `/health` que refleje su alcance real.

## Versiones y verificación efectuada

- BD Docker fijada por digest: `pgrouting/pgrouting:16-3.5-3.8.0`.
- Python Docker: `3.12.12-slim-bookworm`, también por digest.
- Dependencias Python y hashes: `requirements.lock`; entradas directas en `requirements.in`.
- Se verificó la existencia y el digest de ambas imágenes en el registro.
- Ambos Compose pasaron `config --quiet` con Docker Compose real 2.40.3.
- Pruebas SQL y de integración ejecutadas con **PostgreSQL 16.15, PostGIS 3.4.2 y
  pgRouting 3.6.1 reales**, fuera de Docker. Ver [evidencia/VALIDACION.md](evidencia/VALIDACION.md).

**Revisión local del 17 de octubre:** se ejecutaron la construcción Docker, las
pruebas con las imágenes fijadas y `main` en Docker Desktop. La evidencia nueva
está en `evidencia/revision_2026-10-17/`; las cifras anteriores describen la
validación original. El job de GitLab no se ha ejecutado como parte de esta revisión.

## Incorporar al GitLab UDP

Copiar el contenido de este paquete a una rama del proyecto del equipo. Revisar
conflictos con archivos existentes; no reemplazar el trabajo ajeno a ciegas. Ejecutar
`./main probar`, `./main` dos veces y conservar evidencia del run publicado. Versionar
código, SQL, diagrama, contratos y snapshot de entrada; excluir `.env` y salidas de ejecución.

No se realizó un push: no se recibió la URL del repositorio específico ni acceso a él.
La plataforma objetivo sigue siendo GitLab UDP; no se creó un repositorio en GitHub.

## Archivos de datos y evidencia

El [diccionario de I](Infraestructura/DICCIONARIO.md) documenta la única salida ETL
implementada y su cargador. El [diccionario de entradas](datos/entrada/fase1/README.md)
explica los GeoJSON legados y el manifiesto. Los archivos de configuración, esquemas
y evidencia no se cuentan como nuevas APIs ni como datasets de metadata/amenazas.

La fuente AIP manual y los riesgos históricos conservan sus limitaciones de fase 1;
esta entrega no los transforma en ET automatizados ni en alertas actuales.
