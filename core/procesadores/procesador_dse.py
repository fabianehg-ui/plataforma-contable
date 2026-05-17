"""
core/procesadores/procesador_dse.py

Procesador de Documentos Soporte Electrónicos (DSE).

Los DSE son COMPRAS a personas naturales NO obligadas a facturar
electrónicamente. La empresa JIPER los emite a sí misma como soporte
contable. Suelen ser:
  - SERVICIOS NO OBLIGADOS A FE (90% del volumen): servicios profesionales,
    administración inmobiliaria, transporte de personas, comisiones, etc.
  - COMPRAS NO OBLIGADOS A FE: insumos comprados a personas naturales

Cada DSE tiene:
  - Supplier (emisor real) = persona natural / entidad
  - Customer (receptor)    = la empresa (JIPER)
  - Concepto (en el item description)
  - Retención en la fuente posible (si aplica)

REGLAS DE PROCESAMIENTO:

  1. Lee el ZIP descargado del portal DIAN con todos los DSE del mes.
  2. Clasifica por tipo (SERVICIOS vs COMPRAS) según item description.
  3. Mapea proveedores conocidos a cuentas específicas.
  4. Genera asiento:
       Db CUENTA GASTO (segun concepto)
       Cr CUENTA PROVEEDOR/CXP (13xx o 22xx)
       Db/Cr RETENCIONES si aplica

  5. Genera plano Silla3 listo para subir.

OUTPUT:
  - plano DataFrame (formato Silla3)
  - resumen por proveedor
  - alertas si hay DSE sin clasificar
"""

from __future__ import annotations

import io
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ============================================================
# Constantes
# ============================================================

TOLERANCIA_PESOS = 5.0

# Columnas del plano Silla3 (mismas que POS y STL)
COLUMNAS_PLANO = [
    "CUENTA",
    "COMPROBANTE",
    "FECHA",
    "DOCUMENTO",
    "DOC REFERENCIA",
    "NIT",
    "DETALLE",
    "TR",
    "VALOR",
    "BASE",
    "CENTRO DE COSTO",
]


# ============================================================
# Configuración por defecto
# ============================================================

CONFIG_DSE_DEFAULT = {
    "comprobante_dse": "3",  # típicamente Comprobante de Egreso/Causación
    "cc_default": "001100",  # general / administración
    "cta_proveedor": "23358001",  # CXP servicios — ajustable

    # Mapeo de conceptos a cuenta
    "cuentas_por_concepto": {
        "SERVICIOS NO OBLIGADOS A FE": {
            "cta_gasto": "51359501",       # OTROS SERVICIOS (gasto admin)
            "etiqueta": "Servicios",
        },
        "COMPRAS NO OBLIGADOS A FE": {
            "cta_gasto": "51359501",       # OTROS SERVICIOS por defecto - editable
            "etiqueta": "Compras",
        },
    },

    # Proveedores con cuenta específica (override del genérico)
    "proveedores_especiales": {
        # NIT → cuenta gasto
        "900266206": {  # CONJUNTO SAN LUCAS PLAZA
            "cta_gasto": "51201001",  # Arrendamiento construcciones
            "concepto":  "ARRENDAMIENTO",
        },
        "890905730": {  # COOPERATIVA TRANSPORTADORES TAX
            "cta_gasto": "51355001",  # Transporte
            "concepto":  "TRANSPORTE",
        },
        "800093761": {  # EMPRESA TRANSPORTADORA TAXIS
            "cta_gasto": "51355001",
            "concepto":  "TRANSPORTE",
        },
    },

    "nit_empresa": "901038325",
}


def cargar_config_dse(ruta: str | Path | None = None) -> dict:
    """Carga configuración DSE. Si no hay archivo, usa default."""
    if ruta is None:
        ruta = Path(__file__).resolve().parents[1] / "data" / "config_dse.json"
    ruta = Path(ruta)
    if not ruta.exists():
        return CONFIG_DSE_DEFAULT
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# Procesador
# ============================================================

def procesar_dse(
    fuente_zip,
    config: dict | None = None,
    anio: int | None = None,
    mes: int | None = None,
) -> dict:
    """
    Procesa ZIP de DSE y genera plano contable.

    Args:
        fuente_zip: bytes/path/file-like del ZIP de DSE descargado de DIAN
        config: configuración DSE (cuentas, conceptos)
        anio, mes: filtros opcionales

    Returns:
        dict con plano, resumen, alertas
    """
    from core.procesadores.parser_xml_stl import procesar_zip_xmls_stl, parsear_xml_dian

    if config is None:
        config = cargar_config_dse()

    log = []

    # Leer ZIP
    resultado_zip = procesar_zip_xmls_stl(fuente_zip)
    log.extend(resultado_zip["log"])

    # Filtrar solo los DSE
    dses = []
    for f in resultado_zip["facturas"]:
        if f.get("es_duplicado"):
            continue
        # DSE = facturas con tipo_codigo 05 (Documento Soporte Electrónico)
        if f["tipo_codigo"] != "05":
            continue

        fecha = f["fecha"]
        if anio and fecha and fecha.year != anio:
            continue
        if mes and fecha and fecha.month != mes:
            continue
        dses.append(f)

    log.append(f"📋 DSE detectados: {len(dses)}")

    # Inferir período
    if anio is None or mes is None:
        fechas = [d["fecha"] for d in dses if d["fecha"]]
        if fechas:
            ultima = max(fechas)
            anio = anio or ultima.year
            mes  = mes or ultima.month

    # Para cada DSE, extraer concepto y proveedor
    # Necesitamos releer el XML para sacar el concepto del item description
    # (el parser_xml_stl no extrae eso por defecto)
    # Re-parsear los XMLs de DSE
    dses_enriquecidos = []
    import zipfile
    import re

    # Volver a leer el ZIP para extraer conceptos
    if hasattr(fuente_zip, "read"):
        fuente_zip.seek(0)
        bio = io.BytesIO(fuente_zip.read())
    elif isinstance(fuente_zip, (bytes, bytearray)):
        bio = io.BytesIO(bytes(fuente_zip))
    elif isinstance(fuente_zip, (str, Path)):
        bio = str(fuente_zip)
    else:
        bio = fuente_zip

    conceptos_por_folio = {}
    with zipfile.ZipFile(bio, 'r') as zf:
        for nombre in zf.namelist():
            if not nombre.lower().endswith('.zip'):
                continue
            try:
                with zipfile.ZipFile(io.BytesIO(zf.read(nombre)), 'r') as zf2:
                    for n2 in zf2.namelist():
                        if not n2.lower().endswith('.xml'):
                            continue
                        c = zf2.read(n2).decode('utf-8', errors='replace')
                        # Detectar AttachedDocument
                        if '<AttachedDocument' in c[:500]:
                            m = re.search(
                                r'<cbc:Description><!\[CDATA\[(.*?)\]\]></cbc:Description>',
                                c, re.DOTALL
                            )
                            if m:
                                c = m.group(1)
                        # Folio
                        if '</ext:UBLExtensions>' in c:
                            tail = c[c.find('</ext:UBLExtensions>'):]
                            m = re.search(r'<cbc:ID>([^<]+)</cbc:ID>', tail)
                        else:
                            m = re.search(r'<cbc:ID>([^<]+)</cbc:ID>', c)
                        folio = m.group(1) if m else None
                        if not folio:
                            continue
                        # Item description
                        item_desc = re.findall(
                            r'<cac:Item>.*?<cbc:Description>([^<]+)</cbc:Description>',
                            c, re.DOTALL
                        )
                        conceptos_por_folio[folio] = item_desc[0].strip() if item_desc else ""
            except Exception:
                continue

    # Generar líneas contables
    lineas = []
    resumen_concepto = defaultdict(lambda: {"docs": 0, "total": 0.0})
    resumen_proveedor = defaultdict(lambda: {"docs": 0, "total": 0.0, "nombre": ""})
    alertas = []

    cuentas_concepto = config["cuentas_por_concepto"]
    proveedores_especiales = config.get("proveedores_especiales", {})
    cta_proveedor = config["cta_proveedor"]
    comprobante   = str(config["comprobante_dse"])
    cc_default    = config["cc_default"]

    for d in dses:
        folio = d["folio"]
        fecha = d["fecha"]
        fecha_str = fecha.strftime("%m/%d/%Y") if fecha else ""

        # En DSE el "Supplier" es el proveedor (persona natural)
        # y el "Customer" es JIPER (la empresa)
        nit_prov    = d["nit_emisor"]
        nombre_prov = d["nombre_emisor"]
        total       = round(d["totales"]["payable"], 2)
        concepto    = conceptos_por_folio.get(folio, "")

        if total <= 0:
            alertas.append({
                "tipo": "dse_total_cero",
                "folio": folio,
                "mensaje": "Total <= 0, se ignora",
            })
            continue

        # Determinar cuenta gasto:
        # 1. Si el proveedor está en proveedores_especiales → usar esa cuenta
        # 2. Si no, mapear por concepto
        cta_gasto = None
        if nit_prov in proveedores_especiales:
            cta_gasto = proveedores_especiales[nit_prov]["cta_gasto"]
            tipo_etiqueta = proveedores_especiales[nit_prov]["concepto"]
        elif concepto in cuentas_concepto:
            cta_gasto = cuentas_concepto[concepto]["cta_gasto"]
            tipo_etiqueta = cuentas_concepto[concepto]["etiqueta"]
        else:
            # No clasificado → usar cuenta SERVICIOS por defecto + alerta
            cta_gasto = cuentas_concepto.get("SERVICIOS NO OBLIGADOS A FE", {}).get("cta_gasto", "51359501")
            tipo_etiqueta = "Sin clasificar"
            alertas.append({
                "tipo": "concepto_no_mapeado",
                "folio": folio,
                "nit_prov": nit_prov,
                "concepto": concepto,
                "mensaje": f"Concepto '{concepto}' no está mapeado. Se usó cuenta genérica.",
            })

        documento = folio.replace("DSE", "") if folio.startswith("DSE") else folio
        doc_ref   = folio
        detalle   = f"DSE {folio} - {nombre_prov[:30]}"

        # Db Gasto
        lineas.append({
            "CUENTA":          cta_gasto,
            "COMPROBANTE":     comprobante,
            "FECHA":           fecha_str,
            "DOCUMENTO":       documento,
            "DOC REFERENCIA":  doc_ref,
            "NIT":             nit_prov,
            "DETALLE":         detalle,
            "TR":              "1",
            "VALOR":           total,
            "BASE":            "",
            "CENTRO DE COSTO": cc_default,
        })

        # Cr Proveedor / Cuenta por pagar
        lineas.append({
            "CUENTA":          cta_proveedor,
            "COMPROBANTE":     comprobante,
            "FECHA":           fecha_str,
            "DOCUMENTO":       documento,
            "DOC REFERENCIA":  doc_ref,
            "NIT":             nit_prov,
            "DETALLE":         detalle,
            "TR":              "2",
            "VALOR":           total,
            "BASE":            "",
            "CENTRO DE COSTO": cc_default,
        })

        resumen_concepto[concepto or "(sin descripción)"]["docs"] += 1
        resumen_concepto[concepto or "(sin descripción)"]["total"] += total

        k_prov = nit_prov
        resumen_proveedor[k_prov]["docs"] += 1
        resumen_proveedor[k_prov]["total"] += total
        resumen_proveedor[k_prov]["nombre"] = nombre_prov

    import pandas as pd
    plano = pd.DataFrame(lineas, columns=COLUMNAS_PLANO) if lineas else pd.DataFrame(columns=COLUMNAS_PLANO)

    # Cuadre
    if len(plano) > 0:
        debitos  = plano[plano["TR"] == "1"]["VALOR"].sum()
        creditos = plano[plano["TR"] == "2"]["VALOR"].sum()
    else:
        debitos = creditos = 0.0
    diferencia = round(debitos - creditos, 2)

    log.append(f"💰 Total Db: ${debitos:,.2f}, Total Cr: ${creditos:,.2f}")
    log.append(f"📐 Cuadre: {'✅' if abs(diferencia) < TOLERANCIA_PESOS else '❌'}")

    return {
        "plano":               plano,
        "resumen_concepto":    dict(resumen_concepto),
        "resumen_proveedor":   dict(resumen_proveedor),
        "alertas":             alertas,
        "cuadre": {
            "debitos":    round(debitos, 2),
            "creditos":   round(creditos, 2),
            "diferencia": diferencia,
            "cuadra":     abs(diferencia) < TOLERANCIA_PESOS,
        },
        "log":                 log,
        "metadatos": {
            "anio": anio,
            "mes":  mes,
            "dses_procesados": len(dses),
            "lineas_plano":    len(plano),
            "duplicados_zip":  resultado_zip["duplicados"],
        },
    }


# ============================================================
# Exportadores
# ============================================================

def plano_dse_a_tsv(df) -> bytes:
    if len(df) == 0:
        return "".encode("utf-8-sig")
    return df.to_csv(sep="\t", index=False, encoding="utf-8-sig").encode("utf-8-sig")


def plano_dse_a_csv(df) -> bytes:
    if len(df) == 0:
        return "".encode("utf-8-sig")
    return df.to_csv(sep=",", index=False, encoding="utf-8-sig").encode("utf-8-sig")


def plano_dse_a_xlsx(df, resumen: dict | None = None) -> bytes:
    import pandas as pd
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Plano", index=False)

        if resumen is not None:
            # Resumen por concepto
            rc = resumen.get("resumen_concepto") or {}
            if rc:
                df_rc = pd.DataFrame([
                    {"Concepto": k, "Docs": v["docs"], "Total": v["total"]}
                    for k, v in rc.items()
                ])
                df_rc.to_excel(w, sheet_name="Por concepto", index=False)

            # Resumen por proveedor
            rp = resumen.get("resumen_proveedor") or {}
            if rp:
                df_rp = pd.DataFrame([
                    {"NIT": k, "Nombre": v["nombre"], "Docs": v["docs"], "Total": v["total"]}
                    for k, v in rp.items()
                ]).sort_values("Total", ascending=False)
                df_rp.to_excel(w, sheet_name="Por proveedor", index=False)

            # Cuadre
            cu = resumen.get("cuadre", {})
            meta = resumen.get("metadatos", {})
            df_cu = pd.DataFrame([
                {"Concepto": "Período",     "Valor": f"{meta.get('anio','')}-{meta.get('mes',''):02d}" if meta.get('mes') else ""},
                {"Concepto": "DSE",         "Valor": meta.get("dses_procesados", 0)},
                {"Concepto": "Líneas",      "Valor": meta.get("lineas_plano", 0)},
                {"Concepto": "Débitos",     "Valor": cu.get("debitos", 0)},
                {"Concepto": "Créditos",    "Valor": cu.get("creditos", 0)},
                {"Concepto": "Diferencia",  "Valor": cu.get("diferencia", 0)},
                {"Concepto": "Cuadra",      "Valor": "✅" if cu.get("cuadra") else "❌"},
            ])
            df_cu.to_excel(w, sheet_name="Cuadre", index=False)

            # Alertas
            alertas = resumen.get("alertas") or []
            if alertas:
                pd.DataFrame(alertas).to_excel(w, sheet_name="Alertas", index=False)

    buf.seek(0)
    return buf.read()
