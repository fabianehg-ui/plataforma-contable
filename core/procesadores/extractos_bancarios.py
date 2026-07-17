"""
core/procesadores/extractos_bancarios.py
Lee extractos bancarios en PDF (Bancolombia, Banco de Bogota, BBVA), clasifica
los gastos bancarios y arma el plano de Contai repartiendo entre centros de costo.

Validado con mayo 2026 (JIPER): las 12 cuentas de los 3 bancos cuadran exacto
contra el total que declara cada extracto.
"""
from __future__ import annotations

import re
from collections import defaultdict

import pdfplumber

# ---------------------------------------------------------------- configuración
BANCOS = [
    {
        "nombre": "BANCOLOMBIA",
        "detectar": "IMPTO GOBIERNO 4X1000",          # texto del CUERPO, unico de este banco
        "nit": "890903938",
        "cuenta_puc": "11100501",
        "patron": r'(\d{1,2}/\d{2})\s+(.+?)\s+(-[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})(?!\d)',
        "g_desc": 2, "g_valor": 3,
    },
    {
        "nombre": "BANCO DE BOGOTA",
        "detectar": "Cobro 4x1.000 GMF",
        "nit": "860002964",
        "cuenta_puc": "11100502",
        "patron": r'(\d{2}/\d{2})\s+(\w{4})\s+(.+?)\s+(-[\d,]+\.\d{2})\s+([\d,]+\.\d{2})(?!\d)',
        "g_desc": 3, "g_valor": 4,
    },
    {
        "nombre": "BBVA",
        "detectar": "CARGO POR IMPUESTO 4X1.000",
        "nit": "860003020",
        "cuenta_puc": "11100503",
        "patron": r'(\d{4})\s+\d{2}-\d{2}-\d{4}\s+\d{2}-\d{2}-\d{4}\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})(?!\d)',
        "g_desc": 2, "g_valor": 3,
    },
]

# palabra clave -> (cuenta, detalle). El ORDEN manda: gana la primera que coincida.
REGLAS = [
    (r'4X1\.?000|4 ?POR ?MIL|IMPTO GOBIERNO', "53059501", "GRAVAMEN 4X1000"),
    (r'\bIVA\b',                              "53050502", "IVA GASTOS BANCARIOS"),
    (r'COMISION|COMIS\b',                     "53051501", "COMISIONES"),
    (r'SERVICIO PAGO|CUOTA ?(DE )?MANEJO|C MANEJO|SERV TRANS EFECTIVO|SERVICIO ADMON|SERV ADMON',
                                              "53050501", "GASTOS BANCARIOS"),
]
CUENTA_IVA = "53050502"
DIVISOR_IVA = 0.19


# ---------------------------------------------------------------------- lectura
def _normaliza(t: str) -> str:
    """Colapsa espacios pero CONSERVA los saltos: el patron usa '.' que no cruza
    el salto, asi cada movimiento queda dentro de su renglon. Si se unieran las
    lineas, los encabezados de pagina se mezclarian con los movimientos."""
    t = t.replace("\t", " ").replace("\r", "\n")
    return re.sub(r'[ ]{2,}', ' ', t)


def texto_pdf(archivo) -> str:
    partes = []
    with pdfplumber.open(archivo) as pdf:
        for pg in pdf.pages:
            partes.append(pg.extract_text() or "")
    return _normaliza("\n".join(partes))


def detectar_banco(texto: str):
    """Gana el banco cuya clave aparece MAS veces: un extracto de Bancolombia
    menciona 'BBVA' en pagos interbancarios, por eso no basta la 1a coincidencia."""
    mejor, mejor_n = None, 0
    for b in BANCOS:
        n = len(re.findall(re.escape(b["detectar"]), texto, re.I))
        if n > mejor_n:
            mejor, mejor_n = b, n
    return mejor, mejor_n


def clasificar(desc: str):
    for pat, cta, det in REGLAS:
        if re.search(pat, desc, re.I):
            return cta, det
    return None, None


def leer_extracto(archivo) -> dict:
    """Devuelve {'banco', 'movimientos': [...], 'sin_clasificar': n, 'total_capturado'}."""
    texto = texto_pdf(archivo)
    banco, hits = detectar_banco(texto)
    if not banco:
        return {"banco": None, "movimientos": [], "sin_clasificar": 0, "total_capturado": 0.0}

    movs, sin, total = [], 0, 0.0
    for m in re.finditer(banco["patron"], texto):
        g = m.groups()
        desc = g[banco["g_desc"] - 1].strip()
        valor = abs(float(g[banco["g_valor"] - 1].replace(",", "")))
        total += valor
        cta, det = clasificar(desc)
        if cta:
            movs.append({"banco": banco["nombre"], "ref": g[0], "descripcion": desc,
                         "valor": valor, "cuenta": cta, "detalle": det})
        else:
            sin += 1
    return {"banco": banco, "movimientos": movs, "sin_clasificar": sin,
            "total_capturado": total, "coincidencias": hits}


# ----------------------------------------------------------------------- resumen
def resumen(movimientos: list) -> dict:
    """{banco: {cuenta: valor}} + totales."""
    r = defaultdict(lambda: defaultdict(float))
    for m in movimientos:
        r[m["banco"]][m["cuenta"]] += m["valor"]
    return {b: dict(c) for b, c in r.items()}


# ------------------------------------------------------------------------ plano
MOV = ["CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
       "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO"]


def _repartir(total: float, n: int) -> list:
    """Divide en n partes iguales (enteros); el residuo va al ultimo centro."""
    t = int(round(total))
    base = t // n
    partes = [base] * n
    partes[-1] += t - base * n
    return partes


def build_plano(movimientos: list, centros: list, comprobante="10", documento="1",
                fecha="05/31/2026", divisor_iva=DIVISOR_IVA) -> dict:
    """Cada gasto lleva el NIT de SU banco; el credito va a la cuenta PUC del banco."""
    nit = {b["nombre"]: b["nit"] for b in BANCOS}
    puc = {b["nombre"]: b["cuenta_puc"] for b in BANCOS}
    det = {}
    for m in movimientos:
        det[m["cuenta"]] = m["detalle"]

    res = resumen(movimientos)
    n = len(centros)
    L = [MOV]
    total_db = total_cr = 0
    for banco in res:
        tot_banco = 0
        for cta, val in sorted(res[banco].items()):
            if round(val) == 0:
                continue
            vals = _repartir(val, n)
            bases = _repartir(round(val / divisor_iva), n) if cta == CUENTA_IVA else [None] * n
            for cc, v, b in zip(centros, vals, bases):
                L.append([cta, comprobante, fecha, documento, documento, nit[banco],
                          f"{det[cta]} {banco}", "1", v, b if b else "", cc])
                total_db += v
                tot_banco += v
        if tot_banco:
            L.append([puc[banco], comprobante, fecha, documento, documento, nit[banco],
                      f"GASTOS BANCARIOS {banco}", "2", tot_banco, "", ""])
            total_cr += tot_banco
    return {"filas": L, "debitos": total_db, "creditos": total_cr,
            "cuadra": total_db == total_cr}


def plano_a_texto(filas: list) -> str:
    return "\r\n".join("\t".join(str(x) for x in f) for f in filas) + "\r\n"
