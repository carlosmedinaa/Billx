"""Pruebas de calculos.py (no necesitan base de datos).

    python -m unittest discover -s tests -p "test_calculos.py" -v
"""
import os
import sys
import unittest
from decimal import Decimal as D

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calculos import a_decimal, calcular_documento, importe_linea, porcentaje_recargo, redondear


def linea(cantidad, precio, iva=21, dto=0):
    return {"cantidad": cantidad, "precio_unitario": precio,
            "porcentaje_iva": iva, "porcentaje_descuento": dto}


class PruebasConversion(unittest.TestCase):
    def test_float_sin_error_binario(self):
        self.assertEqual(a_decimal(1.005), D("1.005"))

    def test_texto_formato_espanol(self):
        self.assertEqual(a_decimal("1.234,56 €"), D("1234.56"))
        self.assertEqual(a_decimal("21 %"), D("21"))
        self.assertEqual(a_decimal("10,5"), D("10.5"))

    def test_valores_vacios_o_invalidos(self):
        self.assertEqual(a_decimal(None), D("0"))
        self.assertEqual(a_decimal(""), D("0"))
        self.assertEqual(a_decimal("abc"), D("0"))
        self.assertEqual(a_decimal("nan"), D("0"))
        self.assertEqual(a_decimal("", por_defecto=1), D("1"))


class PruebasRedondeo(unittest.TestCase):
    def test_1005_redondea_a_101(self):
        # Con float, round(1.005, 2) da 1.0: este es el caso que motivo Decimal
        self.assertEqual(redondear("1.005"), D("1.01"))
        self.assertEqual(redondear(1.005), D("1.01"))
        self.assertEqual(importe_linea(1, "1.005"), D("1.01"))
        self.assertEqual(importe_linea(1, 1.005), D("1.01"))

    def test_half_up_en_negativos(self):
        self.assertEqual(redondear("-1.005"), D("-1.01"))

    def test_importe_con_descuento(self):
        self.assertEqual(importe_linea(3, "19.99", 15), D("50.97"))   # 50.9745
        self.assertEqual(importe_linea("2,5", "10", "10"), D("22.50"))
        self.assertEqual(importe_linea(1, 100, 100), D("0.00"))


class PruebasDocumento(unittest.TestCase):
    def test_documento_general_agrupado_por_iva(self):
        r = calcular_documento([
            linea(2, "10.00", 21),
            linea(1, "33.33", 21, dto=10),     # 29.997 -> 30.00
            linea(4, "2.50", 10),
            linea(1, "7.77", 4),
            linea(1, "5", 0),
        ])
        self.assertEqual([g["porcentaje_iva"] for g in r["desglose"]], [21, 10, 4, 0])
        g21 = r["desglose"][0]
        self.assertEqual(g21["base"], D("50.00"))
        self.assertEqual(g21["cuota_iva"], D("10.50"))
        self.assertEqual(r["base_imponible"], D("72.77"))
        self.assertEqual(r["total_iva"], D("10.50") + D("1.00") + D("0.31"))
        self.assertEqual(r["total_recargo"], D("0.00"))
        self.assertEqual(r["total_retencion"], D("0.00"))
        self.assertEqual(r["total"], D("72.77") + D("11.81"))
        self.assertEqual([l["importe"] for l in r["lineas"]],
                         [D("20.00"), D("30.00"), D("10.00"), D("7.77"), D("5.00")])

    def test_mismo_tipo_con_distinta_escritura_se_agrupa(self):
        r = calcular_documento([linea(1, 10, "21"), linea(1, 10, 21.0), linea(1, 10, D("21.00"))])
        self.assertEqual(len(r["desglose"]), 1)
        self.assertEqual(r["desglose"][0]["base"], D("30.00"))

    def test_iva_redondeado_por_grupo_no_por_linea(self):
        # 7 lineas de 0,07 al 21 %: redondeando por linea saldria 0,01 x 7 = 0,07;
        # por grupo es 0,49 x 21 % = 0,1029 -> 0,10
        r = calcular_documento([linea(1, "0.07", 21)] * 7)
        self.assertEqual(r["total_iva"], D("0.10"))

    def test_cliente_exento(self):
        r = calcular_documento([linea(1, 100, 21), linea(1, 50, 10)],
                               exento_iva=1, recargo_equivalencia=1)
        self.assertEqual(r["total_iva"], D("0.00"))
        self.assertEqual(r["total_recargo"], D("0.00"))
        self.assertEqual(len(r["desglose"]), 1)
        self.assertEqual(r["desglose"][0]["porcentaje_iva"], 0)
        self.assertEqual(r["total"], D("150.00"))
        self.assertTrue(all(l["porcentaje_iva_aplicado"] == 0 for l in r["lineas"]))

    def test_recargo_equivalencia(self):
        self.assertEqual(porcentaje_recargo(21), D("5.2"))
        self.assertEqual(porcentaje_recargo("10,00"), D("1.4"))
        self.assertEqual(porcentaje_recargo(4.0), D("0.5"))
        self.assertEqual(porcentaje_recargo(0), D("0"))
        r = calcular_documento([linea(1, 100, 21), linea(1, 100, 10), linea(1, 100, 4), linea(1, 100, 0)],
                               recargo_equivalencia=True)
        self.assertEqual([g["cuota_recargo"] for g in r["desglose"]],
                         [D("5.20"), D("1.40"), D("0.50"), D("0.00")])
        self.assertEqual(r["total_recargo"], D("7.10"))
        self.assertEqual(r["total"], D("400.00") + D("35.00") + D("7.10"))

    def test_retencion_irpf(self):
        r = calcular_documento([linea(1, "1000.00", 21)], porcentaje_irpf=15)
        self.assertEqual(r["total_retencion"], D("150.00"))
        self.assertEqual(r["total"], D("1000.00") + D("210.00") - D("150.00"))
        r = calcular_documento([linea(1, "33.35", 21)], porcentaje_irpf="7")   # 2.3345
        self.assertEqual(r["total_retencion"], D("2.33"))

    def test_recargo_e_irpf_a_la_vez(self):
        r = calcular_documento([linea(2, "125.50", 21, dto=5)],             # 238.45
                               recargo_equivalencia=1, porcentaje_irpf=15)
        self.assertEqual(r["base_imponible"], D("238.45"))
        self.assertEqual(r["total_iva"], D("50.07"))        # 50.0745
        self.assertEqual(r["total_recargo"], D("12.40"))    # 12.3994
        self.assertEqual(r["total_retencion"], D("35.77"))  # 35.7675
        self.assertEqual(r["total"], D("265.15"))

    def test_documento_vacio(self):
        r = calcular_documento([])
        self.assertEqual(r["total"], D("0.00"))
        self.assertEqual(r["desglose"], [])

    def test_no_modifica_las_lineas_de_entrada(self):
        entrada = [linea(1, 10)]
        calcular_documento(entrada)
        self.assertNotIn("importe", entrada[0])

    def test_totales_siempre_con_dos_decimales(self):
        r = calcular_documento([linea(1, 10)])
        for clave in ("base_imponible", "total_iva", "total_recargo", "total_retencion", "total"):
            self.assertEqual(r[clave].as_tuple().exponent, -2, clave)


if __name__ == "__main__":
    unittest.main()
