"""Pruebas del parser sin OpenOPC ni acceso a iFIX."""

import copy
import json
from pathlib import Path
import tempfile
import unittest

from python_scheduler.parse_config_json import (
    CANTIDAD_PUNTOS_PREDICCION,
    cargar_estructura_tramos,
    construir_campo_prediccion,
)


def tramo(identificador, base=None):
    return {
        "id": identificador,
        "base-tag": base or "SYS_" + identificador,
        "presion-ingreso": " PE.F_CV ",
        "presion-egreso": "FIX.PS.F_CV",
    }


class ConfiguracionTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.ruta = Path(self.temporal.name) / "config.json"

    def cargar(self, config):
        self.ruta.write_text(json.dumps(config), encoding="utf-8")
        original = self.ruta.read_bytes()
        resultado = cargar_estructura_tramos(self.ruta)
        self.assertEqual(self.ruta.read_bytes(), original)
        return resultado

    def mixto(self):
        return {"tag_prefix_opcua": "ignorado", "sistemas": {
            "S1": {"tramos": [tramo("A")], "subsistemas": [
                {"id": "SUB", "tramos": [tramo("B")]},
                {"id": "VACIO", "tramos": []},
            ]},
            "S2": {"subsistemas": [{"tramos": [tramo("C")]}]},
        }}

    def test_ambas_ubicaciones_y_sistemas_sin_perder_tramos(self):
        config = self.mixto()
        resultado = self.cargar(config)
        self.assertEqual(set(resultado), {"A", "B", "C"})
        for identificador, t in resultado.items():
            self.assertEqual(set(t), {"id", "base_tag", "tags", "datos"})
            self.assertEqual(t["id"], identificador)

    def test_solo_directos_solo_anidados_y_vacios(self):
        for sistema, esperado in (
            ({"tramos": [tramo("A")]}, {"A"}),
            ({"subsistemas": [{"tramos": [tramo("A")]}]}, {"A"}),
            ({"tramos": [], "subsistemas": []}, set()),
        ):
            with self.subTest(sistema=sistema):
                self.assertEqual(set(self.cargar({"sistemas": {"S": sistema}})), esperado)

    def test_tags_actuales_y_72_puntos_exactos(self):
        resultado = self.cargar(self.mixto())
        self.assertEqual(CANTIDAD_PUNTOS_PREDICCION, 72)
        for t in resultado.values():
            tags, datos = t["tags"], t["datos"]
            self.assertEqual(tags["presion_ingreso"], "FIX.PE.F_CV")
            self.assertEqual(tags["presion_egreso"], "FIX.PS.F_CV")
            for clave in ("diametro", "espesor", "longitud", "ppromedio", "linepack"):
                self.assertEqual(tags[clave], f"FIX.{t['base_tag']}_{clave.upper()}.F_CV")
            for clave in ("ppromedio_pred", "linepack_pred"):
                esperados = [f"FIX.{t['base_tag']}_{clave.upper()}.F_{i:02d}" for i in range(72)]
                self.assertEqual(tags[clave], esperados)
                self.assertEqual(len(set(tags[clave])), 72)
            pred = datos["prediccion"]
            self.assertEqual(len(pred["puntos"]), 72)
            for i, punto in enumerate(pred["puntos"]):
                self.assertEqual(punto, {"indice": i, "campo": f"F_{i:02d}",
                    "presion_promedio": None, "linepack": None, "valido": False, "error": None})
            self.assertIsNone(pred["ultima_firma"])
            self.assertIsNone(pred["firma_pendiente"])
            self.assertFalse(pred["calculada"])
            self.assertFalse(datos["escritura"]["exitosa"])

    def test_estados_no_compartidos(self):
        resultado = self.cargar(self.mixto())
        anterior = copy.deepcopy(resultado["B"])
        resultado["A"]["datos"]["prediccion"]["puntos"][0]["linepack"] = 123
        resultado["A"]["datos"]["escritura"]["exitosa"] = True
        self.assertEqual(resultado["B"], anterior)
        self.assertIsNone(resultado["A"]["datos"]["prediccion"]["puntos"][1]["linepack"])

    def test_id_duplicado_entre_ubicaciones_y_sistemas(self):
        for sistema, indice in (("S1", 0), ("S2", 0)):
            config = self.mixto()
            config["sistemas"][sistema]["subsistemas"][indice]["tramos"][0]["id"] = " A "
            with self.subTest(sistema=sistema), self.assertRaisesRegex(ValueError, "ID de tramo duplicado"):
                self.cargar(config)

    def test_salidas_duplicadas_casefold_y_espacios(self):
        config = self.mixto()
        config["sistemas"]["S2"]["subsistemas"][0]["tramos"][0]["base-tag"] = " sys_a "
        with self.assertRaisesRegex(ValueError, "Tag de salida duplicado"):
            self.cargar(config)

    def test_estructura_invalida(self):
        casos = [[], {}, {"sistemas": []}]
        for sistema in ({}, None, {"tramos": None}, {"tramos": {}},
                        {"subsistemas": None}, {"subsistemas": [None]},
                        {"subsistemas": [{}]}, {"subsistemas": [{"tramos": {}}]},
                        {"tramos": [None]}):
            casos.append({"sistemas": {"S": sistema}})
        for config in casos:
            with self.subTest(config=config), self.assertRaises(ValueError):
                self.cargar(config)

    def test_campos_obligatorios_en_ambas_ubicaciones(self):
        for campo in ("id", "base-tag", "presion-ingreso", "presion-egreso"):
            for valor in (None, "", "  ", 7):
                for directo in (True, False):
                    t = tramo("A")
                    t[campo] = valor
                    sistema = {"tramos": [t]} if directo else {"subsistemas": [{"tramos": [t]}]}
                    with self.subTest(campo=campo, valor=valor, directo=directo), self.assertRaises(ValueError):
                        self.cargar({"sistemas": {"S": sistema}})
            t = tramo("A")
            del t[campo]
            with self.assertRaisesRegex(ValueError, "Falta el campo obligatorio"):
                self.cargar({"sistemas": {"S": {"tramos": [t]}}})

    def test_json_malformado_y_ruta_inexistente(self):
        with self.assertRaises(FileNotFoundError):
            cargar_estructura_tramos(self.ruta)
        self.ruta.write_text('{"sistemas":', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JSON inválido"):
            cargar_estructura_tramos(self.ruta)

    def test_limites_indices(self):
        self.assertEqual(construir_campo_prediccion(0), "F_00")
        self.assertEqual(construir_campo_prediccion(71), "F_71")
        for i in (-1, 72):
            with self.assertRaises(ValueError):
                construir_campo_prediccion(i)
        for i in (True, 1.0, "0"):
            with self.assertRaises(TypeError):
                construir_campo_prediccion(i)


if __name__ == "__main__":
    unittest.main()
