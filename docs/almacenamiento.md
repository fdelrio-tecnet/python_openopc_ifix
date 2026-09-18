# Almacenamiento SQLite — etapa 2 completa

[Inicio](../README.md) · [Modelo](modelo_datos.md) · [Operación](operacion.md)

## Alcance implementado

Paquete [almacenamiento](../almacenamiento/__init__.py), con biblioteca estándar
Python 3.9: no importa OpenOPC, no instala servicios y no abre puertos. No hay
acceso al disco al importar el paquete. El esquema v3 contiene metadatos, catálogo,
geometrías, resultados actuales/predictivos y adquisición. No implementa OPC UA.

| API pública | Contrato |
|---|---|
| `inicializar_base(ruta, tiempo_espera=5.0)` | Crea un archivo nuevo y devuelve su ruta absoluta; cierra su conexión |
| `abrir_base(ruta, solo_lectura=False, tiempo_espera=5.0)` | Abre exclusivamente una base existente compatible; devuelve una conexión que debe cerrarse |
| `transaccion(conn, escritura=False)` | Context manager: BEGIN de lectura o BEGIN IMMEDIATE de escritura, COMMIT normal, rollback ante excepción |
| `ErrorEsquema` | Excepción de base ajena, esquema incompatible o metadatos inválidos; deriva de ValueError |
| `migrar_base_v1(ruta, ruta_backup)` | Migra exclusivamente v1 a v2 con backup obligatorio en archivo nuevo |
| `migrar_base(ruta, ruta_backup)` | Ruta recomendada: migra v1/v2 a v3 con backup obligatorio nuevo |

Resultados/snapshots: ver [API específica](repositorio_resultados.md).
Consola ejecutable: ver [administración](configuracion_importaciones.md).

La [API de importaciones](configuracion_importaciones.md) agrega validadores e
importadores de catálogo/geometría, con resumen y una revisión por carga con cambios.

Las funciones se implementan en [conexion.py](../almacenamiento/conexion.py).
Errores de ruta/opciones: ValueError; archivo ya existente al inicializar:
FileExistsError; fallas del motor/disco: excepciones SQLite/OS sin ocultarlas.
También se revierte cuando falla el COMMIT. No hay reintentos automáticos.

## Uso mínimo, sin datos operativos

Ejemplo equivalente a las pruebas, ejecutado desde la raíz con un directorio temporal:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from almacenamiento import inicializar_base, abrir_base, transaccion

with TemporaryDirectory() as directorio:
    ruta = Path(directorio) / "ensayo.sqlite3"
    inicializar_base(ruta)
    conn = abrir_base(ruta, solo_lectura=True)
    try:
        with transaccion(conn):
            revision = conn.execute(
                "SELECT valor FROM metadatos WHERE clave='revision_global'"
            ).fetchone()[0]
            assert revision == 0
    finally:
        conn.close()
```

No utilizar `with conn` como sustituto de `close()`: el contexto de sqlite3 no
cierra la conexión. Dentro de `transaccion` no ejecutar COMMIT, ROLLBACK ni
`executescript`, ni operar OPC, calcular o esperar. No admite transacciones anidadas.
`escritura=False` selecciona BEGIN diferido; la protección contra escrituras se
obtiene abriendo con `solo_lectura=True`, no con ese parámetro del contexto.

## Concurrencia y durabilidad

- WAL se activa al crear y se exige al abrir, sin cambiar el journal de una base ajena.
- Conexiones escritoras usan `synchronous=FULL`; integridad de referencias activada.
- Lectores usan URI `mode=ro` y `query_only`; no pueden crear ni modificar la base.
- Escritores usan `mode=rw`: equivocarse de ruta nunca crea otra base silenciosamente.
- Cada hilo/proceso necesita conexión propia. SQLite sigue admitiendo un escritor
  a la vez; BEGIN IMMEDIATE toma el bloqueo antes del trabajo transaccional.
- Espera configurable de 0 a 60 segundos, por operación bloqueada, no plazo total
  de ciclo. El valor inicial de 5 segundos deberá ajustarse con mediciones.
- Conexiones en autocommit fuera del contexto. Importadores y repositorio agrupan
  filas y revisión en una transacción. Cada resultado y su adquisición son atómicos.
- Snapshot fijo desde la primera lectura del bloque; mantenerlo breve para no
  retrasar checkpoints ni permitir crecimiento innecesario de WAL.

## Inicialización, compatibilidad y recuperación

La ruta debe ser absoluta y el directorio existir. Se rechazan UNC, pero no se
detectan todas las unidades de red mapeadas o carpetas sincronizadas: su exclusión
es responsabilidad del despliegue. Se requiere acceso a archivos WAL/SHM incluso
para el funcionamiento normal del conjunto de procesos bajo el mismo usuario.

La creación usa apertura exclusiva: no reemplaza ni siquiera un archivo vacío.
Si falla después de crearlo, conserva el archivo para diagnóstico; no lo borra ni
repara automáticamente. El operador debe revisar la causa antes de reintentar en
una ruta nueva. Solo se crean bases temporales durante las pruebas.

Se validan `application_id` (0x4C504143), `user_version=3`, versión duplicada en
metadatos y revisión global entera no negativa. No es una verificación forense de
integridad ni protege contra manipulación SQL por otro programa del mismo usuario.
No se ejecuta `integrity_check` completo en cada conexión.

### Migración explícita v1/v2 → v3

1. Detener calculadores, publicador y otros lectores/escritores; mantenerlos
   detenidos hasta verificar el esquema y actualizar el software de todos ellos.
2. Invocar `migrar_base(ruta_absoluta_base, ruta_absoluta_backup_nuevo)` o el comando
   `migrar-base`. Rechaza bases ajenas/no v1/v2 y destinos existentes; no recrea la base.
3. La función toma BEGIN IMMEDIATE, hace backup SQLite desde una conexión lectora
   independiente (incluye WAL), verifica integridad del backup y agrega tablas,
   índices y versión en la misma transacción. Conserva revision_global.
4. Abrir mediante `abrir_base`, comprobar versión 3 e importar datos explícitamente.
   Los clientes anteriores v1/v2 rechazan la nueva base; actualizar todos juntos.

La función histórica `migrar_base_v1` conserva su contrato v1 → v2, pero v2 no
se abre con el cliente actual: después se requiere `migrar_base` con otro backup.
Para nuevas operaciones usar directamente `migrar_base` y evitar el paso intermedio.

El backup usa páginas de 256 y un plazo de 60 segundos comprobado entre pasos;
no es una garantía de interrupción de E/S bloqueada ni del integrity_check.
Durante backup/migración se mantiene el bloqueo escritor: operación administrativa,
no parte de los ciclos periódicos. En errores se revierte SQL, pero no se elimina
el backup ni un archivo parcial; diagnosticar antes de reutilizarlo.

Recuperación manual: con todos los procesos detenidos, verificar el backup y
restaurarlo a **otra ruta**, conservar la base fallida y apuntar la configuración a
la copia restaurada. Una copia v1/v2 requiere software compatible o migrar. No copiar
solo el .db de una base activa, ni sobrescribir archivos con WAL/SHM existentes.
No hay comando de restauración ni política de retención automatizada.

## Verificación y siguiente parte

13 pruebas nuevas cubren persistencia, creación exclusiva, bases ausentes/ajenas,
versión incompatible, metadatos incompletos, rollback (incluido fallo de COMMIT),
anidamiento, lector protegido, snapshot y bloqueo/reintento de dos conexiones.
Estas pruebas iniciales usan conexiones independientes en un proceso. La etapa 2c
agrega una prueba con dos procesos reales; no hay ensayos de cortes de energía ni benchmarks.

Se agregan 12 pruebas de importación/migración: cargas, cambios, omisiones,
reactivación, rechazo de inválidos, fallas intermedias, backup obligatorio y rollback
de migración. Etapa 2c agrega 19 pruebas de paquetes, snapshots, adquisición,
consola y concurrencia. Siguiente: servidor UA con productor de prueba. No se
modifica aún el destino OPC DA actual ni se cambia su política de confirmación.
