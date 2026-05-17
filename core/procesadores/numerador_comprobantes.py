"""
core/procesadores/numerador_comprobantes.py

Asigna numeración consecutiva a los asientos contables, agrupando por COMPROBANTE.

Reglas:
  - Cada comprobante (20 compras, 21 NCs recibidas, 426 STL, 401 Indiana, etc.)
    tiene su propia secuencia que empieza en 1 cada mes.
  - Cada FACTURA/NC original es UN asiento (todas sus líneas comparten el mismo
    número de documento interno).
  - Para POS consolidado, cada día×prefijo es UN asiento.

EXPONE:
    Numerador: clase que asigna números consecutivos por comprobante.
    aplicar_numeracion(df_plano): aplica numeración al DataFrame en bloque.
    extraer_folio_numerico(folio): extrae solo dígitos del folio (sin prefijo).
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

import pandas as pd


def extraer_folio_numerico(folio: str) -> str:
    """
    Devuelve solo los dígitos del folio (sin prefijo alfabético).

    Ejemplos:
        "FELC1234" → "1234"
        "DSE3029"  → "3029"
        "NCI-456"  → "456"
        "1234"     → "1234"
        ""         → ""
    """
    if folio is None or pd.isna(folio):
        return ""
    s = str(folio).strip()
    if not s:
        return ""
    # Extraer solo dígitos
    digitos = re.sub(r"\D", "", s)
    return digitos


class Numerador:
    """
    Lleva contadores por comprobante. Cada llamada con un nuevo
    (comprobante, doc_original) devuelve el siguiente número de ese comprobante.
    Si vuelve a llamarse con la misma combinación, devuelve el mismo número
    (todas las líneas del mismo asiento comparten el consecutivo).
    """

    def __init__(self):
        # comprobante → siguiente consecutivo libre
        self._siguiente: dict[str, int] = defaultdict(lambda: 1)
        # (comprobante, doc_original) → consecutivo asignado
        self._asignados: dict[tuple, int] = {}

    def asignar(self, comprobante: str, doc_original: str) -> int:
        """
        Devuelve el consecutivo asignado a (comprobante, doc_original).
        Si es nueva combinación, toma el siguiente disponible para ese
        comprobante e incrementa el contador.
        """
        comp = str(comprobante).strip()
        doc = str(doc_original).strip()
        clave = (comp, doc)

        if clave in self._asignados:
            return self._asignados[clave]

        n = self._siguiente[comp]
        self._asignados[clave] = n
        self._siguiente[comp] = n + 1
        return n

    def resumen(self) -> dict[str, int]:
        """Devuelve {comprobante: cantidad_de_asientos_asignados}."""
        return {comp: n - 1 for comp, n in self._siguiente.items()}


def aplicar_numeracion(
    df_plano: pd.DataFrame,
    col_comprobante: str = "COMPROBANTE",
    col_documento: str = "DOCUMENTO",
    col_referencia: str = "DOC REFERENCIA",
) -> pd.DataFrame:
    """
    Toma un plano contable que ya tiene en `DOCUMENTO` el formato "PREFIJO+folio"
    (ej. "FELC1234") y lo transforma en:
      - DOCUMENTO       → consecutivo por comprobante (1, 2, 3...)
      - DOC REFERENCIA  → solo los dígitos del folio original (sin prefijo)

    Agrupa por (COMPROBANTE, DOCUMENTO_original) — todas las líneas del mismo
    asiento conservan el mismo consecutivo.

    Args:
        df_plano: DataFrame con las columnas del plano.

    Returns:
        DataFrame con DOCUMENTO y DOC REFERENCIA actualizados.
    """
    if df_plano is None or len(df_plano) == 0:
        return df_plano

    df = df_plano.copy()
    # Guardar el documento original como referencia
    df["_doc_original"] = df[col_documento].astype(str)
    # Extraer folio numérico para DOC REFERENCIA
    df[col_referencia] = df["_doc_original"].apply(extraer_folio_numerico)

    # Asignar consecutivo por (comprobante, doc_original)
    # IMPORTANTE: respetar el orden actual del DataFrame (es el orden cronológico
    # en que ya están armados los asientos). Eso garantiza que asiento 1 = primero
    # del mes para ese comprobante.
    numerador = Numerador()

    # Orden de primera aparición de cada (comp, doc) determina el consecutivo
    nuevos_nums = []
    for _, row in df.iterrows():
        comp = str(row[col_comprobante]).strip()
        doc_orig = str(row["_doc_original"]).strip()
        nuevos_nums.append(numerador.asignar(comp, doc_orig))

    df[col_documento] = nuevos_nums
    df = df.drop(columns=["_doc_original"])

    # Forzar string para evitar problemas de tipo
    df[col_documento] = df[col_documento].astype(str)
    df[col_referencia] = df[col_referencia].astype(str)

    return df


def aplicar_numeracion_con_resumen(
    df_plano: pd.DataFrame,
    col_comprobante: str = "COMPROBANTE",
    col_documento: str = "DOCUMENTO",
    col_referencia: str = "DOC REFERENCIA",
) -> tuple[pd.DataFrame, dict]:
    """
    Como aplicar_numeracion() pero también devuelve un resumen
    {comprobante: cantidad_asientos}.
    """
    if df_plano is None or len(df_plano) == 0:
        return df_plano, {}

    df = df_plano.copy()
    df["_doc_original"] = df[col_documento].astype(str)
    df[col_referencia] = df["_doc_original"].apply(extraer_folio_numerico)

    numerador = Numerador()
    nuevos_nums = []
    for _, row in df.iterrows():
        comp = str(row[col_comprobante]).strip()
        doc_orig = str(row["_doc_original"]).strip()
        nuevos_nums.append(numerador.asignar(comp, doc_orig))

    df[col_documento] = nuevos_nums
    df = df.drop(columns=["_doc_original"])
    df[col_documento] = df[col_documento].astype(str)
    df[col_referencia] = df[col_referencia].astype(str)

    return df, numerador.resumen()
