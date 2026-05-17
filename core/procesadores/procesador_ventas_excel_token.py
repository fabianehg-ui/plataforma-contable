"""
core/procesadores/procesador_ventas_excel_token.py

Procesa el Excel del Token DIAN para generar el plano contable de ventas POS,
SIN necesidad de descargar XMLs.

FÓRMULA (acordada con Luz):
    Para cada factura POS:
        base       = INC / 0.08
        total_contable = base + INC
        propina    = Total_factura - base - INC   (≈10%, NO se contabiliza)

ASIENTO contable (mismo formato que el procesador POS antiguo):
    Db  CUENTA DE CAJA    = base + INC  (total_contable)
    Cr  CTA BASE V        = base
    Cr  CTA ICO           = INC

Las sucursales se mapean por prefijo (IND, MLA, VIV, etc.) → datos_punto.json.

CASOS QUE EL EXCEL CUBRE BIEN (>99% de POS):
    - Facturas con INC 8% + propina
    - Facturas exentas (sin IVA ni INC)
    - Facturas 19% puro (a empresas, raras en POS)

CASOS QUE NO CUBRE (van al flujo XML):
    - Facturas con mezcla de tarifas (ej. línea 5% + línea 19%) — "MIXTAS"

EXPONE:
    procesar_ventas_excel(df_excel, mapeo_sucursales) -> ResultadoVentas
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import pandas as pd


# ─── Constantes contables ────────────────────────────────────

# Tolerancia de cuadre en pesos (redondeo)
TOLERANCIA = 5

# Tarifa única estándar para restaurantes de JIPER
TARIFA_INC_POS = 0.08

# Cuenta IVA generado por tarifa (24080xxx en JIPER)
# Para el plano de ventas usamos cuenta única, pero subcuentas por tarifa
CUENTAS_IVA_VENTAS = {
    "19%":   "24080501",   # IVA generado 19% en ventas
    "5%":    "24080502",   # IVA generado 5% en ventas
    "16%":   "24080503",   # IVA generado 16% (raro pero existe)
}

# NIT genérico para consumidor final
NIT_GENERICO_POS = "222222222"
DETALLE_PREFIJO = "VENTAS POS "

# Columnas del plano de salida (igual que procesador POS antiguo)
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

# Tipos de transacción
TR_DEBITO = "1"
TR_CREDITO = "2"


@dataclass
class FacturaVenta:
    """Una factura procesada desde el Excel."""
    cufe: str
    folio: str
    prefijo: str
    fecha: date
    total: float
    inc: float
    iva: float
    base_calc: float          # INC / 0.08
    propina: float            # Total - base - INC
    tarifa: str               # 'INC8%' / 'EXENTA' / '19%' / 'MIXTA'
    cc: Optional[str]
    cuenta_caja: Optional[str]
    cta_base_v: Optional[str]
    cta_ico: Optional[str]
    comprobante: Optional[str]
    nombre_sucursal: Optional[str]


@dataclass
class ResultadoVentas:
    """Resultado de procesar todo el Excel."""
    procesadas: List[FacturaVenta] = field(default_factory=list)
    mixtas: List[FacturaVenta] = field(default_factory=list)
    sin_sucursal: List[FacturaVenta] = field(default_factory=list)
    errores: List[dict] = field(default_factory=list)
    plano_df: Optional[pd.DataFrame] = None

    def resumen(self) -> dict:
        total_base = sum(f.base_calc for f in self.procesadas)
        total_inc = sum(f.inc for f in self.procesadas)
        total_propina = sum(f.propina for f in self.procesadas)
        total_facturado = sum(f.total for f in self.procesadas)
        # Por sucursal
        por_suc = {}
        for f in self.procesadas:
            key = f.nombre_sucursal or "Sin sucursal"
            if key not in por_suc:
                por_suc[key] = {"facs": 0, "base": 0, "inc": 0, "propina": 0, "total": 0}
            por_suc[key]["facs"] += 1
            por_suc[key]["base"] += f.base_calc
            por_suc[key]["inc"] += f.inc
            por_suc[key]["propina"] += f.propina
            por_suc[key]["total"] += f.total
        return {
            "facs_procesadas": len(self.procesadas),
            "facs_mixtas": len(self.mixtas),
            "facs_sin_sucursal": len(self.sin_sucursal),
            "total_base": total_base,
            "total_inc": total_inc,
            "total_propina": total_propina,
            "total_facturado": total_facturado,
            "por_sucursal": por_suc,
        }


# ─── Helpers ─────────────────────────────────────────────────

def _extraer_prefijo(folio: str, prefijo_col: str) -> str:
    """
    Si el Excel trae columna Prefijo separada, usarla.
    Si no, extraer de Folio.
    """
    if prefijo_col and str(prefijo_col).strip():
        return str(prefijo_col).strip().upper()
    m = re.match(r"^([A-Z_]+)", str(folio).upper().strip())
    return m.group(1) if m else ""


def _f(v) -> float:
    """Convierte a float, manejando NaN."""
    try:
        f = float(v)
        if pd.isna(f):
            return 0.0
        return f
    except (ValueError, TypeError):
        return 0.0


def _clasificar_tarifa(inc: float, iva: float, total: float, otros: float, ret: float) -> str:
    """
    Deduce la tarifa única de la factura.
    Devuelve: 'INC8%' / 'EXENTA' / '5%' / '19%' / 'MIXTA'
    """
    # Caso 1: exenta (sin IVA ni INC)
    if abs(iva) < 0.01 and abs(inc) < 0.01:
        return "EXENTA"

    # Caso 2: INC puro (sin IVA)
    if abs(inc) > 0.01 and abs(iva) < 0.01:
        base = inc / TARIFA_INC_POS
        calc = base + iva + inc + otros + ret
        diff = total - calc
        # Tolerar propina hasta 15% sobre la base
        if -TOLERANCIA <= diff <= base * 0.15:
            return "INC8%"
        return "MIXTA"

    # Caso 3: IVA puro (sin INC)
    if abs(iva) > 0.01 and abs(inc) < 0.01:
        for tarifa in [0.19, 0.05]:
            base = iva / tarifa
            calc = base + iva + inc + otros + ret
            diff = total - calc
            if -TOLERANCIA <= diff <= base * 0.15:
                return f"{int(tarifa*100)}%"
        return "MIXTA"

    # Caso 4: IVA + INC = MIXTA
    return "MIXTA"


# ─── Procesamiento principal ─────────────────────────────────

def procesar_ventas_excel(
    df_excel: pd.DataFrame,
    mapeo_sucursales: Dict[str, dict],
) -> ResultadoVentas:
    """
    Procesa el DataFrame del Excel del Token DIAN y genera el plano contable
    de ventas POS.

    Args:
        df_excel: DataFrame YA filtrado por mes y grupo='Emitido', viene
                  del lector_excel_token (con columnas snake_case).
        mapeo_sucursales: dict de prefijo→{cc, nombre, cuenta_caja, cta_base_v,
                          cta_ico, comprobante, tipo}. Si una sucursal no tiene
                          mapeo, la factura va a sin_sucursal.

    Returns:
        ResultadoVentas con .procesadas, .mixtas, .sin_sucursal y .plano_df.
    """
    resultado = ResultadoVentas()

    # Solo trabajamos con tipos que cuentan como venta POS contable
    # (Factura electrónica + DSE). Las NCs se manejan aparte.
    TIPOS_VENTA = {"Factura electrónica", "Documento equivalente POS"}

    # Convertir columnas numéricas con tolerancia
    cols_num_extra = ["IVA", "ICA", "IC", "INC", "Timbre", "INC Bolsas",
                      "IN Carbono", "IN Combustibles", "IC Datos", "ICL",
                      "INPP", "IBUA", "ICUI", "Rete IVA", "Rete Renta", "Rete ICA"]
    df = df_excel.copy()
    for c in cols_num_extra:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
        else:
            df[c] = 0.0

    OTROS = ["ICA", "IC", "Timbre", "INC Bolsas", "IN Carbono", "IN Combustibles",
             "IC Datos", "ICL", "INPP", "IBUA", "ICUI"]

    filas_plano = []

    for _, row in df.iterrows():
        tipo = row.get("tipo_documento", "")
        if tipo not in TIPOS_VENTA:
            continue

        cufe = str(row.get("cufe", "")).strip()
        folio = str(row.get("folio", "")).strip()
        prefijo_col = str(row.get("prefijo", "")).strip()
        prefijo = _extraer_prefijo(folio, prefijo_col)

        inc = _f(row["INC"])
        iva = _f(row["IVA"])
        total = _f(row.get("total", 0))
        otros = sum(_f(row[c]) for c in OTROS)
        ret = _f(row["Rete IVA"]) + _f(row["Rete Renta"]) + _f(row["Rete ICA"])

        tarifa = _clasificar_tarifa(inc, iva, total, otros, ret)

        # Fecha
        fecha_em = row.get("fecha_emision")
        if pd.isna(fecha_em) or fecha_em is None:
            fecha = date.today()
        else:
            try:
                fecha = fecha_em.date() if hasattr(fecha_em, "date") else fecha_em
            except Exception:
                fecha = date.today()

        # Cálculos contables (solo si NO es MIXTA)
        if tarifa == "MIXTA":
            base_calc = 0
            propina = 0
        elif tarifa == "INC8%":
            base_calc = inc / TARIFA_INC_POS
            propina = total - base_calc - inc - otros - ret
        elif tarifa == "EXENTA":
            base_calc = total - inc - iva - otros - ret
            propina = 0
        elif tarifa.endswith("%"):  # 5%, 19%
            tarifa_decimal = float(tarifa.rstrip("%")) / 100
            base_calc = iva / tarifa_decimal
            propina = total - base_calc - iva - inc - otros - ret
        else:
            base_calc = 0
            propina = 0

        # Buscar sucursal por prefijo
        sucursal_info = mapeo_sucursales.get(prefijo, {})

        fac = FacturaVenta(
            cufe=cufe, folio=folio, prefijo=prefijo,
            fecha=fecha, total=total, inc=inc, iva=iva,
            base_calc=base_calc, propina=propina, tarifa=tarifa,
            cc=sucursal_info.get("cc"),
            cuenta_caja=sucursal_info.get("cuenta_caja"),
            cta_base_v=sucursal_info.get("cta_base_v"),
            cta_ico=sucursal_info.get("cta_ico"),
            comprobante=sucursal_info.get("comprobante"),
            nombre_sucursal=sucursal_info.get("nombre"),
        )

        # Clasificar destino
        if tarifa == "MIXTA":
            resultado.mixtas.append(fac)
            continue

        if not sucursal_info:
            resultado.sin_sucursal.append(fac)
            continue

        # Si no tiene cuentas configuradas, va a sin_sucursal (problema de datos)
        if not (fac.cuenta_caja and fac.cta_base_v and fac.cta_ico):
            resultado.sin_sucursal.append(fac)
            continue

        resultado.procesadas.append(fac)

        # Generar 3 líneas del asiento
        comp = fac.comprobante or "497"
        fecha_str = fac.fecha.strftime("%m/%d/%Y")
        detalle = f"{DETALLE_PREFIJO}{fac.nombre_sucursal or prefijo}"

        # Total contable = base + INC + IVA + otros (omite propina)
        total_contable = round(fac.base_calc + inc + iva + otros, 0)

        # Db Caja
        filas_plano.append({
            "CUENTA":         fac.cuenta_caja,
            "COMPROBANTE":    comp,
            "FECHA":          fecha_str,
            "DOCUMENTO":      f"{prefijo}{folio}",
            "DOC REFERENCIA": "",
            "NIT":            NIT_GENERICO_POS,
            "DETALLE":        detalle,
            "TR":             TR_DEBITO,
            "VALOR":          total_contable,
            "BASE":           "",
            "CENTRO DE COSTO": fac.cc,
        })
        # Cr Base V
        filas_plano.append({
            "CUENTA":         fac.cta_base_v,
            "COMPROBANTE":    comp,
            "FECHA":          fecha_str,
            "DOCUMENTO":      f"{prefijo}{folio}",
            "DOC REFERENCIA": "",
            "NIT":            NIT_GENERICO_POS,
            "DETALLE":        detalle,
            "TR":             TR_CREDITO,
            "VALOR":          round(fac.base_calc, 0),
            "BASE":           "",
            "CENTRO DE COSTO": fac.cc,
        })
        # Cr ICO (INC 8%)
        if inc > 0:
            filas_plano.append({
                "CUENTA":         fac.cta_ico,
                "COMPROBANTE":    comp,
                "FECHA":          fecha_str,
                "DOCUMENTO":      f"{prefijo}{folio}",
                "DOC REFERENCIA": "",
                "NIT":            NIT_GENERICO_POS,
                "DETALLE":        detalle,
                "TR":             TR_CREDITO,
                "VALOR":          round(inc, 0),
                "BASE":           round(fac.base_calc, 0),
                "CENTRO DE COSTO": fac.cc,
            })
        # Cr IVA generado (para STL 19%, 5%, 16%)
        if iva > 0:
            cuenta_iva = CUENTAS_IVA_VENTAS.get(tarifa, "24080501")
            filas_plano.append({
                "CUENTA":         cuenta_iva,
                "COMPROBANTE":    comp,
                "FECHA":          fecha_str,
                "DOCUMENTO":      f"{prefijo}{folio}",
                "DOC REFERENCIA": "",
                "NIT":            NIT_GENERICO_POS,
                "DETALLE":        f"IVA GENERADO {tarifa} - {detalle}",
                "TR":             TR_CREDITO,
                "VALOR":          round(iva, 0),
                "BASE":           round(fac.base_calc, 0),
                "CENTRO DE COSTO": fac.cc,
            })
        # Cr Otros impuestos sumados (ICA, IC, Timbre, etc.)
        if otros > 0.5:
            filas_plano.append({
                "CUENTA":         "24959501",   # cuenta genérica otros impuestos
                "COMPROBANTE":    comp,
                "FECHA":          fecha_str,
                "DOCUMENTO":      f"{prefijo}{folio}",
                "DOC REFERENCIA": "",
                "NIT":            NIT_GENERICO_POS,
                "DETALLE":        f"OTROS IMPUESTOS - {detalle}",
                "TR":             TR_CREDITO,
                "VALOR":          round(otros, 0),
                "BASE":           round(fac.base_calc, 0),
                "CENTRO DE COSTO": fac.cc,
            })

    if filas_plano:
        resultado.plano_df = pd.DataFrame(filas_plano, columns=COLUMNAS_PLANO)
    else:
        resultado.plano_df = pd.DataFrame(columns=COLUMNAS_PLANO)

    return resultado


def cargar_mapeo_desde_json(ruta: str) -> Dict[str, dict]:
    """
    Lee mapeo_prefijos_token.json y devuelve dict prefijo→info_sucursal.

    Filtra SOLO prefijos de tipo 'venta' (no NCs). Para NCs usar la versión
    cargar_mapeo_ncs() o el mapeo completo via cargar_mapeo_completo().
    """
    import json as _json
    with open(ruta) as f:
        data = _json.load(f)
    out = {}
    for item in data.get("mapeos", []):
        if item.get("tipo") != "venta":
            continue
        out[item["prefijo"].upper()] = {
            "cc": item["cc"],
            "nombre": item["sede"],
            "cuenta_caja": item["cuenta_caja"],
            "cta_base_v": item["cta_base_v"],
            "cta_ico": item["cta_ico"],
            "comprobante": item["comprobante"],
            "clase": item.get("clase", ""),
            "tipo": "venta",
        }
    return out


def cargar_mapeo_completo(ruta: str) -> Dict[str, dict]:
    """Carga el mapeo completo (ventas + NCs) — útil para el clasificador y reporte de auditoría."""
    import json as _json
    with open(ruta) as f:
        data = _json.load(f)
    out = {}
    for item in data.get("mapeos", []):
        out[item["prefijo"].upper()] = {
            "cc": item["cc"],
            "nombre": item["sede"],
            "cuenta_caja": item["cuenta_caja"],
            "cta_base_v": item["cta_base_v"],
            "cta_ico": item["cta_ico"],
            "comprobante": item["comprobante"],
            "clase": item.get("clase", ""),
            "tipo": item["tipo"],
        }
    return out


def dataframe_a_plano_tsv(df: pd.DataFrame) -> str:
    """
    Convierte el DataFrame del plano a TSV con la columna de cabecera.
    Formato Siigo: tab-separado, sin índice, encabezados.
    """
    if df is None or len(df) == 0:
        return ""
    return df[COLUMNAS_PLANO].to_csv(sep="\t", index=False)
