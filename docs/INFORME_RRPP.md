# Informe Final: Rediseño RRPP (*Risk-Adaptive Resilient Patrol Planning*)

**Rama:** `feature/rrpp` · **Protocolo congelado SHA-256:** `0e60b5f32c8aa99274a38b779188905404351030ec10afd4844c93735ddfab63` · **Run ID BD:** `b80f9b83-cad7-53b8-a8b8-34a2a17e614c` · **Semilla:** `20261104`

> **Alcance académico:** Simulación 100 % académica para Valparaíso. Las estaciones de Bomberos (`M1`) y los focos activos sintéticos (`A2` en pruebas) son supuestos de simulación.

---

## (a) Resumen Ejecutivo por Etapas

1. **Etapa 1 — Reconocimiento, Regresión de Baselines y Campo de Riesgo $R(x,y,t)$** (`e2bc38c`):
   - Congelación de los 4 baselines (`dijkstra_distance`, `dijkstra_weighted`, `gurobi`, `annealing`) bajo `mode="grid"` con semilla `20261104`.
   - Implementación de `core/risk_field.py` (`RiskConfig`, `RiskField`, `compute_risk_field`) separando riesgo de incendio $R(x,y,t)$ de riesgo/restricción para el dron (`observable = False` en `A3` y área urbana, $R=0$ solo fuera de `forest_zone_utm`).
   - Corrección de procedencia: **A4 = SENAPRED** (`S7`, densidad 2020–2024, pesos supuestos `[1,3,5,10,20]%`, `a4_unknown_pct = 20.0%`), **M2 = CONAF/CIREN** (`S2`, 2019), **M3 = Copernicus GLO-30** (`S3`, `~30.9 m N-S × 25.9 m E-O`, `EGM2008`), **A2 = NASA FIRMS** (`"empty"` en snapshot real = 0 focos).
   - Diagnóstico Valparaíso (`45 m`, `27 543` celdas): correlación de Spearman con $R$ dominada por interfaz urbano-forestal $U = 0.7108$, seguida de $p_{A4} = 0.5890$, $F_{M2} = 0.3262$ y $S = -0.0197$; concentración de riesgo (norma `max`): top 5 % = `45.73 %`, top 10 % = `63.82 %`; riesgo inobservable = `0.73 %` (`0.48 %` a `90 m`).
2. **Etapa 2 — Perfil Eólico 48 h ECMWF y Propagación Anisotrópica** (`7856a96`):
   - `core/wind_profile.py` (`WindConfig`, `WindProfile`): interpolación circular/linear de 48 h (`ECMWF IFS 0.25°`, celda `(-33.0, -71.5)` para `(-33.078420, -71.616327)`), ley de potencia $1/7$ por altura AGL, factor elíptico tipo Rothermel y perturbaciones lognormal + von Mises.
3. **Etapa 3 — Tareas Adaptativas por Quadtree** (`6f87999`):
   - `core/adaptive_tasks.py` (`AdaptiveTaskConfig`, `build_adaptive_tasks`): subdivisión guiada por $R$ con `min_cell_m >= 30.0`, recorte estricto a `forest_zone_utm \ A3`, espaciado variable de franjas y compatibilidad con `oriented_tasks()` / `fixed_route()`.
4. **Etapa 4 — Optimización ALNS de Latencia Ponderada por Riesgo** (`f2e8c7f`):
   - `core/alns.py` (`LatencyConfig`, `detect_gurobi_license`, `alns_risk`, `gurobi_latency_route`) e integración en `core/patrol.py` bajo `mode="risk_adaptive"`.
   - Detección automática de licencia Gurobi restringida (`tier='restricted'`, tope `28` tareas) y uso de `alns_risk` (3 destroy × 3 repair adaptativos + SA) como motor principal.
5. **Etapa 5 — Simulación Monte Carlo de Igniciones y Comparativa Experimental** (`9152443`):
   - `experiments/protocolo_congelado.json` congelado previo a la ejecución (`n_ignitions = 1000`, `station_inventory` ∈ `{1, 20}`).
   - `core/ignition_sim.py` (`sample_ignitions`, `evaluate_route_robustness`, `wilson_ci95`, `run_compare_cli`), exportando `results/comparison.csv`, `results/comparison_summary.json` y `evidencia/fase5_risk_curve.png`.
6. **Etapa 6 — Corredores Redundantes $k=2$ y Replanificación $< 1\text{ s}$** (`ef6ae88`):
   - `core/replan.py`: `redundant_return_corridors()` (Edmonds-Karp en Python puro, sin dependencia externa de `networkx`) y `replan_mission()` para focos sintéticos FIRMS o ráfagas en `< 1 s`.
7. **Etapa 7 — UI, Documentación e Informe Final**:
   - Selector de modo (`grid` vs `risk_adaptive`) y criterio `alns_risk` en `Sitio Web/patrol.html` y `Sitio Web/patrol.js`, actualización de `AGENTS.md`, `docs/MEMORIA_TECNICA.md` y este informe.

---

## (b) Archivos Creados y Modificados

- **Creados (core & experimentos):** `core/risk_field.py`, `core/wind_profile.py`, `core/adaptive_tasks.py`, `core/alns.py`, `core/ignition_sim.py`, `core/replan.py`, `experiments/protocolo_congelado.json`, `tools/render_risk_field_png.py`, `tools/render_diagnostic_2x3.py`, `tools/run_ablation_sensitivity.py`.
- **Creados (tests, resultados, evidencia, docs):** `tests/fixtures/baseline_regression_expected.json`, `tests/test_baseline_regression.py`, `tests/test_risk_field.py`, `tests/test_wind_profile.py`, `tests/test_adaptive_tasks.py`, `tests/test_alns_latency.py`, `tests/test_ignition_sim.py`, `tests/test_replan.py`, `results/comparison.csv`, `results/comparison_summary.json`, `results/ablation.csv`, `results/sensitivity.csv`, `evidencia/fase1a_R_valparaiso.png`, `evidencia/fase1a_diagnostico_2x3.png`, `evidencia/fase5_risk_curve.png`, `docs/DECISIONES.md`, `docs/MEMORIA_TECNICA.md`, `docs/INFORME_RRPP.md`, `AGENTS.md`.
- **Modificados:** `core/patrol.py` (hook `mode="risk_adaptive"`), `core/web.py` (endpoint `/api/aereo/patrullaje/riesgo`), `Sitio Web/patrol.html` (`#patrol-mode`), `Sitio Web/patrol.js` (etiqueta SENAPRED, capa `Campo de riesgo R(x,y,t)`, criterio `alns_risk`).

---

## (c) Resultados de la Suite de Pruebas (`unittest`, tras edición final de código)

Ejecución verificada en `udp-ruteo-fase2-web-1` (`Ran 19 tests in 20.379s — OK`, **0 fallos, 0 omitidos**):

| Módulo | Test | Estado |
| :--- | :--- | :--- |
| `tests.test_baseline_regression` | `test_four_baselines_frozen_with_fixed_seed` | OK |
| `tests.test_risk_field` | `test_a3_unobservable_preserves_risk_and_non_forest_is_zero` | OK |
| `tests.test_risk_field` | `test_a4_unknown_pct_sensitivity_5_10_20` | OK |
| `tests.test_risk_field` | `test_config_min_cell_respects_dsm_resolution` | OK |
| `tests.test_risk_field` | `test_firms_empty_vs_unknown_and_synthetic_hotspot` | OK |
| `tests.test_risk_field` | `test_fuel_coefficient_hierarchy` | OK |
| `tests.test_risk_field` | `test_wind_convention_from_direction_and_upslope_risk` | OK |
| `tests.test_wind_profile` | `test_circular_interpolation_and_uniform_baseline` | OK |
| `tests.test_wind_profile` | `test_headwind_vs_tailwind_edge_travel_time` | OK |
| `tests.test_wind_profile` | `test_power_law_agl_monotonic_with_altitude` | OK |
| `tests.test_wind_profile` | `test_rothermel_anisotropic_monotonicity` | OK |
| `tests.test_wind_profile` | `test_wind_perturbation_reproducible_and_smoke_plume` | OK |
| `tests.test_adaptive_tasks` | `test_quadtree_coverage_a3_exclusion_and_density_spearman` | OK |
| `tests.test_alns_latency` | `test_license_detection_and_alns_vs_gurobi_gap` | OK |
| `tests.test_alns_latency` | `test_patrol_calculate_risk_adaptive_mode` | OK |
| `tests.test_alns_latency` | `test_station_inventory_1_triggers_recharge_wait` | OK |
| `tests.test_ignition_sim` | `test_wilson_ci_and_reproducible_ignitions` | OK |
| `tests.test_replan` | `test_mid_mission_synthetic_firms_and_wind_gust_under_1s` | OK |
| `tests.test_replan` | `test_redundant_k2_return_corridors_on_graph` | OK |

---

## (d) Comparativa Experimental (`results/comparison.csv`, $N=1000$ igniciones)

| `inv` | Método | $E[D]$ (s) | $\text{CVaR}_{95}$ (s) | Detectadas (%) | Riesgo $T \le 15'$ (%) | Recargas | Energía (Wh) | Tiempo vuelo (s) | Cómputo (s) |
| :---: | :--- | ---: | ---: | ---: | ---: | :---: | ---: | ---: | ---: |
| 1 | `dijkstra_distance` | 13854.33 | 14400.0 | 3.8 | 54.97 | 0 | 10.20 | 158.95 | 0.6766 |
| 1 | `dijkstra_weighted` | 13854.33 | 14400.0 | 3.8 | 54.97 | 0 | 10.20 | 158.95 | 0.7665 |
| 1 | `gurobi` | 13854.15 | 14400.0 | 3.8 | 54.97 | 0 | 10.24 | 159.61 | 0.6429 |
| 1 | `annealing` | 13854.33 | 14400.0 | 3.8 | 54.97 | 0 | 10.20 | 158.95 | 0.7635 |
| **1** | **`alns_risk`** | **12388.81** | **14400.0** | **14.1** | **56.97** | **0** | **38.44** | **599.06** | **6.0269** |
| 20 | `dijkstra_distance` | 13854.33 | 14400.0 | 3.8 | 54.97 | 0 | 10.20 | 158.95 | 0.6067 |
| 20 | `dijkstra_weighted` | 13854.33 | 14400.0 | 3.8 | 54.97 | 0 | 10.20 | 158.95 | 0.7758 |
| 20 | `gurobi` | 13854.33 | 14400.0 | 3.8 | 54.97 | 0 | 10.20 | 158.95 | 0.7691 |
| 20 | `annealing` | 13854.33 | 14400.0 | 3.8 | 54.97 | 0 | 10.20 | 158.95 | 0.7687 |
| **20** | **`alns_risk`** | **12388.81** | **14400.0** | **14.1** | **56.97** | **0** | **38.44** | **599.06** | **6.0992** |

- **Lectura honesta:** `alns_risk` reduce el retraso esperado de detección en **1465.5 s** (`-10.6 %` respecto a la penalización máxima de 4 h) y multiplica por **3.71×** la fracción de igniciones detectadas (`14.1 %` vs `3.8 %`), a costa de mayor recorrido (`5281.46 m` vs `1266.07 m`, `38.44 Wh` vs `10.20 Wh`) y mayor tiempo de cómputo (`~6.0 s` vs `~0.7 s`). En todas las corridas, `drone_survival_pct = 84.0 %` (`IC Wilson 95 %: [81.6, 86.14]`).
- **Invarianza `inv = 1` vs `20` en el polígono demo:** El sector de prueba (`~1.2 km²`) se cubre dentro de una sola batería (`38.44 Wh < 77 Wh`, `0` recargas), por lo que ambas variantes coinciden; el impacto de `inv = 1` (espera de recarga) se manifiesta en misiones multi-batería (verificado explícitamente en `test_station_inventory_1_triggers_recharge_wait`).
- **Resultado desfavorable en $\text{CVaR}_{95}$:** Al ser la tasa de detección en un solo barrido $\le 14.1\ \%$, el 5 % superior de los escenarios corresponde íntegramente a igniciones no detectadas (`14400.0 s`), igualando $\text{CVaR}_{95}$ entre métodos.

---

## (e) Ablación y Análisis de Sensibilidad (`results/ablation.csv`, `results/sensitivity.csv`)

### Ablación Incremental (5 pasos, `station_inventory = 1`)

| Paso | $E[D]$ (s) | Detectadas (%) | Riesgo $T \le 15'$ (%) | Energía (Wh) | Tiempo (s) |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `1_grid_uniform` | 13854.33 | 3.8 | 54.97 | 10.20 | 158.95 |
| `2_adaptive_tasks_nn` | 12871.64 | 10.7 | 55.05 | 33.31 | 519.19 |
| `3_adaptive_plus_alns_latency` | 12871.64 | 10.7 | 55.05 | 33.31 | 519.19 |
| `4_adaptive_plus_alns_plus_ecmwf_wind` | 12758.23 | 11.5 | 57.38 | 34.49 | 537.44 |
| `5_adaptive_plus_alns_wind_discounted` | 12758.23 | 11.5 | 57.38 | 34.49 | 537.44 |

- El mayor salto proviene de sustituir la grilla uniforme por tareas adaptativas por quadtree (`-982.69 s` en $E[D]$, `+6.9 pp` en detección); la incorporación del perfil eólico ECMWF de 48 h aporta un beneficio adicional (`-113.41 s`, `+0.8 pp` en detección, `+2.33 pp` en riesgo cubierto a 15 min). En el grafo real `CorridorGraph` (`calculate()`), `alns_risk` alcanza `12388.81 s` (`14.1 %`).

### Sensibilidad (8 parámetros, 24 corridas)

- **Parámetros sensibles en el sector:**
  - `urban_decay_m` (`150 → 300 → 600 m`): $E[D]$ varía de `12800.25 s` (`11.2 %`) a `12758.23 s` (`11.5 %`) y `12715.35 s` (`11.8 %`).
  - `beta2_wind` (`0.04 → 0.08 → 0.16`): $E[D]$ pasa por `12658.68 s` (`12.2 %`), `12758.23 s` (`11.5 %`) y `12743.59 s` (`11.6 %`).
  - `beta1_slope` (`0.25 / 0.50 → 1.00`): `12758.23 s` (`11.5 %`) → `12730.38 s` (`11.7 %`).
  - `normalization_mode` (`max` vs `log` / `quantile`): `12758.23 s` (`11.5 %`) vs `12786.52 s` / `12786.41 s` (`11.3 %`).
- **Parámetros invariantes en el sector compacto (`0` recargas):** `a4_unknown_pct` (`5/10/20`), `lambda1_risk` (`0.5/1.0/2.0`), `lambda2_recharge` (`60/120/240`) y `kappa_discount` (`0/0.001/0.005`) arrojan `12758.23 s` (`11.5 %`), ya que el polígono no requiere recarga intermedia y la cobertura A4 supera el 88 %.

---

## (f) Supuestos Explícitos

1. Estaciones `M1` de Bomberos como bases de despegue/recarga y `station_inventory = 1` por defecto.
2. Tabla `[1, 3, 5, 10, 20] %` para clases ordinales `A4` de SENAPRED como peso supuesto (no probabilidad calibrada).
3. Horario de simulación retrospectivo (`ECMWF IFS 0.25°`, octubre 2026) en una única celda de grilla sin canalización topográfica de quebradas.
4. Igniciones muestreadas en simulación Monte Carlo (`N = 1000`, `seed = 20261104`); snapshot real `A2` FIRMS = `"empty"`.

---

## (g) Limitaciones y Deuda Técnica

- **Resolución A4 en bloques:** Los 26 polígonos ordinales de SENAPRED generan escalones cuadrados en $p_{A4}$; no se aplicó suavizado artificial.
- **Sin `matplotlib`/`PIL`/`networkx` en contenedor:** Las gráficas PNG (`evidencia/*.png`) se generan vía `zlib`/`struct` en Python puro y el flujo $k=2$ en `core/replan.py` usa Edmonds-Karp propio.
- **Gurobi restringido (~2000 variables):** Limita el MILP exacto a $\le 28$ tareas; instancias mayores dependen de `alns_risk`.
- **Polígono demo de `~1.2 km²`:** No fuerza recargas en ruta (`recharges = 0`); conviene evaluar un corredor regional multi-batería ($\ge 10\text{ km}^2$) en trabajo futuro para contrastar `inv = 1` vs `20` en campo abierto.

---

## (h) Decisiones Pendientes de Revisión

1. Calibrar empíricamente los pesos de `A4` (`[1, 3, 5, 10, 20] %`) contra histórico de igniciones locales cuando se disponga de serie temporal completa.
2. Evaluar si `alns_risk` debe incorporarse como opción predeterminada para sectores grandes o mantenerse bajo selección explícita `mode="risk_adaptive"` en la UI.
