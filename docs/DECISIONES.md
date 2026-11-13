# Registro de Decisiones y Supuestos — Proyecto RRPP (Valparaíso)

## Hechos Verificados del Snapshot (`run_id: b80f9b83-cad7-53b8-a8b8-34a2a17e614c`)
- **A4**: SENAPRED (`S7`, *Amenaza por incendio forestal 2024*, densidad 2020–2024), 26 polígonos en BD (29 en manifest) de clase ordinal 1–5. La tabla `[1, 3, 5, 10, 20] %` es un **peso supuesto**, no una probabilidad calibrada. `a4_unknown_pct = 20.0` (configurable en `RiskConfig`).
- **M2**: CONAF / CIREN (`S2`, 2019), 679 registros con `especi1_co`, `subuse`, `forest_type`.
- **M3**: Copernicus GLO-30 (`S3`, celda `S34 W072`), derivado de TanDEM-X, datum `EGM2008`, resolución nativa 1 arcseg (`~30.9 m N-S × 25.9 m E-O`).
- **M4**: Open-Meteo / ECMWF IFS `0.25°`, 48 registros horarios a 10 m, snapshot retrospectivo octubre 2026. Coordenada solicitada: `(-33.0784, -71.6163)`; celda devuelta por ECMWF: `(-33.0, -71.5)`.
- **A2**: NASA FIRMS VIIRS NOAA-20 C2, 0 detecciones reales (`"empty"`). Toda prueba con focos FIRMS usa datos sintéticos rotulados explícitamente.
- **A3**: DGAC AIP ENR 5.1; bloquea la observación del dron (`observable = False`), **no** anula $R$. El `0.48 %` (a 90 m) / `0.73 %` (a 45 m) de riesgo inobservable depende de que `forest_zone_utm` ya excluye el casco urbano.
- **Baterías (`station_inventory`)**: valor efectivo por defecto = `1` en UI, JS, JSON y backend (`20` es opción continua). Los experimentos congelarán ambas variantes (`1` y `20`).

## Decisiones de Diseño por Etapa

### Etapa 1 — Campo de Riesgo $R(x,y,t)$
1. **Normalización por defecto (`normalization_mode = 'max'`)**:
   - Evidencia cuantitativa (`27 543` celdas forestales a 45 m): Spearman($R, U$) = `0.7108`, Spearman($R, p_{A4}$) = `0.5890`, Spearman($R, F_{M2}$) = `0.3262`, Spearman($R, S$) = `-0.0197`. El factor dominante es la **interfaz urbano-forestal $U$** seguido de $p_{A4}$.
   - Con `max`, el top 5 % de celdas concentra **`45.73 %`** del riesgo y el top 10 % **`63.82 %`**. Con `quantile`, cae a **`9.76 %`** y **`19.00 %`**, destruyendo el gradiente de prioridad para el ruteo por latencia. Se conserva `max` como default y `log` / `quantile` configurables en `RiskConfig`.
2. **Bloques cuadrados de A4**:
   - Provenientes de la resolución gruesa de los 26 polígonos ordinales de SENAPRED; se preservan sin suavizado artificial y se declaran como limitación.
3. **Polígonos interiores oscuros en Panel A**:
   - Corresponden a clase ordinal `1` (`peso supuesto = 1 %`, 45.9 % del área forestal), mientras que las zonas sin cobertura (`11.61 %` a 45 m / `11.81 %` a 90 m) reciben `a4_unknown_pct = 20 %`.
