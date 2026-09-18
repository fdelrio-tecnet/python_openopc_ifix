"""Modelo lógico de nodos; no asigna namespace ni NodeIds de un servidor real."""

from dataclasses import dataclass
from typing import Tuple
from urllib.parse import quote

from python_scheduler.constantes import CANTIDAD_PUNTOS_PREDICCION


@dataclass(frozen=True)
class DefinicionNodo:
    """Identidad lógica estable por ID, nombre de negocio y tipo/dimensión previstos.

    `clave` es candidato a identificador string UA, no un NodeId serializado.
    `nombre` conserva base_tag + sufijo, sin el prefijo FIX ni campos OPC DA.
    `dimensiones=()` indica escalar; `(72,)` una serie ordenada. Solo lectura.
    """

    clave: str
    tramo_id: str
    nombre: str
    ciclo: str
    tipo: str
    dimensiones: Tuple[int, ...]
    unidad: str
    decimales: int
    escribible: bool = False


def definir_nodos(tramo_id: str, base_tag: str) -> Tuple[DefinicionNodo, ...]:
    """Devuelve tres definiciones sin E/S; ValueError ante ID/base vacíos o no texto.

    La identidad usa ID (sensible a mayúsculas), no posición ni base-tag. Escapa
    separadores y porcentajes para evitar colisiones entre IDs. Cambiar base_tag
    cambia el nombre visible, no la clave. Mapeo IGS/AR todavía por verificar.
    """
    if any(not isinstance(v, str) or not v.strip() for v in (tramo_id, base_tag)):
        raise ValueError('ID y base_tag deben ser textos no vacíos')
    tramo_id, base_tag = tramo_id.strip(), base_tag.strip()
    prefix = 'tramos/' + quote(tramo_id, safe='') + '/'
    specs = (
        ('PPROMEDIO', 'actual', (), 'bar abs', 3),
        ('LINEPACK', 'actual', (), 'Sm3', 2),
        ('LINEPACK_PRED', 'predictivo', (CANTIDAD_PUNTOS_PREDICCION,), 'Sm3', 2),
    )
    return tuple(DefinicionNodo(prefix + suffix, tramo_id, base_tag + '_' + suffix,
                                ciclo, 'Double', dimensiones, unidad, decimales)
                 for suffix, ciclo, dimensiones, unidad, decimales in specs)
