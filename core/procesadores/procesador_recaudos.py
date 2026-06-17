"""
core/procesadores/procesador_recaudos.py

Recaudos de tesorería (Comprobantes de Ingreso de bittal) -> plano Contai.
Declarativo: el comportamiento de cada "Medio de Pago" sale del MAPEO, no del
código. Agregar/cambiar un canal = editar el diccionario (idealmente en la
config de la empresa).

Reglas (segun lo definido):
  - Cada franquicia suma TC + TD en UN registro por DIA.
  - Transferencia: UN registro por cada movimiento.
  - Efectivo, Cruce de Cuentas y Pago Docto: NO aplican (se excluyen).
"""
from __future__ import annotations

import io
from datetime import date
from typing import Tuple, List

import pandas as pd

COLUMNAS_PLANO = [
    "CUENTA", "COMPROBANTE", "FECHA", "DOCUMENTO", "DOC REFERENCIA",
    "NIT", "DETALLE", "TR", "VALOR", "BASE", "CENTRO DE COSTO",
]
TR_DEBITO, TR_CREDITO = "1", "2"

# ----------------------------------------------------------------------
# MAPEO (esto vive idealmente en core/data/empresas/<NIT>/recaudos.json)
# ----------------------------------------------------------------------
MAPEO = {
    # >>> PENDIENTES de confirmar <<<
    "comprobante": "1",                             # comprobante Contai de ingresos
    "contrapartida_cuenta": "11050500",             # Cr: CAJA (traslado caja -> banco)
    "contrapartida_nit": "",                        # cuentas de balance: sin tercero
    "valor_col": "Valor Documento",                 # o "Valor En Dinero"
    # medio de pago -> (grupo, cuenta banco Db, modo)
    "canales": {
        "TRANSFERENCIA":              {"grupo": "TRANSFERENCIA", "banco": "11100500", "modo": "movimiento"},
        "TC AMEX":                    {"grupo": "AMEX",          "banco": "11100500", "modo": "dia"},
        "TC Dinners Club":            {"grupo": "DINERS",        "banco": "11100500", "modo": "dia"},
        "TC MASTER":                  {"grupo": "MASTER",        "banco": "11100501", "modo": "dia"},
        "TD MASTER":                  {"grupo": "MASTER",        "banco": "11100501", "modo": "dia"},
        "TC VISA":                    {"grupo": "VISA",          "banco": "11100501", "modo": "dia"},
        "TD VISA":                    {"grupo": "VISA",          "banco": "11100501", "modo": "dia"},
        # PENDIENTES (cuenta/modo por definir):
        "TRANSFERENCIA ADDI":         {"grupo": "ADDI",          "banco": "13050501", "modo": "movimiento", "nit": "tercero"},
        "TRANSFERENCIA MERCADO PAGO": {"grupo": "MERCADOPAGO",   "banco": "PENDIENTE", "modo": "movimiento"},
    },
    "excluir": ["EFECTIVO", "CRUCE CUENTAS", "PAGO DOCTO"],
    "centro": "",  # si manejas centro de costo en recaudos
}


def _fecha_mmddaaaa(d) -> str:
    d = pd.to_datetime(d)
    return f"{d.month:02d}/{d.day:02d}/{d.year}"


def _entero(v) -> str:
    return str(int(round(float(v))))


def procesar_recaudos(archivo, mapeo: dict = MAPEO) -> Tuple[pd.DataFrame, List[str], dict]:
    """Lee el Excel de Comprobantes de Ingreso y arma el plano de recaudos."""
    log: List[str] = []
    df = pd.read_excel(archivo, sheet_name="Documentos")
    log.append(f"📂 Filas leídas: {len(df)}")

    # filtrar anuladas
    if "Anulado" in df.columns:
        antes = len(df)
        df = df[df["Anulado"].isna() | (df["Anulado"] == False)]
        if antes - len(df):
            log.append(f"  ⚠️ Anuladas filtradas: {antes - len(df)}")

    canales = mapeo["canales"]
    valor_col = mapeo["valor_col"]
    comp = mapeo["comprobante"]
    cr_cta = mapeo["contrapartida_cuenta"]
    cr_nit = mapeo["contrapartida_nit"]
    centro = mapeo.get("centro", "")

    # clasificar y excluir
    df["_medio"] = df["Medio de Pago"].astype(str).str.strip()
    excluidos = df[df["_medio"].isin(mapeo["excluir"])]
    if len(excluidos):
        log.append(f"  ⏭️ Excluidos (no aplican): {len(excluidos)} "
                   f"({', '.join(sorted(excluidos['_medio'].unique()))})")
    sin_map = df[~df["_medio"].isin(canales) & ~df["_medio"].isin(mapeo["excluir"])]
    if len(sin_map):
        log.append(f"  ❓ Medios sin mapear (se ignoran): "
                   f"{', '.join(sorted(sin_map['_medio'].unique()))}")

    df = df[df["_medio"].isin(canales)].copy()
    df["_grupo"] = df["_medio"].map(lambda m: canales[m]["grupo"])
    df["_banco"] = df["_medio"].map(lambda m: canales[m]["banco"])
    df["_modo"] = df["_medio"].map(lambda m: canales[m]["modo"])
    df["_fecha"] = pd.to_datetime(df["Fecha"]).dt.date
    df["_valor"] = pd.to_numeric(df[valor_col], errors="coerce").fillna(0.0)

    filas: List[dict] = []

    # --- construir todas las líneas DÉBITO (cada recaudo), con su fecha ---
    debitos = []  # {fecha, banco, valor, nit, detalle}

    # transferencias y Addi: por movimiento (Addi lleva NIT del tercero)
    mov = df[df["_modo"] == "movimiento"]
    for _, r in mov.iterrows():
        usa_tercero = canales[r["_medio"]].get("nit") == "tercero"
        nit_deb = str(r.get("NIT", "")).split(".")[0] if usa_tercero else cr_nit
        debitos.append({"fecha": r["_fecha"], "banco": r["_banco"],
                        "valor": float(r["_valor"]), "nit": nit_deb,
                        "detalle": f"Recaudo {r['_grupo']}"})

    # franquicias: TC+TD del grupo sumadas en un registro por día
    dia = df[df["_modo"] == "dia"]
    g = dia.groupby(["_grupo", "_banco", "_fecha"], as_index=False)["_valor"].sum()
    for _, r in g.iterrows():
        debitos.append({"fecha": r["_fecha"], "banco": r["_banco"],
                        "valor": float(r["_valor"]), "nit": cr_nit,
                        "detalle": f"Recaudo {r['_grupo']} del día"})

    # --- emitir por DOCUMENTO (= día): N débitos + 1 ÚNICO crédito a caja por el total ---
    from itertools import groupby
    debitos.sort(key=lambda x: (x["fecha"], x["banco"]))
    for fecha, items_iter in groupby(debitos, key=lambda x: x["fecha"]):
        items = list(items_iter)
        doc = str(pd.to_datetime(fecha).day)        # documento y doc. ref = día del mes
        f_str = _fecha_mmddaaaa(fecha)
        total = 0
        for it in items:
            v = int(round(it["valor"]))
            total += v
            filas.append({"CUENTA": it["banco"], "COMPROBANTE": comp, "FECHA": f_str,
                          "DOCUMENTO": doc, "DOC REFERENCIA": doc, "NIT": it["nit"],
                          "DETALLE": it["detalle"], "TR": TR_DEBITO, "VALOR": str(v),
                          "BASE": "", "CENTRO DE COSTO": centro})
        # un solo crédito por documento = suma de los débitos del día
        filas.append({"CUENTA": cr_cta, "COMPROBANTE": comp, "FECHA": f_str,
                      "DOCUMENTO": doc, "DOC REFERENCIA": doc, "NIT": cr_nit,
                      "DETALLE": "Recaudo del día", "TR": TR_CREDITO, "VALOR": str(total),
                      "BASE": "", "CENTRO DE COSTO": centro})

    plano = pd.DataFrame(filas, columns=COLUMNAS_PLANO)
    total_db = sum(int(x["VALOR"]) for x in filas if x["TR"] == TR_DEBITO)
    total_cr = sum(int(x["VALOR"]) for x in filas if x["TR"] == TR_CREDITO)
    documentos = len({x["DOCUMENTO"] for x in filas})
    resumen = {
        "lineas": len(plano),
        "documentos": documentos,
        "total_db": total_db,
        "total_cr": total_cr,
        "cuadra": total_db == total_cr,
        "por_grupo": dia.groupby("_grupo")["_valor"].sum().astype(int).to_dict(),
        "movimientos_transf_addi": len(mov),
    }
    log.append(f"✅ {documentos} documentos (días), Db={total_db:,} / Cr={total_cr:,} "
               f"({'cuadra' if total_db == total_cr else 'DESCUADRA'})")
    return plano, log, resumen


def dataframe_a_plano_tsv(df: pd.DataFrame, incluir_encabezado_excel: bool = True) -> bytes:
    out = df[COLUMNAS_PLANO].copy()
    for c in out.columns:
        out[c] = out[c].astype(str).str.replace("\t", " ", regex=False)
    tsv = out.to_csv(sep="\t", index=False, header=True, lineterminator="\r\n")
    if incluir_encabezado_excel:
        tsv = "sep=\t\r\n" + tsv
    return tsv.encode("utf-8")
