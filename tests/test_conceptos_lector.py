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


# base mínima por normatividad (base_uvt × UVT)
UVT_2026 = 52_374
RFCOMP_MIN = {"codigo": "RFCOMP", "tarifa": 2.5, "base_calculo": "base",
              "cuenta": "236540", "nombre": "ReteFuente compras 2.5%", "base_uvt": 27}


class TestBaseMinimaRetencion:
    def test_no_retiene_si_base_menor_al_minimo(self):
        # base 17.435 << 27 UVT (~1.414.098) → no retiene
        assert cp.calcular_retencion(17_435, 3_313, RFCOMP_MIN, uvt=UVT_2026) == 0

    def test_retiene_si_base_supera_minimo(self):
        assert cp.calcular_retencion(2_000_000, 380_000, RFCOMP_MIN, uvt=UVT_2026) == 50_000

    def test_forzar_aplica_aunque_no_alcance(self):
        assert cp.calcular_retencion(17_435, 3_313, RFCOMP_MIN, uvt=UVT_2026, forzar=True) == 436

    def test_sin_uvt_no_valida_minimo(self):
        # compatibilidad: sin UVT se comporta como antes
        assert cp.calcular_retencion(17_435, 0, RFCOMP_MIN, uvt=0) == 436

    def test_aplicar_concepto_omite_retefuente_bajo_minimo(self):
        conc = {"naturaleza": "compra", "cuenta_base": "143501",
                "cuenta_contrapartida": "220505", "maneja_iva": True, "maneja_retencion": True}
        lineas = cp.aplicar_concepto(conc, 17_435, tipo_iva=IVA19,
                                     retenciones=[RFCOMP_MIN], uvt=UVT_2026)
        # sin línea de retención
        assert not any(l["tipo"].startswith("retencion") for l in lineas)
        assert cp.resumen_asiento(lineas)["cuadra"] is True

    def test_aplicar_concepto_con_forzar_incluye_retefuente(self):
        conc = {"naturaleza": "compra", "cuenta_base": "143501",
                "cuenta_contrapartida": "220505", "maneja_iva": True, "maneja_retencion": True}
        lineas = cp.aplicar_concepto(conc, 17_435, tipo_iva=IVA19,
                                     retenciones=[RFCOMP_MIN], uvt=UVT_2026, forzar_retencion=True)
        assert any(l["tipo"].startswith("retencion") for l in lineas)


class TestEvaluarRetenciones:
    def test_reporta_motivo_cuando_no_aplica(self):
        ev = cp.evaluar_retenciones(17_435, 3_313, [RFCOMP_MIN], uvt=UVT_2026)
        assert ev[0]["aplicada"] is False
        assert "mínimo" in ev[0]["motivo"]

    def test_aplica_cuando_supera(self):
        ev = cp.evaluar_retenciones(2_000_000, 380_000, [RFCOMP_MIN], uvt=UVT_2026)
        assert ev[0]["aplicada"] is True and ev[0]["valor"] == 50_000


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


# ============================================================
# Régimen del proveedor + sugerencia de retención
# ============================================================

XML_REG = XML_UBL.replace(
    "<cbc:RegistrationName>PAPELERIA EL LAPIZ S.A.S</cbc:RegistrationName>",
    "<cbc:RegistrationName>PAPELERIA EL LAPIZ S.A.S</cbc:RegistrationName>"
    "<cbc:TaxLevelCode listName=\"O-13;O-15;O-23\">48</cbc:TaxLevelCode>")

XML_NO_RESP = XML_UBL.replace(
    "<cbc:RegistrationName>PAPELERIA EL LAPIZ S.A.S</cbc:RegistrationName>",
    "<cbc:RegistrationName>PAPELERIA EL LAPIZ S.A.S</cbc:RegistrationName>"
    "<cbc:TaxLevelCode listName=\"R-99-PN\">49</cbc:TaxLevelCode>")


class TestRegimen:
    def test_gran_contribuyente_autorretenedor(self):
        r = lf.leer_xml(XML_REG.encode("utf-8"))
        reg = r["regimen"]
        assert reg["iva"] == "responsable"
        assert reg["gran_contribuyente"] is True
        assert reg["autorretenedor"] is True
        assert reg["agente_retencion_iva"] is True
        assert "Autorretenedor" in reg["texto"]

    def test_no_responsable(self):
        r = lf.leer_xml(XML_NO_RESP.encode("utf-8"))
        reg = r["regimen"]
        assert reg["iva"] == "no_responsable"
        assert reg["autorretenedor"] is False

    def test_sin_taxlevelcode_no_revienta(self):
        r = lf.leer_xml(XML_UBL.encode("utf-8"))
        assert r["regimen"]["iva"] in ("desconocido", "responsable", "no_responsable")


IVA19C = {"codigo": "IVA19", "tarifa": 19, "cuenta": "240820", "tipo": "C"}
RFC = {"codigo": "RFCOMP", "tarifa": 2.5, "base_calculo": "base", "cuenta": "236540", "clase": "fuente"}
RIVA = {"codigo": "RETEIVA", "tarifa": 15, "base_calculo": "iva", "cuenta": "236701", "clase": "iva"}
CONC = {"naturaleza": "compra", "cuenta_base": "143501", "cuenta_contrapartida": "220505",
        "maneja_iva": True, "maneja_retencion": True,
        "tipo_iva_codigo": "IVA19", "tipo_retencion_codigo": "RFCOMP"}


class TestAjustarPorRegimen:
    def test_autorretenedor_quita_retefuente(self):
        reg = {"iva": "responsable", "autorretenedor": True, "regimen_simple": False}
        iva, rets, notas = cp.ajustar_por_regimen(CONC, [RFC, RIVA], [IVA19C], reg)
        assert iva == "IVA19"           # IVA sí (es responsable)
        assert "RFCOMP" not in rets     # no retefuente (autorretenedor)
        assert any("autorretenedor" in n.lower() for n in notas)

    def test_no_responsable_quita_iva_y_reteiva(self):
        conc = dict(CONC, tipo_retencion_codigo="RETEIVA")
        reg = {"iva": "no_responsable", "autorretenedor": False, "regimen_simple": False}
        iva, rets, notas = cp.ajustar_por_regimen(conc, [RFC, RIVA], [IVA19C], reg)
        assert iva is None
        assert "RETEIVA" not in rets

    def test_sin_regimen_usa_defaults_del_concepto(self):
        iva, rets, notas = cp.ajustar_por_regimen(CONC, [RFC, RIVA], [IVA19C], None)
        assert iva == "IVA19" and rets == ["RFCOMP"] and notas == []


# ============================================================
# Lectura de ZIP
# ============================================================

class TestLeerZip:
    def _zip_con(self, archivos):
        import io as _io, zipfile
        buf = _io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for nombre, contenido in archivos.items():
                z.writestr(nombre, contenido)
        return buf.getvalue()

    def test_zip_con_un_xml(self):
        zb = self._zip_con({"FE4587.xml": XML_UBL})
        facs = lf.leer_zip(zb)
        assert len(facs) == 1
        assert facs[0]["nit"] == "800197268"

    def test_zip_con_dos_xml(self):
        zb = self._zip_con({"a.xml": XML_UBL, "b.xml": XML_REG})
        facs = lf.leer_zip(zb)
        assert len(facs) == 2

    def test_dispatcher_facturas_zip(self):
        zb = self._zip_con({"a.xml": XML_UBL, "b.xml": XML_REG})
        facs = lf.leer_facturas("paquete.zip", zb)
        assert len(facs) == 2

    def test_dispatcher_facturas_unico(self):
        facs = lf.leer_facturas("f.xml", XML_UBL.encode("utf-8"))
        assert len(facs) == 1


# ============================================================
# Bases por tarifa (IVA diferencial)
# ============================================================

# XML con dos líneas: una al 19% y otra al 5%
XML_MULTI = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>FE99</cbc:ID><cbc:IssueDate>2026-06-30</cbc:IssueDate>
  <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
  <cac:AccountingSupplierParty><cac:Party><cac:PartyTaxScheme>
    <cbc:RegistrationName>MIXTA SAS</cbc:RegistrationName>
    <cbc:CompanyID>900900</cbc:CompanyID></cac:PartyTaxScheme></cac:Party>
  </cac:AccountingSupplierParty>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount>3000000.00</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount>3000000.00</cbc:TaxExclusiveAmount>
    <cbc:PayableAmount>3290000.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine><cbc:ID>1</cbc:ID>
    <cbc:LineExtensionAmount>2000000.00</cbc:LineExtensionAmount>
    <cac:TaxTotal><cbc:TaxAmount>380000.00</cbc:TaxAmount><cac:TaxSubtotal>
      <cbc:TaxableAmount>2000000.00</cbc:TaxableAmount><cbc:TaxAmount>380000.00</cbc:TaxAmount>
      <cac:TaxCategory><cbc:Percent>19.00</cbc:Percent>
      <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme></cac:TaxCategory>
    </cac:TaxSubtotal></cac:TaxTotal>
    <cac:Item><cbc:Description>Bien gravado 19</cbc:Description></cac:Item></cac:InvoiceLine>
  <cac:InvoiceLine><cbc:ID>2</cbc:ID>
    <cbc:LineExtensionAmount>1000000.00</cbc:LineExtensionAmount>
    <cac:TaxTotal><cbc:TaxAmount>50000.00</cbc:TaxAmount><cac:TaxSubtotal>
      <cbc:TaxableAmount>1000000.00</cbc:TaxableAmount><cbc:TaxAmount>50000.00</cbc:TaxAmount>
      <cac:TaxCategory><cbc:Percent>5.00</cbc:Percent>
      <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme></cac:TaxCategory>
    </cac:TaxSubtotal></cac:TaxTotal>
    <cac:Item><cbc:Description>Bien gravado 5</cbc:Description></cac:Item></cac:InvoiceLine>
</Invoice>"""


class TestBasesPorTarifa:
    def test_dos_tarifas(self):
        r = lf.leer_xml(XML_MULTI.encode("utf-8"))
        bt = {b["tarifa"]: b for b in r["bases_por_tarifa"]}
        assert set(bt) == {19.0, 5.0}
        assert bt[19.0]["base"] == 2_000_000 and bt[19.0]["iva"] == 380_000
        assert bt[5.0]["base"] == 1_000_000 and bt[5.0]["iva"] == 50_000

    def test_orden_descendente(self):
        r = lf.leer_xml(XML_MULTI.encode("utf-8"))
        tarifas = [b["tarifa"] for b in r["bases_por_tarifa"]]
        assert tarifas == sorted(tarifas, reverse=True)


class TestDesgloseIVA:
    def test_asiento_con_bases_separadas_cuadra(self):
        conc = {"naturaleza": "compra", "cuenta_base": "143501",
                "cuenta_contrapartida": "220505", "maneja_iva": True,
                "maneja_retencion": True}
        desg = [
            {"tarifa": 19, "base": 2_000_000, "iva": 380_000, "cuenta": "240820"},
            {"tarifa": 5, "base": 1_000_000, "iva": 50_000, "cuenta": "240820"},
        ]
        rfc = {"codigo": "RFCOMP", "tarifa": 2.5, "base_calculo": "base", "cuenta": "236540"}
        lineas = cp.aplicar_concepto(conc, 0, retenciones=[rfc], desglose_iva=desg)
        r = cp.resumen_asiento(lineas)
        assert r["cuadra"] is True
        # dos líneas de base (una por tarifa) al débito
        bases = [l for l in lineas if l["tipo"] == "base"]
        assert len(bases) == 2
        assert {l["valor"] for l in bases} == {2_000_000, 1_000_000}
        # dos líneas de IVA (380.000 y 50.000)
        ivas = [l for l in lineas if l["tipo"] == "iva"]
        assert {l["valor"] for l in ivas} == {380_000, 50_000}
        # retención sobre base total (3.000.000 * 2.5% = 75.000)
        ret = [l for l in lineas if l["tipo"].startswith("retencion")][0]
        assert ret["valor"] == 75_000


# ============================================================
# Sugerencia automática de concepto
# ============================================================

CONCEPTOS_SEED = [
    {"codigo": "COMPRA_BIEN_19", "nombre": "Compra de bienes 19%", "naturaleza": "compra"},
    {"codigo": "COMPRA_SERV_19", "nombre": "Servicios 19%", "naturaleza": "compra"},
    {"codigo": "HONORARIOS", "nombre": "Honorarios 19%", "naturaleza": "compra"},
    {"codigo": "ARRENDAMIENTO", "nombre": "Arrendamiento", "naturaleza": "compra"},
]


class TestSugerirConcepto:
    def test_honorarios(self):
        fac = {"nombre": "ASESORES XYZ", "items": [{"descripcion": "Honorarios asesoría contable"}]}
        assert cp.clasificar_factura(fac) == "honorarios"
        assert cp.sugerir_concepto(fac, CONCEPTOS_SEED) == "HONORARIOS"

    def test_arrendamiento(self):
        fac = {"nombre": "INMOBILIARIA", "items": [{"descripcion": "Canon de arrendamiento local"}]}
        assert cp.sugerir_concepto(fac, CONCEPTOS_SEED) == "ARRENDAMIENTO"

    def test_servicios(self):
        fac = {"nombre": "ASEO TOTAL", "items": [{"descripcion": "Servicio de aseo mensual"}]}
        assert cp.sugerir_concepto(fac, CONCEPTOS_SEED) == "COMPRA_SERV_19"

    def test_compra_por_defecto(self):
        fac = {"nombre": "FERRETERIA", "items": [{"descripcion": "Tornillos y tuercas"}]}
        assert cp.clasificar_factura(fac) == "compra"
        assert cp.sugerir_concepto(fac, CONCEPTOS_SEED) == "COMPRA_BIEN_19"


# ============================================================
# Productos agrícolas (base 92 UVT, tarifa 1.5%)
# ============================================================

RFAGRO = {"codigo": "RFAGRO", "nombre": "ReteFuente compras agrícolas/pecuarios 1.5%",
          "tarifa": 1.5, "base_calculo": "base", "cuenta": "236540", "base_uvt": 92}

CONCEPTOS_AGRO = CONCEPTOS_SEED + [
    {"codigo": "COMPRA_AGRICOLA", "nombre": "Compra productos agrícolas/pecuarios",
     "naturaleza": "compra"}]


class TestAgricola:
    def test_clasifica_agricola(self):
        fac = {"nombre": "AGROPECUARIA EL CAMPO", "items": [{"descripcion": "Café pergamino y plátano"}]}
        assert cp.clasificar_factura(fac) == "agricola"

    def test_sugiere_concepto_agricola(self):
        fac = {"nombre": "AGROPECUARIA EL CAMPO", "items": [{"descripcion": "Ganado en pie"}]}
        assert cp.sugerir_concepto(fac, CONCEPTOS_AGRO) == "COMPRA_AGRICOLA"

    def test_base_minima_92_uvt(self):
        # 92 UVT ≈ 4.818.408. Base 3.000.000 → no retiene
        assert cp.calcular_retencion(3_000_000, 0, RFAGRO, uvt=UVT_2026) == 0
        # Base 5.000.000 → retiene 1.5% = 75.000
        assert cp.calcular_retencion(5_000_000, 0, RFAGRO, uvt=UVT_2026) == 75_000

    def test_semillas_en_catalogo_estandar(self):
        cods_ret = {t[0] for t in cp.SEED_TIPOS_RETENCION}
        cods_con = {c[0] for c in cp.SEED_CONCEPTOS}
        assert "RFAGRO" in cods_ret
        assert "COMPRA_AGRICOLA" in cods_con
