"""Importadores y migraciones sobre SQLite temporal; sin COM ni datos reales."""

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from almacenamiento import (
    ErrorEsquema, abrir_base, inicializar_base, importar_catalogo,
    importar_geometrias, migrar_base, migrar_base_v1, validar_catalogo, validar_geometrias,
)
from almacenamiento.conexion import APPLICATION_ID


class ImportacionesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'actual.sqlite3'
        inicializar_base(self.path)
        self.conn = abrir_base(self.path)
        self.addCleanup(self.conn.close)

    def archivo(self, data, nombre='entrada.json'):
        path = self.root / nombre
        path.write_text(json.dumps(data), encoding='utf-8')
        return path

    def catalogo(self, **tags):
        return self.archivo({'sistemas': {'s': {'tramos': [
            {'id': k, 'base-tag': tag, 'presion-ingreso': 'ENT.F_CV',
             'presion-egreso': 'FIX.SAL.F_CV'} for k, tag in tags.items()]}}})

    def geometria(self, **longitudes):
        return self.archivo({'version_formato': 1, 'tramos': {
            k: {'diametro_exterior_pulgadas': 6, 'espesor_milimetros': 4,
                'longitud_metros': length} for k, length in longitudes.items()}})

    def snapshot(self):
        return [self.conn.execute('SELECT * FROM ' + table + ' ORDER BY 1').fetchall()
                for table in ('metadatos', 'tramos', 'geometrias')]

    def test_catalogo_altas_identico_cambio_intercambio_e_inactivacion(self):
        path = self.catalogo(A='TAG_A', B='TAG_B')
        original = path.read_bytes()
        summary = importar_catalogo(self.conn, path)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(summary['agregados'], 2)
        self.assertEqual(summary['catalogo_sin_geometria'], ['A', 'B'])
        self.assertEqual(summary['revision'], 1)
        self.assertEqual(self.conn.execute('SELECT presion_ingreso_tag FROM tramos').fetchone()[0],
                         'FIX.ENT.F_CV')
        before = self.snapshot()
        summary = importar_catalogo(self.conn, path)
        self.assertEqual(summary['inalterados'], 2)
        self.assertEqual(before, self.snapshot())
        summary = importar_catalogo(self.conn, self.catalogo(A='TAG_B', B='TAG_A'))
        self.assertEqual(summary['modificados'], 2)
        self.assertEqual(len(summary['cambios_base_tag']), 2)
        summary = importar_catalogo(self.conn, self.catalogo(B='TAG_A'))
        self.assertEqual(summary['ids_inactivados'], ['A'])
        self.assertEqual(self.conn.execute("SELECT activo FROM tramos WHERE id='A'").fetchone()[0], 0)
        summary = importar_catalogo(self.conn, self.catalogo(A='TAG_B', B='TAG_A'))
        self.assertEqual(summary['ids_reactivados'], ['A'])

    def test_geometrias_discordantes_versiones_y_reapertura(self):
        importar_catalogo(self.conn, self.catalogo(A='TAG_A'))
        path = self.geometria(B=10000)
        summary = importar_geometrias(self.conn, path)
        self.assertEqual(summary['geometria_sin_catalogo'], ['B'])
        self.assertEqual(summary['catalogo_sin_geometria'], ['A'])
        before = self.snapshot()
        importar_geometrias(self.conn, path)
        self.assertEqual(before, self.snapshot())
        importar_geometrias(self.conn, self.geometria(B=20000))
        self.assertEqual(self.conn.execute('SELECT version FROM geometrias').fetchone()[0], 2)
        summary = importar_geometrias(self.conn, self.geometria())
        self.assertEqual(summary['ids_inactivados'], ['B'])
        importar_geometrias(self.conn, self.geometria(B=20000))
        reopened = abrir_base(self.path, solo_lectura=True)
        try:
            row = reopened.execute('SELECT * FROM geometrias').fetchone()
            self.assertEqual(row['version'], 4)
            self.assertEqual(row['longitud_metros'], 20000)
            self.assertTrue(row['actualizada_en'].endswith('+00:00'))
        finally:
            reopened.close()

    def test_catalogo_anidado_y_duplicados(self):
        tramo = {'id': 'A', 'base-tag': 'TAG', 'presion-ingreso': 'P', 'presion-egreso': 'Q'}
        path = self.archivo({'sistemas': {'s': {'subsistemas': [{'tramos': [tramo]}]}}})
        self.assertEqual(list(validar_catalogo(path)), ['A'])
        before = self.snapshot()
        for tags in ({'A': 'TAG', 'B': 'tag'},):
            with self.assertRaises(ValueError):
                importar_catalogo(self.conn, self.catalogo(**tags))
        path = self.archivo({'sistemas': {'s': {'tramos': [tramo, tramo]}}})
        with self.assertRaises(ValueError):
            importar_catalogo(self.conn, path)
        self.assertEqual(before, self.snapshot())

    def test_json_invalido_y_miembros_duplicados(self):
        path = self.root / 'invalido.json'
        before = self.snapshot()
        for raw in ('{', '{"sistemas":{},"sistemas":{}}',
                    '{"version_formato":1,"tramos":{"A":{},"A":{}}}',
                    '{"version_formato":1,"tramos":{},"extra":NaN}'):
            path.write_text(raw, encoding='utf-8')
            for operation in (importar_catalogo, importar_geometrias):
                with self.subTest(raw=raw, op=operation), self.assertRaises(ValueError):
                    operation(self.conn, path)
        self.assertEqual(before, self.snapshot())

    def test_geometria_invalida_no_cambia_datos(self):
        importar_geometrias(self.conn, self.geometria(A=10000))
        before = self.snapshot()
        for value in (True, None, '100', 0, -1, float('nan'), float('inf'), 10**400):
            with self.subTest(value=value), self.assertRaises(ValueError):
                importar_geometrias(self.conn, self.geometria(A=value))
        path = self.geometria(A=10000)
        data = json.loads(path.read_text())
        data['tramos']['A']['espesor_milimetros'] = 1000
        with self.assertRaises(ValueError):
            importar_geometrias(self.conn, self.archivo(data))
        self.assertEqual(before, self.snapshot())

    def test_formato_campos_y_ids_geometricos(self):
        valid = json.loads(self.geometria(A=100).read_text())
        invalid = [[], {'version_formato': True, 'tramos': {}},
                   {'version_formato': 2, 'tramos': {}}, {'version_formato': 1, 'tramos': []}]
        for ids in ({'': valid['tramos']['A']}, {'A': {}, ' A ': {}}, {'A': {}}):
            invalid.append({'version_formato': 1, 'tramos': ids})
        extra = json.loads(json.dumps(valid))
        extra['tramos']['A']['longitud_m'] = 2
        invalid.append(extra)
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                validar_geometrias(self.archivo(data))

    def test_fallo_intermedio_revierte_filas_y_revision(self):
        for geometry in (False, True):
            table, key = ('geometrias', 'tramo_id') if geometry else ('tramos', 'id')
            self.conn.execute("CREATE TRIGGER fallo BEFORE INSERT ON {} WHEN NEW.{}='B' "
                              "BEGIN SELECT RAISE(ABORT, 'ensayo'); END".format(table, key))
            before = self.snapshot()
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    if geometry:
                        importar_geometrias(self.conn, self.geometria(A=100, B=200))
                    else:
                        importar_catalogo(self.conn, self.catalogo(A='TAG_A', B='TAG_B'))
                self.assertEqual(before, self.snapshot())
            finally:
                self.conn.execute('DROP TRIGGER fallo')

    def test_catalogo_vacio_y_reutilizacion_base_inactiva(self):
        importar_catalogo(self.conn, self.catalogo(A='TAG'))
        importar_catalogo(self.conn, self.catalogo())
        summary = importar_catalogo(self.conn, self.catalogo(B='TAG'))
        self.assertEqual(summary['agregados'], 1)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM tramos').fetchone()[0], 2)

    def crear_v1(self):
        path = self.root / 'previa.sqlite3'
        conn = sqlite3.connect(str(path))
        conn.execute('PRAGMA journal_mode=WAL')
        conn.executescript("CREATE TABLE metadatos (clave TEXT PRIMARY KEY NOT NULL, "
                           "valor INTEGER NOT NULL CHECK(typeof(valor)='integer' AND valor>=0));"
                           "INSERT INTO metadatos VALUES ('version_esquema',1);"
                           "INSERT INTO metadatos VALUES ('revision_global',7);")
        conn.execute('PRAGMA application_id={}'.format(APPLICATION_ID))
        conn.execute('PRAGMA user_version=1')
        conn.close()
        return path

    def test_migracion_v1_backup_y_datos_conservados(self):
        path = self.crear_v1()
        # Mantener WAL abierto y con una escritura confirmada, sin escritores activos.
        holder = sqlite3.connect(str(path), isolation_level=None)
        self.addCleanup(holder.close)
        holder.execute("UPDATE metadatos SET valor=7 WHERE clave='revision_global'")
        with self.assertRaises(ErrorEsquema):
            abrir_base(path)
        backup = migrar_base(path, self.root / 'backup.sqlite3')
        conn = abrir_base(path)
        try:
            self.assertEqual(conn.execute("SELECT valor FROM metadatos WHERE clave='revision_global'").fetchone()[0], 7)
            self.assertEqual(importar_catalogo(conn, self.catalogo(A='TAG'))['revision'], 8)
        finally:
            conn.close()
        old = sqlite3.connect(str(backup))
        try:
            self.assertEqual(old.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertEqual(old.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        finally:
            old.close()
        restored = self.root / 'restaurada.sqlite3'
        shutil.copy2(backup, restored)  # Backup cerrado, no copia de la base WAL activa.
        migrar_base(restored, self.root / 'restaurada_previa.sqlite3')
        restored_conn = abrir_base(restored)
        try:
            self.assertEqual(restored_conn.execute(
                "SELECT valor FROM metadatos WHERE clave='revision_global'").fetchone()[0], 7)
        finally:
            restored_conn.close()
        with self.assertRaises(ErrorEsquema):
            migrar_base_v1(path, self.root / 'otro.sqlite3')
        self.assertFalse((self.root / 'otro.sqlite3').exists())

    def test_migracion_no_sobrescribe_backup(self):
        path = self.crear_v1()
        backup = self.root / 'existente.sqlite3'
        backup.write_bytes(b'no tocar')
        with self.assertRaises(FileExistsError):
            migrar_base_v1(path, backup)
        self.assertEqual(backup.read_bytes(), b'no tocar')
        with self.assertRaises(ErrorEsquema):
            abrir_base(path)

    def test_migracion_fallida_conserva_v1_y_backup(self):
        path = self.crear_v1()
        conn = sqlite3.connect(str(path))
        conn.execute('CREATE TABLE geometrias (dato TEXT)')
        conn.close()
        backup = self.root / 'fallida.sqlite3'
        with self.assertRaises(sqlite3.OperationalError):
            migrar_base_v1(path, backup)
        conn = sqlite3.connect(str(path))
        try:
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertFalse(conn.execute("SELECT name FROM sqlite_master WHERE name='tramos'").fetchall())
        finally:
            conn.close()
        self.assertTrue(backup.exists())

    def test_importacion_lector_y_transaccion_abierta(self):
        path = self.catalogo(A='TAG')
        reader = abrir_base(self.path, solo_lectura=True)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                importar_catalogo(reader, path)
        finally:
            reader.close()
        self.conn.execute('BEGIN')
        try:
            with self.assertRaises(ValueError):
                importar_catalogo(self.conn, path)
            self.assertTrue(self.conn.in_transaction)
        finally:
            self.conn.rollback()


if __name__ == '__main__':
    unittest.main()
