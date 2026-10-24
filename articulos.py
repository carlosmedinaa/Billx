from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QDialog, QFormLayout, QLabel, QTextEdit
from database import listar, obtener, insertar, actualizar, eliminar, existe_valor, valores_distintos
from ui_common import DialogoFicha, PanelLista, campo_texto, campo_combo, campo_moneda, campo_decimal, checkbox, a_float, fmt_num, fmt_moneda, ItemNumerico, ROJO

TIPOS_ARTICULO = ("Producto", "Servicio")
UNIDADES = ("Unidad", "Hora", "Kg", "Litro", "Metro", "m2", "Caja", "Servicio")
IVAS = ("21", "10", "4", "0")

def siguiente_referencia(prefijo="ART"):
    maximo = 0
    for referencia in valores_distintos("articulos", "referencia"):
        partes = str(referencia).split("-")
        if len(partes) >= 2 and partes[0].upper() == prefijo and partes[-1].isdigit():
            maximo = max(maximo, int(partes[-1]))
    return prefijo + "-{:04d}".format(maximo + 1)

def precio_con_iva(precio_venta, iva):
    return a_float(precio_venta) * (1 + a_float(iva) / 100)

class DialogoArticulo(DialogoFicha):
    titulo_nuevo = "Nuevo articulo o servicio"
    titulo_editar = "Editar articulo o servicio"
    ancho_minimo = 560

    def construir(self, layout):
        formulario = QFormLayout()
        formulario.setSpacing(10)
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_referencia = campo_texto("ART-0001", 30)
        self.txt_descripcion = campo_texto("Descripcion que saldra en la factura", 200)
        self.cmb_tipo = campo_combo(TIPOS_ARTICULO)
        self.cmb_familia = campo_combo(("",) + tuple(valores_distintos("articulos", "familia")), editable=True)
        self.cmb_unidad = campo_combo(UNIDADES, editable=True)
        self.spn_coste = campo_moneda()
        self.spn_venta = campo_moneda()
        self.cmb_iva = campo_combo(IVAS, editable=True)
        self.chk_stock = checkbox("Controlar el stock de este articulo")
        self.spn_stock = campo_decimal(maximo=9999999.0)
        self.spn_stock_min = campo_decimal(maximo=9999999.0)
        self.chk_activo = checkbox("Articulo activo", True)
        self.txt_notas = QTextEdit()
        self.txt_notas.setMaximumHeight(80)

        self.lbl_calculo = QLabel()
        self.lbl_calculo.setStyleSheet("color: #2563eb; font-weight: 600;")

        formulario.addRow("Referencia *", self.txt_referencia)
        formulario.addRow("Descripcion *", self.txt_descripcion)
        formulario.addRow("Tipo", self.cmb_tipo)
        formulario.addRow("Familia", self.cmb_familia)
        formulario.addRow("Unidad", self.cmb_unidad)
        formulario.addRow("Precio de coste", self.spn_coste)
        formulario.addRow("Precio de venta (sin IVA)", self.spn_venta)
        formulario.addRow("IVA (%)", self.cmb_iva)
        formulario.addRow("", self.lbl_calculo)
        formulario.addRow(self.chk_stock)
        formulario.addRow("Stock actual", self.spn_stock)
        formulario.addRow("Stock minimo", self.spn_stock_min)
        formulario.addRow(self.chk_activo)
        formulario.addRow("Notas", self.txt_notas)
        layout.addLayout(formulario)

        self.spn_coste.valueChanged.connect(self._actualizar_calculo)
        self.spn_venta.valueChanged.connect(self._actualizar_calculo)
        self.cmb_iva.currentTextChanged.connect(self._actualizar_calculo)
        self.cmb_tipo.currentTextChanged.connect(self._tipo_cambiado)
        self.chk_stock.toggled.connect(self._alternar_stock)
        self._alternar_stock(False)
        self._actualizar_calculo()

    def _tipo_cambiado(self, tipo):
        if tipo == "Servicio":
            self.chk_stock.setChecked(False)
            self.cmb_unidad.setCurrentText("Hora")
        self.chk_stock.setEnabled(tipo != "Servicio")

    def _alternar_stock(self, activado):
        self.spn_stock.setEnabled(activado)
        self.spn_stock_min.setEnabled(activado)

    def _iva_valido(self):
        valor = a_float(self.cmb_iva.currentText(), por_defecto=-1.0)
        return valor if 0 <= valor <= 100 else None

    def _actualizar_calculo(self):
        iva = self._iva_valido()
        if iva is None:
            self.lbl_calculo.setText("El IVA debe ser un numero entre 0 y 100.")
            self.lbl_calculo.setStyleSheet("color: #dc2626; font-weight: 600;")
            return
        venta = self.spn_venta.value()
        coste = self.spn_coste.value()
        pvp = precio_con_iva(venta, iva)
        margen = "margen " + fmt_num((venta - coste) / coste * 100) + " %" if coste > 0 else "margen sin calcular"
        self.lbl_calculo.setText("PVP con IVA: " + fmt_moneda(pvp) + "  \u2022  " + margen)
        self.lbl_calculo.setStyleSheet("color: #2563eb; font-weight: 600;")

    def cargar(self, registro):
        if not registro:
            self.txt_referencia.setText(siguiente_referencia())
            return
        self.txt_referencia.setText(str(registro.get("referencia") or siguiente_referencia()))
        self.txt_descripcion.setText(str(registro.get("descripcion") or ""))
        tipo = str(registro.get("tipo") or "Producto")
        if tipo in TIPOS_ARTICULO:
            self.cmb_tipo.setCurrentText(tipo)
        self.cmb_familia.setCurrentText(str(registro.get("familia") or ""))
        self.cmb_unidad.setCurrentText(str(registro.get("unidad") or "Unidad"))
        self.spn_coste.setValue(a_float(registro.get("precio_coste")))
        self.spn_venta.setValue(a_float(registro.get("precio_venta")))
        self.cmb_iva.setCurrentText(fmt_num(registro.get("iva"), 0))
        self.chk_stock.setChecked(bool(registro.get("control_stock")))
        self.spn_stock.setValue(a_float(registro.get("stock")))
        self.spn_stock_min.setValue(a_float(registro.get("stock_minimo")))
        self.chk_activo.setChecked(bool(registro.get("activo", 1)))
        self.txt_notas.setPlainText(str(registro.get("notas") or ""))
        self._actualizar_calculo()

    def guardar(self):
        if self._iva_valido() is None:
            return self.aviso("El IVA debe ser un numero entre 0 y 100.", self.cmb_iva)
        controla = self.chk_stock.isChecked()
        datos = {
            "referencia": self.txt_referencia.text().strip(),
            "descripcion": self.txt_descripcion.text().strip(),
            "tipo": self.cmb_tipo.currentText(),
            "familia": self.cmb_familia.currentText().strip(),
            "unidad": self.cmb_unidad.currentText().strip() or "Unidad",
            "precio_coste": self.spn_coste.value(),
            "precio_venta": self.spn_venta.value(),
            "iva": self._iva_valido() or 0.0,
            "control_stock": 1 if controla else 0,
            "stock": self.spn_stock.value() if controla else 0.0,
            "stock_minimo": self.spn_stock_min.value() if controla else 0.0,
            "activo": 1 if self.chk_activo.isChecked() else 0,
            "notas": self.txt_notas.toPlainText().strip(),
        }
        if not datos["referencia"]:
            return self.aviso("La referencia es obligatoria.", self.txt_referencia)
        if not datos["descripcion"]:
            return self.aviso("La descripcion es obligatoria.", self.txt_descripcion)
        if existe_valor("articulos", "referencia", datos["referencia"], self.registro_id):
            return self.aviso("Ya existe un articulo con esa referencia.", self.txt_referencia)
        if self.registro_id:
            actualizar("articulos", self.registro_id, datos)
        else:
            self.registro_id = insertar("articulos", datos)
        return True

class ArticulosWidget(PanelLista):
    titulo = "Articulos y servicios"
    subtitulo = "Catalogo que alimentara las lineas de presupuestos, albaranes y facturas."
    placeholder_busqueda = "Buscar por referencia, descripcion o familia..."
    nombre_exportacion = "articulos"
    columna_expandible = 1
    columnas = (
        ("Referencia", "referencia", "texto"),
        ("Descripcion", "descripcion", "texto"),
        ("Tipo", "tipo", "texto"),
        ("Familia", "familia", "texto"),
        ("Unidad", "unidad", "texto"),
        ("Coste", "precio_coste", "moneda"),
        ("Venta", "precio_venta", "moneda"),
        ("IVA", "iva", "porcentaje"),
        ("PVP con IVA", "pvp", "moneda"),
        ("Stock", "stock", "numero"),
        ("Estado", "activo", "activo"),
    )

    def anadir_filtros(self, layout):
        self.cmb_filtro_tipo = campo_combo(("Todos",) + TIPOS_ARTICULO)
        self.cmb_filtro_tipo.currentIndexChanged.connect(self.cargar)
        self.chk_solo_activos = checkbox("Solo activos")
        self.chk_solo_activos.toggled.connect(self.cargar)
        self.chk_bajo_minimo = checkbox("Bajo minimo")
        self.chk_bajo_minimo.toggled.connect(self.cargar)
        layout.addWidget(self.cmb_filtro_tipo)
        layout.addWidget(self.chk_solo_activos)
        layout.addWidget(self.chk_bajo_minimo)

    def listar(self, texto):
        condiciones = []
        params = []
        tipo = self.cmb_filtro_tipo.currentText()
        if tipo != "Todos":
            condiciones.append("tipo = ?")
            params.append(tipo)
        if self.chk_solo_activos.isChecked():
            condiciones.append("activo = 1")
        if self.chk_bajo_minimo.isChecked():
            condiciones.append("control_stock = 1 AND stock <= stock_minimo")
        return listar("articulos", texto=texto, campos_busqueda=("referencia", "descripcion", "familia"), condiciones=condiciones, params=params, orden="referencia COLLATE NOCASE")

    def obtener(self, registro_id):
        return obtener("articulos", registro_id)

    def borrar(self, registro_id):
        return eliminar("articulos", registro_id)

    def etiqueta(self, registro):
        return str(registro.get("referencia")) + " - " + str(registro.get("descripcion"))

    def preparar_duplicado(self, registro):
        copia = dict(registro)
        copia["referencia"] = siguiente_referencia()
        copia["stock"] = 0.0
        return copia

    def abrir_ficha(self, registro=None, duplicar=False):
        dialogo = DialogoArticulo(self, registro=registro, duplicar=duplicar)
        return dialogo.exec() == QDialog.DialogCode.Accepted

    def celda_personalizada(self, registro, clave):
        if clave == "pvp":
            pvp = precio_con_iva(registro.get("precio_venta"), registro.get("iva"))
            return ItemNumerico(fmt_moneda(pvp), pvp)
        if clave == "stock":
            if not registro.get("control_stock"):
                return ItemNumerico("\u2014", -1.0)
            stock = a_float(registro.get("stock"))
            item = ItemNumerico(fmt_num(stock), stock)
            if stock <= a_float(registro.get("stock_minimo")):
                item.setForeground(QColor(ROJO))
            return item
        return None

    def resumen(self, registros):
        valor = sum(a_float(r.get("stock")) * a_float(r.get("precio_coste")) for r in registros if r.get("control_stock"))
        bajos = sum(1 for r in registros if r.get("control_stock") and a_float(r.get("stock")) <= a_float(r.get("stock_minimo")))
        return str(len(registros)) + " articulo(s)  \u2022  valor stock: " + fmt_moneda(valor) + "  \u2022  " + str(bajos) + " bajo minimo"