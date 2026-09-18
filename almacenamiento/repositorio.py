"""Último estado, paquetes atómicos y snapshots; sin fórmulas ni conexiones OPC."""

import json
import math
from datetime import datetime, timezone
from decimal import Decimal

from python_scheduler.constantes import CANTIDAD_PUNTOS_PREDICCION
from .conexion import _validar_esquema, transaccion


TABLAS = ('tramos', 'geometrias', 'resultados_actuales',
          'predicciones_linepack', 'estado_adquisicion')
RESULTADOS = {'actual': 'resultados_actuales', 'predictivo': 'predicciones_linepack'}


class ConflictoActualizacion(ValueError):
    """Paquete obsoleto o ID reutilizado: releer estado y recalcular, no forzar."""


def _entero(value, nombre, minimo=0):
    if type(value) is not int or value < minimo or value > 9223372036854775807:
        raise ValueError(nombre + ': entero fuera de rango')
    return value


def _texto(value, nombre):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(nombre + ': texto vacío o inválido')
    return value.strip()


def _fecha(value):
    if not isinstance(value, str):
        raise ValueError('La fecha debe ser texto ISO 8601 con zona horaria')
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError('La fecha debe incluir zona horaria')
    return date.astimezone(timezone.utc).isoformat(timespec='microseconds')


def _numero(value, nombre, positivo=False):
    try:
        valido = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valido = False
    if not valido or value < 0 or (positivo and value == 0):
        raise ValueError(nombre + ': número finito fuera de rango')
    return float(value)


def firma_presiones(presiones):
    """72 centésimas enteras, truncadas hacia cero desde la representación decimal.

    Admite negativos para comparación; rechaza bool/no finitos y tamaño distinto
    de la constante compartida. Guardar una predicción exige presiones positivas.
    No modifica ni redondea los valores usados en cálculos.
    """
    if not isinstance(presiones, (list, tuple)) or len(presiones) != CANTIDAD_PUNTOS_PREDICCION:
        raise ValueError('La firma requiere exactamente 72 presiones')
    result = []
    for value in presiones:
        try:
            valido = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            valido = False
        if not valido:
            raise ValueError('Presión no finita o no numérica en firma')
        # scaleb desplaza el exponente sin introducir el error binario de * 100.
        decimal = Decimal(str(value))
        parts = decimal.as_tuple()
        result.append(int(Decimal((parts.sign, parts.digits, parts.exponent + 2))))
    return result


def _revision(conn):
    value = conn.execute("SELECT valor FROM metadatos WHERE clave='revision_global'").fetchone()[0]
    value = _entero(value + 1, 'revision')
    conn.execute("UPDATE metadatos SET valor=? WHERE clave='revision_global'", (value,))
    return value


def _fila(conn, table, tramo):
    row = conn.execute('SELECT * FROM ' + table + ' WHERE tramo_id=?', (tramo,)).fetchone()
    return dict(row) if row else None


def _contexto(conn, tramo, geometria_version, catalogo_revision):
    row = conn.execute('SELECT t.activo, t.revision, g.activa, g.version FROM tramos t '
                       'JOIN geometrias g ON g.tramo_id=t.id WHERE t.id=?', (tramo,)).fetchone()
    if not row or not row[0] or not row[2] or row[1] != catalogo_revision or row[3] != geometria_version:
        raise ConflictoActualizacion('Tramo/geometría inactivos, ausentes o modificados')


def _estado(conn, tramo, ciclo):
    row = conn.execute('SELECT * FROM estado_adquisicion WHERE tramo_id=? AND ciclo=?',
                       (tramo, ciclo)).fetchone()
    return dict(row) if row else None


def _escribir_estado(conn, tramo, ciclo, fecha, estado, detalle, resultado, revision):
    anterior = _estado(conn, tramo, ciclo)
    ultima = fecha if estado == 'valido' else (
        anterior['ultima_lectura_valida_en'] if anterior else None)
    conn.execute('INSERT OR REPLACE INTO estado_adquisicion VALUES (?,?,?,?,?,?,?,?)',
                 (tramo, ciclo, fecha, ultima, estado, detalle, resultado, revision))


def guardar_actual(conn, *, tramo_id, geometria_version, catalogo_revision,
                   revision_anterior, actualizacion_id, calculado_en,
                   presion_promedio_bar_abs, linepack_sm3):
    """Guarda pareja bar abs/Sm³ sin redondear, más adquisición válida atómica.

    Requiere conexión escritora v3 sin transacción. Revisión anterior de este
    resultado (0 si ausente), versión geométrica y revisión del tramo leídas antes
    de calcular. Fecha ISO con zona e ID único por paquete. Devuelve revisión e
    indicador repetido. ValueError: contrato; ConflictoActualizacion: concurrencia
    o paquete antiguo/ID reutilizado; SQLite: se propaga con rollback. No cierra conn.
    """
    values = dict(presion_promedio_bar_abs=_numero(presion_promedio_bar_abs, 'presion', True),
                  linepack_sm3=_numero(linepack_sm3, 'linepack'))
    return _guardar(conn, 'actual', tramo_id, geometria_version, catalogo_revision,
                    revision_anterior, actualizacion_id, calculado_en, values)


def guardar_prediccion(conn, *, tramo_id, geometria_version, catalogo_revision,
                       revision_anterior, actualizacion_id, calculado_en, presiones, linepacks):
    """Guarda 72 presiones absolutas y 72 Sm³, firma y estado en un COMMIT.

    Mismo control de versiones/excepciones que guardar_actual. Valida todos los
    puntos antes de escribir; calcula firma internamente, nunca acepta serie parcial.
    El almacenamiento valida contrato numérico, no recalcula ni verifica fórmulas.
    """
    if any(not isinstance(v, (list, tuple)) or len(v) != CANTIDAD_PUNTOS_PREDICCION
           for v in (presiones, linepacks)):
        raise ValueError('Se requieren exactamente 72 presiones y 72 linepacks')
    ps = [_numero(v, 'presion', True) for v in presiones]
    ls = [_numero(v, 'linepack') for v in linepacks]
    values = dict(presiones_json=json.dumps(ps, allow_nan=False),
                  linepacks_json=json.dumps(ls, allow_nan=False),
                  firma_presiones_json=json.dumps(firma_presiones(ps)))
    return _guardar(conn, 'predictivo', tramo_id, geometria_version, catalogo_revision,
                    revision_anterior, actualizacion_id, calculado_en, values)


def _guardar(conn, ciclo, tramo, version, catalogo, anterior, identificador, fecha, values):
    tramo = _texto(tramo, 'tramo_id')
    identificador = _texto(identificador, 'actualizacion_id')
    version = _entero(version, 'geometria_version', 1)
    catalogo = _entero(catalogo, 'catalogo_revision', 1)
    anterior = _entero(anterior, 'revision_anterior')
    fecha = _fecha(fecha)
    table = RESULTADOS[ciclo]
    values.update(geometria_version=version, catalogo_revision=catalogo,
                  actualizacion_id=identificador, calculado_en=fecha)
    with transaccion(conn, escritura=True):
        _validar_esquema(conn)
        _contexto(conn, tramo, version, catalogo)
        old = _fila(conn, table, tramo)
        if old and old['actualizacion_id'] == identificador:
            if any(old[k] != v for k, v in values.items()):
                raise ConflictoActualizacion('ID de paquete reutilizado con otro contenido')
            return dict(revision=old['revision'], repetido=True)
        if (old['revision'] if old else 0) != anterior:
            raise ConflictoActualizacion('Otro paquete reemplazó el resultado leído')
        acquisition = _estado(conn, tramo, ciclo)
        if ((old and fecha <= old['calculado_en']) or
                (acquisition and fecha <= acquisition['ultimo_intento_en'])):
            raise ConflictoActualizacion('Paquete con fecha antigua o ambigua')
        revision = _revision(conn)
        values.update(tramo_id=tramo, revision=revision)
        fields = list(values)
        conn.execute('INSERT OR REPLACE INTO {} ({}) VALUES ({})'.format(
            table, ','.join(fields), ','.join('?' for _ in fields)), list(values.values()))
        _escribir_estado(conn, tramo, ciclo, fecha, 'valido', None, revision, revision)
    return dict(revision=revision, repetido=False)


def registrar_adquisicion(conn, *, tramo_id, ciclo, observado_en, estado,
                          detalle=None, resultado_revision=None):
    """Registra error_lectura/error_calculo o lectura válida sin nuevo cálculo.

    Válido exige revisión del resultado vigente, contexto actual y fecha posterior
    al cálculo. Errores conservan última lectura válida, sin reemplazar resultados.
    Fechas anteriores/conflictivas se rechazan. Repetición exacta no cambia revisión.
    Devuelve revisión/repetido; excepciones y conexión igual que guardar_actual.
    """
    tramo = _texto(tramo_id, 'tramo_id')
    fecha = _fecha(observado_en)
    if ciclo not in RESULTADOS or estado not in ('valido', 'error_lectura', 'error_calculo'):
        raise ValueError('Ciclo o estado inválido')
    if detalle is not None and not isinstance(detalle, str):
        raise ValueError('detalle debe ser texto o None')
    if estado == 'valido':
        _entero(resultado_revision, 'resultado_revision', 1)
    elif resultado_revision is not None:
        raise ValueError('Errores no deben confirmar una revisión de resultado')
    with transaccion(conn, escritura=True):
        _validar_esquema(conn)
        if not conn.execute('SELECT 1 FROM tramos WHERE id=? AND activo=1', (tramo,)).fetchone():
            raise ConflictoActualizacion('Tramo ausente o inactivo')
        if estado == 'valido':
            result = _fila(conn, RESULTADOS[ciclo], tramo)
            if not result or result['revision'] != resultado_revision or fecha < result['calculado_en']:
                raise ConflictoActualizacion('Resultado no vigente para esta adquisición')
            _contexto(conn, tramo, result['geometria_version'], result['catalogo_revision'])
        old = _estado(conn, tramo, ciclo)
        if old and fecha <= old['ultimo_intento_en']:
            if (fecha == old['ultimo_intento_en'] and estado == old['estado']
                    and detalle == old['detalle'] and resultado_revision == old['resultado_revision']):
                return dict(revision=old['revision'], repetido=True)
            raise ConflictoActualizacion('Adquisición antigua o distinta con misma fecha')
        revision = _revision(conn)
        _escribir_estado(conn, tramo, ciclo, fecha, estado, detalle, resultado_revision, revision)
    return dict(revision=revision, repetido=False)


def leer_snapshot(conn, desde_revision=0):
    """Devuelve {revision, tablas: {nombre: [dict, ...]}} en un snapshot consistente.

    Desde 0: último estado completo, incluidos inactivos. Otro cursor: filas con
    revisión mayor al cursor y hasta el límite devuelto; no es histórico de eventos.
    Cursor inválido/futuro: ValueError. Arrays permanecen JSON de texto. No calcula
    calidad ni vencimiento. Cierra la transacción, no la conexión, antes de retornar.
    Tras restauración/reinicio cargar siempre desde 0. Avanzar cursor solo al publicar.
    """
    desde_revision = _entero(desde_revision, 'desde_revision')
    with transaccion(conn):
        _validar_esquema(conn)
        limit = conn.execute("SELECT valor FROM metadatos WHERE clave='revision_global'").fetchone()[0]
        if desde_revision > limit:
            raise ValueError('Cursor posterior a la base: recargar snapshot completo')
        tables = {table: [dict(row) for row in conn.execute(
            'SELECT * FROM ' + table + ' WHERE revision>? AND revision<=? ORDER BY revision, 1',
            (desde_revision, limit))] for table in TABLAS}
    return dict(revision=limit, tablas=tables)
