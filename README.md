# Ruteo aéreo de drones en Valparaíso · fase 2

Simulador académico Docker con PostgreSQL 16.9, PostGIS 3.5.2, pgRouting 3.8.0 y Leaflet local.
Despeje vertical no verificado. No representa vuelos autorizados ni una navegación 3D.

## Ejecutar

Con Docker activo, desde Git Bash o WSL:

```bash
./main probar
./main
```

Abrir http://127.0.0.1:8080. El host solo necesita Bash y Docker Compose v2.
La instancia verificada de entrega está en http://127.0.0.1:18081:

```bash
COMPOSE_PROJECT_NAME=udp-ruteo-fase2-entrega WEB_PORT=18081 ./main estado
COMPOSE_PROJECT_NAME=udp-ruteo-fase2-entrega WEB_PORT=18081 ./main
```

`main` genera `.env` si falta, construye la imagen, aplica SQL/migraciones, ejecuta nueve ETL y cargas,
audita y publica atómicamente. No elimina volúmenes. `./main detener` conserva los datos.
`./main iniciar --mode online` exige adquirir todas las fuentes; no oculta una caída de DGAC.

## Geografía y bases

Se conserva el polígono original de **54,920709 km²**. El tránsito admite un buffer de **1.100 m**
en EPSG:32719, con **97,716233 km²** totales. Este límite geométrico no implica permiso de vuelo.
El contrato 4.0 contiene **154 nodos y 1.114 arcos dirigidos**, en una componente fuerte.
Las calles no condicionan la red. Malla: 800 m, ocho vecinos, enlaces hasta 1.500 m incluidos
los enlaces temporales de consultas. Cada segmento completo debe quedar dentro de tránsito.

Los destinos y orígenes libres permanecen en vigilancia. Fuera solo se aceptan cuatro bases
seleccionadas: Décima, Décima Segunda, Décima Tercera y Décima Quinta. La base inicial sigue siendo
Décima Sexta, Laguna Verde, SENAPRED 104, **[lon −71.657239211, lat −33.101901690]**.
S1H:19 y S1:104 se concilian sin duplicar ni desplazar la base histórica. Hay 16 instalaciones
catalogadas, cinco candidatas y once de contexto. Una base candidata puede resultar bloqueada por AIP.

## Uso

1. Elegir base o inicio por clic/coordenadas, y destino dentro de vigilancia.
2. Revisar hora UTC y condición del pronóstico. El snapshot permite una simulación histórica,
   no una afirmación de disponibilidad actual.
3. Calcular hasta dos opciones con idas distintas. Ida continua y retorno discontinuo.
4. Ajustar presupuesto, límite de viento o desvío. Solo se permiten restricciones más exigentes.
5. Comparar ambos métodos: cuatro misiones, 100 escenarios y diferencial en puntos porcentuales.
6. Dibujar bloqueos y replanificar desde un nodo con fase y tiempo consumido. Un retorno de
   emergencia no cuenta como vigilancia completada. No hay escape modelado durante un segmento.
7. Descargar resultado y solicitud con perfil, geometrías y hashes.

La referencia genera D1/D2 por longitud usando `pgr_dijkstra`, tanto para ida como regreso.
No filtra amenazas ni autonomía al generar. La propuesta utiliza `pgr_KSP`/Yen sobre arcos admitidos,
hasta tres idas por tres regresos, y ordena candidatos por exposición y tiempo. La generación es
limitada; no garantiza óptimo global ni independencia espacial.

## Adquisición y evaluación reproducible

```bash
# Actualiza seis fuentes y registra la reutilización de DSM/AIP verificados:
./main adquirir --sources S1,S1H,S2,S4,S5,S7 --reuse S3,S6
./main iniciar --mode snapshot

# Tras preparar datos/runs/solicitud_demo.json y ejecutar main:
./main evaluar --request datos/runs/solicitud_demo.json

# Lote fijado antes del cálculo: hasta 120 casos, dos perfiles y 100 escenarios por caso
./main evaluar --experiment config/evaluacion_fase2.json
```

`adquirir` no publica en la BD. Un fallo conserva el manifiesto activo y deja un diagnóstico aparte.
Los originales activos están en `datos/entrada/aereo_v2`; los anteriores se conservan en `aereo`.
La adquisición selectiva es explícita, no equivale a una actualización fresca de todas las fuentes.

## Evidencia y documentación

- [Informe de entrega](evidencia/fase2_2026-10-19/INFORME.md).
- [Contrato, API y diccionario ampliado](docs/FASE2_METADATA_TRANSITO.md).
- [Matriz de rúbrica y guion](presentacion/MATRIZ_RUBRICA.md).
- [SQL inicial](BD/crear_bd.sql), migraciones 002–004 y [catálogo visual](BD/diagrama_fase2.svg).
- `evidencia/fase2_2026-10-19`: pruebas, software, SQL, fuentes, mapas, comparación y capturas.

En el ejemplo documentado, ambos conjuntos sobreviven al **99 %** de los 100 escenarios: **ΔR = 0 pp**.
No demuestra superioridad ni una probabilidad real. Los escenarios son sintéticos y las misiones
se fijan antes de evaluarlos. El pronóstico se congela en la hora elegida durante toda la misión.

Se preservan S1–S7 del informe y se añade S1H como catálogo complementario de Bomberos de
IDE Chile/Junta Nacional, republicado en ArcGIS. M1–M4 adaptan los aportes de Diego Hidalgo.
La capa adicional de riesgo de clases sin procedencia/semántica verificadas queda excluida.
Vegetación 2019, recurrencia 2020–2024, viento a 10 m y DSM ~30 m mantienen sus limitaciones.
La actualización completa online depende de DGAC. GitLab UDP y Canvas requieren entrega del equipo.
`etl_complete` acredita cargas; `phase2_complete=false` no certifica nota, publicación ni seguridad.

## Cierre de rúbrica

La preferencia opcional `max_historical_class` acepta enteros 1–5 o null. Desactivada
conserva las rutas anteriores; activada excluye clases superiores y tramos sin cobertura
histórica. Expresa una política preventiva simulada, no un incendio activo. La interfaz
permite mostrar u ocultar D1/D2/P1/P2 individualmente y exportar el perfil efectivo.

El lote completo conserva todos los casos: 4 mejoras, 114 empates y 2 empeoramientos;
delta medio +1,65 pp. Separados por perfil: +0,03 pp predeterminado y +3,27 pp con clase
máxima 4. Solo 13/120 casos propuestos son viables en el control. Son resultados
descriptivos de escenarios sintéticos, sin superioridad estadística demostrada.

Entrega actual: [informe de cierre](evidencia/cierre_fase2_2026-10-19/INFORME.md),
[matriz](presentacion/MATRIZ_RUBRICA.md) y `presentacion/fase2_valparaiso_cierre.pptx`
(22 láminas principales y 14 anexos). La presentación anterior se conserva como antecedente.
Consultar `evidencia/cierre_fase2_2026-10-19/ENTREGA_MANUAL.md` para GitLab UDP y Canvas.

Se aplicaron geomaster y webapp-testing. La referencia de software está en la documentación ampliada.
