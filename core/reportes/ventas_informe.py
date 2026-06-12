"""
Lectura de ventas del INFORME (EEFF "P&G por punto") por centro de costo y mes.

El P&G del informe trae, en cada hoja (Grupo1..4, CDP, Admon, ML...), un bloque
de 10 columnas por punto. La fila "% PARTICIPACION" contiene los códigos de CC
(en el desplazamiento +2 / +4 del bloque); dos filas más abajo está la fila de
meses (ENERO en el inicio del bloque, FEBRERO en +2, MARZO en +4, luego
DIFERENCIA y ACUMULADO que se ignoran). El renglón "Ventas" trae el valor de
ventas y "Devoluciones en ventas" las devoluciones (en negativo).

Devuelve un dict {(cc4, mes_num): {"ventas": x, "devol": y}} donde cc4 es el
código de CC a 4 dígitos (p. ej. "1107") y mes_num ∈ 1..12. El ingreso neto del
mes = ventas + devol (las devoluciones vienen en negativo).
"""
from __future__ import annotations

from typing import Dict, Tuple, Union, IO

from openpyxl import load_workbook

_MES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

_PASO = 10  # ancho del bloque de cada punto


def _num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _mes_de(v) -> Union[int, None]:
    """Devuelve el número de mes si la celda nombra un mes; None si es
    DIFERENCIA, ACUMULADO, vacío u otra cosa."""
    if not v:
        return None
    u = str(v).strip().upper()
    for nombre, num in _MES.items():
        if nombre in u:
            return num
    return None


def cargar_ventas_eeff(archivo: Union[str, IO[bytes]]) -> Dict[Tuple[str, int], Dict[str, float]]:
    """Lee el EEFF y devuelve ventas/devoluciones por (cc4, mes)."""
    wb = load_workbook(archivo, read_only=True, data_only=True)
    ventas: Dict[Tuple[str, int], Dict[str, float]] = {}

    for hoja in wb.sheetnames:
        ws = wb[hoja]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        rp = next((i for i, x in enumerate(rows)
                   if x and x[0] and str(x[0]).strip().upper().startswith("% PARTICIPACION")), None)
        if rp is None or rp + 2 >= len(rows):
            continue
        rv = next((i for i, x in enumerate(rows)
                   if x and x[0] and str(x[0]).strip().lower() == "ventas"), None)
        if rv is None:
            continue
        rd = next((i for i, x in enumerate(rows)
                   if x and x[0] and str(x[0]).strip().lower().startswith("devoluciones")), None)

        fcc = rows[rp]
        fmes = rows[rp + 2]
        fv = rows[rv]
        fd = rows[rd] if rd is not None else None
        ncol = len(fmes)

        # primera columna que nombra un mes -> inicio del primer bloque
        b0 = next((c for c in range(1, ncol) if _mes_de(fmes[c]) is not None), None)
        if b0 is None:
            continue

        b = b0
        while b < ncol:
            # el código de CC del bloque está en +2 (o +4)
            cc = None
            for off in (2, 4):
                if b + off < len(fcc) and fcc[b + off] not in (None, ""):
                    s = str(fcc[b + off]).strip()
                    if s and s[-4:].isdigit():
                        cc = s[-4:]
                        break
            if cc:
                for off in (0, 2, 4, 6, 8):
                    if b + off >= ncol:
                        break
                    mes = _mes_de(fmes[b + off])
                    if mes is None:
                        continue
                    v = _num(fv[b + off]) if b + off < len(fv) else 0.0
                    d = _num(fd[b + off]) if (fd is not None and b + off < len(fd)) else 0.0
                    e = ventas.setdefault((cc, mes), {"ventas": 0.0, "devol": 0.0})
                    e["ventas"] += v
                    e["devol"] += d
            b += _PASO

    return ventas
