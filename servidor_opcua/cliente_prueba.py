"""Cliente de diagnóstico local, solo lectura; no importa OpenOPC."""

import argparse
import asyncio
import json

from .configuracion import cargar_configuracion
from .nodos import definir_nodos


async def consultar(config, tramo_id, base_tag):
    """Lee tres DataValues incluyendo calidad no Good; no escribe ni crea nodos."""
    from asyncua import Client, ua

    result = []
    async with Client(config.endpoint) as client:
        idx = await client.get_namespace_index(config.namespace_uri)
        for spec in definir_nodos(tramo_id, base_tag):
            value = await client.get_node(ua.NodeId(spec.clave, idx)).read_data_value(False)
            result.append(dict(clave=spec.clave, estado=value.StatusCode.name,
                               valor=value.Value.Value if value.Value else None,
                               timestamp=value.SourceTimestamp.isoformat() if value.SourceTimestamp else None))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Leer un tramo del servidor UA de ensayo')
    parser.add_argument('--config', required=True)
    parser.add_argument('--tramo-id', default='ENSAYO-001')
    parser.add_argument('--base-tag', default='ENSAYO_001')
    args = parser.parse_args()
    print(json.dumps(asyncio.run(consultar(cargar_configuracion(args.config), args.tramo_id,
                                         args.base_tag)), ensure_ascii=True))
