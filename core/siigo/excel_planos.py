"""
core/siigo/excel_planos.py
Convierte el Excel "Movimiento ventas y compras" exportado de Siigo (que SÍ trae
el detalle: base, IVA por tarifa y retenciones por concepto) en planos de Contai,
con el asiento contable completo. Es la vía para empresas SIN API.

Estructura del Excel: filas de encabezado arriba; luego por documento hay varias
filas 'Secuencia' (renglones con base/IVA/retención) y una 'Formas de pago' (total).
"""
from __future__ import annotations

from collections import defaultdict, OrderedDict

import openpyxl

TAB, CRLF, ANCHO, PAIS = "\t", "\r\n", 9, "169"
MOV = ["CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA", "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO"]
NITH = ["NIT", "Tipo", "Nombre", "Direccion", "Ciudad", "Telefono", "Municipio", "Activo", "Tiene RUT", "Pais",
        "Primer Nombre", "Segundo Nombre", "Primer Apellido", "Segundo Apellido", "Email", "Celular", "Plazo",
        "Actividad Económica", "Indicativo", "Naturaleza"]


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _ent(v):
    import math
    return str(int(math.floor(abs(_num(v)) + 0.5)))


def _clean(v):
    s = "" if v is None else str(v)
    for ch in ("\t", "\r", "\n"):
        s = s.replace(ch, " ")
    return s.strip()


def _fecha(v):
    s = str(v or "")[:10]
    if "-" in s:
        p = s.split("-")
        if len(p) == 3:
            return f"{p[1]}/{p[2]}/{p[0]}"
    if "/" in s:
        return s
    return ""


def leer_excel(path_or_file) -> list:
    """Devuelve una lista de documentos agregados:
    {tipo, prefijo, consecutivo, nit, tercero, fecha, centro,
     base_by_iva{label:val}, iva_by{label:val}, ret_by{label:val}, total_pagar}."""
    wb = openpyxl.load_workbook(path_or_file, read_only=True, data_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hi = next(i for i, r in enumerate(rows) if r and any(str(c) == "Tipo transacción" for c in r))
    H = [str(c) if c is not None else "" for c in rows[hi]]

    def idx(name):
        for i, h in enumerate(H):
            if h.strip().startswith(name):
                return i
        return -1

    c = {k: idx(v) for k, v in {
        "tipo": "Tipo transacción", "comp": "Número comprobante", "cons": "Consecutivo",
        "nit": "Identificación", "terc": "Nombre tercero", "centro": "Centro costo",
        "fecha": "Fecha elaboración", "reg": "Tipo de registro", "cant": "Cantidad",
        "vu": "Valor unitario", "desc": "Valor desc", "ivaL": "Impuesto cargo",
        "retL": "Impuesto retención", "total": "Total",
    }.items()}
    c["ivaV"] = c["ivaL"] + 1
    c["retV"] = c["retL"] + 1

    docs = OrderedDict()
    for r in rows[hi + 1:]:
        if not r or r[c["tipo"]] is None:
            continue
        tt = str(r[c["tipo"]])
        if tt.startswith("Procesado"):
            continue
        key = (tt, str(r[c["comp"]]), str(r[c["cons"]]))
        if key not in docs:
            docs[key] = {
                "tipo": tt, "prefijo": str(r[c["comp"]] or ""), "consecutivo": str(r[c["cons"]] or ""),
                "nit": _clean(r[c["nit"]]), "tercero": _clean(r[c["terc"]]),
                "fecha": _fecha(r[c["fecha"]]), "centro": _clean(r[c["centro"]]),
                "base_by_iva": defaultdict(float), "iva_by": defaultdict(float),
                "ret_by": defaultdict(float), "total_pagar": 0.0,
            }
        d = docs[key]
        reg = str(r[c["reg"]])
        if reg == "Secuencia":
            base = _num(r[c["vu"]]) * (_num(r[c["cant"]]) or 1) - _num(r[c["desc"]])
            il = str(r[c["ivaL"]] or "SIN IVA"); rl = str(r[c["retL"]] or "").strip()
            d["base_by_iva"][il] += base
            d["iva_by"][il] += _num(r[c["ivaV"]])
            if rl:
                d["ret_by"][rl] += _num(r[c["retV"]])
        elif reg == "Formas de pago":
            d["total_pagar"] += _num(r[c["total"]])

    out = []
    for d in docs.values():
        if not d["total_pagar"]:
            d["total_pagar"] = sum(d["base_by_iva"].values()) + sum(d["iva_by"].values()) - sum(d["ret_by"].values())
        out.append(d)
    return out


def _es_nc(tipo):
    t = (tipo or "").lower()
    return "nota" in t or "crédito" in t or "credito" in t


def resumen(docs) -> dict:
    pref = sorted({d["prefijo"] for d in docs})
    ivas = sorted({k for d in docs for k in d["base_by_iva"].keys()})
    rets = sorted({k for d in docs for k in d["ret_by"].keys()})
    return {"prefijos": pref, "ivas": ivas, "retenciones": rets,
            "facturas": sum(1 for d in docs if not _es_nc(d["tipo"])),
            "notas": sum(1 for d in docs if _es_nc(d["tipo"]))}


def _comp_centro(d, mapeo):
    e = (mapeo or {}).get(d["prefijo"], {})
    return (e.get("comprobante") or "REVISAR"), (e.get("centro") or d.get("centro") or "")


def _ref(d):
    return (d["consecutivo"] or "").rjust(ANCHO, "0")


def build_ventas(docs, mapeo, cuentas) -> dict:
    """Asiento completo: Db cartera / Db retenciones / Cr ventas por tarifa / Cr IVA por tarifa.
    La cartera se calcula como (base + IVA - retención) ya redondeados, para que
    cada documento cuadre exactamente al peso."""
    ctas = cuentas or {}
    cta_cartera = ctas.get("cartera", "13050502")
    ventas = ctas.get("ventas", {}); iva = ctas.get("iva", {}); reten = ctas.get("retencion", {})
    L = [TAB.join(MOV)]
    faltan = set()
    tot_db = tot_cr = 0
    n = 0
    for d in docs:
        if _es_nc(d["tipo"]):
            continue
        comp, centro = _comp_centro(d, mapeo)
        ref = _ref(d); fecha = d["fecha"]; nit = d["nit"]; det = _clean("Venta " + d["prefijo"] + "-" + d["consecutivo"])
        cr_doc = 0
        cr_lines = []  # (cuenta, detalle, valor)
        for il, base in d["base_by_iva"].items():
            bv = int(round(base)); cta = ventas.get(il)
            if not cta: faltan.add("ventas " + il)
            cr_lines.append((cta or "VENTAS?", "Base " + il, bv)); cr_doc += bv
        for il, val in d["iva_by"].items():
            iv = int(round(val))
            if iv <= 0:
                continue
            cta = iva.get(il)
            if not cta: faltan.add("IVA " + il)
            cr_lines.append((cta or "IVA?", il, iv)); cr_doc += iv
        ret_lines = []
        ret_total = 0
        for rl, val in d["ret_by"].items():
            rv = int(round(val)); cta = reten.get(rl)
            if not cta: faltan.add("retención " + rl)
            ret_lines.append((cta or "RETENCION?", rl, rv)); ret_total += rv
        cartera = cr_doc - ret_total  # = total a pagar, cuadra exacto
        # Débitos
        L.append(TAB.join([cta_cartera, comp, fecha, ref, ref, nit, det, "1", str(cartera), "", centro]))
        for cta, dl, val in ret_lines:
            L.append(TAB.join([cta, comp, fecha, ref, ref, nit, _clean(dl), "1", str(val), "", centro]))
        # Créditos
        for cta, dl, val in cr_lines:
            L.append(TAB.join([cta, comp, fecha, ref, ref, nit, _clean(dl), "2", str(val), "", centro]))
        tot_db += cartera + ret_total
        tot_cr += cr_doc
        n += 1
    return {"content": CRLF.join(L) + CRLF, "count": n, "db": tot_db, "cr": tot_cr,
            "cuadra": tot_db == tot_cr, "faltan": sorted(faltan)}


def build_recibos(docs, consecutivo_inicial, mapeo, cuenta_efectivo="11050503", cuenta_cartera="13050502", comprobante="1") -> dict:
    try:
        cons = max(1, round(float(consecutivo_inicial or 1)))
    except (TypeError, ValueError):
        cons = 1
    inicio = cons; L = [TAB.join(MOV)]; n = 0
    for d in sorted((x for x in docs if not _es_nc(x["tipo"])), key=lambda x: (x["fecha"], _ref(x))):
        total = d["total_pagar"]
        if total <= 0:
            continue
        _, centro = _comp_centro(d, mapeo)
        doc = str(cons).rjust(ANCHO, "0"); ref = _ref(d); fecha = d["fecha"]; nit = d["nit"]
        det = _clean("Recaudo factura " + d["prefijo"] + "-" + d["consecutivo"])
        L.append(TAB.join([cuenta_efectivo, comprobante, fecha, doc, doc, nit, det, "1", _ent(total), "", centro]))
        L.append(TAB.join([cuenta_cartera, comprobante, fecha, doc, ref, nit, det, "2", _ent(total), "", centro]))
        cons += 1; n += 1
    return {"content": CRLF.join(L) + CRLF, "count": n, "desde": inicio, "hasta": inicio + n - 1}


def build_terceros(docs) -> str:
    vistos = OrderedDict()
    for d in docs:
        nit = (d["nit"] or "").strip()
        if not nit or nit in vistos:
            continue
        vistos[nit] = d["tercero"]
    L = [TAB.join(NITH)]
    for nit, nombre in vistos.items():
        try:
            jur = int(nit) >= 800000000
        except ValueError:
            jur = False
        L.append(TAB.join([nit, "D" if jur else "C", nombre, "", "", "", "", "S", "N", PAIS,
                           "", "", "", "", "", "", "0", "", "", "J" if jur else "N"]))
    return CRLF.join(L) + CRLF
