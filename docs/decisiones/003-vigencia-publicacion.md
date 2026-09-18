# ADR 003 — Disponibilidad separada del transporte UA

Fecha: 2026-09-18. Estado: implementada la proyección; transporte pendiente.

## Decisión

Preparar valores/fechas/disponibilidad en una función pura, independiente de una
biblioteca UA. Actual y predictivo se evalúan por separado. Un problema local no
detiene otros tramos, pero un snapshot global mal formado se rechaza.

La vigencia actual depende del cálculo; la predictiva depende de la última
verificación válida de ese mismo resultado. Verificar un valor no recalculado no
rejuvenece el cálculo actual. Se mantienen las fechas originales y se bloquean
fechas futuras. Umbrales configurables iniciales: 120 y 1800 segundos, inclusivos.

Estados internos no equivalen a StatusCodes. El futuro adaptador tendrá que traducirlos
y comprobar cómo IGS/iFIX exponen falta de valor o calidad no válida. No publicar
un número como válido solo porque persiste en SQLite.

## Consecuencias

Permite probar vencimiento/contexto sin red, sin reloj real y sin dependencia UA.
Exige que el adaptador respete el estado y gestione fallas de fuente, caché/cursor y
reinicios. La proyección no garantiza persistencia PDB ni confirma consumo.

NodeIds definitivos y namespace siguen pendientes: por ahora solo hay claves
lógicas estables por ID de tramo y sufijo, con nombres derivados del base-tag.
Contrato y límites: [publicación](../publicacion_opcua.md).
