"""
Detector de tipo de documento DIAN y mapeo a comprobantes contables.

Estrategias de detección (en orden de prioridad):
  1. Prefijo del nombre del archivo (FE_, NC_, ND_, DS_) — el bookmarklet v0.2 los pone
  2. Tag raíz del XML (Invoice/CreditNote/DebitNote)
  3. ProfileID del XML (cuando dice "Documento Soporte")
  4. InvoiceTypeCode (01=FE, 05=DS)

Uso típico:
    from core.procesadores.detector_tipo_doc import detectar_tipo_documento
    tipo = detectar_tipo_documento(xml_root, nombre_archivo='FE_2026-03-15_...zip')
    # → ('FE', 'comprobante_3')
"""
from __future__ import annotations
import re
import xml.etree.ElementTree as ET
from typing import Optional


NS = {
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
}


# Mapeo de tipo DIAN → comprobante contable (configuración Silla Tres)
MAPEO_COMPROBANTES_DEFAULT = {
    'FE': {'comprobante': '3', 'descripcion': 'Causación factura compra'},
    'DS': {'comprobante': '3', 'descripcion': 'Causación documento soporte'},
    'NC': {'comprobante': '12', 'descripcion': 'Nota crédito recibida'},
    'ND': {'comprobante': '7', 'descripcion': 'Nota débito recibida'},
    'ACUSE': {'comprobante': '', 'descripcion': 'Acuse de recibo (no se contabiliza)'},
    'DESCONOCIDO': {'comprobante': '99', 'descripcion': 'Tipo no detectado - revisar manualmente'},
}


def detectar_tipo_por_nombre_archivo(nombre: str) -> Optional[str]:
    """
    Detecta el tipo a partir del prefijo del nombre del archivo.
    El bookmarklet v0.2 pone el tipo de PRIMERO: FE_, NC_, ND_, DS_.

    Returns: 'FE', 'NC', 'ND', 'DS' o None si no detecta.
    """
    if not nombre:
        return None
    n = str(nombre).upper().strip()
    # Quitar ruta si viene
    n = n.split('/')[-1].split('\\')[-1]

    # Patrón: TIPO_ al inicio
    m = re.match(r'^(FE|NC|ND|DS)[_\-]', n)
    if m:
        return m.group(1)

    return None


def get_inner_document(root: ET.Element) -> ET.Element:
    """
    Si el XML es un AttachedDocument, extrae el documento real del Description.
    """
    tag = root.tag.split('}')[-1]
    if tag == 'AttachedDocument':
        for desc in root.iter('{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Description'):
            if desc.text and ('<Invoice' in desc.text or '<CreditNote' in desc.text or '<DebitNote' in desc.text):
                try:
                    return ET.fromstring(desc.text)
                except ET.ParseError:
                    pass
    return root


def detectar_tipo_por_xml(root: ET.Element) -> str:
    """
    Detecta el tipo a partir del contenido del XML.

    Lógica:
    - Tag raíz <CreditNote>          → NC
    - Tag raíz <DebitNote>           → ND
    - Tag raíz <ApplicationResponse> → ACUSE (acuse de recibo, no contable)
    - Tag raíz <Invoice> y…
        InvoiceTypeCode = '01'   → FE
        InvoiceTypeCode = '05'   → DS  (se le llama "Documento soporte")
        ProfileID contiene "Documento Soporte" → DS
        En otro caso             → FE  (default razonable)

    Returns: 'FE', 'NC', 'ND', 'DS', 'ACUSE' o 'DESCONOCIDO'
    """
    inner = get_inner_document(root)
    tag = inner.tag.split('}')[-1]

    if tag == 'CreditNote':
        return 'NC'
    if tag == 'DebitNote':
        return 'ND'
    if tag == 'ApplicationResponse':
        return 'ACUSE'

    if tag == 'Invoice':
        # Distinguir FE de DS
        itc = inner.find('cbc:InvoiceTypeCode', NS)
        itc_val = itc.text.strip() if itc is not None and itc.text else ''

        prof = inner.find('cbc:ProfileID', NS)
        prof_val = (prof.text or '').upper() if prof is not None else ''

        # InvoiceTypeCode oficiales DIAN:
        # 01 = Factura de Venta
        # 02 = Factura de Exportación
        # 03 = Factura por contingencia
        # 04 = Factura de contingencia
        # 05 = Documento Soporte
        if itc_val == '05':
            return 'DS'
        # ProfileID a veces dice "Documento Soporte en adquisiciones efectuadas"
        if 'DOCUMENTO SOPORTE' in prof_val or 'DS-' in prof_val or 'SOPORTE' in prof_val:
            return 'DS'

        # Default: factura electrónica
        return 'FE'

    return 'DESCONOCIDO'


def detectar_tipo_documento(
    xml_root: Optional[ET.Element] = None,
    nombre_archivo: str = '',
    contenido_xml: str = ''
) -> tuple[str, str]:
    """
    Detección unificada en orden de prioridad:
      1. Prefijo del nombre de archivo (más rápido y confiable si viene del bookmarklet v0.2)
      2. Análisis del contenido XML

    Returns: (tipo, fuente) donde:
      - tipo: 'FE'|'NC'|'ND'|'DS'|'DESCONOCIDO'
      - fuente: 'nombre_archivo'|'xml'|'sin_datos'
    """
    # Prioridad 1: nombre del archivo
    if nombre_archivo:
        tipo = detectar_tipo_por_nombre_archivo(nombre_archivo)
        if tipo:
            return (tipo, 'nombre_archivo')

    # Prioridad 2: análisis del XML
    if xml_root is None and contenido_xml:
        try:
            xml_root = ET.fromstring(contenido_xml)
        except ET.ParseError:
            return ('DESCONOCIDO', 'sin_datos')

    if xml_root is not None:
        tipo = detectar_tipo_por_xml(xml_root)
        return (tipo, 'xml')

    return ('DESCONOCIDO', 'sin_datos')


def mapear_a_comprobante(
    tipo: str,
    catalogo_comprobantes: Optional[dict] = None
) -> dict:
    """
    Devuelve la información del comprobante contable correspondiente al tipo.

    Args:
      tipo: 'FE'|'NC'|'ND'|'DS'|'DESCONOCIDO'
      catalogo_comprobantes: opcional, dict con la configuración de la empresa.
        Si es None, usa MAPEO_COMPROBANTES_DEFAULT.

    Returns: dict con 'comprobante', 'descripcion'.
    """
    catalogo = catalogo_comprobantes or MAPEO_COMPROBANTES_DEFAULT
    return catalogo.get(tipo, catalogo.get('DESCONOCIDO', {
        'comprobante': '99',
        'descripcion': 'Tipo no detectado'
    }))
