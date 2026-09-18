import json
import tempfile
import unittest
from pathlib import Path

from servidor_opcua.configuracion import ConfiguracionUA, cargar_configuracion
from servidor_opcua.productor_prueba import crear_ensayo
from almacenamiento import abrir_base, leer_snapshot


class ConfiguracionUATests(unittest.TestCase):
    def test_resolucion_portable_y_loopback(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'servidor.json'
            file.write_text(json.dumps({'base_sqlite': 'linepack.sqlite3', 'puerto': 49123}))
            config = cargar_configuracion(file)
            self.assertEqual(config.base_sqlite, (Path(folder) / 'linepack.sqlite3').resolve())
            self.assertEqual(config.endpoint, 'opc.tcp://127.0.0.1:49123/linepack/')
            self.assertFalse(config.base_sqlite.exists())

    def test_opciones_no_admiten_host_o_claves_duplicadas(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'servidor.json'
            for raw in ('{"base_sqlite":"a","host":"0.0.0.0"}',
                        '{"base_sqlite":"a","puerto":1,"puerto":2}'):
                file.write_text(raw)
                with self.assertRaises(ValueError):
                    cargar_configuracion(file)

    def test_parametros_invalidos(self):
        base = Path.cwd() / 'no-creada.sqlite3'
        for kwargs in ({'puerto': True}, {'puerto': 0}, {'puerto': 65536},
                       {'namespace_uri': 'http://otro'}, {'sondeo_segundos': float('nan')},
                       {'sondeo_segundos': 0}, {'vigencia_actual_segundos': -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ConfiguracionUA(base, **kwargs)

    def test_productor_sintetico_no_sobrescribe(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / 'ensayo.sqlite3'
            crear_ensayo(base)
            with self.assertRaises(FileExistsError):
                crear_ensayo(base)
            conn = abrir_base(base, solo_lectura=True)
            try:
                data = leer_snapshot(conn)
                self.assertEqual(data['tablas']['tramos'][0]['id'], 'ENSAYO-001')
                self.assertEqual(len(json.loads(data['tablas']['predicciones_linepack'][0]['linepacks_json'])), 72)
            finally:
                conn.close()
