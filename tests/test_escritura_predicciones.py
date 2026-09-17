"""Contrato de escritura predictiva, sin COM ni servidor OPC."""
import copy
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

from python_scheduler.parse_config_json import (
    construir_tags_prediccion, crear_estructura_prediccion,
)

# Carga aislada: no reemplaza el módulo productivo en otros tests.
spec = importlib.util.spec_from_file_location(
    "python_scheduler._opc_link_prueba",
    Path(__file__).resolve().parents[1] / "python_scheduler" / "opc_link.py",
)
opc_link = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"OpenOPC": types.ModuleType("OpenOPC")}):
    spec.loader.exec_module(opc_link)


def crear_tramo(base="SYS_A"):
    pred = crear_estructura_prediccion()
    pred.update(cambio_detectado=True, calculada=True,
                ultima_firma=(4400,) * 72, firma_pendiente=(4500,) * 72)
    for punto in pred["puntos"]:
        punto.update(valido=True, presion_promedio=45.0, linepack=7993.126)
    return {"base_tag": base,
            "tags": {"linepack_pred": construir_tags_prediccion(base, "LINEPACK_PRED")},
            "datos": {"prediccion": pred}}


class ClienteFalso:
    def __init__(self, responder=None):
        self.llamadas = []
        self.responder = responder

    def write(self, lote):
        self.llamadas.append(list(lote))
        normal = [(tag, "Success") for tag, _ in lote]
        return self.responder(normal, len(self.llamadas)) if self.responder else normal


class EscrituraPredictivaTests(unittest.TestCase):
    def setUp(self):
        self.tramos = {"A": crear_tramo()}
        self.pred = self.tramos["A"]["datos"]["prediccion"]

    def verificar_no_consolidada(self):
        self.assertFalse(self.pred["escritura"]["exitosa"])
        self.assertEqual(self.pred["ultima_firma"], (4400,) * 72)
        self.assertEqual(self.pred["firma_pendiente"], (4500,) * 72)
        self.assertTrue(self.pred["cambio_detectado"])
        self.assertTrue(self.pred["escritura"]["error"])

    def test_exito_desordenado_casefold_y_precision(self):
        cliente = ClienteFalso(lambda r, n: [(t.lower(), " success ") for t, _ in reversed(r)])
        opc_link.escribir_predicciones_tramos(cliente, self.tramos)
        self.assertTrue(self.pred["escritura"]["exitosa"])
        self.assertEqual(self.pred["escritura"]["puntos_exitosos"], 72)
        self.assertEqual(self.pred["ultima_firma"], (4500,) * 72)
        self.assertIsNone(self.pred["firma_pendiente"])
        self.assertFalse(self.pred["cambio_detectado"])
        self.assertEqual(cliente.llamadas[0][0][1], 7993.13)
        self.assertEqual(self.pred["puntos"][0]["linepack"], 7993.126)

    def test_respuestas_incompletas_ambiguas_o_invalidas(self):
        casos = {
            "falta_00": lambda r, n: r[1:],
            "falta_71": lambda r, n: r[:-1],
            "vacia": lambda r, n: [],
            "none": lambda r, n: None,
            "duplicado_reemplaza_faltante": lambda r, n: r[:-1] + [r[0]],
            "duplicado_extra": lambda r, n: r + [r[0]],
            "desconocido": lambda r, n: r + [("OTRO", "Success")],
            "malformada": lambda r, n: r + [("incorrecta",)],
            "escalar_multiple": lambda r, n: "Success",
            "error": lambda r, n: r[:-1] + [(r[-1][0], "Error")],
        }
        for nombre, responder in casos.items():
            with self.subTest(nombre=nombre):
                self.setUp()
                opc_link.escribir_predicciones_tramos(ClienteFalso(responder), self.tramos)
                self.verificar_no_consolidada()

    def test_lotes_y_respuestas_individuales(self):
        for size in (1, 10, 71, 100):
            with self.subTest(size=size):
                self.setUp()
                cliente = ClienteFalso(lambda r, n: "Success" if len(r) == 1 else r)
                opc_link.escribir_predicciones_tramos(cliente, self.tramos, size)
                self.assertTrue(self.pred["escritura"]["exitosa"])
                self.assertEqual(sum(map(len, cliente.llamadas)), 72)
                self.assertTrue(all(len(lote) <= size for lote in cliente.llamadas))

    def test_respuesta_de_otro_lote_no_completa_faltante(self):
        primero = self.tramos["A"]["tags"]["linepack_pred"][0]
        cliente = ClienteFalso(lambda r, n: r[1:] if n == 1 else r + [(primero, "Success")])
        opc_link.escribir_predicciones_tramos(cliente, self.tramos, 36)
        self.verificar_no_consolidada()
        self.assertEqual(self.pred["escritura"]["puntos_exitosos"], 71)

    def test_reintento_y_tramo_siguiente(self):
        self.tramos["B"] = crear_tramo("SYS_B")
        cliente = ClienteFalso(lambda r, n: r[:-1] if n == 1 else r)
        opc_link.escribir_predicciones_tramos(cliente, self.tramos)
        self.verificar_no_consolidada()
        self.assertTrue(self.tramos["B"]["datos"]["prediccion"]["escritura"]["exitosa"])
        opc_link.escribir_predicciones_tramos(cliente, self.tramos)
        self.assertEqual(len(cliente.llamadas), 3)
        self.assertEqual(len(cliente.llamadas[-1]), 72)
        self.assertTrue(self.pred["escritura"]["exitosa"])

    def test_excepcion_global_se_propaga_sin_consolidar(self):
        error = RuntimeError("desconectado")
        def responder(r, n):
            if n == 2:
                raise error
            return r
        cliente = ClienteFalso(responder)
        with self.assertRaises(RuntimeError) as caught:
            opc_link.escribir_predicciones_tramos(cliente, self.tramos, 36)
        self.assertIs(caught.exception, error)
        self.verificar_no_consolidada()
        self.assertEqual(self.pred["escritura"]["puntos_exitosos"], 36)
        self.assertEqual(self.pred["escritura"]["puntos_fallidos"], 36)

    def test_precondiciones_invalidas_no_escriben(self):
        original = copy.deepcopy(self.tramos)
        for caso in ("71_puntos", "73_puntos", "71_tags", "duplicado", "campo", "nan", "infinito", "firma"):
            with self.subTest(caso=caso):
                self.tramos = copy.deepcopy(original)
                self.pred = self.tramos["A"]["datos"]["prediccion"]
                tags = self.tramos["A"]["tags"]["linepack_pred"]
                if caso == "71_puntos": self.pred["puntos"].pop()
                if caso == "73_puntos": self.pred["puntos"].append(copy.deepcopy(self.pred["puntos"][-1]))
                if caso == "71_tags": tags.pop()
                if caso == "duplicado": tags[-1] = tags[0]
                if caso == "campo": self.pred["puntos"][0]["campo"] = "F_71"
                if caso == "nan": self.pred["puntos"][0]["linepack"] = float("nan")
                if caso == "infinito": self.pred["puntos"][0]["linepack"] = float("inf")
                if caso == "firma": self.pred["firma_pendiente"] = None
                cliente = ClienteFalso()
                opc_link.escribir_predicciones_tramos(cliente, self.tramos)
                self.assertEqual(cliente.llamadas, [])
                self.assertFalse(self.pred["escritura"]["exitosa"])
                self.assertEqual(self.pred["ultima_firma"], (4400,) * 72)

    def test_sin_cambio_o_sin_calculo(self):
        for campo in ("cambio_detectado", "calculada"):
            self.setUp()
            self.pred[campo] = False
            cliente = ClienteFalso()
            opc_link.escribir_predicciones_tramos(cliente, self.tramos)
            self.assertEqual(cliente.llamadas, [])

    def test_lote_invalido(self):
        for size in (0, -1, True, 1.5, "10"):
            with self.assertRaises(ValueError):
                opc_link.escribir_predicciones_tramos(ClienteFalso(), self.tramos, size)


if __name__ == "__main__":
    unittest.main()
