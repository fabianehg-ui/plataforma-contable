"""
Tests de CONCEPTOS programados y LECTOR de facturas — lógica pura.

Ejecutar: pytest tests/test_conceptos_lector.py -v
"""
import pytest

from core.contable import conceptos as cp
from core.contable import lector_factura as lf


# ============================================================
# aplicar_concepto
# ============================================================

IVA19 = {"codigo": "IVA19", "tarifa": 19, "cuenta": "240820", "tipo": "C"}
RFCOMP = {"codigo": "RFCOMP", "tarifa": 2.5, "base_calculo": "base", "cuenta": "236540"}
RETEIVA = {"codigo": "RETEIVA", "tarifa": 15, "base_calculo": "iva", "cuenta": "236701"}
IVA19V = {"codigo": "IVA19V", "tarifa": 19, "cuenta": "240810", "tipo": "V"}

CONC_COMPRA = {
    "naturaleza": "compra", "cuenta_base": "143501", "cuenta_contrapartida": "220505",
    "maneja_iva": True, "maneja_retencion": True,
}
CONC_VENTA = {
    "naturaleza": "venta", "cuenta_base": "413501", "cuenta_contrapartida": "130505",
    "maneja_iva": True, "maneja_retencion": False,
}


def _resumen(lineas):
    return cp.resumen_asiento(lineas)


class TestAplicarConceptoCompra:
    def test_compra_iva_y_retefuente_cuadra(self):
        base = 1_000_000
        lineas = cp.aplicar_concepto(CONC_COMPRA, base, tipo_iva=IVA19,
                                     retenciones=[RFCOMP], nit="800", detalle="x")
        r = _resumen(lineas)
        assert r["cuadra"] is True
        # Db: base 1.000.000 + IVA 190.000 = 1.190.000
        assert r["debitos"] == 1_190_000
        # Cr: rete 25.000 + neto 1.165.000 = 1.190.000
        assert r["creditos"] == 1_190_000

    def test_valores_por_cuenta(self):
        lineas = cp.aplicar_concepto(CONC_COMPRA, 1_000_000, tipo_iva=IVA19,
                                     retenciones=[RFCOMP])
        by = {l["cuenta"]: l for l in lineas}
        assert by["143501"]["tr"] == "1" and by["143501"]["valor"] == 1_000_000
        assert by["240820"]["tr"] == "1" and by["240820"]["valor"] == 190_000
        assert by["236540"]["tr"] == "2" and by["236540"]["valor"] == 25_000
        assert by["220505"]["tr"] == "2" and by["220505"]["valor"] == 1_165_000

    def test_reteiva_se_calcula_sobre_el_iva(self):
        # reteIVA 15% sobre IVA (190.000) = 28.500
        lineas = cp.aplicar_concepto(CONC_COMPRA, 1_000_000, tipo_iva=IVA19,
                                     retenciones=[RFCOMP, RETEIVA])
        by = {l["cuenta"]: l for l in lineas}
        assert by["236701"]["valor"] == 28_500
        assert _resumen(lineas)["cuadra"] is True

    def test_sin_iva_ni_retencion(self):
        conc = {"naturaleza": "compra", "cuenta_base": "513535",
                "cuenta_contrapartida": "111005", "maneja_iva": False,
                "maneja_retencion": False}
        lineas = cp.aplicar_concepto(conc, 200_000)
        assert len(lineas) == 2
        r = _resumen(lineas)
        assert r["debitos"] == 200_000 == r["creditos"]

    def test_override_de_cuentas(self):
        lineas = cp.aplicar_concepto(CONC_COMPRA, 100_000, tipo_iva=IVA19,
                                     retenciones=[RFCOMP],
                                     cuenta_base="519595",
                                     cuenta_contrapartida="111005")
        cuentas = {l["cuenta"] for l in lineas}
        assert "519595" in cuentas and "111005" in cuentas
        assert "143501" not in cuentas and "220505" not in cuentas


class TestAplicarConceptoVenta:
    def test_venta_gravada_cuadra_y_signos(self):
        lineas = cp.aplicar_concepto(CONC_VENTA, 1_000_000, tipo_iva=IVA19V)
        by = {l["cuenta"]: l for l in lineas}
        # ingreso al crédito, IVA generado al crédito, cliente al débito
        assert by["413501"]["tr"] == "2" and by["413501"]["valor"] == 1_000_000
        assert by["240810"]["tr"] == "2" and by["240810"]["valor"] == 190_000
        assert by["130505"]["tr"] == "1" and by["130505"]["valor"] == 1_190_000
        assert _resumen(lineas)["cuadra"] is True


class TestCalcularRetencion:
    def test_base(self):
        assert cp.calcular_retencion(1_000_000, 190_000, RFCOMP) == 25_000

    def test_iva(self):
        assert cp.calcular_retencion(1_000_000, 190_000, RETEIVA) == 28_500


# ============================================================
# Lector — parsing de números y heurística de texto
# ============================================================

class TestNumeros:
    def test_formato_colombiano_con_decimales(self):
        assert lf._a_int("1.234.567,89") == 1_234_567

    def test_formato_us(self):
        assert lf._a_int("1,234,567.00") == 1_234_567

    def test_con_signo_peso(self):
        assert lf._a_int("$ 1.190.000") == 1_190_000

    def test_vacio(self):
        assert lf._a_int("") == 0 and lf._a_int(None) == 0


class TestFechas:
    def test_iso(self):
        assert lf._norm_fecha("2026-06-15") == "2026-06-15"

    def test_dmy(self):
        assert lf._norm_fecha("15/06/2026") == "2026-06-15"

    def test_texto_largo(self):
        assert lf._norm_fecha("Bogotá, 15 de junio de 2026") == "2026-06-15"


class TestHeuristicaTexto:
    TEXTO = (
        "PAPELERIA EL LAPIZ S.A.S\n"
        "NIT: 800.197.268-4\n"
        "Factura de venta No. FE-4587\n"
        "Fecha: 30/06/2026\n"
        "Subtotal: 2.000.000\n"
        "IVA 19%: 380.000\n"
        "ReteFuente: 50.000\n"
        "Total a pagar: $ 2.330.000\n"
    )

    def test_extrae_nit(self):
        # NIT sin DV, consistente con el XML (CompanyID).
        r = lf.extraer_de_texto(self.TEXTO, "pdf")
        assert r["nit"] == "800197268"

    def test_extrae_montos(self):
        r = lf.extraer_de_texto(self.TEXTO, "pdf")
        assert r["base"] == 2_000_000
        assert r["iva"] == 380_000
        assert r["total"] == 2_330_000
        assert r["rete_fuente"] == 50_000

    def test_extrae_numero_y_nombre(self):
        r = lf.extraer_de_texto(self.TEXTO, "pdf")
        assert "4587" in r["numero"]
        assert "PAPELERIA" in r["nombre"].upper()

    def test_confianza(self):
        assert lf.extraer_de_texto(self.TEXTO, "pdf")["confianza"] == "media"
        assert lf.extraer_de_texto(self.TEXTO, "imagen")["confianza"] == "baja"


# ============================================================
# Lector — XML UBL (reusa parsear_xml_dian)
# ============================================================

XML_UBL = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>FE4587</cbc:ID>
  <cbc:UUID>abc123</cbc:UUID>
  <cbc:IssueDate>2026-06-30</cbc:IssueDate>
  <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyName><cbc:Name>PAPELERIA EL LAPIZ S.A.S</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme>
        <cbc:RegistrationName>PAPELERIA EL LAPIZ S.A.S</cbc:RegistrationName>
        <cbc:CompanyID>800197268</cbc:CompanyID>
      </cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="COP">380000.00</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="COP">2000000.00</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="COP">380000.00</cbc:TaxAmount>
      <cac:TaxCategory>
        <cbc:Percent>19.00</cbc:Percent>
        <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="COP">2000000.00</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="COP">2000000.00</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="COP">2380000.00</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="COP">2380000.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:LineExtensionAmount currencyID="COP">2000000.00</cbc:LineExtensionAmount>
    <cac:Item><cbc:Description>Resma papel</cbc:Description></cac:Item>
  </cac:InvoiceLine>
</Invoice>"""


class TestLeerXML:
    def test_lee_campos_clave(self):
        r = lf.leer_xml(XML_UBL.encode("utf-8"), "FE4587.xml")
        assert r["formato"] == "xml"
        assert r["confianza"] == "alta"
        assert r["nit"] == "800197268"
        assert "PAPELERIA" in r["nombre"].upper()
        assert r["fecha"] == "2026-06-30"
        assert r["numero"] == "FE4587"
        assert r["base"] == 2_000_000
        assert r["iva"] == 380_000
        assert r["total"] == 2_380_000

    def test_dispatcher_detecta_xml(self):
        r = lf.leer_factura("factura.xml", XML_UBL.encode("utf-8"))
        assert r["formato"] == "xml" and r["nit"] == "800197268"


class TestOCRDisponible:
    def test_no_revienta(self):
        # Solo verifica que la función corre y devuelve bool.
        assert isinstance(lf.ocr_disponible(), bool)
