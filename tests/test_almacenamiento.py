"""Pruebas SQLite aisladas: exclusivamente archivos temporales, nunca iFIX."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from almacenamiento import ErrorEsquema, abrir_base, inicializar_base, transaccion


class AlmacenamientoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "base # local.sqlite3"

    def abrir(self, **kwargs):
        conn = abrir_base(self.path, **kwargs)
        self.addCleanup(conn.close)
        return conn

    def crear(self):
        inicializar_base(self.path)
        return self.abrir()

    def revision(self, conn):
        return conn.execute(
            "SELECT valor FROM metadatos WHERE clave='revision_global'"
        ).fetchone()[0]

    def incrementar(self, conn):
        conn.execute("UPDATE metadatos SET valor=valor+1 WHERE clave='revision_global'")

    def test_creacion_persistencia_y_pragmas(self):
        conn = self.crear()
        self.assertEqual(conn.execute('PRAGMA journal_mode').fetchone()[0], 'wal')
        self.assertEqual(conn.execute('PRAGMA synchronous').fetchone()[0], 2)
        self.assertEqual(conn.execute('PRAGMA foreign_keys').fetchone()[0], 1)
        self.assertEqual(self.revision(conn), 0)
        with transaccion(conn, escritura=True):
            self.incrementar(conn)
        conn.close()
        self.assertEqual(self.revision(self.abrir()), 1)

    def test_no_sobrescribe_base_ni_archivo_ajeno(self):
        self.path.write_bytes(b'contenido ajeno')
        with self.assertRaises(FileExistsError):
            inicializar_base(self.path)
        self.assertEqual(self.path.read_bytes(), b'contenido ajeno')

    def test_abrir_ausente_no_crea(self):
        for readonly in (False, True):
            with self.assertRaises(sqlite3.OperationalError):
                abrir_base(self.path, solo_lectura=readonly)
        self.assertFalse(self.path.exists())

    def test_no_reinicializa_base_existente(self):
        conn = self.crear()
        with transaccion(conn, escritura=True):
            self.incrementar(conn)
        with self.assertRaises(FileExistsError):
            inicializar_base(self.path)
        self.assertEqual(self.revision(conn), 1)

    def test_error_de_commit_revierte(self):
        conn = self.crear()
        # Restricción diferida: el INSERT pasa, pero el COMMIT falla.
        conn.execute('CREATE TABLE padre (id INTEGER PRIMARY KEY)')
        conn.execute('CREATE TABLE hijo (id INTEGER REFERENCES padre(id) '
                     'DEFERRABLE INITIALLY DEFERRED)')
        with self.assertRaises(sqlite3.IntegrityError):
            with transaccion(conn, escritura=True):
                self.incrementar(conn)
                conn.execute('INSERT INTO hijo VALUES (1)')
        self.assertFalse(conn.in_transaction)
        self.assertEqual(self.revision(conn), 0)
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM hijo').fetchone()[0], 0)

    def test_ruta_y_timeout_invalidos_sin_crear(self):
        with self.assertRaises(ValueError):
            inicializar_base('relativa.sqlite3')
        for valor in (True, -1, 61, float('nan'), float('inf'), '5'):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                inicializar_base(self.path, valor)
        self.assertFalse(self.path.exists())

    def test_base_ajena_no_se_adopta(self):
        conn = sqlite3.connect(str(self.path))
        conn.execute('CREATE TABLE otro (dato TEXT)')
        conn.close()
        original = self.path.read_bytes()
        with self.assertRaises(ErrorEsquema):
            self.abrir()
        self.assertEqual(self.path.read_bytes(), original)

    def test_version_incompatible_rechazada(self):
        conn = self.crear()
        conn.execute('PRAGMA user_version=99')
        for readonly in (False, True):
            with self.assertRaises(ErrorEsquema):
                self.abrir(solo_lectura=readonly)
        self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 99)

    def test_metadatos_incompletos_rechazados(self):
        conn = self.crear()
        conn.execute("DELETE FROM metadatos WHERE clave='revision_global'")
        with self.assertRaises(ErrorEsquema):
            self.abrir()

    def test_rollback_y_anidamiento(self):
        conn = self.crear()
        with self.assertRaisesRegex(RuntimeError, 'fallo'):
            with transaccion(conn, escritura=True):
                self.incrementar(conn)
                raise RuntimeError('fallo')
        self.assertEqual(self.revision(conn), 0)
        with transaccion(conn, escritura=True):
            self.incrementar(conn)
            with self.assertRaises(ValueError):
                with transaccion(conn):
                    pass
            self.assertTrue(conn.in_transaction)
        self.assertEqual(self.revision(conn), 1)

    def test_lector_no_puede_escribir(self):
        self.crear()
        reader = self.abrir(solo_lectura=True)
        with self.assertRaises(sqlite3.OperationalError):
            with transaccion(reader):
                self.incrementar(reader)
        self.assertFalse(reader.in_transaction)
        self.assertEqual(self.revision(reader), 0)

    def test_snapshot_lector_estable_mientras_escritor_confirma(self):
        writer = self.crear()
        reader = self.abrir(solo_lectura=True)
        with transaccion(reader):
            self.assertEqual(self.revision(reader), 0)
            with transaccion(writer, escritura=True):
                self.incrementar(writer)
            self.assertEqual(self.revision(reader), 0)
        self.assertEqual(self.revision(reader), 1)

    def test_segundo_escritor_bloqueado_y_reintento_explicito(self):
        first = self.crear()
        second = self.abrir(tiempo_espera=0)
        with transaccion(first, escritura=True):
            self.incrementar(first)
            with self.assertRaises(sqlite3.OperationalError):
                with transaccion(second, escritura=True):
                    self.fail('No debe adquirir el bloqueo')
            self.assertFalse(second.in_transaction)
        with transaccion(second, escritura=True):
            self.incrementar(second)
        self.assertEqual(self.revision(second), 2)


if __name__ == '__main__':
    unittest.main()
