"""
procesador_dian_xml.py
======================

Procesa un ZIP descargado del portal DIAN (catalogo-vpfe.dian.gov.co) que
contiene N sub-ZIPs, cada uno con el XML firmado de una factura, nota crédito
o nota débito recibida.

Flujo:
1. Descomprime el ZIP maestro y cada sub-ZIP
2. Parsea el XML UBL 2.1 (formato DIAN)
3. Detecta la empresa receptora por NIT
4. Carga el catálogo de mapeo de esa empresa
5. Aplica mapeo NIT-emisor + reglas de ítem → cuenta + centro de costo
6. Genera líneas del plano contable con consecutivos por comprobante
7. Marca documentos con NIT no mapeado como "pendiente_revision"

Multi-empresa:
- Cada empresa tiene su carpeta en core/data/empresas/<NIT>_<id>/
- La detección es automática vía el NIT del receptor en cada XML
- Si llegan XMLs de empresas mezcladas en un mismo ZIP, se separan
  y se procesa cada empresa de forma independiente

Multi-ZIP (v0.2):
- procesar_multiples_zips() acepta una lista de (nombre_zip, bytes)
- Detecta duplicados por CUFE entre ZIPs
- Filtra por rango de fechas opcional
- Separa salidas por tipo de comprobante o consolida en un único plano

Versión: 0.2 (29-04-2026)
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

# Precisión para Decimal — pesos colombianos no tienen subdivisión menor que centavo
getcontext().prec = 28

# ============================================================================
# CONSTANTES
# ============================================================================

# Namespaces UBL 2.1 + DIAN
NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "fe": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "sts": "dian:gov:co:facturaelectronica:Structures-2-1",
}

# UBL InvoiceTypeCode → comprobante
UBL_TIPO_DOC = {
    "01": "factura_recibida",       # Factura electrónica venta
    "02": "factura_recibida",       # Exportación
    "03": "factura_recibida",       # Contingencia
    "05": "documento_soporte_recibido",  # DS adquiridos
    "91": "nota_credito_recibida",
    "92": "nota_debito_recibida",
}

# Códigos DIAN de tributos (TaxScheme/ID en UBL)
# Referencia: Resolución DIAN tabla 13.2.6.2
TAX_SCHEME_IVA = "01"
TAX_SCHEME_IC = "04"          # Impuesto al Consumo (alias INC)
TAX_SCHEME_INC = "04"
TAX_SCHEME_RETE_IVA = "05"
TAX_SCHEME_RETE_FUENTE = "06"
TAX_SCHEME_RETE_ICA = "07"
TAX_SCHEME_ICUI = "34"        # Impuesto al Consumo de bolsas plásticas
TAX_SCHEME_IBUA = "35"        # Impuesto bebidas azucaradas (Ley 2277/2022)
TAX_SCHEME_ICUI_ALT = "36"    # Impuesto productos comestibles ultra-procesados (alt)

# Patrones por nombre de tributo (algunos proveedores ponen el nombre, no el código)
PATRONES_NOMBRE_IMPUESTO = [
    (re.compile(r"\bIBUA\b|bebid.*azucar|bebid.*ultra", re.IGNORECASE), "ibua"),
    (re.compile(r"\bICUI\b|comestibles?\s*ultra|ultra.*procesado", re.IGNORECASE), "icui"),
    (re.compile(r"\bINC\b|consumo\s*nacional|impto\.?\s*consumo|impuesto\s*al\s*consumo", re.IGNORECASE), "inc"),
]

# El nodo raíz del XML cambia según el tipo
RAIZ_POR_TIPO = {
    "Invoice": "01",
    "CreditNote": "91",
    "DebitNote": "92",
}

# ============================================================================
# DATACLASSES — modelo de datos
# ============================================================================

@dataclass
class ItemFactura:
    """Un ítem (línea) de la factura tal como viene en el XML."""
    numero_linea: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    valor_bruto: Decimal       # cantidad * precio_unitario
    descuento: Decimal         # AllowanceCharge a nivel de línea
    valor_neto: Decimal        # bruto - descuento (base gravable de línea)
    iva_porcentaje: Decimal    # 0, 5, 19...
    iva_valor: Decimal         # valor del IVA en pesos
    es_servicio: bool          # heurística simple para escoger cuenta IVA
    codigo_producto: str = ""
    unidad_medida: str = ""

    # Impuestos especiales (v0.2.2) — separados del IVA
    inc_valor: Decimal = field(default_factory=lambda: Decimal(0))     # Impuesto Nacional al Consumo (8%)
    inc_porcentaje: Decimal = field(default_factory=lambda: Decimal(0))
    ibua_valor: Decimal = field(default_factory=lambda: Decimal(0))    # Impuesto bebidas ultra-procesadas
    icui_valor: Decimal = field(default_factory=lambda: Decimal(0))    # Impuesto consumo ultraprocesados industrializados
    otros_impuestos_valor: Decimal = field(default_factory=lambda: Decimal(0))
    otros_impuestos_detalle: list = field(default_factory=list)        # [{nombre, codigo, valor}]

    # Resultado del mapeo (se llena después)
    cuenta: str = ""
    centro_costo: str = ""
    concepto: str = ""
    regla_aplicada: str = ""   # qué regla del catálogo lo asentó


@dataclass
class DocumentoDIAN:
    """Un XML procesado, con todos los campos relevantes para contabilizar."""
    # Identificación
    cufe: str                  # también llamado CUDE/CUFE — id único DIAN
    tipo_codigo: str           # 01, 91, 92, 05...
    tipo_nombre: str           # "factura_recibida", "nota_credito_recibida"...
    prefijo: str
    numero: str
    fecha_emision: str         # YYYY-MM-DD — fecha de emisión del documento
    fecha_vencimiento: str

    # Emisor
    nit_emisor: str
    nombre_emisor: str
    tipo_persona_emisor: str   # "1" natural, "2" jurídica
    regimen_emisor: str        # "48" responsable IVA, "49" no responsable

    # Receptor (= la empresa)
    nit_receptor: str
    nombre_receptor: str

    # Totales (cabecera)
    moneda: str
    valor_bruto: Decimal       # LineExtensionAmount
    descuento_total: Decimal   # AllowanceTotalAmount
    valor_base_gravable: Decimal  # TaxExclusiveAmount
    iva_total: Decimal
    valor_total: Decimal       # PayableAmount

    # Retenciones (si vienen en el XML — algunas FE las traen, otras no)
    rete_fuente: Decimal
    rete_iva: Decimal
    rete_ica: Decimal

    # Ítems
    items: list[ItemFactura] = field(default_factory=list)

    # Totales de impuestos especiales (v0.2.2)
    inc_total: Decimal = field(default_factory=lambda: Decimal(0))
    ibua_total: Decimal = field(default_factory=lambda: Decimal(0))
    icui_total: Decimal = field(default_factory=lambda: Decimal(0))
    otros_impuestos_total: Decimal = field(default_factory=lambda: Decimal(0))

    # Metadata del procesamiento
    archivo_origen: str = ""    # nombre del sub-ZIP del que salió
    zip_origen: str = ""        # nombre del ZIP maestro (para multi-zip)
    fecha_recepcion: str = ""   # YYYY-MM-DD — cuándo DIAN recibió el doc (extraída del nombre del archivo del bookmarklet)
    advertencias: list[str] = field(default_factory=list)
    pendiente_revision: bool = False
    razon_pendiente: str = ""


@dataclass
class LineaPlano:
    """Una línea del plano contable final (formato Siigo / sistema de Casa)."""
    fecha: str                   # YYYY/MM/DD
    comprobante: str             # "COMP 7", "COMP 13"...
    consecutivo: str             # "20260300001"
    cuenta: str
    centro_costo: str
    nit_tercero: str
    descripcion: str
    documento_referencia: str
    debito: Decimal
    credito: Decimal
    base: Decimal = Decimal("0")  # para retenciones/IVA: base gravable
    porcentaje: Decimal = Decimal("0")


# ============================================================================
# REGISTRY DE EMPRESAS
# ============================================================================

class RegistryEmpresas:
    """Carga y cachea los catálogos de todas las empresas configuradas."""

    def __init__(self, ruta_empresas: Path):
        self.ruta = Path(ruta_empresas)
        self._index: dict[str, Any] | None = None
        self._cache_empresas: dict[str, dict] = {}

    @property
    def index(self) -> dict[str, Any]:
        if self._index is None:
            idx_path = self.ruta / "_empresas_index.json"
            if not idx_path.exists():
                raise FileNotFoundError(f"No existe {idx_path}")
            self._index = json.loads(idx_path.read_text(encoding="utf-8"))
        return self._index

    def listar(self) -> list[dict]:
        """Devuelve la lista de empresas activas."""
        return [e for e in self.index["empresas"] if e.get("activa", True)]

    def buscar_por_nit(self, nit: str) -> dict | None:
        """Busca empresa por NIT. Acepta formatos con o sin DV (900451388 o 900451388-9)."""
        nit_norm = self._normalizar_nit(nit)
        for emp in self.index["empresas"]:
            if self._normalizar_nit(emp["nit"]) == nit_norm:
                return emp
        return None

    @staticmethod
    def _normalizar_nit(nit: str) -> str:
        """Quita caracteres no numéricos y, si tiene DV (formato XXX-Y), lo descarta."""
        if not nit:
            return ""
        # Si trae guión, tomar solo la parte antes del guión
        s = str(nit).split("-")[0]
        # Limpiar puntos, espacios, etc.
        s = re.sub(r"[^0-9]", "", s)
        return s

    def cargar(self, empresa_id: str) -> dict:
        """Carga los 3 catálogos de una empresa."""
        if empresa_id in self._cache_empresas:
            return self._cache_empresas[empresa_id]

        emp_meta = next((e for e in self.index["empresas"] if e["id"] == empresa_id), None)
        if not emp_meta:
            raise ValueError(f"Empresa '{empresa_id}' no está en el índice")

        carpeta = self.ruta / emp_meta["carpeta"]
        if not carpeta.exists():
            raise FileNotFoundError(f"No existe carpeta {carpeta}")

        empresa = json.loads((carpeta / "empresa.json").read_text(encoding="utf-8"))
        mapeo = json.loads((carpeta / "mapeo_nits.json").read_text(encoding="utf-8"))
        cc = json.loads((carpeta / "centros_costo.json").read_text(encoding="utf-8"))

        bundle = {
            "meta": emp_meta,
            "empresa": empresa,
            "mapeo": mapeo,
            "centros_costo": cc,
        }
        self._cache_empresas[empresa_id] = bundle
        return bundle


# ============================================================================
# PARSER XML UBL 2.1 / DIAN
# ============================================================================

def _texto(elem: ET.Element | None, default: str = "") -> str:
    if elem is None or elem.text is None:
        return default
    return elem.text.strip()


def _decimal(elem: ET.Element | None, default: str = "0") -> Decimal:
    txt = _texto(elem, default)
    try:
        return Decimal(txt) if txt else Decimal(default)
    except Exception:
        return Decimal(default)


def _find(root: ET.Element, xpath: str) -> ET.Element | None:
    """Find con namespaces ya resueltos."""
    return root.find(xpath, NS)


def _findall(root: ET.Element, xpath: str) -> list[ET.Element]:
    return root.findall(xpath, NS)


def _detectar_raiz(root: ET.Element) -> tuple[str, str]:
    """Algunos XMLs DIAN vienen envueltos en <AttachedDocument>; el documento real
    está dentro del CDATA de cac:Attachment/cac:ExternalReference/cbc:Description.
    Si no, el root es directamente Invoice/CreditNote/DebitNote."""
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    return tag, RAIZ_POR_TIPO.get(tag, "")


def _extraer_documento_anidado(root: ET.Element) -> ET.Element | None:
    """Si es AttachedDocument, extrae el documento interno de cbc:Description CDATA."""
    if not root.tag.endswith("AttachedDocument"):
        return None
    desc = root.find(".//cac:Attachment/cac:ExternalReference/cbc:Description", NS)
    if desc is None or not desc.text:
        return None
    try:
        # El CDATA contiene el XML de la factura/NC/ND
        return ET.fromstring(desc.text)
    except ET.ParseError:
        return None


def parsear_xml_dian(xml_bytes: bytes, archivo_origen: str = "") -> DocumentoDIAN:
    """Parsea un XML DIAN y devuelve el DocumentoDIAN normalizado."""
    root = ET.fromstring(xml_bytes)

    # Si es AttachedDocument, extraer el doc interno
    interno = _extraer_documento_anidado(root)
    if interno is not None:
        root = interno

    tag, codigo_inferido = _detectar_raiz(root)

    # InvoiceTypeCode (cuando aplica)
    inv_type = _find(root, "cbc:InvoiceTypeCode")
    credit_type = _find(root, "cbc:CreditNoteTypeCode")
    debit_type = _find(root, "cbc:DebitNoteTypeCode")

    if inv_type is not None:
        tipo_codigo = _texto(inv_type, codigo_inferido or "01")
    elif credit_type is not None:
        tipo_codigo = "91"
    elif debit_type is not None:
        tipo_codigo = "92"
    else:
        tipo_codigo = codigo_inferido or "01"

    tipo_nombre = UBL_TIPO_DOC.get(tipo_codigo, "factura_recibida")

    # Identificación
    cufe = _texto(_find(root, "cbc:UUID"))
    id_completo = _texto(_find(root, "cbc:ID"))
    # Separar prefijo y número (ej. "FE12345" → prefijo="FE", numero="12345")
    m = re.match(r"^([A-Za-z]*)(\d+)$", id_completo)
    if m:
        prefijo, numero = m.group(1), m.group(2)
    else:
        prefijo, numero = "", id_completo

    fecha_emision = _texto(_find(root, "cbc:IssueDate"))
    fecha_venc = _texto(_find(root, "cbc:DueDate"))

    # Emisor (AccountingSupplierParty)
    sup = _find(root, "cac:AccountingSupplierParty/cac:Party")
    nit_emisor = ""
    nombre_emisor = ""
    tipo_persona_emisor = ""
    regimen_emisor = ""
    if sup is not None:
        nit_emisor = _texto(_find(sup, "cac:PartyTaxScheme/cbc:CompanyID"))
        nombre_emisor = _texto(_find(sup, "cac:PartyTaxScheme/cbc:RegistrationName"))
        if not nombre_emisor:
            nombre_emisor = _texto(_find(sup, "cac:PartyName/cbc:Name"))
        tipo_persona_emisor = _texto(_find(sup, "cac:PartyTaxScheme/cbc:TaxLevelCode"))
        # Régimen: 48 = responsable IVA, 49 = no responsable
        # (algunas FE lo traen en cbc:AdditionalAccountID dentro de Party)
        regimen_emisor = _texto(_find(sup, "cbc:AdditionalAccountID"))

    # Receptor (AccountingCustomerParty)
    cust = _find(root, "cac:AccountingCustomerParty/cac:Party")
    nit_receptor = ""
    nombre_receptor = ""
    if cust is not None:
        nit_receptor = _texto(_find(cust, "cac:PartyTaxScheme/cbc:CompanyID"))
        nombre_receptor = _texto(_find(cust, "cac:PartyTaxScheme/cbc:RegistrationName"))
        if not nombre_receptor:
            nombre_receptor = _texto(_find(cust, "cac:PartyName/cbc:Name"))

    # Moneda
    moneda = _texto(_find(root, "cbc:DocumentCurrencyCode"), "COP")

    # Totales (LegalMonetaryTotal)
    total = _find(root, "cac:LegalMonetaryTotal")
    valor_bruto = _decimal(_find(total, "cbc:LineExtensionAmount")) if total is not None else Decimal(0)
    desc_total = _decimal(_find(total, "cbc:AllowanceTotalAmount")) if total is not None else Decimal(0)
    base_gravable = _decimal(_find(total, "cbc:TaxExclusiveAmount")) if total is not None else Decimal(0)
    valor_total = _decimal(_find(total, "cbc:PayableAmount")) if total is not None else Decimal(0)

    # IVA total — sumar TaxTotal donde TaxScheme/ID == "01"
    iva_total = Decimal(0)
    rete_fuente = Decimal(0)
    rete_iva = Decimal(0)
    rete_ica = Decimal(0)
    inc_total = Decimal(0)
    ibua_total = Decimal(0)
    icui_total = Decimal(0)
    otros_imp_total = Decimal(0)
    for tt in _findall(root, "cac:TaxTotal"):
        for sub in _findall(tt, "cac:TaxSubtotal"):
            scheme_id = _texto(_find(sub, "cac:TaxCategory/cac:TaxScheme/cbc:ID"))
            scheme_name = _texto(_find(sub, "cac:TaxCategory/cac:TaxScheme/cbc:Name"))
            tax_amount = _decimal(_find(sub, "cbc:TaxAmount"))

            if scheme_id == TAX_SCHEME_IVA:
                iva_total += tax_amount
            elif scheme_id == TAX_SCHEME_RETE_FUENTE:
                rete_fuente += tax_amount
            elif scheme_id == TAX_SCHEME_RETE_IVA:
                rete_iva += tax_amount
            elif scheme_id == TAX_SCHEME_RETE_ICA:
                rete_ica += tax_amount
            elif scheme_id == TAX_SCHEME_IBUA:
                ibua_total += tax_amount
            elif scheme_id == TAX_SCHEME_ICUI or scheme_id == TAX_SCHEME_ICUI_ALT:
                icui_total += tax_amount
            elif scheme_id == TAX_SCHEME_INC:
                inc_total += tax_amount
            else:
                # Si el código no es estándar, intentar identificar por nombre
                tipo_detectado = _detectar_impuesto_por_nombre(scheme_name)
                if tipo_detectado == "ibua":
                    ibua_total += tax_amount
                elif tipo_detectado == "icui":
                    icui_total += tax_amount
                elif tipo_detectado == "inc":
                    inc_total += tax_amount
                elif scheme_id and scheme_id not in ("00", ""):
                    # Cualquier otro tributo no reconocido
                    otros_imp_total += tax_amount

    # Ítems
    items: list[ItemFactura] = []
    line_xpath = "cac:InvoiceLine" if tipo_codigo in ("01", "02", "03", "04", "05") else (
        "cac:CreditNoteLine" if tipo_codigo == "91" else "cac:DebitNoteLine"
    )
    for idx, line in enumerate(_findall(root, line_xpath), start=1):
        items.append(_parsear_linea(line, idx, line_xpath))

    return DocumentoDIAN(
        cufe=cufe,
        tipo_codigo=tipo_codigo,
        tipo_nombre=tipo_nombre,
        prefijo=prefijo,
        numero=numero,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_venc,
        nit_emisor=nit_emisor,
        nombre_emisor=nombre_emisor,
        tipo_persona_emisor=tipo_persona_emisor,
        regimen_emisor=regimen_emisor,
        nit_receptor=nit_receptor,
        nombre_receptor=nombre_receptor,
        moneda=moneda,
        valor_bruto=valor_bruto,
        descuento_total=desc_total,
        valor_base_gravable=base_gravable,
        iva_total=iva_total,
        valor_total=valor_total,
        rete_fuente=rete_fuente,
        rete_iva=rete_iva,
        rete_ica=rete_ica,
        items=items,
        archivo_origen=archivo_origen,
        inc_total=inc_total,
        ibua_total=ibua_total,
        icui_total=icui_total,
        otros_impuestos_total=otros_imp_total,
    )


def _detectar_impuesto_por_nombre(nombre: str) -> str:
    """Devuelve 'ibua' | 'icui' | 'inc' | '' según el nombre del tributo."""
    if not nombre:
        return ""
    for regex, tipo in PATRONES_NOMBRE_IMPUESTO:
        if regex.search(nombre):
            return tipo
    return ""


def _parsear_linea(line: ET.Element, idx: int, line_tag: str) -> ItemFactura:
    """Parsea una línea de InvoiceLine / CreditNoteLine / DebitNoteLine."""
    descripcion = _texto(_find(line, "cac:Item/cbc:Description"))
    if not descripcion:
        descripcion = _texto(_find(line, "cac:Item/cbc:Name"))

    # Cantidad — el tag cambia según el tipo de línea
    if "CreditNote" in line_tag:
        cantidad = _decimal(_find(line, "cbc:CreditedQuantity"), "1")
    elif "DebitNote" in line_tag:
        cantidad = _decimal(_find(line, "cbc:DebitedQuantity"), "1")
    else:
        cantidad = _decimal(_find(line, "cbc:InvoicedQuantity"), "1")

    precio = _decimal(_find(line, "cac:Price/cbc:PriceAmount"))
    valor_bruto = cantidad * precio

    # Descuento de línea
    descuento = Decimal(0)
    for ac in _findall(line, "cac:AllowanceCharge"):
        is_charge = _texto(_find(ac, "cbc:ChargeIndicator")).lower() == "true"
        amt = _decimal(_find(ac, "cbc:Amount"))
        if not is_charge:
            descuento += amt

    valor_neto = _decimal(_find(line, "cbc:LineExtensionAmount"))
    if valor_neto == 0:
        valor_neto = valor_bruto - descuento

    # IVA de línea
    iva_pct = Decimal(0)
    iva_valor = Decimal(0)
    inc_valor = Decimal(0)
    inc_pct = Decimal(0)
    ibua_valor = Decimal(0)
    icui_valor = Decimal(0)
    otros_imp_valor = Decimal(0)
    otros_detalle: list = []
    for tt in _findall(line, "cac:TaxTotal"):
        for sub in _findall(tt, "cac:TaxSubtotal"):
            scheme_id = _texto(_find(sub, "cac:TaxCategory/cac:TaxScheme/cbc:ID"))
            scheme_name = _texto(_find(sub, "cac:TaxCategory/cac:TaxScheme/cbc:Name"))
            tax_amount = _decimal(_find(sub, "cbc:TaxAmount"))
            pct = _decimal(_find(sub, "cac:TaxCategory/cbc:Percent"))

            if scheme_id == TAX_SCHEME_IVA:
                iva_valor += tax_amount
                if pct > iva_pct:
                    iva_pct = pct
            elif scheme_id == TAX_SCHEME_INC:
                inc_valor += tax_amount
                if pct > inc_pct:
                    inc_pct = pct
            elif scheme_id == TAX_SCHEME_IBUA:
                ibua_valor += tax_amount
            elif scheme_id == TAX_SCHEME_ICUI or scheme_id == TAX_SCHEME_ICUI_ALT:
                icui_valor += tax_amount
            elif scheme_id in (TAX_SCHEME_RETE_IVA, TAX_SCHEME_RETE_FUENTE, TAX_SCHEME_RETE_ICA):
                # Retenciones: ya se manejan a nivel de cabecera, ignorar acá
                pass
            else:
                tipo = _detectar_impuesto_por_nombre(scheme_name)
                if tipo == "ibua":
                    ibua_valor += tax_amount
                elif tipo == "icui":
                    icui_valor += tax_amount
                elif tipo == "inc":
                    inc_valor += tax_amount
                elif scheme_id and scheme_id not in ("00", ""):
                    otros_imp_valor += tax_amount
                    otros_detalle.append({
                        "codigo": scheme_id,
                        "nombre": scheme_name,
                        "valor": float(tax_amount),
                    })

    # Heurística servicio vs bien:
    # - UBL StandardItemIdentification.ExtendedID con código "999" suele ser servicio en DIAN
    # - O por palabras clave en descripción
    es_servicio = _detectar_servicio(descripcion, line)

    codigo = _texto(_find(line, "cac:Item/cac:StandardItemIdentification/cbc:ID"))
    unidad = ""
    qty_elem = _find(line, "cbc:InvoicedQuantity")
    if qty_elem is None:
        qty_elem = _find(line, "cbc:CreditedQuantity")
    if qty_elem is None:
        qty_elem = _find(line, "cbc:DebitedQuantity")
    if qty_elem is not None:
        unidad = qty_elem.attrib.get("unitCode", "")

    return ItemFactura(
        numero_linea=idx,
        descripcion=descripcion,
        cantidad=cantidad,
        precio_unitario=precio,
        valor_bruto=valor_bruto,
        descuento=descuento,
        valor_neto=valor_neto,
        iva_porcentaje=iva_pct,
        iva_valor=iva_valor,
        es_servicio=es_servicio,
        codigo_producto=codigo,
        unidad_medida=unidad,
        inc_valor=inc_valor,
        inc_porcentaje=inc_pct,
        ibua_valor=ibua_valor,
        icui_valor=icui_valor,
        otros_impuestos_valor=otros_imp_valor,
        otros_impuestos_detalle=otros_detalle,
    )


PALABRAS_SERVICIO = re.compile(
    r"\b(servicio|honorario|asesor[ií]a|consultor[ií]a|mantenimiento|"
    r"reparaci[oó]n|alquiler|arrendamiento|suscripci[oó]n|licencia|"
    r"transporte|flete|comisi[oó]n|capacitaci[oó]n|hospedaje|publicidad)\b",
    re.IGNORECASE
)


# v0.2.2 — Detección de proveedores de insumos alimenticios
# Tanto por nombre del emisor como por palabras clave en la descripción del ítem
PALABRAS_INSUMO_ALIMENTICIO_EMISOR = re.compile(
    r"\b(POSTOBON|COCA[\s\-]*COLA|BAVARIA|FEMSA|FRITO\s*LAY|NUTRESA|"
    r"COLANTA|ALPINA|ALQUERIA|PARMALAT|"
    r"CARNES|CARNICOS?|FRIGOR[ií]ficos?|D'?\s*CARNES|"
    r"NUTRIENTES|CONCENTRADOS?|PURINA|SOLLA|"
    r"ATLANTIC\s*FS|DISTRIBUIDORA\s*DE\s*ALIMENTOS|FRUVER|FRUTAS|HORTALIZAS|"
    r"PANIFICAD|PANADER|HARIN|MOLINOS|"
    r"COMERCIALIZADORA\s*DE\s*ALIMENTOS|TECNOLOG[IÍ]A\s*ALIMENTARIA|"
    r"PESCADER|MARISCOS|AVES|POLLOS?|"
    r"ABARROTES|GRANEROS|"
    r"COOPERATIVA\s*COL(ANTA)?)\b",
    re.IGNORECASE
)

PALABRAS_INSUMO_ALIMENTICIO_ITEM = re.compile(
    r"\b(carne|pollo|pescado|cerdo|res|costilla|chicharr[oó]n|chorizo|"
    r"jam[oó]n|salchich|hamburgues|"
    r"leche|queso|yogur|crema|mantequilla|l[aá]cteo|"
    r"huevos?\b|"
    r"arroz|frijol|lenteja|pasta|harina|az[uú]car|sal\b|aceite|"
    r"tomate|cebolla|zanahoria|papa|pl[aá]tano|"
    r"fruta|verdura|hortaliza|legumbre|"
    r"pan\b|panader|tortilla|arepa|"
    r"refresco|gaseosa|bebida|jugo\b|agua|cerveza|"
    r"caf[eé]\s*(en\s*grano|molido|tostado)?|"
    r"alimento|concentrado|forraje|materia\s*prima)\b",
    re.IGNORECASE
)


def _es_insumo_alimenticio(nombre_emisor: str, descripcion_items: str) -> bool:
    """Detecta si una factura corresponde a compra de insumos alimenticios.

    Aplica si:
    - El nombre del emisor matchea palabras de proveedor de alimentos, O
    - La descripción de algún ítem matchea palabras de alimentos
    """
    if PALABRAS_INSUMO_ALIMENTICIO_EMISOR.search(nombre_emisor or ""):
        return True
    if PALABRAS_INSUMO_ALIMENTICIO_ITEM.search(descripcion_items or ""):
        return True
    return False


def _detectar_servicio(descripcion: str, line: ET.Element) -> bool:
    if PALABRAS_SERVICIO.search(descripcion or ""):
        return True
    # UNSPSC code que empieza con 80-86 suele ser servicio
    code = _texto(_find(line, "cac:Item/cac:StandardItemIdentification/cbc:ID"))
    if code and len(code) >= 2:
        try:
            primeros = int(code[:2])
            if 80 <= primeros <= 86:
                return True
        except ValueError:
            pass
    return False


# ============================================================================
# MOTOR DE MAPEO
# ============================================================================

def aplicar_mapeo(doc: DocumentoDIAN, bundle_empresa: dict) -> DocumentoDIAN:
    """Aplica el catálogo de mapeo de la empresa a cada ítem del documento.

    Modifica `doc` in-place (asigna cuenta, centro_costo, concepto, regla_aplicada
    a cada ítem) y marca pendiente_revision si el NIT no está catalogado.

    v0.2.2: Si el NIT no está catalogado pero detectamos que es proveedor de insumos
    alimenticios (por nombre del emisor o palabras clave en ítems), asigna 143505
    automáticamente Y NO marca como pendiente_revision (la asignación es correcta).
    """
    mapeo_full = bundle_empresa["mapeo"]
    fallback = mapeo_full.get("_fallback_global", {
        "cuenta": "519095",
        "centro_costo": "ADMIN",
        "concepto": "PENDIENTE DE MAPEO",
    })
    catalogo = mapeo_full.get("mapeo", {})
    empresa = bundle_empresa.get("empresa", {})
    auto_insumos = empresa.get("auto_insumos_alimenticios", {})  # {"activo": true, "cuenta": "143505", "centro_costo": "PROD"}

    nit = re.sub(r"[^0-9]", "", doc.nit_emisor or "")
    entrada = catalogo.get(nit)

    if entrada is None:
        # NIT no catalogado: intentar auto-detección de insumo alimenticio
        descripciones = " ".join((it.descripcion or "") for it in doc.items)
        if (auto_insumos.get("activo")
                and _es_insumo_alimenticio(doc.nombre_emisor, descripciones)):
            cuenta_ins = auto_insumos.get("cuenta", "143505")
            cc_ins = auto_insumos.get("centro_costo", empresa.get("centro_costo_default", "ADMIN"))
            concepto_ins = auto_insumos.get("concepto", "Materia prima - alimentos (auto)")
            for it in doc.items:
                it.cuenta = cuenta_ins
                it.centro_costo = cc_ins
                it.concepto = concepto_ins
                it.regla_aplicada = "AUTO_INSUMO_ALIMENTICIO"
            # Marcar como sugerencia para que el usuario confirme y catalogue formalmente
            doc.advertencias.append(
                f"NIT {nit} ({doc.nombre_emisor}) detectado automáticamente como insumo "
                f"alimenticio → cuenta {cuenta_ins}. Considerar catalogarlo formalmente."
            )
            return doc

        # Fallback al PENDIENTE_MAPEO
        doc.pendiente_revision = True
        doc.razon_pendiente = f"NIT {nit} ({doc.nombre_emisor}) no está en el catálogo"
        doc.advertencias.append(doc.razon_pendiente)
        for it in doc.items:
            it.cuenta = fallback["cuenta"]
            it.centro_costo = fallback["centro_costo"]
            it.concepto = fallback["concepto"]
            it.regla_aplicada = "FALLBACK_GLOBAL"
        return doc

    # NIT catalogado: aplicar reglas_item primero, luego default
    reglas = entrada.get("reglas_item", []) or []
    default = entrada.get("default", {})

    if not default:
        doc.advertencias.append(f"NIT {nit} catalogado sin 'default' — se usa fallback global")
        default = fallback

    for it in doc.items:
        regla_match = None
        for regla in reglas:
            patron = regla.get("patron", "")
            if not patron:
                continue
            if re.search(patron, it.descripcion or "", re.IGNORECASE):
                regla_match = regla
                break

        if regla_match:
            it.cuenta = regla_match["cuenta"]
            it.centro_costo = regla_match["centro_costo"]
            it.concepto = regla_match.get("concepto", "")
            it.regla_aplicada = f"REGLA_ITEM:{regla_match.get('patron', '')}"
        else:
            it.cuenta = default["cuenta"]
            it.centro_costo = default["centro_costo"]
            it.concepto = default.get("concepto", "")
            it.regla_aplicada = "DEFAULT_NIT"

    return doc


# ============================================================================
# GENERACIÓN DE PLANO CONTABLE
# ============================================================================

def _q(v: Decimal) -> Decimal:
    """Redondear a peso (0 decimales) — formato Casa UnoTres."""
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class GeneradorPlano:
    """Genera líneas de plano contable a partir de DocumentoDIAN ya mapeados.

    Maneja consecutivos por comprobante (cada comprobante tiene su propia
    numeración YYYYMMNNN desde 001).
    """

    def __init__(self, bundle_empresa: dict, anio_mes: str):
        """anio_mes formato 'YYYYMM' — para los consecutivos."""
        self.empresa = bundle_empresa["empresa"]
        self.anio_mes = anio_mes
        self._consecutivos: dict[str, int] = defaultdict(int)
        self._consecutivo_inicial = self.empresa.get("consecutivo_inicial", 1)

    def _siguiente_consecutivo(self, comp: str) -> str:
        """Devuelve el siguiente consecutivo para un comprobante, formato YYYYMMNNN."""
        if comp not in self._consecutivos:
            self._consecutivos[comp] = self._consecutivo_inicial - 1
        self._consecutivos[comp] += 1
        return f"{self.anio_mes}{self._consecutivos[comp]:03d}"

    def generar(self, doc: DocumentoDIAN) -> list[LineaPlano]:
        """Genera todas las líneas del plano para un documento."""
        comp = self._comprobante_para(doc)
        consecutivo = self._siguiente_consecutivo(comp)
        fecha_plano = doc.fecha_emision.replace("-", "/")
        doc_ref = f"{doc.prefijo}{doc.numero}"
        es_nc = doc.tipo_codigo == "91"

        lineas: list[LineaPlano] = []
        suma_neto = Decimal(0)

        # 1) Líneas de gasto/compra (una por ítem, agrupando los que comparten cuenta+CC)
        agrupados = self._agrupar_items(doc.items)
        for (cuenta, cc, concepto), grupo in agrupados.items():
            valor = sum((it.valor_neto for it in grupo), Decimal(0))
            valor = _q(valor)
            if valor == 0:
                continue
            lineas.append(LineaPlano(
                fecha=fecha_plano,
                comprobante=comp,
                consecutivo=consecutivo,
                cuenta=cuenta,
                centro_costo=cc,
                nit_tercero=doc.nit_emisor,
                descripcion=concepto or doc.nombre_emisor,
                documento_referencia=doc_ref,
                debito=valor if not es_nc else Decimal(0),
                credito=valor if es_nc else Decimal(0),
            ))
            suma_neto += valor

        # 2) IVA discriminado por tarifa (v0.2.2)
        # El catálogo de cuentas IVA puede tener estructura simple (legacy) o por tarifa:
        #   "cuentas_iva": {
        #     "bienes": "24080201",                  ← legacy: aplica a todo
        #     "servicios": "24080308",
        #     "reverso_iva_nc": "24080204",
        #     "por_tarifa": {                        ← nuevo: específico por %
        #       "5":  {"bienes": "24080203", "servicios": "24080306"},
        #       "19": {"bienes": "24080201", "servicios": "24080308"}
        #     }
        #   }
        iva_total = _q(doc.iva_total)
        if iva_total != 0:
            cuentas_iva_cfg = self.empresa.get("cuentas_iva", {})
            por_tarifa_cfg = cuentas_iva_cfg.get("por_tarifa", {})
            cuenta_iva_legacy_bienes = cuentas_iva_cfg.get("bienes", "24080201")
            cuenta_iva_legacy_serv = cuentas_iva_cfg.get("servicios", "24080308")
            cuenta_reverso_nc = cuentas_iva_cfg.get("reverso_iva_nc", "24080204")

            # Agrupar IVA por (porcentaje, es_servicio)
            grupos_iva: dict[tuple[str, bool], Decimal] = defaultdict(lambda: Decimal(0))
            for it in doc.items:
                if it.iva_valor != 0:
                    pct_key = str(int(it.iva_porcentaje))
                    grupos_iva[(pct_key, it.es_servicio)] += it.iva_valor

            # Ajustar redondeos para que la suma coincida con iva_total exacto
            suma_calc = sum(grupos_iva.values(), Decimal(0))
            diff = iva_total - _q(suma_calc)
            if diff != 0 and grupos_iva:
                # Asignar diferencia al grupo con mayor monto
                key_mayor = max(grupos_iva.keys(), key=lambda k: abs(grupos_iva[k]))
                grupos_iva[key_mayor] += diff

            # Generar línea por cada (tarifa, naturaleza)
            for (pct_key, es_serv), valor in grupos_iva.items():
                v = _q(valor)
                if v == 0:
                    continue

                # Determinar cuenta según tarifa + naturaleza + si es NC
                if es_nc:
                    cuenta_iva = cuenta_reverso_nc
                else:
                    tarifa_cfg = por_tarifa_cfg.get(pct_key, {})
                    if es_serv:
                        cuenta_iva = tarifa_cfg.get("servicios", cuenta_iva_legacy_serv)
                    else:
                        cuenta_iva = tarifa_cfg.get("bienes", cuenta_iva_legacy_bienes)

                tipo_label = "servicios" if es_serv else "bienes"
                desc_iva = (
                    f"Reverso IVA NC {tipo_label} ({pct_key}%)" if es_nc
                    else f"IVA descontable {tipo_label} {pct_key}%"
                )

                cc_iva = (self._cc_dominante_servicios(doc.items) if es_serv
                          else self._cc_dominante_bienes(doc.items))

                lineas.append(LineaPlano(
                    fecha=fecha_plano, comprobante=comp, consecutivo=consecutivo,
                    cuenta=cuenta_iva,
                    centro_costo=cc_iva,
                    nit_tercero=doc.nit_emisor,
                    descripcion=desc_iva,
                    documento_referencia=doc_ref,
                    debito=v if not es_nc else Decimal(0),
                    credito=v if es_nc else Decimal(0),
                    porcentaje=Decimal(pct_key) if pct_key.isdigit() else Decimal(0),
                ))

        # 2.5) Impuestos especiales: INC, IBUA, ICUI, otros (v0.2.2)
        cuentas_imp_esp = self.empresa.get("cuentas_impuestos_especiales", {})
        for total_imp, key_cfg, etiqueta in [
            (doc.inc_total, "inc", "INC (Impuesto Nacional al Consumo)"),
            (doc.ibua_total, "ibua", "IBUA (Impuesto Bebidas Azucaradas)"),
            (doc.icui_total, "icui", "ICUI (Impuesto Productos Ultra-procesados)"),
            (doc.otros_impuestos_total, "otros", "Otros impuestos"),
        ]:
            v = _q(total_imp)
            if v == 0:
                continue
            cuenta_imp = cuentas_imp_esp.get(key_cfg)
            if not cuenta_imp:
                # Si no está definida en la empresa, usa fallback estándar
                fallback_cuentas_imp = {
                    "inc": "24080530",
                    "ibua": "24080540",
                    "icui": "24080515",
                    "otros": "24089595",
                }
                cuenta_imp = fallback_cuentas_imp.get(key_cfg, "24089595")
                doc.advertencias.append(
                    f"Empresa sin cuenta para {key_cfg.upper()} configurada — usando fallback {cuenta_imp}"
                )

            lineas.append(LineaPlano(
                fecha=fecha_plano, comprobante=comp, consecutivo=consecutivo,
                cuenta=cuenta_imp,
                centro_costo=self._cc_dominante_bienes(doc.items),
                nit_tercero=doc.nit_emisor,
                descripcion=etiqueta if not es_nc else f"Reverso NC - {etiqueta}",
                documento_referencia=doc_ref,
                debito=v if not es_nc else Decimal(0),
                credito=v if es_nc else Decimal(0),
            ))

        # 3) Retenciones (si vienen en el XML)
        ret_cuentas = self.empresa.get("cuentas_retencion_default", {})
        for valor, cuenta_key, etiqueta in [
            (doc.rete_fuente, "rete_fuente", "Retención en la fuente"),
            (doc.rete_iva, "rete_iva", "ReteIVA"),
            (doc.rete_ica, "rete_ica", "ReteICA"),
        ]:
            v = _q(valor)
            if v == 0:
                continue
            cuenta = ret_cuentas.get(cuenta_key)
            if not cuenta:
                continue
            lineas.append(LineaPlano(
                fecha=fecha_plano, comprobante=comp, consecutivo=consecutivo,
                cuenta=cuenta,
                centro_costo=self.empresa.get("centro_costo_default", "ADMIN"),
                nit_tercero=doc.nit_emisor,
                descripcion=etiqueta,
                documento_referencia=doc_ref,
                debito=Decimal(0) if not es_nc else v,
                credito=v if not es_nc else Decimal(0),
            ))

        # 4) Contrapartida = cuenta por pagar (22050501 estándar)
        # Db = neto + IVA, Cr = retenciones; el saldo va a cuenta por pagar
        total_db = sum((l.debito for l in lineas), Decimal(0))
        total_cr = sum((l.credito for l in lineas), Decimal(0))
        contrapartida = total_db - total_cr

        if contrapartida != 0:
            lineas.append(LineaPlano(
                fecha=fecha_plano, comprobante=comp, consecutivo=consecutivo,
                cuenta="22050501",
                centro_costo=self.empresa.get("centro_costo_default", "ADMIN"),
                nit_tercero=doc.nit_emisor,
                descripcion=doc.nombre_emisor[:60],
                documento_referencia=doc_ref,
                debito=Decimal(0) if contrapartida > 0 else abs(contrapartida),
                credito=contrapartida if contrapartida > 0 else Decimal(0),
            ))

        return lineas

    def _comprobante_para(self, doc: DocumentoDIAN) -> str:
        return self.empresa["comprobantes"].get(doc.tipo_nombre, "COMP 7")

    def _agrupar_items(self, items: list[ItemFactura]) -> dict[tuple[str, str, str], list[ItemFactura]]:
        out: dict[tuple[str, str, str], list[ItemFactura]] = defaultdict(list)
        for it in items:
            key = (it.cuenta, it.centro_costo, it.concepto)
            out[key].append(it)
        return out

    def _iva_por_naturaleza(self, items: list[ItemFactura]) -> tuple[Decimal, Decimal]:
        b = sum((it.iva_valor for it in items if not it.es_servicio), Decimal(0))
        s = sum((it.iva_valor for it in items if it.es_servicio), Decimal(0))
        return b, s

    def _cc_dominante_bienes(self, items: list[ItemFactura]) -> str:
        bienes = [it for it in items if not it.es_servicio]
        if not bienes:
            return self.empresa.get("centro_costo_default", "ADMIN")
        return max(set(it.centro_costo for it in bienes), key=lambda cc: sum(
            (it.valor_neto for it in bienes if it.centro_costo == cc), Decimal(0)
        ))

    def _cc_dominante_servicios(self, items: list[ItemFactura]) -> str:
        servs = [it for it in items if it.es_servicio]
        if not servs:
            return self.empresa.get("centro_costo_default", "ADMIN")
        return max(set(it.centro_costo for it in servs), key=lambda cc: sum(
            (it.valor_neto for it in servs if it.centro_costo == cc), Decimal(0)
        ))


# ============================================================================
# PROCESADOR DE ZIP
# ============================================================================

def extraer_xmls_de_zip_maestro(zip_bytes: bytes) -> list[tuple[str, bytes]]:
    """Recibe el ZIP grande descargado por el bookmarklet (que contiene
    sub-ZIPs, uno por documento) y devuelve una lista [(nombre_archivo, xml_bytes)]
    con todos los XMLs encontrados.
    """
    xmls: list[tuple[str, bytes]] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zmaestro:
        for nombre in zmaestro.namelist():
            if nombre.startswith("_"):  # _MANIFIESTO.txt, _FALLIDOS.json
                continue
            if nombre.lower().endswith(".zip"):
                with zmaestro.open(nombre) as sub_f:
                    sub_bytes = sub_f.read()
                try:
                    with zipfile.ZipFile(io.BytesIO(sub_bytes)) as zsub:
                        for inner in zsub.namelist():
                            if inner.lower().endswith(".xml"):
                                xmls.append((f"{nombre}::{inner}", zsub.read(inner)))
                except zipfile.BadZipFile:
                    continue
            elif nombre.lower().endswith(".xml"):
                xmls.append((nombre, zmaestro.read(nombre)))
    return xmls


# ============================================================================
# API DE ALTO NIVEL — entrypoint del módulo
# ============================================================================

@dataclass
class ResultadoProcesamiento:
    empresa_id: str
    empresa_nit: str
    empresa_razon_social: str
    documentos: list[DocumentoDIAN]
    lineas_plano: list[LineaPlano]
    nits_pendientes: list[dict]   # NITs que no estaban en el catálogo
    advertencias: list[str]
    cuadre_db: Decimal
    cuadre_cr: Decimal
    cuadrado: bool


def procesar_zip(
    zip_bytes: bytes,
    registry: RegistryEmpresas,
    anio_mes: str,
    empresa_id_forzada: str | None = None,
) -> list[ResultadoProcesamiento]:
    """Procesa un ZIP descargado del bookmarklet.

    Si `empresa_id_forzada` se indica, todos los XMLs se asignan a esa empresa.
    Si no, se detecta la empresa por el NIT receptor de cada XML, y se separan
    en múltiples ResultadoProcesamiento (uno por empresa).
    """
    xmls = extraer_xmls_de_zip_maestro(zip_bytes)
    if not xmls:
        return []

    # Parsear todos los XMLs primero
    docs: list[DocumentoDIAN] = []
    for nombre, xml_bytes in xmls:
        try:
            doc = parsear_xml_dian(xml_bytes, archivo_origen=nombre)
            docs.append(doc)
        except Exception as e:
            # Loguear pero seguir
            ph = DocumentoDIAN(
                cufe="", tipo_codigo="01", tipo_nombre="factura_recibida",
                prefijo="", numero="", fecha_emision="", fecha_vencimiento="",
                nit_emisor="", nombre_emisor="", tipo_persona_emisor="", regimen_emisor="",
                nit_receptor="", nombre_receptor="",
                moneda="COP", valor_bruto=Decimal(0), descuento_total=Decimal(0),
                valor_base_gravable=Decimal(0), iva_total=Decimal(0), valor_total=Decimal(0),
                rete_fuente=Decimal(0), rete_iva=Decimal(0), rete_ica=Decimal(0),
                items=[], archivo_origen=nombre,
            )
            ph.pendiente_revision = True
            ph.razon_pendiente = f"Error parseando XML: {e}"
            ph.advertencias.append(ph.razon_pendiente)
            docs.append(ph)

    # Agrupar por empresa receptora
    if empresa_id_forzada:
        empresas_docs = {empresa_id_forzada: docs}
    else:
        empresas_docs = defaultdict(list)
        for d in docs:
            emp = registry.buscar_por_nit(d.nit_receptor)
            if emp:
                empresas_docs[emp["id"]].append(d)
            else:
                empresas_docs.setdefault("__sin_empresa__", []).append(d)

    resultados: list[ResultadoProcesamiento] = []

    for emp_id, docs_emp in empresas_docs.items():
        if emp_id == "__sin_empresa__":
            # Documentos cuyo NIT receptor no coincide con ninguna empresa configurada
            res = ResultadoProcesamiento(
                empresa_id="(no identificada)",
                empresa_nit="",
                empresa_razon_social="(NIT receptor no coincide con ninguna empresa configurada)",
                documentos=docs_emp,
                lineas_plano=[],
                nits_pendientes=[],
                advertencias=[
                    f"{len(docs_emp)} documento(s) con NIT receptor no configurado: " +
                    ", ".join(sorted({d.nit_receptor for d in docs_emp}))
                ],
                cuadre_db=Decimal(0),
                cuadre_cr=Decimal(0),
                cuadrado=False,
            )
            resultados.append(res)
            continue

        bundle = registry.cargar(emp_id)
        for d in docs_emp:
            aplicar_mapeo(d, bundle)

        gen = GeneradorPlano(bundle, anio_mes)
        lineas: list[LineaPlano] = []
        for d in sorted(docs_emp, key=lambda x: (x.fecha_emision, x.tipo_nombre, x.numero)):
            if d.cufe == "" and d.razon_pendiente:
                # Documento con error de parseo: no genera plano
                continue
            lineas.extend(gen.generar(d))

        # NITs pendientes (no catalogados)
        nits_pend: dict[str, dict] = {}
        for d in docs_emp:
            if d.pendiente_revision and d.nit_emisor:
                nits_pend.setdefault(d.nit_emisor, {
                    "nit": d.nit_emisor,
                    "nombre": d.nombre_emisor,
                    "documentos": 0,
                    "valor_total": Decimal(0),
                })
                nits_pend[d.nit_emisor]["documentos"] += 1
                nits_pend[d.nit_emisor]["valor_total"] += d.valor_total

        # Cuadre
        cuadre_db = sum((l.debito for l in lineas), Decimal(0))
        cuadre_cr = sum((l.credito for l in lineas), Decimal(0))

        res = ResultadoProcesamiento(
            empresa_id=emp_id,
            empresa_nit=bundle["empresa"]["nit"],
            empresa_razon_social=bundle["empresa"]["razon_social"],
            documentos=docs_emp,
            lineas_plano=lineas,
            nits_pendientes=list(nits_pend.values()),
            advertencias=[],
            cuadre_db=cuadre_db,
            cuadre_cr=cuadre_cr,
            cuadrado=(cuadre_db == cuadre_cr),
        )
        resultados.append(res)

    return resultados


# ============================================================================
# EXPORTACIÓN A FORMATO PLANO (TXT)
# ============================================================================

def exportar_plano_txt(lineas: list[LineaPlano], separador: str = "\t") -> str:
    """Exporta las líneas a formato plano tabular separado por tabs.
    Cabeceras compatibles con la convención del proyecto.
    """
    cabeceras = [
        "FECHA", "COMPROBANTE", "CONSECUTIVO", "CUENTA", "CENTRO_COSTO",
        "NIT_TERCERO", "DESCRIPCION", "DOCUMENTO_REF", "DEBITO", "CREDITO"
    ]
    out = [separador.join(cabeceras)]
    for l in lineas:
        out.append(separador.join([
            l.fecha,
            l.comprobante,
            l.consecutivo,
            l.cuenta,
            l.centro_costo,
            l.nit_tercero,
            l.descripcion.replace(separador, " "),
            l.documento_referencia,
            f"{l.debito:.0f}",
            f"{l.credito:.0f}",
        ]))
    return "\n".join(out) + "\n"


# ============================================================================
# v0.2 — PROCESAMIENTO MULTI-ZIP CON DEDUPLICACIÓN Y FILTRADO POR FECHAS
# ============================================================================

@dataclass
class ZipInput:
    """Una entrada del uploader múltiple: nombre lógico + bytes."""
    nombre: str
    contenido: bytes
    tipo_declarado: str = ""   # opcional: "FE", "NC", "ND", "DS" — declarado por el usuario


@dataclass
class ResumenIngesta:
    """Resumen de qué entró, qué se quedó, qué se descartó."""
    total_xmls_extraidos: int
    duplicados_descartados: int
    fuera_de_rango_fecha: int
    errores_parseo: int
    por_tipo: dict[str, int]                 # {"factura_recibida": 12, "nota_credito_recibida": 2, ...}
    por_zip: dict[str, int]                  # {"FE_marzo.zip": 12, "NC_marzo.zip": 2}
    por_empresa: dict[str, int]              # {"silla_tres": 14, "casa_unotres": 5}
    inconsistencias_tipo: list[dict]         # XMLs cuyo tipo real no coincide con el declarado
    descartados_detalle: list[dict] = field(default_factory=list)  # detalle de cada descarte


def procesar_multiples_zips(
    zips: list[ZipInput],
    registry: RegistryEmpresas,
    anio_mes: str,
    fecha_desde: str = "",
    fecha_hasta: str = "",
    empresa_id_forzada: str | None = None,
    modo_filtro_fecha: str = "emision",   # "emision" | "recepcion" | "ninguno"
) -> tuple[list[ResultadoProcesamiento], ResumenIngesta]:
    """Procesa múltiples ZIPs en una sola pasada.

    Args:
        zips: lista de ZipInput (nombre, bytes, tipo_declarado opcional)
        registry: RegistryEmpresas
        anio_mes: 'YYYYMM' para los consecutivos
        fecha_desde: 'YYYY-MM-DD' opcional
        fecha_hasta: 'YYYY-MM-DD' opcional
        empresa_id_forzada: si se indica, todos los XMLs van a esa empresa
        modo_filtro_fecha:
            - "emision": filtra por fecha_emision del XML (default, comportamiento legacy)
            - "recepcion": filtra por fecha_recepcion (cuándo DIAN recibió el doc)
            - "ninguno": no filtra por fecha — procesa todo

    Returns:
        (resultados, resumen) — resultados es una lista de ResultadoProcesamiento
        (uno por empresa detectada) y resumen es un ResumenIngesta con la trazabilidad.
    """
    cufes_vistos: set[str] = set()
    docs_unicos: list[DocumentoDIAN] = []
    resumen = ResumenIngesta(
        total_xmls_extraidos=0,
        duplicados_descartados=0,
        fuera_de_rango_fecha=0,
        errores_parseo=0,
        por_tipo=defaultdict(int),
        por_zip=defaultdict(int),
        por_empresa=defaultdict(int),
        inconsistencias_tipo=[],
        descartados_detalle=[],
    )

    # Mapeo: tipo declarado por el usuario → tipo_codigo esperado
    tipo_declarado_a_codigo = {
        "FE": "01", "FACTURA": "01",
        "NC": "91", "NOTA_CREDITO": "91", "NOTACREDITO": "91",
        "ND": "92", "NOTA_DEBITO": "92", "NOTADEBITO": "92",
        "DS": "05", "DOCUMENTO_SOPORTE": "05",
    }

    for zin in zips:
        try:
            xmls = extraer_xmls_de_zip_maestro(zin.contenido)
        except Exception as e:
            resumen.por_zip[zin.nombre] = -1  # marca de error
            continue

        resumen.total_xmls_extraidos += len(xmls)
        codigo_esperado = tipo_declarado_a_codigo.get((zin.tipo_declarado or "").upper().strip(), "")

        for nombre_archivo, xml_bytes in xmls:
            try:
                doc = parsear_xml_dian(xml_bytes, archivo_origen=nombre_archivo)
                doc.zip_origen = zin.nombre
                # Intentar extraer fecha_recepcion del nombre del archivo del bookmarklet
                # Formato esperado: YYYY-MM-DD_NIT_PREFIJO_TRACK.zip
                m_fecha = re.match(r"^(\d{4}-\d{2}-\d{2})_", nombre_archivo)
                if m_fecha:
                    doc.fecha_recepcion = m_fecha.group(1)
            except Exception as e:
                resumen.errores_parseo += 1
                resumen.descartados_detalle.append({
                    "razon": "error_parseo",
                    "zip": zin.nombre,
                    "archivo": nombre_archivo,
                    "error": str(e),
                })
                continue

            # Inconsistencia tipo declarado vs tipo real
            if codigo_esperado and doc.tipo_codigo != codigo_esperado:
                resumen.inconsistencias_tipo.append({
                    "zip": zin.nombre,
                    "archivo": nombre_archivo,
                    "tipo_declarado": zin.tipo_declarado,
                    "tipo_real": doc.tipo_nombre,
                    "documento": f"{doc.prefijo}{doc.numero}",
                })

            # Filtrar por fecha (según modo elegido)
            fuera_rango = False
            fecha_para_filtrar = ""
            if modo_filtro_fecha == "emision":
                fecha_para_filtrar = doc.fecha_emision
            elif modo_filtro_fecha == "recepcion":
                fecha_para_filtrar = doc.fecha_recepcion or doc.fecha_emision

            if modo_filtro_fecha != "ninguno" and fecha_para_filtrar:
                if fecha_desde and fecha_para_filtrar < fecha_desde:
                    fuera_rango = True
                if fecha_hasta and fecha_para_filtrar > fecha_hasta:
                    fuera_rango = True

            if fuera_rango:
                resumen.fuera_de_rango_fecha += 1
                resumen.descartados_detalle.append({
                    "razon": "fuera_de_rango_fecha",
                    "zip": zin.nombre,
                    "archivo": nombre_archivo,
                    "documento": f"{doc.prefijo}{doc.numero}",
                    "tipo": doc.tipo_nombre,
                    "fecha_emision": doc.fecha_emision,
                    "fecha_recepcion": doc.fecha_recepcion,
                    "nit_emisor": doc.nit_emisor,
                    "nombre_emisor": doc.nombre_emisor,
                    "valor": float(doc.valor_total),
                    "modo_filtro": modo_filtro_fecha,
                })
                continue

            # Deduplicación por CUFE
            if doc.cufe and doc.cufe in cufes_vistos:
                resumen.duplicados_descartados += 1
                resumen.descartados_detalle.append({
                    "razon": "duplicado_cufe",
                    "zip": zin.nombre,
                    "archivo": nombre_archivo,
                    "documento": f"{doc.prefijo}{doc.numero}",
                    "tipo": doc.tipo_nombre,
                    "cufe": doc.cufe[:16] + "...",
                    "nit_emisor": doc.nit_emisor,
                    "nombre_emisor": doc.nombre_emisor,
                })
                continue
            if doc.cufe:
                cufes_vistos.add(doc.cufe)

            docs_unicos.append(doc)
            resumen.por_zip[zin.nombre] += 1
            resumen.por_tipo[doc.tipo_nombre] += 1

    # Ahora aplicar el flujo estándar (idéntico a procesar_zip pero ya con docs deduplicados)
    if not docs_unicos:
        return [], resumen

    # Agrupar por empresa receptora
    if empresa_id_forzada:
        empresas_docs = {empresa_id_forzada: docs_unicos}
    else:
        empresas_docs = defaultdict(list)
        for d in docs_unicos:
            emp = registry.buscar_por_nit(d.nit_receptor)
            if emp:
                empresas_docs[emp["id"]].append(d)
            else:
                empresas_docs.setdefault("__sin_empresa__", []).append(d)

    resultados: list[ResultadoProcesamiento] = []

    for emp_id, docs_emp in empresas_docs.items():
        if emp_id == "__sin_empresa__":
            res = ResultadoProcesamiento(
                empresa_id="(no identificada)",
                empresa_nit="",
                empresa_razon_social="(NIT receptor no coincide con ninguna empresa configurada)",
                documentos=docs_emp,
                lineas_plano=[],
                nits_pendientes=[],
                advertencias=[
                    f"{len(docs_emp)} documento(s) con NIT receptor no configurado: " +
                    ", ".join(sorted({d.nit_receptor for d in docs_emp}))
                ],
                cuadre_db=Decimal(0),
                cuadre_cr=Decimal(0),
                cuadrado=False,
            )
            resultados.append(res)
            continue

        bundle = registry.cargar(emp_id)
        for d in docs_emp:
            aplicar_mapeo(d, bundle)

        gen = GeneradorPlano(bundle, anio_mes)
        lineas: list[LineaPlano] = []
        for d in sorted(docs_emp, key=lambda x: (x.fecha_emision, x.tipo_nombre, x.numero)):
            if d.cufe == "" and d.razon_pendiente:
                continue
            lineas.extend(gen.generar(d))

        # NITs pendientes
        nits_pend: dict[str, dict] = {}
        for d in docs_emp:
            if d.pendiente_revision and d.nit_emisor:
                nits_pend.setdefault(d.nit_emisor, {
                    "nit": d.nit_emisor,
                    "nombre": d.nombre_emisor,
                    "documentos": 0,
                    "valor_total": Decimal(0),
                })
                nits_pend[d.nit_emisor]["documentos"] += 1
                nits_pend[d.nit_emisor]["valor_total"] += d.valor_total

        cuadre_db = sum((l.debito for l in lineas), Decimal(0))
        cuadre_cr = sum((l.credito for l in lineas), Decimal(0))

        res = ResultadoProcesamiento(
            empresa_id=emp_id,
            empresa_nit=bundle["empresa"]["nit"],
            empresa_razon_social=bundle["empresa"]["razon_social"],
            documentos=docs_emp,
            lineas_plano=lineas,
            nits_pendientes=list(nits_pend.values()),
            advertencias=[],
            cuadre_db=cuadre_db,
            cuadre_cr=cuadre_cr,
            cuadrado=(cuadre_db == cuadre_cr),
        )
        resultados.append(res)
        resumen.por_empresa[emp_id] = len(docs_emp)

    return resultados, resumen


# ============================================================================
# v0.2 — SEPARACIÓN DE PLANOS POR COMPROBANTE
# ============================================================================

def separar_lineas_por_comprobante(
    lineas: list[LineaPlano],
) -> dict[str, list[LineaPlano]]:
    """Agrupa las líneas del plano por tipo de comprobante (COMP 7, COMP 13, etc).

    Útil cuando el sistema contable destino requiere planos separados por
    comprobante (algunos sistemas Siigo / WORLD OFFICE lo prefieren así).
    """
    out: dict[str, list[LineaPlano]] = defaultdict(list)
    for l in lineas:
        out[l.comprobante].append(l)
    return dict(out)


# ============================================================================
# v0.2 — REPORTE EJECUTIVO
# ============================================================================

def generar_reporte_ejecutivo(resultado: ResultadoProcesamiento) -> dict:
    """Genera un reporte resumen de KPIs para una empresa.

    Devuelve un dict con totales, top proveedores, distribución por tipo, etc.
    """
    docs = resultado.documentos
    docs_validos = [d for d in docs if d.cufe and not d.razon_pendiente]

    # Totales por tipo
    por_tipo: dict[str, dict] = defaultdict(lambda: {"cantidad": 0, "valor_total": Decimal(0), "iva": Decimal(0)})
    for d in docs_validos:
        signo = -1 if d.tipo_codigo == "91" else 1   # NC resta
        por_tipo[d.tipo_nombre]["cantidad"] += 1
        por_tipo[d.tipo_nombre]["valor_total"] += d.valor_total * signo
        por_tipo[d.tipo_nombre]["iva"] += d.iva_total * signo

    # Top proveedores por valor
    proveedores: dict[str, dict] = defaultdict(lambda: {"nombre": "", "cantidad": 0, "valor": Decimal(0)})
    for d in docs_validos:
        if not d.nit_emisor:
            continue
        signo = -1 if d.tipo_codigo == "91" else 1
        proveedores[d.nit_emisor]["nombre"] = d.nombre_emisor
        proveedores[d.nit_emisor]["cantidad"] += 1
        proveedores[d.nit_emisor]["valor"] += d.valor_total * signo

    top_proveedores = sorted(
        [{"nit": nit, **info} for nit, info in proveedores.items()],
        key=lambda x: x["valor"],
        reverse=True,
    )[:10]

    # Totales globales
    total_compras = sum(
        (d.valor_total for d in docs_validos if d.tipo_codigo != "91"),
        Decimal(0),
    )
    total_nc = sum(
        (d.valor_total for d in docs_validos if d.tipo_codigo == "91"),
        Decimal(0),
    )
    total_iva = sum((d.iva_total for d in docs_validos if d.tipo_codigo != "91"), Decimal(0)) - \
                sum((d.iva_total for d in docs_validos if d.tipo_codigo == "91"), Decimal(0))
    total_retenciones = sum(
        ((d.rete_fuente + d.rete_iva + d.rete_ica) for d in docs_validos),
        Decimal(0),
    )

    return {
        "empresa": resultado.empresa_razon_social,
        "nit": resultado.empresa_nit,
        "documentos_totales": len(docs),
        "documentos_validos": len(docs_validos),
        "documentos_pendientes": len([d for d in docs if d.pendiente_revision]),
        "total_compras_brutas": float(total_compras),
        "total_notas_credito": float(total_nc),
        "total_compras_netas": float(total_compras - total_nc),
        "total_iva_descontable": float(total_iva),
        "total_retenciones_practicadas": float(total_retenciones),
        "por_tipo": {
            k: {"cantidad": v["cantidad"], "valor_total": float(v["valor_total"]), "iva": float(v["iva"])}
            for k, v in por_tipo.items()
        },
        "top_proveedores": [
            {"nit": p["nit"], "nombre": p["nombre"], "cantidad": p["cantidad"], "valor": float(p["valor"])}
            for p in top_proveedores
        ],
        "nits_pendientes_mapeo": len(resultado.nits_pendientes),
        "cuadre_db": float(resultado.cuadre_db),
        "cuadre_cr": float(resultado.cuadre_cr),
        "cuadrado": resultado.cuadrado,
    }


# ============================================================================
# v0.2 — DETECCIÓN DE SERVICIOS PÚBLICOS (heurística sobre proveedor + ítems)
# ============================================================================

REGEX_SERVICIO_PUBLICO_EMISOR = re.compile(
    r"\b(EPM|EMPRESAS\s*P[UÚ]BLICAS|E\.?S\.?P\.?|CODENSA|ENEL|EAAB|ACUEDUCTO|"
    r"VANTI|GAS\s*NATURAL|CLARO|MOVISTAR|TIGO|UNE|EMPRESAS?\s*VARIAS|"
    r"AFINIA|AIR-?E|ELECTRICARIBE|EMSA|ESSA|CHEC|EBSA|CENS)\b",
    re.IGNORECASE,
)

CUENTAS_SERVICIOS_PUBLICOS = {
    "energia": "513525",
    "agua": "513530",
    "telecomunicaciones": "513535",
    "gas": "513540",
    "aseo": "513545",
}

REGEX_TIPO_SERVICIO = [
    (re.compile(r"energ[ií]a|kwh\b|electric", re.IGNORECASE), "energia"),
    (re.compile(r"agua|acueducto|alcantarillado", re.IGNORECASE), "agua"),
    # Internet/telco PRIMERO para que "megas" no caiga en regex de gas
    (re.compile(r"internet|fibra|banda\s*ancha|red\s*fija|telefon[ií]a|m[oó]vil|celular|megas?\b",
                re.IGNORECASE), "telecomunicaciones"),
    # \bgas\b con palabra completa (no matchea "megas")
    (re.compile(r"\bgas\b\s*(natural)?", re.IGNORECASE), "gas"),
    (re.compile(r"aseo|recolecci[oó]n|residuos", re.IGNORECASE), "aseo"),
]


def es_servicio_publico(doc: DocumentoDIAN) -> tuple[bool, str]:
    """Detecta si una factura corresponde a servicios públicos.

    Returns:
        (es_sp, tipo) — tipo es "energia"|"agua"|"gas"|"telecomunicaciones"|"aseo"|""
    """
    nombre = doc.nombre_emisor or ""
    if not REGEX_SERVICIO_PUBLICO_EMISOR.search(nombre):
        return False, ""

    # Detectar el subtipo por las descripciones de los ítems
    textos = " ".join(it.descripcion or "" for it in doc.items)
    for regex, tipo in REGEX_TIPO_SERVICIO:
        if regex.search(textos) or regex.search(nombre):
            return True, tipo
    return True, "energia"  # default si es ESP pero no podemos clasificar

