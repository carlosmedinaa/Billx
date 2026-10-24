import logging
import math
import os
from datetime import datetime
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics

from calculos import calcular_documento, redondear
from database import obtener_documento_completo, obtener

log = logging.getLogger("billx")


def _num(valor, decimales=2):
    """Numero con coma decimal (sin separador de miles), como el resto del PDF."""
    return f"{valor:.{decimales}f}".replace(".", ",")


def _miles(valor):
    """1234567.8 -> '1.234.567,80' (para el listado, donde los totales son grandes)."""
    return f"{valor:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def dibujar_marca_agua(c, texto, ancho, alto, margen=0.85, tamano_maximo=90):
    """Marca de agua en la diagonal de la pagina, con el tamano justo para que
    el texto quepa ENTERO (sea largo o corto) dentro del margen indicado."""
    fuente = "Helvetica-Bold"
    angulo = math.atan2(alto, ancho)
    cos_a, sin_a = math.cos(angulo), math.sin(angulo)
    ancho_texto = pdfmetrics.stringWidth(texto, fuente, 1)   # por punto de tamano
    alto_texto = 0.72                                          # altura de mayusculas aprox.
    # Caja del texto girado: ancho*cos + alto*sin <= ancho pagina (y lo mismo en vertical)
    tamano = min(
        margen * ancho / (ancho_texto * cos_a + alto_texto * sin_a),
        margen * alto / (ancho_texto * sin_a + alto_texto * cos_a),
        tamano_maximo,
    )
    c.saveState()
    c.translate(ancho / 2, alto / 2)
    c.rotate(math.degrees(angulo))
    c.setFont(fuente, tamano)
    c.setFillColorRGB(0.92, 0.92, 0.92)  # Gris muy claro estilo marca de agua real
    c.drawCentredString(0, -tamano * alto_texto / 2, texto)   # centrada tambien en vertical
    c.restoreState()


def _parrafo(texto, estilo):
    """Paragraph interpreta su texto como XML: sin escapar, un '&' o un '<'
    en la descripcion rompe el PDF. Los saltos de linea se respetan."""
    return Paragraph(escape(str(texto or "")).replace("\n", "<br/>"), estilo)


def generar_pdf(documento_id, ruta_salida):
    doc = obtener_documento_completo(documento_id)
    if not doc:
        raise ValueError("El documento no existe.")

    empresa = obtener("empresas", doc["empresa_id"])
    if not empresa:
        raise ValueError("La empresa emisora ya no existe.")

    cliente = obtener("clientes", doc["cliente_id"])
    if not cliente:
        cliente = {}

    c = canvas.Canvas(ruta_salida, pagesize=A4)
    ancho, alto = A4
    margen_izq = 1.5 * cm
    margen_der = ancho - 1.5 * cm

    # --- MARCA DE AGUA ---
    estado = doc.get("estado", "")
    if estado != "Pagada":
        texto_agua = "EN CURSO DE REDACCIÓN" if estado == "Borrador" else "NO ABONADO"
        dibujar_marca_agua(c, texto_agua, ancho, alto)

    # --- CABECERA EMPRESA (Arriba Izquierda) ---
    y_empresa = alto - 1.5 * cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margen_izq, y_empresa, empresa.get("nombre", "").upper())
    
    y_empresa -= 0.5 * cm
    c.setFont("Helvetica", 8)
    if empresa.get("direccion"):
        c.drawString(margen_izq, y_empresa, empresa.get("direccion", ""))
        y_empresa -= 0.4 * cm
    c.drawString(margen_izq, y_empresa, f"{empresa.get('cp', '')} {empresa.get('ciudad', '').upper()}")
    
    y_empresa -= 0.6 * cm
    
    # Función para alinear perfectamente las etiquetas y sus valores
    def dibujar_etiqueta_valor(etiqueta, valor, y_pos):
        if valor:
            c.setFont("Helvetica-Bold", 8)
            c.drawString(margen_izq, y_pos, etiqueta)
            c.setFont("Helvetica", 8)
            c.drawString(margen_izq + 1.2 * cm, y_pos, valor)
            return y_pos - 0.4 * cm
        return y_pos

    y_empresa = dibujar_etiqueta_valor("Telf:", empresa.get("telefono", ""), y_empresa)
    y_empresa = dibujar_etiqueta_valor("Email:", empresa.get("email", ""), y_empresa)
    y_empresa = dibujar_etiqueta_valor("Web:", empresa.get("web", ""), y_empresa)
    y_empresa = dibujar_etiqueta_valor("CIF/NIF:", empresa.get("nif", ""), y_empresa)

    # --- LOGO (Arriba Derecha) ---
    logo_path = empresa.get("logo", "")
    if logo_path and os.path.isfile(logo_path):
        try:
            c.drawImage(logo_path, ancho - 6.5 * cm, alto - 3.5 * cm, width=5*cm, height=2.5*cm, preserveAspectRatio=True, anchor='ne')
        except Exception:
            pass

    # --- DATOS DEL CLIENTE (Centro Derecha) ---
    y_cliente = alto - 4.5 * cm
    c.setFont("Helvetica", 9)
    
    lineas_cliente = [
        doc.get("cliente_nombre", ""),
        doc.get("cliente_direccion", ""),
        f"{doc.get('cliente_cp', '')} {doc.get('cliente_ciudad', '')}",
        doc.get("cliente_nif", "")
    ]
    
    x_cliente = ancho / 2 + 1 * cm
    for linea in lineas_cliente:
        if linea.strip():
            c.drawString(x_cliente, y_cliente, linea)
            y_cliente -= 0.4 * cm

    # --- TÍTULO (Caja Gris) ---
    y_titulo = alto - 8.5 * cm
    c.setFillColorRGB(0.9, 0.9, 0.9)
    c.rect(margen_izq, y_titulo - 0.25 * cm, 6 * cm, 0.8 * cm, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 14)
    
    titulo_txt = doc["tipo"].capitalize()
    if estado == "Borrador":
        titulo_txt += " en curso"
    c.drawString(margen_izq + 0.2 * cm, y_titulo, titulo_txt)

    # --- TABLA META INFO ---
    def fecha_es(texto):
        try:
            return datetime.strptime(texto, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return texto or ""

    # Vencimiento y forma de pago son los GUARDADOS en el documento: la ficha
    # actual del cliente puede haber cambiado desde que se emitio.
    fecha_str = fecha_es(doc.get("fecha"))
    vto_str = fecha_es(doc.get("fecha_vencimiento")) or fecha_str

    meta_data = [
        ["Número", "Fecha", "Código cliente", "Vencimiento", "Forma de pago", "CIF/NIF"],
        [doc["numero"], fecha_str, cliente.get("codigo", ""), vto_str, doc.get("forma_pago", ""), doc.get("cliente_nif", "")]
    ]
    
    meta_table = Table(meta_data, colWidths=[2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 4.5*cm, 3.5*cm])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, 1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    w_meta, h_meta = meta_table.wrap(ancho, alto)
    y_meta = y_titulo - 1.0 * cm - h_meta
    meta_table.drawOn(c, margen_izq, y_meta)

    # Fecha de entrega (Como en tu foto de referencia)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(margen_izq, y_meta - 0.5 * cm, f"Fecha de entrega: {fecha_str}")

    # --- TABLA DE LÍNEAS DE ARTÍCULOS ---
    lines_data = [["Descripción", "Cant.", "Código", "P.U. sin IVA", "Dto %", "Importe", "IVA"]]

    calculo = calcular_documento(
        doc.get("lineas", []),
        exento_iva=doc.get("exento_iva"),
        recargo_equivalencia=doc.get("recargo_equivalencia"),
        porcentaje_irpf=doc.get("porcentaje_irpf"),
    )
    if calculo["total"] != redondear(doc.get("total")):
        # Documentos antiguos calculados con la version anterior (sin descuento por linea)
        log.warning("Documento %s: total guardado %s y recalculado %s no coinciden",
                    doc.get("numero"), doc.get("total"), calculo["total"])

    # Recargo y retencion anaden filas a la tabla de totales: se sube todo el
    # bloque inferior para que no pise el pie de pagina.
    filas_extra = (calculo["total_recargo"] > 0) + (calculo["total_retencion"] > 0)
    subida = filas_extra * 0.6 * cm

    # Preparar el estilo para que los textos largos salten de línea (Párrafos)
    estilos = getSampleStyleSheet()
    estilo_desc = estilos["Normal"]
    estilo_desc.fontSize = 8
    estilo_desc.leading = 10

    for linea in calculo["lineas"]:
        lines_data.append([
            _parrafo(linea.get("descripcion", ""), estilo_desc), # Párrafo: los textos largos saltan de línea
            _num(linea.get("cantidad") or 0),
            linea.get("referencia", ""),
            _num(linea.get("precio_unitario") or 0),
            _num(linea.get("porcentaje_descuento") or 0) if linea.get("porcentaje_descuento") else "",
            _num(linea["importe"]),
            _num(linea["porcentaje_iva_aplicado"]) + "%",
        ])

    col_widths = [6.5*cm, 1.5*cm, 2.2*cm, 2.3*cm, 1.3*cm, 2.5*cm, 1.7*cm]
    
    # CÁLCULO INTELIGENTE DEL ESPACIO:
    # La tabla empezará en 'y_lines_top' y queremos que termine exactamente en 'y_bottom_area'
    y_lines_top = y_meta - 0.8 * cm
    y_bottom_area = 7.0 * cm + subida
    
    available_height = y_lines_top - y_bottom_area
    
    # Medimos cuánto ocupa realmente la tabla con los datos actuales
    temp_table = Table(lines_data, colWidths=col_widths)
    temp_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    _, h_data = temp_table.wrap(ancho, alto)
    
    # Si sobra espacio, añadimos una fila transparente que estire la tabla hacia abajo
    filler_height = available_height - h_data
    if filler_height > 0:
        lines_data.append([""] * len(col_widths))
        row_heights = [None] * (len(lines_data) - 1) + [filler_height]
    else:
        row_heights = None

    lines_table = Table(lines_data, colWidths=col_widths, rowHeights=row_heights)
    
    style_lines = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (2, 1), (2, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
        ('GRID', (0, 0), (-1, 0), 0.5, colors.grey),
        ('LINEBEFORE', (1, 0), (-1, -1), 0.5, colors.grey), # Dibuja solo las verticales interiores
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]
    lines_table.setStyle(TableStyle(style_lines))

    w_lines, h_lines = lines_table.wrap(ancho, alto)
    y_lines = y_lines_top - h_lines
    lines_table.drawOn(c, margen_izq, y_lines)

    # --- TABLAS INFERIORES (Desglose IVA y TOTALES) ---
    # Posicionadas de forma fija a una distancia segura de la tabla principal
    y_bottom = 6.5 * cm + subida

    # Tabla Desglose IVA (Izquierda)
    con_recargo = calculo["total_recargo"] > 0
    iva_data = [["% IVA", "B.I.", "Importe IVA"] + (["% R.E.", "Importe R.E."] if con_recargo else [])]
    for grupo in calculo["desglose"]:
        fila = [_num(grupo["porcentaje_iva"]), _num(grupo["base"]), _num(grupo["cuota_iva"])]
        if con_recargo:
            fila += [_num(grupo["porcentaje_recargo"]), _num(grupo["cuota_recargo"])]
        iva_data.append(fila)
        
    while len(iva_data) < 3: # Asegurarnos que tenga algo de altura por estética
        iva_data.append([""] * len(iva_data[0]))

    anchos_iva = [1.5*cm, 2.5*cm, 2.5*cm] + ([1.5*cm, 2.2*cm] if con_recargo else [])
    iva_table = Table(iva_data, colWidths=anchos_iva)
    iva_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    w_iva, h_iva = iva_table.wrap(ancho, alto)
    iva_table.drawOn(c, margen_izq, y_bottom - h_iva)

    # Tabla Totales (Derecha)
    totales_data = [
        ["Total bruto sin IVA", _num(calculo["base_imponible"])],
        ["Total IVA", _num(calculo["total_iva"])],
    ]
    if con_recargo:
        totales_data.append(["Recargo de equivalencia", _num(calculo["total_recargo"])])
    totales_data.append(["Total con IVA", _num(calculo["base_imponible"] + calculo["total_iva"] + calculo["total_recargo"])])
    if calculo["total_retencion"] > 0:
        totales_data.append([f"Retención IRPF ({_num(calculo['porcentaje_irpf'])}%)", "-" + _num(calculo["total_retencion"])])
    totales_data.append(["Total a pagar", _num(calculo["total"]) + " €"])
    
    totales_table = Table(totales_data, colWidths=[4*cm, 3*cm])
    totales_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#e5e7eb")), 
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))

    w_totales, h_totales = totales_table.wrap(ancho, alto)
    totales_table.drawOn(c, margen_der - w_totales, y_bottom - h_totales)

    # --- PIE DE PÁGINA ---
    # Posicionado fijamente abajo del todo sin posibilidad de superponerse
    c.setFont("Helvetica", 7)
    pie_y = 3.0 * cm
    c.drawString(margen_izq, pie_y, "Descuento por pronto pago: 0%. Un interés de demora del 8% por retraso de pago puede ser aplicado.")
    
    c.drawCentredString(ancho / 2, 2.0 * cm, f"CIF/NIF: {empresa.get('nif', '')}")
    c.drawRightString(margen_der, 2.0 * cm, "1 de 1")

    c.save()

TITULOS_LISTADO = {"factura": "Facturas", "presupuesto": "Presupuestos", "albaran": "Albaranes"}


def generar_listado_pdf(documentos, ruta_salida, tipo_doc, fecha_inicio, fecha_fin):
    """Un unico PDF con el listado de documentos (una fila por documento) y sus totales.

    documentos: filas de la tabla documentos. Los importes son los GUARDADOS en
    cada documento (lo que se emitio), sumados con Decimal.
    """
    from reportlab.lib.pagesizes import landscape
    from reportlab.platypus import SimpleDocTemplate, Spacer

    estilos = getSampleStyleSheet()
    estilo_celda = estilos["Normal"].clone("celda_listado", fontSize=8, leading=10)

    def importe(doc, campo):
        return redondear(doc.get(campo))

    con_recargo = any(importe(d, "total_recargo") for d in documentos)
    con_retencion = any(importe(d, "total_retencion") for d in documentos)

    cabecera = ["Número", "Fecha", "Cliente", "NIF", "Base", "IVA"]
    campos = ["base_imponible", "total_iva"]
    if con_recargo:
        cabecera.append("Recargo")
        campos.append("total_recargo")
    if con_retencion:
        cabecera.append("Retención")
        campos.append("total_retencion")
    cabecera += ["Total", "Estado"]
    campos.append("total")

    def fecha_es(texto):
        try:
            return datetime.strptime(texto, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return texto or ""

    sumas = {campo: redondear(0) for campo in campos}
    filas = [cabecera]
    for doc in documentos:
        fila = [doc.get("numero", ""), fecha_es(doc.get("fecha")),
                _parrafo(doc.get("cliente_nombre", ""), estilo_celda), doc.get("cliente_nif", "")]
        for campo in campos:
            valor = importe(doc, campo)
            sumas[campo] += valor
            fila.append(("-" if campo == "total_retencion" and valor else "") + _miles(valor))
        fila.append(doc.get("estado", ""))
        filas.append(fila)
    fila_total = ["TOTAL", f"{len(documentos)} doc.", "", ""]
    fila_total += [("-" if c == "total_retencion" and sumas[c] else "") + _miles(sumas[c]) for c in campos]
    fila_total.append("")
    filas.append(fila_total)

    # Apaisado: ancho util 29,7 - 3 = 26,7 cm. La columna Cliente se queda lo que sobra.
    n_importes = len(campos)
    fijas = 2.6 + 2.2 + 2.6 + 2.4 * n_importes + 2.2
    anchos = [2.6*cm, 2.2*cm, (26.7 - fijas)*cm, 2.6*cm] + [2.4*cm] * n_importes + [2.2*cm]
    primera_importe = 4

    tabla = Table(filas, colWidths=anchos, repeatRows=1)
    tabla.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (primera_importe, 1), (primera_importe + n_importes - 1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor("#f9fafb")]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#e5e7eb")),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))

    titulo = "Listado de " + TITULOS_LISTADO.get(tipo_doc, tipo_doc).lower()
    periodo = f"Del {fecha_es(fecha_inicio)} al {fecha_es(fecha_fin)}"

    def pie(canvas_pdf, plantilla):
        canvas_pdf.saveState()
        canvas_pdf.setFont("Helvetica", 7)
        ancho_pag = plantilla.pagesize[0]
        canvas_pdf.drawString(1.5*cm, 1.0*cm, f"{titulo} · {periodo}")
        canvas_pdf.drawRightString(ancho_pag - 1.5*cm, 1.0*cm, f"Página {plantilla.page}")
        canvas_pdf.restoreState()

    plantilla = SimpleDocTemplate(
        ruta_salida, pagesize=landscape(A4), title=f"{titulo} - {periodo}",
        leftMargin=1.5*cm, rightMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.6*cm,
    )
    plantilla.build(
        [Paragraph(titulo, estilos["Title"]), Paragraph(periodo, estilos["Normal"]), Spacer(1, 0.4*cm), tabla],
        onFirstPage=pie, onLaterPages=pie,
    )
