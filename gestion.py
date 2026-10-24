import sys
import traceback
import logging
import os
from datetime import datetime
if sys.platform == "win32":
    os.environ['QT_QPA_PLATFORM'] = 'windows:darkmode=0'
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
    QFileDialog
)

from config import BASE_DIR, auto_init_db
from errores import BillxError, ConfigError, DatabaseError
from database import init_db, comprobar_conexion, comprobar_esquema, contar, empresa_predeterminada, previsualizar_numero
from backup import volcar_base_de_datos
from empresas import EmpresasWidget
from clientes import ClientesWidget
from articulos import ArticulosWidget
from documentos import DocumentosWidget

VERSION = "1.0"

MENU_ESTILO = """
QPushButton {
    background: transparent;
    color: #d1d5db;
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
    text-align: left;
    font-size: 14px;
}
QPushButton:hover { background: #374151; color: #ffffff; }
QPushButton:checked { background: #2563eb; color: #ffffff; font-weight: 600; }
"""

def panel_informativo(titulo, mensaje, color="#6b7280"):
    contenedor = QWidget()
    layout = QVBoxLayout(contenedor)
    layout.setContentsMargins(40, 40, 40, 40)
    layout.setSpacing(10)
    layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

    lbl_titulo = QLabel(titulo)
    lbl_titulo.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
    lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

    lbl_mensaje = QLabel(mensaje)
    lbl_mensaje.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl_mensaje.setWordWrap(True)
    lbl_mensaje.setStyleSheet("color: " + color + ";")
    lbl_mensaje.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    layout.addWidget(lbl_titulo)
    layout.addWidget(lbl_mensaje)
    return contenedor

def crear_pantalla(titulo, constructor):
    if constructor is None:
        return panel_informativo(
            titulo,
            "Este modulo todavia no esta desarrollado.\n"
            "El siguiente paso son los documentos con sus lineas y totales.",
        )
    try:
        return constructor()
    except Exception:
        return panel_informativo(
            titulo,
            "No se pudo abrir la seccion " + titulo + ":\n\n" + traceback.format_exc(limit=4),
            color="#dc2626",
        )

class VentanaPrincipal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Billx")
        self.resize(1280, 760)
        self.setMinimumSize(1024, 640)
        self.botones = []
        self._dialogo_importacion = None
        self.secciones = (
            ("Inicio", self._crear_inicio),
            ("Empresas", EmpresasWidget),
            ("Clientes", ClientesWidget),
            ("Articulos", ArticulosWidget),
            ("Presupuestos", lambda: DocumentosWidget("presupuesto")),
            ("Albaranes", lambda: DocumentosWidget("albaran")),
            ("Facturas", lambda: DocumentosWidget("factura")),
        )
        self._construir_ui()
        self._cambiar_seccion(0)

    def _construir_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QHBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(self._crear_menu())

        self.paginas = QStackedWidget()
        self.paginas.setStyleSheet("background: #f3f4f6;")
        raiz.addWidget(self.paginas, 1)

        for titulo, constructor in self.secciones:
            self.paginas.addWidget(crear_pantalla(titulo, constructor))

    def _crear_menu(self):
        menu = QFrame()
        menu.setFixedWidth(230)
        menu.setStyleSheet("background: #1f2937;")

        layout = QVBoxLayout(menu)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(6)

        logo = QLabel("Billx")
        logo.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        logo.setStyleSheet("color: #ffffff;")
        layout.addWidget(logo)

        # Debajo, la empresa con la que se trabaja (sale de la base de datos, no del codigo)
        try:
            empresa = empresa_predeterminada() or {}
        except DatabaseError:
            empresa = {}
        nombre_empresa = empresa.get("nombre_comercial") or empresa.get("nombre") or ""
        if nombre_empresa:
            lbl_empresa = QLabel(nombre_empresa)
            lbl_empresa.setWordWrap(True)
            lbl_empresa.setStyleSheet("color: #9ca3af; font-size: 12px;")
            layout.addWidget(lbl_empresa)

        separador = QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        separador.setStyleSheet("background: #374151; color: #374151; max-height: 1px;")
        layout.addWidget(separador)
        layout.addSpacing(8)

        for indice, seccion in enumerate(self.secciones):
            boton = QPushButton(seccion[0])
            boton.setCheckable(True)
            boton.setAutoExclusive(True)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.setMinimumHeight(42)
            boton.setStyleSheet(MENU_ESTILO)
            boton.clicked.connect(lambda _marcado, i=indice: self._cambiar_seccion(i))
            layout.addWidget(boton)
            self.botones.append(boton)

        layout.addStretch(1)

        # --- BOTÓN IMPORTAR EBP ---
        btn_importar = QPushButton("  Importar datos EBP")
        btn_importar.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_importar.setMinimumHeight(42)
        btn_importar.setStyleSheet("""
            QPushButton {
                background: #0b7285;
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 13px;
                font-weight: bold;
                text-align: left;
            }
            QPushButton:hover { background: #095c6b; }
            QPushButton:pressed { background: #07454f; }
        """)
        btn_importar.clicked.connect(self.abrir_importacion)
        layout.addWidget(btn_importar)
        layout.addSpacing(4)
        # --------------------------

        # --- BOTÓN DE COPIA DE SEGURIDAD MANUAL ---
        btn_copia = QPushButton("Hacer Copia Seguridad")
        btn_copia.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copia.setStyleSheet("""
            QPushButton {
                background: #374151;
                color: #9ca3af;
                border: none;
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
                text-align: left;
            }
            QPushButton:hover { background: #4b5563; color: #ffffff; }
        """)
        btn_copia.clicked.connect(self._hacer_copia_manual)
        layout.addWidget(btn_copia)
        layout.addSpacing(4)
        # ------------------------------------------

        pie = QLabel("v" + VERSION + " \u2022 datos en servidor")
        pie.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(pie)
        return menu

    def abrir_importacion(self):
        """Abre el diálogo de importación de datos de EBP (importacion_ebp.py)."""
        try:
            from importacion_ebp import DialogoImportacionEBP
        except ImportError as e:
            QMessageBox.critical(
                self, "Módulo no encontrado",
                "No se pudo cargar 'importacion_ebp.py'.\n\n"
                "Comprueba que el archivo está en la misma carpeta que este programa.\n\n"
                f"Detalle: {e}"
            )
            return

        # Si ya está abierto, lo traemos al frente sin duplicarlo
        if self._dialogo_importacion is not None and self._dialogo_importacion.isVisible():
            self._dialogo_importacion.raise_()
            self._dialogo_importacion.activateWindow()
            return

        self._dialogo_importacion = DialogoImportacionEBP(parent=self)
        self._dialogo_importacion.exec()

    def _hacer_copia_manual(self):
        """Volcado completo de la base de datos del servidor (mysqldump) a un .sql."""
        sugerencia = f"billx_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar Copia de Seguridad",
            os.path.join(os.path.expanduser("~"), sugerencia),
            "Volcado SQL (*.sql)"
        )
        if not ruta:
            return
        if not ruta.lower().endswith(".sql"):
            ruta += ".sql"

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            volcar_base_de_datos(ruta)
        except BillxError as error:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "No se pudo guardar la copia", str(error))
            return
        QApplication.restoreOverrideCursor()
        QMessageBox.information(
            self, "Éxito",
            f"Copia de seguridad guardada correctamente en:\n{ruta}"
        )

    def _crear_inicio(self):
        contenedor = QWidget()
        layout = QVBoxLayout(contenedor)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        titulo = QLabel("Bienvenido")
        titulo.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        layout.addWidget(titulo)

        self.lbl_contadores = QLabel()
        self.lbl_contadores.setStyleSheet(
            "background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px;"
            "padding: 16px; font-size: 14px; color: #111827;"
        )
        layout.addWidget(self.lbl_contadores)

        texto = QLabel(
            "Orden de trabajo recomendado:\n\n"
            "  1. Empresas: da de alta la empresa emisora, su NIF, su logo y las series de numeracion.\n"
            "  2. Clientes: registra los clientes con sus datos fiscales y forma de pago.\n"
            "  3. Articulos: crea el catalogo con precios, IVA y stock.\n"
            "  4. Presupuestos, albaranes y facturas: se construyen sobre los tres anteriores.\n\n"
            "Los datos se guardan en el servidor (MySQL). La copia de seguridad automática la hace el "
            "servidor cada noche; también puedes descargar una copia manual desde el botón del menú inferior."
        )
        texto.setStyleSheet("color: #4b5563; font-size: 14px;")
        texto.setWordWrap(True)
        layout.addWidget(texto)

        contenedor.cargar = self._actualizar_contadores
        self._actualizar_contadores()
        return contenedor

    def _actualizar_contadores(self):
        try:
            total_empresas = contar("empresas")
            total_clientes = contar("clientes", ("activo = 1",))
            total_articulos = contar("articulos", ("activo = 1",))
            bajo_minimo = contar("articulos", ("control_stock = 1", "stock <= stock_minimo"))
            empresa = empresa_predeterminada()
        except DatabaseError as error:
            self.lbl_contadores.setText("No se pudo leer la base de datos: " + str(error))
            return
        nombre = empresa["nombre"] if empresa else "sin definir"
        proxima = previsualizar_numero(empresa["id"], "factura") if empresa else "-"
        self.lbl_contadores.setText(
            "Empresa emisora: " + str(nombre) + "\n"
            "Proxima factura: " + str(proxima) + "\n"
            "Empresas: " + str(total_empresas) + "    \u2022    Clientes activos: " +
            str(total_clientes) + "    \u2022    Articulos activos: " + str(total_articulos) +
            "    \u2022    Bajo stock minimo: " + str(bajo_minimo)
        )

    def _cambiar_seccion(self, indice):
        if indice < 0 or indice >= self.paginas.count():
            return
        self.paginas.setCurrentIndex(indice)
        for i, boton in enumerate(self.botones):
            boton.setChecked(i == indice)
        widget = self.paginas.widget(indice)
        recargar = getattr(widget, "cargar", None)
        if callable(recargar):
            try:
                recargar()
            except DatabaseError as error:
                logging.getLogger("billx").warning("Fallo al recargar seccion: %s", error)
                QMessageBox.warning(self, "Sin conexión con los datos", str(error))
            except Exception:
                logging.getLogger("billx").exception("Fallo al recargar la seccion %s", indice)

    # (closeEvent con copia local/USB eliminado: con MySQL remoto no hay fichero que copiar.
    #  La copia diaria vive en el servidor: scripts/backup_servidor.sh)

    def closeEvent(self, evento):
        """Con varias fichas de documento abiertas, avisar antes de perder lo no guardado."""
        from documentos import cerrar_ventanas_independientes, ventanas_documento_abiertas
        abiertas = ventanas_documento_abiertas()
        if abiertas:
            respuesta = QMessageBox.question(
                self, "Hay documentos abiertos",
                f"Tienes {len(abiertas)} documento(s) abierto(s). Lo que no hayas guardado se perderá.\n\n"
                "¿Cerrar el programa igualmente?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if respuesta != QMessageBox.StandardButton.Yes:
                evento.ignore()
                return
        cerrar_ventanas_independientes()   # son ventanas propias: si no, el programa no terminaria
        evento.accept()

def _configurar_logging():
    """Log a fichero junto al programa: sin consola en el .exe, es la unica pista."""
    try:
        logging.basicConfig(
            filename=os.path.join(BASE_DIR, "billx.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            encoding="utf-8",
        )
    except OSError:
        logging.basicConfig(level=logging.INFO)


def _instalar_manejador_global():
    """Red de seguridad: en PyQt6 una excepcion no capturada dentro de un slot
    TERMINA el programa. Con esto se registra y se avisa al usuario en su lugar."""
    def manejador(tipo, valor, tb):
        if issubclass(tipo, KeyboardInterrupt):
            sys.__excepthook__(tipo, valor, tb)
            return
        logging.getLogger("billx").error("Excepcion no controlada", exc_info=(tipo, valor, tb))
        if isinstance(valor, BillxError):
            titulo, texto = "Aviso", str(valor)
        else:
            titulo = "Error inesperado"
            texto = ("Ha ocurrido un error inesperado. La aplicación sigue abierta, pero conviene "
                     "repetir la operación y revisar que se guardó.\n\nDetalle: " + str(valor) +
                     "\n\n(Más información en billx.log)")
        try:
            QMessageBox.critical(None, titulo, texto)
        except Exception:
            sys.__excepthook__(tipo, valor, tb)
    sys.excepthook = manejador


def main():
    _configurar_logging()
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    _instalar_manejador_global()
    try:
        if auto_init_db():
            init_db()          # solo desarrollo: necesita permisos DDL
        comprobar_conexion()   # falla rapido (timeout) y con mensaje claro si Tailscale esta caido
        comprobar_esquema()    # version nueva sin migrar la base: aviso claro en vez de errores sueltos
    except (ConfigError, DatabaseError) as error:
        logging.getLogger("billx").error("Arranque fallido: %s", error)
        QMessageBox.critical(None, "No se pudo iniciar Billx", str(error))
        return 1
    ventana = VentanaPrincipal()
    ventana.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
