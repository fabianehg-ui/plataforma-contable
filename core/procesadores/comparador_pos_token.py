"""
core/procesadores/comparador_pos_token.py

Compara el plano contable del POS (procesado con procesar_pos) contra
el agregado del Token DIAN (parsear_token_dian) por (fecha, sucursal).

Devuelve un dataframe con todas las celdas (fecha × sucursal):
  - SOLO en POS  → la sucursal vendió ese día pero la factura no llegó
                    al Token (puede ser que esté pendiente de envío DIAN).
  - SOLO en TOKEN → hay facturas en DIAN pero no hay ventas POS ese día
                    (puede ser que falte el reporte POS).
  - COINCIDE     → ambas fuentes reportan ~lo mismo (dentro de tolerancia).
  - DIFIERE      → ambas reportan pero los montos no cuadran.

Funciones públicas:
    comparar_pos_token(df_plano_pos, df_token_agregado,
                       tolerancia_pesos=100)
        → DataFrame con columnas:
            fecha, sucursal_cc, sucursal_nombre, prefijo,
            total_pos, total_token, diferencia, pct_dif,
            estado, fuente_recomendada, fuente_elegida
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from core.procesadores.parser_token_dian import agregar_plano_pos_por_fecha_cc


ESTADO_COINCIDE = "coincide"
ESTADO_DIFIERE = "difiere"
ESTADO_SOLO_POS = "solo_pos"
ESTADO_SOLO_TOKEN = "solo_token"


def comparar_pos_token(
    df_plano_pos: pd.DataFrame,
    df_token_agregado: pd.DataFrame,
    tolerancia_pesos: int = 100,
) -> pd.DataFrame:
    """
    Cruza el plano POS y el agregado del Token por (fecha, sucursal_cc)
    e identifica las diferencias.

    Args:
        df_plano_pos: DataFrame del plano contable POS (procesar_pos).
        df_token_agregado: DataFrame agregado del Token
            (parsear_token_dian → 'agregado_fecha_prefijo').
        tolerancia_pesos: diferencia absoluta tolerada para considerar
            que ambos cuadran (default $100).

    Returns:
        DataFrame con todas las celdas (fecha × sucursal) y su estado.
    """
    # 1. Reducir el POS a (fecha, sucursal_cc, total_pos)
    pos_agg = agregar_plano_pos_por_fecha_cc(df_plano_pos)

    # 2. Preparar el Token (renombrar columnas para el merge)
    tok = df_token_agregado.copy() if df_token_agregado is not None else pd.DataFrame()
    if len(tok) > 0:
        tok = tok.rename(columns={
            "total_bruto": "total_token",
        })
        # Convertir fecha a date Python si vino como string
        if not pd.api.types.is_datetime64_any_dtype(tok["fecha"]):
            tok["fecha"] = pd.to_datetime(tok["fecha"], errors="coerce").dt.date

    # 3. Outer join por (fecha, sucursal_cc)
    if len(pos_agg) == 0 and len(tok) == 0:
        return pd.DataFrame(columns=[
            "fecha", "sucursal_cc", "sucursal_nombre", "prefijo",
            "total_pos", "total_token", "diferencia", "pct_dif",
            "estado", "fuente_recomendada", "fuente_elegida",
            "docs_token", "estado_desglose", "propina_estimada",
        ])

    if len(tok) == 0:
        # Solo POS, no hay token cargado
        merged = pos_agg.copy()
        merged["total_token"] = 0.0
        merged["prefijo"] = ""
        merged["sucursal_nombre"] = ""
        merged["docs_token"] = 0
        merged["estado_desglose"] = ""
        merged["propina_estimada"] = 0.0
    elif len(pos_agg) == 0:
        # Solo Token, no hay POS cargado
        merged = tok.copy()
        merged["total_pos"] = 0.0
    else:
        merged = pd.merge(
            pos_agg,
            tok[[
                "fecha", "sucursal_cc", "prefijo", "sucursal_nombre",
                "docs", "total_token", "estado_desglose", "propina_estimada",
            ]],
            on=["fecha", "sucursal_cc"],
            how="outer",
        )
        merged = merged.rename(columns={"docs": "docs_token"})

    # 4. Rellenar nulos para evitar problemas aritméticos
    merged["total_pos"] = pd.to_numeric(merged.get("total_pos", 0), errors="coerce").fillna(0)
    merged["total_token"] = pd.to_numeric(merged.get("total_token", 0), errors="coerce").fillna(0)

    for col in ["prefijo", "sucursal_nombre", "estado_desglose"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna("").astype(str)
        else:
            merged[col] = ""

    for col in ["docs_token", "propina_estimada"]:
        if col in merged.columns:
            merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0)
        else:
            merged[col] = 0

    # 5. Calcular diferencia y estado
    merged["diferencia"] = merged["total_pos"] - merged["total_token"]
    merged["pct_dif"] = merged.apply(
        lambda r: (
            abs(r["diferencia"]) / r["total_token"] * 100
            if r["total_token"] > 0 else
            (100.0 if r["total_pos"] > 0 else 0.0)
        ),
        axis=1,
    )

    def _estado(r):
        if r["total_pos"] == 0 and r["total_token"] == 0:
            return ESTADO_COINCIDE  # ambos cero (no debería ocurrir tras filtros)
        if r["total_pos"] == 0:
            return ESTADO_SOLO_TOKEN
        if r["total_token"] == 0:
            return ESTADO_SOLO_POS
        if abs(r["diferencia"]) <= tolerancia_pesos:
            return ESTADO_COINCIDE
        return ESTADO_DIFIERE

    merged["estado"] = merged.apply(_estado, axis=1)

    def _recomendada(r):
        # Heurística de recomendación (el contador puede ignorarla):
        if r["estado"] == ESTADO_COINCIDE:
            return "pos"  # cualquiera sirve, elegimos POS por consistencia
        if r["estado"] == ESTADO_SOLO_POS:
            return "pos"
        if r["estado"] == ESTADO_SOLO_TOKEN:
            return "token"
        # Difiere: el Token (DIAN) suele ser más confiable como verdad oficial,
        # pero el POS refleja la operación real. Se recomienda Token por defecto.
        return "token"

    merged["fuente_recomendada"] = merged.apply(_recomendada, axis=1)
    # La elección inicial es la recomendada; el contador puede cambiarla
    merged["fuente_elegida"] = merged["fuente_recomendada"]

    # 6. Ordenar y reordenar columnas
    columnas_final = [
        "fecha", "sucursal_cc", "sucursal_nombre", "prefijo",
        "total_pos", "total_token", "diferencia", "pct_dif",
        "docs_token", "estado_desglose", "propina_estimada",
        "estado", "fuente_recomendada", "fuente_elegida",
    ]
    # Asegurar que existan todas las columnas
    for c in columnas_final:
        if c not in merged.columns:
            merged[c] = ""

    merged = merged[columnas_final].sort_values(
        ["fecha", "sucursal_cc"],
    ).reset_index(drop=True)

    return merged


def resumen_comparacion(df_comparado: pd.DataFrame) -> dict:
    """
    Devuelve un dict con el resumen de la comparación, útil para mostrar
    métricas en la UI.
    """
    if df_comparado is None or len(df_comparado) == 0:
        return {
            "total_celdas":  0,
            "coincide":      0,
            "difiere":       0,
            "solo_pos":      0,
            "solo_token":    0,
            "total_pos":     0,
            "total_token":   0,
            "diferencia":    0,
        }

    counts = df_comparado["estado"].value_counts().to_dict()
    return {
        "total_celdas":  len(df_comparado),
        "coincide":      counts.get(ESTADO_COINCIDE, 0),
        "difiere":       counts.get(ESTADO_DIFIERE, 0),
        "solo_pos":      counts.get(ESTADO_SOLO_POS, 0),
        "solo_token":    counts.get(ESTADO_SOLO_TOKEN, 0),
        "total_pos":     int(df_comparado["total_pos"].sum()),
        "total_token":   int(df_comparado["total_token"].sum()),
        "diferencia":    int(df_comparado["total_pos"].sum() - df_comparado["total_token"].sum()),
    }


def aplicar_elecciones_al_plano(
    df_plano_pos: pd.DataFrame,
    df_comparado: pd.DataFrame,
    sucursales: list,
) -> pd.DataFrame:
    """
    Devuelve un plano contable AJUSTADO según las elecciones del contador.

    Lógica:
      - Donde fuente_elegida == 'pos' → conserva las filas originales del POS.
      - Donde fuente_elegida == 'token' → reemplaza las filas del POS de
        ese (fecha, CC) con líneas reconstruidas a partir del total Token.
      - Donde es solo_token y fuente_elegida == 'token' → agrega líneas
        nuevas a partir del Token.
      - Donde es solo_pos y fuente_elegida == 'pos' → conserva como está.

    Args:
        df_plano_pos: plano original de procesar_pos.
        df_comparado: tabla de comparación con la columna fuente_elegida.
        sucursales: lista de Sucursal (con cta_caja, cta_base_v, cta_ico).

    Returns:
        DataFrame con el plano final (mismas columnas que df_plano_pos).
    """
    from datetime import date, datetime

    if df_plano_pos is None:
        df_plano_pos = pd.DataFrame()

    # Indexar sucursales por CC
    suc_por_cc = {s.cc: s for s in sucursales}

    # 1) Identificar celdas (fecha, CC) donde se eligió Token
    if len(df_comparado) == 0:
        return df_plano_pos.copy()

    df_cmp = df_comparado.copy()
    df_cmp["_fecha"] = pd.to_datetime(df_cmp["fecha"], errors="coerce").dt.date

    celdas_token = df_cmp[df_cmp["fuente_elegida"] == "token"].copy()
    celdas_pos = df_cmp[df_cmp["fuente_elegida"] == "pos"].copy()

    # 2) Filtrar el plano POS para excluir las celdas donde se eligió Token
    if len(df_plano_pos) > 0:
        df_pos = df_plano_pos.copy()

        def _to_date(s):
            try:
                return datetime.strptime(str(s).strip(), "%m/%d/%Y").date()
            except Exception:
                return None

        df_pos["_fecha_d"] = df_pos["FECHA"].apply(_to_date)
        df_pos["_cc"] = df_pos["CENTRO DE COSTO"].astype(str)

        celdas_excluir = set(
            (r["_fecha"], str(r["sucursal_cc"]))
            for _, r in celdas_token.iterrows()
            if r["_fecha"] is not None and pd.notna(r["sucursal_cc"])
        )

        mask_excluir = df_pos.apply(
            lambda r: (r["_fecha_d"], r["_cc"]) in celdas_excluir,
            axis=1,
        )
        df_pos_conservado = df_pos[~mask_excluir].drop(columns=["_fecha_d", "_cc"])
    else:
        df_pos_conservado = df_plano_pos.copy()

    # 3) Construir filas nuevas a partir del Token para las celdas elegidas
    filas_token = []
    for _, r in celdas_token.iterrows():
        cc = str(r["sucursal_cc"])
        suc = suc_por_cc.get(cc)
        if not suc:
            continue
        if r["_fecha"] is None or pd.isna(r["total_token"]):
            continue
        total_bruto = float(r["total_token"])
        if total_bruto <= 0:
            continue

        fecha_str = r["_fecha"].strftime("%m/%d/%Y")
        # Reconstruir desglose: base + INC (igual que el desglose teórico)
        base = round(total_bruto / 1.08)
        inc = round(base * 0.08)
        # Ajuste para que cuadre exacto:
        suma = base + inc
        ajuste = int(round(total_bruto)) - suma
        # Si hay ajuste residual, se suma a base (manejo de propina/redondeo)
        base += ajuste

        documento = f"POS{cc[-3:]}{r['_fecha'].strftime('%d')}"
        detalle = f"VENTAS POS TOKEN {suc.nombre_reporte}"
        nit_generico = "222222222"

        # Linea Db (caja): total
        filas_token.append({
            "CUENTA":            suc.cuenta_caja,
            "COMPROBANTE":       suc.comprobante,
            "FECHA":             fecha_str,
            "DOCUMENTO":         documento,
            "DOC REFERENCIA":    documento,
            "NIT":               nit_generico,
            "DETALLE":           detalle,
            "TR":                "1",
            "VALOR":             int(round(total_bruto)),
            "BASE":              0,
            "CENTRO DE COSTO":   cc,
        })
        # Linea Cr (base ventas)
        filas_token.append({
            "CUENTA":            suc.cta_base_v,
            "COMPROBANTE":       suc.comprobante,
            "FECHA":             fecha_str,
            "DOCUMENTO":         documento,
            "DOC REFERENCIA":    documento,
            "NIT":               nit_generico,
            "DETALLE":           detalle,
            "TR":                "2",
            "VALOR":             int(base),
            "BASE":              int(base),
            "CENTRO DE COSTO":   cc,
        })
        # Linea Cr (INC)
        if inc > 0:
            filas_token.append({
                "CUENTA":          suc.cta_ico,
                "COMPROBANTE":     suc.comprobante,
                "FECHA":           fecha_str,
                "DOCUMENTO":       documento,
                "DOC REFERENCIA":  documento,
                "NIT":             nit_generico,
                "DETALLE":         detalle,
                "TR":              "2",
                "VALOR":           int(inc),
                "BASE":            int(base),
                "CENTRO DE COSTO": cc,
            })

    df_token_filas = pd.DataFrame(filas_token, columns=df_plano_pos.columns if len(df_plano_pos) else [
        "CUENTA","COMPROBANTE","FECHA","DOCUMENTO","DOC REFERENCIA","NIT",
        "DETALLE","TR","VALOR","BASE","CENTRO DE COSTO",
    ])

    # 4) Concatenar y devolver
    if len(df_pos_conservado) > 0 and len(df_token_filas) > 0:
        df_final = pd.concat([df_pos_conservado, df_token_filas], ignore_index=True)
    elif len(df_pos_conservado) > 0:
        df_final = df_pos_conservado
    else:
        df_final = df_token_filas

    # Ordenar por fecha y CC para presentación
    if len(df_final) > 0:
        df_final = df_final.sort_values(
            ["FECHA", "CENTRO DE COSTO", "TR"]
        ).reset_index(drop=True)

    return df_final
