"""
Ajuste PILA -> gasto (dentro del comprobante de PROVISIÓN, comp 9).

Objetivo (regla del usuario):
    Cruzar, por cada concepto, la diferencia entre lo que quedó acreditado al
    PASIVO en la contabilidad del mes (causación nómina + provisión + vacaciones)
    y lo que realmente cobra la PILA del mes, ajustándola contra el GASTO del
    concepto (gasto pensión, gasto EPS, gasto ARL, gasto caja) con un débito o
    crédito según el caso, hasta dejar el pasivo del mes = saldo PILA.

Mecánica por concepto:
    contable = créditos al pasivo del concepto − débitos (movimiento neto del mes)
    diferencia = PILA − contable
        diferencia > 0  (falta pasivo):  Db GASTO / Cr PASIVO   por la diferencia
        diferencia < 0  (sobra pasivo):  Db PASIVO / Cr GASTO   por la diferencia
    Cada ajuste es autobalanceado (pasivo vs gasto), así el plano sigue cuadrado.

Las cuentas de PASIVO por concepto son las que ya usa procesador_nomina
(coinciden con el árbol 25-50 de Contai). Las cuentas de GASTO se reciben como
parámetro porque dependen del PUC real de la empresa (en especial el gasto EPS,
que no existe en la provisión por estar exonerada del 8,5% patronal).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd

from core.procesadores.procesador_nomina import (
    COLUMNAS_PLANO,
    COMPROBANTE_PROVISION,
    _formato_fecha_plano,  # noqa: F401  (reutilizamos formato si se pasa date)
)


# Definición de conceptos: pasivo(s) contable(s) y a cuál se ajusta.
CONCEPTOS_PILA = [
    {
        "key": "pension",
        "nombre": "Fondo de pensión",
        "pasivo": ["25503001", "25503002"],   # provisión patronal + deducción trabajador
        "pasivo_ajuste": "25503001",
        "gasto_default": "510470",             # gasto pensión (ADMIN)
        "pila_attr": "aportes_pension",
    },
    {
        "key": "salud",
        "nombre": "EPS / Salud",
        "pasivo": ["25500502", "25500501"],    # deducción trabajador (+ prov. si hubiera)
        "pasivo_ajuste": "25500502",
        "gasto_default": "",                   # exonerada: no hay gasto EPS en la provisión
        "pila_attr": "aportes_salud",
    },
    {
        "key": "arl",
        "nombre": "ARL / Riesgos",
        "pasivo": ["25500601"],
        "pasivo_ajuste": "25500601",
        "gasto_default": "510468",             # gasto ARL (ADMIN)
        "pila_attr": "aportes_riesgos",
    },
    {
        "key": "caja",
        "nombre": "Caja de compensación",
        "pasivo": ["25501001"],
        "pasivo_ajuste": "25501001",
        "gasto_default": "510472",             # gasto caja (ADMIN)
        "pila_attr": "aportes_cajas",
    },
]


def gastos_default() -> Dict[str, str]:
    """Cuentas de gasto por defecto (del módulo de nómina)."""
    return {c["key"]: c["gasto_default"] for c in CONCEPTOS_PILA}


def _neto_credito(df: pd.DataFrame, cuentas: List[str]) -> int:
    """Movimiento neto acreditado (Cr − Db) del mes para esas cuentas de pasivo."""
    cuentas = [str(c) for c in cuentas]
    sub = df[df["CUENTA"].astype(str).isin(cuentas)]
    if len(sub) == 0:
        return 0
    cr = pd.to_numeric(sub[sub["TR"].astype(str) == "2"]["VALOR"], errors="coerce").fillna(0).sum()
    db = pd.to_numeric(sub[sub["TR"].astype(str) == "1"]["VALOR"], errors="coerce").fillna(0).sum()
    return int(round(cr - db))


def conciliar(
    df_mes: pd.DataFrame,
    pila_por_concepto: Dict[str, int],
) -> List[dict]:
    """Devuelve la conciliación por concepto (sin generar líneas todavía).

    Cada item: {key, nombre, pila, contable, diferencia, pasivo_ajuste}.
    """
    filas = []
    for c in CONCEPTOS_PILA:
        pila_v = int(round(pila_por_concepto.get(c["key"], 0)))
        contable_v = _neto_credito(df_mes, c["pasivo"])
        filas.append({
            "key": c["key"],
            "nombre": c["nombre"],
            "pila": pila_v,
            "contable": contable_v,
            "diferencia": pila_v - contable_v,
            "pasivo_ajuste": c["pasivo_ajuste"],
        })
    return filas


def generar_ajuste_pila(
    df_mes: pd.DataFrame,
    pila_por_concepto: Dict[str, int],
    gasto_por_concepto: Dict[str, str],
    fecha: str = "",
    documento: str = "",
    comprobante: Optional[str] = None,
    nit: str = "",
    centro_costo: str = "",
) -> Tuple[pd.DataFrame, List[dict]]:
    """Genera las líneas de ajuste PILA (comp provisión) y la conciliación.

    Args:
        df_mes: plano del mes ANTES del ajuste (nómina + provisión + vacaciones).
        pila_por_concepto: {'pension':v, 'salud':v, 'arl':v, 'caja':v} desde la PILA.
        gasto_por_concepto: {'pension':cuenta, 'salud':cuenta, 'arl':cuenta, 'caja':cuenta}.
        fecha: MM/DD/AAAA.
        documento: consecutivo (por defecto el mismo de la provisión).
        comprobante: por defecto COMPROBANTE_PROVISION (comp 9).
        nit, centro_costo: opcionales.

    Returns:
        (df_ajuste, conciliacion). df_ajuste puede venir vacío si todo cuadra
        o si falta la cuenta de gasto de algún concepto (se marca en la
        conciliación con 'sin_gasto': True).
    """
    comp = str(comprobante if comprobante is not None else COMPROBANTE_PROVISION)
    conc = conciliar(df_mes, pila_por_concepto)
    filas: List[dict] = []

    def _fila(cuenta, tr, valor, detalle, base=0):
        return {
            "CUENTA": str(cuenta),
            "COMPROBANTE": comp,
            "FECHA": fecha,
            "DOCUMENTO": str(documento),
            "DOC REFERENCIA": str(documento),
            "NIT": str(nit),
            "DETALLE": detalle,
            "TR": tr,
            "VALOR": int(valor),
            "BASE": int(base),
            "CENTRO DE COSTO": centro_costo,
        }

    for item in conc:
        diff = item["diferencia"]
        gasto = str(gasto_por_concepto.get(item["key"], "") or "").strip()
        item["gasto"] = gasto
        item["sin_gasto"] = (diff != 0 and not gasto)
        item["ajustado"] = False
        if diff == 0 or not gasto:
            continue
        val = abs(diff)
        pasivo = item["pasivo_ajuste"]
        detalle = f"AJUSTE PILA {item['nombre'].upper()}"
        if diff > 0:
            # Falta pasivo: Db gasto / Cr pasivo
            filas.append(_fila(gasto, "1", val, detalle))
            filas.append(_fila(pasivo, "2", val, detalle))
        else:
            # Sobra pasivo: Db pasivo / Cr gasto
            filas.append(_fila(pasivo, "1", val, detalle))
            filas.append(_fila(gasto, "2", val, detalle))
        item["ajustado"] = True

    df_aj = pd.DataFrame(filas, columns=COLUMNAS_PLANO)
    return df_aj, conc
