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

El parser quita espacios externos; detecta IDs repetidos por igualdad exacta y
salidas repetidas sin distinguir mayúsculas. Las entradas compartidas están permitidas. Añade `FIX.` a
las presiones cuando falta y genera geometría/salidas actuales y 72 tags por serie.
`base-tag` se espera sin prefijo FIX ni campo. No deducir existencia real de tags
por el hecho de que la generación de strings sea correcta.

El archivo real se comprobó en septiembre de 2026: 21 tramos directos y 30 en
subsistemas, 51 IDs sin colisiones. Es una referencia de esa revisión, no un
requisito fijo: nuevos tramos deben poder incorporarse.

## JSON de geometría — formato implementado

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

Ejemplo ilustrativo, no geometría real aprobada. Existe importador mediante API Python.
El JSON es entrada de administración; SQLite conserva la versión importada, aunque
el calculador aún no consume geometría desde SQLite.
Editar el archivo no cambia la base automáticamente. No reimportar sin petición
en cada reinicio, para evitar revertir inadvertidamente una versión activa.

Validar: formato soportado, IDs no vacíos, campos completos, números finitos
positivos, diámetro interno mayor que cero y ausencia de IDs/miembros JSON
duplicados antes de que un parser pueda sobrescribirlos silenciosamente.

## Semántica de importación implementada

- Carga explícita del archivo completo, transaccional.
- Error de estructura o magnitudes: rechazar la importación y conservar el estado
  anterior; dar ubicación/ID y motivo.
- ID solo en geometría: aceptar y conservar, aunque no se utilice todavía.
- ID solo en catálogo: aceptar; cálculo no disponible por falta de geometría.
- Diferencias entre archivos: informar, nunca tratarlas como falla global.
- Reemplazo completo: geometrías y tramos omitidos quedan inactivos, sin
  borrado físico. Mostrar las inactivaciones explícitamente en el resumen.
- Misma geometría: sin nueva versión. Cambio de valores o activación: nueva versión.
- Importación del catálogo: altas/cambios/inactivaciones; base-tags modificados
  deben destacarse por su impacto en nodos/IGS.

La política de recarga dinámica del catálogo y creación/retiro de nodos UA debe
cerrarse al implementar el servidor; no prometer altas en caliente antes de probarlas.

## API Python implementada

En `almacenamiento` se exportan:

- `validar_catalogo(ruta)` y `validar_geometrias(ruta)`: lectura/validación sin base.
- `importar_catalogo(conn, ruta)` y `importar_geometrias(conn, ruta)`: reciben una
  conexión escritora v3 sin transacción abierta; no la cierran. Devuelven resumen
  solo después de COMMIT. Fallas de SQLite/archivo se propagan; contenido inválido
  produce ValueError. Las escrituras y su revisión se revierten juntas ante fallo.

Cada archivo se lee una sola vez, antes de tomar el bloqueo de escritura. La lectura
estricta rechaza miembros JSON duplicados en cualquier nivel y NaN/Infinity.
El catálogo reutiliza `construir_estructura_tramos` del parser, sin duplicar sus reglas.
La geometría rechaza campos desconocidos y versiones distintas del entero 1;
también IDs duplicados después de strip. Espesor cero no está permitido.

El resumen incluye `agregados`, `modificados`, `inalterados`, `inactivados`,
`ids_inactivados`, `ids_reactivados`, `cambios_base_tag` (ID/anterior/nuevo),
`catalogo_sin_geometria`, `geometria_sin_catalogo` y `revision`. Las discordancias
comparan registros activos; las reactivaciones se cuentan entre los modificados.
Una transacción con cambios asigna la misma nueva revisión a todas las filas
afectadas. La carga idéntica conserva revisiones, versiones y timestamps.

**Archivo vacío válido:** inactiva todos los registros activos de su colección.
Antes de importar, revisar que se está cargando el archivo completo; no enviar
solo los cambios. Geometría y catálogo se importan por separado, nunca se exige
que sus conjuntos de IDs coincidan. Estas funciones no modifican el JSON original.

Ejemplo de uso de API (rutas elegidas por el operador, no ejecutar sobre producción
sin revisar el archivo): `importar_geometrias(conn, ruta_json)`. La apertura/cierre
de conexión está detallada en [almacenamiento](almacenamiento.md).

## Interfaz de administración — implementada

Desde la raíz, con el intérprete elegido:

```console
python -m administracion --help
```

Sintaxis de los subcomandos (BASE, BACKUP y ARCHIVO son marcadores a sustituir,
no rutas de producción; entrecomillar si hay espacios):

```text
python -m administracion crear-base --base BASE
python -m administracion migrar-base --base BASE --backup BACKUP
python -m administracion validar-config --archivo ARCHIVO
python -m administracion validar-geometria --archivo ARCHIVO
python -m administracion importar-config --base BASE --archivo ARCHIVO
python -m administracion importar-geometria --base BASE --archivo ARCHIVO
python -m administracion mostrar-estado --base BASE
```

BASE/BACKUP requieren rutas absolutas locales; directorios deben existir. Crear
no sobreescribe y migrar requiere backup nuevo. Las importaciones aplican de inmediato
el archivo **completo**, incluyendo inactivaciones por omisión: validar/revisar antes.
No hay confirmación interactiva ni recarga automática. Validar no abre SQLite;
mostrar-estado usa conexión de solo lectura y devuelve snapshot completo (no calidad UA).
Salida correcta: JSON en stdout, código 0. Errores de argumentos/datos/SQLite/OS:
stderr y código 2. No usar mostrar-estado como log periódico de miles de puntos.
La CLI no cambia endpoint, programas de cálculo ni configuración de iFIX.

El informe de importación debe incluir cantidades agregadas, modificadas,
inalteradas, inactivadas y discordancias, más revisión resultante.

## Configuración UA implementada y opciones pendientes

El archivo [opcua.ejemplo.json](../configuracion/opcua.ejemplo.json) define base,
puerto, namespace, sondeo y vigencias del servidor de ensayo. La base relativa se
resuelve respecto de ese JSON. Ver [contrato completo](servidor_opcua_ensayo.md).
No se recarga automáticamente; altas/cambios de nombres de nodos exigen reinicio.
La configuración del coordinador, reintentos y logs rotativos sigue pendiente.

Intervalos del calculador 30/600 segundos, calidad Good exigida, timeouts/reintentos
y rotación de logs deberán incorporarse a su configuración operativa. Los umbrales
UA implementados son iniciales; requieren validación en destino.

No guardar opciones de este programa dentro del JSON compartido de CamuLinepack.
