"""
core/f350/muisca_adapter.py
Puente entre el módulo F350 existente y el cliente de Muisca.

Toma el resultado de `core.f350.procesador.procesar_declaracion(...)`
—que ya usa parser_contai, clasificador, nit_utils.inferir_tipo_persona,
casillas y autorretencion— y lo convierte en {numero_casilla: valor},
que es lo que MuiscaF350Client.construir_doc() necesita.

No duplica lógica: reutiliza `obtener_casillas_f350()` del propio módulo.
"""
from __future__ import annotations

from core.f350.casillas import obtener_casillas_f350


def _casilla_de(concepto: str, tipo_persona: str | None = None):
    """Devuelve el número de casilla para un concepto (y tipo de persona si aplica).
    `obtener_casillas_f350` es la fuente de verdad del repo."""
    try:
        c = obtener_casillas_f350(concepto, tipo_persona) if tipo_persona else obtener_casillas_f350(concepto)
    except TypeError:
        c = obtener_casillas_f350(concepto)
    if isinstance(c, dict):
        # p.ej. {"juridica": 42, "natural": 95} o {"retencion": 42, "base": ...}
        if tipo_persona:
            k = "juridica" if str(tipo_persona).upper().startswith(("J", "PJ")) else "natural"
            return c.get(k) or c.get("retencion")
        return c.get("retencion") or next(iter(c.values()), None)
    return c


def casillas_desde_procesado(resultado: dict) -> dict:
    """
    Entrada: dict devuelto por procesar_declaracion().
    Salida: {"casillas": {n: valor}, "avisos": [...]}
    Suma: retenciones de renta (por concepto y tipo de persona),
          autorretenciones y retenciones de IVA, según lo que traiga el resultado.
    """
    casillas: dict[int, int] = {}
    avisos: list[str] = []

    def add(cas, valor):
        if not cas or not valor:
            return
        casillas[int(cas)] = casillas.get(int(cas), 0) + int(round(float(valor)))

    # 1) Movimientos clasificados (cada uno con concepto, tipo_persona y retención)
    for m in resultado.get("movimientos", []) or []:
        concepto = m.get("concepto") or m.get("concepto_f350")
        tipo = m.get("tipo_persona") or m.get("tipo")
        ret = m.get("retencion") or m.get("valor_retencion") or 0
        cas = m.get("casilla") or _casilla_de(concepto, tipo)
        if not cas:
            avisos.append(f"Sin casilla para el concepto '{concepto}' ({tipo}).")
            continue
        add(cas, ret)

    # 2) Si el resultado ya trae retenciones agrupadas, úsalas cuando no hubo movimientos
    if not casillas:
        for r in resultado.get("retenciones_agrupadas", []) or []:
            concepto = r.get("concepto")
            tipo = r.get("tipo_persona")
            cas = r.get("casilla") or _casilla_de(concepto, tipo)
            if not cas:
                avisos.append(f"Sin casilla para '{concepto}'.")
                continue
            add(cas, r.get("retencion", 0))

    # 3) Autorretenciones (incluye 114-1 / Ventas)
    for a in resultado.get("autorretenciones", []) or []:
        val = a.get("retencion", 0)
        if not val:
            continue
        cas = a.get("casilla") or _casilla_de(a.get("concepto"))
        if not cas:
            avisos.append(f"Sin casilla para autorretención '{a.get('concepto')}'.")
            continue
        add(cas, val)

    # 4) Retenciones de IVA, si el procesado las trae
    for r in resultado.get("retenciones_iva", []) or []:
        cas = r.get("casilla") or _casilla_de(r.get("concepto"), r.get("tipo_persona"))
        add(cas, r.get("retencion", 0))

    return {"casillas": casillas, "avisos": avisos}
