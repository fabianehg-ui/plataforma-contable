"""
Tests del procesador_dian_xml.

Construye XMLs UBL 2.1 sintéticos (ajustados al formato DIAN) y verifica:
- Parseo de cabecera, ítems, IVA, retenciones
- Detección de empresa por NIT receptor
- Aplicación de mapeo NIT + reglas_item
- Cuadre Db = Cr en plano generado
- Manejo de NIT no catalogado (pendiente_revision)
- Manejo de NC (créditos en lugar de débitos)
- Empaquetamiento ZIP de ZIPs
"""

import io
import json
import zipfile
import unittest
from decimal import Decimal
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "core" / "procesadores"))

from procesador_dian_xml import (  # type: ignore
    RegistryEmpresas,
    parsear_xml_dian,
    aplicar_mapeo,
    GeneradorPlano,
    procesar_zip,
    extraer_xmls_de_zip_maestro,
    exportar_plano_txt,
)

EMPRESAS_DIR = Path(__file__).parent.parent / "core" / "data" / "empresas"


# ----------------------------------------------------------------------------
# Helper: construir un XML UBL Invoice mínimo
# ----------------------------------------------------------------------------

def xml_invoice(
    nit_receptor="900451388",
    nombre_receptor="Silla Tres SAS",
    nit_emisor="890900099",
    nombre_emisor="Industrias Estra S.A",
    cufe="abc123" * 16,  # 96 chars
    prefijo="FE",
    numero="12345",
    fecha="2026-03-15",
    items=None,
    rete_fuente=0,
    rete_iva=0,
    rete_ica=0,
    tipo="Invoice",  # Invoice | CreditNote | DebitNote
):
    """Devuelve bytes de un XML UBL 2.1 con la estructura mínima que parsea el procesador."""
    items = items or [
        {"desc": "Café x kilo", "cantidad": 10, "precio": 25000, "iva_pct": 19},
    ]

    # Calcular totales
    total_neto = sum(i["cantidad"] * i["precio"] for i in items)
    total_iva = sum(i["cantidad"] * i["precio"] * i.get("iva_pct", 0) / 100 for i in items)
    total_pagar = total_neto + total_iva - rete_fuente - rete_iva - rete_ica

    # Construir líneas
    lineas_xml = []
    line_tag = "InvoiceLine" if tipo == "Invoice" else (
        "CreditNoteLine" if tipo == "CreditNote" else "DebitNoteLine"
    )
    qty_tag = "InvoicedQuantity" if tipo == "Invoice" else (
        "CreditedQuantity" if tipo == "CreditNote" else "DebitedQuantity"
    )

    for idx, it in enumerate(items, 1):
        valor_linea = it["cantidad"] * it["precio"]
        iva_linea = valor_linea * it.get("iva_pct", 0) / 100
        lineas_xml.append(f"""
  <cac:{line_tag}>
    <cbc:ID>{idx}</cbc:ID>
    <cbc:{qty_tag} unitCode="EA">{it["cantidad"]}</cbc:{qty_tag}>
    <cbc:LineExtensionAmount currencyID="COP">{valor_linea}</cbc:LineExtensionAmount>
    <cac:TaxTotal>
      <cbc:TaxAmount currencyID="COP">{iva_linea}</cbc:TaxAmount>
      <cac:TaxSubtotal>
        <cbc:TaxableAmount currencyID="COP">{valor_linea}</cbc:TaxableAmount>
        <cbc:TaxAmount currencyID="COP">{iva_linea}</cbc:TaxAmount>
        <cac:TaxCategory>
          <cbc:Percent>{it.get('iva_pct', 0)}</cbc:Percent>
          <cac:TaxScheme><cbc:ID>01</cbc:ID></cac:TaxScheme>
        </cac:TaxCategory>
      </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:Item>
      <cbc:Description>{it["desc"]}</cbc:Description>
    </cac:Item>
    <cac:Price>
      <cbc:PriceAmount currencyID="COP">{it["precio"]}</cbc:PriceAmount>
    </cac:Price>
  </cac:{line_tag}>
""")

    # TaxTotal global
    tax_totals = []
    if total_iva > 0:
        tax_totals.append(f"""
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="COP">{total_iva}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="COP">{total_neto}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="COP">{total_iva}</cbc:TaxAmount>
      <cac:TaxCategory>
        <cbc:Percent>19</cbc:Percent>
        <cac:TaxScheme><cbc:ID>01</cbc:ID></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>""")
    for valor, sid in [(rete_fuente, "06"), (rete_iva, "05"), (rete_ica, "07")]:
        if valor > 0:
            tax_totals.append(f"""
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="COP">{valor}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="COP">{total_neto}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="COP">{valor}</cbc:TaxAmount>
      <cac:TaxCategory>
        <cac:TaxScheme><cbc:ID>{sid}</cbc:ID></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>""")

    # Namespace de la raíz
    if tipo == "Invoice":
        root_ns = 'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"'
    elif tipo == "CreditNote":
        root_ns = 'xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"'
    else:
        root_ns = 'xmlns="urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2"'

    type_code_tag = ""
    if tipo == "Invoice":
        type_code_tag = "<cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>"
    elif tipo == "CreditNote":
        type_code_tag = "<cbc:CreditNoteTypeCode>91</cbc:CreditNoteTypeCode>"
    elif tipo == "DebitNote":
        type_code_tag = "<cbc:DebitNoteTypeCode>92</cbc:DebitNoteTypeCode>"

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<{tipo} {root_ns}
  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>UBL 2.1</cbc:UBLVersionID>
  <cbc:ID>{prefijo}{numero}</cbc:ID>
  <cbc:UUID>{cufe}</cbc:UUID>
  <cbc:IssueDate>{fecha}</cbc:IssueDate>
  <cbc:DueDate>{fecha}</cbc:DueDate>
  <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
  {type_code_tag}

  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyName><cbc:Name>{nombre_emisor}</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme>
        <cbc:RegistrationName>{nombre_emisor}</cbc:RegistrationName>
        <cbc:CompanyID>{nit_emisor}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>01</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingSupplierParty>

  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyName><cbc:Name>{nombre_receptor}</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme>
        <cbc:RegistrationName>{nombre_receptor}</cbc:RegistrationName>
        <cbc:CompanyID>{nit_receptor}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>01</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingCustomerParty>

  {''.join(tax_totals)}

  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="COP">{total_neto}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="COP">{total_neto}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="COP">{total_neto + total_iva}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="COP">{total_pagar}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>

  {''.join(lineas_xml)}
</{tipo}>
"""
    return xml.encode("utf-8")


def empaquetar_zip_maestro(xmls: list[tuple[str, bytes]]) -> bytes:
    """Empaqueta XMLs como lo haría el bookmarklet (ZIP de ZIPs)."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zmaestro:
        for nombre, xml_bytes in xmls:
            sub = io.BytesIO()
            with zipfile.ZipFile(sub, "w", zipfile.ZIP_DEFLATED) as zsub:
                zsub.writestr(f"{nombre}.xml", xml_bytes)
            zmaestro.writestr(f"{nombre}.zip", sub.getvalue())
        zmaestro.writestr("_MANIFIESTO.txt", f"Total: {len(xmls)}\n")
    return out.getvalue()


# ----------------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------------

class TestParser(unittest.TestCase):
    def test_parsea_factura_basica(self):
        xml = xml_invoice()
        doc = parsear_xml_dian(xml)
        self.assertEqual(doc.nit_emisor, "890900099")
        self.assertEqual(doc.nit_receptor, "900451388")
        self.assertEqual(doc.tipo_codigo, "01")
        self.assertEqual(doc.tipo_nombre, "factura_recibida")
        self.assertEqual(doc.prefijo, "FE")
        self.assertEqual(doc.numero, "12345")
        self.assertEqual(len(doc.items), 1)
        self.assertEqual(doc.items[0].cantidad, Decimal("10"))
        self.assertEqual(doc.items[0].precio_unitario, Decimal("25000"))
        self.assertEqual(doc.iva_total, Decimal("47500"))   # 10*25000*0.19

    def test_parsea_nota_credito(self):
        xml = xml_invoice(tipo="CreditNote", prefijo="NC", numero="999")
        doc = parsear_xml_dian(xml)
        self.assertEqual(doc.tipo_codigo, "91")
        self.assertEqual(doc.tipo_nombre, "nota_credito_recibida")

    def test_parsea_retenciones(self):
        xml = xml_invoice(rete_fuente=6250, rete_iva=7125, rete_ica=2500)
        doc = parsear_xml_dian(xml)
        self.assertEqual(doc.rete_fuente, Decimal("6250"))
        self.assertEqual(doc.rete_iva, Decimal("7125"))
        self.assertEqual(doc.rete_ica, Decimal("2500"))

    def test_multiples_items(self):
        xml = xml_invoice(items=[
            {"desc": "Café Premium 1kg", "cantidad": 5, "precio": 30000, "iva_pct": 19},
            {"desc": "Resma de papel A4", "cantidad": 10, "precio": 18000, "iva_pct": 19},
            {"desc": "Servicio de consultoría", "cantidad": 1, "precio": 500000, "iva_pct": 19},
        ])
        doc = parsear_xml_dian(xml)
        self.assertEqual(len(doc.items), 3)
        # Servicio de consultoría debe detectarse como servicio
        servicios = [it for it in doc.items if it.es_servicio]
        self.assertEqual(len(servicios), 1)
        self.assertIn("consultor", servicios[0].descripcion.lower())


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)

    def test_lista_empresas(self):
        emps = self.reg.listar()
        self.assertEqual(len(emps), 2)
        nits = {e["nit"] for e in emps}
        self.assertIn("900473959", nits)
        self.assertIn("900451388", nits)

    def test_busca_por_nit(self):
        emp = self.reg.buscar_por_nit("900451388")
        self.assertIsNotNone(emp)
        self.assertEqual(emp["id"], "silla_tres")

    def test_busca_por_nit_con_dv(self):
        # Algunos XMLs traen el NIT con DV (900451388-9), debe funcionar igual
        emp = self.reg.buscar_por_nit("900451388-9")
        self.assertIsNotNone(emp)

    def test_busca_nit_inexistente(self):
        self.assertIsNone(self.reg.buscar_por_nit("999999999"))

    def test_carga_bundle(self):
        bundle = self.reg.cargar("silla_tres")
        self.assertEqual(bundle["empresa"]["nit"], "900451388")
        self.assertIn("890900099", bundle["mapeo"]["mapeo"])


class TestMapeo(unittest.TestCase):
    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)
        self.bundle = self.reg.cargar("silla_tres")

    def test_nit_catalogado_default(self):
        # Industrias Estra (890900099) con ítem genérico
        xml = xml_invoice(items=[
            {"desc": "Producto genérico", "cantidad": 1, "precio": 100000, "iva_pct": 19}
        ])
        doc = parsear_xml_dian(xml)
        aplicar_mapeo(doc, self.bundle)
        self.assertFalse(doc.pendiente_revision)
        self.assertEqual(doc.items[0].cuenta, "519560")
        self.assertEqual(doc.items[0].centro_costo, "ADMIN")
        self.assertEqual(doc.items[0].regla_aplicada, "DEFAULT_NIT")

    def test_nit_catalogado_regla_papel(self):
        # Mismo NIT pero ítem que matchea regla de papelería
        xml = xml_invoice(items=[
            {"desc": "Resma de papel bond carta", "cantidad": 5, "precio": 18000, "iva_pct": 19}
        ])
        doc = parsear_xml_dian(xml)
        aplicar_mapeo(doc, self.bundle)
        self.assertEqual(doc.items[0].cuenta, "519515")  # Papelería
        self.assertIn("REGLA_ITEM", doc.items[0].regla_aplicada)

    def test_nit_no_catalogado(self):
        # Item genérico (no alimenticio) para forzar fallback verdadero
        xml = xml_invoice(
            nit_emisor="999999999",
            nombre_emisor="Proveedor Desconocido",
            items=[{"desc": "Producto genérico XYZ", "cantidad": 1, "precio": 100000, "iva_pct": 19}],
        )
        doc = parsear_xml_dian(xml)
        aplicar_mapeo(doc, self.bundle)
        self.assertTrue(doc.pendiente_revision)
        self.assertIn("999999999", doc.razon_pendiente)
        self.assertEqual(doc.items[0].regla_aplicada, "FALLBACK_GLOBAL")
        self.assertEqual(doc.items[0].cuenta, "519095")

    def test_factura_multiitem_distintas_cuentas(self):
        # Industrias Estra con ítems mixtos: papel + café
        xml = xml_invoice(items=[
            {"desc": "Café Premium 1kg", "cantidad": 5, "precio": 30000, "iva_pct": 19},
            {"desc": "Resma de papel A4", "cantidad": 10, "precio": 18000, "iva_pct": 19},
            {"desc": "Vasos plásticos", "cantidad": 100, "precio": 500, "iva_pct": 19},
        ])
        doc = parsear_xml_dian(xml)
        aplicar_mapeo(doc, self.bundle)
        cuentas = [it.cuenta for it in doc.items]
        self.assertEqual(cuentas[0], "519560")  # café
        self.assertEqual(cuentas[1], "519515")  # papel
        self.assertEqual(cuentas[2], "519560")  # default (vasos no matchea ninguna regla)


class TestPlano(unittest.TestCase):
    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)

    def test_factura_simple_cuadra(self):
        xml = xml_invoice(items=[
            {"desc": "Producto X", "cantidad": 1, "precio": 100000, "iva_pct": 19}
        ])
        zip_bytes = empaquetar_zip_maestro([("doc1", xml)])
        resultados = procesar_zip(zip_bytes, self.reg, "202603")
        self.assertEqual(len(resultados), 1)
        r = resultados[0]
        self.assertTrue(r.cuadrado, f"Db={r.cuadre_db} Cr={r.cuadre_cr}")
        self.assertEqual(r.empresa_id, "silla_tres")

    def test_nota_credito_invierte_signos(self):
        xml = xml_invoice(
            tipo="CreditNote", prefijo="NC", numero="555",
            items=[{"desc": "Producto X", "cantidad": 1, "precio": 100000, "iva_pct": 19}],
        )
        zip_bytes = empaquetar_zip_maestro([("nc1", xml)])
        resultados = procesar_zip(zip_bytes, self.reg, "202603")
        r = resultados[0]
        self.assertTrue(r.cuadrado)
        # En NC, las líneas de gasto van a CRÉDITO
        gasto = [l for l in r.lineas_plano if l.cuenta == "519560"]
        self.assertTrue(any(l.credito > 0 for l in gasto))
        self.assertTrue(all(l.debito == 0 for l in gasto))

    def test_factura_con_retenciones_cuadra(self):
        xml = xml_invoice(
            items=[{"desc": "Producto X", "cantidad": 1, "precio": 1000000, "iva_pct": 19}],
            rete_fuente=25000, rete_iva=28500, rete_ica=10000,
        )
        zip_bytes = empaquetar_zip_maestro([("doc1", xml)])
        resultados = procesar_zip(zip_bytes, self.reg, "202603")
        r = resultados[0]
        self.assertTrue(r.cuadrado, f"Db={r.cuadre_db} Cr={r.cuadre_cr}")

    def test_nit_no_catalogado_genera_pendiente(self):
        xml = xml_invoice(
            nit_emisor="999999999", nombre_emisor="Desconocido SAS",
            items=[{"desc": "Servicio random", "cantidad": 1, "precio": 50000, "iva_pct": 0}]
        )
        zip_bytes = empaquetar_zip_maestro([("doc1", xml)])
        resultados = procesar_zip(zip_bytes, self.reg, "202603")
        r = resultados[0]
        self.assertEqual(len(r.nits_pendientes), 1)
        self.assertEqual(r.nits_pendientes[0]["nit"], "999999999")

    def test_consecutivos_independientes_por_comprobante(self):
        # 2 facturas + 1 NC: COMP 7 debe llevar 1,2 / COMP 13 debe llevar 1
        xmls = [
            ("fe1", xml_invoice(prefijo="FE", numero="100", cufe="a" * 96)),
            ("fe2", xml_invoice(prefijo="FE", numero="101", cufe="b" * 96)),
            ("nc1", xml_invoice(tipo="CreditNote", prefijo="NC", numero="50", cufe="c" * 96)),
        ]
        zip_bytes = empaquetar_zip_maestro(xmls)
        resultados = procesar_zip(zip_bytes, self.reg, "202603")
        r = resultados[0]
        consec_comp7 = sorted({l.consecutivo for l in r.lineas_plano if l.comprobante == "COMP 7"})
        consec_comp13 = sorted({l.consecutivo for l in r.lineas_plano if l.comprobante == "COMP 13"})
        self.assertEqual(consec_comp7, ["202603001", "202603002"])
        self.assertEqual(consec_comp13, ["202603001"])

    def test_separacion_multi_empresa(self):
        # Una factura para Silla Tres (900451388) y otra para Casa UnoTres (900473959)
        xmls = [
            ("st", xml_invoice(nit_receptor="900451388")),
            ("c13", xml_invoice(nit_receptor="900473959")),
        ]
        zip_bytes = empaquetar_zip_maestro(xmls)
        resultados = procesar_zip(zip_bytes, self.reg, "202603")
        ids = {r.empresa_id for r in resultados}
        self.assertIn("silla_tres", ids)
        self.assertIn("casa_unotres", ids)

    def test_xml_con_nit_receptor_desconocido_se_aparta(self):
        xml = xml_invoice(nit_receptor="111111111", nombre_receptor="No-Configurada SAS")
        zip_bytes = empaquetar_zip_maestro([("x", xml)])
        resultados = procesar_zip(zip_bytes, self.reg, "202603")
        # Debe generar un resultado con empresa_id "(no identificada)"
        sin_emp = [r for r in resultados if "no identificada" in r.empresa_id.lower()]
        self.assertEqual(len(sin_emp), 1)

    def test_export_plano_txt_estructura(self):
        xml = xml_invoice()
        zip_bytes = empaquetar_zip_maestro([("doc1", xml)])
        resultados = procesar_zip(zip_bytes, self.reg, "202603")
        r = resultados[0]
        txt = exportar_plano_txt(r.lineas_plano)
        self.assertIn("FECHA\tCOMPROBANTE", txt)
        self.assertIn("COMP 7", txt)
        self.assertIn("890900099", txt)


class TestExtractorZip(unittest.TestCase):
    def test_zip_de_zips(self):
        xml1 = xml_invoice(numero="111", cufe="a" * 96)
        xml2 = xml_invoice(numero="222", cufe="b" * 96)
        zip_bytes = empaquetar_zip_maestro([("doc1", xml1), ("doc2", xml2)])
        xmls = extraer_xmls_de_zip_maestro(zip_bytes)
        self.assertEqual(len(xmls), 2)

    def test_zip_con_xml_directo(self):
        # Algunos casos: ZIP que tiene XMLs directamente sin sub-ZIPs
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            z.writestr("factura1.xml", xml_invoice())
        xmls = extraer_xmls_de_zip_maestro(out.getvalue())
        self.assertEqual(len(xmls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
