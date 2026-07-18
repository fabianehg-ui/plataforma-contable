"""
core/contable/integracion.py

Puente contable ÚNICO de INTEGRAL: cn_movimientos es el libro central y cada
módulo o ESCRIBE (causa su plano) o LEE de la contabilidad.

- contabilizar(): cualquier módulo pasa su plano de 11 columnas y queda causado
  en cn_movimientos con un período elegido y una etiqueta `origen`.
- resumen_por_origen() / reversar_origen(): trazabilidad y deshacer por módulo.
- retenciones_practicadas(): lee la 2365 de cn_movimientos por NIT y concepto
  (para alimentar la Retención en la Fuente / F350 / exógena 1003).

Así, conectar un módulo nuevo = generar su plano y llamar a contabilizar()
(o usar el componente ui_contabilizar.render_contabilizar).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from core.contable import servicio_contable as cont


# Etiquetas de origen (de dónde viene cada causación)
ORIGENES = {
    "nomina": "Nómina",
    "nomina_mes": "Nómina (mes)",
    "vacaciones": "Vacaciones / Liquidaciones",
    "ajuste_pila": "Ajuste PILA",
    "ventas": "Ventas C13",
    "pos": "Ingresos POS",
    "compras": "Compras y Egresos",
    "bancos": "Bancos",
    "bittal": "Bittal",
    "dian_xml": "DIAN XML",
    "siigo": "Siigo",
    "captura": "Captura manual",
    "importado": "Importado",
    "correccion": "Corrección",
    "pago": "Pagos (egreso)",
    "recaudo": "Recaudos (recibo de caja)",
}


def etiqueta_origen(origen: str) -> str:
    return ORIGENES.get(str(origen), str(origen or "—"))


# ============================================================
# Cuadre de un plano (PURO)
# ============================================================

def cuadre_plano(df: pd.DataFrame) -> dict:
    """{debitos, creditos, diferencia, cuadra, lineas} de un plano de 11 col."""
    if df is None or len(df) == 0:
        return {"debitos": 0, "creditos": 0, "diferencia": 0, "cuadra": True, "lineas": 0}
    d = df.copy()
    tr = d["TR"].astype(str)
    val = pd.to_numeric(d["VALOR"], errors="coerce").fillna(0).astype(int)
    db = int(val[tr == "1"].sum())
    cr = int(val[tr == "2"].sum())
    return {"debitos": db, "creditos": cr, "diferencia": db - cr,
            "cuadra": db == cr, "lineas": int(len(d))}


def plano_texto_a_df(contenido) -> pd.DataFrame:
    """Convierte un plano de texto Contai (TSV, SIN encabezado) — bytes o str —
    a un DataFrame de 11 columnas. Sirve para causar planos que los módulos
    generan como texto/bytes (Bittal, Bancos, etc.)."""
    if contenido is None:
        return pd.DataFrame(columns=cont.COLUMNAS_PLANO)
    if isinstance(contenido, (bytes, bytearray)):
        try:
            contenido = contenido.decode("utf-8")
        except UnicodeDecodeError:
            contenido = contenido.decode("latin-1")
    lineas = [l for l in str(contenido).splitlines()
              if l.strip() and not l.lower().startswith("sep=")]
    if lineas and "CUENTA" in lineas[0].upper():   # quitar encabezado si viene
        lineas = lineas[1:]
    filas = [l.split("\t") for l in lineas]
    df = pd.DataFrame(filas)
    if df.empty:
        return pd.DataFrame(columns=cont.COLUMNAS_PLANO)
    df = df.iloc[:, :11]
    df.columns = cont.COLUMNAS_PLANO[:df.shape[1]]
    return df.fillna("")


# ============================================================
# ESCRIBIR — causar el plano de un módulo en cn_movimientos
# ============================================================

def contabilizar(sb, empresa_id: str, periodo: str, df_plano: pd.DataFrame,
                 origen: str, user_id: Optional[str] = None,
                 reemplazar: bool = False, crear_periodo: bool = True) -> dict:
    """Causa el plano de un módulo en cn_movimientos.

    Args:
        periodo: 'AAAAMM'.
        origen: etiqueta del módulo (clave de ORIGENES).
        reemplazar: borra primero lo de ese (periodo, origen) — evita duplicar
                    al reprocesar el mismo módulo/mes.
        crear_periodo: crea el período si no existe (no reabre uno protegido).
    Returns: {insertados, periodo, origen, cuadre}.
    Raises: PermissionError si el período está protegido.
    """
    if crear_periodo:
        cont.crear_periodo(sb, empresa_id, str(periodo))
    n = cont.guardar_plano(
        sb, empresa_id, str(periodo), df_plano,
        origen=origen, user_id=user_id, reemplazar=reemplazar,
    )
    return {"insertados": n, "periodo": str(periodo), "origen": origen,
            "cuadre": cuadre_plano(df_plano)}


# ============================================================
# TRAZABILIDAD — qué causó cada módulo y deshacer por módulo
# ============================================================

def resumen_por_origen(sb, empresa_id: str, periodo: str) -> list[dict]:
    """Por cada origen del período: líneas, débitos, créditos y cuadre."""
    movs = cont.listar_movimientos(sb, empresa_id, str(periodo))
    grupos: dict = {}
    for m in movs:
        o = m.get("origen") or "—"
        g = grupos.setdefault(o, {"origen": o, "etiqueta": etiqueta_origen(o),
                                  "lineas": 0, "debitos": 0, "creditos": 0})
        g["lineas"] += 1
        v = int(m.get("valor") or 0)
        if str(m.get("tr")) == "1":
            g["debitos"] += v
        else:
            g["creditos"] += v
    filas = list(grupos.values())
    for g in filas:
        g["diferencia"] = g["debitos"] - g["creditos"]
        g["cuadra"] = g["debitos"] == g["creditos"]
    filas.sort(key=lambda x: x["etiqueta"])
    return filas


def reversar_origen(sb, empresa_id: str, periodo: str, origen: str) -> None:
    """Borra todo lo causado por un módulo en un período (respeta protegido)."""
    if cont.periodo_protegido(sb, empresa_id, str(periodo)):
        raise PermissionError(f"El período {periodo} está PROTEGIDO; no se puede reversar.")
    cont.eliminar_movimientos(sb, empresa_id, str(periodo), origen=origen)


# ============================================================
# LEER — alimentar módulos desde la contabilidad
# ============================================================

def _signed(m) -> int:
    v = int(round(float(m.get("valor") or 0)))
    return v if str(m.get("tr")) == "1" else -v


def retenciones_practicadas(sb, empresa_id: str, desde: str, hasta: str,
                            prefijos=("2365",)) -> pd.DataFrame:
    """Retenciones que la empresa PRACTICÓ (cuenta 2365…) por NIT y subcuenta
    (= concepto), leídas de cn_movimientos. Alimenta el F350 / exógena 1003.

    El valor de la retención = saldo CRÉDITO de la cuenta (Cr − Db).
    """
    prefijos = tuple(str(p) for p in prefijos)
    movs = cont._fetch_paginado(
        sb, empresa_id, "cuenta,periodo,nit,detalle,tr,valor,base",
        periodo_gte=str(desde), periodo_lte=str(hasta))
    filas: dict = {}
    for m in movs:
        cta = str(m.get("cuenta") or "")
        if not cta.startswith(prefijos):
            continue
        nit = m.get("nit") or "(sin NIT)"
        key = (nit, cta)
        g = filas.setdefault(key, {"NIT": nit, "Cuenta": cta, "Retención": 0, "Base": 0})
        g["Retención"] += -_signed(m)              # Cr − Db
        g["Base"] += int(m.get("base") or 0)
    out = [g for g in filas.values() if g["Retención"] != 0]
    out.sort(key=lambda r: (r["Cuenta"], r["NIT"]))
    return pd.DataFrame(out, columns=["NIT", "Cuenta", "Base", "Retención"])


def movimientos_cuenta(sb, empresa_id: str, cuenta_prefijo: str,
                       desde: str, hasta: str) -> pd.DataFrame:
    """Movimientos de las cuentas que empiezan por `cuenta_prefijo` en el rango.
    Útil para que cualquier módulo lea saldos/base de la contabilidad."""
    movs = cont._fetch_paginado(
        sb, empresa_id, "cuenta,periodo,fecha,nit,detalle,tr,valor,base",
        periodo_gte=str(desde), periodo_lte=str(hasta))
    pref = str(cuenta_prefijo)
    filas = [m for m in movs if str(m.get("cuenta") or "").startswith(pref)]
    return pd.DataFrame(filas)
