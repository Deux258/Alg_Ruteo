# Verificación de Diego Muñoz y delimitación de Valparaíso

Revisión del 17 de octubre de 2026. La base técnica funciona en Docker. Se corrigió
la delimitación para usar exactamente el GeoJSON suministrado por el usuario.

| Comprobación | Implementación original | Después de aplicar el polígono |
|---|---:|---:|
| Nodos / arcos dirigidos | 85 / 480 | 13 / 62 |
| Nodos fuera del polígono | 72 | 0 |
| Arcos no completamente cubiertos | 418 | 0 |
| Componentes fuertes / débiles | 2 / 2 | 1 / 1 |
| Bases candidatas dentro | 0 | 0 |
| Pruebas en Docker aprobadas | 46 de 46 | 54 de 54 |

El polígono es válido, usa WGS84/CRS84 y tiene **54,9207 km²** en EPSG:32719.
SHA-256: `7d3a0472f2e7fdde88d6316f89c31d6da50914e06cabb6bf8bd270ce54c905b7`.
Se conservó el archivo adjunto sin cambiar sus bytes. No se certifica como límite
administrativo oficial: se aplica como el área de estudio solicitada.

El adaptador conserva únicamente puntos y líneas completas cubiertos por el
polígono, incluyendo el borde y respetando huecos. El cargador rechaza geometrías
externas y un linaje con otro polígono. PostGIS repite la comprobación antes de
publicar. La configuración contiene la nueva envolvente para futuras consultas;
el rectángulo anterior queda identificado como legado. Los originales de fase 1
se conservaron intactos, al igual que el SQL versión 1 y sus 22 tablas.

Se ejecutaron `main probar`, `main` y su repetición, incluyendo la construcción de
las imágenes fijadas: PostgreSQL 16.9, PostGIS 3.5.2, pgRouting 3.8.0 y Python
3.12.12. No hubo fallos, errores ni pruebas omitidas. Se verificaron la carga,
transacciones, claves y extremos, costo Dijkstra por longitud, publicación,
permisos de lectura, HTTP y repetición sin duplicados. Las nuevas regresiones
incluyen polígonos cóncavos, huecos, borde y geometrías inválidas.

La ejecución final publica el run `b4d0f3af-fccb-5f0a-8731-36ba4594a94f`.
La repetición conserva ese ID y 75 entidades, con `idempotent=true`.
El diagnóstico quedó en http://127.0.0.1:18080, en el proyecto Docker aislado
`udp-ruteo-fase2-revision`. Para detenerlo sin borrar datos:

```bash
docker compose -p udp-ruteo-fase2-revision down
```

**Limitación pendiente:** recortar no equivale a reconstruir la red para toda la
nueva zona. Solo 10,6236 km² del polígono coinciden con el rectángulo previamente
consultado (19,34 %). Las ocho bases originales quedan fuera. El resultado sirve
para verificar la base técnica y rutas entre nodos de vigilancia, pero no para
demostrar una misión desde una base ni cobertura territorial completa. El equipo
debe regenerar la malla y obtener bases candidatas reales dentro del nuevo AOI.
La web informa `mission_ready=false`; el alcance completo de fase 2 sigue pendiente.

Evidencias: `pruebas_originales.json`, `pruebas_corregidas.json`,
`delimitacion_original.json`, `delimitacion_corregida.json`,
`ejecucion_inicial.json`, `ejecucion_repetida.json` y `health.json`.
Los JSON de esta carpeta son reportes de validación; sus campos de conteos,
topología, versiones, fechas, hashes y advertencias no son nuevas fuentes ETL.
El diccionario espacial está en `datos/entrada/aoi/README.md` y el del dataset
de infraestructura en `Infraestructura/DICCIONARIO.md`.
