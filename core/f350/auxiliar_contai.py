"""
core/f350/auxiliar_contai.py
Lee el PDF "Análisis de % de Retención e IVA - Resumido" de Contai y devuelve,
por cada cuenta de retención (23-65-xx-xx), sus líneas: NIT, nombre, base,
retención y tarifa.
"""
from __future__ import annotations

import re

import pdfplumber

_RX_CTA = re.compile(r'^\s*(\d{2}-\d{2}-\d{2}-\d{2})\s+(.+?)\s*$')
_RX_DET = re.compile(r'([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d.]+)\s+(\d{6,})\s+(.+?)\s*$')


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def parse_auxiliar(ruta_pdf: str) -> list:
    txt = ""
    with pdfplumber.open(ruta_pdf) as pdf:
        for pg in pdf.pages:
            txt += (pg.extract_text() or "") + "\n"

    cuentas, cta = [], None
    for l in txt.splitlines():
        m = _RX_CTA.match(l)
        if m and "Total" not in l:
            cta = {"cuenta": m.group(1), "nombre_cta": m.group(2).strip(), "lineas": []}
            cuentas.append(cta)
            continue
        if cta:
            d = _RX_DET.search(l)
            if d:
                cta["lineas"].append({
                    "ret": _num(d.group(1)), "base": _num(d.group(2)),
                    "tarifa": float(d.group(3)), "nit": d.group(4), "nombre": d.group(5).strip(),
                })
    return [c for c in cuentas if c["lineas"]]
