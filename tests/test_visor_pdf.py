"""Prueba del visor de PDF integrado (no necesita base de datos).

    python -m unittest discover -s tests -p "test_visor_pdf.py" -v
"""
import os
import sys
import tempfile
import unittest
from decimal import Decimal as D
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import QApplication

import impresion
from visor_pdf import VistaPreviaPDF, imprimir_documento, leer_y_borrar

app = QApplication.instance() or QApplication([])


def pdf_de_prueba(estado="Borrador"):
    doc = {"tipo": "presupuesto", "numero": "A/PR00001907", "fecha": "2026-08-06", "fecha_vencimiento": "2026-08-06",
           "forma_pago": "Transferencia", "empresa_id": 1, "cliente_id": 1, "cliente_nombre": "Obras & Co <SL>",
           "cliente_nif": "B1", "estado": estado, "total": D("121.00"),
           "lineas": [{"descripcion": "Encimera & fregadero", "cantidad": D("1"), "precio_unitario": D("100"),
                       "porcentaje_iva": D("21")}]}
    fd, ruta = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    with mock.patch.object(impresion, "obtener_documento_completo", return_value=doc), \
         mock.patch.object(impresion, "obtener", return_value={"nombre": "Empresa", "nif": "X"}):
        impresion.generar_pdf(1, ruta)
    return leer_y_borrar(ruta), ruta


class PruebasVisor(unittest.TestCase):
    def test_carga_en_memoria_y_borra_el_temporal(self):
        datos, ruta = pdf_de_prueba()
        self.assertTrue(datos.startswith(b"%PDF"))
        self.assertFalse(os.path.exists(ruta))
        visor = VistaPreviaPDF(datos, titulo="Presupuesto A/PR00001907")
        self.addCleanup(visor.close)
        self.assertEqual(visor.documento.status(), QPdfDocument.Status.Ready)
        self.assertEqual(visor.documento.pageCount(), 1)
        self.assertIn("1 página", visor.lbl_paginas.text())

    def test_tamano_inicial_segun_pantalla(self):
        from PyQt6.QtCore import QRect
        visor = VistaPreviaPDF(pdf_de_prueba()[0])
        self.addCleanup(visor.close)
        tamano = visor.tamano_inicial(QRect(0, 0, 1920, 1032))
        self.assertEqual(tamano.height(), int(1032 * 0.92))          # casi toda la altura
        self.assertGreaterEqual(tamano.width(), 820)
        self.assertLessEqual(tamano.width(), int(1920 * 0.9))

    def test_zoom(self):
        visor = VistaPreviaPDF(pdf_de_prueba()[0])
        self.addCleanup(visor.close)
        visor.show()
        self.assertEqual(visor.vista.zoomMode(), QPdfView.ZoomMode.FitToWidth)
        visor._zoom(1.25)
        self.assertEqual(visor.vista.zoomMode(), QPdfView.ZoomMode.Custom)
        antes = visor.vista.zoomFactor()
        visor._zoom(1.25)
        self.assertAlmostEqual(visor.vista.zoomFactor(), antes * 1.25)
        for _ in range(30):
            visor._zoom(1.25)
        self.assertLessEqual(visor.vista.zoomFactor(), 4.0)
        visor._pagina_entera()
        self.assertEqual(visor.vista.zoomMode(), QPdfView.ZoomMode.FitInView)

    def test_guardar_como(self):
        datos = pdf_de_prueba()[0]
        visor = VistaPreviaPDF(datos)
        self.addCleanup(visor.close)
        destino = os.path.join(tempfile.mkdtemp(), "copia")          # sin .pdf: se anade
        with mock.patch("visor_pdf.QFileDialog.getSaveFileName", return_value=(destino, "")), \
             mock.patch("visor_pdf.QMessageBox.information"):
            visor.guardar_como()
        with open(destino + ".pdf", "rb") as archivo:
            self.assertEqual(archivo.read(), datos)

    def test_imprimir_varias_paginas(self):
        # El listado trimestral si ocupa varias paginas
        docs = [{"numero": "FAC-%04d" % i, "fecha": "2026-07-01", "cliente_nombre": "Cliente", "cliente_nif": "",
                 "base_imponible": D("100"), "total_iva": D("21"), "total": D("121"), "estado": "Emitida"}
                for i in range(80)]
        fd, ruta = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        impresion.generar_listado_pdf(docs, ruta, "factura", "2026-07-01", "2026-09-30")
        visor = VistaPreviaPDF(leer_y_borrar(ruta))
        self.addCleanup(visor.close)
        paginas = visor.documento.pageCount()
        self.assertGreater(paginas, 1)
        impresora = QPrinter(QPrinter.PrinterMode.HighResolution)
        impresora.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        salida = os.path.join(tempfile.mkdtemp(), "impreso.pdf")
        impresora.setOutputFileName(salida)
        imprimir_documento(visor.documento, impresora)
        impreso = QPdfDocument(None)
        impreso.load(salida)
        self.assertEqual(impreso.pageCount(), paginas)
        impreso.close()


if __name__ == "__main__":
    unittest.main()
