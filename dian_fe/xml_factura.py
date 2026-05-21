"""
core/dian_fe/xml_factura.py

Generador de XML UBL 2.1 para Factura Electrónica de Venta DIAN.

Versión INICIAL — cubre el escenario JIPER (restaurante INC 8%):
  - Líneas con un solo impuesto (INC o IVA)
  - Sin descuentos globales complejos
  - Sin retenciones (las agregaremos cuando aparezcan en escenarios DIAN)
  - Sin múltiples monedas
  - Persona jurídica emisor, consumidor final / persona jurídica adquiriente

⚠️ ALCANCE: Este módulo es BASE. Probablemente fallará en el primer
envío contra DIAN porque hay decenas de campos que el Anexo Técnico
exige con formatos muy específicos. Cada rechazo de DIAN te dará un
código (FAJ24, FAJ58, etc.) que indica el campo a corregir.

Estructura UBL 2.1 generada:

  <Invoice>
    <ext:UBLExtensions>
      [Extensión 1: DianExtensions]
      [Extensión 2: Placeholder firma]
    </ext:UBLExtensions>
    <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
    <cbc:CustomizationID>10</cbc:CustomizationID>          ← 10 = FE estándar
    <cbc:ProfileID>DIAN 2.1</cbc:ProfileID>
    <cbc:ProfileExecutionID>2</cbc:ProfileExecutionID>     ← 2 = habilitación
    <cbc:ID>{PrefijoFolio}</cbc:ID>                        ← Ej. SETP990000001
    <cbc:UUID schemeName="CUFE-SHA384">{CUFE}</cbc:UUID>
    <cbc:IssueDate>{YYYY-MM-DD}</cbc:IssueDate>
    <cbc:IssueTime>{HH:MM:SS-05:00}</cbc:IssueTime>
    <cbc:InvoiceTypeCode listAgencyID="195" listAgencyName="..." listURI="...">01</cbc:InvoiceTypeCode>
    <cbc:Note>Notas opcionales</cbc:Note>
    <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
    <cac:AccountingSupplierParty>  ← Emisor (JIPER)
      ...estructura completa de empresa
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>  ← Cliente
      ...
    </cac:AccountingCustomerParty>
    <cac:PaymentMeans>             ← Medio/forma de pago
      ...
    </cac:PaymentMeans>
    <cac:TaxTotal>                 ← Impuestos totales
      ...
    </cac:TaxTotal>
    <cac:LegalMonetaryTotal>       ← Totales
      <cbc:LineExtensionAmount>...</cbc:LineExtensionAmount>
      <cbc:TaxExclusiveAmount>...</cbc:TaxExclusiveAmount>
      <cbc:TaxInclusiveAmount>...</cbc:TaxInclusiveAmount>
      <cbc:PayableAmount>...</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
    <cac:InvoiceLine>              ← Una por cada línea
      ...
    </cac:InvoiceLine>
  </Invoice>
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Optional

from lxml import etree

from .modelos import (
    Factura, LineaFactura, ParteFE,
    TIPO_DOC_NIT, ORG_JURIDICA, ORG_NATURAL,
    TRIBUTO_IVA, TRIBUTO_INC, TRIBUTO_ICA,
)


# ════════════════════════════════════════════════════════════════════════
# Namespaces UBL 2.1 + DIAN
# ════════════════════════════════════════════════════════════════════════

NS = {
    None: "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sts": "dian:gov:co:facturaelectronica:Structures-2-1",
    "xades": "http://uri.etsi.org/01903/v1.3.2#",
    "xades141": "http://uri.etsi.org/01903/v1.4.1#",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

NIT_DIAN = "800197268"
DV_DIAN = "4"


# ════════════════════════════════════════════════════════════════════════
# API principal
# ════════════════════════════════════════════════════════════════════════

def generar_xml_factura(factura: Factura) -> bytes:
    """
    Genera el XML UBL 2.1 de la factura como bytes UTF-8.

    El XML resultante NO está firmado. Pasar a firmador_xades.firmar_xml()
    para agregar la firma XAdES-EPES.

    Args:
        factura: instancia de Factura con totales ya calculados y CUFE asignado.

    Returns:
        XML como bytes (UTF-8).
    """
    _validar(factura)

    root = etree.Element("Invoice", nsmap=NS)

    # 1) UBL Extensions (DIAN + placeholder firma)
    _agregar_ubl_extensions(root, factura)

    # 2) Cabecera UBL
    _agregar_cabecera(root, factura)

    # 3) Resolución de numeración
    _agregar_resolucion(root, factura)

    # 4) Períodos
    _agregar_periodo(root, factura)

    # 5) Partes
    _agregar_supplier_party(root, factura.emisor)
    _agregar_customer_party(root, factura.adquiriente)

    # 6) Medio de pago
    _agregar_payment_means(root, factura)

    # 7) Impuestos totales
    _agregar_tax_total(root, factura)

    # 8) Totales monetarios
    _agregar_legal_monetary_total(root, factura)

    # 9) Líneas
    for linea in factura.lineas:
        _agregar_invoice_line(root, linea)

    return etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=False,
    )


# ════════════════════════════════════════════════════════════════════════
# Constructores de cada bloque
# ════════════════════════════════════════════════════════════════════════

def _t(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def _fmt(d: Decimal) -> str:
    """Formato monetario DIAN: 2 decimales, punto."""
    if not isinstance(d, Decimal):
        d = Decimal(str(d))
    return f"{d.quantize(Decimal('0.01')):.2f}"


def _fmt_cantidad(d: Decimal) -> str:
    """Formato cantidad DIAN: hasta 6 decimales."""
    if not isinstance(d, Decimal):
        d = Decimal(str(d))
    return f"{d.quantize(Decimal('0.000001')):.6f}"


def _validar(f: Factura) -> None:
    if not f.emisor or not f.adquiriente:
        raise ValueError("La factura debe tener emisor y adquiriente")
    if not f.resolucion:
        raise ValueError("La factura debe tener resolución")
    if not f.lineas:
        raise ValueError("La factura debe tener al menos una línea")
    if not f.cufe or len(f.cufe) != 96:
        raise ValueError(
            f"La factura debe tener CUFE de 96 caracteres "
            f"(recibí longitud {len(f.cufe) if f.cufe else 0})"
        )


def _agregar_ubl_extensions(root, factura: Factura) -> None:
    """Las dos extensiones UBL: DianExtensions + placeholder firma."""
    ext_root = etree.SubElement(root, _t("ext", "UBLExtensions"))

    # ── Extensión 1: DianExtensions ──
    ext1 = etree.SubElement(ext_root, _t("ext", "UBLExtension"))
    ec1 = etree.SubElement(ext1, _t("ext", "ExtensionContent"))
    dian = etree.SubElement(ec1, _t("sts", "DianExtensions"))

    # InvoiceControl (rango de numeración autorizado)
    ic = etree.SubElement(dian, _t("sts", "InvoiceControl"))
    inv_auth = etree.SubElement(ic, _t("sts", "InvoiceAuthorization"))
    inv_auth.text = factura.resolucion.numero
    auth_period = etree.SubElement(ic, _t("sts", "AuthorizationPeriod"))
    sd = etree.SubElement(auth_period, _t("cbc", "StartDate"))
    sd.text = factura.resolucion.fecha_desde.strftime("%Y-%m-%d")
    ed = etree.SubElement(auth_period, _t("cbc", "EndDate"))
    ed.text = factura.resolucion.fecha_hasta.strftime("%Y-%m-%d")
    auth_range = etree.SubElement(ic, _t("sts", "AuthorizedInvoices"))
    pref = etree.SubElement(auth_range, _t("sts", "Prefix"))
    pref.text = factura.resolucion.prefijo
    fr = etree.SubElement(auth_range, _t("sts", "From"))
    fr.text = str(factura.resolucion.rango_desde)
    to = etree.SubElement(auth_range, _t("sts", "To"))
    to.text = str(factura.resolucion.rango_hasta)

    # InvoiceSource
    src = etree.SubElement(dian, _t("sts", "InvoiceSource"))
    src_c = etree.SubElement(src, _t("cbc", "IdentificationCode"))
    src_c.set("listAgencyID", "6")
    src_c.set("listAgencyName", "United Nations Economic Commission for Europe")
    src_c.set("listSchemeURI", "urn:oasis:names:specification:ubl:codelist:gc:CountryIdentificationCode-2.1")
    src_c.text = "CO"

    # SoftwareProvider
    sp = etree.SubElement(dian, _t("sts", "SoftwareProvider"))
    sp_id = etree.SubElement(sp, _t("sts", "ProviderID"))
    sp_id.set("schemeAgencyID", "195")
    sp_id.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    sp_id.set("schemeID", factura.emisor.dv or "0")
    sp_id.set("schemeName", "31")
    sp_id.text = factura.emisor.numero_documento

    sp_sw = etree.SubElement(sp, _t("sts", "SoftwareID"))
    sp_sw.set("schemeAgencyID", "195")
    sp_sw.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    sp_sw.text = factura.software_id

    # SoftwareSecurityCode (hash SHA-384 calculado del SoftwareID + PIN + CUFE)
    # Algoritmo DIAN:
    #   SoftwareSecurityCode = SHA-384(SoftwareID + PIN + CUFE)
    import hashlib
    ssc_string = f"{factura.software_id}{factura.software_security_code}{factura.cufe}"
    ssc_hash = hashlib.sha384(ssc_string.encode("utf-8")).hexdigest()

    ssc = etree.SubElement(dian, _t("sts", "SoftwareSecurityCode"))
    ssc.set("schemeAgencyID", "195")
    ssc.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    ssc.text = ssc_hash

    # AuthorizationProvider (DIAN)
    ap = etree.SubElement(dian, _t("sts", "AuthorizationProvider"))
    ap_id = etree.SubElement(ap, _t("sts", "AuthorizationProviderID"))
    ap_id.set("schemeAgencyID", "195")
    ap_id.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    ap_id.set("schemeID", DV_DIAN)
    ap_id.set("schemeName", "31")
    ap_id.text = NIT_DIAN

    # QRCode (URL para validación pública DIAN)
    qr = etree.SubElement(dian, _t("sts", "QRCode"))
    # Formato del QR según DIAN
    qr.text = _construir_url_qr(factura)

    # ── Extensión 2: placeholder firma ──
    ext2 = etree.SubElement(ext_root, _t("ext", "UBLExtension"))
    etree.SubElement(ext2, _t("ext", "ExtensionContent"))


def _construir_url_qr(factura: Factura) -> str:
    """
    Construye la URL del QR para validación pública DIAN.

    Formato (Anexo Técnico):
        https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={CUFE}
    """
    return f"https://catalogo-vpfe.dian.gov.co/document/searchqr?documentkey={factura.cufe}"


def _agregar_cabecera(root, factura: Factura) -> None:
    """Elementos UBL estándar de cabecera."""
    def add(tag, text, **attrs):
        e = etree.SubElement(root, _t("cbc", tag))
        for k, v in attrs.items():
            e.set(k, v)
        e.text = text
        return e

    add("UBLVersionID", "UBL 2.1")
    add("CustomizationID", "10")   # 10 = Factura electrónica estándar
    add("ProfileID", "DIAN 2.1: Factura Electrónica de Venta")
    add("ProfileExecutionID", factura.ambiente)
    add("ID", factura.numero_factura)

    uuid = add("UUID", factura.cufe)
    uuid.set("schemeName", "CUFE-SHA384")

    add("IssueDate", factura.fecha_emision.strftime("%Y-%m-%d"))

    if factura.fecha_emision.tzinfo:
        offset = factura.fecha_emision.strftime("%z")
        hora = f"{factura.fecha_emision.strftime('%H:%M:%S')}{offset[:3]}:{offset[3:]}"
    else:
        hora = f"{factura.fecha_emision.strftime('%H:%M:%S')}-05:00"
    add("IssueTime", hora)

    if factura.fecha_vencimiento:
        add("DueDate", factura.fecha_vencimiento.strftime("%Y-%m-%d"))

    inv_type = add("InvoiceTypeCode", factura.tipo_factura)
    inv_type.set("listAgencyID", "195")
    inv_type.set("listAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    inv_type.set("listURI", "http://www.dian.gov.co")

    for nota in factura.notas:
        add("Note", nota)

    dc = add("DocumentCurrencyCode", factura.moneda)
    dc.set("listAgencyID", "6")
    dc.set("listAgencyName", "United Nations Economic Commission for Europe")
    dc.set("listID", "ISO 4217 Alpha")

    add("LineCountNumeric", str(len(factura.lineas)))


def _agregar_resolucion(root, factura: Factura) -> None:
    """No genera nada — la resolución ya va en DianExtensions/InvoiceControl."""
    pass


def _agregar_periodo(root, factura: Factura) -> None:
    """Periodo de facturación (mismo día por defecto)."""
    p = etree.SubElement(root, _t("cac", "InvoicePeriod"))
    sd = etree.SubElement(p, _t("cbc", "StartDate"))
    sd.text = factura.fecha_emision.strftime("%Y-%m-%d")
    ed = etree.SubElement(p, _t("cbc", "EndDate"))
    ed.text = factura.fecha_emision.strftime("%Y-%m-%d")


def _agregar_supplier_party(root, parte: ParteFE) -> None:
    """AccountingSupplierParty = emisor (vendedor)."""
    asp = etree.SubElement(root, _t("cac", "AccountingSupplierParty"))
    asp_id = etree.SubElement(asp, _t("cbc", "AdditionalAccountID"))
    asp_id.text = parte.tipo_organizacion  # 1=jurídica, 2=natural

    party = etree.SubElement(asp, _t("cac", "Party"))
    _llenar_party(party, parte, es_supplier=True)


def _agregar_customer_party(root, parte: ParteFE) -> None:
    """AccountingCustomerParty = adquiriente (cliente)."""
    acp = etree.SubElement(root, _t("cac", "AccountingCustomerParty"))
    acp_id = etree.SubElement(acp, _t("cbc", "AdditionalAccountID"))
    acp_id.text = parte.tipo_organizacion

    party = etree.SubElement(acp, _t("cac", "Party"))
    _llenar_party(party, parte, es_supplier=False)


def _llenar_party(party, parte: ParteFE, es_supplier: bool) -> None:
    """Llena los datos de una Party (común para supplier y customer)."""
    # PartyIdentification
    pid = etree.SubElement(party, _t("cac", "PartyIdentification"))
    pid_id = etree.SubElement(pid, _t("cbc", "ID"))
    pid_id.set("schemeAgencyID", "195")
    pid_id.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    pid_id.set("schemeID", parte.dv or "0")
    pid_id.set("schemeName", parte.tipo_documento_id)
    pid_id.text = parte.numero_documento

    # PartyName
    pname = etree.SubElement(party, _t("cac", "PartyName"))
    name = etree.SubElement(pname, _t("cbc", "Name"))
    name.text = parte.nombre_comercial or parte.razon_social

    # PhysicalLocation con dirección
    if parte.direccion:
        loc = etree.SubElement(party, _t("cac", "PhysicalLocation"))
        addr = etree.SubElement(loc, _t("cac", "Address"))
        addr_id = etree.SubElement(addr, _t("cbc", "ID"))
        addr_id.text = parte.municipio_codigo
        addr_city = etree.SubElement(addr, _t("cbc", "CityName"))
        addr_city.text = parte.municipio_nombre
        addr_cs = etree.SubElement(addr, _t("cbc", "CountrySubentity"))
        addr_cs.text = parte.departamento_nombre
        addr_cs_code = etree.SubElement(addr, _t("cbc", "CountrySubentityCode"))
        addr_cs_code.text = parte.departamento_codigo
        addr_line = etree.SubElement(addr, _t("cac", "AddressLine"))
        addr_line_text = etree.SubElement(addr_line, _t("cbc", "Line"))
        addr_line_text.text = parte.direccion
        country = etree.SubElement(addr, _t("cac", "Country"))
        country_id = etree.SubElement(country, _t("cbc", "IdentificationCode"))
        country_id.text = parte.pais_codigo
        country_name = etree.SubElement(country, _t("cbc", "Name"))
        country_name.set("languageID", "es")
        country_name.text = parte.pais_nombre

    # PartyTaxScheme (régimen fiscal)
    pts = etree.SubElement(party, _t("cac", "PartyTaxScheme"))
    pts_rname = etree.SubElement(pts, _t("cbc", "RegistrationName"))
    pts_rname.text = parte.razon_social
    pts_cid = etree.SubElement(pts, _t("cbc", "CompanyID"))
    pts_cid.set("schemeAgencyID", "195")
    pts_cid.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    pts_cid.set("schemeID", parte.dv or "0")
    pts_cid.set("schemeName", parte.tipo_documento_id)
    pts_cid.text = parte.numero_documento

    pts_tlc = etree.SubElement(pts, _t("cbc", "TaxLevelCode"))
    pts_tlc.set("listName", ";".join(parte.responsabilidades) if parte.responsabilidades else "R-99-PN")
    pts_tlc.text = parte.regimen_fiscal_codigo

    # RegistrationAddress (dirección fiscal)
    if parte.direccion:
        ra = etree.SubElement(pts, _t("cac", "RegistrationAddress"))
        ra_id = etree.SubElement(ra, _t("cbc", "ID"))
        ra_id.text = parte.municipio_codigo
        ra_city = etree.SubElement(ra, _t("cbc", "CityName"))
        ra_city.text = parte.municipio_nombre
        ra_cs = etree.SubElement(ra, _t("cbc", "CountrySubentity"))
        ra_cs.text = parte.departamento_nombre
        ra_cs_code = etree.SubElement(ra, _t("cbc", "CountrySubentityCode"))
        ra_cs_code.text = parte.departamento_codigo
        ra_line = etree.SubElement(ra, _t("cac", "AddressLine"))
        ra_line_text = etree.SubElement(ra_line, _t("cbc", "Line"))
        ra_line_text.text = parte.direccion
        ra_country = etree.SubElement(ra, _t("cac", "Country"))
        ra_country_id = etree.SubElement(ra_country, _t("cbc", "IdentificationCode"))
        ra_country_id.text = parte.pais_codigo
        ra_country_name = etree.SubElement(ra_country, _t("cbc", "Name"))
        ra_country_name.set("languageID", "es")
        ra_country_name.text = parte.pais_nombre

    # TaxScheme dentro de PartyTaxScheme
    ts = etree.SubElement(pts, _t("cac", "TaxScheme"))
    ts_id = etree.SubElement(ts, _t("cbc", "ID"))
    ts_id.text = "01"  # IVA por defecto
    ts_name = etree.SubElement(ts, _t("cbc", "Name"))
    ts_name.text = "IVA"

    # PartyLegalEntity
    ple = etree.SubElement(party, _t("cac", "PartyLegalEntity"))
    ple_name = etree.SubElement(ple, _t("cbc", "RegistrationName"))
    ple_name.text = parte.razon_social
    ple_cid = etree.SubElement(ple, _t("cbc", "CompanyID"))
    ple_cid.set("schemeAgencyID", "195")
    ple_cid.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    ple_cid.set("schemeID", parte.dv or "0")
    ple_cid.set("schemeName", parte.tipo_documento_id)
    ple_cid.text = parte.numero_documento

    # Contact (opcional)
    if parte.email or parte.telefono:
        contact = etree.SubElement(party, _t("cac", "Contact"))
        if parte.telefono:
            c_phone = etree.SubElement(contact, _t("cbc", "Telephone"))
            c_phone.text = parte.telefono
        if parte.email:
            c_email = etree.SubElement(contact, _t("cbc", "ElectronicMail"))
            c_email.text = parte.email


def _agregar_payment_means(root, factura: Factura) -> None:
    """PaymentMeans = forma y medio de pago."""
    pm = etree.SubElement(root, _t("cac", "PaymentMeans"))
    pm_id = etree.SubElement(pm, _t("cbc", "ID"))
    pm_id.text = factura.medio_pago.forma   # 1=contado, 2=crédito
    pm_code = etree.SubElement(pm, _t("cbc", "PaymentMeansCode"))
    pm_code.text = factura.medio_pago.medio   # 10=efectivo, etc.
    if factura.medio_pago.fecha_vencimiento:
        pm_date = etree.SubElement(pm, _t("cbc", "PaymentDueDate"))
        pm_date.text = factura.medio_pago.fecha_vencimiento.strftime("%Y-%m-%d")


def _agregar_tax_total(root, factura: Factura) -> None:
    """TaxTotal con cada impuesto agregado."""
    if not factura.impuestos_totales:
        return

    tt = etree.SubElement(root, _t("cac", "TaxTotal"))
    total_tax = sum((i.valor for i in factura.impuestos_totales), Decimal("0"))
    tt_amount = etree.SubElement(tt, _t("cbc", "TaxAmount"))
    tt_amount.set("currencyID", factura.moneda)
    tt_amount.text = _fmt(total_tax)

    for imp in factura.impuestos_totales:
        sub = etree.SubElement(tt, _t("cac", "TaxSubtotal"))
        sub_base = etree.SubElement(sub, _t("cbc", "TaxableAmount"))
        sub_base.set("currencyID", factura.moneda)
        sub_base.text = _fmt(imp.base_gravable)
        sub_amount = etree.SubElement(sub, _t("cbc", "TaxAmount"))
        sub_amount.set("currencyID", factura.moneda)
        sub_amount.text = _fmt(imp.valor)
        sub_cat = etree.SubElement(sub, _t("cac", "TaxCategory"))
        sub_pct = etree.SubElement(sub_cat, _t("cbc", "Percent"))
        sub_pct.text = _fmt(imp.porcentaje)
        sub_scheme = etree.SubElement(sub_cat, _t("cac", "TaxScheme"))
        ss_id = etree.SubElement(sub_scheme, _t("cbc", "ID"))
        ss_id.text = imp.codigo
        ss_name = etree.SubElement(sub_scheme, _t("cbc", "Name"))
        ss_name.text = imp.nombre


def _agregar_legal_monetary_total(root, factura: Factura) -> None:
    """LegalMonetaryTotal con todos los totales."""
    lmt = etree.SubElement(root, _t("cac", "LegalMonetaryTotal"))
    moneda = factura.moneda

    def add(tag, valor):
        e = etree.SubElement(lmt, _t("cbc", tag))
        e.set("currencyID", moneda)
        e.text = _fmt(valor)

    add("LineExtensionAmount", factura.totales.line_extension)
    add("TaxExclusiveAmount", factura.totales.tax_exclusive)
    add("TaxInclusiveAmount", factura.totales.tax_inclusive)
    add("AllowanceTotalAmount", factura.totales.allowance_total)
    add("ChargeTotalAmount", factura.totales.charge_total)
    add("PrePaidAmount", factura.totales.prepaid)
    add("PayableAmount", factura.totales.payable)


def _agregar_invoice_line(root, linea: LineaFactura) -> None:
    """Una InvoiceLine por cada producto/servicio facturado."""
    il = etree.SubElement(root, _t("cac", "InvoiceLine"))
    il_id = etree.SubElement(il, _t("cbc", "ID"))
    il_id.text = str(linea.numero_linea)

    il_qty = etree.SubElement(il, _t("cbc", "InvoicedQuantity"))
    il_qty.set("unitCode", linea.unidad)
    il_qty.text = _fmt_cantidad(linea.cantidad)

    il_amount = etree.SubElement(il, _t("cbc", "LineExtensionAmount"))
    il_amount.set("currencyID", "COP")
    il_amount.text = _fmt(linea.base_gravable)

    # Impuestos de la línea
    if linea.impuestos:
        il_tax = etree.SubElement(il, _t("cac", "TaxTotal"))
        total_tax_linea = sum((i.valor for i in linea.impuestos), Decimal("0"))
        il_tax_amount = etree.SubElement(il_tax, _t("cbc", "TaxAmount"))
        il_tax_amount.set("currencyID", "COP")
        il_tax_amount.text = _fmt(total_tax_linea)

        for imp in linea.impuestos:
            sub = etree.SubElement(il_tax, _t("cac", "TaxSubtotal"))
            sb = etree.SubElement(sub, _t("cbc", "TaxableAmount"))
            sb.set("currencyID", "COP")
            sb.text = _fmt(imp.base_gravable)
            sa = etree.SubElement(sub, _t("cbc", "TaxAmount"))
            sa.set("currencyID", "COP")
            sa.text = _fmt(imp.valor)
            sc = etree.SubElement(sub, _t("cac", "TaxCategory"))
            sp = etree.SubElement(sc, _t("cbc", "Percent"))
            sp.text = _fmt(imp.porcentaje)
            ssch = etree.SubElement(sc, _t("cac", "TaxScheme"))
            ssch_id = etree.SubElement(ssch, _t("cbc", "ID"))
            ssch_id.text = imp.codigo
            ssch_name = etree.SubElement(ssch, _t("cbc", "Name"))
            ssch_name.text = imp.nombre

    # Item (producto/servicio)
    item = etree.SubElement(il, _t("cac", "Item"))
    item_desc = etree.SubElement(item, _t("cbc", "Description"))
    item_desc.text = linea.descripcion

    if linea.codigo_estandar:
        item_std = etree.SubElement(item, _t("cac", "StandardItemIdentification"))
        item_std_id = etree.SubElement(item_std, _t("cbc", "ID"))
        item_std_id.set("schemeID", linea.tipo_codigo_estandar)
        item_std_id.text = linea.codigo_estandar
    else:
        item_seller = etree.SubElement(item, _t("cac", "SellersItemIdentification"))
        item_seller_id = etree.SubElement(item_seller, _t("cbc", "ID"))
        item_seller_id.text = linea.codigo_producto

    # Price
    price = etree.SubElement(il, _t("cac", "Price"))
    price_amount = etree.SubElement(price, _t("cbc", "PriceAmount"))
    price_amount.set("currencyID", "COP")
    price_amount.text = _fmt(linea.precio_unitario)
    price_qty = etree.SubElement(price, _t("cbc", "BaseQuantity"))
    price_qty.set("unitCode", linea.unidad)
    price_qty.text = _fmt_cantidad(Decimal("1"))
