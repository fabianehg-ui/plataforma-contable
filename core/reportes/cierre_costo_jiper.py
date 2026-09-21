# -*- coding: utf-8 -*-
"""
core/reportes/cierre_costo_jiper.py

Genera los PLANOS de Contai del cierre mensual de costo de JIPER SAS:

    Documento 4 — CIERRE DE COSTO
        Por cada centro de costo cierra las compras del mes (71059501/502/503),
        registra el costo (61400501 alimentos, 61401001 cafetería y aseo) y el
        neto de inventario (14050501 alimentos, 14050502 cafetería y aseo).
        Fórmula:  costo = inv_inicial + compras − inv_final
                  Δinventario (14) = inv_final − inv_inicial

    Documento 5 — TRASLADOS DE CDP
        Reclasifica los traslados de producción del CDP a los puntos de venta
        (61409501 alimentos, 61409502 cafetería y aseo). Movimiento interno que
        NETEA A CERO: los CDP acreditan (envían) y los puntos debitan (reciben).

Entradas:
    - BP para costo (.xlsx): Balance de Prueba con columnas
        Cuenta | Equivalencia | Nombre | Centro de Costos | Nombre CC |
        Saldo Anterior | Débitos | Créditos | Nuevo Saldo
      De aquí salen las COMPRAS del mes (movimiento deb−cred de 710501/02/03/04)
      y el INVENTARIO INICIAL (saldo anterior de 14050501/14050502) por CC.
    - RESULTADOS (.xlsx): hoja "RESULTADOS JUNIO 2026" (u otro mes), puntos en
      columnas. De aquí salen los INVENTARIOS FINALES (fila 13 alimentos, fila 25
      cafetería/aseo) y los TRASLADOS del CDP (filas 11+12 alimentos, 23+24
      cafetería/aseo).

Salida:
    (doc4_txt, doc5_txt, resumen). Cada plano es texto TAB-delimitado, con fila
    de encabezado (Contai descarta la primera línea), fin de línea \\r\\n, listo
    para guardar en .txt (latin-1) e importar a Contai.

NOTA: módulo específico de JIPER SAS. El mapeo centro de costo ↔ columna del
RESULTADOS y los nombres viven en MAPEO (abajo). Si cambia el layout del
RESULTADOS hay que ajustar las filas (FILA_*) o el MAPEO.
"""
from __future__ import annotations

import io
from datetime import datetime

NIT_JIPER = "901038325"

# ---------------------------------------------------------------------------
# Mapeo centro de costo -> (columna en la hoja RESULTADOS, nombre del CC)
# La columna es índice base-0 dentro de la fila (col 3 = primer punto).
# ---------------------------------------------------------------------------
MAPEO = {
    "001106": (3,  "SL VIVA ENVIGADO"),
    "001107": (4,  "SL LAURELES"),
    "001108": (5,  "SL LLANOGRANDE"),
    "001109": (6,  "SL BURBUJA POBLADO"),
    "001117": (7,  "SL MILLA DE ORO"),
    "001118": (8,  "SL HOTEL NOCK"),
    "001101": (9,  "SL INDIANA"),
    "001104": (10, "SL SAN LUCAS"),
    "001111": (11, "SL CIUDAD DEL RIO"),
    "001112": (12, "SL FABRICATO"),
    "001114": (13, "SL UNICENTRO"),
    "001116": (14, "SL MEDICAL TOWER"),
    "001102": (15, "SL OVIEDO"),
    "001103": (16, "SL EL TESORO"),
    "001105": (17, "SL DEL ESTE"),
    "001110": (18, "SL MIXY LOS COLORES"),
    "001113": (19, "SL LOS MOLINOS"),
    "001115": (20, "SL LAS VEGAS"),
    "001204": (21, "ML LAURELES"),
    "001203": (22, "ML VIVA ENVIGADO"),
    "001201": (23, "ML EL TESORO"),
    "001205": (24, "ML FABRICATO"),
    "001207": (25, "ML MILLA DE ORO"),
    "001202": (26, "ML REMEDIOS"),
    "001119": (27, "SL VENDING"),
    "001004": (28, "LINEA INSTITUCIONAL"),
    "001002": (29, "CDP LA REGIONAL"),
    "001003": (30, "CDP MEDELLIN"),
}

# Centro de costo que cuadra los traslados de CDP (plug del documento 5).
CC_PLUG_CDP = "001002"   # CDP LA REGIONAL

# Filas (base-0) de la hoja RESULTADOS
FILA_INV_FIN_ALIM = 13          # INV, FINAL ALIMENTOS
FILA_INV_FIN_CAFASEO = 25       # INV, FINAL ASEO Y CAFETERIA
FILA_TRAS_ALIM = (11, 12)       # TRASLADOS ALIMENTOS (CDP REGIONAL, CDP MEDELLIN)
FILA_TRAS_CAFASEO = (23, 24)    # TRASLADOS ASEO Y CAFETERIA (REGIONAL, MEDELLIN)

HDR = ["CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOCREF", "NIT",
       "DETALLE", "TR", "VALOR", "BASE", "CC"]


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _abrir(fuente, hoja=None):
    import openpyxl
    if isinstance(fuente, (bytes, bytearray)):
        wb = openpyxl.load_workbook(io.BytesIO(fuente), data_only=True, read_only=True)
    elif hasattr(fuente, "read"):
        wb = openpyxl.load_workbook(io.BytesIO(fuente.read()), data_only=True, read_only=True)
    else:
        wb = openpyxl.load_workbook(fuente, data_only=True, read_only=True)
    if hoja is None:
        return wb.active
    # buscar por nombre exacto o que empiece por "RESULTADOS"
    for ws in wb.worksheets:
        if ws.title.strip().upper() == hoja.strip().upper():
            return ws
    for ws in wb.worksheets:
        if ws.title.strip().upper().startswith("RESULTADOS"):
            return ws
    return wb.active


def _leer_bp(bp_fuente):
    """Del BP: compras del mes (710501/02 alim, 710503 caf, 710504 aseo) e
    inventario inicial (saldo anterior 14050501 alim, 14050502 caf/aseo) por CC."""
    ws = _abrir(bp_fuente)
    ca, cf, cs, ia, ic = {}, {}, {}, {}, {}
    for r in ws.iter_rows(values_only=True):
        cta = str(r[0] or "").strip()
        cc = str(r[3] or "").strip() if len(r) > 3 else ""
        if not cc or not cta:
            continue
        mov = _num(r[6]) - _num(r[7]) if len(r) > 7 else 0.0
        sa = _num(r[5]) if len(r) > 5 else 0.0
        if cta.startswith("710501") or cta.startswith("710502"):
            ca[cc] = ca.get(cc, 0.0) + mov
        elif cta.startswith("710503"):
            cf[cc] = cf.get(cc, 0.0) + mov
        elif cta.startswith("710504"):
            cs[cc] = cs.get(cc, 0.0) + mov
        if cta.startswith("14050501"):
            ia[cc] = ia.get(cc, 0.0) + sa
        elif cta.startswith("14050502"):
            ic[cc] = ic.get(cc, 0.0) + sa
    return ca, cf, cs, ia, ic


def _leer_resultados(res_fuente):
    """Del RESULTADOS: inventario final y traslados de CDP por CC."""
    ws = _abrir(res_fuente, hoja="RESULTADOS")
    rows = list(ws.iter_rows(values_only=True))

    def cell(ri, col):
        if ri < len(rows) and col < len(rows[ri]):
            return _num(rows[ri][col])
        return 0.0

    fin_a, fin_c, tras_a, tras_c = {}, {}, {}, {}
    for cc, (col, _nom) in MAPEO.items():
        fin_a[cc] = cell(FILA_INV_FIN_ALIM, col)
        fin_c[cc] = cell(FILA_INV_FIN_CAFASEO, col)
        tras_a[cc] = sum(cell(ri, col) for ri in FILA_TRAS_ALIM)
        tras_c[cc] = sum(cell(ri, col) for ri in FILA_TRAS_CAFASEO)
    return fin_a, fin_c, tras_a, tras_c


def _fila(cta, det, val, cc, tr, comp, fecha, doc):
    return "\t".join([cta, comp, fecha, doc, doc, NIT_JIPER, det,
                      str(tr), f"{val:.2f}", "0", cc])


def generar_cierre_costo(bp_fuente, res_fuente, comprobante="10",
                         doc_costo="4", doc_cdp="5", fecha=None):
    """
    Genera los planos de cierre de costo (doc 4) y traslados de CDP (doc 5).

    Returns:
        (doc4_txt, doc5_txt, resumen)
    """
    comp = str(comprobante or "10").strip()
    d4 = str(doc_costo or "4").strip()
    d5 = str(doc_cdp or "5").strip()
    if fecha:
        fecha_str = fecha if isinstance(fecha, str) else fecha.strftime("%m/%d/%Y")
    else:
        # último día del mes actual por defecto; el usuario normalmente lo fija
        fecha_str = datetime.today().strftime("%m/%d/%Y")

    ca, cf, cs, ia, ic = _leer_bp(bp_fuente)
    fin_a, fin_c, tras_a, tras_c = _leer_resultados(res_fuente)

    ccs = sorted(MAPEO.keys())

    # ---------------- Documento 4: cierre de costo ----------------
    l4 = ["\t".join(HDR)]
    l4.append(_fila("71059501", "REGISTRO DE CONTROL NO ELIMINAR", 0.0, "001001", 1, comp, fecha_str, d4))
    tot = {"compras": 0.0, "costo": 0.0}
    for cc in ccs:
        nom = MAPEO[cc][1]
        c_a = ca.get(cc, 0.0)
        c_f = cf.get(cc, 0.0)
        c_s = cs.get(cc, 0.0)
        i_a = ia.get(cc, 0.0)
        i_c = ic.get(cc, 0.0)
        f_a = fin_a.get(cc, 0.0)
        f_c = fin_c.get(cc, 0.0)
        costo_a = i_a + c_a - f_a
        net_a = f_a - i_a
        costo_c = i_c + (c_f + c_s) - f_c
        net_c = f_c - i_c
        if round(c_a, 2) != 0:
            l4.append(_fila("71059501", f"CIERRE COMPRAS ALIMENTOS {nom}", abs(c_a), cc, 2 if c_a > 0 else 1, comp, fecha_str, d4))
            tot["compras"] += c_a
        if round(costo_a, 2) != 0:
            l4.append(_fila("61400501", f"COSTO ALIMENTOS {nom}", abs(costo_a), cc, 1 if costo_a > 0 else 2, comp, fecha_str, d4))
            tot["costo"] += costo_a
        if round(net_a, 2) != 0:
            l4.append(_fila("14050501", f"INVENTARIO ALIMENTOS {nom}", abs(net_a), cc, 1 if net_a > 0 else 2, comp, fecha_str, d4))
        if round(c_f, 2) != 0:
            l4.append(_fila("71059502", f"CIERRE COMPRAS CAFETERIA {nom}", abs(c_f), cc, 2 if c_f > 0 else 1, comp, fecha_str, d4))
            tot["compras"] += c_f
        if round(c_s, 2) != 0:
            l4.append(_fila("71059503", f"CIERRE COMPRAS ASEO {nom}", abs(c_s), cc, 2 if c_s > 0 else 1, comp, fecha_str, d4))
            tot["compras"] += c_s
        if round(costo_c, 2) != 0:
            l4.append(_fila("61401001", f"COSTO CAFETERIA Y ASEO {nom}", abs(costo_c), cc, 1 if costo_c > 0 else 2, comp, fecha_str, d4))
            tot["costo"] += costo_c
        if round(net_c, 2) != 0:
            l4.append(_fila("14050502", f"INVENTARIO CAFETERIA Y ASEO {nom}", abs(net_c), cc, 1 if net_c > 0 else 2, comp, fecha_str, d4))
    doc4_txt = "\r\n".join(l4) + "\r\n"

    # ---------------- Documento 5: traslados de CDP ----------------
    ta = {cc: round(tras_a.get(cc, 0.0), 2) for cc in ccs}
    tc = {cc: round(tras_c.get(cc, 0.0), 2) for cc in ccs}
    # cuadre al centavo: el residuo va al CDP plug (alimentos)
    residuo = round(sum(ta.values()) + sum(tc.values()), 2)
    ta[CC_PLUG_CDP] = round(ta[CC_PLUG_CDP] - residuo, 2)

    l5 = ["\t".join(HDR)]
    l5.append(_fila("71059501", "REGISTRO DE CONTROL NO ELIMINAR", 0.0, "001001", 1, comp, fecha_str, d5))
    tot_tras = 0.0
    for cc in ccs:
        nom = MAPEO[cc][1]
        va = ta[cc]
        vc = tc[cc]
        if round(va, 2) != 0:
            l5.append(_fila("61409501", f"TRASLADO CDP ALIMENTOS {nom}", abs(va), cc, 1 if va > 0 else 2, comp, fecha_str, d5))
            tot_tras += abs(va)
        if round(vc, 2) != 0:
            l5.append(_fila("61409502", f"TRASLADO CDP CAFETERIA Y ASEO {nom}", abs(vc), cc, 1 if vc > 0 else 2, comp, fecha_str, d5))
            tot_tras += abs(vc)
    doc5_txt = "\r\n".join(l5) + "\r\n"

    def cuadre(txt):
        d = c = 0.0
        for ln in txt.split("\r\n")[1:]:
            if not ln.strip():
                continue
            f = ln.split("\t")
            (d := d + float(f[8])) if f[7] == "1" else (c := c + float(f[8]))
        return round(d, 2), round(c, 2)

    d4d, d4c = cuadre(doc4_txt)
    d5d, d5c = cuadre(doc5_txt)
    resumen = {
        "fecha": fecha_str,
        "doc4_lineas": len(l4) - 1,
        "doc5_lineas": len(l5) - 1,
        "doc4_debitos": d4d, "doc4_creditos": d4c, "doc4_dif": round(d4d - d4c, 2),
        "doc5_debitos": d5d, "doc5_creditos": d5c, "doc5_dif": round(d5d - d5c, 2),
        "total_compras": round(tot["compras"], 2),
        "total_costo": round(tot["costo"], 2),
        "total_traslados": round(tot_tras, 2),
    }
    return doc4_txt, doc5_txt, resumen
