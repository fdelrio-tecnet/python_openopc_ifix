from datetime import datetime
from numbers import Real
from typing import Any, Dict, Iterable, List, Optional
import math
import OpenOPC

if __package__:
    from .constantes import CANTIDAD_PUNTOS_PREDICCION
else:
    from constantes import CANTIDAD_PUNTOS_PREDICCION


# Campos que contienen tags de entrada.
CAMPOS_ENTRADA = (
    "presion_ingreso",
    "presion_egreso",
    "diametro",
    "espesor",
    "longitud",
)

# Precisión utilizada al escribir resultados actuales en iFIX.
DECIMALES_PPROMEDIO = 3
DECIMALES_LINEPACK = 2
DECIMALES_FIRMA_PREDICCION = 2


def conectar_opc(
    servidor: str = "Intellution.OPCiFIX.1",
    host: str = "localhost",
):
    """
    Crea un cliente OpenOPC y establece la conexión.

    Devuelve el cliente conectado.
    """

    opc = OpenOPC.client()

    try:
        opc.connect(servidor, host)
        return opc

    except Exception:
        try:
            opc.close()
        except Exception:
            pass

        raise


def cerrar_opc(opc) -> None:
    """
    Cierra una conexión OpenOPC.

    Si el cliente es None o ya está cerrado, no interrumpe
    la finalización del programa.
    """

    if opc is None:
        return

    try:
        opc.close()
    except Exception as error:
        print(
            f"Advertencia al cerrar la conexión OPC: {error!r}"
        )


def _reiniciar_estado_escritura(
    tramo: Dict[str, Any],
) -> None:
    """
    Reinicia el estado del último intento de escritura de un tramo.

    No modifica:
        - los valores leídos;
        - la presión promedio calculada;
        - el linepack calculado;
        - la sección predictiva.

    Parameters
    ----------
    tramo:
        Estructura correspondiente a un tramo.

    Raises
    ------
    ValueError:
        Si el tramo no contiene una sección válida en
        datos["escritura"].
    """

    datos = tramo.get("datos")

    if not isinstance(datos, dict):
        raise ValueError(
            "El tramo no contiene una estructura válida en 'datos'."
        )

    escritura = datos.get("escritura")

    if not isinstance(escritura, dict):
        raise ValueError(
            "El tramo no contiene una estructura válida en "
            "datos['escritura']."
        )

    escritura["exitosa"] = False
    escritura["ppromedio"] = None
    escritura["linepack"] = None
    escritura["error"] = None
    escritura["timestamp"] = None

def _reiniciar_estado_escritura_prediccion(
    tramo,
) -> None:
    """
    Reinicia el estado de la última escritura predictiva.
    """

    escritura = (
        tramo["datos"]
        ["prediccion"]
        ["escritura"]
    )

    escritura["exitosa"] = False
    escritura["puntos_exitosos"] = 0
    escritura["puntos_fallidos"] = 0
    escritura["error"] = None
    escritura["timestamp"] = None


def _es_resultado_escritura_exitoso(
    resultado: Any,
) -> bool:
    """
    Determina si una respuesta de escritura de OpenOPC representa
    una operación exitosa.

    Normalmente OpenOPC devuelve el texto:

        Success

    La comparación no distingue mayúsculas y minúsculas.

    Parameters
    ----------
    resultado:
        Resultado individual devuelto por OpenOPC.

    Returns
    -------
    bool:
        True si el resultado equivale a "Success".
    """

    if resultado is None:
        return False

    return str(resultado).strip().casefold() == "success"

def escribir_resultados_tramos(
    opc: Any,
    tramos: Dict[str, Dict[str, Any]],
    tamano_lote: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Escribe en iFIX la presión promedio y el linepack actual de
    todos los tramos válidos.

    La función:

    1. Recorre la estructura de tramos.
    2. Selecciona únicamente los tramos válidos.
    3. Verifica que presión promedio y linepack sean numéricos.
    4. Redondea los valores para la escritura.
    5. Construye una lista de tuplas compatible con OpenOPC.
    6. Ejecuta opc.write().
    7. Asocia cada respuesta con su tramo.
    8. Actualiza datos["escritura"].

    La presión promedio se escribe con tres decimales.
    El linepack se escribe con dos decimales.

    Parameters
    ----------
    opc:
        Cliente OpenOPC ya conectado al servidor de iFIX.

    tramos:
        Diccionario de tramos indexado por ID.

    tamano_lote:
        Cantidad máxima de escrituras por llamada a opc.write().

        Si es None, todas las escrituras se realizan en una única
        llamada.

        Por ejemplo, tamano_lote=100 divide las escrituras en lotes
        de hasta 100 elementos.

    Returns
    -------
    Dict[str, Dict[str, Any]]:
        El mismo diccionario recibido, con la sección
        datos["escritura"] actualizada.

    Raises
    ------
    ValueError:
        Si la estructura general de tramos es inválida.

    RuntimeError:
        Si opc.write() falla completamente o devuelve un formato
        inesperado.

    Notes
    -----
    Un tramo que no tenga datos válidos no se escribe. Su estado de
    escritura queda marcado como no exitoso con un mensaje explicativo.

    Un error individual informado por OpenOPC no detiene el análisis
    de las respuestas de los demás tags.
    """

    if not isinstance(tramos, dict):
        raise ValueError(
            "La estructura de tramos debe ser un diccionario."
        )

    if tamano_lote is not None and tamano_lote <= 0:
        raise ValueError(
            "tamano_lote debe ser mayor que cero o None."
        )

    if not tramos:
        return tramos

    escrituras: List[tuple] = []

    # Relaciona cada Item ID con el tramo y el resultado que representa.
    destino_por_tag: Dict[str, Dict[str, str]] = {}

    momento_intento = datetime.now()

    # --------------------------------------------------------
    # 1. Preparar las escrituras
    # --------------------------------------------------------

    for tramo_id, tramo in tramos.items():
        if not isinstance(tramo, dict):
            raise ValueError(
                f"El tramo '{tramo_id}' no tiene una "
                "estructura válida."
            )

        datos = tramo.get("datos")
        tags = tramo.get("tags")

        if not isinstance(datos, dict):
            raise ValueError(
                f"El tramo '{tramo_id}' no contiene una "
                "estructura válida en 'datos'."
            )

        if not isinstance(tags, dict):
            raise ValueError(
                f"El tramo '{tramo_id}' no contiene una "
                "estructura válida en 'tags'."
            )

        _reiniciar_estado_escritura(tramo)

        escritura = datos["escritura"]
        escritura["timestamp"] = momento_intento

        if not datos.get("valido", False):
            escritura["error"] = (
                "No se escribieron resultados porque el tramo "
                "no tiene una lectura y un cálculo válidos."
            )
            continue

        presion_promedio = datos.get("presion_promedio")
        linepack = datos.get("linepack")

        if not _es_valor_numerico(presion_promedio):
            escritura["error"] = (
                "La presión promedio calculada no es numérica: "
                f"{presion_promedio!r}."
            )
            continue

        if not _es_valor_numerico(linepack):
            escritura["error"] = (
                "El linepack calculado no es numérico: "
                f"{linepack!r}."
            )
            continue

        tag_ppromedio = tags.get("ppromedio")
        tag_linepack = tags.get("linepack")

        if (
            not isinstance(tag_ppromedio, str)
            or not tag_ppromedio.strip()
        ):
            escritura["error"] = (
                "El tag de presión promedio no es válido."
            )
            continue

        if (
            not isinstance(tag_linepack, str)
            or not tag_linepack.strip()
        ):
            escritura["error"] = (
                "El tag de linepack no es válido."
            )
            continue

        tag_ppromedio = tag_ppromedio.strip()
        tag_linepack = tag_linepack.strip()

        valor_ppromedio = round(
            float(presion_promedio),
            DECIMALES_PPROMEDIO,
        )

        valor_linepack = round(
            float(linepack),
            DECIMALES_LINEPACK,
        )

        escrituras.append(
            (
                tag_ppromedio,
                valor_ppromedio,
            )
        )

        escrituras.append(
            (
                tag_linepack,
                valor_linepack,
            )
        )

        destino_por_tag[
            _normalizar_nombre_tag(tag_ppromedio)
        ] = {
            "tramo_id": tramo_id,
            "campo": "ppromedio",
        }

        destino_por_tag[
            _normalizar_nombre_tag(tag_linepack)
        ] = {
            "tramo_id": tramo_id,
            "campo": "linepack",
        }

    # No hay nada para escribir.
    if not escrituras:
        return tramos

    # --------------------------------------------------------
    # 2. Dividir las escrituras en lotes
    # --------------------------------------------------------

    if tamano_lote is None:
        lotes = [escrituras]
    else:
        lotes = [
            escrituras[inicio:inicio + tamano_lote]
            for inicio in range(
                0,
                len(escrituras),
                tamano_lote,
            )
        ]

    respuestas_por_tag: Dict[str, Any] = {}

    # --------------------------------------------------------
    # 3. Ejecutar opc.write()
    # --------------------------------------------------------

    for lote in lotes:
        try:
            respuestas = opc.write(lote)

        except Exception as error:
            raise RuntimeError(
                "Falló completamente una operación de escritura "
                f"OpenOPC: {error}"
            ) from error

        if respuestas is None:
            raise RuntimeError(
                "OpenOPC no devolvió resultados para una "
                "operación de escritura."
            )

        # Una escritura múltiple debería devolver una colección.
        if not isinstance(respuestas, (list, tuple)):
            raise RuntimeError(
                "OpenOPC devolvió un formato de escritura "
                f"inesperado: {type(respuestas).__name__}."
            )

        for respuesta in respuestas:
            if (
                not isinstance(respuesta, (list, tuple))
                or len(respuesta) != 2
            ):
                raise RuntimeError(
                    "Formato inesperado en la respuesta de "
                    f"escritura OPC: {respuesta!r}"
                )

            nombre_tag, resultado = respuesta

            if not isinstance(nombre_tag, str):
                raise RuntimeError(
                    "OpenOPC devolvió un nombre de tag inválido "
                    f"durante la escritura: {nombre_tag!r}"
                )

            respuestas_por_tag[
                _normalizar_nombre_tag(nombre_tag)
            ] = resultado

    # --------------------------------------------------------
    # 4. Distribuir respuestas entre los tramos
    # --------------------------------------------------------

    for tag_normalizado, destino in destino_por_tag.items():
        tramo_id = destino["tramo_id"]
        campo = destino["campo"]

        escritura = tramos[tramo_id]["datos"]["escritura"]

        if tag_normalizado not in respuestas_por_tag:
            escritura[campo] = "Sin respuesta"
            continue

        escritura[campo] = respuestas_por_tag[tag_normalizado]

    # --------------------------------------------------------
    # 5. Evaluar el resultado general de cada tramo
    # --------------------------------------------------------

    for tramo_id, tramo in tramos.items():
        escritura = tramo["datos"]["escritura"]

        resultado_ppromedio = escritura["ppromedio"]
        resultado_linepack = escritura["linepack"]

        # Si ambos siguen en None, el tramo fue descartado durante
        # la preparación y ya tiene un mensaje de error.
        if (
            resultado_ppromedio is None
            and resultado_linepack is None
        ):
            continue

        errores = []

        if not _es_resultado_escritura_exitoso(
            resultado_ppromedio
        ):
            errores.append(
                "La escritura de presión promedio devolvió "
                f"{resultado_ppromedio!r}."
            )

        if not _es_resultado_escritura_exitoso(
            resultado_linepack
        ):
            errores.append(
                "La escritura de linepack devolvió "
                f"{resultado_linepack!r}."
            )

        if errores:
            escritura["exitosa"] = False
            escritura["error"] = " ".join(errores)
        else:
            escritura["exitosa"] = True
            escritura["error"] = None

        escritura["timestamp"] = momento_intento

    return tramos

def escribir_predicciones_tramos(
    opc,
    tramos,
    tamano_lote=None,
):
    """
    Escribe los puntos predictivos y confirma una respuesta Success única
    por cada tag enviado, dentro de su lote. Las anomalías de respuesta
    impiden consolidar la firma, pero no detienen los otros tramos.
    Una excepción de opc.write se propaga para permitir la reconexión.
    Esta confirmación no implica readback ni persistencia en iFIX.
    """

    if tamano_lote is not None and (
        isinstance(tamano_lote, bool)
        or not isinstance(tamano_lote, int)
        or tamano_lote <= 0
    ):
        raise ValueError("tamano_lote debe ser un entero positivo o None.")

    momento = datetime.now()
    cantidad = CANTIDAD_PUNTOS_PREDICCION

    for tramo in tramos.values():

        prediccion = tramo["datos"]["prediccion"]

        _reiniciar_estado_escritura_prediccion(
            tramo
        )

        prediccion["escritura"]["timestamp"] = (
            momento
        )

        if not prediccion["cambio_detectado"]:
            continue

        if not prediccion["calculada"]:
            prediccion["escritura"]["error"] = (
                "La predicción no fue calculada."
            )
            continue

        escritura = prediccion["escritura"]
        try:
            puntos = prediccion["puntos"]
            tags = tramo["tags"]["linepack_pred"]
            firma = prediccion["firma_pendiente"]
            if not isinstance(puntos, list) or len(puntos) != cantidad:
                raise ValueError(f"Se requieren exactamente {cantidad} puntos.")
            if not isinstance(tags, list) or len(tags) != cantidad:
                raise ValueError(f"Se requieren exactamente {cantidad} tags de salida.")
            if not isinstance(firma, tuple) or len(firma) != cantidad:
                raise ValueError(f"Se requiere una firma pendiente de {cantidad} puntos.")

            escrituras = []
            unicos = set()
            for indice, (punto, tag) in enumerate(zip(puntos, tags)):
                campo = f"F_{indice:02d}"
                if not isinstance(punto, dict) or not punto.get("valido"):
                    raise ValueError(f"Punto inválido: {indice}.")
                if punto.get("indice") != indice or punto.get("campo") != campo:
                    raise ValueError(f"Índice/campo inconsistente en el punto {indice}.")
                if not isinstance(tag, str) or not tag.strip():
                    raise ValueError(f"Tag inválido en el punto {indice}.")
                tag = tag.strip()
                esperado = f"FIX.{tramo['base_tag']}_LINEPACK_PRED.{campo}"
                clave = _normalizar_nombre_tag(tag)
                if clave != _normalizar_nombre_tag(esperado):
                    raise ValueError(f"Tag no corresponde al punto {indice}: '{tag}'.")
                if clave in unicos:
                    raise ValueError(f"Tag de salida duplicado: '{tag}'.")
                unicos.add(clave)
                valor = punto.get("linepack")
                if not _es_valor_numerico(valor) or not math.isfinite(float(valor)):
                    raise ValueError(f"Linepack inválido en el punto {indice}: {valor!r}.")
                escrituras.append((tag, round(float(valor), DECIMALES_LINEPACK)))
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            escritura["error"] = f"No se escribió la predicción: {error}"
            continue

        errores = []
        exitosos = 0
        for lote in _dividir_en_lotes(escrituras, tamano_lote):
            esperados = {_normalizar_nombre_tag(tag): tag for tag, _ in lote}
            recibidos = {clave: [] for clave in esperados}
            try:
                respuestas = opc.write(lote)
            except Exception as error:
                escritura["puntos_exitosos"] = exitosos
                escritura["puntos_fallidos"] = cantidad - exitosos
                escritura["error"] = f"Falla global de escritura OPC: {error}"
                raise

            # OpenOPC devuelve una lista incluso para un lote de un item.
            # Se admite también la respuesta escalar de escritura individual.
            if len(lote) == 1 and isinstance(respuestas, str):
                respuestas = [(lote[0][0], respuestas)]
            elif (len(lote) == 1 and isinstance(respuestas, (list, tuple))
                  and len(respuestas) == 2 and isinstance(respuestas[0], str)):
                respuestas = [respuestas]
            if not isinstance(respuestas, (list, tuple)):
                errores.append("Formato inválido de respuestas OPC.")
                respuestas = []
            for respuesta in respuestas:
                if (not isinstance(respuesta, (list, tuple)) or len(respuesta) != 2
                        or not isinstance(respuesta[0], str)):
                    errores.append(f"Respuesta OPC inválida: {respuesta!r}.")
                    continue
                tag, resultado = respuesta
                clave = _normalizar_nombre_tag(tag)
                if clave not in esperados:
                    errores.append(f"Respuesta de tag ajeno al lote: '{tag}'.")
                    continue
                recibidos[clave].append(resultado)

            for clave, resultados in recibidos.items():
                tag = esperados[clave]
                if not resultados:
                    errores.append(f"Sin respuesta: '{tag}'.")
                elif len(resultados) != 1:
                    errores.append(f"Respuesta duplicada: '{tag}'.")
                elif not _es_resultado_escritura_exitoso(resultados[0]):
                    errores.append(f"Error de escritura '{tag}': {resultados[0]!r}.")
                else:
                    exitosos += 1

        escritura["puntos_exitosos"] = exitosos
        # Incluye puntos faltantes, ambiguos o rechazados, no respuestas extra.
        escritura["puntos_fallidos"] = cantidad - exitosos
        if exitosos == cantidad and not errores:
            escritura["exitosa"] = True
            prediccion["ultima_firma"] = firma
            prediccion["firma_pendiente"] = None
            prediccion["cambio_detectado"] = False
        else:
            escritura["error"] = " ".join(errores)

    return tramos

def _calidad_es_buena(calidad: Any) -> bool:
    """
    Determina si una calidad OPC comienza con 'Good'.

    OpenOPC puede devolver valores como:
        Good
        Good: Non-specific
    """

    if calidad is None:
        return False

    return str(calidad).strip().lower().startswith("good")


def _es_valor_numerico(valor: Any) -> bool:
    """
    Determina si un valor es numérico, finito y representable como float.

    bool se excluye explícitamente porque en Python es una subclase
    de int, pero no debe tratarse como un valor analógico.
    """

    try:
        return isinstance(valor, Real) and not isinstance(valor, bool) and math.isfinite(float(valor))
    except (ValueError, OverflowError):
        return False

def _valor_firma_prediccion(
    valor: float,
) -> int:
    """
    Convierte un valor de presión promedio predicha en una
    representación entera truncada a dos decimales.

    Ejemplos:

        45.129 -> 4512
        45.121 -> 4512
        45.130 -> 4513
    """

    return math.trunc(
        float(valor)
        * (10 ** DECIMALES_FIRMA_PREDICCION)
    )

def _construir_firma_prediccion(
    valores,
) -> tuple:
    """
    Construye una firma inmutable utilizada para detectar cambios.
    """

    return tuple(
        _valor_firma_prediccion(valor)
        for valor in valores
    )

def _firmas_son_distintas(
    firma_anterior,
    firma_nueva,
) -> bool:
    """
    Compara dos firmas y finaliza al encontrar la primera
    diferencia.
    """

    if len(firma_anterior) != len(firma_nueva):
        return True

    for anterior, nuevo in zip(
        firma_anterior,
        firma_nueva,
    ):
        if anterior != nuevo:
            return True

    return False

def _normalizar_nombre_tag(tag: str) -> str:
    """
    Normaliza un Item ID para realizar comparaciones internas.

    Se utiliza casefold para tolerar diferencias entre mayúsculas
    y minúsculas en los nombres devueltos por OpenOPC.
    """

    return tag.strip().casefold()


def _obtener_tags_lectura(
    tramos: Dict[str, Dict[str, Any]],
) -> List[str]:
    """
    Obtiene todos los Item IDs de entrada sin duplicados.

    Si varios tramos utilizan una misma presión, el tag se incluirá
    una sola vez en la lectura OPC.
    """

    tags_unicos: Dict[str, str] = {}

    for tramo_id, tramo in tramos.items():
        tags = tramo.get("tags")

        if not isinstance(tags, dict):
            raise ValueError(
                f"El tramo '{tramo_id}' no contiene una "
                "estructura válida en 'tags'."
            )

        for campo in CAMPOS_ENTRADA:
            tag = tags.get(campo)

            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(
                    f"El tramo '{tramo_id}' no tiene un tag "
                    f"válido para '{campo}'."
                )

            tag = tag.strip()
            clave_normalizada = _normalizar_nombre_tag(tag)

            # Se conserva la primera escritura original del Item ID.
            tags_unicos.setdefault(clave_normalizada, tag)

    return sorted(
        tags_unicos.values(),
        key=str.casefold,
    )


def _dividir_en_lotes(
    elementos: List[str],
    tamano_lote: Optional[int],
) -> Iterable[List[str]]:
    """
    Divide una lista en lotes.

    Si tamano_lote es None, todos los tags se leen en una única
    operación OPC.
    """

    if tamano_lote is None:
        yield elementos
        return

    if tamano_lote <= 0:
        raise ValueError(
            "tamano_lote debe ser mayor que cero o None."
        )

    for inicio in range(0, len(elementos), tamano_lote):
        yield elementos[inicio:inicio + tamano_lote]


def _leer_tags_opc(
    opc: Any,
    tags: List[str],
    tamano_lote: Optional[int],
) -> Dict[str, Dict[str, Any]]:
    """
    Ejecuta las lecturas OpenOPC y crea un índice por Item ID.

    La estructura resultante es:

        nombre normalizado:
            nombre
            valor
            calidad
            timestamp
    """

    resultados_por_tag: Dict[str, Dict[str, Any]] = {}

    for lote in _dividir_en_lotes(tags, tamano_lote):
        if not lote:
            continue

        resultados = opc.read(lote)

        if resultados is None:
            raise RuntimeError(
                "OpenOPC no devolvió resultados para el lote."
            )

        if not isinstance(resultados, (list, tuple)):
            raise RuntimeError(
                "OpenOPC devolvió un formato inesperado: "
                f"{type(resultados).__name__}."
            )

        for resultado in resultados:
            if (
                not isinstance(resultado, (list, tuple))
                or len(resultado) != 4
            ):
                raise RuntimeError(
                    "Formato inesperado en la respuesta OPC: "
                    f"{resultado!r}"
                )

            nombre, valor, calidad, timestamp = resultado

            if not isinstance(nombre, str):
                raise RuntimeError(
                    "OpenOPC devolvió un nombre de tag inválido: "
                    f"{nombre!r}"
                )

            clave = _normalizar_nombre_tag(nombre)

            resultados_por_tag[clave] = {
                "nombre": nombre,
                "valor": valor,
                "calidad": calidad,
                "timestamp": timestamp,
            }

    return resultados_por_tag


def _reiniciar_datos_entrada(
    tramo: Dict[str, Any],
) -> None:
    """
    Limpia los valores del ciclo anterior.

    Esto evita utilizar accidentalmente un valor viejo si un tag no
    puede leerse durante el ciclo actual.

    No modifica la sección predictiva del tramo.
    """

    datos = tramo["datos"]

    for campo in CAMPOS_ENTRADA:
        datos[campo] = None

    # Los resultados anteriores también se invalidan. De esta forma,
    # no se escribirá un resultado calculado con entradas antiguas.
    datos["presion_promedio"] = None
    datos["linepack"] = None

    datos["valido"] = False
    datos["error"] = None
    datos["timestamp"] = None


def _obtener_resultado_tag(
    resultados_por_tag: Dict[str, Dict[str, Any]],
    tag: str,
) -> Optional[Dict[str, Any]]:
    """
    Busca el resultado OPC correspondiente a un Item ID.
    """

    return resultados_por_tag.get(
        _normalizar_nombre_tag(tag)
    )


def leer_datos_tramos(
    opc: Any,
    tramos: Dict[str, Dict[str, Any]],
    exigir_calidad_good: bool = True,
    tamano_lote: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Lee mediante OpenOPC los datos actuales necesarios para calcular
    la presión promedio y el linepack de cada tramo.

    Esta función no lee los campos predictivos. Las predicciones se
    procesarán mediante una función independiente, ya que tienen otra
    frecuencia de actualización y necesitan detección de cambios.

    La función realiza las siguientes operaciones:

    1. Extrae los tags de presión y datos constructivos.
    2. Elimina Item IDs duplicados.
    3. Ejecuta una lectura múltiple con OpenOPC.
    4. Indexa los resultados por nombre de tag.
    5. Distribuye los valores en tramo["datos"].
    6. Marca cada tramo como válido o inválido.

    Parameters
    ----------
    opc:
        Cliente OpenOPC ya conectado al servidor de iFIX.

    tramos:
        Diccionario creado por cargar_estructura_tramos().

    exigir_calidad_good:
        Por defecto True: un tag cuya calidad no comience con "Good"
        invalida el tramo.

        Si es False, se acepta el valor siempre que sea numérico,
        aunque la calidad OPC no sea Good.

    tamano_lote:
        Cantidad máxima de tags por llamada a opc.read().

        None:
            Lee todos los tags en una misma llamada.

        Ejemplo:
            100 divide la lectura en lotes de hasta 100 tags.

    Returns
    -------
    dict:
        El mismo diccionario recibido, con la sección "datos"
        actualizada para cada tramo.

    Raises
    ------
    ValueError:
        Si la estructura de tramos es inválida.

    RuntimeError:
        Si la operación opc.read() falla completamente o devuelve
        un formato inesperado.

    Notes
    -----
    Los errores particulares de un tag no interrumpen el procesamiento
    de los demás tramos. Únicamente se marca como inválido el tramo que
    depende del tag fallido.
    """

    if not isinstance(tramos, dict):
        raise ValueError(
            "La estructura de tramos debe ser un diccionario."
        )

    if not tramos:
        return tramos

    # --------------------------------------------------------
    # 1. Verificar y reiniciar el estado de los tramos
    # --------------------------------------------------------

    for tramo_id, tramo in tramos.items():
        if not isinstance(tramo, dict):
            raise ValueError(
                f"El tramo '{tramo_id}' no tiene una "
                "estructura válida."
            )

        datos = tramo.get("datos")

        if not isinstance(datos, dict):
            raise ValueError(
                f"El tramo '{tramo_id}' no contiene una "
                "estructura válida en 'datos'."
            )

        _reiniciar_datos_entrada(tramo)
        _reiniciar_estado_escritura(tramo)

    # --------------------------------------------------------
    # 2. Obtener todos los tags únicos
    # --------------------------------------------------------

    tags_lectura = _obtener_tags_lectura(tramos)

    if not tags_lectura:
        raise ValueError(
            "No se encontraron tags de entrada para leer."
        )

    # --------------------------------------------------------
    # 3. Ejecutar la lectura OPC
    # --------------------------------------------------------

    resultados_por_tag = _leer_tags_opc(
        opc=opc,
        tags=tags_lectura,
        tamano_lote=tamano_lote,
    )

    momento_ciclo = datetime.now()

    # --------------------------------------------------------
    # 4. Distribuir los resultados entre los tramos
    # --------------------------------------------------------

    for tramo_id, tramo in tramos.items():
        tags = tramo["tags"]
        datos = tramo["datos"]

        errores: List[str] = []
        timestamps: List[Any] = []

        for campo in CAMPOS_ENTRADA:
            tag = tags[campo]

            resultado = _obtener_resultado_tag(
                resultados_por_tag,
                tag,
            )

            if resultado is None:
                errores.append(
                    f"No se recibió el tag '{tag}'."
                )
                continue

            valor = resultado["valor"]
            calidad = resultado["calidad"]
            timestamp = resultado["timestamp"]

            if not _es_valor_numerico(valor):
                errores.append(
                    f"El tag '{tag}' devolvió un valor "
                    f"no numérico: {valor!r}."
                )
                continue

            if (
                exigir_calidad_good
                and not _calidad_es_buena(calidad)
            ):
                errores.append(
                    f"El tag '{tag}' tiene calidad "
                    f"'{calidad}'."
                )
                continue

            # Convertimos a float para que los cálculos posteriores
            # reciban un tipo numérico consistente.
            datos[campo] = float(valor)

            if timestamp is not None:
                timestamps.append(timestamp)

        # ----------------------------------------------------
        # 5. Registrar el estado general del tramo
        # ----------------------------------------------------

        if errores:
            datos["valido"] = False
            datos["error"] = " ".join(errores)
        else:
            datos["valido"] = True
            datos["error"] = None

        # Se guarda el momento local del ciclo. Los timestamps OPC
        # individuales fueron usados únicamente como referencia.
        datos["timestamp"] = momento_ciclo

    return tramos

def leer_predicciones_tramos(
    opc,
    tramos,
    exigir_calidad_good=True,
    tamano_lote=None,
):
    """
    Lee los 72 valores de PPROMEDIO_PRED de todos los tramos
    y determina si existen cambios respecto de la última
    predicción procesada.

    Exige Good por defecto; puede desactivarse con exigir_calidad_good=False.
    Invalida los resultados derivados antes de leer y conserva ultima_firma.
    Una lectura sin cambios deja calculada=False: no hay cálculo nuevo.
    """

    tags_unicos = {}
    tramos_validos = []
    # Invalidar resultados antes de OPC, incluso si la llamada global falla.
    for tramo in tramos.values():
        prediccion = tramo["datos"]["prediccion"]
        prediccion.update(cambio_detectado=False, firma_pendiente=None,
                          calculada=False, timestamp_calculo=None,
                          timestamp_lectura=None, error=None)
        _reiniciar_estado_escritura_prediccion(tramo)
        puntos = prediccion.get("puntos")
        if isinstance(puntos, list):
            for punto in puntos:
                if isinstance(punto, dict):
                    punto.update(presion_promedio=None, linepack=None,
                                 valido=False, error=None)
        tags = tramo.get("tags", {}).get("ppromedio_pred")
        if (not isinstance(puntos, list) or len(puntos) != CANTIDAD_PUNTOS_PREDICCION
                or not isinstance(tags, list) or len(tags) != CANTIDAD_PUNTOS_PREDICCION):
            prediccion["error"] = "Se requieren exactamente 72 puntos y tags predictivos."
            continue
        if any(not isinstance(p, dict) or p.get("indice") != i
               or p.get("campo") != f"F_{i:02d}" for i, p in enumerate(puntos)):
            prediccion["error"] = "Índice/campo predictivo inconsistente."
            continue
        if any(not isinstance(t, str) or not t.strip() for t in tags):
            prediccion["error"] = "Tag predictivo inválido."
            continue
        claves = [_normalizar_nombre_tag(t) for t in tags]
        if len(set(claves)) != CANTIDAD_PUNTOS_PREDICCION or any(
            not clave.endswith(f"_ppromedio_pred.f_{i:02d}")
            for i, clave in enumerate(claves)
        ):
            prediccion["error"] = "Tags predictivos duplicados o fuera de orden."
            continue
        tramos_validos.append(tramo)
        for clave, tag in zip(claves, tags):
            tags_unicos.setdefault(clave, tag.strip())
    tags_lectura = sorted(tags_unicos.values(), key=str.casefold)

    resultados_por_tag = _leer_tags_opc(
        opc=opc,
        tags=tags_lectura,
        tamano_lote=tamano_lote,
    )

    momento_ciclo = datetime.now()

    for tramo in tramos_validos:

        prediccion = tramo["datos"]["prediccion"]
        puntos = prediccion["puntos"]

        prediccion["cambio_detectado"] = False
        prediccion["firma_pendiente"] = None
        prediccion["timestamp_lectura"] = momento_ciclo
        prediccion["error"] = None

        valores_firma = []

        lectura_valida = True

        for indice, punto in enumerate(puntos):

            punto["presion_promedio"] = None
            punto["valido"] = False
            punto["error"] = None

            tag = tramo["tags"]["ppromedio_pred"][indice]

            resultado = _obtener_resultado_tag(
                resultados_por_tag,
                tag,
            )

            if resultado is None:
                lectura_valida = False

                punto["error"] = (
                    f"No se recibió el tag '{tag}'."
                )

                continue

            valor = resultado["valor"]
            calidad = resultado["calidad"]

            if not _es_valor_numerico(valor):
                lectura_valida = False

                punto["error"] = (
                    f"Valor inválido: {valor!r}"
                )

                continue

            if (
                exigir_calidad_good
                and not _calidad_es_buena(calidad)
            ):
                lectura_valida = False

                punto["error"] = (
                    f"Calidad inválida: {calidad}"
                )

                continue

            valor = float(valor)

            punto["presion_promedio"] = valor
            punto["valido"] = True

            valores_firma.append(valor)

        if not lectura_valida:
            prediccion["error"] = (
                "La lectura predictiva contiene valores inválidos."
            )
            continue

        try:
            firma_nueva = _construir_firma_prediccion(valores_firma)
        except (ValueError, OverflowError) as error:
            prediccion["error"] = f"No se pudo construir la firma: {error}"
            continue

        prediccion["firma_pendiente"] = firma_nueva

        ultima_firma = prediccion["ultima_firma"]

        if ultima_firma is None:

            prediccion["cambio_detectado"] = True

        else:

            prediccion["cambio_detectado"] = (
                _firmas_son_distintas(
                    ultima_firma,
                    firma_nueva,
                )
            )

    return tramos
