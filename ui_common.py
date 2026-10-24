import csv
import os
from datetime import datetime
from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget
)
from errores import DatabaseError

EURO = "\u20ac"
AZUL = "#2563eb"
VERDE = "#0f766e"
MORADO = "#7c3aed"
ROJO = "#dc2626"
GRIS = "#4b5563"

ESTILO_TABLA = """
QTableWidget {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    gridline-color: #f3f4f6;
    selection-background-color: #dbeafe;
    selection-color: #111827;
}
QTableWidget::item { padding: 6px; }
QHeaderView::section {
    background: #f9fafb;
    border: none;
    border-bottom: 1px solid #e5e7eb;
    padding: 8px;
    font-weight: 600;
}
"""

def fmt_num(valor, decimales=2):
    try:
        # Decimal se formatea tal cual (sin pasar por float) para no perder exactitud
        numero = valor if isinstance(valor, Decimal) else float(valor or 0)
        texto = "{:,.{}f}".format(numero, decimales)
    except (TypeError, ValueError):
        return "0,00" if decimales else "0"
    return texto.replace(",", "\u00a0").replace(".", ",").replace("\u00a0", ".")

def fmt_moneda(valor):
    return fmt_num(valor) + " " + EURO

def a_float(valor, por_defecto=0.0):
    if isinstance(valor, (int, float, Decimal)):
        return float(valor)
    texto = str(valor or "").strip()
    for sobra in ("%", EURO, " ", "\u00a0"):
        texto = texto.replace(sobra, "")
    if not texto:
        return por_defecto
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return por_defecto

def crear_boton(texto, color=AZUL, funcion=None):
    boton = QPushButton(texto)
    boton.setCursor(Qt.CursorShape.PointingHandCursor)
    boton.setMinimumHeight(34)
    boton.setStyleSheet(
        "QPushButton {"
        "  background: " + color + ";"
        "  color: #ffffff; border: none; border-radius: 6px;"
        "  padding: 6px 16px; font-weight: 600;"
        "}"
        "QPushButton:hover { background: " + color + "; border: 1px solid #111827; }"
        "QPushButton:pressed { padding-top: 7px; }"
        "QPushButton:disabled { background: #d1d5db; color: #6b7280; }"
    )
    if funcion is not None:
        boton.clicked.connect(funcion)
    return boton

def campo_texto(placeholder="", maxlen=120):
    campo = QLineEdit()
    campo.setPlaceholderText(placeholder)
    campo.setMaxLength(maxlen)
    campo.setClearButtonEnabled(True)
    return campo

def campo_moneda(maximo=9999999.99):
    spin = QDoubleSpinBox()
    spin.setRange(0.0, maximo)
    spin.setDecimals(2)
    spin.setSingleStep(1.0)
    spin.setSuffix(" " + EURO)
    spin.setGroupSeparatorShown(True)
    return spin

def campo_decimal(maximo=9999999.99, decimales=2, sufijo=""):
    spin = QDoubleSpinBox()
    spin.setRange(0.0, maximo)
    spin.setDecimals(decimales)
    spin.setSingleStep(1.0)
    spin.setGroupSeparatorShown(True)
    if sufijo:
        spin.setSuffix(sufijo)
    return spin

def campo_entero(maximo=9999, sufijo=""):
    spin = QSpinBox()
    spin.setRange(0, maximo)
    if sufijo:
        spin.setSuffix(sufijo)
    return spin

def campo_combo(opciones=(), editable=False):
    combo = QComboBox()
    combo.setEditable(editable)
    for opcion in opciones:
        combo.addItem(str(opcion))
    return combo

def checkbox(texto, marcado=False):
    caja = QCheckBox(texto)
    caja.setChecked(marcado)
    return caja

class ItemNumerico(QTableWidgetItem):
    def __init__(self, texto, valor):
        super().__init__(texto)
        self.valor = a_float(valor)
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, otro):
        if isinstance(otro, ItemNumerico):
            return self.valor < otro.valor
        return super().__lt__(otro)

class DialogoFicha(QDialog):
    titulo_nuevo = "Nuevo registro"
    titulo_editar = "Editar registro"
    ancho_minimo = 560

    def __init__(self, parent=None, registro=None, duplicar=False):
        super().__init__(parent)
        self.registro = dict(registro or {})
        self.duplicar = duplicar
        self.registro_id = None if duplicar else self.registro.get("id")
        self.setWindowTitle(self.titulo_editar if self.registro_id else self.titulo_nuevo)
        self.setMinimumWidth(self.ancho_minimo)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(18, 18, 18, 18)
        raiz.setSpacing(12)
        self.construir(raiz)

        botones = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        botones.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        botones.accepted.connect(self._intentar_guardar)
        botones.rejected.connect(self.reject)
        raiz.addWidget(botones)

        self.cargar(self.registro)

    def construir(self, layout):
        raise NotImplementedError

    def cargar(self, registro):
        pass

    def guardar(self):
        raise NotImplementedError

    def _intentar_guardar(self):
        try:
            if self.guardar():
                self.accept()
        except ValueError as error:
            QMessageBox.warning(self, "Revisa los datos", str(error))
        except DatabaseError as error:
            QMessageBox.critical(self, "Error de base de datos", str(error))

    def aviso(self, mensaje, widget=None):
        QMessageBox.warning(self, "Falta informacion", mensaje)
        if widget is not None:
            widget.setFocus()
        return False

class PanelLista(QWidget):
    titulo = "Registros"
    subtitulo = ""
    placeholder_busqueda = "Buscar..."
    columnas = (("Nombre", "nombre", "texto"),)
    columna_expandible = 0
    permite_duplicar = True
    nombre_exportacion = "listado"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._registros = []
        self._construir_ui()
        self.cargar()

    def listar(self, texto):
        raise NotImplementedError

    def obtener(self, registro_id):
        raise NotImplementedError

    def abrir_ficha(self, registro=None, duplicar=False):
        raise NotImplementedError

    def borrar(self, registro_id):
        raise NotImplementedError

    def etiqueta(self, registro):
        return str(registro.get("nombre") or registro.get("id") or "")

    def preparar_duplicado(self, registro):
        return dict(registro)

    def anadir_filtros(self, layout):
        pass

    def resumen(self, registros):
        return str(len(registros)) + " registro(s)"

    def celda_personalizada(self, registro, clave):
        return None

    def _construir_ui(self):
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(24, 20, 24, 20)
        raiz.setSpacing(12)

        lbl_titulo = QLabel(self.titulo)
        lbl_titulo.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        raiz.addWidget(lbl_titulo)

        if self.subtitulo:
            lbl_sub = QLabel(self.subtitulo)
            lbl_sub.setStyleSheet("color: #6b7280;")
            lbl_sub.setWordWrap(True)
            raiz.addWidget(lbl_sub)

        barra = QHBoxLayout()
        barra.setSpacing(8)
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText(self.placeholder_busqueda)
        self.txt_buscar.setClearButtonEnabled(True)
        self.txt_buscar.setMinimumHeight(32)
        self.txt_buscar.textChanged.connect(self.cargar)
        barra.addWidget(self.txt_buscar, 1)
        self.anadir_filtros(barra)
        raiz.addLayout(barra)

        acciones = QHBoxLayout()
        acciones.setSpacing(8)
        self.btn_nuevo = crear_boton("Nuevo", AZUL, self._nuevo)
        self.btn_editar = crear_boton("Editar", VERDE, self._editar)
        self.btn_eliminar = crear_boton("Eliminar", ROJO, self._eliminar)
        self.btn_exportar = crear_boton("Exportar CSV", GRIS, self._exportar_csv)
        acciones.addWidget(self.btn_nuevo)
        acciones.addWidget(self.btn_editar)
        if self.permite_duplicar:
            self.btn_duplicar = crear_boton("Duplicar", MORADO, self._duplicar)
            acciones.addWidget(self.btn_duplicar)
        else:
            self.btn_duplicar = None
        acciones.addWidget(self.btn_eliminar)
        acciones.addWidget(self.btn_exportar)
        acciones.addStretch(1)
        raiz.addLayout(acciones)

        self.tabla = QTableWidget(0, len(self.columnas))
        self.tabla.setHorizontalHeaderLabels([c[0] for c in self.columnas])
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setSortingEnabled(True)
        self.tabla.setWordWrap(False)
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setStyleSheet(ESTILO_TABLA)
        self.tabla.doubleClicked.connect(self._editar)
        self.tabla.itemSelectionChanged.connect(self._actualizar_acciones)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        if 0 <= self.columna_expandible < len(self.columnas):
            cabecera.setSectionResizeMode(self.columna_expandible, QHeaderView.ResizeMode.Stretch)
        raiz.addWidget(self.tabla, 1)

        linea = QFrame()
        linea.setFrameShape(QFrame.Shape.HLine)
        linea.setStyleSheet("color: #e5e7eb;")
        raiz.addWidget(linea)

        self.lbl_estado = QLabel()
        self.lbl_estado.setStyleSheet("color: #374151;")
        raiz.addWidget(self.lbl_estado)

        self._actualizar_acciones()

    def cargar(self):
        try:
            self._registros = self.listar(self.txt_buscar.text().strip())
        except (DatabaseError, ValueError) as error:
            QMessageBox.critical(self, "No se pudieron leer los datos", str(error))
            self._registros = []

        self.tabla.setSortingEnabled(False)
        self.tabla.setRowCount(0)
        for fila, registro in enumerate(self._registros):
            self.tabla.insertRow(fila)
            for columna, definicion in enumerate(self.columnas):
                _encabezado, clave, tipo = definicion
                item = self._crear_celda(registro, clave, tipo)
                if columna == 0:
                    item.setData(Qt.ItemDataRole.UserRole, registro.get("id"))
                self.tabla.setItem(fila, columna, item)
        self.tabla.setSortingEnabled(True)
        self.lbl_estado.setText(self.resumen(self._registros))
        self._actualizar_acciones()

    def _crear_celda(self, registro, clave, tipo):
        personalizada = self.celda_personalizada(registro, clave)
        if personalizada is not None:
            return personalizada
        valor = registro.get(clave)
        if tipo == "moneda":
            return ItemNumerico(fmt_moneda(valor), valor)
        if tipo == "numero":
            return ItemNumerico(fmt_num(valor), valor)
        if tipo == "porcentaje":
            return ItemNumerico(fmt_num(valor) + " %", valor)
        if tipo == "bool":
            item = QTableWidgetItem("Si" if valor else "No")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            return item
        if tipo == "activo":
            item = QTableWidgetItem("Activo" if valor else "Inactivo")
            if not valor:
                item.setForeground(QColor("#9ca3af"))
            return item
        return QTableWidgetItem("" if valor is None else str(valor))

    def seleccion_id(self):
        fila = self.tabla.currentRow()
        if fila < 0:
            return None
        item = self.tabla.item(fila, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _actualizar_acciones(self):
        hay = self.seleccion_id() is not None
        self.btn_editar.setEnabled(hay)
        self.btn_eliminar.setEnabled(hay)
        if self.btn_duplicar is not None:
            self.btn_duplicar.setEnabled(hay)
        self.btn_exportar.setEnabled(self.tabla.rowCount() > 0)

    def _nuevo(self):
        if self.abrir_ficha():
            self.cargar()

    def _registro_actual(self):
        registro_id = self.seleccion_id()
        if not registro_id:
            return None
        registro = self.obtener(registro_id)
        if not registro:
            QMessageBox.information(self, "Registro no encontrado", "El registro ya no existe.")
            self.cargar()
            return None
        return registro

    def _editar(self):
        registro = self._registro_actual()
        if registro and self.abrir_ficha(registro=registro):
            self.cargar()

    def _duplicar(self):
        registro = self._registro_actual()
        if registro and self.abrir_ficha(registro=self.preparar_duplicado(registro), duplicar=True):
            self.cargar()

    def _eliminar(self):
        registro = self._registro_actual()
        if not registro:
            return
        respuesta = QMessageBox.question(
            self, "Confirmar eliminacion",
            "Vas a eliminar:\n\n" + self.etiqueta(registro) + "\n\n\u00bfEliminar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if respuesta != QMessageBox.StandardButton.Yes:
            return
        try:
            self.borrar(registro["id"])
        except DatabaseError as error:
            QMessageBox.critical(self, "No se pudo eliminar", str(error))
            return
        self.cargar()

    def _exportar_csv(self):
        if self.tabla.rowCount() == 0:
            return
        sugerencia = os.path.join(
            os.path.expanduser("~"),
            self.nombre_exportacion + "_" + datetime.now().strftime("%Y%m%d") + ".csv",
        )
        ruta, _ = QFileDialog.getSaveFileName(self, "Exportar a CSV", sugerencia, "Archivos CSV (*.csv)")
        if not ruta:
            return
        if not ruta.lower().endswith(".csv"):
            ruta += ".csv"
        try:
            with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
                escritor = csv.writer(archivo, delimiter=";")
                escritor.writerow([c[0] for c in self.columnas])
                for fila in range(self.tabla.rowCount()):
                    escritor.writerow([
                        self.tabla.item(fila, col).text() if self.tabla.item(fila, col) else ""
                        for col in range(self.tabla.columnCount())
                    ])
        except OSError as error:
            QMessageBox.critical(self, "Error al exportar", str(error))
            return
        QMessageBox.information(self, "Exportacion completada", "Archivo guardado en:\n" + ruta)