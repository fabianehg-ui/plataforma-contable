"""Tests v0.2.2 — IVA discriminado por tarifa, impuestos especiales, auto-insumos."""
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core" / "procesadores"))
sys.path.insert(0, str(Path(__file__).parent))

from procesador_dian_xml import (
    RegistryEmpresas,
    parsear_xml_dian,
    aplicar_mapeo,
    procesar_multiples_zips,
    ZipInput,
    _es_insumo_alimenticio,
)
from test_procesador_dian_xml import xml_invoice, empaquetar_zip_maestro

EMPRESAS_DIR = Path(__file__).parent.parent / "core" / "data" / "empresas"


# Helper para construir XMLs con impuestos especiales (INC, IBUA, ICUI)
def xml_invoice_con_impuestos(
    nit_emisor="800176100",
    nombre_emisor="D'CARNES S.A",
    nit_receptor="900451388",
    items=None,
    inc_valor=0, inc_pct=8,
    ibua_valor=0,
    icui_valor=0,
    cufe="x" * 96, prefijo="FE", numero="123", fecha="2026-03-15",
):
    """Genera XML UBL con TaxScheme adicionales para impuestos especiales."""
    items = items or [{"desc": "Producto X", "cantidad": 1, "precio": 100000, "iva_pct": 19}]
    total_neto = sum(i["cantidad"] * i["precio"] for i in items)
    total_iva = sum(i["cantidad"] * i["precio"] * i.get("iva_pct", 0) / 100 for i in items)

    # TaxTotal del IVA
    tax_totals_xml = []
    if total_iva > 0:
        tax_totals_xml.append(f"""
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="COP">{total_iva}</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="COP">{total_neto}</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="COP">{total_iva}</cbc:TaxAmount>
                <cac:TaxCategory>
                    <cbc:Percent>19</cbc:Percent>
                    <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
                </cac:TaxCategory>
            </cac:TaxSubtotal>
        </cac:TaxTotal>""")
    if inc_valor > 0:
        tax_totals_xml.append(f"""
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="COP">{inc_valor}</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="COP">{total_neto}</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="COP">{inc_valor}</cbc:TaxAmount>
                <cac:TaxCategory>
                    <cbc:Percent>{inc_pct}</cbc:Percent>
                    <cac:TaxScheme><cbc:ID>04</cbc:ID><cbc:Name>INC</cbc:Name></cac:TaxScheme>
                </cac:TaxCategory>
            </cac:TaxSubtotal>
        </cac:TaxTotal>""")
    if ibua_valor > 0:
        tax_totals_xml.append(f"""
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="COP">{ibua_valor}</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="COP">{total_neto}</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="COP">{ibua_valor}</cbc:TaxAmount>
                <cac:TaxCategory>
                    <cac:TaxScheme><cbc:ID>35</cbc:ID><cbc:Name>IBUA</cbc:Name></cac:TaxScheme>
                </cac:TaxCategory>
            </cac:TaxSubtotal>
        </cac:TaxTotal>""")
    if icui_valor > 0:
        tax_totals_xml.append(f"""
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="COP">{icui_valor}</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="COP">{total_neto}</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="COP">{icui_valor}</cbc:TaxAmount>
                <cac:TaxCategory>
                    <cac:TaxScheme><cbc:ID>34</cbc:ID><cbc:Name>ICUI</cbc:Name></cac:TaxScheme>
                </cac:TaxCategory>
            </cac:TaxSubtotal>
        </cac:TaxTotal>""")

    total_pagar = total_neto + total_iva + inc_valor + ibua_valor + icui_valor

    # Líneas
    lineas_xml = []
    for idx, it in enumerate(items, 1):
        valor_l = it["cantidad"] * it["precio"]
        iva_l = valor_l * it.get("iva_pct", 0) / 100
        lineas_xml.append(f"""
        <cac:InvoiceLine>
            <cbc:ID>{idx}</cbc:ID>
            <cbc:InvoicedQuantity unitCode="EA">{it['cantidad']}</cbc:InvoicedQuantity>
            <cbc:LineExtensionAmount currencyID="COP">{valor_l}</cbc:LineExtensionAmount>
            <cac:TaxTotal>
                <cbc:TaxAmount currencyID="COP">{iva_l}</cbc:TaxAmount>
                <cac:TaxSubtotal>
                    <cbc:TaxableAmount currencyID="COP">{valor_l}</cbc:TaxableAmount>
                    <cbc:TaxAmount currencyID="COP">{iva_l}</cbc:TaxAmount>
                    <cac:TaxCategory>
                        <cbc:Percent>{it.get('iva_pct', 0)}</cbc:Percent>
                        <cac:TaxScheme><cbc:ID>01</cbc:ID></cac:TaxScheme>
                    </cac:TaxCategory>
                </cac:TaxSubtotal>
            </cac:TaxTotal>
            <cac:Item><cbc:Description>{it['desc']}</cbc:Description></cac:Item>
            <cac:Price><cbc:PriceAmount currencyID="COP">{it['precio']}</cbc:PriceAmount></cac:Price>
        </cac:InvoiceLine>""")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>{prefijo}{numero}</cbc:ID>
    <cbc:UUID>{cufe}</cbc:UUID>
    <cbc:IssueDate>{fecha}</cbc:IssueDate>
    <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
    <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>

    <cac:AccountingSupplierParty><cac:Party>
        <cac:PartyName><cbc:Name>{nombre_emisor}</cbc:Name></cac:PartyName>
        <cac:PartyTaxScheme>
            <cbc:RegistrationName>{nombre_emisor}</cbc:RegistrationName>
            <cbc:CompanyID>{nit_emisor}</cbc:CompanyID>
            <cac:TaxScheme><cbc:ID>01</cbc:ID></cac:TaxScheme>
        </cac:PartyTaxScheme>
    </cac:Party></cac:AccountingSupplierParty>

    <cac:AccountingCustomerParty><cac:Party>
        <cac:PartyTaxScheme>
            <cbc:RegistrationName>Silla Tres SAS</cbc:RegistrationName>
            <cbc:CompanyID>{nit_receptor}</cbc:CompanyID>
            <cac:TaxScheme><cbc:ID>01</cbc:ID></cac:TaxScheme>
        </cac:PartyTaxScheme>
    </cac:Party></cac:AccountingCustomerParty>

    {''.join(tax_totals_xml)}

    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="COP">{total_neto}</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="COP">{total_neto}</cbc:TaxExclusiveAmount>
        <cbc:PayableAmount currencyID="COP">{total_pagar}</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>

    {''.join(lineas_xml)}
</Invoice>"""
    return xml.encode("utf-8")


class TestIvaPorTarifa(unittest.TestCase):
    """Verifica que el plano discrimine IVA 5% del 19%."""

    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)

    def test_factura_iva_19_va_a_24080201(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice(
                nit_emisor="890900099", nombre_emisor="Industrias Estra",
                items=[{"desc": "Producto", "cantidad": 1, "precio": 100000, "iva_pct": 19}],
                cufe="a" * 96,
            )),
        ])
        zips = [ZipInput(nombre="z.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603", modo_filtro_fecha="ninguno")
        cuentas_iva = [l.cuenta for l in resultados[0].lineas_plano if l.cuenta.startswith("2408")]
        self.assertIn("24080201", cuentas_iva)

    def test_factura_iva_5_va_a_24080203(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice(
                nit_emisor="890900099", nombre_emisor="Industrias Estra",
                items=[{"desc": "Producto exento parcial", "cantidad": 1, "precio": 100000, "iva_pct": 5}],
                cufe="b" * 96,
            )),
        ])
        zips = [ZipInput(nombre="z.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603", modo_filtro_fecha="ninguno")
        cuentas_iva = [l.cuenta for l in resultados[0].lineas_plano if l.cuenta.startswith("2408")]
        self.assertIn("24080203", cuentas_iva)
        self.assertNotIn("24080201", cuentas_iva)

    def test_factura_mixta_5_y_19_genera_dos_lineas_iva(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice(
                nit_emisor="890900099", nombre_emisor="Industrias Estra",
                items=[
                    {"desc": "Producto 19%", "cantidad": 1, "precio": 100000, "iva_pct": 19},
                    {"desc": "Producto 5%", "cantidad": 1, "precio": 50000, "iva_pct": 5},
                ],
                cufe="c" * 96,
            )),
        ])
        zips = [ZipInput(nombre="z.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603", modo_filtro_fecha="ninguno")
        cuentas_iva = [l.cuenta for l in resultados[0].lineas_plano if l.cuenta.startswith("2408")]
        # Debe tener AMBAS cuentas distintas
        self.assertIn("24080201", cuentas_iva)
        self.assertIn("24080203", cuentas_iva)
        # Y la suma debe cuadrar
        self.assertTrue(resultados[0].cuadrado)

    def test_porcentaje_iva_se_registra_en_linea(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice(
                nit_emisor="890900099", nombre_emisor="Industrias Estra",
                items=[{"desc": "P", "cantidad": 1, "precio": 100000, "iva_pct": 19}],
                cufe="d" * 96,
            )),
        ])
        zips = [ZipInput(nombre="z.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603", modo_filtro_fecha="ninguno")
        # La línea de IVA debe tener porcentaje=19
        linea_iva = next(l for l in resultados[0].lineas_plano if l.cuenta == "24080201")
        self.assertEqual(linea_iva.porcentaje, Decimal("19"))


class TestImpuestosEspeciales(unittest.TestCase):
    """Verifica el parsing y asentamiento de INC, IBUA, ICUI."""

    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)

    def test_parsea_inc(self):
        xml = xml_invoice_con_impuestos(
            inc_valor=8000,
            items=[{"desc": "Comida", "cantidad": 1, "precio": 100000, "iva_pct": 0}],
        )
        doc = parsear_xml_dian(xml)
        self.assertEqual(doc.inc_total, Decimal("8000"))
        self.assertEqual(doc.iva_total, Decimal("0"))

    def test_parsea_ibua(self):
        xml = xml_invoice_con_impuestos(
            nit_emisor="890903939", nombre_emisor="POSTOBON S.A.",
            ibua_valor=2500,
            items=[{"desc": "Bebida azucarada", "cantidad": 1, "precio": 50000, "iva_pct": 19}],
        )
        doc = parsear_xml_dian(xml)
        self.assertEqual(doc.ibua_total, Decimal("2500"))

    def test_parsea_icui(self):
        xml = xml_invoice_con_impuestos(
            icui_valor=1500,
            items=[{"desc": "Comestible ultra-procesado", "cantidad": 1, "precio": 30000, "iva_pct": 19}],
        )
        doc = parsear_xml_dian(xml)
        self.assertEqual(doc.icui_total, Decimal("1500"))

    def test_inc_genera_linea_en_plano_24080530(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice_con_impuestos(
                inc_valor=8000,
                items=[{"desc": "Almuerzo restaurante", "cantidad": 1, "precio": 100000, "iva_pct": 0}],
                cufe="e" * 96,
            )),
        ])
        zips = [ZipInput(nombre="z.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603", modo_filtro_fecha="ninguno")
        cuentas = [l.cuenta for l in resultados[0].lineas_plano]
        self.assertIn("24080530", cuentas)
        self.assertTrue(resultados[0].cuadrado)

    def test_ibua_genera_linea_en_plano_24080540(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice_con_impuestos(
                nit_emisor="890903939", nombre_emisor="POSTOBON S.A.",
                ibua_valor=2500,
                items=[{"desc": "Bebida", "cantidad": 1, "precio": 50000, "iva_pct": 19}],
                cufe="f" * 96,
            )),
        ])
        zips = [ZipInput(nombre="z.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603", modo_filtro_fecha="ninguno")
        cuentas = [l.cuenta for l in resultados[0].lineas_plano]
        self.assertIn("24080540", cuentas)
        self.assertTrue(resultados[0].cuadrado)

    def test_factura_con_iva_e_impuestos_especiales_cuadra(self):
        # Factura tipo Postobón con IVA 19% + IBUA
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice_con_impuestos(
                nit_emisor="890903939", nombre_emisor="POSTOBON S.A.",
                ibua_valor=3500, inc_valor=4000,
                items=[{"desc": "Bebida azucarada x 12", "cantidad": 1, "precio": 100000, "iva_pct": 19}],
                cufe="g" * 96,
            )),
        ])
        zips = [ZipInput(nombre="z.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603", modo_filtro_fecha="ninguno")
        self.assertTrue(resultados[0].cuadrado)
        cuentas = set(l.cuenta for l in resultados[0].lineas_plano)
        self.assertIn("24080201", cuentas)  # IVA 19%
        self.assertIn("24080540", cuentas)  # IBUA
        self.assertIn("24080530", cuentas)  # INC


class TestAutoInsumosAlimenticios(unittest.TestCase):
    """Verifica que NITs no catalogados de alimentos vayan a 143505 automáticamente."""

    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)

    def test_detector_por_nombre_emisor(self):
        # Postobón es bebidas
        self.assertTrue(_es_insumo_alimenticio("POSTOBON S.A.", "Producto X"))
        # D'Carnes
        self.assertTrue(_es_insumo_alimenticio("D'CARNES S.A", "Producto X"))
        # Colanta
        self.assertTrue(_es_insumo_alimenticio("COOPERATIVA COLANTA", "Producto X"))
        # No alimenticio
        self.assertFalse(_es_insumo_alimenticio("SIIGO S.A.S", "Software"))

    def test_detector_por_descripcion_item(self):
        self.assertTrue(_es_insumo_alimenticio("ALMACEN XYZ", "Pollo entero 2kg"))
        self.assertTrue(_es_insumo_alimenticio("PROVEEDOR", "Leche entera 1 litro"))
        self.assertTrue(_es_insumo_alimenticio("XYZ", "Tomate, cebolla, papa"))

    def test_postobon_no_catalogado_va_a_143505(self):
        # NIT que NO está en mapeo_nits.json de Silla Tres
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice(
                nit_emisor="890903939",
                nombre_emisor="POSTOBON S.A.",
                items=[{"desc": "Bebida gaseosa 350ml", "cantidad": 12, "precio": 2000, "iva_pct": 19}],
                cufe="h" * 96,
            )),
        ])
        zips = [ZipInput(nombre="z.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603", modo_filtro_fecha="ninguno")

        # La línea de gasto debe ir a 143505 (no a 519095 PENDIENTE)
        lineas_gasto = [l for l in resultados[0].lineas_plano
                        if not l.cuenta.startswith("2") and not l.cuenta.startswith("220")]
        self.assertTrue(any(l.cuenta == "143505" for l in lineas_gasto),
                        f"Esperaba 143505, obtuve cuentas: {[l.cuenta for l in lineas_gasto]}")
        # Y NO debe estar en pendientes_revision (porque la auto-detección la asentó OK)
        self.assertEqual(len(resultados[0].nits_pendientes), 0)

    def test_siigo_no_catalogado_no_va_a_143505(self):
        # SIIGO claramente NO es insumo alimenticio → va a fallback PENDIENTE
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice(
                nit_emisor="830048145",
                nombre_emisor="SIIGO S.A.S",
                items=[{"desc": "Licencia software contable mensual", "cantidad": 1, "precio": 65000, "iva_pct": 19}],
                cufe="i" * 96,
            )),
        ])
        zips = [ZipInput(nombre="z.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603", modo_filtro_fecha="ninguno")

        # SIIGO va a 519095 (PENDIENTE), no a 143505
        cuentas = [l.cuenta for l in resultados[0].lineas_plano]
        self.assertIn("519095", cuentas)
        self.assertNotIn("143505", cuentas)
        # Sí debe aparecer como pendiente
        self.assertEqual(len(resultados[0].nits_pendientes), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
