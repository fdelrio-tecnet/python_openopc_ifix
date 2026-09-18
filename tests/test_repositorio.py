"""Último estado e intercambio local; datos sintéticos, sin iFIX."""

import contextlib
import io
import json
import multiprocessing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from administracion.__main__ import main
from almacenamiento import (
    ConflictoActualizacion, abrir_base, firma_presiones, guardar_actual,
    guardar_prediccion, importar_catalogo, importar_geometrias, inicializar_base,
    leer_snapshot, migrar_base, registrar_adquisicion,
)


def _producir(path, packet, salida):
    """Proceso independiente usado en la prueba de concurrencia real."""
    conn = abrir_base(path)
    try:
        try:
            guardar_actual(conn, **packet)
            salida.put('guardado')
        except ConflictoActualizacion:
            salida.put('conflicto')
    finally:
        conn.close()


class RepositorioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'base.sqlite3'
        inicializar_base(self.path)
        self.conn = abrir_base(self.path)
        self.addCleanup(self.conn.close)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'sistemas': {'s': {'tramos': [
            {'id': 'A', 'base-tag': 'TAG', 'presion-ingreso': 'P', 'presion-egreso': 'Q'}]}}}))
        self.geo = self.root / 'geo.json'
        self.geo.write_text(json.dumps({'version_formato': 1, 'tramos': {'A': {
            'diametro_exterior_pulgadas': 6, 'espesor_milimetros': 4, 'longitud_metros': 10000}}}))
        importar_catalogo(self.conn, self.config)
        importar_geometrias(self.conn, self.geo)

    def packet(self, **changes):
        packet = dict(tramo_id='A', geometria_version=1, catalogo_revision=1,
                      revision_anterior=0, actualizacion_id='p1', calculado_en='2026-09-18T10:00:00Z',
                      presion_promedio_bar_abs=45.498474367603876, linepack_sm3=7993.124399335523)
        packet.update(changes)
        return packet

    def pred(self, **changes):
        packet = self.packet()
        packet.pop('presion_promedio_bar_abs')
        packet.pop('linepack_sm3')
        packet.update(presiones=[45.498474] * 72, linepacks=[7993.124] * 72)
        packet.update(changes)
        return packet

    def test_actual_precision_estado_y_reapertura(self):
        packet = self.packet()
        saved = guardar_actual(self.conn, **packet)
        self.assertEqual(saved['revision'], 3)
        other = abrir_base(self.path, solo_lectura=True)
        try:
            snap = leer_snapshot(other)
            result = snap['tablas']['resultados_actuales'][0]
            self.assertEqual(result['linepack_sm3'], packet['linepack_sm3'])
            self.assertEqual(result['presion_promedio_bar_abs'], packet['presion_promedio_bar_abs'])
            state = snap['tablas']['estado_adquisicion'][0]
            self.assertEqual(state['resultado_revision'], saved['revision'])
            self.assertEqual(state['estado'], 'valido')
            self.assertFalse(other.in_transaction)
        finally:
            other.close()

    def test_reintento_identico_y_id_reutilizado(self):
        guardar_actual(self.conn, **self.packet())
        before = leer_snapshot(self.conn)
        self.assertTrue(guardar_actual(self.conn, **self.packet())['repetido'])
        self.assertEqual(before, leer_snapshot(self.conn))
        with self.assertRaises(ConflictoActualizacion):
            guardar_actual(self.conn, **self.packet(linepack_sm3=3))
        self.assertEqual(before, leer_snapshot(self.conn))

    def test_paquete_retrasado_y_revision_conflictiva(self):
        first = guardar_actual(self.conn, **self.packet())
        with self.assertRaises(ConflictoActualizacion):
            guardar_actual(self.conn, **self.packet(actualizacion_id='p2', calculado_en='2026-09-18T11:00:00Z'))
        guardar_actual(self.conn, **self.packet(actualizacion_id='p2', calculado_en='2026-09-18T11:00:00Z',
                                               revision_anterior=first['revision']))
        with self.assertRaises(ConflictoActualizacion):
            guardar_actual(self.conn, **self.packet())

    def test_cambio_geometria_y_catalogo_rechazan_resultado(self):
        data = json.loads(self.geo.read_text())
        data['tramos']['A']['longitud_metros'] = 20000
        self.geo.write_text(json.dumps(data))
        importar_geometrias(self.conn, self.geo)
        with self.assertRaises(ConflictoActualizacion):
            guardar_actual(self.conn, **self.packet())
        config = json.loads(self.config.read_text())
        config['sistemas']['s']['tramos'][0]['presion-ingreso'] = 'NUEVA'
        self.config.write_text(json.dumps(config))
        importar_catalogo(self.conn, self.config)
        with self.assertRaises(ConflictoActualizacion):
            guardar_actual(self.conn, **self.packet(geometria_version=2))

    def test_inactivo_no_admite_resultado(self):
        self.geo.write_text('{"version_formato":1,"tramos":{}}')
        importar_geometrias(self.conn, self.geo)
        with self.assertRaises(ConflictoActualizacion):
            guardar_actual(self.conn, **self.packet(geometria_version=2))

    def test_prediccion_72_y_firma(self):
        guardar_prediccion(self.conn, **self.pred())
        row = leer_snapshot(self.conn)['tablas']['predicciones_linepack'][0]
        self.assertEqual(json.loads(row['firma_presiones_json']), [4549] * 72)
        self.assertEqual(json.loads(row['presiones_json'])[71], 45.498474)
        self.assertEqual(json.loads(row['linepacks_json'])[0], 7993.124)
        self.assertTrue(guardar_prediccion(self.conn, **self.pred())['repetido'])

    def test_series_invalidas_conservan_resultado(self):
        saved = guardar_prediccion(self.conn, **self.pred())
        before = leer_snapshot(self.conn)
        for values in ([1] * 71, [1] * 73, [1] * 71 + [float('nan')],
                       [1] * 71 + [True], [1] * 71 + [-1]):
            for name in ('presiones', 'linepacks'):
                with self.subTest(name=name, values=values[-1:]), self.assertRaises(ValueError):
                    guardar_prediccion(self.conn, **self.pred(**{name: values, 'actualizacion_id': 'p2',
                        'revision_anterior': saved['revision'], 'calculado_en': '2026-09-18T11:00:00Z'}))
        self.assertEqual(before, leer_snapshot(self.conn))

    def test_firma_decimales_negativos_y_extremos(self):
        values = [1.15] * 72
        self.assertEqual(firma_presiones(values), [115] * 72)
        values[0], values[71] = -1.159, 2.999
        signature = firma_presiones(values)
        self.assertEqual(signature[0], -115)
        self.assertEqual(signature[71], 299)

    def test_datos_actuales_invalidos_sin_mutacion(self):
        before = leer_snapshot(self.conn)
        for changes in ({'presion_promedio_bar_abs': 0}, {'linepack_sm3': float('inf')},
                        {'linepack_sm3': True}, {'revision_anterior': True},
                        {'actualizacion_id': ''}, {'calculado_en': '2026-09-18T10:00:00'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                guardar_actual(self.conn, **self.packet(**changes))
        self.assertEqual(before, leer_snapshot(self.conn))

    def test_rollback_resultado_y_revision_si_falla_estado(self):
        self.conn.execute("CREATE TRIGGER fallo BEFORE INSERT ON estado_adquisicion "
                          "BEGIN SELECT RAISE(ABORT, 'ensayo'); END")
        before = leer_snapshot(self.conn)
        with self.assertRaises(sqlite3.IntegrityError):
            guardar_actual(self.conn, **self.packet())
        self.assertEqual(before, leer_snapshot(self.conn))
        self.conn.execute('DROP TRIGGER fallo')
        self.assertEqual(guardar_actual(self.conn, **self.packet())['revision'], 3)

    def test_verificacion_sin_cambios_y_error_conserva_valores(self):
        saved = guardar_prediccion(self.conn, **self.pred())
        before = leer_snapshot(self.conn)['tablas']['predicciones_linepack']
        kwargs = dict(tramo_id='A', ciclo='predictivo', observado_en='2026-09-18T10:10:00Z',
                      estado='valido', resultado_revision=saved['revision'])
        registrar_adquisicion(self.conn, **kwargs)
        self.assertTrue(registrar_adquisicion(self.conn, **kwargs)['repetido'])
        registrar_adquisicion(self.conn, tramo_id='A', ciclo='predictivo',
                             observado_en='2026-09-18T10:20:00Z', estado='error_lectura', detalle='Bad')
        snap = leer_snapshot(self.conn)
        self.assertEqual(snap['tablas']['predicciones_linepack'], before)
        state = snap['tablas']['estado_adquisicion'][0]
        self.assertEqual(state['ultima_lectura_valida_en'], '2026-09-18T10:10:00.000000+00:00')
        self.assertEqual(state['estado'], 'error_lectura')
        # Reintentar paquete ya guardado no debe borrar el error más reciente.
        guardar_prediccion(self.conn, **self.pred())
        self.assertEqual(snap, leer_snapshot(self.conn))

    def test_adquisicion_vieja_o_revision_invalida(self):
        saved = guardar_actual(self.conn, **self.packet())
        for date, revision in (('2026-09-18T09:00:00Z', saved['revision']),
                               ('2026-09-18T11:00:00Z', 999)):
            with self.assertRaises(ConflictoActualizacion):
                registrar_adquisicion(self.conn, tramo_id='A', ciclo='actual', observado_en=date,
                                     estado='valido', resultado_revision=revision)

    def test_snapshot_incremental_inactivaciones_y_cursor(self):
        initial = leer_snapshot(self.conn)
        self.assertEqual(initial['revision'], 2)
        self.assertFalse(any(leer_snapshot(self.conn, 2)['tablas'].values()))
        guardar_actual(self.conn, **self.packet())
        delta = leer_snapshot(self.conn, 2)
        self.assertFalse(delta['tablas']['tramos'])
        self.assertEqual(len(delta['tablas']['resultados_actuales']), 1)
        self.config.write_text('{"sistemas":{}}')
        importar_catalogo(self.conn, self.config)
        delta = leer_snapshot(self.conn, 3)
        self.assertEqual(delta['tablas']['tramos'][0]['activo'], 0)
        with self.assertRaises(ValueError):
            leer_snapshot(self.conn, 999)

    def test_snapshot_con_escritura_entre_consultas_no_omite_cambios(self):
        reader = abrir_base(self.path, solo_lectura=True)
        written = []

        def durante_lectura(sql):
            if sql.startswith('SELECT * FROM resultados_actuales') and not written:
                written.append(guardar_actual(self.conn, **self.packet()))

        try:
            reader.set_trace_callback(durante_lectura)
            snap = leer_snapshot(reader)
            reader.set_trace_callback(None)
            self.assertEqual(len(written), 1)
            self.assertEqual(snap['revision'], 2)
            self.assertFalse(snap['tablas']['resultados_actuales'])
            self.assertFalse(snap['tablas']['estado_adquisicion'])
            delta = leer_snapshot(reader, snap['revision'])
            self.assertEqual(delta['revision'], 3)
            self.assertEqual(len(delta['tablas']['resultados_actuales']), 1)
            self.assertEqual(len(delta['tablas']['estado_adquisicion']), 1)
        finally:
            reader.close()

    def test_verificacion_no_renueva_resultado_con_geometria_obsoleta(self):
        saved = guardar_prediccion(self.conn, **self.pred())
        data = json.loads(self.geo.read_text())
        data['tramos']['A']['longitud_metros'] = 20000
        self.geo.write_text(json.dumps(data))
        importar_geometrias(self.conn, self.geo)
        with self.assertRaises(ConflictoActualizacion):
            registrar_adquisicion(self.conn, tramo_id='A', ciclo='predictivo', estado='valido',
                                 resultado_revision=saved['revision'], observado_en='2026-09-18T11:00:00Z')

    def test_prediccion_falla_estado_revierte_serie_y_firma(self):
        self.conn.execute("CREATE TRIGGER fallo BEFORE INSERT ON estado_adquisicion "
                          "BEGIN SELECT RAISE(ABORT, 'ensayo'); END")
        before = leer_snapshot(self.conn)
        with self.assertRaises(sqlite3.IntegrityError):
            guardar_prediccion(self.conn, **self.pred())
        self.assertEqual(before, leer_snapshot(self.conn))

    def test_dos_productores_en_procesos_independientes(self):
        ctx = multiprocessing.get_context('spawn')
        queue = ctx.Queue()
        processes = [ctx.Process(target=_producir, args=(str(self.path),
                     self.packet(actualizacion_id='p' + str(i)), queue)) for i in range(2)]
        try:
            for process in processes:
                process.start()
            for process in processes:
                process.join(15)
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(sorted([queue.get(timeout=2), queue.get(timeout=2)]), ['conflicto', 'guardado'])
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(5)
            queue.close()
            queue.join_thread()

    def test_migracion_v2_conserva_catalogo_y_geometria(self):
        for table in ('estado_adquisicion', 'resultados_actuales', 'predicciones_linepack'):
            self.conn.execute('DROP TABLE ' + table)
        self.conn.execute('PRAGMA user_version=2')
        self.conn.execute("UPDATE metadatos SET valor=2 WHERE clave='version_esquema'")
        self.conn.close()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['migrar-base', '--base', str(self.path),
                                   '--backup', str(self.root / 'v2.backup')]), 0)
        conn = abrir_base(self.path)
        try:
            snap = leer_snapshot(conn)
            self.assertEqual(snap['revision'], 2)
            self.assertEqual(snap['tablas']['geometrias'][0]['longitud_metros'], 10000)
            guardar_actual(conn, **self.packet())
        finally:
            conn.close()

    def test_consola_validar_consultar_importar_crear_y_error(self):
        for args in (['validar-config', '--archivo', str(self.config)],
                     ['validar-geometria', '--archivo', str(self.geo)],
                     ['mostrar-estado', '--base', str(self.path)],
                     ['importar-config', '--base', str(self.path), '--archivo', str(self.config)],
                     ['importar-geometria', '--base', str(self.path), '--archivo', str(self.geo)],
                     ['crear-base', '--base', str(self.root / 'nueva.sqlite3')]):
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                self.assertEqual(main(args), 0)
            self.assertIsInstance(json.loads(stream.getvalue()), dict)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['crear-base', '--base', str(self.path)]), 2)


if __name__ == '__main__':
    unittest.main()
