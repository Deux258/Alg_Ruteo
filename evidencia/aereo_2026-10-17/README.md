# Evidencias del simulador aéreo

Leer [INFORME.md](INFORME.md) para resultados, límites y bloqueo externo.

| Archivo | Campos / significado |
|---|---|
| `pruebas.json`, `pruebas.log` | Conteos ejecutados, fallos, errores, omisiones, duración en s, Python y versiones reales de BD; el log identifica cada prueba. |
| `arranque_limpio.json`, `ejecucion_snapshot.json` | UUID, modo, alcance, status, ETL completo, tiempos ET/carga, conteos I y M1-M4/A1-A4, auditoría topológica/espacial y consultas de ejemplo. `idempotent=true` significa repetición sin carga duplicada. `phase2_complete=false` distingue toda la rúbrica de las cargas implementadas. |
| `espacial.json` | ST_Covers del AOI y toda la infraestructura: totales, dentro/fuera, segmentos con extremos dentro que salen del polígono, bases dentro y hashes de los archivos contrastados. WGS84 para pertenencia, UTM 19S para área en km². |
| `solicitud.json` | Entrada reproducible de la API con origen/destino [lon,lat], modo de misión y hora histórica UTC. |
| `ruta.json` | FeatureCollection y respuesta de planificación: alternativas de ida/regreso, IDs y geometrías, km, segundos, observación, exposición en m ponderados, longitud desconocida y restantes. Contrato completo en docs/DATOS_AEREOS.md. |
| `bloqueo.json` | `request` con evento explícitamente sintético y `result` calculado tras excluir sus segmentos afectados. No acredita un incendio real. |
| `interfaz/resultado.json` | Checks Playwright, versión/canal del navegador, errores de página/recursos, URL y resultados inicial/con bloqueo. `successful` requiere cumplir todos los checks del script. |
| `interfaz/*.png`, `interfaz/dom_inicial.html` | Capturas nativas de escritorio y móvil y DOM inspeccionado antes de las acciones. HTML solo para evidencia, no se sirve como aplicación. |
| `online_bloqueado.json` | Informe de adquisición parcial: respuestas de seis fuentes y error DNS S6. Los archivos originales referenciados se conservan en datos/entrada/aereo. No es un manifiesto activo ni un éxito online. |
| `*.log` de main | Construcción, servicios, salud y resumen de las ejecuciones. |
| `comparacion.svg/png` | Geometrías de red vial anterior y corredores aéreos actuales a escala común. El PNG es opcional; SVG se genera sin dependencias externas. |

Coordenadas GeoJSON: WGS84 [longitud, latitud], grados. Área y longitudes se
calculan en EPSG:32719; distancias en km, tiempos en segundos. IDs grandes en las
respuestas HTTP se representan como texto; los informes internos de SQL pueden
conservar enteros. NoData/null no equivale a cero ni a seguridad de vuelo.

## Regenerar

`./main probar` conserva el resultado actual en evidencia/local. Con el mismo
proyecto Compose que la aplicación publicada:

```bash
docker compose run --rm --no-deps -v "$PWD/evidencia/local:/app/evidencia/local" etl python -m tools.probar_aereo
python tools/probar_interfaz_aerea.py --url http://127.0.0.1:18081
python tools/generar_mapa_aereo.py
```

Playwright requiere Python y paquete playwright 1.56.0 como herramienta de prueba,
además de Chrome o Edge instalado (usar `--channel msedge` para Edge). Se ejecuta
headless. La aplicación y la suite de BD funcionan dentro de Docker. La figura
SVG usa Python estándar; `--png` requiere Pillow solo para generar esa copia.

Para reproducir otro corte, restaurar su manifiesto archivado por hash y sus
originales, manteniendo configuración/perfil. No sustituir datos del snapshot
para luego conservar su mismo run. Los hashes y diccionarios están en el
[contrato de datos](../../docs/DATOS_AEREOS.md).
