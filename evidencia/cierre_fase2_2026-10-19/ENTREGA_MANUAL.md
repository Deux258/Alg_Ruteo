# Entrega manual del equipo

El usuario realizará la carga con su cuenta universitaria. Solo se conoce la portada
https://giteit.udp.cl/; no se conoce la URL del proyecto ni la tarea de Canvas. No se
solicitan contraseñas y no se ha publicado ni enviado contenido a otras personas.

1. Revisar y guardar los cambios locales del proyecto en una versión Git del equipo.
   La huella code_sha256 identifica lo probado; el commit indicado en la evidencia
   es la base del trabajo y no se presenta como si incluyera estos cambios locales.
2. Configurar un remoto adicional con la URL exacta del proyecto del equipo. Conservar
   el remoto GitHub actual. Cargar el código, originales conservados, diccionarios,
   SQL, presentación de cierre y evidencia. No cargar `.env`, `tmp` o credenciales.
3. Confirmar que están los logs de esta entrega. `.gitignore` permite expresamente
   los de evidencia/cierre_fase2_2026-10-19; no basta verlos en el equipo local.
4. Ejecutar CI en GitLab. Si no hay runner Docker con servicios, registrarlo como
   pendiente; la configuración existente no equivale a una ejecución aprobada.
5. Clonar desde GitLab en una carpeta nueva. Con Bash y Docker activos, ejecutar
   `./main probar`, `./main` y luego
   `./main evaluar --experiment config/evaluacion_fase2.json`.
   Usar un COMPOSE_PROJECT_NAME nuevo y un WEB_PORT libre para obtener BD vacía.
   Comprobar que los archivos del lote aparecen en datos/runs/evaluaciones del host.
6. Registrar commit GitLab, URL, ID de pipeline, versiones y resultado. El manifiesto
   de entrega verifica los bytes; no contiene `.env`. Un cambio de código requiere
   nuevas pruebas y evidencia, no renombrar las anteriores.
7. Abrir las 36 diapositivas y revisar tablas, JSON, SQL, mapas y anexos en la aplicación
   elegida para exponer. La validación automática no acredita apertura en PowerPoint.
8. Subir la presentación de cierre a la tarea correcta en Canvas y confirmar la entrega.
   Mantener el comprobante universitario fuera del repositorio si contiene datos privados.

El sistema funciona en modo snapshot con originales verificados. No declarar una
actualización online completa mientras no terminen las ocho adquisiciones necesarias.
No declarar 60 puntos aprobados: quedan la revisión docente y la entrega efectiva.
