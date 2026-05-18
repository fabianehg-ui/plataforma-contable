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
import json
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

    # Régimen del RECEPTOR (cliente) — para STL detectar si es Régimen Simple
    tax_level_receptor: str = ""
    tax_level_principal_receptor: str = ""


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
    tax_level_cli = ""
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
            tlc = tax_scheme.find("cbc:TaxLevelCode", NS)
            if tlc is not None and tlc.text:
                tax_level_cli = tlc.text.strip()

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
        tax_level_receptor=tax_level_cli,
        tax_level_principal_receptor=tax_level_cli.split(";")[0].strip() if tax_level_cli else "",
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

    # ── Si el CLIENTE STL es agente retenedor, nos retiene a nosotros ──
    # Cuando JIPER vende a un Gran Contribuyente (O-13) o Agente de Retención
    # IVA (O-23), el CLIENTE practica retenciones que JIPER debe registrar
    # como anticipos por cobrar (no como egreso).
    #
    # Reglas:
    #   O-13 Gran Contribuyente → cliente nos retiene retef Y reteIVA
    #   O-23 Agente Ret IVA     → cliente nos retiene reteIVA solamente
    #   O-15 Autorretenedor     → NO nos retiene
    #   O-47 RST                → NO nos retiene
    #   R-99-PN                 → NO nos retiene
    #
    # Asiento:
    #   Db CxC (al cliente) = total - retef_anticipo - reteiva_anticipo
    #   Db 135515 ANTICIPO RETEFUENTE   = retef que el cliente nos descontó
    #   Db 135517 ANTICIPO RETEIVA      = reteIVA que el cliente nos descontó
    #   (los Cr ingresos+IVA+INC no cambian)
    regimen_receptor = (fac.tax_level_receptor or "").upper()
    codigos_receptor = [c.strip() for c in regimen_receptor.replace(",", ";").split(";") if c.strip()]
    cliente_es_gc = "O-13" in codigos_receptor
    cliente_es_arIVA = "O-23" in codigos_receptor

    base_total = sum(fac.bases_por_tarifa.values())

    if (cliente_es_gc or cliente_es_arIVA) and base_total > 0:
        # Tarifa retefuente típica para venta de productos: 2.5%
        # (compras puro = 2.5%, servicios = 4%, en STL casi siempre es producto)
        retef_anticipo = round(base_total * 0.025, 0) if cliente_es_gc else 0
        # ReteIVA del 15% sobre IVA generado (aplica a O-13 y O-23)
        reteiva_anticipo = round(fac.total_iva * 0.15, 0) if (cliente_es_gc or cliente_es_arIVA) and fac.total_iva > 0 else 0

        total_anticipos = retef_anticipo + reteiva_anticipo

        if total_anticipos > 0:
            # Db 135515 ANTICIPO RETEFUENTE
            if retef_anticipo > 0:
                out.append({
                    "CUENTA": "135515",
                    "COMPROBANTE": COMPROBANTE_STL,
                    "FECHA": fecha_str,
                    "DOCUMENTO": fac.folio,
                    "DOC REFERENCIA": "",
                    "NIT": fac.nit_receptor,
                    "DETALLE": f"ANT RETEF 2.5% (cliente GC retiene) - {detalle}",
                    "TR": TR_DEBITO,
                    "VALOR": retef_anticipo,
                    "BASE": round(base_total, 0),
                    "CENTRO DE COSTO": CC_INSTITUCIONAL,
                })
            # Db 135517 ANTICIPO RETEIVA
            if reteiva_anticipo > 0:
                tipo_cliente = "GC" if cliente_es_gc else "AR IVA"
                out.append({
                    "CUENTA": "135517",
                    "COMPROBANTE": COMPROBANTE_STL,
                    "FECHA": fecha_str,
                    "DOCUMENTO": fac.folio,
                    "DOC REFERENCIA": "",
                    "NIT": fac.nit_receptor,
                    "DETALLE": f"ANT RETEIVA 15% (cliente {tipo_cliente} retiene) - {detalle}",
                    "TR": TR_DEBITO,
                    "VALOR": reteiva_anticipo,
                    "BASE": round(fac.total_iva, 0),
                    "CENTRO DE COSTO": CC_INSTITUCIONAL,
                })
            # Ajustar el Db CxC original (primer item): el cliente paga MENOS
            if out and out[0]["CUENTA"] == CUENTA_CXC_STL:
                out[0]["VALOR"] = round(out[0]["VALOR"] - total_anticipos, 0)

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


# ─── Procesador de COMPRAS MIXTAS → plano contable detallado ────
# Comprobantes contables JIPER (verificado contra histórico marzo+abril 2026):
#   3   = CXP COMPRAS (causación facturas recibidas)        ✅
#   5   = NC VENTAS no-POS (notas crédito ventas externas)  ✅
#   6   = NC COMPRAS / Arrendamientos                       ✅
#   8   = DOCUMENTOS SOPORTE (DSE compras no electrónicas)  ✅
#   20  = NO EXISTE — antes lo usaba mal
COMPROBANTE_COMPRAS = "3"          # CXP compras (era "20", corregido v22)
COMPROBANTE_NC_COMPRAS = "6"       # NC compras
COMPROBANTE_NC_VENTAS = "5"        # NC ventas (no POS)
COMPROBANTE_DOC_SOPORTE = "8"      # Documentos Soporte
CC_COMPRAS = "001001"
CUENTA_PROVEEDORES_COM = "22050505"
CUENTAS_IVA_DESCONTABLE_COM = {
    "19%":  "24081003",
    "5%":   "24081003",
    "16%":  "24081003",
}
CUENTA_INC_COMPRAS_PAGADO = "71050205"
CUENTA_GASTO_FALLBACK_COM = "73959501"


def procesar_zip_compras_mixtas(
    zip_bytes: bytes,
    ruta_mapeo_historico: str,
    ruta_tabla_retenciones: str,
    ruta_mapeo_concepto: str,
    ruta_maestro_terceros: Optional[str] = None,
) -> ResultadoXMLs:
    """
    Procesa ZIP de XMLs de compras MIXTAS y genera plano contable detallado
    con IVA discriminado real por línea, aplicando retenciones según régimen.

    Args:
        zip_bytes: bytes del ZIP plano con XMLs
        ruta_mapeo_historico: ruta a mapeo_compras_historico.json (NIT→cuenta)
        ruta_tabla_retenciones: ruta a tabla_retenciones.json
        ruta_mapeo_concepto: ruta a mapeo_cuenta_a_concepto_retencion.json
        ruta_maestro_terceros: ruta opcional a maestro_terceros.json (para régimen)

    Returns:
        ResultadoXMLs con plano contable
    """
    from . import maestro_terceros as mt
    from .motor_retenciones import MotorRetenciones

    res = ResultadoXMLs()

    # Cargar configuración
    with open(ruta_mapeo_historico, encoding="utf-8") as f:
        mapeo_hist_raw = json.load(f)
    # Convertir mapeo_compras_historico a dict NIT→{cuenta_gasto, cuenta_nombre}
    mapeo_nit_cuenta = {}
    for entry in mapeo_hist_raw.get("mapeo", []):
        nit = entry.get("nit", "").strip()
        if nit:
            mapeo_nit_cuenta[nit] = {
                "cuenta_gasto": entry.get("cuenta_gasto"),
                "cuenta_nombre": entry.get("cuenta_nombre"),
            }

    motor = MotorRetenciones(ruta_tabla_retenciones, ruta_mapeo_concepto)
    maestro = mt.cargar_maestro_terceros(ruta_maestro_terceros) if ruta_maestro_terceros else {"terceros": {}}

    # Parsear todos los XMLs y filtrar solo COMPRAS (recibidas)
    NIT_JIPER = "901038325"
    for nombre, xml_str in iter_xmls_de_zip(zip_bytes):
        try:
            factura = parsear_factura(xml_str)
            if factura is None:
                res.errores.append(f"{nombre}: no se pudo parsear")
                continue
            # Solo recibidas (JIPER es el receptor, no el emisor)
            if factura.nit_receptor != NIT_JIPER:
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
        filas.extend(_generar_lineas_compra_mixta(
            fac, mapeo_nit_cuenta, motor, maestro
        ))

    if filas:
        res.plano_df = pd.DataFrame(filas, columns=COLUMNAS_PLANO)
        res.plano_lineas = len(filas)
        from .numerador_comprobantes import aplicar_numeracion
        res.plano_df = aplicar_numeracion(res.plano_df)
    else:
        res.plano_df = pd.DataFrame(columns=COLUMNAS_PLANO)

    return res


def _generar_lineas_compra_mixta(fac, mapeo_nit_cuenta, motor, maestro):
    """Genera líneas contables para una compra MIXTA desde XML."""
    from . import maestro_terceros as mt

    out = []
    fecha_str = fac.fecha.strftime("%m/%d/%Y")

    # Decidir comprobante según tipo de documento (verificado contra histórico
    # JIPER marzo+abril 2026, confirmado en sesión 2026-05-18):
    #   "01" Factura Electrónica recibida → CXP comprobante 3
    #   "05" Documento Soporte (DSE recibido, ej. servicios públicos EPM/Comfama
    #        y otros emitidos por persona natural) → comprobante 3
    #        Nota: DSE *emitidos* por JIPER irían al comp 8, pero este procesador
    #        solo trabaja recibidos (filtra por nit_receptor == NIT_JIPER).
    #   "91" Nota Crédito recibida        → NC compras comprobante 6 (reversa TR)
    #   "92" Nota Débito recibida         → comprobante 6, MISMO sentido que FE
    #        (la ND aumenta la deuda con el proveedor, no la reversa).
    tipo = (fac.tipo_documento or "01").strip()
    if tipo == "91":
        comprobante = COMPROBANTE_NC_COMPRAS
        prefijo_det = "NC COMPRA"
    elif tipo == "92":
        comprobante = COMPROBANTE_NC_COMPRAS   # mismo comp que NC
        prefijo_det = "ND COMPRA"
    elif tipo == "05":
        comprobante = COMPROBANTE_COMPRAS      # DSE recibido va al 3 (no al 8)
        prefijo_det = "DS"
    else:
        comprobante = COMPROBANTE_COMPRAS
        prefijo_det = "COMPRA"

    detalle = f"{prefijo_det} {fac.nombre_emisor[:30]} ({fac.folio})"

    # Buscar cuenta gasto del proveedor
    info_map = mapeo_nit_cuenta.get(fac.nit_emisor, {})
    cuenta_gasto = info_map.get("cuenta_gasto") or CUENTA_GASTO_FALLBACK_COM

    # Base sin IVA
    base_total = sum(fac.bases_por_tarifa.values())

    # Calcular retenciones según régimen
    regimen = mt.regimen_proveedor(maestro, fac.nit_emisor, default="R-99-PN")
    res_ret = motor.calcular(
        fecha_factura=fac.fecha,
        base_gravable=base_total,
        iva=fac.total_iva,
        cuenta_gasto=cuenta_gasto,
        regimen_proveedor=regimen,
        declarante=True,
    )

    # Si es NC compras (tipo 91), invertir los TR (Db ↔ Cr) porque la NC
    # reversa la causación original: el proveedor nos devuelve, así que:
    #   Db proveedor (reverso de la causación)
    #   Cr cuenta gasto + Cr IVA descontable (reverso)
    # La ND (tipo 92) NO se reversa: aumenta la deuda, va en mismo sentido que FE.
    es_nc = (tipo == "91")
    tr_principal = TR_CREDITO if es_nc else TR_DEBITO   # gasto/IVA: si NC va a Cr (reverso)
    tr_proveedor = TR_DEBITO if es_nc else TR_CREDITO   # proveedor: si NC va a Db (reverso)
    tr_retenciones = TR_DEBITO if es_nc else TR_CREDITO  # retenciones también se reversan

    # Db cuenta gasto (por cada tarifa de IVA con base > 0)
    for tarifa, base in fac.bases_por_tarifa.items():
        if base <= 0.5:
            continue
        out.append({
            "CUENTA": cuenta_gasto,
            "COMPROBANTE": comprobante,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_emisor,
            "DETALLE": f"{detalle} [base {tarifa}]",
            "TR": tr_principal,
            "VALOR": round(base, 0),
            "BASE": "",
            "CENTRO DE COSTO": CC_COMPRAS,
        })

    # Db IVA descontable por tarifa (Cr si es NC)
    for tarifa, iva_tarifa in fac.iva_por_tarifa.items():
        if iva_tarifa <= 0.5:
            continue
        cuenta_iva = CUENTAS_IVA_DESCONTABLE_COM.get(tarifa, "24081003")
        base_tarifa = fac.bases_por_tarifa.get(tarifa, 0)
        out.append({
            "CUENTA": cuenta_iva,
            "COMPROBANTE": comprobante,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_emisor,
            "DETALLE": f"IVA {tarifa} DESC - {detalle}",
            "TR": tr_principal,
            "VALOR": round(iva_tarifa, 0),
            "BASE": round(base_tarifa, 0),
            "CENTRO DE COSTO": CC_COMPRAS,
        })

    # Db INC pagado (Cr si es NC)
    if fac.inc_total > 0.5:
        out.append({
            "CUENTA": CUENTA_INC_COMPRAS_PAGADO,
            "COMPROBANTE": comprobante,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_emisor,
            "DETALLE": f"INC pagado - {detalle}",
            "TR": tr_principal,
            "VALOR": round(fac.inc_total, 0),
            "BASE": "",
            "CENTRO DE COSTO": CC_COMPRAS,
        })

    # Total Cr proveedor = total factura - retenciones (Db si es NC)
    cr_total = fac.total_factura
    if res_ret.aplica_retefuente:
        cr_total -= res_ret.valor_retefuente
        out.append({
            "CUENTA": res_ret.cuenta_retefuente_puc,
            "COMPROBANTE": comprobante,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_emisor,
            "DETALLE": f"Retef {res_ret.concepto_retencion} - {detalle}",
            "TR": tr_retenciones,
            "VALOR": round(res_ret.valor_retefuente, 0),
            "BASE": round(base_total, 0),
            "CENTRO DE COSTO": CC_COMPRAS,
        })
    if res_ret.aplica_reteiva:
        cr_total -= res_ret.valor_reteiva
        out.append({
            "CUENTA": res_ret.cuenta_reteiva_puc,
            "COMPROBANTE": comprobante,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_emisor,
            "DETALLE": f"ReteIVA - {detalle}",
            "TR": tr_retenciones,
            "VALOR": round(res_ret.valor_reteiva, 0),
            "BASE": round(fac.total_iva, 0),
            "CENTRO DE COSTO": CC_COMPRAS,
        })

    # Cr proveedor (Db si es NC) — lo que efectivamente se paga / devuelve
    out.append({
        "CUENTA": CUENTA_PROVEEDORES_COM,
        "COMPROBANTE": comprobante,
        "FECHA": fecha_str,
        "DOCUMENTO": fac.folio,
        "DOC REFERENCIA": "",
        "NIT": fac.nit_emisor,
        "DETALLE": detalle,
        "TR": tr_proveedor,
        "VALOR": round(cr_total, 0),
        "BASE": "",
        "CENTRO DE COSTO": CC_COMPRAS,
    })

    return out


# ─── Procesador de VENTAS MIXTAS → plano contable ───────────────
# IMPORTANTE: una venta MIXTA va al MISMO comprobante de su sucursal POS.
# El comprobante se deduce del prefijo del folio (MED→416 Medical Tower, MVI→420 Milagros Viva, etc.)
# La cuenta de IVA y la cuenta de ingreso varían según la tarifa.
CUENTA_PROPINAS = "28150505"   # PROPINAS (pasivo a empleados) - verificado histórico
CUENTAS_INGRESOS_VENTAS_MIX_POR_TARIFA = {
    "0%":   "41200902",   # PANADERIA CONGELADA SIN IVA
    "5%":   "41200905",   # OTROS PANADERIA IVA 5%
    "19%":  "41200906",   # OTRAS VENTAS GVADAS AL 19%
    "16%":  "41200906",
    "INC8%":"41401501",   # VENTAS PUNTOS CON ICO 8%
}


def procesar_zip_ventas_mixtas(
    zip_bytes: bytes,
    ruta_mapeo_prefijos: Optional[str] = None,
) -> ResultadoXMLs:
    """
    Procesa ZIP de XMLs de ventas MIXTAS emitidas por JIPER → plano contable.

    El comprobante y centro de costo de cada venta se deducen del PREFIJO del
    folio (MED→416 Medical Tower, MVI→420 Milagros Viva, etc.). Esto respeta
    el modelo contable existente de JIPER donde cada sucursal POS tiene su
    propio comprobante.

    Args:
        zip_bytes: bytes del ZIP plano con XMLs
        ruta_mapeo_prefijos: ruta a mapeo_prefijos_token.json. Si es None usa
                              "mapeo_prefijos_token.json" en el directorio actual.
    """
    res = ResultadoXMLs()
    NIT_JIPER = "901038325"

    # Cargar mapeo de prefijos
    if ruta_mapeo_prefijos is None:
        from pathlib import Path
        ruta_mapeo_prefijos = "mapeo_prefijos_token.json"
    try:
        with open(ruta_mapeo_prefijos, encoding="utf-8") as f:
            mapeo_pref_raw = json.load(f)
        # Indexar: prefijo → dict con comprobante, cc, etc.
        mapeo_pref = {}
        for entry in mapeo_pref_raw.get("mapeos", []):
            pref = entry.get("prefijo", "").upper().strip()
            if pref:
                mapeo_pref[pref] = entry
    except Exception as e:
        res.errores.append(f"No se pudo cargar mapeo de prefijos: {e}")
        mapeo_pref = {}

    for nombre, xml_str in iter_xmls_de_zip(zip_bytes):
        try:
            factura = parsear_factura(xml_str)
            if factura is None:
                res.errores.append(f"{nombre}: no se pudo parsear")
                continue
            # Solo emitidas por JIPER (JIPER es el emisor)
            if factura.nit_emisor != NIT_JIPER:
                continue
            # Excluir STL (van por procesar_zip_stl)
            if factura.prefijo.upper().startswith("STL"):
                continue
            # Evitar duplicados
            if any(f.cufe == factura.cufe for f in res.facturas):
                continue
            res.facturas.append(factura)
        except Exception as e:
            res.errores.append(f"{nombre}: {e}")

    # Generar plano
    filas = []
    sin_mapeo = []
    for fac in res.facturas:
        info_pref = mapeo_pref.get(fac.prefijo.upper().strip())
        if not info_pref:
            sin_mapeo.append(fac.folio)
            continue
        filas.extend(_generar_lineas_venta_mixta(fac, info_pref))

    if sin_mapeo:
        res.errores.append(
            f"{len(sin_mapeo)} ventas sin prefijo mapeado: {', '.join(sin_mapeo[:5])}..."
        )

    if filas:
        res.plano_df = pd.DataFrame(filas, columns=COLUMNAS_PLANO)
        res.plano_lineas = len(filas)
        from .numerador_comprobantes import aplicar_numeracion
        res.plano_df = aplicar_numeracion(res.plano_df)
    else:
        res.plano_df = pd.DataFrame(columns=COLUMNAS_PLANO)

    return res


def _generar_lineas_venta_mixta(fac, info_pref: dict):
    """
    Líneas contables para una venta MIXTA emitida.

    Modelo:
        Db CAJA SUCURSAL (cta del mapeo)             total factura
        Cr Ingresos por tarifa                       base × tarifa
        Cr IVA por tarifa                            iva
        Cr INC (si aplica)                           inc
    """
    out = []
    fecha_str = fac.fecha.strftime("%m/%d/%Y")
    detalle = f"VENTA {fac.nombre_receptor[:30]} ({fac.folio})"

    comprobante = info_pref.get("comprobante", "426")
    cc = info_pref.get("cc", "001003")
    cuenta_caja = info_pref.get("cuenta_caja", "11050505")

    # Db caja sucursal (lo que entra)
    out.append({
        "CUENTA": cuenta_caja,
        "COMPROBANTE": comprobante,
        "FECHA": fecha_str,
        "DOCUMENTO": fac.folio,
        "DOC REFERENCIA": "",
        "NIT": fac.nit_receptor,
        "DETALLE": detalle,
        "TR": TR_DEBITO,
        "VALOR": round(fac.total_factura, 0),
        "BASE": "",
        "CENTRO DE COSTO": cc,
    })

    # Cr ingresos por tarifa
    for tarifa, base in fac.bases_por_tarifa.items():
        if base <= 0.5:
            continue
        cuenta_ing = CUENTAS_INGRESOS_VENTAS_MIX_POR_TARIFA.get(tarifa, "41200902")
        out.append({
            "CUENTA": cuenta_ing,
            "COMPROBANTE": comprobante,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_receptor,
            "DETALLE": f"VENTA {tarifa} - {detalle}",
            "TR": TR_CREDITO,
            "VALOR": round(base, 0),
            "BASE": "",
            "CENTRO DE COSTO": cc,
        })

        # Cr IVA por tarifa
        iva = fac.iva_por_tarifa.get(tarifa, 0)
        if iva > 0.5:
            cuenta_iva = CUENTA_IVA_19_GENERADO if tarifa == "19%" else CUENTA_IVA_5_GENERADO
            out.append({
                "CUENTA": cuenta_iva,
                "COMPROBANTE": comprobante,
                "FECHA": fecha_str,
                "DOCUMENTO": fac.folio,
                "DOC REFERENCIA": "",
                "NIT": fac.nit_receptor,
                "DETALLE": f"IVA {tarifa} GEN - {detalle}",
                "TR": TR_CREDITO,
                "VALOR": round(iva, 0),
                "BASE": round(base, 0),
                "CENTRO DE COSTO": cc,
            })

    if fac.inc_total > 0.5:
        out.append({
            "CUENTA": CUENTA_INC_GENERADO,
            "COMPROBANTE": comprobante,
            "FECHA": fecha_str,
            "DOCUMENTO": fac.folio,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_receptor,
            "DETALLE": f"INC GEN - {detalle}",
            "TR": TR_CREDITO,
            "VALOR": round(fac.inc_total, 0),
            "BASE": "",
            "CENTRO DE COSTO": cc,
        })

    # ── Cuadre: si el total cobrado (Db) > suma de Cr, la diferencia son
    # propinas/extras que no llegaron como tarifa en el XML. Van a 28150505
    # (PROPINAS, pasivo a empleados).
    cr_acumulado = (
        sum(fac.bases_por_tarifa.values())
        + sum(fac.iva_por_tarifa.values())
        + fac.inc_total
    )
    diferencia = round(fac.total_factura - cr_acumulado, 0)
    if abs(diferencia) > 0.5:
        if diferencia > 0:
            # El Db es mayor → necesitamos un Cr extra a propinas
            out.append({
                "CUENTA": CUENTA_PROPINAS,
                "COMPROBANTE": comprobante,
                "FECHA": fecha_str,
                "DOCUMENTO": fac.folio,
                "DOC REFERENCIA": "",
                "NIT": fac.nit_receptor,
                "DETALLE": f"PROPINAS/EXTRAS - {detalle}",
                "TR": TR_CREDITO,
                "VALOR": round(diferencia, 0),
                "BASE": "",
                "CENTRO DE COSTO": cc,
            })
        else:
            # Caso raro: Cr > Db → ajuste al Db (no debería pasar pero por si acaso)
            out.append({
                "CUENTA": CUENTA_PROPINAS,
                "COMPROBANTE": comprobante,
                "FECHA": fecha_str,
                "DOCUMENTO": fac.folio,
                "DOC REFERENCIA": "",
                "NIT": fac.nit_receptor,
                "DETALLE": f"AJUSTE - {detalle}",
                "TR": TR_DEBITO,
                "VALOR": round(abs(diferencia), 0),
                "BASE": "",
                "CENTRO DE COSTO": cc,
            })

    return out


# ─── Consolidador de planos del mes ─────────────────────────────
def consolidar_planos(
    planos_ventas: list,
    planos_compras: list,
) -> dict:
    """
    Consolida múltiples planos en dos finales (ventas y compras) con
    deduplicación por (COMPROBANTE, DOCUMENTO, DOC REFERENCIA, NIT).

    REGLA DE DEDUPLICACIÓN:
        Si un documento aparece en varios planos, gana el ÚLTIMO de la lista
        (los XMLs reemplazan al Token porque tienen IVA discriminado real).

    Args:
        planos_ventas: lista de DataFrames de ventas en orden de prioridad
                       (el último gana sobre el primero)
        planos_compras: igual pero para compras

    Returns:
        dict con keys 'ventas' y 'compras' → DataFrames consolidados
    """
    def _consolidar(planos):
        if not planos:
            return pd.DataFrame(columns=COLUMNAS_PLANO)

        # Filtrar None / vacíos
        planos = [p for p in planos if p is not None and len(p) > 0]
        if not planos:
            return pd.DataFrame(columns=COLUMNAS_PLANO)

        # Acumulamos en orden inverso para que el último gane
        # (primero los más prioritarios = XMLs, después el Token)
        docs_vistos = set()
        partes = []

        # Iterar AL REVÉS: prioridad alta primero
        for plano in reversed(planos):
            p = plano.copy()
            # Clave única por documento: (COMPROBANTE, DOC REFERENCIA o DOCUMENTO, NIT)
            # Usamos DOC REFERENCIA si existe; si no, DOCUMENTO
            p["_clave"] = p.apply(
                lambda r: (
                    str(r["COMPROBANTE"]).strip(),
                    str(r["DOC REFERENCIA"]).strip() or str(r["DOCUMENTO"]).strip(),
                    str(r["NIT"]).strip(),
                ),
                axis=1
            )
            # Filtrar filas cuya clave ya fue vista (de un plano de mayor prioridad)
            mask_nuevos = ~p["_clave"].isin(docs_vistos)
            p_nuevos = p[mask_nuevos].drop(columns=["_clave"])
            partes.append(p_nuevos)
            # Marcar todas estas claves como vistas
            docs_vistos.update(p[mask_nuevos]["_clave"].tolist())

        # Concatenar (los más prioritarios quedan al principio si invertimos)
        partes.reverse()
        return pd.concat(partes, ignore_index=True)

    return {
        "ventas": _consolidar(planos_ventas),
        "compras": _consolidar(planos_compras),
    }
