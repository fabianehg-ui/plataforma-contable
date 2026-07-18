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


def buscar_movimientos(sb, empresa_id: str, periodo: Optional[str] = None,
                       comprobante: Optional[str] = None, documento: Optional[str] = None,
                       cuenta: Optional[str] = None, nit: Optional[str] = None,
                       origen: Optional[str] = None, limit: int = 2000) -> list[dict]:
    """Lista movimientos con filtros combinables (para corrección por registros).

    Devuelve filas COMPLETAS (incluye `id`), necesarias para editar/eliminar.
    """
    q = sb.table("cn_movimientos").select("*").eq("empresa_id", empresa_id)
    if periodo:
        q = q.eq("periodo", str(periodo))
    if comprobante:
        q = q.eq("comprobante", str(comprobante))
    if documento:
        q = q.eq("documento", str(documento))
    if cuenta:
        q = q.eq("cuenta", str(cuenta))
    if nit:
        q = q.eq("nit", str(nit))
    if origen:
        q = q.eq("origen", origen)
    return (q.order("fecha").order("comprobante").order("documento")
            .limit(limit).execute().data or [])


# ============================================================
# Corrección de movimientos (por registro y por comprobante)
# ============================================================

_CAMPOS_MOV = {
    "cuenta", "comprobante", "fecha", "documento", "doc_referencia",
    "nit", "detalle", "tr", "valor", "base", "centro_costo",
}


def actualizar_movimiento(sb, empresa_id: str, mov_id: str, campos: dict) -> dict:
    """Actualiza un registro de cn_movimientos por su id (corrección puntual).

    Solo toca los campos permitidos; normaliza fecha (→ISO) y valor/base (→int).
    Respeta el período protegido del movimiento (si `periodo` o la fila lo están).
    """
    # Averiguar el período del registro para respetar protección
    actual = (sb.table("cn_movimientos").select("periodo")
              .eq("empresa_id", empresa_id).eq("id", mov_id).limit(1).execute())
    if actual.data:
        per = actual.data[0].get("periodo")
        if per and periodo_protegido(sb, empresa_id, per):
            raise PermissionError(f"El período {per} está PROTEGIDO; no se puede corregir.")

    payload = {}
    for k, v in campos.items():
        if k not in _CAMPOS_MOV:
            continue
        if k == "fecha":
            payload[k] = _fecha_iso(v)
        elif k in ("valor", "base"):
            payload[k] = _int(v)
        else:
            payload[k] = None if v is None or str(v) == "" else str(v)
    if not payload:
        return {}
    res = (sb.table("cn_movimientos").update(payload)
           .eq("empresa_id", empresa_id).eq("id", mov_id).execute())
    return (res.data or [{}])[0]


def eliminar_movimiento(sb, empresa_id: str, mov_id: str) -> None:
    """Elimina un registro por id (respeta período protegido)."""
    actual = (sb.table("cn_movimientos").select("periodo")
              .eq("empresa_id", empresa_id).eq("id", mov_id).limit(1).execute())
    if actual.data:
        per = actual.data[0].get("periodo")
        if per and periodo_protegido(sb, empresa_id, per):
            raise PermissionError(f"El período {per} está PROTEGIDO; no se puede eliminar.")
    sb.table("cn_movimientos").delete().eq("empresa_id", empresa_id).eq("id", mov_id).execute()


def eliminar_comprobante(sb, empresa_id: str, periodo: str,
                         comprobante: str, documento: str) -> None:
    """Borra todas las líneas de un asiento (periodo, comprobante, documento)."""
    (sb.table("cn_movimientos").delete()
       .eq("empresa_id", empresa_id).eq("periodo", str(periodo))
       .eq("comprobante", str(comprobante)).eq("documento", str(documento)).execute())


def reemplazar_comprobante(sb, empresa_id: str, periodo: str,
                           comprobante: str, documento: str, df: pd.DataFrame,
                           user_id: Optional[str] = None) -> int:
    """Corrección por comprobante: borra el asiento y lo reinserta desde el plano.

    `df` = DataFrame de 11 columnas (COLUMNAS_PLANO) con las líneas corregidas.
    Respeta el período protegido. Devuelve el número de líneas insertadas.
    """
    if periodo_protegido(sb, empresa_id, periodo):
        raise PermissionError(
            f"El período {periodo} está PROTEGIDO; no se puede corregir el comprobante.")
    eliminar_comprobante(sb, empresa_id, periodo, comprobante, documento)
    return guardar_plano(sb, empresa_id, periodo, df, origen="correccion",
                         user_id=user_id, reemplazar=False)


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


# ============================================================
# Fetch con paginación (PostgREST devuelve máx 1000 por página)
# ============================================================

def _fetch_paginado(sb, empresa_id: str, columns: str,
                    periodo_gte: Optional[str] = None,
                    periodo_lte: Optional[str] = None,
                    extra_eq: Optional[dict] = None,
                    pagina: int = 1000) -> list[dict]:
    filas: list[dict] = []
    off = 0
    while True:
        q = sb.table("cn_movimientos").select(columns).eq("empresa_id", empresa_id)
        if periodo_gte is not None:
            q = q.gte("periodo", periodo_gte)
        if periodo_lte is not None:
            q = q.lte("periodo", periodo_lte)
        for k, v in (extra_eq or {}).items():
            q = q.eq(k, v)
        res = q.range(off, off + pagina - 1).execute()
        chunk = res.data or []
        filas.extend(chunk)
        if len(chunk) < pagina:
            break
        off += pagina
    return filas


def _nombres_cuentas(sb, empresa_id: str) -> dict:
    """{codigo: nombre} del plan de cuentas de la empresa (para reportes)."""
    return {c["codigo"]: c.get("nombre", "") for c in listar_plan_cuentas(sb, empresa_id)}


# ============================================================
# Cálculos PUROS (sin red) — testeables
# ============================================================

def _signed(m) -> int:
    v = int(round(float(m.get("valor") or 0)))
    return v if str(m.get("tr")) == "1" else -v


def _calc_balance_prueba(movs: list[dict], desde: str, hasta: str,
                         nombres: Optional[dict] = None) -> pd.DataFrame:
    nombres = nombres or {}
    cuentas = sorted({m["cuenta"] for m in movs})
    filas = []
    for cta in cuentas:
        ms = [m for m in movs if m["cuenta"] == cta]
        s_ant = sum(_signed(m) for m in ms if m["periodo"] < desde)
        deb = sum(int(m["valor"]) for m in ms if desde <= m["periodo"] <= hasta and str(m["tr"]) == "1")
        cre = sum(int(m["valor"]) for m in ms if desde <= m["periodo"] <= hasta and str(m["tr"]) == "2")
        s_fin = s_ant + deb - cre
        if s_ant == 0 and deb == 0 and cre == 0:
            continue
        filas.append({
            "Cuenta": cta,
            "Nombre": nombres.get(cta, ""),
            "Saldo anterior": s_ant,
            "Débitos": deb,
            "Créditos": cre,
            "Saldo final": s_fin,
        })
    return pd.DataFrame(filas, columns=[
        "Cuenta", "Nombre", "Saldo anterior", "Débitos", "Créditos", "Saldo final",
    ])


def _calc_libro_auxiliar(movs: list[dict], desde: str, hasta: str) -> pd.DataFrame:
    # saldo anterior (antes de 'desde')
    s_ant = sum(_signed(m) for m in movs if m["periodo"] < desde)
    ms = [m for m in movs if desde <= m["periodo"] <= hasta]
    ms.sort(key=lambda m: (m.get("fecha") or "", m.get("comprobante") or "", m.get("documento") or ""))
    filas = []
    saldo = s_ant
    for m in ms:
        deb = int(m["valor"]) if str(m["tr"]) == "1" else 0
        cre = int(m["valor"]) if str(m["tr"]) == "2" else 0
        saldo += deb - cre
        filas.append({
            "Fecha": m.get("fecha"),
            "Comp": m.get("comprobante"),
            "Documento": m.get("documento"),
            "NIT": m.get("nit"),
            "Detalle": m.get("detalle"),
            "Débito": deb,
            "Crédito": cre,
            "Saldo": saldo,
            "C. Costo": m.get("centro_costo"),
        })
    df = pd.DataFrame(filas, columns=[
        "Fecha", "Comp", "Documento", "NIT", "Detalle", "Débito", "Crédito", "Saldo", "C. Costo",
    ])
    return df, s_ant


def _calc_estado_cartera(movs: list[dict], prefijos) -> pd.DataFrame:
    prefijos = tuple(prefijos)
    por_nit = {}
    for m in movs:
        if not str(m["cuenta"]).startswith(prefijos):
            continue
        nit = m.get("nit") or "(sin NIT)"
        por_nit[nit] = por_nit.get(nit, 0) + _signed(m)
    filas = [{"NIT": k, "Saldo cartera": v} for k, v in por_nit.items() if v != 0]
    filas.sort(key=lambda r: -r["Saldo cartera"])
    return pd.DataFrame(filas, columns=["NIT", "Saldo cartera"])


# ============================================================
# Reportes (con red)
# ============================================================

def balance_prueba(sb, empresa_id: str, desde: str, hasta: str) -> pd.DataFrame:
    """Balance de prueba entre dos períodos 'AAAAMM' (inclusive)."""
    movs = _fetch_paginado(sb, empresa_id, "cuenta,periodo,tr,valor", periodo_lte=hasta)
    return _calc_balance_prueba(movs, str(desde), str(hasta), _nombres_cuentas(sb, empresa_id))


def libro_auxiliar(sb, empresa_id: str, cuenta: Optional[str] = None,
                   nit: Optional[str] = None, desde: str = "000000",
                   hasta: str = "999999"):
    """Movimientos detallados con saldo corriente. Filtra por cuenta y/o NIT."""
    extra = {}
    if cuenta:
        extra["cuenta"] = str(cuenta)
    if nit:
        extra["nit"] = str(nit)
    movs = _fetch_paginado(
        sb, empresa_id,
        "cuenta,periodo,fecha,comprobante,documento,doc_referencia,nit,detalle,tr,valor,base,centro_costo",
        periodo_lte=str(hasta), extra_eq=extra or None,
    )
    return _calc_libro_auxiliar(movs, str(desde), str(hasta))


def estado_cartera(sb, empresa_id: str, hasta: str = "999999",
                   prefijos=("13",)) -> pd.DataFrame:
    """Saldo de cartera por tercero (cuentas que empiezan por 'prefijos')."""
    movs = _fetch_paginado(sb, empresa_id, "cuenta,periodo,nit,tr,valor", periodo_lte=str(hasta))
    return _calc_estado_cartera(movs, prefijos)


# ============================================================
# Estados financieros
# ============================================================

CLASES_PUC = {
    "1": "Activo", "2": "Pasivo", "3": "Patrimonio",
    "4": "Ingresos", "5": "Gastos", "6": "Costos de ventas",
    "7": "Costos de producción",
}


def _calc_estado_resultados(movs: list[dict], desde: str, hasta: str):
    ing = gas = cos = 0
    det = {}  # grupo 2 dígitos -> valor
    for m in movs:
        if not (desde <= m["periodo"] <= hasta):
            continue
        cta = str(m["cuenta"])
        cl = cta[:1]
        s = _signed(m)
        if cl == "4":
            ing += -s
        elif cl == "5":
            gas += s
        elif cl in ("6", "7"):
            cos += s
        else:
            continue
        g = cta[:2]
        det[g] = det.get(g, 0) + (-s if cl == "4" else s)
    utilidad = ing - cos - gas
    resumen = pd.DataFrame([
        {"Concepto": "Ingresos (clase 4)", "Valor": ing},
        {"Concepto": "(−) Costos (6, 7)", "Valor": cos},
        {"Concepto": "(−) Gastos (clase 5)", "Valor": gas},
        {"Concepto": "= Utilidad / (Pérdida) del período", "Valor": utilidad},
    ])
    detalle = pd.DataFrame(
        [{"Grupo": g, "Valor": v} for g, v in sorted(det.items())],
        columns=["Grupo", "Valor"],
    )
    return resumen, detalle, {"ingresos": ing, "costos": cos, "gastos": gas, "utilidad": utilidad}


def _calc_balance_general(movs: list[dict], hasta: str):
    anio = str(hasta)[:4]
    inicio_anio = anio + "01"
    activo = pasivo = patrim = 0
    ing = gas = cos = 0
    grupos = {}  # (clase, grupo2) -> saldo presentación
    for m in movs:
        if m["periodo"] > hasta:
            continue
        cta = str(m["cuenta"])
        cl = cta[:1]
        s = _signed(m)
        if cl == "1":
            activo += s
            grupos[("1", cta[:2])] = grupos.get(("1", cta[:2]), 0) + s
        elif cl == "2":
            pasivo += -s
            grupos[("2", cta[:2])] = grupos.get(("2", cta[:2]), 0) + (-s)
        elif cl == "3":
            patrim += -s
            grupos[("3", cta[:2])] = grupos.get(("3", cta[:2]), 0) + (-s)
        # Resultado del ejercicio (año en curso hasta el corte)
        if inicio_anio <= m["periodo"] <= hasta:
            if cl == "4":
                ing += -s
            elif cl == "5":
                gas += s
            elif cl in ("6", "7"):
                cos += s
    utilidad = ing - cos - gas
    pas_pat_util = pasivo + patrim + utilidad
    resumen = pd.DataFrame([
        {"Concepto": "ACTIVO (1)", "Valor": activo},
        {"Concepto": "PASIVO (2)", "Valor": pasivo},
        {"Concepto": "PATRIMONIO (3)", "Valor": patrim},
        {"Concepto": "Utilidad del ejercicio", "Valor": utilidad},
        {"Concepto": "= Pasivo + Patrimonio + Utilidad", "Valor": pas_pat_util},
    ])
    detalle = pd.DataFrame(
        [{"Clase": CLASES_PUC.get(cl, cl), "Grupo": g, "Valor": v}
         for (cl, g), v in sorted(grupos.items())],
        columns=["Clase", "Grupo", "Valor"],
    )
    info = {"activo": activo, "pasivo": pasivo, "patrimonio": patrim,
            "utilidad": utilidad, "cuadra": activo == pas_pat_util,
            "diferencia": activo - pas_pat_util}
    return resumen, detalle, info


def estado_resultados(sb, empresa_id: str, desde: str, hasta: str):
    """Estado de resultados (PyG) entre dos períodos 'AAAAMM'."""
    movs = _fetch_paginado(sb, empresa_id, "cuenta,periodo,tr,valor", periodo_lte=str(hasta))
    return _calc_estado_resultados(movs, str(desde), str(hasta))


def balance_general(sb, empresa_id: str, hasta: str):
    """Balance general acumulado a un corte 'AAAAMM' (con utilidad del año)."""
    movs = _fetch_paginado(sb, empresa_id, "cuenta,periodo,tr,valor", periodo_lte=str(hasta))
    return _calc_balance_general(movs, str(hasta))


# ============================================================
# Libro Mayor y Balances  (libro oficial)
# ============================================================
#
# El "Libro Mayor y Balances" resume, por cuenta, el saldo que traía antes del
# rango (saldo anterior), el movimiento débito y crédito del rango y el saldo
# final. La diferencia con el balance de prueba es que aquí se puede AGREGAR
# a un nivel de cuenta (clase 1 díg, mayor 2, cuenta 4, subcuenta 6…), como lo
# exige el libro oficial.

def _nivel_cuenta(cta, nivel: Optional[int]) -> str:
    s = str(cta)
    return s[:nivel] if nivel else s


def _calc_libro_mayor(movs: list[dict], desde: str, hasta: str,
                      nivel: Optional[int] = None,
                      nombres: Optional[dict] = None) -> pd.DataFrame:
    """Libro mayor por cuenta (opcionalmente agregada a `nivel` dígitos).

    Función PURA. `movs` debe traer todo el histórico <= hasta para que el
    saldo anterior sea correcto.
    """
    nombres = nombres or {}
    acc: dict[str, list[int]] = {}  # cuenta -> [saldo_ant, debitos, creditos]
    for m in movs:
        cta = _nivel_cuenta(m["cuenta"], nivel)
        d = acc.setdefault(cta, [0, 0, 0])
        p = m["periodo"]
        if p < desde:
            d[0] += _signed(m)
        elif desde <= p <= hasta:
            if str(m["tr"]) == "1":
                d[1] += int(m["valor"])
            else:
                d[2] += int(m["valor"])
    filas = []
    for cta in sorted(acc):
        s_ant, deb, cre = acc[cta]
        s_fin = s_ant + deb - cre
        if s_ant == 0 and deb == 0 and cre == 0:
            continue
        filas.append({
            "Cuenta": cta,
            "Nombre": nombres.get(cta, ""),
            "Saldo anterior": s_ant,
            "Débitos": deb,
            "Créditos": cre,
            "Saldo final": s_fin,
        })
    return pd.DataFrame(filas, columns=[
        "Cuenta", "Nombre", "Saldo anterior", "Débitos", "Créditos", "Saldo final",
    ])


def libro_mayor(sb, empresa_id: str, desde: str, hasta: str,
                nivel: Optional[int] = None) -> pd.DataFrame:
    """Libro Mayor y Balances entre dos períodos 'AAAAMM' (inclusive).

    `nivel`: si se da, agrega las cuentas a ese número de dígitos
    (1=clase, 2=grupo/mayor, 4=cuenta, 6=subcuenta). None = cuenta tal como
    está guardada (auxiliar).
    """
    movs = _fetch_paginado(sb, empresa_id, "cuenta,periodo,tr,valor", periodo_lte=str(hasta))
    return _calc_libro_mayor(movs, str(desde), str(hasta), nivel, _nombres_cuentas(sb, empresa_id))


# ============================================================
# Libro Diario / Comprobante de Diario  (impresión del asiento)
# ============================================================
#
# Un comprobante de diario se identifica por (comprobante, documento) dentro de
# un período. Reúne todas las líneas del asiento (débitos y créditos) que deben
# cuadrar Db=Cr. El "libro diario" es la lista cronológica de esos asientos.

def _agrupar_comprobantes(movs: list[dict]) -> list[dict]:
    """Agrupa movimientos por (comprobante, documento) → un asiento por grupo.

    Devuelve la lista ordenada cronológicamente (libro diario) con totales y
    bandera de cuadre por asiento. Función PURA.
    """
    grupos: dict[tuple, dict] = {}
    for m in movs:
        k = (str(m.get("comprobante") or ""), str(m.get("documento") or ""))
        g = grupos.get(k)
        if g is None:
            g = {
                "comprobante": k[0], "documento": k[1],
                "fecha": m.get("fecha"), "detalle": m.get("detalle") or "",
                "debitos": 0, "creditos": 0, "lineas": 0,
            }
            grupos[k] = g
        if str(m.get("tr")) == "1":
            g["debitos"] += int(m["valor"])
        else:
            g["creditos"] += int(m["valor"])
        g["lineas"] += 1
        f = m.get("fecha")
        if f and (not g["fecha"] or f < g["fecha"]):
            g["fecha"] = f
        if not g["detalle"] and m.get("detalle"):
            g["detalle"] = m["detalle"]
    filas = list(grupos.values())
    for g in filas:
        g["cuadra"] = g["debitos"] == g["creditos"]
        g["diferencia"] = g["debitos"] - g["creditos"]
    filas.sort(key=lambda g: (g["fecha"] or "", g["comprobante"], g["documento"]))
    return filas


def _calc_comprobante(movs: list[dict], comprobante: str, documento: str,
                      nombres: Optional[dict] = None):
    """Arma el asiento (comprobante, documento): encabezado, líneas y totales.

    Función PURA. Devuelve (header:dict, detalle:DataFrame, totales:dict).
    Las líneas se ordenan débitos primero (tr=1) y luego por cuenta.
    """
    nombres = nombres or {}
    lineas = [
        m for m in movs
        if str(m.get("comprobante") or "") == str(comprobante)
        and str(m.get("documento") or "") == str(documento)
    ]
    lineas.sort(key=lambda m: (str(m.get("tr")), str(m.get("cuenta"))))
    filas = []
    tot_db = tot_cr = 0
    for m in lineas:
        deb = int(m["valor"]) if str(m["tr"]) == "1" else 0
        cre = int(m["valor"]) if str(m["tr"]) == "2" else 0
        tot_db += deb
        tot_cr += cre
        filas.append({
            "Cuenta": m.get("cuenta"),
            "Nombre": nombres.get(str(m.get("cuenta")), ""),
            "NIT": m.get("nit"),
            "Detalle": m.get("detalle"),
            "C. Costo": m.get("centro_costo"),
            "Débito": deb,
            "Crédito": cre,
        })
    detalle = pd.DataFrame(filas, columns=[
        "Cuenta", "Nombre", "NIT", "Detalle", "C. Costo", "Débito", "Crédito",
    ])
    fecha = next((m.get("fecha") for m in lineas if m.get("fecha")), None)
    header = {
        "comprobante": str(comprobante),
        "documento": str(documento),
        "fecha": fecha,
        "periodo": lineas[0].get("periodo") if lineas else None,
        "detalle": next((m.get("detalle") for m in lineas if m.get("detalle")), ""),
        "lineas": len(lineas),
    }
    totales = {
        "debitos": tot_db, "creditos": tot_cr,
        "diferencia": tot_db - tot_cr, "cuadra": tot_db == tot_cr,
    }
    return header, detalle, totales


def listar_comprobantes_periodo(sb, empresa_id: str, periodo: str,
                                comprobante: Optional[str] = None) -> list[dict]:
    """Libro diario del período: lista de asientos (comprobante, documento)."""
    extra = {"comprobante": str(comprobante)} if comprobante else None
    movs = _fetch_paginado(
        sb, empresa_id, "comprobante,documento,fecha,detalle,tr,valor",
        periodo_gte=str(periodo), periodo_lte=str(periodo), extra_eq=extra,
    )
    return _agrupar_comprobantes(movs)


def comprobante_diario(sb, empresa_id: str, periodo: str,
                       comprobante: str, documento: str):
    """Trae un comprobante de diario completo para imprimir/exportar."""
    movs = _fetch_paginado(
        sb, empresa_id,
        "cuenta,periodo,fecha,comprobante,documento,doc_referencia,nit,detalle,tr,valor,base,centro_costo",
        periodo_gte=str(periodo), periodo_lte=str(periodo),
        extra_eq={"comprobante": str(comprobante), "documento": str(documento)},
    )
    return _calc_comprobante(movs, comprobante, documento, _nombres_cuentas(sb, empresa_id))


# ============================================================
# Terceros (maestro de NITs)
# ============================================================

def listar_terceros(sb, empresa_id: str, query: Optional[str] = None,
                    limit: int = 5000) -> list[dict]:
    q = sb.table("cn_terceros").select("*").eq("empresa_id", empresa_id)
    if query:
        q = q.ilike("nombre", f"%{query}%")
    return q.order("nit").limit(limit).execute().data or []


def obtener_tercero(sb, empresa_id: str, nit: str) -> dict:
    res = (
        sb.table("cn_terceros").select("*")
          .eq("empresa_id", empresa_id).eq("nit", str(nit)).limit(1).execute()
    )
    return (res.data or [{}])[0]


def upsert_tercero(sb, empresa_id: str, nit: str, nombre: str, **campos) -> dict:
    payload = {"empresa_id": empresa_id, "nit": str(nit), "nombre": nombre, **campos}
    res = sb.table("cn_terceros").upsert(payload, on_conflict="empresa_id,nit").execute()
    return (res.data or [{}])[0]


# ============================================================
# Importación de maestros (desde DataFrame / plano)
# ============================================================

def _norm(s: str) -> str:
    """Normaliza un encabezado: minúsculas, sin tildes ni espacios/símbolos."""
    s = str(s).strip().lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        s = s.replace(a, b)
    return "".join(ch for ch in s if ch.isalnum())


def _bool_sn(v) -> bool:
    return str(v).strip().upper() in ("S", "SI", "SÍ", "1", "TRUE", "X", "V")


# Alias de columnas -> campo canónico
_ALIAS_TERCEROS = {
    "nit": "nit", "identificacion": "nit", "cedula": "nit", "documento": "nit",
    "nombre": "nombre", "razonsocial": "nombre", "nombrerazonsocial": "nombre", "tercero": "nombre",
    "tipo": "tipo_persona", "tipopersona": "tipo_persona", "tipodepersona": "tipo_persona",
    "dv": "dv", "digitoverificacion": "dv",
    "regimen": "regimen", "email": "email", "correo": "email",
    "telefono": "telefono", "tel": "telefono",
    "direccion": "direccion", "municipio": "municipio", "ciudad": "municipio",
}

_ALIAS_CUENTAS = {
    "cuenta": "codigo", "codigo": "codigo", "cod": "codigo", "cuentacontable": "codigo",
    "nombre": "nombre", "descripcion": "nombre", "nombrecuenta": "nombre",
    "naturaleza": "naturaleza", "nat": "naturaleza",
    "tipo": "tipo_cuenta", "tipocuenta": "tipo_cuenta",
    "manejanit": "maneja_nit", "nit": "maneja_nit",
    "manejacc": "maneja_cc", "centrocosto": "maneja_cc", "cc": "maneja_cc",
    "manejabase": "maneja_base", "base": "maneja_base",
}


def _mapear_columnas(df: pd.DataFrame, alias: dict, posicional: list[str]) -> pd.DataFrame:
    """Renombra columnas de df a campos canónicos usando alias por nombre; si no
    hay encabezados reconocibles, usa mapeo POSICIONAL (col0, col1, ...)."""
    ren = {}
    for col in df.columns:
        canon = alias.get(_norm(col))
        if canon:
            ren[col] = canon
    if ren:
        out = df.rename(columns=ren)
        # dejar solo columnas canónicas conocidas
        cols = [c for c in out.columns if c in set(alias.values())]
        return out[cols]
    # Sin encabezados reconocibles -> posicional
    out = df.iloc[:, :len(posicional)].copy()
    out.columns = posicional[:out.shape[1]]
    return out


def importar_terceros(sb, empresa_id: str, df: pd.DataFrame, lote: int = 500) -> int:
    """Importa terceros desde un DataFrame. Reconoce columnas por nombre
    (NIT, NOMBRE, TIPO, DV, REGIMEN, EMAIL, TELEFONO, DIRECCION, MUNICIPIO)
    o, si no hay encabezados, asume posición: NIT, NOMBRE, TIPO."""
    m = _mapear_columnas(df, _ALIAS_TERCEROS, ["nit", "nombre", "tipo_persona"])
    filas = []
    for _, r in m.iterrows():
        nit = str(r.get("nit", "")).strip()
        nombre = str(r.get("nombre", "")).strip()
        if not nit or not nombre:
            continue
        fila = {"empresa_id": empresa_id, "nit": nit, "nombre": nombre}
        for c in ("tipo_persona", "dv", "regimen", "email", "telefono", "direccion", "municipio"):
            v = r.get(c)
            if v is not None and str(v).strip() != "":
                fila[c] = str(v).strip()[:1] if c == "tipo_persona" else str(v).strip()
        filas.append(fila)
    total = 0
    for i in range(0, len(filas), lote):
        chunk = filas[i:i + lote]
        sb.table("cn_terceros").upsert(chunk, on_conflict="empresa_id,nit").execute()
        total += len(chunk)
    return total


def importar_cuentas_desde_df(sb, empresa_id: str, df: pd.DataFrame, lote: int = 500) -> int:
    """Importa plan de cuentas desde un DataFrame. Reconoce CODIGO, NOMBRE,
    NATURALEZA, TIPO, MANEJA NIT/CC/BASE; o posición: CODIGO, NOMBRE, NATURALEZA."""
    m = _mapear_columnas(df, _ALIAS_CUENTAS, ["codigo", "nombre", "naturaleza"])
    filas = []
    for _, r in m.iterrows():
        codigo = str(r.get("codigo", "")).strip()
        nombre = str(r.get("nombre", "")).strip()
        if not codigo or not nombre:
            continue
        fila = {"codigo": codigo, "nombre": nombre, "nivel": len(codigo)}
        nat = str(r.get("naturaleza", "")).strip().upper()[:1]
        if nat in ("D", "C"):
            fila["naturaleza"] = nat
        tc = str(r.get("tipo_cuenta", "")).strip().upper()[:1]
        if tc:
            fila["tipo_cuenta"] = tc
        for c in ("maneja_nit", "maneja_cc", "maneja_base"):
            if c in m.columns:
                fila[c] = _bool_sn(r.get(c))
        filas.append(fila)
    return importar_plan_cuentas(sb, empresa_id, filas, lote=lote)


# ============================================================
# Importación de históricos (plano de 11 columnas -> cn_movimientos)
# ============================================================

def importar_movimientos(sb, empresa_id: str, df: pd.DataFrame,
                         origen: str = "importado", user_id: Optional[str] = None,
                         lote: int = 500) -> dict:
    """Importa un plano (DataFrame de 11 columnas) derivando el PERÍODO de la
    FECHA de cada fila (AAAAMM). Crea los períodos faltantes y respeta los
    protegidos (se saltan y se reportan).

    Returns: {insertados, periodos, saltados_protegidos}.
    """
    registros = []
    periodos = set()
    for _, row in df.iterrows():
        f_iso = _fecha_iso(row.get("FECHA"))
        periodo = (f_iso[:4] + f_iso[5:7]) if f_iso else ""
        reg = {"empresa_id": empresa_id, "periodo": periodo, "origen": origen or None}
        for col_plano, col_db in _MAPA_PLANO_DB.items():
            val = row.get(col_plano)
            if col_db == "fecha":
                reg[col_db] = f_iso
            elif col_db in ("valor", "base"):
                reg[col_db] = _int(val)
            else:
                reg[col_db] = None if val is None or str(val) == "" else str(val)
        if user_id:
            reg["creado_por"] = user_id
        registros.append(reg)
        periodos.add(periodo)

    # Crear períodos faltantes (no reabre protegidos por ignore_duplicates)
    for p in sorted(periodos):
        if p:
            crear_periodo(sb, empresa_id, p)

    # Saltar períodos protegidos
    protegidos = {p for p in periodos if p and periodo_protegido(sb, empresa_id, p)}
    a_insertar = [r for r in registros if r["periodo"] not in protegidos]

    total = 0
    for i in range(0, len(a_insertar), lote):
        chunk = a_insertar[i:i + lote]
        sb.table("cn_movimientos").insert(chunk).execute()
        total += len(chunk)

    return {
        "insertados": total,
        "periodos": sorted(p for p in periodos if p),
        "saltados_protegidos": sorted(protegidos),
    }
