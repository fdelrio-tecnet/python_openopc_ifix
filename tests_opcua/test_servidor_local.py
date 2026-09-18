"""Integración opt-in. Abre puerto efímero SOLO en 127.0.0.1; requiere entorno UA."""

import copy
import asyncio
import logging
import socket
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from asyncua import Client, ua
from servidor_opcua.adaptador import AdaptadorUA
from servidor_opcua.configuracion import ConfiguracionUA
from servidor_opcua.publicacion import preparar_publicacion
from servidor_opcua.productor_prueba import crear_ensayo
from servidor_opcua.cliente_prueba import consultar
from servidor_opcua.__main__ import _leer
from servidor_opcua.__main__ import ejecutar
from almacenamiento import abrir_base, guardar_actual


class ServidorLocalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        logging.getLogger('asyncua').setLevel(logging.ERROR)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = crear_ensayo(Path(self.tmp.name) / 'ensayo.sqlite3')
        # Puerto efímero de test; carrera de reserva/cierre posible, falla sin forzar otro servicio.
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        self.config = ConfiguracionUA(self.base, puerto=port)
        self.snapshot = _leer(self.base)
        self.now = datetime.now(timezone.utc)
        self.values = preparar_publicacion(self.snapshot, ahora=self.now)
        self.adapter = AdaptadorUA(self.config)
        self.addAsyncCleanup(self.cerrar)
        await self.adapter.iniciar(self.values)

    async def cerrar(self):
        if self.adapter is not None:
            await self.adapter.cerrar()

    async def test_valores_tipos_array_y_solo_lectura(self):
        async with Client(self.config.endpoint) as client:
            idx = await client.get_namespace_index(self.config.namespace_uri)
            for publication in self.values:
                node = client.get_node(ua.NodeId(publication.nodo.clave, idx))
                value = await node.read_data_value()
                self.assertTrue(value.StatusCode.is_good())
                self.assertEqual(await node.read_data_type(), ua.NodeId(ua.ObjectIds.Double))
                self.assertEqual(value.SourceTimestamp, publication.calculado_en)
                if publication.nodo.dimensiones:
                    self.assertEqual(await node.read_value_rank(), 1)
                    self.assertEqual(await node.read_array_dimensions(), [72])
                    self.assertEqual(value.Value.Value[0], 7993.12)
                    self.assertEqual(value.Value.Value[71], 8064.12)
                    self.assertEqual(len(value.Value.Value), 72)
                with self.assertRaises(ua.UaStatusCodeError):
                    await node.write_value(123.0, ua.VariantType.Double)
            with self.assertRaises(ua.UaStatusCodeError):
                await client.nodes.objects.add_folder(ua.NodeId('intruso', idx), 'intruso')

    async def test_sin_resultado_bad_y_null_no_cero(self):
        data = copy.deepcopy(self.snapshot)
        data['tablas']['resultados_actuales'] = []
        data['tablas']['predicciones_linepack'] = []
        await self.adapter.publicar(preparar_publicacion(data, ahora=self.now))
        result = await consultar(self.config, 'ENSAYO-001', 'ENSAYO_001')
        self.assertTrue(all(r['estado'] == 'BadWaitingForInitialData' and r['valor'] is None for r in result))

    async def test_vencimiento_sin_cambios_y_falla_fuente(self):
        await self.adapter.publicar(preparar_publicacion(self.snapshot, ahora=self.now + timedelta(hours=1)))
        result = await consultar(self.config, 'ENSAYO-001', 'ENSAYO_001')
        self.assertTrue(all(r['estado'] == 'UncertainLastUsableValue' for r in result))
        await self.adapter.invalidar_fuente()
        result = await consultar(self.config, 'ENSAYO-001', 'ENSAYO_001')
        self.assertTrue(all(r['estado'] == 'BadNoCommunication' and r['valor'] is None for r in result))

    async def test_reinicio_mismas_identidades_y_fechas(self):
        before = await consultar(self.config, 'ENSAYO-001', 'ENSAYO_001')
        await self.adapter.cerrar()
        self.adapter = AdaptadorUA(self.config)
        await self.adapter.iniciar(self.values)
        after = await consultar(self.config, 'ENSAYO-001', 'ENSAYO_001')
        self.assertEqual(before, after)

    async def test_catalogo_distinto_requiere_reinicio(self):
        data = copy.deepcopy(self.snapshot)
        data['tablas']['tramos'][0]['base_tag'] = 'OTRO_TAG'
        with self.assertRaises(ValueError):
            await self.adapter.publicar(preparar_publicacion(data, ahora=self.now))

    async def test_puerto_ocupado_no_se_reemplaza(self):
        other = AdaptadorUA(self.config)
        try:
            with self.assertRaises(OSError):
                await other.iniciar(self.values)
            result = await consultar(self.config, 'ENSAYO-001', 'ENSAYO_001')
            self.assertEqual(result[0]['valor'], 45.498)
        finally:
            await other.cerrar()

    async def test_sondeo_real_actualiza_y_cancelacion_cierra_listener(self):
        await self.adapter.cerrar()
        self.adapter = None
        config = ConfiguracionUA(self.base, puerto=self.config.puerto, sondeo_segundos=0.1)
        task = asyncio.create_task(ejecutar(config))

        async def esperar(valor):
            for _ in range(60):
                if task.done():
                    task.result()
                try:
                    result = await consultar(config, 'ENSAYO-001', 'ENSAYO_001')
                    if result[1]['valor'] == valor:
                        return
                except (OSError, asyncio.TimeoutError):
                    pass
                await asyncio.sleep(0.1)
            self.fail('No llegó el valor esperado por el sondeo')

        try:
            await asyncio.wait_for(esperar(7993.12), 15)
            conn = abrir_base(self.base)
            try:
                guardar_actual(conn, tramo_id='ENSAYO-001', geometria_version=1,
                               catalogo_revision=1, revision_anterior=3, actualizacion_id='ensayo-siguiente',
                               calculado_en=datetime.now(timezone.utc).isoformat(),
                               presion_promedio_bar_abs=46.0, linepack_sm3=8000.0)
            finally:
                conn.close()
            await asyncio.wait_for(esperar(8000.0), 15)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        with socket.socket() as probe:
            probe.settimeout(1)
            self.assertNotEqual(probe.connect_ex(('127.0.0.1', config.puerto)), 0)


if __name__ == '__main__':
    unittest.main()
