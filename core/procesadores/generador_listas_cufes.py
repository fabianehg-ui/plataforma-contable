"""
core/procesadores/generador_listas_cufes.py

Genera las listas JSON de CUFEs para que la extensión Chrome descargue los
XMLs solo de los documentos que realmente necesitan procesamiento detallado.

Lógica:
  - Lista A — COMPRAS MIXTAS: facturas recibidas donde no se puede deducir
    una tarifa única (necesitan XML para discriminar líneas).
  - Lista B — VENTAS MIXTAS: lo mismo para emitidas (raro pero pasa).
  - Lista C — TODAS RECIBIDAS: opción para descargar todas las compras si
    quieres maestro completo de proveedores con direcciones.

Filosofía: la extensión Chrome NO debería bajar 37k XMLs cuando 99% se
clasifican desde el Excel. Solo bajamos los que de verdad lo necesitan.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd


def _clasificar_tarifa_basica(row, otros, ret):
    """
    Versión simplificada del clasificador (sin dependencias externas).
    Devuelve True si cuadra con tarifa pura, False si es MIXTA.
    """
    TOLERANCIA = 5
    iva = float(row.get("IVA", 0) or 0)
    inc = float(row.get("INC", 0) or 0)
    total = float(row.get("total", 0) or 0)

    # Exenta
    if abs(iva) < 0.01 and abs(inc) < 0.01:
        return True, "EXENTA"

    # IVA puro (sin INC)
    if abs(iva) > 0.01 and abs(inc) < 0.01:
        for tarifa in [0.05, 0.19, 0.16]:
            base = iva / tarifa
            calc = base + iva + inc + otros + ret
            diff = total - calc
            if -TOLERANCIA <= diff <= base * 0.15:
                return True, f"{int(tarifa*100)}%"
        return False, "MIXTA"

    # INC puro
    if abs(inc) > 0.01 and abs(iva) < 0.01:
        for tarifa_inc in [0.08, 0.16]:
            base = inc / tarifa_inc
            calc = base + iva + inc + otros + ret
            diff = total - calc
            if -TOLERANCIA <= diff <= base * 0.15:
                return True, f"INC{int(tarifa_inc*100)}%"
        return False, "MIXTA"

    # Mezcla IVA + INC
    return False, "MIXTA"


def clasificar_df_por_tarifa(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega al DataFrame las columnas 'cuadra_excel' (bool) y 'tarifa_detectada' (str).
    """
    cols_otros = ["ICA", "IC", "Timbre", "INC Bolsas", "IN Carbono", "IN Combustibles",
                  "IC Datos", "ICL", "INPP", "IBUA", "ICUI"]
    cols_ret = ["Rete IVA", "Rete Renta", "Rete ICA"]

    df = df.copy()
    for c in cols_otros + cols_ret + ["IVA", "INC"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
        else:
            df[c] = 0

    df["_otros_imp"] = df[cols_otros].sum(axis=1)
    df["_ret_total"] = df[cols_ret].sum(axis=1)

    cuadra_list, tarifa_list = [], []
    for _, row in df.iterrows():
        cuadra, tarifa = _clasificar_tarifa_basica(row, row["_otros_imp"], row["_ret_total"])
        cuadra_list.append(cuadra)
        tarifa_list.append(tarifa)
    df["cuadra_excel"] = cuadra_list
    df["tarifa_detectada"] = tarifa_list

    return df


# Tipos excluidos siempre (no van a contabilidad ni a XML)
TIPOS_NO_CONTABLES = {"Application response", "Nomina Individual"}


def generar_lista_todos_recibidos(
    df: pd.DataFrame,
    fecha_desde=None,
    fecha_hasta=None,
) -> List[dict]:
    """
    Lista TODOS los CUFEs recibidos del mes, sin filtros de tarifa.
    Útil para descargar el 100% de XMLs recibidos: FE, NC, ND, DSE, doc
    equivalentes, etc. — todo lo que entra a contabilidad por compras.

    Excluye únicamente los TIPOS_NO_CONTABLES (Application response, Nómina
    Individual) que no representan documentos contables de compra.

    Args:
        df: DataFrame de la captura DIAN/token, con columnas grupo,
            tipo_documento, cufe, fecha_emision, etc.
        fecha_desde, fecha_hasta: opcional, filtra por fecha_emision (date).

    Returns:
        Lista de dicts ordenados por fecha asc, listos para la extensión Chrome.
    """
    df_recb = df[df["grupo"].str.lower() == "recibido"].copy()
    df_recb = df_recb[~df_recb["tipo_documento"].isin(TIPOS_NO_CONTABLES)]

    if fecha_desde is not None:
        df_recb = df_recb[df_recb["fecha_emision"].dt.date >= fecha_desde]
    if fecha_hasta is not None:
        df_recb = df_recb[df_recb["fecha_emision"].dt.date <= fecha_hasta]

    df_recb = df_recb.sort_values("fecha_emision")

    out = []
    for _, row in df_recb.iterrows():
        if not row.get("cufe"):
            continue
        out.append({
            "cufe":             row["cufe"],
            "folio":            row.get("folio", ""),
            "prefijo":          row.get("prefijo", ""),
            "tipo_documento":   row["tipo_documento"],
            "fecha_emision":    row["fecha_emision"].strftime("%Y-%m-%d") if pd.notna(row["fecha_emision"]) else "",
            "nit_emisor":       row.get("nit_emisor", ""),
            "nombre_emisor":    row.get("nombre_emisor", ""),
            "nit_receptor":     row.get("nit_receptor", ""),
            "nombre_receptor":  row.get("nombre_receptor", ""),
            "total":            float(row.get("total", 0) or 0),
            "grupo":            row["grupo"],
            "razon":            "TODOS_RECIBIDOS",
        })
    return out


def generar_lista_emitidos_stl_y_dse(
    df: pd.DataFrame,
    fecha_desde=None,
    fecha_hasta=None,
) -> List[dict]:
    """
    Lista A para descarga directa desde DIAN:
    EMITIDOS por la empresa donde prefijo == "STL" (mayoristas) MÁS
    todos los DSE emitidos (tipo "Documento Soporte Electrónico", o
    cualquier nombre que contenga "Soporte" — el Excel del Token a veces
    nombra esto distinto).

    No incluye otros prefijos emitidos (MED, MVI, IND, OVI, etc.) porque
    esos se resuelven 100% desde el Excel.

    Args:
        df: DataFrame del Excel del Token normalizado.
        fecha_desde, fecha_hasta: filtros opcionales (datetime.date).

    Returns:
        Lista de dicts ordenados por fecha asc, con cufe, folio, prefijo, etc.
    """
    df_em = df[df["grupo"].str.lower() == "emitido"].copy()
    df_em = df_em[~df_em["tipo_documento"].isin(TIPOS_NO_CONTABLES)]

    if fecha_desde is not None:
        df_em = df_em[df_em["fecha_emision"].dt.date >= fecha_desde]
    if fecha_hasta is not None:
        df_em = df_em[df_em["fecha_emision"].dt.date <= fecha_hasta]

    # Filtro: prefijo STL O tipo documento soporte (DSE)
    es_stl = df_em["prefijo"].astype(str).str.upper().str.startswith("STL")
    es_dse = df_em["tipo_documento"].astype(str).str.contains(
        "Soporte", case=False, na=False
    )
    df_filt = df_em[es_stl | es_dse]

    df_filt = df_filt.sort_values("fecha_emision")

    out = []
    for _, row in df_filt.iterrows():
        if not row.get("cufe"):
            continue
        es_stl_row = str(row.get("prefijo", "")).upper().startswith("STL")
        razon = "STL_EMITIDO" if es_stl_row else "DSE_EMITIDO"
        out.append({
            "cufe":             row["cufe"],
            "folio":            row.get("folio", ""),
            "prefijo":          row.get("prefijo", ""),
            "tipo_documento":   row["tipo_documento"],
            "fecha_emision":    row["fecha_emision"].strftime("%Y-%m-%d") if pd.notna(row["fecha_emision"]) else "",
            "nit_emisor":       row.get("nit_emisor", ""),
            "nombre_emisor":    row.get("nombre_emisor", ""),
            "nit_receptor":     row.get("nit_receptor", ""),
            "nombre_receptor":  row.get("nombre_receptor", ""),
            "total":            float(row.get("total", 0) or 0),
            "grupo":            row["grupo"],
            "razon":            razon,
        })
    return out


def generar_lista_compras_mixtas(df: pd.DataFrame) -> List[dict]:
    """
    Genera lista de CUFEs de COMPRAS RECIBIDAS MIXTAS.
    Estas son las únicas compras que necesitan descargar XML real.
    """
    df_recb = df[df["grupo"].str.lower() == "recibido"].copy()
    df_recb = df_recb[~df_recb["tipo_documento"].isin(TIPOS_NO_CONTABLES)]
    df_clasif = clasificar_df_por_tarifa(df_recb)
    mixtas = df_clasif[df_clasif["tarifa_detectada"] == "MIXTA"]

    out = []
    for _, row in mixtas.iterrows():
        if not row["cufe"]:
            continue
        out.append({
            "cufe":             row["cufe"],
            "folio":            row["folio"],
            "prefijo":          row["prefijo"],
            "tipo_documento":   row["tipo_documento"],
            "fecha_emision":    row["fecha_emision"].strftime("%Y-%m-%d") if pd.notna(row["fecha_emision"]) else "",
            "nit_emisor":       row["nit_emisor"],
            "nombre_emisor":    row["nombre_emisor"],
            "nit_receptor":     row["nit_receptor"],
            "nombre_receptor":  row["nombre_receptor"],
            "total":            float(row["total"]),
            "grupo":            row["grupo"],
            "razon":            "MIXTA",
        })
    return out


def generar_lista_ventas_mixtas(df: pd.DataFrame) -> List[dict]:
    """Igual pero para ventas emitidas (caso raro, < 50/mes en JIPER)."""
    df_em = df[df["grupo"].str.lower() == "emitido"].copy()
    df_em = df_em[~df_em["tipo_documento"].isin(TIPOS_NO_CONTABLES)]
    df_clasif = clasificar_df_por_tarifa(df_em)
    mixtas = df_clasif[df_clasif["tarifa_detectada"] == "MIXTA"]

    out = []
    for _, row in mixtas.iterrows():
        if not row["cufe"]:
            continue
        out.append({
            "cufe":             row["cufe"],
            "folio":            row["folio"],
            "prefijo":          row["prefijo"],
            "tipo_documento":   row["tipo_documento"],
            "fecha_emision":    row["fecha_emision"].strftime("%Y-%m-%d") if pd.notna(row["fecha_emision"]) else "",
            "nit_emisor":       row["nit_emisor"],
            "nombre_emisor":    row["nombre_emisor"],
            "nit_receptor":     row["nit_receptor"],
            "nombre_receptor":  row["nombre_receptor"],
            "total":            float(row["total"]),
            "grupo":            row["grupo"],
            "razon":            "MIXTA",
        })
    return out


def generar_lista_proveedores_unicos(
    df_token,
    maestro_existente: Optional[dict] = None,
    mapeo_historico: Optional[dict] = None,
) -> List[dict]:
    """
    Para cada NIT proveedor único en los recibidos, devuelve UN CUFE representativo
    (el de mayor valor). Útil para descargar 1 XML por NIT y extraer régimen + dirección.

    Excluye NITs que ya están en:
      - maestro_existente['terceros']  (régimen + dirección ya conocidos)
      - mapeo_historico['mapeo']        (NIT ya tiene cuenta gasto histórica)

    Es decir: solo trae los proveedores REALMENTE NUEVOS, los que no aparecen ni
    en el maestro ni en la contabilidad existente.

    Returns:
        Lista de dicts con campos cufe, folio, prefijo, nit_emisor, nombre_emisor, total.
    """
    df = df_token[df_token["grupo"].str.lower() == "recibido"].copy()
    if len(df) == 0:
        return []

    import re
    def _normalizar(s):
        if not s: return ""
        return re.sub(r"\D", "", str(s).split("-")[0])

    df["NIT_norm"] = df["nit_emisor"].apply(_normalizar)

    # Construir set de NITs ya conocidos (maestro + histórico)
    nits_conocidos = set()
    if maestro_existente:
        nits_conocidos |= set(maestro_existente.get("terceros", {}).keys())
    if mapeo_historico:
        # mapeo_historico tiene formato {"mapeo": [{"nit": "...", ...}, ...]}
        for entry in mapeo_historico.get("mapeo", []):
            nit = _normalizar(entry.get("nit", ""))
            if nit:
                nits_conocidos.add(nit)

    if nits_conocidos:
        df = df[~df["NIT_norm"].isin(nits_conocidos)]
        if len(df) == 0:
            return []

    # Para cada NIT, el CUFE de mayor valor
    df["total_num"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    df = df.sort_values("total_num", ascending=False).drop_duplicates("NIT_norm")

    out = []
    for _, row in df.iterrows():
        if not row.get("cufe"):
            continue
        out.append({
            "cufe":             row["cufe"],
            "folio":            row["folio"],
            "prefijo":          row["prefijo"],
            "tipo_documento":   row["tipo_documento"],
            "fecha_emision":    row["fecha_emision"].strftime("%Y-%m-%d") if pd.notna(row["fecha_emision"]) else "",
            "nit_emisor":       row["NIT_norm"],
            "nombre_emisor":    row["nombre_emisor"],
            "total":            float(row["total_num"]),
            "razon":            "PROVEEDOR_UNICO",
        })
    return out


def generar_lista_stl_completa(df_token, fecha_desde=None, fecha_hasta=None) -> List[str]:
    """
    Genera la lista de TODOS los CUFEs de STL emitidas (no solo MIXTAS).
    El procesador desde XML necesita todos para parsear IVA por línea.
    """
    df = df_token[df_token["grupo"].str.lower() == "emitido"].copy()
    df = df[df["prefijo"].astype(str).str.upper().str.startswith("STL")]

    if fecha_desde is not None:
        df = df[df["fecha_emision"].dt.date >= fecha_desde]
    if fecha_hasta is not None:
        df = df[df["fecha_emision"].dt.date <= fecha_hasta]

    return df["cufe"].dropna().astype(str).tolist()


def generar_lista_todas_compras_unicas(
    df_token,
    fecha_desde=None,
    fecha_hasta=None,
    maestro_existente: Optional[dict] = None,
) -> List[dict]:
    """
    Genera la lista de CUFEs para descargar XMLs de TODOS los proveedores únicos
    de compras del mes (no solo los nuevos).

    Lógica:
      - Para cada NIT proveedor único en los recibidos, devuelve UN CUFE
        representativo (el de mayor valor).
      - Se INCLUYEN proveedores que ya estén en histórico (a diferencia de
        generar_lista_proveedores_unicos), porque necesitamos su régimen real
        del XML para decidir retención.
      - Solo se EXCLUYEN los que ya están en el maestro CON régimen registrado
        (tax_level_principal no vacío).

    Esto se usa para resolver el bug de retenciones aplicadas a autorretenedores
    como EPM/Postobón que sí están en el histórico pero sin su régimen real
    declarado.

    Returns:
        Lista de dicts con campos cufe, folio, nit_emisor, nombre_emisor, total.
    """
    df = df_token[df_token["grupo"].str.lower() == "recibido"].copy()
    if fecha_desde is not None:
        df = df[df["fecha_emision"].dt.date >= fecha_desde]
    if fecha_hasta is not None:
        df = df[df["fecha_emision"].dt.date <= fecha_hasta]
    if len(df) == 0:
        return []

    import re
    def _normalizar(s):
        if not s: return ""
        return re.sub(r"\D", "", str(s).split("-")[0])

    df["NIT_norm"] = df["nit_emisor"].apply(_normalizar)

    # Solo excluir los que YA tienen régimen real en el maestro
    nits_con_regimen = set()
    if maestro_existente:
        for nit, datos in maestro_existente.get("terceros", {}).items():
            if datos.get("tax_level_principal"):
                nits_con_regimen.add(_normalizar(nit))

    if nits_con_regimen:
        df = df[~df["NIT_norm"].isin(nits_con_regimen)]
        if len(df) == 0:
            return []

    # Para cada NIT, el CUFE de mayor valor
    df["total_num"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    df = df.sort_values("total_num", ascending=False).drop_duplicates("NIT_norm")

    out = []
    for _, row in df.iterrows():
        if not row.get("cufe"):
            continue
        out.append({
            "cufe":             row["cufe"],
            "folio":            row["folio"],
            "prefijo":          row["prefijo"],
            "tipo_documento":   row["tipo_documento"],
            "fecha_emision":    row["fecha_emision"].strftime("%Y-%m-%d") if pd.notna(row["fecha_emision"]) else "",
            "nit_emisor":       row["NIT_norm"],
            "nombre_emisor":    row["nombre_emisor"],
            "total":            float(row["total_num"]),
            "razon":            "PROVEEDOR_REGIMEN",
        })
    return out
