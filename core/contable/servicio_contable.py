"""
core/contable/servicio_contable.py

Capa de servicio del NÚCLEO CONTABLE (tablas cn_* de la migración
014_nucleo_contable.sql). Sigue el patrón de core/f350/servicios.py:
cada función recibe el cliente Supabase `sb` como primer argumento.

Grupos:
    - Catálogos globales : valores anuales, calendario tributario, municipios, parámetros
    - Por empresa        : plan de cuentas, centros de costo, comprobantes,
                           valores de parámetros, períodos, movimientos

Lo más importante: guardar_plano() toma un DataFrame con el layout de 11
columnas de Contai (el que ya generan los módulos de nómina, vacaciones y
ajuste PILA) y lo persiste en cn_movimientos.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import pandas as pd


# Columnas del plano (idénticas a procesador_nomina.COLUMNAS_PLANO)
COLUMNAS_PLANO = [
    "CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
    "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO",
]

# Mapa columna del plano -> columna de cn_movimientos
_MAPA_PLANO_DB = {
    "CUENTA": "cuenta",
    "COMPROBANTE": "comprobante",
    "FECHA": "fecha",
    "DOCUMENTO": "documento",
    "DOC REFERENCIA": "doc_referencia",
    "NIT": "nit",
    "DETALLE": "detalle",
    "TR": "tr",
    "VALOR": "valor",
    "BASE": "base",
    "CENTRO DE COSTO": "centro_costo",
}


# ============================================================
# Helpers
# ============================================================

def _fecha_iso(v) -> Optional[str]:
    """Convierte una fecha de plano ('MM/DD/AAAA') o date a ISO 'YYYY-MM-DD'."""
    if v is None or v == "":
        return None
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s  # se deja tal cual si no se reconoce


def _int(v) -> int:
    try:
        return int(round(float(str(v).replace(",", "").replace("$", "").strip() or 0)))
    except (ValueError, TypeError):
        return 0


def plano_a_registros(
    df: pd.DataFrame,
    empresa_id: str,
    periodo: str,
    origen: str = "",
    user_id: Optional[str] = None,
) -> list[dict]:
    """Convierte un DataFrame de plano (11 columnas) en filas para cn_movimientos.

    Función PURA (sin red): útil para pruebas y para revisar antes de insertar.
    """
    registros = []
    for _, row in df.iterrows():
        reg = {"empresa_id": empresa_id, "periodo": str(periodo), "origen": origen or None}
        for col_plano, col_db in _MAPA_PLANO_DB.items():
            val = row.get(col_plano)
            if col_db == "fecha":
                reg[col_db] = _fecha_iso(val)
            elif col_db in ("valor", "base"):
                reg[col_db] = _int(val)
            else:
                reg[col_db] = None if val is None or str(val) == "" else str(val)
        if user_id:
            reg["creado_por"] = user_id
        registros.append(reg)
    return registros


# ============================================================
# Catálogos globales
# ============================================================

def obtener_valores_anuales(sb, anio: int) -> dict:
    """Valores anuales (SMMLV, UVT, aux transporte, topes). {} si no existe."""
    res = (
        sb.table("cn_valores_anuales").select("*").eq("anio", int(anio)).limit(1).execute()
    )
    return (res.data or [{}])[0]


def obtener_calendario(sb, anio: int, impuesto: str, digito_nit: str) -> list[dict]:
    """Fechas de vencimiento para un impuesto/año/dígito de NIT."""
    res = (
        sb.table("cn_calendario_tributario").select("*")
          .eq("anio", int(anio)).eq("impuesto", impuesto)
          .eq("digito_nit", str(digito_nit)).execute()
    )
    return res.data or []


def listar_municipios(sb, query: Optional[str] = None, limit: int = 50) -> list[dict]:
    q = sb.table("cn_municipios").select("codigo_dane, nombre, departamento")
    if query:
        q = q.ilike("nombre", f"%{query}%")
    return q.order("codigo_dane").limit(limit).execute().data or []


def listar_parametros(sb) -> list[dict]:
    """Definición de parámetros (global)."""
    return sb.table("cn_parametros").select("*").order("codigo").execute().data or []


# ============================================================
# Parámetros por empresa
# ============================================================

def obtener_valor_parametro(sb, empresa_id: str, codigo: str, defecto=None):
    res = (
        sb.table("cn_parametros_valor").select("valor")
          .eq("empresa_id", empresa_id).eq("codigo", str(codigo))
          .limit(1).execute()
    )
    if res.data:
        return res.data[0]["valor"]
    return defecto


def set_valor_parametro(sb, empresa_id: str, codigo: str, valor) -> dict:
    payload = {
        "empresa_id": empresa_id,
        "codigo": str(codigo),
        "valor": None if valor is None else str(valor),
    }
    res = (
        sb.table("cn_parametros_valor")
          .upsert(payload, on_conflict="empresa_id,codigo")
          .execute()
    )
    return (res.data or [{}])[0]


# ============================================================
# Plan de cuentas
# ============================================================

def listar_plan_cuentas(sb, empresa_id: str, limit: int = 10000) -> list[dict]:
    return (
        sb.table("cn_plan_cuentas").select("*")
          .eq("empresa_id", empresa_id).order("codigo").limit(limit)
          .execute().data or []
    )


def upsert_cuenta(sb, empresa_id: str, codigo: str, nombre: str, **campos) -> dict:
    payload = {"empresa_id": empresa_id, "codigo": str(codigo), "nombre": nombre, **campos}
    res = (
        sb.table("cn_plan_cuentas")
          .upsert(payload, on_conflict="empresa_id,codigo")
          .execute()
    )
    return (res.data or [{}])[0]


def importar_plan_cuentas(sb, empresa_id: str, filas: list[dict], lote: int = 500) -> int:
    """Carga masiva del PUC. `filas` = [{codigo, nombre, naturaleza, ...}, ...]."""
    total = 0
    payload = [{"empresa_id": empresa_id, **f} for f in filas]
    for i in range(0, len(payload), lote):
        chunk = payload[i:i + lote]
        sb.table("cn_plan_cuentas").upsert(chunk, on_conflict="empresa_id,codigo").execute()
        total += len(chunk)
    return total


# ============================================================
# Centros de costo y comprobantes
# ============================================================

def listar_centros_costo(sb, empresa_id: str) -> list[dict]:
    return (
        sb.table("cn_centros_costo").select("*")
          .eq("empresa_id", empresa_id).order("codigo").execute().data or []
    )


def upsert_centro_costo(sb, empresa_id: str, codigo: str, nombre: str) -> dict:
    payload = {"empresa_id": empresa_id, "codigo": str(codigo), "nombre": nombre}
    res = sb.table("cn_centros_costo").upsert(payload, on_conflict="empresa_id,codigo").execute()
    return (res.data or [{}])[0]


def listar_comprobantes(sb, empresa_id: str) -> list[dict]:
    return (
        sb.table("cn_comprobantes").select("*")
          .eq("empresa_id", empresa_id).order("codigo").execute().data or []
    )


def upsert_comprobante(sb, empresa_id: str, codigo: str, nombre: str) -> dict:
    payload = {"empresa_id": empresa_id, "codigo": str(codigo), "nombre": nombre}
    res = sb.table("cn_comprobantes").upsert(payload, on_conflict="empresa_id,codigo").execute()
    return (res.data or [{}])[0]


# ============================================================
# Períodos
# ============================================================

def listar_periodos(sb, empresa_id: str) -> list[dict]:
    return (
        sb.table("cn_periodos").select("*")
          .eq("empresa_id", empresa_id).order("periodo").execute().data or []
    )


def crear_periodo(sb, empresa_id: str, periodo: str, nombre: str = "",
                  fecha_inicial=None, fecha_final=None) -> dict:
    payload = {
        "empresa_id": empresa_id,
        "periodo": str(periodo),
        "nombre": nombre or None,
        "fecha_inicial": _fecha_iso(fecha_inicial),
        "fecha_final": _fecha_iso(fecha_final),
        "estado": "A",
    }
    # ignore_duplicates: si el período YA existe no lo toca (no reabre uno protegido)
    res = sb.table("cn_periodos").upsert(
        payload, on_conflict="empresa_id,periodo", ignore_duplicates=True
    ).execute()
    return (res.data or [{}])[0]


def cambiar_estado_periodo(sb, empresa_id: str, periodo: str, estado: str) -> dict:
    """estado: 'A' abierto | 'P' protegido."""
    res = (
        sb.table("cn_periodos").update({"estado": estado})
          .eq("empresa_id", empresa_id).eq("periodo", str(periodo)).execute()
    )
    return (res.data or [{}])[0]


def periodo_protegido(sb, empresa_id: str, periodo: str) -> bool:
    res = (
        sb.table("cn_periodos").select("estado")
          .eq("empresa_id", empresa_id).eq("periodo", str(periodo)).limit(1).execute()
    )
    return bool(res.data) and res.data[0]["estado"] == "P"


# ============================================================
# Movimientos (el plano de 11 columnas)
# ============================================================

def guardar_plano(
    sb, empresa_id: str, periodo: str, df: pd.DataFrame,
    origen: str = "", user_id: Optional[str] = None,
    reemplazar: bool = False, lote: int = 500,
) -> int:
    """Guarda un plano (DataFrame de 11 columnas) en cn_movimientos.

    Args:
        periodo: 'AAAAMM' (ej. '202605').
        origen: etiqueta de dónde viene ('nomina','vacaciones','ajuste_pila'...).
        reemplazar: si True, borra primero los movimientos de ese
                    (periodo, origen) antes de insertar (evita duplicados al
                    reprocesar). Respeta el período protegido.
    Returns:
        número de filas insertadas.
    Raises:
        PermissionError si el período está protegido.
    """
    if periodo_protegido(sb, empresa_id, periodo):
        raise PermissionError(
            f"El período {periodo} está PROTEGIDO; no se pueden grabar movimientos."
        )

    if reemplazar and origen:
        eliminar_movimientos(sb, empresa_id, periodo, origen=origen)

    registros = plano_a_registros(df, empresa_id, periodo, origen=origen, user_id=user_id)
    total = 0
    for i in range(0, len(registros), lote):
        chunk = registros[i:i + lote]
        sb.table("cn_movimientos").insert(chunk).execute()
        total += len(chunk)
    return total


def listar_movimientos(sb, empresa_id: str, periodo: str,
                       comprobante: Optional[str] = None,
                       origen: Optional[str] = None) -> list[dict]:
    q = (
        sb.table("cn_movimientos").select("*")
          .eq("empresa_id", empresa_id).eq("periodo", str(periodo))
    )
    if comprobante is not None:
        q = q.eq("comprobante", str(comprobante))
    if origen is not None:
        q = q.eq("origen", origen)
    return q.order("comprobante").order("documento").execute().data or []


def eliminar_movimientos(sb, empresa_id: str, periodo: str,
                         comprobante: Optional[str] = None,
                         origen: Optional[str] = None) -> None:
    q = (
        sb.table("cn_movimientos").delete()
          .eq("empresa_id", empresa_id).eq("periodo", str(periodo))
    )
    if comprobante is not None:
        q = q.eq("comprobante", str(comprobante))
    if origen is not None:
        q = q.eq("origen", origen)
    q.execute()


def saldos_por_cuenta(sb, empresa_id: str, periodo: str) -> pd.DataFrame:
    """Saldo por cuenta del período: débitos, créditos y saldo (Db−Cr)."""
    movs = listar_movimientos(sb, empresa_id, periodo)
    if not movs:
        return pd.DataFrame(columns=["cuenta", "debitos", "creditos", "saldo"])
    df = pd.DataFrame(movs)
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0)
    db = df[df["tr"] == "1"].groupby("cuenta")["valor"].sum()
    cr = df[df["tr"] == "2"].groupby("cuenta")["valor"].sum()
    out = pd.DataFrame({"debitos": db, "creditos": cr}).fillna(0)
    out["saldo"] = out["debitos"] - out["creditos"]
    return out.reset_index().sort_values("cuenta")


def cuadre_periodo(sb, empresa_id: str, periodo: str) -> dict:
    """Devuelve {debitos, creditos, cuadra} del período completo."""
    movs = listar_movimientos(sb, empresa_id, periodo)
    db = sum(int(m["valor"]) for m in movs if m.get("tr") == "1")
    cr = sum(int(m["valor"]) for m in movs if m.get("tr") == "2")
    return {"debitos": db, "creditos": cr, "diferencia": db - cr, "cuadra": db == cr}
