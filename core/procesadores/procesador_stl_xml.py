"""
core/procesadores/procesador_stl_xml.py

Procesa los XMLs de las STL emitidas (descargados con la extensión Chrome) para
generar el plano contable con IVA discriminado real por línea.

REEMPLAZA el procesamiento de STL desde el Excel del Token, que no tiene el
detalle de IVA por producto.

ENTRADA:
    - ZIP de la extensión Chrome (contiene ZIPs anidados con XMLs de las STL)
    - El XML es de tipo Factura Electrónica de Venta (Invoice)

SALIDA:
    - DataFrame con plano contable (asientos):
        Db CC INSTITUCIONAL              total facturado
        Cr Ingresos por tarifa           base
        Cr IVA por tarifa                iva
        Cr INC                           inc (si aplica)

CONVENCIÓN JIPER:
    - Todas las STL se asientan a CC 001003 INSTITUCIONAL
    - Comprobante 426 (ventas STL)
    - Cuenta de ingresos base: 41401501 (varía por tarifa)
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd


# ─── Namespaces UBL/DIAN ────────────────────────────────────
NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sts": "dian:gov:co:facturaelectronica:Structures-2-1",
}


# ─── Constantes contables ───────────────────────────────────
COMPROBANTE_STL = "426"
CC_INSTITUCIONAL = "001003"

# Cuenta CxC (cliente STL — la STL es a crédito, se cobra después)
CUENTA_CXC_STL = "13050501"

# Ingresos por tarifa (cuenta cabeza 41401501 — el subdetalle depende de JIPER)
CUENTAS_INGRESOS_TARIFA = {
    "0%":   "41401501",
    "5%":   "41401501",
    "19%":  "41401501",
    "INC8%":"41401501",
}

# IVA generado (cuenta pasiva)
CUENTAS_IVA_GENERADO = {
    "0%":   None,
    "5%":   "24080510",
    "19%":  "24080501",
    "INC8%":None,
}

# INC generado
CUENTA_INC_GENERADO = "24080515"

TR_DEBITO = "1"
TR_CREDITO = "2"

COLUMNAS_PLANO = [
    "CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
    "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO",
]


# ─── Estructura de datos ────────────────────────────────────
@dataclass
class LineaSTL:
    """Una línea de detalle dentro de la STL."""
    cantidad: float
    descripcion: str
    base: float
    iva: float
    inc: float
    tarifa: str  # "0%", "5%", "19%", "INC8%"
    total_linea: float


@dataclass
class FacturaSTL:
    """Factura STL completa parseada desde XML."""
    folio: str          # ej "STL15808"
    prefijo: str        # "STL"
    numero: str         # "15808"
    cufe: str
    fecha: date
    nit_cliente: str
    nombre_cliente: str
    total_factura: float
    lineas: list[LineaSTL] = field(default_factory=list)

    # Totales agregados por tarifa
    bases_por_tarifa: dict = field(default_factory=dict)  # "19%" -> $X
    iva_por_tarifa: dict = field(default_factory=dict)
    inc_total: float = 0
    total_iva: float = 0
    total_base: float = 0


@dataclass
class ResultadoSTL:
    """Resultado del procesamiento de STL."""
    facturas: list[FacturaSTL] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    plano_df: Optional[pd.DataFrame] = None
    plano_lineas: int = 0

    def resumen(self) -> dict:
        total_base = sum(f.total_base for f in self.facturas)
        total_iva = sum(f.total_iva for f in self.facturas)
        total_inc = sum(f.inc_total for f in self.facturas)
        return {
            "facturas_procesadas": len(self.facturas),
            "errores": len(self.errores),
            "total_base": total_base,
            "total_iva": total_iva,
            "total_inc": total_inc,
            "total_facturado": total_base + total_iva + total_inc,
            "lineas_plano": self.plano_lineas,
        }


# ─── Parsing del XML ────────────────────────────────────────
def _normalizar_nit(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"\D", "", str(s).split("-")[0])


def parsear_xml_stl(xml_str: str) -> Optional[FacturaSTL]:
    """
    Parsea un XML de FE (Invoice) STL y devuelve una FacturaSTL con sus líneas.

    Returns:
        FacturaSTL o None si no se puede parsear.
    """
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None

    # Datos básicos
    folio_completo = ""
    fid = root.find("cbc:ID", NS)
    if fid is not None and fid.text:
        folio_completo = fid.text.strip()

    # Separar prefijo y número
    m = re.match(r"([A-Z]+)(\d+)", folio_completo)
    prefijo = m.group(1) if m else ""
    numero = m.group(2) if m else folio_completo

    # CUFE
    cufe = ""
    uuid_node = root.find("cbc:UUID", NS)
    if uuid_node is not None and uuid_node.text:
        cufe = uuid_node.text.strip()

    # Fecha de emisión
    fecha = None
    fdate = root.find("cbc:IssueDate", NS)
    if fdate is not None and fdate.text:
        try:
            fecha = datetime.strptime(fdate.text.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass

    # Cliente (adquiriente)
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

    # Totales
    total_factura = 0
    legal_total = root.find("cac:LegalMonetaryTotal/cbc:PayableAmount", NS)
    if legal_total is not None and legal_total.text:
        try:
            total_factura = float(legal_total.text)
        except ValueError:
            pass

    factura = FacturaSTL(
        folio=folio_completo,
        prefijo=prefijo,
        numero=numero,
        cufe=cufe,
        fecha=fecha or date.today(),
        nit_cliente=nit_cli,
        nombre_cliente=nombre_cli,
        total_factura=total_factura,
    )

    # Procesar cada InvoiceLine
    for line in root.findall("cac:InvoiceLine", NS):
        linea = _parsear_linea_xml(line)
        if linea:
            factura.lineas.append(linea)

    # Agregados por tarifa
    for ln in factura.lineas:
        factura.total_base += ln.base
        factura.total_iva += ln.iva
        factura.inc_total += ln.inc

        if ln.tarifa not in factura.bases_por_tarifa:
            factura.bases_por_tarifa[ln.tarifa] = 0
            factura.iva_por_tarifa[ln.tarifa] = 0
        factura.bases_por_tarifa[ln.tarifa] += ln.base
        factura.iva_por_tarifa[ln.tarifa] += ln.iva

    return factura


def _parsear_linea_xml(line_node) -> Optional[LineaSTL]:
    """Parsea un cac:InvoiceLine."""
    # Cantidad
    cantidad = 0
    qty = line_node.find("cbc:InvoicedQuantity", NS)
    if qty is not None and qty.text:
        try:
            cantidad = float(qty.text)
        except ValueError:
            pass

    # Descripción
    descripcion = ""
    desc_node = line_node.find("cac:Item/cbc:Description", NS)
    if desc_node is not None and desc_node.text:
        descripcion = desc_node.text.strip()

    # Base (LineExtensionAmount = valor de la línea SIN IVA)
    base = 0
    base_node = line_node.find("cbc:LineExtensionAmount", NS)
    if base_node is not None and base_node.text:
        try:
            base = float(base_node.text)
        except ValueError:
            pass

    # IVA / INC dentro de TaxTotal
    iva = 0
    inc = 0
    tarifa_iva = 0.0
    tarifa_inc = 0.0

    for tax_total in line_node.findall("cac:TaxTotal", NS):
        for subtax in tax_total.findall("cac:TaxSubtotal", NS):
            tax_amount = subtax.find("cbc:TaxAmount", NS)
            tcat = subtax.find("cac:TaxCategory", NS)
            if tcat is None:
                continue
            tax_id_node = tcat.find("cac:TaxScheme/cbc:ID", NS)
            tarifa_node = tcat.find("cbc:Percent", NS)
            if tax_id_node is None or tax_amount is None:
                continue

            tax_id = tax_id_node.text.strip() if tax_id_node.text else ""
            try:
                amount = float(tax_amount.text) if tax_amount.text else 0
            except ValueError:
                amount = 0
            try:
                tarifa_pct = float(tarifa_node.text) if (tarifa_node is not None and tarifa_node.text) else 0
            except ValueError:
                tarifa_pct = 0

            if tax_id == "01":  # IVA
                iva += amount
                tarifa_iva = tarifa_pct
            elif tax_id == "04":  # INC
                inc += amount
                tarifa_inc = tarifa_pct

    # Clasificar tarifa
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

    total_linea = base + iva + inc

    return LineaSTL(
        cantidad=cantidad,
        descripcion=descripcion,
        base=base,
        iva=iva,
        inc=inc,
        tarifa=tarifa,
        total_linea=total_linea,
    )


# ─── Procesamiento del ZIP ──────────────────────────────────
def procesar_zip_xmls_stl(zip_bytes: bytes) -> ResultadoSTL:
    """
    Procesa un ZIP de XMLs descargados por la extensión Chrome.

    El ZIP de la extensión es: ZIP exterior → contiene ZIPs por documento → cada
    ZIP interno tiene el .xml + .pdf de esa STL.

    Args:
        zip_bytes: bytes del ZIP descargado.

    Returns:
        ResultadoSTL con todas las facturas parseadas + plano contable.
    """
    resultado = ResultadoSTL()

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf_outer:
            for nombre_outer in zf_outer.namelist():
                if not nombre_outer.lower().endswith(".zip"):
                    continue

                try:
                    inner_bytes = zf_outer.read(nombre_outer)
                    with zipfile.ZipFile(io.BytesIO(inner_bytes)) as zf_inner:
                        for nombre_inner in zf_inner.namelist():
                            if not nombre_inner.lower().endswith(".xml"):
                                continue
                            xml_bytes = zf_inner.read(nombre_inner)
                            xml_str = xml_bytes.decode("utf-8", errors="ignore")
                            factura = parsear_xml_stl(xml_str)
                            if factura is None:
                                resultado.errores.append(
                                    f"No se pudo parsear: {nombre_outer}/{nombre_inner}"
                                )
                                continue
                            resultado.facturas.append(factura)
                            break  # 1 XML por ZIP interno
                except Exception as e:
                    resultado.errores.append(f"{nombre_outer}: {e}")

    except zipfile.BadZipFile:
        resultado.errores.append("El archivo no es un ZIP válido")
        return resultado

    # Generar plano contable
    filas = []
    for fac in resultado.facturas:
        filas.extend(_generar_lineas_factura(fac))

    if filas:
        resultado.plano_df = pd.DataFrame(filas, columns=COLUMNAS_PLANO)
        resultado.plano_lineas = len(filas)

        # Aplicar numeración consecutiva
        from .numerador_comprobantes import aplicar_numeracion
        resultado.plano_df = aplicar_numeracion(resultado.plano_df)
    else:
        resultado.plano_df = pd.DataFrame(columns=COLUMNAS_PLANO)

    return resultado


def _generar_lineas_factura(fac: FacturaSTL) -> list[dict]:
    """
    Genera el asiento contable de una FacturaSTL.

    Modelo:
        Db CxC (13050501) Cliente              total_factura
        Cr Ingresos (41401501) por tarifa     base × tarifa
        Cr IVA por tarifa                     iva
        Cr INC                                inc (si aplica)
    """
    out = []
    fecha_str = fac.fecha.strftime("%m/%d/%Y")
    detalle_base = f"STL {fac.nombre_cliente[:30]} ({fac.folio})"

    # Db CxC al cliente
    out.append({
        "CUENTA": CUENTA_CXC_STL,
        "COMPROBANTE": COMPROBANTE_STL,
        "FECHA": fecha_str,
        "DOCUMENTO": fac.folio,
        "DOC REFERENCIA": "",
        "NIT": fac.nit_cliente,
        "DETALLE": detalle_base,
        "TR": TR_DEBITO,
        "VALOR": round(fac.total_factura, 0),
        "BASE": "",
        "CENTRO DE COSTO": CC_INSTITUCIONAL,
    })

    # Cr Ingresos por cada tarifa
    for tarifa, base in fac.bases_por_tarifa.items():
        if base <= 0.5:
            continue
        cuenta_ing = CUENTAS_INGRESOS_TARIFA.get(tarifa, "41401501")
        out.append({
            "CUENTA": cuenta_ing,
            "COMPROBANTE": COMPROBANTE_STL,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_cliente,
            "DETALLE": f"VENTA STL {tarifa} - {detalle_base}",
            "TR": TR_CREDITO,
            "VALOR": round(base, 0),
            "BASE": "",
            "CENTRO DE COSTO": CC_INSTITUCIONAL,
        })

        # Cr IVA por tarifa
        iva = fac.iva_por_tarifa.get(tarifa, 0)
        cuenta_iva = CUENTAS_IVA_GENERADO.get(tarifa)
        if iva > 0.5 and cuenta_iva:
            out.append({
                "CUENTA": cuenta_iva,
                "COMPROBANTE": COMPROBANTE_STL,
                "FECHA": fecha_str,
                "DOCUMENTO": fac.folio,
                "DOC REFERENCIA": "",
                "NIT": fac.nit_cliente,
                "DETALLE": f"IVA {tarifa} GEN - {detalle_base}",
                "TR": TR_CREDITO,
                "VALOR": round(iva, 0),
                "BASE": round(base, 0),
                "CENTRO DE COSTO": CC_INSTITUCIONAL,
            })

    # Cr INC (si aplica)
    if fac.inc_total > 0.5:
        out.append({
            "CUENTA": CUENTA_INC_GENERADO,
            "COMPROBANTE": COMPROBANTE_STL,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_cliente,
            "DETALLE": f"INC GEN - {detalle_base}",
            "TR": TR_CREDITO,
            "VALOR": round(fac.inc_total, 0),
            "BASE": "",
            "CENTRO DE COSTO": CC_INSTITUCIONAL,
        })

    return out


def generar_lista_cufes_stl(df_token, fecha_desde=None, fecha_hasta=None) -> list[str]:
    """
    Genera la lista de CUFEs de todas las STL emitidas en el rango para que la
    extensión Chrome los descargue.

    Args:
        df_token: DataFrame del lector_excel_token.
        fecha_desde, fecha_hasta: rango opcional.

    Returns:
        Lista de CUFEs (strings).
    """
    df = df_token[df_token["grupo"].str.lower() == "emitido"].copy()
    df = df[df["prefijo"].astype(str).str.upper().str.startswith("STL")]

    if fecha_desde is not None:
        df = df[df["fecha_emision"].dt.date >= fecha_desde]
    if fecha_hasta is not None:
        df = df[df["fecha_emision"].dt.date <= fecha_hasta]

    return df["cufe"].dropna().astype(str).tolist()
