#!/usr/bin/env python3

"""Ensayo manual contra iFIX real; consulte README.md de este directorio."""

import time
from datetime import datetime

import OpenOPC


OPC_SERVER = "Intellution.OPCiFIX.1"
OPC_HOST = "localhost"

INTERVAL_SECONDS = 30

TAGS = [
    "FIX.PRUEBA_OPC_PE.F_CV",
    "FIX.PRUEBA_OPC_PS.F_CV",
]


def mostrar_resultados(resultados):
    """
    Muestra los resultados devueltos por OpenOPC.

    Para una lectura múltiple, cada resultado normalmente tiene:
        nombre, valor, calidad, timestamp
    """

    fecha_lectura = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print()
    print("=" * 80)
    print(f"Lectura local: {fecha_lectura}")
    print("=" * 80)

    for nombre, valor, calidad, timestamp in resultados:
        if calidad == "Good":
            valor_texto = (
                f"{valor:.2f}"
                if isinstance(valor, (int, float))
                else str(valor)
            )

            print(
                f"{nombre:<35} "
                f"Valor={valor_texto:<10} "
                f"Calidad={calidad:<10} "
                f"Timestamp={timestamp}"
            )
        else:
            print(
                f"{nombre:<35} "
                f"Valor={valor!r:<10} "
                f"Calidad={calidad:<10} "
                f"Timestamp={timestamp}"
            )


def main():
    opc = None

    try:
        print("Creando cliente OpenOPC...")
        opc = OpenOPC.client()

        print(f"Conectando con {OPC_SERVER}...")
        opc.connect(OPC_SERVER, OPC_HOST)

        print("Conexión establecida.")
        print("Tags configurados:")

        for tag in TAGS:
            print(f"  {tag}")

        print(f"Intervalo de lectura: {INTERVAL_SECONDS} segundos")
        print("Presioná Ctrl+C para detener.")

        while True:
            try:
                resultados = opc.read(TAGS)

                mostrar_resultados(resultados)

            except Exception as error:
                fecha_error = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                print()
                print(f"[{fecha_error}] Error durante la lectura OPC:")
                print(repr(error))

            time.sleep(INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print()
        print("Lectura detenida por el usuario.")

    except Exception as error:
        print()
        print("No se pudo iniciar la comunicación OPC:")
        print(repr(error))

    finally:
        if opc is not None:
            try:
                opc.close()
                print("Conexión OPC cerrada.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
