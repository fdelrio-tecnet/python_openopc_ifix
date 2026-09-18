# Repositorio de resultados — etapa 2c

[Inicio](../README.md) · [SQLite](almacenamiento.md) · [Modelo](modelo_datos.md)

Implementado en [repositorio.py](../almacenamiento/repositorio.py), exportado por
`almacenamiento`. Solo biblioteca estándar y constante compartida de 72 puntos.
No ejecuta fórmulas, no usa OpenOPC y no publica en UA. El calculador existente
todavía escribe mediante su ruta OPC DA; esta API es el destino para su integración futura.

## Paquete y control de concurrencia

`guardar_actual(conn, *, tramo_id, geometria_version, catalogo_revision,
revision_anterior, actualizacion_id, calculado_en, presion_promedio_bar_abs,
linepack_sm3)` guarda la pareja completa y el estado de adquisición válido juntos.

`guardar_prediccion` recibe los mismos campos comunes, más `presiones` y `linepacks`
en vez de los dos escalares. Exige dos listas/tuplas de **exactamente 72 números**.
Presiones absolutas positivas, linepack no negativo; booleanos, NaN e infinitos
rechazados. No comprueba que los linepacks correspondan matemáticamente a las
presiones: esa responsabilidad y sus pruebas siguen en `calculos.py`.

Las funciones no redondean valores al guardar. El futuro publicador debe redondear
PPROMEDIO a 3 decimales y LINEPACK/LINEPACK_PRED a 2, conservando lo almacenado.

Antes de calcular, obtener un snapshot y conservar:

- `geometria_version`: versión de geometría del tramo, activa.
- `catalogo_revision`: revisión de la fila del tramo, activo. Cambiar tags también
  invalida cálculos en vuelo, aunque la geometría no cambie.
- `revision_anterior`: revisión del resultado del **mismo tramo y ciclo**, no la
  revisión global. Usar 0 si todavía no existe.

Cerrar la lectura, calcular fuera de transacciones y guardar el paquete. Dentro
de BEGIN IMMEDIATE se verifica todo antes de escribir. Un cambio concurrente
produce `ConflictoActualizacion` (subclase de ValueError): releer y recalcular;
no reemplazar automáticamente el token para forzar un cálculo antiguo.

`actualizacion_id` es una cadena no vacía generada por el productor (UUID sugerido)
y se conserva al reintentar. Solo el **último paquete** se deduplica: mismo ID y
contenido devuelve su revisión con `repetido=True`, sin renovar timestamps ni
borrar un error posterior. Mismo ID con otro contenido se rechaza. Un paquete
anterior al último no puede sobrescribirlo porque conserva una revisión antigua.
No hay historial ilimitado de IDs ni protección contra productores que falsifiquen
tokens; cada variable sigue teniendo un único productor responsable.

Fechas: texto ISO 8601 con zona, normalizado a UTC con microsegundos. Nuevo paquete
debe tener fecha posterior tanto al cálculo previo como al último intento de
adquisición. Fechas iguales para paquetes distintos son ambiguas y se rechazan.
Si el reloj local retrocede, los paquetes pueden rechazarse hasta corregirlo;
el productor debe registrar el conflicto, no fabricar fechas nuevas para datos viejos.
En esta etapa `calculado_en` también sirve como fecha del intento válido; el futuro
coordinador debe guardar en orden y no registrar primero el mismo intento por separado.

Salida: `{"revision": entero, "repetido": bool}` después de COMMIT. Contrato inválido:
ValueError; conflicto: ConflictoActualizacion; fallas de SQLite se propagan con rollback
completo de resultado, firma, estado y revisión. No se cierra la conexión del llamador.

## Predicción y firma

La firma se deriva en el repositorio, no la aporta el productor: 72 enteros en
centésimas truncados hacia cero desde la representación decimal de cada número.
Así 1.15 produce 115, evitando el efecto binario de `int(1.15 * 100)`. El helper
`firma_presiones` admite negativos para comparación (-1.159 → -115), aunque guardar
una predicción rechaza presiones no positivas. Los valores originales permanecen
completos en `presiones_json`; los otros arrays son `linepacks_json` y `firma_presiones_json`.

Al integrar, comparar firma con corte en la primera diferencia y recalcular si
falta resultado, cambia geometría o catálogo. Si no hay cambios, registrar una
adquisición válida para ese resultado. La lógica de decisión del calculador no se
cambia aquí: su firma OPC DA actual no se migra automáticamente al nuevo destino.

El COMMIT conjunto de los 72 valores y firma es la confirmación de almacenamiento.
No confirma publicación UA, persistencia PDB ni consumo por iFIX.

## Adquisición sin reescritura del resultado

`registrar_adquisicion(conn, *, tramo_id, ciclo, observado_en, estado,
detalle=None, resultado_revision=None)` admite ciclos `actual`/`predictivo` y estados:

- `valido`: requiere revisión exacta del resultado actual y contexto geométrico/
  catálogo todavía vigente. Actualiza la última verificación sin tocar el array.
- `error_lectura`, `error_calculo`: no confirma resultado; conserva último cálculo
  y fecha de la última lectura válida. Detalle opcional de texto; nunca almacenar
  credenciales ni secretos. No requiere geometría utilizable, sí tramo activo.

Rechaza observaciones atrasadas o distintas con la misma fecha. Repetición exacta
no incrementa revisión. Fallas de guardado no se registran como guardado exitoso:
el coordinador deberá emitir logging externo si SQLite no está disponible.

## Snapshot y consulta incremental

`leer_snapshot(conn, desde_revision=0)` devuelve:

```text
revision: límite global del snapshot
tablas:
  tramos: [filas como diccionarios]
  geometrias: [...]
  resultados_actuales: [...]
  predicciones_linepack: [... arrays en texto JSON ...]
  estado_adquisicion: [...]
```

El límite y todas las filas se leen en una transacción consistente. Desde 0 devuelve
el último estado completo; otro cursor devuelve filas `(cursor, límite]`, incluidos
inactivos. El publicador debe conservar su snapshot local y aplicar deltas por clave;
solo avanzar cursor tras publicar el conjunto. Si falla, reintentar sin omitir cambios.
Nunca mantener la transacción durante operaciones UA. No hay historial: un valor
intermedio reemplazado antes del sondeo no necesariamente será publicado.

Tras reiniciar o restaurar cargar **siempre desde 0**. Un cursor mayor a la revisión
actual es error, pero eso no detecta todos los restores: no persistir el cursor.

**Snapshot no equivale a valores publicables.** Puede contener cálculos antiguos:
el futuro publicador debe comprobar tramo/geom activos, versiones coincidentes,
estado válido asociado a la revisión del resultado y antigüedad de adquisición.
Debe evaluar vencimiento incluso si no llegan cambios. No se genera calidad UA
ni se marca como vigente un resultado solo por estar persistido.

## Verificación y límites

Pruebas de atomicidad, 72 puntos, firmas, precisión, idempotencia, resultados
atrasados, cambio de contexto, verificación sin cambios, rollback y snapshots
con escritor concurrente. Dos procesos independientes compiten por el mismo token:
uno guarda y el otro recibe conflicto. No es un benchmark ni una prueba prolongada.

Toda escritura es por tramo/ciclo; no hay transacción de resultados para todos
los tramos juntos. JSON predicho exige tamaño 72; catálogo/snapshots se materializan
en memoria. El productor/publicador futuro debe medir latencia, memoria y tamaño
de lotes en el equipo real. Python 3.9 x86 y COM siguen pendientes de verificación.
