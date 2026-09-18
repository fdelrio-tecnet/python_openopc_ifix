"""Modelo del publicador sin sockets, COM ni dependencia OPC UA."""

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from almacenamiento import (
    abrir_base, guardar_actual, guardar_prediccion, importar_catalogo,
    importar_geometrias, inicializar_base, leer_snapshot,
)
from servidor_opcua import PoliticaVigencia, definir_nodos, preparar_publicacion


FECHA = '2026-09-18T10:00:00.000000+00:00'
AHORA = datetime.fromisoformat(FECHA)


def snapshot():
    common = dict(tramo_id='A', geometria_version=1, catalogo_revision=1,
                  calculado_en=FECHA, actualizacion_id='paquete')
    return {'revision': 4, 'tablas': {
        'tramos': [dict(id='A', base_tag='SYS_A', activo=1, revision=1)],
        'geometrias': [dict(tramo_id='A', activa=1, version=1, revision=2)],
        'resultados_actuales': [dict(common, revision=3,
                                    presion_promedio_bar_abs=45.498474367603876,
                                    linepack_sm3=7993.124399335523)],
        'predicciones_linepack': [dict(common, revision=4, presiones_json=json.dumps([45.498474] * 72),
                                     linepacks_json=json.dumps([7993.124] * 72),
                                     firma_presiones_json=json.dumps([4549] * 72))],
        'estado_adquisicion': [dict(tramo_id='A', ciclo=ciclo, estado='valido', detalle=None,
                                   ultimo_intento_en=FECHA, ultima_lectura_valida_en=FECHA,
                                   resultado_revision=revision, revision=revision)
                               for ciclo, revision in (('actual', 3), ('predictivo', 4))],
    }}


class PublicacionTests(unittest.TestCase):
    def test_nodos_nombres_dimensiones_y_claves_estables(self):
        nodes = definir_nodos('037-001-A', 'SYS_037_001_A')
        self.assertEqual([n.nombre for n in nodes], [
            'SYS_037_001_A_PPROMEDIO', 'SYS_037_001_A_LINEPACK', 'SYS_037_001_A_LINEPACK_PRED'])
        self.assertEqual([n.dimensiones for n in nodes], [(), (), (72,)])
        self.assertTrue(all(not n.escribible for n in nodes))
        changed = definir_nodos('037-001-A', 'NUEVO_TAG')
        self.assertEqual([n.clave for n in nodes], [n.clave for n in changed])
        self.assertNotEqual(definir_nodos('A/B', 'TAG')[0].clave,
                            definir_nodos('A%2FB', 'TAG')[0].clave)
        with self.assertRaises(ValueError):
            definir_nodos('', 'TAG')

    def test_precision_presentacion_y_no_mutacion(self):
        data = snapshot()
        original = copy.deepcopy(data)
        values = preparar_publicacion(data, ahora=AHORA)
        self.assertEqual([v.disponibilidad for v in values], ['disponible'] * 3)
        self.assertEqual([v.valor for v in values[:2]], [45.498, 7993.12])
        self.assertEqual(values[2].valor, (7993.12,) * 72)
        self.assertEqual(values[0].calculado_en, AHORA)
        self.assertEqual(original, data)
        # Valores diferentes en cada índice detectan inversión/mezcla de posiciones.
        serie = [7000 + i / 10 for i in range(72)]
        data['tablas']['predicciones_linepack'][0]['linepacks_json'] = json.dumps(serie)
        self.assertEqual(preparar_publicacion(data, ahora=AHORA)[2].valor, tuple(serie))

    def test_sin_resultados_no_inventa_ceros(self):
        data = snapshot()
        data['tablas']['resultados_actuales'] = []
        data['tablas']['predicciones_linepack'] = []
        values = preparar_publicacion(data, ahora=AHORA)
        self.assertTrue(all(v.valor is None and v.disponibilidad == 'no_disponible' for v in values))
        self.assertTrue(all(v.motivo == 'sin_resultado' for v in values))

    def test_vencimiento_sin_nuevas_revisiones_limites(self):
        data = snapshot()
        before = preparar_publicacion(data, ahora=AHORA + timedelta(seconds=119.999))
        self.assertEqual(before[0].disponibilidad, 'disponible')
        values = preparar_publicacion(data, ahora=AHORA + timedelta(seconds=120))
        self.assertEqual(values[0].disponibilidad, 'vencido')
        self.assertEqual(values[0].valor, 45.498)
        self.assertEqual(values[2].disponibilidad, 'disponible')
        values = preparar_publicacion(data, ahora=AHORA + timedelta(seconds=1800))
        self.assertEqual(values[2].disponibilidad, 'vencido')
        self.assertEqual(values[2].calculado_en, AHORA)

    def test_verificacion_reciente_no_rejuvenece_calculo_actual(self):
        data = snapshot()
        data['revision'] = 6
        for i, state in enumerate(data['tablas']['estado_adquisicion']):
            state.update(ultimo_intento_en=(AHORA + timedelta(hours=1)).isoformat(),
                         ultima_lectura_valida_en=(AHORA + timedelta(hours=1)).isoformat(), revision=5+i)
        values = preparar_publicacion(data, ahora=AHORA + timedelta(hours=1, seconds=1))
        self.assertEqual(values[0].disponibilidad, 'vencido')
        self.assertEqual(values[2].disponibilidad, 'disponible')
        self.assertEqual(values[2].calculado_en, AHORA)
        self.assertEqual(values[2].verificado_en, AHORA + timedelta(hours=1))

    def test_cambios_contexto_inactivos_y_sin_geometria(self):
        for table, field, value, reason in (
                ('tramos', 'activo', 0, 'tramo_inactivo'),
                ('geometrias', 'activa', 0, 'geometria_no_disponible'),
                ('geometrias', 'version', 2, 'contexto_modificado'),
                ('tramos', 'revision', 2, 'contexto_modificado')):
            data = snapshot()
            data['tablas'][table][0][field] = value
            with self.subTest(table=table, field=field):
                values = preparar_publicacion(data, ahora=AHORA)
                self.assertTrue(all(v.valor is None and v.motivo == reason for v in values))
        data = snapshot()
        data['tablas']['geometrias'] = []
        self.assertEqual(preparar_publicacion(data, ahora=AHORA)[2].motivo, 'geometria_no_disponible')

    def test_adquisicion_invalida_sin_marca_disponible(self):
        for estado in ('error_lectura', 'error_calculo'):
            data = snapshot()
            data['tablas']['estado_adquisicion'][0]['estado'] = estado
            values = preparar_publicacion(data, ahora=AHORA)
            self.assertEqual(values[0].motivo, estado)
            self.assertEqual(values[0].disponibilidad, 'no_disponible')
            self.assertEqual(values[0].valor, 45.498)
            self.assertEqual(values[2].disponibilidad, 'disponible')

    def test_adquisicion_de_otro_resultado_o_ausente(self):
        data = snapshot()
        data['tablas']['estado_adquisicion'][0]['resultado_revision'] = 2
        self.assertEqual(preparar_publicacion(data, ahora=AHORA)[0].motivo, 'adquisicion_no_corresponde')
        data['tablas']['estado_adquisicion'] = []
        self.assertEqual(preparar_publicacion(data, ahora=AHORA)[0].motivo, 'sin_adquisicion')

    def test_fechas_futuras_sin_zona_o_inconsistentes(self):
        data = snapshot()
        self.assertEqual(preparar_publicacion(data, ahora=AHORA), preparar_publicacion(
            data, ahora=AHORA.astimezone(timezone(timedelta(hours=-3)))))
        self.assertTrue(all(v.motivo == 'fecha_futura' for v in preparar_publicacion(
            data, ahora=AHORA - timedelta(seconds=1))))
        data['tablas']['resultados_actuales'][0]['calculado_en'] = '2026-09-18T10:00:00'
        self.assertEqual(preparar_publicacion(data, ahora=AHORA)[0].motivo, 'datos_invalidos')
        data = snapshot()
        data['tablas']['estado_adquisicion'][0]['ultimo_intento_en'] = (AHORA - timedelta(seconds=1)).isoformat()
        self.assertEqual(preparar_publicacion(data, ahora=AHORA)[0].motivo, 'datos_invalidos')
        with self.assertRaises(ValueError):
            preparar_publicacion(snapshot(), ahora=AHORA.replace(tzinfo=None))

    def test_series_corruptas_se_aislan_al_ciclo(self):
        for field, raw in (('linepacks_json', '[]'), ('linepacks_json', 'no-json'),
                           ('linepacks_json', '[' * 2000 + '0' + ']' * 2000),
                           ('linepacks_json', json.dumps([1] * 71 + [float('nan')])),
                           ('presiones_json', json.dumps([True] * 72)),
                           ('firma_presiones_json', json.dumps([4548] * 72))):
            data = snapshot()
            data['tablas']['predicciones_linepack'][0][field] = raw
            with self.subTest(field=field, raw=raw[:15]):
                values = preparar_publicacion(data, ahora=AHORA)
                self.assertEqual(values[2].motivo, 'datos_invalidos')
                self.assertIsNone(values[2].valor)
                self.assertEqual(values[0].disponibilidad, 'disponible')

    def test_numero_invalido_no_afecta_otro_tramo(self):
        data = snapshot()
        for table, rows in data['tablas'].items():
            extra = copy.deepcopy(rows)
            for row in extra:
                row['id' if table == 'tramos' else 'tramo_id'] = 'B'
                if table == 'tramos':
                    row['base_tag'] = 'SYS_B'
            rows.extend(extra)
        data['tablas']['resultados_actuales'][0]['linepack_sm3'] = float('inf')
        values = preparar_publicacion(data, ahora=AHORA)
        self.assertEqual(values[0].motivo, 'datos_invalidos')
        self.assertEqual(values[3].disponibilidad, 'disponible')

    def test_orden_y_reinicio_no_cambian_identidad_ni_fechas(self):
        data = snapshot()
        first = preparar_publicacion(data, ahora=AHORA)
        for rows in data['tablas'].values():
            rows.reverse()
        self.assertEqual(first, preparar_publicacion(data, ahora=AHORA + timedelta(seconds=1)))

    def test_politica_configurable_y_rechazo_de_umbral_invalido(self):
        values = preparar_publicacion(snapshot(), ahora=AHORA + timedelta(seconds=10),
                                       politica=PoliticaVigencia(10, 20))
        self.assertEqual(values[0].disponibilidad, 'vencido')
        self.assertEqual(values[2].disponibilidad, 'disponible')
        for value in (True, 0, -1, float('inf'), float('nan'), '120'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PoliticaVigencia(actual_segundos=value)

    def test_snapshot_incompleto_duplicado_o_revision_futura(self):
        data = snapshot()
        del data['tablas']['geometrias']
        with self.assertRaises(ValueError):
            preparar_publicacion(data, ahora=AHORA)
        data = snapshot()
        data['tablas']['tramos'].append(dict(data['tablas']['tramos'][0]))
        with self.assertRaises(ValueError):
            preparar_publicacion(data, ahora=AHORA)
        data = snapshot()
        data['revision'] = 2
        self.assertEqual(preparar_publicacion(data, ahora=AHORA)[0].motivo, 'datos_invalidos')

    def test_productor_sqlite_temporal_y_proyeccion_sin_escrituras(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'ensayo.sqlite3'
            inicializar_base(path)
            conn = abrir_base(path)
            try:
                config = root / 'config.json'
                config.write_text(json.dumps({'sistemas': {'s': {'tramos': [dict(
                    id='A', **{'base-tag': 'SYS_A', 'presion-ingreso': 'P', 'presion-egreso': 'Q'})]}}}))
                geo = root / 'geo.json'
                geo.write_text(json.dumps({'version_formato': 1, 'tramos': {'A': dict(
                    diametro_exterior_pulgadas=6, espesor_milimetros=4, longitud_metros=10000)}}))
                importar_catalogo(conn, config)
                importar_geometrias(conn, geo)
                packet = dict(tramo_id='A', geometria_version=1, catalogo_revision=1,
                              revision_anterior=0, actualizacion_id='ensayo', calculado_en=FECHA)
                guardar_actual(conn, **packet, presion_promedio_bar_abs=45.498474, linepack_sm3=7993.124)
                guardar_prediccion(conn, **packet, presiones=[45.498474] * 72, linepacks=[7993.124] * 72)
                before = leer_snapshot(conn)
                values = preparar_publicacion(before, ahora=AHORA)
                self.assertTrue(all(v.disponibilidad == 'disponible' for v in values))
                self.assertEqual(before, leer_snapshot(conn))
            finally:
                conn.close()


if __name__ == '__main__':
    unittest.main()
