# Registro de cambios

## Sin versión publicada

### Etapa 3a — preparación de publicación (2026-09-18)

- Modelo lógico de tres nodos por tramo, con claves estables candidatas y nombres actuales.
- Preparación pura de disponibilidad/fechas/valores desde snapshot completo, sin red.
- Vencimiento configurable, control de contexto, serie íntegra de 72 y aislamiento
  de errores locales. Redondeo solo para publicación; SQLite conserva precisión.
- 15 pruebas nuevas; 85 en total. Prueba productor SQLite temporal → preparación.
- ADR 003 y documentación actualizados. Biblioteca UA, endpoint y pruebas IGS
  todavía pendientes; no se modificó el calculador ni la base de datos operativa.

### Etapa 2c — resultados y cierre de almacenamiento (2026-09-18)

- Esquema v3: resultados actuales, series completas de 72 y adquisición, con índices.
- Guardado atómico de resultados/firmas/estado, precisión sin redondeo, validación
  de versiones geométricas y catálogo, token de revisión y reintentos idempotentes.
- Adquisición sin cambios separada del cálculo, errores sin borrar último valor.
- Snapshots completos/incrementales coherentes para el futuro publicador.
- Migración v1/v2 a v3 con backup, preservando la API histórica v1 → v2.
- Consola local para crear/migrar, validar/importar JSON y mostrar estado.
- ADR 002 y documentación de contratos; 70 pruebas offline satisfactorias.
- Sin integración del calculador con SQLite ni implementación OPC UA en esta etapa.

### Etapa 2b — catálogo y geometrías

- Esquema v2 con tablas de catálogo y geometrías, índices por revisión y unicidad
  de base-tags activos normalizados con casefold.
- API Python de validación/importación completa: altas, cambios, inactivaciones,
  versiones geométricas y discordancias informadas sin rechazo global.
- Reimportación idéntica sin cambios; rollback de filas y revisión ante fallas.
- Parser reutilizable desde objeto, sin cambiar estructura ni contenido del JSON.
- Migración explícita v1 a v2 con backup obligatorio, sin recrear bases existentes.
- 12 pruebas nuevas, 51 en total; documentación actualizada. Consola administrativa,
  resultados, snapshots y conexión del calculador a SQLite todavía pendientes.

### Etapa 2a — infraestructura SQLite

- Agregado paquete `almacenamiento` con creación exclusiva, identificación/versión
  de esquema, conexiones reutilizables y transacciones con rollback.
- WAL, synchronous FULL, lectura protegida y timeout de bloqueo configurable.
- Esquema v1 limitado a metadatos; tablas e importadores de negocio siguen pendientes.
- 13 pruebas SQLite nuevas; 39 pruebas offline en total. No se accedió a iFIX.
- Documentadas API, límites, cierre, recuperación y futura migración explícita.
- Ignorados archivos auxiliares SQLite WAL/SHM/journal para no versionar datos locales.

### Limpieza y organización

- Retiradas las capturas obsoletas `arbol_ifix.json`, `arbol_ifix.txt`, `tags.txt`
  y registrada la eliminación preexistente de `python_scheduler.zip`. Se pueden
  recuperar desde el historial Git.
- Movidos los ensayos OPC reales de `tests/` a `herramientas/manuales/`, con nombres
  que no se descubren como pruebas automáticas y una guía de sus efectos.
- Movida la guía histórica OpenOPC a `docs/referencias/`; enlaces actualizados.
- La suite completa puede descubrirse en `tests/` sin importar OpenOPC real.
- Entornos y recursos locales ignorados (`.venv`, `.idea`, `openopc/`) conservados.

### Base documental — 2026-09-17

- Incorporados README principal, reglas de mantenimiento y documentos de
  arquitectura, modelo de datos, importación, instalación, operación y pruebas.
- Registrada la decisión de usar SQLite compartido local y JSON para importar
  geometría; HTTP y Named Pipes no forman parte del diseño inicial.
- Documentado el flujo hacia IGS/iFIX/Operations Hub y la diferencia entre
  resultados guardados, publicados y consumidos.
- Identificadas las partes planificadas, las implementadas y las verificaciones
  pendientes. Esta entrega no implementa SQLite ni el servidor OPC UA.

### Cambios de código previos a la base documental

- Parser: reúne tramos directos y de subsistemas; rechaza IDs y salidas duplicadas.
  Se verificaron 51 IDs del archivo real durante la revisión de septiembre de 2026.
- Escritura predictiva: confirma 72 respuestas únicas por tag y lote, conserva la
  firma ante fallos y respeta el tamaño de lote.
- Lecturas y cálculos: rechazo de valores no finitos, Good configurable exigido
  por defecto, validación de 72 puntos y limpieza del estado antes de leer.
- Agregada constante compartida y 26 pruebas automáticas sin iFIX.
- `main.py` continúa como stub. El flujo SQLite/OPC UA todavía no está integrado.

Este registro describe el estado de trabajo; no implica una release o commit publicado.
