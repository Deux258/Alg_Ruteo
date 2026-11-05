# Entorno geográfico 2D/3D

La pantalla de patrullaje recupera OpenStreetMap como mapa base 2D y añade cartografía
vectorial local. En **04 · Cartografía y entorno** se puede alternar OpenStreetMap con
el mapa local y activar las seis capas de forma independiente. Las mismas selecciones
se aplican a la vista 3D. Las fichas 2D muestran atributos, fuente y estimaciones.

| Capa | Datos y representación | Efecto sobre la misión |
|---|---|---|
| Edificios | Huellas OSM con patios interiores; techos y paredes extruidos | Superficie de obstáculos, alturas de vuelo y línea de vista |
| Agua | Cuerpos de agua, cauces y mar derivado de la orientación de la costa OSM | Se descartan bases/estaciones que estén sobre agua cartografiada; el sobrevuelo sigue permitido |
| Cobertura del suelo | Catastro CONAF 2019 complementado con usos y coberturas OSM | Bosques incorporan una envolvente de copas estimada; las demás categorías describen el entorno |
| Árboles | Puntos e hileras OSM; símbolos de copas dentro de bosques | Los árboles mapeados y bosques afectan la envolvente; los símbolos generados no se presentan como observaciones |
| Calles y caminos | OSM, con nombres y atributos en fichas | Referencia y orientación; no se convierten en restricciones viales para el dron |
| Curvas de nivel | Intersecciones cada 20 m de la malla DSM de 30 m | Representan la superficie utilizada; no son curvas topográficas levantadas en terreno |

El arrastre permite orbitar; Mayús + arrastre o el botón derecho desplaza la cámara;
la rueda controla el zoom. **Ver toda el área** recupera la extensión y **Centrar misión**
encuadra las rutas calculadas. La escala vertical es métrica, sin exageración añadida.
Los créditos de OpenStreetMap, CONAF y Copernicus permanecen visibles en 3D.

## Alturas y obstáculos

`height` OSM tiene prioridad, con metros por defecto y conversión explícita de pies.
Cuando falta se utilizan niveles de edificio × 3 m; sin niveles, 9 m para edificios.
Los árboles sin altura usan 8 m y copa de 4 m de diámetro; los bosques, 12 m. Todos
estos valores son supuestos declarados en `config/escena.json` y en las fichas.

La base de edificios y árboles se aproxima con el mínimo de muestras DSM interiores
y vecinas a 30 m. La envolvente es `max(DSM, base aproximada + altura del objeto)`.
Esto conserva objetos ya reflejados en el DSM y evita sumar automáticamente su altura
al techo. Sigue siendo una aproximación: no se dispone de un DTM ni de cotas de base
levantadas. Las copas de bosque siguen la superficie local, sin aplanar todo un bosque
a la cota de su punto más alto.

Las trayectorias mantienen la altura elegida sobre esa envolvente. Además del muestreo
regular de 15 m, se muestrean entradas, salidas y puntos adyacentes de las geometrías
de obstáculos: un edificio estrecho entre dos muestras regulares no queda omitido.
Los ascensos y descensos modifican tiempos y batería. La comprobación de visibilidad
usa la misma superficie y cortes. La simulación recupera la misma instantánea utilizada
para calcular la ruta; si no está disponible, exige recalcular.

## Fuentes y rendimiento

La instantánea adquirida contiene, dentro del área de vuelo, 25.148 edificios,
más de 400 cuerpos/cursos de agua, 789 árboles o hileras y 7.171 tramos de calles/caminos.
La cobertura combina 1.153 geometrías CONAF/OSM. No implica un inventario completo
o actualizado en terreno. Los metadatos conservan ID OSM, revisión y fecha cuando
están presentes. La consulta y el hash de los originales están en
`datos/entrada/escena/manifest.json`.

La triangulación, las curvas y los símbolos se preparan una vez y se conservan en
un derivado comprimido, ligado a hashes de código, DSM, CONAF y OSM. El mapa 2D no
descarga la geometría de renderizado 3D hasta que se solicita esa vista.

- `GET /api/aereo/patrullaje/mapa`: incorpora `geography`, con fuentes, capas GeoJSON,
  conteos y advertencias, junto con la malla DSM.
- `GET /api/aereo/patrullaje/escena3d`: geometría de renderizado local y SHA de la escena.
- El resultado de ruteo contiene `geographic_scene`, con hashes, fecha y modelo de altura.
- **Exportar capas GeoJSON** descarga todas las capas WGS84 y sus metadatos.

El mapa local conserva geometrías aunque no haya conexión. Las teselas de OpenStreetMap
se solicitan directamente al visualizar el mapa 2D, con atribución y caché del navegador;
no se ofrecen descargas masivas ni precarga. Su URL está en `config/escena.json`.

El mar se representa también en el contexto rectangular del DSM, con nivel medio
aproximado de 0 m; esto no rellena vacíos del DSM para volar ni amplía el área permitida.
Los edificios mantienen geometría original recortada al área de vuelo; agua, coberturas
y caminos se generalizan a 1 m y las curvas a 0,3 m para reducir tamaño. Los huecos
de datos DSM no se convierten en elevación cero ni se conectan mediante curvas.

## Reproducción y comprobaciones

```bash
python -m Infraestructura.descargar_escena
python -m tools.preparar_escena --context datos/runs/<run>/context.json
python -m unittest tests.test_geographic_scene tests.test_patrol -v
python -m tools.verificar_entorno --chrome "<ruta a Chrome>" --mission
```

El navegador se verifica sin grabación. La producción de video sigue pospuesta.
La nueva cartografía cambia la superficie y puede cambiar los resultados de rutas;
las evidencias de la fase anterior se conservan como resultados de aquella versión.

Fuentes: [Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL),
[Simple 3D Buildings](https://wiki.openstreetmap.org/wiki/Simple_3D_Buildings),
[orientación de costas](https://wiki.openstreetmap.org/wiki/Tag:natural%3Dcoastline),
[licencia OSM](https://www.openstreetmap.org/copyright) y
[política de teselas](https://operations.osmfoundation.org/policies/tiles/).
