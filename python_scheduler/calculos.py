#!/usr/bin/env python3

from datetime import datetime
from numbers import Real
from typing import Any, Dict


# ============================================================
# CONSTANTES GENERALES
# ============================================================

# Se conserva el mismo valor utilizado en Visual Basic.
PI_SOBRE_4 = 0.785398

# Condiciones estándar para expresar el linepack en Sm3.
TEMPERATURA_ESTANDAR_KELVIN = 288.15
PRESION_ESTANDAR_BAR_ABS = 1.01325

# Temperatura fija del gas.
TEMPERATURA_GAS_KELVIN = 288.15

# Presión atmosférica utilizada para convertir barg a bar abs.
PRESION_ATMOSFERICA_BAR = 1.01325

# Factor de compresibilidad fijo.
FACTOR_COMPRESIBILIDAD_Z = 0.92

# Las presiones actuales de ingreso y egreso llegan en barg.
PRESIONES_ACTUALES_SON_RELATIVAS = True

# Las presiones promedio predichas ya llegan en bar absolutos,
# de acuerdo con el comportamiento del código Visual Basic.
PRESIONES_PREDICHAS_SON_ABSOLUTAS = True


# ============================================================
# FUNCIONES AUXILIARES DE VALIDACIÓN
# ============================================================

def _es_numero_valido(valor: Any) -> bool:
    """
    Determina si un valor es numérico y puede utilizarse en los
    cálculos.

    Los valores booleanos se excluyen porque bool es una subclase
    de int en Python, pero no representa una magnitud analógica.

    Parameters
    ----------
    valor:
        Valor que se desea validar.

    Returns
    -------
    bool:
        True si el valor es numérico y no es booleano.
    """

    return (
        isinstance(valor, Real)
        and not isinstance(valor, bool)
    )


def _obtener_numero_positivo(
    valor: Any,
    nombre: str,
) -> float:
    """
    Valida que un valor sea numérico y estrictamente positivo.

    Parameters
    ----------
    valor:
        Valor que se desea validar.

    nombre:
        Nombre descriptivo utilizado en el mensaje de error.

    Returns
    -------
    float:
        Valor convertido a float.

    Raises
    ------
    ValueError:
        Si el valor no es numérico o es menor o igual que cero.
    """

    if not _es_numero_valido(valor):
        raise ValueError(
            f"{nombre} no es un valor numérico válido: {valor!r}."
        )

    valor_float = float(valor)

    if valor_float <= 0:
        raise ValueError(
            f"{nombre} debe ser mayor que cero. "
            f"Valor recibido: {valor_float}."
        )

    return valor_float


def _validar_estructura_tramo(
    tramo: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Valida la estructura mínima necesaria para calcular un tramo.

    Parameters
    ----------
    tramo:
        Estructura correspondiente a un tramo.

    Returns
    -------
    Dict[str, Any]:
        Sección tramo["datos"].

    Raises
    ------
    ValueError:
        Si el tramo o su sección "datos" no tienen la estructura
        esperada.
    """

    if not isinstance(tramo, dict):
        raise ValueError(
            "El tramo debe ser un diccionario."
        )

    datos = tramo.get("datos")

    if not isinstance(datos, dict):
        raise ValueError(
            "El tramo no contiene una estructura válida en 'datos'."
        )

    return datos


# ============================================================
# CONVERSIÓN DE PRESIÓN
# ============================================================

def convertir_presion_actual_a_absoluta(
    presion_bar: float,
) -> float:
    """
    Convierte una presión actual a bar absolutos.

    Cuando PRESIONES_ACTUALES_SON_RELATIVAS es True, la presión
    recibida se interpreta como barg y se suma la presión
    atmosférica.

    Parameters
    ----------
    presion_bar:
        Presión actual expresada en barg o bar abs, según la
        configuración global.

    Returns
    -------
    float:
        Presión expresada en bar absolutos.

    Raises
    ------
    ValueError:
        Si la presión no es numérica o no es positiva.
    """

    presion = _obtener_numero_positivo(
        presion_bar,
        "La presión actual",
    )

    if PRESIONES_ACTUALES_SON_RELATIVAS:
        return presion + PRESION_ATMOSFERICA_BAR

    return presion


# ============================================================
# CÁLCULO DE PRESIÓN PROMEDIO
# ============================================================

def calcular_presion_promedio_bar_abs(
    presion_ingreso_bar: float,
    presion_egreso_bar: float,
) -> float:
    """
    Calcula la presión promedio del tramo en bar absolutos.

    Las presiones actuales se convierten primero a absolutas cuando
    están expresadas en barg.

    La fórmula utilizada es:

                         2 * (P1² + P1*P2 + P2²)
        P_promedio =    --------------------------
                              3 * (P1 + P2)

    Parameters
    ----------
    presion_ingreso_bar:
        Presión actual de ingreso.

    presion_egreso_bar:
        Presión actual de egreso.

    Returns
    -------
    float:
        Presión promedio expresada en bar absolutos.

    Raises
    ------
    ValueError:
        Si alguna presión es inválida o el cálculo produce un
        resultado no positivo.
    """

    p1_abs = convertir_presion_actual_a_absoluta(
        presion_ingreso_bar
    )

    p2_abs = convertir_presion_actual_a_absoluta(
        presion_egreso_bar
    )

    denominador = 3.0 * (p1_abs + p2_abs)

    if denominador == 0:
        raise ValueError(
            "No se puede calcular la presión promedio porque "
            "el denominador es cero."
        )

    numerador = 2.0 * (
        p1_abs ** 2
        + p1_abs * p2_abs
        + p2_abs ** 2
    )

    presion_promedio = numerador / denominador

    if presion_promedio <= 0:
        raise ValueError(
            "La presión promedio calculada no es válida. "
            f"Resultado: {presion_promedio} bar abs."
        )

    return presion_promedio


# ============================================================
# CÁLCULOS GEOMÉTRICOS
# ============================================================

def calcular_diametro_interno_metros(
    diametro_exterior_pulgadas: float,
    espesor_milimetros: float,
) -> float:
    """
    Calcula el diámetro interno del caño en metros.

    Fórmula:

        diámetro interno =
            diámetro exterior en pulgadas * 0.0254
            - 2 * espesor en milímetros / 1000

    Parameters
    ----------
    diametro_exterior_pulgadas:
        Diámetro exterior del caño en pulgadas.

    espesor_milimetros:
        Espesor de pared del caño en milímetros.

    Returns
    -------
    float:
        Diámetro interno en metros.

    Raises
    ------
    ValueError:
        Si los datos son inválidos o el diámetro interno resulta
        menor o igual que cero.
    """

    diametro_exterior = _obtener_numero_positivo(
        diametro_exterior_pulgadas,
        "El diámetro exterior",
    )

    espesor = _obtener_numero_positivo(
        espesor_milimetros,
        "El espesor",
    )

    diametro_exterior_metros = (
        diametro_exterior * 0.0254
    )

    espesor_metros = espesor / 1000.0

    diametro_interno_metros = (
        diametro_exterior_metros
        - 2.0 * espesor_metros
    )

    if diametro_interno_metros <= 0:
        raise ValueError(
            "El diámetro interno calculado es inválido. "
            f"Diámetro exterior: {diametro_exterior} pulgadas. "
            f"Espesor: {espesor} mm. "
            f"Diámetro interno: "
            f"{diametro_interno_metros} m."
        )

    return diametro_interno_metros


def calcular_volumen_interno_m3(
    diametro_exterior_pulgadas: float,
    espesor_milimetros: float,
    longitud_metros: float,
) -> float:
    """
    Calcula el volumen interno del tramo en metros cúbicos.

    Fórmula:

        volumen =
            PI_SOBRE_4
            * diámetro interno²
            * longitud

    Parameters
    ----------
    diametro_exterior_pulgadas:
        Diámetro exterior del caño en pulgadas.

    espesor_milimetros:
        Espesor de pared del caño en milímetros.

    longitud_metros:
        Longitud del tramo en metros.

    Returns
    -------
    float:
        Volumen interno en metros cúbicos.

    Raises
    ------
    ValueError:
        Si la longitud es inválida o el volumen calculado no es
        positivo.
    """

    longitud = _obtener_numero_positivo(
        longitud_metros,
        "La longitud",
    )

    diametro_interno = calcular_diametro_interno_metros(
        diametro_exterior_pulgadas,
        espesor_milimetros,
    )

    volumen = (
        PI_SOBRE_4
        * diametro_interno ** 2
        * longitud
    )

    if volumen <= 0:
        raise ValueError(
            "El volumen interno calculado es inválido. "
            f"Resultado: {volumen} m3."
        )

    return volumen


# ============================================================
# CÁLCULO DE LINEPACK
# ============================================================

def calcular_linepack_sm3(
    presion_promedio_bar_abs: float,
    diametro_exterior_pulgadas: float,
    espesor_milimetros: float,
    longitud_metros: float,
) -> float:
    """
    Calcula el linepack del tramo en metros cúbicos estándar.

    Fórmula:

        Linepack =
            volumen interno
            * (presión promedio absoluta /
               presión estándar absoluta)
            * (temperatura estándar /
               temperatura del gas)
            * (1 / factor de compresibilidad Z)

    La presión promedio recibida debe estar expresada en bar
    absolutos.

    Parameters
    ----------
    presion_promedio_bar_abs:
        Presión promedio del tramo en bar absolutos.

    diametro_exterior_pulgadas:
        Diámetro exterior del caño en pulgadas.

    espesor_milimetros:
        Espesor del caño en milímetros.

    longitud_metros:
        Longitud del tramo en metros.

    Returns
    -------
    float:
        Linepack calculado en Sm3.

    Raises
    ------
    ValueError:
        Si algún dato es inválido o el linepack no resulta positivo.
    """

    presion_promedio = _obtener_numero_positivo(
        presion_promedio_bar_abs,
        "La presión promedio absoluta",
    )

    if TEMPERATURA_ESTANDAR_KELVIN <= 0:
        raise ValueError(
            "La temperatura estándar debe ser mayor que cero."
        )

    if TEMPERATURA_GAS_KELVIN <= 0:
        raise ValueError(
            "La temperatura del gas debe ser mayor que cero."
        )

    if PRESION_ESTANDAR_BAR_ABS <= 0:
        raise ValueError(
            "La presión estándar debe ser mayor que cero."
        )

    if FACTOR_COMPRESIBILIDAD_Z <= 0:
        raise ValueError(
            "El factor de compresibilidad Z debe ser mayor "
            "que cero."
        )

    volumen_interno = calcular_volumen_interno_m3(
        diametro_exterior_pulgadas,
        espesor_milimetros,
        longitud_metros,
    )

    linepack = (
        volumen_interno
        * (
            presion_promedio
            / PRESION_ESTANDAR_BAR_ABS
        )
        * (
            TEMPERATURA_ESTANDAR_KELVIN
            / TEMPERATURA_GAS_KELVIN
        )
        * (
            1.0
            / FACTOR_COMPRESIBILIDAD_Z
        )
    )

    if linepack <= 0:
        raise ValueError(
            "El linepack calculado es inválido. "
            f"Resultado: {linepack} Sm3."
        )

    return linepack


# ============================================================
# CÁLCULO ACTUAL DE UN TRAMO
# ============================================================

def calcular_datos_tramo(
    tramo: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Calcula la presión promedio actual y el linepack de un tramo.

    La función utiliza los valores previamente cargados en:

        tramo["datos"]["presion_ingreso"]
        tramo["datos"]["presion_egreso"]
        tramo["datos"]["diametro"]
        tramo["datos"]["espesor"]
        tramo["datos"]["longitud"]

    Los resultados se guardan en:

        tramo["datos"]["presion_promedio"]
        tramo["datos"]["linepack"]

    Si el tramo ya está marcado como inválido, no se intenta
    calcular y se conservan los datos de error existentes.

    Parameters
    ----------
    tramo:
        Diccionario correspondiente a un tramo.

    Returns
    -------
    Dict[str, Any]:
        El mismo diccionario de tramo actualizado.

    Notes
    -----
    La función modifica el diccionario recibido y devuelve la misma
    referencia para hacer explícito el flujo del programa.
    """

    datos = _validar_estructura_tramo(tramo)

    datos["presion_promedio"] = None
    datos["linepack"] = None

    if not datos.get("valido", False):
        if not datos.get("error"):
            datos["error"] = (
                "El tramo no tiene datos de entrada válidos."
            )

        return tramo

    try:
        presion_ingreso = _obtener_numero_positivo(
            datos.get("presion_ingreso"),
            "La presión de ingreso",
        )

        presion_egreso = _obtener_numero_positivo(
            datos.get("presion_egreso"),
            "La presión de egreso",
        )

        diametro = _obtener_numero_positivo(
            datos.get("diametro"),
            "El diámetro exterior",
        )

        espesor = _obtener_numero_positivo(
            datos.get("espesor"),
            "El espesor",
        )

        longitud = _obtener_numero_positivo(
            datos.get("longitud"),
            "La longitud",
        )

        presion_promedio = calcular_presion_promedio_bar_abs(
            presion_ingreso,
            presion_egreso,
        )

        linepack = calcular_linepack_sm3(
            presion_promedio_bar_abs=presion_promedio,
            diametro_exterior_pulgadas=diametro,
            espesor_milimetros=espesor,
            longitud_metros=longitud,
        )

        datos["presion_promedio"] = presion_promedio
        datos["linepack"] = linepack

        datos["valido"] = True
        datos["error"] = None

    except (TypeError, ValueError, ArithmeticError) as error:
        datos["presion_promedio"] = None
        datos["linepack"] = None

        datos["valido"] = False
        datos["error"] = (
            f"Error de cálculo: {error}"
        )

    return tramo


# ============================================================
# CÁLCULO ACTUAL DE TODOS LOS TRAMOS
# ============================================================

def calcular_todos_los_tramos(
    tramos: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """
    Calcula la presión promedio actual y el linepack de todos los
    tramos.

    Un error físico o matemático en un tramo no interrumpe el
    procesamiento de los demás.

    Parameters
    ----------
    tramos:
        Diccionario de tramos indexado por ID.

    Returns
    -------
    Dict[str, Dict[str, Any]]:
        El mismo diccionario actualizado.

    Raises
    ------
    ValueError:
        Si la estructura principal no es un diccionario o contiene
        un tramo con formato inválido.
    """

    if not isinstance(tramos, dict):
        raise ValueError(
            "La estructura de tramos debe ser un diccionario."
        )

    for tramo_id, tramo in tramos.items():
        if not isinstance(tramo, dict):
            raise ValueError(
                f"El tramo '{tramo_id}' no tiene una "
                "estructura válida."
            )

        calcular_datos_tramo(tramo)

    return tramos


# ============================================================
# CÁLCULO PREDICTIVO DE UN TRAMO
# ============================================================

def calcular_prediccion_tramo(
    tramo: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Calcula los 72 valores de linepack predicho de un tramo.

    Cada punto predictivo debe contener una presión promedio
    predicha expresada en bar absolutos:

        tramo["datos"]["prediccion"]["puntos"][i]
            ["presion_promedio"]

    El resultado se guarda en:

        tramo["datos"]["prediccion"]["puntos"][i]
            ["linepack"]

    Los datos constructivos utilizados son los mismos del cálculo
    actual:

        tramo["datos"]["diametro"]
        tramo["datos"]["espesor"]
        tramo["datos"]["longitud"]

    Cada punto se procesa de forma independiente. Si un punto falla,
    los demás continúan calculándose.

    La predicción se marca como calculada únicamente si todos los
    puntos se calcularon correctamente.

    Parameters
    ----------
    tramo:
        Diccionario correspondiente a un tramo.

    Returns
    -------
    Dict[str, Any]:
        El mismo diccionario de tramo actualizado.

    Raises
    ------
    ValueError:
        Si la estructura predictiva general es inválida.
    """

    datos = _validar_estructura_tramo(tramo)

    prediccion = datos.get("prediccion")

    if not isinstance(prediccion, dict):
        raise ValueError(
            "El tramo no contiene una estructura válida "
            "en datos['prediccion']."
        )

    puntos = prediccion.get("puntos")

    if not isinstance(puntos, list):
        raise ValueError(
            "La predicción del tramo no contiene una lista "
            "válida de puntos."
        )

    prediccion["calculada"] = False
    prediccion["timestamp_calculo"] = None
    prediccion["error"] = None

    errores_generales = []

    try:
        diametro = _obtener_numero_positivo(
            datos.get("diametro"),
            "El diámetro exterior",
        )

        espesor = _obtener_numero_positivo(
            datos.get("espesor"),
            "El espesor",
        )

        longitud = _obtener_numero_positivo(
            datos.get("longitud"),
            "La longitud",
        )

    except (TypeError, ValueError) as error:
        mensaje = (
            "No se puede calcular la predicción porque los "
            f"datos constructivos son inválidos: {error}"
        )

        prediccion["error"] = mensaje

        for punto in puntos:
            if isinstance(punto, dict):
                punto["linepack"] = None
                punto["valido"] = False
                punto["error"] = mensaje

        return tramo

    cantidad_validos = 0

    for posicion, punto in enumerate(puntos):
        if not isinstance(punto, dict):
            errores_generales.append(
                f"El punto predictivo {posicion} no tiene una "
                "estructura válida."
            )
            continue

        punto["linepack"] = None
        punto["valido"] = False
        punto["error"] = None

        campo = punto.get(
            "campo",
            f"posición {posicion}",
        )

        try:
            presion_promedio = _obtener_numero_positivo(
                punto.get("presion_promedio"),
                (
                    "La presión promedio predicha "
                    f"del campo {campo}"
                ),
            )

            # De acuerdo con el Visual Basic, las presiones promedio
            # predichas ya están expresadas en bar absolutos.
            if not PRESIONES_PREDICHAS_SON_ABSOLUTAS:
                presion_promedio += PRESION_ATMOSFERICA_BAR

            linepack = calcular_linepack_sm3(
                presion_promedio_bar_abs=presion_promedio,
                diametro_exterior_pulgadas=diametro,
                espesor_milimetros=espesor,
                longitud_metros=longitud,
            )

            punto["linepack"] = linepack
            punto["valido"] = True
            punto["error"] = None

            cantidad_validos += 1

        except (TypeError, ValueError, ArithmeticError) as error:
            punto["linepack"] = None
            punto["valido"] = False
            punto["error"] = (
                f"Error de cálculo para {campo}: {error}"
            )

            errores_generales.append(
                punto["error"]
            )

    cantidad_total = len(puntos)

    if (
        cantidad_total > 0
        and cantidad_validos == cantidad_total
    ):
        prediccion["calculada"] = True
        prediccion["error"] = None
    else:
        prediccion["calculada"] = False

        prediccion["error"] = (
            f"Se calcularon correctamente "
            f"{cantidad_validos} de {cantidad_total} "
            "puntos predictivos."
        )

    prediccion["timestamp_calculo"] = datetime.now()

    return tramo


# ============================================================
# CÁLCULO PREDICTIVO DE TODOS LOS TRAMOS
# ============================================================

def calcular_predicciones_todos_los_tramos(
    tramos: Dict[str, Dict[str, Any]],
    solo_con_cambio: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """
    Calcula los linepacks predictivos de todos los tramos.

    Parameters
    ----------
    tramos:
        Diccionario de tramos indexado por ID.

    solo_con_cambio:
        Si es True, solamente se calculan los tramos cuya sección
        predictiva tenga:

            cambio_detectado = True

        Si es False, se intenta calcular la predicción de todos los
        tramos.

    Returns
    -------
    Dict[str, Dict[str, Any]]:
        El mismo diccionario actualizado.

    Raises
    ------
    ValueError:
        Si la estructura principal o la estructura predictiva de
        algún tramo es inválida.

    Notes
    -----
    Esta función no compara firmas, no lee OpenOPC y no promueve
    firma_pendiente a ultima_firma. Esas operaciones pertenecen al
    módulo de comunicación y al coordinador principal.
    """

    if not isinstance(tramos, dict):
        raise ValueError(
            "La estructura de tramos debe ser un diccionario."
        )

    for tramo_id, tramo in tramos.items():
        if not isinstance(tramo, dict):
            raise ValueError(
                f"El tramo '{tramo_id}' no tiene una "
                "estructura válida."
            )

        datos = _validar_estructura_tramo(tramo)
        prediccion = datos.get("prediccion")

        if not isinstance(prediccion, dict):
            raise ValueError(
                f"El tramo '{tramo_id}' no contiene una "
                "estructura predictiva válida."
            )

        if (
            solo_con_cambio
            and not prediccion.get(
                "cambio_detectado",
                False,
            )
        ):
            continue

        calcular_prediccion_tramo(tramo)

    return tramos