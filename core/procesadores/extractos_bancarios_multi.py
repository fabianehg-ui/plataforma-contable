# -*- coding: utf-8 -*-
"""
core/procesadores/extractos_bancarios_multi.py

Procesa extractos bancarios en PDF y arma el plano de Contai con los GASTOS e
INGRESOS bancarios, repartidos en PARTES IGUALES entre los centros de costo que
elija el usuario, con la CONTRAPARTIDA contra la cuenta PUC del banco.

Es CONFIG-DRIVEN (multiempresa): los bancos, las reglas de clasificación y los
centros de costo se definen POR EMPRESA (tablas bancos_config / bancos_reglas /
bancos_cc, migración 020) y se editan desde la plataforma.

Un "banco" de la config tiene:
    nombre      -> etiqueta (p.ej. "DAVIVIENDA 7872")
    detectar    -> texto que identifica el extracto (p.ej. "03986999 7872")
    formato     -> parser a usar (davivienda / occidente / bancolombia_cta /
                   bancolombia_ahorro / fidu_davivienda / fidu_bancolombia /
                   bogota / bbva)
    nit         -> NIT del banco
    cuenta_puc  -> cuenta del banco en el PUC (la contrapartida)

Una "regla" (lista blanca) tiene:
    patron  -> regex sobre la descripción del movimiento
    cuenta  -> cuenta PUC del concepto
    lado    -> 'D' gasto (débito concepto, crédito banco) |
               'C' ingreso (débito banco, crédito concepto) |
               'R' retención (débito concepto, crédito banco)  [= como D]
    base    -> True si la cuenta lleva base gravable (IVA) en la columna BASE

Solo se contabilizan los movimientos que casan con alguna regla; el resto
(nómina, proveedores, cuotas de crédito, consignaciones, traslados) queda FUERA
del plano a propósito.
"""
from __future__ import annotations

import re
from collections import defaultdict

try:
    import pdfplumber
except Exception:  # noqa: BLE001
    pdfplumber = None


# ===========================================================================
# Lectura del PDF
# ===========================================================================
def _normaliza(t: str) -> str:
    t = t.replace("\t", " ").replace("\r", "\n")
    return re.sub(r"[ ]{2,}", " ", t)


def texto_pdf(archivo) -> str:
    partes = []
    with pdfplumber.open(archivo) as pdf:
        for pg in pdf.pages:
            partes.append(pg.extract_text() or "")
    return _normaliza("\n".join(partes))


def _num(s: str) -> float:
    """Convierte '1,234.56' o '1.234,56' a float."""
    s = str(s).strip().replace("$", "").replace(" ", "")
    if not s:
        return 0.0
    # formato colombiano con coma decimal: 1.234,56
    if re.search(r"\d\.\d{3},\d", s) or (s.count(",") == 1 and s.count(".") >= 1 and s.rfind(",") > s.rfind(".")):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return abs(float(s))
    except ValueError:
        return 0.0


# ===========================================================================
# Parsers por formato -> lista de {desc, valor, debito}
#   debito=True  -> salió plata del banco (candidato a GASTO / retención)
#   debito=False -> entró plata al banco  (candidato a INGRESO)
# ===========================================================================
def parse_occidente(texto: str):
    """DIA DESC [IDENT] DEBITOS CREDITOS SALDO."""
    movs = []
    pat = re.compile(r"^(\d{1,2})\s+(.+?)\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+[\d,]+\.\d{2}\s*$")
    for l in texto.split("\n"):
        m = pat.match(l.strip())
        if not m:
            continue
        desc = re.sub(r"\s+[A-Z]?\d{5,}\s*$", "", m.group(2)).strip()  # quitar IDENT final
        deb, cred = _num(m.group(3)), _num(m.group(4))
        if deb > 0:
            movs.append({"desc": desc, "valor": deb, "debito": True})
        elif cred > 0:
            movs.append({"desc": desc, "valor": cred, "debito": False})
    return movs


def parse_davivienda(texto: str):
    """DD MM DESC OFICINA DOC $VALOR(+/-) $SALDO(+/-). El signo del VALOR manda."""
    movs = []
    pat = re.compile(r"^(\d{2})\s+(\d{2})\s+(.+?)\s+\$([\d,]+\.\d{2})([+-])\s+\$[\d,]+\.\d{2}[+-]")
    for l in texto.split("\n"):
        m = pat.match(l.strip())
        if not m:
            continue
        # la descripción es todo lo previo al valor; quitar oficina/doc de la cola
        desc = m.group(3).strip()
        desc = re.sub(r"\s+\d{3,4}$", "", desc).strip()      # doc
        val = _num(m.group(4))
        movs.append({"desc": desc, "valor": val, "debito": m.group(5) == "-"})
    return movs


def parse_bancolombia_ahorro(texto: str):
    """DD/MM DESCRIPCIÓN [SUCURSAL] [DCTO] VALOR SALDO. En ahorros los ABONOS
    (intereses) entran; los cargos salen. Se distingue por palabra clave en la
    descripción (ABONO/INTERES = ingreso)."""
    movs = []
    pat = re.compile(r"^(\d{2}/\d{2})\s+(.+?)\s+([\d,]+\.\d{2}|\.\d{2}|[\d,]+)\s+([\d,]+\.\d{2}|\.\d{2})\s*$")
    for l in texto.split("\n"):
        m = pat.match(l.strip())
        if not m:
            continue
        desc = m.group(2).strip()
        val = _num(m.group(3))
        if val == 0:
            continue
        es_ing = bool(re.search(r"ABONO|INTERES|RENDIMIEN", desc, re.I))
        movs.append({"desc": desc, "valor": val, "debito": not es_ing})
    return movs


def parse_bancolombia_cta(texto: str):
    """Cuenta corriente Bancolombia: fecha DESC -valor saldo (cargos negativos)."""
    movs = []
    pat = re.compile(r"(\d{1,2}/\d{2})\s+(.+?)\s+(-?[\d,]+\.\d{2})\s+(-?[\d,]+\.\d{2})(?!\d)")
    for m in re.finditer(pat, texto):
        desc = m.group(2).strip()
        val = _num(m.group(3))
        deb = m.group(3).strip().startswith("-")
        movs.append({"desc": desc, "valor": val, "debito": deb})
    return movs


def _buscar_valor(texto: str, etiqueta_regex: str):
    """Devuelve el primer valor numérico que sigue a una etiqueta."""
    m = re.search(etiqueta_regex + r"[^\d\-]*([\d\.,]+)", texto, re.I)
    return _num(m.group(1)) if m else 0.0


def parse_fidu_davivienda(texto: str):
    """Fiducuenta Davivienda (resumen). Rendimientos abonados = ingreso;
    comisión de administración = gasto; retención en la fuente = retención;
    GMF = gasto."""
    movs = []
    rend = _buscar_valor(texto, r"Rendimientos abonados")
    if rend:
        movs.append({"desc": "RENDIMIENTOS ABONADOS", "valor": rend, "debito": False})
    # comisión de administración: el "Valor Periodo" en la línea 'S4 1.80 639.15 ...'
    mcom = re.search(r"COMISI[ÓO]N DE ADMINISTRACI[ÓO]N.*?\n.*?\n\s*\S+\s+[\d.]+\s+([\d.,]+)", texto, re.I | re.S)
    com = _num(mcom.group(1)) if mcom else _buscar_valor(texto, r"Comisi[óo]n administraci[óo]n")
    if com:
        movs.append({"desc": "COMISION ADMINISTRACION FIDUCUENTA", "valor": com, "debito": True})
    ret = _buscar_valor(texto, r"Retenci[óo]n en la fuente")
    if ret:
        movs.append({"desc": "RETENCION EN LA FUENTE RENDIMIENTOS", "valor": ret, "debito": True})
    gmf = _buscar_valor(texto, r"Gravamen a movimientos financieros")
    if gmf:
        movs.append({"desc": "GMF FIDUCUENTA", "valor": gmf, "debito": True})
    comret = _buscar_valor(texto, r"Comisi[óo]n retiro")
    if comret:
        movs.append({"desc": "COMISION RETIRO FIDUCUENTA", "valor": comret, "debito": True})
    return movs


def parse_fidu_bancolombia(texto: str):
    """Fiducuenta Bancolombia (resumen). REND. NETOS = ingreso;
    RETENCIÓN / RETEFTE = retención."""
    movs = []
    # bloque resumen: 'REND. NETOS RETENCIÓN NUEVO SALDO' seguido de los valores
    mres = re.search(r"REND\.?\s*NETOS\s+RETENCI[ÓO]N\s+NUEVO SALDO.*?\n([\d\.,]+)\s+([\d\.,]+)", texto, re.I | re.S)
    if mres:
        rend = _num(mres.group(1))
        ret = _num(mres.group(2))
        if rend:
            movs.append({"desc": "RENDIMIENTOS NETOS FIDUCUENTA", "valor": rend, "debito": False})
        if ret:
            movs.append({"desc": "RETEFUENTE RENDIMIENTOS FIDUCUENTA", "valor": ret, "debito": True})
    else:
        # sumar las líneas RETEFTE
        ret = sum(_num(x) for x in re.findall(r"RETEFTE\s+([\d\.,]+)", texto, re.I))
        if ret:
            movs.append({"desc": "RETEFUENTE RENDIMIENTOS FIDUCUENTA", "valor": ret, "debito": True})
    return movs


PARSERS = {
    "occidente": parse_occidente,
    "davivienda": parse_davivienda,
    "bancolombia_ahorro": parse_bancolombia_ahorro,
    "bancolombia_cta": parse_bancolombia_cta,
    "fidu_davivienda": parse_fidu_davivienda,
    "fidu_bancolombia": parse_fidu_bancolombia,
}


# ===========================================================================
# Clasificación (config-driven) y armado del plano
# ===========================================================================
def clasificar(desc: str, reglas: list):
    """Devuelve (cuenta, lado, base, etiqueta) de la primera regla que casa."""
    for r in reglas:
        if re.search(r["patron"], desc, re.I):
            return r["cuenta"], r.get("lado", "D"), bool(r.get("base")), r.get("etiqueta", "")
    return None, None, False, None


def leer_extracto(archivo, bancos: list, reglas: list) -> dict:
    """Detecta el banco por su 'detectar', parsea y clasifica los movimientos."""
    texto = texto_pdf(archivo)
    banco = None
    for b in bancos:
        clave = str(b.get("detectar") or "").strip()
        if clave and clave in texto:
            banco = b
            break
    if not banco:
        return {"banco": None, "movimientos": [], "sin_clasificar": 0}
    parser = PARSERS.get(banco.get("formato"))
    if not parser:
        return {"banco": banco, "movimientos": [], "sin_clasificar": 0, "error": "formato sin parser"}
    crudos = parser(texto)
    movs, sin = [], 0
    for mv in crudos:
        cta, lado, base, etq = clasificar(mv["desc"], reglas)
        if not cta:
            sin += 1
            continue
        # coherencia: un gasto debería ser débito; un ingreso, crédito. Se respeta
        # el 'lado' de la regla (la regla manda el asiento).
        movs.append({"banco": banco["nombre"], "descripcion": mv["desc"],
                     "valor": round(mv["valor"], 2), "cuenta": cta, "lado": lado,
                     "base": base, "detalle": etq or mv["desc"][:40]})
    return {"banco": banco, "movimientos": movs, "sin_clasificar": sin}


def resumen(movimientos: list) -> dict:
    """{banco: {(cuenta,lado): valor}}."""
    r = defaultdict(lambda: defaultdict(float))
    for m in movimientos:
        r[m["banco"]][(m["cuenta"], m["lado"])] += m["valor"]
    return {b: dict(c) for b, c in r.items()}


HDR = ["CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
       "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO"]


def _repartir(total: float, n: int) -> list:
    """Divide en n partes iguales (2 decimales); el residuo va al último centro."""
    t = round(total, 2)
    base = round(t / n, 2)
    partes = [base] * n
    partes[-1] = round(t - base * (n - 1), 2)
    return partes


def build_plano(movimientos: list, bancos: list, centros: list, reglas: list,
                comprobante="10", documento="1", fecha="07/31/2026",
                divisor_iva=0.19) -> dict:
    """Arma el plano: conceptos repartidos por CC, contrapartida a la cuenta del
    banco. Gasto/retención (lado D): concepto DÉBITO, banco CRÉDITO. Ingreso
    (lado C): concepto CRÉDITO, banco DÉBITO. Cada banco cuadra por su cuenta."""
    nit = {b["nombre"]: str(b.get("nit") or "") for b in bancos}
    puc = {b["nombre"]: str(b.get("cuenta_puc") or "") for b in bancos}
    detalle = {}
    base_de = {}
    for m in movimientos:
        detalle[(m["cuenta"], m["lado"])] = m["detalle"]
        base_de[(m["cuenta"], m["lado"])] = m["base"]

    res = resumen(movimientos)
    n = len(centros)
    L = [HDR]
    total_db = total_cr = 0.0
    for banco, conc in res.items():
        neto_banco = 0.0  # + si el banco queda debitado (ingresos), - si creditado (gastos)
        for (cta, lado), val in sorted(conc.items()):
            if round(val, 2) == 0:
                continue
            tr_concepto = "1" if lado in ("D", "R") else "2"
            vals = _repartir(val, n)
            bases = _repartir(round(val / divisor_iva, 2), n) if base_de.get((cta, lado)) else [None] * n
            for cc, v, b in zip(centros, vals, bases):
                L.append([cta, comprobante, fecha, documento, documento, nit.get(banco, ""),
                          f"{detalle[(cta, lado)]} {banco}", tr_concepto, v,
                          (b if b else ""), cc])
                if tr_concepto == "1":
                    total_db += v
                else:
                    total_cr += v
            neto_banco += (-val) if lado in ("D", "R") else (val)
        # contrapartida banco: si neto<0 va CRÉDITO (gastos), si neto>0 DÉBITO (ingresos)
        neto_banco = round(neto_banco, 2)
        if neto_banco != 0:
            if neto_banco < 0:
                L.append([puc.get(banco, ""), comprobante, fecha, documento, documento,
                          nit.get(banco, ""), f"MOVIMIENTO BANCARIO {banco}", "2",
                          round(-neto_banco, 2), "", ""])
                total_cr += round(-neto_banco, 2)
            else:
                L.append([puc.get(banco, ""), comprobante, fecha, documento, documento,
                          nit.get(banco, ""), f"MOVIMIENTO BANCARIO {banco}", "1",
                          round(neto_banco, 2), "", ""])
                total_db += round(neto_banco, 2)
    total_db = round(total_db, 2)
    total_cr = round(total_cr, 2)
    return {"filas": L, "debitos": total_db, "creditos": total_cr,
            "cuadra": abs(total_db - total_cr) < 0.01}


def plano_a_texto(filas: list) -> str:
    def fmt(x):
        if isinstance(x, float):
            return f"{x:.2f}"
        return str(x)
    return "\r\n".join("\t".join(fmt(x) for x in f) for f in filas) + "\r\n"


# ===========================================================================
# Formatos disponibles y valores por defecto
# ===========================================================================
FORMATOS = ["davivienda", "occidente", "bancolombia_cta", "bancolombia_ahorro",
            "fidu_davivienda", "fidu_bancolombia"]

LADOS = {"D": "Gasto (débito concepto / crédito banco)",
         "C": "Ingreso (débito banco / crédito concepto)",
         "R": "Retención (débito concepto / crédito banco)"}

# Reglas por defecto (lista blanca). RETENCIÓN antes que INGRESO para que
# "RETEFUENTE RENDIMIENTOS" no caiga como ingreso.
REGLAS_DEFECTO = [
    {"orden": 1, "patron": r"4X1\.?000|4 ?POR ?MIL|IMPTO GOBIERNO|\bGMF\b|GRAVAMEN",
     "cuenta": "53059501", "lado": "D", "base": False, "etiqueta": "GRAVAMEN 4X1000"},
    {"orden": 2, "patron": r"\bIVA\b", "cuenta": "53050502", "lado": "D",
     "base": True, "etiqueta": "IVA GASTOS BANCARIOS"},
    {"orden": 3, "patron": r"RETEFUENTE|RETEFTE|RETENCION",
     "cuenta": "13551501", "lado": "R", "base": False, "etiqueta": "RETEFUENTE RENDIMIENTOS"},
    {"orden": 4, "patron": r"COMISION|COMIS\b", "cuenta": "53051501", "lado": "D",
     "base": False, "etiqueta": "COMISIONES"},
    {"orden": 5, "patron": r"CUOTA ADMIN|CUOTA ?MANEJO|C ?MANEJO|CobroServicio|"
     r"MANEJO ?PORTAL|CobroTransf|CobroTransferencia|NdCobro|SERVICIO ?RECAUDO|"
     r"SERV ?TRANS|SERVICIO ADMON|SERV ADMON|CobroServicioEmpresarial",
     "cuenta": "53050501", "lado": "D", "base": False, "etiqueta": "GASTOS BANCARIOS"},
    {"orden": 6, "patron": r"RENDIMIEN|ABONO INTERES|INTERESES AHORR|INTERES\b",
     "cuenta": "42100501", "lado": "C", "base": False, "etiqueta": "INGRESOS FINANCIEROS"},
]


# ===========================================================================
# Configuración por empresa (Supabase)
# ===========================================================================
def cargar_bancos(sb, empresa_id) -> list:
    try:
        r = (sb.table("bancos_config").select("*")
             .eq("empresa_id", empresa_id).order("orden").execute())
        return [dict(x) for x in (r.data or [])]
    except Exception:  # noqa: BLE001
        return []


def guardar_bancos(sb, empresa_id, filas) -> int:
    filas = [f for f in filas if str(f.get("nombre") or "").strip()
             and str(f.get("cuenta_puc") or "").strip()]
    nombres = [str(f["nombre"]).strip() for f in filas]
    actuales = {b["nombre"]: b for b in cargar_bancos(sb, empresa_id)}
    for nom in actuales:
        if nom not in nombres:
            sb.table("bancos_config").delete().eq("empresa_id", empresa_id).eq("nombre", nom).execute()
    payload = []
    for i, f in enumerate(filas):
        payload.append({
            "empresa_id": empresa_id, "nombre": str(f["nombre"]).strip(),
            "detectar": str(f.get("detectar") or "").strip(),
            "formato": str(f.get("formato") or "").strip(),
            "nit": str(f.get("nit") or "").strip(),
            "cuenta_puc": str(f.get("cuenta_puc") or "").strip(), "orden": i,
        })
    if payload:
        sb.table("bancos_config").upsert(payload, on_conflict="empresa_id,nombre").execute()
    return len(payload)


def cargar_reglas(sb, empresa_id) -> list:
    try:
        r = (sb.table("bancos_reglas").select("*")
             .eq("empresa_id", empresa_id).order("orden").execute())
        return [dict(x) for x in (r.data or [])]
    except Exception:  # noqa: BLE001
        return []


def guardar_reglas(sb, empresa_id, filas) -> int:
    filas = [f for f in filas if str(f.get("patron") or "").strip()
             and str(f.get("cuenta") or "").strip()]
    sb.table("bancos_reglas").delete().eq("empresa_id", empresa_id).execute()
    payload = []
    for i, f in enumerate(filas):
        payload.append({
            "empresa_id": empresa_id, "orden": i,
            "patron": str(f["patron"]).strip(), "cuenta": str(f["cuenta"]).strip(),
            "lado": (str(f.get("lado") or "D").strip().upper() or "D")[:1],
            "base": bool(f.get("base")), "etiqueta": str(f.get("etiqueta") or "").strip(),
        })
    if payload:
        sb.table("bancos_reglas").insert(payload).execute()
    return len(payload)


def cargar_centros(sb, empresa_id) -> list:
    try:
        r = (sb.table("bancos_cc").select("centro_costo,orden")
             .eq("empresa_id", empresa_id).order("orden").execute())
        return [str(x["centro_costo"]).strip() for x in (r.data or []) if x.get("centro_costo")]
    except Exception:  # noqa: BLE001
        return []


def guardar_centros(sb, empresa_id, centros) -> int:
    centros = [str(c).strip() for c in centros if str(c).strip()]
    sb.table("bancos_cc").delete().eq("empresa_id", empresa_id).execute()
    payload = [{"empresa_id": empresa_id, "centro_costo": c, "orden": i}
               for i, c in enumerate(dict.fromkeys(centros))]
    if payload:
        sb.table("bancos_cc").insert(payload).execute()
    return len(payload)


def sembrar_reglas_defecto(sb, empresa_id) -> int:
    return guardar_reglas(sb, empresa_id, REGLAS_DEFECTO)


# ===========================================================================
# Semilla para GRUPO DE LOLITA (bancos + reglas con sus cuentas del PUC)
# ===========================================================================
BANCOS_LOLITA = [
    {"nombre": "DAVIVIENDA 7872",         "detectar": "03986999 7872",     "formato": "davivienda",         "nit": "860034313", "cuenta_puc": "11200513"},
    {"nombre": "OCCIDENTE 9426",          "detectar": "405-08942-6",       "formato": "occidente",          "nit": "890300279", "cuenta_puc": "11100505"},
    {"nombre": "BANCOLOMBIA AHORRO 8271", "detectar": "255438271",         "formato": "bancolombia_ahorro", "nit": "890903938", "cuenta_puc": "11100501"},
    {"nombre": "FIDU DAVIVIENDA 3122",    "detectar": "0607039800123122",  "formato": "fidu_davivienda",    "nit": "800182281", "cuenta_puc": "11304001"},
    {"nombre": "FIDU BANCOLOMBIA 4655",   "detectar": "15000304655",       "formato": "fidu_bancolombia",   "nit": "800180687", "cuenta_puc": "11304002"},
    {"nombre": "BANCOLOMBIA CTE 4451",    "detectar": "864314451",         "formato": "bancolombia_cta",    "nit": "890903938", "cuenta_puc": "11100599"},
]

REGLAS_LOLITA = [
    {"patron": r"4X1\.?000|4 ?POR ?MIL|IMPTO GOBIERNO|\bGMF\b|GRAVAMEN", "cuenta": "53050601", "lado": "D", "base": False, "etiqueta": "GRAVAMEN 4X1000"},
    {"patron": r"\bIVA\b",                                               "cuenta": "24081009", "lado": "D", "base": True,  "etiqueta": "IVA DESCONTABLE GASTOS"},
    {"patron": r"RETEFUENTE|RETEFTE|RETENCION",                          "cuenta": "13551509", "lado": "R", "base": False, "etiqueta": "RETEFUENTE RENDIMIENTOS"},
    {"patron": r"COMISION|COMIS\b",                                      "cuenta": "53051501", "lado": "D", "base": False, "etiqueta": "COMISIONES"},
    {"patron": r"CUOTA ADMIN|CUOTA ?MANEJO|C ?MANEJO|CobroServicio|MANEJO ?PORTAL|CobroTransf|CobroTransferencia|NdCobro|SERVICIO ?RECAUDO|SERV ?TRANS|CobroServicioEmpresarial", "cuenta": "53050501", "lado": "D", "base": False, "etiqueta": "GASTOS BANCARIOS"},
    {"patron": r"RENDIMIEN|ABONO INTERES|INTERESES AHORR|INTERES\b",     "cuenta": "42100501", "lado": "C", "base": False, "etiqueta": "INGRESOS FINANCIEROS"},
]


def sembrar_lolita(sb, empresa_id) -> tuple:
    """Carga los bancos y reglas de GRUPO DE LOLITA. Devuelve (n_bancos, n_reglas)."""
    nb = guardar_bancos(sb, empresa_id, BANCOS_LOLITA)
    nr = guardar_reglas(sb, empresa_id, REGLAS_LOLITA)
    return nb, nr
