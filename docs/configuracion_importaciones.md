# Configuración e importaciones

[Inicio](../README.md) · [Modelo de datos](modelo_datos.md)

## Configuración de tramos existente

El JSON pertenece a CamuLinepack y su estructura no se modifica. El parser
implementado, `cargar_estructura_tramos`, reconoce:

```text
sistemas (objeto)
└── sistema (objeto)
    ├── tramos (lista, opcional)
    └── subsistemas (lista, opcional)
        └── subsistema (objeto)
            └── tramos (lista, obligatoria)
```

Cada sistema debe incluir al menos `tramos` o `subsistemas`; ambas colecciones
pueden estar vacías. Cada tramo requiere strings no vacíos: `id`, `base-tag`,
`presion-ingreso` y `presion-egreso`. Se ignoran otros campos de negocio.

El parser quita espacios externos; detecta IDs repetidos y salidas repetidas sin
distinguir mayúsculas. Las entradas compartidas están permitidas. Añade `FIX.` a
las presiones cuando falta y genera geometría/salidas actuales y 72 tags por serie.
`base-tag` se espera sin prefijo FIX ni campo. No deducir existencia real de tags
por el hecho de que la generación de strings sea correcta.

El archivo real se comprobó en septiembre de 2026: 21 tramos directos y 30 en
subsistemas, 51 IDs sin colisiones. Es una referencia de esa revisión, no un
requisito fijo: nuevos tramos deben poder incorporarse.

## JSON de geometría — formato propuesto

```json
{
  "version_formato": 1,
  "tramos": {
    "037-001-A": {
      "diametro_exterior_pulgadas": 6.0,
      "espesor_milimetros": 4.0,
      "longitud_metros": 10000.0
    }
  }
}
```

Ejemplo ilustrativo, no geometría real aprobada. Todavía no hay importador.
El JSON es entrada de administración; SQLite será la fuente operativa tras importar.
Editar el archivo no cambia la base automáticamente. No reimportar sin petición
en cada reinicio, para evitar revertir inadvertidamente una versión activa.

Validar: formato soportado, IDs no vacíos, campos completos, números finitos
positivos, diámetro interno mayor que cero y ausencia de IDs/miembros JSON
duplicados antes de que un parser pueda sobrescribirlos silenciosamente.

## Semántica de importación acordada/propuesta

- Carga explícita del archivo completo, transaccional.
- Error de estructura o magnitudes: rechazar la importación y conservar el estado
  anterior; dar ubicación/ID y motivo.
- ID solo en geometría: aceptar y conservar, aunque no se utilice todavía.
- ID solo en catálogo: aceptar; cálculo no disponible por falta de geometría.
- Diferencias entre archivos: informar, nunca tratarlas como falla global.
- Propuesta de reemplazo completo: geometrías omitidas quedan inactivas, sin
  borrado físico. Mostrar las inactivaciones explícitamente en el resumen.
- Misma geometría: sin nueva versión. Cambio de valores o activación: nueva versión.
- Importación del catálogo: altas/cambios/inactivaciones; base-tags modificados
  deben destacarse por su impacto en nodos/IGS.

La política de recarga dinámica del catálogo y creación/retiro de nodos UA debe
cerrarse al implementar el servidor; no prometer altas en caliente antes de probarlas.

## Interfaz de administración — no implementada

Operaciones previstas: `validar-config`, `importar-config`, `validar-geometria`,
`importar-geometria`, `mostrar-estado`. Son nombres conceptuales; no comandos
ejecutables todavía. La implementación documentará sintaxis, códigos de salida,
rutas y ejemplos comprobados.

El informe de importación debe incluir cantidades agregadas, modificadas,
inalteradas, inactivadas y discordancias, más revisión resultante.

## Opciones operativas pendientes de materializar

Rutas absolutas de base y JSON, endpoint/namespace UA, intervalos 30/600 segundos,
sondeo SQLite inicial de 1–2 segundos, calidad Good exigida, timeouts/reintentos y
rotación de logs. Umbrales iniciales propuestos: 2 minutos sin actualización actual
y 30 minutos sin verificación predictiva válida. Deben ser configurables y probarse.

No guardar opciones de este programa dentro del JSON compartido de CamuLinepack.
