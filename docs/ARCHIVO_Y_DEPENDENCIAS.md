# Conservación, archivo y dependencias

Se conserva `/fase2`, ruteo vial, sus APIs, SQL/migraciones, originales, manifiestos,
atribuciones y pruebas. No se elimina un módulo por antigüedad.

| Material | Estado y procedencia |
|---|---|
| `evidencia/*2026-10-17*`, `*2026-10-19*` | Archivo académico de red vial/fase 2, versiones y hashes en sus manifiestos. No acredita el código actual. |
| `evidencia/final_2026-11-04`, `entorno_3d_2026-11-04`, `reproductor_2026-11-05` | Evidencia histórica de patrullaje, cartografía y reproductor; conservar, fuera del runtime. |
| `presentacion/` | Entregas y material expositivo conservados; excluido del contenedor. |
| `aportes_metadata_diego/datos/` | Resultados generados del aporte original; conservados fuera del runtime. |
| `tools/figuras_fase2.py`, `evidencia_fase2.py`, `evidencia_cierre.py` | Generadores históricos identificados por fase; conservan sus nombres/referencias para reproducción. |
| `tests/fixtures/a3_v1.json` | Copia exacta del fixture antes alojado en evidencia; las pruebas ya no dependen de material histórico del contenedor. |

El archivo es lógico: se preservan las rutas referenciadas por entregas previas.
`.dockerignore` separa ese material del despliegue, sin perder el historial académico.

## Almacén de originales idénticos

`config/asset_aliases.json` mantiene los nombres originales y sus SHA-256.
`core/assets.py` resuelve esos nombres hacia `datos/entrada/blobs/<sha256>` y
verifica integridad. Los manifiestos originales no cambian. El DSM repetido y el
mapa histórico idéntico tienen una única copia física cada uno; los lectores
activos se migran antes de retirar duplicados. Las pruebas verifican los alias
y rechazan archivos corruptos o nombres desconocidos. No se deduplica por nombre
ni por similitud, únicamente por igualdad de bytes.

## Inventario de dependencias

| Grupo | Archivo fijado | Uso |
|---|---|---|
| Base | `requirements.lock` | PostgreSQL/SQL, validación, geometría y ETL. |
| Geográfico | `requirements.aerial.lock` | DSM/CRS, fuentes aéreas y productor BCN (`pyshp`). |
| Optimización | `requirements.patrol.lock` | Gurobi 13.0.3; licencia/capacidad se comprueban en el modelo de entrega. |
| QA | `requirements.test.lock` | Playwright y dependencias; solo target Docker `test`. |
| Navegador | `Sitio Web/vendor/` | Bibliotecas locales, créditos/licencias conservados. |
| Node | Docker `node:24.21.0-bookworm-slim` con digest | Ejecuta pruebas JS; no se incluye en la imagen de producción. |
| Sistema | `docker/packages/manifest.json` | Paquete oficial Debian de libexpat1, conservado y comprobado por SHA-256 antes de instalar. |

Los paquetes usan hashes de wheel y las imágenes base usan digest. No se retira
una dependencia transitiva porque no tenga un import directo: `pip check` y la
regresión se ejecutan dentro del entorno fijado. Las licencias y secretos quedan
fuera del repositorio y del contexto Docker.

El paquete libexpat1 se conserva porque APT retiró del índice la versión
anteriormente fijada. La construcción ya no depende de que el índice siga
publicando ese archivo. El manifiesto registra versión, origen y licencia;
el paquete Debian mantiene los avisos de copyright del proveedor.
