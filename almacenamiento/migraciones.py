"""Migración explícita y acotada; detener los demás procesos antes de invocarla."""

import sqlite3
import time
from pathlib import Path

from .conexion import (
    ErrorEsquema, Ruta, _conectar, _ruta_local, _validar_esquema, transaccion,
)


def migrar_base_v1(ruta: Ruta, ruta_backup: Ruta) -> Path:
    """Migra v1 a v2 con backup obligatorio en archivo NUEVO; devuelve su ruta.

    Mantener todos los consumidores detenidos hasta completar la migración. El
    bloqueo de escritura se conserva desde la validación hasta el COMMIT. Backup
    SQLite desde conexión lectora independiente, incluyendo WAL; límite 60 s.
    ErrorEsquema para versión ajena, FileExistsError si existe el backup y errores
    SQLite/OS se propagan. Fallo SQL revierte la migración, no borra el backup.
    Un backup fallido puede quedar incompleto: no usarlo sin verificar integridad.
    No restaura automáticamente ni admite repetir migración sobre una base v2.
    """
    return _migrar(ruta, ruta_backup, 1, 2, ('catalogo.sql',))


def migrar_base(ruta: Ruta, ruta_backup: Ruta) -> Path:
    """Migra v1 o v2 a v3 con backup nuevo; mismo contrato de migrar_base_v1.

    Rechaza cualquier otra versión. No modifica esquemas automáticamente al abrir.
    """
    conn = _conectar(_ruta_local(ruta), True, 5.0)
    try:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version not in (1, 2):
            raise ErrorEsquema('Solo se admite migración desde v1 o v2')
        _validar_esquema(conn, version)
    finally:
        conn.close()
    files = ('catalogo.sql', 'resultados.sql') if version == 1 else ('resultados.sql',)
    return _migrar(ruta, ruta_backup, version, 3, files)


def _migrar(ruta, ruta_backup, anterior, nueva, archivos):
    path, backup = _ruta_local(ruta), _ruta_local(ruta_backup)
    if path == backup:
        raise ValueError('El backup debe usar otra ruta')
    schema = '\n'.join(Path(__file__).with_name(f).read_text(encoding='utf-8') for f in archivos)
    conn = _conectar(path, False, 5.0)
    try:
        _validar_esquema(conn, anterior)
        conn.execute('PRAGMA synchronous=FULL')
        with transaccion(conn, escritura=True):
            _validar_esquema(conn, anterior)
            with backup.open('xb'):
                pass
            reader = _conectar(path, True, 5.0)
            try:
                destination = sqlite3.connect(str(backup))
                try:
                    deadline = time.monotonic() + 60

                    def progreso(status, remaining, total):
                        if time.monotonic() > deadline:
                            raise TimeoutError('Se agotó el plazo del backup')

                    reader.backup(destination, pages=256, progress=progreso, sleep=0.05)
                    if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                        raise ValueError('Backup sin integridad confirmada')
                    if destination.execute('PRAGMA user_version').fetchone()[0] != anterior:
                        raise ValueError('Backup no corresponde a la versión de origen')
                finally:
                    destination.close()
            finally:
                reader.close()
            # SQL propio, sin triggers. No usar executescript dentro de BEGIN.
            statement = ''
            for line in schema.splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    conn.execute(statement)
                    statement = ''
            if statement.strip():
                raise ValueError('SQL de migración incompleto')
            conn.execute("UPDATE metadatos SET valor=? WHERE clave='version_esquema'", (nueva,))
            conn.execute('PRAGMA user_version={}'.format(nueva))
            _validar_esquema(conn, nueva)
    finally:
        conn.close()
    return backup
