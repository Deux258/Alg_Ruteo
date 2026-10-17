# Validación de la entrega de Diego Muñoz

## Comprobado en esta sesión

- **46 pruebas ejecutadas: 0 fallos, 0 errores y 0 omisiones.**
- Creación y reaplicación del DDL en PostgreSQL real; migraciones adicionales
  transaccionales, repetibles y protegidas por checksum.
- Carga de 85 nodos y 480 arcos; repetición sin duplicados.
- Dos componentes fuertes y débiles, de 75 y 10 nodos, sin nodos aislados.
- Geometrías en EPSG:32719, longitudes generadas en km y costos pgRouting
  reconciliados con la suma de longitudes.
- Rechazo de extremos incoherentes, cambios de nodos que invaliden arcos,
  referencias cruzadas entre runs y modificaciones de snapshots publicados.
- Un origen/destino entre componentes devuelve ausencia de camino.
- Un cargador fallido y una publicación completa incompleta conservan el run anterior.
- Usuario web de solo lectura y respuestas HTTP reales de diagnóstico.
- Preservación de BIGINT para JavaScript, sin pérdida de precisión.
- Instalación independiente de `requirements.lock` con verificación de hashes.
- Ambos archivos Compose validados mediante `config --quiet` con la CLI oficial
  Docker Compose **2.40.3+ds1-0ubuntu1~24.04.1**.
- Tags y digests de imágenes consultados en el registro de Docker.

## Motores efectivamente usados

La suite de BD se ejecutó fuera de Docker, con binarios reales sin modificar de:

- PostgreSQL 16.15, paquetes Ubuntu 24.04.
- PostGIS 3.4.2.
- pgRouting 3.6.1.

El entorno solo asigna UID 0; se utilizó fakeroot para presentar al motor un
usuario y una propiedad de archivos compatibles con su arranque. Esto afectó al
entorno local de permisos, no simuló SQL, extensiones, geometrías ni algoritmos.
El motor escuchó únicamente en loopback y se detuvo al terminar la suite.

Los resultados y logs preservados están en `pruebas_ejecutadas.json` y
`pruebas_ejecutadas.log`. Las evidencias contienen la hora UTC, versiones y
resultados reales. Los archivos `imagenes_verificadas.json` y
`compose_verificado.json` son registros de verificación, no datasets ETL.

## Pendiente de comprobar con Docker Engine

No hay Docker Engine ni socket Docker disponible en este entorno. **No se
ejecutaron builds ni contenedores Docker**, ni el job de GitLab. Las imágenes
fijadas proponen PostgreSQL 16 / PostGIS 3.5 / pgRouting 3.8.0: su combinación exacta
no fue la usada en la suite nativa. No se presenta compatibilidad binaria probada
entre esos dos conjuntos de versiones.

Para cerrar esa verificación en una máquina con Docker:

```bash
./main probar
./main
./main
./main estado
```

El test usa una BD efímera distinta de la de trabajo. Registrar la salida de
`evidencia/local/pruebas.json`, las versiones de `resumen.json`, el segundo arranque
idempotente y el healthcheck. Ante un fallo, conservar logs y corregirlo antes de
declarar ejecutada la plataforma en Docker.

## Alcance académico que no se acredita todavía

Los ocho ET de metadata/amenazas, la reconstrucción online de infraestructura,
Leaflet, k rutas, algoritmo propuesto y comparación de resiliencia no forman parte
de esta implementación acotada. No se adjudican esos puntos de la rúbrica por
tener tablas vacías preparadas. M1 y A3 siguen pendientes como entregables de fuentes.

## Referencias técnicas de implementación

- Imagen mantenida por pgRouting: https://github.com/pgRouting/docker-pgrouting
- Orden y dependencias Compose: https://docs.docker.com/compose/how-tos/startup-order/
- Triggers diferibles: https://www.postgresql.org/docs/16/sql-createtrigger.html
- Medición métrica: https://postgis.net/docs/ST_Length.html

La documentación y las pruebas locales se deben acompañar con evidencia de la
ejecución Docker del equipo en la presentación; no reemplazarla por este documento.
