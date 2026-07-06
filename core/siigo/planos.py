"""
core/siigo/planos.py
Formatea los datos de Siigo hacia los planos de Contai (TXT tab-delimitado, CRLF).

Portado 1:1 de la extensión (contai-format.js). Incluye:
  - Detección de prefijos y de bases/impuestos (plan de cuentas).
  - Plano de VENTAS: modo flexible (plan de cuentas) o legado (una cuenta).
  - Plano de RECIBOS: 'cancelar todo' (usa el saldo `balance`; omite saldo 0) y
    'desde Siigo' (reproduce los vouchers asentados).
  - Plano de NITs / terceros.
"""
from __future__ import annotations

import math
from typing import Optional

TAB = "\t"
CRLF = "\r\n"

# ── Config por defecto (modo legado, empresa de servicios de salud) ──
VENTAS = {
    "cuentaClientes": "13050502",   # CLIENTES NACIONALES (débito)
    "cuentaVentas": "41659503",     # SERVICIOS (crédito)
    "cuentasImpuesto": {},          # sin IVA en salud
    "comprobanteCentro": {          # comprobante Contai -> centro (sin guion)
        "04FEB": "1004",  # Bogotá
        "04FEP": "1003",  # Palmas
        "04FER": "1002",  # Rionegro
        "004FE": "1005",  # Envigado (genérico)
    },
    "prefijoComprobante": {         # prefijo electrónico Siigo -> comprobante Contai
        "FESD": "004FE",
        "FEBO": "04FEB",
        "RIFE": "04FER",
        "PAFE": "04FEP",
    },
    "comprobanteSinMapear": "REVISAR",
    "nitEnVentas": True,
}

RECIBO = {
    "comprobante": "1",                       # comprobante Contai de recibos de caja
    "cuentaCaja": "11050503",                 # CAJA (débito / contrapartida)
    "cuentaCartera": VENTAS["cuentaClientes"],  # 13050502 (crédito, cancela cartera)
    "docAncho": 9,
}

DOC_ANCHO = 9

MOV_HEADER = [
    "CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
    "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO",
]

NIT_HEADER = [
    "NIT", "Tipo", "Nombre", "Direccion", "Ciudad", "Telefono", "Municipio",
    "Activo", "Tiene RUT", "Pais", "Primer Nombre", "Segundo Nombre",
    "Primer Apellido", "Segundo Apellido", "Email", "Celular", "Plazo",
    "Actividad Económica", "Indicativo", "Naturaleza",
]
PAIS_COLOMBIA = "169"

ETIQUETA_BASE = {
    "BASE_19": "Base gravada 19%",
    "BASE_5": "Base gravada 5%",
    "BASE_GRAVADA": "Base gravada (otra tarifa)",
    "BASE_NO_GRAVADA": "Base no gravada / exenta (0%)",
    "BASE_EXCLUIDA": "Base excluida",
}
ORDEN_BASE = ["BASE_19", "BASE_5", "BASE_GRAVADA", "BASE_NO_GRAVADA", "BASE_EXCLUIDA"]


# ── Helpers ──────────────────────────────────────────────────────────
def _num(v) -> float:
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _entero(v) -> str:
    # round half up sobre el valor absoluto (como Math.round(Math.abs(...)) en JS)
    return str(int(math.floor(abs(_num(v)) + 0.5)))


def _clean(v) -> str:
    s = "" if v is None else str(v)
    for ch in ("\t", "\r", "\n"):
        s = s.replace(ch, " ")
    return s.strip()


def _iso_parts(iso):
    s = (str(iso) if iso else "")[:10]
    parts = s.split("-")
    y = parts[0] if len(parts) > 0 else ""
    m = parts[1] if len(parts) > 1 else ""
    d = parts[2] if len(parts) > 2 else ""
    return y, m, d


def _fecha_mmddyyyy(iso) -> str:
    y, m, d = _iso_parts(iso)
    return f"{m}/{d}/{y}" if y else ""


def _fecha_yyyymmdd(iso) -> str:
    y, m, d = _iso_parts(iso)
    return f"{y}{m}{d}" if y else ""


def _numero_factura(inv) -> str:
    pref = str(inv.get("prefix") or "").strip()
    numero = str(inv.get("number") or "").strip()
    s = f"{pref}{numero}" if (pref or numero) else str(inv.get("name") or "")
    return s.rjust(DOC_ANCHO, "0")


# ── Prefijos ─────────────────────────────────────────────────────────
def sugerencia_prefijo(prefijo: str) -> dict:
    p = str(prefijo or "").strip().upper()
    comp = VENTAS["prefijoComprobante"].get(p, "")
    centro = VENTAS["comprobanteCentro"].get(comp, "") if comp else ""
    return {"comprobante": comp, "centro": centro}


def prefijos_de(invoices: list) -> list:
    conteo: dict = {}
    for inv in invoices or []:
        p = str(inv.get("prefix") or "").strip().upper()
        if not p:
            continue
        conteo[p] = conteo.get(p, 0) + 1
    out = []
    for prefix in sorted(conteo):
        s = sugerencia_prefijo(prefix)
        out.append({"prefix": prefix, "count": conteo[prefix], **s})
    return out


def _resolver_prefijo(prefijo: str, mapeo: Optional[dict]) -> dict:
    p = str(prefijo or "").strip().upper()
    if mapeo and p in mapeo:
        comp = (mapeo[p].get("comprobante") or "").strip() or VENTAS["comprobanteSinMapear"]
        return {"comprobante": comp, "centro": str(mapeo[p].get("centro") or "").strip()}
    comp = VENTAS["prefijoComprobante"].get(p, VENTAS["comprobanteSinMapear"])
    return {"comprobante": comp, "centro": VENTAS["comprobanteCentro"].get(comp, "")}


# ── Clasificación de bases / impuestos ───────────────────────────────
def _es_iva(t) -> bool:
    return "IVA" in f"{t.get('type') or ''} {t.get('name') or ''}".upper()


def _pct(t):
    try:
        return float(t.get("percentage"))
    except (TypeError, ValueError):
        return None


def _categoria_base(item) -> str:
    ivas = [t for t in (item.get("taxes") or []) if _es_iva(t)]
    if not ivas:
        return "BASE_EXCLUIDA"
    pct = None
    for t in ivas:
        p = _pct(t)
        if p is not None:
            pct = p
            break
    if pct == 19:
        return "BASE_19"
    if pct == 5:
        return "BASE_5"
    if pct == 0:
        return "BASE_NO_GRAVADA"
    return "BASE_GRAVADA"


def _cat_de_tarifa(pct):
    if pct == 19:
        return "BASE_19"
    if pct == 5:
        return "BASE_5"
    if pct == 0:
        return "BASE_NO_GRAVADA"
    return None


def _fmt_pct(pct):
    if pct is None:
        return ""
    return str(int(pct)) if float(pct).is_integer() else f"{pct:g}"


def _grupo_impuesto(t) -> dict:
    tipo = str(t.get("type") or t.get("name") or "IMP").upper()
    pct = _pct(t)
    key = f"{tipo}|{_fmt_pct(pct)}"
    label = tipo if pct is None else f"{tipo} {_fmt_pct(pct)}%"
    return {"key": key, "label": label, "tipo": tipo, "percentage": pct}


def detectar_plan(invoices: list) -> dict:
    bases = set()
    taxes: dict = {}
    for inv in invoices or []:
        for it in inv.get("items") or []:
            bases.add(_categoria_base(it))
            for t in it.get("taxes") or []:
                if not _num(t.get("value")):
                    continue
                g = _grupo_impuesto(t)
                prev = taxes.get(g["key"])
                taxes[g["key"]] = {**g, "count": (prev["count"] if prev else 0) + 1}
    return {
        "bases": [{"cat": b, "label": ETIQUETA_BASE[b]} for b in ORDEN_BASE if b in bases],
        "taxes": sorted(taxes.values(), key=lambda x: x["label"]),
    }


def etiqueta_base(cat: str) -> str:
    return ETIQUETA_BASE.get(cat, cat)


# ── Plano de VENTAS ──────────────────────────────────────────────────
def _rows_ventas_legado(invoices, mapeo):
    rows = []
    for inv in invoices or []:
        fecha = _fecha_mmddyyyy(inv.get("date"))
        nit = (inv.get("customer") or {}).get("identification") or ""
        nit_v = nit if VENTAS["nitEnVentas"] else ""
        r = _resolver_prefijo(inv.get("prefix"), mapeo)
        comp, centro = r["comprobante"], r["centro"]
        doc = _numero_factura(inv)
        detalle = _clean(f"Venta {inv.get('name') or inv.get('number') or ''}")

        base = 0.0
        imp: dict = {}
        for it in inv.get("items") or []:
            base += _num(it.get("price")) * _num(it.get("quantity")) - _num((it.get("discount") or {}).get("value"))
            for t in it.get("taxes") or []:
                tipo = t.get("type") or t.get("name") or "IMP"
                imp[tipo] = imp.get(tipo, 0.0) + _num(t.get("value"))
        total_imp = sum(imp.values())
        debito = base + total_imp

        rows.append([VENTAS["cuentaClientes"], comp, fecha, doc, doc, nit, detalle, "1", _entero(debito), "", centro])
        rows.append([VENTAS["cuentaVentas"], comp, fecha, doc, doc, nit_v, detalle, "2", _entero(base), "", centro])
        for tipo, valor in imp.items():
            if not valor:
                continue
            cuenta = VENTAS["cuentasImpuesto"].get(tipo, "")
            rows.append([cuenta, comp, fecha, doc, doc, nit_v, f"{tipo} - {detalle}", "2", _entero(valor), _entero(base), centro])
    return rows


def _rows_ventas_flex(invoices, mapeo, plan):
    rows = []
    bases = plan.get("bases") or {}
    impuestos = plan.get("impuestos") or {}
    for inv in invoices or []:
        fecha = _fecha_mmddyyyy(inv.get("date"))
        nit = (inv.get("customer") or {}).get("identification") or ""
        nit_v = nit if VENTAS["nitEnVentas"] else ""
        r = _resolver_prefijo(inv.get("prefix"), mapeo)
        comp, centro = r["comprobante"], r["centro"]
        doc = _numero_factura(inv)
        detalle = _clean(f"Venta {inv.get('name') or inv.get('number') or ''}")

        base_por_cat: dict = {}
        imp_por_grupo: dict = {}
        for it in inv.get("items") or []:
            base_item = _num(it.get("price")) * _num(it.get("quantity")) - _num((it.get("discount") or {}).get("value"))
            cat = _categoria_base(it)
            base_por_cat[cat] = base_por_cat.get(cat, 0.0) + base_item
            for t in it.get("taxes") or []:
                v = _num(t.get("value"))
                if not v:
                    continue
                g = _grupo_impuesto(t)
                prev = imp_por_grupo.get(g["key"])
                imp_por_grupo[g["key"]] = {
                    "label": g["label"], "percentage": g["percentage"],
                    "value": (prev["value"] if prev else 0.0) + v,
                }
        total_base = sum(base_por_cat.values())
        total_imp = sum(o["value"] for o in imp_por_grupo.values())
        total = total_base + total_imp

        rows.append([plan.get("cuentaPorCobrar") or "", comp, fecha, doc, doc, nit, detalle, "1", _entero(total), "", centro])
        for cat in ORDEN_BASE:
            valor = base_por_cat.get(cat)
            if not valor:
                continue
            rows.append([bases.get(cat, ""), comp, fecha, doc, doc, nit_v, f"{ETIQUETA_BASE[cat]} - {detalle}", "2", _entero(valor), "", centro])
        for key, obj in imp_por_grupo.items():
            if not obj["value"]:
                continue
            cat = _cat_de_tarifa(obj["percentage"])
            base_imp = base_por_cat[cat] if (cat and base_por_cat.get(cat)) else total_base
            rows.append([impuestos.get(key, ""), comp, fecha, doc, doc, nit_v, f"{obj['label']} - {detalle}", "2", _entero(obj["value"]), _entero(base_imp), centro])
    return rows


def _plan_usable(plan) -> bool:
    return bool(plan and (plan.get("cuentaPorCobrar") or (plan.get("bases") and len(plan["bases"]))))


def build_ventas(invoices, mapeo=None, plan=None) -> str:
    rows = _rows_ventas_flex(invoices, mapeo, plan) if _plan_usable(plan) else _rows_ventas_legado(invoices, mapeo)
    lines = [TAB.join(MOV_HEADER)]
    lines += [TAB.join(map(str, r)) for r in rows]
    return CRLF.join(lines) + CRLF


# ── Plano de RECIBOS: 'cancelar todo' (usa el saldo) ─────────────────
def _total_factura(inv) -> float:
    base = 0.0
    total_imp = 0.0
    for it in inv.get("items") or []:
        base += _num(it.get("price")) * _num(it.get("quantity")) - _num((it.get("discount") or {}).get("value"))
        for t in it.get("taxes") or []:
            total_imp += _num(t.get("value"))
    return base + total_imp


def _saldo_factura(inv) -> float:
    b = inv.get("balance") if isinstance(inv, dict) else None
    if b is not None and b != "":
        return _num(b)
    return _total_factura(inv)


def _ordenar_facturas(invoices):
    return sorted(invoices or [], key=lambda inv: (_fecha_yyyymmdd(inv.get("date")), _numero_factura(inv)))


def build_recibos_cancelar(invoices, consecutivo_inicial, mapeo=None, plan=None) -> dict:
    """Un recibo por factura con SALDO > 0 (Db efectivo / Cr cuenta por cobrar).
    Omite las de saldo 0 (nota crédito o ya pagadas). Devuelve dict con content, rango, omitidas."""
    cuenta_efectivo = (plan or {}).get("cuentaEfectivo") or RECIBO["cuentaCaja"]
    cuenta_cxc = (plan or {}).get("cuentaPorCobrar") or RECIBO["cuentaCartera"]
    try:
        cons = max(1, round(float(consecutivo_inicial or 1)))
    except (TypeError, ValueError):
        cons = 1
    inicio = cons
    rows = []
    omitidas = 0
    for inv in _ordenar_facturas(invoices):
        total = _saldo_factura(inv)
        if total <= 0:
            omitidas += 1
            continue
        fecha = _fecha_mmddyyyy(inv.get("date"))
        nit = (inv.get("customer") or {}).get("identification") or ""
        centro = _resolver_prefijo(inv.get("prefix"), mapeo)["centro"]
        doc = str(cons).rjust(RECIBO["docAncho"], "0")
        factura_no = _numero_factura(inv)
        detalle = _clean(f"Recaudo factura {inv.get('name') or factura_no}")
        rows.append([cuenta_efectivo, RECIBO["comprobante"], fecha, doc, doc, nit, detalle, "1", _entero(total), "", centro])
        rows.append([cuenta_cxc, RECIBO["comprobante"], fecha, doc, factura_no, nit, detalle, "2", _entero(total), "", centro])
        cons += 1
    lines = [TAB.join(MOV_HEADER)] + [TAB.join(map(str, r)) for r in rows]
    count = len(rows) // 2
    rango = {"desde": inicio, "hasta": inicio + count - 1, "count": count} if count else {"desde": inicio, "hasta": inicio, "count": 0}
    return {"content": CRLF.join(lines) + CRLF, "rango": rango, "omitidas": omitidas}


# ── Plano de RECIBOS: 'desde Siigo' (vouchers asentados) ─────────────
def _numero_doc(v) -> str:
    n = str(v.get("number") or "").strip() or str(v.get("name") or "").strip()
    return n.rjust(DOC_ANCHO, "0")


def _ref_factura(due) -> str:
    if not due:
        return ""
    s = f"{str(due.get('prefix') or '').strip()}{str(due.get('consecutive') or '').strip()}"
    return s.rjust(DOC_ANCHO, "0") if s else ""


def build_recibos_siigo(vouchers, plan=None) -> dict:
    """Reproduce los recibos asentados en Siigo. Cuadra con la cuenta de efectivo
    del plan si el voucher no trae el lado del banco. Devuelve dict con content, count."""
    cuenta_efectivo = (plan or {}).get("cuentaEfectivo") or RECIBO["cuentaCaja"]
    lines = [TAB.join(MOV_HEADER)]
    count = 0
    ordenados = sorted(vouchers or [], key=lambda v: str(v.get("date") or ""))
    for v in ordenados:
        fecha = _fecha_mmddyyyy(v.get("date"))
        nit = (v.get("customer") or {}).get("identification") or ""
        doc = _numero_doc(v)
        centro = "" if v.get("cost_center") is None else str(v.get("cost_center"))
        detalle = _clean(f"Recibo {v.get('name') or doc}")

        debitos = 0.0
        creditos = 0.0
        filas = []
        for it in v.get("items") or []:
            val = _num(it.get("value"))
            if not val:
                continue
            cuenta = (it.get("account") or {}).get("code") or ""
            mov = str((it.get("account") or {}).get("movement") or "").lower()
            tr = "1" if mov == "debit" else "2"
            if tr == "1":
                debitos += val
            else:
                creditos += val
            ref = _ref_factura(it.get("due")) or doc
            filas.append([cuenta, RECIBO["comprobante"], fecha, doc, ref, nit, detalle, tr, _entero(val), "", centro])
        for f in filas:
            lines.append(TAB.join(map(str, f)))
        desbalance = creditos - debitos
        if abs(desbalance) >= 1:
            tr = "1" if desbalance > 0 else "2"
            lines.append(TAB.join(map(str, [cuenta_efectivo, RECIBO["comprobante"], fecha, doc, doc, nit, detalle, tr, _entero(abs(desbalance)), "", centro])))
        count += 1
    return {"content": CRLF.join(lines) + CRLF, "count": count}


# ── Plano de NITs / terceros ─────────────────────────────────────────
def _rows_terceros(customers):
    rows = []
    for c in customers or []:
        es_juridica = str(c.get("person_type") or "").lower().startswith("company")
        naturaleza = "J" if es_juridica else "N"
        nombre = c.get("name")
        nombre = " ".join(nombre) if isinstance(nombre, list) else (nombre or "")
        contacto = (c.get("contacts") or [{}])[0] if (c.get("contacts")) else {}
        addr = c.get("address") or {}
        city = addr.get("city") or {}
        phones = c.get("phones") or []
        phone0 = phones[0] if len(phones) > 0 else {}
        cel = ""
        ph = contacto.get("phone")
        if isinstance(ph, dict):
            cel = ph.get("number") or ""
        elif isinstance(ph, str):
            cel = ph
        elif len(phones) > 1:
            cel = phones[1].get("number") or ""
        rows.append([
            c.get("identification") or "",
            "D" if es_juridica else "C",
            _clean(nombre),
            _clean(addr.get("address")),
            _clean(city.get("city_name")),
            _clean(phone0.get("number")),
            city.get("city_code") or "",
            "N" if c.get("active") is False else "S",
            "N",
            PAIS_COLOMBIA,
            _clean(contacto.get("first_name")),
            "",
            _clean(contacto.get("last_name")),
            "",
            _clean(contacto.get("email")),
            _clean(cel),
            "0",
            "",
            _clean(phone0.get("indicative")),
            naturaleza,
        ])
    return rows


def build_terceros(customers) -> str:
    lines = [TAB.join(NIT_HEADER)] + [TAB.join(map(str, r)) for r in _rows_terceros(customers)]
    return CRLF.join(lines) + CRLF


def terceros_matrix(customers) -> list:
    return [NIT_HEADER] + _rows_terceros(customers)
