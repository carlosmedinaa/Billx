"""Vista previa de PDF dentro de la aplicacion (QtPdf), sin abrir un programa externo.

El PDF se guarda en memoria: el temporal se borra en cuanto se lee, asi que no
quedan ficheros bloqueados ni restos en la carpeta temporal de Windows.
"""
import os
import sys
import tempfile

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QSize, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
from PyQt6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout

from ui_common import AZUL, GRIS, VERDE, crear_boton

ZOOM_MIN, ZOOM_MAX, PASO_ZOOM = 0.25, 4.0, 1.25


class VistaPreviaPDF(QDialog):
    """Ventana no modal con el PDF: zoom, guardar, imprimir y abrir fuera si hace falta."""

    def __init__(self, datos_pdf, titulo="Vista previa", nombre_sugerido="documento.pdf", parent=None):
        super().__init__(parent)
        self.datos_pdf = bytes(datos_pdf)
        self.nombre_sugerido = nombre_sugerido
        self.setWindowTitle(titulo)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(900, 1000)

        # El buffer debe vivir tanto como el documento: se guarda en self
        self._buffer = QBuffer(self)
        self._buffer.setData(QByteArray(self.datos_pdf))
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.documento = QPdfDocument(self)
        self.documento.load(self._buffer)

        self.vista = QPdfView(self)
        self.vista.setDocument(self.documento)
        self.vista.setPageMode(QPdfView.PageMode.MultiPage)
        self.vista.setPageSpacing(12)
        self.vista.setStyleSheet("background: #6b7280;")
        self._ajustar_ancho()

        barra = QHBoxLayout()
        barra.addWidget(crear_boton("−", GRIS, lambda: self._zoom(1 / PASO_ZOOM)))
        barra.addWidget(crear_boton("+", GRIS, lambda: self._zoom(PASO_ZOOM)))
        barra.addWidget(crear_boton("Ajustar ancho", GRIS, self._ajustar_ancho))
        barra.addWidget(crear_boton("Página entera", GRIS, self._pagina_entera))
        self.lbl_paginas = QLabel()
        barra.addWidget(self.lbl_paginas)
        barra.addStretch(1)
        barra.addWidget(crear_boton("🖨️ Imprimir", AZUL, self.imprimir))
        barra.addWidget(crear_boton("💾 Guardar PDF", VERDE, self.guardar_como))
        barra.addWidget(crear_boton("Abrir fuera", GRIS, self.abrir_externo))

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(8, 8, 8, 8)
        raiz.addLayout(barra)
        raiz.addWidget(self.vista, 1)

        paginas = self.documento.pageCount()
        self.lbl_paginas.setText(f"  {paginas} página{'s' if paginas != 1 else ''}")

    def tamano_inicial(self, pantalla):
        """Casi toda la altura de la pantalla y ancho de folio A4, sin bajar del
        ancho que necesita la barra de botones."""
        alto = int(pantalla.height() * 0.92)
        ancho = min(int(pantalla.width() * 0.9), max(self.minimumSizeHint().width(), 820, int(alto * 0.72)))
        return QSize(ancho, alto)

    # --- zoom ---------------------------------------------------------------
    def _ajustar_ancho(self):
        self.vista.setZoomMode(QPdfView.ZoomMode.FitToWidth)

    def _pagina_entera(self):
        self.vista.setZoomMode(QPdfView.ZoomMode.FitInView)

    def _zoom(self, factor):
        actual = self.vista.zoomFactor() if self.vista.zoomMode() == QPdfView.ZoomMode.Custom else self._zoom_efectivo()
        self.vista.setZoomMode(QPdfView.ZoomMode.Custom)
        self.vista.setZoomFactor(max(ZOOM_MIN, min(ZOOM_MAX, actual * factor)))

    def _zoom_efectivo(self):
        """Zoom equivalente al modo 'ajustar' actual, para que +/- partan de lo que se ve."""
        if self.documento.pageCount() == 0:
            return 1.0
        ancho_pagina = self.documento.pagePointSize(0).width() * self.logicalDpiX() / 72.0
        return max(ZOOM_MIN, (self.vista.viewport().width() - 24) / ancho_pagina) if ancho_pagina else 1.0

    # --- acciones -------------------------------------------------------------
    def guardar_como(self):
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar PDF", os.path.join(os.path.expanduser("~"), self.nombre_sugerido), "Archivos PDF (*.pdf)"
        )
        if not ruta:
            return
        if not ruta.lower().endswith(".pdf"):
            ruta += ".pdf"
        try:
            with open(ruta, "wb") as archivo:
                archivo.write(self.datos_pdf)
        except OSError as error:
            QMessageBox.critical(self, "No se pudo guardar", str(error))
            return
        QMessageBox.information(self, "Guardado", "PDF guardado en:\n" + ruta)

    def imprimir(self):
        impresora = QPrinter(QPrinter.PrinterMode.HighResolution)
        impresora.setDocName(self.nombre_sugerido)
        dialogo = QPrintDialog(impresora, self)
        dialogo.setMinMax(1, max(1, self.documento.pageCount()))
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return
        imprimir_documento(self.documento, impresora)

    def abrir_externo(self):
        """Plan B: abrir con el visor de PDF del sistema (como hacia antes la app)."""
        fd, ruta = tempfile.mkstemp(suffix=".pdf", prefix="billx_")
        with os.fdopen(fd, "wb") as archivo:
            archivo.write(self.datos_pdf)
        if os.name == "nt":
            os.startfile(ruta)
        else:
            import subprocess
            subprocess.call(("open" if sys.platform == "darwin" else "xdg-open", ruta))

    def closeEvent(self, evento):
        self.documento.close()
        super().closeEvent(evento)


def imprimir_documento(documento, impresora):
    """Pinta cada pagina del PDF en la impresora, a su resolucion y centrada."""
    desde, hasta = impresora.fromPage(), impresora.toPage()
    if desde == 0 and hasta == 0:              # "todas las paginas"
        desde, hasta = 1, documento.pageCount()
    pintor = QPainter()
    if not pintor.begin(impresora):
        raise OSError("No se pudo iniciar la impresión.")
    try:
        dpi = impresora.resolution()
        area = impresora.pageLayout().paintRectPixels(dpi)
        for numero in range(desde - 1, hasta):
            if numero > desde - 1:
                impresora.newPage()
            puntos = documento.pagePointSize(numero)
            escala = min(area.width() / puntos.width(), area.height() / puntos.height())
            tamano = QSize(int(puntos.width() * escala), int(puntos.height() * escala))
            imagen = documento.render(numero, tamano)
            origen = QPointF((area.width() - tamano.width()) / 2, (area.height() - tamano.height()) / 2)
            pintor.drawImage(origen, imagen)
    finally:
        pintor.end()


def leer_y_borrar(ruta):
    """Lee el PDF generado en un temporal y borra el temporal."""
    try:
        with open(ruta, "rb") as archivo:
            return archivo.read()
    finally:
        try:
            os.remove(ruta)
        except OSError:
            pass
