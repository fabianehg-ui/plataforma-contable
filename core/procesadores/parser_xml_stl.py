"""
core/procesadores/parser_xml_stl.py

Parser de XMLs UBL (facturas electrónicas DIAN) específicamente para el
flujo STL. Lee un ZIP que contiene los XMLs descargados manualmente del
portal DIAN y extrae:

  - Folio, fecha, NIT receptor, nombre receptor
  - Total, base sin IVA, total con IVA
  - LÍNEA POR LÍNEA: descripción, base, IVA, tarifa (19% / 5% / 0% / 8% INC)
  - Tipo de impuesto: IVA (01), INC (04)

A diferencia del Token DIAN (que solo trae totales globales), el XML
permite discriminar EXACTAMENTE cada línea con su tarifa real, lo que
da mucha más precisión al plano contable.

USO:

    from parser_xml_stl import procesar_zip_xmls_stl

    resultado = procesar_zip_xmls_stl(zip_bytes_o_path)
    # resultado['facturas'] = list[dict]
    # cada dict tiene: folio, fecha, nit_receptor, nombre_receptor,
    #                   lineas=[{descripcion, base, iva, tarifa_pct, tax_id}, ...],
    #                   totales={total, base_sin_iva, total_con_iva, iva_total}
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# ============================================================
# Regex para parsing UBL (rápido y sin dependencias XML)
# ============================================================

RX_ID                    = re.compile(r'<cbc:ID>([^<]+)</cbc:ID>')
RX_PROFILE               = re.compile(r'<cbc:ProfileID>([^<]+)</cbc:ProfileID>')
RX_ISSUE_DATE            = re.compile(r'<cbc:IssueDate>([^<]+)</cbc:IssueDate>')
RX_INVOICE_TYPE_CODE     = re.compile(r'<cbc:InvoiceTypeCode[^>]*>(\d+)</cbc:InvoiceTypeCode>')
RX_CREDIT_NOTE_TYPE_CODE = re.compile(r'<cbc:CreditNoteTypeCode[^>]*>(\d+)</cbc:CreditNoteTypeCode>')

# Para AccountingSupplierParty y AccountingCustomerParty
RX_SUPPLIER_BLOCK = re.compile(
    r'<cac:AccountingSupplierParty>(.*?)</cac:AccountingSupplierParty>',
    re.DOTALL
)
RX_CUSTOMER_BLOCK = re.compile(
    r'<cac:AccountingCustomerParty>(.*?)</cac:AccountingCustomerParty>',
    re.DOTALL
)
RX_COMPANY_ID = re.compile(r'<cbc:CompanyID[^>]*>(\d+)</cbc:CompanyID>')
RX_REG_NAME   = re.compile(r'<cbc:RegistrationName>([^<]+)</cbc:RegistrationName>')

# Totales (LegalMonetaryTotal)
RX_LEGAL_BLOCK = re.compile(
    r'<cac:LegalMonetaryTotal>(.*?)</cac:LegalMonetaryTotal>',
    re.DOTALL
)
RX_LINE_EXT       = re.compile(r'<cbc:LineExtensionAmount[^>]*>([\d.]+)</cbc:LineExtensionAmount>')
RX_TAX_EXCLUSIVE  = re.compile(r'<cbc:TaxExclusiveAmount[^>]*>([\d.]+)</cbc:TaxExclusiveAmount>')
RX_TAX_INCLUSIVE  = re.compile(r'<cbc:TaxInclusiveAmount[^>]*>([\d.]+)</cbc:TaxInclusiveAmount>')
RX_PAYABLE        = re.compile(r'<cbc:PayableAmount[^>]*>([\d.]+)</cbc:PayableAmount>')

# Líneas (InvoiceLine o CreditNoteLine)
RX_INVOICE_LINES   = re.compile(r'<cac:InvoiceLine>(.*?)</cac:InvoiceLine>', re.DOTALL)
RX_CREDIT_LINES    = re.compile(r'<cac:CreditNoteLine>(.*?)</cac:CreditNoteLine>', re.DOTALL)

# Dentro de cada línea
RX_LINE_DESC = re.compile(r'<cbc:Description>([^<]+)</cbc:Description>')
RX_LINE_QTY  = re.compile(r'<cbc:(?:Invoiced|Credited)Quantity[^>]*>([\d.]+)</cbc:(?:Invoiced|Credited)Quantity>')
RX_LINE_AMT  = re.compile(r'<cbc:LineExtensionAmount[^>]*>([\d.]+)</cbc:LineExtensionAmount>')

# TaxSubtotal: trae base, IVA y tarifa
RX_TAX_SUBTOTAL = re.compile(
    r'<cac:TaxSubtotal>\s*'
    r'<cbc:TaxableAmount[^>]*>([\d.]+)</cbc:TaxableAmount>\s*'
    r'<cbc:TaxAmount[^>]*>([\d.]+)</cbc:TaxAmount>\s*'
    r'<cac:TaxCategory>\s*'
    r'<cbc:Percent>([\d.]+)</cbc:Percent>\s*'
    r'<cac:TaxScheme>\s*'
    r'<cbc:ID>(\d+)</cbc:ID>\s*'
    r'<cbc:Name>([^<]+)</cbc:Name>',
    re.DOTALL
)


# ============================================================
# Mapas de constantes
# ============================================================

# Códigos DIAN para tipo de impuesto
TAX_SCHEME_NAMES = {
    "01": "IVA",
    "04": "INC",
    "ZZ": "Otro",
}

# Códigos DIAN para tipo de documento
DOC_TYPE_NAMES = {
    "01": "Factura electrónica de venta",
    "02": "Factura electrónica de exportación",
    "03": "Factura electrónica por contingencia",
    "04": "Factura electrónica de venta - tributos",
    "05": "Documento Soporte Electrónico",
    "20": "Nota crédito por contingencia",
    "21": "Nota débito por contingencia",
    "91": "Nota crédito de factura electrónica",
    "92": "Nota débito de factura electrónica",
}


# ============================================================
# Helpers
# ============================================================

def _f(s: Union[str, None, float]) -> float:
    """Convierte string a float. Devuelve 0.0 si no se puede."""
    if s is None:
        return 0.0
    try:
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _parsear_fecha(s: str) -> Optional[date]:
    """Parsea fecha YYYY-MM-DD."""
    if not s:
        return None
    try:
        return datetime.strptime(s.strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ============================================================
# Parser principal (un solo XML)
# ============================================================

def parsear_xml_dian(contenido_xml: str) -> Optional[dict]:
    """
    Parsea un XML UBL DIAN (Invoice o CreditNote) y extrae:

    Returns:
        dict con:
            tipo_doc: 'factura' o 'nota_credito'
            tipo_codigo: '01' / '91' / etc
            folio: 'STL15808', 'NC2579', etc (cbc:ID del documento)
            fecha: date
            nit_emisor: str
            nombre_emisor: str
            nit_receptor: str
            nombre_receptor: str
            totales: {
                line_extension: float,
                tax_exclusive: float,
                tax_inclusive: float,
                payable: float,
            }
            lineas: list[{
                descripcion: str,
                cantidad: float,
                base_total: float,  # LineExtensionAmount
                base_gravada: float,  # TaxableAmount (suma de TaxSubtotal)
                iva: float,
                tarifa_pct: float,  # 19, 5, 8 (INC), 0
                tax_scheme: '01' (IVA) o '04' (INC) o None (sin impuesto)
            }]

        None si el contenido no es un XML válido o no se pudo parsear.
    """
    if not contenido_xml or '<' not in contenido_xml:
        return None

    es_invoice = '<Invoice ' in contenido_xml[:1000]
    es_credit  = '<CreditNote ' in contenido_xml[:1000]
    if not (es_invoice or es_credit):
        return None

    tipo_doc = "factura" if es_invoice else "nota_credito"
    tipo_codigo = None
    if es_invoice:
        m = RX_INVOICE_TYPE_CODE.search(contenido_xml)
        tipo_codigo = m.group(1) if m else "01"
    else:
        m = RX_CREDIT_NOTE_TYPE_CODE.search(contenido_xml)
        tipo_codigo = m.group(1) if m else "91"

    # Folio: el primer <cbc:ID> a nivel de documento
    # (los XMLs UBL ponen el ID del documento antes que los IDs anidados)
    folio = None
    # Buscar después del cierre de UBLExtensions
    pos_inicio = contenido_xml.find('</ext:UBLExtensions>')
    if pos_inicio > 0:
        m = RX_ID.search(contenido_xml, pos_inicio)
        if m:
            folio = m.group(1).strip()
    if not folio:
        m = RX_ID.search(contenido_xml)
        folio = m.group(1).strip() if m else "UNKNOWN"

    # Fecha
    m = RX_ISSUE_DATE.search(contenido_xml)
    fecha = _parsear_fecha(m.group(1)) if m else None

    # Emisor
    nit_emisor = ""
    nombre_emisor = ""
    m_sup = RX_SUPPLIER_BLOCK.search(contenido_xml)
    if m_sup:
        bloque = m_sup.group(1)
        m_id = RX_COMPANY_ID.search(bloque)
        nit_emisor = m_id.group(1) if m_id else ""
        m_n = RX_REG_NAME.search(bloque)
        nombre_emisor = m_n.group(1).strip() if m_n else ""

    # Receptor
    nit_receptor = ""
    nombre_receptor = ""
    m_cust = RX_CUSTOMER_BLOCK.search(contenido_xml)
    if m_cust:
        bloque = m_cust.group(1)
        m_id = RX_COMPANY_ID.search(bloque)
        nit_receptor = m_id.group(1) if m_id else ""
        m_n = RX_REG_NAME.search(bloque)
        nombre_receptor = m_n.group(1).strip() if m_n else ""

    # Totales
    totales = {
        "line_extension": 0.0,
        "tax_exclusive":  0.0,
        "tax_inclusive":  0.0,
        "payable":        0.0,
    }
    m_legal = RX_LEGAL_BLOCK.search(contenido_xml)
    if m_legal:
        bloque = m_legal.group(1)
        m = RX_LINE_EXT.search(bloque);      totales["line_extension"] = _f(m.group(1)) if m else 0.0
        m = RX_TAX_EXCLUSIVE.search(bloque); totales["tax_exclusive"]  = _f(m.group(1)) if m else 0.0
        m = RX_TAX_INCLUSIVE.search(bloque); totales["tax_inclusive"]  = _f(m.group(1)) if m else 0.0
        m = RX_PAYABLE.search(bloque);       totales["payable"]        = _f(m.group(1)) if m else 0.0

    # Líneas
    lineas_raw = RX_INVOICE_LINES.findall(contenido_xml) if es_invoice else RX_CREDIT_LINES.findall(contenido_xml)
    lineas = []
    for ln_xml in lineas_raw:
        desc = RX_LINE_DESC.search(ln_xml)
        descripcion = desc.group(1).strip() if desc else ""
        qty = RX_LINE_QTY.search(ln_xml)
        cantidad = _f(qty.group(1)) if qty else 0.0
        amt = RX_LINE_AMT.search(ln_xml)
        base_total = _f(amt.group(1)) if amt else 0.0

        # TaxSubtotal: puede haber 0, 1 o más por línea (caso multi-impuesto)
        # Sumamos todos los subtotales encontrados en la línea
        subtotales = RX_TAX_SUBTOTAL.findall(ln_xml)
        # Si no hay TaxSubtotal → línea exenta (0%)
        if not subtotales:
            lineas.append({
                "descripcion":  descripcion,
                "cantidad":     cantidad,
                "base_total":   base_total,
                "base_gravada": base_total,  # toda la base es exenta
                "iva":          0.0,
                "tarifa_pct":   0.0,
                "tax_scheme":   None,
                "tax_name":     "Exento",
            })
        else:
            # Tomar el principal (primera ocurrencia) — usualmente solo hay uno por línea
            base, iva, pct, scheme_id, scheme_name = subtotales[0]
            lineas.append({
                "descripcion":  descripcion,
                "cantidad":     cantidad,
                "base_total":   base_total,
                "base_gravada": _f(base),
                "iva":          _f(iva),
                "tarifa_pct":   _f(pct),
                "tax_scheme":   scheme_id,
                "tax_name":     scheme_name.strip(),
            })

    return {
        "tipo_doc":         tipo_doc,
        "tipo_codigo":      tipo_codigo,
        "tipo_nombre":      DOC_TYPE_NAMES.get(tipo_codigo, tipo_codigo or "?"),
        "folio":            folio,
        "fecha":            fecha,
        "nit_emisor":       nit_emisor,
        "nombre_emisor":    nombre_emisor,
        "nit_receptor":     nit_receptor,
        "nombre_receptor":  nombre_receptor,
        "totales":          totales,
        "lineas":           lineas,
        "n_lineas":         len(lineas),
    }


# ============================================================
# Procesador del ZIP
# ============================================================

def procesar_zip_xmls_stl(
    fuente_zip: Union[bytes, str, Path, io.BytesIO],
    prefijo_filtro: Optional[str] = None,
    nit_emisor_filtro: Optional[str] = None,
) -> dict:
    """
    Lee un ZIP descargado del portal DIAN y extrae los XMLs.

    El ZIP puede contener:
      - XMLs directos
      - ZIPs anidados (cada factura en su propio ZIP, como descarga la DIAN)

    Args:
        fuente_zip: bytes, ruta o BytesIO del ZIP.
        prefijo_filtro: si se pasa (ej. "STL"), solo procesa folios que
                        empiecen con ese prefijo. Default None = todos.
        nit_emisor_filtro: si se pasa, solo procesa los del emisor.

    Returns:
        dict con:
            'facturas':         list[dict] (resultado de parsear_xml_dian para cada)
            'errores':          list[dict] con 'archivo', 'mensaje'
            'archivos_zip':     int (cuántos XMLs se procesaron)
            'archivos_no_xml':  int (cuántos archivos en el ZIP no eran XML)
            'duplicados':       int (cuántos folios estaban repetidos)
            'log':              list[str]
    """
    facturas = []
    errores = []
    archivos_no_xml = 0
    folios_vistos = set()
    duplicados = 0
    log = []

    # Normalizar fuente
    if isinstance(fuente_zip, (bytes, bytearray)):
        zip_io = io.BytesIO(fuente_zip)
    elif isinstance(fuente_zip, io.BytesIO):
        zip_io = fuente_zip
    elif isinstance(fuente_zip, (str, Path)):
        zip_io = str(fuente_zip)
    elif hasattr(fuente_zip, "read"):
        zip_io = io.BytesIO(fuente_zip.read())
    else:
        raise TypeError(f"Tipo de fuente no soportado: {type(fuente_zip)}")

    try:
        with zipfile.ZipFile(zip_io, 'r') as zf:
            nombres = zf.namelist()
            log.append(f"📦 ZIP abierto: {len(nombres)} archivos dentro")

            for nombre in nombres:
                # Saltar directorios
                if nombre.endswith('/'):
                    continue

                try:
                    contenido_bytes = zf.read(nombre)
                except Exception as e:
                    errores.append({"archivo": nombre, "mensaje": f"No se pudo leer: {e}"})
                    continue

                # ¿Es un ZIP anidado? (descarga típica DIAN)
                if nombre.lower().endswith('.zip'):
                    try:
                        with zipfile.ZipFile(io.BytesIO(contenido_bytes), 'r') as zf2:
                            for nombre2 in zf2.namelist():
                                if not nombre2.lower().endswith('.xml'):
                                    archivos_no_xml += 1
                                    continue
                                try:
                                    xml_str = zf2.read(nombre2).decode('utf-8', errors='replace')
                                except Exception as e:
                                    errores.append({"archivo": f"{nombre}>{nombre2}", "mensaje": str(e)})
                                    continue
                                _procesar_xml_individual(
                                    xml_str, f"{nombre}>{nombre2}",
                                    facturas, errores, folios_vistos,
                                    prefijo_filtro, nit_emisor_filtro
                                )
                    except zipfile.BadZipFile:
                        errores.append({"archivo": nombre, "mensaje": "ZIP anidado corrupto"})
                        continue

                # ¿Es un XML directo?
                elif nombre.lower().endswith('.xml'):
                    try:
                        xml_str = contenido_bytes.decode('utf-8', errors='replace')
                    except Exception as e:
                        errores.append({"archivo": nombre, "mensaje": f"Decodificación: {e}"})
                        continue
                    _procesar_xml_individual(
                        xml_str, nombre,
                        facturas, errores, folios_vistos,
                        prefijo_filtro, nit_emisor_filtro
                    )

                else:
                    archivos_no_xml += 1

    except zipfile.BadZipFile:
        raise ValueError("El archivo no es un ZIP válido")

    # Detectar duplicados (mismo folio aparece varias veces — el bug del bookmarklet)
    folios_lista = [f["folio"] for f in facturas]
    duplicados = len(folios_lista) - len(set(folios_lista))

    log.append(f"✅ Facturas parseadas: {len(facturas)}")
    log.append(f"⚠️ Archivos no XML: {archivos_no_xml}")
    if duplicados > 0:
        log.append(f"🚨 ALERTA: {duplicados} folios DUPLICADOS — el ZIP puede estar corrupto")
    if errores:
        log.append(f"❌ Errores: {len(errores)}")

    return {
        "facturas":        facturas,
        "errores":         errores,
        "archivos_no_xml": archivos_no_xml,
        "duplicados":      duplicados,
        "total_xmls":      len(facturas) + len(errores),
        "log":             log,
    }


def _procesar_xml_individual(
    xml_str: str,
    nombre_archivo: str,
    facturas: list,
    errores: list,
    folios_vistos: set,
    prefijo_filtro: Optional[str],
    nit_emisor_filtro: Optional[str],
):
    """Helper para parsear un XML individual y agregarlo a la lista."""
    try:
        # ¿Es AttachedDocument (que envuelve el XML real)?
        if '<AttachedDocument' in xml_str[:500]:
            # Extraer el CDATA con el XML interior
            m = re.search(r'<cbc:Description><!\[CDATA\[(.*?)\]\]></cbc:Description>', xml_str, re.DOTALL)
            if m:
                xml_str = m.group(1)
            else:
                # Otra forma: buscar el <Invoice o <CreditNote dentro
                idx_inv = xml_str.find('<Invoice ')
                idx_cn = xml_str.find('<CreditNote ')
                idx = min([i for i in (idx_inv, idx_cn) if i >= 0], default=-1)
                if idx >= 0:
                    # Encontrar el final del documento
                    if xml_str[idx:idx+10].startswith('<Invoice'):
                        end_tag = '</Invoice>'
                    else:
                        end_tag = '</CreditNote>'
                    end_idx = xml_str.find(end_tag, idx)
                    if end_idx > 0:
                        xml_str = xml_str[idx:end_idx + len(end_tag)]

        resultado = parsear_xml_dian(xml_str)
        if resultado is None:
            errores.append({"archivo": nombre_archivo, "mensaje": "No es Invoice ni CreditNote"})
            return

        # Filtros
        if nit_emisor_filtro and resultado["nit_emisor"] != nit_emisor_filtro:
            return
        if prefijo_filtro:
            folio = resultado["folio"]
            if not folio.upper().startswith(prefijo_filtro.upper()):
                return

        # Detectar duplicado
        if resultado["folio"] in folios_vistos:
            resultado["es_duplicado"] = True
        else:
            resultado["es_duplicado"] = False
            folios_vistos.add(resultado["folio"])

        facturas.append(resultado)
    except Exception as e:
        errores.append({"archivo": nombre_archivo, "mensaje": f"Parse error: {e}"})


# ============================================================
# Helpers para usar el resultado en el procesador STL
# ============================================================

def agrupar_lineas_por_tarifa(factura: dict) -> dict:
    """
    Agrupa las líneas de una factura por tarifa de IVA.

    Returns:
        dict { '19': {'base': X, 'iva': Y, 'lineas': N}, '0': {...}, ... }

        Las tarifas que NO son IVA (ej. INC 8%) van bajo su key específica.
    """
    grupos = {}
    for linea in factura["lineas"]:
        scheme = linea.get("tax_scheme")
        tarifa = linea["tarifa_pct"]

        # Clave: combinar tipo de impuesto + tarifa
        # IVA 19% → "iva_19"
        # IVA 5%  → "iva_5"
        # Sin IVA → "sin_iva"
        # INC 8%  → "inc_8"
        if scheme == "01":  # IVA
            if tarifa == 0:
                key = "sin_iva"
            else:
                key = f"iva_{int(round(tarifa))}"
        elif scheme == "04":  # INC
            key = f"inc_{int(round(tarifa))}"
        else:
            key = "sin_iva" if tarifa == 0 else f"otro_{int(round(tarifa))}"

        if key not in grupos:
            grupos[key] = {"base": 0.0, "iva": 0.0, "lineas": 0, "tarifa_pct": tarifa, "tax_scheme": scheme}
        grupos[key]["base"] += linea["base_gravada"]
        grupos[key]["iva"]  += linea["iva"]
        grupos[key]["lineas"] += 1

    return grupos
