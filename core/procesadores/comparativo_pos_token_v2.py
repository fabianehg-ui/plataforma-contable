"""
core/procesadores/comparativo_pos_token_v2.py

Comparativo de auditoría:
  base_token_neta = base_token (FE emitidas) − base_NC_token (notas crédito)
  Indicador      = base_token_neta / base_POS

Sirve para validar la efectividad del paquete de facturación electrónica
DIAN: si el sistema POS dice $X y la facturación electrónica emitió $Y,
¿cuánto se está logrando facturar de lo que pasó por caja?

EXPONE:
    construir_comparativo(df_token, base_pos_por_sucursal, mapeo_completo) -> DataFrame
"""
from __future__ import annotations

from typing import Dict

import pandas as pd

from core.procesadores import procesador_ventas_excel_token as pve


def construir_comparativo(
    df_token: pd.DataFrame,
    base_pos_por_sucursal: Dict[str, float],
    mapeo_completo: Dict[str, dict],
) -> pd.DataFrame:
    """
    Construye el reporte comparativo.

    Args:
        df_token: DataFrame del lector_excel_token, filtrado por rango y emitidos.
                  Contiene tanto facturas (FE) como notas crédito (NC).
        base_pos_por_sucursal: dict cc → base POS del mes (sale del procesador POS).
        mapeo_completo: dict prefijo → info sucursal (ventas + NCs).

    Returns:
        DataFrame con columnas:
          Sucursal, Clase, CC, Base POS, Base Token FE, Base NC Token,
          Token Neto, Diferencia, Efectividad %
        Más filas de subtotales por Clase y fila Gran Total al final.
    """
    # Para cada factura/NC, obtener cc + clase desde el mapeo
    df = df_token.copy()
    cols_otros = ["ICA", "IC", "Timbre", "INC Bolsas", "IN Carbono", "IN Combustibles",
                  "IC Datos", "ICL", "INPP", "IBUA", "ICUI"]
    cols_ret = ["Rete IVA", "Rete Renta", "Rete ICA"]
    for c in cols_otros + cols_ret + ["IVA", "INC"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
        else:
            df[c] = 0
    df["_otros"] = df[cols_otros].sum(axis=1)
    df["_ret"] = df[cols_ret].sum(axis=1)

    # Asignar cc / clase / es_nc por prefijo
    info_por_fila = []
    for _, row in df.iterrows():
        prefijo = str(row.get("prefijo", "")).upper().strip()
        m = mapeo_completo.get(prefijo, {})
        info_por_fila.append({
            "cc": m.get("cc", ""),
            "sede": m.get("nombre", ""),
            "clase": m.get("clase", ""),
            "es_nc": m.get("tipo") == "nc",
            "tipo_doc": row.get("tipo_documento", ""),
        })
    df_info = pd.DataFrame(info_por_fila)
    df = pd.concat([df.reset_index(drop=True), df_info], axis=1)

    # Calcular base contable por fila (omitiendo propina)
    # Para INC8% puro: base = INC / 0.08
    # Para IVA 19%/5%: base = IVA / tarifa
    # Para exenta: base = Total - IVA - INC - otros - ret
    def calcular_base(r):
        iva = r["IVA"]; inc = r["INC"]; otros = r["_otros"]; ret = r["_ret"]
        total = float(r.get("total", 0) or 0)
        if abs(iva) < 0.01 and abs(inc) < 0.01:
            return total - otros - ret
        if abs(inc) > 0.01 and abs(iva) < 0.01:
            return inc / 0.08
        if abs(iva) > 0.01 and abs(inc) < 0.01:
            for tarifa in [0.19, 0.05]:
                base = iva / tarifa
                if -5 <= total - base - iva - otros - ret <= base * 0.15:
                    return base
        return total - iva - inc - otros - ret
    df["base_calc"] = df.apply(calcular_base, axis=1)

    # Agrupar por sucursal: base FE y base NC por separado
    df_validos = df[df["cc"] != ""]
    df_fe = df_validos[df_validos["tipo_doc"] == "Factura electrónica"]
    df_nc = df_validos[df_validos["tipo_doc"] == "Nota de crédito electrónica"]

    base_fe = df_fe.groupby("cc")["base_calc"].sum().to_dict()
    base_nc = df_nc.groupby("cc")["base_calc"].sum().to_dict()
    sedes = df_validos.groupby("cc").agg(
        sede=("sede", "first"),
        clase=("clase", "first"),
    ).to_dict("index")

    # Construir filas del reporte
    todos_cc = set(base_fe) | set(base_nc) | set(base_pos_por_sucursal.keys())
    filas = []
    for cc in sorted(todos_cc):
        info = sedes.get(cc, {})
        sede = info.get("sede", f"CC {cc}")
        clase = info.get("clase", "")
        b_pos = float(base_pos_por_sucursal.get(cc, 0))
        b_fe = float(base_fe.get(cc, 0))
        b_nc = float(base_nc.get(cc, 0))
        b_token_neto = b_fe - b_nc
        diferencia = b_token_neto - b_pos
        efectividad = (b_token_neto / b_pos * 100) if b_pos > 0 else (0 if b_token_neto == 0 else None)
        filas.append({
            "CC": cc,
            "Sucursal": sede,
            "Clase": clase,
            "Base POS": round(b_pos, 0),
            "Base Token FE": round(b_fe, 0),
            "Base NC Token": round(b_nc, 0),
            "Token Neto": round(b_token_neto, 0),
            "Diferencia": round(diferencia, 0),
            "Efectividad %": round(efectividad, 2) if efectividad is not None else None,
        })

    df_rep = pd.DataFrame(filas)
    if len(df_rep) == 0:
        return df_rep

    # Ordenar por clase + sede
    df_rep = df_rep.sort_values(["Clase", "Sucursal"]).reset_index(drop=True)

    # Agregar subtotales por clase y gran total
    filas_finales = []
    for clase in df_rep["Clase"].unique():
        sub = df_rep[df_rep["Clase"] == clase]
        for _, r in sub.iterrows():
            filas_finales.append(r.to_dict())
        # Subtotal por clase
        b_pos_sub = sub["Base POS"].sum()
        b_tok_sub = sub["Token Neto"].sum()
        ef_sub = (b_tok_sub / b_pos_sub * 100) if b_pos_sub > 0 else None
        filas_finales.append({
            "CC": "",
            "Sucursal": f"── SUBTOTAL {clase} ──",
            "Clase": clase,
            "Base POS": b_pos_sub,
            "Base Token FE": sub["Base Token FE"].sum(),
            "Base NC Token": sub["Base NC Token"].sum(),
            "Token Neto": b_tok_sub,
            "Diferencia": sub["Diferencia"].sum(),
            "Efectividad %": round(ef_sub, 2) if ef_sub is not None else None,
        })

    # Gran total
    g_pos = df_rep["Base POS"].sum()
    g_tok = df_rep["Token Neto"].sum()
    g_ef = (g_tok / g_pos * 100) if g_pos > 0 else None
    filas_finales.append({
        "CC": "",
        "Sucursal": "═══ GRAN TOTAL ═══",
        "Clase": "",
        "Base POS": g_pos,
        "Base Token FE": df_rep["Base Token FE"].sum(),
        "Base NC Token": df_rep["Base NC Token"].sum(),
        "Token Neto": g_tok,
        "Diferencia": df_rep["Diferencia"].sum(),
        "Efectividad %": round(g_ef, 2) if g_ef is not None else None,
    })

    return pd.DataFrame(filas_finales)


def extraer_base_pos_por_sucursal(plano_pos_df: pd.DataFrame) -> Dict[str, float]:
    """
    Del plano POS antiguo extrae la base por CC (centro de costo).

    El plano POS tiene la columna 'CC' / 'CENTRO DE COSTO' y la BASE va
    en filas de crédito de la cuenta cta_base_v.

    Estrategia simple: sumar los VALOR de las filas TR=2 (créditos) donde
    la cuenta corresponde a base (no a INC/ICO).
    """
    if plano_pos_df is None or len(plano_pos_df) == 0:
        return {}
    df = plano_pos_df.copy()
    df["VALOR"] = pd.to_numeric(df["VALOR"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)

    # Detectar columna CC (puede ser "CC" o "CENTRO DE COSTO")
    cc_col = None
    for c in df.columns:
        if c.upper() in ("CC", "CENTRO DE COSTO"):
            cc_col = c
            break
    if not cc_col:
        return {}

    # Detectar columna cuenta
    cuenta_col = None
    for c in df.columns:
        if c.upper() == "CUENTA":
            cuenta_col = c
            break
    if not cuenta_col:
        return {}

    # Tomar solo créditos de cuentas que NO son la de INC (24800505 en JIPER)
    df = df[df["TR"].astype(str) == "2"]
    df = df[~df[cuenta_col].astype(str).str.startswith("248")]
    df = df[~df[cuenta_col].astype(str).str.startswith("249")]  # otros impuestos

    base_por_cc = df.groupby(cc_col)["VALOR"].sum().to_dict()
    # Normalizar cc a string con ceros a la izquierda
    return {str(k).zfill(6): float(v) for k, v in base_por_cc.items() if k}
