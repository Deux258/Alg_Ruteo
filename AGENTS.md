# Reglas y Hechos Verificados del Workspace (`Alg_Ruteo` / RRPP)

## Hechos Verificados del Snapshot
- **A4**: proviene de **SENAPRED** (`S7`, *Amenaza por incendio forestal 2024*, densidad 2020–2024), **no** de CONAF. Es una clase ordinal 1–5 (26 polígonos en BD / 29 en manifest); la tabla `[1, 3, 5, 10, 20] %` es un **peso supuesto**, no una probabilidad calibrada (`a4_unknown_pct = 20.0`).
- **M2**: **CONAF / CIREN** (`S2`, 2019), con `especi1_co`, `subuse` y `forest_type`.
- **M3**: **Copernicus GLO-30** (`S3`, celda `S34 W072`), derivado de TanDEM-X; `~30.9 m N-S × 25.9 m E-O`; datum `EGM2008`.
- **M4**: **ECMWF IFS 0.25°** vía Open-Meteo (celda devuelta `(-33.0, -71.5)`, coordenada solicitada `(-33.0784, -71.6163)`), 48 registros horarios a 10 m, snapshot retrospectivo octubre 2026.
- **A2**: **NASA FIRMS** (`empty` en el snapshot real = 0 detecciones). Toda prueba con focos FIRMS debe rotularse explícitamente como sintética. Distinguir siempre `"empty"` de `"unknown"`.
- **A3**: DGAC AIP ENR 5.1; **no** anula $R$, sino que marca `observable = False` (junto con áreas urbanas). $R = 0$ solo fuera de `forest_zone_utm`.
- **`station_inventory`**: valor efectivo por defecto = **`1`** en UI, JS, JSON y backend (`20` es opción de simulación continua).
- **Alcance**: 100 % simulación académica; las estaciones M1 de Bomberos son un supuesto académico.

## Restricciones Duras de Ingeniería
1. Conservar intactos los 4 baselines (`dijkstra_distance`, `dijkstra_weighted`, `gurobi`, `annealing`) bajo comportamiento por defecto; activar RRPP mediante `mode="risk_adaptive"`.
2. Geometría interna en `EPSG:32719`; exportar `[lon, lat, z_EGM2008]` en `EPSG:4326`.
3. Respetar bloqueo duro A3, exclusión urbana (`forest_zone_utm`), modelo `mu_drain` y límite `SUMMARY_LIMIT = 1 MiB` (`publish_result()` / `ResourceStore`).
4. Toda aleatoriedad con `seed` explícita (`20261104`).
5. Parámetros centralizados en `config/patrullaje.json` y dataclasses (`RiskConfig`, `WindConfig`, `AdaptiveTaskConfig`, `LatencyConfig`).
6. Detectar licencia de Gurobi al inicio; si es restringida (~2000 vars), acotar MILP y usar `alns_risk` como motor principal.
