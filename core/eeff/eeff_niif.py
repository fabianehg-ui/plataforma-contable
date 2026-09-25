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

CUENTA_TRASLADO_COSTO = "143599"   # traslado al costo (se omite en compras)
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


def inyectar_bce(wb, rows, hoja, unidad="pesos", mes=None):
    """Reemplaza los datos de la hoja del BCE (desde la fila 4) con `rows`
    (normalizadas a PESOS internamente, colapsadas por NIT). Guiado por el
    ENCABEZADO real de la hoja (fila 3): ubica las columnas Saldo Anterior,
    Débitos, Créditos, Nuevo Saldo, NIVEL y (si existe) Mes.
      unidad = 'pesos'  -> escribe en pesos (plantilla con DATOS que divide /1000)
             = 'miles'  -> escribe en miles (plantilla que ya trabaja en miles)
    """
    ws = wb[hoja]
    rows = _agregar_por_nit(rows)
    factor = 0.001 if unidad == "miles" else 1.0
    # mapear columnas por el encabezado (fila 3)
    hdr = [str(ws.cell(3, j).value or "").strip().lower() for j in range(1, 16)]
    def cidx(*frag, default=None):
        for f in frag:
            for j, h in enumerate(hdr, 1):
                if f in h:
                    return j
        return default
    cCta = cidx("cuenta", default=1)
    cEq = cidx("equivalencia", default=2)
    cNom = 3
    for j, h in enumerate(hdr, 1):
        if h == "nombre":
            cNom = j; break
    cNit = cidx("nit", default=4)
    cNomNit = cidx("nombre nit", default=5)
    cSA = cidx("saldo anterior", default=6)
    cDeb = cidx("débito", "debito", default=7)
    cCred = cidx("crédito", "credito", default=8)
    cNS = cidx("nuevo saldo", default=9)
    cMes = cidx("mes")
    cNiv = cidx("nivel")
    # limpiar datos viejos (desde fila 4 hasta el final)
    if ws.max_row >= 4:
        ws.delete_rows(4, ws.max_row - 3)
    i = 4
    for r in rows:
        ws.cell(i, cCta, _cta_num(r["cuenta"]))
        if cEq:
            ws.cell(i, cEq, r["equivalencia"])
        ws.cell(i, cNom, r["nombre"])
        if cNit:
            ws.cell(i, cNit, r["nit"])
        if cNomNit:
            ws.cell(i, cNomNit, r["nombre_nit"])
        ws.cell(i, cSA, round(r["saldo_ant"] * factor, 2))
        ws.cell(i, cDeb, round(r["debitos"] * factor, 2))
        ws.cell(i, cCred, round(r["creditos"] * factor, 2))
        ws.cell(i, cNS, round(r["nuevo_saldo"] * factor, 2))
        if cMes:
            ws.cell(i, cMes, round((r["debitos"] - r["creditos"]) * factor, 2))
        if cNiv:
            ws.cell(i, cNiv, f"=+LEN({_colletter(cCta)}{i})")
        i += 1
    return i - 4


def _colletter(idx):
    from openpyxl.utils import get_column_letter
    return get_column_letter(idx)


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


def aplicar_visibilidad(wb, visibles, activa=None):
    """Deja visibles solo las hojas de `visibles` (por nombre); las demás quedan
    ocultas. Fija la hoja activa. Robusto a nombres que no existan."""
    vis = set(visibles or [])
    presentes = [s for s in vis if s in wb.sheetnames]
    if not presentes:
        return
    for ws in wb.worksheets:
        ws.sheet_state = "visible" if ws.title in vis else "hidden"
    dest = activa if (activa and activa in wb.sheetnames) else presentes[0]
    try:
        wb.active = wb.sheetnames.index(dest)
    except Exception:  # noqa: BLE001
        pass


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


# ===========================================================================
# Configuración de las dos plantillas (informes) disponibles
# ===========================================================================
PLANTILLAS = OrderedDict([
    ("fiscal", {
        "titulo": "Estado de Situación Financiera Fiscal",
        "archivo": "EEFF_NIIF_GRUPO_DE_LOLITA.xlsx",
        "hoja_2026": "BCE 2026", "hoja_2025": "BCE 2025",
        "unidad": "pesos",         # la hoja DATOS divide por 1000
        "anexo_cc": False,         # normalito: solo balance por terceros, sin CC
        "drill_cc": False,
        "muestra_cc": False,
        "descripcion": "Estado de resultados, situación financiera, cambios en el "
                       "patrimonio y flujo de caja (NIIF). Balance por terceros (NIT), "
                       "sin centros de costo.",
    }),
    ("administrativo", {
        "titulo": "Balance General y PyG Administrativo",
        "nativo": True,             # se genera desde cero (no rellena plantilla)
        "muestra_cc": False,
        "descripcion": "Balance general y P&G administrativo por centro de costo, "
                       "generado desde el balance por NIT y centro de costo: TODAS las "
                       "cuentas de ingreso, costo y gasto por CC, con mes y acumulado del "
                       "año (más comparativo del año anterior con análisis vertical), "
                       "EBITDA, juego de inventarios, ESF que cuadra, IMPORRENTA, "
                       "indicadores, observaciones y detalle por tercero. Al hacer clic en "
                       "el número de una cuenta, filtra su detalle (se descarga como libro "
                       "con macros .xlsm). Lo que no mueve centro de costo (p.ej. la 43 de "
                       "intereses) se reparte entre los CC proporcional a las ventas.",
    }),
])


def _hojas_bce(wb, cfg):
    h26 = cfg["hoja_2026"] if cfg["hoja_2026"] in wb.sheetnames else None
    h25 = cfg["hoja_2025"] if cfg["hoja_2025"] in wb.sheetnames else None
    if h26 is None or h25 is None:
        # respaldo: detectar por nombre que contenga 2026/2025
        for s in wb.sheetnames:
            if h26 is None and "2026" in s:
                h26 = s
            if h25 is None and "2025" in s:
                h25 = s
    return h26, h25


def generar_informe(template, bp_actual, bp_anio_anterior, mes, anio,
                    bp_cc=None, anio_comp=None, tipo="fiscal", cfg=None):
    """Rellena la plantilla del tipo indicado y devuelve los bytes del informe.
      template          : bytes/ruta de la plantilla.
      bp_actual         : BP del mes (año en curso)          -> hoja 2026
      bp_anio_anterior  : BP del mismo mes del año anterior  -> hoja 2025
      bp_cc             : BP por NIT y CC del mes (para el anexo, si aplica).
      tipo              : 'fiscal' | 'administrativo' (define hojas y unidad).
    Los BP se leen en pesos o miles (autodetectado) y se inyectan en la unidad
    que la plantilla espera (pesos o miles)."""
    import openpyxl
    cfg = cfg or PLANTILLAS.get(tipo, PLANTILLAS["fiscal"])
    unidad = cfg.get("unidad", "pesos")
    data = template if isinstance(template, (bytes, bytearray)) else open(template, "rb").read()
    wb = openpyxl.load_workbook(io.BytesIO(data))  # con fórmulas
    hoja_act, hoja_ant = _hojas_bce(wb, cfg)
    n1 = inyectar_bce(wb, leer_bp(bp_actual)["rows"], hoja_act, unidad=unidad, mes=mes)
    n2 = inyectar_bce(wb, leer_bp(bp_anio_anterior)["rows"], hoja_ant, unidad=unidad, mes=mes)
    actualizar_meta(wb, mes, anio, anio_comp)
    anexo = None
    if bp_cc is not None and cfg.get("anexo_cc", False):
        anexo = construir_anexo_cc(wb, leer_bp(bp_cc), mes, anio)
    if bp_cc is not None and cfg.get("drill_cc", False):
        anexo = enlazar_pyg_cc_tercero(wb, leer_bp(bp_cc), mes, anio)
    if cfg.get("hojas_visibles"):
        aplicar_visibilidad(wb, cfg["hojas_visibles"], cfg.get("hoja_activa"))
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


# ===========================================================================
# ANEXO administrativo: P&G por CC con DRILL-DOWN al detalle por tercero
# ===========================================================================
def _dig(x):
    return re.sub(r"[^0-9]", "", str(x or ""))


def construir_drill_cc_tercero(wb, bp_cc_leido, mes, anio):
    """Crea dos hojas en el libro:
      · 'PYG POR CC'       : matriz cuenta (6 díg) x centro de costo, resultado del
                             mes. Cada celda con valor es un HIPERVÍNCULO que salta
                             al detalle por tercero de esa cuenta en ese CC.
      · 'DETALLE TERCERO'  : por cada (centro de costo, cuenta) el desglose por
                             tercero (NIT) que compone el valor; con enlace «volver».
    Devuelve totales por CC (para memoria/comparativo)."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.hyperlink import Hyperlink

    rows = bp_cc_leido["rows"]
    ccs = OrderedDict()
    det = defaultdict(lambda: defaultdict(float))   # (cc,c6) -> {(nit,nom): val}
    mat = defaultdict(float)                          # (c6,cc) -> val
    nom6 = {}; nom4 = {}; nom2 = {}
    tot_cc = defaultdict(lambda: {"ingresos": 0.0, "costos": 0.0, "gastos": 0.0})
    for r in rows:
        cta = _dig(r["cuenta"]); cc = r["cc"]
        if not cta or cta[0] not in "456":
            continue
        if not cc:  # filas de subtotal -> nombres
            if len(cta) == 6:
                nom6[cta] = r["nombre"]
            elif len(cta) == 4:
                nom4[cta] = r["nombre"]
            elif len(cta) == 2:
                nom2[cta] = r["nombre"]
            continue
        ccs.setdefault(cc, r["nombre_cc"] or cc)
        val = (r["creditos"] - r["debitos"]) if cta[0] == "4" else (r["debitos"] - r["creditos"])
        c6 = cta[:6]
        det[(cc, c6)][(r["nit"], r["nombre_nit"])] += val
        mat[(c6, cc)] += val
        k = {"4": "ingresos", "6": "costos", "5": "gastos"}[cta[0]]
        tot_cc[cc][k] += val

    cc_list = list(ccs.keys())
    # estilos
    az = PatternFill("solid", fgColor="1F4E78"); wht = Font(color="FFFFFF", bold=True)
    grp = PatternFill("solid", fgColor="D9E1F2"); clsf = PatternFill("solid", fgColor="BDD7EE")
    bld = Font(bold=True); cen = Alignment(horizontal="center", vertical="center")
    rgt = Alignment(horizontal="right")
    link = Font(color="0563C1", underline="single")
    thin = Side(style="thin", color="D0D0D0"); bd = Border(thin, thin, thin, thin)
    money = '#,##0'
    escala = 0.001  # mostrar en miles

    NDET = "DETALLE TERCERO"
    NMAT = "PYG POR CC"
    for nm in (NMAT, NDET):
        if nm in wb.sheetnames:
            del wb[nm]
    wd = wb.create_sheet(NDET)
    wm = wb.create_sheet(NMAT)

    # ---- Hoja DETALLE: bloques por (cc, cuenta6), guarda fila destino ----
    destino = {}   # (cc,c6) -> fila
    wd.cell(1, 1, "DETALLE POR TERCERO — " + f"{MESES[mes]} {anio} (miles)").font = Font(bold=True, size=12, color="1F4E78")
    dr = 3
    for cc in cc_list:
        c6s = sorted([c6 for (c, c6) in det if c == cc])
        if not c6s:
            continue
        cc_cell = wd.cell(dr, 1, f"CENTRO DE COSTO: {cc}  {ccs[cc]}")
        cc_cell.font = Font(bold=True, color="FFFFFF"); 
        for cc2 in range(1, 5):
            wd.cell(dr, cc2).fill = az
        dr += 1
        for c6 in c6s:
            destino[(cc, c6)] = dr
            tt = sum(det[(cc, c6)].values())
            h = wd.cell(dr, 1, f"{c6}  {nom6.get(c6, '')}"); h.font = bld; h.fill = grp
            wd.cell(dr, 2, "").fill = grp
            hv = wd.cell(dr, 3, round(tt * escala, 0)); hv.font = bld; hv.fill = grp
            hv.number_format = money; hv.alignment = rgt
            back = wd.cell(dr, 4, "↩ volver"); back.font = link
            back.hyperlink = Hyperlink(ref=back.coordinate, location=f"'{NMAT}'!A1")
            dr += 1
            wd.cell(dr, 1, "NIT").font = bld; wd.cell(dr, 2, "Tercero").font = bld
            wd.cell(dr, 3, "Valor").font = bld
            dr += 1
            for (nit, nom), v in sorted(det[(cc, c6)].items(), key=lambda x: -abs(x[1])):
                wd.cell(dr, 1, nit)
                wd.cell(dr, 2, str(nom)[:45])
                vc = wd.cell(dr, 3, round(v * escala, 0)); vc.number_format = money; vc.alignment = rgt
                dr += 1
            dr += 1
    wd.column_dimensions["A"].width = 16; wd.column_dimensions["B"].width = 42
    wd.column_dimensions["C"].width = 16; wd.column_dimensions["D"].width = 12
    wd.freeze_panes = "A3"

    # ---- Hoja MATRIZ: cuenta6 x CC, celdas con hipervínculo al detalle ----
    wm.cell(1, 1, f"{bp_cc_leido['meta'].get('empresa','')}").font = Font(bold=True, size=13, color="1F4E78")
    wm.cell(2, 1, f"P&G POR CENTRO DE COSTO — {MESES[mes]} {anio} (miles). "
                  "Clic en un valor para ver el detalle por tercero.").font = Font(italic=True, color="808080")
    hrow = 4
    wm.cell(hrow, 1, "CUENTA").fill = az; wm.cell(hrow, 1).font = wht
    wm.cell(hrow, 2, "NOMBRE").fill = az; wm.cell(hrow, 2).font = wht
    for k, cc in enumerate(cc_list):
        c = wm.cell(hrow, 3 + k, ccs[cc]); c.fill = az; c.font = wht; c.alignment = cen
    tcol = 3 + len(cc_list)
    c = wm.cell(hrow, tcol, "TOTAL"); c.fill = az; c.font = wht; c.alignment = cen

    r = hrow + 1
    clases = OrderedDict([("4", "INGRESOS"), ("6", "COSTOS DE VENTAS"), ("5", "GASTOS")])
    all_c6 = sorted({c6 for (c6, cc) in mat})
    for cls, cls_nom in clases.items():
        c6s_cls = [c for c in all_c6 if c.startswith(cls)]
        if not c6s_cls:
            continue
        # fila clase
        rc = wm.cell(r, 1, cls); rc.fill = clsf; rc.font = bld
        wm.cell(r, 2, cls_nom).fill = clsf; wm.cell(r, 2).font = bld
        tot_row_class = {}
        for k, cc in enumerate(cc_list):
            s = sum(mat.get((c6, cc), 0.0) for c6 in c6s_cls)
            tot_row_class[cc] = s
            cc2 = wm.cell(r, 3 + k, round(s * escala, 0)); cc2.fill = clsf; cc2.font = bld
            cc2.number_format = money; cc2.alignment = rgt
        tcell = wm.cell(r, tcol, round(sum(tot_row_class.values()) * escala, 0))
        tcell.fill = clsf; tcell.font = bld; tcell.number_format = money; tcell.alignment = rgt
        r += 1
        # agrupar por 4 díg
        for g4 in sorted({c[:4] for c in c6s_cls}):
            c6s_g = [c for c in c6s_cls if c[:4] == g4]
            g4_start = r
            for c6 in c6s_g:
                wm.cell(r, 1, c6)
                wm.cell(r, 2, nom6.get(c6, ""))
                rtot = 0.0
                for k, cc in enumerate(cc_list):
                    v = mat.get((c6, cc), 0.0)
                    cell = wm.cell(r, 3 + k, round(v * escala, 0))
                    cell.number_format = money; cell.alignment = rgt
                    cell.border = bd
                    if abs(v) > 0 and (cc, c6) in destino:
                        cell.font = link
                        cell.hyperlink = Hyperlink(ref=cell.coordinate,
                                                   location=f"'{NDET}'!A{destino[(cc, c6)]}")
                    rtot += v
                tc = wm.cell(r, tcol, round(rtot * escala, 0))
                tc.number_format = money; tc.alignment = rgt; tc.font = bld
                wm.row_dimensions[r].outlineLevel = 1
                r += 1
    wm.column_dimensions["A"].width = 12; wm.column_dimensions["B"].width = 34
    for k in range(len(cc_list) + 1):
        wm.column_dimensions[get_column_letter(3 + k)].width = 13
    wm.freeze_panes = "C5"
    # mover las hojas del anexo al frente (después de las de estados)
    out = {}
    for cc in cc_list:
        t = tot_cc[cc]
        out[cc] = {"nombre": ccs[cc], "ingresos": round(t["ingresos"], 2),
                   "costos": round(t["costos"], 2), "gastos": round(t["gastos"], 2),
                   "utilidad": round(t["ingresos"] - t["costos"] - t["gastos"], 2)}
    return {"ccs": ccs, "n_cuentas": len(all_c6), "n_terceros_blocks": len(destino),
            "total_utilidad": round(sum(v["utilidad"] for v in out.values()), 2),
            "utilidad": {cc: out[cc]["utilidad"] for cc in cc_list}}


# ===========================================================================
# Administrativo: enlaces por tercero DENTRO de la hoja P&G por CC (2.E.R.I.)
# ===========================================================================
def _norm_cc(s):
    s = re.sub(r"\(.*?\)", "", str(s or "")).upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def enlazar_pyg_cc_tercero(wb, bp_cc_leido, mes, anio,
                           hoja="2.E.R.I. MES-ACUMULADO"):
    """En la hoja del P&G por centro de costo (la que ya trae el diseño con una
    columna por punto), pone HIPERVÍNCULOS en las celdas del MES ACTUAL, solo en
    las filas de cuentas clase 5, grupo 42, grupo 43 y la fila de COMPRAS (cuenta
    14 débitos). Cada enlace lleva a la hoja 'DETALLE TERCERO' con el desglose por
    tercero de esa cuenta en ese centro de costo. La cuenta 41 se deja igual."""
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.worksheet.hyperlink import Hyperlink
    if hoja not in wb.sheetnames:
        return None
    ws = wb[hoja]
    mkey = f"{anio}-{mes:02d}"
    # 1) localizar el bloque del mes actual (columna total con el rótulo del mes)
    total_col = None
    for j in range(1, ws.max_column + 1):
        v = ws.cell(8, j).value
        if v and mkey in str(v):
            total_col = j
    if not total_col:
        return None
    cc_cols = list(range(total_col - 9, total_col))   # 9 columnas de CC
    col_ccname = {j: str(ws.cell(8, j).value or "") for j in cc_cols}

    # 2) mapa nombre CC (encabezado) -> código de CC del balance
    rows = bp_cc_leido["rows"]
    cc_code_by_name = {}
    for r in rows:
        if r["cc"]:
            cc_code_by_name.setdefault(_norm_cc(r["nombre_cc"]), r["cc"])
    col_cc = {}
    for j in cc_cols:
        code = cc_code_by_name.get(_norm_cc(col_ccname[j]))
        if code:
            col_cc[j] = code

    # 3) cuentas HOJA = las que ninguna otra cuenta más larga extiende (no subtotales)
    codeset = set()
    for r in rows:
        c = _dig(r["cuenta"])
        if c:
            codeset.add(c)
    parents = set()
    for c in codeset:
        for L in range(2, len(c)):
            if c[:L] in codeset:
                parents.add(c[:L])
    hojas = codeset - parents

    # leafs por CC y leafs SIN CC (para repartir)
    leafs_by_cc = defaultdict(list)   # cc_code -> [(cta, nit, nom, cr_de, deb)]
    leafs_nocc = []                    # [(cta, nit, nom, cr_de, deb)]  (sin centro)
    for r in rows:
        cta = _dig(r["cuenta"])
        if not cta or cta not in hojas:   # solo cuentas hoja (movimiento real)
            continue
        tup = (cta, r["nit"], r["nombre_nit"], r["creditos"] - r["debitos"], r["debitos"])
        if r["cc"]:
            leafs_by_cc[r["cc"]].append(tup)        # detalle por CC
        elif r["nit"]:
            leafs_nocc.append(tup)                  # genuino SIN centro (tiene tercero)
        # sin cc y sin nit = fila de SUBTOTAL de la cuenta -> se ignora (duplica)

    def _mov(cta, cr_de, deb, es_compras):
        if es_compras:
            if cta.startswith(CUENTA_TRASLADO_COSTO):   # 143599, traslado al costo
                return 0.0
            return -cr_de                                # débitos − créditos
        return cr_de                                     # ingresos + / gastos −

    # 3b) BASE DE REPARTO: ventas (ingresos operacionales, clase 41) por CC → peso
    ventas_cc = defaultdict(float)
    for cc_code, lst in leafs_by_cc.items():
        for (cta, _n, _m, cr_de, _d) in lst:
            if cta.startswith("41"):
                ventas_cc[cc_code] += cr_de
    cc_mapeados = set(col_cc.values())
    tot_ventas = sum(v for cc, v in ventas_cc.items() if cc in cc_mapeados)
    # peso por columna
    peso = {}
    cols_map = [j for j in cc_cols if j in col_cc]
    for j in cols_map:
        peso[j] = (ventas_cc.get(col_cc[j], 0.0) / tot_ventas) if tot_ventas else (1.0 / len(cols_map))

    def detalle(prefix, cc_code, es_compras):
        agg = defaultdict(float); nombres = {}
        for (cta, nit, nom, cr_de, deb) in leafs_by_cc.get(cc_code, ()):
            if not cta.startswith(prefix):
                continue
            v = _mov(cta, cr_de, deb, es_compras)
            if v == 0:
                continue
            agg[nit] += v; nombres[nit] = nom
        return [(nit, nombres.get(nit, ""), val) for nit, val in agg.items()]

    def nocc_total(prefix, es_compras):
        s = 0.0
        for (cta, nit, nom, cr_de, deb) in leafs_nocc:
            if cta.startswith(prefix):
                s += _mov(cta, cr_de, deb, es_compras)
        return s

    # 4) filas a calcular/enlazar: clase 5, grupos 42/43, y compras (14)
    targets = []   # (fila, prefijo, es_compras)
    for i in range(9, ws.max_row + 1):
        code = _dig(ws.cell(i, 1).value)
        name = str(ws.cell(i, 2).value or "")
        if not code:
            continue
        if code.startswith("42") or code.startswith("43") or code.startswith("5"):
            targets.append((i, code, False))
        elif code == "14" and "compra" in name.lower():
            targets.append((i, code, True))

    # 5) hoja DETALLE: un bloque por (prefijo, cc) — dedup por código
    NDET = "DETALLE TERCERO"
    if NDET in wb.sheetnames:
        del wb[NDET]
    wd = wb.create_sheet(NDET)
    az = PatternFill("solid", fgColor="1F4E78"); grp = PatternFill("solid", fgColor="D9E1F2")
    wht = Font(color="FFFFFF", bold=True); bld = Font(bold=True)
    rgt = Alignment(horizontal="right"); link = Font(color="0563C1", underline="single")
    money = '#,##0'
    wd.cell(1, 1, f"DETALLE POR TERCERO — {MESES[mes]} {anio} (miles)").font = Font(bold=True, size=12, color="1F4E78")
    dr = 3
    destino = {}     # (prefijo, cc_code) -> fila
    # nombre de cada cuenta = el de su fila enlazada (para 14 -> "Compras")
    nombres_cta = {}
    for (fila, code, es_compras) in targets:
        nombres_cta.setdefault(code, str(ws.cell(fila, 2).value or "").strip())
    # precalcular el no-CC por cuenta (una vez)
    nocc_por_code = {}
    for (fila, code, es_compras) in targets:
        if code not in nocc_por_code:
            nocc_por_code[code] = nocc_total(code, es_compras)

    hechos = set()
    for (fila, code, es_compras) in targets:
        ncc = nocc_por_code.get(code, 0.0)
        for j in cols_map:
            cc_code = col_cc[j]
            if (code, cc_code) in hechos:
                continue
            det = detalle(code, cc_code, es_compras)     # directos por tercero
            reparto = ncc * peso.get(j, 0.0)             # parte del sin-CC (prop. ventas)
            if not det and abs(reparto) < 0.5:
                continue
            hechos.add((code, cc_code))
            destino[(code, cc_code)] = dr
            ccname = col_ccname[j].strip()
            tt = sum(v for _, _, v in det) + reparto
            h = wd.cell(dr, 1, f"{code}  {nombres_cta.get(code,'')}".strip())
            h.font = bld; h.fill = grp
            wd.cell(dr, 2, ccname).font = bld; wd.cell(dr, 2).fill = grp
            hv = wd.cell(dr, 3, round(tt / 1000.0, 0)); hv.font = bld; hv.fill = grp
            hv.number_format = money; hv.alignment = rgt
            bk = wd.cell(dr, 4, "↩ volver"); bk.font = link
            bk.hyperlink = Hyperlink(ref=bk.coordinate, location=f"'{hoja}'!A{fila}")
            dr += 1
            wd.cell(dr, 1, "NIT").font = bld; wd.cell(dr, 2, "Tercero").font = bld
            wd.cell(dr, 3, "Valor (miles)").font = bld
            dr += 1
            for nit, nom, val in sorted(det, key=lambda x: -abs(x[2])):
                wd.cell(dr, 1, nit); wd.cell(dr, 2, str(nom)[:45])
                vc = wd.cell(dr, 3, round(val / 1000.0, 0)); vc.number_format = money; vc.alignment = rgt
                dr += 1
            if abs(reparto) >= 0.5:
                wd.cell(dr, 1, "—")
                wd.cell(dr, 2, "REPARTO SIN CC (prop. ventas)").font = Font(italic=True, color="808080")
                vc = wd.cell(dr, 3, round(reparto / 1000.0, 0)); vc.number_format = money; vc.alignment = rgt
                vc.font = Font(italic=True, color="808080")
                dr += 1
            dr += 1
    wd.column_dimensions["A"].width = 16; wd.column_dimensions["B"].width = 36
    wd.column_dimensions["C"].width = 20; wd.column_dimensions["D"].width = 14
    wd.column_dimensions["E"].width = 10
    wd.freeze_panes = "A3"

    # 6) ESCRIBIR el valor por CC (directo + reparto) y poner el hipervínculo
    nlinks = 0
    for (fila, code, es_compras) in targets:
        ncc = nocc_por_code.get(code, 0.0)
        for j in cols_map:
            cc_code = col_cc[j]
            cell = ws.cell(fila, j)
            # no tocar celdas con fórmula
            if isinstance(cell.value, str) and cell.value.startswith("="):
                continue
            det = detalle(code, cc_code, es_compras)
            valor = sum(v for _, _, v in det) + ncc * peso.get(j, 0.0)
            cell.value = round(valor / 1000.0, 0)     # en miles
            cell.number_format = money
            if (code, cc_code) in destino:
                cell.hyperlink = Hyperlink(ref=cell.coordinate,
                                           location=f"'{NDET}'!A{destino[(code, cc_code)]}")
                base = cell.font
                cell.font = Font(color="0563C1", underline="single",
                                 bold=base.bold, size=base.sz, name=base.name)
                nlinks += 1
    # ubicar DETALLE junto a la hoja del P&G
    try:
        idx = wb.sheetnames.index(hoja)
        wb.move_sheet(NDET, offset=(idx + 1) - wb.sheetnames.index(NDET))
    except Exception:  # noqa: BLE001
        pass
    reparto_tot = sum(v for v in nocc_por_code.values())
    return {"n_links": nlinks, "n_bloques": len(destino), "mes_col_total": total_col,
            "reparto_sin_cc": round(reparto_tot / 1000.0, 0),
            "base_reparto": "ventas por CC" if tot_ventas else "partes iguales"}


# ===========================================================================
# INFORME NATIVO: P&G por centro de costo (todas las cuentas 4/5/6), mes y
# acumulado, con reparto de lo SIN CC (p.ej. la 43 intereses) prop. a ventas y
# drill-down por tercero. Generado 100% desde el balance (no rellena plantilla).
# ===========================================================================
def _hojas_set(rows):
    codeset = set()
    for r in rows:
        c = _dig(r["cuenta"])
        if c:
            codeset.add(c)
    parents = set()
    for c in codeset:
        for L in range(1, len(c)):
            if c[:L] in codeset:
                parents.add(c[:L])
    return codeset - parents


def _agrega_resultado(rows):
    """Devuelve estructuras para el P&G por CC:
       leaf_cc[(code,cc)] = [mes, acum]   ; leaf_nocc[code] = [mes, acum]
       terc[(code,cc)] = {nit:[nom,mes]}  ; ccs{code:nombre} ; nombre{code:nom}
    mes = créditos−débitos ; acum = −nuevo_saldo  (ingreso +, gasto −).
    Solo cuentas HOJA de clases 4/5/6."""
    hojas = _hojas_set(rows)
    leaf_cc = defaultdict(lambda: [0.0, 0.0])
    leaf_nocc = defaultdict(lambda: [0.0, 0.0])
    terc = defaultdict(dict)
    ccs = OrderedDict(); nombre = {}
    for r in rows:
        c = _dig(r["cuenta"])
        if not c or c[0] not in "456":
            continue
        if r["nombre"]:                       # nombre de TODO código (también padres/grupos)
            nombre[c] = r["nombre"]
        if c not in hojas:
            continue
        mes = r["creditos"] - r["debitos"]
        acum = -r["nuevo_saldo"]
        if r["cc"]:
            ccs.setdefault(r["cc"], r["nombre_cc"] or r["cc"])
            leaf_cc[(c, r["cc"])][0] += mes
            leaf_cc[(c, r["cc"])][1] += acum
            if r["nit"] and abs(mes) > 0:
                t = terc[(c, r["cc"])].setdefault(r["nit"], [r["nombre_nit"], 0.0])
                t[1] += mes
        elif r["nit"]:
            leaf_nocc[c][0] += mes
            leaf_nocc[c][1] += acum
    return leaf_cc, leaf_nocc, terc, ccs, nombre


def leer_estado_costo(fuente):
    """Lee el 'Estado del Costo' por punto de venta (con el que se hace el traslado
    del costo). Devuelve {codigo_cc_solo_dígitos: {'ini','comp','fin'}} en pesos.
    Columnas esperadas: CC | PUNTO DE VENTA | INVENTARIO INICIAL | (+) COMPRAS |
    (=) DISPONIBLE | (−) INV. FINAL | (=) COSTO."""
    import openpyxl
    data = fuente if isinstance(fuente, (bytes, bytearray)) else (
        fuente.read() if hasattr(fuente, "read") else open(fuente, "rb").read())
    ws = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    # el encabezado es la fila que trae al menos 2 de: inicial / compras / final
    # (tolera "INV. INICIAL", "INVENTARIO INICIAL", "+ COMPRAS", "− INV. FINAL", etc.)
    hdr_i = None
    for i, r in enumerate(rows[:15]):
        up = [str(c or "").strip().lower() for c in r]
        if sum(1 for x in up if ("inicial" in x or "compras" in x or "final" in x)) >= 2:
            hdr_i = i
            break
    if hdr_i is None:
        hdr_i = 3
    up = [str(c or "").strip().lower() for c in rows[hdr_i]]

    def col(*frag):
        for f in frag:
            for j, h in enumerate(up):
                if f in h:
                    return j
        return None
    cCC = col("centro de costo", "cc")
    if cCC is None:
        cCC = 0
    cIni = col("inicial")                         # "INV. INICIAL" / "INVENTARIO INICIAL"
    cComp = col("compras")
    cFin = col("inv. final", "inventario final", "inv final", "final")

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0
    out = {}
    for r in rows[hdr_i + 1:]:
        raw = str(r[cCC] or "").strip()
        if not raw or raw.upper().startswith("TOTAL"):
            continue
        code = "".join(ch for ch in raw if ch.isdigit())
        if not code:
            continue
        out[code] = {"ini": num(r[cIni]) if cIni is not None else 0.0,
                     "comp": num(r[cComp]) if cComp is not None else 0.0,
                     "fin": num(r[cFin]) if cFin is not None else 0.0}
    return out


def _incrustar_macro(xlsx_bytes):
    """Envuelve el .xlsx en un .xlsm incrustando la macro (vbaProject.bin) que, al
    hacer clic en el número de una cuenta, filtra la hoja DETALLE TERCERO por esa
    cuenta. Si el vbaProject.bin no está junto al módulo, devuelve el .xlsx igual."""
    import os as _os, zipfile as _zip, io as _io2
    vba = _os.path.join(_os.path.dirname(__file__), "vbaProject.bin")
    if not _os.path.exists(vba):
        return xlsx_bytes, False
    with _zip.ZipFile(_io2.BytesIO(xlsx_bytes), "r") as zin:
        data = {n: zin.read(n) for n in zin.namelist()}
    ct = data["[Content_Types].xml"].decode("utf-8").replace(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml")
    if "vbaProject" not in ct:
        ct = ct.replace("</Types>",
            '<Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/></Types>')
    rels = data["xl/_rels/workbook.xml.rels"].decode("utf-8")
    if "vbaProject" not in rels:
        rels = rels.replace("</Relationships>",
            '<Relationship Id="rIdVbaProj1" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="vbaProject.bin"/></Relationships>')
    data["[Content_Types].xml"] = ct.encode("utf-8")
    data["xl/_rels/workbook.xml.rels"] = rels.encode("utf-8")
    data["xl/vbaProject.bin"] = open(vba, "rb").read()
    out = _io2.BytesIO()
    with _zip.ZipFile(out, "w", _zip.ZIP_DEFLATED) as zout:
        for n, b in data.items():
            zout.writestr(n, b)
    return out.getvalue(), True


def generar_pyg_nativo(bp_cc, mes, anio, empresa="GRUPO DE LOLITA S.A.S",
                       nit="900.307.969-5", cartera=None, cxp=None,
                       bp_ant=None, anio_comp=None, historia=None, informe_hist=None,
                       inventario=None):
    """Construye el informe NATIVO (workbook nuevo) y devuelve sus bytes.
    cartera / cxp: informes de cartera del paquete administrativo.
    inventario: bytes del 'Estado del Costo' por punto de venta (traslado del
    costo); si se pasa, el inventario inicial/compras/final POR CENTRO DE COSTO
    del juego de inventarios se toma REAL de ahí, en vez de repartir por costo.
    bp_ant: balance del año anterior (comparativo ESF y ERI).
    historia: {periodo: {(cuenta,cc): valor_mes}} de meses anteriores del año
    (memoria) para armar la hoja de resultados MES A MES.
    informe_hist: bytes del INFORME ANTIGUO; de él se extrae el resultado POR
    CENTRO DE COSTO de los meses previos (mapeando los CC a los códigos nativos) y
    se siembra en `historia`. Los meses sembrados se devuelven en result['historia_seed']
    para persistirlos en memoria."""
    if isinstance(cartera, (bytes, bytearray)) or hasattr(cartera, "read") or isinstance(cartera, str):
        cartera = leer_cartera(cartera)
    if isinstance(cxp, (bytes, bytearray)) or hasattr(cxp, "read") or isinstance(cxp, str):
        cxp = leer_cartera(cxp)
    sub_ant = None; rows_ant = None
    if bp_ant is not None:
        rows_ant = leer_bp(bp_ant)["rows"]
        sub_ant = {}
        for rr_ in rows_ant:
            c = _dig(rr_["cuenta"])
            if c and not rr_["cc"] and not rr_["nit"]:
                sub_ant[c] = rr_["nuevo_saldo"]
    import io as _io
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.hyperlink import Hyperlink

    d = leer_bp(bp_cc)
    rows = d["rows"]
    leaf_cc, leaf_nocc, terc, ccs, nombre = _agrega_resultado(rows)
    hojas = _hojas_set(rows)
    cc_list = sorted(ccs.keys())
    leafcodes = sorted({c for (c, cc) in leaf_cc} | set(leaf_nocc))
    # Plaza Fabricato: es figura fiscal (ajena a la operación). No recibe reparto de
    # gastos/ingresos globales; su resultado real y su EBITDA se dejan en cero.
    cc_plaza = next((cc for cc in cc_list if "FABRICATO" in _norm_cc(ccs.get(cc, ""))), None)

    def _sin_plaza(w):
        """Anula el peso de reparto de Plaza y renormaliza el resto."""
        if cc_plaza and cc_plaza in w:
            w = dict(w); w[cc_plaza] = 0.0
            s = sum(w.values())
            if s:
                w = {cc: w[cc] / s for cc in w}
        return w

    # pesos de reparto por ventas (clase 41): mes y acumulado
    vt_mes = defaultdict(float); vt_acum = defaultdict(float)
    for (c, cc), (m, a) in leaf_cc.items():
        if c.startswith("41"):
            vt_mes[cc] += m; vt_acum[cc] += a
    tot_m = sum(vt_mes.values()); tot_a = sum(vt_acum.values())
    wm = _sin_plaza({cc: (vt_mes[cc] / tot_m if tot_m else 1.0 / len(cc_list)) for cc in cc_list})
    wa = _sin_plaza({cc: (vt_acum[cc] / tot_a if tot_a else 1.0 / len(cc_list)) for cc in cc_list})

    def sum_filter(pred):
        """(mes_cc{cc:v}, acum_cc{cc:v}) con reparto de lo sin-CC prop. ventas,
        sobre las cuentas hoja que cumplan el predicado `pred(codigo)`."""
        dm = defaultdict(float); da = defaultdict(float); nm = 0.0; na = 0.0
        for lc in leafcodes:
            if not pred(lc):
                continue
            for cc in cc_list:
                v = leaf_cc.get((lc, cc))
                if v:
                    dm[cc] += v[0]; da[cc] += v[1]
            nc = leaf_nocc.get(lc)
            if nc:
                nm += nc[0]; na += nc[1]
        mes_cc = {cc: dm.get(cc, 0.0) + nm * wm[cc] for cc in cc_list}
        acum_cc = {cc: da.get(cc, 0.0) + na * wa[cc] for cc in cc_list}
        return mes_cc, acum_cc

    def sum_prefix(prefix):
        return sum_filter(lambda lc: lc.startswith(prefix))

    ncc = len(cc_list)
    periodo = f"{anio}-{int(mes):02d}"
    historia = dict(historia or {})
    # sembrar meses previos POR CENTRO DE COSTO desde el informe antiguo
    historia_seed = {}
    if informe_hist is not None:
        cc_map = {_norm_cc(nom): code for code, nom in ccs.items()}
        try:
            extra = extraer_historia_eri(informe_hist, anio, hasta_periodo=periodo, cc_map=cc_map)
        except Exception:  # noqa: BLE001
            extra = {}
        for p, d in extra.items():
            if p not in historia:
                historia[p] = d; historia_seed[p] = d
    per_hist = sorted(p for p in historia if p < periodo and str(p)[:4] == str(anio))
    cur_md = leafdata_actual(leaf_cc, leaf_nocc)
    pdata = {}
    for p in per_hist + [periodo]:
        md = cur_md if p == periodo else historia[p]
        vt = defaultdict(float)
        for (cta, cc), v in md.items():
            if cc != NOCC and str(cta).startswith("41"):
                vt[cc] += v
        tv = sum(vt.values())
        w = _sin_plaza({cc: (vt[cc] / tv if tv else 1.0 / ncc) for cc in cc_list})
        pdata[p] = (md, w)

    def sPf(p, pred):
        md, w = pdata[p]; dm = defaultdict(float); nocc = 0.0
        for (cta, cc), v in md.items():
            if not pred(str(cta)):
                continue
            if cc == NOCC or cc == "__TOT__":
                nocc += v
            else:
                dm[cc] += v
        return {cc: dm.get(cc, 0.0) + nocc * w.get(cc, 0.0) for cc in cc_list}

    def sP(p, prefix):
        return sPf(p, lambda c: str(c).startswith(prefix))

    def tPf(p, pred):
        # total del mes p sobre las cuentas que cumplen pred (per-CC, sin-CC y __TOT__)
        md, _w = pdata[p]
        return sum(v for (cta, cc), v in md.items() if pred(str(cta)))

    def tP(p, prefix):
        return tPf(p, lambda c: c.startswith(prefix))

    # ---- año anterior (totales por prefijo, mes y acumulado) ----
    lc_ant = ln_ant = None
    if rows_ant is not None:
        lc_ant, ln_ant, _ta, _ca, _na = _agrega_resultado(rows_ant)

    def tot_antf(pred, idx):
        if lc_ant is None:
            return 0.0
        s = 0.0
        for (c, cc), (m, a) in lc_ant.items():
            if pred(str(c)):
                s += m if idx == 0 else a
        for c, (m, a) in ln_ant.items():
            if pred(str(c)):
                s += m if idx == 0 else a
        return s

    def tot_ant(prefix, idx):
        return tot_antf(lambda c: c.startswith(prefix), idx)

    # ---- diseño de columnas ----
    nh = len(per_hist)
    prior_period = per_hist[-1] if per_hist else None
    comp_ant = lc_ant is not None
    BW = ncc + 2                             # bloque mensual (CC + total + A.V)
    c_h0 = 3
    def hist_cc0(i): return c_h0 + i * BW    # 1ª col de CC del mes histórico i
    def hist_tot(i): return c_h0 + i * BW + ncc   # col TOTAL del mes histórico i
    def hist_av(i): return c_h0 + i * BW + ncc + 1   # col A.V del mes histórico i
    c_mes0 = c_h0 + nh * BW
    c_mes_tot = c_mes0 + ncc
    c_mes_av = c_mes_tot + 1
    c_gap = c_mes_av + 1
    c_ac0 = c_gap + 1
    c_ac_tot = c_ac0 + ncc
    c_ac_av = c_ac_tot + 1
    c_var = c_ac_av + 1                       # VAR MES ($)
    c_varp = c_var + 1                        # VAR MES (%)
    if comp_ant:
        # comparativo 2025: MES 2025 + A.V | ACUM 2025 + A.V | DIF AÑOS $ | DIF AÑOS %
        c_m25 = c_varp + 1; c_m25av = c_m25 + 1
        c_a25 = c_m25av + 1; c_a25av = c_a25 + 1
        c_va25 = c_a25av + 1; c_va25p = c_va25 + 1; ncol = c_va25p
    else:
        c_m25 = c_m25av = c_a25 = c_a25av = c_va25 = c_va25p = None; ncol = c_varp

    # ---------- construir workbook ----------
    NPG = "2.E.R.I. MES-ACUMULADO"
    wb = Workbook(); ws = wb.active; ws.title = NPG
    az = PatternFill("solid", fgColor="1F4E78"); wht = Font(color="FFFFFF", bold=True)
    clsf = PatternFill("solid", fgColor="BDD7EE"); grpf = PatternFill("solid", fgColor="DDEBF7")
    totf = PatternFill("solid", fgColor="FCE4D6")
    bld = Font(bold=True); cen = Alignment(horizontal="center", vertical="center")
    rgt = Alignment(horizontal="right"); link = Font(color="0563C1", underline="single")
    money = '#,##0'; esc = 0.001

    ws.cell(1, 1, empresa).font = Font(bold=True, size=13, color="1F4E78")
    ws.cell(2, 1, f"NIT: {nit}").font = Font(color="808080")
    ws.cell(3, 1, f"ESTADO DE RESULTADOS POR CENTRO DE COSTO — MES A MES · {MESES[mes]} {anio} "
                  "(miles). Clic en una cuenta para el detalle por tercero.").font = Font(italic=True, color="808080")
    hr = 5
    r_ing = hr + 1                            # fila de INGRESOS (base del A.V)
    ws.cell(hr, 1, "CUENTA").fill = az; ws.cell(hr, 1).font = wht
    ws.cell(hr, 2, "NOMBRE").fill = az; ws.cell(hr, 2).font = wht
    def _hcell(col, txt):
        c = ws.cell(hr, col, txt); c.fill = az; c.font = wht; c.alignment = cen; return c
    # meses históricos: bloque con CC desplegables + total + A.V (contraído por defecto)
    for i, p in enumerate(per_hist):
        mnum = int(str(p).split("-")[1])
        cc0 = hist_cc0(i); ctot = hist_tot(i)
        ws.merge_cells(start_row=hr - 1, start_column=cc0, end_row=hr - 1, end_column=hist_av(i))
        h = ws.cell(hr - 1, cc0, f"MES {MESES[mnum]}"); h.font = bld; h.alignment = cen
        for k, cc in enumerate(cc_list):
            _hcell(cc0 + k, ccs[cc])
        _hcell(ctot, p); _hcell(hist_av(i), "A.V")
    # bloque MES actual y ACUMULADO (con CC + A.V)
    ws.merge_cells(start_row=hr - 1, start_column=c_mes0, end_row=hr - 1, end_column=c_mes_av)
    ws.cell(hr - 1, c_mes0, f"MES {MESES[mes]}").font = bld; ws.cell(hr - 1, c_mes0).alignment = cen
    ws.merge_cells(start_row=hr - 1, start_column=c_ac0, end_row=hr - 1, end_column=c_ac_av)
    ws.cell(hr - 1, c_ac0, f"ACUMULADO {anio}").font = bld; ws.cell(hr - 1, c_ac0).alignment = cen
    for k, cc in enumerate(cc_list):
        for base in (c_mes0, c_ac0):
            _hcell(base + k, ccs[cc])
    _hcell(c_mes_tot, f"MES {MESES[mes][:3]}"); _hcell(c_mes_av, "A.V")
    _hcell(c_ac_tot, f"ACUM {anio}"); _hcell(c_ac_av, "A.V")
    _hcell(c_var, "VAR MES $"); _hcell(c_varp, "VAR MES %")
    if comp_ant:
        _ac = anio_comp or anio - 1
        _hcell(c_m25, f"MES {_ac}"); _hcell(c_m25av, "A.V")
        _hcell(c_a25, f"ACUM {_ac}"); _hcell(c_a25av, "A.V")
        _hcell(c_va25, "DIF AÑOS $"); _hcell(c_va25p, "DIF AÑOS %")

    # hoja de detalle por tercero (mes actual) — TABLA PLANA con AUTOFILTRO
    wd = wb.create_sheet("DETALLE TERCERO")
    wd.cell(1, 1, f"DETALLE POR TERCERO — {MESES[mes]} {anio} (miles) · "
                  "usa el filtro de cada columna (Cuenta, Centro de costo, "
                  "Tercero) para ver una cuenta").font = Font(bold=True, size=12, color="1F4E78")
    # encabezado de la tabla en la fila 3, con AutoFiltro
    for k, t in enumerate(["Cuenta", "Centro de costo", "NIT", "Tercero", "Valor mov. del mes"]):
        hc = wd.cell(3, 1 + k, t); hc.font = wht; hc.fill = az; hc.alignment = cen
    dr = 4; destino = {}

    def escribe_detalle(code4, back_ref=None):
        """Agrega las filas de una CUENTA a la tabla plana filtrable: una fila por
        (cuenta hoja, centro de costo, NIT) con el MOVIMIENTO DEL MES. Columnas:
        Cuenta | Centro de costo | NIT | Tercero | Valor mov. del mes. Registra en
        `destino` la primera fila de la cuenta para el salto desde el número."""
        nonlocal dr
        agg = {}                                     # (lc, cc, nit) -> [nombre, valor_mes]
        for lc in leafcodes:
            if lc.startswith(code4):
                for cc in cc_list:
                    for nit_, (nom_, val) in terc.get((lc, cc), {}).items():
                        a = agg.setdefault((lc, cc, nit_), [nom_, 0.0]); a[1] += val
        if not agg:
            return None
        destino[code4] = dr                          # primera fila de la cuenta
        # ordenado por centro de costo y, dentro de cada CC, por valor descendente
        for (lc, cc, nit_), (nom_, val) in sorted(
                agg.items(), key=lambda x: (str(ccs.get(x[0][1], x[0][1])), -abs(x[1][1]))):
            wd.cell(dr, 1, lc)
            wd.cell(dr, 2, ccs.get(cc, cc))
            wd.cell(dr, 3, nit_)
            wd.cell(dr, 4, str(nom_)[:38])
            vc = wd.cell(dr, 5, round(val * esc, 0)); vc.number_format = money; vc.alignment = rgt
            dr += 1
        return destino[code4]

    def _celda(rr, col, val, bold=False, fill=None):
        c = ws.cell(rr, col, round(val * esc, 0)); c.number_format = money; c.alignment = rgt
        if bold:
            c.font = bld
        if fill:
            c.fill = fill
        return c

    def _avf(rr, totcol, fill=None):
        """A.V = celda del total / INGRESOS del mismo mes (fórmula, %)."""
        L = get_column_letter(totcol)
        c = ws.cell(rr, totcol + 1, f"=IFERROR({L}{rr}/{L}{r_ing},0)")
        c.number_format = '0.0%'; c.alignment = rgt
        if fill:
            c.fill = fill
        return c

    def _pcts(rr, fill=None):
        """% variación mes vs mes anterior y % diferencia entre años (fórmulas)."""
        mesL = get_column_letter(c_mes_tot)
        if nh > 0:
            pL = get_column_letter(hist_tot(nh - 1))
            pv = ws.cell(rr, c_varp, f"=IFERROR(({mesL}{rr}-{pL}{rr})/ABS({pL}{rr}),0)")
        else:
            pv = ws.cell(rr, c_varp, 0)
        pv.number_format = '0.0%'; pv.alignment = rgt
        if fill:
            pv.fill = fill
        if comp_ant:
            acL = get_column_letter(c_ac_tot); a25L = get_column_letter(c_a25)
            dv = ws.cell(rr, c_va25p, f"=IFERROR(({acL}{rr}-{a25L}{rr})/ABS({a25L}{rr}),0)")
            dv.number_format = '0.0%'; dv.alignment = rgt
            if fill:
                dv.fill = fill

    def fila(r, code, nom, nivel, mes_cc, acum_cc, fill=None, drill4=None, match=None):
        pred = match or (lambda c: c.startswith(code))
        ci = ws.cell(r, 1, code); cn = ws.cell(r, 2, ("   " * nivel) + str(nom))
        if fill:
            for c in range(1, ncol + 1):
                ws.cell(r, c).fill = fill
            ci.font = bld; cn.font = bld
        # meses históricos: CC desplegables + total (negrilla) + A.V
        for i, p in enumerate(per_hist):
            mcc_h = sPf(p, pred); th = 0.0
            for k, cc in enumerate(cc_list):
                _celda(r, hist_cc0(i) + k, mcc_h[cc], fill=fill); th += mcc_h[cc]
            _celda(r, hist_tot(i), th, bold=True, fill=fill)
            _avf(r, hist_tot(i), fill=fill)
        drill_loc = (f"'DETALLE TERCERO'!A{destino[drill4]}"
                     if (drill4 and drill4 in destino) else None)
        tm = ta = 0.0
        for k, cc in enumerate(cc_list):
            m = mes_cc[cc]; a = acum_cc[cc]
            cm = _celda(r, c_mes0 + k, m); caa = _celda(r, c_ac0 + k, a)
            # el NÚMERO del mes es clicable (abre el detalle), pero se queda en NEGRO
            if drill_loc and abs(m) > 0:
                cm.hyperlink = Hyperlink(ref=cm.coordinate, location=drill_loc)
                cm.font = Font(color="FF000000")      # negro OPACO (evita el azul de hipervínculo)
            tm += m; ta += a
        mt = _celda(r, c_mes_tot, tm, bold=True, fill=fill); _avf(r, c_mes_tot, fill=fill)
        if drill_loc and abs(tm) > 0:                 # total del mes también clicable, en negro
            mt.hyperlink = Hyperlink(ref=mt.coordinate, location=drill_loc)
            mt.font = Font(bold=True, color="FF000000")
        _celda(r, c_ac_tot, ta, bold=True, fill=fill); _avf(r, c_ac_tot, fill=fill)
        prior = tPf(prior_period, pred) if prior_period else 0.0
        _celda(r, c_var, tm - prior, fill=fill)
        if comp_ant:
            a25 = tot_antf(pred, 1)
            _celda(r, c_m25, tot_antf(pred, 0), fill=fill)
            _celda(r, c_a25, a25, fill=fill)
            _avf(r, c_m25, fill=fill); _avf(r, c_a25, fill=fill)     # A.V 2025 mes y acum
            _celda(r, c_va25, ta - a25, fill=fill)
        _pcts(r, fill=fill)
        return tm, ta

    codes4 = sorted({lc[:4] for lc in leafcodes if len(lc) >= 4})
    for code4 in codes4:
        escribe_detalle(code4)
    if dr > 4:                                   # AutoFiltro sobre toda la tabla del detalle
        wd.auto_filter.ref = f"A3:E{dr - 1}"

    # ---- juego de inventarios POR CENTRO DE COSTO (14: inicial + compras − final = costo 61) ----
    inv_sa = inv_ns = 0.0
    for rr_ in rows:
        if _dig(rr_["cuenta"]) == "1435" and not rr_["cc"] and not rr_["nit"]:
            inv_sa = rr_["saldo_ant"]; inv_ns = rr_["nuevo_saldo"]
    inv_fin_bal = inv_ns                                     # inventario final del año (balance, 1435)
    # costo por CC (año y mes) desde el balance
    inv_costo_cc = defaultdict(float); inv_costo_mes_cc = defaultdict(float)
    for (lc, cc), (m, a) in leaf_cc.items():
        if str(lc).startswith("6"):
            inv_costo_cc[cc] += -a; inv_costo_mes_cc[cc] += -m
    inv_tot_costo = sum(inv_costo_cc.values())
    # inicial (enero) y compras (ene..jun) por CC, del informe antiguo
    _prim = per_hist[0] if per_hist else None
    inv_ini_ene_cc = {cc: (historia.get(_prim, {}).get(("__INVINI__", cc), 0.0) if _prim else 0.0)
                      for cc in cc_list}
    inv_comp_old_cc = {cc: sum(historia.get(p, {}).get(("__COMPRAS__", cc), 0.0) for p in per_hist)
                       for cc in cc_list}
    inv_compras_tot = inv_tot_costo + inv_fin_bal - sum(inv_ini_ene_cc.values())
    _july_comp = inv_compras_tot - sum(inv_comp_old_cc.values())
    inv_comp_full_cc = {}; inv_fin_acc_cc = {}
    for cc in cc_list:
        _sh = (inv_costo_cc[cc] / inv_tot_costo) if inv_tot_costo else 1.0 / max(1, len(cc_list))
        inv_comp_full_cc[cc] = inv_comp_old_cc[cc] + _july_comp * _sh
        inv_fin_acc_cc[cc] = inv_ini_ene_cc[cc] + inv_comp_full_cc[cc] - inv_costo_cc[cc]

    # INVENTARIO REAL POR CC: si se subió el Estado del Costo (traslado), se usa el
    # inventario inicial/compras/final REAL por centro de costo (en vez del reparto
    # por participación del costo). Mapea por código de CC (solo dígitos).
    if inventario is not None:
        est = inventario if isinstance(inventario, dict) else leer_estado_costo(inventario)
        if est:
            def _cod(cc):
                return "".join(ch for ch in str(cc) if ch.isdigit())
            for cc in cc_list:
                e = est.get(_cod(cc))
                if e:
                    inv_ini_ene_cc[cc] = e["ini"]
                    inv_comp_full_cc[cc] = e["comp"]
                    inv_fin_acc_cc[cc] = e["fin"]
                else:                                 # CC sin inventario en el traslado
                    inv_ini_ene_cc[cc] = 0.0
                    inv_comp_full_cc[cc] = 0.0
                    inv_fin_acc_cc[cc] = 0.0

    def inv_pcc(p, cc, which):
        """valor del juego por CC en el mes p ('ini','comp','fin')."""
        if p != periodo:
            key = {"ini": "__INVINI__", "comp": "__COMPRAS__", "fin": "__INVFIN__"}[which]
            return (historia.get(p, {}) or {}).get((key, cc), 0.0)
        ini = (historia.get(prior_period, {}).get(("__INVFIN__", cc), 0.0)
               if prior_period else inv_ini_ene_cc[cc])
        fin = inv_fin_acc_cc[cc]
        if which == "ini":
            return ini
        if which == "fin":
            return fin
        return inv_costo_mes_cc[cc] + fin - ini

    def inv_acc_cc(cc, which):
        return {"ini": inv_ini_ene_cc[cc], "comp": inv_comp_full_cc[cc],
                "fin": inv_fin_acc_cc[cc]}[which]

    def fila_juego(r, label, which, sign=1):
        """Fila del juego de inventarios con VALORES POR CC (mes histórico, mes
        actual y acumulado), total en negrilla y A.V."""
        ws.cell(r, 2, "   " + label).font = Font(italic=True, color="404040")
        for i, p in enumerate(per_hist):
            th = 0.0
            for k, cc in enumerate(cc_list):
                v = sign * inv_pcc(p, cc, which); _celda(r, hist_cc0(i) + k, v); th += v
            _celda(r, hist_tot(i), th, bold=True); _avf(r, hist_tot(i))
        tm = 0.0
        for k, cc in enumerate(cc_list):
            v = sign * inv_pcc(periodo, cc, which); _celda(r, c_mes0 + k, v); tm += v
        _celda(r, c_mes_tot, tm, bold=True); _avf(r, c_mes_tot)
        ta = 0.0
        for k, cc in enumerate(cc_list):
            v = sign * inv_acc_cc(cc, which); _celda(r, c_ac0 + k, v); ta += v
        _celda(r, c_ac_tot, ta, bold=True); _avf(r, c_ac_tot)
        prior = sum(sign * inv_pcc(prior_period, cc, which) for cc in cc_list) if prior_period else 0.0
        _celda(r, c_var, tm - prior)
        if comp_ant:                                  # comparativo 2025 del juego (mes y acum)
            m25v, a25v = inv25.get(which, (0.0, 0.0))
            a25 = sign * a25v
            _celda(r, c_m25, sign * m25v); _celda(r, c_a25, a25)
            _avf(r, c_m25); _avf(r, c_a25)
            _celda(r, c_va25, ta - a25)
        _pcts(r)
        ws.row_dimensions[r].outlineLevel = 1
        return r

    # comparativo 2025 del juego de inventarios (del balance del año anterior, cuenta 1435):
    #   mes = movimiento del mes; acum = inicial=saldo_ant, final=nuevo_saldo,
    #   compras=costo_acum+final−inicial (cuadra con el costo acumulado 2025).
    inv25 = {"ini": (0.0, 0.0), "comp": (0.0, 0.0), "fin": (0.0, 0.0)}
    if comp_ant and rows_ant is not None:
        _sa = _db = _ns = 0.0
        for _r in rows_ant:
            if _dig(_r["cuenta"]) == "1435" and not _r["cc"] and not _r["nit"]:
                _sa = _r["saldo_ant"]; _db = _r["debitos"]; _ns = _r["nuevo_saldo"]; break
        _costo_ac = -tot_ant("6", 1)                  # costo acumulado 2025 (positivo)
        inv25 = {"ini": (_sa, _sa),
                 "comp": (_db, _costo_ac + _ns - _sa),
                 "fin": (_ns, _ns)}

    CLS = OrderedDict([("4", "INGRESOS"), ("6", "COSTO DE VENTAS"), ("5", "GASTOS")])
    r = hr + 1
    for cls, cls_nom in CLS.items():
        codes_cls = [lc for lc in leafcodes if lc.startswith(cls)]
        if not codes_cls:
            continue
        m_cc, a_cc = sum_prefix(cls)
        fila(r, cls, cls_nom, 0, m_cc, a_cc, fill=clsf); r += 1
        # ---- COSTO DE VENTAS detallado como JUEGO DE INVENTARIOS (por CC) ----
        if cls == "6":
            fila_juego(r, "Inventario inicial", "ini"); r += 1
            fila_juego(r, "(+) Compras del periodo", "comp"); r += 1
            fila_juego(r, "(−) Inventario final", "fin", sign=-1); r += 1
            continue
        for g2 in sorted({lc[:2] for lc in codes_cls}):
            # ---- cuenta 41 resumida en 3 conceptos (como el informe antiguo) ----
            if g2 == "41":
                AJU = "41359599"      # dif. facturación DIAN vs ventas POS (Henko)
                p_dev = lambda c: c.startswith("4175")
                p_aju = lambda c: c == AJU
                p_vta = lambda c: (c.startswith("41") and not c.startswith("4175")
                                   and c != AJU)
                mg, ag = sum_prefix("41")
                fila(r, "41", nombre.get("41", "OPERACIONALES"), 1, mg, ag, fill=grpf,
                     match=lambda c: c.startswith("41"))
                ws.row_dimensions[r].outlineLevel = 1; r += 1
                conceptos = [
                    ("4135", "Ventas", p_vta, None),
                    ("4175", "Devoluciones", p_dev, "4175"),
                    (AJU, "Ajuste dif. Henko (fact. DIAN vs POS)", p_aju, None),
                ]
                for cod_lbl, txt, pr, drill in conceptos:
                    mm, aa = sum_filter(pr)
                    fila(r, cod_lbl, txt, 2, mm, aa, drill4=drill, match=pr)
                    ws.row_dimensions[r].outlineLevel = 2; r += 1
                continue
            mg, ag = sum_prefix(g2)
            fila(r, g2, nombre.get(g2, g2), 1, mg, ag, fill=grpf)
            ws.row_dimensions[r].outlineLevel = 1; r += 1
            g2_leaves = [lc for lc in codes_cls if lc[:2] == g2]
            for c4 in sorted({lc[:4] for lc in g2_leaves}):
                m4, a4 = sum_prefix(c4)
                fila(r, c4, nombre.get(c4, c4), 2, m4, a4, drill4=c4)
                ws.row_dimensions[r].outlineLevel = 2; r += 1
                for lc in sorted({x for x in g2_leaves if x[:4] == c4 and len(x) > 4}):
                    ml, al = sum_prefix(lc)
                    fila(r, lc, nombre.get(lc, lc), 3, ml, al, drill4=c4)
                    ws.row_dimensions[r].outlineLevel = 3; ws.row_dimensions[r].hidden = True; r += 1

    # ---------- resumen: operacional, financiero, neta, EBITDA, ajustes, real ----------
    def mtot(period, kind):
        t = lambda pref: tP(period, pref)
        base = t("41") + t("42") + t("6") + t("5") - t("53") - t("54")   # operacional
        if kind == "op":
            return base
        if kind == "ebitda":
            return base - t("5260") - t("5265")
        if kind == "neta":
            return base + t("43") + t("53") + t("54")
        return t(kind)
    def atot(kind):    # acumulado del año (mes actual, acum)
        _, a = sum_prefix("__none__")  # placeholder
        def ta(pref): return sum(sum_prefix(pref)[1].values())
        base = ta("41") + ta("42") + ta("6") + ta("5") - ta("53") - ta("54")
        if kind == "op":
            return base
        if kind == "ebitda":
            return base - ta("5260") - ta("5265")
        if kind == "neta":
            return base + ta("43") + ta("53") + ta("54")
        return ta(kind)
    def antot(kind):
        t = lambda pref: tot_ant(pref, 1)
        base = t("41") + t("42") + t("6") + t("5") - t("53") - t("54")
        if kind == "op":
            return base
        if kind == "ebitda":
            return base - t("5260") - t("5265")
        if kind == "neta":
            return base + t("43") + t("53") + t("54")
        if kind == "bruta":
            return t("41") + t("6")
        if kind == "otrgas":
            return t("55")
        if kind == "cosfin":
            return t("53")
        if kind == "operac":
            return base
        if kind == "antes":
            return base + t("43") + t("53")
        return t(kind)

    # --- versiones POR CENTRO DE COSTO (resultado centro por centro) ---
    def mtot_cc(period, kind):
        def t(pref): return sP(period, pref)      # {cc: valor} del mes
        base = {cc: t("41").get(cc, 0) + t("42").get(cc, 0) + t("6").get(cc, 0)
                + t("5").get(cc, 0) - t("53").get(cc, 0) - t("54").get(cc, 0) for cc in cc_list}
        if kind == "op":
            return base
        if kind == "ebitda":
            return {cc: base[cc] - t("5260").get(cc, 0) - t("5265").get(cc, 0) for cc in cc_list}
        if kind == "neta":
            return {cc: base[cc] + t("43").get(cc, 0) + t("53").get(cc, 0) + t("54").get(cc, 0) for cc in cc_list}
        if kind == "bruta":
            return {cc: t("41").get(cc, 0) + t("6").get(cc, 0) for cc in cc_list}
        if kind == "otrgas":                       # otros gastos: clase 55
            return {cc: t("55").get(cc, 0) for cc in cc_list}
        if kind == "cosfin":                       # costos financieros: clase 53
            return {cc: t("53").get(cc, 0) for cc in cc_list}
        if kind == "operac":                       # utilidad operacional (= base, incluye 55)
            return base
        if kind == "antes":                        # antes de impuestos
            return {cc: base[cc] + t("43").get(cc, 0) + t("53").get(cc, 0) for cc in cc_list}
        return t(kind)

    def atot_cc(kind):
        def ta(pref): return sum_prefix(pref)[1]   # {cc: acum}
        base = {cc: ta("41").get(cc, 0) + ta("42").get(cc, 0) + ta("6").get(cc, 0)
                + ta("5").get(cc, 0) - ta("53").get(cc, 0) - ta("54").get(cc, 0) for cc in cc_list}
        if kind == "op":
            return base
        if kind == "ebitda":
            return {cc: base[cc] - ta("5260").get(cc, 0) - ta("5265").get(cc, 0) for cc in cc_list}
        if kind == "neta":
            return {cc: base[cc] + ta("43").get(cc, 0) + ta("53").get(cc, 0) + ta("54").get(cc, 0) for cc in cc_list}
        if kind == "bruta":
            return {cc: ta("41").get(cc, 0) + ta("6").get(cc, 0) for cc in cc_list}
        if kind == "otrgas":
            return {cc: ta("55").get(cc, 0) for cc in cc_list}
        if kind == "cosfin":
            return {cc: ta("53").get(cc, 0) for cc in cc_list}
        if kind == "operac":
            return base
        if kind == "antes":
            return {cc: base[cc] + ta("43").get(cc, 0) + ta("53").get(cc, 0) for cc in cc_list}
        return ta(kind)

    def fila_cc(rr, label, get_pcc, get_acc, fill=None, bold=True, ital=False,
                m25=None, a25=None):
        """Escribe una fila con VALOR POR CC (meses históricos, mes actual y acum),
        total en negrilla, A.V y variaciones. get_pcc(p)->{cc:v}; get_acc()->{cc:v}."""
        cell = ws.cell(rr, 2, label)
        cell.font = Font(bold=(bold and not ital), italic=ital,
                         color=("808080" if ital else "000000"))
        for i, p in enumerate(per_hist):
            d = get_pcc(p); th = 0.0
            for k, cc in enumerate(cc_list):
                v = d.get(cc, 0.0); _celda(rr, hist_cc0(i) + k, v, fill=fill); th += v
            _celda(rr, hist_tot(i), th, bold=True, fill=fill); _avf(rr, hist_tot(i), fill=fill)
        dc = get_pcc(periodo); tm = 0.0
        for k, cc in enumerate(cc_list):
            v = dc.get(cc, 0.0); _celda(rr, c_mes0 + k, v, fill=fill); tm += v
        _celda(rr, c_mes_tot, tm, bold=True, fill=fill); _avf(rr, c_mes_tot, fill=fill)
        da = get_acc(); ta = 0.0
        for k, cc in enumerate(cc_list):
            v = da.get(cc, 0.0); _celda(rr, c_ac0 + k, v, fill=fill); ta += v
        _celda(rr, c_ac_tot, ta, bold=True, fill=fill); _avf(rr, c_ac_tot, fill=fill)
        prior = sum(get_pcc(prior_period).values()) if prior_period else 0.0
        _celda(rr, c_var, tm - prior, fill=fill)
        if comp_ant and m25 is not None:
            _celda(rr, c_m25, m25, fill=fill); _celda(rr, c_a25, a25, fill=fill)
            _avf(rr, c_m25, fill=fill); _avf(rr, c_a25, fill=fill)   # A.V 2025 mes y acum
            _celda(rr, c_va25, ta - a25, fill=fill)
        if fill:
            for c in range(1, ncol + 1):
                ws.cell(rr, c).fill = fill
        _pcts(rr, fill=fill)
        return tm, ta

    def rsum(rr, label, kind, fill=None, ital=False):
        return fila_cc(rr, label, lambda p: mtot_cc(p, kind), lambda: atot_cc(kind),
                       fill=fill, bold=True, ital=ital,
                       m25=(tot_ant_kind_mes(kind) if comp_ant else None),
                       a25=(antot(kind) if comp_ant else None))
        return rr

    def tot_ant_kind_mes(kind):
        t = lambda pref: tot_ant(pref, 0)
        base = t("41") + t("42") + t("6") + t("5") - t("53") - t("54")
        if kind == "op":
            return base
        if kind == "ebitda":
            return base - t("5260") - t("5265")
        if kind == "neta":
            return base + t("43") + t("53") + t("54")
        if kind == "bruta":
            return t("41") + t("6")
        if kind == "otrgas":
            return t("55")
        if kind == "cosfin":
            return t("53")
        if kind == "operac":
            return base
        if kind == "antes":
            return base + t("43") + t("53")
        return t(kind)

    # ---- ESTADO DE RESULTADOS (cascada tipo fiscal) ----
    r += 1
    rsum(r, "INGRESOS OPERACIONALES", "41", fill=grpf); r += 1
    rsum(r, "(−) Costo de ventas", "6"); r += 1
    rsum(r, "GANANCIA BRUTA", "bruta", fill=grpf); r += 1
    rsum(r, "(+) Otros ingresos (42)", "42"); r += 1
    rsum(r, "(−) Gastos operacionales de ventas (52)", "52"); r += 1
    rsum(r, "(−) Gastos operacionales de administración (51)", "51"); r += 1
    rsum(r, "(−) Otros gastos", "otrgas"); r += 1
    rsum(r, "GANANCIA (PÉRDIDA) OPERACIONAL", "operac", fill=grpf); r += 1
    rsum(r, "(+) Ingresos financieros (43)", "43"); r += 1
    rsum(r, "(−) Costos financieros (53)", "cosfin"); r += 1
    rsum(r, "GANANCIA (PÉRDIDA) ANTES DE IMPUESTOS", "antes", fill=grpf); r += 1
    rsum(r, "(−) Impuesto a las ganancias (54)", "54"); r += 1
    r_neta = r; rsum(r, "GANANCIA (PÉRDIDA) NETA — RESULTADO DEL EJERCICIO", "neta", fill=totf); r += 2
    # AJUSTES: meses previos reconstruidos del informe antiguo; mes en curso
    # AUTOMÁTICO según los comentarios del antiguo. RESULTADO REAL = neta + ajustes.
    from openpyxl.comments import Comment
    ws.cell(r, 2, "AJUSTES:").font = Font(bold=True, italic=True, color="808080"); r += 1

    def _bal_t(pref, idx="mes", nombre=None):
        s = 0.0
        for rr_ in rows:
            c = _dig(rr_["cuenta"])
            if not (c.startswith(pref) and (rr_["cc"] or rr_["nit"])):
                continue
            if nombre and nombre.upper() not in (rr_["nombre_nit"] or "").upper():
                continue
            s += (rr_["debitos"] - rr_["creditos"]) if idx == "mes" else rr_["nuevo_saldo"]
        return s
    cc_plaza = next((cc for cc in cc_list if "FABRICATO" in _norm_cc(ccs[cc])), None)
    ncc0 = max(1, len(cc_list))
    # automáticos del mes en curso, según los comentarios del informe antiguo
    ft_cur_tot = _bal_t("52359503", "mes")                    # servicio admón socios
    fe_cur_tot = _bal_t("52104501", "mes", nombre="SERVICIOS EMPRESARIALES")  # honorarios

    def _solo_op(d):
        """FT/FE se reparten solo entre CC OPERATIVOS (Plaza Fabricato queda en 0);
        el total del ajuste se divide igual entre ellos."""
        if not cc_plaza:
            return d
        tot = sum(d.values())
        return {cc: (0.0 if cc == cc_plaza else tot / _ncc_op) for cc in cc_list}

    def _aj_pcc(key, cur_map, p):
        if p != periodo:                                       # meses previos: del antiguo
            return _solo_op({cc: historia.get(p, {}).get((key, cc), 0.0) for cc in cc_list})
        return _solo_op(cur_map())

    def _aj_acc(key, cur_map):
        prev = _solo_op({cc: sum(historia.get(p, {}).get((key, cc), 0.0) for p in per_hist)
                         for cc in cc_list})
        cur = _solo_op(cur_map())
        return {cc: prev[cc] + cur.get(cc, 0.0) for cc in cc_list}

    _ncc_op = max(1, len([cc for cc in cc_list if cc != cc_plaza]))   # CC operativos (sin Plaza)

    def ft_cur():                                    # dividido igual entre CC operativos (sin Plaza)
        return {cc: (0.0 if cc == cc_plaza else ft_cur_tot / _ncc_op) for cc in cc_list}

    def fe_cur():
        return {cc: (0.0 if cc == cc_plaza else fe_cur_tot / _ncc_op) for cc in cc_list}

    def ar_pcc(p):     # AJUSTE que ANULA el resultado de Plaza Fabricato (figura fiscal)
        d = {cc: 0.0 for cc in cc_list}
        if cc_plaza:
            d[cc_plaza] = -mtot_cc(p, "neta").get(cc_plaza, 0.0)
        return d

    def ar_acc():
        d = {cc: 0.0 for cc in cc_list}
        if cc_plaza:
            d[cc_plaza] = -atot_cc("neta").get(cc_plaza, 0.0)
        return d

    def _ajrow(label, key, cur_map, comment):
        rr = r_hold[0]
        fila_cc(rr, label, lambda p: _aj_pcc(key, cur_map, p),
                lambda: _aj_acc(key, cur_map), ital=True)
        if comment:
            ws.cell(rr, 2).comment = Comment(comment, "Composición")
        r_hold[0] += 1
        return rr
    r_hold = [r]
    r_ft = _ajrow("(+) FT SERV ADMÓN PTOS VTA (DV)-UTILIDADES", "__AJ_FT__", ft_cur,
                  "Se SUMA a la utilidad (gasto que no va al resultado de la empresa). "
                  "Cuenta 52359503 — servicio admón a socios (Andrés Montoya, Fernando, Razem), "
                  "dividido igual por centro de costo.")
    r_fe = _ajrow("(+) FE SOCIOS (INTERESES)", "__AJ_FE__", fe_cur,
                  "Se SUMA a la utilidad (gasto que no va al resultado de la empresa). "
                  "Cuenta 52104501 — honorarios a Servicios Empresariales CYA, dividido igual por centro de costo.")
    # Ajuste de Plaza Fabricato: ANULA su resultado (no se toma de la historia; se
    # calcula como −neta del CC en cada periodo, para dejar su RESULTADO REAL en 0).
    r_ar = r_hold[0]
    fila_cc(r_ar, "(±) UTILIDAD / PÉRDIDA PLAZA FABRICATO", ar_pcc, ar_acc, ital=True)
    ws.cell(r_ar, 2).comment = Comment(
        "Plaza Fabricato es figura fiscal, ajena a la operación: su resultado se ANULA "
        "(−neta del CC), por eso su RESULTADO REAL y su EBITDA quedan en cero y no recibe "
        "reparto de gastos/ingresos globales.", "Composición")
    r_hold[0] += 1
    r = r_hold[0]

    def res_pcc(p):
        n = mtot_cc(p, "neta"); ft = _aj_pcc("__AJ_FT__", ft_cur, p)
        fe = _aj_pcc("__AJ_FE__", fe_cur, p); ar = ar_pcc(p)
        return {cc: n.get(cc, 0) + ft.get(cc, 0) + fe.get(cc, 0) + ar.get(cc, 0) for cc in cc_list}

    def res_acc():
        n = atot_cc("neta"); ft = _aj_acc("__AJ_FT__", ft_cur)
        fe = _aj_acc("__AJ_FE__", fe_cur); ar = ar_acc()
        return {cc: n.get(cc, 0) + ft.get(cc, 0) + fe.get(cc, 0) + ar.get(cc, 0) for cc in cc_list}
    r_res = r; fila_cc(r, "RESULTADO REAL", res_pcc, res_acc, fill=totf, bold=True); r += 1

    # EBITDA al final: se suma a la utilidad después de ajustes (RESULTADO REAL)
    # la depreciación y amortización (5260 + 5265), que son los gastos que no
    # implican salida de efectivo.
    def dep_pcc(p):
        d1 = sP(p, "5260"); d2 = sP(p, "5265")
        return {cc: (0.0 if cc == cc_plaza else -d1.get(cc, 0.0) - d2.get(cc, 0.0)) for cc in cc_list}

    def dep_acc():
        a1 = sum_prefix("5260")[1]; a2 = sum_prefix("5265")[1]
        return {cc: (0.0 if cc == cc_plaza else -a1.get(cc, 0.0) - a2.get(cc, 0.0)) for cc in cc_list}

    def ebi_pcc(p):
        res = res_pcc(p); dep = dep_pcc(p)
        return {cc: res.get(cc, 0.0) + dep.get(cc, 0.0) for cc in cc_list}

    def ebi_acc():
        res = res_acc(); dep = dep_acc()
        return {cc: res.get(cc, 0.0) + dep.get(cc, 0.0) for cc in cc_list}

    fila_cc(r, "(+) Depreciación y amortización", dep_pcc, dep_acc, ital=True); r += 1
    r_ebi = r; fila_cc(r, "EBITDA", ebi_pcc, ebi_acc, fill=grpf, bold=True); r += 1

    ws.column_dimensions["A"].width = 12; ws.column_dimensions["B"].width = 40
    for k in range(ncc + 1):
        ws.column_dimensions[get_column_letter(c_mes0 + k)].width = 12
        ws.column_dimensions[get_column_letter(c_ac0 + k)].width = 12
    for cx in [c_gap]:
        ws.column_dimensions[get_column_letter(cx)].width = 2
    # columnas de totales/variaciones/A.V (siempre visibles)
    for cx in ([c_mes_av, c_ac_av, c_var, c_varp] +
               ([c_m25, c_m25av, c_a25, c_a25av, c_va25, c_va25p] if comp_ant else [])):
        ws.column_dimensions[get_column_letter(cx)].width = 9 if cx in (
            c_mes_av, c_ac_av, c_varp, c_va25p, c_m25av, c_a25av) else 12
    # columnas de CC desplegables (contraídas por defecto): meses históricos + MES + ACUM
    hist_bases = [hist_cc0(i) for i in range(nh)]
    for base in hist_bases + [c_mes0, c_ac0]:
        for k in range(ncc):
            cl = ws.column_dimensions[get_column_letter(base + k)]
            cl.outlineLevel = 1; cl.hidden = True; cl.width = 12
    for i in range(nh):                       # total y A.V de cada mes histórico (visibles)
        ws.column_dimensions[get_column_letter(hist_tot(i))].width = 12
        ws.column_dimensions[get_column_letter(hist_av(i))].width = 9
    ws.sheet_properties.outlinePr.summaryRight = True
    ws.freeze_panes = ws.cell(hr + 1, 3).coordinate
    ws.sheet_properties.outlinePr.summaryBelow = False
    wd.column_dimensions["A"].width = 14; wd.column_dimensions["B"].width = 24
    wd.column_dimensions["C"].width = 16; wd.column_dimensions["D"].width = 38
    wd.column_dimensions["E"].width = 16
    wd.freeze_panes = "A4"

    # ===================== agregados consolidados (acumulado del año) =====================
    def totp(prefix, idx):
        s = 0.0
        for lc in leafcodes:
            if lc.startswith(prefix):
                for cc in cc_list:
                    v = leaf_cc.get((lc, cc))
                    if v:
                        s += v[idx]
                nc = leaf_nocc.get(lc)
                if nc:
                    s += nc[idx]
        return s
    # saldos de balance: usar los SUBTOTALES del balance (fila sin cc y sin nit),
    # así se cuentan también capital/reservas que no tienen tercero, y el balance
    # cuadra exacto (Activo = Pasivo + Patrimonio + Resultado).
    sub = {}; nom_bal = {}
    for rr_ in rows:
        c = _dig(rr_["cuenta"])
        if c and not rr_["cc"] and not rr_["nit"]:
            sub[c] = rr_["nuevo_saldo"]; nom_bal[c] = rr_["nombre"]
    def ns(prefix):
        return sub.get(prefix, 0.0)

    ing = totp("41", 1); otros = totp("42", 1); costo = totp("6", 1)
    gastos_op = totp("5", 1) - totp("53", 1) - totp("54", 1)
    op_t = ing + otros + costo + gastos_op
    fin = totp("43", 1) + totp("53", 1)
    antes_t = op_t + fin
    imp_t = totp("54", 1)
    neta_t = antes_t + imp_t
    ebitda_t = op_t - totp("5260", 1) - totp("5265", 1)
    bruta_t = ing + otros + costo
    resultado = -(ns("4") + ns("5") + ns("6"))     # utilidad del ejercicio (YTD)
    activo = ns("1"); pasivo = -ns("2")
    patrim = -ns("3") + resultado                   # patrimonio total (incluye resultado)
    inv = ns("14"); cxc = ns("13"); efec = ns("11")
    act_corr = ns("11") + ns("13") + ns("14") + ns("1355")
    pas_corr = pasivo + ns("21")                     # obligaciones financieras (21) = no corriente
    provs = -ns("2205")

    # inventario POR CENTRO DE COSTO (para OBSERVACIONES): inicial (año) + compras
    # (año) − final = costo, por CC. inicial/final del informe antiguo por CC; el
    # costo del balance (clase 6 por CC). Compras se deriva para que cuadre.
    # inventario FINAL por punto de venta (mismo del juego del ERI, acumulado)
    inv_cc = [(ccs[cc], inv_fin_acc_cc.get(cc, 0.0) * esc) for cc in cc_list
              if abs(inv_fin_acc_cc.get(cc, 0.0) * esc) >= 1]
    iva_bim = None
    if informe_hist is not None:
        try:
            iva_bim = extraer_iva_bimestres(informe_hist)
        except Exception:  # noqa: BLE001
            iva_bim = None
    _observaciones_sheet(wb, rows, sub, nom_bal, MESES[mes], anio, esc=esc,
                         cartera=cartera, cxp=cxp, mes=mes, inv_cc=inv_cc,
                         iva_bimestres=iva_bim)
    res_ant = None
    if sub_ant is not None:
        res_ant = -(sub_ant.get("4", 0.0) + sub_ant.get("5", 0.0) + sub_ant.get("6", 0.0))
    _esf_sheet(wb, MESES[mes], anio, sub, nom_bal, resultado, esc=esc,
               sub_ant=sub_ant, resultado_ant=res_ant, anio_comp=anio_comp or (anio - 1),
               mes=mes)

    # ---- provisión de renta: saldos digitados de meses previos (informe antiguo) ----
    prov_hist = {"meses": {}, "disc": {"nombre": None, "meses": {}}}
    if informe_hist is not None:
        try:
            prov_hist = extraer_provision_hist(informe_hist, anio, periodo)
        except Exception:  # noqa: BLE001
            pass
    disc_nom = prov_hist["disc"].get("nombre")
    disc_hist = prov_hist["disc"].get("meses", {})

    def _mov_bal(pref):
        return sum(rr["debitos"] - rr["creditos"] for rr in rows
                   if _dig(rr["cuenta"]).startswith(pref) and (rr["cc"] or rr["nit"]))

    def _gasto_persona(nombre):
        """Gasto (clase 5) atribuido a un tercero por su nombre → (mes, acumulado)."""
        if not nombre:
            return 0.0, 0.0
        up = re.sub(r"\s+", " ", str(nombre).strip().upper())
        mesv = acum = 0.0
        for rr in rows:
            nn = re.sub(r"\s+", " ", (rr["nombre_nit"] or "").strip().upper())
            if nn and (nn == up or up in nn or nn in up) and _dig(rr["cuenta"]).startswith("5"):
                acum += rr["nuevo_saldo"]; mesv += (rr["debitos"] - rr["creditos"])
        return mesv, acum
    disc_mes, disc_acum = _gasto_persona(disc_nom)

    MANUAL = ("nda", "asu", "eja", "don", "comp", "sfa", "antant", "ansig")
    prov = []
    for p in per_hist + [periodo]:
        mnum = int(str(p).split("-")[1])
        hm = prov_hist["meses"].get(p, {})
        d = dict(label=MESES[mnum].upper(), periodo=p,
                 ing=tP(p, "41"), util=mtot(p, "neta"),
                 gmf=0.5 * (-tP(p, "530506")),        # 50% del movimiento del GMF 4x1000
                 mora=-tP(p, "530521"),
                 multas=-tP(p, "559520"),
                 ndv=-tP(p, "529596"),                # gastos no deducibles ventas (529596)
                 ndind=-tP(p, "52959515"))            # gastos no deducibles costos indirectos
        if p == periodo:                       # mes en curso
            for f in MANUAL:
                d[f] = None                    # digitable (aún no hay saldo)
            d["ret"] = _mov_bal("195515"); d["aut"] = _mov_bal("195519")
            d["disc"] = disc_mes               # gasto del mes de la persona (balance)
        else:                                  # meses previos: del informe antiguo
            for f in MANUAL:
                d[f] = hm.get(f)
            d["ret"] = hm.get("ret"); d["aut"] = hm.get("aut")
            d["disc"] = disc_hist.get(p)
        prov.append(d)
    _provision_renta_sheet(wb, MESES[mes], anio, prov, esc=esc,
                           reten_acum=sub.get("195515", 0.0),
                           autoret_acum=sub.get("195519", 0.0),
                           disc={"nombre": disc_nom, "acum": disc_acum})
    def _kpis(f):
        ing_ = f("41"); otros_ = f("42"); costo_ = f("6")
        gastos_op_ = f("5") - f("53") - f("54")
        op_ = ing_ + otros_ + costo_ + gastos_op_
        fin_ = f("43") + f("53"); neta_ = op_ + fin_ + f("54")
        return dict(ing=ing_, op=op_, neta=neta_, bruta=ing_ + otros_ + costo_,
                    ebitda=op_ - f("5260") - f("5265"), gtot=f("5") - f("54"),
                    nomina=f("5205") + f("5210") + f("5215"))
    gpl = _kpis(lambda p: totp(p, 1))
    gpl_ant = _kpis(lambda p: tot_ant(p, 1)) if rows_ant is not None else \
        {k: 0.0 for k in gpl}
    _indicadores_sheet(wb, MESES[mes], anio, mes, gpl, gpl_ant,
                       anio_comp=anio_comp or (anio - 1), esc=esc)

    # orden de hojas: 1 ERI, 2 ESF, 3 Provisión, 4 Indicadores, 5 Observaciones, 6 Movimiento
    orden = [NPG, "4.ESF=BALANCE", "OBSERVACIONES", "PROVISION RENTA", "INDICADORES",
             "DETALLE TERCERO"]
    wb._sheets.sort(key=lambda s: orden.index(s.title) if s.title in orden else 99)

    # MEMORIA del mes en curso: además del resultado por cuenta×CC, guardar los datos
    # ESPECIALES del mes (juego de inventarios y ajustes FT/FE) para que el próximo mes
    # reconstruya bien la columna de ESTE mes sin volver a subir nada.
    leafdata_mem = dict(cur_md)
    for cc in cc_list:
        vi = inv_pcc(periodo, cc, "ini"); vco = inv_pcc(periodo, cc, "comp"); vf = inv_pcc(periodo, cc, "fin")
        if abs(vi) > 0:  leafdata_mem[("__INVINI__", cc)] = vi
        if abs(vco) > 0: leafdata_mem[("__COMPRAS__", cc)] = vco
        if abs(vf) > 0:  leafdata_mem[("__INVFIN__", cc)] = vf
    _ftm = ft_cur(); _fem = fe_cur()
    for cc in cc_list:
        if abs(_ftm.get(cc, 0.0)) > 0: leafdata_mem[("__AJ_FT__", cc)] = _ftm[cc]
        if abs(_fem.get(cc, 0.0)) > 0: leafdata_mem[("__AJ_FE__", cc)] = _fem[cc]

    forzar_recalculo(wb)
    buf = _io.BytesIO(); wb.save(buf)
    final_bytes, con_macro = _incrustar_macro(buf.getvalue())
    return {"bytes": final_bytes, "es_xlsm": con_macro, "ccs": ccs, "n_cuentas": len(leafcodes),
            "n_detalles": len(destino), "periodo": periodo, "leafdata": leafdata_mem,
            "meses": per_hist + [periodo], "historia_seed": historia_seed,
            "reparto_mes": round(sum(leaf_nocc[c][0] for c in leaf_nocc) * esc, 0),
            "reparto_acum": round(sum(leaf_nocc[c][1] for c in leaf_nocc) * esc, 0)}


# ===========================================================================
# Hojas auxiliares del informe nativo: PROVISION RENTA e INDICADORES
# ===========================================================================
def _estilo_hoja(ws):
    from openpyxl.styles import Font, PatternFill, Alignment
    return dict(
        az=PatternFill("solid", fgColor="1F4E78"), wht=Font(color="FFFFFF", bold=True),
        grp=PatternFill("solid", fgColor="D9E1F2"), tot=PatternFill("solid", fgColor="FCE4D6"),
        bld=Font(bold=True), ital=Font(italic=True, color="808080"),
        rgt=Alignment(horizontal="right"))


def _provision_renta_sheet(wb, mes_nom, anio, prov, esc=0.001, tarifa=0.35,
                           reten_acum=0.0, autoret_acum=0.0, disc=None):
    """PROYECCIÓN DEL IMPUESTO DE RENTA con el DISEÑO del informe anterior: MES A
    MES + ACUMULADO. Toma AUTOMÁTICO del balance ingresos, utilidad, GMF 50%
    (gravamen 4x1000), intereses de mora, multas y no deducibles; los demás rubros
    (retenciones, autorretenciones, compensaciones, etc.) quedan en gris (digitables)
    y todo lo demás se recalcula por fórmula."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter as GL
    if "PROVISION RENTA" in wb.sheetnames:
        del wb["PROVISION RENTA"]
    ws = wb.create_sheet("PROVISION RENTA")
    ws.sheet_view.showGridLines = False
    band = PatternFill("solid", fgColor="DDEBF7"); gris = PatternFill("solid", fgColor="D9D9D9")
    naranja = PatternFill("solid", fgColor="FCE4D6"); amar = PatternFill("solid", fgColor="FFF2CC")
    bld = Font(bold=True); rgt = Alignment(horizontal="right"); cen = Alignment(horizontal="center", vertical="center")
    edit = Font(color="0563C1"); rojo = Font(color="C00000")
    thin = Side(style="thin", color="BFBFBF")
    money = '#,##0'; pct = '0.0%'
    nmes = len(prov)
    # columnas: A vacía-margen, B etiqueta, C..(C+nmes-1) meses, luego ACUMULADO
    c0 = 3
    cacc = c0 + nmes                       # columna ACUMULADO
    cols_mes = list(range(c0, c0 + nmes))
    def L(c): return GL(c)
    # ---- título ----
    for i, t in enumerate(["GRUPO DE LOLITA SAS", "NIT: 900.307.969-5",
                           f"A {mes_nom.upper()} DE {anio}",
                           f"PROYECCION IMPUESTO DE RENTA AÑO GRAVABLE {anio}",
                           "(Cifras Expresadas en Miles de Pesos Colombianos)"]):
        ws.merge_cells(start_row=i + 1, start_column=2, end_row=i + 1, end_column=cacc)
        c = ws.cell(i + 1, 2, t); c.alignment = cen
        c.font = Font(bold=True, size=12 if i else 13, color="1F4E78" if i == 0 else "000000")
        for cc in range(2, cacc + 1):
            ws.cell(i + 1, cc).fill = band
    ws.cell(7, 2, "La siguiente proyección es válida solo para empresas con utilidad acumulada.").font = Font(italic=True, color="1F7A1F")
    # ---- encabezado de meses ----
    hr = 9
    for j, d in enumerate(prov):
        c = ws.cell(hr, c0 + j, d["label"]); c.font = bld; c.alignment = cen
    ca = ws.cell(hr, cacc, "ACUMULADO"); ca.font = bld; ca.alignment = cen
    ws.cell(hr, cacc + 2, "DILIGENCIAR LOS VALORES EN GRIS").font = Font(italic=True, color="808080")

    def sumfmt(row):
        return f"=SUM({L(c0)}{row}:{L(c0+nmes-1)}{row})"

    rows_ref = {}
    def fila(row, txt, valores=None, formula=None, acum=None, acum_val=None, fmt=money,
             bold=False, fill=None, editable=False, pctrow=False, rojo_=False, perfield=None):
        ws.cell(row, 2, txt)
        if bold:
            ws.cell(row, 2).font = bld
        if rojo_:
            ws.cell(row, 2).font = rojo
        if perfield is not None:                    # valor por mes (None = digitable)
            valores = [d.get(perfield) for d in prov]
            editable = True
        for j in range(nmes):
            cc = ws.cell(row, c0 + j)
            v = valores[j] if valores is not None else None
            if formula:
                cc.value = formula(row, c0 + j, L(c0 + j))
            elif pctrow:
                cc.value = f"=IFERROR({L(c0+j)}{pctrow}/{L(c0+j)}{pctrow-1},0)"
            elif editable and v is None:
                cc.value = None; cc.fill = gris; cc.font = edit
            else:
                cc.value = round((v or 0) * esc, 0)
            cc.number_format = fmt; cc.alignment = rgt
            if bold:
                cc.font = bld
            if fill:
                cc.fill = fill
        # ACUMULADO
        ca = ws.cell(row, cacc)
        if pctrow:
            ca.value = f"=IFERROR({L(cacc)}{pctrow}/{L(cacc)}{pctrow-1},0)"
        elif acum_val is not None:
            ca.value = round(acum_val * esc, 0)
        elif acum == "sum":
            ca.value = sumfmt(row)
        elif acum:
            ca.value = acum(row, cacc, L(cacc))
        elif editable:
            ca.value = sumfmt(row); ca.fill = gris
        else:
            ca.value = sumfmt(row)
        ca.number_format = fmt; ca.alignment = rgt
        if bold:
            ca.font = bld
        if fill:
            ca.fill = fill
        rows_ref[txt] = row
        return row

    r = hr + 1
    R_ING = fila(r, "INGRESOS NETOS OPERACIONALES", [d["ing"] for d in prov], bold=True); r += 1
    R_UTIL = fila(r, "UTILIDAD CONTABLE ACUMULADA", [d["util"] for d in prov], bold=True); r += 1
    R_PCT = r; fila(r, "", pctrow=R_UTIL, fmt=pct); r += 1
    R_NDA = fila(r, "Gastos No Deducibles Admon", perfield="nda"); r += 1
    R_NDV = fila(r, "Gastos No Deducibles Ventas (529596)", [d["ndv"] for d in prov]); r += 1
    R_GMF = fila(r, "GMF 50% (530506)", [d["gmf"] for d in prov]); r += 1
    R_MORA = fila(r, "Intereses Por Mora Fiscal", [d["mora"] for d in prov], rojo_=True); r += 1
    R_ASU = fila(r, "Impuestos Asumidos", perfield="asu"); r += 1
    R_EJA = fila(r, "Costos y Gastos de Ejercicios Ant", perfield="eja"); r += 1
    R_MUL = fila(r, "Multas y Sanciones", [d["multas"] for d in prov]); r += 1
    R_NDI = fila(r, "Gastos No Deducibles costos indirectos", [d["ndind"] for d in prov]); r += 1
    R_DON = fila(r, "Donaciones", perfield="don"); r += 1
    r += 1
    # UTILIDAD FISCAL = utilidad + no deducibles
    def f_fiscal(row, col, cl):
        return (f"=+{cl}{R_UTIL}+{cl}{R_NDA}+{cl}{R_NDV}+{cl}{R_GMF}+{cl}{R_MORA}"
                f"+{cl}{R_ASU}+{cl}{R_EJA}+{cl}{R_MUL}+{cl}{R_NDI}+{cl}{R_DON}")
    R_FIS = fila(r, "UTILIDAD FISCAL", formula=f_fiscal, acum=f_fiscal, bold=True); r += 1
    R_COMP = fila(r, "COMPENSACION DE PRESUNTIVA", perfield="comp", fill=amar); r += 1
    r += 1
    # deducción por discapacidad = gasto atribuido al/los trabajador(es) con discapacidad
    # (100% adicional → doble deducción). Mes en curso y acumulado AUTOMÁTICOS del
    # balance por el NIT de la persona; meses previos del informe antiguo.
    disc = disc or {}
    lbl_disc = ("Gasto trabajador con discapacidad: " + disc["nombre"]) \
        if disc.get("nombre") else "Gasto trabajador(es) con discapacidad (digita)"
    R_SALD = fila(r, lbl_disc, perfield="disc", acum_val=disc.get("acum", 0.0)); r += 1
    def f_disc(row, col, cl):
        return f"=+{cl}{R_SALD}"
    R_DISC = fila(r, "DEDUCCIÓN POR DISCAPACIDAD 200% (100% ADICIONAL)",
                  formula=f_disc, acum=f_disc, bold=True); r += 1
    r += 1
    def f_rl(row, col, cl):
        return f"=+{cl}{R_FIS}-{cl}{R_COMP}-{cl}{R_DISC}"
    R_RL = fila(r, "RENTA LIQUIDA", formula=f_rl, acum=f_rl, bold=True); r += 1
    def f_imp(row, col, cl):
        return f"=+{cl}{R_RL}*{tarifa}"
    R_IMP = fila(r, "Impuesto de Renta", formula=f_imp, acum=f_imp, fill=naranja); r += 1
    def f_neto(row, col, cl):
        return f"=+{cl}{R_IMP}"
    R_NETO = fila(r, "Impuesto Neto de Renta Corriente", formula=f_neto, acum=f_neto,
                  bold=True, fill=gris); r += 1
    r += 1
    R_SFA = fila(r, "Saldo a Favor Renta año anterior", perfield="sfa"); r += 1
    R_ANT = fila(r, "Anticipo de Renta año anterior", perfield="antant"); r += 1
    R_RET = fila(r, "Retenciones que le practicaron (195515)", perfield="ret",
                 acum_val=reten_acum); r += 1
    R_AUT = fila(r, "Autorretenciones (195519)", perfield="aut",
                 acum_val=autoret_acum); r += 1
    R_ANS = fila(r, "Anticipo de Renta año siguiente", perfield="ansig"); r += 1
    r += 1
    def f_saldo(row, col, cl):
        return f"=+{cl}{R_NETO}-{cl}{R_SFA}-{cl}{R_RET}-{cl}{R_AUT}"
    R_SAL = fila(r, "Saldo a Favor / Pagar Aprox Renta", formula=f_saldo, acum=f_saldo, bold=True); r += 1
    # A PAGAR / A FAVOR
    ws.cell(r, 2, "").font = bld
    for j in range(nmes):
        cl = L(c0 + j)
        c = ws.cell(r, c0 + j, f'=IF({cl}{R_SAL}>=0,"A PAGAR","A FAVOR")'); c.alignment = cen
        c.font = Font(bold=True, color="C00000")
    cl = L(cacc)
    ws.cell(r, cacc, f'=IF({cl}{R_SAL}>=0,"A PAGAR","A FAVOR")').alignment = cen
    ws.cell(r, cacc).font = Font(bold=True, color="C00000")
    # anchos
    ws.column_dimensions["A"].width = 2; ws.column_dimensions["B"].width = 44
    for c in cols_mes + [cacc]:
        ws.column_dimensions[L(c)].width = 12
    from openpyxl.worksheet.properties import PageSetupProperties
    ws.page_setup.orientation = "landscape"; ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.freeze_panes = ws.cell(hr + 1, c0).coordinate


def _indicadores_sheet(wb, mes_nom, anio, mes, gpl, gpl_ant, anio_comp=None, esc=0.001):
    """ANÁLISIS GERENCIAL con el DISEÑO del informe anterior (OTROS, LIQUIDEZ,
    ENDEUDAMIENTO, ACTIVIDAD, RENTABILIDAD, DETERIOROS PATRIMONIALES), dos columnas
    (año actual vs anterior), TODO por fórmulas auditables: los rubros de balance
    referencian la hoja 4.ESF=BALANCE y los de resultado una base P&G (miles)."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    if "INDICADORES" in wb.sheetnames:
        del wb["INDICADORES"]
    ws = wb.create_sheet("INDICADORES")
    ws.sheet_view.showGridLines = False
    mm = int(mes); ac = anio_comp or (anio - 1)
    per_act = f"{anio}-{mm:02d}"; per_ant = f"{ac}-{mm:02d}"
    ESF = "'4.ESF=BALANCE'"
    band = PatternFill("solid", fgColor="DDEBF7"); sec = PatternFill("solid", fgColor="D9E1F2")
    diaf = PatternFill("solid", fgColor="D9D2B0"); info = PatternFill("solid", fgColor="EAF1FB")
    bld = Font(bold=True); cen = Alignment(horizontal="center", vertical="center")
    rgt = Alignment(horizontal="right"); wrap = Alignment(wrap_text=True, vertical="center")
    thin = Side(style="thin", color="BFBFBF"); dark = Side(style="thin", color="404040")
    cb = Border(top=thin, bottom=thin, left=thin, right=thin)
    money = '#,##0'; pct = '0.0%'; ratio = '0.00'; dias = '0'
    # ---- banda de título ----
    tit = ["GRUPO DE LOLITA SAS", "NIT: 900.307.969-5", "ANALISIS  GERENCIAL",
           f"A {mes_nom.upper()} DE {anio} Y {ac}"]
    for i, t in enumerate(tit):
        ws.merge_cells(start_row=i + 1, start_column=1, end_row=i + 1, end_column=5)
        c = ws.cell(i + 1, 1, t); c.alignment = cen
        c.font = Font(bold=True, size=13 if i == 0 else 11, color="1F4E78" if i == 0 else "000000")
        for cc in range(1, 6):
            ws.cell(i + 1, cc).fill = band
    # ---- base P&G (miles) en G:I, auditable, referenciada por las fórmulas ----
    ws.cell(5, 7, "BASE P&G (miles)").font = bld
    ws.cell(5, 8, per_act).font = bld; ws.cell(5, 9, per_ant).font = bld
    base_rows = [("ing", "Ingresos netos oper."), ("op", "Utilidad operacional"),
                 ("neta", "Utilidad neta"), ("bruta", "Utilidad bruta"),
                 ("ebitda", "EBITDA"), ("gtot", "Gastos totales (sin imp.)"),
                 ("nomina", "Gasto de nómina")]
    gref = {}
    for i, (k, lbl) in enumerate(base_rows):
        rr_ = 6 + i; gref[k] = rr_
        ws.cell(rr_, 7, lbl)
        a = ws.cell(rr_, 8, round(gpl[k] * esc, 0)); b = ws.cell(rr_, 9, round(gpl_ant[k] * esc, 0))
        for cc in (a, b):
            cc.number_format = money; cc.alignment = rgt
    Ga = lambda k: f"$H${gref[k]}"; Gp = lambda k: f"$I${gref[k]}"

    def seccion(r, txt):
        ws.cell(r, 1, txt).font = bld
        ws.cell(r, 2, per_act).font = bld; ws.cell(r, 3, per_ant).font = bld
        for cc in range(1, 6):
            ws.cell(r, cc).fill = sec
        for cc in (2, 3):
            ws.cell(r, cc).alignment = cen

    def fila(r, txt, f26, f25, fmt=money, resalta=False):
        ws.cell(r, 1, txt)
        a = ws.cell(r, 2, f26); b = ws.cell(r, 3, f25)
        for cc in (a, b):
            cc.number_format = fmt; cc.alignment = rgt; cc.border = cb
            if resalta:
                cc.fill = diaf; cc.font = bld
    # ============================ OTROS ============================
    seccion(5, "OTROS")
    fila(6, "EBITDA", f"=+{Ga('ebitda')}", f"=+{Gp('ebitda')}")
    fila(7, "CASH FLOW", f"=+{Ga('neta')}", f"=+{Gp('neta')}");
    ws.cell(7, 1).font = bld; ws.cell(7, 2).font = bld; ws.cell(7, 3).font = bld
    fila(8, "GASTOS TOTALES (SIN PROVISION IMPUESTOS)", f"=+{Ga('gtot')}", f"=+{Gp('gtot')}")
    fila(9, "COSTO DE CARTERA", f"=+{ESF}!C28+{ESF}!C32", f"=+{ESF}!F28+{ESF}!F32")
    fila(10, "COSTO DE INVENTARIO", f"=+{ESF}!C36", f"=+{ESF}!F36")
    fila(11, "PARTICIPACION DE GASTOS TOTALES EN LAS VENTAS",
         f"=IFERROR({Ga('gtot')}/{Ga('ing')},0)", f"=IFERROR({Gp('gtot')}/{Gp('ing')},0)", pct)
    fila(12, "COSTO DE LA NOMINA EN LAS VENTAS",
         f"=IFERROR({Ga('nomina')}/{Ga('ing')},0)", f"=IFERROR({Gp('nomina')}/{Gp('ing')},0)", pct)
    # ====================== LIQUIDEZ ======================
    seccion(13, "INDICADORES DE LIQUIDEZ")
    fila(14, "CAPITAL DE TRABAJO", f"=+{ESF}!C44-{ESF}!N42", f"=+{ESF}!F44-{ESF}!Q42")
    fila(15, "RAZON CORRIENTE", f"=IFERROR({ESF}!C44/{ESF}!N42,0)",
         f"=IFERROR({ESF}!F44/{ESF}!Q42,0)", ratio)
    # ====================== ENDEUDAMIENTO ======================
    seccion(17, "INDICADORES DE ENDEUDAMIENTO")
    fila(18, "ENDEUDAMIENTO", f"=IFERROR({ESF}!N58/{ESF}!C75,0)",
         f"=IFERROR({ESF}!Q58/{ESF}!F75,0)", pct)
    fila(19, "ENDEUDAMIENTO A CORTO PLAZO", f"=IFERROR({ESF}!N42/{ESF}!N58,0)",
         f"=IFERROR({ESF}!Q42/{ESF}!Q58,0)", pct)
    # ====================== ACTIVIDAD ======================
    seccion(21, "INDICADORES DE ACTIVIDAD")
    fila(22, "PROMEDIO DE  C X C", f"=+{ESF}!C28+{ESF}!C32", f"=+{ESF}!F28+{ESF}!F32")
    fila(23, "ROTACION  C X C", f"=IFERROR({Ga('ing')}/B22,0)", f"=IFERROR({Gp('ing')}/C22,0)", ratio)
    fila(24, "ROTACIÓN DE CARTERA EN DIAS",
         f"=IFERROR((365/B23)/12*{mm},0)", f"=IFERROR((365/C23)/12*{mm},0)", dias, resalta=True)
    fila(26, "PROMEDIO DE C X P", f"=+{ESF}!N16", f"=+{ESF}!Q16")
    fila(27, "ROTACIÓN C X P", f"=IFERROR({Ga('ing')}/B26,0)", f"=IFERROR({Gp('ing')}/C26,0)", ratio)
    fila(28, "ROTACIÓN DE PROVEEDORES EN DIAS",
         f"=IFERROR((365/B27)/12*{mm},0)", f"=IFERROR((365/C27)/12*{mm},0)", dias, resalta=True)
    # ====================== RENTABILIDAD ======================
    seccion(30, "INDICADORES DE RENTABILIDAD AÑO")
    fila(31, "MARGEN BRUTO", f"=IFERROR({Ga('bruta')}/{Ga('ing')},0)",
         f"=IFERROR({Gp('bruta')}/{Gp('ing')},0)", pct)
    fila(32, "MARGEN OPERACIONAL", f"=IFERROR({Ga('op')}/{Ga('ing')},0)",
         f"=IFERROR({Gp('op')}/{Gp('ing')},0)", pct)
    fila(33, "MARGEN NETO", f"=IFERROR({Ga('neta')}/{Ga('ing')},0)",
         f"=IFERROR({Gp('neta')}/{Gp('ing')},0)", pct)
    fila(34, "RENDIMIENTO DEL PATRIMONIO", f"=IFERROR({Ga('neta')}/{ESF}!N73,0)",
         f"=IFERROR({Gp('neta')}/{ESF}!Q73,0)", pct)
    # ============== DETERIOROS PATRIMONIALES ==============
    r = 35
    ws.cell(r, 1, "INDICADORES DE DETERIOROS PATRIMONIALES Y RIESGOS DE INSOLVENCIA").font = bld
    ws.cell(r, 2, per_act).font = bld; ws.cell(r, 3, per_ant).font = bld
    ws.cell(r, 4, "ANALISIS").font = bld; ws.cell(r, 5, "RESULTADO").font = bld
    for cc in range(1, 6):
        ws.cell(r, cc).fill = sec
    for cc in (2, 3, 4, 5):
        ws.cell(r, cc).alignment = cen

    def deterioro(r0, titulo, sub26, sub25, v26, v25, analisis, resultado_f, fmt=money):
        ws.merge_cells(start_row=r0, start_column=1, end_row=r0 + 1, end_column=1)
        ws.cell(r0, 1, titulo).alignment = wrap
        ws.cell(r0, 2, sub26).alignment = cen; ws.cell(r0, 3, sub25).alignment = cen
        ws.cell(r0, 2).fill = info; ws.cell(r0, 3).fill = info
        a = ws.cell(r0 + 1, 2, v26); b = ws.cell(r0 + 1, 3, v25)
        for cc in (a, b):
            cc.number_format = fmt; cc.alignment = rgt
        ws.merge_cells(start_row=r0, start_column=4, end_row=r0 + 1, end_column=4)
        ws.cell(r0, 4, analisis).alignment = wrap
        ws.merge_cells(start_row=r0, start_column=5, end_row=r0 + 1, end_column=5)
        rc = ws.cell(r0, 5, resultado_f); rc.alignment = wrap
        for dr in (r0, r0 + 1):
            for cc in range(1, 6):
                ws.cell(dr, cc).border = cb
    deterioro(36, "POSICION PATRIMONIAL NEGATIVA", f"PATRIMONIO {per_act}",
              f"PATRIMONIO {per_ant}", f"=+{ESF}!N73", f"=+{ESF}!Q73",
              "Hay detrimento patrimonial si el patrimonio es inferior a 0",
              '=IF(B37<0,"Existe detrimento patrimonial","No existe detrimento patrimonial")')
    deterioro(38, "PERDIDAS CONSECUTIVAS (DOS PERIODOS)", f"PERDIDA {per_act}",
              f"PERDIDA {per_ant}", f"=IF({Ga('neta')}<0,{Ga('neta')},0)",
              f"=IF({Gp('neta')}<0,{Gp('neta')},0)",
              "Hay detrimento si el resultado es negativo en ambos periodos",
              '=IF(AND(B39<0,C39<0),"Existe detrimento patrimonial","No existe detrimento patrimonial")')
    deterioro(40, "RIESGO DE INSOLVENCIA SEGÚN CAPITAL DE TRABAJO",
              f"INDICADOR {per_act}", f"INDICADOR {per_ant}",
              f"=IFERROR(({ESF}!C28+{ESF}!C36-{ESF}!N16)/{ESF}!N42,0)",
              f"=IFERROR(({ESF}!F28+{ESF}!F36-{ESF}!Q16)/{ESF}!Q42,0)",
              "Hay riesgo de insolvencia si el indicador es menor que 0.5",
              '=IF(B41<0.5,"Existe riesgo de insolvencia","No existe riesgo de insolvencia")', ratio)
    deterioro(42, "RIESGO DE INSOLVENCIA SEGÚN RESULTADO DEL EJERCICIO",
              "UAII / ACTIVO", "PASIVO / ACTIVO",
              f"=IFERROR(({Ga('op')})/{ESF}!C75,0)", f"=IFERROR({ESF}!N58/{ESF}!C75,0)",
              "Hay riesgo si el primer factor es menor que el segundo",
              '=IF(B43<C43,"Existe riesgo de insolvencia","No existe riesgo de insolvencia")', ratio)
    # anchos y layout
    for c, w in {"A": 46, "B": 14, "C": 14, "D": 30, "E": 26, "F": 2,
                 "G": 22, "H": 12, "I": 12}.items():
        ws.column_dimensions[c].width = w
    from openpyxl.worksheet.properties import PageSetupProperties
    ws.page_setup.orientation = "landscape"; ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.freeze_panes = "A5"


# estructura del ESF (nivel, código, etiqueta) — plan de cuentas de Grupo de Lolita
ESF_ACTIVO = [
    (1, "11", "EFECTIVO Y EQUIVALENTES AL EFECTIVO"),
    (2, "1105", "Caja"), (2, "1110", "Bancos"), (2, "1120", "Cuentas de ahorro"),
    (2, "1130", "Equivalentes al efectivo"),
    (1, "13", "CUENTAS POR COBRAR"),
    (2, "1305", "Clientes"), (2, "1325", "CxC socios y accionistas"),
    (2, "1330", "Anticipos y avances"), (2, "1355", "Anticipo de impuestos"),
    (2, "1365", "Préstamos a empleados"), (2, "1380", "Deudores varios"),
    (1, "14", "INVENTARIOS"),
    (2, "1435", "Mercancías no fabricadas"), (2, "1436", "Otros inventarios"),
    (1, "15", "PROPIEDAD, PLANTA Y EQUIPO"),
    (2, "1510", "Mejoras a propiedades ajenas"), (2, "1516", "Construcciones y edificaciones"),
    (2, "1520", "Maquinaria y equipo"), (2, "1524", "Equipo de oficina"),
    (2, "1528", "Equipo de procesamiento de datos"), (2, "1592", "Depreciación acumulada"),
    (1, "16", "INTANGIBLES"),
    (1, "17", "OTROS ACTIVOS"),
    (1, "18", "OTROS ACTIVOS"),
    (1, "19", "ACTIVOS POR IMPUESTOS"),
    (2, "1955", "Anticipo de impuestos y saldos a favor"),
]
ESF_PASIVO = [
    (1, "21", "OBLIGACIONES FINANCIERAS"),
    (2, "2105", "Obligaciones financieras"), (2, "2120", "Compañías de financiamiento"),
    (2, "2195", "Otras obligaciones"),
    (1, "22", "PROVEEDORES"), (2, "2205", "Nacionales"),
    (1, "23", "CUENTAS POR PAGAR"),
    (2, "2335", "Costos y gastos por pagar"), (2, "2365", "Retención en la fuente"),
    (2, "2367", "Retenciones de IVA"), (2, "2368", "Retención de ICA"),
    (2, "2369", "Autorretención"), (2, "2370", "Retenciones y aportes de nómina"),
    (2, "2380", "Acreedores varios"),
    (1, "24", "PASIVO POR IMPUESTOS"),
    (2, "2402", "Impuesto diferido"), (2, "2404", "Impuesto de renta"),
    (2, "2406", "Acreedores oficiales"), (2, "2408", "Impuesto sobre las ventas"),
    (2, "2412", "Impuesto de industria y comercio"),
    (1, "25", "BENEFICIOS A EMPLEADOS"),
    (2, "2505", "Salarios por pagar"), (2, "2510", "Cesantías"),
    (2, "2515", "Intereses a las cesantías"), (2, "2520", "Prima de servicios"),
    (2, "2525", "Vacaciones"), (2, "2530", "Provisiones de nómina"),
    (2, "2550", "Retención y aportes de nómina"),
    (1, "26", "PASIVOS ESTIMADOS Y PROVISIONES"),
    (1, "28", "OTROS PASIVOS"), (2, "2805", "Anticipos y avances recibidos"),
]
ESF_PATRIM = [
    (2, "3105", "Capital suscrito y pagado"), (2, "3115", "Aportes sociales"),
    (2, "3305", "Reservas"), (2, "37", "Resultados de ejercicios anteriores"),
]


ESF_ACT = [
    (10, 0, "Activos Corrientes", ("h",)),
    (11, 1, "Efectivo y Equivalentes de Efectivo", ("f", "=SUM(C12:C15)", "=SUM(F12:F15)")),
    (12, 2, "Caja", ("v", ["1105"], 1)),
    (13, 2, "Bancos", ("v", ["1110"], 1)),
    (14, 2, "Cuentas de ahorros", ("v", ["1120"], 1)),
    (15, 2, "Inversiones a la vista", ("v", ["1130"], 1)),
    (19, 1, "Instrumentos Financieros", ("f", "=+C20", "=+F20")),
    (20, 2, "Acciones", ("v", [], 1)),
    (23, 1, "Activos por Impuesto", ("f", "=+C24", "=+F24")),
    (24, 2, "Anticipo de Impuestos", ("v", ["1955"], 1)),
    (27, 1, "Cuentas Por Cobrar", ("f", "=SUM(C28:C33)", "=SUM(F28:F33)")),
    (28, 2, "Clientes", ("v", ["1305"], 1)),
    (29, 2, "Accionistas", ("v", [], 1)),
    (30, 2, "Anticipos y avances", ("v", ["1330", "1325"], 1)),
    (31, 2, "A empleados", ("v", ["1365"], 1)),
    (32, 2, "Deudores varios", ("v", ["1380"], 1)),
    (36, 1, "Inventarios", ("f", "=SUM(C37:C41)", "=SUM(F37:F41)")),
    (37, 2, "Materias primas", ("v", [], 1)),
    (38, 2, "Productos en proceso", ("v", [], 1)),
    (39, 2, "Mercancia no fabricada por la empresa", ("v", ["1435"], 1)),
    (40, 2, "Otros Inventarios", ("v", ["1436"], 1)),
    (44, 0, "Total Activos Corrientes", ("f", "=+C36+C27+C11+C23+C19", "=+F36+F27+F11+F23+F19")),
    (46, 0, "Activos No Corrientes", ("h",)),
    (48, 1, "Inversiones", ("f", "=+C49", "=+F49")),
    (49, 2, "Fideicomisos", ("v", [], 1)),
    (52, 1, "Propiedad Planta y Equipo", ("f", "=SUM(C53:C59)", "=SUM(F53:F59)")),
    (53, 2, "Mejoras en propiedad ajena", ("v", ["1510"], 1)),
    (54, 2, "Construcciones y edificaciones", ("v", ["1516"], 1)),
    (55, 2, "Maquinaria y equipo", ("v", ["1520"], 1)),
    (56, 2, "Equipo de oficina", ("v", ["1524"], 1)),
    (57, 2, "Equipo de computo", ("v", ["1528"], 1)),
    (58, 2, "Flota y equipo de transporte", ("v", [], 1)),
    (59, 2, "Depreciacion acumulada", ("v", ["1592"], 1)),
    (61, 1, "Intangibles", ("f", "=+C62", "=+F62")),
    (62, 2, "Licencias", ("v", ["16"], 1)),
    (64, 1, "Otros activos", ("f", "=+C65", "=+F65")),
    (65, 2, "Gastos pagados por anticipado", ("v", ["17"], 1)),
    (67, 1, "Activo por impuesto", ("f", "=+C68", "=+F68")),
    (68, 2, "Impuesto diferido", ("v", [], 1)),
    (71, 0, "Total Activos No Corrientes", ("f", "=+C52+C61+C64+C48+C67", "=+F52+F61+F64+F48+F67")),
    (75, 0, "Total Activos", ("f", "=+C71+C44", "=+F71+F44")),
]
ESF_PAS = [
    (10, 0, "Pasivos Corrientes", ("h",)),
    (11, 1, "Obligaciones Financieras", ("f", "=SUM(N12:N13)", "=SUM(Q12:Q13)")),
    (12, 2, "Sobregiro", ("v", [], -1)),
    (13, 2, "Tarjetas de Crédito", ("v", [], -1)),
    (16, 1, "Cuentas Por Pagar", ("f", "=SUM(N17:N18)", "=SUM(Q17:Q18)")),
    (17, 2, "Proveedores", ("v", ["2205"], -1)),
    (18, 2, "Acreedores Varios", ("v", ["2380", "2370", "2335"], -1)),
    (22, 1, "Pasivo Por Impuestos", ("f", "=SUM(N23:N26)", "=SUM(Q23:Q26)")),
    (23, 2, "Retención en la fuente", ("v", ["240605"], -1)),
    (24, 2, "Impuesto sobre las ventas", ("v", ["240610", "2408"], -1)),
    (25, 2, "Provision Industria y comercio", ("v", ["2615"], -1)),
    (26, 2, "Provision Impuesto de renta", ("v", ["2404"], -1)),
    (28, 1, "Beneficios a Empleados", ("f", "=SUM(N29:N34)", "=SUM(Q29:Q34)")),
    (29, 2, "Salarios por pagar", ("v", ["2505"], -1)),
    (30, 2, "Cesantias", ("v", ["253005", "2510"], -1)),
    (31, 2, "Intereses a Cesantias", ("v", ["253010", "2515"], -1)),
    (32, 2, "Prima de servicios", ("v", ["253020", "2520"], -1)),
    (33, 2, "Vacaciones", ("v", ["2525", "253015"], -1)),
    (34, 2, "Aportes sobre la nomina", ("v", ["2550"], -1)),
    (36, 1, "Otros Pasivos", ("f", "=SUM(N37:N39)", "=SUM(Q37:Q39)")),
    (37, 2, "Anticipos y avances", ("v", ["2805"], -1)),
    (38, 2, "Ingresos para terceros", ("v", [], -1)),
    (39, 2, "Embargos", ("v", [], -1)),
    (42, 0, "Total Pasivos Corrientes", ("f", "=+N28+N22+N16+N36+N11", "=+Q28+Q22+Q16+Q36+Q11")),
    (44, 0, "Pasivos No Corrientes", ("h",)),
    (45, 1, "Obligaciones Financieras", ("f", "=SUM(N46:N48)", "=SUM(Q46:Q48)")),
    (46, 2, "Bancos Nacionales", ("v", ["2105"], -1)),
    (47, 2, "Compañias De Financiamiento", ("v", ["2120"], -1)),
    (48, 2, "Otras obligaciones", ("v", ["2195"], -1)),
    (50, 1, "Otros Pasivos", ("f", "=SUM(N51:N51)", "=SUM(Q51:Q51)")),
    (51, 2, "Otras obligaciones", ("v", [], -1)),
    (53, 1, "Pasivo Por Impuestos", ("f", "=+N54+N55", "=+Q54+Q55")),
    (54, 2, "Impuesto diferido", ("v", ["2402"], -1)),
    (55, 2, "", ("v", [], -1)),
    (56, 0, "Total Pasivo No Corriente", ("f", "=+N45+N53+N50", "=+Q45+Q53+Q50")),
    (58, 0, "Total Pasivos", ("f", "=+N56+N42", "=+Q56+Q42")),
    (60, 0, "Patrimonio", ("h",)),
    (61, 1, "Capital Social", ("f", "=+N62", "=+Q62")),
    (62, 2, "Capital suscrito y pagado", ("v", ["3105"], -1)),
    (64, 1, "Reservas", ("f", "=+N65", "=+Q65")),
    (65, 2, "Reserva legal", ("v", ["3305"], -1)),
    (67, 1, "Resultado del Ejercicio", ("f", "=+N68", "=+Q68")),
    (68, 2, "Utilidad del ejercicio", ("res",)),
    (70, 1, "Resultados Acumulados", ("f", "=+N71+N72", "=+Q71+Q72")),
    (71, 2, "Utilidades acumuladas", ("v", ["3705", "3710"], -1)),
    (72, 2, "Impactos por transicion", ("v", ["3715"], -1)),
    (73, 0, "Total Patrimonio", ("f", "=+N61+N64+N67+N70", "=+Q61+Q64+Q67+Q70")),
    (75, 0, "Total Pasivos y Patrimonio", ("f", "=+N73+N58", "=+Q73+Q58")),
]


def _esf_sheet(wb, mes_nom, anio, sub, nom_bal, resultado, esc=0.001,
               sub_ant=None, resultado_ant=None, anio_comp=None, mes=None):
    """ESF de DOS COLUMNAS (Activos | Pasivos+Patrimonio) con el DISEÑO del
    informe anterior (banda de título, encabezado sombreado, celdas con borde,
    subtotales con línea, sin cuadrícula), calculado del balance, con
    A.V/VARIACIÓN/A.H como fórmulas (IFERROR). Cuadra: Activos = Pasivo+Patrimonio."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter as GL
    if "4.ESF=BALANCE" in wb.sheetnames:
        del wb["4.ESF=BALANCE"]
    ws = wb.create_sheet("4.ESF=BALANCE")
    ws.sheet_view.showGridLines = False
    band = PatternFill("solid", fgColor="DDEBF7")     # banda de título / encabezado
    hdrf = PatternFill("solid", fgColor="D9E1F2")
    bld = Font(bold=True); rgt = Alignment(horizontal="right"); cen = Alignment(horizontal="center", vertical="center")
    money = '#,##0'; pct = '0.0%'
    thin = Side(style="thin", color="BFBFBF"); dark = Side(style="thin", color="404040")
    box = Border(top=dark, bottom=dark, left=dark, right=dark)
    celda_b = Border(top=thin, bottom=thin, left=thin, right=thin)
    sub_b = Border(top=dark, bottom=dark)
    mm = int(mes) if mes else 0
    ac = anio_comp or (anio - 1); res_ant = resultado_ant or 0.0
    per_act = f"{anio}-{mm:02d}"; per_ant = f"{ac}-{mm:02d}"
    # ---- banda de título (A1:U6, combinada y centrada) ----
    titulos = ["GRUPO DE LOLITA SAS", "NIT: 900.307.969-5",
               "ESTADO DE SITUACIÓN FINANCIERA",
               f"A {mes_nom.upper()} DE {anio} Y {ac}",
               "(Cifras expresadas en Miles de pesos colombianos)"]
    for i, t in enumerate(titulos):
        rr = i + 2
        ws.merge_cells(start_row=rr, start_column=1, end_row=rr, end_column=21)
        c = ws.cell(rr, 1, t); c.alignment = cen
        c.font = Font(bold=True, size=12 if i else 13, color="1F4E78" if i == 0 else "000000")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=21)
    for rr in range(1, 8):
        for cc in range(1, 22):
            ws.cell(rr, cc).fill = band
    # ---- encabezados fila 8 ----
    for lbl, cols in (("ACTIVOS", (1, 3, 4, 6, 7, 9, 10)), ("PASIVOS", (12, 14, 15, 17, 18, 20, 21))):
        txts = [lbl, per_act, "A.V", per_ant, "A.V", "VARIACION", "A.H"]
        for t, cc in zip(txts, cols):
            c = ws.cell(8, cc, t); c.fill = hdrf; c.font = bld
            c.alignment = (Alignment(horizontal="left") if cc in (1, 12) else cen)
            c.border = Border(top=dark, bottom=dark)

    def valor(codes, sign, subd):
        return sign * sum(subd.get(c, 0.0) for c in codes)

    # --- cuadre exacto: la utilidad del ejercicio absorbe el redondeo a miles ---
    # (cada línea se redondea por separado; para que Activos = Pasivo+Patrimonio
    #  la fila 'res' se fija = suma de activos redondeados − resto de pasivo/patrim.)
    def _leafsum(lineas, subd):
        s = 0.0
        for _row, _lvl, _label, spec in lineas:
            if spec and spec[0] == "v":
                s += round(valor(spec[1], spec[2], subd) * esc, 0)
        return s
    _RA = _leafsum(ESF_ACT, sub); _RPP = _leafsum(ESF_PAS, sub)
    res_disp = _RA - _RPP                                    # utilidad ajustada (año en curso)
    _RA25 = _leafsum(ESF_ACT, sub_ant or {}); _RPP25 = _leafsum(ESF_PAS, sub_ant or {})
    res25_disp = _RA25 - _RPP25                              # utilidad ajustada (comparativo)

    def pintar(lineas, cols):
        LBL, V26, AV26, V25, AV25, VAR, AH = cols
        Lc = GL(V26); Fc = GL(V25); totref = f"${Lc}$75"; totref25 = f"${Fc}$75"
        numcols = (V26, AV26, V25, AV25, VAR, AH)
        for row, lvl, label, spec in lineas:
            cl = ws.cell(row, LBL, label)
            if spec[0] == "h":
                cl.font = bld; cl.fill = hdrf
                for cc in cols:
                    ws.cell(row, cc).fill = hdrf
                continue
            if lvl == 0:
                cl.font = bld
            elif lvl == 1:
                cl.font = Font(bold=True, color="1F4E78")
            else:
                cl.value = "   " + label
            if spec[0] == "v":
                _c, codes, sign = spec
                c26 = ws.cell(row, V26, round(valor(codes, sign, sub) * esc, 0))
                c25 = ws.cell(row, V25, round(valor(codes, sign, sub_ant or {}) * esc, 0))
            elif spec[0] == "res":
                c26 = ws.cell(row, V26, res_disp)
                c25 = ws.cell(row, V25, res25_disp)
            else:  # 'f'
                c26 = ws.cell(row, V26, spec[1]); c25 = ws.cell(row, V25, spec[2])
            bold_num = lvl in (0, 1)   # totales de grupo (nivel 1) también en negrilla
            for cc in (c26, c25):
                cc.number_format = money; cc.alignment = rgt
            if bold_num:
                c26.font = bld; c25.font = bld
            # A.V / VARIACIÓN / A.H como fórmulas
            av1 = ws.cell(row, AV26, f"=IFERROR({Lc}{row}/{totref},0)")
            av2 = ws.cell(row, AV25, f"=IFERROR({Fc}{row}/{totref25},0)")
            vr = ws.cell(row, VAR, f"=+{Lc}{row}-{Fc}{row}")
            ah = ws.cell(row, AH, f"=IFERROR(({Lc}{row}-{Fc}{row})/{Fc}{row},0)")
            for cc in (av1, av2, ah):
                cc.number_format = pct; cc.alignment = rgt
            vr.number_format = money; vr.alignment = rgt
            # bordes de las celdas numéricas
            bd = sub_b if lvl == 0 else celda_b
            for cx in numcols:
                cell = ws.cell(row, cx)
                cell.border = bd
                if bold_num:
                    cell.font = bld
    pintar(ESF_ACT, (1, 3, 4, 6, 7, 9, 10))
    pintar(ESF_PAS, (12, 14, 15, 17, 18, 20, 21))
    # control (diferencia = 0)
    ws.cell(77, 12, "DIFERENCIA (control = 0)").font = bld
    d = ws.cell(77, 14, "=+C75-N75"); d.number_format = money; d.alignment = rgt; d.font = bld
    # anchos de columna (según plantilla)
    widths = {"A": 31, "B": 3, "C": 15, "D": 9, "E": 3, "F": 15, "G": 9, "H": 3,
              "I": 13, "J": 12, "K": 2, "L": 42, "M": 2, "N": 16, "O": 12, "P": 3,
              "Q": 15, "R": 9, "S": 3, "T": 15, "U": 14}
    for c, w in widths.items():
        ws.column_dimensions[c].width = w
    ws.freeze_panes = "A9"
    from openpyxl.worksheet.properties import PageSetupProperties
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_area = "A1:U77"

def leer_cartera(fuente):
    """Lee un informe de cartera del paquete administrativo (Análisis Resumido de
    Cliente por NIT, o de Acreedor por Código). Devuelve {nit: [nombre, total]}
    donde nit son los dígitos tal como los trae el informe (sin verificación)."""
    import openpyxl
    data = fuente if isinstance(fuente, (bytes, bytearray)) else (
        fuente.read() if hasattr(fuente, "read") else open(fuente, "rb").read())
    ws = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    hi = 0
    for i, r in enumerate(rows[:8]):
        up = [str(c or "").strip().lower() for c in r]
        if any("total" in x for x in up) and any(
                any(w in x for w in ("cliente", "código", "codigo", "nit", "acreedor"))
                for x in up):
            hi = i; break
    up = [str(c or "").strip().lower() for c in rows[hi]]
    def col(*frag):
        for f in frag:
            for j, h in enumerate(up):
                if f in h:
                    return j
        return None
    cId = col("cliente", "código acreedor", "codigo acreedor", "código", "codigo", "nit")
    cNom = col("nombre")
    cTot = col("total")
    out = {}
    for r in rows[hi + 1:]:
        idv = re.sub(r"[^0-9]", "", str(r[cId] or "")) if cId is not None else ""
        if not idv:
            continue
        try:
            t = float(r[cTot] or 0) if cTot is not None else 0.0
        except (TypeError, ValueError):
            t = 0.0
        nom = str(r[cNom]) if cNom is not None and r[cNom] else ""
        a = out.setdefault(idv, [nom, 0.0]); a[1] += t
        if nom and not a[0]:
            a[0] = nom
    return out


def _nitkey(nit):
    d = re.sub(r"[^0-9]", "", str(nit or ""))
    return d[:-1] if len(d) >= 2 else d       # quita el dígito de verificación


def _observaciones_sheet(wb, rows, sub, nom_bal, mes_nom, anio, esc=0.001,
                         cartera=None, cxp=None, mes=None, inv_cc=None, iva_bimestres=None):
    """OBSERVACIONES con el DISEÑO del informe anterior:
      · Caja de IVA (bimestres digitables), RETENCION POR PAGAR, IVA PERIODO
        (mes/acum) y PRESION DE IVA — automáticos del balance.
      · Detalle por cuenta 1105 Caja / 1110-1120-1130 Bancos: SALDO del balance
        por subcuenta, BASE y OBSERVACION editables, DIFERENCIA por fórmula.
      · Comparativo de cartera CLIENTES (1305+2805) y PROVEEDORES (2205+133005)
        contable vs módulo administrativo, cruzado por NIT."""
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    if "OBSERVACIONES" in wb.sheetnames:
        del wb["OBSERVACIONES"]
    ws = wb.create_sheet("OBSERVACIONES")
    ws.sheet_view.showGridLines = False
    mm = int(mes) if mes else 0
    band = PatternFill("solid", fgColor="DDEBF7"); ivaf = PatternFill("solid", fgColor="FDF3D0")
    hdrf = PatternFill("solid", fgColor="D9E1F2"); azul = PatternFill("solid", fgColor="1F4E78")
    wht = Font(color="FFFFFF", bold=True); edit = Font(color="0563C1")
    bld = Font(bold=True); rgt = Alignment(horizontal="right"); cen = Alignment(horizontal="center", vertical="center")
    thin = Side(style="thin", color="BFBFBF"); dark = Side(style="thin", color="404040")
    cb = Border(top=thin, bottom=thin, left=thin, right=thin)
    money = '#,##0'; pct = '0.0%'

    def ns(p): return sub.get(p, 0.0)

    def contable(prefixes):
        agg = {}
        for rr_ in rows:
            c = _dig(rr_["cuenta"])
            if rr_["nit"] and any(c.startswith(p) for p in prefixes):
                k = _nitkey(rr_["nit"])
                a = agg.setdefault(k, [rr_["nombre_nit"], 0.0]); a[1] += rr_["nuevo_saldo"]
        return agg

    def subcuentas(parent, exclude=None, nivel=None):
        """Subcuentas bajo `parent` (fila subtotal: sin cc y sin nit), con nombre y
        saldo (miles). `nivel`=N → agrupa a códigos de N dígitos; None → hojas
        (nivel de cuenta completo). `exclude`: prefijos a omitir."""
        tot = {}
        for rr_ in rows:
            c = _dig(rr_["cuenta"])
            if not (c and c.startswith(parent) and not rr_["cc"] and not rr_["nit"]):
                continue
            if exclude and any(c.startswith(x) for x in exclude):
                continue
            tot[c] = [rr_["nombre"], rr_["nuevo_saldo"]]
        if nivel is not None:
            out = [(c, tot[c][0], tot[c][1] * esc) for c in tot
                   if len(c) == nivel and abs(tot[c][1] * esc) >= 1]
            return sorted(out)
        codes = set(tot)
        padres = {c[:L] for c in codes for L in range(len(parent) + 1, len(c)) if c[:L] in codes}
        hojas = [(c, tot[c][0], tot[c][1] * esc) for c in codes
                 if c not in padres and len(c) > len(parent) and abs(tot[c][1] * esc) >= 1]
        return sorted(hojas)

    def terceros(parent, exclude=None):
        """Saldo por TERCERO (NIT) bajo `parent` (miles), mayor a menor."""
        agg = {}
        for rr_ in rows:
            c = _dig(rr_["cuenta"])
            if c.startswith(parent) and rr_["nit"]:
                if exclude and any(c.startswith(x) for x in exclude):
                    continue
                a = agg.setdefault(rr_["nit"], [rr_["nombre_nit"], 0.0]); a[1] += rr_["nuevo_saldo"]
        out = [(k, a[0], a[1] * esc) for k, a in agg.items() if abs(a[1] * esc) >= 1]
        return sorted(out, key=lambda x: -abs(x[2]))

    def por_cc(parent):
        """Saldo por CENTRO DE COSTO bajo `parent` (miles)."""
        agg = {}
        for rr_ in rows:
            c = _dig(rr_["cuenta"])
            if c.startswith(parent) and rr_["cc"]:
                a = agg.setdefault(rr_["cc"], [rr_["nombre_cc"] or rr_["cc"], 0.0])
                a[1] += rr_["nuevo_saldo"]
        out = [(k, a[0], a[1] * esc) for k, a in agg.items() if abs(a[1] * esc) >= 1]
        return sorted(out, key=lambda x: -abs(x[2]))

    # ===================== título =====================
    for i, t in enumerate(["GRUPO DE LOLITA SAS", "NIT: 900.307.969-5",
                           f"A {mes_nom.upper()} DE {anio}", "CIFRAS EN MILES DE PESOS"]):
        ws.merge_cells(start_row=i + 1, start_column=1, end_row=i + 1, end_column=6)
        c = ws.cell(i + 1, 1, t); c.alignment = cen
        c.font = Font(bold=True, size=13 if i == 0 else 11, color="1F4E78" if i == 0 else "000000")
        for cc in range(1, 7):
            ws.cell(i + 1, cc).fill = band
    # ===================== caja de IVA =====================
    ws.cell(7, 3, "MES").font = bld; ws.cell(7, 3).alignment = cen
    ws.cell(7, 4, "ACUMULADO").font = bld; ws.cell(7, 4).alignment = cen
    bim = iva_bimestres or []
    for i in range(1, 6):
        ws.cell(5 + i, 5, f"IVA BIMESTRE {i}").font = bld
        v = bim[i - 1] if i - 1 < len(bim) else None
        b = ws.cell(5 + i, 6, round(v * esc, 0) if v else None)
        b.number_format = money; b.alignment = rgt
        b.font = edit; b.fill = ivaf              # reconstruidos del antiguo / editables
    reten = -ns("240605")                          # retención por pagar = 2406 (240605)
    iva_acum = -ns("2408")
    iva_mes = sum((rr_["creditos"] - rr_["debitos"]) for rr_ in rows
                  if _dig(rr_["cuenta"]).startswith("2408") and (rr_["cc"] or rr_["nit"]))
    ventas_acum = -ns("41")
    ventas_mes = sum((rr_["creditos"] - rr_["debitos"]) for rr_ in rows
                     if _dig(rr_["cuenta"]).startswith("41") and (rr_["cc"] or rr_["nit"]))
    ws.cell(9, 2, "RETENCION POR PAGAR").font = bld
    c = ws.cell(9, 3, round(reten * esc, 0)); c.number_format = money; c.alignment = rgt
    ws.cell(11, 2, "IVA PERIODO").font = bld
    for col, v in ((3, iva_mes), (4, iva_acum + sum(0 for _ in range(0)))):
        cc = ws.cell(11, col, round(v * esc, 0)); cc.number_format = money; cc.alignment = rgt
    # acumulado de IVA período = IVA por pagar acum + lo ya pagado en bimestres
    ws.cell(11, 4).value = f"=+{round(iva_acum*esc,0)}+SUM(F6:F10)"
    ws.cell(12, 2, "PRESION DE IVA").font = bld
    pm = ws.cell(12, 3, f"=IFERROR(C11/{round(ventas_mes*esc,0) or 1},0)")
    pa = ws.cell(12, 4, f"=IFERROR(D11/{round(ventas_acum*esc,0) or 1},0)")
    for cc in (pm, pa):
        cc.number_format = pct; cc.alignment = rgt
    r = [15]

    # ===================== detalle por cuenta =====================
    def _det_lineas(code_hdr, titulo, lineas, total_val, con_base=False, obs_default="",
                    cols_extra=None):
        """Escribe una sección: encabezado (código+título+total), tabla de líneas
        [(nombre, saldo_miles)] y control (Σ líneas − total)."""
        if abs(total_val) < 0.5 and not lineas:
            return
        i = r[0]
        ws.cell(i, 1, int(code_hdr) if str(code_hdr).isdigit() else code_hdr).font = bld
        ws.cell(i, 2, titulo).font = bld
        tc = ws.cell(i, 3, round(total_val, 0)); tc.number_format = money
        tc.alignment = rgt; tc.font = bld
        i += 1
        cols = cols_extra or (["DETALLE", "SALDO", "BASE", "DIFERENCIA", "OBSERVACION"]
                              if con_base else ["DETALLE", "SALDO", "OBSERVACION"])
        for k, t in enumerate(cols):
            hc = ws.cell(i, 2 + k, t); hc.fill = hdrf; hc.font = bld; hc.border = cb
            hc.alignment = cen
        i += 1
        ini = i
        for nom, saldo in lineas:
            ws.cell(i, 2, str(nom).strip()[:34]).border = cb
            sc = ws.cell(i, 3, round(saldo, 0)); sc.number_format = money; sc.alignment = rgt; sc.border = cb
            if con_base:
                bc = ws.cell(i, 4, None); bc.number_format = money; bc.alignment = rgt
                bc.font = edit; bc.border = cb
                dc = ws.cell(i, 5, f"=C{i}-D{i}"); dc.number_format = money; dc.alignment = rgt; dc.border = cb
                ws.cell(i, 6, None).font = edit; ws.cell(i, 6).border = cb
            else:
                oc = ws.cell(i, 4, obs_default or None); oc.font = edit; oc.border = cb
            i += 1
        ws.cell(i, 2, "DIFERENCIA (control)").font = bld
        sc = ws.cell(i, 3, f"=SUM(C{ini}:C{i-1})-C{r[0]}" if i > ini else 0)
        sc.number_format = money; sc.alignment = rgt; sc.font = bld
        r[0] = i + 2

    def det_cuenta(code, titulo, modo="sub", con_base=False, obs_default="",
                   exclude=None, nivel=None):
        if modo == "nit":
            detalle = terceros(code, exclude)
        elif modo == "cc":
            detalle = por_cc(code)
        else:
            detalle = subcuentas(code, exclude, nivel=nivel)
        _det_lineas(code, titulo, [(nom, saldo) for _c, nom, saldo in detalle],
                    ns(code) * esc, con_base=con_base, obs_default=obs_default)

    def det_inventario_cc():
        """INVENTARIO FINAL por PUNTO DE VENTA (centro de costo), del año."""
        if not inv_cc:
            det_cuenta("14", "INVENTARIOS", modo="sub")
            return
        i = r[0]
        ws.cell(i, 1, 14).font = bld
        ws.cell(i, 2, "INVENTARIO FINAL POR PUNTO DE VENTA").font = bld
        tc = ws.cell(i, 3, round(sum(x[1] for x in inv_cc), 0)); tc.number_format = money
        tc.alignment = rgt; tc.font = bld
        i += 1
        for k, t in enumerate(["CENTRO DE COSTO", "INV. FINAL", "OBSERVACION"]):
            hc = ws.cell(i, 2 + k, t); hc.fill = hdrf; hc.font = bld; hc.border = cb; hc.alignment = cen
        i += 1; ini = i
        for cc_name, vf in inv_cc:
            ws.cell(i, 2, str(cc_name).strip()[:30]).border = cb
            x = ws.cell(i, 3, round(vf, 0)); x.number_format = money
            x.alignment = rgt; x.border = cb
            ws.cell(i, 4, "Inventario según información administrativa").font = edit
            ws.cell(i, 4).border = cb
            i += 1
        ws.cell(i, 2, "DIFERENCIA (control)").font = bld
        x = ws.cell(i, 3, f"=SUM(C{ini}:C{i-1})-C{r[0]}")
        x.number_format = money; x.alignment = rgt; x.font = bld
        r[0] = i + 2

    det_cuenta("1105", "CAJA", con_base=True)
    det_cuenta("1110", "BANCOS (moneda nacional)", obs_default="Conciliada con extracto")
    det_cuenta("1120", "BANCOS", obs_default="Conciliada con extracto")
    det_cuenta("1130", "FONDOS / FIDUCUENTA", obs_default="Conciliada con extracto")
    det_cuenta("1325", "CXC A SOCIOS Y ACCIONISTAS", modo="nit")
    # 1330: el DETALLE de saldos SÍ incluye el anticipo UTS (133010)
    det_cuenta("1330", "ANTICIPOS Y AVANCES (1330, incluye anticipo UTS)", modo="nit")
    det_cuenta("1365", "PRESTAMOS A EMPLEADOS", modo="nit")
    det_cuenta("1380", "OTRAS CUENTAS POR COBRAR", modo="nit",
               obs_default="Cxc entre compañías")
    det_inventario_cc()
    # ---- 15 PROPIEDAD PLANTA Y EQUIPO: activos por clase (sin depreciación) +
    #      depreciación acumulada global ----
    dep_codes = [c for c in sub if len(c) == 6 and c.startswith("15") and c.endswith("92")]
    dep_total = sum(ns(c) for c in dep_codes) * esc
    l15 = []
    for cod, nom, saldo in subcuentas("15", nivel=4):
        dclass = sum(ns(c) for c in dep_codes if c.startswith(cod)) * esc
        l15.append((nom, saldo - dclass))       # bruto = neto − depreciación
    if abs(dep_total) >= 1:
        l15.append(("DEPRECIACIÓN ACUMULADA (global)", dep_total))
    _det_lineas("15", "PROPIEDAD, PLANTA Y EQUIPO", l15, ns("15") * esc)
    det_cuenta("16", "INTANGIBLES", modo="sub")
    det_cuenta("1955", "ACTIVOS POR IMPUESTOS (1955)", modo="sub", nivel=6,
               obs_default="Retenciones que le practicaron / saldos a favor")
    det_cuenta("21", "OBLIGACIONES FINANCIERAS", modo="sub")

    # ===================== comparativo de cartera =====================
    def bloque(titulo, cont_map, anti_map, mod_map, cont_lbl, anti_lbl):
        i = r[0]
        for c in range(1, 7):
            ws.cell(i, c).fill = azul
        ws.cell(i, 1, titulo).font = wht
        r[0] += 1; i = r[0]
        for c, t in enumerate(["NIT", "TERCERO", "MÓDULO", cont_lbl, anti_lbl, "DIFERENCIA"]):
            cell = ws.cell(i, 1 + c, t); cell.fill = hdrf; cell.font = bld; cell.border = cb
            cell.alignment = cen
        r[0] += 1
        mod_map = mod_map or {}; anti_map = anti_map or {}
        keys = sorted(set(cont_map) | set(mod_map) | set(anti_map),
                      key=lambda k: -abs((cont_map.get(k) or ["", 0])[1] or (mod_map.get(k) or ["", 0])[1]))
        ini = r[0]
        for k in keys:
            cv = cont_map.get(k, [None, 0.0]); mv = mod_map.get(k); av = anti_map.get(k, [None, 0.0])
            # omitir terceros en ceros (contable, módulo y anticipos todos ~0)
            if (abs(cv[1] * esc) < 0.5 and abs((mv[1] if mv else 0) * esc) < 0.5
                    and abs(av[1] * esc) < 0.5):
                continue
            nombre = cv[0] or (mv[0] if mv else "") or av[0]
            i = r[0]
            ws.cell(i, 1, k).border = cb; ws.cell(i, 2, str(nombre)[:40]).border = cb
            cm = ws.cell(i, 3, None if mv is None else round(mv[1] * esc, 0))       # MÓDULO
            cm.number_format = money; cm.alignment = rgt; cm.font = edit; cm.border = cb
            cc = ws.cell(i, 4, round(cv[1] * esc, 0))                                # CONTAB
            cc.number_format = money; cc.alignment = rgt; cc.border = cb
            ca = ws.cell(i, 5, round(av[1] * esc, 0))                                # ANTICIPOS
            ca.number_format = money; ca.alignment = rgt; ca.border = cb
            cd = ws.cell(i, 6, f"=C{i}-(D{i}+E{i})")                                 # DIFERENCIA
            cd.number_format = money; cd.alignment = rgt; cd.border = cb
            r[0] += 1
        i = r[0]
        ws.cell(i, 2, "TOTAL").font = bld
        for cl, rng in ((3, "C"), (4, "D"), (5, "E"), (6, "F")):
            x = ws.cell(i, cl, f"=SUM({rng}{ini}:{rng}{i-1})")
            x.number_format = money; x.alignment = rgt; x.font = bld
        for c in range(1, 7):
            ws.cell(i, c).fill = hdrf
        r[0] += 2

    bloque("1305 CLIENTES  (módulo  vs  contable 1305 y anticipos 2805)",
           contable(["1305"]), contable(["2805"]), cartera, "1305 CONTAB", "2805 ANTICIPOS")
    # anticipos de proveedores = 133005 (se excluye 133010 «ANTICIPOS UTS»)
    bloque("2205 PROVEEDORES / ACREEDORES  (módulo  vs  contable 2205 y anticipos 133005)",
           contable(["2205"]), contable(["133005"]), cxp, "2205 CONTAB", "133005 ANTICIPOS")

    # ===================== detalle de cuentas de pasivo =====================
    det_cuenta("2380", "ACREEDORES VARIOS", modo="nit", obs_default="Saldos entre compañías")
    det_cuenta("2404", "IMPUESTO DE RENTA (2404)", modo="sub", nivel=4)
    # PASIVO POR IMPUESTOS (2406) a nivel de cuenta completo + IVA (2408) sumado
    l2406 = [(nom, saldo) for _c, nom, saldo in subcuentas("2406")]
    if abs(ns("2408") * esc) >= 1:
        l2406.append(("IMPUESTO SOBRE LAS VENTAS - IVA (2408)", ns("2408") * esc))
    _det_lineas("2406", "PASIVO POR IMPUESTOS (2406 + IVA 2408)", l2406,
                (ns("2406") + ns("2408")) * esc)
    det_cuenta("2412", "IMPUESTO DE INDUSTRIA Y COMERCIO (2412)", modo="sub", nivel=4)
    det_cuenta("2615", "PROVISIÓN INDUSTRIA Y COMERCIO (2615)", modo="sub", nivel=4)
    # 25 BENEFICIOS: saldos de 2510, 2515, 2525, 253005, 253010, 253015, 253020;
    # y 2550 + 2570 + 2580 sumados como «Retenciones y aportes de nómina»
    l25 = []
    _lbl25 = {"2510": "Cesantías (2510)", "2515": "Intereses sobre cesantías (2515)",
              "2525": "Vacaciones consolidadas (2525)", "253005": "Cesantías (2530)",
              "253010": "Intereses sobre cesantías (2530)", "253015": "Vacaciones (2530)",
              "253020": "Prima de servicios (2530)"}
    for cod in ("2510", "2515", "2525", "253005", "253010", "253015", "253020"):
        v = ns(cod) * esc
        if abs(v) >= 1:
            l25.append((_lbl25.get(cod, nom_bal.get(cod, cod)), v))
    ret_nom = (ns("2550") + ns("2570") + ns("2580")) * esc
    if abs(ret_nom) >= 1:
        l25.append(("Retenciones y aportes de nómina (2550+2570+2580)", ret_nom))
    _det_lineas("25", "BENEFICIOS A LOS TRABAJADORES", l25, ns("25") * esc)
    det_cuenta("26", "PASIVOS ESTIMADOS Y PROVISIONES", modo="sub")

    ws.cell(r[0] + 1, 1, "Los valores en azul (BASE, OBSERVACION, MÓDULO, bimestres de IVA) se "
                         "digitan; SALDO, RETENCIÓN, IVA y CONTABLE salen del balance; las "
                         "DIFERENCIAS son fórmulas.").font = Font(italic=True, color="808080")
    for c, w in {"A": 8, "B": 40, "C": 15, "D": 15, "E": 15, "F": 26}.items():
        ws.column_dimensions[c].width = w
    from openpyxl.worksheet.properties import PageSetupProperties
    ws.page_setup.orientation = "portrait"; ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.freeze_panes = "A5"


# ===========================================================================
# Memoria MES A MES del Estado de Resultados por CC (tabla eeff_eri_mensual)
# ===========================================================================
NOCC = "__NOCC__"     # marcador de movimiento sin centro de costo


def leafdata_actual(leaf_cc, leaf_nocc):
    """{(cuenta, cc): valor_mes} del mes en curso, para guardar y rearmar."""
    d = {}
    for (lc, cc), (mes, _a) in leaf_cc.items():
        if abs(mes) > 0:
            d[(lc, cc)] = mes
    for lc, (mes, _a) in leaf_nocc.items():
        if abs(mes) > 0:
            d[(lc, NOCC)] = d.get((lc, NOCC), 0.0) + mes
    return d


def guardar_eri_mensual(sb, empresa_id, periodo, leafdata):
    """Guarda el movimiento del mes (cuenta hoja × CC) del periodo."""
    try:
        sb.table("eeff_eri_mensual").delete().eq("empresa_id", empresa_id)\
            .eq("periodo", periodo).execute()
    except Exception:  # noqa: BLE001
        pass
    payload = [{"empresa_id": empresa_id, "periodo": periodo, "cc": cc,
                "cuenta": cta, "valor": float(v)}
               for (cta, cc), v in leafdata.items() if abs(v) > 0]
    for i in range(0, len(payload), 500):
        sb.table("eeff_eri_mensual").upsert(
            payload[i:i + 500], on_conflict="empresa_id,periodo,cc,cuenta").execute()
    return len(payload)


def cargar_eri_historia(sb, empresa_id, anio, hasta_periodo):
    """{periodo: {(cuenta,cc): valor_mes}} de los meses guardados del año
    ANTERIORES a `hasta_periodo`."""
    try:
        r = (sb.table("eeff_eri_mensual").select("periodo,cc,cuenta,valor")
             .eq("empresa_id", empresa_id).like("periodo", f"{anio}-%")
             .lt("periodo", hasta_periodo).execute())
    except Exception:  # noqa: BLE001
        return {}
    hist = {}
    for x in (r.data or []):
        hist.setdefault(x["periodo"], {})[(str(x["cuenta"]), str(x["cc"]))] = float(x["valor"])
    return hist


def extraer_historia_eri(fuente, anio, hoja="2.E.R.I. MES-ACUMULADO",
                         hasta_periodo=None, cc_map=None):
    """Del informe ANTERIOR (hoja de resultados mes a mes) extrae los meses ya
    llenos del `anio` como historia para el informe nativo.
      · sin cc_map → {periodo: {(cuenta, '__TOT__'): valor_pesos}} usando la columna
        TOTAL de cada bloque mensual.
      · con cc_map {nombre_normalizado: codigo_cc} → {periodo: {(cuenta, cc): valor}}
        leyendo las 9 columnas de CC (inmediatamente antes del total) de cada mes,
        de modo que el resultado por CENTRO DE COSTO quede en cada mes histórico.
    Solo cuentas HOJA (para no duplicar al sumar)."""
    import openpyxl
    data = fuente if isinstance(fuente, (bytes, bytearray)) else (
        fuente.read() if hasattr(fuente, "read") else open(fuente, "rb").read())
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    if hoja not in wb.sheetnames:
        for s in wb.sheetnames:
            if "E.R.I" in s.upper() and "ACUM" in s.upper():
                hoja = s; break
        else:
            return {}
    ws = wb[hoja]
    rows = list(ws.iter_rows(values_only=True))
    # fila de encabezados: la que tenga varias etiquetas 'YYYY-MM'
    hdr_i = None
    pat = re.compile(rf"{anio}-\d\d")
    for i, r in enumerate(rows[:12]):
        if sum(1 for c in r if c and pat.fullmatch(str(c).strip())) >= 2:
            hdr_i = i; break
    if hdr_i is None:
        return {}
    hdr = rows[hdr_i]
    # columnas TOTAL de cada mes (encabezado = 'YYYY-MM'); saltar el actual si hasta
    col_periodo = {}
    for j, c in enumerate(hdr):
        if c and pat.fullmatch(str(c).strip()):
            p = str(c).strip()
            if hasta_periodo and p >= hasta_periodo:
                continue
            col_periodo[j] = p
    if not col_periodo:
        return {}
    # cuentas hoja: códigos de col A que ninguna otra fila extiende
    codes = []
    for r in rows[hdr_i + 1:]:
        c = _dig(r[0]) if r and r[0] is not None else ""
        if c:
            codes.append(c)
    codeset = set(codes)
    parents = set()
    for c in codeset:
        for L in range(1, len(c)):
            if c[:L] in codeset:
                parents.add(c[:L])
    hojas = codeset - parents
    hist = {p: {} for p in col_periodo.values()}

    def _num(x):
        try:
            return float(x or 0)
        except (TypeError, ValueError):
            return 0.0

    # columnas de CC por mes: las 9 columnas inmediatamente ANTES de la del total,
    # mapeando el nombre del encabezado a un código de CC del informe nativo
    cc_cols_por_periodo = {}
    if cc_map:
        for j, p in col_periodo.items():
            pares = []
            for jj in range(max(0, j - 9), j):
                code = cc_map.get(_norm_cc(hdr[jj])) if jj < len(hdr) else None
                if code:
                    pares.append((jj, code))
            cc_cols_por_periodo[j] = pares

    # filas del juego de inventarios (cuenta 14): inicial / compras / final
    INV_LBL = {"inventario inicial": "__INVINI__", "compras": "__COMPRAS__",
               "inventario final": "__INVFIN__"}
    # filas de AJUSTES (al pie del ERI antiguo) → se guardan como total del mes
    AJ_LBL = [("ft serv admon ptos vta", "__AJ_FT__"), ("fe socios", "__AJ_FE__"),
              ("ingresos menos costo arriendo plaza fabricato", "__AJ_AR__")]

    for r in rows[hdr_i + 1:]:
        c = _dig(r[0]) if r and r[0] is not None else ""
        lbl = str(r[1]).strip().lower() if len(r) > 1 and r[1] is not None else ""
        # juego de inventarios (cuenta 14): total del mes + POR CENTRO DE COSTO
        if c.startswith("14") and lbl in INV_LBL:
            key = INV_LBL[lbl]
            for j, p in col_periodo.items():
                tot = _num(r[j] if j < len(r) else None)
                if abs(tot) > 0:
                    hist[p][(key, "__TOT__")] = hist[p].get((key, "__TOT__"), 0.0) + tot * 1000.0
                if cc_map:
                    for jj, code in cc_cols_por_periodo.get(j, []):
                        v = _num(r[jj] if jj < len(r) else None)
                        if abs(v) > 0:
                            hist[p][(key, code)] = hist[p].get((key, code), 0.0) + v * 1000.0
            continue
        # AJUSTES del pie (FT serv, FE socios, arriendo Plaza Fabricato): total + POR CC
        aj_key = next((k for frag, k in AJ_LBL if frag in lbl), None)
        if aj_key:
            for j, p in col_periodo.items():
                v = _num(r[j] if j < len(r) else None)
                if abs(v) > 0:
                    hist[p][(aj_key, "__TOT__")] = hist[p].get((aj_key, "__TOT__"), 0.0) + v * 1000.0
                if cc_map:
                    for jj, code in cc_cols_por_periodo.get(j, []):
                        vv = _num(r[jj] if jj < len(r) else None)
                        if abs(vv) > 0:
                            hist[p][(aj_key, code)] = hist[p].get((aj_key, code), 0.0) + vv * 1000.0
            continue
        # AJUSTE DIFERENCIA HENKO: fila sin código en el antiguo → cuenta 41359599
        es_henko = "ajuste henk" in lbl
        if es_henko:
            c = "41359599"
        if not es_henko and (not c or c not in hojas or c[0] not in "456"):
            continue
        for j, p in col_periodo.items():
            tot = _num(r[j] if j < len(r) else None)
            if cc_map:
                ssum = 0.0
                for jj, code in cc_cols_por_periodo.get(j, []):
                    v = _num(r[jj] if jj < len(r) else None)
                    if abs(v) > 0:
                        hist[p][(c, code)] = hist[p].get((c, code), 0.0) + v * 1000.0
                        ssum += v
                rem = tot - ssum                 # lo que no quedó en ningún CC
                if abs(rem) > 1e-9:
                    hist[p][(c, NOCC)] = hist[p].get((c, NOCC), 0.0) + rem * 1000.0
            elif abs(tot) > 0:
                hist[p][(c, "__TOT__")] = hist[p].get((c, "__TOT__"), 0.0) + tot * 1000.0
    return {p: d for p, d in hist.items() if d}


def extraer_iva_bimestres(fuente):
    """Del INFORME ANTIGUO (hoja OBSERVACIONES) reconstruye los 5 bimestres de IVA
    (valores en pesos). Devuelve [b1, b2, b3, b4, b5] (None donde no haya)."""
    import openpyxl
    data = fuente if isinstance(fuente, (bytes, bytearray)) else (
        fuente.read() if hasattr(fuente, "read") else open(fuente, "rb").read())
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    hoja = None
    for s in wb.sheetnames:
        if "OBSERVAC" in s.upper():
            hoja = s; break
    if hoja is None:
        return [None] * 5
    bim = [None] * 5
    for r in wb[hoja].iter_rows(values_only=True):
        for j, c in enumerate(r):
            m = re.match(r"IVA BIMESTRE (\d)", str(c or "").strip().upper())
            if m and j + 1 < len(r):
                try:
                    bim[int(m.group(1)) - 1] = float(r[j + 1] or 0) * 1000.0
                except (TypeError, ValueError):
                    pass
    return bim


_MES2NUM = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
            "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
            "noviembre": 11, "diciembre": 12}


def extraer_provision_hist(fuente, anio, hasta_periodo=None):
    """Del INFORME ANTIGUO (hoja de proyección de renta) extrae, por cada mes
    previo, los saldos DIGITADOS A MANO (gastos no deducibles, impuestos asumidos,
    costos ej. ant., donaciones, compensación, saldos a favor / anticipos y las
    RETENCIONES y AUTORRETENCIONES) y el/los TRABAJADOR(ES) con discapacidad.
    Devuelve {'meses': {periodo:{campo:valor_pesos}},
              'disc': {'nombre':.., 'meses':{periodo:valor_pesos}}}."""
    import openpyxl
    data = fuente if isinstance(fuente, (bytes, bytearray)) else (
        fuente.read() if hasattr(fuente, "read") else open(fuente, "rb").read())
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    hoja = None
    for s in wb.sheetnames:
        u = s.upper()
        if "IMPORENTA" in u or "IMPORRENTA" in u or ("RENTA" in u and "PROV" in u):
            hoja = s; break
    if hoja is None:
        return {"meses": {}, "disc": {"nombre": None, "meses": {}}}
    rows = list(wb[hoja].iter_rows(values_only=True))

    def _num(x):
        try:
            return float(x or 0)
        except (TypeError, ValueError):
            return 0.0

    hdr_i = None
    for i, r in enumerate(rows[:16]):
        names = [str(c or "").strip().lower() for c in r]
        if sum(1 for n in names if n in _MES2NUM) >= 3:
            hdr_i = i; break
    if hdr_i is None:
        return {"meses": {}, "disc": {"nombre": None, "meses": {}}}
    col_per = {}
    for j, c in enumerate(rows[hdr_i]):
        n = str(c or "").strip().lower()
        if n in _MES2NUM:
            p = f"{anio}-{_MES2NUM[n]:02d}"
            if hasta_periodo and p >= hasta_periodo:
                continue
            col_per[j] = p
    FIELDS = {
        "gastos no deducibles admon": "nda", "gastos no deducibles ventas": "ndv",
        "impuestos asumidos": "asu", "costos y gastos de ejercicios ant": "eja",
        "donaciones": "don", "compensacion de presuntiva": "comp",
        "saldo a favor renta año anterior": "sfa",
        "anticipo de renta año anterior": "antant",
        "retenciones que le practicaron": "ret",
        "autoretenciones": "aut", "autorretenciones": "aut",
        "anticipo de renta año siguiente": "ansig"}
    meses = {p: {} for p in col_per.values()}
    disc = {"nombre": None, "meses": {}}
    en_empleados = False
    for r in rows[hdr_i + 1:]:
        lbl = str(r[1] or "").strip().lower() if len(r) > 1 else ""
        key = FIELDS.get(lbl)
        if key:
            for j, p in col_per.items():
                v = _num(r[j] if j < len(r) else None)
                if abs(v) > 0:
                    meses[p][key] = meses[p].get(key, 0.0) + v * 1000.0
        if "nombre empleado" in lbl:
            en_empleados = True
            continue
        if en_empleados and len(r) > 1 and r[1] and not disc["nombre"]:
            vals = {}; has = False
            for j, p in col_per.items():
                v = _num(r[j] if j < len(r) else None)
                if abs(v) > 0:
                    has = True
                vals[p] = v * 1000.0
            if has:
                disc["nombre"] = str(r[1]).strip(); disc["meses"] = vals
    return {"meses": {p: d for p, d in meses.items() if d}, "disc": disc}
