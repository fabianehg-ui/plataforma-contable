# -*- coding: utf-8 -*-
"""
core/costo/costo_oasis.py

Traslado del costo de GRUPO DE LOLITA a partir de:
  1) el INFORME DE INVENTARIOS (archivo grande con la data cruda por producto):
     inventario FINAL sin IVA (SUBTOTAL + ICUI) por centro de costo a una fecha.
  2) el BALANCE de la CUENTA 14 por centro de costo (Balance de Prueba):
     las COMPRAS del mes = débitos de la cuenta 14 por CC.
  3) el inventario INICIAL = el inventario FINAL guardado del mes anterior
     (se memoriza para que no haya descuadres).

Costo por CC = inventario inicial + compras − inventario final.
Plano: deja el inventario final en la cuenta 14 (crédito 143599) y lleva a la
cuenta 61 lo consumido (débito 613599).
"""
from __future__ import annotations
import io, re
from collections import defaultdict

CUENTA_INV = "143599"      # cuenta 14 — inventario (crédito por el costo)
CUENTA_COSTO = "613599"    # cuenta 61 — costo de mercancía (débito)
NIT_TRASLADO = "120"
DETALLE = "TRASLADO DEL COSTO"
COMPROBANTE = "20"

# OASIS del informe -> centro de costo de GRUPO DE LOLITA
MAPA_OASIS_CC = {
    "MONTERREY": "100401", "TORRE MEDICA": "100501", "PUNTO CLAVE": "100601",
    "MAYORCA P4": "100901", "MAYORCA PISO 4": "100901",
    "MAYORCA MEGA PLAZA": "101201", "MEGAPLAZA": "101201", "MEGA PLAZA": "101201",
    "CLINICA PRADO": "101301", "CLINICA DEL PRADO": "101301",
    "LIBERTAD": "101801", "LA LIBERTAD": "101801", "PLAZA DE LA LIBERTAD": "101801",
    "UNICENTRO": "103001",
}
NOMBRES_CC = {
    "100401": "MONTERREY", "100501": "TORRE MEDICA", "100601": "PUNTO CLAVE",
    "100901": "MAYORCA PISO 4", "101201": "MAYORCA MEGA PLAZA",
    "101301": "CLINICA DEL PRADO", "101801": "PLAZA DE LA LIBERTAD", "103001": "UNICENTRO",
}
HDR_PLANO = ["CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOCREF", "NIT",
             "DETALLE", "TR", "VALOR", "BASE", "CC"]


def _num(x) -> float:
    try:
        return float(str(x).replace(",", "").replace("$", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def _abrir(fuente, hoja=None):
    import openpyxl
    data = fuente if isinstance(fuente, (bytes, bytearray)) else (
        fuente.read() if hasattr(fuente, "read") else open(fuente, "rb").read())
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    if hoja:
        for ws in wb.worksheets:
            if ws.title.strip().upper() == str(hoja).strip().upper():
                return ws, wb
    return wb.active, wb


def _col(up, *frag):
    for f in frag:
        for j, h in enumerate(up):
            if f in str(h or "").strip().upper():
                return j
    return None


def inventario_final_informe(fuente, fecha, version="sin_iva", mapa=None):
    """Del INFORME (data cruda por producto) devuelve {cc: valor} del inventario
    a la `fecha` dada (datetime o 'YYYY-MM-DD'), agrupado por centro de costo.
      · version='sin_iva': TOTAL PRECIO SIN IVA + ICUI
      · version='con_iva': TOTAL PRECIO CON IVA
    Busca automáticamente la hoja con la data cruda (columnas TOTAL PRECIO...,
    FECHA, OASIS) y mapea OASIS -> CC con `mapa` (o el de LOLITA)."""
    mapa = mapa or MAPA_OASIS_CC
    try:
        fkey = fecha.strftime("%Y-%m-%d")
    except AttributeError:
        fkey = str(fecha)[:10]
    import openpyxl
    data = fuente if isinstance(fuente, (bytes, bytearray)) else (
        fuente.read() if hasattr(fuente, "read") else open(fuente, "rb").read())
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    # localizar la hoja cruda
    ws = None
    for w in wb.worksheets:
        hdr = next(w.iter_rows(min_row=1, max_row=1, values_only=True), None) or ()
        up = [str(c or "").strip().upper() for c in hdr]
        if _col(up, "TOTAL PRECIO SIN IVA") is not None and _col(up, "OASIS") is not None \
                and _col(up, "FECHA") is not None:
            ws = w
            break
    if ws is None:
        return {}
    hdr = [str(c or "").strip().upper() for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
    cSin = _col(hdr, "TOTAL PRECIO SIN IVA")
    cCon = _col(hdr, "TOTAL PRECIO CON IVA")
    cIcui = _col(hdr, "ICUI")
    cFec = _col(hdr, "FECHA")
    cOa = _col(hdr, "OASIS")
    out = defaultdict(float)
    for r in ws.iter_rows(min_row=2, values_only=True):
        fe = r[cFec] if cFec is not None else None
        try:
            k = fe.strftime("%Y-%m-%d")
        except AttributeError:
            k = str(fe)[:10] if fe else ""
        if k != fkey:
            continue
        oa = str(r[cOa] or "").strip().upper() if cOa is not None else ""
        cc = mapa.get(oa)
        if not cc:
            continue
        if version == "con_iva":
            out[cc] += _num(r[cCon]) if cCon is not None else 0.0
        else:
            out[cc] += (_num(r[cSin]) if cSin is not None else 0.0) + \
                       (_num(r[cIcui]) if cIcui is not None else 0.0)
    return {cc: round(v, 2) for cc, v in out.items()}


def fechas_informe(fuente):
    """Fechas disponibles en el informe (para elegir el corte final)."""
    import openpyxl
    data = fuente if isinstance(fuente, (bytes, bytearray)) else (
        fuente.read() if hasattr(fuente, "read") else open(fuente, "rb").read())
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = None
    for w in wb.worksheets:
        hdr = next(w.iter_rows(min_row=1, max_row=1, values_only=True), None) or ()
        up = [str(c or "").strip().upper() for c in hdr]
        if _col(up, "TOTAL PRECIO SIN IVA") is not None and _col(up, "OASIS") is not None:
            ws = w
            break
    if ws is None:
        return []
    hdr = [str(c or "").strip().upper() for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
    cFec = _col(hdr, "FECHA")
    fechas = set()
    for r in ws.iter_rows(min_row=2, values_only=True):
        fe = r[cFec] if cFec is not None else None
        try:
            fechas.add(fe.strftime("%Y-%m-%d"))
        except AttributeError:
            pass
    return sorted(fechas)


def compras_balance14(fuente, cuenta_prefijo="14"):
    """Del BALANCE de la cuenta 14 por CC: {cc: {'saldo_anterior','debitos',
    'creditos','compras'}}.
    COMPRAS (movimiento neto del mes) = Débitos − Créditos: los créditos son las
    DEVOLUCIONES o notas crédito de la cuenta 14 y deben restarse. Solo suma las
    filas que traen centro de costo (evita duplicar los subtotales de las cuentas
    padre)."""
    ws, _ = _abrir(fuente)
    rows = list(ws.iter_rows(values_only=True))
    hdr_i = 0
    for i, r in enumerate(rows[:8]):
        up = [str(c or "").strip().lower() for c in r]
        if "cuenta" in up and any("débito" in x or "debito" in x for x in up):
            hdr_i = i
            break
    up = [str(c or "").strip().lower() for c in rows[hdr_i]]
    def col(*frag):
        for f in frag:
            for j, h in enumerate(up):
                if f in h:
                    return j
        return None
    cCta = col("cuenta") or 0
    cCC = col("centro de costo")
    cSA = col("saldo anterior")
    cDeb = col("débito", "debito")
    cCred = col("crédito", "credito")
    out = defaultdict(lambda: {"saldo_anterior": 0.0, "debitos": 0.0, "creditos": 0.0})
    for r in rows[hdr_i + 1:]:
        cta = str(r[cCta] or "").strip()
        cc = str(r[cCC] or "").strip() if cCC is not None else ""
        if not cta.startswith(cuenta_prefijo) or not cc:
            continue
        out[cc]["saldo_anterior"] += _num(r[cSA]) if cSA is not None else 0.0
        out[cc]["debitos"] += _num(r[cDeb]) if cDeb is not None else 0.0
        out[cc]["creditos"] += abs(_num(r[cCred])) if cCred is not None else 0.0
    res = {}
    for cc, v in out.items():
        deb = round(v["debitos"], 2)
        cred = round(v["creditos"], 2)
        res[cc] = {"saldo_anterior": round(v["saldo_anterior"], 2),
                   "debitos": deb, "creditos": cred,
                   "compras": round(deb - cred, 2)}  # neto: débitos − devoluciones
    return res


def generar_traslado(inicial, compras, final, comprobante=COMPROBANTE,
                     documento="7", fecha=None, nit=NIT_TRASLADO,
                     cuenta_inv=CUENTA_INV, cuenta_costo=CUENTA_COSTO, ccs=None,
                     detalle_compras=None):
    """inicial/compras/final: dict {cc: valor}. Devuelve {estado, filas, debitos,
    creditos, cuadra}. Costo = inicial + compras − final por CC. Plano:
    cuenta 143599 crédito (deja final en la 14) y 613599 débito (costo a la 61)."""
    import datetime
    if not fecha:
        fecha = datetime.date.today().strftime("%m/%d/%Y")
    ccs = ccs or sorted(set(list(inicial) + list(compras) + list(final)),
                        key=lambda c: str(c))
    detalle_compras = detalle_compras or {}
    estado, filas = [], [list(HDR_PLANO)]
    tot_deb = tot_cred = 0.0
    tini = tcom = tfin = tcosto = 0.0
    tdebc = tdevo = 0.0
    for cc in ccs:
        cc = str(cc)
        ini = round(float(inicial.get(cc, 0) or 0), 2)
        com = round(float(compras.get(cc, 0) or 0), 2)
        fin = round(float(final.get(cc, 0) or 0), 2)
        det = detalle_compras.get(cc, {})
        debc = round(float(det.get("debitos", com) or 0), 2)   # compras brutas
        devo = round(float(det.get("creditos", 0) or 0), 2)    # devoluciones/NC
        costo = round(ini + com - fin, 2)
        estado.append({"cc": cc, "nombre": NOMBRES_CC.get(cc, cc),
                       "inicial": ini, "compras_brutas": debc, "devoluciones": devo,
                       "compras": com, "disponible": round(ini + com, 2),
                       "final": fin, "costo": costo})
        tini += ini; tcom += com; tfin += fin; tcosto += costo
        tdebc += debc; tdevo += devo
        if costo == 0:
            continue
        filas.append([cuenta_inv, comprobante, fecha, documento, documento, nit,
                      DETALLE, "2", f"{costo:.2f}", "0", cc])
        filas.append([cuenta_costo, comprobante, fecha, documento, documento, nit,
                      DETALLE, "1", f"{costo:.2f}", "0", cc])
        tot_cred += costo; tot_deb += costo
    return {"estado": estado, "filas": filas,
            "debitos": round(tot_deb, 2), "creditos": round(tot_cred, 2),
            "cuadra": abs(tot_deb - tot_cred) < 0.01,
            "totales": {"inicial": round(tini, 2), "compras_brutas": round(tdebc, 2),
                        "devoluciones": round(tdevo, 2), "compras": round(tcom, 2),
                        "final": round(tfin, 2), "costo": round(tcosto, 2)},
            "n": len(filas) - 1}


def plano_a_texto(filas) -> str:
    return "\r\n".join("\t".join(str(c) for c in f) for f in filas) + "\r\n"


# ===========================================================================
# Memoria del inventario final por periodo (Supabase) — tabla costo_inventario_final
# ===========================================================================
def guardar_inventario_final(sb, empresa_id, periodo, final, version="sin_iva"):
    """Guarda {cc: valor} del inventario final del `periodo` (YYYY-MM) para
    reusarlo como inicial del mes siguiente."""
    try:
        sb.table("costo_inventario_final").delete().eq("empresa_id", empresa_id)\
            .eq("periodo", periodo).eq("version", version).execute()
    except Exception:  # noqa: BLE001
        pass
    payload = [{"empresa_id": empresa_id, "periodo": periodo, "version": version,
                "cc": str(cc), "valor": float(v)} for cc, v in final.items()]
    if payload:
        sb.table("costo_inventario_final").upsert(
            payload, on_conflict="empresa_id,periodo,version,cc").execute()
    return len(payload)


def cargar_inventario_final(sb, empresa_id, periodo, version="sin_iva"):
    """Devuelve {cc: valor} guardado para ese periodo (para usar como inicial)."""
    try:
        r = (sb.table("costo_inventario_final").select("cc,valor")
             .eq("empresa_id", empresa_id).eq("periodo", periodo)
             .eq("version", version).execute())
        return {str(x["cc"]): float(x["valor"]) for x in (r.data or [])}
    except Exception:  # noqa: BLE001
        return {}


def periodo_anterior(periodo):
    """'2026-07' -> '2026-06'."""
    try:
        y, m = periodo.split("-")
        y, m = int(y), int(m)
        m -= 1
        if m == 0:
            m = 12; y -= 1
        return f"{y:04d}-{m:02d}"
    except Exception:  # noqa: BLE001
        return ""


# ===========================================================================
# Exportar Excel: ESTADO DEL COSTO + PLANO
# ===========================================================================
def estado_costo_excel(resultado, periodo="", version="sin_iva",
                       empresa="GRUPO DE LOLITA S.A.S", documento="7", fecha=""):
    """Devuelve bytes de un .xlsx con la hoja ESTADO DEL COSTO (por CC) y la
    hoja PLANO (las líneas del traslado)."""
    import io as _io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "ESTADO DEL COSTO"
    az = PatternFill("solid", fgColor="1F4E78")
    gr = PatternFill("solid", fgColor="D9E1F2")
    tot = PatternFill("solid", fgColor="FCE4D6")
    wht = Font(color="FFFFFF", bold=True)
    bld = Font(bold=True)
    cen = Alignment(horizontal="center", vertical="center")
    rgt = Alignment(horizontal="right")
    thin = Side(style="thin", color="BFBFBF")
    bd = Border(left=thin, right=thin, top=thin, bottom=thin)
    money = '#,##0'

    ws.merge_cells("A1:G1")
    ws["A1"] = f"{empresa} — ESTADO DEL COSTO"
    ws["A1"].font = Font(bold=True, size=14, color="1F4E78")
    ws.merge_cells("A2:G2")
    vtxt = "sin IVA (SUBTOTAL + ICUI)" if version == "sin_iva" else "con IVA"
    ws["A2"] = f"Periodo {periodo}  ·  inventario {vtxt}  ·  documento {documento}  ·  fecha {fecha}"
    ws["A2"].font = Font(italic=True, color="808080")

    hdr = ["CENTRO DE COSTO", "PUNTO", "INV. INICIAL", "COMPRAS BRUTAS",
           "− DEVOLUCIONES", "= COMPRAS NETAS", "= DISPONIBLE", "− INV. FINAL", "= COSTO"]
    r0 = 4
    for j, h in enumerate(hdr, 1):
        c = ws.cell(r0, j, h); c.fill = az; c.font = wht; c.alignment = cen; c.border = bd
    r = r0 + 1
    for e in resultado["estado"]:
        vals = [e["cc"], e["nombre"], e["inicial"], e.get("compras_brutas", e["compras"]),
                e.get("devoluciones", 0), e["compras"], e["disponible"], e["final"], e["costo"]]
        for j, v in enumerate(vals, 1):
            c = ws.cell(r, j, v); c.border = bd
            if j >= 3:
                c.number_format = money; c.alignment = rgt
            elif j == 1:
                c.alignment = cen
        r += 1
    t = resultado["totales"]
    trow = ["TOTAL", "", t["inicial"], t.get("compras_brutas", t["compras"]),
            t.get("devoluciones", 0), t["compras"],
            round(t["inicial"] + t["compras"], 2), t["final"], t["costo"]]
    for j, v in enumerate(trow, 1):
        c = ws.cell(r, j, v); c.fill = tot; c.font = bld; c.border = bd
        if j >= 3:
            c.number_format = money; c.alignment = rgt
    widths = [16, 22, 14, 15, 15, 15, 14, 14, 15]
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A5"

    ws2 = wb.create_sheet("PLANO")
    for i, row in enumerate(resultado["filas"], 1):
        for j, v in enumerate(row, 1):
            c = ws2.cell(i, j, v)
            if i == 1:
                c.fill = gr; c.font = bld; c.alignment = cen
    for j, w in enumerate([9, 6, 12, 10, 10, 8, 22, 5, 16, 6, 9], 1):
        ws2.column_dimensions[get_column_letter(j)].width = w
    ws2.freeze_panes = "A2"

    buf = _io.BytesIO(); wb.save(buf); return buf.getvalue()


def periodo_siguiente(periodo):
    """'2026-07' -> '2026-08'."""
    try:
        y, m = periodo.split("-")
        y, m = int(y), int(m)
        m += 1
        if m == 13:
            m = 1; y += 1
        return f"{y:04d}-{m:02d}"
    except Exception:  # noqa: BLE001
        return ""
