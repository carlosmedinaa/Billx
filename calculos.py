"""Calculo de importes de documentos. UNICA fuente de verdad del dinero.

Todo se hace con Decimal y redondeo comercial (ROUND_HALF_UP) a 2 decimales.
Pantalla (documentos.py), guardado (database.guardar_documento) e impresion
(impresion.py) llaman a calcular_documento(), asi nunca pueden discrepar.

Reglas:
  importe de linea = cantidad x precio x (1 - dto% / 100), redondeado a 2 dec.
  base             = suma de importes, agrupada por tipo de IVA.
  cuota IVA        = base del grupo x %IVA, redondeada por grupo.
  cliente exento   = IVA 0 % y sin recargo de equivalencia.
  recargo de eq.   = 21 -> 5,2 %; 10 -> 1,4 %; 4 -> 0,5 % (sobre la base del grupo).
  retencion IRPF   = base total x %IRPF de la empresa emisora.
  total            = base + IVA + recargo - retencion.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENTIMO = Decimal("0.01")
CERO = Decimal("0")
CIEN = Decimal("100")

RECARGO_EQUIVALENCIA = {
    Decimal("21"): Decimal("5.2"),
    Decimal("10"): Decimal("1.4"),
    Decimal("4"): Decimal("0.5"),
}


def a_decimal(valor, por_defecto=CERO):
    """Convierte numeros, Decimal o texto ("1.234,56", "21 %", "10 €") a Decimal.

    Los float se convierten via str() para no arrastrar el error binario:
    1.005 (float) -> Decimal("1.005"), no Decimal("1.00499999...").
    """
    if valor is None or isinstance(valor, bool):
        return Decimal(por_defecto)
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, int):
        return Decimal(valor)
    if isinstance(valor, float):
        return Decimal(str(valor))
    texto = str(valor).strip()
    for sobra in ("%", "€", " ", " "):
        texto = texto.replace(sobra, "")
    if not texto:
        return Decimal(por_defecto)
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        resultado = Decimal(texto)
    except InvalidOperation:
        return Decimal(por_defecto)
    return resultado if resultado.is_finite() else Decimal(por_defecto)


def redondear(valor):
    return a_decimal(valor).quantize(CENTIMO, rounding=ROUND_HALF_UP)


def importe_linea(cantidad, precio, porcentaje_descuento=0):
    factor = 1 - a_decimal(porcentaje_descuento) / CIEN
    return redondear(a_decimal(cantidad) * a_decimal(precio) * factor)


def porcentaje_recargo(porcentaje_iva):
    return RECARGO_EQUIVALENCIA.get(a_decimal(porcentaje_iva).normalize(), CERO)


def calcular_documento(lineas, exento_iva=False, recargo_equivalencia=False, porcentaje_irpf=0):
    """Calcula lineas, desglose por IVA y totales de un documento.

    lineas: iterable de dicts con cantidad, precio_unitario, porcentaje_descuento
    y porcentaje_iva (valores numericos o texto). Devuelve un dict con:
      lineas            copia de cada linea + "importe" y "porcentaje_iva_aplicado"
      desglose          lista de grupos (de mayor a menor %IVA) con
                        porcentaje_iva, base, cuota_iva, porcentaje_recargo, cuota_recargo
      base_imponible, total_iva, total_recargo, porcentaje_irpf,
      total_retencion, total      (todos Decimal con 2 decimales)
    """
    exento = bool(int(exento_iva or 0))
    con_recargo = bool(int(recargo_equivalencia or 0)) and not exento
    pct_irpf = a_decimal(porcentaje_irpf)

    calculadas = []
    bases = {}
    for linea in lineas:
        importe = importe_linea(
            linea.get("cantidad", 0),
            linea.get("precio_unitario", 0),
            linea.get("porcentaje_descuento", 0),
        )
        pct_iva = CERO if exento else a_decimal(linea.get("porcentaje_iva", 0))
        # normalize() agrupa 21, 21.0 y 21.00 en el mismo tipo de IVA
        clave = pct_iva.normalize()
        bases[clave] = bases.get(clave, CERO) + importe
        calculada = dict(linea)
        calculada["importe"] = importe
        calculada["porcentaje_iva_aplicado"] = clave
        calculadas.append(calculada)

    desglose = []
    for pct_iva in sorted(bases, reverse=True):
        base = bases[pct_iva]
        pct_re = porcentaje_recargo(pct_iva) if con_recargo else CERO
        desglose.append({
            "porcentaje_iva": pct_iva,
            "base": base,
            "cuota_iva": redondear(base * pct_iva / CIEN),
            "porcentaje_recargo": pct_re,
            "cuota_recargo": redondear(base * pct_re / CIEN),
        })

    base_imponible = sum((g["base"] for g in desglose), CERO).quantize(CENTIMO)
    total_iva = sum((g["cuota_iva"] for g in desglose), CERO).quantize(CENTIMO)
    total_recargo = sum((g["cuota_recargo"] for g in desglose), CERO).quantize(CENTIMO)
    total_retencion = redondear(base_imponible * pct_irpf / CIEN)

    return {
        "lineas": calculadas,
        "desglose": desglose,
        "base_imponible": base_imponible,
        "total_iva": total_iva,
        "total_recargo": total_recargo,
        "porcentaje_irpf": pct_irpf,
        "total_retencion": total_retencion,
        "total": base_imponible + total_iva + total_recargo - total_retencion,
    }
