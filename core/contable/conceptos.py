"""
core/contable/conceptos.py

Atajos de captura para INTEGRAL: tipos de IVA, tipos de retención y
"conceptos programados" (plantillas de asiento). Mismo patrón que
servicio_contable.py: cada función recibe el cliente Supabase `sb` primero.

Lo central es aplicar_concepto(): dado un concepto y una BASE gravable,
genera las líneas del asiento (partida doble) ya cuadradas Db = Cr, para
que la Captura las muestre listas y editables en lugar de digitarlas.

Modelo de un concepto (parametrico, cubre el 80% de compras/ventas):

    COMPRA:
        Db  cuenta_base            = base
        Db  cuenta_iva             = base * tarifa_iva            (si maneja_iva)
        Cr  cuenta_retencion(i)    = ret_i                        (si hay retenciones)
        Cr  cuenta_contrapartida   = base + iva - Σret            (neto a pagar)

    VENTA (simétrico):
        Cr  cuenta_base (ingreso)  = base
        Cr  cuenta_iva (generado)  = base * tarifa_iva
        Db  cuenta_retencion(i)    = ret_i          (retención que ME practican)
        Db  cuenta_contrapartida   = base + iva - Σret            (neto a cobrar)

Cada retención puede calcularse sobre la BASE (retefuente, reteICA) o sobre
el IVA (reteIVA), según su campo base_calculo.
"""
from __future__ import annotations

from typing import Optional


# ============================================================
# Helpers
# ============================================================

def _num(v, defecto=0.0) -> float:
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (ValueError, TypeError, AttributeError):
        return defecto


def _int(v) -> int:
    try:
        return int(round(float(v)))
    except (ValueError, TypeError):
        return 0


def calcular_retencion(base: int, iva: int, tipo_ret: dict) -> int:
    """Valor de una retención según su base de cálculo ('base' o 'iva')."""
    if not tipo_ret:
        return 0
    tarifa = _num(tipo_ret.get("tarifa"))
    sobre = iva if str(tipo_ret.get("base_calculo", "base")).lower() == "iva" else base
    return _int(sobre * tarifa / 100.0)


# ============================================================
# aplicar_concepto — PURO (sin red), testeable
# ============================================================

def aplicar_concepto(
    concepto: dict,
    base,
    tipo_iva: Optional[dict] = None,
    retenciones: Optional[list[dict]] = None,
    nit: str = "",
    detalle: str = "",
    cuenta_base: Optional[str] = None,
    cuenta_contrapartida: Optional[str] = None,
    desglose_iva: Optional[list[dict]] = None,
) -> list[dict]:
    """Genera las líneas del asiento para un concepto y una base gravable.

    Args:
        concepto: fila de cn_conceptos (dict). Usa naturaleza, cuenta_base,
                  cuenta_contrapartida, maneja_iva, maneja_retencion.
        base: base gravable (número). Se ignora si se pasa desglose_iva.
        tipo_iva: fila de cn_tipos_iva (dict) o None.
        retenciones: lista de filas de cn_tipos_retencion (dicts) a aplicar.
        nit / detalle: se copian a cada línea.
        cuenta_base / cuenta_contrapartida: sobreescriben las del concepto.
        desglose_iva: para facturas con TARIFAS DIFERENCIALES, lista de
                      {tarifa, base, iva, cuenta}. Si se pasa, se generan
                      líneas de base e IVA SEPARADAS por tarifa.

    Returns:
        lista de dicts {cuenta, tr, valor, base, nit, detalle, tipo} donde
        tr='1' (débito) o '2' (crédito). Cuadran Db = Cr.
    """
    base = _int(base)
    retenciones = retenciones or []
    naturaleza = str(concepto.get("naturaleza") or "compra").lower()
    c_base = cuenta_base or concepto.get("cuenta_base") or ""
    c_contra = cuenta_contrapartida or concepto.get("cuenta_contrapartida") or ""
    maneja_iva = bool(concepto.get("maneja_iva", True))

    # Buckets por tarifa (unifica el caso simple y el de tarifas diferenciales)
    if desglose_iva:
        buckets = [{
            "tarifa": _num(b.get("tarifa")), "base": _int(b.get("base")),
            "iva": _int(b.get("iva")),
            "cuenta": b.get("cuenta") or (tipo_iva.get("cuenta") if tipo_iva else ""),
        } for b in desglose_iva if _int(b.get("base"))]
    elif maneja_iva and tipo_iva is not None:
        iva = _int(base * _num(tipo_iva.get("tarifa")) / 100.0)
        buckets = [{"tarifa": _num(tipo_iva.get("tarifa")), "base": base,
                    "iva": iva, "cuenta": tipo_iva.get("cuenta") or ""}]
    else:
        buckets = [{"tarifa": 0, "base": base, "iva": 0, "cuenta": ""}]

    base_total = sum(b["base"] for b in buckets)
    iva_total = sum(b["iva"] for b in buckets)

    # Retenciones (solo si el concepto las maneja) — sobre los totales
    rets = []
    if bool(concepto.get("maneja_retencion", True)):
        for tr_ in retenciones:
            if not tr_:
                continue
            val = calcular_retencion(base_total, iva_total, tr_)
            if val:
                rets.append((tr_, val))
    total_ret = sum(v for _, v in rets)
    neto = base_total + iva_total - total_ret

    es_venta = naturaleza == "venta"
    tr_base = "2" if es_venta else "1"          # ingreso=Cr / gasto=Db
    tr_iva = "2" if es_venta else "1"
    tr_ret = "1" if es_venta else "2"           # a mí me retienen=Db / yo retengo=Cr
    tr_contra = "1" if es_venta else "2"        # cliente=Db / proveedor-banco=Cr
    multi = len(buckets) > 1

    lineas: list[dict] = []

    def _add(cuenta, tr, valor, base_col=0, tipo="", suf=""):
        if not cuenta or valor == 0:
            return
        lineas.append({
            "cuenta": str(cuenta).strip(),
            "tr": tr,
            "valor": _int(valor),
            "base": _int(base_col),
            "nit": nit,
            "detalle": (detalle + suf) if suf else detalle,
            "tipo": tipo,
        })

    # Base (una línea por tarifa cuando hay desglose)
    for b in buckets:
        suf = f" (IVA {b['tarifa']:g}%)" if multi else ""
        _add(c_base, tr_base, b["base"], base_col=b["base"], tipo="base", suf=suf)
    # IVA por tarifa
    for b in buckets:
        if b["iva"]:
            suf = f" (IVA {b['tarifa']:g}%)" if multi else ""
            _add(b["cuenta"], tr_iva, b["iva"], base_col=b["base"], tipo="iva", suf=suf)
    # Retenciones
    for tr_, val in rets:
        _add(tr_.get("cuenta") or "", tr_ret, val, base_col=base_total,
             tipo="retencion:" + str(tr_.get("codigo") or ""))
    # Contrapartida
    _add(c_contra, tr_contra, neto, base_col=0, tipo="contrapartida")

    return lineas


# ============================================================
# Clasificación automática de la factura → concepto sugerido
# ============================================================

_KW_CATEGORIA = {
    "honorarios": ["honorar", "asesor", "consultor", "profesional", "abogad",
                   "contad", "revisor", "auditor"],
    "arrendamiento": ["arrend", "arriendo", "canon", "alquiler", "alquil"],
    "servicios": ["servicio", "mantenim", "reparac", "transporte", "vigilancia",
                  "aseo", "publicidad", "instalac", "soporte", "mano de obra"],
}

_CAT_A_CONCEPTO_KW = {
    "honorarios": ["honorar"],
    "arrendamiento": ["arrend", "arriendo", "canon"],
    "servicios": ["servicio", "serv"],
    "compra": ["compra", "bien", "mercan", "insumo"],
}


def clasificar_factura(factura: dict) -> str:
    """Deduce la categoría de la factura por palabras clave del proveedor y de
    los ítems: 'honorarios' | 'arrendamiento' | 'servicios' | 'compra'."""
    partes = [str(factura.get("nombre") or "")]
    for it in factura.get("items", []) or []:
        partes.append(str(it.get("descripcion") or ""))
    txt = " ".join(partes).lower()
    for cat, kws in _KW_CATEGORIA.items():   # honorarios y arrendamiento antes que servicios
        if any(k in txt for k in kws):
            return cat
    return "compra"


def sugerir_concepto(factura: dict, conceptos: list[dict]) -> Optional[str]:
    """Devuelve el código del concepto (de compra) que mejor calza con la
    factura, o None si no encuentra uno claro."""
    cat = clasificar_factura(factura)
    kws = _CAT_A_CONCEPTO_KW.get(cat, [])
    compras = [c for c in conceptos if str(c.get("naturaleza") or "compra") == "compra"]
    for c in compras:
        blob = f"{c.get('codigo', '')} {c.get('nombre', '')}".lower()
        if any(k in blob for k in kws):
            return c["codigo"]
    return None


def ajustar_por_regimen(concepto: dict, tipos_ret: list[dict],
                        tipos_iva: list[dict], regimen: Optional[dict]):
    """Sugiere IVA y retenciones según el régimen del proveedor (compras).

    Reglas prácticas (editables por el usuario en la Captura):
      - Proveedor NO responsable de IVA → sin IVA descontable ni reteIVA.
      - Proveedor autorretenedor de renta o Régimen Simple (RST) → no se le
        practica ReteFuente de renta.
      - ReteICA depende del municipio/actividad → se deja manual.

    Returns: (iva_codigo|None, [retencion_codigos], [notas]).
    """
    ret_by = {t["codigo"]: t for t in tipos_ret}
    notas: list[str] = []

    iva_cod = concepto.get("tipo_iva_codigo") if concepto.get("maneja_iva") else None

    rets: list[str] = []
    if concepto.get("maneja_retencion") and concepto.get("tipo_retencion_codigo"):
        rets = [concepto["tipo_retencion_codigo"]]

    if regimen:
        if regimen.get("iva") == "no_responsable":
            if iva_cod is not None:
                iva_cod = None
                notas.append("Proveedor NO responsable de IVA → sin IVA descontable.")
            iva_prev = len(rets)
            rets = [r for r in rets if ret_by.get(r, {}).get("clase") != "iva"]
            if len(rets) != iva_prev:
                notas.append("Sin ReteIVA (proveedor no responsable de IVA).")

        if regimen.get("autorretenedor") or regimen.get("regimen_simple"):
            quitados = [r for r in rets if ret_by.get(r, {}).get("clase") == "fuente"]
            if quitados:
                rets = [r for r in rets if r not in quitados]
                motivo = ("autorretenedor de renta" if regimen.get("autorretenedor")
                          else "Régimen Simple (RST)")
                notas.append(f"Proveedor {motivo} → no se practica ReteFuente de renta.")

    # solo dejar códigos que existan
    rets = [r for r in rets if r in ret_by]
    return iva_cod, rets, notas


def resumen_asiento(lineas: list[dict]) -> dict:
    """{debitos, creditos, cuadra} de un conjunto de líneas."""
    db = sum(l["valor"] for l in lineas if l["tr"] == "1")
    cr = sum(l["valor"] for l in lineas if l["tr"] == "2")
    return {"debitos": db, "creditos": cr, "diferencia": db - cr, "cuadra": db == cr}


# ============================================================
# CRUD — tipos de IVA
# ============================================================

def tablas_existen(sb, empresa_id: str) -> bool:
    """True si las tablas de conceptos ya existen (migración 016 aplicada).

    Evita que las páginas revienten con APIError cuando la migración aún no
    se corrió en Supabase.
    """
    try:
        sb.table("cn_conceptos").select("id").eq("empresa_id", empresa_id).limit(1).execute()
        return True
    except Exception:
        return False


def listar_tipos_iva(sb, empresa_id: str) -> list[dict]:
    return (sb.table("cn_tipos_iva").select("*")
            .eq("empresa_id", empresa_id).order("codigo").execute().data or [])


def upsert_tipo_iva(sb, empresa_id: str, codigo: str, nombre: str,
                    tarifa, cuenta: str = "", tipo: str = "C") -> dict:
    payload = {"empresa_id": empresa_id, "codigo": str(codigo), "nombre": nombre,
               "tarifa": _num(tarifa), "cuenta": cuenta or None, "tipo": (tipo or "C")[:1]}
    res = sb.table("cn_tipos_iva").upsert(payload, on_conflict="empresa_id,codigo").execute()
    return (res.data or [{}])[0]


def eliminar_tipo_iva(sb, empresa_id: str, codigo: str) -> None:
    sb.table("cn_tipos_iva").delete().eq("empresa_id", empresa_id).eq("codigo", str(codigo)).execute()


# ============================================================
# CRUD — tipos de retención
# ============================================================

def listar_tipos_retencion(sb, empresa_id: str) -> list[dict]:
    return (sb.table("cn_tipos_retencion").select("*")
            .eq("empresa_id", empresa_id).order("codigo").execute().data or [])


def upsert_tipo_retencion(sb, empresa_id: str, codigo: str, nombre: str, tarifa,
                          base_calculo: str = "base", base_uvt=0,
                          cuenta: str = "", clase: str = "fuente") -> dict:
    payload = {"empresa_id": empresa_id, "codigo": str(codigo), "nombre": nombre,
               "tarifa": _num(tarifa), "base_calculo": base_calculo or "base",
               "base_uvt": _num(base_uvt), "cuenta": cuenta or None,
               "clase": clase or "fuente"}
    res = sb.table("cn_tipos_retencion").upsert(payload, on_conflict="empresa_id,codigo").execute()
    return (res.data or [{}])[0]


def eliminar_tipo_retencion(sb, empresa_id: str, codigo: str) -> None:
    sb.table("cn_tipos_retencion").delete().eq("empresa_id", empresa_id).eq("codigo", str(codigo)).execute()


# ============================================================
# CRUD — conceptos
# ============================================================

def listar_conceptos(sb, empresa_id: str, naturaleza: Optional[str] = None) -> list[dict]:
    q = sb.table("cn_conceptos").select("*").eq("empresa_id", empresa_id)
    if naturaleza:
        q = q.eq("naturaleza", naturaleza)
    return q.order("codigo").execute().data or []


def obtener_concepto(sb, empresa_id: str, codigo: str) -> dict:
    res = (sb.table("cn_conceptos").select("*")
           .eq("empresa_id", empresa_id).eq("codigo", str(codigo)).limit(1).execute())
    return (res.data or [{}])[0]


def upsert_concepto(sb, empresa_id: str, codigo: str, nombre: str, **campos) -> dict:
    payload = {"empresa_id": empresa_id, "codigo": str(codigo), "nombre": nombre, **campos}
    res = sb.table("cn_conceptos").upsert(payload, on_conflict="empresa_id,codigo").execute()
    return (res.data or [{}])[0]


def eliminar_concepto(sb, empresa_id: str, codigo: str) -> None:
    sb.table("cn_conceptos").delete().eq("empresa_id", empresa_id).eq("codigo", str(codigo)).execute()


# ============================================================
# Juego ESTÁNDAR (Colombia) — se siembra por empresa desde la UI
# ============================================================
# Cuentas por defecto de PUC comercial; el usuario las ajusta a su plan.

SEED_TIPOS_IVA = [
    # codigo, nombre, tarifa, cuenta, tipo(C/V)
    ("IVA19",  "IVA 19% descontable (compras)", 19, "240820", "C"),
    ("IVA5",   "IVA 5% descontable (compras)",   5, "240820", "C"),
    ("IVA0",   "IVA 0% / excluido",              0, "",       "C"),
    ("IVA19V", "IVA 19% generado (ventas)",     19, "240810", "V"),
    ("IVA5V",  "IVA 5% generado (ventas)",       5, "240810", "V"),
]

SEED_TIPOS_RETENCION = [
    # codigo, nombre, tarifa, base_calculo, base_uvt, cuenta, clase
    ("RFCOMP",  "ReteFuente compras 2.5%",           2.5, "base", 27,  "236540", "fuente"),
    ("RFSERV4", "ReteFuente servicios 4% (declar.)", 4,   "base", 4,   "236525", "fuente"),
    ("RFSERV6", "ReteFuente servicios 6% (no dec.)", 6,   "base", 4,   "236525", "fuente"),
    ("RFHON10", "ReteFuente honorarios 10%",         10,  "base", 0,   "236515", "fuente"),
    ("RFHON11", "ReteFuente honorarios 11%",         11,  "base", 0,   "236515", "fuente"),
    ("RFARR",   "ReteFuente arrendamientos 3.5%",    3.5, "base", 27,  "236530", "fuente"),
    ("RETEIVA", "ReteIVA 15% (sobre el IVA)",        15,  "iva",  0,   "236701", "iva"),
    ("RETEICA", "ReteICA (tarifa municipal)",        0.7, "base", 0,   "236805", "ica"),
]

SEED_CONCEPTOS = [
    # codigo, nombre, naturaleza, comprobante, cuenta_base, cuenta_contra,
    #   tipo_iva_codigo, tipo_ret_codigo, maneja_iva, maneja_ret, descripcion
    ("COMPRA_BIEN_19", "Compra de bienes 19% + ReteCompras 2.5%", "compra", "3",
     "143501", "220505", "IVA19", "RFCOMP", True, True,
     "Compra gravada de mercancía/insumos con IVA descontable y retención por compras."),
    ("COMPRA_SERV_19", "Servicios 19% + ReteServicios 4%", "compra", "3",
     "513535", "220505", "IVA19", "RFSERV4", True, True,
     "Servicios gravados con IVA descontable y retención por servicios."),
    ("HONORARIOS", "Honorarios 19% + Rete 11%", "compra", "3",
     "511030", "220505", "IVA19", "RFHON11", True, True,
     "Honorarios profesionales con IVA descontable y retención por honorarios."),
    ("ARRENDAMIENTO", "Arrendamiento 19% + Rete 3.5%", "compra", "3",
     "512010", "220505", "IVA19", "RFARR", True, True,
     "Arrendamiento de bienes con IVA descontable y retención por arrendamiento."),
    ("SERV_PUBLICOS", "Servicios públicos (sin IVA ni retención)", "compra", "2",
     "513535", "111005", "IVA0", None, False, False,
     "Servicios públicos: no llevan IVA descontable ni retención en la fuente."),
    ("COMPRA_EXCLUIDA", "Compra excluida/exenta (sin IVA ni retención)", "compra", "3",
     "143501", "220505", "IVA0", None, False, False,
     "Compra excluida o exenta: sin IVA descontable ni retención."),
    ("VENTA_19", "Venta gravada 19%", "venta", "1",
     "413501", "130505", "IVA19V", None, True, False,
     "Venta de mercancía gravada con IVA generado (contrapartida a clientes)."),
]


def sembrar_estandar(sb, empresa_id: str, sobrescribir: bool = False) -> dict:
    """Siembra el juego estándar de tipos y conceptos para la empresa.

    Con sobrescribir=False (por defecto) usa upsert por (empresa_id, codigo):
    crea los que faltan y refresca los existentes. Devuelve conteos.
    """
    n_iva = n_ret = n_con = 0
    for cod, nom, tar, cta, tipo in SEED_TIPOS_IVA:
        upsert_tipo_iva(sb, empresa_id, cod, nom, tar, cta, tipo)
        n_iva += 1
    for cod, nom, tar, bc, uvt, cta, clase in SEED_TIPOS_RETENCION:
        upsert_tipo_retencion(sb, empresa_id, cod, nom, tar, bc, uvt, cta, clase)
        n_ret += 1
    for (cod, nom, nat, comp, cbase, ccontra, tiva, tret,
         m_iva, m_ret, desc) in SEED_CONCEPTOS:
        upsert_concepto(
            sb, empresa_id, cod, nom,
            naturaleza=nat, comprobante=comp,
            cuenta_base=cbase, cuenta_contrapartida=ccontra,
            tipo_iva_codigo=tiva, tipo_retencion_codigo=tret,
            maneja_iva=m_iva, maneja_retencion=m_ret, descripcion=desc,
        )
        n_con += 1
    return {"tipos_iva": n_iva, "tipos_retencion": n_ret, "conceptos": n_con}
