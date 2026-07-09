"""
core/f350/vista_formulario.py
Arma la vista del F350 tal como se ve en el portal: cada concepto con sus
casillas de base y retención (jurídica / natural), autorretenciones y totales.

No duplica lógica: usa los mapeos del repo (casillas.py) y el dict {casilla: valor}
que ya produce muisca_adapter.casillas_desde_procesado().
"""
from __future__ import annotations

from core.f350.casillas import (
    MAPEO_CASILLAS_F350,
    AUTORRET_CASILLAS_F350,
    CONCEPTOS_ORDEN_F350,
)

TOTALES = [
    (129, "Menos retenciones en exceso o indebidas"),
    (130, "Total retenciones renta y complementario"),
    (131, "A responsables del impuesto sobre las ventas"),
    (132, "Practicadas por servicios a no residentes"),
    (133, "Menos retenciones IVA en exceso o indebidas"),
    (134, "Total retenciones IVA"),
    (135, "Retenciones impuesto timbre nacional"),
    (136, "Total retenciones"),
    (137, "Sanciones"),
    (138, "Total retenciones más sanciones"),
]


def _v(casillas: dict, num) -> int:
    if not num:
        return 0
    return int(casillas.get(int(num), 0) or 0)


def filas_retenciones(casillas: dict, solo_con_valor: bool = False) -> list:
    """Una fila por concepto, en el orden del formulario, con las 4 casillas."""
    filas = []
    for concepto in CONCEPTOS_ORDEN_F350:
        m = MAPEO_CASILLAS_F350.get(concepto, {})
        bj, rj = m.get("PJ", (None, None))
        bn, rn = m.get("PN", (None, None))
        fila = {
            "Concepto": concepto,
            "Base PJ": _v(casillas, bj), "Cas.": bj or "",
            "Retención PJ": _v(casillas, rj), "Cas. ": rj or "",
            "Base PN": _v(casillas, bn), "Cas.  ": bn or "",
            "Retención PN": _v(casillas, rn), "Cas.   ": rn or "",
        }
        if solo_con_valor and not any([fila["Base PJ"], fila["Retención PJ"], fila["Base PN"], fila["Retención PN"]]):
            continue
        filas.append(fila)
    return filas


def filas_autorretenciones(casillas: dict, solo_con_valor: bool = False) -> list:
    filas = []
    for concepto, (cb, cr) in AUTORRET_CASILLAS_F350.items():
        fila = {"Concepto": concepto, "Cas. base": cb, "Base": _v(casillas, cb),
                "Cas. ret.": cr, "Autorretención": _v(casillas, cr)}
        if solo_con_valor and not (fila["Base"] or fila["Autorretención"]):
            continue
        filas.append(fila)
    return filas


def filas_totales(casillas: dict) -> list:
    return [{"Casilla": n, "Concepto": txt, "Valor": _v(casillas, n)} for n, txt in TOTALES]


def verificacion(casillas: dict, tolerancia: int = 1000) -> dict:
    """Chequeos de consistencia antes de subir al portal.
    La DIAN aproxima los valores al múltiplo de mil más cercano, así que se
    admite una diferencia de hasta `tolerancia` pesos por renglón redondeado."""
    avisos = []
    suma_renta = 0
    for concepto in CONCEPTOS_ORDEN_F350:
        m = MAPEO_CASILLAS_F350.get(concepto, {})
        suma_renta += _v(casillas, m.get("PJ", (None, None))[1]) + _v(casillas, m.get("PN", (None, None))[1])
    suma_auto = sum(_v(casillas, cr) for _, (_, cr) in AUTORRET_CASILLAS_F350.items())

    def dif(a, b):
        return abs(a - b)

    esperado_130 = suma_renta + suma_auto - _v(casillas, 129)
    if dif(_v(casillas, 130), esperado_130) > tolerancia:
        avisos.append(f"Casilla 130 ({_v(casillas,130):,}) ≠ retenciones + autorretenciones − 129 ({esperado_130:,}).")
    esperado_136 = _v(casillas, 130) + _v(casillas, 134) + _v(casillas, 135)
    if dif(_v(casillas, 136), esperado_136) > tolerancia:
        avisos.append(f"Casilla 136 ({_v(casillas,136):,}) ≠ 130 + 134 + 135 ({esperado_136:,}).")
    esperado_138 = _v(casillas, 136) + _v(casillas, 137)
    if dif(_v(casillas, 138), esperado_138) > tolerancia:
        avisos.append(f"Casilla 138 ({_v(casillas,138):,}) ≠ 136 + 137 ({esperado_138:,}).")
    return {"ok": not avisos, "avisos": avisos,
            "total_renta": suma_renta, "total_autorret": suma_auto}
