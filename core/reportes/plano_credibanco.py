# -*- coding: utf-8 -*-
"""
core/reportes/plano_credibanco.py

Genera el PLANO de Contai con los GASTOS y RETENCIONES de Credibanco
(comisión, retefuente, reteIVA y reteICA) por centro de costo, a partir del
reporte crudo de Credibanco (.xlsx / .xls).

Reemplaza la macro de Excel "CREDIBANCO_MACROS.xlsm" (P1→P2→P3):
    P1  agrupa el crudo por centro de costo (mapea el código con el MAESTRO)
    P2  resume por centro de costo: comisión, retefuente, reteIVA, reteICA
    P3  arma el plano (una línea por cuenta y centro de costo)

Ventajas frente a la macro:
  - Reconoce los encabezados con espacio O con guion bajo (VALOR_COMISION,
    VALOR COMISION, etc.), así que funciona con el crudo tal como lo baja
    Credibanco, sin corregir el archivo.
  - Conserva el centro de costo a 6 dígitos (001110), no lo trunca a 1110.
  - No escribe líneas en cero.

Uso:
    from core.reportes.plano_credibanco import generar_plano_credibanco
    txt, resumen = generar_plano_credibanco(fuente, comprobante="10", documento="1")
"""
from __future__ import annotations

import io
from datetime import datetime

# ---------------------------------------------------------------------------
# MAESTRO: código de establecimiento -> (OASIS, CENTRO DE COSTO 6 dígitos)
# (tomado de la hoja MAESTRO de la macro; JIPER SAS)
# ---------------------------------------------------------------------------
MAESTRO = {
    "15335938": ("SL INDIANA", "001101"),
    "15335946": ("SL EL TESORO", "001103"),
    "15337249": ("SL OVIEDO", "001102"),
    "16302135": ("SL SAN LUCAS", "001104"),
    "16338469": ("SL DEL ESTE", "001105"),
    "16475907": ("SL VIVA ENVIGADO", "001106"),
    "16935967": ("SL LAURELES", "001107"),
    "16935991": ("SL LLANOGRANDE", "001108"),
    "17141482": ("SL BURBUJA POBLADO", "001109"),
    "18959593": ("SL MIXY LOS COLORES", "001110"),
    "19025956": ("SL CIUDAD DEL RIO", "001111"),
    "19512185": ("SL LOS MOLINOS", "001113"),
    "19710524": ("SL UNICENTRO", "001114"),
    "20248027": ("SL FABRICATO", "001112"),
    "20705364": ("SL LAS VEGAS", "001115"),
    "22608517": ("SL MEDICAL TOWER", "001116"),
    "22890008": ("SL MILLA DE ORO", "001117"),
    "30887715": ("SL HOTEL NOCK", "001118"),
    "30876635": ("ML EL TESORO", "001201"),
    "30876429": ("ML FABRICATO", "001205"),
    "30876445": ("ML MANILA", "001206"),
    "30876643": ("ML VIVA ENVIGADO", "001203"),
    "30881007": ("ML LAURELES", "001204"),
    "30881023": ("ML MILLA DE ORO", "001207"),
    "30998447": ("SL VENDING", "001119"),
}

# ---------------------------------------------------------------------------
# CONFIG por defecto (hoja CONFIG de la macro). Todo es override-able.
# ---------------------------------------------------------------------------
CONFIG_DEF = {
    "cuenta_comision": "53051501",
    "cuenta_retefuente": "19551501",
    "cuenta_rete_iva": "24082505",
    "cuenta_rete_ica": "52150503",
    "divisor_retefuente": 0.015,
    "divisor_rete_iva": 0.15,
    "divisor_rete_ica": 0.009,
    "nit": "890903938",
    "detalle": "CONCILIACION BANCARIA",
    "tipo": "1",
    "comprobante": "10",
}

# Encabezado del plano (13 columnas, igual que la macro)
PLANO_HDR = ["CTA NIIF", "Comprobante", "Fecha(mm/dd/yyyy)", "COMPRBNT", "Doc ref",
             "Nit", "DETALLE", "Tipo", "Valor", "Base", "Centro de Costo",
             "Trans. Ext", "Plazo"]


def _norm(s) -> str:
    """Normaliza un título: mayúsculas, sin espacios sobrantes, guion bajo→espacio."""
    return str(s or "").strip().upper().replace("_", " ")


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _fecha(v):
    """Devuelve un datetime a partir de una celda (date, 'YYYYMMDD' o texto)."""
    if isinstance(v, datetime):
        return v
    s = str(v or "").strip()
    if len(s) == 8 and s.isdigit():
        try:
            return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def _abrir(fuente):
    """Abre el reporte (ruta, bytes o file-like) y devuelve la hoja de datos."""
    import openpyxl
    if isinstance(fuente, (bytes, bytearray)):
        wb = openpyxl.load_workbook(io.BytesIO(fuente), data_only=True, read_only=True)
    elif hasattr(fuente, "read"):
        wb = openpyxl.load_workbook(io.BytesIO(fuente.read()), data_only=True, read_only=True)
    else:
        wb = openpyxl.load_workbook(fuente, data_only=True, read_only=True)
    # buscar la hoja que tenga la columna VALOR COMISION
    for ws in wb.worksheets:
        hdr = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ())
        if any(_norm(h) == "VALOR COMISION" for h in hdr):
            return ws
    return wb.worksheets[0]


def generar_plano_credibanco(fuente, comprobante=None, documento="1", config=None,
                             maestro=None):
    """
    Genera el plano de Contai (texto tab-delimitado) con los gastos y
    retenciones de Credibanco por centro de costo.

    Args:
        fuente:      reporte crudo de Credibanco (ruta / bytes / file-like .xlsx).
        comprobante: comprobante del asiento (por defecto CONFIG = "10").
        documento:   documento / consecutivo (va en COMPRBNT y Doc ref).
        config:      dict opcional para sobreescribir cuentas/divisores/NIT/etc.
        maestro:     dict {codigo: (oasis, centro_costo)} de la empresa. Si es
                     None se usa el MAESTRO embebido (JIPER).

    Returns:
        (plano_txt, resumen) donde
          plano_txt : str con encabezado + líneas, separado por TAB, \\r\\n, listo
                      para guardar en .txt e importar a Contai.
          resumen   : dict con totales y detalle por centro de costo.
    """
    cfg = dict(CONFIG_DEF)
    if config:
        cfg.update({k: v for k, v in config.items() if v not in (None, "")})
    maes = maestro if maestro else MAESTRO
    comp = str(comprobante or cfg["comprobante"]).strip()
    doc = str(documento or "1").strip()

    ws = _abrir(fuente)
    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        raise ValueError("El reporte de Credibanco está vacío.")
    hdr = [_norm(h) for h in filas[0]]
    idx = {h: i for i, h in enumerate(hdr)}

    def col(*titulos):
        for t in titulos:
            if _norm(t) in idx:
                return idx[_norm(t)]
        return None

    cCod = col("CODIGO ESTABLECIMIENTO")
    cCom = col("VALOR COMISION")
    cRet = col("VALOR RETEFUENTE")
    cRiva = col("VALOR RETE IVA")
    cRica = col("VALOR RTE ICA")
    cCanje = col("FECHA DE CANJE")
    if cCod is None or cCom is None:
        raise ValueError(
            "No reconozco las columnas del archivo (falta CODIGO ESTABLECIMIENTO "
            "o VALOR COMISION). Verifica que sea el reporte de Credibanco.")

    # ---- agrupar por centro de costo ----
    agg = {}                      # cc -> {oasis, comision, retefuente, riva, rica}
    fecha_max = None
    for r in filas[1:]:
        if cCod >= len(r):
            continue
        cod = str(r[cCod] or "").strip()
        if not cod:
            continue
        oasis, cc = maes.get(cod, (cod, cod))
        a = agg.setdefault(cc, {"oasis": oasis, "com": 0.0, "ret": 0.0, "riva": 0.0, "rica": 0.0})
        a["com"] += _num(r[cCom]) if cCom is not None and cCom < len(r) else 0
        a["ret"] += _num(r[cRet]) if cRet is not None and cRet < len(r) else 0
        a["riva"] += _num(r[cRiva]) if cRiva is not None and cRiva < len(r) else 0
        a["rica"] += _num(r[cRica]) if cRica is not None and cRica < len(r) else 0
        if cCanje is not None and cCanje < len(r):
            f = _fecha(r[cCanje])
            if f and (fecha_max is None or f > fecha_max):
                fecha_max = f
    if fecha_max is None:
        fecha_max = datetime.today()
    fecha_str = fecha_max.strftime("%m/%d/%Y")

    # ---- armar el plano (por cuenta y centro de costo) ----
    lineas = ["\t".join(PLANO_HDR)]

    def escribe(cta, valor, base, cc):
        if round(valor, 2) == 0 and round(base, 2) == 0:
            return
        campos = [cta, comp, fecha_str, doc, doc, cfg["nit"], cfg["detalle"],
                  cfg["tipo"], f"{valor:.2f}", f"{base:.2f}", cc, "", ""]
        lineas.append("\t".join(campos))

    ccs = sorted(agg.keys())
    tot = {"com": 0.0, "ret": 0.0, "riva": 0.0, "rica": 0.0}
    # Valor y base SIEMPRE en POSITIVO: en el plano de Contai el signo lo da el
    # Tipo (1=débito), así que el valor debe ir positivo o el sistema lo rechaza.
    # Orden igual que la macro: comisiones, retefuente, reteIVA, reteICA.
    for cc in ccs:
        v = abs(agg[cc]["com"])
        escribe(cfg["cuenta_comision"], v, 0.0, cc); tot["com"] += v
    for cc in ccs:
        v = abs(agg[cc]["ret"])
        escribe(cfg["cuenta_retefuente"], v, v / cfg["divisor_retefuente"] if cfg["divisor_retefuente"] else 0, cc); tot["ret"] += v
    for cc in ccs:
        v = abs(agg[cc]["riva"])
        escribe(cfg["cuenta_rete_iva"], v, v / cfg["divisor_rete_iva"] if cfg["divisor_rete_iva"] else 0, cc); tot["riva"] += v
    for cc in ccs:
        v = abs(agg[cc]["rica"])
        escribe(cfg["cuenta_rete_ica"], v, v / cfg["divisor_rete_ica"] if cfg["divisor_rete_ica"] else 0, cc); tot["rica"] += v

    plano_txt = "\r\n".join(lineas) + "\r\n"
    resumen = {
        "fecha": fecha_str,
        "centros": len(ccs),
        "lineas": len(lineas) - 1,
        "total_comision": tot["com"],
        "total_retefuente": tot["ret"],
        "total_rete_iva": tot["riva"],
        "total_rete_ica": tot["rica"],
        "detalle": {cc: agg[cc] for cc in ccs},
    }
    return plano_txt, resumen


def plano_credibanco_bytes(*args, **kwargs) -> bytes:
    """Igual que generar_plano_credibanco pero devuelve (bytes_latin1, resumen)."""
    txt, resumen = generar_plano_credibanco(*args, **kwargs)
    return txt.encode("latin-1", errors="replace"), resumen


# ===========================================================================
# Configuración por empresa (Supabase) — tablas credibanco_maestro / _config
# (ver db/migrations/019_credibanco_plano.sql). Cada empresa define su propio
# maestro (código -> centro de costo) y sus cuentas, sin tocar código.
# ===========================================================================

def cargar_maestro(sb, empresa_id) -> dict:
    """Devuelve {codigo: (oasis, centro_costo)} de la empresa desde Supabase.
    Si la empresa no tiene maestro cargado, devuelve {} (la UI puede sembrarlo)."""
    try:
        r = (sb.table("credibanco_maestro")
             .select("codigo,oasis,centro_costo")
             .eq("empresa_id", empresa_id).execute())
        out = {}
        for row in (r.data or []):
            cod = str(row.get("codigo") or "").strip()
            if cod:
                out[cod] = (str(row.get("oasis") or "").strip(),
                            str(row.get("centro_costo") or "").strip())
        return out
    except Exception:  # noqa: BLE001
        return {}


def guardar_maestro(sb, empresa_id, filas) -> int:
    """Reemplaza el maestro de la empresa por `filas` (lista de dicts con
    codigo, oasis, centro_costo). Borra los códigos que ya no estén."""
    filas = [f for f in filas if str(f.get("codigo") or "").strip()
             and str(f.get("centro_costo") or "").strip()]
    codigos = [str(f["codigo"]).strip() for f in filas]
    # borrar los que ya no estén
    actuales = cargar_maestro(sb, empresa_id)
    sobran = [c for c in actuales if c not in codigos]
    for c in sobran:
        sb.table("credibanco_maestro").delete().eq("empresa_id", empresa_id).eq("codigo", c).execute()
    # upsert de los actuales
    payload = [{"empresa_id": empresa_id, "codigo": str(f["codigo"]).strip(),
                "oasis": str(f.get("oasis") or "").strip(),
                "centro_costo": str(f["centro_costo"]).strip()} for f in filas]
    if payload:
        sb.table("credibanco_maestro").upsert(payload, on_conflict="empresa_id,codigo").execute()
    return len(payload)


def cargar_config(sb, empresa_id) -> dict:
    """Devuelve el CONFIG de la empresa mezclado con los valores por defecto."""
    cfg = dict(CONFIG_DEF)
    try:
        r = (sb.table("credibanco_config").select("*")
             .eq("empresa_id", empresa_id).limit(1).execute())
        if r.data:
            row = r.data[0]
            for k in cfg:
                if row.get(k) not in (None, ""):
                    cfg[k] = row[k]
    except Exception:  # noqa: BLE001
        pass
    return cfg


def guardar_config(sb, empresa_id, cfg) -> None:
    """Upsert de la fila de config de la empresa."""
    campos = ["cuenta_comision", "cuenta_retefuente", "cuenta_rete_iva", "cuenta_rete_ica",
              "divisor_retefuente", "divisor_rete_iva", "divisor_rete_ica",
              "nit", "detalle", "tipo", "comprobante"]
    payload = {"empresa_id": empresa_id}
    for k in campos:
        if k in cfg and cfg[k] not in (None, ""):
            payload[k] = cfg[k]
    sb.table("credibanco_config").upsert(payload, on_conflict="empresa_id").execute()


def maestro_jiper_filas() -> list:
    """El maestro de JIPER como lista de dicts, para sembrarlo con un botón."""
    return [{"codigo": c, "oasis": v[0], "centro_costo": v[1]} for c, v in MAESTRO.items()]
