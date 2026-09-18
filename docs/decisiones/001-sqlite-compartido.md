# ADR 001 — SQLite compartido local

Fecha: 2026-09-17. Estado: **decisión aceptada; infraestructura implementada,
catálogo/geometría/resultados implementados; integración OPC pendiente**.
Ver [etapa 2](../almacenamiento.md).

## Contexto

Los productores Python y el servidor OPC UA correrán en el mismo equipo y con
el mismo usuario. OpenOPC exige Python 3.9 x86; el servidor UA tendrá otro entorno.
Se desea evitar HTTP/puertos adicionales y permitir futuros productores de otras
variables. Solo se necesita último estado, no histórico. La geometría se prepara
en JSON y debe sobrevivir reinicios.

## Decisión

- SQLite en disco local es fuente operativa e intercambio entre procesos.
- JSON compartido de tramos permanece intacto; catálogo importado en la base.
- JSON de geometría solo se importa/actualiza explícitamente.
- Módulo común compatible con Python 3.9 controla validación y transacciones.
- Publicador UA consulta revisiones; inicialmente no escribe en SQLite.
- Resultado guardado y resultado publicado son estados diferentes.
- Mantener último estado, admitiendo reemplazo de ciclos intermedios.

## Alternativas consideradas

| Alternativa | Razón para no elegirla inicialmente |
|---|---|
| HTTP local | Puerto de escucha adicional y una interfaz innecesaria para este alcance |
| Named Pipes | Viable sin TCP, pero requiere protocolo/reconexión y no conserva mensajes tras reiniciar |
| Escritura directa UA desde productores | Requiere cliente compatible con entorno x86 y no resuelve por sí sola almacenamiento |
| JSON compartido para resultados | Coordinación, reemplazo seguro y confirmación más complejos con varios productores |
| Base cliente-servidor | Servicio y administración adicionales sin necesidad demostrada |

## Consecuencias

Ventajas: intercambio entre runtimes, operación independiente durante parada del
publicador, transacciones y ausencia de servicio de base de datos separado.

Costos: esquema compartido versionado, sondeo con latencia, escrituras serializadas,
gestión de backups y archivos auxiliares. Una confirmación de COMMIT no asegura
que IGS/iFIX haya leído. No hay aislamiento por productor bajo un usuario común.

Revisar esta decisión si aparecen dispositivos remotos, alta concurrencia de
escritura medida, necesidad de entregar todos los eventos, redundancia o permisos
por productor. No migrar por un número hipotético de tramos sin mediciones.

## Referencias

- [Usos apropiados de SQLite](https://www.sqlite.org/whentouse.html).
- [WAL y concurrencia](https://www.sqlite.org/wal.html).
- [Modelo lógico local](../modelo_datos.md).
- [Arquitectura y flujo](../arquitectura.md).
