"""
core/f350/mapeo_f350.py
Convierte las cuentas de retención de Contai en valores por CASILLA del
Formulario 350 (2026), separando persona jurídica y natural.

Casillas (retención practicada a título de renta) — instructivo DIAN 2026:
  Honorarios 42/95 · Comisiones 43/96 · Servicios 44/97 · Rend. financieros 45/98 ·
  Arrendamientos 46/99 · Regalías 47/100 · Dividendos 48/101 · Compras 49/102 ·
  Tarjetas 50/103 · Construcción 51/104 · Loterías 52/106 · Minería 53/107 ·
  Otros 54/108 · Rentas de trabajo (nat) 93.
Cada tupla es (concepto, casilla_juridica, casilla_natural).
Ajusta este diccionario a tu plan de cuentas Contai si usas otros códigos.
"""
from __future__ import annotations

import re

MAPEO_CUENTAS = {
    "23-65-15-02": ("Honorarios", 42, 95),
    "23-65-25-01": ("Servicios", 44, 97),
    "23-65-25-02": ("Servicios", 44, 97),
    "23-65-25-03": ("Servicios (fletes/transporte de carga)", 44, 97),
    "23-65-25-06": ("Regalías / propiedad intelectual (software)", 47, 100),  # REVISAR: ¿regalías, servicios u otros?
    "23-65-30-01": ("Arrendamientos", 46, 99),
    "23-65-40-04": ("Compras", 49, 102),
}

_MARCAS_JUR = re.compile(r'\b(S\.?A\.?S?|LTDA|E\.?U|S\.?C\.?A|& ?CIA)\b', re.I)
_PALABRAS_JUR = ("GRUPO", "INVERSION", "SERVI", "COMERCIA", "RESTO", "CAFE",
                 "DESARROLLO", "SANEAMIENTO", "TRANSACCIO", "RAPPI", "SAPHETY")


def es_juridica(nit: str, nombre: str) -> bool:
    n = (nombre or "").upper()
    if _MARCAS_JUR.search(n) or any(w in n for w in _PALABRAS_JUR):
        return True
    s = str(nit)
    return len(s) == 9 and s[:1] in "89"   # NIT de empresa (heurística; verificar dudosos)


def calcular_casillas(cuentas: list, overrides_tipo: dict | None = None) -> dict:
    """Devuelve {'casillas': {num: valor}, 'detalle': [...], 'total': x}.
    overrides_tipo: {nit: 'J'|'N'} para forzar el tipo de persona de un tercero."""
    overrides_tipo = overrides_tipo or {}
    casillas, detalle = {}, []
    for c in cuentas:
        concepto, cj, cn = MAPEO_CUENTAS.get(c["cuenta"], (c["nombre_cta"], 54, 108))
        for x in c["lineas"]:
            forced = overrides_tipo.get(x["nit"])
            jur = (forced == "J") if forced else es_juridica(x["nit"], x["nombre"])
            cas = cj if jur else cn
            casillas[cas] = casillas.get(cas, 0) + x["ret"]
            detalle.append({"concepto": concepto, "tipo": "Jurídica" if jur else "Natural",
                            "casilla": cas, "nit": x["nit"], "nombre": x["nombre"], "retencion": x["ret"]})
    casillas = {k: int(round(v)) for k, v in casillas.items()}
    return {"casillas": casillas, "detalle": detalle, "total": sum(casillas.values())}
