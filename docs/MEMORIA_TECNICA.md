# Memoria Técnica del Sistema de Patrullaje Aéreo Forestal (`Alg_Ruteo` / RRPP)

> **Alcance:** Simulación académica 100 % sintética para Valparaíso (Chile). Las estaciones de Bomberos (`M1`) operan como bases de despegue y recarga bajo supuesto académico.

## 1. Fuentes de Datos Verificadas del Snapshot (`datos/entrada/aereo_v2/manifest.json`)

| Capa | Fuente Oficial / Origen | Detalles Verificados |
| :--- | :--- | :--- |
| **M1** | Cuerpos de Bomberos de Valparaíso | Estaciones base de despegue y recarga (`station_inventory` efectivo por defecto = **1** en UI, JS, JSON y backend; `20` es variante experimental de simulación continua). |
| **M2** | **CONAF / CIREN** (`S2`, 2019) | Cobertura vegetacional con atributos `especi1_co`, `subuse` y `forest_type`. |
| **M3** | **Copernicus GLO-30** (`S3`, celda `S34 W072`) | Modelo digital de superficie derivado de TanDEM-X; espaciado real en UTM 19S de `~30.9 m N-S × 25.9 m E-O`; datum vertical `EGM2008`. |
| **M4** | **ECMWF IFS 0.25°** vía Open-Meteo (`S4`) | 48 registros horarios de viento a 10 m AGL (snapshot retrospectivo octubre 2026). Coordenada solicitada `(-33.078420, -71.616327)`, celda devuelta `(-33.0, -71.5)`. |
| **A1** | Viento derivado de **M4** | Perfil horario + perturbaciones estocásticas (lognormal + von Mises) y ajuste de altura por ley de potencia $1/7$. |
| **A2** | **NASA FIRMS** (`S5`) | En el snapshot real el estado es `"empty"` (**0** detecciones). Toda prueba con focos activos se rotula explícitamente como **sintética**. Se distingue siempre `"empty"` de `"unknown"`. |
| **A3** | **DGAC AIP ENR 5.1** (`S6`) | Zonas de exclusión aérea (bloqueo duro para rutas y tareas). **No** anula el riesgo de incendio $R$: marca `observable = False` (junto con áreas urbanas). |
| **A4** | **SENAPRED** (`S7`, *Amenaza por incendio forestal 2024*, densidad 2020–2024) | Clase ordinal `1–5` (26 polígonos en BD / 29 en manifest). La tabla `[1, 3, 5, 10, 20] %` es un **peso supuesto**, no una probabilidad calibrada (`a4_unknown_pct = 20.0` % por defecto). |

## 2. Coordenadas, Perfil Vertical y Aeronaves

- **Proyecciones**: Toda la geometría y cálculo métrico interno se ejecuta en **UTM 19S (`EPSG:32719`)**; la exportación GeoJSON/API entrega `[lon, lat, z_EGM2008]` en **`EPSG:4326`**.
- **Perfil vertical**: `banded-ramp-1` sobre el DSM Copernicus GLO-30 (`EGM2008`), con cinemática de segmentos en `core/vertical_profile.py` (`edge_kinematics`) y despeje mínimo configurable (por defecto `70 m` sobre el terreno modelado).
- **Aeronaves soportadas**: `DJI Mavic 3T` (default), `DJI Matrice 30T` (`263 Wh`, IP55, crucero `12 m/s`, recarga `165 min`), `DJI Matrice 350 RTK`.
- **Modelo de batería e inventario**: El inventario por defecto por estación es **`1` batería** (`station_inventory = 1`), con espera explícita de recarga (`recharge_s ≈ 9900–10800 s` según cargador/modelo). El modo de inventario `20` se conserva como variante comparativa de intercambio rápido continuo.
- **Límite de respuesta API**: `SUMMARY_LIMIT = 1 MiB` (`publish_result()` / `ResourceStore` en `core/web.py`), con carga diferida de geometrías pesadas y endpoints dedicados (`?view=summary`, `/api/aereo/patrullaje/riesgo`).

## 3. Arquitectura RRPP (*Risk-Adaptive Resilient Patrol Planning*)

El modo `mode="risk_adaptive"` (preservando intactos los 4 baselines `dijkstra_distance`, `dijkstra_weighted`, `gurobi` y `annealing` bajo `mode="grid"`) reemplaza el barrido uniforme por un pipeline en 6 módulos:

1. **Campo de riesgo de incendio $R(x,y,t)$** (`core/risk_field.py` / `RiskConfig`):
   $$R(x,y,t) = p_{A4}(x,y) \cdot F_{M2}(x,y) \cdot S(\nabla z, \vec{w}_t) \cdot U(d_{\text{urbano}}) + \text{FIRMS}_{A2}(x,y,t)$$
   - $R = 0$ únicamente fuera de `forest_zone_utm`.
   - Dentro de `A3` y áreas urbanas se preserva $R$ pero `observable = False` (`0.73 %` del riesgo inobservable a `45 m`, `0.48 %` a `90 m`, condicionado a que `forest_zone_utm` excluye el casco urbano).
2. **Perfil eólico 48 h y propagación anisotrópica** (`core/wind_profile.py` / `WindConfig`):
   - Interpolación circular de dirección eólica (convención meteorológica *desde donde sopla* convertida al vector hacia donde empuja) e interpolación lineal de magnitud sobre los 48 registros ECMWF.
   - Ajuste por altura AGL con ley de potencia $1/7$: $w(z) = w_{10}(z/10)^{1/7}$.
   - Velocidad tierra vectorizada $\vec{v}_{\text{ground}}$ y factor anisotrópico tipo Rothermel para propagación de incendio y visibilidad de columna de humo.
3. **Tareas adaptativas por Quadtree** (`core/adaptive_tasks.py` / `AdaptiveTaskConfig`):
   - Subdivisión guiada por $R(x,y,t)$ con tamaño de celda mínimo `min_cell_m >= 30.0` (resolución nativa del DSM), recorte estricto a `forest_zone_utm \ A3` y `representative_point()` fuera de `A3`.
   - Espaciado variable de franjas y prioridad inversa a la densidad de riesgo (`track_density_spearman > 0`).
4. **Optimización de latencia mínima ponderada por riesgo + CVaR** (`core/alns.py` / `LatencyConfig`):
   - Detección automática de licencia Gurobi al inicio; al detectar licencia restringida (~2000 variables), acota el MILP exacto (`gurobi_latency_route`) a instancias pequeñas ($\le 28$ tareas) y emplea **`alns_risk`** (3 operadores *destroy* × 3 *repair* adaptativos + aceptación tipo *Simulated Annealing*, `seed = 20261104`) como motor principal.
   - Función objetivo:
     $$\min \;\lambda_1 \sum_i R_i \, a_i + \lambda_2 \, N_{\text{recargas}} + \gamma \, \text{CVaR}_{95}(D)$$
     penalizando el tiempo de llegada $a_i$ ponderado por riesgo $R_i$, el número de recargas en estaciones `M1` (modelando espera cuando `station_inventory = 1`) y la cola de peor escenario $\text{CVaR}_{95}$.
5. **Simulación Monte Carlo de igniciones y evaluación robusta** (`core/ignition_sim.py`):
   - Muestreo estratificado por $R(x,y,t)$ de $N = 1000$ igniciones sintéticas reproducibles (`seed = 20261104`), propagación de detección por cono IR (`effective_view_radius_m`) y visibilidad de pluma de humo, cálculo de $E[D]$, $\text{CVaR}_{95}(D)$, curva temporal $R(T)$ e intervalos de Wilson al 95 % para supervivencia del dron.
6. **Resiliencia en vuelo: corredores $k=2$ y replanificación $< 1\text{ s}$** (`core/replan.py`):
   - `redundant_return_corridors()` mediante flujo máximo Edmonds-Karp en Python puro ($k=2$ caminos disjuntos en aristas hacia estaciones `M1`).
   - `replan_mission()` para inserción rápida de focos FIRMS sintéticos o desvío por ráfagas/amenazas en `< 1 s`.

## 4. Registro de Cambios y Parámetros Centralizados

- Los parámetros del sistema viven en `config/patrullaje.json` y en las dataclasses `RiskConfig`, `WindConfig`, `AdaptiveTaskConfig` y `LatencyConfig`.
- La trazabilidad experimental completa, tablas comparativas, ablación y análisis de sensibilidad se documentan en [`docs/INFORME_RRPP.md`](INFORME_RRPP.md).
