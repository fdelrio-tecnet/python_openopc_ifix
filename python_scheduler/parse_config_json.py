import json
from pathlib import Path
from typing import Any, Dict, Union, List

# ============================================================
# CONFIGURACIÓN DE PREDICCIONES
# ============================================================

if __package__:
    from .constantes import CANTIDAD_PUNTOS_PREDICCION
else:
    from constantes import CANTIDAD_PUNTOS_PREDICCION

SUFIJO_PPROMEDIO_PRED = "PPROMEDIO_PRED"
SUFIJO_LINEPACK_PRED = "LINEPACK_PRED"

PREFIJO_OPC = "FIX."
CAMPO_NUMERICO = "F_CV"



def cargar_estructura_tramos(
    ruta_json: Union[str, Path],
) -> Dict[str, Dict[str, Any]]:
    """
    Carga el archivo JSON de configuración y construye una estructura
    plana de tramos, indexada por el ID único de cada tramo.

    Incluye tanto sistema['tramos'] como subsistema['tramos'], sin
    modificar el JSON compartido. Los IDs y las salidas OPC deben ser
    únicos en toda la configuración; las entradas pueden compartirse.

    Por cada tramo se generan:

    Datos actuales:
        - tag de presión de ingreso;
        - tag de presión de egreso;
        - tag de diámetro;
        - tag de espesor;
        - tag de longitud;
        - tag de presión promedio;
        - tag de linepack.

    Datos predictivos:
        - 72 tags de presión promedio predicha;
        - 72 tags de linepack predicho;
        - 72 posiciones para almacenar valores y estados.

    Los tags quedan preparados como Item IDs completos para OpenOPC.

    La estructura devuelta tiene esta forma general:

        {
            "037-001-A": {
                "id": "037-001-A",
                "base_tag": "SYS_037_001_A",

                "tags": {
                    "presion_ingreso": "...",
                    "presion_egreso": "...",
                    "diametro": "...",
                    "espesor": "...",
                    "longitud": "...",
                    "ppromedio": "...",
                    "linepack": "...",

                    "ppromedio_pred": [
                        "...F_00",
                        "...F_01",
                        "...F_71"
                    ],

                    "linepack_pred": [
                        "...F_00",
                        "...F_01",
                        "...F_71"
                    ]
                },

                "datos": {
                    "presion_ingreso": None,
                    "presion_egreso": None,
                    "diametro": None,
                    "espesor": None,
                    "longitud": None,
                    "presion_promedio": None,
                    "linepack": None,
                    "valido": False,
                    "error": None,
                    "timestamp": None,
                    },

                    "escritura": {
                    "exitosa": False,
                    "ppromedio": None,
                    "linepack": None,
                    "error": None,
                    "timestamp": None
                    },

                    "prediccion": {
                        "puntos": [...],
                        "ultima_firma": None,
                        "firma_pendiente": None,
                        "cambio_detectado": False,
                        "calculada": False,
                        "timestamp_lectura": None,
                        "timestamp_calculo": None,
                        "error": None
                    }
                }
            }
        }

    Parameters
    ----------
    ruta_json:
        Ruta al archivo JSON. Puede recibirse como string o Path.

    Returns
    -------
    Dict[str, Dict[str, Any]]:
        Diccionario de tramos indexado por ID.

    Raises
    ------
    FileNotFoundError:
        Si el archivo no existe.

    ValueError:
        Si el JSON es inválido, falta una estructura obligatoria,
        un tramo está incompleto o existe un ID repetido.
    """

    ruta = Path(ruta_json)

    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encontró el archivo JSON: {ruta.resolve()}"
        )

    if not ruta.is_file():
        raise ValueError(
            f"La ruta no corresponde a un archivo: {ruta.resolve()}"
        )

    try:
        with ruta.open("r", encoding="utf-8") as archivo:
            configuracion = json.load(archivo)

    except json.JSONDecodeError as error:
        raise ValueError(
            f"El archivo contiene JSON inválido. "
            f"Línea {error.lineno}, columna {error.colno}: "
            f"{error.msg}"
        ) from error

    if not isinstance(configuracion, dict):
        raise ValueError(
            "El elemento principal del JSON debe ser un objeto."
        )

    sistemas = configuracion.get("sistemas")

    if sistemas is None:
        raise ValueError(
            "El JSON no contiene la clave obligatoria 'sistemas'."
        )

    if not isinstance(sistemas, dict):
        raise ValueError(
            "La clave 'sistemas' debe contener un objeto JSON."
        )

    tramos_por_id: Dict[str, Dict[str, Any]] = {}
    destinos_por_tag: Dict[str, str] = {}

    for nombre_sistema, sistema in sistemas.items():
        if not isinstance(sistema, dict):
            raise ValueError(
                f"El sistema '{nombre_sistema}' debe ser un objeto."
            )

        grupos_tramos = []
        if "tramos" in sistema:
            tramos_directos = sistema["tramos"]
            if not isinstance(tramos_directos, list):
                raise ValueError(
                    f"La clave 'tramos' del sistema '{nombre_sistema}' "
                    "debe contener una lista."
                )
            grupos_tramos.append((f"sistema '{nombre_sistema}'", tramos_directos))

        subsistemas = sistema.get("subsistemas", [])

        if "subsistemas" not in sistema and "tramos" not in sistema:
            raise ValueError(
                f"El sistema '{nombre_sistema}' no contiene "
                "la clave 'subsistemas' ni 'tramos'."
            )

        if not isinstance(subsistemas, list):
            raise ValueError(
                f"Los subsistemas de '{nombre_sistema}' "
                "deben estar contenidos en una lista."
            )

        for indice_subsistema, subsistema in enumerate(subsistemas):
            if not isinstance(subsistema, dict):
                raise ValueError(
                    f"El subsistema ubicado en la posición "
                    f"{indice_subsistema} del sistema "
                    f"'{nombre_sistema}' debe ser un objeto."
                )

            subsistema_id = subsistema.get("id", "<sin ID>")
            tramos = subsistema.get("tramos")

            if tramos is None:
                raise ValueError(
                    f"El subsistema '{subsistema_id}' del sistema "
                    f"'{nombre_sistema}' no contiene la clave 'tramos'."
                )

            if not isinstance(tramos, list):
                raise ValueError(
                    f"La clave 'tramos' del subsistema "
                    f"'{subsistema_id}' debe contener una lista."
                )

            grupos_tramos.append((
                f"sistema '{nombre_sistema}', subsistema '{subsistema_id}'",
                tramos,
            ))

        for contexto_grupo, tramos in grupos_tramos:
            for indice_tramo, tramo_json in enumerate(tramos):
                contexto = (
                    f"{contexto_grupo}, "
                    f"posición de tramo {indice_tramo}"
                )

                if not isinstance(tramo_json, dict):
                    raise ValueError(
                        f"El tramo ubicado en {contexto} "
                        "debe ser un objeto."
                    )

                campos_obligatorios = (
                    "id",
                    "base-tag",
                    "presion-ingreso",
                    "presion-egreso",
                )

                for campo in campos_obligatorios:
                    if campo not in tramo_json:
                        raise ValueError(
                            f"Falta el campo obligatorio '{campo}' "
                            f"en {contexto}."
                        )

                    valor = tramo_json[campo]

                    if not isinstance(valor, str):
                        raise ValueError(
                            f"El campo '{campo}' en {contexto} "
                            "debe ser una cadena de texto."
                        )

                    if not valor.strip():
                        raise ValueError(
                            f"El campo '{campo}' en {contexto} "
                            "no puede estar vacío."
                        )

                tramo_id = tramo_json["id"].strip()
                base_tag = tramo_json["base-tag"].strip()

                if tramo_id in tramos_por_id:
                    base_anterior = tramos_por_id[tramo_id]["base_tag"]

                    raise ValueError(
                        f"Se encontró el ID de tramo duplicado "
                        f"'{tramo_id}'. Ya estaba asociado al "
                        f"base tag '{base_anterior}' y volvió a "
                        f"aparecer con '{base_tag}'."
                    )

                presion_ingreso = normalizar_item_id_opc(
                    tramo_json["presion-ingreso"]
                )

                presion_egreso = normalizar_item_id_opc(
                    tramo_json["presion-egreso"]
                )

                tramos_por_id[tramo_id] = {
                    "id": tramo_id,
                    "base_tag": base_tag,

                    "tags": {
                        # ----------------------------------------------------
                        # Entradas actuales
                        # ----------------------------------------------------

                        "presion_ingreso": presion_ingreso,
                        "presion_egreso": presion_egreso,

                        "diametro": construir_tag_desde_base(
                            base_tag,
                            "DIAMETRO",
                        ),

                        "espesor": construir_tag_desde_base(
                            base_tag,
                            "ESPESOR",
                        ),

                        "longitud": construir_tag_desde_base(
                            base_tag,
                            "LONGITUD",
                        ),

                        # ----------------------------------------------------
                        # Salidas actuales
                        # ----------------------------------------------------

                        "ppromedio": construir_tag_desde_base(
                            base_tag,
                            "PPROMEDIO",
                        ),

                        "linepack": construir_tag_desde_base(
                            base_tag,
                            "LINEPACK",
                        ),

                        # ----------------------------------------------------
                        # Entradas predictivas
                        # ----------------------------------------------------

                        "ppromedio_pred": construir_tags_prediccion(
                            base_tag=base_tag,
                            sufijo=SUFIJO_PPROMEDIO_PRED,
                        ),

                        # ----------------------------------------------------
                        # Salidas predictivas
                        # ----------------------------------------------------

                        "linepack_pred": construir_tags_prediccion(
                            base_tag=base_tag,
                            sufijo=SUFIJO_LINEPACK_PRED,
                        ),
                    },

                    "datos": {
                            # --------------------------------------------------------
                            # Entradas y resultados actuales
                            # --------------------------------------------------------

                            "presion_ingreso": None,
                            "presion_egreso": None,
                            "diametro": None,
                            "espesor": None,
                            "longitud": None,
                            "presion_promedio": None,
                            "linepack": None,

                            # --------------------------------------------------------
                            # Estado de lectura y cálculo actual
                            # --------------------------------------------------------

                            "valido": False,
                            "error": None,
                            "timestamp": None,

                            # --------------------------------------------------------
                            # Estado de escritura actual
                            # --------------------------------------------------------

                            "escritura": {
                                "exitosa": False,
                                "ppromedio": None,
                                "linepack": None,
                                "error": None,
                                "timestamp": None,
                            },

                            # --------------------------------------------------------
                            # Datos predictivos
                            # --------------------------------------------------------

                            "prediccion": crear_estructura_prediccion(),
                        },
                }

                tags = tramos_por_id[tramo_id]["tags"]
                salidas = [tags["ppromedio"], tags["linepack"]] + tags["linepack_pred"]
                for tag in salidas:
                    clave = tag.strip().casefold()
                    if clave in destinos_por_tag:
                        raise ValueError(
                            f"Tag de salida duplicado '{tag}' en el tramo "
                            f"'{tramo_id}' ({contexto}); ya pertenece al tramo "
                            f"'{destinos_por_tag[clave]}'. Revise los base-tags."
                        )
                    destinos_por_tag[clave] = tramo_id

    return tramos_por_id


def normalizar_item_id_opc(tag: str) -> str:
    """
    Convierte un nombre de tag en un Item ID completo de iFIX.

    Ejemplo:

        MPL_TAG_PE.F_CV

    Resultado:

        FIX.MPL_TAG_PE.F_CV

    Si el tag ya comienza con FIX., no vuelve a agregar el prefijo.
    """

    tag = tag.strip()

    if tag.upper().startswith(PREFIJO_OPC):
        return tag

    return f"{PREFIJO_OPC}{tag}"


def construir_tag_desde_base(
    base_tag: str,
    sufijo: str,
) -> str:
    """
    Construye un Item ID OPC completo a partir del base tag.

    Ejemplo:

        base_tag = SYS_037_001_A
        sufijo   = DIAMETRO

    Resultado:

        FIX.SYS_037_001_A_DIAMETRO.F_CV
    """

    base_tag = base_tag.strip()
    sufijo = sufijo.strip().upper()

    return (
        f"{PREFIJO_OPC}"
        f"{base_tag}_{sufijo}."
        f"{CAMPO_NUMERICO}"
    )

def construir_campo_prediccion(indice: int) -> str:
    """
    Construye el nombre de un campo predictivo de iFIX.

    Los índices se expresan con dos dígitos:

        0  -> F_00
        1  -> F_01
        9  -> F_09
        10 -> F_10
        71 -> F_71

    Parameters
    ----------
    indice:
        Posición de la predicción. Debe estar comprendida entre
        cero y CANTIDAD_PUNTOS_PREDICCION - 1.

    Returns
    -------
    str:
        Nombre del campo iFIX correspondiente al índice.

    Raises
    ------
    TypeError:
        Si indice no es un entero.

    ValueError:
        Si indice está fuera del rango permitido.
    """

    if not isinstance(indice, int) or isinstance(indice, bool):
        raise TypeError(
            "El índice de predicción debe ser un número entero."
        )

    if not 0 <= indice < CANTIDAD_PUNTOS_PREDICCION:
        raise ValueError(
            "El índice de predicción debe estar comprendido entre "
            f"0 y {CANTIDAD_PUNTOS_PREDICCION - 1}. "
            f"Valor recibido: {indice}."
        )

    return f"F_{indice:02d}"

def construir_tags_prediccion(
    base_tag: str,
    sufijo: str,
) -> List[str]:
    """
    Construye todos los Item IDs OPC correspondientes a una serie
    predictiva de iFIX.

    Por ejemplo, para:

        base_tag = "SYS_037_001_A"
        sufijo = "PPROMEDIO_PRED"

    genera:

        FIX.SYS_037_001_A_PPROMEDIO_PRED.F_00
        FIX.SYS_037_001_A_PPROMEDIO_PRED.F_01
        ...
        FIX.SYS_037_001_A_PPROMEDIO_PRED.F_71

    Parameters
    ----------
    base_tag:
        Tag base del tramo, sin el prefijo FIX y sin el campo.

    sufijo:
        Sufijo del tag predictivo. Por ejemplo:
        PPROMEDIO_PRED o LINEPACK_PRED.

    Returns
    -------
    ListLista ordenada con los Item IDs OPC de los 72 puntos.

    Raises
    ------
    TypeError:
        Si base_tag o sufijo no son cadenas de texto.

    ValueError:
        Si base_tag o sufijo están vacíos.
    """

    if not isinstance(base_tag, str):
        raise TypeError(
            "base_tag debe ser una cadena de texto."
        )

    if not isinstance(sufijo, str):
        raise TypeError(
            "sufijo debe ser una cadena de texto."
        )

    base_tag = base_tag.strip()
    sufijo = sufijo.strip().upper()

    if not base_tag:
        raise ValueError(
            "base_tag no puede estar vacío."
        )

    if not sufijo:
        raise ValueError(
            "sufijo no puede estar vacío."
        )

    tags = []

    for indice in range(CANTIDAD_PUNTOS_PREDICCION):
        campo = construir_campo_prediccion(indice)

        item_id = (
            f"{PREFIJO_OPC}"
            f"{base_tag}_{sufijo}."
            f"{campo}"
        )

        tags.append(item_id)

    return tags

def crear_estructura_prediccion() -> Dict[str, Any]:
    """
    Crea la estructura dinámica utilizada para almacenar las
    predicciones de un tramo.

    Se crean 72 puntos. Cada punto almacenará:

        - índice numérico;
        - nombre del campo iFIX;
        - presión promedio predicha;
        - linepack predicho;
        - estado de validez;
        - mensaje de error.

    La estructura también mantiene información general necesaria
    para detectar cambios y controlar el procesamiento.

    Returns
    -------
    Dict[str, Any]:
        Estructura predictiva inicial con todos los valores vacíos.

    Notes
    -----
    ultima_firma representa la última predicción calculada y escrita
    correctamente.

    firma_pendiente representa la firma de la última lectura que
    todavía debe calcularse o escribirse.

    La firma no se almacenará hasta que el procesamiento predictivo
    haya terminado correctamente.
    """

    puntos = []

    for indice in range(CANTIDAD_PUNTOS_PREDICCION):
        puntos.append(
            {
                "indice": indice,
                "campo": construir_campo_prediccion(indice),
                "presion_promedio": None,
                "linepack": None,
                "valido": False,
                "error": None,
            }
        )

    return {
        "puntos": puntos,

        # Firma de la última predicción procesada correctamente.
        "ultima_firma": None,

        # Firma de una lectura nueva pendiente de procesar.
        "firma_pendiente": None,

        # Indica si la lectura actual difiere de ultima_firma.
        "cambio_detectado": False,

        # Indica si los linepacks predictivos fueron calculados.
        "calculada": False,

        # Momento en que se leyeron los valores predictivos.
        "timestamp_lectura": None,

        # Momento en que se calcularon los linepacks.
        "timestamp_calculo": None,

        # Error general del ciclo predictivo.
        "error": None,

        "escritura": {
            "exitosa": False,
            "puntos_exitosos": 0,
            "puntos_fallidos": 0,
            "error": None,
            "timestamp": None,
        },

    }
