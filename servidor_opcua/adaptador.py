"""Adaptador asyncua de ensayo local. Importar solo en el entorno UA separado."""

from datetime import datetime, timezone
from urllib.parse import quote

from asyncua import Server, ua
from asyncua.crypto.permission_rules import User, UserRole


class _UsuarioLectura:
    def get_user(self, iserver, username=None, password=None, certificate=None):
        # Ningún cliente externo se convierte en administrador, ni siquiera 'admin'.
        return User(role=UserRole.User) if username is None else None


def convertir_datavalue(publicacion):
    """Traduce disponibilidad interna a DataValue. Bad expone Null, nunca cero.

    Good conserva tipo Double/array y timestamps de cálculo. Vencido con último
    valor: UncertainLastUsableValue. SQLite sigue conservando valores íntegros.
    """
    if publicacion.disponibilidad == 'disponible':
        code = ua.StatusCodes.Good
    elif publicacion.disponibilidad == 'vencido':
        code = ua.StatusCodes.UncertainLastUsableValue
    elif publicacion.motivo in ('sin_resultado', 'sin_adquisicion'):
        code = ua.StatusCodes.BadWaitingForInitialData
    elif publicacion.motivo == 'error_lectura':
        code = ua.StatusCodes.BadNoCommunication
    else:
        code = ua.StatusCodes.BadOutOfService
    status = ua.StatusCode(code)
    if status.is_bad() or publicacion.valor is None:
        value = ua.Variant(None, ua.VariantType.Null)
    else:
        raw = list(publicacion.valor) if publicacion.nodo.dimensiones else publicacion.valor
        value = ua.Variant(raw, ua.VariantType.Double)
    return ua.DataValue(Value=value, StatusCode=status,
                        SourceTimestamp=publicacion.calculado_en,
                        ServerTimestamp=datetime.now(timezone.utc))


class AdaptadorUA:
    """Servidor con catálogo fijo durante cada ejecución; variables solo lectura.

    Crear/iniciar/publicar/cerrar desde un único event loop. Inicio requiere las
    publicaciones completas. Un cambio de nombres/nodos requiere reiniciar; no
    hay altas en caliente en 3b. No almacena historia ni escribe en SQLite.
    """

    def __init__(self, configuracion):
        self.configuracion = configuracion
        self.server = Server(user_manager=_UsuarioLectura())
        self.nodos = {}
        self.definiciones = {}
        self.namespace_index = None

    async def iniciar(self, publicaciones):
        """Inicializa nodos con calidad antes de escuchar; falla sin elegir otro puerto."""
        await self.server.init()
        self.server.set_endpoint(self.configuracion.endpoint)
        self.server.set_server_name('Linepack — ensayo local')
        self.server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        self.server.set_identity_tokens([ua.AnonymousIdentityToken])
        self.namespace_index = await self.server.register_namespace(self.configuracion.namespace_uri)
        idx = self.namespace_index
        root = await self.server.nodes.objects.add_folder(ua.NodeId('Linepack', idx), 'Linepack')
        folders = {}
        for item in publicaciones:
            spec = item.nodo
            if spec.clave in self.nodos:
                raise ValueError('Identificador de nodo duplicado')
            if spec.tramo_id not in folders:
                folders[spec.tramo_id] = await root.add_folder(
                    ua.NodeId('tramos/' + quote(spec.tramo_id, safe=''), idx),
                    ua.QualifiedName(spec.tramo_id, idx))
            node = await folders[spec.tramo_id].add_variable(
                ua.NodeId(spec.clave, idx), ua.QualifiedName(spec.nombre, idx),
                ua.Variant(None, ua.VariantType.Null), datatype=ua.NodeId(ua.ObjectIds.Double))
            await node.write_value_rank(1 if spec.dimensiones else ua.ValueRank.Scalar)
            await node.write_array_dimensions(list(spec.dimensiones))
            await node.set_read_only()
            self.nodos[spec.clave] = node
            self.definiciones[spec.clave] = spec
        await self.publicar(publicaciones)
        await self.server.start()

    async def publicar(self, publicaciones):
        """Publica conjunto completo; una falla se propaga. No hay atomicidad entre nodos UA."""
        specs = {item.nodo.clave: item.nodo for item in publicaciones}
        if len(specs) != len(publicaciones) or specs != self.definiciones:
            raise ValueError('Cambió el catálogo UA: reiniciar tras revisar configuración')
        for item in publicaciones:
            await self.nodos[item.nodo.clave].write_value(convertir_datavalue(item))

    async def invalidar_fuente(self):
        """Marca todo BadNoCommunication/Null ante falla de fuente; errores se propagan."""
        for node in self.nodos.values():
            await node.write_value(ua.DataValue(Value=ua.Variant(None, ua.VariantType.Null),
                                               StatusCode=ua.StatusCode(ua.StatusCodes.BadNoCommunication)))

    async def cerrar(self):
        """Cierra listeners, sesiones y tareas internas; también tras inicio parcial."""
        await self.server.stop()
