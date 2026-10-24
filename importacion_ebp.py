"""
importacion_ebp.py
Importa los CSV exportados de EBP directamente a las tablas propias del
programa, de modo que los datos aparezcan en Clientes, Articulos,
Presupuestos, Pedidos, Albaranes, Facturas y Abonos.

Uso desde el programa:  boton "Importar datos EBP" -> abrir_dialogo_importacion(self)
Uso independiente:      python importacion_ebp.py

Caracteristicas:
  * Detecta automaticamente codificacion (UTF-8 / Windows-1252) y separador
    (; , tabulador |) de cada CSV.
  * Detecta que contiene cada archivo por su cabecera, sin importar el nombre
    ni el idioma (español, frances o ingles de EBP).
  * Soporta CSV "planos" donde cada fila es una linea de factura y repite los
    datos de la cabecera del documento.
  * Descubre por si mismo los nombres de columna de TUS tablas, asi que no
    depende de como este escrito database.py.
  * Es idempotente: cada fila guarda su identificador de origen en la columna
    ebp_id, por lo que se puede reimportar sin duplicar.
  * Hace copia de seguridad de la base de datos antes de tocar nada.
"""

import csv
import io
import os
import re
import shutil
import sqlite3
import sys
import traceback
import unicodedata
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ═════════════════════════════════════════════════════════════
#  LOCALIZAR LA BASE DE DATOS
# ═════════════════════════════════════════════════════════════
def localizar_db():
    """Devuelve la ruta de la base de datos que usa el programa."""
    try:
        from database import DB_PATH as ruta  # type: ignore
        if ruta:
            return ruta if os.path.isabs(ruta) else os.path.join(BASE_DIR, ruta)
    except Exception:
        pass

    for nombre in ("gestion.db", "facturacion.db", "datos.db", "empresa.db"):
        candidata = os.path.join(BASE_DIR, nombre)
        if os.path.exists(candidata):
            return candidata

    for nombre in sorted(os.listdir(BASE_DIR)):
        if nombre.lower().endswith((".db", ".sqlite", ".sqlite3")):
            return os.path.join(BASE_DIR, nombre)

    return os.path.join(BASE_DIR, "gestion.db")


# ═════════════════════════════════════════════════════════════
#  NORMALIZACION DE TEXTO Y VALORES
# ═════════════════════════════════════════════════════════════
def norm(valor):
    """'Código Postal ' -> 'codigopostal'  (sin acentos, sin espacios, minusculas)."""
    if valor is None:
        return ""
    descompuesto = unicodedata.normalize("NFKD", str(valor))
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", sin_acentos.lower())


def texto(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def numero(valor, defecto=0.0):
    """Acepta 1.234,56 / 1,234.56 / 1234.56 / '12 €' / vacio."""
    if valor is None:
        return defecto
    if isinstance(valor, (int, float)):
        return float(valor)
    limpio = str(valor).strip()
    if not limpio:
        return defecto
    negativo = limpio.startswith("(") and limpio.endswith(")")
    limpio = re.sub(r"[^0-9,.\-]", "", limpio)
    if not limpio or limpio in ("-", ".", ","):
        return defecto
    if "," in limpio and "." in limpio:
        if limpio.rfind(",") > limpio.rfind("."):
            limpio = limpio.replace(".", "").replace(",", ".")
        else:
            limpio = limpio.replace(",", "")
    else:
        limpio = limpio.replace(",", ".")
    try:
        resultado = float(limpio)
    except ValueError:
        return defecto
    return -resultado if negativo else resultado


FORMATOS_FECHA = (
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y",
    "%d/%m/%y", "%d.%m.%Y", "%Y%m%d",
)


def fecha(valor):
    bruto = texto(valor)
    if not bruto:
        return ""
    bruto = bruto.replace("T", " ").split(" ")[0]
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(bruto, formato).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return bruto


# ═════════════════════════════════════════════════════════════
#  SINONIMOS DE COLUMNA (origen EBP y destino del programa)
#  Todo en forma normalizada: sin acentos, sin espacios, minusculas.
# ═════════════════════════════════════════════════════════════
ID_UNICO = ("id", "uniqueid", "idunique", "guid", "uid", "identificador", "rowid")

# --- Clientes ---
CLI_NOMBRE = ("nombre", "razonsocial", "nombrefiscal", "nombrecomercial",
              "cliente", "tercero", "denominacion", "nombrecompleto",
              "name", "companyname", "nomtiers", "nom", "raisonsociale")
CLI_CODIGO = ("codigocliente", "codcliente", "numerocliente", "numcliente",
              "codigotercero", "codigo", "clientcode", "codetiers",
              "cuentacontable", "referenciacliente")
CLI_NIF = ("nif", "cif", "dni", "nifcif", "numerofiscal", "identificacionfiscal",
           "numeroidentificacionfiscal", "documento", "vatnumber", "siret",
           "numerotva", "nifdni")
CLI_DIRECCION = ("direccion", "direccion1", "domicilio", "calle",
                 "direccioncompleta", "address", "address1", "adresse")
CLI_CP = ("cp", "codigopostal", "codpostal", "zip", "postalcode", "codepostal")
CLI_POBLACION = ("poblacion", "ciudad", "localidad", "city", "ville")
CLI_PROVINCIA = ("provincia", "region", "estadoprovincia", "departamento", "state")
CLI_PAIS = ("pais", "country", "pays")
CLI_TELEFONO = ("telefono", "telefono1", "tel", "fijo", "telfijo", "phone", "telephone")
CLI_MOVIL = ("movil", "telefono2", "celular", "mobile", "gsm", "portable")
CLI_EMAIL = ("email", "correo", "correoelectronico", "mail", "emailaddress")
CLI_WEB = ("web", "sitioweb", "paginaweb", "website", "siteweb")
CLI_NOTAS = ("notas", "observaciones", "comentarios", "notes", "comment", "commentaire")

# --- Documentos ---
DOC_NUMERO = ("numero", "numerodocumento", "numdocumento", "num", "numfactura",
              "numerofactura", "numerodefactura", "serienumero", "referencia",
              "referenciadocumento", "numeropieza", "documentnumber",
              "piecenumber", "invoicenumber", "numeropiece")
DOC_FECHA = ("fecha", "fechadocumento", "fechaemision", "fechafactura",
             "date", "documentdate", "invoicedate", "datepiece")
DOC_TIPO = ("tipo", "tipodocumento", "tipodedocumento", "tipofactura", "clase",
            "documenttype", "typepiece", "naturaleza")
DOC_CLIENTE_ID = ("clienteid", "idcliente", "terceroid", "idtercero", "customerid",
                  "tiersid", "clientid")
DOC_CLIENTE_COD = CLI_CODIGO
DOC_CLIENTE_NOMBRE = ("nombrecliente", "clientenombre", "razonsocialcliente",
                      "customername", "nomclient") + CLI_NOMBRE
DOC_BASE = ("baseimponible", "base", "importebase", "importeneto", "totalneto",
            "subtotal", "totalsiniva", "totalht", "nettotal", "montantht")
DOC_IVA = ("totaliva", "iva", "importeiva", "cuotaiva", "impuestos",
           "totaltva", "taxamount", "montanttva")
DOC_TOTAL = ("total", "totalfactura", "importetotal", "totaldocumento",
             "totalconiva", "totalapagar", "totalttc", "grandtotal", "montantttc")
DOC_ESTADO = ("estado", "situacion", "status", "etat")

# --- Lineas ---
LIN_DOC_REF = ("documentoid", "iddocumento", "documento", "facturaid", "idfactura",
               "documentid", "pieceid", "idpiece") + DOC_NUMERO
LIN_REFERENCIA = ("referenciaarticulo", "codigoarticulo", "refarticulo", "codarticulo",
                  "articuloid", "idarticulo", "referencia", "codigo", "ref",
                  "codigoproducto", "itemid", "articlecode", "refarticle")
LIN_DESCRIPCION = ("descripcion", "descripcionlarga", "concepto", "designacion",
                   "detalle", "nombrearticulo", "texto", "description",
                   "designation", "libelle")
LIN_CANTIDAD = ("cantidad", "unidades", "cant", "qty", "quantity", "quantite")
LIN_PRECIO = ("preciounitario", "precio", "precioventa", "pvp", "importeunitario",
              "unitprice", "prixunitaire", "puht")
LIN_DESCUENTO = ("descuento", "dto", "descuentoporcentaje", "porcentajedescuento",
                 "discount", "remise")
LIN_IVA = ("iva", "tipoiva", "porcentajeiva", "ivaporcentaje", "tva", "taxrate", "vatrate")
LIN_TOTAL = ("totallinea", "importelinea", "total", "importe", "importeneto",
             "totalht", "linetotal", "montant")
LIN_ORDEN = ("orden", "posicion", "numlinea", "linea", "lineorder", "position")

# --- Articulos ---
ART_REFERENCIA = LIN_REFERENCIA
ART_DESCRIPCION = LIN_DESCRIPCION
ART_PRECIO = ("precioventa", "precio", "pvp", "preciounitario", "pvprecomendado",
              "salesprice", "prixvente")
ART_COSTE = ("preciocoste", "coste", "costo", "preciocompra", "purchaseprice", "prixachat")
ART_IVA = LIN_IVA
ART_FAMILIA = ("familia", "categoria", "grupo", "family", "category", "famille")
ART_STOCK = ("stock", "existencias", "cantidadstock", "stockactual", "quantitystock")
ART_UNIDAD = ("unidad", "unidadmedida", "um", "unit", "unite")


# ═════════════════════════════════════════════════════════════
#  TIPOS DE DOCUMENTO
# ═════════════════════════════════════════════════════════════
TIPOS_TEXTO = {
    "presupuesto": "presupuesto", "presupuestos": "presupuesto", "oferta": "presupuesto",
    "devis": "presupuesto", "quote": "presupuesto", "estimate": "presupuesto",
    "pedido": "pedido", "pedidos": "pedido", "pedidocliente": "pedido",
    "commande": "pedido", "order": "pedido", "customerorder": "pedido",
    "albaran": "albaran", "albaranes": "albaran", "entrega": "albaran",
    "bonlivraison": "albaran", "livraison": "albaran", "delivery": "albaran",
    "deliveryorder": "albaran", "deliverynote": "albaran",
    "factura": "factura", "facturas": "factura", "facturaventa": "factura",
    "facture": "factura", "invoice": "factura",
    "abono": "abono", "abonos": "abono", "facturarectificativa": "abono",
    "rectificativa": "abono", "avoir": "abono", "creditmemo": "abono",
    "creditnote": "abono", "notacredito": "abono",
}

# Codigos numericos de EBP (los mas habituales; ajustables si algo cae mal)
TIPOS_CODIGO = {
    "0": "presupuesto",
    "1": "pedido",
    "2": "albaran",
    "3": "factura",
    "4": "abono",
    "5": "factura",
}

PREFIJOS_NUMERO = (
    ("FR", "abono"), ("NC", "abono"), ("AB", "abono"), ("AV", "abono"),
    ("PR", "presupuesto"), ("PU", "presupuesto"), ("DE", "presupuesto"),
    ("OF", "presupuesto"), ("QT", "presupuesto"),
    ("AL", "albaran"), ("BL", "albaran"), ("DL", "albaran"),
    ("PE", "pedido"), ("PC", "pedido"), ("BC", "pedido"), ("CM", "pedido"),
    ("FA", "factura"), ("FV", "factura"), ("IN", "factura"), ("FC", "factura"),
)

PISTAS_NOMBRE_TIPO = (
    ("rectificativ", "abono"), ("abono", "abono"), ("avoir", "abono"),
    ("credit", "abono"),
    ("presupuest", "presupuesto"), ("devis", "presupuesto"),
    ("quote", "presupuesto"), ("estimate", "presupuesto"), ("oferta", "presupuesto"),
    ("albaran", "albaran"), ("livraison", "albaran"), ("delivery", "albaran"),
    ("pedido", "pedido"), ("commande", "pedido"), ("order", "pedido"),
    ("factur", "factura"), ("invoice", "factura"),
)


def tipo_desde_valor(valor):
    clave = norm(valor)
    if not clave:
        return ""
    if clave.endswith("0") and clave[:-1].isdigit() is False:
        pass
    if clave in TIPOS_TEXTO:
        return TIPOS_TEXTO[clave]
    numerico = re.sub(r"[^0-9]", "", clave)
    if numerico and numerico == clave.replace(".", ""):
        return TIPOS_CODIGO.get(str(int(numerico)), "")
    for fragmento, tipo in PISTAS_NOMBRE_TIPO:
        if fragmento in clave:
            return tipo
    return ""


def tipo_desde_numero(valor):
    bruto = texto(valor).upper()
    if not bruto:
        return ""
    prefijo = re.match(r"[A-Z]{1,3}", bruto)
    if not prefijo:
        return ""
    letras = prefijo.group(0)
    for clave, tipo in PREFIJOS_NUMERO:
        if letras.startswith(clave):
            return tipo
    return ""


def tipo_desde_nombre_archivo(nombre):
    clave = norm(nombre)
    for fragmento, tipo in PISTAS_NOMBRE_TIPO:
        if fragmento in clave:
            return tipo
    return ""


# ═════════════════════════════════════════════════════════════
#  LECTURA DE CSV
# ═════════════════════════════════════════════════════════════
def leer_csv(ruta):
    """Devuelve (cabeceras_originales, lista_de_filas_normalizadas)."""
    contenido = None
    for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(ruta, "r", encoding=codificacion, newline="") as archivo:
                contenido = archivo.read()
            break
        except UnicodeDecodeError:
            continue
    if contenido is None:
        raise IOError("No se pudo leer el archivo con ninguna codificacion conocida.")

    if not contenido.strip():
        return [], []

    muestra = contenido[:8192]
    try:
        separador = csv.Sniffer().sniff(muestra, delimiters=";,\t|").delimiter
    except csv.Error:
        primera_linea = muestra.splitlines()[0] if muestra.splitlines() else ""
        conteos = {d: primera_linea.count(d) for d in (";", ",", "\t", "|")}
        separador = max(conteos, key=lambda d: conteos[d])
        if conteos[separador] == 0:
            separador = ";"

    lector = csv.reader(io.StringIO(contenido), delimiter=separador)
    try:
        cabeceras = next(lector)
    except StopIteration:
        return [], []

    claves = []
    vistas = set()
    for indice, cabecera in enumerate(cabeceras):
        clave = norm(cabecera) or ("col%d" % indice)
        while clave in vistas:
            clave += "_"
        vistas.add(clave)
        claves.append(clave)

    filas = []
    for valores in lector:
        if not any(texto(v) for v in valores):
            continue
        fila = {}
        for indice, clave in enumerate(claves):
            fila[clave] = valores[indice] if indice < len(valores) else ""
        filas.append(fila)

    return cabeceras, filas


def valor(fila, candidatas):
    for clave in candidatas:
        if clave in fila:
            contenido = texto(fila[clave])
            if contenido:
                return contenido
    return ""


def tiene(campos, candidatas):
    return any(clave in campos for clave in candidatas)


def clasificar(nombre_archivo, campos):
    """Devuelve 'clientes' | 'articulos' | 'documentos' | 'lineas' | 'mixto' | ''."""
    clave_nombre = norm(nombre_archivo)

    hay_doc_ref = tiene(campos, LIN_DOC_REF)
    hay_numero = tiene(campos, DOC_NUMERO)
    hay_fecha = tiene(campos, DOC_FECHA)
    hay_total_doc = tiene(campos, DOC_TOTAL) or tiene(campos, DOC_BASE)
    hay_cantidad = tiene(campos, LIN_CANTIDAD)
    hay_precio = tiene(campos, LIN_PRECIO)
    hay_nif = tiene(campos, CLI_NIF)
    hay_nombre = tiene(campos, CLI_NOMBRE)
    hay_contacto = tiene(campos, CLI_DIRECCION) or tiene(campos, CLI_CP) \
        or tiene(campos, CLI_EMAIL) or tiene(campos, CLI_TELEFONO)
    hay_ref_art = tiene(campos, ART_REFERENCIA)
    nivel_linea = hay_cantidad or (hay_precio and hay_ref_art)

    if any(p in clave_nombre for p in ("client", "tiers", "customer")) and not nivel_linea:
        return "clientes"
    if any(p in clave_nombre for p in ("articul", "article", "item", "product", "produit")) \
            and not hay_doc_ref:
        return "articulos"

    if hay_doc_ref and nivel_linea:
        return "mixto" if (hay_fecha or hay_total_doc or hay_nombre) else "lineas"
    if nivel_linea and hay_ref_art and not hay_doc_ref:
        return "articulos"
    if (hay_numero or hay_doc_ref) and (hay_fecha or hay_total_doc):
        return "documentos"
    if hay_nif or (hay_nombre and hay_contacto):
        return "clientes"
    if hay_nombre and hay_ref_art:
        return "articulos"
    return ""


# ═════════════════════════════════════════════════════════════
#  UTILIDADES DE ESQUEMA SQLITE
# ═════════════════════════════════════════════════════════════
def tabla_existe(cur, nombre):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (nombre,))
    return cur.fetchone() is not None


def info_columnas(cur, tabla):
    cur.execute('PRAGMA table_info("%s")' % tabla)
    info = {}
    for fila in cur.fetchall():
        info[fila[1]] = {
            "tipo": (fila[2] or "").upper(),
            "notnull": bool(fila[3]),
            "default": fila[4],
            "pk": bool(fila[5]),
        }
    return info


def mapa_normalizado(info):
    return {norm(nombre): nombre for nombre in info}


def col(cols_norm, candidatas):
    for clave in candidatas:
        if clave in cols_norm:
            return cols_norm[clave]
    return None


def clave_primaria(info):
    for nombre, datos in info.items():
        if datos["pk"]:
            return nombre
    return "rowid"


def primera_tabla(cur, candidatas):
    for nombre in candidatas:
        if tabla_existe(cur, nombre):
            return nombre
    return None


def asegurar_ebp_id(cur, tabla):
    if "ebp_id" not in info_columnas(cur, tabla):
        cur.execute('ALTER TABLE "%s" ADD COLUMN ebp_id TEXT' % tabla)


def es_numerica(tipo):
    return any(t in tipo for t in ("INT", "REAL", "NUM", "DEC", "FLOA", "DOUB", "BOOL"))


def rellenar_obligatorias(info, datos):
    for nombre, meta in info.items():
        if nombre in datos or nombre == "ebp_id" or meta["pk"]:
            continue
        if meta["notnull"] and meta["default"] is None:
            datos[nombre] = 0 if es_numerica(meta["tipo"]) else ""
    return datos


def upsert(cur, tabla, info, pk, datos, ebp_id):
    """Inserta o actualiza segun ebp_id. Devuelve (id_local, creada)."""
    datos = {k: v for k, v in datos.items() if k in info and k != pk}
    cur.execute('SELECT "%s" FROM "%s" WHERE ebp_id = ?' % (pk, tabla), (ebp_id,))
    existente = cur.fetchone()

    if existente:
        id_local = existente[0]
        if datos:
            asignaciones = ", ".join('"%s" = ?' % k for k in datos)
            cur.execute(
                'UPDATE "%s" SET %s WHERE "%s" = ?' % (tabla, asignaciones, pk),
                list(datos.values()) + [id_local],
            )
        return id_local, False

    fila = rellenar_obligatorias(info, dict(datos))
    fila["ebp_id"] = ebp_id
    nombres = ", ".join('"%s"' % k for k in fila)
    marcas = ", ".join("?" for _ in fila)
    cur.execute(
        'INSERT INTO "%s" (%s) VALUES (%s)' % (tabla, nombres, marcas),
        tuple(fila.values()),
    )
    return cur.lastrowid, True


# ═════════════════════════════════════════════════════════════
#  IMPORTADOR
# ═════════════════════════════════════════════════════════════
class Importador:
    TABLAS_LINEAS = ("lineas_documento", "lineas", "documento_lineas",
                     "lineas_factura", "detalle_documento", "documento_linea")

    def __init__(self, carpeta, db_path=None, registrar=None):
        self.carpeta = carpeta
        self.db_path = db_path or localizar_db()
        self.registrar = registrar or (lambda mensaje: None)
        self.avisos = []
        self.totales = {
            "clientes": [0, 0], "articulos": [0, 0],
            "documentos": [0, 0], "lineas": [0, 0],
        }
        self.por_tipo = {}
        self.cli_por_id = {}
        self.cli_por_codigo = {}
        self.cli_por_nif = {}
        self.cli_por_nombre = {}
        self.doc_por_clave = {}
        self.docs_migrados = []
        self.arts_por_referencia = {}

    # ── infraestructura ────────────────────────────────────
    def log(self, mensaje=""):
        self.registrar(mensaje)

    def copia_seguridad(self):
        if not os.path.exists(self.db_path):
            return None
        carpeta = os.path.join(BASE_DIR, "backups")
        os.makedirs(carpeta, exist_ok=True)
        destino = os.path.join(
            carpeta,
            "%s_antes_import_%s.db" % (
                os.path.splitext(os.path.basename(self.db_path))[0],
                datetime.now().strftime("%Y%m%d_%H%M%S"),
            ),
        )
        shutil.copyfile(self.db_path, destino)
        return destino

    def archivos_csv(self):
        if not os.path.isdir(self.carpeta):
            return []
        encontrados = []
        for raiz, _, nombres in os.walk(self.carpeta):
            if os.path.basename(raiz).lower() in ("backups", "__pycache__"):
                continue
            for nombre in sorted(nombres):
                if nombre.lower().endswith((".csv", ".txt")):
                    encontrados.append(os.path.join(raiz, nombre))
        return encontrados

    # ── proceso principal ──────────────────────────────────
    def ejecutar(self):
        self.log("Base de datos: %s" % self.db_path)

        if not os.path.exists(self.db_path):
            self.log("ERROR: no encuentro la base de datos. Abre el programa una vez "
                     "para que se cree y vuelve a importar.")
            return False

        archivos = self.archivos_csv()
        if not archivos:
            self.log("ERROR: no hay ningun archivo .csv en la carpeta seleccionada.")
            return False

        copia = self.copia_seguridad()
        if copia:
            self.log("Copia de seguridad: %s" % copia)
        self.log("")

        # 1. Clasificar todos los archivos antes de escribir nada
        grupos = {"clientes": [], "articulos": [], "documentos": [], "lineas": [], "mixto": []}
        self.log("── ARCHIVOS DETECTADOS ──")
        for ruta in archivos:
            nombre = os.path.basename(ruta)
            try:
                cabeceras, filas = leer_csv(ruta)
            except Exception as error:
                self.avisos.append("No se pudo leer %s: %s" % (nombre, error))
                continue
            if not filas:
                self.log("  %-34s (vacio, se omite)" % nombre)
                continue
            campos = set(filas[0].keys())
            clase = clasificar(nombre, campos)
            if not clase:
                self.log("  %-34s SIN RECONOCER" % nombre)
                self.avisos.append(
                    "No reconozco el contenido de %s. Cabecera: %s"
                    % (nombre, " | ".join(cabeceras[:12]))
                )
                continue
            self.log("  %-34s %-11s %d filas" % (nombre, clase, len(filas)))
            grupos[clase].append((nombre, filas))
        self.log("")

        conexion = sqlite3.connect(self.db_path)
        conexion.row_factory = sqlite3.Row
        cur = conexion.cursor()

        try:
            for necesaria in ("clientes", "documentos"):
                if not tabla_existe(cur, necesaria):
                    self.log("ERROR: la tabla '%s' no existe en la base de datos." % necesaria)
                    return False

            self.log("── IMPORTANDO ──")
            for nombre, filas in grupos["clientes"]:
                self.importar_clientes(cur, nombre, filas)
            self.cargar_clientes_existentes(cur)

            for nombre, filas in grupos["articulos"]:
                self.importar_articulos(cur, nombre, filas)

            for nombre, filas in grupos["documentos"]:
                self.importar_documentos(cur, nombre, filas)

            for nombre, filas in grupos["mixto"]:
                self.importar_mixto(cur, nombre, filas)

            for nombre, filas in grupos["lineas"]:
                self.importar_lineas(cur, nombre, filas)

            self.deducir_articulos(cur)
            self.recalcular_totales(cur)
            conexion.commit()

        except Exception:
            conexion.rollback()
            self.log("")
            self.log("── ERROR: no se ha guardado nada ──")
            self.log(traceback.format_exc())
            return False
        finally:
            conexion.close()

        self.informe()
        return True

    def informe(self):
        self.log("")
        self.log("── RESUMEN ──")
        etiquetas = (("clientes", "Clientes  "), ("articulos", "Articulos "),
                     ("documentos", "Documentos"), ("lineas", "Lineas    "))
        for clave, etiqueta in etiquetas:
            nuevos, actualizados = self.totales[clave]
            self.log("  %s  %4d nuevos   %4d actualizados" % (etiqueta, nuevos, actualizados))
        if self.por_tipo:
            self.log("")
            self.log("  Documentos por tipo:")
            for tipo in sorted(self.por_tipo):
                self.log("    - %-13s %d" % (tipo, self.por_tipo[tipo]))
        if self.avisos:
            self.log("")
            self.log("── AVISOS ──")
            for aviso in self.avisos:
                self.log("  * %s" % aviso)
        self.log("")
        self.log("Listo. Cierra esta ventana y entra en Clientes, Articulos, "
                 "Presupuestos, Albaranes o Facturas.")

    # ── clientes ───────────────────────────────────────────
    def importar_clientes(self, cur, nombre_archivo, filas):
        asegurar_ebp_id(cur, "clientes")
        info = info_columnas(cur, "clientes")
        cols = mapa_normalizado(info)
        pk = clave_primaria(info)

        destino = {
            "nombre": col(cols, CLI_NOMBRE),
            "codigo": col(cols, CLI_CODIGO),
            "nif": col(cols, CLI_NIF),
            "direccion": col(cols, CLI_DIRECCION),
            "cp": col(cols, CLI_CP),
            "poblacion": col(cols, CLI_POBLACION),
            "provincia": col(cols, CLI_PROVINCIA),
            "pais": col(cols, CLI_PAIS),
            "telefono": col(cols, CLI_TELEFONO),
            "movil": col(cols, CLI_MOVIL),
            "email": col(cols, CLI_EMAIL),
            "web": col(cols, CLI_WEB),
            "notas": col(cols, CLI_NOTAS),
        }
        origen = {
            "nombre": CLI_NOMBRE, "codigo": CLI_CODIGO, "nif": CLI_NIF,
            "direccion": CLI_DIRECCION, "cp": CLI_CP, "poblacion": CLI_POBLACION,
            "provincia": CLI_PROVINCIA, "pais": CLI_PAIS, "telefono": CLI_TELEFONO,
            "movil": CLI_MOVIL, "email": CLI_EMAIL, "web": CLI_WEB, "notas": CLI_NOTAS,
        }

        nuevos = actualizados = 0
        for indice, fila in enumerate(filas, start=1):
            nombre = valor(fila, CLI_NOMBRE)
            nif = valor(fila, CLI_NIF)
            codigo = valor(fila, CLI_CODIGO)
            id_origen = valor(fila, ID_UNICO)

            if not (nombre or nif or codigo or id_origen):
                continue

            ebp_id = ("cli:" + id_origen) if id_origen else \
                     ("cli:cod:" + codigo) if codigo else \
                     ("cli:nif:" + norm(nif)) if nif else \
                     ("cli:nom:" + norm(nombre) or "cli:fila:%d" % indice)

            datos = {}
            for campo, columna in destino.items():
                if columna:
                    datos[columna] = valor(fila, origen[campo])
            if destino["nombre"] and not datos.get(destino["nombre"]):
                datos[destino["nombre"]] = nif or codigo or "Cliente %d" % indice
            if "activo" in info:
                datos["activo"] = 1

            id_local, creado = upsert(cur, "clientes", info, pk, datos, ebp_id)
            if creado:
                nuevos += 1
            else:
                actualizados += 1

            if id_origen:
                self.cli_por_id[norm(id_origen)] = id_local
            if codigo:
                self.cli_por_codigo[norm(codigo)] = id_local
            if nif:
                self.cli_por_nif[norm(nif)] = id_local
            if nombre:
                self.cli_por_nombre[norm(nombre)] = id_local

        self.totales["clientes"][0] += nuevos
        self.totales["clientes"][1] += actualizados
        self.log("  %-34s clientes: %d nuevos, %d actualizados"
                 % (nombre_archivo, nuevos, actualizados))

    def cargar_clientes_existentes(self, cur):
        """Indexa tambien los clientes que ya estaban en el programa."""
        info = info_columnas(cur, "clientes")
        cols = mapa_normalizado(info)
        pk = clave_primaria(info)
        columna_nombre = col(cols, CLI_NOMBRE)
        columna_nif = col(cols, CLI_NIF)
        columna_codigo = col(cols, CLI_CODIGO)

        seleccion = ['"%s" AS id_local' % pk]
        if columna_nombre:
            seleccion.append('"%s" AS nombre' % columna_nombre)
        if columna_nif:
            seleccion.append('"%s" AS nif' % columna_nif)
        if columna_codigo:
            seleccion.append('"%s" AS codigo' % columna_codigo)

        cur.execute("SELECT %s FROM clientes" % ", ".join(seleccion))
        for fila in cur.fetchall():
            claves = fila.keys()
            id_local = fila["id_local"]
            if "nombre" in claves and texto(fila["nombre"]):
                self.cli_por_nombre.setdefault(norm(fila["nombre"]), id_local)
            if "nif" in claves and texto(fila["nif"]):
                self.cli_por_nif.setdefault(norm(fila["nif"]), id_local)
            if "codigo" in claves and texto(fila["codigo"]):
                self.cli_por_codigo.setdefault(norm(fila["codigo"]), id_local)

    def resolver_cliente(self, fila):
        for candidatas, indice in (
            (DOC_CLIENTE_ID, self.cli_por_id),
            (DOC_CLIENTE_COD, self.cli_por_codigo),
            (CLI_NIF, self.cli_por_nif),
            (DOC_CLIENTE_NOMBRE, self.cli_por_nombre),
        ):
            clave = norm(valor(fila, candidatas))
            if clave and clave in indice:
                return indice[clave]
        return None

    # ── articulos ──────────────────────────────────────────
    def importar_articulos(self, cur, nombre_archivo, filas):
        if not tabla_existe(cur, "articulos"):
            self.avisos.append("No existe la tabla articulos: se omite %s." % nombre_archivo)
            return
        asegurar_ebp_id(cur, "articulos")
        info = info_columnas(cur, "articulos")
        cols = mapa_normalizado(info)
        pk = clave_primaria(info)

        columna_ref = col(cols, ART_REFERENCIA)
        columna_desc = col(cols, ART_DESCRIPCION)
        columna_precio = col(cols, ART_PRECIO)
        columna_coste = col(cols, ART_COSTE)
        columna_iva = col(cols, ART_IVA)
        columna_familia = col(cols, ART_FAMILIA)
        columna_stock = col(cols, ART_STOCK)
        columna_unidad = col(cols, ART_UNIDAD)

        nuevos = actualizados = 0
        for indice, fila in enumerate(filas, start=1):
            referencia = valor(fila, ART_REFERENCIA)
            descripcion = valor(fila, ART_DESCRIPCION)
            if not (referencia or descripcion):
                continue
            ebp_id = "art:" + (norm(referencia) or norm(descripcion) or str(indice))

            datos = {}
            if columna_ref:
                datos[columna_ref] = referencia or ("ART%05d" % indice)
            if columna_desc:
                datos[columna_desc] = descripcion or referencia
            if columna_precio:
                datos[columna_precio] = numero(valor(fila, ART_PRECIO))
            if columna_coste:
                datos[columna_coste] = numero(valor(fila, ART_COSTE))
            if columna_iva:
                datos[columna_iva] = numero(valor(fila, ART_IVA), 21.0)
            if columna_familia:
                datos[columna_familia] = valor(fila, ART_FAMILIA)
            if columna_stock:
                datos[columna_stock] = numero(valor(fila, ART_STOCK))
            if columna_unidad:
                datos[columna_unidad] = valor(fila, ART_UNIDAD)
            if "activo" in info:
                datos["activo"] = 1

            id_local, creado = upsert(cur, "articulos", info, pk, datos, ebp_id)
            if creado:
                nuevos += 1
            else:
                actualizados += 1
            if referencia:
                self.arts_por_referencia[norm(referencia)] = id_local

        self.totales["articulos"][0] += nuevos
        self.totales["articulos"][1] += actualizados
        self.log("  %-34s articulos: %d nuevos, %d actualizados"
                 % (nombre_archivo, nuevos, actualizados))

    # ── documentos ─────────────────────────────────────────
    def _preparar_documentos(self, cur):
        asegurar_ebp_id(cur, "documentos")
        info = info_columnas(cur, "documentos")
        cols = mapa_normalizado(info)
        destino = {
            "pk": clave_primaria(info),
            "numero": col(cols, DOC_NUMERO),
            "fecha": col(cols, DOC_FECHA),
            "tipo": col(cols, DOC_TIPO),
            "cliente": col(cols, ("clienteid", "idcliente", "cliente", "terceroid")),
            "empresa": col(cols, ("empresaid", "idempresa", "empresa")),
            "base": col(cols, DOC_BASE),
            "iva": col(cols, DOC_IVA),
            "total": col(cols, DOC_TOTAL),
            "estado": col(cols, DOC_ESTADO),
            "notas": col(cols, CLI_NOTAS),
        }
        return info, destino

    def _empresa_por_defecto(self, cur):
        if not tabla_existe(cur, "empresas"):
            return None
        info = info_columnas(cur, "empresas")
        cols = mapa_normalizado(info)
        pk = clave_primaria(info)
        marca = col(cols, ("predeterminada", "espredeterminada", "pordefecto", "defecto"))
        if marca:
            cur.execute('SELECT "%s" FROM empresas WHERE "%s" = 1 LIMIT 1' % (pk, marca))
            fila = cur.fetchone()
            if fila:
                return fila[0]
        cur.execute('SELECT "%s" FROM empresas ORDER BY "%s" LIMIT 1' % (pk, pk))
        fila = cur.fetchone()
        return fila[0] if fila else None

    def _guardar_documento(self, cur, info, destino, fila, nombre_archivo,
                           ebp_id, empresa_id, contador):
        numero_doc = valor(fila, DOC_NUMERO)
        tipo = (tipo_desde_valor(valor(fila, DOC_TIPO))
                or tipo_desde_numero(numero_doc)
                or tipo_desde_nombre_archivo(nombre_archivo))
        if not tipo:
            tipo = "factura"
            self.avisos.append(
                "Documento %s sin tipo reconocible: guardado como factura."
                % (numero_doc or ebp_id)
            )

        datos = {}
        if destino["numero"]:
            datos[destino["numero"]] = numero_doc or ("EBP-%05d" % contador)
        if destino["fecha"]:
            datos[destino["fecha"]] = fecha(valor(fila, DOC_FECHA)) or \
                datetime.now().strftime("%Y-%m-%d")
        if destino["tipo"]:
            datos[destino["tipo"]] = tipo
        if destino["cliente"]:
            datos[destino["cliente"]] = self.resolver_cliente(fila)
        if destino["empresa"] and empresa_id is not None:
            datos[destino["empresa"]] = empresa_id
        if destino["base"]:
            datos[destino["base"]] = numero(valor(fila, DOC_BASE))
        if destino["iva"]:
            datos[destino["iva"]] = numero(valor(fila, DOC_IVA))
        if destino["total"]:
            datos[destino["total"]] = numero(valor(fila, DOC_TOTAL))
        if destino["notas"]:
            datos[destino["notas"]] = valor(fila, CLI_NOTAS)

        id_local, creado = upsert(cur, "documentos", info, destino["pk"], datos, ebp_id)
        self.por_tipo[tipo] = self.por_tipo.get(tipo, 0) + 1
        if id_local not in self.docs_migrados:
            self.docs_migrados.append(id_local)

        for clave in (norm(valor(fila, ID_UNICO)), norm(numero_doc)):
            if clave:
                self.doc_por_clave[clave] = id_local
        return id_local, creado

    def importar_documentos(self, cur, nombre_archivo, filas):
        info, destino = self._preparar_documentos(cur)
        empresa_id = self._empresa_por_defecto(cur) if destino["empresa"] else None
        if destino["empresa"] and empresa_id is None:
            self.avisos.append(
                "No hay ninguna empresa emisora dada de alta; los documentos quedan "
                "sin empresa. Crea la empresa en la seccion Empresas y reimporta."
            )

        nuevos = actualizados = 0
        for indice, fila in enumerate(filas, start=1):
            id_origen = valor(fila, ID_UNICO)
            numero_doc = valor(fila, DOC_NUMERO)
            if not (id_origen or numero_doc):
                continue
            ebp_id = "doc:" + (id_origen or norm(numero_doc))
            _, creado = self._guardar_documento(
                cur, info, destino, fila, nombre_archivo, ebp_id, empresa_id, indice
            )
            if creado:
                nuevos += 1
            else:
                actualizados += 1

        self.totales["documentos"][0] += nuevos
        self.totales["documentos"][1] += actualizados
        self.log("  %-34s documentos: %d nuevos, %d actualizados"
                 % (nombre_archivo, nuevos, actualizados))

    # ── lineas ─────────────────────────────────────────────
    def _preparar_lineas(self, cur):
        tabla = primera_tabla(cur, self.TABLAS_LINEAS)
        if not tabla:
            return None, None, None
        asegurar_ebp_id(cur, tabla)
        info = info_columnas(cur, tabla)
        cols = mapa_normalizado(info)
        destino = {
            "pk": clave_primaria(info),
            "documento": col(cols, ("documentoid", "iddocumento", "documento", "facturaid")),
            "articulo": col(cols, ("articuloid", "idarticulo", "articulo")),
            "referencia": col(cols, ("referencia", "codigo", "ref", "refarticulo")),
            "descripcion": col(cols, LIN_DESCRIPCION),
            "cantidad": col(cols, LIN_CANTIDAD),
            "precio": col(cols, LIN_PRECIO),
            "descuento": col(cols, LIN_DESCUENTO),
            "iva": col(cols, LIN_IVA),
            "total": col(cols, LIN_TOTAL),
            "orden": col(cols, LIN_ORDEN),
        }
        return tabla, info, destino

    def _guardar_linea(self, cur, tabla, info, destino, fila, ebp_id,
                       documento_local, orden):
        cantidad = numero(valor(fila, LIN_CANTIDAD), 1.0)
        precio = numero(valor(fila, LIN_PRECIO))
        descuento = numero(valor(fila, LIN_DESCUENTO))
        iva = numero(valor(fila, LIN_IVA), 21.0)
        total = numero(valor(fila, LIN_TOTAL))
        if not total:
            total = round(cantidad * precio * (1.0 - descuento / 100.0), 2)
        referencia = valor(fila, LIN_REFERENCIA)
        descripcion = valor(fila, LIN_DESCRIPCION) or referencia

        datos = {}
        if destino["documento"]:
            datos[destino["documento"]] = documento_local
        if destino["referencia"]:
            datos[destino["referencia"]] = referencia
        if destino["descripcion"]:
            datos[destino["descripcion"]] = descripcion
        if destino["cantidad"]:
            datos[destino["cantidad"]] = cantidad
        if destino["precio"]:
            datos[destino["precio"]] = precio
        if destino["descuento"]:
            datos[destino["descuento"]] = descuento
        if destino["iva"]:
            datos[destino["iva"]] = iva
        if destino["total"]:
            datos[destino["total"]] = total
        if destino["orden"]:
            datos[destino["orden"]] = int(numero(valor(fila, LIN_ORDEN), orden))
        if destino["articulo"] and referencia:
            id_articulo = self.arts_por_referencia.get(norm(referencia))
            if id_articulo is not None:
                datos[destino["articulo"]] = id_articulo

        return upsert(cur, tabla, info, destino["pk"], datos, ebp_id)

    def importar_lineas(self, cur, nombre_archivo, filas):
        tabla, info, destino = self._preparar_lineas(cur)
        if not tabla:
            self.avisos.append(
                "No encuentro la tabla de lineas del programa, asi que los documentos "
                "quedan sin detalle. Dime como se llama y lo ajusto."
            )
            return
        if not destino["documento"]:
            self.avisos.append(
                "La tabla %s no tiene columna de documento: no se pueden vincular las lineas."
                % tabla
            )
            return

        nuevas = actualizadas = huerfanas = 0
        for indice, fila in enumerate(filas, start=1):
            clave_doc = norm(valor(fila, LIN_DOC_REF))
            documento_local = self.doc_por_clave.get(clave_doc)
            if documento_local is None:
                huerfanas += 1
                continue
            id_origen = valor(fila, ID_UNICO)
            ebp_id = "lin:" + (id_origen or "%s:%d" % (clave_doc, indice))
            _, creada = self._guardar_linea(
                cur, tabla, info, destino, fila, ebp_id, documento_local, indice
            )
            if creada:
                nuevas += 1
            else:
                actualizadas += 1

        self.totales["lineas"][0] += nuevas
        self.totales["lineas"][1] += actualizadas
        if huerfanas:
            self.avisos.append(
                "%s: %d lineas no encontraron su documento y se han omitido."
                % (nombre_archivo, huerfanas)
            )
        self.log("  %-34s lineas: %d nuevas, %d actualizadas"
                 % (nombre_archivo, nuevas, actualizadas))

    # ── archivo plano: documento + linea en la misma fila ──
    def importar_mixto(self, cur, nombre_archivo, filas):
        info_doc, destino_doc = self._preparar_documentos(cur)
        tabla_lineas, info_lin, destino_lin = self._preparar_lineas(cur)
        empresa_id = self._empresa_por_defecto(cur) if destino_doc["empresa"] else None

        grupos = {}
        orden_grupos = []
        for fila in filas:
            clave = norm(valor(fila, ID_UNICO)) or norm(valor(fila, LIN_DOC_REF)) \
                or norm(valor(fila, DOC_NUMERO))
            if not clave:
                continue
            if clave not in grupos:
                grupos[clave] = []
                orden_grupos.append(clave)
            grupos[clave].append(fila)

        docs_nuevos = docs_act = lin_nuevas = lin_act = 0

        for posicion, clave in enumerate(orden_grupos, start=1):
            bloque = grupos[clave]
            cabecera = bloque[0]
            ebp_id_doc = "doc:" + clave
            documento_local, creado = self._guardar_documento(
                cur, info_doc, destino_doc, cabecera, nombre_archivo,
                ebp_id_doc, empresa_id, posicion
            )
            if creado:
                docs_nuevos += 1
            else:
                docs_act += 1

            if not tabla_lineas or not destino_lin["documento"]:
                continue

            for indice, fila in enumerate(bloque, start=1):
                if not (valor(fila, LIN_DESCRIPCION) or valor(fila, LIN_REFERENCIA)
                        or valor(fila, LIN_CANTIDAD)):
                    continue
                ebp_id_lin = "lin:%s:%d" % (clave, indice)
                _, creada = self._guardar_linea(
                    cur, tabla_lineas, info_lin, destino_lin, fila,
                    ebp_id_lin, documento_local, indice
                )
                if creada:
                    lin_nuevas += 1
                else:
                    lin_act += 1

        self.totales["documentos"][0] += docs_nuevos
        self.totales["documentos"][1] += docs_act
        self.totales["lineas"][0] += lin_nuevas
        self.totales["lineas"][1] += lin_act
        self.log("  %-34s documentos: %d nuevos / lineas: %d nuevas"
                 % (nombre_archivo, docs_nuevos, lin_nuevas))

    # ── articulos deducidos de las lineas ──────────────────
    def deducir_articulos(self, cur):
        if not tabla_existe(cur, "articulos"):
            return
        tabla_lineas, info_lin, destino_lin = self._preparar_lineas(cur)
        if not tabla_lineas or not destino_lin["referencia"]:
            return

        asegurar_ebp_id(cur, "articulos")
        info = info_columnas(cur, "articulos")
        cols = mapa_normalizado(info)
        pk = clave_primaria(info)
        columna_ref = col(cols, ART_REFERENCIA)
        if not columna_ref:
            return
        columna_desc = col(cols, ART_DESCRIPCION)
        columna_precio = col(cols, ART_PRECIO)
        columna_iva = col(cols, ART_IVA)

        seleccion = ['"%s" AS referencia' % destino_lin["referencia"]]
        if destino_lin["descripcion"]:
            seleccion.append('MAX("%s") AS descripcion' % destino_lin["descripcion"])
        if destino_lin["precio"]:
            seleccion.append('MAX("%s") AS precio' % destino_lin["precio"])
        if destino_lin["iva"]:
            seleccion.append('MAX("%s") AS iva' % destino_lin["iva"])

        cur.execute(
            'SELECT %s FROM "%s" WHERE TRIM(COALESCE("%s", \'\')) <> \'\' GROUP BY "%s"'
            % (", ".join(seleccion), tabla_lineas,
               destino_lin["referencia"], destino_lin["referencia"])
        )
        nuevos = 0
        for fila in cur.fetchall():
            claves = fila.keys()
            referencia = texto(fila["referencia"])
            if not referencia or norm(referencia) in self.arts_por_referencia:
                continue

            cur.execute(
                'SELECT "%s" FROM articulos WHERE "%s" = ? LIMIT 1' % (pk, columna_ref),
                (referencia,),
            )
            if cur.fetchone():
                continue

            datos = {columna_ref: referencia}
            if columna_desc:
                descripcion = texto(fila["descripcion"]) if "descripcion" in claves else ""
                datos[columna_desc] = descripcion or referencia
            if columna_precio and "precio" in claves:
                datos[columna_precio] = numero(fila["precio"])
            if columna_iva and "iva" in claves:
                datos[columna_iva] = numero(fila["iva"], 21.0)
            if "activo" in info:
                datos["activo"] = 1

            id_local, creado = upsert(cur, "articulos", info, pk, datos,
                                      "art:ref:" + norm(referencia))
            self.arts_por_referencia[norm(referencia)] = id_local
            if creado:
                nuevos += 1

        if nuevos:
            self.totales["articulos"][0] += nuevos
            self.log("  %-34s articulos deducidos de las lineas: %d"
                     % ("(catalogo)", nuevos))

    # ── totales de cabecera ────────────────────────────────
    def recalcular_totales(self, cur):
        if not self.docs_migrados:
            return
        info_doc = info_columnas(cur, "documentos")
        cols_doc = mapa_normalizado(info_doc)
        pk_doc = clave_primaria(info_doc)
        columna_base = col(cols_doc, DOC_BASE)
        columna_iva = col(cols_doc, DOC_IVA)
        columna_total = col(cols_doc, DOC_TOTAL)
        if not (columna_base or columna_iva or columna_total):
            return

        tabla_lineas, _, destino_lin = self._preparar_lineas(cur)
        if not tabla_lineas or not destino_lin["documento"] or not destino_lin["total"]:
            return

        columna_iva_linea = destino_lin["iva"]
        ajustados = 0

        for id_doc in self.docs_migrados:
            seleccion = 'SUM("%s") AS base' % destino_lin["total"]
            if columna_iva_linea:
                seleccion += ', SUM("%s" * COALESCE("%s", 0) / 100.0) AS cuota' % (
                    destino_lin["total"], columna_iva_linea
                )
            cur.execute(
                'SELECT %s FROM "%s" WHERE "%s" = ?'
                % (seleccion, tabla_lineas, destino_lin["documento"]),
                (id_doc,),
            )
            fila = cur.fetchone()
            if not fila or fila["base"] is None:
                continue
            base = round(float(fila["base"]), 2)
            cuota = round(float(fila["cuota"]), 2) if "cuota" in fila.keys() \
                and fila["cuota"] is not None else 0.0

            actuales = {}
            comprobar = [c for c in (columna_base, columna_iva, columna_total) if c]
            cur.execute(
                'SELECT %s FROM documentos WHERE "%s" = ?'
                % (", ".join('"%s"' % c for c in comprobar), pk_doc),
                (id_doc,),
            )
            registro = cur.fetchone()
            if registro:
                for columna in comprobar:
                    actuales[columna] = numero(registro[columna])

            datos = {}
            if columna_base and not actuales.get(columna_base):
                datos[columna_base] = base
            if columna_iva and not actuales.get(columna_iva):
                datos[columna_iva] = cuota
            if columna_total and not actuales.get(columna_total):
                datos[columna_total] = round(base + cuota, 2)
            if not datos:
                continue

            asignaciones = ", ".join('"%s" = ?' % c for c in datos)
            cur.execute(
                'UPDATE documentos SET %s WHERE "%s" = ?' % (asignaciones, pk_doc),
                list(datos.values()) + [id_doc],
            )
            ajustados += 1

        if ajustados:
            self.log("  %-34s totales recalculados en %d documentos"
                     % ("(cabeceras)", ajustados))


# ═════════════════════════════════════════════════════════════
#  INTERFAZ GRAFICA
# ═════════════════════════════════════════════════════════════
try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import (
        QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
        QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
    )
    PYQT_DISPONIBLE = True
except ImportError:  # permite usar el modulo sin PyQt instalado
    PYQT_DISPONIBLE = False


if PYQT_DISPONIBLE:

    class PanelImportacionEBP(QWidget):
        """Panel reutilizable: sirve como seccion del programa o dentro de un dialogo."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.carpeta = ""
            self._construir()

        def _construir(self):
            raiz = QVBoxLayout(self)
            raiz.setContentsMargins(20, 20, 20, 20)
            raiz.setSpacing(12)

            titulo = QLabel("Importar datos de EBP")
            fuente = QFont()
            fuente.setPointSize(16)
            fuente.setBold(True)
            titulo.setFont(fuente)
            raiz.addWidget(titulo)

            explicacion = QLabel(
                "Selecciona la carpeta donde tienes los CSV exportados de EBP. "
                "Se detecta automaticamente que contiene cada archivo y los datos "
                "se guardan en las mismas tablas que usa el programa, asi que "
                "apareceran en Clientes, Articulos, Presupuestos, Albaranes y Facturas.\n"
                "Antes de escribir nada se hace una copia de seguridad en la carpeta "
                "backups. Puedes importar varias veces sin duplicar registros."
            )
            explicacion.setWordWrap(True)
            raiz.addWidget(explicacion)

            fila = QHBoxLayout()
            self.campo_carpeta = QLineEdit()
            self.campo_carpeta.setReadOnly(True)
            self.campo_carpeta.setPlaceholderText("Ninguna carpeta seleccionada")
            self.campo_carpeta.setMinimumHeight(32)
            self.campo_carpeta.setAccessibleName("Carpeta con los CSV de EBP")
            fila.addWidget(self.campo_carpeta, 1)

            self.boton_elegir = QPushButton("Elegir carpeta…")
            self.boton_elegir.setMinimumHeight(32)
            self.boton_elegir.clicked.connect(self.elegir_carpeta)
            fila.addWidget(self.boton_elegir)
            raiz.addLayout(fila)

            self.registro = QPlainTextEdit()
            self.registro.setReadOnly(True)
            self.registro.setMinimumHeight(300)
            self.registro.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            self.registro.setFont(QFont("Consolas", 9))
            self.registro.setAccessibleName("Resultado de la importacion")
            self.registro.setPlaceholderText(
                "Aqui se mostrara el detalle de la importacion."
            )
            raiz.addWidget(self.registro, 1)

            botones = QHBoxLayout()
            botones.addStretch(1)
            self.boton_importar = QPushButton("Importar")
            self.boton_importar.setMinimumHeight(36)
            self.boton_importar.setMinimumWidth(130)
            self.boton_importar.setDefault(True)
            self.boton_importar.setEnabled(False)
            self.boton_importar.clicked.connect(self.importar)
            botones.addWidget(self.boton_importar)
            raiz.addLayout(botones)

        def escribir(self, mensaje=""):
            self.registro.appendPlainText(mensaje)
            self.registro.verticalScrollBar().setValue(
                self.registro.verticalScrollBar().maximum()
            )
            QApplication.processEvents()

        def elegir_carpeta(self):
            inicio = self.carpeta or BASE_DIR
            elegida = QFileDialog.getExistingDirectory(
                self, "Carpeta con los CSV exportados de EBP", inicio
            )
            if not elegida:
                return
            self.carpeta = elegida
            self.campo_carpeta.setText(elegida)
            cuantos = len([n for n in os.listdir(elegida)
                           if n.lower().endswith((".csv", ".txt"))])
            self.registro.clear()
            self.escribir("Carpeta: %s" % elegida)
            self.escribir("Archivos CSV encontrados: %d" % cuantos)
            self.boton_importar.setEnabled(cuantos > 0)
            if cuantos == 0:
                self.escribir("")
                self.escribir("No hay archivos .csv en esa carpeta. Elige la carpeta "
                              "donde EBP dejo la exportacion.")

        def importar(self):
            if not self.carpeta:
                return
            confirmacion = QMessageBox.question(
                self,
                "Confirmar importacion",
                "Se van a escribir los datos de EBP en la base de datos del programa.\n\n"
                "Antes se guardara una copia de seguridad en la carpeta 'backups'.\n\n"
                "¿Continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if confirmacion != QMessageBox.StandardButton.Yes:
                return

            self.registro.clear()
            self.boton_importar.setEnabled(False)
            self.boton_elegir.setEnabled(False)
            self.setCursor(Qt.CursorShape.WaitCursor)
            try:
                importador = Importador(self.carpeta, registrar=self.escribir)
                correcto = importador.ejecutar()
            finally:
                self.unsetCursor()
                self.boton_importar.setEnabled(True)
                self.boton_elegir.setEnabled(True)

            if correcto:
                QMessageBox.information(
                    self, "Importacion terminada",
                    "Los datos ya estan en la base de datos del programa.\n\n"
                    "Entra en Clientes, Articulos, Presupuestos, Albaranes o Facturas "
                    "para verlos. Revisa el detalle por si hay avisos."
                )
            else:
                QMessageBox.warning(
                    self, "La importacion no se completo",
                    "No se ha guardado nada. Revisa el detalle de la ventana para ver "
                    "el motivo."
                )

    class DialogoImportacionEBP(QDialog):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Importar datos de EBP")
            self.setMinimumSize(760, 560)
            disposicion = QVBoxLayout(self)
            disposicion.setContentsMargins(0, 0, 0, 0)
            self.panel = PanelImportacionEBP(self)
            disposicion.addWidget(self.panel)

            cierre = QHBoxLayout()
            cierre.setContentsMargins(20, 0, 20, 16)
            cierre.addStretch(1)
            boton_cerrar = QPushButton("Cerrar")
            boton_cerrar.setMinimumHeight(32)
            boton_cerrar.clicked.connect(self.accept)
            cierre.addWidget(boton_cerrar)
            disposicion.addLayout(cierre)

    def abrir_dialogo_importacion(parent=None):
        dialogo = DialogoImportacionEBP(parent)
        return dialogo.exec()

    # Alias por si el cargador de secciones del programa usa otro nombre
    def crear_widget(parent=None):
        return PanelImportacionEBP(parent)

    def get_widget(parent=None):
        return PanelImportacionEBP(parent)

    def crear_vista(parent=None):
        return PanelImportacionEBP(parent)

    Widget = PanelImportacionEBP
    Vista = PanelImportacionEBP
    Pantalla = PanelImportacionEBP
    ImportacionEBPWidget = PanelImportacionEBP


# ═════════════════════════════════════════════════════════════
#  EJECUCION INDEPENDIENTE
# ═════════════════════════════════════════════════════════════
def main():
    if PYQT_DISPONIBLE and "--consola" not in sys.argv:
        aplicacion = QApplication.instance() or QApplication(sys.argv)
        dialogo = DialogoImportacionEBP()
        dialogo.show()
        return aplicacion.exec()

    carpeta = ""
    for argumento in sys.argv[1:]:
        if not argumento.startswith("--"):
            carpeta = argumento
            break
    if not carpeta:
        carpeta = input("Ruta de la carpeta con los CSV de EBP: ").strip().strip('"')
    if not os.path.isdir(carpeta):
        print("ERROR: la carpeta indicada no existe.")
        return 1

    importador = Importador(carpeta, registrar=print)
    return 0 if importador.ejecutar() else 1


if __name__ == "__main__":
    codigo = main()
    try:
        input("\nPulsa Enter para cerrar...")
    except EOFError:
        pass
    sys.exit(codigo)