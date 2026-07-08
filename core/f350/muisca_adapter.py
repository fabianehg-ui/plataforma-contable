"""
core/f350/muisca_adapter.py
Puente entre el modulo F350 existente y el cliente de Muisca.

Convierte el resultado de `core.f350.procesador.procesar_declaracion(...)`
en {numero_casilla: valor}, que es lo que MuiscaF350Client.construir_doc() necesita.

Usa los mapeos del propio repo:
  - obtener_casillas_f350(concepto, tipo_tercero)  -> retenciones a terceros
    OJO: espera el tipo como texto ("Persona Natural" / "Persona Juridica").
  - AUTORRET_CASILLAS_F350[concepto] -> (base, retencion) para autorretenciones.
"""
from __future__ import annotations

from core.f350.casillas import obtener_casillas_f350, AUTORRET_CASILLAS_F350

# Totales del F350 (Res. 000031/2024)
CASILLA_TOTAL_RENTA = 130
CASILLA_TOTAL_IVA = 134
CASILLA_TOTAL_RETENCIONES = 136
CASILLA_SANCIONES = 137
CASILLA_TOTAL_MAS_SANCIONES = 138


def _tipo_texto(tipo) -> str:
    """Normaliza cualquier variante a lo que espera obtener_casillas_f350:
    exactamente 'Persona Natural' para PN; cualquier otra cosa se trata como PJ."""
    t = str(tipo or "").strip().upper()
    es_natural = t.startswith("PN") or "NATURAL" in t
    return "Persona Natural" if es_natural else "Persona Jurídica"


def casillas_desde_procesado(resultado: dict, incluir_totales: bool = True) -> dict:
    casillas: dict = {}
    avisos: list = []

    def add(cas, valor):
        if not cas or not valor:
            return
        casillas[int(cas)] = casillas.get(int(cas), 0) + int(round(float(valor)))

    # 1) Retenciones practicadas a terceros (base + retencion, por tipo de persona)
    filas = resultado.get("retenciones_agrupadas") or resultado.get("movimientos") or []
    for m in filas:
        concepto = m.get("concepto") or m.get("concepto_f350")
        if not concepto:
            continue
        tipo = m.get("tipo_persona") or m.get("tipo_tercero") or m.get("tipo")
        base = m.get("base") or m.get("base_retencion") or 0
        ret = m.get("retencion") or m.get("valor_retencion") or 0
        es_ext = bool(m.get("es_extranjero", False))
        try:
            cbase, cret = obtener_casillas_f350(concepto, _tipo_texto(tipo), es_ext)
        except Exception as e:  # noqa: BLE001
            avisos.append("Sin casilla para '%s' (%s): %s" % (concepto, tipo, e))
            continue
        if not cret:
            avisos.append("Concepto '%s' no tiene casilla para %s." % (concepto, _tipo_texto(tipo)))
            continue
        add(cbase, base)
        add(cret, ret)

    # 2) Autorretenciones -> AUTORRET_CASILLAS_F350 (NO el mapeo de terceros)
    for a in resultado.get("autorretenciones", []) or []:
        base = a.get("base", 0)
        val = a.get("retencion", 0)
        if not base and not val:
            continue
        concepto = a.get("concepto")
        par = AUTORRET_CASILLAS_F350.get(concepto)
        if not par:
            avisos.append("Autorretencion sin casilla: '%s'." % concepto)
            continue
        cbase, cret = par
        add(cbase, base)
        add(cret, val)

    # 3) Retenciones de IVA (si el procesado las trae con casilla explicita)
    for r in resultado.get("retenciones_iva", []) or []:
        cas = r.get("casilla")
        if cas:
            add(cas, r.get("retencion", 0))

    # 4) Totales
    if incluir_totales:
        tot = resultado.get("totales", {}) or {}
        total_renta = int(round(tot.get("total_retenciones_renta", 0) or 0))
        total_iva = int(round(tot.get("total_retenciones_iva", 0) or 0))
        sanciones = int(round(tot.get("sanciones", 0) or 0))
        if total_renta:
            add(CASILLA_TOTAL_RENTA, total_renta)
        if total_iva:
            add(CASILLA_TOTAL_IVA, total_iva)
        total_ret = total_renta + total_iva
        if total_ret:
            add(CASILLA_TOTAL_RETENCIONES, total_ret)
            if sanciones:
                add(CASILLA_SANCIONES, sanciones)
            add(CASILLA_TOTAL_MAS_SANCIONES, total_ret + sanciones)

    return {"casillas": casillas, "avisos": avisos}
