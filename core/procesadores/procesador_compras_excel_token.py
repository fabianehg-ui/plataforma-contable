"""
core/procesadores/procesador_compras_excel_token.py

Procesa el Excel del Token DIAN para generar el plano contable de COMPRAS
recibidas, con la misma lógica de tarifa diferencial que ventas:

  - Factura electrónica recibida → genera asiento de compra
  - Tarifa pura (0% / 5% / 19% / INC8%) → plano contable directo
  - Tarifa MIXTA → lista para descargar XML (no entra al plano)

CUENTAS:
  Db CUENTA GASTO (según mapeo NIT→cuenta histórica)
  Db IVA DESCONTABLE (según tarifa)
  Cr PROVEEDORES NACIONALES (22050505)

EXPONE:
    procesar_compras_v1(df_excel, ruta_mapeo_historico) -> ResultadoCompras
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


# ─── Constantes ──────────────────────────────────────────────

TOLERANCIA = 5

# Tarifas válidas para deducción matemática
TARIFAS_IVA = [0.19, 0.05, 0.16]
TARIFAS_INC = [0.08, 0.16]

# Cuenta de proveedores (PUC estándar)
CUENTA_PROVEEDORES = "22050505"

# IVA descontable por tarifa (cuentas estándar PUC)
CUENTAS_IVA_DESCONTABLE = {
    "19%":  "24080601",
    "5%":   "24080605",
    "16%":  "24080606",
}

# INC pagado en compras (gasto, no descontable normalmente)
CUENTA_INC_COMPRAS = "51959505"

# Cuentas PUC para impuestos discriminados en compras
# NOTA: IBUA, ICUI, IC, ICL son mayor valor del costo del producto en compras
# (Ley 2277/2022 art. 513-3 — no descontables). Para JIPER que compra los
# productos (no los produce), estos impuestos suben el costo.
# Agrupación pedida por el usuario:
#   - Impuesto saludable    = IBUA + ICUI
#   - Impuesto al consumo   = IC + INC Bolsas
#   - Impuesto a los licores = ICL
CUENTAS_IMPUESTOS_COMPRAS = {
    "saludable":   "71050601",  # IBUA + ICUI
    "consumo":     "71050603",  # IC + INC Bolsas
    "licores":     "71050605",  # ICL
    "ica":         "23686801",  # ICA retenido (si aparece)
    "carbono":     "71050606",
    "combustibles":"71050607",
    "datos":       "71050608",
    "inpp":        "71050609",
    "timbre":      "51959501",
}

# Mapeo columna del Excel → categoría
COLUMNA_A_CATEGORIA = {
    "IBUA":            "saludable",
    "ICUI":            "saludable",
    "IC":              "consumo",
    "INC Bolsas":      "consumo",
    "ICL":             "licores",
    "ICA":             "ica",
    "IN Carbono":      "carbono",
    "IN Combustibles": "combustibles",
    "IC Datos":        "datos",
    "INPP":            "inpp",
    "Timbre":          "timbre",
}

# Nombres legibles para el detalle del asiento
NOMBRES_CATEGORIA = {
    "saludable":   "IMP SALUDABLE",
    "consumo":     "IMP CONSUMO",
    "licores":     "IMP LICORES",
    "ica":         "ICA",
    "carbono":     "IN CARBONO",
    "combustibles":"IN COMBUSTIBLES",
    "datos":       "IC DATOS",
    "inpp":        "INPP",
    "timbre":      "TIMBRE",
}

# Cuenta fallback si proveedor no está mapeado
CUENTA_GASTO_FALLBACK = "73959501"   # GASTOS DIVERSOS

# Comprobante de compras (revisar con Luz si quiere otro)
COMPROBANTE_COMPRAS = "20"  # estándar para compras nacionales

# Columnas del plano (mismo formato que ventas)
COLUMNAS_PLANO = [
    "CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
    "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO",
]
TR_DEBITO = "1"
TR_CREDITO = "2"

# Centro de costo: las compras no tienen sucursal específica del Token,
# se asignan al CC principal por defecto (PRINCIPAL = 001001).
# El usuario puede mapear NITs específicos a CCs específicos si quiere.
CC_PRINCIPAL = "001001"


# ─── Estructuras ─────────────────────────────────────────────

@dataclass
class CompraToken:
    cufe: str
    folio: str
    prefijo: str
    fecha: date
    tipo_doc: str             # FE / NC / ND / DS-equivalente
    nit_emisor: str           # proveedor
    nombre_emisor: str
    total: float
    iva: float
    inc: float
    otros: float
    ret: float
    tarifa: str               # 0% / 5% / 19% / 16% / INC8% / MIXTA
    base_calc: float
    cuenta_gasto: Optional[str] = None
    cuenta_nombre: Optional[str] = None
    # Impuestos discriminados por columna del Excel
    impuestos_detalle: dict = field(default_factory=dict)


@dataclass
class ResultadoCompras:
    """Resultado del procesamiento."""
    plano_df: Optional[pd.DataFrame] = None
    plano_lineas: int = 0

    procesadas: List[CompraToken] = field(default_factory=list)
    mixtas: List[CompraToken] = field(default_factory=list)
    sin_cuenta: List[CompraToken] = field(default_factory=list)  # NITs sin mapeo
    notas_credito: List[CompraToken] = field(default_factory=list)  # NCs recibidas, manejo separado

    # Retenciones (v2)
    retenciones_aplicadas: List[dict] = field(default_factory=list)
    total_retefuente: float = 0
    total_reteiva: float = 0

    def resumen(self) -> dict:
        # Por proveedor
        por_prov = {}
        for c in self.procesadas:
            k = c.nit_emisor
            if k not in por_prov:
                por_prov[k] = {
                    "nombre": c.nombre_emisor,
                    "docs": 0, "base": 0, "iva": 0,
                    "inc": 0, "total": 0,
                    "cuenta": c.cuenta_gasto,
                    "cuenta_nombre": c.cuenta_nombre,
                }
            por_prov[k]["docs"] += 1
            por_prov[k]["base"] += c.base_calc
            por_prov[k]["iva"] += c.iva
            por_prov[k]["inc"] += c.inc
            por_prov[k]["total"] += c.total

        total_base = sum(c.base_calc for c in self.procesadas)
        total_iva = sum(c.iva for c in self.procesadas)
        total_inc = sum(c.inc for c in self.procesadas)
        total_fact = sum(c.total for c in self.procesadas)

        # Por cuenta
        por_cuenta = {}
        for c in self.procesadas:
            k = c.cuenta_gasto or "SIN_CUENTA"
            if k not in por_cuenta:
                por_cuenta[k] = {
                    "nombre": c.cuenta_nombre or "Sin nombre",
                    "docs": 0,
                    "total_base": 0,
                }
            por_cuenta[k]["docs"] += 1
            por_cuenta[k]["total_base"] += c.base_calc

        # Por tarifa
        por_tarifa = {}
        for c in self.procesadas:
            por_tarifa[c.tarifa] = por_tarifa.get(c.tarifa, 0) + 1

        return {
            "procesadas": len(self.procesadas),
            "mixtas": len(self.mixtas),
            "sin_cuenta": len(self.sin_cuenta),
            "notas_credito": len(self.notas_credito),
            "lineas_plano": self.plano_lineas,
            "total_base": total_base,
            "total_iva": total_iva,
            "total_inc": total_inc,
            "total_facturado": total_fact,
            "por_proveedor": por_prov,
            "por_cuenta": por_cuenta,
            "por_tarifa": por_tarifa,
        }


# ─── Helpers ─────────────────────────────────────────────────

def _f(v) -> float:
    try:
        f = float(v)
        if pd.isna(f):
            return 0.0
        return f
    except (ValueError, TypeError):
        return 0.0


def _normalizar_nit(s) -> str:
    if pd.isna(s):
        return ""
    s = str(s).split("-")[0]
    return re.sub(r"\D", "", s)


def _clasificar_tarifa(iva: float, inc: float, total: float, otros: float, ret: float) -> str:
    """Misma lógica que ventas pero adaptada a compras."""
    if abs(iva) < 0.01 and abs(inc) < 0.01:
        return "EXENTA"

    if abs(iva) > 0.01 and abs(inc) < 0.01:
        for tarifa in TARIFAS_IVA:
            base = iva / tarifa
            diff = total - base - iva - inc - otros - ret
            if -TOLERANCIA <= diff <= base * 0.05:
                return f"{int(tarifa*100)}%"
        return "MIXTA"

    if abs(inc) > 0.01 and abs(iva) < 0.01:
        for tarifa in TARIFAS_INC:
            base = inc / tarifa
            diff = total - base - iva - inc - otros - ret
            if -TOLERANCIA <= diff <= base * 0.05:
                return f"INC{int(tarifa*100)}%"
        return "MIXTA"

    return "MIXTA"


def _calcular_base(tarifa: str, iva: float, inc: float, total: float, otros: float, ret: float) -> float:
    if tarifa == "EXENTA":
        return total - iva - inc - otros - ret
    if tarifa.startswith("INC"):
        return inc / 0.08
    if tarifa.endswith("%"):
        tarifa_dec = float(tarifa.rstrip("%")) / 100
        return iva / tarifa_dec
    return 0


def cargar_mapeo_historico(ruta: str) -> Dict[str, dict]:
    """
    Lee mapeo_compras_historico.json y devuelve dict NIT→info.

    Returns: {nit: {cuenta_gasto, cuenta_nombre, nombre}}
    """
    with open(ruta) as f:
        data = json.load(f)
    out = {}
    for item in data.get("mapeo", []):
        out[item["nit"]] = {
            "cuenta_gasto": item["cuenta_gasto"],
            "cuenta_nombre": item.get("cuenta_nombre", ""),
            "nombre": item.get("nombre", ""),
        }
    return out


# ─── Procesamiento principal ─────────────────────────────────

TIPO_FE = "Factura electrónica"
TIPO_NC = "Nota de crédito electrónica"
TIPO_ND = "Nota de débito electrónica"
TIPO_FE_CONT = "Factura electrónica de contingencia"
TIPO_DEQ_POS = "Documento equivalente POS"
TIPO_DEQ_SP = "Documento equivalente - Servicios públicos domiciliarios"
TIPO_DEQ_TP = "Documento equivalente - Transporte aéreo de pasajeros"
TIPOS_COMPRA_NORMAL = {TIPO_FE, TIPO_FE_CONT, TIPO_DEQ_POS, TIPO_DEQ_SP, TIPO_DEQ_TP, TIPO_ND}

TIPOS_EXCLUIR = {"Application response", "Nomina Individual"}


def procesar_compras_v1(
    df_excel: pd.DataFrame,
    ruta_mapeo_historico: str,
    cc_default: str = CC_PRINCIPAL,
) -> ResultadoCompras:
    """
    Procesa el DataFrame del Excel del Token (filtrado o no) y arma el plano
    contable de compras.

    Args:
        df_excel: DataFrame del lector_excel_token (con columnas normalizadas).
        ruta_mapeo_historico: ruta a mapeo_compras_historico.json.
        cc_default: centro de costo por defecto.

    Returns:
        ResultadoCompras con plano_df y métricas.
    """
    resultado = ResultadoCompras()

    mapeo = cargar_mapeo_historico(ruta_mapeo_historico)

    # Filtrar solo recibidos (compras) y tipos contables
    df = df_excel[df_excel["grupo"].str.lower() == "recibido"].copy()
    df = df[~df["tipo_documento"].isin(TIPOS_EXCLUIR)]

    if len(df) == 0:
        resultado.plano_df = pd.DataFrame(columns=COLUMNAS_PLANO)
        return resultado

    # Numéricos
    OTROS_COLS = ["ICA", "IC", "Timbre", "INC Bolsas", "IN Carbono",
                  "IN Combustibles", "IC Datos", "ICL", "INPP", "IBUA", "ICUI"]
    RET_COLS = ["Rete IVA", "Rete Renta", "Rete ICA"]
    for c in ["IVA", "INC"] + OTROS_COLS + RET_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
        else:
            df[c] = 0

    filas_plano = []

    for _, row in df.iterrows():
        cufe = str(row.get("cufe", "")).strip()
        folio = str(row.get("folio", "")).strip()
        prefijo = str(row.get("prefijo", "")).strip().upper()
        tipo_doc = row.get("tipo_documento", "")
        nit_emisor = _normalizar_nit(row.get("nit_emisor", ""))
        nombre_emisor = str(row.get("nombre_emisor", "")).strip()
        total = _f(row.get("total", 0))
        iva = _f(row["IVA"])
        inc = _f(row["INC"])
        otros = sum(_f(row[c]) for c in OTROS_COLS)
        ret = sum(_f(row[c]) for c in RET_COLS)

        # Acumular impuestos por categoría
        impuestos_detalle = {}
        for col_excel, categoria in COLUMNA_A_CATEGORIA.items():
            val = _f(row[col_excel])
            if val > 0.5:
                impuestos_detalle[categoria] = impuestos_detalle.get(categoria, 0) + val

        tarifa = _clasificar_tarifa(iva, inc, total, otros, ret)
        base = _calcular_base(tarifa, iva, inc, total, otros, ret)

        # Fecha
        fe = row.get("fecha_emision")
        try:
            fecha = fe.date() if hasattr(fe, "date") else fe
        except Exception:
            fecha = date.today()
        if fecha is None or pd.isna(fecha):
            fecha = date.today()

        # Buscar cuenta en mapeo
        info_map = mapeo.get(nit_emisor, {})
        cuenta_gasto = info_map.get("cuenta_gasto")
        cuenta_nombre = info_map.get("cuenta_nombre")

        compra = CompraToken(
            cufe=cufe, folio=folio, prefijo=prefijo,
            fecha=fecha, tipo_doc=tipo_doc,
            nit_emisor=nit_emisor, nombre_emisor=nombre_emisor,
            total=total, iva=iva, inc=inc, otros=otros, ret=ret,
            tarifa=tarifa, base_calc=base,
            cuenta_gasto=cuenta_gasto,
            cuenta_nombre=cuenta_nombre,
            impuestos_detalle=impuestos_detalle,
        )

        # Las NCs recibidas van aparte (revierten compra previa)
        if tipo_doc == TIPO_NC:
            resultado.notas_credito.append(compra)
            continue

        if tarifa == "MIXTA":
            resultado.mixtas.append(compra)
            continue

        if not cuenta_gasto:
            resultado.sin_cuenta.append(compra)
            continue

        resultado.procesadas.append(compra)

        # Generar líneas del asiento
        filas_plano.extend(_generar_lineas_compra(compra, cc_default))

    if filas_plano:
        resultado.plano_df = pd.DataFrame(filas_plano, columns=COLUMNAS_PLANO)
        resultado.plano_lineas = len(filas_plano)
    else:
        resultado.plano_df = pd.DataFrame(columns=COLUMNAS_PLANO)
        resultado.plano_lineas = 0

    # Aplicar numeración consecutiva por comprobante (DOCUMENTO=1,2,3... DOC REFERENCIA=folio sin prefijo)
    if resultado.plano_df is not None and len(resultado.plano_df) > 0:
        from .numerador_comprobantes import aplicar_numeracion
        resultado.plano_df = aplicar_numeracion(resultado.plano_df)

    return resultado


def _generar_lineas_compra(c: CompraToken, cc: str) -> List[dict]:
    """
    Asiento estándar de compra:
        Db CUENTA GASTO         base
        Db IVA DESCONTABLE      iva (si > 0)
        Db INC pagado           inc (si > 0)
        Db Otros impuestos      otros (si > 0)
        Cr Proveedores          total + ret  (porque ret se va luego por separado)

    Las retenciones se omiten por ahora (van por otro flujo de retención
    en la fuente). Asiento simplificado: total = base + iva + inc + otros.
    """
    fecha_str = c.fecha.strftime("%m/%d/%Y")
    doc = f"{c.prefijo}{c.folio}" if c.prefijo else c.folio
    detalle = f"COMPRA {c.nombre_emisor[:35]} ({doc})"

    out = []

    # Db cuenta gasto
    out.append({
        "CUENTA": c.cuenta_gasto,
        "COMPROBANTE": COMPROBANTE_COMPRAS,
        "FECHA": fecha_str,
        "DOCUMENTO": doc,
        "DOC REFERENCIA": "",
        "NIT": c.nit_emisor,
        "DETALLE": detalle,
        "TR": TR_DEBITO,
        "VALOR": round(c.base_calc, 0),
        "BASE": "",
        "CENTRO DE COSTO": cc,
    })

    # Db IVA descontable
    if c.iva > 0:
        cuenta_iva = CUENTAS_IVA_DESCONTABLE.get(c.tarifa, CUENTAS_IVA_DESCONTABLE["19%"])
        out.append({
            "CUENTA": cuenta_iva,
            "COMPROBANTE": COMPROBANTE_COMPRAS,
            "FECHA": fecha_str,
            "DOCUMENTO": doc,
            "DOC REFERENCIA": "",
            "NIT": c.nit_emisor,
            "DETALLE": f"IVA {c.tarifa} DESC - {detalle}",
            "TR": TR_DEBITO,
            "VALOR": round(c.iva, 0),
            "BASE": round(c.base_calc, 0),
            "CENTRO DE COSTO": cc,
        })

    # Db INC pagado (si fuera el caso de compra a restaurante: poco común)
    if c.inc > 0:
        out.append({
            "CUENTA": CUENTA_INC_COMPRAS,
            "COMPROBANTE": COMPROBANTE_COMPRAS,
            "FECHA": fecha_str,
            "DOCUMENTO": doc,
            "DOC REFERENCIA": "",
            "NIT": c.nit_emisor,
            "DETALLE": f"INC pagado - {detalle}",
            "TR": TR_DEBITO,
            "VALOR": round(c.inc, 0),
            "BASE": round(c.base_calc, 0),
            "CENTRO DE COSTO": cc,
        })

    # Db impuestos discriminados (saludable, consumo, licores, etc.)
    for categoria, valor in (c.impuestos_detalle or {}).items():
        if valor <= 0.5:
            continue
        cuenta = CUENTAS_IMPUESTOS_COMPRAS.get(categoria, "24959501")
        nombre = NOMBRES_CATEGORIA.get(categoria, categoria.upper())
        out.append({
            "CUENTA": cuenta,
            "COMPROBANTE": COMPROBANTE_COMPRAS,
            "FECHA": fecha_str,
            "DOCUMENTO": doc,
            "DOC REFERENCIA": "",
            "NIT": c.nit_emisor,
            "DETALLE": f"{nombre} - {detalle}",
            "TR": TR_DEBITO,
            "VALOR": round(valor, 0),
            "BASE": round(c.base_calc, 0),
            "CENTRO DE COSTO": cc,
        })

    # Cr Proveedores (incluye retenciones para que cuadre con base+iva+inc+otros)
    cr_total = c.base_calc + c.iva + c.inc + c.otros
    # Retenciones (negativas) reducirían el Cr al proveedor:
    # Cr_proveedor = total + ret (porque ret es negativo)
    # Pero esto requiere generar líneas Cr retención también. Por ahora simplificamos:
    # Cr proveedor = base + iva + inc + otros (igual que Db total)
    out.append({
        "CUENTA": CUENTA_PROVEEDORES,
        "COMPROBANTE": COMPROBANTE_COMPRAS,
        "FECHA": fecha_str,
        "DOCUMENTO": doc,
        "DOC REFERENCIA": "",
        "NIT": c.nit_emisor,
        "DETALLE": detalle,
        "TR": TR_CREDITO,
        "VALOR": round(cr_total, 0),
        "BASE": "",
        "CENTRO DE COSTO": cc,
    })

    return out


def dataframe_a_plano_tsv(df: pd.DataFrame) -> str:
    """Exporta el plano a TSV."""
    if df is None or len(df) == 0:
        return ""
    return df.to_csv(sep="\t", index=False)


# ════════════════════════════════════════════════════════════════════
# v2: con motor de retenciones
# ════════════════════════════════════════════════════════════════════

def procesar_compras_v2(
    df_excel: pd.DataFrame,
    ruta_mapeo_historico: str,
    ruta_tabla_retenciones: str,
    ruta_mapeo_concepto: str,
    ruta_maestro_terceros: Optional[str] = None,
    cc_default: str = CC_PRINCIPAL,
) -> "ResultadoCompras":
    """
    Procesa compras con:
      - mapeo NIT → cuenta gasto (histórico balance)
      - retención en la fuente (según concepto + régimen + fecha)
      - reteIVA (a RST)
      - Maestro de terceros para identificar régimen (default R-99-PN si no está)

    Genera las líneas Cr de retención dentro del mismo asiento.
    """
    from .motor_retenciones import MotorRetenciones
    from . import maestro_terceros as mt

    resultado = ResultadoCompras()

    mapeo_cuenta = cargar_mapeo_historico(ruta_mapeo_historico)
    motor = MotorRetenciones(ruta_tabla_retenciones, ruta_mapeo_concepto)
    maestro = mt.cargar_maestro_terceros(ruta_maestro_terceros) if ruta_maestro_terceros else {"terceros": {}}

    # Filtrar recibidos
    df = df_excel[df_excel["grupo"].str.lower() == "recibido"].copy()
    df = df[~df["tipo_documento"].isin(TIPOS_EXCLUIR)]
    if len(df) == 0:
        resultado.plano_df = pd.DataFrame(columns=COLUMNAS_PLANO)
        return resultado

    OTROS_COLS = ["ICA", "IC", "Timbre", "INC Bolsas", "IN Carbono",
                  "IN Combustibles", "IC Datos", "ICL", "INPP", "IBUA", "ICUI"]
    RET_COLS = ["Rete IVA", "Rete Renta", "Rete ICA"]
    for c in ["IVA", "INC"] + OTROS_COLS + RET_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
        else:
            df[c] = 0

    filas_plano = []
    retenciones_aplicadas = []  # para resumen

    for _, row in df.iterrows():
        cufe = str(row.get("cufe", "")).strip()
        folio = str(row.get("folio", "")).strip()
        prefijo = str(row.get("prefijo", "")).strip().upper()
        tipo_doc = row.get("tipo_documento", "")
        nit_emisor = _normalizar_nit(row.get("nit_emisor", ""))
        nombre_emisor = str(row.get("nombre_emisor", "")).strip()
        total = _f(row.get("total", 0))
        iva = _f(row["IVA"])
        inc = _f(row["INC"])
        otros = sum(_f(row[c]) for c in OTROS_COLS)
        ret = sum(_f(row[c]) for c in RET_COLS)

        # Acumular impuestos por categoría (saludable, consumo, licores, etc.)
        impuestos_detalle = {}
        for col_excel, categoria in COLUMNA_A_CATEGORIA.items():
            val = _f(row[col_excel])
            if val > 0.5:
                impuestos_detalle[categoria] = impuestos_detalle.get(categoria, 0) + val

        tarifa = _clasificar_tarifa(iva, inc, total, otros, ret)
        base = _calcular_base(tarifa, iva, inc, total, otros, ret)

        fe = row.get("fecha_emision")
        try:
            fecha = fe.date() if hasattr(fe, "date") else fe
        except Exception:
            fecha = date.today()
        if fecha is None or pd.isna(fecha):
            fecha = date.today()

        info_map = mapeo_cuenta.get(nit_emisor, {})
        cuenta_gasto = info_map.get("cuenta_gasto")
        cuenta_nombre = info_map.get("cuenta_nombre")

        compra = CompraToken(
            cufe=cufe, folio=folio, prefijo=prefijo,
            fecha=fecha, tipo_doc=tipo_doc,
            nit_emisor=nit_emisor, nombre_emisor=nombre_emisor,
            total=total, iva=iva, inc=inc, otros=otros, ret=ret,
            tarifa=tarifa, base_calc=base,
            cuenta_gasto=cuenta_gasto,
            cuenta_nombre=cuenta_nombre,
            impuestos_detalle=impuestos_detalle,
        )

        if tipo_doc == TIPO_NC:
            resultado.notas_credito.append(compra)
            continue
        if tarifa == "MIXTA":
            resultado.mixtas.append(compra)
            continue
        if not cuenta_gasto:
            resultado.sin_cuenta.append(compra)
            continue

        # Calcular retenciones
        regimen = mt.regimen_proveedor(maestro, nit_emisor, default="R-99-PN")
        res_retencion = motor.calcular(
            fecha_factura=fecha,
            base_gravable=base,
            iva=iva,
            cuenta_gasto=cuenta_gasto,
            regimen_proveedor=regimen,
            declarante=True,  # asumimos declarante por defecto
        )

        if res_retencion.aplica_retefuente or res_retencion.aplica_reteiva:
            retenciones_aplicadas.append({
                "nit": nit_emisor,
                "nombre": nombre_emisor,
                "concepto": res_retencion.concepto_retencion,
                "regimen": regimen,
                "retefuente": res_retencion.valor_retefuente,
                "reteiva": res_retencion.valor_reteiva,
            })

        resultado.procesadas.append(compra)
        filas_plano.extend(_generar_lineas_compra_con_retencion(compra, cc_default, res_retencion))

    if filas_plano:
        resultado.plano_df = pd.DataFrame(filas_plano, columns=COLUMNAS_PLANO)
        resultado.plano_lineas = len(filas_plano)
    else:
        resultado.plano_df = pd.DataFrame(columns=COLUMNAS_PLANO)

    # Aplicar numeración consecutiva por comprobante
    if resultado.plano_df is not None and len(resultado.plano_df) > 0:
        from .numerador_comprobantes import aplicar_numeracion
        resultado.plano_df = aplicar_numeracion(resultado.plano_df)

    # Agregar resumen de retenciones al resultado
    resultado.retenciones_aplicadas = retenciones_aplicadas
    total_retefuente = sum(r["retefuente"] for r in retenciones_aplicadas)
    total_reteiva = sum(r["reteiva"] for r in retenciones_aplicadas)
    resultado.total_retefuente = total_retefuente
    resultado.total_reteiva = total_reteiva

    return resultado


def _generar_lineas_compra_con_retencion(c: "CompraToken", cc: str, res_ret) -> List[dict]:
    """
    Asiento completo de compra con retenciones:
        Db CUENTA GASTO            base
        Db IVA DESCONTABLE         iva
        Db INC pagado              inc (si)
        Db Otros impuestos         otros (si)
        Cr PROVEEDORES             total - retefuente - reteiva
        Cr RETEFUENTE              retefuente (si aplica)
        Cr RETEIVA                 reteiva (si aplica)
    """
    fecha_str = c.fecha.strftime("%m/%d/%Y")
    doc = f"{c.prefijo}{c.folio}" if c.prefijo else c.folio
    detalle = f"COMPRA {c.nombre_emisor[:35]} ({doc})"

    out = []

    # Db cuenta gasto
    out.append({
        "CUENTA": c.cuenta_gasto,
        "COMPROBANTE": COMPROBANTE_COMPRAS,
        "FECHA": fecha_str,
        "DOCUMENTO": doc,
        "DOC REFERENCIA": "",
        "NIT": c.nit_emisor,
        "DETALLE": detalle,
        "TR": TR_DEBITO,
        "VALOR": round(c.base_calc, 0),
        "BASE": "",
        "CENTRO DE COSTO": cc,
    })

    # Db IVA descontable
    if c.iva > 0:
        cuenta_iva = CUENTAS_IVA_DESCONTABLE.get(c.tarifa, CUENTAS_IVA_DESCONTABLE["19%"])
        out.append({
            "CUENTA": cuenta_iva,
            "COMPROBANTE": COMPROBANTE_COMPRAS,
            "FECHA": fecha_str,
            "DOCUMENTO": doc,
            "DOC REFERENCIA": "",
            "NIT": c.nit_emisor,
            "DETALLE": f"IVA {c.tarifa} DESC - {detalle}",
            "TR": TR_DEBITO,
            "VALOR": round(c.iva, 0),
            "BASE": round(c.base_calc, 0),
            "CENTRO DE COSTO": cc,
        })

    # Db INC pagado
    if c.inc > 0:
        out.append({
            "CUENTA": CUENTA_INC_COMPRAS,
            "COMPROBANTE": COMPROBANTE_COMPRAS,
            "FECHA": fecha_str,
            "DOCUMENTO": doc,
            "DOC REFERENCIA": "",
            "NIT": c.nit_emisor,
            "DETALLE": f"INC pagado - {detalle}",
            "TR": TR_DEBITO,
            "VALOR": round(c.inc, 0),
            "BASE": round(c.base_calc, 0),
            "CENTRO DE COSTO": cc,
        })

    # Db impuestos discriminados (UNA LÍNEA POR CATEGORÍA con valor>0)
    # Categorías: saludable (IBUA+ICUI), consumo (IC+INC Bolsas), licores (ICL),
    # ica, carbono, combustibles, datos, inpp, timbre.
    for categoria, valor in (c.impuestos_detalle or {}).items():
        if valor <= 0.5:
            continue
        cuenta = CUENTAS_IMPUESTOS_COMPRAS.get(categoria, "24959501")
        nombre = NOMBRES_CATEGORIA.get(categoria, categoria.upper())
        out.append({
            "CUENTA": cuenta,
            "COMPROBANTE": COMPROBANTE_COMPRAS,
            "FECHA": fecha_str,
            "DOCUMENTO": doc,
            "DOC REFERENCIA": "",
            "NIT": c.nit_emisor,
            "DETALLE": f"{nombre} - {detalle}",
            "TR": TR_DEBITO,
            "VALOR": round(valor, 0),
            "BASE": round(c.base_calc, 0),
            "CENTRO DE COSTO": cc,
        })

    # Calcular Cr proveedor (descontando retenciones)
    cr_total = c.base_calc + c.iva + c.inc + c.otros
    if res_ret.aplica_retefuente:
        cr_total -= res_ret.valor_retefuente
    if res_ret.aplica_reteiva:
        cr_total -= res_ret.valor_reteiva

    # Cr Proveedores (neto a pagar)
    out.append({
        "CUENTA": CUENTA_PROVEEDORES,
        "COMPROBANTE": COMPROBANTE_COMPRAS,
        "FECHA": fecha_str,
        "DOCUMENTO": doc,
        "DOC REFERENCIA": "",
        "NIT": c.nit_emisor,
        "DETALLE": detalle,
        "TR": TR_CREDITO,
        "VALOR": round(cr_total, 0),
        "BASE": "",
        "CENTRO DE COSTO": cc,
    })

    # Cr Retefuente (si aplica)
    if res_ret.aplica_retefuente:
        out.append({
            "CUENTA": res_ret.cuenta_retefuente_puc,
            "COMPROBANTE": COMPROBANTE_COMPRAS,
            "FECHA": fecha_str,
            "DOCUMENTO": doc,
            "DOC REFERENCIA": "",
            "NIT": c.nit_emisor,
            "DETALLE": f"RETEF {res_ret.concepto_retencion} {res_ret.tarifa_retefuente*100:.1f}% - {detalle}",
            "TR": TR_CREDITO,
            "VALOR": round(res_ret.valor_retefuente, 0),
            "BASE": round(c.base_calc, 0),
            "CENTRO DE COSTO": cc,
        })

    # Cr ReteIVA (si aplica)
    if res_ret.aplica_reteiva:
        out.append({
            "CUENTA": res_ret.cuenta_reteiva_puc,
            "COMPROBANTE": COMPROBANTE_COMPRAS,
            "FECHA": fecha_str,
            "DOCUMENTO": doc,
            "DOC REFERENCIA": "",
            "NIT": c.nit_emisor,
            "DETALLE": f"RETEIVA 15% RST - {detalle}",
            "TR": TR_CREDITO,
            "VALOR": round(res_ret.valor_reteiva, 0),
            "BASE": round(c.iva, 0),
            "CENTRO DE COSTO": cc,
        })

    return out
