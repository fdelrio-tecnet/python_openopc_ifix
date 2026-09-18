"""Conexiones SQLite locales compatibles con Python 3.9.

Cada proceso/hilo debe abrir su propia conexión. No se reintentan operaciones
automáticamente ni se crean bases al abrirlas. Los errores SQLite se propagan.
"""

import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Union


VERSION_ESQUEMA = 3
APPLICATION_ID = 0x4C504143  # LPAC: distingue esta base de otras aplicaciones.
TIEMPO_ESPERA_SEGUNDOS = 5.0
Ruta = Union[str, Path]


class ErrorEsquema(ValueError):
    """Base ajena, no inicializada o incompatible; no se migra automáticamente."""


def _ruta_local(ruta: Ruta) -> Path:
    path = Path(ruta)
    if not path.is_absolute():
        raise ValueError("La ruta de SQLite debe ser absoluta")
    path = path.resolve()
    if str(path).startswith(("\\\\", "//")):
        raise ValueError("SQLite debe ubicarse en disco local, no en una ruta UNC")
    return path


def _validar_espera(segundos: float) -> float:
    if (isinstance(segundos, bool) or not isinstance(segundos, (int, float))
            or not math.isfinite(segundos) or not 0 <= segundos <= 60):
        raise ValueError("tiempo_espera debe ser finito, entre 0 y 60 segundos")
    return float(segundos)


def _conectar(path: Path, solo_lectura: bool, espera: float) -> sqlite3.Connection:
    mode = "ro" if solo_lectura else "rw"
    conn = sqlite3.connect(
        path.as_uri() + "?mode=" + mode,
        uri=True,
        timeout=espera,
        isolation_level=None,
    )
    conn.row_factory = sqlite3.Row
    return conn


def _validar_esquema(conn: sqlite3.Connection, esperada: int = VERSION_ESQUEMA) -> None:
    if conn.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
        raise ErrorEsquema("La base no pertenece a esta aplicación")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version != esperada:
        raise ErrorEsquema(
            "Versión de esquema incompatible: {} (esperada {})".format(
                version, esperada))
    try:
        rows = dict(conn.execute("SELECT clave, valor FROM metadatos").fetchall())
    except sqlite3.DatabaseError as exc:
        raise ErrorEsquema("No se pueden leer los metadatos del esquema") from exc
    if (type(rows.get("version_esquema")) is not int
            or rows["version_esquema"] != esperada
            or type(rows.get("revision_global")) is not int
            or rows["revision_global"] < 0):
        raise ErrorEsquema("Metadatos de versión/revisión inválidos")
    if conn.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
        raise ErrorEsquema("La base debe estar inicializada en modo WAL")
    if esperada >= 2:
        try:
            conn.execute('SELECT id, base_tag, base_tag_clave, presion_ingreso_tag, '
                         'presion_egreso_tag, activo, revision FROM tramos LIMIT 0')
            conn.execute('SELECT tramo_id, diametro_exterior_pulgadas, '
                         'espesor_milimetros, longitud_metros, activa, version, '
                         'actualizada_en, revision FROM geometrias LIMIT 0')
        except sqlite3.DatabaseError as exc:
            raise ErrorEsquema('Esquema v2 incompleto') from exc
    if esperada >= 3:
        try:
            for table in ('resultados_actuales', 'predicciones_linepack'):
                conn.execute('SELECT tramo_id, geometria_version, catalogo_revision, '
                             'calculado_en, actualizacion_id, revision FROM ' + table + ' LIMIT 0')
            conn.execute('SELECT presion_promedio_bar_abs, linepack_sm3 FROM resultados_actuales LIMIT 0')
            conn.execute('SELECT presiones_json, linepacks_json, firma_presiones_json '
                         'FROM predicciones_linepack LIMIT 0')
            conn.execute('SELECT tramo_id, ciclo, ultimo_intento_en, ultima_lectura_valida_en, '
                         'estado, detalle, resultado_revision, revision FROM estado_adquisicion LIMIT 0')
        except sqlite3.DatabaseError as exc:
            raise ErrorEsquema('Esquema v3 incompleto') from exc


def inicializar_base(ruta: Ruta, tiempo_espera: float = TIEMPO_ESPERA_SEGUNDOS) -> Path:
    """Crea y cierra una base nueva v3; devuelve su ruta absoluta.

    No crea directorios ni reemplaza archivos existentes (FileExistsError).
    Ruta relativa/UNC o espera inválida: ValueError. Fallas de E/S y SQLite se
    propagan. Si falla después de crear el archivo, lo conserva para diagnóstico;
    no intenta eliminarlo, recrearlo ni reparar otra base automáticamente.
    """
    path = _ruta_local(ruta)
    espera = _validar_espera(tiempo_espera)
    schema = Path(__file__).with_name("esquema.sql").read_text(encoding="utf-8")
    schema += Path(__file__).with_name("catalogo.sql").read_text(encoding="utf-8")
    schema += Path(__file__).with_name("resultados.sql").read_text(encoding="utf-8")
    with path.open("xb"):
        pass
    conn = _conectar(path, False, espera)
    try:
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        if mode.lower() != "wal":
            raise ErrorEsquema("No se pudo activar WAL")
        conn.execute("PRAGMA synchronous=FULL")
        # executescript abre su propia secuencia: BEGIN/COMMIT van dentro de ella.
        conn.executescript(
            "BEGIN IMMEDIATE;\n" + schema
            + "\nPRAGMA application_id={};\nPRAGMA user_version={};\nCOMMIT;".format(
                APPLICATION_ID, VERSION_ESQUEMA))
        _validar_esquema(conn)
    finally:
        conn.close()
    return path


def abrir_base(ruta: Ruta, *, solo_lectura: bool = False,
               tiempo_espera: float = TIEMPO_ESPERA_SEGUNDOS) -> sqlite3.Connection:
    """Abre una base existente y compatible; el llamador debe ejecutar close().

    Nunca inicializa ni migra. `solo_lectura=True` usa mode=ro y query_only.
    Espera de bloqueo: segundos, 0..60 (por operación SQLite, no por ciclo).
    Propaga errores SQLite/OS; ErrorEsquema señala incompatibilidad. Una conexión
    fallida se cierra. No compartir la conexión entre hilos ni procesos.
    """
    if type(solo_lectura) is not bool:
        raise ValueError("solo_lectura debe ser booleano")
    path = _ruta_local(ruta)
    conn = _conectar(path, solo_lectura, _validar_espera(tiempo_espera))
    try:
        _validar_esquema(conn)
        conn.execute("PRAGMA foreign_keys=ON")
        if solo_lectura:
            conn.execute("PRAGMA query_only=ON")
        else:
            conn.execute("PRAGMA synchronous=FULL")
        return conn
    except BaseException:
        conn.close()
        raise


@contextmanager
def transaccion(conn: sqlite3.Connection, *, escritura: bool = False
                ) -> Iterator[sqlite3.Connection]:
    """Snapshot de lectura o transacción BEGIN IMMEDIATE de escritura.

    Confirma al salir normalmente y revierte ante excepciones, incluido fallo
    de COMMIT. Rechaza anidamiento sin alterar la transacción exterior. No cierra
    la conexión ni incrementa revisiones por sí misma. No operar OPC ni esperar
    dentro del bloque. No usar executescript: puede confirmar antes de tiempo.
    """
    if type(escritura) is not bool:
        raise ValueError("escritura debe ser booleano")
    if conn.in_transaction:
        raise ValueError("No se permiten transacciones anidadas")
    conn.execute("BEGIN IMMEDIATE" if escritura else "BEGIN")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
