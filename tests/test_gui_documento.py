"""Prueba de DialogoDocumento sin pantalla (QT_QPA_PLATFORM=offscreen) contra billx_test.

Casos: cliente exento, cliente con recargo de equivalencia (y descuento habitual)
y empresa con retencion IRPF; ademas editar (conserva numero y regimen) y duplicar.
"""
import os
import sys
import unittest
from decimal import Decimal as D
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_pruebas import crear_cliente, crear_empresa, exigir_base_de_pruebas, vaciar_tablas

app = None


def setUpModule():
    global app
    exigir_base_de_pruebas()
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])


class PruebasDialogoDocumento(unittest.TestCase):
    def setUp(self):
        import database
        import documentos
        self.db = database
        self.doc = documentos
        vaciar_tablas()
        self.empresa_sin_irpf = crear_empresa(nombre="Sin IRPF", nif="B1", predeterminada=1)
        self.empresa_irpf = crear_empresa(nombre="Con IRPF", nif="B2", retencion_irpf=15, serie_factura="IRPF-")
        self.cli_normal = crear_cliente(nombre="Normal")
        self.cli_exento = crear_cliente(nombre="Exento", exento_iva=1, recargo_equivalencia=1)
        self.cli_recargo = crear_cliente(nombre="Recargo", recargo_equivalencia=1, descuento=10,
                                         forma_pago="Confirming", dias_pago=60)
        # Un aviso (QMessageBox) bloquearia la prueba: se convierte en fallo con su texto
        avisos = mock.patch("ui_common.QMessageBox", **{
            "warning.side_effect": lambda _p, titulo, texto: self.fail(titulo + ": " + texto),
            "critical.side_effect": lambda _p, titulo, texto: self.fail(titulo + ": " + texto),
        })
        avisos.start()
        self.addCleanup(avisos.stop)

    # --- utilidades -------------------------------------------------------
    def abrir(self, registro=None, duplicar=False):
        dlg = self.doc.DialogoDocumento(None, registro=registro, duplicar=duplicar, tipo_doc="factura")
        self.addCleanup(dlg.deleteLater)
        return dlg

    def elegir_empresa(self, dlg, empresa_id):
        dlg.cmb_empresa.setCurrentIndex(dlg.cmb_empresa.findData(empresa_id))

    def rellenar_linea(self, dlg, fila, descripcion, cantidad, precio, iva="21", dto=None):
        while dlg.tabla_lineas.rowCount() <= fila:
            dlg._anadir_linea_vacia()
        celda = lambda col: dlg.tabla_lineas.cellWidget(fila, col)
        celda(self.doc.COL_DESCRIPCION).setText(descripcion)
        celda(self.doc.COL_CANTIDAD).setValue(cantidad)
        celda(self.doc.COL_PRECIO).setValue(precio)
        celda(self.doc.COL_IVA).setCurrentText(iva)
        if dto is not None:
            celda(self.doc.COL_DTO).setValue(dto)

    def guardar(self, dlg):
        dlg._intentar_guardar()
        self.assertEqual(dlg.result(), dlg.DialogCode.Accepted)
        return self.db.obtener_documento_completo(dlg.documento_guardado_id)

    # --- casos ------------------------------------------------------------
    def test_cliente_exento(self):
        dlg = self.abrir()
        self.elegir_empresa(dlg, self.empresa_sin_irpf)
        dlg._seleccionar_cliente(self.db.obtener("clientes", self.cli_exento))
        self.rellenar_linea(dlg, 0, "Obra exenta", 2, 100.0, "21")

        self.assertEqual(dlg.calculo["total_iva"], D("0.00"))
        self.assertEqual(dlg.calculo["total_recargo"], D("0.00"))   # exento anula el recargo
        self.assertEqual(dlg.calculo["total"], D("200.00"))
        self.assertIn("0,00", dlg.lbl_iva.text())
        self.assertFalse(dlg.lbl_regimen.isHidden())
        self.assertIn("exento", dlg.lbl_regimen.text())
        self.assertTrue(dlg.lbl_recargo.isHidden())
        self.assertTrue(dlg.lbl_retencion.isHidden())

        doc = self.guardar(dlg)
        self.assertEqual(doc["numero"], "FAC-0001")
        self.assertEqual(doc["exento_iva"], 1)
        self.assertEqual(doc["recargo_equivalencia"], 0)
        self.assertEqual(doc["total_iva"], D("0.00"))
        self.assertEqual(doc["total"], D("200.00"))

    def test_cliente_con_recargo_y_descuento_habitual(self):
        dlg = self.abrir()
        self.elegir_empresa(dlg, self.empresa_sin_irpf)
        dlg._seleccionar_cliente(self.db.obtener("clientes", self.cli_recargo))
        # La linea vacia inicial recibe el descuento habitual del cliente (10 %)
        self.assertAlmostEqual(dlg.tabla_lineas.cellWidget(0, self.doc.COL_DTO).value(), 10.0)
        self.assertEqual(dlg.cmb_forma_pago.currentText(), "Confirming")
        self.rellenar_linea(dlg, 0, "Encimera", 1, 1000.0, "21")
        self.rellenar_linea(dlg, 1, "Fregadero", 1, 100.0, "10")
        self.assertAlmostEqual(dlg.tabla_lineas.cellWidget(1, self.doc.COL_DTO).value(), 10.0)

        # Base 900 + 90; IVA 189 + 9; recargo 46,80 + 1,26
        self.assertEqual(dlg.calculo["base_imponible"], D("990.00"))
        self.assertEqual(dlg.calculo["total_iva"], D("198.00"))
        self.assertEqual(dlg.calculo["total_recargo"], D("48.06"))
        self.assertEqual(dlg.calculo["total"], D("1236.06"))
        self.assertFalse(dlg.lbl_recargo.isHidden())
        self.assertIn("48,06", dlg.lbl_recargo.text())
        self.assertIn("900,00", dlg.tabla_lineas.cellWidget(0, self.doc.COL_IMPORTE).text())

        doc = self.guardar(dlg)
        self.assertEqual(doc["recargo_equivalencia"], 1)
        self.assertEqual(doc["total_recargo"], D("48.06"))
        self.assertEqual(doc["total"], D("1236.06"))
        self.assertEqual(doc["forma_pago"], "Confirming")
        self.assertEqual([l["porcentaje_descuento"] for l in doc["lineas"]], [D("10.00"), D("10.00")])

    def test_empresa_con_irpf_editar_y_duplicar(self):
        dlg = self.abrir()
        self.elegir_empresa(dlg, self.empresa_irpf)
        dlg._seleccionar_cliente(self.db.obtener("clientes", self.cli_normal))
        self.rellenar_linea(dlg, 0, "Mano de obra & montaje", 10, 33.35, "21")   # 333,50

        self.assertEqual(dlg.calculo["total_retencion"], D("50.03"))   # 50,025
        self.assertEqual(dlg.calculo["total"], D("333.50") + D("70.04") - D("50.03"))
        self.assertFalse(dlg.lbl_retencion.isHidden())
        self.assertIn("15,00", dlg.lbl_retencion.text())
        self.assertIn("-50,03", dlg.lbl_retencion.text())
        # Cambiar a una empresa sin IRPF quita la retencion
        self.elegir_empresa(dlg, self.empresa_sin_irpf)
        self.assertEqual(dlg.calculo["total_retencion"], D("0.00"))
        self.assertTrue(dlg.lbl_retencion.isHidden())
        self.elegir_empresa(dlg, self.empresa_irpf)

        doc = self.guardar(dlg)
        self.assertEqual(doc["numero"], "IRPF-0001")
        self.assertEqual(doc["porcentaje_irpf"], D("15.00"))
        self.assertEqual(doc["total_retencion"], D("50.03"))

        # La empresa baja su IRPF: el documento YA emitido conserva el suyo al editarlo
        self.db.actualizar("empresas", self.empresa_irpf, {"retencion_irpf": 7})
        editar = self.abrir(registro=doc)
        self.assertEqual(editar.txt_numero.text(), "IRPF-0001")
        self.assertEqual(editar.calculo["total_retencion"], D("50.03"))
        editar.cmb_estado.setCurrentText("Pagada")
        editado = self.guardar(editar)
        self.assertEqual(editado["id"], doc["id"])
        self.assertEqual(editado["numero"], "IRPF-0001")
        self.assertEqual(editado["estado"], "Pagada")
        self.assertEqual(editado["total_retencion"], D("50.03"))

        # Duplicar: numero nuevo y regimen ACTUAL de la empresa (7 %)
        duplicado = self.abrir(registro=doc, duplicar=True)
        self.assertEqual(duplicado.calculo["porcentaje_irpf"], D("7.00"))
        copia = self.guardar(duplicado)
        self.assertEqual(copia["numero"], "IRPF-0002")
        self.assertEqual(copia["total_retencion"], D("23.35"))   # 23,345
        self.assertEqual(self.db.contar("documentos"), 2)
        self.assertEqual(self.db.obtener("empresas", self.empresa_irpf)["siguiente_factura"], 3)

    def test_linea_con_importe_sin_descripcion_avisa(self):
        dlg = self.abrir()
        dlg._seleccionar_cliente(self.db.obtener("clientes", self.cli_normal))
        self.rellenar_linea(dlg, 0, "", 1, 50.0)
        with mock.patch.object(dlg, "aviso", return_value=False) as aviso:
            dlg._intentar_guardar()
        self.assertIn("descripción", aviso.call_args[0][0])
        self.assertEqual(self.db.contar("documentos"), 0)
        self.assertEqual(self.db.obtener("empresas", self.empresa_sin_irpf)["siguiente_factura"], 1)


class PruebasVentanasYListado(unittest.TestCase):
    def setUp(self):
        import database
        import documentos
        self.db = database
        self.doc = documentos
        vaciar_tablas()
        self.empresa = crear_empresa(nombre="Empresa", nif="B1", predeterminada=1)
        self.cliente = crear_cliente(nombre="Cliente & Hijos <SL>", dias_pago=30)
        lineas = [{"descripcion": "Encimera", "cantidad": 1, "precio_unitario": 100, "porcentaje_iva": 21}]
        cab = {"tipo": "presupuesto", "fecha": "2026-09-10", "fecha_vencimiento": "2026-10-10",
               "empresa_id": self.empresa, "cliente_id": self.cliente, "cliente_nombre": "Cliente & Hijos <SL>",
               "estado": "Borrador"}
        self.presupuesto_id = database.guardar_documento(cab, lineas, asignar_numero=True)
        self.otro_id = database.guardar_documento(dict(cab, fecha="2026-09-20"), lineas, asignar_numero=True)
        avisos = mock.patch.multiple("documentos.QMessageBox", information=mock.DEFAULT, warning=mock.DEFAULT,
                                     critical=mock.DEFAULT)
        self.avisos = avisos.start()
        self.addCleanup(avisos.stop)
        self.panel = documentos.DocumentosWidget("presupuesto")
        self.addCleanup(self.cerrar_todo)

    def cerrar_todo(self):
        for ventana in self.doc.ventanas_documento_abiertas():
            ventana.reject()
        self.panel.deleteLater()

    def test_convertir_presupuesto_en_factura_con_fecha_de_hoy(self):
        from datetime import date, timedelta
        registro = self.db.obtener_documento_completo(self.presupuesto_id)
        ventana = self.panel._abrir_ventana(registro, duplicar=True, tipo_doc="factura", fecha_de_hoy=True,
                                            al_guardar=lambda: self.doc.QMessageBox.information(None, "Éxito", "ok"))
        hoy = date.today()
        self.assertEqual(ventana.dt_fecha.date().toPyDate(), hoy)
        self.assertEqual(ventana.dt_vencimiento.date().toPyDate(), hoy + timedelta(days=30))
        self.assertTrue(ventana.isVisible())
        self.assertFalse(ventana.isModal())

        ventana._intentar_guardar()
        factura = self.db.listar("documentos", condiciones=("tipo = ?",), params=("factura",))
        self.assertEqual(len(factura), 1)
        self.assertEqual(factura[0]["fecha"], hoy.isoformat())
        self.assertEqual(factura[0]["numero"], "FAC-0001")
        self.assertEqual(self.db.obtener("documentos", self.presupuesto_id)["fecha"], "2026-09-10")
        self.avisos["information"].assert_called_once()
        self.assertEqual(self.doc.ventanas_documento_abiertas(), [])

    def test_duplicar_normal_conserva_la_fecha(self):
        registro = self.db.obtener_documento_completo(self.presupuesto_id)
        ventana = self.panel._abrir_ventana(registro, duplicar=True)
        self.assertEqual(ventana.dt_fecha.date().toString("yyyy-MM-dd"), "2026-09-10")

    def test_varias_ventanas_a_la_vez(self):
        uno = self.db.obtener_documento_completo(self.presupuesto_id)
        dos = self.db.obtener_documento_completo(self.otro_id)
        v1 = self.panel._abrir_ventana(uno)
        v2 = self.panel._abrir_ventana(dos)
        v3 = self.panel._abrir_ventana()                     # uno nuevo, a la vez
        self.assertEqual(len(self.doc.ventanas_documento_abiertas()), 3)
        self.assertTrue(all(v.isVisible() for v in (v1, v2, v3)))
        # Ventanas propias (boton en la barra de tareas) y en cascada: ninguna tapa a otra
        self.assertTrue(all(v.parent() is None and v.isWindow() for v in (v1, v2, v3)))
        self.assertEqual(len({(v.x(), v.y()) for v in (v1, v2, v3)}), 3)
        self.assertIn("PRE-0001", v1.windowTitle())
        self.assertIn("PRE-0002", v2.windowTitle())
        # Abrir otra vez el mismo documento no crea una segunda ventana que lo pisaria
        self.assertIs(self.panel._abrir_ventana(uno), v1)
        self.assertEqual(len(self.doc.ventanas_documento_abiertas()), 3)
        # No se puede borrar un documento abierto en una ventana
        with self.assertRaises(self.db.DatabaseError):
            self.panel.borrar(self.presupuesto_id)
        v1.reject()
        self.assertEqual(len(self.doc.ventanas_documento_abiertas()), 2)
        self.assertTrue(self.panel.borrar(self.presupuesto_id))

    def test_listado_pdf_un_solo_fichero(self):
        import tempfile
        from impresion import generar_listado_pdf
        filas = self.db.listar("documentos", condiciones=("tipo = ?",), params=("presupuesto",), orden="fecha")
        fd, ruta = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            generar_listado_pdf(filas, ruta, "presupuesto", "2026-07-01", "2026-09-30")
            with open(ruta, "rb") as pdf:
                self.assertTrue(pdf.read(5).startswith(b"%PDF"))
        finally:
            os.remove(ruta)

    def test_trimestres(self):
        from datetime import date
        self.assertEqual(self.doc.trimestre_de(date(2026, 9, 10)), (date(2026, 7, 1), date(2026, 9, 30)))
        self.assertEqual(self.doc.trimestre_de(date(2026, 11, 2)), (date(2026, 10, 1), date(2026, 12, 31)))
        self.assertEqual(self.doc.trimestre_de(date(2026, 2, 28)), (date(2026, 1, 1), date(2026, 3, 31)))
        dlg = self.doc.DialogoExportarFechas(None, "factura")
        self.addCleanup(dlg.deleteLater)
        self.assertNotEqual(dlg.cmb_trimestre.currentData(), None)   # trimestre cerrado por defecto
        dlg.dt_inicio.setDate(date(2026, 1, 15))
        self.assertIsNone(dlg.cmb_trimestre.currentData())          # tocar fechas -> "a mano"


if __name__ == "__main__":
    unittest.main()
