#!/usr/bin/env python3

"""Ensayo manual con escrituras reales en iFIX; consulte README.md local."""

import time
from datetime import datetime

import OpenOPC


# ============================================================
# CONFIGURACIÓN OPC
# ============================================================

OPC_SERVER = "Intellution.OPCiFIX.1"
OPC_HOST = "localhost"

INTERVALO_LECTURA_SEGUNDOS = 30
INTERVALO_RECONEXION_SEGUNDOS = 10


# ============================================================
# TAGS IFIX
# ============================================================

TAG_PE = "FIX.PRUEBA_OPC_PE.F_CV"
TAG_PS = "FIX.PRUEBA_OPC_PS.F_CV"

TAG_PPROMEDIO = "FIX.PRUEBA_OPC_PPROMEDIO.F_CV"
TAG_LINEPACK = "FIX.PRUEBA_OPC_LINEPACK.F_CV"

TAGS_ENTRADA = [
    TAG_PE,
    TAG_PS,
]

TAGS_SALIDA = [
    TAG_PPROMEDIO,
    TAG_LINEPACK,
]


# ============================================================
# CONSTANTES GENERALES
# ============================================================

# Se conserva el valor utilizado en el script Visual Basic.
PI_SOBRE_4 = 0.785398

# Condiciones estándar para Sm3.
TEMPERATURA_ESTANDAR_KELVIN = 288.15
PRESION_ESTANDAR_BAR_ABS = 1.01325

# Conversión de presión relativa a absoluta.
PRESION_1_ATM_EN_BAR = 1.01325

# Factor de compresibilidad fijo.
FACTOR_Z_POR_DEFECTO = 0.92

# Las presiones PE y PS están expresadas en bar relativos.
PRESIONES_SON_RELATIVAS = True


# ============================================================
# CONSTANTES DEL TRAMO DE PRUEBA
# ============================================================

DIAMETRO_EXTERIOR_PULGADAS = 6.0
ESPESOR_MILIMETROS = 4.0
LONGITUD_METROS = 10_000.0

# Por ahora se utiliza una temperatura fija igual a la estándar.
TEMPERATURA_GAS_KELVIN = 288.15


# ============================================================
# PRECISIÓN DE ESCRITURA
# ============================================================

DECIMALES_PPROMEDIO = 3
DECIMALES_LINEPACK = 2


# ============================================================
# CÁLCULOS DEL TRAMO
# ============================================================

def calcular_diametro_interno_metros():
    """
    Calcula el diámetro interno del caño.

    Diámetro exterior:
        pulgadas * 0,0254 = metros

    Espesor:
        2 * espesor_mm / 1000 = metros

    Diámetro interno:
        diámetro exterior - 2 * espesor
    """

    diametro_exterior_metros = (
        DIAMETRO_EXTERIOR_PULGADAS * 0.0254
    )

    espesor_total_metros = (
        2.0 * ESPESOR_MILIMETROS / 1000.0
    )

    diametro_interno_metros = (
        diametro_exterior_metros - espesor_total_metros
    )

    if diametro_interno_metros <= 0:
        raise ValueError(
            "El diámetro interno calculado es inválido: "
            f"{diametro_interno_metros} m"
        )

    return diametro_interno_metros


def calcular_volumen_interno_m3():
    """
    Calcula el volumen interno del tramo.

    Volumen:
        pi/4 * diámetro_interno^2 * longitud
    """

    diametro_interno_metros = (
        calcular_diametro_interno_metros()
    )

    volumen_m3 = (
        PI_SOBRE_4
        * diametro_interno_metros ** 2
        * LONGITUD_METROS
    )

    if volumen_m3 <= 0:
        raise ValueError(
            "El volumen interno calculado es inválido: "
            f"{volumen_m3} m3"
        )

    return volumen_m3


def convertir_presion_absoluta(presion_bar):
    """
    Convierte una presión relativa en bar a presión absoluta.

    Si en el futuro las presiones ya llegan como absolutas,
    PRESIONES_SON_RELATIVAS debe cambiarse a False.
    """

    if PRESIONES_SON_RELATIVAS:
        return presion_bar + PRESION_1_ATM_EN_BAR

    return presion_bar


def calcular_presion_promedio_bar_abs(pe_bar, ps_bar):
    """
    Calcula la presión promedio utilizando la fórmula del
    script Visual Basic:

                 2 * (P1^2 + P1*P2 + P2^2)
        Pprom =  --------------------------------
                       3 * (P1 + P2)

    P1 y P2 se convierten primero a presión absoluta.
    """

    if pe_bar <= 0:
        raise ValueError(
            f"La presión PE es inválida: {pe_bar}"
        )

    if ps_bar <= 0:
        raise ValueError(
            f"La presión PS es inválida: {ps_bar}"
        )

    pe_bar_abs = convertir_presion_absoluta(pe_bar)
    ps_bar_abs = convertir_presion_absoluta(ps_bar)

    denominador = 3.0 * (pe_bar_abs + ps_bar_abs)

    if denominador == 0:
        raise ValueError(
            "No es posible calcular la presión promedio: "
            "el denominador es cero."
        )

    numerador = 2.0 * (
        pe_bar_abs ** 2
        + pe_bar_abs * ps_bar_abs
        + ps_bar_abs ** 2
    )

    presion_promedio_bar_abs = numerador / denominador

    if presion_promedio_bar_abs <= 0:
        raise ValueError(
            "La presión promedio calculada es inválida: "
            f"{presion_promedio_bar_abs} bar abs"
        )

    return presion_promedio_bar_abs


def calcular_linepack_sm3(presion_promedio_bar_abs):
    """
    Calcula el linepack del tramo en Sm3.

    Linepack =
        volumen_interno
        * (presión_promedio_abs / presión_estándar_abs)
        * (temperatura_estándar / temperatura_gas)
        * (1 / factor_Z)
    """

    if presion_promedio_bar_abs <= 0:
        raise ValueError(
            "La presión promedio debe ser mayor que cero."
        )

    if TEMPERATURA_GAS_KELVIN <= 0:
        raise ValueError(
            "La temperatura del gas debe ser mayor que cero."
        )

    if FACTOR_Z_POR_DEFECTO <= 0:
        raise ValueError(
            "El factor Z debe ser mayor que cero."
        )

    volumen_interno_m3 = calcular_volumen_interno_m3()

    linepack_sm3 = (
        volumen_interno_m3
        * (
            presion_promedio_bar_abs
            / PRESION_ESTANDAR_BAR_ABS
        )
        * (
            TEMPERATURA_ESTANDAR_KELVIN
            / TEMPERATURA_GAS_KELVIN
        )
        * (
            1.0
            / FACTOR_Z_POR_DEFECTO
        )
    )

    if linepack_sm3 <= 0:
        raise ValueError(
            "El linepack calculado es inválido: "
            f"{linepack_sm3} Sm3"
        )

    return linepack_sm3


# ============================================================
# FUNCIONES OPC
# ============================================================

def conectar_opc():
    """
    Crea un nuevo cliente OpenOPC y se conecta al servidor
    OPC DA de iFIX.
    """

    opc = OpenOPC.client()
    opc.connect(OPC_SERVER, OPC_HOST)

    return opc


def normalizar_calidad(calidad):
    """
    Normaliza el texto de calidad entregado por OpenOPC.
    """

    if calidad is None:
        return ""

    return str(calidad).strip()


def calidad_es_buena(calidad):
    """
    Considera válidas las calidades cuyo texto comienza con Good.
    """

    return normalizar_calidad(calidad).lower().startswith(
        "good"
    )


def leer_presiones(opc):
    """
    Lee PE y PS en una única llamada OPC.

    Devuelve:
        pe
        ps
        resultados originales
    """

    resultados = opc.read(TAGS_ENTRADA)

    if not resultados:
        raise RuntimeError(
            "OpenOPC no devolvió resultados para PE y PS."
        )

    valores = {}

    for resultado in resultados:
        if len(resultado) != 4:
            raise RuntimeError(
                "Formato inesperado en la lectura OPC: "
                f"{resultado!r}"
            )

        nombre, valor, calidad, timestamp = resultado

        valores[nombre] = {
            "valor": valor,
            "calidad": calidad,
            "timestamp": timestamp,
        }

    if TAG_PE not in valores:
        raise RuntimeError(
            f"No se recibió el tag {TAG_PE}."
        )

    if TAG_PS not in valores:
        raise RuntimeError(
            f"No se recibió el tag {TAG_PS}."
        )

    pe_data = valores[TAG_PE]
    ps_data = valores[TAG_PS]

    if not isinstance(pe_data["valor"], (int, float)):
        raise ValueError(
            f"El valor de PE no es numérico: "
            f"{pe_data['valor']!r}"
        )

    if not isinstance(ps_data["valor"], (int, float)):
        raise ValueError(
            f"El valor de PS no es numérico: "
            f"{ps_data['valor']!r}"
        )

    # Para esta primera prueba solamente se informa si la calidad
    # no es Good. El cálculo continúa si el valor es numérico.
    if not calidad_es_buena(pe_data["calidad"]):
        print(
            f"ADVERTENCIA: calidad de PE no es Good: "
            f"{pe_data['calidad']}"
        )

    if not calidad_es_buena(ps_data["calidad"]):
        print(
            f"ADVERTENCIA: calidad de PS no es Good: "
            f"{ps_data['calidad']}"
        )

    return (
        float(pe_data["valor"]),
        float(ps_data["valor"]),
        resultados,
    )


def escribir_resultados(
    opc,
    presion_promedio_bar_abs,
    linepack_sm3,
):
    """
    Escribe presión promedio y linepack en una sola llamada OPC.

    OpenOPC recibe una lista de tuplas:
        (Item ID, valor)
    """

    presion_para_escribir = round(
        presion_promedio_bar_abs,
        DECIMALES_PPROMEDIO,
    )

    linepack_para_escribir = round(
        linepack_sm3,
        DECIMALES_LINEPACK,
    )

    escrituras = [
        (
            TAG_PPROMEDIO,
            presion_para_escribir,
        ),
        (
            TAG_LINEPACK,
            linepack_para_escribir,
        ),
    ]

    resultados = opc.write(escrituras)

    return (
        presion_para_escribir,
        linepack_para_escribir,
        resultados,
    )


# ============================================================
# PRESENTACIÓN DE RESULTADOS
# ============================================================

def mostrar_configuracion():
    diametro_interno = calcular_diametro_interno_metros()
    volumen_interno = calcular_volumen_interno_m3()

    print("=" * 78)
    print("CÁLCULO DE LINEPACK MEDIANTE OPENOPC")
    print("=" * 78)
    print(f"Servidor OPC:              {OPC_SERVER}")
    print(f"Host:                      {OPC_HOST}")
    print(f"Intervalo:                 {INTERVALO_LECTURA_SEGUNDOS} s")
    print()
    print("Tags de entrada:")
    print(f"  PE:                      {TAG_PE}")
    print(f"  PS:                      {TAG_PS}")
    print()
    print("Tags de salida:")
    print(f"  Presión promedio:        {TAG_PPROMEDIO}")
    print(f"  Linepack:                {TAG_LINEPACK}")
    print()
    print("Geometría del tramo:")
    print(
        f"  Diámetro exterior:       "
        f"{DIAMETRO_EXTERIOR_PULGADAS:.2f} pulgadas"
    )
    print(
        f"  Espesor:                 "
        f"{ESPESOR_MILIMETROS:.2f} mm"
    )
    print(
        f"  Longitud:                "
        f"{LONGITUD_METROS:.2f} m"
    )
    print(
        f"  Diámetro interno:        "
        f"{diametro_interno:.6f} m"
    )
    print(
        f"  Volumen interno:         "
        f"{volumen_interno:.3f} m3"
    )
    print()
    print("Condiciones de cálculo:")
    print(
        f"  Presiones relativas:     "
        f"{PRESIONES_SON_RELATIVAS}"
    )
    print(
        f"  Temperatura de gas:      "
        f"{TEMPERATURA_GAS_KELVIN:.2f} K"
    )
    print(
        f"  Factor Z:                "
        f"{FACTOR_Z_POR_DEFECTO:.3f}"
    )
    print()
    print("Presioná Ctrl+C para detener.")
    print("=" * 78)


def mostrar_ciclo(
    pe_bar,
    ps_bar,
    presion_promedio_bar_abs,
    linepack_sm3,
    resultados_lectura,
    resultados_escritura,
):
    ahora = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print()
    print("-" * 78)
    print(f"[{ahora}] Cálculo completado")
    print("-" * 78)

    print(f"PE relativa:               {pe_bar:.2f} barg")
    print(f"PS relativa:               {ps_bar:.2f} barg")
    print(
        f"PE absoluta:               "
        f"{convertir_presion_absoluta(pe_bar):.3f} bar abs"
    )
    print(
        f"PS absoluta:               "
        f"{convertir_presion_absoluta(ps_bar):.3f} bar abs"
    )
    print(
        f"Presión promedio:          "
        f"{presion_promedio_bar_abs:.3f} bar abs"
    )
    print(f"Linepack:                  {linepack_sm3:.2f} Sm3")

    print()
    print("Resultados de lectura OPC:")

    for nombre, valor, calidad, timestamp in resultados_lectura:
        print(
            f"  {nombre}: "
            f"valor={valor!r}, "
            f"calidad={calidad}, "
            f"timestamp={timestamp}"
        )

    print()
    print(
        "Resultado devuelto por opc.write(): "
        f"{resultados_escritura!r}"
    )


# ============================================================
# CICLO PRINCIPAL
# ============================================================

def ejecutar_ciclo(opc):
    """
    Realiza un ciclo completo:

    1. Lee PE y PS.
    2. Calcula presión promedio absoluta.
    3. Calcula linepack.
    4. Escribe ambos resultados en iFIX.
    """

    pe_bar, ps_bar, resultados_lectura = (
        leer_presiones(opc)
    )

    presion_promedio_bar_abs = (
        calcular_presion_promedio_bar_abs(
            pe_bar,
            ps_bar,
        )
    )

    linepack_sm3 = calcular_linepack_sm3(
        presion_promedio_bar_abs
    )

    (
        presion_escrita,
        linepack_escrito,
        resultados_escritura,
    ) = escribir_resultados(
        opc,
        presion_promedio_bar_abs,
        linepack_sm3,
    )

    mostrar_ciclo(
        pe_bar=pe_bar,
        ps_bar=ps_bar,
        presion_promedio_bar_abs=presion_escrita,
        linepack_sm3=linepack_escrito,
        resultados_lectura=resultados_lectura,
        resultados_escritura=resultados_escritura,
    )


def main():
    opc = None

    mostrar_configuracion()

    try:
        while True:
            if opc is None:
                try:
                    print()
                    print(
                        f"Conectando con {OPC_SERVER}..."
                    )

                    opc = conectar_opc()

                    print("Conexión OPC establecida.")

                except Exception as error:
                    ahora = datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                    print(
                        f"[{ahora}] No se pudo establecer "
                        f"la conexión OPC: {error!r}"
                    )
                    print(
                        "Nuevo intento dentro de "
                        f"{INTERVALO_RECONEXION_SEGUNDOS} segundos."
                    )

                    opc = None
                    time.sleep(
                        INTERVALO_RECONEXION_SEGUNDOS
                    )
                    continue

            try:
                # El primer cálculo se ejecuta inmediatamente.
                ejecutar_ciclo(opc)

                time.sleep(
                    INTERVALO_LECTURA_SEGUNDOS
                )

            except Exception as error:
                ahora = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                print()
                print(
                    f"[{ahora}] Error durante el ciclo: "
                    f"{error!r}"
                )

                # Se cierra el cliente para forzar una conexión
                # nueva en el siguiente intento.
                try:
                    opc.close()
                except Exception:
                    pass

                opc = None

                print(
                    "Se intentará reconectar dentro de "
                    f"{INTERVALO_RECONEXION_SEGUNDOS} segundos."
                )

                time.sleep(
                    INTERVALO_RECONEXION_SEGUNDOS
                )

    except KeyboardInterrupt:
        print()
        print("Ejecución detenida por el usuario.")

    finally:
        if opc is not None:
            try:
                opc.close()
            except Exception:
                pass

        print("Conexión OPC cerrada.")


if __name__ == "__main__":
    main()
