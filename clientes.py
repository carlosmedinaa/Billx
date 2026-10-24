from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFormLayout, QTabWidget, QTextEdit, QWidget
from database import listar, obtener, insertar, actualizar, eliminar, existe_valor, valores_distintos
from ui_common import DialogoFicha, PanelLista, campo_texto, campo_combo, campo_entero, campo_decimal, checkbox, a_float, fmt_num

FORMAS_PAGO = ("Transferencia", "Efectivo", "Tarjeta", "Domiciliacion", "Cheque", "Confirming")

def siguiente_codigo_cliente():
    maximo = 0
    for codigo in valores_distintos("clientes", "codigo"):
        parte = str(codigo).split("-")[-1]
        if parte.isdigit():
            maximo = max(maximo, int(parte))
    return "CLI-{:04d}".format(maximo + 1)

class DialogoCliente(DialogoFicha):
    titulo_nuevo = "Nuevo cliente"
    titulo_editar = "Editar cliente"
    ancho_minimo = 620

    def construir(self, layout):
        pestanas = QTabWidget()
        pestanas.addTab(self._pestana_generales(), "Datos generales")
        pestanas.addTab(self._pestana_facturacion(), "Facturacion")
        layout.addWidget(pestanas)

    def _pestana_generales(self):
        pagina = QWidget()
        formulario = QFormLayout(pagina)
        formulario.setSpacing(10)
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.txt_codigo = campo_texto("CLI-0001", 20)
        self.txt_nombre = campo_texto("Nombre o razon social", 150)
        self.txt_comercial = campo_texto("Nombre comercial (opcional)", 150)
        self.txt_nif = campo_texto("NIF / CIF / NIE", 20)
        self.txt_direccion = campo_texto("Calle, numero, piso", 200)
        self.txt_cp = campo_texto("28001", 10)
        self.txt_ciudad = campo_texto("Poblacion", 100)
        self.txt_provincia = campo_texto("Provincia", 100)
        self.txt_pais = campo_texto("Pais", 60)
        self.txt_pais.setText("España")
        self.txt_telefono = campo_texto("+34 600 000 000", 30)
        self.txt_email = campo_texto("cliente@correo.com", 120)
        self.txt_contacto = campo_texto("Persona de contacto", 120)
        self.chk_activo = checkbox("Cliente activo", True)

        formulario.addRow("Codigo", self.txt_codigo)
        formulario.addRow("Nombre *", self.txt_nombre)
        formulario.addRow("Nombre comercial", self.txt_comercial)
        formulario.addRow("NIF / CIF", self.txt_nif)
        formulario.addRow("Direccion", self.txt_direccion)
        formulario.addRow("Codigo postal", self.txt_cp)
        formulario.addRow("Ciudad", self.txt_ciudad)
        formulario.addRow("Provincia", self.txt_provincia)
        formulario.addRow("Pais", self.txt_pais)
        formulario.addRow("Telefono", self.txt_telefono)
        formulario.addRow("Email", self.txt_email)
        formulario.addRow("Contacto", self.txt_contacto)
        formulario.addRow(self.chk_activo)
        return pagina

    def _pestana_facturacion(self):
        pagina = QWidget()
        formulario = QFormLayout(pagina)
        formulario.setSpacing(10)
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.cmb_forma_pago = campo_combo(FORMAS_PAGO)
        self.spn_dias = campo_entero(365, " dias")
        self.spn_descuento = campo_decimal(maximo=100.0, sufijo=" %")
        self.txt_iban = campo_texto("ES00 0000 0000 0000 0000 0000", 34)
        self.chk_recargo = checkbox("Aplicar recargo de equivalencia (5,2 %)")
        self.chk_exento = checkbox("Cliente exento de IVA")
        self.txt_notas = QTextEdit()
        self.txt_notas.setMaximumHeight(90)

        formulario.addRow("Forma de pago", self.cmb_forma_pago)
        formulario.addRow("Vencimiento", self.spn_dias)
        formulario.addRow("Descuento habitual", self.spn_descuento)
        formulario.addRow("IBAN", self.txt_iban)
        formulario.addRow(self.chk_recargo)
        formulario.addRow(self.chk_exento)
        formulario.addRow("Notas", self.txt_notas)
        return pagina

    def cargar(self, registro):
        if not registro:
            self.txt_codigo.setText(siguiente_codigo_cliente())
            return
        self.txt_codigo.setText(str(registro.get("codigo") or siguiente_codigo_cliente()))
        self.txt_nombre.setText(str(registro.get("nombre") or ""))
        self.txt_comercial.setText(str(registro.get("nombre_comercial") or ""))
        self.txt_nif.setText(str(registro.get("nif") or ""))
        self.txt_direccion.setText(str(registro.get("direccion") or ""))
        self.txt_cp.setText(str(registro.get("cp") or ""))
        self.txt_ciudad.setText(str(registro.get("ciudad") or ""))
        self.txt_provincia.setText(str(registro.get("provincia") or ""))
        self.txt_pais.setText(str(registro.get("pais") or "España"))
        self.txt_telefono.setText(str(registro.get("telefono") or ""))
        self.txt_email.setText(str(registro.get("email") or ""))
        self.txt_contacto.setText(str(registro.get("contacto") or ""))
        self.chk_activo.setChecked(bool(registro.get("activo", 1)))
        forma = str(registro.get("forma_pago") or FORMAS_PAGO[0])
        if forma in FORMAS_PAGO:
            self.cmb_forma_pago.setCurrentText(forma)
        self.spn_dias.setValue(int(registro.get("dias_pago") or 0))
        self.spn_descuento.setValue(a_float(registro.get("descuento")))
        self.txt_iban.setText(str(registro.get("iban") or ""))
        self.chk_recargo.setChecked(bool(registro.get("recargo_equivalencia")))
        self.chk_exento.setChecked(bool(registro.get("exento_iva")))
        self.txt_notas.setPlainText(str(registro.get("notas") or ""))

    def guardar(self):
        datos = {
            "codigo": self.txt_codigo.text().strip(),
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
            "contacto": self.txt_contacto.text().strip(),
            "iban": self.txt_iban.text().strip().upper(),
            "forma_pago": self.cmb_forma_pago.currentText(),
            "dias_pago": self.spn_dias.value(),
            "descuento": self.spn_descuento.value(),
            "recargo_equivalencia": 1 if self.chk_recargo.isChecked() else 0,
            "exento_iva": 1 if self.chk_exento.isChecked() else 0,
            "notas": self.txt_notas.toPlainText().strip(),
            "activo": 1 if self.chk_activo.isChecked() else 0,
        }
        if not datos["nombre"]:
            return self.aviso("El nombre del cliente es obligatorio.", self.txt_nombre)
        if not datos["codigo"]:
            datos["codigo"] = siguiente_codigo_cliente()
        if existe_valor("clientes", "codigo", datos["codigo"], self.registro_id):
            return self.aviso("El codigo ya esta en uso.", self.txt_codigo)
        if datos["nif"] and existe_valor("clientes", "nif", datos["nif"], self.registro_id):
            return self.aviso("Ya existe un cliente con ese NIF.", self.txt_nif)
        if self.registro_id:
            actualizar("clientes", self.registro_id, datos)
        else:
            self.registro_id = insertar("clientes", datos)
        return True

class ClientesWidget(PanelLista):
    titulo = "Clientes"
    subtitulo = "Fichas con los datos fiscales y las condiciones de pago de cada cliente."
    placeholder_busqueda = "Buscar por codigo, nombre, NIF, ciudad o email..."
    nombre_exportacion = "clientes"
    columna_expandible = 1
    columnas = (
        ("Codigo", "codigo", "texto"),
        ("Nombre", "nombre", "texto"),
        ("NIF", "nif", "texto"),
        ("Ciudad", "ciudad", "texto"),
        ("Telefono", "telefono", "texto"),
        ("Email", "email", "texto"),
        ("Dto.", "descuento", "porcentaje"),
        ("Estado", "activo", "activo"),
    )

    def anadir_filtros(self, layout):
        self.chk_solo_activos = checkbox("Solo activos")
        self.chk_solo_activos.toggled.connect(self.cargar)
        layout.addWidget(self.chk_solo_activos)

    def listar(self, texto):
        condiciones = []
        params = []
        if self.chk_solo_activos.isChecked():
            condiciones.append("activo = 1")
        return listar("clientes", texto=texto, campos_busqueda=("codigo", "nombre", "nombre_comercial", "nif", "ciudad", "email"), condiciones=condiciones, params=params, orden="nombre COLLATE NOCASE")

    def obtener(self, registro_id):
        return obtener("clientes", registro_id)

    def borrar(self, registro_id):
        return eliminar("clientes", registro_id)

    def etiqueta(self, registro):
        return str(registro.get("codigo")) + " - " + str(registro.get("nombre"))

    def preparar_duplicado(self, registro):
        copia = dict(registro)
        copia["codigo"] = siguiente_codigo_cliente()
        copia["nif"] = ""
        copia["nombre"] = str(copia.get("nombre") or "") + " (copia)"
        return copia

    def abrir_ficha(self, registro=None, duplicar=False):
        dialogo = DialogoCliente(self, registro=registro, duplicar=duplicar)
        return dialogo.exec() == QDialog.DialogCode.Accepted

    def celda_personalizada(self, registro, clave):
        if clave == "dias_pago":
            dias = int(registro.get("dias_pago") or 0)
            texto = "Al contado" if dias == 0 else str(dias) + " dias"
            return __import__('ui_common', fromlist=['ItemNumerico']).ItemNumerico(texto, dias)
        return None

    def resumen(self, registros):
        activos = sum(1 for r in registros if r.get("activo"))
        exentos = sum(1 for r in registros if r.get("exento_iva"))
        medio = (sum(a_float(r.get("descuento")) for r in registros) / len(registros)) if registros else 0.0
        return str(len(registros)) + " cliente(s)  \u2022  " + str(activos) + " activo(s)  \u2022  " + str(exentos) + " exento(s)  \u2022  dto. medio " + fmt_num(medio) + " %"