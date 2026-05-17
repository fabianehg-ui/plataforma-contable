"""
core/procesadores/maestro_terceros.py

Lee/escribe `maestro_terceros.json`, un archivo incremental que guarda para cada NIT:
  - Nombre razón social
  - Régimen fiscal (TaxLevelCode: R-99-PN, O-13, O-15, O-23, O-47)
  - Dirección, ciudad, departamento
  - Tipo de persona (PJ/PN)
  - Actividad económica

Cuando se procesa una compra, se consulta este maestro. Si el NIT no está, se
asume "R-99-PN declarante" (lo más conservador para JIPER como agente retenedor:
sí le retiene). Luego, con la descarga selectiva de XMLs, se completa el
maestro y la siguiente vez ya retiene correctamente.

EXPONE:
    cargar_maestro_terceros(ruta) -> dict[nit, dict]
    actualizar_maestro_desde_xml(maestro, parsed_xml) -> bool
    guardar_maestro_terceros(maestro, ruta)
    extraer_datos_tercero_de_xml(xml_str) -> dict
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional


# Namespaces UBL/DIAN
NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "ext": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "sts": "dian:gov:co:facturaelectronica:Structures-2-1",
}


def _normalizar_nit(s: str) -> str:
    """Quita DV, puntos, espacios. Solo dígitos."""
    if not s:
        return ""
    return re.sub(r"\D", "", str(s).split("-")[0])


def extraer_datos_tercero_de_xml(xml_str: str) -> Optional[dict]:
    """
    Extrae datos del PROVEEDOR (AccountingSupplierParty) desde un XML.

    Returns:
        {
            "nit": "811037075",
            "nombre": "LACTEOS BETANIA S.A.",
            "tax_level_code": "O-13;O-15",         # uno o varios separados por ;
            "tax_level_principal": "O-13",
            "ciudad": "Medellín",
            "ciudad_codigo": "05001",
            "departamento": "Antioquia",
            "departamento_codigo": "05",
            "direccion": "CR 27 C 23 SUR 51",
            "tipo_persona": "1",                    # 1=PJ, 2=PN
            "pais": "CO"
        }
    """
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return None

    # AccountingSupplierParty = el que emite la factura (proveedor cuando es compra)
    supplier = root.find(".//cac:AccountingSupplierParty/cac:Party", NS)
    if supplier is None:
        return None

    # PartyTaxScheme: NIT, nombre, código de régimen
    tax_scheme = supplier.find("cac:PartyTaxScheme", NS)
    nit = ""
    nombre = ""
    tax_level = ""
    if tax_scheme is not None:
        company_id = tax_scheme.find("cbc:CompanyID", NS)
        if company_id is not None and company_id.text:
            nit = _normalizar_nit(company_id.text)

        reg_name = tax_scheme.find("cbc:RegistrationName", NS)
        if reg_name is not None and reg_name.text:
            nombre = reg_name.text.strip()

        tax_level_node = tax_scheme.find("cbc:TaxLevelCode", NS)
        if tax_level_node is not None and tax_level_node.text:
            tax_level = tax_level_node.text.strip()

    # Si no encontró por PartyTaxScheme, intenta por PartyLegalEntity (común)
    if not nombre:
        legal = supplier.find("cac:PartyLegalEntity", NS)
        if legal is not None:
            reg_name = legal.find("cbc:RegistrationName", NS)
            if reg_name is not None and reg_name.text:
                nombre = reg_name.text.strip()

    # PhysicalLocation o RegistrationAddress: dirección
    direccion = ""
    ciudad = ""
    ciudad_cod = ""
    depto = ""
    depto_cod = ""
    pais = ""

    # Intenta primero PhysicalLocation
    phys = supplier.find("cac:PhysicalLocation/cac:Address", NS)
    if phys is None:
        # Fallback: RegistrationAddress dentro de PartyLegalEntity
        phys = supplier.find("cac:PartyLegalEntity/cac:CorporateRegistrationScheme", NS)
    if phys is None:
        # Fallback final: Address suelto
        phys = supplier.find(".//cac:Address", NS)

    if phys is not None:
        for tag, var in [
            ("cbc:CityName", "ciudad"),
            ("cbc:ID", "ciudad_cod"),
            ("cbc:CountrySubentity", "depto"),
            ("cbc:CountrySubentityCode", "depto_cod"),
        ]:
            node = phys.find(tag, NS)
            if node is not None and node.text:
                if var == "ciudad": ciudad = node.text.strip()
                elif var == "ciudad_cod": ciudad_cod = node.text.strip()
                elif var == "depto": depto = node.text.strip()
                elif var == "depto_cod": depto_cod = node.text.strip()

        # Línea de dirección
        line = phys.find("cac:AddressLine/cbc:Line", NS)
        if line is not None and line.text:
            direccion = line.text.strip()

        # País
        country = phys.find("cac:Country/cbc:IdentificationCode", NS)
        if country is not None and country.text:
            pais = country.text.strip()

    # Tipo de persona (1=PJ, 2=PN) viene en AdditionalAccountID
    tipo_persona = ""
    add_id = supplier.find("../cbc:AdditionalAccountID", NS)
    if add_id is None:
        # En algunos casos puede estar a otro nivel
        parent = root.find(".//cac:AccountingSupplierParty", NS)
        if parent is not None:
            add_id = parent.find("cbc:AdditionalAccountID", NS)
    if add_id is not None and add_id.text:
        tipo_persona = add_id.text.strip()

    # Tax_level puede traer múltiples valores separados por ; (ej. "O-13;O-15")
    tax_level_principal = tax_level.split(";")[0].strip() if tax_level else ""

    if not nit:
        return None

    return {
        "nit": nit,
        "nombre": nombre,
        "tax_level_code": tax_level,
        "tax_level_principal": tax_level_principal,
        "ciudad": ciudad,
        "ciudad_codigo": ciudad_cod,
        "departamento": depto,
        "departamento_codigo": depto_cod,
        "direccion": direccion,
        "tipo_persona": tipo_persona,
        "pais": pais,
    }


def cargar_maestro_terceros(ruta: str) -> dict:
    """Carga el maestro existente o devuelve dict vacío."""
    p = Path(ruta)
    if not p.exists():
        return {
            "_meta": {
                "version": "1.0",
                "descripcion": "Maestro de terceros con régimen fiscal, dirección y datos para retenciones y archivo Siigo",
                "creado": datetime.now().isoformat(),
            },
            "terceros": {},
        }
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def guardar_maestro_terceros(maestro: dict, ruta: str) -> None:
    """Guarda el maestro (sobrescribe)."""
    maestro["_meta"]["actualizado"] = datetime.now().isoformat()
    maestro["_meta"]["total_terceros"] = len(maestro.get("terceros", {}))
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(maestro, f, ensure_ascii=False, indent=2)


def actualizar_maestro_desde_xml(maestro: dict, parsed: dict) -> bool:
    """
    Agrega/actualiza un tercero en el maestro.

    Returns:
        True si era nuevo, False si ya existía y se actualizó.
    """
    if not parsed or not parsed.get("nit"):
        return False

    nit = parsed["nit"]
    terceros = maestro.setdefault("terceros", {})
    es_nuevo = nit not in terceros

    # Si ya existía, conservamos lo que ya hay y solo actualizamos campos vacíos
    if not es_nuevo:
        existente = terceros[nit]
        for k, v in parsed.items():
            if v and not existente.get(k):
                existente[k] = v
        existente["fuente_ultima"] = "xml"
        existente["actualizado"] = datetime.now().isoformat()
    else:
        terceros[nit] = {
            **parsed,
            "fuente_inicial": "xml",
            "creado": datetime.now().isoformat(),
        }

    return es_nuevo


def regimen_proveedor(maestro: dict, nit: str, default: str = "R-99-PN") -> str:
    """
    Devuelve el código de régimen del proveedor (TaxLevelCode principal).
    Si no está en el maestro, devuelve el default.
    """
    info = maestro.get("terceros", {}).get(_normalizar_nit(nit))
    if not info:
        return default
    return info.get("tax_level_principal") or default


def datos_tercero(maestro: dict, nit: str) -> Optional[dict]:
    """Devuelve los datos del tercero, o None si no existe."""
    return maestro.get("terceros", {}).get(_normalizar_nit(nit))
