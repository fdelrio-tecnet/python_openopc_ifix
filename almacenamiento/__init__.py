"""Infraestructura SQLite local, sin dependencias OPC ni acceso al importar."""

from .conexion import (
    ErrorEsquema,
    abrir_base,
    inicializar_base,
    transaccion,
)
from .importacion import (
    importar_catalogo, importar_geometrias, validar_catalogo, validar_geometrias,
)
from .migraciones import migrar_base, migrar_base_v1
from .repositorio import (
    ConflictoActualizacion, firma_presiones, guardar_actual, guardar_prediccion,
    leer_snapshot, registrar_adquisicion,
)

__all__ = ["ErrorEsquema", "abrir_base", "inicializar_base", "transaccion"]
__all__ += ["importar_catalogo", "importar_geometrias", "validar_catalogo",
            "validar_geometrias", "migrar_base_v1"]
__all__ += ["migrar_base", "ConflictoActualizacion", "firma_presiones", "guardar_actual",
            "guardar_prediccion", "leer_snapshot", "registrar_adquisicion"]
