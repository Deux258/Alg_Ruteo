# Cierre verificable

La implementación se valida con `./main probar`: PostgreSQL/PostGIS/pgRouting en
`dbtest/ruteo_test`, Python, Node y Chromium sin grabación de video. El ejecutor
rechaza otro host, otro nombre de base o `DATABASE_URL`. La base es tmpfs y los
casos de integración publican exclusivamente dentro de ella.

El workflow canónico es `.github/workflows/verification.yml`. Una ejecución local
no acredita que GitHub Actions haya corrido: ese estado se comprueba al subir la
versión. No se realiza push automáticamente. `.gitlab-ci.yml` se conserva como
compatibilidad histórica; su job Python no sustituye la aceptación de GitHub.

## Presupuesto y modelo

La batería útil conserva su valor real después de la reserva operacional del 20 %.
Se apartan además 60 s para el reporte en cada batería. El presupuesto total de
misión aparta esos 60 s una sola vez. Ejemplos: 1.200 = 1.140 + 60 s;
190 = 130 + 60 s. El simulador usa las capacidades reales y vuelve a verificar
reporte y retorno al detectar un foco. Un reporte incompleto carece de hora final.

Las restricciones meteorológicas y de energía se evalúan en el backend mediante
`core/mission_constraints.py`; la interfaz consulta la misma evaluación. Una hora
bloqueada conserva diagnóstico y probabilidades sin inventar una trayectoria.

La resiliencia se estima sobre escenarios compartidos, con intervalos Wilson al
95 %. Se declara ganador o empate a partir de esa estimación y se explica aparte
el desempate por cómputo. Las probabilidades siguen siendo hipótesis académicas,
no frecuencias calibradas. Un sorteo depende de semilla, escenario e identificador
de amenaza, de modo que agregar otra amenaza no cambia los sorteos anteriores.

## Cartografía y transporte

Los límites comunales preservan el ZIP original BCN, sus hashes, CRS, atribución y
edición declarada por la fuente. Los CUT identifican las comunas. El filtro recorta
la representación de cada capa; la geometría original sigue disponible y el área
permitida de vuelo no cambia. El clima se identifica como información compartida.

Las APIs completas existentes se conservan. `?view=summary` sirve la vista inicial
y la misión compactas; los manifiestos enlazan las capas, probabilidades, grafo y
exportación completos. Los recursos inmutables se identifican por hash, usan ETag
y permiten caché del navegador. Cálculo, sorteo y simulación son operaciones
dinámicas. Las posiciones 3D son Float32 y los colores Uint8 normalizados;
se comprueban sus hashes antes de subirlos a GPU.

Las rutas estáticas se preparan al modificarlas. Cada fotograma actualiza cámara y
marcador. Reemplazar una escena o cerrar el visor libera buffers y listeners; una
respuesta cancelada no puede reemplazar una escena nueva. NoData conserva huecos
de elevación desconocida, sin dibujar una superficie artificial a cota cero.

## Reproducción

```bash
./main adquirir-escena   # explícitamente consulta OSM y BCN
./main preparar-escena  # usa la publicación existente, sin adquirir fuentes
./main probar          # Python + Node + Playwright, BD desechable
```

Las fuentes geográficas se adquieren fuera de las consultas interactivas. El
inicio completo con `./main` prepara los recursos antes de habilitar la web;
una publicación vial conserva su flujo. La preparación explícita también puede
ejecutarse con los comandos anteriores.
La web monta los originales en solo lectura y renueva su proceso al publicar,
para utilizar las mismas fuentes que el ETL. El perfil/modelo y hashes de fuentes
forman parte de las claves de preparación.
Cambiar una misión puede reutilizar geometría inmutable, manteniendo aislados
clima, amenazas, restricciones y conectores de cada consulta.

La evidencia de `evidencia/local/` es regenerable y queda fuera de Git. Cada
ejecución registra la huella de los archivos de código/configuración, versiones
efectivas, omisiones y resultados. Los benchmarks se ejecutan por separado, sin
cálculos concurrentes. El objetivo del 50 % requiere medición; no se deduce de la
presencia de una caché.

La reconstrucción también comprueba el paquete de sistema libexpat1 antes de
instalarlo. Su copia oficial y manifiesto están en `docker/packages/`: evita
que retirar una versión del índice APT impida construir la aplicación.
