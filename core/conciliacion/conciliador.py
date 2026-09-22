# -*- coding: utf-8 -*-
"""
core/conciliacion/conciliador.py

Conciliación bancaria config-driven para INTEGRAL.

Cruza tres fuentes por cuenta bancaria:
  1) AUXILIAR general del mes (libros): filtrado a la cuenta puente del banco
     (p.ej. 11-10-05-99). De aquí salen el SALDO EN LIBROS (saldo anterior),
     las CONSIGNACIONES (total débitos) y los PAGOS (total créditos).
  2) REPORTE DEL BANCO: la hoja del banco con los movimientos y la columna
     'N COMPROBANTE' (el número que la empresa coloca). Se cruza N COMPROBANTE
     con el 'Documento' del auxiliar. Los GTO FINANCIERO se desglosan en gasto
     bancario / comisiones / IVA / GMF.
  3) DATÁFONO (Credibanco, opcional): comisión y retenciones (retefuente,
     reteIVA, reteICA) por centro de costo, que también son NOTAS DÉBITO.

Fórmula (igual a la plantilla de la empresa):
    Saldo en libros
    + Consignaciones (débitos auxiliar)
    − Pagos (créditos auxiliar)
    − Notas débito (gasto banc + comis + comis datáfono + IVA + GMF +
                    reteIVA + retefuente + reteICA)
    = Saldo en libros a fecha de cierre
    − Consignaciones en tránsito (partida conciliatoria)
    = Saldo según extracto del banco

Partidas conciliatorias:
    - En tránsito / no en banco : documentos en libros que no están en el banco.
    - Pagos que no salieron     : ídem, del lado de pagos.
    - No están en contabilidad  : documentos en el banco que no están en libros.
"""
from __future__ import annotations

import io
import re
from collections import defaultdict


def _num(x) -> float:
    try:
        return float(str(x).replace(",", "").replace("$", "").strip() or 0)
    except (ValueError, TypeError):
        return 0.0


def _nk(x) -> str:
    """Llave numérica normalizada de un documento/comprobante (sin ceros a la izq.)."""
    return re.sub(r"\D", "", str(x or "")).lstrip("0")


def _abrir(fuente, hoja=None):
    import openpyxl
    if isinstance(fuente, (bytes, bytearray)):
        wb = openpyxl.load_workbook(io.BytesIO(fuente), data_only=True, read_only=True)
    elif hasattr(fuente, "read"):
        wb = openpyxl.load_workbook(io.BytesIO(fuente.read()), data_only=True, read_only=True)
    else:
        wb = openpyxl.load_workbook(fuente, data_only=True, read_only=True)
    if hoja is None:
        return wb.active, wb
    for ws in wb.worksheets:
        if ws.title.strip().upper() == str(hoja).strip().upper():
            return ws, wb
    return wb.active, wb


# ---- reglas de desglose de GTO FINANCIERO (editable) ----
GASTO_REGLAS_DEF = [
    (r"4X1000|\bGMF\b|IMPTO GOBIERNO|GRAVAMEN", "GMF"),
    (r"\bIVA\b", "IVA"),
    (r"COMIS", "COMISIONES"),
    # el resto -> GASTO BANCARIO
]


def leer_auxiliar(fuente, cuenta_prefijo: str):
    """Del AUXILIAR: saldo anterior, consignaciones (deb), pagos (cred) y el
    detalle por documento de la cuenta que empieza por `cuenta_prefijo`.
    Ignora la fila de SUBTOTAL de la cuenta (la que no trae Nro Registro)."""
    ws, _ = _abrir(fuente)
    rows = list(ws.iter_rows(values_only=True))
    # localizar columnas por encabezado (fila con 'Cuenta' y 'Documento')
    hdr_i = None
    for i, r in enumerate(rows[:8]):
        vals = [str(c or "").strip().lower() for c in r]
        if "cuenta" in vals and "documento" in vals:
            hdr_i = i
            break
    if hdr_i is None:
        hdr_i = 2
    H = {str(c or "").strip().lower(): j for j, c in enumerate(rows[hdr_i])}
    cCta = H.get("cuenta", 0)
    cReg = H.get("nro registro", 5)
    cDoc = H.get("documento", 8)
    cFec = H.get("fecha", 7)
    cDet = H.get("detalle", 10)
    cSA = H.get("saldo anterior", 12)
    cDeb = H.get("débitos", H.get("debitos", 13))
    cCred = H.get("créditos", H.get("creditos", 14))

    pref = cuenta_prefijo.strip()
    saldo_ant = None
    consig = pagos = 0.0
    detalle = []
    for r in rows[hdr_i + 1:]:
        cta = str(r[cCta] or "").strip()
        if not cta.startswith(pref):
            continue
        if saldo_ant is None:
            saldo_ant = _num(r[cSA])
        if not str(r[cReg] or "").strip():
            continue  # fila subtotal de la cuenta
        deb, cred = _num(r[cDeb]), _num(r[cCred])
        if deb == 0 and cred == 0:
            continue
        consig += deb
        pagos += cred
        detalle.append({"doc": _nk(r[cDoc]), "fecha": str(r[cFec] or ""),
                        "detalle": str(r[cDet] or "")[:60], "deb": deb, "cred": cred})
    return {"saldo_ant": saldo_ant or 0.0, "consignaciones": round(consig, 2),
            "pagos": round(pagos, 2), "detalle": detalle}


def leer_banco(fuente, hoja: str, gasto_reglas=None):
    """De la HOJA del banco: movimientos con N COMPROBANTE, débito, crédito y
    concepto; desglose de GTO FINANCIERO en gasto/comisiones/IVA/GMF."""
    reglas = gasto_reglas or GASTO_REGLAS_DEF
    ws, _ = _abrir(fuente, hoja)
    rows = list(ws.iter_rows(values_only=True))
    # encabezado: primera fila con 'N COMPROBANTE' o 'DEBITO'
    hdr_i = 0
    for i, r in enumerate(rows[:6]):
        up = [str(c or "").strip().upper() for c in r]
        if "N COMPROBANTE" in up or "DEBITO" in up or "DÉBITO" in up:
            hdr_i = i
            break
    H = {str(c or "").strip().upper(): j for j, c in enumerate(rows[hdr_i])}
    cNC = H.get("N COMPROBANTE")
    cDeb = H.get("DEBITO", H.get("DÉBITO", H.get("DEBITOS", H.get("DÉBITOS"))))
    cCred = H.get("CREDITO", H.get("CRÉDITO", H.get("CREDITOS", H.get("CRÉDITOS"))))
    cCon = H.get("CONCEPTO")
    cDet = H.get("DETALLE", H.get("TRANSACCIÓN", H.get("DESCRIPCIÓN")))
    cFec = H.get("FECHA")

    movs = []
    g = defaultdict(float)
    for r in rows[hdr_i + 1:]:
        deb = _num(r[cDeb]) if cDeb is not None else 0.0
        cred = _num(r[cCred]) if cCred is not None else 0.0
        if deb == 0 and cred == 0:
            continue
        det = str(r[cDet] or "") if cDet is not None else ""
        con = str(r[cCon] or "").strip() if cCon is not None else ""
        movs.append({"nc": _nk(r[cNC]) if cNC is not None else "",
                     "fecha": str(r[cFec] or "") if cFec is not None else "",
                     "detalle": det[:60], "deb": deb, "cred": cred, "concepto": con})
        if con.upper() == "GTO FINANCIERO":
            v = deb + cred
            cat = "GASTO BANCARIO"
            for pat, nombre in reglas:
                if re.search(pat, det, re.I):
                    cat = nombre
                    break
            g[cat] += v
    return {"movimientos": movs, "gastos": {k: round(v, 2) for k, v in g.items()}}


def _es_encab_datafono(fila):
    """¿Esta fila es el encabezado del resumen del datáfono? Devuelve el mapeo
    de columnas {clave: indice} si lo es, o None."""
    up = [str(c or "").strip().upper() for c in fila]
    joined = " | ".join(up)
    if not (("COMIS" in joined) and ("CENTRO" in joined or "COSTO" in joined)):
        return None
    mp = {}
    for j, v in enumerate(up):
        if ("CENTRO" in v or "COSTO" in v) and "cc" not in mp:
            mp["cc"] = j
        elif "OASIS" in v or "ESTABLEC" in v or "NOMBRE" in v or "PUNTO" in v:
            mp.setdefault("oasis", j)
        elif "COMIS" in v:
            mp.setdefault("comision", j)
        elif "RETEFUENTE" in v or ("RTE" in v and "FUENTE" in v) or "RETE FUENTE" in v \
                or ("RETE" in v and "FUENTE" in v):
            mp.setdefault("retefuente", j)
        elif "IVA" in v and ("RETE" in v or "RTE" in v):
            mp.setdefault("reteiva", j)
        elif "ICA" in v and ("RETE" in v or "RTE" in v):
            mp.setdefault("reteica", j)
    return mp if "comision" in mp else None


def _col_por_nombre(hdr_up, *fragmentos):
    """Índice de la 1ª columna cuyo encabezado contiene alguno de los fragmentos."""
    for frag in fragmentos:
        for j, h in enumerate(hdr_up):
            if frag in h:
                return j
    return None


def maestro_desde_workbook(wb):
    """Si el libro tiene una hoja MAESTRO (CODIGO ESTABLECIMIENTO / OASIS /
    CENTRO DE COSTO), devuelve {establecimiento: (cc, oasis)}; si no, None."""
    for ws in wb.worksheets:
        primera = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not primera:
            continue
        up = [str(c or "").strip().upper() for c in primera]
        iE = _col_por_nombre(up, "CODIGO ESTABLECIMIENTO", "ESTABLECIMIENTO")
        iC = _col_por_nombre(up, "CENTRO DE COSTO", "CENTRO", "COSTO")
        if iE is None or iC is None:
            continue
        iO = _col_por_nombre(up, "OASIS", "NOMBRE", "PUNTO")
        m = {}
        for r in ws.iter_rows(min_row=2, values_only=True):
            est = str(r[iE] or "").strip() if iE < len(r) else ""
            if not est:
                continue
            cc = str(r[iC] or "").strip() if iC < len(r) else ""
            oa = str(r[iO] or "") if iO is not None and iO < len(r) else ""
            m[est] = (cc, oa)
        if m:
            return m
    return None


def maestro_desde_bytes(fuente):
    """Lee el MAESTRO (establecimiento -> cc) de un archivo de macro (.xlsm/.xlsx)."""
    if fuente is None:
        return {}
    import openpyxl
    data = fuente if isinstance(fuente, (bytes, bytearray)) else (
        fuente.read() if hasattr(fuente, "read") else open(fuente, "rb").read())
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    return maestro_desde_workbook(wb) or {}


def _leer_raw_credibanco(wb, maestro=None):
    """Del archivo ORIGINAL de Credibanco (hoja 'Reporte Conciliar' u otra con
    CODIGO ESTABLECIMIENTO y VALOR COMISION): agrupa por centro de costo y suma
    comisión y retenciones. El CC sale del MAESTRO (establecimiento -> cc); si no
    hay MAESTRO, del propio archivo (columna NO TERMINAL / CENTRO DE COSTO, que
    Credibanco ya trae con el código del centro)."""
    maestro = maestro or {}
    for ws in wb.worksheets:
        cabecera = list(ws.iter_rows(min_row=1, max_row=5, values_only=True))
        hdr_up = hdr_i = None
        for i, r in enumerate(cabecera):
            up = [str(c or "").strip().upper() for c in r]
            if _col_por_nombre(up, "CODIGO ESTABLECIMIENTO") is not None and \
               _col_por_nombre(up, "VALOR COMISION", "VALOR COMIS") is not None:
                hdr_up, hdr_i = up, i
                break
        if hdr_up is None:
            continue

        cEst = _col_por_nombre(hdr_up, "CODIGO ESTABLECIMIENTO", "ESTABLECIMIENTO")
        cCom = _col_por_nombre(hdr_up, "VALOR COMISION", "VALOR COMIS")
        cRF = _col_por_nombre(hdr_up, "VALOR RETEFUENTE", "RETEFUENTE")
        cRI = _col_por_nombre(hdr_up, "VALOR RETE IVA", "RETE IVA", "RETEIVA")
        cRA = _col_por_nombre(hdr_up, "VALOR RTE ICA", "RTE ICA", "RETE ICA", "RETEICA")
        cTerm = _col_por_nombre(hdr_up, "NO TERMINAL", "TERMINAL", "CENTRO DE COSTO")

        agg = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
        oasis_of, n = {}, 0
        for r in ws.iter_rows(min_row=hdr_i + 2, values_only=True):
            est = str(r[cEst] or "").strip() if cEst is not None and cEst < len(r) else ""
            if not est:
                continue
            com = abs(_num(r[cCom])) if cCom is not None and cCom < len(r) else 0.0
            rf = abs(_num(r[cRF])) if cRF is not None and cRF < len(r) else 0.0
            ri = abs(_num(r[cRI])) if cRI is not None and cRI < len(r) else 0.0
            ria = abs(_num(r[cRA])) if cRA is not None and cRA < len(r) else 0.0
            if com == 0 and rf == 0 and ri == 0 and ria == 0:
                continue
            cc, oa = "", ""
            if est in maestro:
                cc, oa = maestro[est]
            if not cc and cTerm is not None and cTerm < len(r):
                cc = str(r[cTerm] or "").strip()
            if not cc:
                cc = est
            v = agg[cc]
            v[0] += com; v[1] += rf; v[2] += ri; v[3] += ria
            if oa and cc not in oasis_of:
                oasis_of[cc] = oa
            n += 1
        if n:
            por_cc = [{"cc": cc, "oasis": oasis_of.get(cc, ""),
                       "comision": round(v[0], 2), "retefuente": round(v[1], 2),
                       "reteiva": round(v[2], 2), "reteica": round(v[3], 2)}
                      for cc, v in sorted(agg.items())]
            tot = [sum(v[i] for v in agg.values()) for i in range(4)]
            return {"por_cc": por_cc, "comision": round(tot[0], 2),
                    "retefuente": round(tot[1], 2), "reteiva": round(tot[2], 2),
                    "reteica": round(tot[3], 2), "n_filas": len(por_cc),
                    "hoja": ws.title + " (crudo Credibanco)"}
    return None


def leer_datafono(fuente, hoja="RESUMEN MENSUAL", maestro=None):
    """Comisión y retenciones del datáfono Credibanco por centro de costo.

    Acepta DOS tipos de archivo:
      1) El ARCHIVO ORIGINAL de Credibanco (hoja 'Reporte Conciliar', con CODIGO
         ESTABLECIMIENTO y VALOR COMISION/RETEFUENTE/RETE IVA/RTE ICA): calcula el
         resumen directamente desde el crudo, agrupando por centro de costo con el
         MAESTRO (establecimiento -> cc) que le pases, o con la columna del propio
         archivo. ES EL MODO PREFERIDO (no exige correr la macro).
      2) El archivo de la MACRO ya con la hoja 'RESUMEN MENSUAL' (comisión y
         retenciones por centro de costo): se lee tal cual.

    Robusto: detecta hoja y columnas por su encabezado; toma los valores en
    magnitud (por si vienen en negativo)."""
    vacio = {"por_cc": [], "comision": 0.0, "retefuente": 0.0,
             "reteiva": 0.0, "reteica": 0.0, "n_filas": 0, "hoja": None}
    if fuente is None:
        return vacio

    import openpyxl
    if isinstance(fuente, (bytes, bytearray)):
        wb = openpyxl.load_workbook(io.BytesIO(fuente), data_only=True, read_only=True)
    elif hasattr(fuente, "read"):
        wb = openpyxl.load_workbook(io.BytesIO(fuente.read()), data_only=True, read_only=True)
    else:
        wb = openpyxl.load_workbook(fuente, data_only=True, read_only=True)

    # 1) modo preferido: calcular desde el crudo de Credibanco
    maes = maestro or maestro_desde_workbook(wb)
    crudo = _leer_raw_credibanco(wb, maes)
    if crudo:
        return crudo

    # 2) respaldo: leer la hoja RESUMEN MENSUAL de la macro
    # candidatas: primero la hoja pedida, luego el resto
    orden = ([ws for ws in wb.worksheets if ws.title.strip().upper() == str(hoja).strip().upper()]
             + [ws for ws in wb.worksheets if ws.title.strip().upper() != str(hoja).strip().upper()])

    for ws in orden:
        rows = list(ws.iter_rows(values_only=True))
        mp = hdr_i = None
        for i, r in enumerate(rows[:15]):
            m = _es_encab_datafono(r)
            if m:
                mp, hdr_i = m, i
                break
        if not mp:
            continue

        cCC, cCom = mp.get("cc", 0), mp["comision"]
        cOa = mp.get("oasis", cCC + 1)
        cRF, cRI, cRA = mp.get("retefuente"), mp.get("reteiva"), mp.get("reteica")
        por_cc = []
        com = ret = riva = rica = 0.0
        for r in rows[hdr_i + 1:]:
            cc = str(r[cCC] or "").strip() if cCC < len(r) else ""
            if not cc or cc.upper().startswith(("TOTAL", "SUMA")):
                continue
            # son NOTAS DÉBITO (cargos): se toman en magnitud, por si el export
            # de Credibanco los trae con signo negativo (p.ej. JIPER).
            c = abs(_num(r[cCom])) if cCom < len(r) else 0.0
            rf = abs(_num(r[cRF])) if cRF is not None and cRF < len(r) else 0.0
            ri = abs(_num(r[cRI])) if cRI is not None and cRI < len(r) else 0.0
            ria = abs(_num(r[cRA])) if cRA is not None and cRA < len(r) else 0.0
            if c == 0 and rf == 0 and ri == 0 and ria == 0:
                continue
            oa = str(r[cOa] or "") if cOa < len(r) else ""
            por_cc.append({"cc": cc, "oasis": oa, "comision": c,
                           "retefuente": rf, "reteiva": ri, "reteica": ria})
            com += c; ret += rf; riva += ri; rica += ria
        if por_cc:
            return {"por_cc": por_cc, "comision": round(com, 2),
                    "retefuente": round(ret, 2), "reteiva": round(riva, 2),
                    "reteica": round(rica, 2), "n_filas": len(por_cc), "hoja": ws.title}
    return vacio


def conciliar(aux, banco, datafono, saldo_banco: float,
              transito_real=None, tolerancia: float = 10000.0):
    """Arma la conciliación y las partidas. Recibe los dict de leer_* y el saldo
    del extracto del banco.

    - Si `transito_real` es None: las consignaciones en tránsito se calculan como
      el plug (saldo a cierre − saldo del banco), así siempre cuadra.
    - Si se entrega `transito_real` (valor de las partidas reales en puente): el
      residuo = saldo a cierre − tránsito real − saldo del banco se carga como
      AJUSTE AL PESO a gasto bancario SIEMPRE QUE |residuo| ≤ `tolerancia`
      (por defecto ±10.000), para que cuadre exacto. Si supera la tolerancia se
      deja el residuo visible y `cuadra=False` para que lo revises.
    """
    g = banco["gastos"]
    gasto_banc = g.get("GASTO BANCARIO", 0.0)
    comis = g.get("COMISIONES", 0.0)
    iva = g.get("IVA", 0.0)
    gmf = g.get("GMF", 0.0)
    com_d = datafono["comision"]
    ret_d = datafono["retefuente"]
    riva_d = datafono["reteiva"]
    rica_d = datafono["reteica"]

    ajuste = 0.0
    if transito_real is None:
        notas = round(gasto_banc + comis + com_d + iva + gmf + riva_d + ret_d + rica_d, 2)
        cierre = round(aux["saldo_ant"] + aux["consignaciones"] - aux["pagos"] - notas, 2)
        transito = round(cierre - saldo_banco, 2)
    else:
        transito = round(float(transito_real), 2)
        notas0 = round(gasto_banc + comis + com_d + iva + gmf + riva_d + ret_d + rica_d, 2)
        cierre0 = round(aux["saldo_ant"] + aux["consignaciones"] - aux["pagos"] - notas0, 2)
        residuo = round(cierre0 - transito - saldo_banco, 2)   # lo que sobra/falta
        if abs(residuo) <= tolerancia:
            ajuste = residuo                 # se carga a gasto bancario
            gasto_banc = round(gasto_banc + ajuste, 2)
        notas = round(gasto_banc + comis + com_d + iva + gmf + riva_d + ret_d + rica_d, 2)
        cierre = round(aux["saldo_ant"] + aux["consignaciones"] - aux["pagos"] - notas, 2)

    # cruce por documento
    lby = defaultdict(list)
    bby = defaultdict(list)
    for x in aux["detalle"]:
        lby[x["doc"]].append(x)
    for x in banco["movimientos"]:
        bby[x["nc"]].append(x)
    dl = set(lby) - {""}
    db = set(bby) - {""}
    cruzan = sorted(dl & db)
    solo_libros = sorted(dl - db)   # en libros, no en banco
    solo_banco = sorted(db - dl)    # en banco, no en libros (no en contabilidad)

    return {
        "saldo_ant": round(aux["saldo_ant"], 2),
        "consignaciones": aux["consignaciones"],
        "pagos": aux["pagos"],
        "notas_debito": notas,
        "gasto_bancario": gasto_banc, "comisiones": comis,
        "comision_datafono": com_d, "iva": iva, "gmf": gmf,
        "reteiva": riva_d, "retefuente": ret_d, "reteica": rica_d,
        "saldo_cierre": cierre,
        "consignaciones_transito": transito,
        "saldo_banco": round(saldo_banco, 2),
        "ajuste_al_peso": round(ajuste, 2),
        "cuadra": abs((cierre - transito) - saldo_banco) < 0.01,
        "n_cruzan": len(cruzan),
        "solo_libros": [x for d in solo_libros for x in lby[d]],
        "solo_banco": [x for d in solo_banco for x in bby[d]],
        "datafono_cc": datafono["por_cc"],
    }


# ===========================================================================
# Configuración por empresa (Supabase) — tabla conciliacion_bancos
# ===========================================================================
def cargar_bancos(sb, empresa_id) -> list:
    try:
        r = (sb.table("conciliacion_bancos").select("*")
             .eq("empresa_id", empresa_id).order("orden").execute())
        return [dict(x) for x in (r.data or [])]
    except Exception:  # noqa: BLE001
        return []


def guardar_bancos(sb, empresa_id, filas) -> int:
    filas = [f for f in filas if str(f.get("nombre") or "").strip()
             and str(f.get("cuenta_auxiliar") or "").strip()]
    nombres = [str(f["nombre"]).strip() for f in filas]
    for b in cargar_bancos(sb, empresa_id):
        if b["nombre"] not in nombres:
            sb.table("conciliacion_bancos").delete().eq("empresa_id", empresa_id).eq("nombre", b["nombre"]).execute()
    payload = [{"empresa_id": empresa_id, "nombre": str(f["nombre"]).strip(),
                "cuenta_auxiliar": str(f.get("cuenta_auxiliar") or "").strip(),
                "hoja_reporte": str(f.get("hoja_reporte") or "").strip(), "orden": i}
               for i, f in enumerate(filas)]
    if payload:
        sb.table("conciliacion_bancos").upsert(payload, on_conflict="empresa_id,nombre").execute()
    return len(payload)


BANCOS_LOLITA = [
    {"nombre": "BANCOLOMBIA CTE 4451",   "cuenta_auxiliar": "11-10-05-99", "hoja_reporte": "CTA- PUENTE 4451"},
    {"nombre": "OCCIDENTE 9426",         "cuenta_auxiliar": "11-10-05-05", "hoja_reporte": "OCCIDENTE 9426"},
    {"nombre": "DAVIVIENDA 7872",        "cuenta_auxiliar": "11-20-05-13", "hoja_reporte": "Davivienda cta 7872"},
    {"nombre": "BOGOTA 3199",            "cuenta_auxiliar": "11-10-05-20", "hoja_reporte": "BOGOTA 3199"},
    {"nombre": "BANCOLOMBIA AHORROS",    "cuenta_auxiliar": "11-10-05-06", "hoja_reporte": "BANCOLOMBA AHORROS"},
]


def sembrar_lolita(sb, empresa_id) -> int:
    return guardar_bancos(sb, empresa_id, BANCOS_LOLITA)


# ===========================================================================
# MAESTRO del datáfono por empresa (establecimiento -> centro de costo)
# tabla conciliacion_datafono (migración 022)
# ===========================================================================
def cargar_maestro(sb, empresa_id) -> dict:
    """Devuelve {establecimiento: (cc, oasis)} configurado para la empresa."""
    try:
        r = (sb.table("conciliacion_datafono").select("*")
             .eq("empresa_id", empresa_id).execute())
        return {str(x["establecimiento"]).strip():
                (str(x.get("cc") or "").strip(), str(x.get("oasis") or ""))
                for x in (r.data or []) if str(x.get("establecimiento") or "").strip()}
    except Exception:  # noqa: BLE001
        return {}


def cargar_maestro_filas(sb, empresa_id) -> list:
    """El maestro como lista de filas para editar en la tabla de configuración."""
    m = cargar_maestro(sb, empresa_id)
    return [{"establecimiento": est, "cc": cc, "oasis": oa}
            for est, (cc, oa) in sorted(m.items())]


def guardar_maestro(sb, empresa_id, filas) -> int:
    """filas: [{establecimiento, cc, oasis}]. Reemplaza el maestro de la empresa."""
    filas = [f for f in filas if str(f.get("establecimiento") or "").strip()]
    try:
        sb.table("conciliacion_datafono").delete().eq("empresa_id", empresa_id).execute()
    except Exception:  # noqa: BLE001
        pass
    payload = [{"empresa_id": empresa_id,
                "establecimiento": str(f["establecimiento"]).strip(),
                "cc": str(f.get("cc") or "").strip(),
                "oasis": str(f.get("oasis") or "").strip()} for f in filas]
    if payload:
        sb.table("conciliacion_datafono").upsert(
            payload, on_conflict="empresa_id,establecimiento").execute()
    return len(payload)


def guardar_maestro_dict(sb, empresa_id, maestro: dict) -> int:
    """Guarda un {establecimiento: (cc, oasis)} (p.ej. importado de la macro)."""
    filas = [{"establecimiento": est, "cc": v[0] if isinstance(v, (list, tuple)) else v,
              "oasis": v[1] if isinstance(v, (list, tuple)) and len(v) > 1 else ""}
             for est, v in maestro.items()]
    return guardar_maestro(sb, empresa_id, filas)


# MAESTRO de GRUPO DE LOLITA (de la macro Credibanco): establecimiento -> (cc, oasis)
MAESTRO_LOLITA = {
    "22554349": ("100401", "MONTERREY"),
    "22554331": ("100501", "TORRE MEDICA"),
    "22554323": ("100601", "PUNTO CLAVE"),
    "13382460": ("100901", "MAYORCA PISO 4"),
    "12680385": ("101201", "MEGA PLAZA"),
    "22554307": ("101301", "CLINICA DEL PRADO"),
    "22554273": ("101801", "PLAZA DE LA LIBERTAD"),
    "22554281": ("102001", "PLAZA FABRICATO"),
    "22792659": ("103001", "UNICENTRO"),
}


def sembrar_maestro_lolita(sb, empresa_id) -> int:
    return guardar_maestro_dict(sb, empresa_id, MAESTRO_LOLITA)
