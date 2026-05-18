"""
core/procesadores/procesador_xmls_zip.py

Flujo limpio: la extensión Chrome descarga un ZIP plano con XMLs sueltos
(formato preferido). Este módulo lo procesa.

ESTRUCTURA ESPERADA DEL ZIP:
    cufe1.xml
    cufe2.xml
    cufe3.xml
    ...
    (o también soporta ZIPs anidados como fallback)

USOS:
    1. Procesar STL emitidas → plano contable detallado
    2. Procesar compras MIXTAS → plano contable detallado con IVA real
    3. Extraer datos para maestro de terceros (régimen, dirección)

EXPONE:
    iter_xmls_de_zip(zip_bytes) → iter[(nombre, xml_str)]
    parsear_factura(xml_str) → FacturaXML
    procesar_zip_stl(zip_bytes) → ResultadoSTL
    procesar_zip_compras_mixtas(zip_bytes, mapeo_historico) → ResultadoMixtas
    procesar_zip_para_maestro(zip_bytes, maestro_existente) → resumen
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterator, Optional

import pandas as pd


# ─── Namespaces UBL/DIAN ────────────────────────────────────
NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sts": "dian:gov:co:facturaelectronica:Structures-2-1",
}


# ─── Iteración de ZIPs ──────────────────────────────────────
def iter_xmls_de_zip(zip_bytes: bytes) -> Iterator[tuple[str, str]]:
    """
    Itera XMLs desde un ZIP. Soporta:
      - ZIP plano (XMLs sueltos)         ← preferido
      - ZIP anidado (ZIP de ZIPs)        ← legacy

    Yields:
        (nombre_archivo, xml_str)
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for nombre in zf.namelist():
                if nombre.lower().endswith(".xml"):
                    # XML directo en ZIP plano
                    try:
                        xml_str = zf.read(nombre).decode("utf-8", errors="ignore")
                        yield nombre, xml_str
                    except Exception:
                        continue
                elif nombre.lower().endswith(".zip"):
                    # ZIP anidado (legacy)
                    try:
                        inner_bytes = zf.read(nombre)
                        with zipfile.ZipFile(io.BytesIO(inner_bytes)) as zf_inner:
                            for inner_name in zf_inner.namelist():
                                if inner_name.lower().endswith(".xml"):
                                    xml_str = zf_inner.read(inner_name).decode(
                                        "utf-8", errors="ignore"
                                    )
                                    yield f"{nombre}/{inner_name}", xml_str
                    except Exception:
                        continue
    except zipfile.BadZipFile:
        return


# ─── Parser de factura ──────────────────────────────────────
@dataclass
class LineaXML:
    """Línea de detalle de una factura."""
    cantidad: float
    descripcion: str
    base: float
    iva: float
    inc: float
    tarifa: str  # "0%", "5%", "19%", "16%", "INC8%"
    total_linea: float


@dataclass
class FacturaXML:
    """Factura/NC/DS parseada desde XML UBL."""
    folio: str                      # "STL15808" o "FELC1234"
    prefijo: str
    numero: str
    cufe: str
    fecha: date
    tipo_documento: str             # "01" FE, "05" DS, "91" NC, "92" ND
    nit_emisor: str
    nombre_emisor: str
    nit_receptor: str
    nombre_receptor: str
    total_factura: float
    lineas: list[LineaXML] = field(default_factory=list)

    # Agregados por tarifa
    bases_por_tarifa: dict = field(default_factory=dict)
    iva_por_tarifa: dict = field(default_factory=dict)
    inc_total: float = 0
    total_iva: float = 0
    total_base: float = 0

    # Régimen del emisor (TaxLevelCode)
    tax_level_emisor: str = ""
    tax_level_principal_emisor: str = ""
    ciudad_emisor: str = ""
    direccion_emisor: str = ""


def _normalizar_nit(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\D", "", str(s).split("-")[0])


def parsear_factura(xml_str: str) -> Optional[FacturaXML]:
    """Parsea un XML UBL completo (Invoice o CreditNote)."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None

    # Folio
    folio = ""
    fid = root.find("cbc:ID", NS)
    if fid is not None and fid.text:
        folio = fid.text.strip()

    m = re.match(r"([A-Z]+)(\d+)", folio)
    prefijo = m.group(1) if m else ""
    numero = m.group(2) if m else folio

    # CUFE/UUID
    cufe = ""
    uuid_node = root.find("cbc:UUID", NS)
    if uuid_node is not None and uuid_node.text:
        cufe = uuid_node.text.strip()

    # Fecha
    fecha = None
    fdate = root.find("cbc:IssueDate", NS)
    if fdate is not None and fdate.text:
        try:
            fecha = datetime.strptime(fdate.text.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass

    # Tipo de documento
    tipo_doc = ""
    tipo_node = root.find("cbc:InvoiceTypeCode", NS)
    if tipo_node is None:
        tipo_node = root.find("cbc:CreditNoteTypeCode", NS)
    if tipo_node is not None and tipo_node.text:
        tipo_doc = tipo_node.text.strip()

    # Emisor
    nit_em = ""
    nombre_em = ""
    tax_level = ""
    ciudad_em = ""
    direccion_em = ""

    supplier = root.find("cac:AccountingSupplierParty/cac:Party", NS)
    if supplier is not None:
        tax_scheme = supplier.find("cac:PartyTaxScheme", NS)
        if tax_scheme is not None:
            cid = tax_scheme.find("cbc:CompanyID", NS)
            if cid is not None and cid.text:
                nit_em = _normalizar_nit(cid.text)
            rn = tax_scheme.find("cbc:RegistrationName", NS)
            if rn is not None and rn.text:
                nombre_em = rn.text.strip()
            tlc = tax_scheme.find("cbc:TaxLevelCode", NS)
            if tlc is not None and tlc.text:
                tax_level = tlc.text.strip()

        # Dirección
        addr = supplier.find("cac:PhysicalLocation/cac:Address", NS)
        if addr is not None:
            city = addr.find("cbc:CityName", NS)
            if city is not None and city.text:
                ciudad_em = city.text.strip()
            line = addr.find("cac:AddressLine/cbc:Line", NS)
            if line is not None and line.text:
                direccion_em = line.text.strip()

    # Cliente
    nit_cli = ""
    nombre_cli = ""
    customer = root.find("cac:AccountingCustomerParty/cac:Party", NS)
    if customer is not None:
        tax_scheme = customer.find("cac:PartyTaxScheme", NS)
        if tax_scheme is not None:
            cid = tax_scheme.find("cbc:CompanyID", NS)
            if cid is not None and cid.text:
                nit_cli = _normalizar_nit(cid.text)
            rn = tax_scheme.find("cbc:RegistrationName", NS)
            if rn is not None and rn.text:
                nombre_cli = rn.text.strip()

    # Total
    total_factura = 0
    legal_total = root.find("cac:LegalMonetaryTotal/cbc:PayableAmount", NS)
    if legal_total is not None and legal_total.text:
        try:
            total_factura = float(legal_total.text)
        except ValueError:
            pass

    factura = FacturaXML(
        folio=folio,
        prefijo=prefijo,
        numero=numero,
        cufe=cufe,
        fecha=fecha or date.today(),
        tipo_documento=tipo_doc,
        nit_emisor=nit_em,
        nombre_emisor=nombre_em,
        nit_receptor=nit_cli,
        nombre_receptor=nombre_cli,
        total_factura=total_factura,
        tax_level_emisor=tax_level,
        tax_level_principal_emisor=tax_level.split(";")[0].strip() if tax_level else "",
        ciudad_emisor=ciudad_em,
        direccion_emisor=direccion_em,
    )

    # Líneas
    for ln_tag in ("InvoiceLine", "CreditNoteLine"):
        for line in root.findall(f"cac:{ln_tag}", NS):
            linea = _parsear_linea(line)
            if linea:
                factura.lineas.append(linea)

    # Agregados
    for ln in factura.lineas:
        factura.total_base += ln.base
        factura.total_iva += ln.iva
        factura.inc_total += ln.inc
        factura.bases_por_tarifa[ln.tarifa] = factura.bases_por_tarifa.get(ln.tarifa, 0) + ln.base
        factura.iva_por_tarifa[ln.tarifa] = factura.iva_por_tarifa.get(ln.tarifa, 0) + ln.iva

    return factura


def _parsear_linea(line_node) -> Optional[LineaXML]:
    cantidad = 0
    qty = line_node.find("cbc:InvoicedQuantity", NS)
    if qty is None:
        qty = line_node.find("cbc:CreditedQuantity", NS)
    if qty is not None and qty.text:
        try:
            cantidad = float(qty.text)
        except ValueError:
            pass

    descripcion = ""
    desc = line_node.find("cac:Item/cbc:Description", NS)
    if desc is not None and desc.text:
        descripcion = desc.text.strip()

    base = 0
    base_node = line_node.find("cbc:LineExtensionAmount", NS)
    if base_node is not None and base_node.text:
        try:
            base = float(base_node.text)
        except ValueError:
            pass

    iva = 0
    inc = 0
    tarifa_iva = 0.0

    for tax_total in line_node.findall("cac:TaxTotal", NS):
        for subtax in tax_total.findall("cac:TaxSubtotal", NS):
            tax_amount = subtax.find("cbc:TaxAmount", NS)
            tcat = subtax.find("cac:TaxCategory", NS)
            if tcat is None or tax_amount is None:
                continue
            tax_id_node = tcat.find("cac:TaxScheme/cbc:ID", NS)
            tarifa_node = tcat.find("cbc:Percent", NS)
            if tax_id_node is None:
                continue
            tax_id = tax_id_node.text.strip() if tax_id_node.text else ""
            try:
                amount = float(tax_amount.text) if tax_amount.text else 0
            except ValueError:
                amount = 0
            try:
                pct = float(tarifa_node.text) if (tarifa_node is not None and tarifa_node.text) else 0
            except ValueError:
                pct = 0

            if tax_id == "01":   # IVA
                iva += amount
                tarifa_iva = pct
            elif tax_id == "04":  # INC
                inc += amount

    if iva > 0.5:
        if abs(tarifa_iva - 19) < 0.5:
            tarifa = "19%"
        elif abs(tarifa_iva - 5) < 0.5:
            tarifa = "5%"
        elif abs(tarifa_iva - 16) < 0.5:
            tarifa = "16%"
        else:
            tarifa = f"{tarifa_iva:.0f}%"
    elif inc > 0.5:
        tarifa = "INC8%"
    else:
        tarifa = "0%"

    return LineaXML(
        cantidad=cantidad,
        descripcion=descripcion,
        base=base,
        iva=iva,
        inc=inc,
        tarifa=tarifa,
        total_linea=base + iva + inc,
    )


# ─── Procesador STL → plano contable ────────────────────────
@dataclass
class ResultadoXMLs:
    facturas: list[FacturaXML] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    plano_df: Optional[pd.DataFrame] = None
    plano_lineas: int = 0

    def resumen(self) -> dict:
        return {
            "facturas_procesadas": len(self.facturas),
            "errores": len(self.errores),
            "total_base": sum(f.total_base for f in self.facturas),
            "total_iva": sum(f.total_iva for f in self.facturas),
            "total_inc": sum(f.inc_total for f in self.facturas),
            "total_facturado": sum(f.total_factura for f in self.facturas),
            "lineas_plano": self.plano_lineas,
        }


# Constantes contables (cuentas reales JIPER)
COMPROBANTE_STL = "426"
CC_INSTITUCIONAL = "001003"
CUENTA_CXC_STL = "13050505"           # CLIENTES NACIONALES (verificado en histórico)

# Ingresos por tarifa — cuentas REALES JIPER del comprobante 426
# Verificadas con histórico marzo+abril 2026
CUENTAS_INGRESOS_STL_POR_TARIFA = {
    "0%":   "41200902",   # PANADERIA CONGELADA SIN IVA (la principal, excluida)
    "5%":   "41200905",   # OTROS PANADERIA IVA 5%
    "19%":  "41200906",   # OTRAS VENTAS GVADAS AL 19%
    "16%":  "41200906",   # fallback a 19%
    "INC8%":"41401501",   # VENTAS PUNTOS CON ICO 8%
}
# Cuenta fallback si la tarifa es inesperada
CUENTA_INGRESOS_STL_FALLBACK = "41200902"

CUENTA_IVA_19_GENERADO = "24080503"   # IVA GENERADO 19%
CUENTA_IVA_5_GENERADO = "24080501"    # IVA GENERADO 5%
CUENTA_INC_GENERADO = "24800505"      # IMPUESTO AL CONSUMO 8%

TR_DEBITO = "1"
TR_CREDITO = "2"

COLUMNAS_PLANO = [
    "CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
    "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO",
]


def procesar_zip_stl(zip_bytes: bytes) -> ResultadoXMLs:
    """
    Procesa ZIP de XMLs STL emitidas → plano contable detallado.
    """
    res = ResultadoXMLs()
    for nombre, xml_str in iter_xmls_de_zip(zip_bytes):
        try:
            factura = parsear_factura(xml_str)
            if factura is None:
                res.errores.append(f"{nombre}: no se pudo parsear")
                continue
            # Solo procesar STL
            if not factura.prefijo.upper().startswith("STL"):
                continue
            # Evitar duplicados por CUFE
            if any(f.cufe == factura.cufe for f in res.facturas):
                continue
            res.facturas.append(factura)
        except Exception as e:
            res.errores.append(f"{nombre}: {e}")

    # Generar plano
    filas = []
    for fac in res.facturas:
        filas.extend(_generar_lineas_stl(fac))

    if filas:
        res.plano_df = pd.DataFrame(filas, columns=COLUMNAS_PLANO)
        res.plano_lineas = len(filas)
        # Numerar consecutivamente
        from .numerador_comprobantes import aplicar_numeracion
        res.plano_df = aplicar_numeracion(res.plano_df)
    else:
        res.plano_df = pd.DataFrame(columns=COLUMNAS_PLANO)

    return res


def _generar_lineas_stl(fac: FacturaXML) -> list[dict]:
    fecha_str = fac.fecha.strftime("%m/%d/%Y")
    detalle = f"STL {fac.nombre_receptor[:30]} ({fac.folio})"
    out = []

    # Db CxC
    out.append({
        "CUENTA": CUENTA_CXC_STL,
        "COMPROBANTE": COMPROBANTE_STL,
        "FECHA": fecha_str,
        "DOCUMENTO": fac.folio,
        "DOC REFERENCIA": "",
        "NIT": fac.nit_receptor,
        "DETALLE": detalle,
        "TR": TR_DEBITO,
        "VALOR": round(fac.total_factura, 0),
        "BASE": "",
        "CENTRO DE COSTO": CC_INSTITUCIONAL,
    })

    # Cr ingresos por tarifa (cuenta cambia según tarifa real)
    for tarifa, base in fac.bases_por_tarifa.items():
        if base <= 0.5:
            continue
        # Cuenta de ingreso según tarifa (JIPER usa cuentas distintas por % IVA)
        cuenta_ingresos = CUENTAS_INGRESOS_STL_POR_TARIFA.get(
            tarifa, CUENTA_INGRESOS_STL_FALLBACK
        )
        out.append({
            "CUENTA": cuenta_ingresos,
            "COMPROBANTE": COMPROBANTE_STL,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_receptor,
            "DETALLE": f"VENTA STL {tarifa} - {detalle}",
            "TR": TR_CREDITO,
            "VALOR": round(base, 0),
            "BASE": "",
            "CENTRO DE COSTO": CC_INSTITUCIONAL,
        })

        iva = fac.iva_por_tarifa.get(tarifa, 0)
        if iva > 0.5:
            cuenta_iva = CUENTA_IVA_19_GENERADO if tarifa == "19%" else CUENTA_IVA_5_GENERADO
            out.append({
                "CUENTA": cuenta_iva,
                "COMPROBANTE": COMPROBANTE_STL,
                "FECHA": fecha_str,
                "DOCUMENTO": fac.folio,
                "DOC REFERENCIA": "",
                "NIT": fac.nit_receptor,
                "DETALLE": f"IVA {tarifa} GEN - {detalle}",
                "TR": TR_CREDITO,
                "VALOR": round(iva, 0),
                "BASE": round(base, 0),
                "CENTRO DE COSTO": CC_INSTITUCIONAL,
            })

    if fac.inc_total > 0.5:
        out.append({
            "CUENTA": CUENTA_INC_GENERADO,
            "COMPROBANTE": COMPROBANTE_STL,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_receptor,
            "DETALLE": f"INC GEN - {detalle}",
            "TR": TR_CREDITO,
            "VALOR": round(fac.inc_total, 0),
            "BASE": "",
            "CENTRO DE COSTO": CC_INSTITUCIONAL,
        })

    return out


# ─── Procesador para extraer datos de maestro de terceros ──
def procesar_zip_para_maestro(zip_bytes: bytes, maestro: dict) -> dict:
    """
    Procesa un ZIP de XMLs y actualiza el maestro de terceros.

    Returns:
        dict con {nuevos, actualizados, errores, log}
    """
    from . import maestro_terceros as mt

    nuevos = 0
    actualizados = 0
    errores = 0
    log = []

    for nombre, xml_str in iter_xmls_de_zip(zip_bytes):
        try:
            parsed = mt.extraer_datos_tercero_de_xml(xml_str)
            if parsed:
                es_nuevo = mt.actualizar_maestro_desde_xml(maestro, parsed)
                if es_nuevo:
                    nuevos += 1
                else:
                    actualizados += 1
        except Exception as e:
            errores += 1
            log.append(f"{nombre}: {e}")

    return {
        "nuevos": nuevos,
        "actualizados": actualizados,
        "errores": errores,
        "log": log,
    }
