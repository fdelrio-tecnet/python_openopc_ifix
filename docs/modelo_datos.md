# Modelo de datos y consistencia

[Inicio](../README.md) · [Arquitectura](arquitectura.md) · [Importaciones](configuracion_importaciones.md)

## Estado

Modelo lógico propuesto para la siguiente etapa. No existe todavía esquema SQL,
base inicial ni API de almacenamiento. Los nombres siguientes orientan el diseño;
al implementar deberán documentarse tipos, restricciones, índices y migración.

## Tablas

| Tabla | Clave lógica | Campos y propósito |
|---|---|---|
| `tramos` | `id` | `base_tag`, `presion_ingreso_tag`, `presion_egreso_tag`, `activo`, `revision`: catálogo plano importado |
| `geometrias` | `tramo_id` | `diametro_exterior_pulgadas`, `espesor_milimetros`, `longitud_metros`, `activa`, `version`, `actualizada_en`, `revision` |
| `resultados_actuales` | `tramo_id` | `presion_promedio_bar_abs`, `linepack_sm3`, `geometria_version`, `calculado_en`, `actualizacion_id`, `revision` |
| `predicciones_linepack` | `tramo_id` | `presiones_json`, `linepacks_json`, `firma_presiones_json`, `geometria_version`, `calculado_en`, `actualizacion_id`, `revision` |
| `estado_adquisicion` | `tramo_id`, `ciclo` | `ultimo_intento_en`, `ultima_lectura_valida_en`, `estado`, `detalle`, `revision`; ciclo actual o predictivo |
| `metadatos` | clave | Versión de esquema y contador global de revisiones |

La geometría admite IDs ausentes del catálogo. No imponer una referencia que
impida cargarlos. Los resultados solo deben aceptarse para tramos activos con
geometría utilizable. `base_tag` y salidas de tramos activos deben ser únicos
según la normalización definida en el parser.

No hay tablas de histórico en la primera versión. La inactivación conserva filas;
no borra físicamente información durante una importación normal. Revisar más
adelante la retención de IDs inactivos si el catálogo cambia con frecuencia.

## Unidades, precisión y series

- Geometría: pulgadas, milímetros y metros explícitos en nombres de campos.
- PPROMEDIO y presiones predictivas: bar absolutos. Linepack: Sm³.
- Valores numéricos finitos; booleanos, NaN e infinitos rechazados.
- Conservar precisión de cálculo en almacenamiento; redondear al publicar
  PPROMEDIO a 3 decimales y LINEPACK/LINEPACK_PRED a 2.
- Arrays JSON de exactamente 72 números, ordenados. No usar serialización de
  objetos Python. No requerir extensiones JSON de SQLite para validación.
- Presiones originales preservadas para trazabilidad del último cálculo, sin
  convertir la base en una fuente productora de PPROMEDIO_PRED.
- Firma: 72 enteros, truncamiento hacia cero a centésimas, solo para comparación.
- Las fechas de operación se proponen en UTC con formato consistente. El reloj
  monotónico se usa para intervalos del proceso, nunca como fecha persistida.
- No inventar fechas del horizonte: la referencia de F_00 está pendiente.

## Transacciones e invariantes

1. La pareja actual se reemplaza completa, en una transacción.
2. La predicción se reemplaza solo con 72 puntos válidos, junto con su firma.
3. Una importación válida se activa completa; una inválida no cambia datos activos.
4. Obtener una copia de geometría/versiones, cerrar lectura y calcular fuera de
   cualquier transacción de escritura.
5. Al guardar, comprobar en la misma transacción que tramo y geometría continúan
   activos y que la versión utilizada coincide. Rechazar resultados obsoletos.
6. Reimportar geometría idéntica no cambia su versión. Valores o activación
   distintos sí la cambian.
7. Recalcular predicción si cambia firma, versión geométrica o falta resultado.
8. Errores de adquisición/cálculo actualizan estado, sin reemplazar el último
   resultado válido con cero ni con una serie parcial.

Cada paquete incluye `actualizacion_id`. Un reintento idéntico del último paquete
debe reconocerse sin generar una actualización falsa; reutilizar el mismo ID con
otro contenido debe rechazarse. Antes de implementar hay que fijar la regla para
paquetes retrasados y cómo evitar que un reintento antiguo reemplace uno más nuevo.
No se promete deduplicación histórica ilimitada usando solo una fila por tramo.

## Revisiones y publicación

Una transacción obtiene/incrementa el contador global y asigna esa revisión a las
filas modificadas, todo dentro de la misma transacción. Una transacción puede
actualizar varios tramos con una misma revisión.

El publicador obtiene, dentro de una transacción de lectura, una revisión límite
y las filas entre su cursor y ese límite. Cierra la transacción antes de operar
con UA. Avanza el cursor cuando publica el conjunto; si falla, conserva el trabajo
pendiente/reintenta sin omitir cambios. Las repeticiones deben ser seguras.

Al arrancar se carga un snapshot completo. No es necesario persistir el cursor
del publicador: SQLite mantiene el último estado. Actualizaciones intermedias
pueden sobrescribirse antes de que sean consumidas; no se garantiza historización
de cada ciclo en iFIX.

Los vencimientos se evalúan también cuando no cambian revisiones: el paso del
tiempo no genera por sí solo una nueva fila. Registrar una verificación predictiva
válida sin cambios mantiene viva la adquisición, sin reescribir el array.

## Guardado, publicación y consumo

`COMMIT` confirma almacenamiento, no actualización de UA ni adquisición en iFIX.
La firma del calculador podrá consolidarse al guardar; la publicación será
responsabilidad del servidor. Esto sustituye el criterio actual de 72 respuestas
Success de OPC DA, únicamente cuando se implemente el nuevo destino.

Una fecha reciente de lectura no basta para validar un resultado: también debe
existir cálculo válido, coincidir la geometría y no haber un estado incompatible.
Un resultado recuperado después de reiniciar conserva sus fechas originales.

## Compatibilidad y migraciones

Plan: versión explícita del esquema; inicialización de una base nueva diferenciada
de migración. No recrear una base existente para actualizarla. Procesos con esquema
incompatible deben fallar con diagnóstico claro antes de escribir.

Antes de la primera migración se debe definir backup consistente, actualización
coordinada de procesos, validación posterior y recuperación. Las capacidades SQL
usadas deben probarse con la versión SQLite incluida en ambos runtimes Python.
