"""
core/procesadores/procesador_ventas_excel_token_v2.py

Procesador v2 del Excel del Token DIAN para ventas, con consolidación
inteligente según pediste:

1. POS INC 8% → consolidado por DÍA × PREFIJO (no factura por factura)
2. STL (19% IVA) → detalle factura por factura (necesitas historial de cliente)
3. NCs POS → restan en el MISMO asiento del día/prefijo de venta
   (registro de devolución BRUTO + NC SEPARADA en el día del prefijo)
4. NCs STL → detalle factura por factura
5. DSE → con mapeo NIT → concepto contable
6. MIXTAS → fuera del plano, lista para descargar XML

EXPONE:
  ResultadoVentasV2 (dataclass)
  procesar_ventas_v2(df, mapeo_prefijos, mapeo_dse) -> ResultadoVentasV2
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


# ─── Constantes ──────────────────────────────────────────────

TARIFA_INC_POS = 0.08
TOLERANCIA = 5

NIT_GENERICO_POS = "222222222"
DETALLE_POS_PREFIJO = "VENTAS POS "
DETALLE_NC_PREFIJO  = "DEVOLUCION POS "
DETALLE_STL_PREFIJO = "VTA "

# Cuenta IVA generado en ventas (subcuenta por tarifa)
CUENTAS_IVA_VENTAS = {
    "19%": "24080501",
    "5%":  "24080502",
    "16%": "24080503",
}

# Cuentas estándar
CUENTA_OTROS_IMP_GENERICO = "24959501"
CUENTA_DEVOLUCION_VENTAS = "41754001"   # cuenta de devoluciones para NCs separadas
CUENTA_PROPINAS_POS = "28150505"        # PUC JIPER — pasivo PROPINAS

# Columnas del plano
COLUMNAS_PLANO = [
    "CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
    "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO",
]
TR_DEBITO = "1"
TR_CREDITO = "2"


# ─── Estructuras ─────────────────────────────────────────────

@dataclass
class FacturaTokenV2:
    """Una factura individual con su clasificación."""
    cufe: str
    folio: str
    prefijo: str
    fecha: date
    tipo_doc: str           # 'FE', 'NC', 'DSE'
    es_stl: bool
    es_nc: bool
    nit_emisor: str
    nombre_emisor: str
    nit_receptor: str
    nombre_receptor: str
    total: float
    inc: float
    iva: float
    otros: float
    ret: float
    tarifa: str             # 'INC8%' / '19%' / '5%' / 'EXENTA' / 'MIXTA' / 'ERROR'
    base_calc: float
    propina: float
    sucursal_info: Optional[dict] = None  # del mapeo


@dataclass
class ResultadoVentasV2:
    plano_df: Optional[pd.DataFrame] = None
    plano_lineas: int = 0

    # Por categoría procesada
    pos_consolidados: List[dict] = field(default_factory=list)  # 1 entrada por día×prefijo
    stl_detalladas: List[FacturaTokenV2] = field(default_factory=list)
    ncs_stl_detalladas: List[FacturaTokenV2] = field(default_factory=list)
    dse_detalladas: List[FacturaTokenV2] = field(default_factory=list)

    # Excluidas (no van al plano)
    mixtas: List[FacturaTokenV2] = field(default_factory=list)
    sin_sucursal: List[FacturaTokenV2] = field(default_factory=list)
    sin_concepto_dse: List[FacturaTokenV2] = field(default_factory=list)
    errores: List[FacturaTokenV2] = field(default_factory=list)

    def resumen(self) -> dict:
        # Por sucursal (POS+STL+NC consolidado para vista)
        por_suc = {}
        for grupo in self.pos_consolidados:
            cc = grupo["cc"]
            nombre = grupo["nombre_sucursal"]
            if cc not in por_suc:
                por_suc[cc] = {
                    "nombre": nombre, "clase": grupo.get("clase", ""),
                    "facs": 0, "base": 0, "inc": 0, "iva": 0, "otros": 0,
                    "propina": 0, "total": 0, "nc_base": 0, "nc_inc": 0,
                }
            por_suc[cc]["facs"] += grupo["n_facturas"]
            por_suc[cc]["base"] += grupo["base"]
            por_suc[cc]["inc"]  += grupo["inc"]
            por_suc[cc]["iva"]  += grupo.get("iva", 0)
            por_suc[cc]["otros"] += grupo.get("otros", 0)
            por_suc[cc]["propina"] += grupo["propina"]
            por_suc[cc]["total"] += grupo["total_bruto"]
            por_suc[cc]["nc_base"] += grupo.get("nc_base", 0)
            por_suc[cc]["nc_inc"] += grupo.get("nc_inc", 0)

        total_base_pos    = sum(g["base"] for g in self.pos_consolidados)
        total_inc_pos     = sum(g["inc"]  for g in self.pos_consolidados)
        total_propina_pos = sum(g["propina"] for g in self.pos_consolidados)
        total_nc_base     = sum(g.get("nc_base", 0) for g in self.pos_consolidados)
        total_nc_inc      = sum(g.get("nc_inc", 0)  for g in self.pos_consolidados)

        total_base_stl = sum(f.base_calc for f in self.stl_detalladas)
        total_iva_stl  = sum(f.iva       for f in self.stl_detalladas)

        total_dse = sum(f.total for f in self.dse_detalladas)

        return {
            "asientos_pos": len(self.pos_consolidados),
            "stl_detalladas": len(self.stl_detalladas),
            "ncs_stl_detalladas": len(self.ncs_stl_detalladas),
            "dse_procesados": len(self.dse_detalladas),
            "dse_sin_concepto": len(self.sin_concepto_dse),
            "mixtas": len(self.mixtas),
            "sin_sucursal": len(self.sin_sucursal),
            "lineas_plano": self.plano_lineas,
            "total_base_pos":    total_base_pos,
            "total_inc_pos":     total_inc_pos,
            "total_propina_pos": total_propina_pos,
            "total_nc_base_pos": total_nc_base,
            "total_nc_inc_pos":  total_nc_inc,
            "total_base_stl":    total_base_stl,
            "total_iva_stl":     total_iva_stl,
            "total_dse":         total_dse,
            "por_sucursal":      por_suc,
        }


# ─── Helpers ─────────────────────────────────────────────────

def _f(v) -> float:
    try:
        f = float(v)
        if pd.isna(f):
            return 0.0
        return f
    except (ValueError, TypeError):
        return 0.0


def _extraer_prefijo(folio: str, prefijo_col: str) -> str:
    if prefijo_col and str(prefijo_col).strip():
        return str(prefijo_col).strip().upper()
    m = re.match(r"^([A-Z_]+)", str(folio).upper().strip())
    return m.group(1) if m else ""


def _clasificar_tarifa(inc: float, iva: float, total: float, otros: float, ret: float) -> str:
    if abs(iva) < 0.01 and abs(inc) < 0.01:
        return "EXENTA"
    if abs(inc) > 0.01 and abs(iva) < 0.01:
        base = inc / TARIFA_INC_POS
        diff = total - base - iva - inc - otros - ret
        if -TOLERANCIA <= diff <= base * 0.15:
            return "INC8%"
        return "MIXTA"
    if abs(iva) > 0.01 and abs(inc) < 0.01:
        for tarifa in [0.19, 0.05, 0.16]:
            base = iva / tarifa
            diff = total - base - iva - inc - otros - ret
            if -TOLERANCIA <= diff <= base * 0.15:
                return f"{int(tarifa*100)}%"
        return "MIXTA"
    return "MIXTA"


def _calcular_base(tarifa, inc, iva, total, otros, ret):
    if tarifa == "INC8%":
        base = inc / TARIFA_INC_POS
        propina = total - base - inc - otros - ret
        return base, propina
    if tarifa == "EXENTA":
        return total - inc - iva - otros - ret, 0
    if tarifa.endswith("%"):
        tarifa_dec = float(tarifa.rstrip("%")) / 100
        base = iva / tarifa_dec
        propina = total - base - iva - inc - otros - ret
        return base, propina
    return 0, 0


def _cargar_mapeo_prefijos(ruta: str) -> Dict[str, dict]:
    """Lee mapeo_prefijos_token.json. Devuelve dict prefijo→info_completa."""
    with open(ruta) as f:
        data = json.load(f)
    out = {}
    for item in data.get("mapeos", []):
        out[item["prefijo"].upper()] = item
    return out


def _cargar_mapeo_dse(ruta: str) -> dict:
    """Lee mapeo_dse_conceptos.json. Devuelve {nit→concepto, cuentas, conceptos}."""
    with open(ruta) as f:
        data = json.load(f)
    nit_a_concepto = {}
    for item in data.get("mapeo_nit", []):
        nit_a_concepto[str(item["nit"]).strip()] = item["concepto"]
    return {
        "nit_a_concepto": nit_a_concepto,
        "cuentas": data.get("cuentas_por_concepto", {}),
    }


# ─── Procesamiento principal ─────────────────────────────────

TIPOS_FE = "Factura electrónica"
TIPOS_NC = "Nota de crédito electrónica"
TIPOS_DSE = "Documento soporte con no obligados"
TIPOS_EXCLUIR = {"Application response", "Nomina Individual"}


def procesar_ventas_v2(
    df_excel: pd.DataFrame,
    ruta_mapeo_prefijos: str,
    ruta_mapeo_dse: str,
) -> ResultadoVentasV2:
    """
    Procesa el Excel del Token DIAN aplicando la estrategia de consolidación.
    """
    resultado = ResultadoVentasV2()

    mapeo_pref = _cargar_mapeo_prefijos(ruta_mapeo_prefijos)
    mapeo_dse  = _cargar_mapeo_dse(ruta_mapeo_dse)

    # Solo emitidos
    df = df_excel[df_excel["grupo"].str.lower() == "emitido"].copy()
    df = df[~df["tipo_documento"].isin(TIPOS_EXCLUIR)]

    # Numéricos
    OTROS_COLS = ["ICA", "IC", "Timbre", "INC Bolsas", "IN Carbono",
                  "IN Combustibles", "IC Datos", "ICL", "INPP", "IBUA", "ICUI"]
    RET_COLS = ["Rete IVA", "Rete Renta", "Rete ICA"]
    for c in ["IVA", "INC"] + OTROS_COLS + RET_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
        else:
            df[c] = 0

    # Clasificar cada doc
    facturas: List[FacturaTokenV2] = []
    for _, row in df.iterrows():
        cufe = str(row.get("cufe", "")).strip()
        folio = str(row.get("folio", "")).strip()
        prefijo = _extraer_prefijo(folio, str(row.get("prefijo", "")))
        tipo_doc_text = row.get("tipo_documento", "")
        inc = _f(row["INC"]); iva = _f(row["IVA"])
        otros = sum(_f(row[c]) for c in OTROS_COLS)
        ret = sum(_f(row[c]) for c in RET_COLS)
        total = _f(row.get("total", 0))

        tarifa = _clasificar_tarifa(inc, iva, total, otros, ret)
        base, propina = _calcular_base(tarifa, inc, iva, total, otros, ret)

        fecha_em = row.get("fecha_emision")
        try:
            fecha = fecha_em.date() if hasattr(fecha_em, "date") else fecha_em
        except Exception:
            fecha = date.today()
        if fecha is None or pd.isna(fecha):
            fecha = date.today()

        # Determinar categoría
        tipo_corto = ""
        if tipo_doc_text == TIPOS_FE:
            tipo_corto = "FE"
        elif tipo_doc_text == TIPOS_NC:
            tipo_corto = "NC"
        elif tipo_doc_text == TIPOS_DSE:
            tipo_corto = "DSE"

        es_stl = prefijo == "STL"
        es_nc = tipo_doc_text == TIPOS_NC

        fac = FacturaTokenV2(
            cufe=cufe, folio=folio, prefijo=prefijo,
            fecha=fecha, tipo_doc=tipo_corto,
            es_stl=es_stl, es_nc=es_nc,
            nit_emisor=str(row.get("nit_emisor", "")),
            nombre_emisor=str(row.get("nombre_emisor", "")),
            nit_receptor=str(row.get("nit_receptor", "")),
            nombre_receptor=str(row.get("nombre_receptor", "")),
            total=total, inc=inc, iva=iva, otros=otros, ret=ret,
            tarifa=tarifa, base_calc=base, propina=propina,
            sucursal_info=mapeo_pref.get(prefijo, {}),
        )
        facturas.append(fac)

    # ── Separar por categoría ─────────────────────────────────
    # 1. POS INC8% (incluyendo NCs POS): se consolidan
    # 2. STL FE: detalle individual
    # 3. NC STL: detalle individual
    # 4. DSE: detalle individual con mapeo concepto
    # 5. MIXTAS: aparte para XML

    pos_facturas_a_consolidar = []
    pos_ncs_a_consolidar = []

    for fac in facturas:
        if fac.tarifa == "MIXTA":
            resultado.mixtas.append(fac)
            continue

        if not fac.sucursal_info and fac.tipo_doc in ("FE", "NC"):
            resultado.sin_sucursal.append(fac)
            continue

        if fac.tipo_doc == "DSE":
            concepto = mapeo_dse["nit_a_concepto"].get(fac.nit_receptor.strip())
            if not concepto:
                resultado.sin_concepto_dse.append(fac)
                continue
            cuenta_info = mapeo_dse["cuentas"].get(concepto)
            if not cuenta_info:
                resultado.sin_concepto_dse.append(fac)
                continue
            # Guardar para generar líneas
            resultado.dse_detalladas.append(fac)
            continue

        # FE o NC con sucursal mapeada
        # STL y sus NCs (prefijo NC institucional) van detalladas
        es_stl_o_nc_institucional = fac.es_stl or (fac.prefijo == "NC" and fac.es_nc)
        if es_stl_o_nc_institucional:
            if fac.es_nc:
                resultado.ncs_stl_detalladas.append(fac)
            else:
                resultado.stl_detalladas.append(fac)
            continue

        # POS (FE INC8% o NC que NO sea STL)
        if fac.es_nc:
            pos_ncs_a_consolidar.append(fac)
        else:
            pos_facturas_a_consolidar.append(fac)

    # ── Construir asientos consolidados POS ──────────────────
    # Agrupar por (fecha, prefijo) las FE y separadamente las NC
    grupos_fe = {}  # (fecha, prefijo) -> {n, base, inc, iva, otros, propina, total}
    for fac in pos_facturas_a_consolidar:
        key = (fac.fecha, fac.prefijo)
        if key not in grupos_fe:
            grupos_fe[key] = {
                "fecha": fac.fecha, "prefijo": fac.prefijo,
                "sucursal_info": fac.sucursal_info,
                "n_facturas": 0, "base": 0, "inc": 0, "iva": 0,
                "otros": 0, "propina": 0, "total_bruto": 0,
            }
        g = grupos_fe[key]
        g["n_facturas"] += 1
        g["base"] += fac.base_calc
        g["inc"] += fac.inc
        g["iva"] += fac.iva
        g["otros"] += fac.otros
        g["propina"] += fac.propina
        g["total_bruto"] += fac.total

    grupos_nc = {}
    for fac in pos_ncs_a_consolidar:
        key = (fac.fecha, fac.prefijo)
        if key not in grupos_nc:
            grupos_nc[key] = {
                "fecha": fac.fecha, "prefijo": fac.prefijo,
                "n_ncs": 0, "nc_base": 0, "nc_inc": 0,
                "nc_iva": 0, "nc_total": 0,
            }
        g = grupos_nc[key]
        g["n_ncs"] += 1
        g["nc_base"] += fac.base_calc
        g["nc_inc"] += fac.inc
        g["nc_iva"] += fac.iva
        g["nc_total"] += fac.total

    # Fusionar NCs en sus grupos FE correspondientes (o crear grupo sólo NC si no hay FE ese día)
    todos_grupos = []
    for key, g in grupos_fe.items():
        nc_data = grupos_nc.pop(key, None)
        info = g["sucursal_info"]
        consolidado = {
            "fecha": g["fecha"],
            "prefijo": g["prefijo"],
            "cc": info.get("cc", ""),
            "nombre_sucursal": info.get("sede", ""),
            "cuenta_caja": info.get("cuenta_caja", ""),
            "cta_base_v": info.get("cta_base_v", ""),
            "cta_ico": info.get("cta_ico", ""),
            "comprobante": info.get("comprobante", "497"),
            "clase": info.get("clase", ""),
            "n_facturas": g["n_facturas"],
            "base": g["base"],
            "inc": g["inc"],
            "iva": g["iva"],
            "otros": g["otros"],
            "propina": g["propina"],
            "total_bruto": g["total_bruto"],
            "n_ncs": nc_data["n_ncs"] if nc_data else 0,
            "nc_base": nc_data["nc_base"] if nc_data else 0,
            "nc_inc": nc_data["nc_inc"] if nc_data else 0,
            "nc_iva": nc_data["nc_iva"] if nc_data else 0,
            "nc_total": nc_data["nc_total"] if nc_data else 0,
        }
        todos_grupos.append(consolidado)
        resultado.pos_consolidados.append(consolidado)

    # NCs huérfanas (sin FE el mismo día/prefijo) — caso raro
    for key, g in grupos_nc.items():
        info = mapeo_pref.get(g["prefijo"], {})
        consolidado = {
            "fecha": g["fecha"],
            "prefijo": g["prefijo"],
            "cc": info.get("cc", ""),
            "nombre_sucursal": info.get("sede", ""),
            "cuenta_caja": info.get("cuenta_caja", ""),
            "cta_base_v": info.get("cta_base_v", ""),
            "cta_ico": info.get("cta_ico", ""),
            "comprobante": info.get("comprobante", "497"),
            "clase": info.get("clase", ""),
            "n_facturas": 0,
            "base": 0, "inc": 0, "iva": 0, "otros": 0,
            "propina": 0, "total_bruto": 0,
            "n_ncs": g["n_ncs"],
            "nc_base": g["nc_base"], "nc_inc": g["nc_inc"],
            "nc_iva": g["nc_iva"], "nc_total": g["nc_total"],
        }
        todos_grupos.append(consolidado)
        resultado.pos_consolidados.append(consolidado)

    # ── Construir líneas del plano ────────────────────────────
    filas = []
    for g in todos_grupos:
        filas.extend(_generar_lineas_pos_consolidado(g))

    for fac in resultado.stl_detalladas:
        filas.extend(_generar_lineas_factura_detallada(fac, es_nc=False))

    for fac in resultado.ncs_stl_detalladas:
        filas.extend(_generar_lineas_factura_detallada(fac, es_nc=True))

    for fac in resultado.dse_detalladas:
        filas.extend(_generar_lineas_dse(fac, mapeo_dse))

    if filas:
        resultado.plano_df = pd.DataFrame(filas, columns=COLUMNAS_PLANO)
        resultado.plano_lineas = len(filas)
    else:
        resultado.plano_df = pd.DataFrame(columns=COLUMNAS_PLANO)
        resultado.plano_lineas = 0

    # Aplicar numeración consecutiva por comprobante (DOCUMENTO=1,2,3... DOC REFERENCIA=folio sin prefijo)
    if resultado.plano_df is not None and len(resultado.plano_df) > 0:
        from .numerador_comprobantes import aplicar_numeracion
        resultado.plano_df = aplicar_numeracion(resultado.plano_df)

    return resultado


# ─── Generadores de líneas ───────────────────────────────────

def _generar_lineas_pos_consolidado(g: dict) -> List[dict]:
    """
    Genera un asiento consolidado por (día × prefijo) con BRUTO + NC SEPARADA.

    Líneas (FE / BRUTO):
       Db CAJA           = (base + inc + iva + otros + propina)
       Cr BASE V         = base
       Cr ICO (24800505) = inc
       Cr IVA            = iva (si > 0)
       Cr OTROS          = otros (si > 0)
       Cr PROPINAS       = propina (si > $2)   [cuenta 28150505 — PUC JIPER]

    El cuadre Db = Cr está garantizado por construcción.
    """
    out = []
    fecha_str = g["fecha"].strftime("%m/%d/%Y")
    comp = g["comprobante"]
    detalle_base = f"{DETALLE_POS_PREFIJO}{g['nombre_sucursal']} {fecha_str}"
    doc = f"POS-{g['prefijo']}-{g['fecha'].strftime('%Y%m%d')}"

    # ── BRUTO (si hay facturas) ──
    if g["n_facturas"] > 0:
        propina = round(g.get("propina", 0), 0)
        # Tolerancia: propinas ≤ $2 son redondeo, no se asientan
        if propina <= TOLERANCIA:
            propina = 0

        total_bruto_contable = round(
            g["base"] + g["inc"] + g["iva"] + g["otros"] + propina, 0
        )

        # Db Caja (incluye propina)
        out.append({
            "CUENTA": g["cuenta_caja"], "COMPROBANTE": comp, "FECHA": fecha_str,
            "DOCUMENTO": doc, "DOC REFERENCIA": "",
            "NIT": NIT_GENERICO_POS,
            "DETALLE": f"{detalle_base} ({g['n_facturas']} facs)",
            "TR": TR_DEBITO, "VALOR": total_bruto_contable, "BASE": "",
            "CENTRO DE COSTO": g["cc"],
        })
        # Cr Base
        out.append({
            "CUENTA": g["cta_base_v"], "COMPROBANTE": comp, "FECHA": fecha_str,
            "DOCUMENTO": doc, "DOC REFERENCIA": "",
            "NIT": NIT_GENERICO_POS, "DETALLE": detalle_base,
            "TR": TR_CREDITO, "VALOR": round(g["base"], 0), "BASE": "",
            "CENTRO DE COSTO": g["cc"],
        })
        # Cr INC
        if g["inc"] > 0:
            out.append({
                "CUENTA": g["cta_ico"], "COMPROBANTE": comp, "FECHA": fecha_str,
                "DOCUMENTO": doc, "DOC REFERENCIA": "",
                "NIT": NIT_GENERICO_POS, "DETALLE": f"INC 8% - {detalle_base}",
                "TR": TR_CREDITO, "VALOR": round(g["inc"], 0),
                "BASE": round(g["base"], 0),
                "CENTRO DE COSTO": g["cc"],
            })
        # Cr IVA
        if g["iva"] > 0:
            out.append({
                "CUENTA": "24080501", "COMPROBANTE": comp, "FECHA": fecha_str,
                "DOCUMENTO": doc, "DOC REFERENCIA": "",
                "NIT": NIT_GENERICO_POS, "DETALLE": f"IVA - {detalle_base}",
                "TR": TR_CREDITO, "VALOR": round(g["iva"], 0),
                "BASE": round(g["base"], 0),
                "CENTRO DE COSTO": g["cc"],
            })
        # Cr Otros
        if g["otros"] > 0.5:
            out.append({
                "CUENTA": CUENTA_OTROS_IMP_GENERICO, "COMPROBANTE": comp,
                "FECHA": fecha_str, "DOCUMENTO": doc, "DOC REFERENCIA": "",
                "NIT": NIT_GENERICO_POS, "DETALLE": f"OTROS - {detalle_base}",
                "TR": TR_CREDITO, "VALOR": round(g["otros"], 0),
                "BASE": round(g["base"], 0),
                "CENTRO DE COSTO": g["cc"],
            })
        # Cr Propinas (cuenta 28150505)
        if propina > 0:
            out.append({
                "CUENTA": CUENTA_PROPINAS_POS, "COMPROBANTE": comp,
                "FECHA": fecha_str, "DOCUMENTO": doc, "DOC REFERENCIA": "",
                "NIT": NIT_GENERICO_POS,
                "DETALLE": f"PROPINA VENTAS {g['prefijo']} - {detalle_base}",
                "TR": TR_CREDITO, "VALOR": propina, "BASE": "",
                "CENTRO DE COSTO": g["cc"],
            })

    # ── NC SEPARADA (si hay NCs ese día) ──
    if g.get("n_ncs", 0) > 0:
        nc_total_contable = round(g["nc_base"] + g["nc_inc"] + g["nc_iva"], 0)
        doc_nc = f"NC-{g['prefijo']}-{g['fecha'].strftime('%Y%m%d')}"
        detalle_nc = f"{DETALLE_NC_PREFIJO}{g['nombre_sucursal']} {fecha_str}"

        # Db Devolución en Ventas
        out.append({
            "CUENTA": CUENTA_DEVOLUCION_VENTAS, "COMPROBANTE": comp, "FECHA": fecha_str,
            "DOCUMENTO": doc_nc, "DOC REFERENCIA": "",
            "NIT": NIT_GENERICO_POS,
            "DETALLE": f"{detalle_nc} ({g['n_ncs']} NCs)",
            "TR": TR_DEBITO, "VALOR": round(g["nc_base"], 0), "BASE": "",
            "CENTRO DE COSTO": g["cc"],
        })
        # Db INC (revierte INC pagado)
        if g["nc_inc"] > 0:
            out.append({
                "CUENTA": g["cta_ico"], "COMPROBANTE": comp, "FECHA": fecha_str,
                "DOCUMENTO": doc_nc, "DOC REFERENCIA": "",
                "NIT": NIT_GENERICO_POS, "DETALLE": f"INC NC - {detalle_nc}",
                "TR": TR_DEBITO, "VALOR": round(g["nc_inc"], 0),
                "BASE": round(g["nc_base"], 0),
                "CENTRO DE COSTO": g["cc"],
            })
        # Db IVA (si NC tenía IVA)
        if g["nc_iva"] > 0:
            out.append({
                "CUENTA": "24080501", "COMPROBANTE": comp, "FECHA": fecha_str,
                "DOCUMENTO": doc_nc, "DOC REFERENCIA": "",
                "NIT": NIT_GENERICO_POS, "DETALLE": f"IVA NC - {detalle_nc}",
                "TR": TR_DEBITO, "VALOR": round(g["nc_iva"], 0),
                "BASE": round(g["nc_base"], 0),
                "CENTRO DE COSTO": g["cc"],
            })
        # Cr Caja (regresa)
        out.append({
            "CUENTA": g["cuenta_caja"], "COMPROBANTE": comp, "FECHA": fecha_str,
            "DOCUMENTO": doc_nc, "DOC REFERENCIA": "",
            "NIT": NIT_GENERICO_POS, "DETALLE": detalle_nc,
            "TR": TR_CREDITO, "VALOR": nc_total_contable, "BASE": "",
            "CENTRO DE COSTO": g["cc"],
        })

    return out


def _generar_lineas_factura_detallada(fac: FacturaTokenV2, es_nc: bool) -> List[dict]:
    """Genera asiento factura por factura (para STL y NCs STL)."""
    info = fac.sucursal_info
    comp = info.get("comprobante", "497")
    fecha_str = fac.fecha.strftime("%m/%d/%Y")
    cc = info.get("cc", "")
    detalle = f"{DETALLE_STL_PREFIJO}{fac.nombre_receptor[:30]} ({fac.folio})"
    doc = f"{fac.prefijo}{fac.folio}"

    out = []
    total_contable = round(fac.base_calc + fac.inc + fac.iva + fac.otros, 0)

    if not es_nc:
        # Venta normal: Db Cliente/Caja, Cr Base + IVA + INC
        cuenta_deb = "13050501"   # CLIENTES (asumimos crédito a 30 días para STL)
        out.append({
            "CUENTA": cuenta_deb, "COMPROBANTE": comp, "FECHA": fecha_str,
            "DOCUMENTO": doc, "DOC REFERENCIA": "",
            "NIT": fac.nit_receptor, "DETALLE": detalle,
            "TR": TR_DEBITO, "VALOR": total_contable, "BASE": "",
            "CENTRO DE COSTO": cc,
        })
        out.append({
            "CUENTA": info.get("cta_base_v", "41401501"),
            "COMPROBANTE": comp, "FECHA": fecha_str,
            "DOCUMENTO": doc, "DOC REFERENCIA": "",
            "NIT": fac.nit_receptor, "DETALLE": detalle,
            "TR": TR_CREDITO, "VALOR": round(fac.base_calc, 0), "BASE": "",
            "CENTRO DE COSTO": cc,
        })
        if fac.iva > 0:
            cuenta_iva = CUENTAS_IVA_VENTAS.get(fac.tarifa, "24080501")
            out.append({
                "CUENTA": cuenta_iva, "COMPROBANTE": comp, "FECHA": fecha_str,
                "DOCUMENTO": doc, "DOC REFERENCIA": "",
                "NIT": fac.nit_receptor,
                "DETALLE": f"IVA {fac.tarifa} - {detalle}",
                "TR": TR_CREDITO, "VALOR": round(fac.iva, 0),
                "BASE": round(fac.base_calc, 0),
                "CENTRO DE COSTO": cc,
            })
        if fac.inc > 0:
            out.append({
                "CUENTA": info.get("cta_ico", "24800505"),
                "COMPROBANTE": comp, "FECHA": fecha_str,
                "DOCUMENTO": doc, "DOC REFERENCIA": "",
                "NIT": fac.nit_receptor, "DETALLE": f"INC - {detalle}",
                "TR": TR_CREDITO, "VALOR": round(fac.inc, 0),
                "BASE": round(fac.base_calc, 0),
                "CENTRO DE COSTO": cc,
            })
        if fac.otros > 0.5:
            out.append({
                "CUENTA": CUENTA_OTROS_IMP_GENERICO,
                "COMPROBANTE": comp, "FECHA": fecha_str,
                "DOCUMENTO": doc, "DOC REFERENCIA": "",
                "NIT": fac.nit_receptor, "DETALLE": f"OTROS - {detalle}",
                "TR": TR_CREDITO, "VALOR": round(fac.otros, 0),
                "BASE": round(fac.base_calc, 0),
                "CENTRO DE COSTO": cc,
            })
    else:
        # NC: invierte. Db Devolución/IVA/INC, Cr Cliente
        out.append({
            "CUENTA": CUENTA_DEVOLUCION_VENTAS,
            "COMPROBANTE": comp, "FECHA": fecha_str,
            "DOCUMENTO": doc, "DOC REFERENCIA": "",
            "NIT": fac.nit_receptor, "DETALLE": f"NC {detalle}",
            "TR": TR_DEBITO, "VALOR": round(fac.base_calc, 0), "BASE": "",
            "CENTRO DE COSTO": cc,
        })
        if fac.iva > 0:
            cuenta_iva = CUENTAS_IVA_VENTAS.get(fac.tarifa, "24080501")
            out.append({
                "CUENTA": cuenta_iva, "COMPROBANTE": comp, "FECHA": fecha_str,
                "DOCUMENTO": doc, "DOC REFERENCIA": "",
                "NIT": fac.nit_receptor, "DETALLE": f"NC IVA - {detalle}",
                "TR": TR_DEBITO, "VALOR": round(fac.iva, 0),
                "BASE": round(fac.base_calc, 0),
                "CENTRO DE COSTO": cc,
            })
        if fac.inc > 0:
            out.append({
                "CUENTA": info.get("cta_ico", "24800505"),
                "COMPROBANTE": comp, "FECHA": fecha_str,
                "DOCUMENTO": doc, "DOC REFERENCIA": "",
                "NIT": fac.nit_receptor, "DETALLE": f"NC INC - {detalle}",
                "TR": TR_DEBITO, "VALOR": round(fac.inc, 0),
                "BASE": round(fac.base_calc, 0),
                "CENTRO DE COSTO": cc,
            })
        # Cr Cliente
        out.append({
            "CUENTA": "13050501", "COMPROBANTE": comp, "FECHA": fecha_str,
            "DOCUMENTO": doc, "DOC REFERENCIA": "",
            "NIT": fac.nit_receptor, "DETALLE": f"NC {detalle}",
            "TR": TR_CREDITO,
            "VALOR": round(fac.base_calc + fac.iva + fac.inc + fac.otros, 0),
            "BASE": "", "CENTRO DE COSTO": cc,
        })

    return out


def _generar_lineas_dse(fac: FacturaTokenV2, mapeo_dse: dict) -> List[dict]:
    """
    DSE: Db cuenta de gasto (según concepto mapeado), Cr proveedor / cuenta por pagar.
    """
    concepto = mapeo_dse["nit_a_concepto"].get(fac.nit_receptor.strip())
    cuenta_info = mapeo_dse["cuentas"].get(concepto, {"cuenta": "519595"})
    cuenta_gasto = cuenta_info["cuenta"]

    fecha_str = fac.fecha.strftime("%m/%d/%Y")
    detalle = f"{concepto} - {fac.nombre_receptor[:35]}"
    doc = f"{fac.prefijo}{fac.folio}"

    out = []
    total = round(fac.base_calc + fac.iva + fac.inc + fac.otros, 0)

    # Db Gasto
    out.append({
        "CUENTA": cuenta_gasto, "COMPROBANTE": "26",  # comprobante DSE estándar
        "FECHA": fecha_str, "DOCUMENTO": doc, "DOC REFERENCIA": "",
        "NIT": fac.nit_receptor, "DETALLE": detalle,
        "TR": TR_DEBITO, "VALOR": round(fac.base_calc, 0), "BASE": "",
        "CENTRO DE COSTO": "PRINCIPAL",
    })
    # IVA descontable si hay
    if fac.iva > 0:
        out.append({
            "CUENTA": "24080601",   # IVA descontable en DSE
            "COMPROBANTE": "26", "FECHA": fecha_str, "DOCUMENTO": doc,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_receptor, "DETALLE": f"IVA descontable - {detalle}",
            "TR": TR_DEBITO, "VALOR": round(fac.iva, 0),
            "BASE": round(fac.base_calc, 0),
            "CENTRO DE COSTO": "PRINCIPAL",
        })
    # INC pagado
    if fac.inc > 0:
        out.append({
            "CUENTA": "51959505",  # cuenta INC pagado en compras (gasto)
            "COMPROBANTE": "26", "FECHA": fecha_str, "DOCUMENTO": doc,
            "DOC REFERENCIA": "",
            "NIT": fac.nit_receptor, "DETALLE": f"INC pagado - {detalle}",
            "TR": TR_DEBITO, "VALOR": round(fac.inc, 0),
            "BASE": round(fac.base_calc, 0),
            "CENTRO DE COSTO": "PRINCIPAL",
        })
    # Cr Proveedor (cuenta por pagar)
    out.append({
        "CUENTA": "22050505",  # proveedores nacionales
        "COMPROBANTE": "26", "FECHA": fecha_str, "DOCUMENTO": doc,
        "DOC REFERENCIA": "",
        "NIT": fac.nit_receptor, "DETALLE": detalle,
        "TR": TR_CREDITO, "VALOR": total, "BASE": "",
        "CENTRO DE COSTO": "PRINCIPAL",
    })
    return out
