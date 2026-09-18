"""Proyección pura de un snapshot completo a valores y disponibilidad.

No lee SQLite, no cambia el snapshot, no abre puertos y no genera StatusCodes UA.
El adaptador de red futuro tendrá que aplicar esos estados y manejar fallas globales.
"""

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple, Union

from almacenamiento import firma_presiones
from python_scheduler.constantes import CANTIDAD_PUNTOS_PREDICCION
from .nodos import DefinicionNodo, definir_nodos


@dataclass(frozen=True)
class PoliticaVigencia:
    """Vencimiento en segundos: actual desde cálculo, predictivo desde verificación.

    Defaults iniciales de diseño, no umbrales validados en producción. Booleanos,
    no finitos y valores no positivos producen ValueError. El límite es inclusivo.
    """

    actual_segundos: float = 120.0
    predictivo_segundos: float = 1800.0

    def __post_init__(self):
        for value in (self.actual_segundos, self.predictivo_segundos):
            try:
                valid = type(value) in (int, float) and math.isfinite(value) and value > 0
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError('Los umbrales deben ser segundos finitos positivos')


@dataclass(frozen=True)
class PublicacionNodo:
    """Valor preparado; disponibilidad interna, nunca confirmación de entrega UA.

    `valor` es float/tupla de 72 floats o None, nunca cero de relleno. En vencido
    o error de adquisición conserva el último valor íntegro con estado NO válido.
    Las fechas originales son datetime UTC; no se renuevan al preparar de nuevo.
    """

    nodo: DefinicionNodo
    valor: Optional[Union[float, Tuple[float, ...]]]
    disponibilidad: str
    motivo: str
    calculado_en: Optional[datetime]
    verificado_en: Optional[datetime]
    revision_resultado: Optional[int]


def _fecha(value):
    if not isinstance(value, str):
        raise ValueError('Fecha no textual')
    date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None or date.utcoffset() is None:
        raise ValueError('Fecha sin zona')
    return date.astimezone(timezone.utc)


def _entero(value):
    if type(value) is not int or value <= 0:
        raise ValueError('Revisión/versión inválida')
    return value


def _numero(value, positivo=False):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or value < 0 or (positivo and value == 0):
        raise ValueError('Número inválido')
    return float(value)


def _serie(raw, positivo=False):
    values = json.loads(raw)
    if not isinstance(values, list) or len(values) != CANTIDAD_PUNTOS_PREDICCION:
        raise ValueError('Serie incompleta')
    return tuple(_numero(v, positivo) for v in values)


def _indices(snapshot):
    if not isinstance(snapshot, dict) or type(snapshot.get('revision')) is not int or snapshot['revision'] < 0:
        raise ValueError('Snapshot inválido')
    tables = snapshot.get('tablas')
    if not isinstance(tables, dict):
        raise ValueError('Faltan tablas del snapshot completo')
    keys = {'tramos': ('id',), 'geometrias': ('tramo_id',),
            'resultados_actuales': ('tramo_id',), 'predicciones_linepack': ('tramo_id',),
            'estado_adquisicion': ('tramo_id', 'ciclo')}
    result = {}
    for table, fields in keys.items():
        rows = tables.get(table)
        if not isinstance(rows, list):
            raise ValueError('Falta tabla completa: ' + table)
        indexed = {}
        for row in rows:
            if not isinstance(row, dict) or any(
                    not isinstance(row.get(f), str) or not row[f].strip() for f in fields):
                raise ValueError('Clave inválida en ' + table)
            key = tuple(row[f] for f in fields)
            if key in indexed:
                raise ValueError('Clave duplicada en ' + table)
            indexed[key] = row
        result[table] = indexed
    return result


def _evaluar(tramo, geometria, resultado, estado, ciclo, ahora, politica, limite):
    # Valor por defecto: no existe ningún número publicable, tampoco cero.
    empty = (None, 'no_disponible', None, None, None)
    if not resultado:
        return (*empty, 'sin_resultado')
    try:
        if type(tramo['activo']) is not int or tramo['activo'] not in (0, 1):
            raise ValueError('Activación inválida')
        if not tramo['activo']:
            return (*empty, 'tramo_inactivo')
        if not geometria or geometria.get('activa') != 1:
            return (*empty, 'geometria_no_disponible')
        if type(geometria['activa']) is not int:
            raise ValueError('Activación geométrica inválida')
        revision = _entero(resultado['revision'])
        catrev = _entero(tramo['revision'])
        georev = _entero(geometria['revision'])
        version = _entero(geometria['version'])
        if max(revision, catrev, georev) > limite:
            raise ValueError('Revisión fuera del snapshot')
        if (_entero(resultado['catalogo_revision']) != catrev or
                _entero(resultado['geometria_version']) != version):
            return (*empty, 'contexto_modificado')
        calculado = _fecha(resultado['calculado_en'])
        if calculado > ahora:
            return (*empty, 'fecha_futura')
        if ciclo == 'actual':
            valores = (_numero(resultado['presion_promedio_bar_abs'], True),
                       _numero(resultado['linepack_sm3']))
        else:
            ps = _serie(resultado['presiones_json'], True)
            valores = _serie(resultado['linepacks_json'])
            firma = json.loads(resultado['firma_presiones_json'])
            if (not isinstance(firma, list) or any(type(v) is not int for v in firma)
                    or firma != firma_presiones(ps)):
                raise ValueError('Firma inválida')
        if not estado:
            return (*empty, 'sin_adquisicion')
        state_revision = _entero(estado['revision'])
        if state_revision < revision or state_revision > limite:
            raise ValueError('Estado no corresponde al snapshot')
        intento = _fecha(estado['ultimo_intento_en'])
        verificado = (_fecha(estado['ultima_lectura_valida_en'])
                      if estado.get('ultima_lectura_valida_en') else None)
        if intento > ahora or (verificado and verificado > ahora):
            return (*empty, 'fecha_futura')
        if intento < calculado or (verificado and verificado > intento):
            raise ValueError('Fechas inconsistentes')
        if estado['estado'] in ('error_lectura', 'error_calculo'):
            return valores, 'no_disponible', calculado, verificado, revision, estado['estado']
        if estado['estado'] != 'valido':
            raise ValueError('Estado desconocido')
        if (_entero(estado['resultado_revision']) != revision or not verificado
                or verificado != intento or verificado < calculado):
            return (*empty, 'adquisicion_no_corresponde')
        referencia = calculado if ciclo == 'actual' else verificado
        umbral = politica.actual_segundos if ciclo == 'actual' else politica.predictivo_segundos
        vencido = (ahora - referencia).total_seconds() >= umbral
        return (valores, 'vencido' if vencido else 'disponible', calculado,
                verificado, revision, 'vigencia_agotada' if vencido else 'ok')
    except (KeyError, ValueError, TypeError, OverflowError, RecursionError):
        return (*empty, 'datos_invalidos')


def preparar_publicacion(snapshot_completo, *, ahora: datetime,
                         politica: PoliticaVigencia = PoliticaVigencia()) -> Tuple[PublicacionNodo, ...]:
    """Proyecta snapshot COMPLETO (leer_snapshot desde 0), sin mutarlo ni hacer E/S.

    No pasar un delta: primero debe combinarlo un consumidor futuro con su caché.
    No hay marca en SQLite que permita distinguir un delta de un snapshot completo.
    Reevalúa vencimiento en cada llamada aunque revisión no cambie; reloj inyectado
    con zona, normalizado UTC. ValueError ante estructura/identidad global inválida.
    Datos inválidos de un ciclo se marcan localmente sin detener otros tramos.
    Incluye inactivos para que el futuro adaptador retire/invalide nodos existentes.
    """
    if not isinstance(ahora, datetime) or ahora.tzinfo is None or ahora.utcoffset() is None:
        raise ValueError('ahora debe ser datetime con zona horaria')
    if not isinstance(politica, PoliticaVigencia):
        raise ValueError('politica debe ser PoliticaVigencia')
    ahora = ahora.astimezone(timezone.utc)
    tables = _indices(snapshot_completo)
    output = []
    for key, tramo in sorted(tables['tramos'].items()):
        nodos = definir_nodos(key[0], tramo.get('base_tag'))
        for ciclo, table in (('actual', 'resultados_actuales'), ('predictivo', 'predicciones_linepack')):
            values, status, calc, verified, revision, reason = _evaluar(
                tramo, tables['geometrias'].get(key), tables[table].get(key),
                tables['estado_adquisicion'].get((key[0], ciclo)), ciclo,
                ahora, politica, snapshot_completo['revision'])
            for index, nodo in enumerate(nodos[:2] if ciclo == 'actual' else nodos[2:]):
                value = None
                if values is not None:
                    value = (round(values[index], nodo.decimales) if ciclo == 'actual' else
                             tuple(round(v, nodo.decimales) for v in values))
                output.append(PublicacionNodo(nodo, value, status, reason, calc, verified, revision))
    return tuple(output)
