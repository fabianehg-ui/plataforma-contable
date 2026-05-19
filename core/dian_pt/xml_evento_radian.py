"""
core/dian_pt/xml_evento_radian.py

Generador de XML UBL 2.1 para eventos RADIAN / Recepción Electrónica DIAN.

Soporta eventos:
  - 030: Acuse de recibo de la factura electrónica
  - 031: Reclamo (rechazo de factura)
  - 032: Recibo del bien o prestación del servicio
  - 033: Aceptación expresa de la factura

Estructura general del XML:

  <ApplicationResponse>
    <ext:UBLExtensions>
      <ext:UBLExtension>                       ← Extensión DIAN
        <ext:ExtensionContent>
          <sts:DianExtensions>
            <sts:InvoiceSource>...</sts:InvoiceSource>
            <sts:SoftwareProvider>...</sts:SoftwareProvider>
            <sts:SoftwareSecurityCode>...</sts:SoftwareSecurityCode>
            <sts:AuthorizationProvider>...</sts:AuthorizationProvider>
          </sts:DianExtensions>
        </ext:ExtensionContent>
      </ext:UBLExtension>
      <ext:UBLExtension>                       ← Extensión de firma (vacía aquí)
        <ext:ExtensionContent/>                  Se llena en firmador_xades.py
      </ext:UBLExtension>
    </ext:UBLExtensions>
    <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
    <cbc:CustomizationID>1</cbc:CustomizationID>
    <cbc:ProfileID>DIAN 2.1: Aplicación Comercial</cbc:ProfileID>
    <cbc:ProfileExecutionID>2</cbc:ProfileExecutionID>
    <cbc:ID>{num_evento}</cbc:ID>
    <cbc:UUID>{CUDE}</cbc:UUID>
    <cbc:IssueDate>YYYY-MM-DD</cbc:IssueDate>
    <cbc:IssueTime>HH:MM:SS-05:00</cbc:IssueTime>
    <cac:SenderParty>...</cac:SenderParty>     ← Adquiriente (quien emite el evento)
    <cac:ReceiverParty>...</cac:ReceiverParty> ← Proveedor (emisor de la factura original)
    <cac:DocumentResponse>
      <cac:Response>
        <cbc:ResponseCode>030|031|032|033</cbc:ResponseCode>
        <cbc:Description>...</cbc:Description>
      </cac:Response>
      <cac:DocumentReference>
        <cbc:ID>{NumeroFactura}</cbc:ID>
        <cbc:UUID schemeName="CUFE-SHA384">{CUFE_factura}</cbc:UUID>
        <cbc:IssueDate>YYYY-MM-DD</cbc:IssueDate>
      </cac:DocumentReference>
      <cac:IssuerParty>...</cac:IssuerParty>   ← Proveedor de la factura referida
      <cac:RecipientParty>...</cac:RecipientParty> ← Adquiriente
    </cac:DocumentResponse>
  </ApplicationResponse>

Referencia: Anexo Técnico DIAN, Apéndice 10 - ApplicationResponse para
eventos RADIAN y Recepción Electrónica.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

from lxml import etree


# ════════════════════════════════════════════════════════════════════════
# Namespaces UBL 2.1 + DIAN
# ════════════════════════════════════════════════════════════════════════

NS = {
    None: "urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sts": "dian:gov:co:facturaelectronica:Structures-2-1",
    "xades": "http://uri.etsi.org/01903/v1.3.2#",
    "xades141": "http://uri.etsi.org/01903/v1.4.1#",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}

# Códigos y descripciones oficiales de eventos
EVENTOS = {
    "030": {
        "codigo": "030",
        "descripcion": "Acuse de recibo de Factura Electrónica de Venta",
        "responseCode": "030",
    },
    "031": {
        "codigo": "031",
        "descripcion": "Reclamo de la Factura Electrónica de Venta",
        "responseCode": "031",
    },
    "032": {
        "codigo": "032",
        "descripcion": "Recibo del bien o prestación del servicio",
        "responseCode": "032",
    },
    "033": {
        "codigo": "033",
        "descripcion": "Aceptación expresa de la Factura Electrónica de Venta",
        "responseCode": "033",
    },
}

# Códigos para Reclamo (evento 031) — DIAN tabla 13.3.3
CODIGOS_RECLAMO = {
    "01": "Documento con inconsistencias",
    "02": "Mercancía no entregada totalmente",
    "03": "Mercancía no entregada parcialmente",
    "04": "Servicio no prestado",
}


# ════════════════════════════════════════════════════════════════════════
# Estructuras de datos
# ════════════════════════════════════════════════════════════════════════

@dataclass
class ParteEvento:
    """
    Parte (Sender/Receiver) en el evento RADIAN.

    Se usa tanto para emisor como receptor del evento. Los datos son los
    de la empresa: NIT, razón social, tipo de organización, etc.
    """
    nit: str                                  # NIT sin DV
    dv: str                                   # Dígito de verificación
    razon_social: str                         # Nombre legal de la empresa
    tipo_organizacion: str = "1"              # 1=Jurídica, 2=Natural
    tipo_documento_id: str = "31"             # 31=NIT, 13=CC, etc.
    regimen_fiscal: str = "48"                # 48=Responsable IVA, 49=No responsable
    pais_codigo: str = "CO"
    departamento_codigo: str = "05"           # 05=Antioquia
    municipio_codigo: str = "05001"           # 05001=Medellín
    direccion: str = ""
    email: Optional[str] = None
    obligaciones: str = "O-13"                # Gran contribuyente, etc.

    @property
    def nit_con_dv(self) -> str:
        """NIT con DV separado por guion."""
        return f"{self.nit}-{self.dv}"


@dataclass
class FacturaReferida:
    """
    La factura sobre la que se está emitiendo el evento.

    Datos vienen del CUFE original que dio el proveedor.
    """
    numero: str                              # Ej. "FE-12345"
    cufe: str                                # CUFE SHA-384 del XML original
    fecha_emision: datetime                  # Fecha emisión original
    monto_total: float                       # Total bruto de la factura


@dataclass
class EventoRadian:
    """
    Estructura completa para generar un evento RADIAN.

    Campos:
        tipo_evento: "030", "031", "032", "033"
        num_evento: consecutivo asignado por el adquiriente (string)
        cude: CUDE pre-calculado (de cude_calculator)
        fecha_emision: fecha+hora de emisión del evento
        emisor: el adquiriente (quien acusa la factura)
        receptor: el proveedor (emisor de la factura original)
        factura: la factura sobre la cual va el evento

    Solo para evento 031 (reclamo):
        codigo_reclamo: "01"-"04" según tabla DIAN
    """
    tipo_evento: Literal["030", "031", "032", "033"]
    num_evento: str
    cude: str
    fecha_emision: datetime
    emisor: ParteEvento                      # Adquiriente
    receptor: ParteEvento                    # Proveedor original
    factura: FacturaReferida

    # Datos del software del PT (asignados por DIAN al habilitarse)
    software_id: str = ""                    # SoftwareID asignado por DIAN
    software_security_code: str = ""         # PIN del software (de DIAN)
    clave_tecnica: str = ""                  # Clave técnica (de DIAN)
    proveedor_tecnologico_nit: str = ""      # NIT del PT
    proveedor_tecnologico_dv: str = ""

    # Ambiente
    ambiente: Literal["1", "2"] = "2"        # 1=prod, 2=habilitación

    # Reclamo (solo si tipo_evento == "031")
    codigo_reclamo: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════
# Generador principal
# ════════════════════════════════════════════════════════════════════════

def generar_xml_evento(evento: EventoRadian) -> bytes:
    """
    Genera el XML UBL 2.1 del evento RADIAN como bytes UTF-8.

    El XML resultante NO está firmado. Pasar el resultado a
    firmador_xades.firmar_xml() para agregar la firma XAdES-EPES.

    Args:
        evento: estructura completa con todos los datos.

    Returns:
        XML del evento como bytes (UTF-8, con declaración XML).

    Raises:
        ValueError: si faltan campos críticos.
    """
    _validar_evento(evento)

    # Crear root ApplicationResponse con namespaces
    root = etree.Element(
        "ApplicationResponse",
        nsmap=NS,
    )

    # 1) Extensiones UBL (DIAN + placeholder firma)
    _agregar_ubl_extensions(root, evento)

    # 2) Cabecera estándar UBL
    _agregar_cabecera(root, evento)

    # 3) SenderParty (adquiriente que emite el evento)
    _agregar_parte(root, evento.emisor, tag="SenderParty")

    # 4) ReceiverParty (proveedor original)
    _agregar_parte(root, evento.receptor, tag="ReceiverParty")

    # 5) DocumentResponse (el evento propiamente dicho)
    _agregar_document_response(root, evento)

    # Serializar
    xml_bytes = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=False,
    )
    return xml_bytes


# ════════════════════════════════════════════════════════════════════════
# Constructores de cada bloque
# ════════════════════════════════════════════════════════════════════════

def _ns_tag(prefix: str, tag: str) -> str:
    """Construye un tag con namespace: {url}tag"""
    return f"{{{NS[prefix]}}}{tag}"


def _agregar_ubl_extensions(root, evento: EventoRadian) -> None:
    """
    Agrega las dos UBLExtensions:
      1. DianExtensions (datos del software PT)
      2. Placeholder vacío para la firma XAdES (la llena el firmador)
    """
    ext_root = etree.SubElement(root, _ns_tag("ext", "UBLExtensions"))

    # Extensión 1: DianExtensions
    ext1 = etree.SubElement(ext_root, _ns_tag("ext", "UBLExtension"))
    ec1 = etree.SubElement(ext1, _ns_tag("ext", "ExtensionContent"))
    dian = etree.SubElement(ec1, _ns_tag("sts", "DianExtensions"))

    # InvoiceSource (país de origen del documento)
    src = etree.SubElement(dian, _ns_tag("sts", "InvoiceSource"))
    src_country = etree.SubElement(src, _ns_tag("cbc", "IdentificationCode"))
    src_country.set("listAgencyID", "6")
    src_country.set("listAgencyName", "United Nations Economic Commission for Europe")
    src_country.set("listSchemeURI", "urn:oasis:names:specification:ubl:codelist:gc:CountryIdentificationCode-2.1")
    src_country.text = "CO"

    # SoftwareProvider (datos del PT)
    sp = etree.SubElement(dian, _ns_tag("sts", "SoftwareProvider"))
    sp_id = etree.SubElement(sp, _ns_tag("sts", "ProviderID"))
    sp_id.set("schemeAgencyID", "195")
    sp_id.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    sp_id.set("schemeID", evento.proveedor_tecnologico_dv or "0")
    sp_id.set("schemeName", "31")
    sp_id.text = evento.proveedor_tecnologico_nit or "000000000"

    sp_sw = etree.SubElement(sp, _ns_tag("sts", "SoftwareID"))
    sp_sw.set("schemeAgencyID", "195")
    sp_sw.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    sp_sw.text = evento.software_id or ""

    # SoftwareSecurityCode (PIN del software)
    ssc = etree.SubElement(dian, _ns_tag("sts", "SoftwareSecurityCode"))
    ssc.set("schemeAgencyID", "195")
    ssc.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    ssc.text = evento.software_security_code or ""

    # AuthorizationProvider (siempre DIAN para Colombia)
    ap = etree.SubElement(dian, _ns_tag("sts", "AuthorizationProvider"))
    ap_id = etree.SubElement(ap, _ns_tag("sts", "AuthorizationProviderID"))
    ap_id.set("schemeAgencyID", "195")
    ap_id.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    ap_id.set("schemeID", "4")
    ap_id.set("schemeName", "31")
    ap_id.text = "800197268"  # NIT DIAN

    # Extensión 2: placeholder vacío para la firma XAdES
    # El firmador inserta aquí toda la estructura <ds:Signature>...
    ext2 = etree.SubElement(ext_root, _ns_tag("ext", "UBLExtension"))
    etree.SubElement(ext2, _ns_tag("ext", "ExtensionContent"))


def _agregar_cabecera(root, evento: EventoRadian) -> None:
    """Agrega los elementos UBL estándar de cabecera."""
    info = EVENTOS[evento.tipo_evento]

    e = etree.SubElement(root, _ns_tag("cbc", "UBLVersionID"))
    e.text = "UBL 2.1"

    e = etree.SubElement(root, _ns_tag("cbc", "CustomizationID"))
    e.text = info["responseCode"]   # DIAN usa el código del evento aquí

    e = etree.SubElement(root, _ns_tag("cbc", "ProfileID"))
    e.text = "DIAN 2.1: Eventos Factura Electronica"

    e = etree.SubElement(root, _ns_tag("cbc", "ProfileExecutionID"))
    e.text = evento.ambiente  # 1=prod, 2=hab

    e = etree.SubElement(root, _ns_tag("cbc", "ID"))
    e.text = evento.num_evento

    e = etree.SubElement(root, _ns_tag("cbc", "UUID"))
    e.set("schemeName", "CUDE-SHA384")
    e.text = evento.cude

    e = etree.SubElement(root, _ns_tag("cbc", "IssueDate"))
    e.text = evento.fecha_emision.strftime("%Y-%m-%d")

    e = etree.SubElement(root, _ns_tag("cbc", "IssueTime"))
    if evento.fecha_emision.tzinfo:
        offset = evento.fecha_emision.strftime("%z")
        hora_tz = f"{evento.fecha_emision.strftime('%H:%M:%S')}{offset[:3]}:{offset[3:]}"
    else:
        hora_tz = f"{evento.fecha_emision.strftime('%H:%M:%S')}-05:00"
    e.text = hora_tz


def _agregar_parte(root, parte: ParteEvento, tag: str) -> None:
    """
    Agrega un <cac:SenderParty> o <cac:ReceiverParty> con los datos.

    La estructura es la misma para ambos roles; solo cambia el nombre
    del wrapper.
    """
    wrapper = etree.SubElement(root, _ns_tag("cac", tag))
    party = etree.SubElement(wrapper, _ns_tag("cac", "Party"))

    # PartyIdentification
    pid = etree.SubElement(party, _ns_tag("cac", "PartyIdentification"))
    pid_id = etree.SubElement(pid, _ns_tag("cbc", "ID"))
    pid_id.set("schemeAgencyID", "195")
    pid_id.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    pid_id.set("schemeID", parte.dv)
    pid_id.set("schemeName", parte.tipo_documento_id)
    pid_id.text = parte.nit

    # PartyName (razón social comercial)
    pname = etree.SubElement(party, _ns_tag("cac", "PartyName"))
    name = etree.SubElement(pname, _ns_tag("cbc", "Name"))
    name.text = parte.razon_social

    # PhysicalLocation (dirección)
    if parte.direccion:
        loc = etree.SubElement(party, _ns_tag("cac", "PhysicalLocation"))
        addr = etree.SubElement(loc, _ns_tag("cac", "Address"))

        addr_city_code = etree.SubElement(addr, _ns_tag("cbc", "ID"))
        addr_city_code.text = parte.municipio_codigo

        addr_city_name = etree.SubElement(addr, _ns_tag("cbc", "CityName"))
        addr_city_name.text = _nombre_municipio(parte.municipio_codigo)

        addr_country_subentity = etree.SubElement(addr, _ns_tag("cbc", "CountrySubentity"))
        addr_country_subentity.text = _nombre_departamento(parte.departamento_codigo)

        addr_country_subentity_code = etree.SubElement(addr, _ns_tag("cbc", "CountrySubentityCode"))
        addr_country_subentity_code.text = parte.departamento_codigo

        addr_line = etree.SubElement(addr, _ns_tag("cac", "AddressLine"))
        line = etree.SubElement(addr_line, _ns_tag("cbc", "Line"))
        line.text = parte.direccion

        country = etree.SubElement(addr, _ns_tag("cac", "Country"))
        country_id = etree.SubElement(country, _ns_tag("cbc", "IdentificationCode"))
        country_id.text = parte.pais_codigo

    # PartyTaxScheme (régimen fiscal)
    tax = etree.SubElement(party, _ns_tag("cac", "PartyTaxScheme"))

    tax_name = etree.SubElement(tax, _ns_tag("cbc", "RegistrationName"))
    tax_name.text = parte.razon_social

    tax_id = etree.SubElement(tax, _ns_tag("cbc", "CompanyID"))
    tax_id.set("schemeAgencyID", "195")
    tax_id.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    tax_id.set("schemeID", parte.dv)
    tax_id.set("schemeName", parte.tipo_documento_id)
    tax_id.text = parte.nit

    tax_level = etree.SubElement(tax, _ns_tag("cbc", "TaxLevelCode"))
    tax_level.set("listName", parte.obligaciones)
    tax_level.text = parte.regimen_fiscal

    tax_scheme = etree.SubElement(tax, _ns_tag("cac", "TaxScheme"))
    ts_id = etree.SubElement(tax_scheme, _ns_tag("cbc", "ID"))
    ts_id.text = "01"  # IVA por defecto

    # PartyLegalEntity
    pli = etree.SubElement(party, _ns_tag("cac", "PartyLegalEntity"))

    pli_name = etree.SubElement(pli, _ns_tag("cbc", "RegistrationName"))
    pli_name.text = parte.razon_social

    pli_id = etree.SubElement(pli, _ns_tag("cbc", "CompanyID"))
    pli_id.set("schemeAgencyID", "195")
    pli_id.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    pli_id.set("schemeID", parte.dv)
    pli_id.set("schemeName", parte.tipo_documento_id)
    pli_id.text = parte.nit

    # Contact (opcional pero recomendado por DIAN)
    if parte.email:
        contact = etree.SubElement(party, _ns_tag("cac", "Contact"))
        c_email = etree.SubElement(contact, _ns_tag("cbc", "ElectronicMail"))
        c_email.text = parte.email


def _agregar_document_response(root, evento: EventoRadian) -> None:
    """
    Agrega el bloque <cac:DocumentResponse> que es el evento propiamente:
      - Response: código del evento + descripción
      - DocumentReference: factura sobre la cual se acusa
      - IssuerParty: emisor de la factura referida
      - RecipientParty: receptor de la factura referida
    """
    info = EVENTOS[evento.tipo_evento]
    dr = etree.SubElement(root, _ns_tag("cac", "DocumentResponse"))

    # Response
    resp = etree.SubElement(dr, _ns_tag("cac", "Response"))
    rc = etree.SubElement(resp, _ns_tag("cbc", "ResponseCode"))
    rc.text = info["responseCode"]
    desc = etree.SubElement(resp, _ns_tag("cbc", "Description"))
    desc.text = info["descripcion"]

    # Si es reclamo (031), agregar código de reclamo
    if evento.tipo_evento == "031" and evento.codigo_reclamo:
        # DIAN usa "EffectiveDate" o un Description adicional para el código
        # Aquí usamos un Description adicional con el código y razón
        razon = CODIGOS_RECLAMO.get(evento.codigo_reclamo, "")
        desc2 = etree.SubElement(resp, _ns_tag("cbc", "Description"))
        desc2.text = f"{evento.codigo_reclamo} - {razon}"

    # DocumentReference (la factura referida)
    docref = etree.SubElement(dr, _ns_tag("cac", "DocumentReference"))

    ref_id = etree.SubElement(docref, _ns_tag("cbc", "ID"))
    ref_id.text = evento.factura.numero

    ref_uuid = etree.SubElement(docref, _ns_tag("cbc", "UUID"))
    ref_uuid.set("schemeName", "CUFE-SHA384")
    ref_uuid.text = evento.factura.cufe

    ref_date = etree.SubElement(docref, _ns_tag("cbc", "IssueDate"))
    ref_date.text = evento.factura.fecha_emision.strftime("%Y-%m-%d")

    ref_type = etree.SubElement(docref, _ns_tag("cbc", "DocumentTypeCode"))
    ref_type.text = "01"  # Factura electrónica de venta

    # ValidityPeriod con monto (algunos eventos lo piden)
    val = etree.SubElement(docref, _ns_tag("cac", "ValidityPeriod"))
    val_amount = etree.SubElement(val, _ns_tag("cbc", "DurationMeasure"))
    val_amount.set("unitCode", "DAY")
    val_amount.text = "0"

    # IssuerParty del DocumentReference (proveedor original)
    _agregar_party_inline(dr, evento.receptor, "IssuerParty")

    # RecipientParty del DocumentReference (adquiriente)
    _agregar_party_inline(dr, evento.emisor, "RecipientParty")


def _agregar_party_inline(parent, parte: ParteEvento, tag: str) -> None:
    """
    Versión simplificada de _agregar_parte para usar dentro de
    DocumentResponse. Solo incluye PartyTaxScheme y PartyLegalEntity.
    """
    wrapper = etree.SubElement(parent, _ns_tag("cac", tag))
    party = etree.SubElement(wrapper, _ns_tag("cac", "Party"))

    pid = etree.SubElement(party, _ns_tag("cac", "PartyIdentification"))
    pid_id = etree.SubElement(pid, _ns_tag("cbc", "ID"))
    pid_id.set("schemeAgencyID", "195")
    pid_id.set("schemeAgencyName", "CO, DIAN (Dirección de Impuestos y Aduanas Nacionales)")
    pid_id.set("schemeID", parte.dv)
    pid_id.set("schemeName", parte.tipo_documento_id)
    pid_id.text = parte.nit


# ════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════

def _validar_evento(evento: EventoRadian) -> None:
    """Valida campos críticos."""
    if evento.tipo_evento not in EVENTOS:
        raise ValueError(
            f"tipo_evento inválido: {evento.tipo_evento!r}. "
            f"Válidos: {list(EVENTOS.keys())}"
        )
    if not evento.cude or len(evento.cude) != 96:
        raise ValueError(
            f"CUDE debe ser hex SHA-384 de 96 caracteres, "
            f"recibí longitud {len(evento.cude) if evento.cude else 0}"
        )
    if not evento.num_evento:
        raise ValueError("num_evento es obligatorio")
    if evento.tipo_evento == "031" and not evento.codigo_reclamo:
        raise ValueError(
            "Para evento 031 (reclamo) debe especificarse codigo_reclamo "
            "(01, 02, 03 o 04)"
        )
    if evento.tipo_evento == "031" and evento.codigo_reclamo not in CODIGOS_RECLAMO:
        raise ValueError(
            f"codigo_reclamo inválido: {evento.codigo_reclamo!r}. "
            f"Válidos: {list(CODIGOS_RECLAMO.keys())}"
        )
    if not evento.factura.cufe or len(evento.factura.cufe) != 96:
        raise ValueError("factura.cufe debe ser hex SHA-384 de 96 caracteres")
    if not evento.emisor.nit.isdigit() or not evento.receptor.nit.isdigit():
        raise ValueError("Los NITs deben ser solo dígitos")


# Catálogos mínimos (los reales son tablas DANE completas)
# Esto solo cubre los casos más comunes; el módulo real debería leer de
# core/data/dane_municipios.json. Por ahora hardcoded para empezar.
_MUNICIPIOS = {
    "05001": "Medellín",
    "11001": "Bogotá D.C.",
    "76001": "Cali",
    "08001": "Barranquilla",
    "05266": "Envigado",
    "05088": "Bello",
    "05360": "Itagüí",
}

_DEPARTAMENTOS = {
    "05": "Antioquia",
    "11": "Bogotá D.C.",
    "76": "Valle del Cauca",
    "08": "Atlántico",
    "25": "Cundinamarca",
}


def _nombre_municipio(codigo: str) -> str:
    return _MUNICIPIOS.get(codigo, codigo)


def _nombre_departamento(codigo: str) -> str:
    return _DEPARTAMENTOS.get(codigo, codigo)
