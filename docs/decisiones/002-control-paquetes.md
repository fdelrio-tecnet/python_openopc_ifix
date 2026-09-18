# ADR 002 — Paquetes condicionados por revisión

Fecha: 2026-09-18. Estado: implementado en almacenamiento, integración OPC pendiente.

## Decisión

Cada resultado incluye revisión previa del mismo tramo/ciclo, versión geométrica
y revisión de catálogo obtenidas antes de calcular. Se comprueban bajo bloqueo
de escritura. Un paquete atrasado no puede reemplazar uno nuevo con su token viejo.
Los cambios de tags también invalidan cálculos en vuelo.

Se deduplica solo el último ID/contenido. No se crea un historial ilimitado de IDs.
Las fechas UTC deben avanzar para resultados/observaciones distintos; rechazar
ambigüedades evita que eventos atrasados oculten errores más recientes. Un ajuste
de reloj hacia atrás exige diagnóstico operativo.

El resultado, su firma predictiva y adquisición válida se confirman juntos. La
verificación sin cambios actualiza solo adquisición. Publicar/consumir es otra fase.

## Alternativas y consecuencias

Usar únicamente timestamps depende del reloj y no identifica cálculos sobre una
geometría vieja. Usar solo ID no detiene reintentos antiguos sin un historial.
El token de revisión limita el estado almacenado; a cambio el productor debe
releer/recalcular ante conflicto y conservar el token original en los reintentos.

No es aislamiento de seguridad entre procesos del mismo usuario. Los productores
deben utilizar la API, sin modificar tablas directamente ni inventar tokens.

Contrato completo: [repositorio de resultados](../repositorio_resultados.md).
