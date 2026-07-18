"""
core/contable/dv.py

Dígito de verificación (DV) del NIT — algoritmo oficial DIAN, portado del
add-in de Excel de Contai (csUtilidades.FnDigitoVer) y verificado contra 16
NITs reales.

    digito_verificacion("800197268") -> 4
"""
from __future__ import annotations

# Pesos por posición (de derecha a izquierda), tabla oficial DIAN.
_PESOS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]


def digito_verificacion(nit) -> int:
    """DV (0..9) de un NIT/cédula. Ignora puntos, guiones y espacios."""
    dig = "".join(ch for ch in str(nit) if ch.isdigit())[-15:]
    if not dig:
        return 0
    s = sum(_PESOS[i] * int(d) for i, d in enumerate(reversed(dig)))
    r = s % 11
    return r if r in (0, 1) else 11 - r


def nit_con_dv(nit) -> str:
    """'800197268' -> '800197268-4'."""
    dig = "".join(ch for ch in str(nit) if ch.isdigit())
    return f"{dig}-{digito_verificacion(dig)}" if dig else ""


def dv_valido(nit, dv) -> bool:
    """True si `dv` coincide con el calculado para `nit`."""
    try:
        return int(str(dv).strip()) == digito_verificacion(nit)
    except (ValueError, TypeError):
        return False
