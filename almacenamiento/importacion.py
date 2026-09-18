"""Importaciones completas: validación fuera del bloqueo, activación atómica."""

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from python_scheduler.parse_config_json import construir_estructura_tramos
from .conexion import Ruta, _validar_esquema, transaccion


CAMPOS_GEOMETRIA = (
    'diametro_exterior_pulgadas', 'espesor_milimetros', 'longitud_metros',
)


def _objeto_sin_duplicados(pares):
    result = {}
    for key, value in pares:
        if key in result:
            raise ValueError("Miembro JSON duplicado: {!r}".format(key))
        result[key] = value
    return result


def _constante_invalida(value):
    raise ValueError('Constante no permitida en JSON: ' + value)


def _leer_json(ruta: Ruta) -> Any:
    try:
        with Path(ruta).open(encoding='utf-8-sig') as archivo:
            return json.load(archivo, object_pairs_hook=_objeto_sin_duplicados,
                             parse_constant=_constante_invalida)
    except ValueError as exc:
        raise ValueError('{}: {}'.format(ruta, exc)) from exc


def validar_catalogo(ruta: Ruta) -> Dict[str, Dict[str, Any]]:
    """Lee JSON compartido sin alterarlo; devuelve filas planas sin estados OPC.

    Reutiliza el parser del calculador y rechaza miembros JSON duplicados.
    ValueError ante contenido inválido; errores de archivo se propagan.
    IDs se comparan exactamente tras strip; base-tags usan casefold.
    """
    tramos = construir_estructura_tramos(_leer_json(ruta))
    return {key: dict(base_tag=t['base_tag'],
                      base_tag_clave=t['base_tag'].casefold(),
                      presion_ingreso_tag=t['tags']['presion_ingreso'],
                      presion_egreso_tag=t['tags']['presion_egreso'])
            for key, t in tramos.items()}


def validar_geometrias(ruta: Ruta) -> Dict[str, Dict[str, float]]:
    """Lee formato 1 y devuelve geometrías por ID, en pulgadas/mm/metros.

    Rechaza campos desconocidos, duplicados, booleanos, no finitos, magnitudes
    no positivas y diámetro interno no positivo/no finito mediante ValueError.
    Acepta catálogo vacío; no consulta SQLite ni exige IDs presentes en catálogo.
    """
    data = _leer_json(ruta)
    if not isinstance(data, dict) or set(data) != {'version_formato', 'tramos'}:
        raise ValueError('Geometría requiere exactamente version_formato y tramos')
    if type(data['version_formato']) is not int or data['version_formato'] != 1:
        raise ValueError('version_formato debe ser el entero 1')
    if not isinstance(data['tramos'], dict):
        raise ValueError('tramos de geometría debe ser un objeto')
    result = {}
    for raw_id, values in data['tramos'].items():
        key = raw_id.strip()
        if not key or key in result:
            raise ValueError('ID vacío o duplicado tras normalizar: ' + repr(raw_id))
        if not isinstance(values, dict) or set(values) != set(CAMPOS_GEOMETRIA):
            raise ValueError('{}: campos geométricos incompletos o desconocidos'.format(key))
        row = {}
        for field in CAMPOS_GEOMETRIA:
            value = values[field]
            try:
                valid = (type(value) in (int, float) and math.isfinite(value) and value > 0)
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError('{}: {} debe ser número finito positivo'.format(key, field))
            row[field] = float(value)
        interno = row[CAMPOS_GEOMETRIA[0]] * 0.0254 - 2 * row[CAMPOS_GEOMETRIA[1]] / 1000
        if not math.isfinite(interno) or interno <= 0:
            raise ValueError('{}: diámetro interno inválido'.format(key))
        result[key] = row
    return result


def importar_catalogo(conn: sqlite3.Connection, ruta: Ruta) -> Dict[str, Any]:
    """Importa archivo completo, inactiva omitidos y devuelve resumen tras COMMIT.

    Conexión v2 escritora sin transacción abierta; no la cierra. Validación falla
    sin mutar; fallos SQLite revierten todas las filas y revisión. Resumen incluye
    conteos, IDs inactivados/reactivados, cambios de base-tag y discordancias.
    """
    return _importar(conn, validar_catalogo(ruta), geometria=False)


def importar_geometrias(conn: sqlite3.Connection, ruta: Ruta) -> Dict[str, Any]:
    """Importa geometría completa con mismo contrato transaccional que catálogo.

    Omitidos se inactivan, no se borran. Cambio de valor/activación incrementa
    versión y fecha UTC; reimportación idéntica no cambia nada. IDs ajenos aceptados.
    """
    return _importar(conn, validar_geometrias(ruta), geometria=True)


def _importar(conn, incoming, *, geometria):
    table, keycol, active = ('geometrias', 'tramo_id', 'activa') if geometria else (
        'tramos', 'id', 'activo')
    fields = CAMPOS_GEOMETRIA if geometria else (
        'base_tag', 'base_tag_clave', 'presion_ingreso_tag', 'presion_egreso_tag')
    with transaccion(conn, escritura=True):
        _validar_esquema(conn)
        previous = {r[keycol]: dict(r) for r in conn.execute('SELECT * FROM ' + table)}
        added = sorted(set(incoming) - set(previous))
        modified = sorted(k for k in incoming if k in previous and (
            not previous[k][active] or any(previous[k][f] != incoming[k][f] for f in fields)))
        omitted = sorted(k for k in previous if previous[k][active] and k not in incoming)
        reactivated = [k for k in modified if not previous[k][active]]
        base_changes = [] if geometria else [
            {'id': k, 'anterior': previous[k]['base_tag'], 'nuevo': incoming[k]['base_tag']}
            for k in modified if previous[k]['base_tag'] != incoming[k]['base_tag']]
        revision = conn.execute(
            "SELECT valor FROM metadatos WHERE clave='revision_global'").fetchone()[0]
        if added or modified or omitted:
            revision += 1
            conn.execute("UPDATE metadatos SET valor=? WHERE clave='revision_global'", (revision,))
            now = datetime.now(timezone.utc).isoformat(timespec='microseconds')
            if not geometria:
                # Libera claves antes de intercambios de base-tag A<->B en la misma carga.
                conn.executemany('UPDATE tramos SET activo=0 WHERE id=?',
                                 [(k,) for k in modified + omitted])
            for key in omitted:
                if geometria:
                    conn.execute('UPDATE geometrias SET activa=0, version=version+1, '
                                 'actualizada_en=?, revision=? WHERE tramo_id=?', (now, revision, key))
                else:
                    conn.execute('UPDATE tramos SET revision=? WHERE id=?', (revision, key))
            for key in added + modified:
                row = dict(incoming[key], **{active: 1, 'revision': revision})
                if geometria:
                    row.update(version=previous[key]['version'] + 1 if key in previous else 1,
                               actualizada_en=now)
                columns = list(row)
                values = [row[f] for f in columns]
                if key in previous:
                    conn.execute('UPDATE {} SET {} WHERE {}=?'.format(
                        table, ', '.join(f + '=?' for f in columns), keycol), values + [key])
                else:
                    conn.execute('INSERT INTO {} ({}) VALUES ({})'.format(
                        table, ', '.join(columns + [keycol]), ', '.join('?' for _ in values + [key])),
                        values + [key])
        catalog = {r[0] for r in conn.execute('SELECT id FROM tramos WHERE activo=1')}
        geometries = {r[0] for r in conn.execute('SELECT tramo_id FROM geometrias WHERE activa=1')}
        summary = dict(agregados=len(added), modificados=len(modified),
                       inalterados=len(incoming) - len(added) - len(modified),
                       inactivados=len(omitted), ids_inactivados=omitted,
                       ids_reactivados=reactivated, cambios_base_tag=base_changes,
                       catalogo_sin_geometria=sorted(catalog - geometries),
                       geometria_sin_catalogo=sorted(geometries - catalog), revision=revision)
    return summary
