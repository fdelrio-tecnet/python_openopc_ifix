"""Integración en memoria de lectura, cálculo y escritura sin iFIX."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from python_scheduler import calculos
from python_scheduler.parse_config_json import cargar_estructura_tramos
from test_escritura_predicciones import opc_link


class ClienteCiclo:
    def __init__(self, tramos):
        self.valores = {}
        self.calidades = {}
        self.escrituras = []
        self.fallar_escritura = False
        self.fallar_lectura = False
        for tramo in tramos.values():
            tags = tramo["tags"]
            for campo, valor in zip(opc_link.CAMPOS_ENTRADA, (44.66, 44.31, 6, 4, 10000)):
                self.valores[tags[campo]] = valor
            for tag in tags["ppromedio_pred"]:
                self.valores[tag] = 45.498474367603876

    def read(self, tags):
        if self.fallar_lectura:
            raise RuntimeError("OPC desconectado")
        return [(tag, self.valores[tag], self.calidades.get(tag, "Good"), "timestamp")
                for tag in reversed(tags) if tag in self.valores]

    def write(self, pares):
        self.escrituras.append(list(pares))
        respuestas = [(tag, "Success") for tag, _ in pares]
        return respuestas[:-1] if self.fallar_escritura else respuestas


class CicloTests(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as temporal:
            p = Path(temporal) / "config.json"
            p.write_text(json.dumps({"sistemas": {"S": {"tramos": [
                {"id": i, "base-tag": "SYS_" + i,
                 "presion-ingreso": "PE_" + i + ".F_CV",
                 "presion-egreso": "PS_" + i + ".F_CV"}
                for i in ("A", "B")
            ]}}}), encoding="utf-8")
            self.tramos = cargar_estructura_tramos(p)
        self.opc = ClienteCiclo(self.tramos)
        self.a = self.tramos["A"]
        self.pred = self.a["datos"]["prediccion"]

    def actual(self, **kwargs):
        opc_link.leer_datos_tramos(self.opc, self.tramos, **kwargs)
        calculos.calcular_todos_los_tramos(self.tramos)
        opc_link.escribir_resultados_tramos(self.opc, self.tramos)

    def predictivo(self):
        opc_link.leer_predicciones_tramos(self.opc, self.tramos, tamano_lote=25)
        calculos.calcular_predicciones_todos_los_tramos(self.tramos)
        opc_link.escribir_predicciones_tramos(self.opc, self.tramos, tamano_lote=25)

    def test_ciclo_completo_sin_cambios_y_extremos(self):
        self.actual()
        self.assertAlmostEqual(self.a["datos"]["linepack"], 7993.124399335523)
        self.assertTrue(self.a["datos"]["escritura"]["exitosa"])
        self.predictivo()
        self.assertTrue(self.pred["escritura"]["exitosa"])
        n = len(self.opc.escrituras)
        self.predictivo()
        self.assertEqual(len(self.opc.escrituras), n)
        for indice in (0, 71):
            self.opc.valores[self.a["tags"]["ppromedio_pred"][indice]] += 0.1
            firma = self.pred["ultima_firma"]
            self.predictivo()
            self.assertNotEqual(self.pred["ultima_firma"], firma)
            self.assertTrue(self.pred["escritura"]["exitosa"])

    def test_reintento_tras_relectura(self):
        self.actual()
        self.opc.fallar_escritura = True
        self.predictivo()
        self.assertIsNone(self.pred["ultima_firma"])
        self.assertTrue(self.pred["cambio_detectado"])
        pendiente = self.pred["firma_pendiente"]
        self.opc.fallar_escritura = False
        self.predictivo()
        self.assertEqual(self.pred["ultima_firma"], pendiente)

    def test_good_por_defecto_y_opcion_en_ambos_ciclos(self):
        self.opc.calidades[self.a["tags"]["presion_ingreso"]] = "Bad"
        self.actual()
        self.assertFalse(self.a["datos"]["valido"])
        self.actual(exigir_calidad_good=False)
        self.assertTrue(self.a["datos"]["valido"])
        tag = self.a["tags"]["ppromedio_pred"][0]
        self.opc.calidades[tag] = "Uncertain"
        opc_link.leer_predicciones_tramos(self.opc, self.tramos)
        self.assertFalse(self.pred["cambio_detectado"])
        opc_link.leer_predicciones_tramos(self.opc, self.tramos, exigir_calidad_good=False)
        self.assertTrue(self.pred["cambio_detectado"])

    def test_no_finitos_y_lectura_parcial_son_locales(self):
        self.actual()
        tag = self.a["tags"]["ppromedio_pred"][0]
        for valor in (float("nan"), float("inf"), -float("inf"), None):
            with self.subTest(valor=valor):
                self.opc.valores[tag] = valor
                self.predictivo()
                self.assertIsNone(self.pred["firma_pendiente"])
                self.assertFalse(self.pred["calculada"])
                self.assertIsNotNone(self.tramos["B"]["datos"]["prediccion"]["ultima_firma"])
        del self.opc.valores[tag]
        self.predictivo()
        self.assertFalse(self.pred["calculada"])
        for valor in (float("nan"), float("inf")):
            self.opc.valores[self.a["tags"]["presion_ingreso"]] = valor
            self.actual(exigir_calidad_good=False)
            self.assertFalse(self.a["datos"]["valido"])
            self.assertTrue(self.tramos["B"]["datos"]["valido"])

    def test_excepcion_lecture_invalida_estado_anterior(self):
        self.actual()
        self.predictivo()
        firma = self.pred["ultima_firma"]
        self.opc.fallar_lectura = True
        with self.assertRaises(RuntimeError):
            opc_link.leer_predicciones_tramos(self.opc, self.tramos)
        self.assertEqual(self.pred["ultima_firma"], firma)
        self.assertFalse(self.pred["calculada"])
        self.assertIsNone(self.pred["timestamp_calculo"])
        self.assertIsNone(self.pred["firma_pendiente"])
        self.assertTrue(all(p["linepack"] is None for p in self.pred["puntos"]))
        self.assertFalse(self.pred["escritura"]["exitosa"])

    def test_longitudes_invalidas_en_lectura_y_calculo(self):
        self.actual()
        original = copy.deepcopy(self.tramos)
        for cantidad in (0, 71, 73):
            for campo in ("puntos", "tags"):
                with self.subTest(cantidad=cantidad, campo=campo):
                    tramos = copy.deepcopy(original)
                    pred = tramos["A"]["datos"]["prediccion"]
                    lista = pred["puntos"] if campo == "puntos" else tramos["A"]["tags"]["ppromedio_pred"]
                    lista[:] = (lista + [copy.deepcopy(lista[-1])])[:cantidad]
                    opc_link.leer_predicciones_tramos(self.opc, tramos)
                    self.assertFalse(pred["cambio_detectado"])
                    self.assertTrue(pred["error"])
                    if campo == "puntos":
                        calculos.calcular_prediccion_tramo(tramos["A"])
                        self.assertFalse(pred["calculada"])

    def test_calculo_independiente_de_puntos_y_no_finitos(self):
        self.actual()
        opc_link.leer_predicciones_tramos(self.opc, self.tramos)
        self.pred["puntos"][0]["presion_promedio"] = float("nan")
        calculos.calcular_predicciones_todos_los_tramos(self.tramos)
        self.assertFalse(self.pred["calculada"])
        self.assertEqual(sum(p["valido"] for p in self.pred["puntos"]), 71)
        for valor in (float("nan"), float("inf"), -float("inf"), True):
            with self.assertRaises(ValueError):
                calculos.calcular_presion_promedio_bar_abs(valor, 44.31)
            with self.assertRaises(ValueError):
                calculos.calcular_linepack_sm3(45, 6, 4, valor)


if __name__ == "__main__":
    unittest.main()
