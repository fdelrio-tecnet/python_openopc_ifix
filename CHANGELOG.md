# Registro de cambios

## Sin versión publicada

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
