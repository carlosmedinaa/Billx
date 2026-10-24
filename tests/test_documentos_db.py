"""Pruebas de guardar_documento contra billx_test (ver tests/base_pruebas.py)."""
import os
import sys
import tempfile
import threading
import unittest
from decimal import Decimal as D
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from base_pruebas import crear_cliente, crear_empresa, exigir_base_de_pruebas, vaciar_tablas


def setUpModule():
    exigir_base_de_pruebas()


def cabecera(empresa_id, cliente_id, **extra):
    datos = {"tipo": "factura", "numero": "", "fecha": "2026-10-24", "fecha_vencimiento": "2026-11-23",
             "forma_pago": "Transferencia", "empresa_id": empresa_id, "cliente_id": cliente_id,
             "cliente_nombre": "Cliente", "estado": "Emitida",
             "exento_iva": 0, "recargo_equivalencia": 0, "porcentaje_irpf": 0}
    datos.update(extra)
    return datos


LINEAS = [
    {"descripcion": "Encimera", "cantidad": D("2"), "precio_unitario": D("125.50"),
     "porcentaje_descuento": D("5"), "porcentaje_iva": D("21")},
    {"descripcion": "Transporte", "cantidad": D("1"), "precio_unitario": D("40"),
     "porcentaje_descuento": D("0"), "porcentaje_iva": D("10")},
]


class PruebasGuardarDocumento(unittest.TestCase):
    def setUp(self):
        import database
        self.db = database
        vaciar_tablas()
        self.empresa_id = crear_empresa(retencion_irpf=15)
        self.cliente_id = crear_cliente(nombre="Cliente normal")

    def siguiente(self, tipo="factura"):
        return self.db.obtener("empresas", self.empresa_id)["siguiente_" + tipo]

    def test_nuevo_asigna_numero_y_recalcula_importes(self):
        # Totales falsos a proposito: guardar_documento debe ignorarlos
        cab = cabecera(self.empresa_id, self.cliente_id, recargo_equivalencia=1, porcentaje_irpf=D("15"),
                       base_imponible=1, total_iva=1, total=1)
        doc_id = self.db.guardar_documento(cab, LINEAS, asignar_numero=True)
        doc = self.db.obtener_documento_completo(doc_id)
        self.assertEqual(doc["numero"], "FAC-0001")
        self.assertEqual(self.siguiente(), 2)
        self.assertEqual(doc["base_imponible"], D("278.45"))
        self.assertEqual(doc["total_iva"], D("54.07"))
        self.assertEqual(doc["total_recargo"], D("12.96"))
        self.assertEqual(doc["porcentaje_irpf"], D("15.00"))
        self.assertEqual(doc["total_retencion"], D("41.77"))
        self.assertEqual(doc["total"], D("303.71"))
        self.assertEqual(doc["recargo_equivalencia"], 1)
        self.assertEqual([l["subtotal"] for l in doc["lineas"]], [D("238.45"), D("40.00")])
        self.assertIsInstance(doc["total"], D)
        self.assertTrue(doc["fecha_creacion"])

    def test_editar_conserva_numero_y_fecha_de_alta(self):
        doc_id = self.db.guardar_documento(cabecera(self.empresa_id, self.cliente_id), LINEAS, asignar_numero=True)
        original = self.db.obtener_documento_completo(doc_id)

        cab = cabecera(self.empresa_id, self.cliente_id, numero=original["numero"], estado="Pagada")
        nuevas = [dict(LINEAS[0], cantidad=D("3"))]
        self.assertEqual(self.db.guardar_documento(cab, nuevas, registro_id=doc_id), doc_id)

        editado = self.db.obtener_documento_completo(doc_id)
        self.assertEqual(editado["numero"], "FAC-0001")
        self.assertEqual(editado["estado"], "Pagada")
        self.assertEqual(editado["fecha_creacion"], original["fecha_creacion"])
        self.assertEqual(len(editado["lineas"]), 1)
        self.assertEqual(editado["base_imponible"], D("357.68"))   # 3 x 125,50 x 0,95 = 357,675
        self.assertEqual(self.siguiente(), 2)                      # editar no consume numero
        self.assertEqual(self.db.contar("documentos"), 1)

    def test_duplicar_crea_otro_numero_sin_tocar_el_original(self):
        doc_id = self.db.guardar_documento(cabecera(self.empresa_id, self.cliente_id), LINEAS, asignar_numero=True)
        original = self.db.obtener_documento_completo(doc_id)
        copia_cab = {k: v for k, v in original.items() if k not in ("id", "lineas", "fecha_creacion")}
        copia_id = self.db.guardar_documento(copia_cab, original["lineas"], asignar_numero=True)

        self.assertNotEqual(copia_id, doc_id)
        self.assertEqual(self.db.obtener("documentos", copia_id)["numero"], "FAC-0002")
        self.assertEqual(self.db.obtener("documentos", doc_id)["numero"], "FAC-0001")
        self.assertEqual(len(self.db.obtener_documento_completo(copia_id)["lineas"]), 2)
        self.assertEqual(len(self.db.obtener_documento_completo(doc_id)["lineas"]), 2)
        self.assertEqual(self.siguiente(), 3)

    def test_series_independientes_por_tipo(self):
        self.db.guardar_documento(cabecera(self.empresa_id, self.cliente_id), LINEAS, asignar_numero=True)
        pre_id = self.db.guardar_documento(cabecera(self.empresa_id, self.cliente_id, tipo="presupuesto"),
                                           LINEAS, asignar_numero=True)
        self.assertEqual(self.db.obtener("documentos", pre_id)["numero"], "PRE-0001")

    def test_dos_hilos_a_la_vez_dan_numeros_unicos_y_correlativos(self):
        por_hilo, hilos = 15, 2
        salida = threading.Barrier(hilos)
        errores = []

        def trabajar():
            try:
                salida.wait()
                for _ in range(por_hilo):
                    self.db.guardar_documento(cabecera(self.empresa_id, self.cliente_id), LINEAS, asignar_numero=True)
            except Exception as error:      # se informa en el hilo principal
                errores.append(error)

        trabajadores = [threading.Thread(target=trabajar) for _ in range(hilos)]
        for t in trabajadores:
            t.start()
        for t in trabajadores:
            t.join(120)
        self.assertEqual(errores, [])

        numeros = [d["numero"] for d in self.db.listar("documentos")]
        total = por_hilo * hilos
        self.assertEqual(len(numeros), total)
        self.assertEqual(sorted(numeros), ["FAC-%04d" % n for n in range(1, total + 1)])
        self.assertEqual(self.siguiente(), total + 1)

    def test_fallo_a_mitad_hace_rollback_y_no_consume_numero(self):
        original = self.db._insertar_lineas

        def insertar_y_fallar(cursor, documento_id, lineas):
            original(cursor, documento_id, lineas[:1])   # ya hay cabecera y una linea escritas
            raise RuntimeError("fallo simulado a mitad de guardado")

        with mock.patch.object(self.db, "_insertar_lineas", insertar_y_fallar):
            with self.assertRaises(RuntimeError):
                self.db.guardar_documento(cabecera(self.empresa_id, self.cliente_id), LINEAS, asignar_numero=True)

        self.assertEqual(self.siguiente(), 1)
        self.assertEqual(self.db.contar("documentos"), 0)
        self.assertEqual(self.db.contar("documentos_lineas"), 0)
        doc_id = self.db.guardar_documento(cabecera(self.empresa_id, self.cliente_id), LINEAS, asignar_numero=True)
        self.assertEqual(self.db.obtener("documentos", doc_id)["numero"], "FAC-0001")

    def test_error_real_de_mysql_hace_rollback(self):
        # cantidad fuera de rango para DECIMAL(12,3): MySQL rechaza la 2a linea
        malas = [LINEAS[0], dict(LINEAS[1], cantidad=D("10") ** 12, precio_unitario=D("0"))]
        with self.assertRaises(self.db.DatabaseError):
            self.db.guardar_documento(cabecera(self.empresa_id, self.cliente_id), malas, asignar_numero=True)
        self.assertEqual(self.siguiente(), 1)
        self.assertEqual(self.db.contar("documentos"), 0)
        self.assertEqual(self.db.contar("documentos_lineas"), 0)

    def test_contador_bajado_a_mano_no_duplica(self):
        for _ in range(3):
            self.db.guardar_documento(cabecera(self.empresa_id, self.cliente_id), LINEAS, asignar_numero=True)
        self.db.actualizar("empresas", self.empresa_id, {"siguiente_factura": 2})
        doc_id = self.db.guardar_documento(cabecera(self.empresa_id, self.cliente_id), LINEAS, asignar_numero=True)
        self.assertEqual(self.db.obtener("documentos", doc_id)["numero"], "FAC-0004")
        self.assertEqual(self.siguiente(), 5)

    def test_pdf_desde_la_base_con_caracteres_especiales(self):
        from impresion import generar_pdf
        lineas = [dict(LINEAS[0], descripcion="Mármol & granito <pulido> 3/4\"")]
        cab = cabecera(self.empresa_id, self.cliente_id, porcentaje_irpf=D("15"), cliente_nombre="Obras & Co <SL>")
        doc_id = self.db.guardar_documento(cab, lineas, asignar_numero=True)
        fd, ruta = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            generar_pdf(doc_id, ruta)
            with open(ruta, "rb") as pdf:
                self.assertTrue(pdf.read(5).startswith(b"%PDF"))
        finally:
            os.remove(ruta)


if __name__ == "__main__":
    unittest.main()
