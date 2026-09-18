"""Servidor de ensayo: python -m servidor_opcua --config ARCHIVO --ensayo-local."""

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from almacenamiento import abrir_base, leer_snapshot
from .configuracion import cargar_configuracion
from .publicacion import preparar_publicacion

logger = logging.getLogger(__name__)


def _leer(base):
    # Abrir/leer/cerrar en el mismo worker; nunca compartir una conexión entre hilos.
    conn = abrir_base(base, solo_lectura=True)
    try:
        return leer_snapshot(conn)
    finally:
        conn.close()


async def ejecutar(config):
    """Sondea snapshots completos fuera del event loop. Fallo global: invalida y sale.

    No reconexión automática/servicio ni sondeo incremental en esta parte. Ctrl+C
    cancela el bucle y cierra. La base debe existir; no migra/importa al arrancar.
    """
    from .adaptador import AdaptadorUA

    adapter = AdaptadorUA(config)
    try:
        snapshot = await asyncio.to_thread(_leer, config.base_sqlite)
        values = preparar_publicacion(snapshot, ahora=datetime.now(timezone.utc), politica=config.politica)
        await adapter.iniciar(values)
        logger.info('Ensayo local escuchando en %s; %s nodos', config.endpoint, len(values))
        while True:
            await asyncio.sleep(config.sondeo_segundos)
            snapshot = await asyncio.to_thread(_leer, config.base_sqlite)
            values = preparar_publicacion(snapshot, ahora=datetime.now(timezone.utc), politica=config.politica)
            await adapter.publicar(values)
    except Exception:
        if adapter.nodos:
            try:
                await adapter.invalidar_fuente()
            except Exception:
                logging.exception('No se pudo invalidar toda la salida; se cerrará el servidor')
        raise
    finally:
        await adapter.cerrar()


def main(argv=None):
    """CLI de ensayo explícito; éxito/interrupción 0, falla 1, argumentos inválidos 2."""
    parser = argparse.ArgumentParser(description='Servidor UA de ensayo local, no despliegue productivo')
    parser.add_argument('--config', required=True)
    parser.add_argument('--ensayo-local', action='store_true', required=True,
                        help='Acepta perfil local anónimo sin cifrado, solo para pruebas')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    logger.setLevel(logging.INFO)
    try:
        config = cargar_configuracion(args.config)
        asyncio.run(ejecutar(config))
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        logging.exception('Servidor detenido por error')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
