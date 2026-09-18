"""Crea una base NUEVA con un tramo sintético; nunca actualiza una base existente."""

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from almacenamiento import (abrir_base, guardar_actual, guardar_prediccion,
                            importar_catalogo, importar_geometrias, inicializar_base)
from python_scheduler.constantes import CANTIDAD_PUNTOS_PREDICCION


def crear_ensayo(base):
    """Crea/cierra SQLite con ENSAYO-001. FileExistsError protege datos existentes.

    Valores sintéticos, no aprobación de resultados reales. Si falla conserva base
    parcial para diagnóstico; no borra ni sobreescribe. Devuelve ruta creada.
    """
    base = inicializar_base(Path(base))
    conn = abrir_base(base)
    try:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            geo = Path(directory) / 'geometria.json'
            config.write_text(json.dumps({'sistemas': {'ensayo': {'tramos': [{
                'id': 'ENSAYO-001', 'base-tag': 'ENSAYO_001',
                'presion-ingreso': 'ENTRADA.F_CV', 'presion-egreso': 'SALIDA.F_CV'}]}}}), encoding='utf-8')
            geo.write_text(json.dumps({'version_formato': 1, 'tramos': {'ENSAYO-001': {
                'diametro_exterior_pulgadas': 6, 'espesor_milimetros': 4, 'longitud_metros': 10000}}}), encoding='utf-8')
            cat = importar_catalogo(conn, config)
            importar_geometrias(conn, geo)
        packet = dict(tramo_id='ENSAYO-001', geometria_version=1, catalogo_revision=cat['revision'],
                      revision_anterior=0, actualizacion_id='ensayo-inicial',
                      calculado_en=datetime.now(timezone.utc).isoformat())
        guardar_actual(conn, **packet, presion_promedio_bar_abs=45.498474367603876,
                       linepack_sm3=7993.124399335523)
        guardar_prediccion(conn, **packet, presiones=[45.498474] * CANTIDAD_PUNTOS_PREDICCION,
                           linepacks=[7993.124 + i for i in range(CANTIDAD_PUNTOS_PREDICCION)])
    finally:
        conn.close()
    return base


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generar base NUEVA de ensayo, sin iFIX')
    parser.add_argument('--base', required=True, help='Ruta absoluta local nueva')
    args = parser.parse_args()
    print(crear_ensayo(args.base))
