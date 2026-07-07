"""
core/siigo/web_planos.py
Convierte el listado de MOVIMIENTOS capturado de la web de Siigo (sales_report:
cabecera + total, sin desglose de base/IVA) en planos de Contai.

Con estos datos (docClass, docName, docDate, accountIdentification, accountFullName,
total, isAnnulled) se arma de forma FIABLE:
  - Recibos de caja (Db efectivo / Cr cartera por el total)  -> solo necesita total
  - NITs / terceros (NIT + nombre)
  - Ventas SIMPLE (Db clientes / Cr ventas por el total)  -> correcto solo si NO hay IVA
Para ventas con desglose de IVA hace falta el DETALLE de cada factura (otro endpoint).
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from typing import Optional

TAB, CRLF = "\t", "\r\n"
DOC_ANCHO = 9

MOV_HEADER = ["CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
              "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO"]
NIT_HEADER = ["NIT", "Tipo", "Nombre", "Direccion", "Ciudad", "Telefono", "Municipio",
              "Activo", "Tiene RUT", "Pais", "Primer Nombre", "Segundo Nombre",
              "Primer Apellido", "Segundo Apellido", "Email", "Celular", "Plazo",
              "Actividad Económica", "Indicativo", "Naturaleza"]
PAIS_COLOMBIA = "169"


def _entero(v) -> str:
    import math
    try:
        return str(int(math.floor(abs(float(v or 0)) + 0.5)))
    except (TypeError, ValueError):
        return "0"


# Campos con dos convenciones: sales_report (minuscula) y getreport (PascalCase).
_CAMPOS = {
    "docClass": ("docClass", "DocClass"),
    "docName": ("docName", "DocName"),
    "docDate": ("docDate", "DocDate"),
    "total": ("total", "TotalValue", "Total"),
    "nit": ("accountIdentification", "Identification", "nit"),
    "nombre": ("accountFullName", "AccountName", "fullName"),
    "anulada": ("isAnnulled", "IsAnnulled"),
}


def _g(row: dict, campo: str):
    for k in _CAMPOS.get(campo, (campo,)):
        if k in row:
            return row[k]
    return None


def extraer_filas(j):
    """Devuelve la lista de movimientos de cualquiera de las formas capturadas:
    {rows:[...]}, {data:{Value:{Table:[...]}}}, o una lista directa."""
    if isinstance(j, list):
        return j
    if isinstance(j, dict):
        if isinstance(j.get("rows"), list):
            return j["rows"]

        def find_arr(o, depth=0):
            if depth > 8:
                return None
            if isinstance(o, list):
                return o if (o and isinstance(o[0], dict)) else None
            if isinstance(o, dict):
                for v in o.values():
                    r = find_arr(v, depth + 1)
                    if r is not None:
                        return r
            return None
        return find_arr(j) or []
    return []


def _clean(v) -> str:
    s = "" if v is None else str(v)
    for ch in ("\t", "\r", "\n"):
        s = s.replace(ch, " ")
    return s.strip()


def _fecha(iso) -> str:
    s = (str(iso) or "")[:10]
    p = s.split("-")
    return f"{p[1]}/{p[2]}/{p[0]}" if len(p) == 3 else ""


def _prefijo(doc_name: str) -> str:
    d = str(doc_name or "")
    return d.rsplit("-", 1)[0] if "-" in d else d


def _num(doc_name: str) -> str:
    return str(doc_name or "").replace("-", "").rjust(DOC_ANCHO, "0")


def _resolver(prefijo: str, mapeo: Optional[dict]) -> dict:
    p = (prefijo or "").strip().upper()
    if mapeo and p in mapeo:
        return {"comprobante": (mapeo[p].get("comprobante") or "").strip() or "REVISAR",
                "centro": (mapeo[p].get("centro") or "").strip()}
    return {"comprobante": "REVISAR", "centro": ""}


def facturas(rows: list) -> list:
    return [r for r in rows or [] if _g(r, "docClass") == "FV" and not _g(r, "anulada")]


def prefijos_de(rows: list) -> list:
    c = Counter(_prefijo(_g(r, "docName")) for r in facturas(rows))
    return [{"prefix": k, "count": v} for k, v in sorted(c.items())]


def _ordenar(rows: list) -> list:
    return sorted(rows, key=lambda r: (str(_g(r, "docDate") or "")[:10], _num(_g(r, "docName"))))


# ── Recibos de caja (cancelar todo, por el total) ────────────────────
def build_recibos(rows, consecutivo_inicial, mapeo=None,
                  cuenta_efectivo="11050503", cuenta_cartera="13050502", comprobante="1") -> dict:
    try:
        cons = max(1, round(float(consecutivo_inicial or 1)))
    except (TypeError, ValueError):
        cons = 1
    inicio = cons
    lines = [TAB.join(MOV_HEADER)]
    n = 0
    for r in _ordenar(facturas(rows)):
        total = float(_g(r, "total") or 0)
        if total <= 0:
            continue
        fecha = _fecha(_g(r, "docDate"))
        nit = _g(r, "nit") or ""
        centro = _resolver(_prefijo(_g(r, "docName")), mapeo)["centro"]
        doc = str(cons).rjust(DOC_ANCHO, "0")
        fact = _num(_g(r, "docName"))
        det = _clean(f"Recaudo factura {_g(r, 'docName')}")
        lines.append(TAB.join([cuenta_efectivo, comprobante, fecha, doc, doc, nit, det, "1", _entero(total), "", centro]))
        lines.append(TAB.join([cuenta_cartera, comprobante, fecha, doc, fact, nit, det, "2", _entero(total), "", centro]))
        cons += 1
        n += 1
    rango = {"desde": inicio, "hasta": inicio + n - 1, "count": n} if n else {"desde": inicio, "hasta": inicio, "count": 0}
    return {"content": CRLF.join(lines) + CRLF, "rango": rango}


# ── Ventas SIMPLE (por el total; correcto solo sin IVA) ──────────────
def build_ventas_simple(rows, mapeo=None, cuenta_clientes="13050502", cuenta_ventas="41359503") -> str:
    lines = [TAB.join(MOV_HEADER)]
    for r in facturas(rows):
        total = float(_g(r, "total") or 0)
        if total <= 0:
            continue
        fecha = _fecha(_g(r, "docDate"))
        nit = _g(r, "nit") or ""
        res = _resolver(_prefijo(_g(r, "docName")), mapeo)
        comp, centro = res["comprobante"], res["centro"]
        doc = _num(_g(r, "docName"))
        det = _clean(f"Venta {_g(r, 'docName')}")
        lines.append(TAB.join([cuenta_clientes, comp, fecha, doc, doc, nit, det, "1", _entero(total), "", centro]))
        lines.append(TAB.join([cuenta_ventas, comp, fecha, doc, doc, nit, det, "2", _entero(total), "", centro]))
    return CRLF.join(lines) + CRLF


# ── NITs / terceros (NIT + nombre, deduplicado) ──────────────────────
def build_terceros(rows) -> str:
    vistos = OrderedDict()
    for r in rows or []:
        nit = str(_g(r, "nit") or "").strip()
        if not nit or nit in vistos:
            continue
        vistos[nit] = _clean(_g(r, "nombre"))
    lines = [TAB.join(NIT_HEADER)]
    for nit, nombre in vistos.items():
        try:
            es_jur = int(nit) >= 800000000
        except ValueError:
            es_jur = False
        fila = [nit, "D" if es_jur else "C", nombre, "", "", "", "", "S", "N", PAIS_COLOMBIA,
                "", "", "", "", "", "", "0", "", "", "J" if es_jur else "N"]
        lines.append(TAB.join(fila))
    return CRLF.join(lines) + CRLF
