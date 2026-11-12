# Plan de acción: monitoreo automático, focos aleatorios y recuperación

Estado: implementado en código. Las decisiones actualizadas y el alcance de verificación están en `MONITOREO_AUTOMATICO.md`. Video y presentación permanecen pospuestos. Los ajustes solicitados por el usuario sustituyen las propuestas iniciales de probabilidad configurable y tres recorridos.

## Comportamiento objetivo

Seleccionar un recorrido de monitoreo predefinido, iniciar el vuelo y simular la aparición automática de un foco. El dron solo lo descubre al observarlo durante el vuelo. Entonces registra la detección, evalúa reporte y aterrizaje, compara cuatro técnicas de recuperación y continúa hacia el origen o una estación de bomberos habilitada. La interfaz muestra las alternativas, sus destinos y su factibilidad.

## Decisiones propuestas para la primera versión

1. Tasa fija derivada del registro regional de CONAF: 575 incendios desde el 1 de julio de 2025, publicados el 1 de junio de 2026. Se estima una intensidad por km² y día y p=1−exp(−λAT). No admite un porcentaje definido por el usuario ni sorteos por fotograma.
2. Obtener el primer arribo de un proceso homogéneo de Poisson mediante una uniforme y la transformada exponencial. No restringir artificialmente el incendio al 20–80 % del vuelo. El reloj común mantiene el mismo primer evento al comparar horizontes de distinta duración.
3. Sortear una ubicación uniforme por superficie dentro del objetivo, con elevación conocida. La generación no fuerza que el punto sea observado ni lo coloca en la posición actual del dron. Registrar el soporte espacial válido y los rechazos por falta de datos. Generación y detección son fenómenos distintos.
4. Un foco activo se mantiene hasta detectarse o terminar la misión. No se muestra antes de su aparición ni se usa para decidir la ruta mientras el dron no lo ha observado. Para auditoría puede guardarse el evento completo en una exportación identificada, sin presentarlo anticipadamente como conocimiento del dron.
5. Mantener inicialmente el detector geométrico existente: alcance del perfil y línea de vista contra superficie/obstáculos. No añadir una tasa aleatoria de acierto del sensor sin un modelo separado.
6. Las cuatro técnicas serán las actuales: Dijkstra distancia, Dijkstra con parámetros, Gurobi y recocido simulado. Se evalúan desde el mismo estado y frente a las mismas amenazas conocidas.
7. Comparar origen y siguiente estación de bomberos elegible. «Siguiente» significa la próxima estación habilitada en el itinerario; si no hay una ordenada, elegir una estación alcanzable por costo de vuelo dirigido, no solo por cercanía en línea recta. Excluir el origen de la lista de estaciones alternativas para no duplicar el mismo destino.
8. Cuatro alternativas principales, una por técnica, mostrando el destino que cada una recomienda. Guardar el detalle de ambos destinos por técnica, hasta ocho candidatas, para poder comparar volver al origen frente a aterrizar en estación. Si hay menos soluciones o coincidencias, declararlo; no inventar cuatro trayectorias distintas.
9. Decisión automática de destino por defecto, con posibilidad de inspeccionar/seleccionar otra alternativa factible antes de continuar. Priorizar factibilidad, batería y aterrizaje; después tiempo/riesgo según la política declarada. La llegada al cuartel es un destino simulado, no una certificación de autorización ni de recarga real.

## Situación actual y puntos de extensión

- `core/patrol.py::simulate` recibe un `fire` colocado manualmente, inspecciona visibilidad y genera detección, reporte y regreso.
- `find_recovery`, dentro de esa función, busca un retorno admisible entre origen y estaciones, pero no devuelve una comparación de las cuatro técnicas de recuperación.
- `core/patrol_alternatives.py` construye circuitos de vigilancia diversos; no debe confundirse con el nuevo problema de salir del punto de detección hacia un destino seguro.
- `core/web.py` sirve la planificación, simulación y recursos persistidos.
- `Sitio Web/patrol.js`, `patrol.html` y `flight-player.js` controlan la reproducción, las cámaras y los mensajes.
- `config/patrullaje.json` contiene el perfil y las semillas actuales.

## Fase 1. Contratos y estado de la misión

- Definir un esquema versionado de monitoreo: recorrido, perfil, semilla, escenario, probabilidad del foco y ventana temporal.
- Modelar eventos con ID estable, instante, ubicación, sorteo, resultado y estados generado/activo/detectado/reportado. La transición a detectado requiere observación real dentro del modelo.
- Separar sorteo del foco y sorteo de amenazas de infraestructura. Usar etiquetas distintas en el generador reproducible para que un evento no desplace los sorteos del otro.
- Definir la máquina de estados: lista → vigilancia → foco activo → detectado → evaluación de recuperación → reporte cuando sea viable → desplazamiento a destino → aterrizado; incluir fin sin foco, foco no observado, reporte incompleto y ausencia de retorno seguro.
- Distinguir servicio de detección/reporte completado y cobertura total del patrullaje. Atender un foco y regresar no equivale a terminar el barrido.

Entregable: configuración, esquemas y ejemplos de solicitud/respuesta, con valores y reglas documentadas.

## Fase 2. Recorridos predefinidos sobre la infraestructura existente

- Crear un catálogo versionado que particiona toda el área de estudio en sectores de aproximadamente 400 m, vinculados a bases M1. En el snapshot actual resultan 405 sectores para 54,92 km². Cada trayectoria se calcula y valida al seleccionarla; el certificado de sectorización no equivale a cobertura observada.
- Cada entrada conserva ID, nombre, base, objetivo, itinerario o puntos de paso, parámetros y estaciones elegibles. Incluye la trayectoria calculada y validada para su snapshot; no es únicamente un nombre para un polígono ni una colección de líneas rectas.
- Al seleccionar, mostrar trayectoria, área, duración estimada y restricciones. Permitir iniciar con los valores válidos del catálogo.
- Revalidar o recalcular si cambia terreno, grafo, viento, amenazas, batería o perfil. Identificar los resultados por hashes de datos y configuración para no reutilizar una trayectoria obsoleta.
- Mantener el dibujo/importación de zonas como modo personalizado. El monitoreo automático no requiere usar «Marcar foco».

Entregable: catálogo, carga desde backend y selector de recorrido listo para iniciar.

## Fase 3. Aparición automática y detección durante el vuelo

- Añadir un módulo de eventos, por ejemplo `core/patrol_events.py`, sin seguir ampliando toda la lógica dentro de `simulate`.
- Generar el escenario a partir de semilla e ID, antes de evaluar algoritmos. Conservarlo al pausar, cambiar de cámara o consultar otra alternativa.
- Aplicar la detección únicamente a partir del instante de aparición. Encontrar el primer punto observable de un foco activo, con altura, radio y línea de vista del modelo.
- Exportar momento de aparición y de detección por separado; un foco puede aparecer sin ser detectado.
- Conservar el modo manual como diagnóstico opcional claramente identificado; el flujo principal pasa a ser automático.
- La comparación de técnicas debe reutilizar el mismo evento físico y su reloj. No generar un incendio favorable para cada algoritmo. Si se comparan patrullajes de duración distinta, fijar un reloj/ventana de escenario compartidos en el protocolo de evaluación.

Entregable: simulación reproducible con foco automático, sin intervención del usuario sobre el mapa.

## Fase 4. Cuatro alternativas desde el punto de detección

- Extraer la recuperación a un módulo propio, por ejemplo `core/patrol_recovery.py`, reutilizando el evaluador físico de la infraestructura.
- Congelar posición exacta, instante, batería, consumo acumulado, estaciones usadas y amenazas conocidas al detectar. Si ocurre entre nodos, dividir el enlace conservando tiempos dirigidos por viento, geometría vertical y restricciones de sus arcos residuales.
- Construir los destinos elegibles: origen y siguiente estación; descartar nodos bloqueados, inaccesibles o fuera de los recursos restantes. Una estación cercana puede ser inviable.
- Ejecutar Dijkstra distancia, Dijkstra tiempo/riesgo, un modelo de recuperación de Gurobi y recocido para ambos destinos sobre el mismo estado. Adaptar las formulaciones al problema de recuperación; no volver a optimizar todo el barrido desde la base como si no hubiera vuelo previo.
- Medir cómputo, costo, tiempo de vuelo, batería de llegada, riesgo, destino y estado por candidata. Mantener explícitos errores de licencia, límite de tiempo, búsqueda limitada y ausencia de solución.
- Controlar dimensión y presupuesto de cómputo de Gurobi/recocido. Si se usa un subgrafo o conectores precomputados, identificar ese alcance y no afirmar óptimo global continuo. No sustituir un solver fallido por Dijkstra bajo otro nombre.
- Comprobar reporte más retorno antes de gastar la reserva de reporte. Incluir aterrizaje y presupuesto de misión; si solo se puede regresar, marcar reporte incompleto.
- Separar tiempo de cómputo real y tiempo simulado. Pausar la reproducción mientras se muestran las opciones no debe consumir batería accidentalmente; una espera de vuelo modelada debe tener duración y consumo explícitos y reproducibles.
- Mostrar las rutas en 2D/3D y permitir reproducir el tramo desde la detección hasta el destino elegido, sin reiniciar posición ni batería.

Entregable: comparación de cuatro alternativas principales y detalle auditable por destino.

## Fase 5. API, persistencia e interfaz

- Integrar catálogo, eventos y recuperación en las rutas HTTP existentes, añadiendo operaciones específicas cuando convenga. El backend reconstruye el estado desde una misión persistida: no confía en una batería o posición arbitraria enviada por el navegador.
- Persistir escenario/eventos y candidatas con versión, semilla, hashes, identificador de misión y punto de detección. Reutilizar el almacén de resultados/recursos del proyecto; una migración SQL solo se agrega si se decide indexar ese historial en BD.
- Nueva sección de monitoreo: sector predefinido, tasa oficial de solo lectura, semilla, índice de escenario, iniciar y pasar al siguiente sector pendiente. Sin control de probabilidad ni ventana temporal artificial.
- Mostrar aparición solo desde su instante; detección, reporte y notificación interna en la bitácora. Las perspectivas 2D, seguimiento y POV comparten el mismo estado.
- Al detectar, abrir «Alternativas de recuperación» con cuatro tarjetas/filas, controles de visibilidad, destino, métricas, recomendación y selector de origen/estación.
- Continuar automáticamente con la opción recomendada en el modo automático; ofrecer pausa/selección para inspección. Mantener estados claros mientras calcula y ante respuestas obsoletas o solicitudes ocupadas.
- Exportar JSON/GeoJSON con ruta de monitoreo, evento, punto de detección, evaluación por destino y trayecto ejecutado.
- Una notificación externa a bomberos, correo o SMS queda fuera de esta primera versión; el cambio pedido se implementa dentro del simulador.

Entregable: flujo completo usable sin colocación manual de focos.

## Fase 6. Pruebas, aceptación y documentación

Pruebas deterministas y de integración necesarias:

- Exposición nula nunca genera foco; la frecuencia del generador concuerda estadísticamente con la tasa fijada por el registro oficial. Semillas iguales reproducen evento y rutas. Escenarios distintos no alteran otro sorteo guardado.
- Pausa, velocidad y cambios de cámara no vuelven a sortear ni cambian la probabilidad por misión.
- Muestreo de tiempo/posición dentro de su soporte; revisión estadística sobre muchas semillas con tolerancias justificadas, sin confundirla con calibración de incendios reales.
- No detectar antes de aparecer, fuera de alcance, detrás de un obstáculo o con elevación desconocida. Registrar foco no observado.
- Detección entre nodos con arcos residuales, viento y consumo conservados.
- Origen viable/estación inviable; estación viable/origen inviable; ambos viables; ninguno viable. Próxima estación bloqueada y origen que también figura en el catálogo, sin duplicación.
- Reporte completo frente a reserva insuficiente; aterrizaje incluido; batería no negativa; detener el patrullaje no se contabiliza como cobertura total.
- Cada método ejecuta su implementación; Gurobi se contrasta con un oráculo pequeño y se prueban errores de licencia y límites. Coincidencias de geometría se declaran.
- UI: recorrido listo → iniciar → aparición → detección → cuatro alternativas → decisión → destino y aterrizaje; controles on/off y exportación coherentes.
- Regresión de planificación personalizada, filtros/capas, reproductor y escenarios anteriores. Actualizar esquemas y lectores de exportaciones sin presentar silenciosamente un formato viejo como nuevo.

No mezclar la resiliencia actual de cobertura con el éxito del nuevo servicio de detección. Conservar la métrica histórica identificada y definir por separado detección, reporte y llegada segura bajo escenarios compartidos.

## Orden de implementación

1. Contratos y catálogo de recorridos.
2. Generador de focos y transición de estados.
3. Recuperación desde posición real y evaluación de destinos.
4. Cuatro técnicas de recuperación con restricciones comunes.
5. API, selección automática e interfaz.
6. Pruebas integradas, aceptación y documentación.

## Criterio de finalización

Desde la app se elige un recorrido predefinido y se inicia sin marcar un foco. Un escenario reproducible hace aparecer un incendio durante la vigilancia; el dron lo observa posteriormente, registra la detección y evalúa las cuatro técnicas desde su estado real. Se puede comprobar la comparación origen/estación, la decisión y el aterrizaje, con recursos consistentes y exportación completa. También funcionan los casos sin incendio, sin detección y sin retorno seguro. Video y presentación permanecen pospuestos.
