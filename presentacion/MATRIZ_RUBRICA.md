# Matriz de cierre de fase 2

Entrega actual: fase2_valparaiso_diagnostico.pptx, 22 principales y 14 anexos.
Evidencia adicional: evidencia/diagnostico_fase2_2026-10-19/.
Referencia de criterios: matriz de 60 puntos del plan_accion_fase2.pdf aportado por
el usuario. Las imágenes originales no están archivadas en este repositorio; esta
matriz no se presenta como una nueva verificación literal de ellas ni como nota otorgada.

| ID | Pts | Criterio | Láminas | Evidencia y juicio crítico | Estado técnico | Aceptación docente |
|---|---:|---|---|---|---|---|
|1|2|Docker y extensiones|3,22|Pruebas y main con volumen nuevo. Runner GitLab pendiente.| Comprobado | Por evaluar |
|2|2|Diagrama y SQL|4–5,23–24|29 entidades, PK/FK reales; SQL y migraciones intactos. Diagrama completo en BD/.| Comprobado | Por evaluar |
|3.1|6|Cuatro ET metadata|8–9,26–29|Fuentes, ejecutables y proyecciones JSON reales; se indican campos omitidos.| Comprobado | Por evaluar |
|3.2|2|Cuatro cargas metadata|10,26–29|Cargador inequívoco y conteos reconciliados.| Comprobado | Por evaluar |
|4.1|6|Cuatro ET amenazas|11–12,30–33|Registros reales; FIRMS vacío se conserva sin inventar focos.| ET snapshot probado; descarga S6 bloqueada por DNS | Por evaluar |
|4.2|2|Cuatro cargas amenazas|13,30–33|Cargas probadas, originales y hashes disponibles.| Comprobado | Por evaluar |
|5.1|3|Cuatro modelos de falla|14,33,35|A4 añade exclusión preventiva opcional. No es fuego activo; interpretación docente pendiente.| Política preventiva opcional comprobada | Confirmación 5.1 pendiente |
|5.2|2|Costos y exclusiones|15,35|Metros/segundos y ejemplos ejecutados. Los fixtures sintéticos están identificados.| Comprobado | Por evaluar |
|6.1|3|Preferencias|15,33|Presupuesto, viento, desvío y clase histórica efectivos, con pruebas de UI/exportación.| Comprobado | Por evaluar |
|6.2|2|Defaults|15,22|1200 s, 8 m/s, 1,20 y política histórica desactivada; compatibilidad probada.| Comprobado | Por evaluar |
|7.1|4|Algoritmo y artículo|16|Yen 1971, título y DOI. No atribuye al artículo una garantía de resiliencia.| Comprobado | Por evaluar |
|7.2|6|Funcionamiento|17,36|Hasta nueve pares, exclusiones, reserva, retorno y búsqueda limitada.| Comprobado | Por evaluar |
|8|4|Dos rutas Dijkstra|18,34|SQL ejecutado y resultado, costo km; D2 distinta por exclusión de arcos de D1.| Comprobado | Por evaluar |
|9|4|Dos opciones propuestas|19,36|Ejemplo real con dos; el lote informa cuando hay una o ninguna.| Comprobado | Por evaluar |
|10|6|Métrica implementada|20–21|120 casos fijados, 12000 escenarios, misiones congeladas y denominador común.| Comprobado | Por evaluar |
|11.1|4|Comparación en mapa|18–19,21|Cuatro opciones y controles individuales D1/D2/P1/P2. Se informa proximidad/solapamiento.| Comprobado | Por evaluar |
|11.2|2|Diferencial|21|+1,65 pp medio; default +0,03, clase 4 +3,27. Incluye dos empeoramientos.| Comprobado | Por evaluar |
|Total|60|Cobertura técnica documentada||Sin autoasignación de puntaje.| Cobertura documentada | Evaluación externa |

Infraestructura, main, Leaflet, diccionarios y los nueve JSON quedan en 3,6–7,25–33.
Los anexos son contenido visible de la presentación, no solo notas o enlaces al código.
Los ejemplos de mapas 18–19 conservan el caso retrospectivo anterior; el lote nuevo usa
horas posteriores a adquisición y no filtra por viento favorable. Las condiciones
siguen siendo estáticas durante cada misión.

Pendientes externos: confirmación del criterio 5.1 y revisión de la rúbrica original,
conectividad DNS de DGAC y entrega manual en Canvas por el equipo. La conexión Git
está resuelta y queda fuera de este incremento. No se acredita una ejecución CI remota nueva.
No se exige inventar un diferencial positivo ni se garantiza nota máxima.

Diagnóstico nuevo: 128 pruebas sin omisiones; 120/120 solicitudes idénticas en
rutas, costos y métricas. En 36 se separan motivos principales y simultáneos:
AIP 32/48, historia desconocida 12/24, meteorología 40/40 y presupuesto 23/23.
No sumar simultáneos. El oráculo no halló contradicciones en este lote.
La consulta docente está preparada y no enviada en
`evidencia/diagnostico_fase2_2026-10-19/CONSULTA_DOCENTE.md`.
