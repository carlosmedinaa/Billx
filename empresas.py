import os
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtWidgets import (
    QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget, QTableWidgetItem
)
from database import listar, obtener, insertar, actualizar, eliminar, existe_valor, marcar_empresa_predeterminada, formatear_numero
from ui_common import DialogoFicha, PanelLista, campo_texto, campo_decimal, campo_entero, checkbox, crear_boton, a_float, AZUL, GRIS

EXTENSIONES_LOGO = "Imagenes (*.png *.jpg *.jpeg *.bmp);;Todos los archivos (*.*)"

class DialogoEmpresa(DialogoFicha):
    titulo_nuevo = "Nueva empresa emisora"
    titulo_editar = "Editar empresa emisora"
    ancho_minimo = 620

    def construir(self, layout):
        pestanas = QTabWidget()
        pestanas.addTab(self._pestana_fiscal(), "Datos fiscales")
        pestanas.addTab(self._pestana_contacto(), "Contacto y banco")
        pestanas.addTab(self._pestana_numeracion(), "Numeracion y logo")
        layout.addWidget(pestanas)

    def _pestana_fiscal(self):
        pagina = QWidget()
        formulario = QFormLayout(pagina)
        formulario.setSpacing(10)
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_nombre = campo_texto("Razon social completa", 150)
        self.txt_comercial = campo_texto("Nombre comercial (opcional)", 150)
        self.txt_nif = campo_texto("Ej: B12345678", 20)
        self.txt_direccion = campo_texto("Calle, numero, piso", 200)
        self.txt_cp = campo_texto("28001", 10)
        self.txt_ciudad = campo_texto("Poblacion", 100)
        self.txt_provincia = campo_texto("Provincia", 100)
        self.txt_pais = campo_texto("Pais", 60)
        self.txt_pais.setText("España")
        self.chk_activa = checkbox("Empresa activa", True)
        self.chk_predeterminada = checkbox("Usar como empresa predeterminada")

        formulario.addRow("Razon social *", self.txt_nombre)
        formulario.addRow("Nombre comercial", self.txt_comercial)
        formulario.addRow("NIF / CIF *", self.txt_nif)
        formulario.addRow("Direccion", self.txt_direccion)
        formulario.addRow("Codigo postal", self.txt_cp)
        formulario.addRow("Ciudad", self.txt_ciudad)
        formulario.addRow("Provincia", self.txt_provincia)
        formulario.addRow("Pais", self.txt_pais)
        formulario.addRow(self.chk_activa)
        formulario.addRow(self.chk_predeterminada)
        return pagina

    def _pestana_contacto(self):
        pagina = QWidget()
        formulario = QFormLayout(pagina)
        formulario.setSpacing(10)
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_telefono = campo_texto("+34 600 000 000", 30)
        self.txt_email = campo_texto("facturacion@empresa.com", 120)
        self.txt_web = campo_texto("www.empresa.com", 120)
        self.txt_iban = campo_texto("ES00 0000 0000 0000 0000 0000", 34)
        self.spn_irpf = campo_decimal(maximo=100.0, sufijo=" %")
        self.txt_pie = QTextEdit()
        self.txt_pie.setMaximumHeight(90)

        formulario.addRow("Telefono", self.txt_telefono)
        formulario.addRow("Email", self.txt_email)
        formulario.addRow("Web", self.txt_web)
        formulario.addRow("IBAN", self.txt_iban)
        formulario.addRow("Retencion IRPF", self.spn_irpf)
        formulario.addRow("Pie de documento", self.txt_pie)
        return pagina

    def _pestana_numeracion(self):
        pagina = QWidget()
        contenedor = QVBoxLayout(pagina)
        formulario = QFormLayout()
        formulario.setSpacing(10)
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_serie_fac = campo_texto("FAC-", 10)
        self.txt_serie_fac.setText("FAC-")
        self.txt_serie_pre = campo_texto("PRE-", 10)
        self.txt_serie_pre.setText("PRE-")
        self.txt_serie_alb = campo_texto("ALB-", 10)
        self.txt_serie_alb.setText("ALB-")
        self.spn_num_fac = campo_entero(999999)
        self.spn_num_fac.setValue(1)
        self.spn_num_pre = campo_entero(999999)
        self.spn_num_pre.setValue(1)
        self.spn_num_alb = campo_entero(999999)
        self.spn_num_alb.setValue(1)

        formulario.addRow("Serie de facturas", self.txt_serie_fac)
        formulario.addRow("Siguiente factura", self.spn_num_fac)
        formulario.addRow("Serie de presupuestos", self.txt_serie_pre)
        formulario.addRow("Siguiente presupuesto", self.spn_num_pre)
        formulario.addRow("Serie de albaranes", self.txt_serie_alb)
        formulario.addRow("Siguiente albaran", self.spn_num_alb)
        contenedor.addLayout(formulario)

        self.lbl_ejemplo = QLabel()
        self.lbl_ejemplo.setStyleSheet("color: #2563eb; font-weight: 600;")
        contenedor.addWidget(self.lbl_ejemplo)

        fila_logo = QHBoxLayout()
        self.lbl_logo = QLabel("Sin logo")
        self.lbl_logo.setFixedSize(160, 90)
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_logo.setStyleSheet("border: 1px dashed #d1d5db; border-radius: 6px; color: #9ca3af;")
        fila_logo.addWidget(self.lbl_logo)
        columna_botones = QVBoxLayout()
        columna_botones.addWidget(crear_boton("Seleccionar logo", GRIS, self._elegir_logo))
        columna_botones.addWidget(crear_boton("Quitar logo", "#9ca3af", self._quitar_logo))
        columna_botones.addStretch(1)
        fila_logo.addLayout(columna_botones)
        fila_logo.addStretch(1)
        contenedor.addLayout(fila_logo)
        contenedor.addStretch(1)

        self.ruta_logo = ""
        for widget in (self.txt_serie_fac, self.txt_serie_pre, self.txt_serie_alb):
            widget.textChanged.connect(self._actualizar_ejemplo)
        for widget in (self.spn_num_fac, self.spn_num_pre, self.spn_num_alb):
            widget.valueChanged.connect(self._actualizar_ejemplo)
        self._actualizar_ejemplo()
        return pagina

    def _actualizar_ejemplo(self):
        ejemplos = " \u2022 ".join((
            formatear_numero(self.txt_serie_fac.text(), self.spn_num_fac.value()),
            formatear_numero(self.txt_serie_pre.text(), self.spn_num_pre.value()),
            formatear_numero(self.txt_serie_alb.text(), self.spn_num_alb.value()),
        ))
        self.lbl_ejemplo.setText("Proximos numeros: " + ejemplos)

    def _elegir_logo(self):
        ruta, _ = QFileDialog.getOpenFileName(self, "Seleccionar logo", os.path.expanduser("~"), EXTENSIONES_LOGO)
        if not ruta or QPixmap(ruta).isNull():
            return
        self.ruta_logo = ruta
        self._mostrar_logo()

    def _quitar_logo(self):
        self.ruta_logo = ""
        self._mostrar_logo()

    def _mostrar_logo(self):
        if not self.ruta_logo or not os.path.isfile(self.ruta_logo):
            self.lbl_logo.setPixmap(QPixmap())
            self.lbl_logo.setText("Sin logo" if not self.ruta_logo else "No encontrado")
            return
        imagen = QPixmap(self.ruta_logo)
        self.lbl_logo.setText("")
        self.lbl_logo.setPixmap(imagen.scaled(self.lbl_logo.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def cargar(self, registro):
        if not registro:
            return
        self.txt_nombre.setText(str(registro.get("nombre") or ""))
        self.txt_comercial.setText(str(registro.get("nombre_comercial") or ""))
        self.txt_nif.setText(str(registro.get("nif") or ""))
        self.txt_direccion.setText(str(registro.get("direccion") or ""))
        self.txt_cp.setText(str(registro.get("cp") or ""))
        self.txt_ciudad.setText(str(registro.get("ciudad") or ""))
        self.txt_provincia.setText(str(registro.get("provincia") or ""))
        self.txt_pais.setText(str(registro.get("pais") or "España"))
        self.chk_activa.setChecked(bool(registro.get("activo", 1)))
        self.chk_predeterminada.setChecked(bool(registro.get("predeterminada")))
        self.txt_telefono.setText(str(registro.get("telefono") or ""))
        self.txt_email.setText(str(registro.get("email") or ""))
        self.txt_web.setText(str(registro.get("web") or ""))
        self.txt_iban.setText(str(registro.get("iban") or ""))
        self.spn_irpf.setValue(a_float(registro.get("retencion_irpf")))
        self.txt_pie.setPlainText(str(registro.get("pie_documento") or ""))
        self.txt_serie_fac.setText(str(registro.get("serie_factura") or ""))
        self.txt_serie_pre.setText(str(registro.get("serie_presupuesto") or ""))
        self.txt_serie_alb.setText(str(registro.get("serie_albaran") or ""))
        self.spn_num_fac.setValue(int(registro.get("siguiente_factura") or 1))
        self.spn_num_pre.setValue(int(registro.get("siguiente_presupuesto") or 1))
        self.spn_num_alb.setValue(int(registro.get("siguiente_albaran") or 1))
        self.ruta_logo = str(registro.get("logo") or "")
        self._mostrar_logo()
        self._actualizar_ejemplo()

    def guardar(self):
        datos = {
            "nombre": self.txt_nombre.text().strip(),
            "nombre_comercial": self.txt_comercial.text().strip(),
            "nif": self.txt_nif.text().strip().upper(),
            "direccion": self.txt_direccion.text().strip(),
            "cp": self.txt_cp.text().strip(),
            "ciudad": self.txt_ciudad.text().strip(),
            "provincia": self.txt_provincia.text().strip(),
            "pais": self.txt_pais.text().strip() or "España",
            "telefono": self.txt_telefono.text().strip(),
            "email": self.txt_email.text().strip(),
            "web": self.txt_web.text().strip(),
            "iban": self.txt_iban.text().strip().upper(),
            "logo": self.ruta_logo,
            "serie_factura": self.txt_serie_fac.text().strip(),
            "serie_presupuesto": self.txt_serie_pre.text().strip(),
            "serie_albaran": self.txt_serie_alb.text().strip(),
            "siguiente_factura": self.spn_num_fac.value() or 1,
            "siguiente_presupuesto": self.spn_num_pre.value() or 1,
            "siguiente_albaran": self.spn_num_alb.value() or 1,
            "retencion_irpf": self.spn_irpf.value(),
            "pie_documento": self.txt_pie.toPlainText().strip(),
            "predeterminada": 1 if self.chk_predeterminada.isChecked() else 0,
            "activo": 1 if self.chk_activa.isChecked() else 0,
        }
        if not datos["nombre"]:
            return self.aviso("La razon social es obligatoria.", self.txt_nombre)
        if not datos["nif"]:
            return self.aviso("El NIF o CIF es obligatorio.", self.txt_nif)
        if existe_valor("empresas", "nif", datos["nif"], self.registro_id):
            return self.aviso("Ya existe una empresa con ese NIF.", self.txt_nif)
        if self.registro_id:
            actualizar("empresas", self.registro_id, datos)
        else:
            self.registro_id = insertar("empresas", datos)
        if datos["predeterminada"]:
            marcar_empresa_predeterminada(self.registro_id)
        return True

class EmpresasWidget(PanelLista):
    titulo = "Empresas emisoras"
    subtitulo = "Empresas desde las que emitiras documentos."
    placeholder_busqueda = "Buscar por razon social, NIF o ciudad..."
    nombre_exportacion = "empresas"
    columna_expandible = 0
    columnas = (
        ("Razon social", "nombre", "texto"),
        ("NIF", "nif", "texto"),
        ("Ciudad", "ciudad", "texto"),
        ("Telefono", "telefono", "texto"),
        ("Email", "email", "texto"),
        ("Serie factura", "serie_factura", "texto"),
        ("Prox. factura", "siguiente_factura", "texto"),
        ("IRPF", "retencion_irpf", "porcentaje"),
        ("Predet.", "predeterminada", "bool"),
        ("Estado", "activo", "activo"),
    )

    def listar(self, texto):
        return listar("empresas", texto=texto, campos_busqueda=("nombre", "nombre_comercial", "nif", "ciudad"), orden="predeterminada DESC, nombre COLLATE NOCASE")

    def obtener(self, registro_id):
        return obtener("empresas", registro_id)

    def borrar(self, registro_id):
        return eliminar("empresas", registro_id)

    def etiqueta(self, registro):
        return str(registro.get("nombre")) + " (" + str(registro.get("nif")) + ")"

    def preparar_duplicado(self, registro):
        copia = dict(registro)
        copia["nombre"] = str(copia.get("nombre") or "") + " (copia)"
        copia["nif"] = ""
        copia["predeterminada"] = 0
        return copia

    def abrir_ficha(self, registro=None, duplicar=False):
        dialogo = DialogoEmpresa(self, registro=registro, duplicar=duplicar)
        return dialogo.exec() == QDialog.DialogCode.Accepted

    def celda_personalizada(self, registro, clave):
        if clave == "siguiente_factura":
            item = QTableWidgetItem(formatear_numero(registro.get("serie_factura"), registro.get("siguiente_factura") or 1))
            item.setForeground(QColor(AZUL))
            return item
        if clave == "predeterminada":
            item = QTableWidgetItem("Si" if registro.get("predeterminada") else "")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            return item
        return None

    def resumen(self, registros):
        activas = sum(1 for r in registros if r.get("activo"))
        predet = next((str(r.get("nombre")) for r in registros if r.get("predeterminada")), "ninguna")
        return str(len(registros)) + " empresa(s)  \u2022  " + str(activas) + " activa(s)  \u2022  predeterminada: " + predet