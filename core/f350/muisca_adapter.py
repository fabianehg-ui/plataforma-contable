"""
core/f350/muisca_adapter.py
Puente entre el modulo F350 existente y el cliente de Muisca.

Toma el resultado de `core.f350.procesador.procesar_declaracion(...)`
--que ya usa parser_contai, clasificador, nit_utils.inferir_tipo_persona,
casillas y autorretencion-- y lo convierte en {numero_casilla: valor},
que es lo que MuiscaF350Client.construir_doc() necesita.

Reutiliza `obtener_casillas_f350(concepto, tipo_tercero)` del propio modulo
(firma con DOS argumentos obligatorios), y llena tanto las casillas de BASE
como las de RETENCION, igual que el PDF que genera el modulo.
"""
from __future__ import annotations

from core.f350.casillas import obtener_casillas_f350

# Totales del F350 v10 (Res. 000031/2024).
CASILLA_TOTAL_RENTA = 130
CASILLA_TOTAL_IVA = 134
CASILLA_TOTAL_RETENCIONES = 136
CASILLA_SANCIONES = 137
CASILLA_TOTAL_MAS_SANCIONES = 138


def _norm_tipo(tipo) -> str:
    t = str(tipo or "").strip().upper()
    if t.startswith("PJ") or t.startswith("J") or "JURI" in t:
        return "PJ"
    return "PN"


def _par_casillas(concepto, tipo_tercero):
    """Devuelve (casilla_base, casilla_retencion)."""
    c = obtener_casillas_f350(concepto, _norm_tipo(tipo_tercero))
    if isinstance(c, dict):
        return c.get("base"), c.get("retencion")
    if isinstance(c, (tuple, list)):
        return (c[0], c[1]) if len(c) >= 2 else (None, c[0])
    return None, c


def casillas_desde_procesado(resultado: dict, incluir_totales: bool = True) -> dict:
    casillas = {}
    avisos = []

    def add(cas, valor):
        if not cas or not valor:
            return
        casillas[int(cas)] = casillas.get(int(cas), 0) + int(round(float(valor)))

    # 1) Retenciones de renta
    filas = resultado.get("retenciones_agrupadas") or resultado.get("movimientos") or []
    for m in filas:
        concepto = m.get("concepto") or m.get("concepto_f350")
        tipo = m.get("tipo_persona") or m.get("tipo_tercero") or m.get("tipo")
        base = m.get("base") or m.get("base_retencion") or 0
        ret = m.get("retencion") or m.get("valor_retencion") or 0
        if not concepto:
            continue
        try:
            cbase, cret = _par_casillas(concepto, tipo)
        except Exception as e:  # noqa: BLE001
            avisos.append("Sin casilla para '%s' (%s): %s" % (concepto, tipo, e))
            continue
        if not cret:
            avisos.append("Sin casilla de retencion para '%s' (%s)." % (concepto, tipo))
            continue
        add(cbase, base)
        add(cret, ret)

    # 2) Autorretenciones (114-1 / Ventas / ...)
    for a in resultado.get("autorretenciones", []) or []:
        val = a.get("retencion", 0)
        base = a.get("base", 0)
        if not val and not base:
            continue
        concepto = a.get("concepto")
        try:
            cbase, cret = _par_casillas(concepto, "PJ")
        except Exception as e:  # noqa: BLE001
            avisos.append("Sin casilla para autorretencion '%s': %s" % (concepto, e))
            continue
        add(cbase, base)
        add(cret, val)

    # 3) Retenciones de IVA
    for r in resultado.get("retenciones_iva", []) or []:
        try:
            _, cret = _par_casillas(r.get("concepto"), r.get("tipo_persona"))
            add(cret, r.get("retencion", 0))
        except Exception:  # noqa: BLE001
            avisos.append("Sin casilla para reteIVA '%s'." % r.get("concepto"))

    # 4) Totales
    if incluir_totales:
        tot = resultado.get("totales", {}) or {}
        total_renta = int(round(tot.get("total_retenciones_renta", 0) or 0))
        total_iva = int(round(tot.get("total_retenciones_iva", 0) or 0))
        if total_renta:
            add(CASILLA_TOTAL_RENTA, total_renta)
        if total_iva:
            add(CASILLA_TOTAL_IVA, total_iva)
        total_ret = total_renta + total_iva
        if total_ret:
            add(CASILLA_TOTAL_RETENCIONES, total_ret)
            add(CASILLA_TOTAL_MAS_SANCIONES, total_ret + int(round(tot.get("sanciones", 0) or 0)))

    return {"casillas": casillas, "avisos": avisos}
