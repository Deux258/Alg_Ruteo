# ALG_RUTEO · Tráiler nativo de HyperFrames

## Estado

La composición nativa está en `index.html` y `compositions/`: nueve escenas independientes con textos HTML, gráficos SVG, animaciones GSAP y música original. No usa un MP4 como fuente. Drones, radar, rutas progresivas, alertas, transiciones y movimientos de cámara se calculan en la línea de tiempo. Las escenas se pueden modificar por separado.

**El render nativo está pendiente.** Esta sesión no permite descargar dependencias por npm (`EAI_AGAIN` para `registry.npmjs.org`) ni iniciar Chrome en el aislamiento actual. Las verificaciones ejecutadas aquí comprueban sintaxis JavaScript, estructura, duración y archivos locales; no sustituyen el check, las capturas ni el render oficial de HyperFrames. No existe todavía `renders/Alg_Ruteo_Hyperframes.mp4`.

El video ya disponible en `renders/Alg_Ruteo_Trailer_YouTube_1080p.mp4` es la exportación anterior con Pillow/FFmpeg. Sigue accesible en `preview.html`. No es la exportación nativa de esta composición. El montaje anterior basado en ese MP4 se conserva en `assembly-previous.html.txt`.

## Exportar con HyperFrames

Desde una terminal con acceso a npm y capacidad para ejecutar Chrome, en esta carpeta:

```bash
./render-hyperframes.sh
```

El script instala las dependencias fijadas en `package.json`, copia GSAP a `assets/`, comprueba el entorno, ejecuta el check oficial, guarda nueve capturas, abre la previsualización de HyperFrames y exporta un archivo local:

```
renders/Alg_Ruteo_Hyperframes.mp4
```

Después guarda los metadatos del resultado en `renders/hyperframes-probe.json`. Se detiene si falla una operación. No contiene comandos de publicación, subida a YouTube ni render en la nube.

También se puede proceder por etapas:

```bash
npm install --no-audit --no-fund
npm run prepare:assets
npm run check
npm run preview
npm run render
```

Requisitos: Node.js 22+, FFmpeg y las dependencias de Chrome que comprueba `hyperframes doctor`. Resolución: 1920 × 1080; duración: 60 segundos; frecuencia: 30 fps. El MP4 anterior se conserva y no se sobrescribe.

## Editar

- `compositions/*.html`: textos, gráficos y movimientos de las nueve escenas. Cada archivo contiene su template y su línea GSAP pausada, registrada al terminar su construcción.
- `index.html`: orden, duración de escenas y audio separado.
- `scenes.json`: guion, títulos y tiempos.
- `build_native.py`: generador de las escenas; al ejecutarlo sobrescribe `index.html` y `compositions/`, por lo que los cambios manuales deben incorporarse primero a este generador.
- `assets/score-original.wav`: música original sintetizada a 120 BPM con impactos y señales sincronizadas.
- `assets/fonts/`: fuentes locales y sus licencias.

La composición usa archivos locales y tiempos finitos. No descarga material durante el render. No tiene relojes en tiempo real ni aleatoriedad sin semilla. No necesita claves, licencias de solver, base de datos ni el sistema de vuelos activo.

## Procedencia y alcance

El guion se basa en el README del proyecto y la evidencia de `docs/RESULTADOS_MEJORAS_3D.md`. Las capturas reales se copiaron de `evidencia/mejoras_3d_2026-11-07/` a `assets/simulador-terreno.png` y `assets/simulador-pov.png`. Las mallas y rutas luminosas nativas son gráficas ilustrativas y están identificadas como tales. No representan salidas del solver ni vuelos reales. Los 1.000 escenarios corresponden al protocolo experimental documentado.

Se consultaron las fuentes oficiales de [formato](https://raw.githubusercontent.com/heygen-com/hyperframes/main/skills/hyperframes/references/format.md), [runtimes](https://raw.githubusercontent.com/heygen-com/hyperframes/main/skills/hyperframes/references/runtimes.md) y [CLI](https://hyperframes.app/docs/5-packages/cli).

`YOUTUBE.md` conserva título y descripción opcionales; **no se ha publicado ni se publicará desde el script**. `REVIEW.json` corresponde al MP4 anterior. `NATIVE_STATUS.json` documenta las comprobaciones del proyecto nativo y el bloqueo actual.
