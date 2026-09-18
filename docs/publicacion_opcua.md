# Preparación de publicación — etapa 3a

[Inicio](../README.md) · [Arquitectura](arquitectura.md) · [Resultados SQLite](repositorio_resultados.md)

## Estado real

Existe un modelo lógico de nodos y una función pura que prepara valores, fechas y
disponibilidad desde un snapshot completo. La etapa 3b agrega un
[servidor y cliente UA de ensayo](servidor_opcua_ensayo.md) en entorno separado.
No hay perfil con certificados ni validación en IGS/servidor de destino todavía.
No se modifica SQLite, el calculador o iFIX. Las pruebas usan datos sintéticos;
una de ellas recorre productor SQLite temporal → snapshot → preparación.

## Archivos y API

- [nodos.py](../servidor_opcua/nodos.py): `DefinicionNodo` y `definir_nodos(tramo_id, base_tag)`.
- [publicacion.py](../servidor_opcua/publicacion.py): `PoliticaVigencia`, `PublicacionNodo`
  y `preparar_publicacion(snapshot_completo, *, ahora, politica=PoliticaVigencia())`.

Dataclasses inmutables, biblioteca estándar y Python 3.9 compatible en sintaxis.
El helper compartido de firma mantiene el mismo contrato que almacenamiento.
No se hacen lecturas de base, esperas, consultas de reloj implícitas ni operaciones
OPC dentro de estas funciones. El llamador suministra un datetime con zona para
que la decisión sea reproducible y testeable; se normaliza a UTC.

## Nodos lógicos por tramo

| Sufijo | Nombre de negocio | Tipo previsto | Dimensión | Redondeo |
|---|---|---|---|---|
| PPROMEDIO | `<base_tag>_PPROMEDIO` | Double | Escalar | 3 decimales |
| LINEPACK | `<base_tag>_LINEPACK` | Double | Escalar | 2 decimales |
| LINEPACK_PRED | `<base_tag>_LINEPACK_PRED` | Double | 72 valores | 2 decimales |

Todos se definen como no escribibles; el adaptador UA aplica permisos de solo
lectura, comprobados mediante cliente real local. PPROMEDIO_PRED sigue siendo
entrada ajena y no se vuelve a exponer aquí. Geometrías quedan en SQLite; su
exposición opcional no está implementada en esta parte.

Clave lógica: `tramos/<id escapado>/<sufijo>`. Se escapan separadores/porcentajes
para evitar colisiones. Usa el ID, no el orden ni el base-tag; cambiar base-tag
cambia nombre visible y revisión del catálogo, pero no esta clave. Los nombres
no incluyen `FIX.` ni `.F_CV`: son nombres previstos UA, no Item IDs OPC DA.

Las claves se usan como identificador string UA de ensayo, con namespace URI
configurable; su aceptación en IGS y AR sigue pendiente. Los nombres actuales
de PDB no se cambian automáticamente. Planificar organización por tramo para que
un registro inactivo y otro activo que reutilice base-tag no colisionen por nombre.

## Disponibilidad

Cada `PublicacionNodo` incluye definición, valor, disponibilidad, motivo,
`calculado_en`, `verificado_en` y `revision_resultado`.

| Caso | Estado interno | Valor preparado |
|---|---|---|
| Contexto y adquisición válidos, dentro del plazo | `disponible` | Valor/serie redondeados |
| Se alcanza el plazo configurado | `vencido` | Último valor íntegro, **no vigente** |
| Error de lectura o cálculo | `no_disponible` | Último valor íntegro, **no válido** |
| Sin resultado/adquisición, contexto distinto, inactivo o datos inválidos | `no_disponible` | `None` |

Nunca se rellenan faltantes con cero. Un escalar 0 solo puede aparecer como valor
numérico real admitido (por ejemplo linepack 0), no como sustituto de disponibilidad.
Un consumidor no debe utilizar el valor sin mirar su estado. Los estados aquí
son del proyecto; **no son StatusCodes OPC UA ni calidad iFIX**. La traducción
[implementada en el adaptador](servidor_opcua_ensayo.md) usa Null para Bad, aunque
la preparación conserve un último valor; su interpretación en IGS queda pendiente.

Para habilitar disponibilidad se comprueba: tramo/geometría activos, versión de
geometría y revisión de catálogo coincidentes, estado válido referido al mismo
resultado, revisiones consistentes, fechas con zona y orden temporal. No se
recalcula la geometría ni el linepack: se confía en las validaciones de importación
y cálculo; esto no es una auditoría de integridad de toda la base.

La serie exige 72 presiones positivas y 72 linepacks no negativos y finitos, además
de firma coherente. Una serie corrupta o incompleta invalida ese ciclo completo,
sin truncarla ni publicar puntos de otra generación. El ciclo actual valida la
pareja completa. Una falla numérica/temporal local no detiene otros tramos.

Errores de estructura global (tabla faltante, claves duplicadas, identidad sin ID
o base-tag) producen ValueError: no se debe presentar ese snapshot como válido.
Motivos locales incluyen `sin_resultado`, `tramo_inactivo`,
`geometria_no_disponible`, `contexto_modificado`, `sin_adquisicion`,
`adquisicion_no_corresponde`, `error_lectura`, `error_calculo`, `fecha_futura`,
`datos_invalidos`, `vigencia_agotada` y `ok`. No exponen detalles sensibles del log.

## Tiempo y reinicios

- Actual: vence desde la fecha del **cálculo**, inicialmente a los 120 segundos.
  Una verificación posterior sin nuevo cálculo no extiende su vigencia.
- Predictivo: vence desde la **última verificación válida**, inicialmente a los
  1800 segundos. Una predicción puede seguir igual durante una hora o más sin
  necesidad de reescribir sus linepacks.
- El límite es inclusivo: edad igual al umbral ya está vencida. Se puede cambiar
  por `PoliticaVigencia(actual_segundos=..., predictivo_segundos=...)`; se rechazan
  bool, cero, negativos y no finitos. Son valores iniciales, pendientes de campo.
- Las fechas originales nunca se sustituyen por la hora de preparación o reinicio.
  Si una fecha está en el futuro, se bloquea disponibilidad; no se incorpora una
  tolerancia de reloj implícita. El coordinador futuro deberá gestionar ajustes de reloj.
- Reevaluar en cada sondeo aunque no cambie ninguna revisión: pasar el tiempo no
  cambia SQLite, pero sí puede cambiar la disponibilidad.

Al reiniciar se evalúa el estado persistido sin rejuvenecerlo: un resultado aún
vigente puede resultar disponible. No hay bloqueo adicional por sesión en esta
función. La condición del calculador de esperar la primera lectura actual válida
antes del ciclo predictivo sigue siendo responsabilidad del futuro coordinador.

## Snapshot completo, errores de fuente y alcance pendiente

Usar `leer_snapshot(conn)` desde revisión 0. La función no mantiene caché ni cursor;
**no pasar un delta aislado**. El formato de almacenamiento no permite distinguir
un delta de un snapshot completo con pocas filas. El adaptador futuro tendrá que
combinar deltas y asegurar que todas las dependencias de contexto estén presentes.

Se incluyen tramos inactivos, con valores no disponibles, para permitir invalidar
nodos que ya existían. Todavía no se crean, retiran ni renombran nodos en caliente.

Una excepción al leer SQLite no llega a esta función como dato: el servicio de
ensayo intenta invalidar sus salidas, registra el error y cierra. Reintentos pendientes.
No debe mantener Good indefinidamente sobre una caché que ya no puede verificar.
Tampoco debe avanzar el cursor si falla la publicación de un conjunto.

Etapa 3b implementada: transporte loopback, tipos/StatusCodes, productor y cliente,
verificados en desarrollo. Siguiente parte (3c): sondeo incremental, recuperación
y ensayos IGS/AR autorizados. No hay mediciones de consumo representativas todavía.
