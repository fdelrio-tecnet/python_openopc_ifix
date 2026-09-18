"""Ejecutar con python -m administracion --help desde la raíz del proyecto."""

import argparse
import json
import sqlite3
import sys

from almacenamiento import (
    abrir_base, inicializar_base, importar_catalogo, importar_geometrias,
    leer_snapshot, migrar_base, validar_catalogo, validar_geometrias,
)


def main(argv=None):
    """Consola local: JSON en stdout; errores en stderr y código 2, éxito 0.

    Crear/migrar/importar son acciones explícitas, nunca ejecutadas al consultar.
    No borra ni sobreescribe bases. Omitidos se inactivan al importar archivos completos.
    """
    parser = argparse.ArgumentParser(description='Administración SQLite de linepack, sin OPC')
    commands = parser.add_subparsers(dest='comando', required=True)
    for command in ('crear-base', 'migrar-base', 'mostrar-estado', 'validar-config',
                    'validar-geometria', 'importar-config', 'importar-geometria'):
        sub = commands.add_parser(command)
        if not command.startswith('validar-'):
            sub.add_argument('--base', required=True, help='Ruta absoluta en disco local')
        if command.startswith(('validar-', 'importar-')):
            sub.add_argument('--archivo', required=True, help='JSON completo, no un delta')
        if command == 'migrar-base':
            sub.add_argument('--backup', required=True, help='Ruta absoluta de backup NUEVO')
    args = parser.parse_args(argv)
    try:
        if args.comando == 'crear-base':
            result = {'base': str(inicializar_base(args.base)), 'creada': True}
        elif args.comando == 'migrar-base':
            result = {'backup': str(migrar_base(args.base, args.backup)), 'version_esquema': 3}
        elif args.comando.startswith('validar-'):
            operation = validar_catalogo if args.comando == 'validar-config' else validar_geometrias
            result = {'valido': True, 'tramos': len(operation(args.archivo))}
        else:
            conn = abrir_base(args.base, solo_lectura=args.comando == 'mostrar-estado')
            try:
                if args.comando == 'mostrar-estado':
                    result = leer_snapshot(conn)
                else:
                    operation = importar_catalogo if args.comando == 'importar-config' else importar_geometrias
                    result = operation(conn, args.archivo)
            finally:
                conn.close()
        print(json.dumps(result, ensure_ascii=True, allow_nan=False))
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
