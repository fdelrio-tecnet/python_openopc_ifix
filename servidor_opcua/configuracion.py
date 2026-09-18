"""Configuración portable de ensayo; ninguna ruta de esta computadora es un default."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .publicacion import PoliticaVigencia


@dataclass(frozen=True)
class ConfiguracionUA:
    """Base existente, puerto loopback y namespace estable; no habilita red externa.

    El perfil inicial es anónimo/NoSecurity SOLO para ensayo local. No es una
    configuración de seguridad aprobada para producción.
    """

    base_sqlite: Path
    puerto: int = 48410
    namespace_uri: str = 'urn:linepack:local'
    sondeo_segundos: float = 2.0
    vigencia_actual_segundos: float = 120.0
    vigencia_predictiva_segundos: float = 1800.0

    def __post_init__(self):
        if not isinstance(self.base_sqlite, Path) or not self.base_sqlite.is_absolute():
            raise ValueError('base_sqlite debe resolverse a ruta absoluta local')
        if str(self.base_sqlite).startswith(('\\\\', '//')):
            raise ValueError('No se permiten bases en rutas UNC')
        if type(self.puerto) is not int or not 1 <= self.puerto <= 65535:
            raise ValueError('puerto debe ser entero entre 1 y 65535')
        if not isinstance(self.namespace_uri, str) or not self.namespace_uri.startswith('urn:') or any(
                c.isspace() for c in self.namespace_uri) or len(self.namespace_uri) <= 4:
            raise ValueError('namespace_uri debe ser URN no vacía y sin espacios')
        if (type(self.sondeo_segundos) not in (int, float) or
                not math.isfinite(self.sondeo_segundos) or not 0.1 <= self.sondeo_segundos <= 60):
            raise ValueError('sondeo_segundos debe estar entre 0.1 y 60')
        PoliticaVigencia(self.vigencia_actual_segundos, self.vigencia_predictiva_segundos)

    @property
    def endpoint(self):
        """Endpoint restringido a IPv4 loopback, independiente del hostname del equipo."""
        return 'opc.tcp://127.0.0.1:{}/linepack/'.format(self.puerto)

    @property
    def politica(self):
        """Política de vigencia usada por el preparador puro."""
        return PoliticaVigencia(self.vigencia_actual_segundos, self.vigencia_predictiva_segundos)


def cargar_configuracion(ruta):
    """Carga JSON estricto; base relativa se resuelve respecto del archivo, no cwd.

    Rechaza claves duplicadas/desconocidas y valores inválidos con ValueError.
    No crea ni abre la base; errores de lectura de archivo se propagan.
    """
    def objeto(pares):
        result = {}
        for key, value in pares:
            if key in result:
                raise ValueError('Clave duplicada: ' + key)
            result[key] = value
        return result

    path = Path(ruta).resolve()
    with path.open(encoding='utf-8-sig') as source:
        data = json.load(source, object_pairs_hook=objeto)
    if not isinstance(data, dict) or 'base_sqlite' not in data:
        raise ValueError('Falta base_sqlite')
    if set(data) - set(ConfiguracionUA.__dataclass_fields__):
        raise ValueError('Opciones desconocidas en configuración UA')
    base = data['base_sqlite']
    if not isinstance(base, str) or not base.strip():
        raise ValueError('base_sqlite debe ser texto no vacío')
    data['base_sqlite'] = (path.parent / base).resolve()
    return ConfiguracionUA(**data)
