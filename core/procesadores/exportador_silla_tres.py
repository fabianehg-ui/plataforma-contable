"""
Exportador de plano contable — Formato Silla Tres
==================================================

Formato de columnas requerido:
    CUENTA | Comprobante | Fecha(mm/dd/yyyy) | DOCUMENTO | Doc ref |
    Nit | DETALLE | Tipo | Valor | Base | Centro de Costo

Reglas:
- Tipo: 1 = Débito, 2 = Crédito (NO hay columnas separadas, va en una sola)
- Valor: siempre POSITIVO (el signo está en el Tipo)
- Fecha: formato americano mm/dd/yyyy
- BASE: solo va en líneas de IVA (2408xxxx) y retenciones (2365xx, 2367xx, 2368xx).
  En las demás líneas (inventario, proveedor, gastos) la columna queda VACÍA.
- DOCUMENTO: consecutivo correlativo configurable. Mismo número para todas las
  líneas del MISMO asiento contable; se incrementa al pasar al siguiente.
- Tres formatos disponibles: TXT (tab-separated), CSV (coma), XLSX
"""
from __future__ import annotations
from io import BytesIO
from typing import Any

import pandas as pd


# Cabeceras EXACTAS como las pidió el usuario (orden y mayúsculas)
CABECERAS = [
    "CUENTA",
    "Comprobante",
    "Fecha(mm/dd/yyyy)",
    "DOCUMENTO",
    "Doc ref",
    "Nit",
    "DETALLE",
    "Tipo",
    "Valor",
    "Base",
    "Centro de Costo",
]


# ─── Cuentas que LLEVAN base en el plano Silla Tres ─────────
PREFIJOS_CUENTA_CON_BASE = (
    "2408",   # IVA descontable e IVA generado
    "2365",   # Retención en la fuente (renta)
    "2367",   # Retención IVA
    "2368",   # Retención ICA municipal
    "2370",   # Otras retenciones
    "1355",   # Anticipos de impuestos (cuando vienen del cliente)
    "1365",   # Reteivas a favor / saldos
)


def _cuenta_lleva_base(cuenta: str) -> bool:
    """Indica si una cuenta debe llevar valor en la columna BASE."""
    if not cuenta:
        return False
    return str(cuenta).strip().startswith(PREFIJOS_CUENTA_CON_BASE)


def _fecha_americana(fecha_iso: str) -> str:
    """Convierte 'YYYY-MM-DD' o 'YYYY/MM/DD' → 'MM/DD/YYYY'."""
    if not fecha_iso:
        return ""
    s = str(fecha_iso).strip().replace("/", "-")
    partes = s.split("-")
    if len(partes) == 3 and len(partes[0]) == 4:
        yyyy, mm, dd = partes[0], partes[1], partes[2]
        return f"{mm.zfill(2)}/{dd.zfill(2)}/{yyyy}"
    if len(partes) == 3 and len(partes[2]) == 4:
        dd, mm, yyyy = partes[0], partes[1], partes[2]
        return f"{mm.zfill(2)}/{dd.zfill(2)}/{yyyy}"
    return str(fecha_iso)


def _formato_cc(cc: str, formato: str = "sin_guion") -> str:
    """10-04 → 1004 (sin_guion) / 10-04 (con_guion) / 10 (primer_grupo)."""
    if not cc:
        return ""
    if formato == "sin_guion":
        return str(cc).replace("-", "").replace(".", "")
    if formato == "primer_grupo":
        return str(cc).split("-")[0]
    return str(cc)


def _agrupar_lineas_por_asiento(lineas: list) -> list[list]:
    """Agrupa las líneas del plano en asientos contables.

    Un "asiento" = todas las líneas de la misma factura/documento.
    Se agrupa por (consecutivo_interno, doc_referencia, fecha, nit_tercero).
    """
    grupos: dict[tuple, list] = {}
    orden_aparicion: list[tuple] = []

    for l in lineas:
        clave = (
            str(getattr(l, "consecutivo", "") or ""),
            str(getattr(l, "documento_referencia", "") or ""),
            str(getattr(l, "fecha", "") or ""),
            str(getattr(l, "nit_tercero", "") or ""),
        )
        if clave not in grupos:
            grupos[clave] = []
            orden_aparicion.append(clave)
        grupos[clave].append(l)

    return [grupos[k] for k in orden_aparicion]


def construir_dataframe_silla_tres(
    lineas: list,
    cc_formato: str = "sin_guion",
    consecutivo_inicial: int = 1,
) -> pd.DataFrame:
    """Construye un DataFrame con el formato exacto Silla Tres.

    Args:
        lineas: list[LineaPlano] del procesador
        cc_formato: 'sin_guion' | 'con_guion' | 'primer_grupo'
        consecutivo_inicial: número desde el cual empezar a numerar los DOCUMENTOs.
            Cada asiento contable lleva el mismo número; se incrementa al pasar al
            siguiente asiento.

    Returns:
        pd.DataFrame con columnas en el orden exacto requerido.
    """
    asientos = _agrupar_lineas_por_asiento(lineas)
    filas: list[dict[str, Any]] = []
    consecutivo = int(consecutivo_inicial)

    for asiento in asientos:
        doc_num = str(consecutivo)
        for l in asiento:
            debito = float(getattr(l, "debito", 0) or 0)
            credito = float(getattr(l, "credito", 0) or 0)

            if debito > 0:
                tipo = 1
                valor = debito
            elif credito > 0:
                tipo = 2
                valor = credito
            else:
                tipo = 1
                valor = 0.0

            cuenta = str(getattr(l, "cuenta", "") or "")
            if _cuenta_lleva_base(cuenta):
                base_raw = float(getattr(l, "base", 0) or 0)
                base_str = str(round(base_raw)) if base_raw > 0 else ""
            else:
                base_str = ""

            filas.append({
                "CUENTA": cuenta,
                "Comprobante": str(getattr(l, "comprobante", "") or ""),
                "Fecha(mm/dd/yyyy)": _fecha_americana(getattr(l, "fecha", "")),
                "DOCUMENTO": doc_num,
                "Doc ref": str(getattr(l, "documento_referencia", "") or ""),
                "Nit": str(getattr(l, "nit_tercero", "") or ""),
                "DETALLE": str(getattr(l, "descripcion", "") or "").replace("\t", " ").replace("\n", " "),
                "Tipo": tipo,
                "Valor": round(valor),
                "Base": base_str,
                "Centro de Costo": _formato_cc(str(getattr(l, "centro_costo", "") or ""), cc_formato),
            })
        consecutivo += 1

    return pd.DataFrame(filas, columns=CABECERAS)


# ─── Exportadores ──────────────────────────────────────

def exportar_txt_silla_tres(df: pd.DataFrame, separador: str = "\t") -> bytes:
    """TXT separado por TAB. Devuelve bytes UTF-8 con cabecera."""
    contenido = df.to_csv(sep=separador, index=False, encoding="utf-8")
    return contenido.encode("utf-8")


def exportar_csv_silla_tres(df: pd.DataFrame) -> bytes:
    """CSV separado por coma. Devuelve bytes UTF-8 con cabecera."""
    contenido = df.to_csv(sep=",", index=False, encoding="utf-8")
    return contenido.encode("utf-8")


def exportar_xlsx_silla_tres(df: pd.DataFrame, sheet_name: str = "Plano") -> bytes:
    """Excel .xlsx con cabecera, anchos y columnas-código como TEXTO."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        ws = writer.sheets[sheet_name]
        anchos = {
            "A": 12, "B": 12, "C": 18, "D": 12, "E": 18,
            "F": 14, "G": 50, "H": 6, "I": 14, "J": 14, "K": 14,
        }
        for col, w in anchos.items():
            ws.column_dimensions[col].width = w

        # Columnas como TEXTO (códigos, NITs, CCs)
        for col in ["A", "B", "D", "E", "F", "K"]:
            for row in range(2, len(df) + 2):
                ws[f"{col}{row}"].number_format = "@"

        # Valor con formato millares
        for row in range(2, len(df) + 2):
            ws[f"I{row}"].number_format = "#,##0"
            base_val = ws[f"J{row}"].value
            if base_val not in (None, "", "0"):
                ws[f"J{row}"].number_format = "#,##0"

    return buffer.getvalue()
