# Operación, fallas y recuperación

[Inicio](../README.md) · [Importaciones](configuracion_importaciones.md) · [Pruebas](pruebas.md)

## Estado

Procedimiento objetivo; coordinador pendiente, servidor propio disponible en ensayo.
Existe [almacenamiento SQLite](almacenamiento.md) con importadores de catálogo y
geometrías, resultados, adquisición, snapshots y consola administrativa. Migrar
v1/v2 exige backup. No ejecutar `python_scheduler/main.py` esperando servicio: imprime
`Main` y finaliza. Los scripts manuales existentes pueden escribir en iFIX.
Hay [comando de arranque UA de ensayo](servidor_opcua_ensayo.md), con configuración
portable y sin instalación automática en el equipo de destino. Ante fallo global
intenta invalidar y cierra: no implementa todavía los reintentos de la tabla futura.

## Arranque previsto

1. Comprobar configuración operativa y versión de esquema.
2. Inicializar/importar datos mediante administración cuando corresponda; no
   recrear ni reimportar automáticamente una base existente.
3. Arrancar publicador UA, cargar snapshot de SQLite y evaluar disponibilidad.
4. Arrancar calculador, cargar catálogo/geometría y conectar OpenOPC.
5. Completar primera lectura actual antes de habilitar ciclo predictivo. Un tramo
   inválido no debe bloquear todos los demás; exigir geometría válida por tramo.

El calculador puede guardar aunque el publicador esté detenido. Si la base no
está disponible, no puede confirmar guardado. Al reiniciar el publicador reconstruye
su estado desde la base, por lo que no depende de una nueva firma de presiones.

## Ciclos y disponibilidad

Actual cada 30 segundos y predictivo cada 600, coordinados con `time.monotonic()`
en un hilo para OpenOPC. Evitar acumulación de ciclos atrasados. No compartir el
cliente COM entre hilos ni abrirlo/cerrarlo por cada operación.

Una serie sin cambios recibe una actualización de verificación válida. El servidor
evalúa vencimientos aunque no haya revisiones nuevas. Umbrales propuestos iniciales:
2 minutos desde cálculo actual y 30 minutos desde verificación predictiva válida.
La función de preparación ya implementa estos umbrales configurables e inclusivos;
el proceso de ensayo ya los reevalúa en cada sondeo y aplica StatusCodes UA.

Conservar último valor y fechas, marcándolo como desactualizado/no disponible
cuando corresponda. Nunca presentar cero inicial como resultado válido.
La traducción a StatusCode UA está [documentada](servidor_opcua_ensayo.md);
su interpretación como calidad iFIX queda pendiente de integración.
No renovar timestamps originales solo por reiniciar o republicar.

## Tratamiento previsto de fallas

| Falla | Respuesta |
|---|---|
| Tag local inválido/Bad | Marcar tramo/serie; continuar otros; no publicar cálculo inválido |
| Excepción global OPC DA | Cerrar cliente, espera acotada y reconectar |
| Cambio de geometría durante cálculo | Rechazar resultado con versión anterior y recalcular |
| SQLite ocupado | Espera/reintento acotados; no mantener transacción durante OPC |
| Error de disco o guardado | No confirmar paquete; registrar y reintentar según política |
| Publicación UA fallida | No omitir revisión pendiente; reintentar |
| Reinicio del publicador | Cargar último estado y reevaluar vigencia |
| Importación inválida | Mantener datos activos previos y reportar motivo |
| Discordancia de IDs entre JSON | Reportar; permitir carga; tramo sin geometría no calcula |

No se reenvía un histórico completo de ciclos perdidos: el contrato es último estado.
La confirmación de SQLite no acredita consumo en iFIX. Verificar por lectura real
durante las pruebas de puesta en marcha.

## Logs y cierre

Plan: logging rotativo por proceso; inicio/cierre, versión de esquema, duración,
conteos de tramos, errores por fase, revisiones y datos vencidos. No registrar
cada punto exitoso ni arrays completos en cada ciclo normal.

Cierre: detener nuevos trabajos, finalizar/cancelar operaciones con criterio
documentado, cerrar cliente OPC y conexiones SQLite. No hay rollback de un COMMIT
ya confirmado por el hecho de cerrar el publicador.

## Backups y recuperación

Antes de migrar o restaurar, detener o coordinar productores y publicador. Utilizar
backup consistente de SQLite (API de backup o procedimiento con base cerrada).
No copiar solo el `.db` activo ignorando WAL. Conservar también configuración y
versión del software. Existe backup dentro de `migrar_base`/`migrar-base`; no hay comando
general de backup/restauración. Ver [procedimiento de migración](almacenamiento.md).

Restaurar una base requiere reiniciar cursores y validar esquema, fechas,
geometrías y disponibilidad. No confundir datos restaurados con lecturas nuevas.
Retención de backups y ubicación final pendientes del despliegue.

## Conflictos de paquetes y reloj

El repositorio rechaza revisiones antiguas y cambios de geometría/catálogo durante
el cálculo. Releer y recalcular; nunca sustituir el token de un paquete viejo para
forzar su aceptación. Un reintento conserva ID, datos, fechas y token originales.
Las fechas de paquetes distintos deben avanzar: un retroceso del reloj local
requiere diagnóstico, no inventar timestamps para eludir el control.
Consultar [contrato completo](repositorio_resultados.md).
