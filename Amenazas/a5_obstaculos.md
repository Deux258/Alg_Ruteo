# A5: interferencia física

Fuente independiente de historial: S8 OpenStreetMap, compartida explícitamente con M5.
Modelo: exclusión horizontal conservadora de edificios/tendidos a 20 m y torres/antenas
a 30 m. Se comprueba todo el segmento; no se evita el filtro suponiendo alturas ausentes.

Extractor/cargador: `core.patrol_data.prepare`; entrada independiente
`python -m Amenazas.a5_obstaculos --output RUTA` o `--load RUTA`.
Salida: `datos/runs/<run>/A5.json`, contrato `patrol-dataset-1`, CRS EPSG:32719.

| Campo | Tipo/unidad | Significado |
|---|---|---|
| provider_id | texto | Identificador del obstáculo M5 de origen. |
| kind | categoría | Tipo del obstáculo original. |
| geometry | geometría métrica | Zona excluida derivada del objeto y el perfil. |
| height_m | número m o null | Altura original normalizada; no habilita sobrevuelo. |
| state | texto | excluded_2d. |

El sobre conserva hash de registros y linaje. El catálogo se carga en
`routing.patrol_datasets`; las zonas espaciales se materializan desde M5 en
`routing.flight_obstacles.exclusion`. Las consultas utilizan ambas con el mismo run.
La inexistencia de un objeto en OSM no acredita espacio libre de obstáculos.
