# -*- coding: utf-8 -*-
"""
core/eeff/eeff_niif.py

Estados Financieros NIIF (informe recurrente mensual) — Grupo de Lolita.

El informe es una PLANTILLA de Excel cuyo motor es la hoja DATOS: con SUMIF
mapea cada cuenta contra las hojas 'BCE 2026' (balance del mes, año en curso) y
'BCE 2025' (balance del mismo mes del año anterior), y de ahí salen:
  · Estado de Resultados Integral del MES y ACUMULADO (2026 vs 2025, A.V, A.H)
  · Estado de Situación Financiera (ESF/Balance) 2026 vs 2025
  · Flujo de Efectivo (EFE), Cambios en el Patrimonio (ECP), Indicadores, Notas.

Este módulo NO reescribe las fórmulas: RELLENA la plantilla — inyecta el balance
del mes en 'BCE 2026', el del año anterior en 'BCE 2025', actualiza las fechas y
deja que Excel recalcule (fullCalcOnLoad). Además ANEXA el resultado por centro
de costo del mes (a nivel amplio, con desplegar/contraer).

Entradas:
  · BP del mes por NIT (Normal)           -> hoja 'BCE 2026'
  · BP del mismo mes del año anterior      -> hoja 'BCE 2025'
  · BP del mes por NIT y CENTRO DE COSTO   -> anexo 'RESULTADO POR CC'

Todos los valores se normalizan a PESOS (si el BP viene en Miles, se multiplica).
"""
from __future__ import annotations
import io
import re
from collections import defaultdict, OrderedDict

MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
DIA_FIN = [0, 31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

# columnas del BCE que espera la plantilla (A..J)
BCE_COLS = ["cuenta", "equivalencia", "nombre", "nit", "nombre_nit",
            "saldo_ant", "debitos", "creditos", "nuevo_saldo", "nivel"]


def _num(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace("$", "").replace(" ", "").strip()
    if not s:
        return 0.0
    s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") > 1 \
        else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _cta_num(cta):
    """Código de cuenta como número (la plantilla guarda A numérico)."""
    s = re.sub(r"[^0-9]", "", str(cta or ""))
    return int(s) if s else None


def leer_bp(fuente):
    """Lee un Balance de Prueba (por NIT, o por NIT y CC). Devuelve:
       {'meta': {...}, 'rows': [ {cuenta,equivalencia,nombre,nit,nombre_nit,
         cc,nombre_cc,saldo_ant,debitos,creditos,nuevo_saldo}, ... ] }
    Valores normalizados a PESOS (si el título dice 'Miles', escala x1000).
    Detecta si trae columna de Centro de Costos."""
    import openpyxl
    data = fuente if isinstance(fuente, (bytes, bytearray)) else (
        fuente.read() if hasattr(fuente, "read") else open(fuente, "rb").read())
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    # título / empresa / fecha en las primeras filas
    titulo = " ".join(str(c) for r in rows[:3] for c in r if c)
    empresa = str(rows[0][0]) if rows and rows[0] and rows[0][0] else ""
    en_miles = "mile" in titulo.lower()
    escala = 1000.0 if en_miles else 1.0
    # localizar encabezado
    hdr_i = None
    for i, r in enumerate(rows[:8]):
        up = [str(c or "").strip().lower() for c in r]
        if "cuenta" in up and any("saldo anterior" in x for x in up):
            hdr_i = i
            break
    if hdr_i is None:
        hdr_i = 2
    up = [str(c or "").strip().lower() for c in rows[hdr_i]]

    def col(*frag):
        for f in frag:
            for j, h in enumerate(up):
                if f in h:
                    return j
        return None
    cCta = col("cuenta")
    cEq = col("equivalencia")
    cNom = col("nombre") if col("nombre") != col("nombre nit") else None
    # nombre de la cuenta = primera col "nombre" que no sea "nombre nit"/"nombre cc"
    cNom = None
    for j, h in enumerate(up):
        if h == "nombre" or (h.startswith("nombre") and "nit" not in h and "cc" not in h
                             and "centro" not in h):
            cNom = j
            break
    cNit = col("nit")
    cNomNit = col("nombre nit")
    cCC = col("centro de costo", "centro de costos")
    cNomCC = col("nombre cc", "nombre centro")
    cSA = col("saldo anterior")
    cDeb = col("débito", "debito")
    cCred = col("crédito", "credito")
    cNS = col("nuevo saldo")
    out = []
    for r in rows[hdr_i + 1:]:
        cta = str(r[cCta] or "").strip() if cCta is not None else ""
        if not cta:
            continue
        out.append({
            "cuenta": cta,
            "equivalencia": (str(r[cEq]) if cEq is not None and r[cEq] is not None else ""),
            "nombre": (str(r[cNom]).strip() if cNom is not None and r[cNom] is not None else ""),
            "nit": (str(r[cNit]).strip() if cNit is not None and r[cNit] is not None else ""),
            "nombre_nit": (str(r[cNomNit]).strip() if cNomNit is not None and r[cNomNit] is not None else ""),
            "cc": (str(r[cCC]).strip() if cCC is not None and r[cCC] is not None else ""),
            "nombre_cc": (str(r[cNomCC]).strip() if cNomCC is not None and r[cNomCC] is not None else ""),
            "saldo_ant": _num(r[cSA]) * escala if cSA is not None else 0.0,
            "debitos": _num(r[cDeb]) * escala if cDeb is not None else 0.0,
            "creditos": _num(r[cCred]) * escala if cCred is not None else 0.0,
            "nuevo_saldo": _num(r[cNS]) * escala if cNS is not None else 0.0,
        })
    return {"meta": {"empresa": empresa, "titulo": titulo, "en_miles": en_miles,
                     "tiene_cc": cCC is not None},
            "rows": out}


def _agregar_por_nit(rows):
    """Colapsa las filas por (cuenta, nit) sumando los movimientos — reconstruye
    la vista 'por NIT (Normal)' a partir de una 'por NIT y CC'. Si no hay CC,
    devuelve las filas tal cual."""
    if not any(r["cc"] for r in rows):
        return rows
    agg = OrderedDict()
    for r in rows:
        k = (r["cuenta"], r["nit"])
        if k not in agg:
            agg[k] = dict(r); agg[k]["cc"] = ""; agg[k]["nombre_cc"] = ""
        else:
            for m in ("saldo_ant", "debitos", "creditos", "nuevo_saldo"):
                agg[k][m] += r[m]
    return list(agg.values())


def inyectar_bce(wb, rows, hoja):
    """Reemplaza los datos de la hoja del BCE (desde la fila 4) con `rows`
    (normalizadas a pesos, colapsadas por NIT). Col A numérica; col J = LEN(A)."""
    ws = wb[hoja]
    rows = _agregar_por_nit(rows)
    # limpiar datos viejos (desde fila 4 hasta el final)
    if ws.max_row >= 4:
        ws.delete_rows(4, ws.max_row - 3)
    i = 4
    for r in rows:
        ws.cell(i, 1, _cta_num(r["cuenta"]))
        ws.cell(i, 2, r["equivalencia"])
        ws.cell(i, 3, r["nombre"])
        ws.cell(i, 4, r["nit"])
        ws.cell(i, 5, r["nombre_nit"])
        ws.cell(i, 6, round(r["saldo_ant"], 2))
        ws.cell(i, 7, round(r["debitos"], 2))
        ws.cell(i, 8, round(r["creditos"], 2))
        ws.cell(i, 9, round(r["nuevo_saldo"], 2))
        ws.cell(i, 10, f"=+LEN(A{i})")
        i += 1
    return i - 4


def actualizar_meta(wb, mes, anio, anio_comp=None):
    """Actualiza las fechas del informe en la hoja DATOS y el título del BCE."""
    anio_comp = anio_comp or (anio - 1)
    ws = wb["DATOS"]
    # buscar etiquetas en col G (7) y escribir el valor en col H (8)
    et = {}
    for r in range(1, 40):
        lab = ws.cell(r, 7).value
        if lab:
            et[str(lab).strip().upper()] = r
    def setv(label, val):
        for k, r in et.items():
            if k.startswith(label):
                ws.cell(r, 8, val); return
    dia = DIA_FIN[mes]
    setv("FECHA DE CORTE", f"A {dia} de {MESES[mes]} de {anio} y {anio_comp}")
    setv("MES", mes)
    setv("FECHA E.F", f"{anio}-{mes:02d}")
    setv("FECHA E.F COMP", f"{anio_comp}-{mes:02d}")


def forzar_recalculo(wb):
    """Marca el libro para que Excel/LibreOffice recalcule al abrir."""
    try:
        wb.calculation.calcMode = "auto"
        wb.calculation.fullCalcOnLoad = True
    except Exception:  # noqa: BLE001
        try:
            from openpyxl.workbook.properties import CalcProperties
            wb.calculation = CalcProperties(fullCalcOnLoad=True, calcMode="auto")
        except Exception:  # noqa: BLE001
            pass


def generar_informe(template, bp_actual, bp_anio_anterior, mes, anio,
                    bp_cc=None, anio_comp=None):
    """Rellena la plantilla y devuelve los bytes del informe.
      template          : bytes/ruta de la plantilla EEFF.
      bp_actual         : BP por NIT del mes (año en curso)   -> 'BCE 2026'
      bp_anio_anterior  : BP por NIT del mismo mes año pasado -> 'BCE 2025'
      bp_cc             : BP por NIT y CC del mes (para el anexo). Opcional.
    """
    import openpyxl
    data = template if isinstance(template, (bytes, bytearray)) else open(template, "rb").read()
    wb = openpyxl.load_workbook(io.BytesIO(data))  # con fórmulas
    hoja_act = "BCE 2026" if "BCE 2026" in wb.sheetnames else wb.sheetnames[-2]
    hoja_ant = "BCE 2025" if "BCE 2025" in wb.sheetnames else wb.sheetnames[-1]
    n1 = inyectar_bce(wb, leer_bp(bp_actual)["rows"], hoja_act)
    n2 = inyectar_bce(wb, leer_bp(bp_anio_anterior)["rows"], hoja_ant)
    actualizar_meta(wb, mes, anio, anio_comp)
    anexo = None
    if bp_cc is not None:
        anexo = construir_anexo_cc(wb, leer_bp(bp_cc), mes, anio)
    forzar_recalculo(wb)
    buf = io.BytesIO(); wb.save(buf)
    return {"bytes": buf.getvalue(), "n_actual": n1, "n_anterior": n2, "anexo": anexo}


# ===========================================================================
# ANEXO: resultado por centro de costo del mes (nivel amplio, desplegar/contraer)
# ===========================================================================
CLASES_RES = OrderedDict([("4", "INGRESOS"), ("6", "COSTOS DE VENTAS"), ("5", "GASTOS")])


def resultado_cc(bp_cc_leido, mes=None, anio=None):
    """Del BP por NIT y CC devuelve el RESULTADO DEL MES por centro de costo.
    Estructura jerárquica: clase (4/5/6) -> grupo (2 díg) -> cuenta (4 díg),
    con el valor del mes por cada CC. Signo económico: ingresos positivos,
    costos y gastos positivos como consumo (se restan en la utilidad).
    Movimiento del mes por cuenta/CC:
       ingresos (4): créditos − débitos ; costos/gastos (5,6): débitos − créditos
    """
    rows = bp_cc_leido["rows"]
    ccs = OrderedDict()
    for r in rows:
        if r["cc"]:
            ccs.setdefault(r["cc"], r["nombre_cc"] or r["cc"])
    # nivel cuenta (4 díg) por CC
    # nodo: clave por longitud de código; solo tomamos hojas con CC
    datos = defaultdict(lambda: defaultdict(float))  # (nivel, code) -> {cc: valor}
    nombres = {}
    for r in rows:
        cta = re.sub(r"[^0-9]", "", r["cuenta"])
        if not cta or cta[0] not in "456" or not r["cc"]:
            continue
        signo = 1.0 if cta[0] == "4" else -1.0  # 4 ingreso: cr-de ; 5/6: de-cr
        mov_ing = r["creditos"] - r["debitos"]
        mov_gas = r["debitos"] - r["creditos"]
        val = mov_ing if cta[0] == "4" else mov_gas
        for L in (1, 2, 4):
            if len(cta) >= L:
                code = cta[:L]
                datos[(L, code)][r["cc"]] += val
                nombres.setdefault((L, code), None)
    # nombres a nivel 1/2/4 desde filas de subtotal (sin CC)
    for r in rows:
        cta = re.sub(r"[^0-9]", "", r["cuenta"])
        if cta and cta[0] in "456" and not r["cc"] and len(cta) in (1, 2, 4):
            nombres[(len(cta), cta)] = r["nombre"]
    return {"ccs": ccs, "datos": datos, "nombres": nombres}


def construir_anexo_cc(wb, bp_cc_leido, mes, anio):
    """Crea/reescribe la hoja 'RESULTADO POR CC' con el resultado del mes por
    centro de costo, a nivel amplio (clase y grupo) con las cuentas de 4 dígitos
    agrupadas para desplegar/contraer. Devuelve dict con totales por CC."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    R = resultado_cc(bp_cc_leido, mes, anio)
    ccs = R["ccs"]; datos = R["datos"]; nombres = R["nombres"]
    name = "RESULTADO POR CC"
    if name in wb.sheetnames:
        del wb[name]
    ws = wb.create_sheet(name)
    az = PatternFill("solid", fgColor="1F4E78"); wht = Font(color="FFFFFF", bold=True)
    grp = PatternFill("solid", fgColor="D9E1F2"); tot = PatternFill("solid", fgColor="FCE4D6")
    bld = Font(bold=True); cen = Alignment(horizontal="center", vertical="center")
    rgt = Alignment(horizontal="right")
    thin = Side(style="thin", color="BFBFBF"); bd = Border(thin, thin, thin, thin)
    money = '#,##0'

    cc_list = list(ccs.keys())
    ws.cell(1, 1, f"{bp_cc_leido['meta'].get('empresa','')}").font = Font(bold=True, size=13, color="1F4E78")
    ws.cell(2, 1, f"RESULTADO POR CENTRO DE COSTO — {MESES[mes]} {anio} (miles de pesos)").font = Font(italic=True, color="808080")
    hrow = 4
    ws.cell(hrow, 1, "CONCEPTO").fill = az; ws.cell(hrow, 1).font = wht
    ws.cell(hrow, 2, "CUENTA").fill = az; ws.cell(hrow, 2).font = wht
    for k, cc in enumerate(cc_list):
        c = ws.cell(hrow, 3 + k, ccs[cc]); c.fill = az; c.font = wht; c.alignment = cen
    c = ws.cell(hrow, 3 + len(cc_list), "TOTAL"); c.fill = az; c.font = wht; c.alignment = cen
    ncol = 3 + len(cc_list)

    def escribir_fila(r, concepto, code, nivel, valores, es_grupo=False, es_clase=False):
        ci = ws.cell(r, 1, ("   " * (nivel)) + concepto)
        ws.cell(r, 2, code)
        tt = 0.0
        for k, cc in enumerate(cc_list):
            v = round(valores.get(cc, 0.0) / 1000.0, 0)  # en miles
            cell = ws.cell(r, 3 + k, v); cell.number_format = money; cell.alignment = rgt
            tt += valores.get(cc, 0.0)
        cell = ws.cell(r, ncol, round(tt / 1000.0, 0)); cell.number_format = money; cell.alignment = rgt
        if es_clase:
            for c in range(1, ncol + 1):
                ws.cell(r, c).fill = tot; ws.cell(r, c).font = bld
        elif es_grupo:
            for c in range(1, ncol + 1):
                ws.cell(r, c).fill = grp; ws.cell(r, c).font = bld
        return tt

    r = hrow + 1
    totales_clase = {}
    # niveles de esquema (outline) por fila: clase=0, grupo=1, cuenta=2.
    # Se fija el nivel POR FILA (no con group() sobre rangos) para que no se
    # pisen los niveles; las cuentas (nivel 2) arrancan contraídas.
    for cls, cls_nombre in CLASES_RES.items():
        vals_clase = datos.get((1, cls), {})
        escribir_fila(r, cls_nombre, cls, 0, vals_clase, es_clase=True)
        totales_clase[cls] = {cc: vals_clase.get(cc, 0.0) for cc in cc_list}
        r += 1
        grupos = sorted([code for (L, code) in datos if L == 2 and code[0] == cls])
        for g in grupos:
            vg = datos[(2, g)]
            escribir_fila(r, nombres.get((2, g)) or g, g, 1, vg, es_grupo=True)
            ws.row_dimensions[r].outlineLevel = 1
            r += 1
            ctas = sorted([code for (L, code) in datos if L == 4 and code[:2] == g])
            for cta4 in ctas:
                escribir_fila(r, nombres.get((4, cta4)) or cta4, cta4, 2, datos[(4, cta4)])
                ws.row_dimensions[r].outlineLevel = 2
                ws.row_dimensions[r].hidden = True   # arranca contraído
                r += 1
    # UTILIDAD del mes por CC = ingresos - costos - gastos
    util = {}
    for cc in cc_list:
        util[cc] = (totales_clase.get("4", {}).get(cc, 0.0)
                    - totales_clase.get("6", {}).get(cc, 0.0)
                    - totales_clase.get("5", {}).get(cc, 0.0))
    escribir_fila(r, "UTILIDAD / (PÉRDIDA) DEL MES", "", 0, util, es_clase=True)

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 10
    for k in range(len(cc_list) + 1):
        ws.column_dimensions[get_column_letter(3 + k)].width = 14
    ws.freeze_panes = "C5"
    ws.sheet_properties.outlinePr.summaryBelow = False
    return {"ccs": ccs, "utilidad": {cc: round(util[cc], 2) for cc in cc_list},
            "total_utilidad": round(sum(util.values()), 2)}


# ===========================================================================
# Memoria del resultado por CC (Supabase) — tabla eeff_resultado_cc
# ===========================================================================
def totales_cc_por_clase(bp_cc_leido):
    """{cc: {'ingresos','costos','gastos','utilidad','nombre'}} del mes (pesos)."""
    R = resultado_cc(bp_cc_leido)
    ccs = R["ccs"]; datos = R["datos"]
    out = {}
    for cc, nom in ccs.items():
        ing = datos.get((1, "4"), {}).get(cc, 0.0)
        cos = datos.get((1, "6"), {}).get(cc, 0.0)
        gas = datos.get((1, "5"), {}).get(cc, 0.0)
        out[cc] = {"nombre": nom, "ingresos": round(ing, 2), "costos": round(cos, 2),
                   "gastos": round(gas, 2), "utilidad": round(ing - cos - gas, 2)}
    return out


def guardar_resultado_cc(sb, empresa_id, periodo, totales):
    """Memoriza {cc: {ingresos,costos,gastos,utilidad,nombre}} del periodo."""
    try:
        sb.table("eeff_resultado_cc").delete().eq("empresa_id", empresa_id)\
            .eq("periodo", periodo).execute()
    except Exception:  # noqa: BLE001
        pass
    payload = [{"empresa_id": empresa_id, "periodo": periodo, "cc": str(cc),
                "nombre_cc": v.get("nombre", ""), "ingresos": float(v["ingresos"]),
                "costos": float(v["costos"]), "gastos": float(v["gastos"]),
                "utilidad": float(v["utilidad"])} for cc, v in totales.items()]
    if payload:
        sb.table("eeff_resultado_cc").upsert(payload, on_conflict="empresa_id,periodo,cc").execute()
    return len(payload)


def cargar_resultado_cc(sb, empresa_id, periodo):
    try:
        r = (sb.table("eeff_resultado_cc").select("*")
             .eq("empresa_id", empresa_id).eq("periodo", periodo).execute())
        return {str(x["cc"]): x for x in (r.data or [])}
    except Exception:  # noqa: BLE001
        return {}


def periodo_anterior(periodo):
    try:
        y, m = periodo.split("-"); y, m = int(y), int(m)
        m -= 1
        if m == 0:
            m = 12; y -= 1
        return f"{y:04d}-{m:02d}"
    except Exception:  # noqa: BLE001
        return ""
