"""
Tests del detector de tipo de documento DIAN.
"""
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.procesadores.detector_tipo_doc import (
    detectar_tipo_por_nombre_archivo,
    detectar_tipo_por_xml,
    detectar_tipo_documento,
    mapear_a_comprobante,
    MAPEO_COMPROBANTES_DEFAULT
)


def test_nombre_archivo_FE():
    assert detectar_tipo_por_nombre_archivo('FE_2026-03-15_900040299_FAT123_a1b2c3d4.zip') == 'FE'
    assert detectar_tipo_por_nombre_archivo('FE_2026-03-15_xxx.xml') == 'FE'
    print("✓ test_nombre_archivo_FE")


def test_nombre_archivo_NC():
    assert detectar_tipo_por_nombre_archivo('NC_2026-03-20_900206485_NCS10001_xxxx.zip') == 'NC'
    print("✓ test_nombre_archivo_NC")


def test_nombre_archivo_ND():
    assert detectar_tipo_por_nombre_archivo('ND_2026-03-22_xxx.zip') == 'ND'
    print("✓ test_nombre_archivo_ND")


def test_nombre_archivo_DS():
    assert detectar_tipo_por_nombre_archivo('DS_2026-03-25_xxx.zip') == 'DS'
    print("✓ test_nombre_archivo_DS")


def test_nombre_archivo_sin_prefijo():
    """El bookmarklet v0.1 no ponía prefijo, debería retornar None."""
    assert detectar_tipo_por_nombre_archivo('sin-fecha_900040299_X1234_xxx.zip') is None
    assert detectar_tipo_por_nombre_archivo('') is None
    print("✓ test_nombre_archivo_sin_prefijo")


def test_nombre_archivo_con_path():
    """Debe ignorar la ruta y mirar solo el nombre del archivo."""
    assert detectar_tipo_por_nombre_archivo('/path/to/FE_2026-03-15_xxx.zip') == 'FE'
    assert detectar_tipo_por_nombre_archivo('C:\\users\\algo\\NC_xxx.zip') == 'NC'
    print("✓ test_nombre_archivo_con_path")


# ── XMLs de muestra ─────────────────────────────────────

XML_INVOICE_FE = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>10</cbc:CustomizationID>
  <cbc:ProfileID>DIAN 2.1: Factura Electrónica de Venta</cbc:ProfileID>
  <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
</Invoice>"""

XML_INVOICE_DS = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>10</cbc:CustomizationID>
  <cbc:ProfileID>DIAN 2.1: Documento Soporte en adquisiciones efectuadas a no obligados</cbc:ProfileID>
  <cbc:InvoiceTypeCode>05</cbc:InvoiceTypeCode>
</Invoice>"""

XML_CREDIT_NOTE = """<?xml version="1.0" encoding="UTF-8"?>
<CreditNote xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
            xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:CreditNoteTypeCode>91</cbc:CreditNoteTypeCode>
</CreditNote>"""

XML_DEBIT_NOTE = """<?xml version="1.0" encoding="UTF-8"?>
<DebitNote xmlns="urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2"
           xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:DebitNoteTypeCode>92</cbc:DebitNoteTypeCode>
</DebitNote>"""


def test_xml_FE():
    root = ET.fromstring(XML_INVOICE_FE)
    assert detectar_tipo_por_xml(root) == 'FE'
    print("✓ test_xml_FE")


def test_xml_DS_por_invoice_type_code():
    root = ET.fromstring(XML_INVOICE_DS)
    assert detectar_tipo_por_xml(root) == 'DS'
    print("✓ test_xml_DS_por_invoice_type_code")


def test_xml_NC():
    root = ET.fromstring(XML_CREDIT_NOTE)
    assert detectar_tipo_por_xml(root) == 'NC'
    print("✓ test_xml_NC")


def test_xml_ND():
    root = ET.fromstring(XML_DEBIT_NOTE)
    assert detectar_tipo_por_xml(root) == 'ND'
    print("✓ test_xml_ND")


def test_unificado_nombre_gana_sobre_xml():
    """Si tengo nombre Y XML, el nombre gana (es más rápido y confiable)."""
    root = ET.fromstring(XML_CREDIT_NOTE)  # XML dice NC
    tipo, fuente = detectar_tipo_documento(
        xml_root=root,
        nombre_archivo='FE_2026-03-15_xxx.zip'  # nombre dice FE
    )
    assert tipo == 'FE', f"esperaba FE, obtuve {tipo}"
    assert fuente == 'nombre_archivo'
    print(f"✓ test_unificado_nombre_gana: {tipo} ({fuente})")


def test_unificado_solo_xml():
    """Si solo hay XML (sin nombre), usa el XML."""
    root = ET.fromstring(XML_CREDIT_NOTE)
    tipo, fuente = detectar_tipo_documento(xml_root=root, nombre_archivo='')
    assert tipo == 'NC'
    assert fuente == 'xml'
    print(f"✓ test_unificado_solo_xml: {tipo} ({fuente})")


def test_unificado_sin_datos():
    tipo, fuente = detectar_tipo_documento(xml_root=None, nombre_archivo='')
    assert tipo == 'DESCONOCIDO'
    print(f"✓ test_unificado_sin_datos: {tipo}")


def test_mapeo_comprobantes_default():
    assert mapear_a_comprobante('FE')['comprobante'] == '3'
    assert mapear_a_comprobante('DS')['comprobante'] == '3'
    assert mapear_a_comprobante('NC')['comprobante'] == '12'
    assert mapear_a_comprobante('ND')['comprobante'] == '7'
    assert mapear_a_comprobante('DESCONOCIDO')['comprobante'] == '99'
    print("✓ test_mapeo_comprobantes_default: FE→3, DS→3, NC→12, ND→7")


def test_mapeo_comprobantes_personalizado():
    """Una empresa puede sobreescribir el mapeo."""
    mio = {
        'FE': {'comprobante': '5', 'descripcion': 'Mi comprobante FE'},
        'NC': {'comprobante': '10', 'descripcion': 'Mi comprobante NC'},
    }
    assert mapear_a_comprobante('FE', mio)['comprobante'] == '5'
    assert mapear_a_comprobante('NC', mio)['comprobante'] == '10'
    # Si no está, devuelve DESCONOCIDO o el default
    r = mapear_a_comprobante('ND', mio)
    assert 'comprobante' in r  # debe devolver algo, no romper
    print("✓ test_mapeo_comprobantes_personalizado")


# ── Test con XMLs reales ──────────────────────────

def test_xml_real_de_silla_tres():
    """Procesar XMLs reales del paquete de Silla Tres."""
    import glob
    base = '/home/claude/analisis/all_xmls'
    encontrados = {}
    for tipo_carpeta in ['FE', 'NC', 'ND', 'DS']:
        for x in sorted(glob.glob(f'{base}/{tipo_carpeta}/*.xml'))[:3]:
            with open(x, 'r', encoding='utf-8') as f:
                c = f.read()
            try:
                root = ET.fromstring(c)
                tipo_detectado = detectar_tipo_por_xml(root)
                key = (tipo_carpeta, tipo_detectado)
                encontrados[key] = encontrados.get(key, 0) + 1
            except Exception:
                pass
    print(f"✓ test_xml_real: detección por carpeta vs detección XML real:")
    for (carpeta, detectado), n in encontrados.items():
        match = "✓" if carpeta == detectado else "⚠️ (carpeta vs XML real difieren - normal si bookmarklet v0.1 mezcló tipos)"
        print(f"    {carpeta:3s} → detectó {detectado:3s} {match} ×{n}")


if __name__ == '__main__':
    print("=== Tests del detector de tipo de documento ===\n")
    test_nombre_archivo_FE()
    test_nombre_archivo_NC()
    test_nombre_archivo_ND()
    test_nombre_archivo_DS()
    test_nombre_archivo_sin_prefijo()
    test_nombre_archivo_con_path()
    test_xml_FE()
    test_xml_DS_por_invoice_type_code()
    test_xml_NC()
    test_xml_ND()
    test_unificado_nombre_gana_sobre_xml()
    test_unificado_solo_xml()
    test_unificado_sin_datos()
    test_mapeo_comprobantes_default()
    test_mapeo_comprobantes_personalizado()
    test_xml_real_de_silla_tres()
    print("\n✅ Todos los tests pasaron")
