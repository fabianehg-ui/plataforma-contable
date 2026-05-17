"""
core/procesadores/lector_excel_token.py

Lee el archivo Excel que descarga el portal DIAN cuando le das clic a
"Exportar a Excel" desde el Token. Ese Excel trae todos los documentos
electrónicos del período sin límite de paginación (~44.000 docs de un mes
con operación alta).

Columnas esperadas (las normaliza a snake_case):
    Tipo de documento  → tipo_documento
    CUFE/CUDE          → cufe
    Folio              → folio
    Prefijo            → prefijo
    Fecha Emisión      → fecha_emision (parseada a date)
    NIT Emisor         → nit_emisor (normalizado a solo dígitos)
    Nombre Emisor      → nombre_emisor
    NIT Receptor       → nit_receptor
    Nombre Receptor    → nombre_receptor
    Total              → total
    Estado             → estado
    Grupo              → grupo ('Emitido' o 'Recibido')

EXPONE:
    leer_excel_token(path_o_bytes) -> DataFrame normalizado
    clasificar_para_descarga(df, nit_empresa) -> dict con conteos por rol/tipo
    generar_lista_cufes(df, rol, excluir_tipos) -> list[dict]
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Optional, Union

import pandas as pd


# Columnas que el clasificador siempre necesita
COLUMNAS_REQUERIDAS = {
    "Tipo de documento", "CUFE/CUDE", "Folio", "Prefijo",
    "Fecha Emisión", "NIT Emisor", "Nombre Emisor",
    "NIT Receptor", "Nombre Receptor", "Total", "Grupo",
}

# Tipos que NUNCA aportan a contabilidad (acuses, nómina individual)
# El usuario puede pedir excluirlos al generar la lista
TIPOS_EXCLUIBLES = {
    "Application response",
    "Nomina Individual",
}


def _normalizar_nit(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if "-" in s:
        s = s.split("-", 1)[0]
    return re.sub(r"\D", "", s)


def leer_excel_token(archivo: Union[bytes, str, io.BytesIO]) -> pd.DataFrame:
    """
    Lee el Excel exportado del portal DIAN y devuelve un DataFrame
    normalizado.

    Args:
        archivo: ruta al .xlsx, bytes, o BytesIO.

    Returns:
        DataFrame con columnas estándar y validaciones aplicadas.

    Levanta ValueError si faltan columnas obligatorias.
    """
    df = pd.read_excel(archivo, dtype=str)
    columnas = set(df.columns)
    faltantes = COLUMNAS_REQUERIDAS - columnas
    if faltantes:
        raise ValueError(
            f"El Excel del Token DIAN no tiene las columnas esperadas. "
            f"Faltan: {sorted(faltantes)}. Columnas encontradas: {sorted(columnas)}"
        )

    # Normalizar
    df["nit_emisor"] = df["NIT Emisor"].apply(_normalizar_nit)
    df["nit_receptor"] = df["NIT Receptor"].apply(_normalizar_nit)
    df["fecha_emision"] = pd.to_datetime(
        df["Fecha Emisión"], errors="coerce", dayfirst=True
    )
    df["total"] = pd.to_numeric(
        df["Total"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    ).fillna(0)

    # Renombrar para facilitar uso downstream
    df = df.rename(columns={
        "Tipo de documento": "tipo_documento",
        "CUFE/CUDE":         "cufe",
        "Folio":             "folio",
        "Prefijo":           "prefijo",
        "Nombre Emisor":     "nombre_emisor",
        "Nombre Receptor":   "nombre_receptor",
        "Estado":            "estado",
        "Grupo":             "grupo",
    })

    # Limpiar strings
    for col in ["tipo_documento", "cufe", "folio", "prefijo",
                "nombre_emisor", "nombre_receptor", "estado", "grupo"]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()

    return df


def filtrar_por_rango(
    df: pd.DataFrame,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
) -> pd.DataFrame:
    """Filtra el DataFrame por rango de fecha de emisión."""
    if fecha_desde is None and fecha_hasta is None:
        return df
    mask = pd.Series([True] * len(df), index=df.index)
    if fecha_desde is not None:
        mask &= df["fecha_emision"] >= pd.Timestamp(fecha_desde)
    if fecha_hasta is not None:
        mask &= df["fecha_emision"] <= pd.Timestamp(fecha_hasta) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return df[mask].copy()


def resumen_por_grupo_y_tipo(df: pd.DataFrame) -> pd.DataFrame:
    """Tabla resumen: filas = tipo_documento, columnas = grupo (Emitido/Recibido)."""
    if len(df) == 0:
        return pd.DataFrame(columns=["Emitido", "Recibido", "Total"])
    cross = pd.crosstab(df["tipo_documento"], df["grupo"], margins=True, margins_name="Total")
    return cross


def conteo_para_descarga(
    df: pd.DataFrame,
    excluir_tipos: Optional[set] = None,
) -> dict:
    """
    Devuelve los conteos de documentos útiles (excluyendo tipos no contables).

    Returns:
        {
          'emitidos_brutos': int,
          'emitidos_excluidos': dict[tipo -> int],
          'emitidos_utiles': int,
          'emitidos_desglose': dict[tipo -> int],
          'recibidos_brutos': int,
          'recibidos_excluidos': dict[tipo -> int],
          'recibidos_utiles': int,
          'recibidos_desglose': dict[tipo -> int],
        }
    """
    excluir_tipos = excluir_tipos if excluir_tipos is not None else TIPOS_EXCLUIBLES

    emit = df[df["grupo"].str.lower() == "emitido"]
    recb = df[df["grupo"].str.lower() == "recibido"]

    emit_util = emit[~emit["tipo_documento"].isin(excluir_tipos)]
    recb_util = recb[~recb["tipo_documento"].isin(excluir_tipos)]

    return {
        "emitidos_brutos":   len(emit),
        "emitidos_excluidos": emit[emit["tipo_documento"].isin(excluir_tipos)]["tipo_documento"].value_counts().to_dict(),
        "emitidos_utiles":   len(emit_util),
        "emitidos_desglose": emit_util["tipo_documento"].value_counts().to_dict(),
        "recibidos_brutos":   len(recb),
        "recibidos_excluidos": recb[recb["tipo_documento"].isin(excluir_tipos)]["tipo_documento"].value_counts().to_dict(),
        "recibidos_utiles":  len(recb_util),
        "recibidos_desglose": recb_util["tipo_documento"].value_counts().to_dict(),
    }


def generar_lista_cufes(
    df: pd.DataFrame,
    rol: str,
    excluir_tipos: Optional[set] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
) -> list:
    """
    Genera la lista de CUFEs a descargar.

    Args:
        df: DataFrame del Excel ya leído.
        rol: 'emitido' o 'recibido' (case-insensitive).
        excluir_tipos: set de tipos a excluir. None = usa TIPOS_EXCLUIBLES.
        fecha_desde, fecha_hasta: opcionales para filtrar.

    Returns:
        Lista de dicts: [{cufe, folio, prefijo, tipo, fecha, ...}, ...]
        Lista pensada para que la extensión Chrome la procese: cada dict
        tiene el cufe (que es el trackId para DownloadZipFiles) y metadatos
        útiles para mostrar progreso o reanudar.
    """
    if excluir_tipos is None:
        excluir_tipos = TIPOS_EXCLUIBLES

    df_filt = filtrar_por_rango(df, fecha_desde, fecha_hasta)
    df_filt = df_filt[df_filt["grupo"].str.lower() == rol.lower()]
    df_filt = df_filt[~df_filt["tipo_documento"].isin(excluir_tipos)]

    out = []
    for _, row in df_filt.iterrows():
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
        })
    return out
