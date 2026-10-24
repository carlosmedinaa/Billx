import os
import sys
import tempfile
from datetime import datetime, timedelta
from PyQt6.QtCore import Qt, QDate, QSettings, QSize
from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QVBoxLayout, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QDateEdit,
    QMessageBox, QComboBox, QFileDialog, QLineEdit, QTextEdit,
    QDialogButtonBox
)

from calculos import CERO, a_decimal, calcular_documento, importe_linea
from database import (
    listar, obtener, guardar_documento, obtener_documento_completo,
    eliminar_documento
)
from ui_common import (
    DialogoFicha, PanelLista, campo_texto, campo_decimal, campo_combo,
    crear_boton, a_float, fmt_moneda, fmt_num, AZUL, ROJO, VERDE, MORADO
)
from impresion import generar_listado_pdf, generar_pdf
from visor_pdf import VistaPreviaPDF, leer_y_borrar
from email_sender import enviar_email
from errores import DatabaseError


class BuscadorClientesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buscar Cliente")
        self.resize(600, 450)
        self.cliente_seleccionado = None
        
        layout = QVBoxLayout(self)
        
        self.txt_filtro = QLineEdit(self)
        self.txt_filtro.setPlaceholderText("Escribe para buscar por código, nombre o NIF...")
        self.txt_filtro.textChanged.connect(self._cargar_datos)
        layout.addWidget(self.txt_filtro)
        
        self.tabla = QTableWidget(0, 3, self)
        self.tabla.setHorizontalHeaderLabels(["Código", "Nombre", "NIF"])
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabla.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabla.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabla.doubleClicked.connect(self._aceptar)
        layout.addWidget(self.tabla)
        
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Seleccionar")
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)
        
        self._cargar_datos("")

    def _cargar_datos(self, texto=""):
        self.tabla.setRowCount(0)
        clientes = listar(
            "clientes", 
            texto=texto, 
            campos_busqueda=("codigo", "nombre", "nif"), 
            condiciones=("activo = 1",), 
            orden="nombre ASC"
        )
        for cli in clientes:
            fila = self.tabla.rowCount()
            self.tabla.insertRow(fila)
            
            item_cod = QTableWidgetItem(str(cli.get("codigo", "")))
            item_nom = QTableWidgetItem(str(cli.get("nombre", "")))
            item_nif = QTableWidgetItem(str(cli.get("nif", "")))
            
            item_cod.setData(Qt.ItemDataRole.UserRole, cli)
            
            self.tabla.setItem(fila, 0, item_cod)
            self.tabla.setItem(fila, 1, item_nom)
            self.tabla.setItem(fila, 2, item_nif)

    def _aceptar(self):
        fila = self.tabla.currentRow()
        if fila >= 0:
            item = self.tabla.item(fila, 0)
            self.cliente_seleccionado = item.data(Qt.ItemDataRole.UserRole)
            self.accept()
        else:
            QMessageBox.warning(self, "Aviso", "Por favor, selecciona un cliente de la lista.")


def ajustes_usuario():
    """Preferencias guardadas en este PC (remitente del correo...).

    Las versiones anteriores las guardaban con otro nombre de aplicacion: si
    aun no hay nada con el nombre nuevo, se copian una vez para no perderlas.
    """
    ajustes = QSettings("Billx", "Billx")
    if not ajustes.contains("email_remitente"):
        anteriores = QSettings("MarmolesMedina", "GestionComercial")
        for clave in anteriores.allKeys():
            ajustes.setValue(clave, anteriores.value(clave))
    return ajustes


def texto_rgpd(empresa):
    """Clausula informativa RGPD del pie de los correos, con los datos de la empresa emisora."""
    nombre = empresa.get("nombre") or "la empresa"
    partes_direccion = [empresa.get("direccion"), empresa.get("cp"), empresa.get("ciudad")]
    direccion = ", ".join(str(p).strip() for p in partes_direccion if str(p or "").strip())
    if str(empresa.get("provincia") or "").strip():
        direccion += f" ({empresa['provincia']})"
    texto = (
        "De acuerdo con el Reglamento UE 2016/679 relativo a la protección de las personas físicas en lo "
        "que respecta al tratamiento de datos personales y a la libre circulación de estos datos (RGPD), le "
        "informamos que los datos de contacto utilizados para la presente comunicación están incluidos "
        "en un registro con la finalidad de posibilitar las comunicaciones a través de correo electrónico de "
        f"{nombre}, en los distintos contactos que mantiene dentro del ejercicio "
        "de su actividad (como clientes, asociados, proveedores o personal). La causa que legitima este "
        "tratamiento de datos es el consentimiento. Estos datos serán transmitidos a una entidad que "
        "presta el servicio de asesoramiento laboral, fiscal y contable. Los datos no serán transmitidos a "
        "terceros salvo autorización expresa u obligación legal. Los datos proporcionados se conservarán "
        "mientras se mantenga la relación profesional o durante los años necesarios para cumplir con las "
        "obligaciones legales.\n\n"
        "Sin perjuicio de ello se le informa de que usted podrá ejercitar los derechos de acceso, "
        "rectificación, supresión (derecho al olvido), limitación en el tratamiento, portabilidad y "
        "oposición"
    )
    if direccion:
        texto += f" para lo cual puede dirigirse a la siguiente dirección: {direccion}, adjuntando una fotocopia de su DNI"
    if empresa.get("email"):
        texto += f", o a través de la dirección de correo electrónico: {empresa['email']}"
    return texto + "."


class DialogoEmail(QDialog):
    def __init__(self, parent, doc, empresa, cliente, ruta_pdf):
        super().__init__(parent)
        
        # --- INICIAMOS LA MEMORIA DEL PROGRAMA ---
        self.settings = ajustes_usuario()
        
        tipo_doc = doc.get("tipo") or "documento"
        num_doc = doc.get("numero") or ""
        nom_emp = empresa.get("nombre") or ""
        nom_cli = cliente.get("nombre") or "Cliente"
        
        # Recuperamos el email y contraseña guardados en tu PC
        email_guardado = self.settings.value("email_remitente", empresa.get("email") or "")
        pass_guardada = self.settings.value("email_password", "")
        email_cli = cliente.get("email") or ""

        self.setWindowTitle(f"Enviar {tipo_doc.capitalize()} por Email")
        self.setMinimumWidth(600) # Un poco más ancho para que se lea bien el texto legal
        
        layout = QFormLayout(self)
        
        self.txt_de = QLineEdit(email_guardado)
        self.txt_pass = QLineEdit(pass_guardada)
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pass.setPlaceholderText("Ej: abcd efgh ijkl mnop")
        
        self.txt_para = QLineEdit(email_cli)
        
        asunto_def = f"{tipo_doc.capitalize()} {num_doc} - {nom_emp}"
        self.txt_asunto = QLineEdit(asunto_def)
        
        ley_rgpd = texto_rgpd(empresa)

        # --- CUERPO DEL CORREO FINAL ---
        cuerpo_def = (
            f"Hola {nom_cli},\n\n"
            f"Adjunto le enviamos su {tipo_doc} con número {num_doc}.\n\n"
            f"Quedamos a su entera disposición para cualquier consulta.\n\n"
            f"Un saludo,\n{nom_emp}\n\n"
            f"--------------------------------------------------\n\n"
            f"{ley_rgpd}"
        )
        
        self.txt_cuerpo = QTextEdit(cuerpo_def)
        self.txt_cuerpo.setMinimumHeight(250) # Hacemos la caja de texto más grande por defecto
        
        layout.addRow("De (Tu Email):", self.txt_de)
        layout.addRow("Contraseña:", self.txt_pass)
        layout.addRow("Para (Cliente):", self.txt_para)
        layout.addRow("Asunto:", self.txt_asunto)
        layout.addRow("Mensaje:", self.txt_cuerpo)
        
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Ok).setText("Enviar Email")
        botones.accepted.connect(self.accept)
        botones.rejected.connect(self.reject)
        layout.addRow(botones)
        
    def accept(self):
        # --- GUARDAMOS LOS DATOS AL DARLE A ENVIAR ---
        self.settings.setValue("email_remitente", self.txt_de.text().strip())
        self.settings.setValue("email_password", self.txt_pass.text().strip())
        super().accept()
        
    def datos(self):
        return {
            "remitente": self.txt_de.text().strip(),
            "password": self.txt_pass.text().strip(),
            "destinatario": self.txt_para.text().strip(),
            "asunto": self.txt_asunto.text().strip(),
            "cuerpo": self.txt_cuerpo.toPlainText()
        }


COL_ARTICULO, COL_DESCRIPCION, COL_CANTIDAD, COL_PRECIO, COL_DTO, COL_IVA, COL_IMPORTE = range(7)


class DialogoDocumento(DialogoFicha):
    ancho_minimo = 900

    def __init__(self, parent=None, registro=None, duplicar=False, tipo_doc="factura", fecha_de_hoy=False):
        self.tipo_doc = tipo_doc
        # Al convertir un presupuesto/albaran en factura, la factura se emite HOY
        self.fecha_de_hoy = fecha_de_hoy
        self.titulo_nuevo = f"Nuevo {self.tipo_doc.capitalize()}"
        self.titulo_editar = f"Editar {self.tipo_doc.capitalize()}"
        # Regimen fiscal del documento: sale del cliente (exento, recargo,
        # descuento habitual) y de la empresa (IRPF); al editar, del documento.
        self.exento_iva = False
        self.recargo_equivalencia = False
        self.porcentaje_irpf = CERO
        self.descuento_cliente = 0.0
        self.calculo = calcular_documento([])
        self._cargando = False
        super().__init__(parent, registro, duplicar)

    def tamano_inicial(self, pantalla):
        """Tamaño comodo para trabajar: hasta 1100 x 850, sin pasar del 85 % de la pantalla."""
        return QSize(min(1100, int(pantalla.width() * 0.85)), min(850, int(pantalla.height() * 0.85)))

    def construir(self, layout):
        panel_cabecera = QWidget()
        form_cabecera = QFormLayout(panel_cabecera)

        self.cmb_empresa = campo_combo()
        self.cmb_estado = campo_combo(("Borrador", "Emitida", "Pagada"))
        self.cmb_forma_pago = campo_combo(("Transferencia", "Contado", "Tarjeta", "Pagaré", "Recibo Domiciliado", "Efectivo"))

        estilo_combobox = """
            QComboBox {
                background-color: white;
                color: #1f2937;
                border: 1px solid #d1d5db;
                border-radius: 4px;
                padding: 4px;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                color: #1f2937;
                selection-background-color: #2563eb;
                selection-color: white;
            }
        """
        self.cmb_empresa.setStyleSheet(estilo_combobox)
        self.cmb_estado.setStyleSheet(estilo_combobox)
        self.cmb_forma_pago.setStyleSheet(estilo_combobox)

        self.cliente_id = None
        self.txt_cliente_info = QLineEdit()
        self.txt_cliente_info.setReadOnly(True)
        self.txt_cliente_info.setPlaceholderText("Ningún cliente seleccionado...")
        btn_buscar_cliente = crear_boton("🔍 Buscar Cliente", AZUL, self._abrir_buscador_cliente)

        layout_cliente = QHBoxLayout()
        layout_cliente.addWidget(self.txt_cliente_info, 1)
        layout_cliente.addWidget(btn_buscar_cliente)

        self.dt_fecha = QDateEdit()
        self.dt_fecha.setCalendarPopup(True)
        self.dt_fecha.setDate(datetime.now().date())

        self.dt_vencimiento = QDateEdit()
        self.dt_vencimiento.setCalendarPopup(True)
        self.dt_vencimiento.setDate(datetime.now().date())

        self.txt_numero = campo_texto("Se asignará al guardar", 20)
        self.txt_numero.setReadOnly(True)

        self.empresas_data = listar("empresas", condiciones=("activo = 1",))

        for emp in self.empresas_data:
            self.cmb_empresa.addItem(emp["nombre"], emp["id"])
        self.cmb_empresa.currentIndexChanged.connect(self._empresa_cambiada)

        form_cabecera.addRow("Empresa Emisora:", self.cmb_empresa)
        form_cabecera.addRow("Cliente:", layout_cliente)
        form_cabecera.addRow("Fecha Emisión:", self.dt_fecha)
        form_cabecera.addRow("Fecha Vencimiento:", self.dt_vencimiento)
        form_cabecera.addRow("Forma de Pago:", self.cmb_forma_pago)
        form_cabecera.addRow("Estado:", self.cmb_estado)
        form_cabecera.addRow("Número:", self.txt_numero)
        layout.addWidget(panel_cabecera)

        self.tabla_lineas = QTableWidget(0, 7)
        self.tabla_lineas.setHorizontalHeaderLabels(["Artículo", "Descripción", "Cantidad", "Precio", "Dto %", "IVA %", "Importe"])
        cabecera = self.tabla_lineas.horizontalHeader()
        cabecera.setSectionResizeMode(COL_DESCRIPCION, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.tabla_lineas, 1)

        botones_lineas = QHBoxLayout()
        btn_add = crear_boton("+ Añadir línea", AZUL, self._anadir_linea_vacia)
        btn_del = crear_boton("- Quitar línea", ROJO, self._quitar_linea)
        botones_lineas.addWidget(btn_add)
        botones_lineas.addWidget(btn_del)
        botones_lineas.addStretch()
        layout.addLayout(botones_lineas)

        panel_totales = QWidget()
        layout_totales = QVBoxLayout(panel_totales)
        layout_totales.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.lbl_regimen = QLabel()
        self.lbl_regimen.setStyleSheet("color: #7c3aed; font-weight: 600;")
        self.lbl_base = QLabel("Base Imponible: 0,00 €")
        self.lbl_iva = QLabel("Total IVA: 0,00 €")
        self.lbl_recargo = QLabel()
        self.lbl_retencion = QLabel()
        self.lbl_total = QLabel("TOTAL: 0,00 €")
        self.lbl_total.setStyleSheet("font-size: 18px; font-weight: bold; color: #2563eb;")

        layout_totales.addWidget(self.lbl_regimen)
        layout_totales.addWidget(self.lbl_base)
        layout_totales.addWidget(self.lbl_iva)
        layout_totales.addWidget(self.lbl_recargo)
        layout_totales.addWidget(self.lbl_retencion)
        layout_totales.addWidget(self.lbl_total)
        layout.addWidget(panel_totales)

        self.articulos_data = listar("articulos", condiciones=("activo = 1",))

    def _empresa_actual(self):
        empresa_id = self.cmb_empresa.currentData()
        return next((e for e in self.empresas_data if e["id"] == empresa_id), None)

    def _empresa_cambiada(self):
        if self._cargando:
            return
        empresa = self._empresa_actual()
        self.porcentaje_irpf = a_decimal(empresa.get("retencion_irpf")) if empresa else CERO
        self._calcular_totales()

    def _aplicar_regimen_cliente(self, cli):
        self.exento_iva = bool(cli.get("exento_iva"))
        self.recargo_equivalencia = bool(cli.get("recargo_equivalencia")) and not self.exento_iva
        nuevo_dto = a_float(cli.get("descuento"))
        # Las lineas que aun tienen el descuento habitual anterior pasan al del
        # nuevo cliente; las que el usuario cambio a mano se respetan.
        for fila in range(self.tabla_lineas.rowCount()):
            spn_dto = self.tabla_lineas.cellWidget(fila, COL_DTO)
            if spn_dto and abs(spn_dto.value() - self.descuento_cliente) < 0.005:
                spn_dto.setValue(nuevo_dto)
        self.descuento_cliente = nuevo_dto
        self._calcular_totales()

    def _seleccionar_forma_pago(self, texto):
        texto = (texto or "").strip()
        if not texto:
            return
        idx = self.cmb_forma_pago.findText(texto)
        if idx < 0:
            idx = self.cmb_forma_pago.findText(texto, Qt.MatchFlag.MatchContains)
        if idx < 0:
            # Valor que no esta en la lista (p. ej. "Confirming"): se anade para no perderlo
            self.cmb_forma_pago.addItem(texto)
            idx = self.cmb_forma_pago.count() - 1
        self.cmb_forma_pago.setCurrentIndex(idx)

    def _abrir_buscador_cliente(self):
        dialogo = BuscadorClientesDialog(self)
        if dialogo.exec() == QDialog.DialogCode.Accepted and dialogo.cliente_seleccionado:
            self._seleccionar_cliente(dialogo.cliente_seleccionado)

    def _seleccionar_cliente(self, cli):
        self.cliente_id = cli["id"]
        self.txt_cliente_info.setText(f"{cli['codigo']} - {cli['nombre']} (NIF: {cli.get('nif', '')})")

        # Cargar automáticamente la forma de pago sugerida del cliente
        self._seleccionar_forma_pago(cli.get("forma_pago", ""))

        # Calcular automáticamente la fecha de vencimiento según sus días de pago habituales
        try:
            dias = int(cli.get("dias_pago", 0) or 0)
        except (ValueError, TypeError):
            dias = 0

        fecha_emision = self.dt_fecha.date().toPyDate()
        fecha_calc = fecha_emision + timedelta(days=dias)
        self.dt_vencimiento.setDate(QDate(fecha_calc.year, fecha_calc.month, fecha_calc.day))

        self._aplicar_regimen_cliente(cli)

    def _anadir_linea_vacia(self):
        self._insertar_fila()

    def _insertar_fila(self, datos_linea=None):
        fila = self.tabla_lineas.rowCount()
        self.tabla_lineas.insertRow(fila)

        cmb_articulo = QComboBox()
        cmb_articulo.addItem("-- Seleccionar --", None)
        for art in self.articulos_data:
            cmb_articulo.addItem(art["referencia"], art)

        txt_desc = campo_texto("Descripción", 999999)
        spn_cant = campo_decimal(99999.99, 2)
        spn_cant.setValue(1.0)
        spn_precio = campo_decimal(999999.99, 2, " €")
        spn_dto = campo_decimal(100.0, 2, " %")
        spn_dto.setValue(self.descuento_cliente)
        cmb_iva = campo_combo(("21", "10", "4", "0"))

        lbl_sub = QLabel("0,00 €")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.tabla_lineas.setCellWidget(fila, COL_ARTICULO, cmb_articulo)
        self.tabla_lineas.setCellWidget(fila, COL_DESCRIPCION, txt_desc)
        self.tabla_lineas.setCellWidget(fila, COL_CANTIDAD, spn_cant)
        self.tabla_lineas.setCellWidget(fila, COL_PRECIO, spn_precio)
        self.tabla_lineas.setCellWidget(fila, COL_DTO, spn_dto)
        self.tabla_lineas.setCellWidget(fila, COL_IVA, cmb_iva)
        self.tabla_lineas.setCellWidget(fila, COL_IMPORTE, lbl_sub)

        spn_cant.valueChanged.connect(self._calcular_totales)
        spn_precio.valueChanged.connect(self._calcular_totales)
        spn_dto.valueChanged.connect(self._calcular_totales)
        cmb_iva.currentTextChanged.connect(self._calcular_totales)

        def on_articulo_changed():
            art = cmb_articulo.currentData()
            if art:
                txt_desc.setText(art["descripcion"])
                spn_precio.setValue(a_float(art["precio_venta"]))
                cmb_iva.setCurrentText(str(int(a_float(art["iva"]))))
                self._calcular_totales()

        cmb_articulo.currentIndexChanged.connect(on_articulo_changed)

        if datos_linea:
            idx = cmb_articulo.findText(datos_linea.get("referencia", ""))
            if idx >= 0: cmb_articulo.setCurrentIndex(idx)
            txt_desc.setText(datos_linea.get("descripcion", ""))
            spn_cant.setValue(a_float(datos_linea.get("cantidad", 1)))
            spn_precio.setValue(a_float(datos_linea.get("precio_unitario", 0)))
            spn_dto.setValue(a_float(datos_linea.get("porcentaje_descuento", 0)))
            cmb_iva.setCurrentText(str(int(a_float(datos_linea.get("porcentaje_iva", 21)))))

        self._calcular_totales()

    def _quitar_linea(self):
        fila = self.tabla_lineas.currentRow()
        if fila >= 0:
            self.tabla_lineas.removeRow(fila)
            self._calcular_totales()

    def _lineas_pantalla(self):
        """Una linea por fila de la tabla, con los valores tal cual estan en pantalla."""
        lineas = []
        for fila in range(self.tabla_lineas.rowCount()):
            art_data = self.tabla_lineas.cellWidget(fila, COL_ARTICULO).currentData()
            lineas.append({
                "articulo_id": art_data["id"] if art_data else 0,
                "referencia": art_data["referencia"] if art_data else "",
                "descripcion": self.tabla_lineas.cellWidget(fila, COL_DESCRIPCION).text().strip(),
                "cantidad": a_decimal(self.tabla_lineas.cellWidget(fila, COL_CANTIDAD).value()),
                "precio_unitario": a_decimal(self.tabla_lineas.cellWidget(fila, COL_PRECIO).value()),
                "porcentaje_descuento": a_decimal(self.tabla_lineas.cellWidget(fila, COL_DTO).value()),
                "porcentaje_iva": a_decimal(self.tabla_lineas.cellWidget(fila, COL_IVA).currentText()),
            })
        return lineas

    def _calcular_totales(self):
        # Mientras se construye una fila no estan todas sus celdas: se recalcula al final
        if any(self.tabla_lineas.cellWidget(f, COL_IMPORTE) is None
               for f in range(self.tabla_lineas.rowCount())):
            return
        self.calculo = calcular_documento(
            self._lineas_pantalla(), self.exento_iva, self.recargo_equivalencia, self.porcentaje_irpf
        )
        for fila, linea in enumerate(self.calculo["lineas"]):
            self.tabla_lineas.cellWidget(fila, COL_IMPORTE).setText(fmt_moneda(linea["importe"]))

        if self.exento_iva:
            regimen = "Cliente exento de IVA"
        elif self.recargo_equivalencia:
            regimen = "Cliente en recargo de equivalencia"
        else:
            regimen = ""
        self.lbl_regimen.setText(regimen)
        self.lbl_regimen.setVisible(bool(regimen))

        self.lbl_base.setText(f"Base Imponible: {fmt_moneda(self.calculo['base_imponible'])}")
        self.lbl_iva.setText(f"Total IVA: {fmt_moneda(self.calculo['total_iva'])}")
        self.lbl_recargo.setText(f"Recargo de equivalencia: {fmt_moneda(self.calculo['total_recargo'])}")
        self.lbl_recargo.setVisible(self.calculo["total_recargo"] > 0)
        self.lbl_retencion.setText(
            f"Retención IRPF ({fmt_num(self.calculo['porcentaje_irpf'])} %): "
            f"-{fmt_moneda(self.calculo['total_retencion'])}"
        )
        self.lbl_retencion.setVisible(self.calculo["total_retencion"] > 0)
        self.lbl_total.setText(f"TOTAL: {fmt_moneda(self.calculo['total'])}")

    def cargar(self, registro):
        if not registro:
            for i, emp in enumerate(self.empresas_data):
                if emp.get("predeterminada"):
                    self.cmb_empresa.setCurrentIndex(i)
                    break
            self._empresa_cambiada()
            self._anadir_linea_vacia()
            return

        self._cargando = True
        try:
            cli = self._cargar_cabecera(registro)
            for linea in registro.get("lineas", []):
                self._insertar_fila(linea)
        finally:
            self._cargando = False

        if self.duplicar:
            # Documento nuevo: regimen fiscal ACTUAL del cliente y de la empresa
            self.txt_numero.clear()   # se ve el texto de ayuda "Se asignará al guardar"
            self._empresa_cambiada()
            if self.fecha_de_hoy:
                hoy = datetime.now().date()
                dias = int(a_float(cli.get("dias_pago"))) if cli else 0
                self.dt_fecha.setDate(hoy)
                self.dt_vencimiento.setDate(hoy + timedelta(days=dias))
            if cli:
                self.exento_iva = bool(cli.get("exento_iva"))
                self.recargo_equivalencia = bool(cli.get("recargo_equivalencia")) and not self.exento_iva
        else:
            # Documento existente: se respeta el regimen con el que se emitio
            self.exento_iva = bool(int(registro.get("exento_iva") or 0))
            self.recargo_equivalencia = bool(int(registro.get("recargo_equivalencia") or 0))
            self.porcentaje_irpf = a_decimal(registro.get("porcentaje_irpf"))
            # Con varias ventanas abiertas, el titulo dice cual es cual
            self.setWindowTitle(f"{self.titulo_editar} {registro.get('numero', '')} – {registro.get('cliente_nombre', '')}")
        if cli:
            self.descuento_cliente = a_float(cli.get("descuento"))
        self._calcular_totales()

    def _cargar_cabecera(self, registro):
        """Rellena la cabecera desde el documento. Devuelve la ficha viva del cliente o None."""
        self.txt_numero.setText(registro.get("numero", ""))

        try:
            fecha_dt = datetime.strptime(registro.get("fecha", ""), "%Y-%m-%d")
            self.dt_fecha.setDate(fecha_dt.date())
        except ValueError:
            pass

        try:
            venc_str = registro.get("fecha_vencimiento", "")
            if venc_str:
                venc_dt = datetime.strptime(venc_str, "%Y-%m-%d")
                self.dt_vencimiento.setDate(venc_dt.date())
            else:
                self.dt_vencimiento.setDate(self.dt_fecha.date())
        except ValueError:
            pass

        self._seleccionar_forma_pago(registro.get("forma_pago"))

        estado = registro.get("estado", "Emitida" if self.tipo_doc == "factura" else "Borrador")
        self.cmb_estado.setCurrentText(estado)

        idx_emp = self.cmb_empresa.findData(registro.get("empresa_id"))
        if idx_emp >= 0: self.cmb_empresa.setCurrentIndex(idx_emp)

        # --- CARGAR EL CLIENTE GUARDADO (A prueba de fallos) ---
        self.cliente_id = registro.get("cliente_id")
        cli = None

        # 1. Intentamos buscar la ficha viva del cliente
        if self.cliente_id:
            try:
                cli = obtener("clientes", self.cliente_id)
            except DatabaseError:
                cli = None
        if cli:
            self.txt_cliente_info.setText(f"{cli.get('codigo', '')} - {cli.get('nombre', '')} (NIF: {cli.get('nif', '')})")
        else:
            # 2. Si falla (factura antigua o cliente borrado), rescatamos el texto guardado en la factura
            nombre = registro.get("cliente_nombre", "Cliente Desconocido")
            nif = registro.get("cliente_nif", "")
            self.txt_cliente_info.setText(f"{nombre} (NIF: {nif})")
        return cli

    def guardar(self):
        empresa_id = self.cmb_empresa.currentData()
        cliente_id = self.cliente_id

        if not empresa_id or not cliente_id:
            return self.aviso("Debes seleccionar una empresa y un cliente.")

        lineas = []
        for fila, linea in enumerate(self._lineas_pantalla(), start=1):
            if linea["descripcion"]:
                lineas.append(linea)
            elif importe_linea(linea["cantidad"], linea["precio_unitario"], linea["porcentaje_descuento"]):
                # Sin esto se guardaria un total distinto del que se ve en pantalla
                return self.aviso(f"La línea {fila} tiene importe pero no tiene descripción.")
        if not lineas:
            return self.aviso("El documento debe tener al menos una línea con descripción.")

        cliente = obtener("clientes", cliente_id)
        if not cliente:
            if not self.registro_id:
                return self.aviso("El cliente seleccionado ya no existe.")
            # Editando un documento cuyo cliente se borro: se conservan los datos guardados
            cliente = {k: self.registro.get("cliente_" + k, "")
                       for k in ("nombre", "nif", "direccion", "cp", "ciudad", "provincia", "pais")}

        nuevo = self.registro_id is None   # nuevo o duplicado (DialogoFicha deja None al duplicar)
        cabecera = {
            "tipo": self.tipo_doc,
            "numero": "" if nuevo else self.txt_numero.text(),
            "fecha": self.dt_fecha.date().toString("yyyy-MM-dd"),
            "fecha_vencimiento": self.dt_vencimiento.date().toString("yyyy-MM-dd"),
            "forma_pago": self.cmb_forma_pago.currentText().strip(),
            "empresa_id": empresa_id,
            "cliente_id": cliente_id,
            "cliente_nombre": cliente.get("nombre", ""),
            "cliente_nif": cliente.get("nif", ""),
            "cliente_direccion": cliente.get("direccion", ""),
            "cliente_cp": cliente.get("cp", ""),
            "cliente_ciudad": cliente.get("ciudad", ""),
            "cliente_provincia": cliente.get("provincia", ""),
            "cliente_pais": cliente.get("pais", ""),
            "exento_iva": 1 if self.exento_iva else 0,
            "recargo_equivalencia": 1 if self.recargo_equivalencia else 0,
            "porcentaje_irpf": self.porcentaje_irpf,
            "estado": self.cmb_estado.currentText()
        }

        # Los importes los recalcula guardar_documento con calculos.calcular_documento,
        # la misma funcion que pinta los totales de esta pantalla.
        self.documento_guardado_id = guardar_documento(
            cabecera, lineas, self.registro_id, asignar_numero=nuevo
        )
        return True


# Fichas de documento y vistas previas abiertas. Son ventanas independientes (sin
# padre): cada una tiene su boton en la barra de tareas de Windows. Estas listas
# mantienen viva la referencia de Python mientras la ventana esta abierta.
VENTANAS_ABIERTAS = []
VISORES_ABIERTOS = []
PASO_CASCADA = 32


def ventanas_documento_abiertas():
    return list(VENTANAS_ABIERTAS)


def cerrar_ventanas_independientes():
    """Al salir del programa: cierra fichas y vistas previas (si no, Qt no termina)."""
    for ventana in list(VENTANAS_ABIERTAS) + list(VISORES_ABIERTOS):
        ventana.close()


def mostrar_ventana_independiente(ventana, lista, referencia):
    """Muestra la ventana desplazada respecto a las ya abiertas (en cascada). Si
    salieran todas en el mismo sitio, la ultima taparia a las demas y pareceria
    que solo hay una."""
    ventana.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    ventana.setWindowFlags(ventana.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
    ventana.setWindowModality(Qt.WindowModality.NonModal)

    principal = referencia.window()
    pantalla = principal.screen().availableGeometry() if principal.screen() else None
    # Cada clase decide su tamaño segun la pantalla; adjustSize() la dejaria en el minimo
    if pantalla is not None and hasattr(ventana, "tamano_inicial"):
        ventana.resize(ventana.tamano_inicial(pantalla))
    escalon = PASO_CASCADA * ((len(VENTANAS_ABIERTAS) + len(VISORES_ABIERTOS)) % 8)
    x = principal.frameGeometry().x() + 60 + escalon
    y = principal.frameGeometry().y() + 40 + escalon
    if pantalla is not None:
        x = max(pantalla.left(), min(x, pantalla.right() - ventana.width()))
        y = max(pantalla.top(), min(y, pantalla.bottom() - ventana.height()))
    ventana.move(x, y)

    lista.append(ventana)
    ventana.destroyed.connect(lambda _obj=None, v=ventana: lista.remove(v) if v in lista else None)
    ventana.show()
    ventana.raise_()
    ventana.activateWindow()


class DocumentosWidget(PanelLista):
    columna_expandible = 2
    columnas = (
        ("Número", "numero", "texto"),
        ("Fecha", "fecha", "texto"),
        ("Cliente", "cliente_nombre", "texto"),
        ("Base", "base_imponible", "moneda"),
        ("IVA", "total_iva", "moneda"),
        ("Total", "total", "moneda"),
        ("Estado", "estado", "texto"),
    )

    def __init__(self, tipo_doc="factura", parent=None):
        self.tipo_doc = tipo_doc
        self.titulo = f"{self.tipo_doc.capitalize()}s"
        self.subtitulo = f"Gestión de {self.tipo_doc}s emitidas."
        self.placeholder_busqueda = "Buscar por número o cliente..."
        self.nombre_exportacion = f"{self.tipo_doc}s"
        super().__init__(parent)

        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item.layout() and item.layout().indexOf(self.btn_nuevo) != -1:
                if self.tipo_doc in ["presupuesto", "albaran"]:
                    self.btn_facturar = crear_boton("Convertir a Factura", VERDE, self._convertir_a_factura)
                    item.layout().insertWidget(2, self.btn_facturar)
                
                # --- NUEVO BOTÓN DE PREVISUALIZAR ---
                self.btn_previsualizar = crear_boton("👁️ Previsualizar", "#4b5563", self._previsualizar_pdf)
                item.layout().insertWidget(3, self.btn_previsualizar)
                
                self.btn_pdf = crear_boton("Exportar PDF", AZUL, self._generar_pdf)
                item.layout().insertWidget(4, self.btn_pdf)
                
                self.btn_email = crear_boton("Enviar por Email", MORADO, self._preparar_email)
                item.layout().insertWidget(5, self.btn_email)
                
                # --- NUEVO BOTÓN EXPORTAR TRIMESTRE ---
                self.btn_trimestre = crear_boton("📅 Listado Trimestre (PDF)", "#059669", self._exportar_trimestre)
                item.layout().insertWidget(6, self.btn_trimestre)
                
                break  
            

    def listar(self, texto):
        return listar(
            "documentos", 
            texto=texto, 
            campos_busqueda=("numero", "cliente_nombre", "cliente_nif", "fecha"), 
            condiciones=("tipo = ?",), 
            params=(self.tipo_doc,), 
            orden="fecha DESC, numero DESC"
        )

    def obtener(self, registro_id):
        return obtener_documento_completo(registro_id)

    def abrir_ficha(self, registro=None, duplicar=False):
        self._abrir_ventana(registro, duplicar)
        return False   # no hay que esperar: la lista se recarga cuando la ventana guarda

    def _abrir_ventana(self, registro=None, duplicar=False, tipo_doc=None, fecha_de_hoy=False, al_guardar=None):
        """Abre la ficha como ventana independiente (no modal), sin bloquear el resto."""
        registro_id = None if duplicar else (registro or {}).get("id")
        if registro_id:
            # Dos ventanas editando el mismo documento se pisarian: se trae la que ya hay
            for ventana in VENTANAS_ABIERTAS:
                if ventana.registro_id == registro_id:
                    ventana.showNormal()
                    ventana.raise_()
                    ventana.activateWindow()
                    return ventana
        # Sin padre: ventana propia en la barra de tareas, no queda pegada encima de la principal
        dialogo = DialogoDocumento(None, registro=registro, duplicar=duplicar,
                                   tipo_doc=tipo_doc or self.tipo_doc, fecha_de_hoy=fecha_de_hoy)
        dialogo.accepted.connect(self.cargar)
        if al_guardar is not None:
            dialogo.accepted.connect(al_guardar)
        # Al cerrar (guardar o cancelar) deja de contar como abierta en el acto
        dialogo.finished.connect(lambda _resultado, d=dialogo: VENTANAS_ABIERTAS.remove(d) if d in VENTANAS_ABIERTAS else None)
        mostrar_ventana_independiente(dialogo, VENTANAS_ABIERTAS, self)
        return dialogo

    def borrar(self, registro_id):
        if any(v.registro_id == registro_id for v in VENTANAS_ABIERTAS):
            raise DatabaseError("Este documento está abierto en otra ventana. Ciérrala antes de eliminarlo.")
        return eliminar_documento(registro_id)

    def _actualizar_acciones(self):
        super()._actualizar_acciones()
        hay = self.seleccion_id() is not None
        if hasattr(self, 'btn_facturar'):
            self.btn_facturar.setEnabled(hay)
        if hasattr(self, 'btn_previsualizar'):
            self.btn_previsualizar.setEnabled(hay)
        if hasattr(self, 'btn_pdf'):
            self.btn_pdf.setEnabled(hay)
        if hasattr(self, 'btn_email'):
            self.btn_email.setEnabled(hay)

    def _convertir_a_factura(self):
        registro = self._registro_actual()
        if not registro: return

        respuesta = QMessageBox.question(
            self, "Convertir a Factura", 
            f"¿Deseas generar una factura a partir de este {self.tipo_doc}?\nSe abrirá el borrador de la factura.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if respuesta == QMessageBox.StandardButton.Yes:
            self._abrir_ventana(
                registro, duplicar=True, tipo_doc="factura", fecha_de_hoy=True,
                al_guardar=lambda: QMessageBox.information(
                    self, "Éxito", "Factura generada correctamente. Ve a la pestaña de Facturas para verla."),
            )

    def _generar_pdf(self):
        registro_id = self.seleccion_id()
        if not registro_id: return
        
        doc = self.obtener(registro_id)
        if not doc: return
        sugerencia = f"{doc.get('tipo', 'documento')}_{doc.get('numero', 'SN')}.pdf"
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar PDF", os.path.join(os.path.expanduser("~"), sugerencia), "Archivos PDF (*.pdf)")
        
        if ruta:
            try:
                generar_pdf(registro_id, ruta)
                QMessageBox.information(self, "Éxito", f"PDF generado correctamente en:\n{ruta}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo generar el PDF:\n{str(e)}")

    def _previsualizar_pdf(self):
        registro_id = self.seleccion_id()
        if not registro_id: return
        
        doc = self.obtener(registro_id)
        if not doc: return

        # "/" o "\" en el numero no valen en un nombre de archivo de Windows
        numero_limpio = doc.get('numero', 'SN').replace('/', '-').replace('\\', '-')
        fd, ruta_temp = tempfile.mkstemp(suffix=".pdf", prefix="billx_")
        os.close(fd)
        try:
            generar_pdf(registro_id, ruta_temp)
        except Exception as e:
            try:
                os.remove(ruta_temp)   # temporal a medio escribir
            except OSError:
                pass
            QMessageBox.critical(self, "Error", f"No se pudo previsualizar el PDF:\n{e}")
            return
        datos = leer_y_borrar(ruta_temp)

        # Visor dentro de la app (ventana no modal: se pueden ver varios a la vez)
        visor = VistaPreviaPDF(
            datos,
            titulo=f"{doc.get('tipo', 'documento').capitalize()} {doc.get('numero', '')} – {doc.get('cliente_nombre', '')}",
            nombre_sugerido=f"{doc.get('tipo', 'documento')}_{numero_limpio}.pdf",
        )
        mostrar_ventana_independiente(visor, VISORES_ABIERTOS, self)

    def _exportar_trimestre(self):
        dialogo = DialogoExportarFechas(self, self.tipo_doc)  # <--- Solo hay que añadir "_doc" aquí
        dialogo.exec()

    

    def _preparar_email(self):
        registro_id = self.seleccion_id()
        if not registro_id: return
        
        doc = self.obtener(registro_id)
        if not doc:
            QMessageBox.warning(self, "Aviso", "No se ha podido cargar el documento seleccionado.")
            return
        
        empresa = obtener("empresas", doc.get("empresa_id")) or {}
        cliente = obtener("clientes", doc.get("cliente_id")) or {}
        
        fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        
        try:
            generar_pdf(registro_id, temp_path)
            
            dialogo = DialogoEmail(self, doc, empresa, cliente, temp_path)
            if dialogo.exec() == QDialog.DialogCode.Accepted:
                datos = dialogo.datos()
                if not datos["remitente"] or not datos["password"] or not datos["destinatario"]:
                    QMessageBox.warning(self, "Error", "Faltan campos obligatorios (Email, contraseña o destinatario).")
                    return
                
                try:
                    enviar_email(
                        datos["remitente"], 
                        datos["password"], 
                        datos["destinatario"], 
                        datos["asunto"], 
                        datos["cuerpo"], 
                        temp_path
                    )
                    QMessageBox.information(self, "Éxito", "El correo se ha enviado correctamente al cliente.")
                except Exception as e:
                    QMessageBox.critical(self, "Error al enviar", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo preparar el correo:\n{str(e)}")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass


from PyQt6.QtWidgets import QPushButton


def trimestre_de(fecha):
    """(inicio, fin) del trimestre natural que contiene la fecha (datetime.date)."""
    mes_inicio = 3 * ((fecha.month - 1) // 3) + 1
    inicio = fecha.replace(month=mes_inicio, day=1)
    siguiente = inicio.replace(year=inicio.year + 1, month=1) if mes_inicio == 10 else inicio.replace(month=mes_inicio + 3)
    return inicio, siguiente - timedelta(days=1)


class DialogoExportarFechas(QDialog):
    """Exporta UN PDF con el listado de documentos de un periodo (no un PDF por documento)."""

    def __init__(self, parent=None, tipo_doc="factura"):
        super().__init__(parent)
        self.tipo_doc = tipo_doc
        self.setWindowTitle(f"Listado de {tipo_doc}s en PDF")
        self.setMinimumWidth(380)
        self.construir()

    def construir(self):
        layout = QVBoxLayout(self)

        # Trimestres del año actual y del anterior; por defecto, el último trimestre cerrado
        self.cmb_trimestre = QComboBox()
        hoy = datetime.now().date()
        for anio in (hoy.year, hoy.year - 1):
            for t in range(4, 0, -1):
                inicio = datetime(anio, 3 * t - 2, 1).date()
                if inicio <= hoy:
                    self.cmb_trimestre.addItem(f"{t}º trimestre {anio}", trimestre_de(inicio))
        self.cmb_trimestre.addItem("Fechas a mano", None)

        self.dt_inicio = QDateEdit()
        self.dt_inicio.setCalendarPopup(True)
        self.dt_inicio.setDisplayFormat("dd/MM/yyyy")
        self.dt_fin = QDateEdit()
        self.dt_fin.setCalendarPopup(True)
        self.dt_fin.setDisplayFormat("dd/MM/yyyy")

        layout_fechas = QHBoxLayout()
        layout_fechas.addWidget(QLabel("Desde:"))
        layout_fechas.addWidget(self.dt_inicio)
        layout_fechas.addWidget(QLabel("Hasta:"))
        layout_fechas.addWidget(self.dt_fin)

        layout.addWidget(QLabel(f"Se generará un único PDF con el listado de {self.tipo_doc}s y sus totales."))
        layout.addWidget(self.cmb_trimestre)
        layout.addLayout(layout_fechas)

        self.cmb_trimestre.currentIndexChanged.connect(self._trimestre_elegido)
        self.dt_inicio.dateChanged.connect(self._fecha_a_mano)
        self.dt_fin.dateChanged.connect(self._fecha_a_mano)
        cerrado = trimestre_de(trimestre_de(hoy)[0] - timedelta(days=1))
        idx = self.cmb_trimestre.findData(cerrado)
        self.cmb_trimestre.setCurrentIndex(max(idx, 0))
        self._trimestre_elegido()

        btn_exportar = QPushButton("📄 Guardar listado PDF")
        btn_exportar.setStyleSheet("background-color: #0b7285; color: white; padding: 8px; font-weight: bold;")
        btn_exportar.clicked.connect(self.exportar)
        layout.addWidget(btn_exportar)

    def _trimestre_elegido(self):
        periodo = self.cmb_trimestre.currentData()
        if not periodo:
            return
        self._poniendo_fechas = True
        self.dt_inicio.setDate(periodo[0])
        self.dt_fin.setDate(periodo[1])
        self._poniendo_fechas = False

    def _fecha_a_mano(self):
        if getattr(self, "_poniendo_fechas", False):
            return
        # Si el usuario toca las fechas, el combo pasa a "Fechas a mano"
        self.cmb_trimestre.blockSignals(True)
        self.cmb_trimestre.setCurrentIndex(self.cmb_trimestre.count() - 1)
        self.cmb_trimestre.blockSignals(False)

    def exportar(self):
        fecha_inicio = self.dt_inicio.date().toString("yyyy-MM-dd")
        fecha_fin = self.dt_fin.date().toString("yyyy-MM-dd")
        if fecha_inicio > fecha_fin:
            QMessageBox.warning(self, "Revisa las fechas", "La fecha 'Desde' es posterior a 'Hasta'.")
            return

        try:
            filas = listar(
                "documentos",
                condiciones=("tipo = ?", "fecha >= ?", "fecha <= ?"),
                params=(self.tipo_doc, fecha_inicio, fecha_fin),
                orden="fecha ASC, numero ASC",
            )
        except DatabaseError as e:
            QMessageBox.critical(self, "Error", f"No se pudieron leer los documentos:\n{e}")
            return
        if not filas:
            QMessageBox.warning(self, "Aviso", f"No hay {self.tipo_doc}s en ese rango de fechas.")
            return

        sugerencia = f"Listado_{self.tipo_doc}s_{fecha_inicio}_a_{fecha_fin}.pdf"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar listado PDF", os.path.join(os.path.expanduser("~"), sugerencia), "Archivos PDF (*.pdf)"
        )
        if not ruta:
            return
        if not ruta.lower().endswith(".pdf"):
            ruta += ".pdf"

        try:
            generar_listado_pdf(filas, ruta, self.tipo_doc, fecha_inicio, fecha_fin)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Error", f"Fallo al generar el listado:\n{e}")
            return
        QMessageBox.information(self, "Éxito", f"Listado de {len(filas)} {self.tipo_doc}(s) guardado en:\n{ruta}")
        self.accept()
