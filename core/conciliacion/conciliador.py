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


def _fmt_fecha(v) -> str:
    """Normaliza una fecha a DD/MM/AAAA. Acepta datetime, o el entero DDMMAAAA
    que usa el reporte del banco (p.ej. 1072026 -> 01/07/2026)."""
    if v is None or v == "":
        return ""
    try:
        import datetime as _dt
        if isinstance(v, (_dt.datetime, _dt.date)):
            return v.strftime("%d/%m/%Y")
    except Exception:  # noqa: BLE001
        pass
    s = re.sub(r"\D", "", str(v))
    if 7 <= len(s) <= 8:
        s = s.zfill(8)
        d, m, a = s[:2], s[2:4], s[4:]
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            return f"{d}/{m}/{a}"
    return str(v)


def _expandir_docs(x) -> set:
    """Un renglón del banco (o del auxiliar) puede AGRUPAR varios documentos en la
    misma celda de N COMPROBANTE / Documento. Devuelve el CONJUNTO de documentos
    que representa esa celda, normalizados como _nk (sin ceros a la izquierda).

    Reglas (según cómo lo escribe la empresa):
      · Lista separada por guion / coma / barra / espacio -> cada número es un
        documento distinto:  '28637-28638-5664-5665' -> {28637,28638,5664,5665}
        (el guion NO es rango: '28493-28557' son dos documentos, no 65).
      · Rango explícito con la palabra 'al' o 'a' -> se expande el intervalo:
        'de 1 al 4' / '1 al 4' / '1 a 4' -> {1,2,3,4}.
      · Un solo número -> ese documento.
    """
    s = str(x or "").strip()
    if not s:
        return set()
    nums = re.findall(r"\d+", s)
    if not nums:
        return set()
    low = s.lower()
    m = re.search(r"(\d+)\s*(?:al|a)\s+(\d+)", low)      # rango explícito
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        a, b = min(a, b), max(a, b)
        docs = {str(n) for n in range(a, b + 1)} if 0 <= b - a <= 500 \
            else {str(int(n)) for n in nums}
        docs |= {str(int(n)) for n in nums}             # + cualquier suelto
        return {d for d in docs if d and d != "0"}
    return {str(int(n)) for n in nums if int(n) != 0}   # lista de documentos


_OASIS_STOP = {"PLAZA", "DE", "LA", "DEL", "PISO", "CLINICA", "CLÍNICA", "CENTRO",
               "COSTO", "CL", "SEDE", "LOCAL", "SL", "ML", "EL", "LOS", "LAS", "P4"}


def _oasis_tokens(s) -> set:
    """Palabras significativas de un nombre de punto/OASIS, para poder emparejar
    'CL PRADO' con 'CLINICA DEL PRADO' o 'MAYORCA P4' con 'MAYORCA PISO 4'."""
    s = re.sub(r"[^A-Za-zÁÉÍÓÚÑ0-9 ]", " ", str(s or "")).upper()
    toks = set()
    for w in s.split():
        if len(w) <= 2 or w in _OASIS_STOP or w.isdigit():
            continue
        toks.add(w)
    return toks


def _mapa_cc_oasis(por_cc):
    """Construye un buscador oasis -> (cc, nombre) desde el desglose del datáfono."""
    tabla = []
    for d in por_cc or []:
        toks = _oasis_tokens(d.get("oasis", ""))
        if toks and str(d.get("cc") or "").strip():
            tabla.append((toks, str(d["cc"]).strip(), d.get("oasis", "")))

    def buscar(oasis):
        t = _oasis_tokens(oasis)
        if not t:
            return "", ""
        mejor, score = ("", ""), 0
        for toks, cc, nom in tabla:
            s = len(t & toks)
            if s > score:
                score, mejor = s, (cc, nom)
        return mejor
    return buscar


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
        doc_raw = str(r[cDoc] or "")
        detalle.append({"doc": _nk(doc_raw), "doc_raw": doc_raw,
                        "docs": sorted(_expandir_docs(doc_raw)),
                        "fecha": _fmt_fecha(r[cFec]),
                        "detalle": str(r[cDet] or "")[:60], "deb": deb, "cred": cred})
    return {"saldo_ant": saldo_ant or 0.0, "consignaciones": round(consig, 2),
            "pagos": round(pagos, 2), "detalle": detalle}


# ---- clasificación del TIPO DE ABONO (para el detalle de partidas) ----
TIPO_REGLAS_DEF = [
    (r"ABONO\s*NETO|DATAFONO|DATÁFONO", "DATAFONO"),
    (r"\bQR\b|PAGO\s*QR", "QR"),
    (r"CONSIGNAC", "CONSIGNACION"),
    (r"INTERBANC", "TRANSFERENCIA INTERBANCARIA"),
    (r"TRANSFEREN", "TRANSFERENCIA"),
    (r"\bPSE\b", "PSE"),
    (r"DINERS", "DINERS"),
    (r"EFECTIVO", "EFECTIVO"),
    (r"RAPPI", "RAPPI"),
    (r"NEQUI|DAVIPLATA|LLAVE", "BILLETERA"),
    (r"CORRESPONSAL", "CORRESPONSAL"),
]


def tipo_abono(detalle, concepto=""):
    """Deduce el tipo de abono/egreso (DATAFONO, CONSIGNACION, TRANSFERENCIA, QR,
    PSE, etc.) a partir del detalle y el concepto del movimiento del banco."""
    txt = f"{detalle} {concepto}".upper()
    for pat, nombre in TIPO_REGLAS_DEF:
        if re.search(pat, txt):
            return nombre
    con = str(concepto or "").strip().upper()
    if con and con not in ("CUADRE DE CAJA", "CUADRE DE CAJA MES ANTERIOR"):
        return con
    return "OTRO"


def leer_banco(fuente, hoja: str, gasto_reglas=None):
    """De la HOJA del banco: movimientos con N COMPROBANTE, débito, crédito,
    concepto, OASIS (centro de costo) y tipo de abono; desglose de GTO
    FINANCIERO en gasto/comisiones/IVA/GMF."""
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
    # el encabezado puede repetir 'OASIS'; tomamos la 1ª aparición de cada nombre
    H = {}
    for j, c in enumerate(rows[hdr_i]):
        k = str(c or "").strip().upper()
        if k and k not in H:
            H[k] = j
    cNC = H.get("N COMPROBANTE")
    cDeb = H.get("DEBITO", H.get("DÉBITO", H.get("DEBITOS", H.get("DÉBITOS"))))
    cCred = H.get("CREDITO", H.get("CRÉDITO", H.get("CREDITOS", H.get("CRÉDITOS"))))
    cCon = H.get("CONCEPTO")
    cDet = H.get("DETALLE", H.get("TRANSACCIÓN", H.get("DESCRIPCIÓN")))
    cFec = H.get("FECHA")
    cOa = H.get("OASIS", H.get("CENTRO DE COSTO", H.get("PUNTO")))

    movs = []
    g = defaultdict(float)
    for r in rows[hdr_i + 1:]:
        deb = _num(r[cDeb]) if cDeb is not None else 0.0
        cred = _num(r[cCred]) if cCred is not None else 0.0
        if deb == 0 and cred == 0:
            continue
        det = str(r[cDet] or "") if cDet is not None else ""
        con = str(r[cCon] or "").strip() if cCon is not None else ""
        nc_raw = str(r[cNC] or "") if cNC is not None else ""
        oasis = str(r[cOa] or "").strip() if cOa is not None and cOa < len(r) else ""
        movs.append({"nc": _nk(nc_raw), "nc_raw": nc_raw,
                     "docs": sorted(_expandir_docs(nc_raw)),
                     "fecha": _fmt_fecha(r[cFec]) if cFec is not None else "",
                     "detalle": det[:60], "deb": deb, "cred": cred, "concepto": con,
                     "oasis": oasis, "tipo": tipo_abono(det, con)})
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

    # ---- cruce por documento (expandiendo los renglones que agrupan varios) ----
    def _docs_de(x, llave):
        ds = x.get("docs")
        if ds:
            return set(ds)
        return {x[llave]} if x.get(llave) else set()

    libros_docs = set()
    for x in aux["detalle"]:
        libros_docs |= _docs_de(x, "doc")
    banco_docs = set()
    for x in banco["movimientos"]:
        banco_docs |= _docs_de(x, "nc")
    libros_docs -= {""}
    banco_docs -= {""}

    cruzan = libros_docs & banco_docs
    # un renglón queda "solo" si NINGUNO de sus documentos cruza con el otro lado
    solo_libros = [x for x in aux["detalle"] if _docs_de(x, "doc") and not (_docs_de(x, "doc") & banco_docs)]
    solo_banco = [x for x in banco["movimientos"] if _docs_de(x, "nc") and not (_docs_de(x, "nc") & libros_docs)]

    # ---- enriquecer las partidas pendientes con tipo de abono y centro de costo ----
    _cc_de = _mapa_cc_oasis(datafono.get("por_cc"))

    def _fila_pendiente(x, lado):
        deb, cred = x.get("deb", 0.0), x.get("cred", 0.0)
        valor = cred if lado == "banco" else deb  # en banco: consignaciones=crédito
        valor = valor or deb or cred
        oasis = x.get("oasis", "")
        cc_cod, cc_nom = _cc_de(oasis) if oasis else ("", "")
        docs = x.get("docs") or ([x.get("nc")] if x.get("nc") else [x.get("doc")])
        return {
            "documento": ", ".join(d for d in docs if d),
            "tipo": x.get("tipo", ""),
            "centro_costo": cc_cod,
            "punto": oasis or cc_nom,
            "fecha": x.get("fecha", ""),
            "detalle": x.get("detalle", ""),
            "valor": round(valor, 2),
        }

    pend_banco = [_fila_pendiente(x, "banco") for x in solo_banco]
    pend_libros = [_fila_pendiente(x, "libros") for x in solo_libros]

    # ---- CONSIGNACIONES EN TRÁNSITO: lo que quedó en LIBROS y entra el mes
    # siguiente (consignaciones/datáfonos de los últimos días), acumulando de la
    # fecha más reciente hacia atrás hasta cubrir el monto del tránsito. Cada
    # documento se enriquece con tipo y centro de costo cruzando con el reporte. ----
    def _dkey(f):
        m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", str(f or ""))
        if m:  # DD/MM/AAAA
            return (m.group(3), m.group(2).zfill(2), m.group(1).zfill(2))
        return (str(f or ""),)

    bidx = {}
    for m in banco["movimientos"]:
        for d in (m.get("docs") or ([m.get("nc")] if m.get("nc") else [])):
            if d and d not in bidx:
                bidx[d] = m
    consig_libros = [x for x in aux["detalle"] if x.get("deb", 0) > 0]
    consig_libros.sort(key=lambda x: (_dkey(x.get("fecha", "")), x.get("deb", 0)),
                       reverse=True)
    pend_transito, acc_tr = [], 0.0
    meta_tr = round(float(transito), 2)
    for x in consig_libros:
        docs = x.get("docs") or ([x.get("doc")] if x.get("doc") else [])
        mb = None
        for d in docs:
            if d in bidx:
                mb = bidx[d]
                break
        oasis = (mb or {}).get("oasis", "")
        cc_cod, cc_nom = _cc_de(oasis) if oasis else ("", "")
        val = round(x.get("deb", 0.0), 2)
        pend_transito.append({
            "documento": ", ".join(d for d in docs if d),
            "tipo": (mb or {}).get("tipo", "CONSIGNACION"),
            "centro_costo": cc_cod, "punto": oasis or cc_nom,
            "fecha": x.get("fecha", ""), "detalle": x.get("detalle", ""),
            "valor": val})
        acc_tr += val
        if meta_tr and acc_tr >= meta_tr:
            break

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
        "solo_libros": solo_libros,
        "solo_banco": solo_banco,
        "pend_banco": pend_banco,
        "pend_libros": pend_libros,
        "pend_transito": pend_transito,
        "transito_detalle_total": round(acc_tr, 2),
        "datafono_cc": datafono["por_cc"],
    }


# ===========================================================================
# Exportación a Excel con el ESTILO y las FÓRMULAS de la plantilla de la empresa
# ===========================================================================
_FMT_PESO = '_([$$-240A]\\ * #,##0.00_);_([$$-240A]\\ * \\(#,##0.00\\);_([$$-240A]\\ * "-"??_);_(@_)'
_FMT_NUM = '_(* #,##0.00_);_(* \\(#,##0.00\\);_(* "-"??_);_(@_)'


def exportar_excel(r, nombre_banco="", cuenta="", periodo="", empresa="",
                   elaborado_por="") -> bytes:
    """Arma el archivo de conciliación con el mismo estilo y fórmulas de la
    plantilla de la empresa:
      · Cabecera (empresa / banco / cuenta / periodo).
      · Cuadro: SALDO EN LIBROS + CONSIGNACIONES − PAGOS − NOTAS DÉBITO (con su
        desglose) = SALDO A CIERRE − CONSIGNACIONES EN TRÁNSITO = SALDO EXTRACTO,
        con las sumas puestas como FÓRMULAS.
      · Secciones de partidas pendientes DETALLADAS por documento, tipo de abono
        (datáfono / consignación / transferencia / …), centro de costo y valor.
      · Hoja aparte con el datáfono por centro de costo.
    Devuelve los bytes del .xlsx."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Conciliacion"

    azul = PatternFill("solid", fgColor="1F4E78")
    gris = PatternFill("solid", fgColor="D9E1F2")
    gris2 = PatternFill("solid", fgColor="F2F2F2")
    amar = PatternFill("solid", fgColor="FFF2CC")
    verde = PatternFill("solid", fgColor="E2EFDA")
    b_tit = Font(bold=True, color="FFFFFF", size=11)
    b_bold = Font(bold=True, size=10)
    b_norm = Font(size=10)
    thin = Side(style="thin", color="BFBFBF")
    borde = Border(left=thin, right=thin, top=thin, bottom=thin)
    right = Alignment(horizontal="right")
    center = Alignment(horizontal="center")

    for col, w in zip("ABCDEF", (3, 34, 16, 20, 18, 15)):
        ws.column_dimensions[col].width = w
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    from openpyxl.worksheet.properties import PageSetupProperties
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

    def celda(coord, val, font=None, fill=None, fmt=None, align=None, bordear=False):
        c = ws[coord]
        c.value = val
        if font: c.font = font
        if fill: c.fill = fill
        if fmt: c.number_format = fmt
        if align: c.alignment = align
        if bordear: c.border = borde
        return c

    # ---------- cabecera ----------
    ws.merge_cells("B2:F2"); celda("B2", (empresa or "").upper(), b_tit, azul, align=center)
    ws.merge_cells("B3:F3"); celda("B3", "CONCILIACIÓN BANCARIA", b_bold, gris, align=center)
    ws.merge_cells("B4:F4"); celda("B4", nombre_banco.upper(), b_bold, gris, align=center)
    ws.merge_cells("B5:F5"); celda("B5", f"CUENTA {cuenta}".strip(), b_norm, align=center)
    ws.merge_cells("B6:F6"); celda("B6", (periodo or "").upper(), b_bold, gris, align=center)

    # ---------- cuadro ----------
    fila = 8
    celda(f"B{fila}", "SALDO EN LIBROS", b_bold); celda(f"E{fila}", r["saldo_ant"], b_bold, fmt=_FMT_PESO); f_sl = fila; fila += 1
    celda(f"B{fila}", "(+) CONSIGNACIONES", b_norm); celda(f"E{fila}", r["consignaciones"], b_norm, fmt=_FMT_PESO); f_con = fila; fila += 1
    celda(f"B{fila}", "(−) PAGOS", b_norm); celda(f"E{fila}", -r["pagos"], b_norm, fmt=_FMT_PESO); f_pag = fila; fila += 1
    # notas débito con desglose
    celda(f"B{fila}", "(−) NOTAS DÉBITO", b_bold)
    f_nd = fila; fila += 1
    desglose = [
        ("Gasto bancario", r["gasto_bancario"]),
        ("Comisiones", r["comisiones"]),
        ("Comisión datáfono", r["comision_datafono"]),
        ("IVA", r["iva"]),
        ("G.M.F.", r["gmf"]),
        ("ReteIVA", r["reteiva"]),
        ("Retefuente", r["retefuente"]),
        ("ReteICA", r["reteica"]),
    ]
    f_desg0 = fila
    for et, v in desglose:
        celda(f"B{fila}", "        " + et, b_norm)
        celda(f"D{fila}", v, b_norm, fmt=_FMT_NUM)
        fila += 1
    f_desg1 = fila - 1
    # E de notas débito = -SUM(desglose)
    ws[f"E{f_nd}"] = f"=-SUM(D{f_desg0}:D{f_desg1})"
    ws[f"E{f_nd}"].font = b_bold; ws[f"E{f_nd}"].number_format = _FMT_PESO
    fila += 1
    celda(f"B{fila}", "(=) SALDO EN LIBROS A FECHA DE CIERRE", b_bold, verde)
    ws[f"E{fila}"] = f"=E{f_sl}+E{f_con}+E{f_pag}+E{f_nd}"
    ws[f"E{fila}"].font = b_bold; ws[f"E{fila}"].number_format = _FMT_PESO; ws[f"E{fila}"].fill = verde
    f_cierre = fila; fila += 1

    celda(f"B{fila}", "(−) CONSIGNACIONES EN TRÁNSITO", b_bold, amar)
    celda(f"E{fila}", -r["consignaciones_transito"], b_bold, amar, fmt=_FMT_PESO)
    f_tr = fila; fila += 1

    celda(f"B{fila}", "(=) SALDO SEGÚN EXTRACTO DEL BANCO", b_bold, verde)
    ws[f"E{fila}"] = f"=E{f_cierre}+E{f_tr}"
    ws[f"E{fila}"].font = b_bold; ws[f"E{fila}"].number_format = _FMT_PESO; ws[f"E{fila}"].fill = verde
    f_ext = fila; fila += 1
    celda(f"B{fila}", "SALDO REAL DEL EXTRACTO", b_norm)
    celda(f"E{fila}", r["saldo_banco"], b_norm, fmt=_FMT_PESO); f_real = fila; fila += 1
    celda(f"B{fila}", "DIFERENCIA", b_bold)
    ws[f"E{fila}"] = f"=E{f_ext}-E{f_real}"
    ws[f"E{fila}"].font = b_bold; ws[f"E{fila}"].number_format = _FMT_PESO
    fila += 1
    if abs(r.get("ajuste_al_peso", 0)) > 0:
        celda(f"B{fila}", f"* Ajuste al peso incluido en gasto bancario: {r['ajuste_al_peso']:,.2f}",
              Font(italic=True, size=9)); fila += 1
    fila += 1

    # ---------- detalle de partidas pendientes ----------
    def _seccion(titulo, filas, tipo_def=""):
        nonlocal fila
        celda(f"B{fila}", titulo, b_bold, gris); fila += 1
        celda(f"B{fila}", "DOCUMENTO", b_bold, gris2, bordear=True)
        celda(f"C{fila}", "TIPO DE ABONO", b_bold, gris2, bordear=True)
        celda(f"D{fila}", "CENTRO DE COSTO", b_bold, gris2, bordear=True)
        celda(f"E{fila}", "FECHA", b_bold, gris2, bordear=True, align=center)
        celda(f"F{fila}", "VALOR", b_bold, gris2, bordear=True, align=center)
        fila += 1
        ini = fila
        for p in filas:
            celda(f"B{fila}", p["documento"], b_norm, bordear=True)
            celda(f"C{fila}", p["tipo"] or tipo_def, b_norm, bordear=True)
            cc_txt = (f'{p["centro_costo"]} — ' if p.get("centro_costo") else "") + (p.get("punto") or "")
            celda(f"D{fila}", cc_txt.strip(" —"), b_norm, bordear=True)
            celda(f"E{fila}", p["fecha"], b_norm, bordear=True, align=center)
            celda(f"F{fila}", p["valor"], b_norm, fmt=_FMT_NUM, bordear=True)
            fila += 1
        celda(f"B{fila}", "TOTAL", b_bold, gris2, bordear=True)
        c = ws[f"F{fila}"]
        c.value = f"=SUM(F{ini}:F{fila-1})" if filas else 0
        c.font = b_bold; c.number_format = _FMT_NUM; c.fill = gris2; c.border = borde
        fila += 2

    _seccion("CONSIGNACIONES EN TRÁNSITO — detalle (lo que quedó en libros y entra "
             "el mes siguiente: consignación / datáfono / etc.)", r.get("pend_transito", []))
    if r.get("pend_libros"):
        _seccion("PAGOS EN LIBROS QUE NO SALIERON DEL BANCO", r.get("pend_libros", []), "PAGO")

    # ---------- pie ----------
    if elaborado_por:
        celda(f"B{fila}", "ELABORADO POR:", b_bold); fila += 1
        celda(f"B{fila}", elaborado_por, b_norm); fila += 1

    # ---------- hoja: datáfono por centro de costo ----------
    if r.get("datafono_cc"):
        ws2 = wb.create_sheet("Datafono por CC")
        enc = ["Centro de costo", "Punto / OASIS", "Comisión", "Retefuente", "ReteIVA", "ReteICA"]
        for j, e in enumerate(enc, start=1):
            c = ws2.cell(row=1, column=j, value=e); c.font = b_tit; c.fill = azul; c.alignment = center
        for i, d in enumerate(r["datafono_cc"], start=2):
            ws2.cell(row=i, column=1, value=d.get("cc", ""))
            ws2.cell(row=i, column=2, value=d.get("oasis", ""))
            for j, k in enumerate(["comision", "retefuente", "reteiva", "reteica"], start=3):
                cc = ws2.cell(row=i, column=j, value=d.get(k, 0)); cc.number_format = _FMT_NUM
        for col, w in zip("ABCDEF", (16, 26, 16, 16, 16, 16)):
            ws2.column_dimensions[col].width = w

    ws.sheet_view.showGridLines = False
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ===========================================================================
# PLANO DE GASTOS para Contai (reparto igual + datáfono por centro de costo)
# ===========================================================================
HDR_PLANO = ["CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
             "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO"]

# cuentas del DATÁFONO (de la macro Credibanco) y sus divisores de base
CUENTAS_DATAFONO = {"comision": "53051501", "retefuente": "19551507",
                    "reteiva": "24082505", "reteica": "52150502"}
DIV_DATAFONO = {"retefuente": 0.015, "reteiva": 0.15, "reteica": 0.009}
NIT_DATAFONO = "890903938"

# cuentas de GASTOS BANCARIOS por defecto (config de «Bancos a Contai» de LOLITA)
CUENTAS_GASTO_DEF = {"gasto_bancario": "53050501", "comisiones": "53051501",
                     "iva": "24081009", "gmf": "53050601"}


def cuentas_gasto_desde_reglas(reglas) -> dict:
    """Deduce las cuentas de gastos bancarios desde las reglas de «Bancos a
    Contai» (por su etiqueta/cuenta). Cae a las de LOLITA si no encuentra."""
    m = dict(CUENTAS_GASTO_DEF)
    for rg in reglas or []:
        etq = str(rg.get("etiqueta") or "").upper()
        ct = str(rg.get("cuenta") or "").strip()
        if not ct:
            continue
        if "GASTO" in etq:
            m["gasto_bancario"] = ct
        elif "COMIS" in etq:
            m["comisiones"] = ct
        elif "IVA" in etq:
            m["iva"] = ct
        elif "GMF" in etq or "GRAVAMEN" in etq or "4X1" in etq:
            m["gmf"] = ct
    return m


def _repartir(total: float, n: int) -> list:
    """Divide en n partes iguales (2 decimales); el residuo va al último."""
    t = round(total, 2)
    base = round(t / n, 2)
    partes = [base] * n
    partes[-1] = round(t - base * (n - 1), 2)
    return partes


def generar_plano_gastos(r, centros, cuenta_puc, cuentas_gasto=None,
                         comprobante="10", documento="1", fecha=None,
                         detalle="CONCILIACION BANCARIA",
                         nit_datafono=NIT_DATAFONO, nit_banco=None,
                         cuentas_datafono=None, divisores=None):
    """Arma el plano de Contai de los GASTOS de la conciliación:
      · Gastos bancarios (gasto bancario, comisiones, IVA, GMF) → repartidos en
        PARTES IGUALES entre `centros`.
      · Datáfono Credibanco (comisión, retefuente, reteIVA, reteICA) → por CENTRO
        DE COSTO según la tabla de establecimientos (r['datafono_cc']), con las
        cuentas de la macro y base = valor / divisor.
      · Contrapartida: el total al débito se acredita contra `cuenta_puc` (la
        cuenta puente del banco).
    Devuelve {filas, debitos, creditos, cuadra, n}."""
    import datetime
    if not fecha:
        fecha = datetime.date.today().strftime("%m/%d/%Y")
    cuentas_gasto = cuentas_gasto or CUENTAS_GASTO_DEF
    cuentas_df = cuentas_datafono or CUENTAS_DATAFONO
    divs = divisores or DIV_DATAFONO
    nit_banco = nit_banco or nit_datafono
    centros = [str(c).strip() for c in (centros or []) if str(c).strip()] or ["001001"]

    filas = [list(HDR_PLANO)]

    def add(cta, nit, tr, valor, base, cc):
        filas.append([str(cta), str(comprobante), fecha, str(documento), str(documento),
                      str(nit), detalle, str(tr), f"{round(valor, 2):.2f}",
                      f"{round(base, 2):.2f}", str(cc)])

    tot_deb = 0.0
    # 1) gastos bancarios en partes iguales
    for cta, total in [(cuentas_gasto["gasto_bancario"], r.get("gasto_bancario", 0)),
                       (cuentas_gasto["comisiones"], r.get("comisiones", 0)),
                       (cuentas_gasto["iva"], r.get("iva", 0)),
                       (cuentas_gasto["gmf"], r.get("gmf", 0))]:
        if round(float(total or 0), 2) == 0:
            continue
        for cc, val in zip(centros, _repartir(float(total), len(centros))):
            if round(val, 2) == 0:
                continue
            add(cta, nit_banco, 1, val, 0, cc)
            tot_deb += val
    # 2) datáfono por centro de costo
    for d in r.get("datafono_cc", []):
        cc = str(d.get("cc") or "").strip()
        for key, cta in [("comision", cuentas_df["comision"]),
                         ("retefuente", cuentas_df["retefuente"]),
                         ("reteiva", cuentas_df["reteiva"]),
                         ("reteica", cuentas_df["reteica"])]:
            v = round(float(d.get(key, 0) or 0), 2)
            if v == 0:
                continue
            div = divs.get(key)
            base = round(v / div, 2) if div else 0
            add(cta, nit_datafono, 1, v, base, cc)
            tot_deb += v
    # 3) contrapartida contra la cuenta puente del banco
    tot_deb = round(tot_deb, 2)
    if tot_deb:
        add(cuenta_puc, nit_banco, 2, tot_deb, 0, "")
    return {"filas": filas, "debitos": tot_deb, "creditos": tot_deb,
            "cuadra": True, "n": len(filas) - 1}


def plano_a_texto(filas) -> str:
    """Convierte las filas del plano a texto tabulado (formato Contai)."""
    return "\r\n".join("\t".join(str(c) for c in fila) for fila in filas) + "\r\n"


# ===========================================================================
# PDF de la conciliación con la firma del software que lo generó
# ===========================================================================
def exportar_pdf(r, nombre_banco="", cuenta="", periodo="", empresa="",
                 usuario="") -> bytes:
    """Genera el PDF de la conciliación (cuadro + partidas pendientes detalladas
    por documento, tipo de abono y centro de costo), con el pie de firma del
    software que lo generó (INTEGRAL · fecha y hora)."""
    import datetime
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                    Spacer)

    def money(v):
        v = float(v or 0)
        return f"$ ({abs(v):,.2f})" if v < 0 else f"$ {v:,.2f}"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(letter),
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=16 * mm,
                            title="Conciliación bancaria")
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Title"], fontSize=13, spaceAfter=2,
                       textColor=colors.HexColor("#1F4E78"))
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9.5,
                         textColor=colors.HexColor("#333333"))
    sec = ParagraphStyle("sec", parent=styles["Heading4"], fontSize=10,
                         textColor=colors.HexColor("#1F4E78"), spaceBefore=8, spaceAfter=3)
    el = []
    el.append(Paragraph((empresa or "").upper(), h))
    el.append(Paragraph(f"CONCILIACIÓN BANCARIA · {nombre_banco} · cuenta {cuenta}", sub))
    if periodo:
        el.append(Paragraph(f"Periodo: {periodo}", sub))
    el.append(Spacer(1, 6))

    cuadro = [
        ["SALDO EN LIBROS", money(r["saldo_ant"])],
        ["(+) CONSIGNACIONES", money(r["consignaciones"])],
        ["(−) PAGOS", money(-r["pagos"])],
        ["(−) NOTAS DÉBITO", money(-r["notas_debito"])],
        ["        Gasto bancario", money(-r["gasto_bancario"])],
        ["        Comisiones", money(-r["comisiones"])],
        ["        Comisión datáfono", money(-r["comision_datafono"])],
        ["        IVA", money(-r["iva"])],
        ["        G.M.F.", money(-r["gmf"])],
        ["        ReteIVA", money(-r["reteiva"])],
        ["        Retefuente", money(-r["retefuente"])],
        ["        ReteICA", money(-r["reteica"])],
        ["(=) SALDO EN LIBROS A FECHA DE CIERRE", money(r["saldo_cierre"])],
        ["(−) CONSIGNACIONES EN TRÁNSITO", money(-r["consignaciones_transito"])],
        ["(=) SALDO SEGÚN EXTRACTO DEL BANCO", money(r["saldo_banco"])],
    ]
    t = Table(cuadro, colWidths=[110 * mm, 60 * mm])
    resalta = {0, 3, 12, 13, 14}
    ts = [("FONTSIZE", (0, 0), (-1, -1), 9),
          ("ALIGN", (1, 0), (1, -1), "RIGHT"),
          ("LINEBELOW", (0, -1), (-1, -1), 0.6, colors.HexColor("#1F4E78")),
          ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    for i in resalta:
        ts.append(("FONTNAME", (0, i), (-1, i), "Helvetica-Bold"))
    ts.append(("BACKGROUND", (0, 12), (-1, 12), colors.HexColor("#E2EFDA")))
    ts.append(("BACKGROUND", (0, 13), (-1, 13), colors.HexColor("#FFF2CC")))
    ts.append(("BACKGROUND", (0, 14), (-1, 14), colors.HexColor("#E2EFDA")))
    t.setStyle(TableStyle(ts))
    el.append(t)
    if abs(r.get("ajuste_al_peso", 0)) > 0:
        el.append(Paragraph(f"* Ajuste al peso incluido en gasto bancario: "
                            f"{r['ajuste_al_peso']:,.2f}", sub))

    def tabla_pend(titulo, filas):
        if not filas:
            return
        el.append(Paragraph(titulo, sec))
        data = [["DOCUMENTO", "TIPO DE ABONO", "CENTRO DE COSTO", "FECHA", "VALOR"]]
        tot = 0.0
        for p in filas:
            cc = (f'{p["centro_costo"]} — ' if p.get("centro_costo") else "") + (p.get("punto") or "")
            data.append([p["documento"], p["tipo"], cc.strip(" —"), p["fecha"],
                         f'{p["valor"]:,.2f}'])
            tot += p["valor"]
        data.append(["", "", "", "TOTAL", f"{tot:,.2f}"])
        tt = Table(data, colWidths=[42 * mm, 45 * mm, 60 * mm, 30 * mm, 35 * mm], repeatRows=1)
        tt.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("ALIGN", (4, 1), (4, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F2F2F2")]),
        ]))
        el.append(tt)

    tabla_pend("CONSIGNACIONES EN TRÁNSITO — detalle (lo que quedó en libros y entra "
               "el mes siguiente: consignación / datáfono / etc.)", r.get("pend_transito", []))
    tabla_pend("PAGOS EN LIBROS QUE NO SALIERON DEL BANCO", r.get("pend_libros", []))

    ahora = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    firma = (f"Documento generado por INTEGRAL — Plataforma Contable · {ahora}"
             + (f" · {usuario}" if usuario else "")
             + (f" · {empresa}" if empresa else ""))
    pie = ParagraphStyle("pie", parent=styles["Normal"], fontSize=7.5,
                         textColor=colors.HexColor("#888888"))

    def _foot(canvas, docu):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#CCCCCC"))
        w, _h = landscape(letter)
        canvas.line(14 * mm, 12 * mm, w - 14 * mm, 12 * mm)
        canvas.setFont("Helvetica-Oblique", 7.5)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.drawString(14 * mm, 8 * mm, firma)
        canvas.drawRightString(w - 14 * mm, 8 * mm, f"Página {docu.page}")
        canvas.restoreState()

    el.append(Spacer(1, 6))
    doc.build(el, onFirstPage=_foot, onLaterPages=_foot)
    return buf.getvalue()


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
