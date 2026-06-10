"""
P&G detallado mensual por Centro de Costos.

Replica la estructura de la plantilla "P&G mensual y acum" pero permite
generar una columna de meses (movimiento de cada mes) + Acumulado + A.V.
para CADA centro de costo (o consolidado).

Entradas:
    - Una lista de BalanceCC mensuales (uno por mes) de la MISMA empresa.
      El mes se detecta del campo `periodo` ("Ene-31-2026", ...).
    - Opcional: inventarios por mes y grupo (alimentos/aseo) para el costo
      de materia prima del consolidado.

Conceptos contables:
    - Movimiento del mes de una cuenta = Nuevo Saldo - Saldo Anterior del
      archivo de ese mes.
    - Acumulado = suma de los movimientos mensuales (= Nuevo Saldo del último
      mes, si el año arranca en enero).
    - A.V. (análisis vertical) = renglón_acumulado / total_ingresos_netos_acum.
    - Signos de presentación:
        * Ingresos operacionales (41): se muestran en positivo (= -saldo).
        * Costos y gastos operacionales (5,6,7): positivo (= +saldo).
        * No operacionales (42,43,53,55): ingresos en +, gastos en - (= -saldo).
    - Costo de materia prima = Inv. inicial (cta 14) + Compras (cta 71)
      - Inv. final (cta 14). La cta 14 no viene por CC: en las hojas por CC
      las filas de inventario quedan en 0; en el consolidado se usan los
      valores capturados en el formulario.
"""
from __future__ import annotations

from typing import List, Optional, Dict, Tuple
import re

import pandas as pd

from .reporte_centros_costos import BalanceCC, SIN_CC, ETIQUETA_TOTAL

_MESES = {
    "ene": (1, "Enero"), "feb": (2, "Febrero"), "mar": (3, "Marzo"),
    "abr": (4, "Abril"), "may": (5, "Mayo"), "jun": (6, "Junio"),
    "jul": (7, "Julio"), "ago": (8, "Agosto"), "sep": (9, "Septiembre"),
    "oct": (10, "Octubre"), "nov": (11, "Noviembre"), "dic": (12, "Diciembre"),
}


def _mes_de_periodo(periodo: str) -> Tuple[int, str]:
    m = re.match(r"\s*([A-Za-zÁÉÍÓÚáéíóú]{3})", periodo or "")
    if not m:
        return (99, periodo or "?")
    return _MESES.get(m.group(1).lower()[:3], (99, periodo))


# ------------------------------------------------------------------
# Definición de la plantilla (estructura de renglones)
# ------------------------------------------------------------------
# Cada renglón es una tupla (kind, label, opts):
#   "header"   -> título de sección (sin valores)
#   "blank"    -> fila en blanco
#   "line"     -> codigos=[...], signo="ing"|"egr"|"noop"
#   "inv"      -> key inventario (ini/fin), grupo; valor desde formulario
#   "sub"      -> mas=[labels], menos=[labels]
#   "ebitda"   -> mas=[labels]
# "otros_de" en una line indica grupo del que toma el remanente
#   (total del grupo menos lo ya nombrado).

def _plantilla(con_mil: bool = False, mil: str = "Milagros"):
    L = []
    A = L.append

    def linea_con_mil(label, opts, mil_label, mil_opts, en_subtotal):
        """Agrega la línea principal y (si aplica) su línea Milagros.
        Devuelve la lista de labels que alimentan el subtotal."""
        A(("line", label, opts))
        feeds = [label]
        if con_mil:
            A(("mil", mil_label, mil_opts))
            feeds.append(mil_label)
        en_subtotal.extend(feeds)

    A(("header", "INGRESOS OPERACIONALES", {}))
    ing_feed = []
    A(("line", "   Industrias manufactureras (panadería) [4120]", {"cod": ["4120"], "s": "ing"}))
    ing_feed.append("   Industrias manufactureras (panadería) [4120]")
    A(("line", "   Hoteles y restaurantes [4140]", {"cod": ["4140"], "s": "ing"}))
    ing_feed.append("   Hoteles y restaurantes [4140]")
    A(("line", "   (–) Devoluciones en ventas [4175]", {"cod": ["4175"], "s": "ing"}))
    ing_feed.append("   (–) Devoluciones en ventas [4175]")
    A(("line", "   Otros ingresos operacionales", {"cod": ["41"], "s": "ing",
                                                   "otros_menos": ["4120", "4140", "4175"]}))
    ing_feed.append("   Otros ingresos operacionales")
    if con_mil:
        A(("mil", f"   Ventas restaurantes {mil}", {"cod": ["41"], "s": "ing"}))
        ing_feed.append(f"   Ventas restaurantes {mil}")
    A(("sub", "Total ingresos operacionales (netos)", {"mas": list(ing_feed)}))
    A(("blank", "", {}))

    A(("header", "COSTO DE VENTAS Y DE PRODUCCIÓN", {}))
    A(("header", "Costo de materia prima (cuentas 14 y 71)", {}))
    A(("subhdr", "   Alimentos y bebidas", {}))
    alim_feed = []
    A(("inv", "      (+) Inventario inicial alimentos/bebidas [14050501]", {"grupo": "alim", "tipo": "ini"}))
    alim_feed.append("      (+) Inventario inicial alimentos/bebidas [14050501]")
    A(("line", "      (+) Compras de alimentos [710501]", {"cod": ["710501"], "s": "egr"}))
    alim_feed.append("      (+) Compras de alimentos [710501]")
    A(("line", "      (+) Compras de bebidas, vinos y licores [710502]", {"cod": ["710502"], "s": "egr"}))
    alim_feed.append("      (+) Compras de bebidas, vinos y licores [710502]")
    if con_mil:
        A(("mil", f"      (+) Compras alimentos y bebidas {mil}", {"cod": ["710501", "710502"], "s": "egr"}))
        alim_feed.append(f"      (+) Compras alimentos y bebidas {mil}")
    A(("inv", "      (–) Inventario final alimentos/bebidas [14050501]", {"grupo": "alim", "tipo": "fin"}))
    alim_feed.append("      (–) Inventario final alimentos/bebidas [14050501]")
    A(("sub", "   Costo alimentos y bebidas", {"mas": list(alim_feed)}))

    A(("subhdr", "   Aseo y cafetería", {}))
    aseo_feed = []
    A(("inv", "      (+) Inventario inicial aseo/cafetería [14050502]", {"grupo": "aseo", "tipo": "ini"}))
    aseo_feed.append("      (+) Inventario inicial aseo/cafetería [14050502]")
    A(("line", "      (+) Compras cafetería y empaque [710503]", {"cod": ["710503"], "s": "egr"}))
    aseo_feed.append("      (+) Compras cafetería y empaque [710503]")
    A(("line", "      (+) Compras de aseo [710504]", {"cod": ["710504"], "s": "egr"}))
    aseo_feed.append("      (+) Compras de aseo [710504]")
    if con_mil:
        A(("mil", f"      (+) Compras cafetería y aseo {mil}", {"cod": ["710503", "710504"], "s": "egr"}))
        aseo_feed.append(f"      (+) Compras cafetería y aseo {mil}")
    A(("inv", "      (–) Inventario final aseo/cafetería [14050502]", {"grupo": "aseo", "tipo": "fin"}))
    aseo_feed.append("      (–) Inventario final aseo/cafetería [14050502]")
    A(("sub", "   Costo aseo y cafetería", {"mas": list(aseo_feed)}))
    A(("line", "   Traslados de alimentos / otras compras [710595]",
       {"cod": ["71"], "s": "egr", "otros_menos": ["710501", "710502", "710503", "710504"]}))
    A(("sub", "Total costo de materia prima",
       {"mas": ["   Costo alimentos y bebidas", "   Costo aseo y cafetería",
                "   Traslados de alimentos / otras compras [710595]"]}))
    A(("blank", "", {}))

    A(("header", "Costo de mano de obra (cuenta 72)", {}))
    mo_feed = []
    for nom, cod in [("Aportes sobre la nómina", "7204"), ("Costo de personal", "7205"),
                     ("Costo personal temporal", "7235")]:
        A(("line", f"   {nom} [{cod}]", {"cod": [cod], "s": "egr"})); mo_feed.append(f"   {nom} [{cod}]")
    A(("line", "   Otros costos de mano de obra", {"cod": ["72"], "s": "egr",
                                                   "otros_menos": ["7204", "7205", "7235"]}))
    mo_feed.append("   Otros costos de mano de obra")
    if con_mil:
        A(("mil", f"   Mano de obra {mil}", {"cod": ["72"], "s": "egr"})); mo_feed.append(f"   Mano de obra {mil}")
    A(("sub", "Total costo de mano de obra", {"mas": list(mo_feed)}))
    A(("blank", "", {}))

    A(("header", "Costos indirectos de fabricación (cuenta 73)", {}))
    cif = [("Honorarios", "7310"), ("Impuestos", "7315"), ("Arrendamiento", "7320"),
           ("Afiliaciones y sostenimiento", "7325"), ("Seguros", "7330"),
           ("Servicios", "7335"), ("Trámites y licencias", "7340"),
           ("Mantenimiento y reparaciones", "7345"), ("Adecuación e instalación", "7350"),
           ("Costo de viajes", "7355"), ("Depreciaciones", "7360"),
           ("Amortización", "7365"), ("Diversos", "7395")]
    cif_feed = []
    for nom, cod in cif:
        A(("line", f"   {nom} [{cod}]", {"cod": [cod], "s": "egr"})); cif_feed.append(f"   {nom} [{cod}]")
    A(("line", "   Otros costos indirectos", {"cod": ["73"], "s": "egr",
                                              "otros_menos": [c for _, c in cif]}))
    cif_feed.append("   Otros costos indirectos")
    if con_mil:
        A(("mil", f"   Costos indirectos {mil}", {"cod": ["73"], "s": "egr"})); cif_feed.append(f"   Costos indirectos {mil}")
    A(("sub", "Total costos indirectos de fabricación", {"mas": list(cif_feed)}))
    A(("blank", "", {}))

    A(("header", "Costo de ventas — mercancía (clase 6)", {}))
    c6_feed = []
    A(("line", "   Costo de mercancía vendida [6]", {"cod": ["6"], "s": "egr"})); c6_feed.append("   Costo de mercancía vendida [6]")
    if con_mil:
        A(("mil", f"   Costo de mercancía {mil}", {"cod": ["6"], "s": "egr"})); c6_feed.append(f"   Costo de mercancía {mil}")
    A(("trasl", "   (+) Traslado alimentos desde producción", {"grupo": "alim"})); c6_feed.append("   (+) Traslado alimentos desde producción")
    A(("trasl", "   (+) Traslado aseo desde producción", {"grupo": "aseo"})); c6_feed.append("   (+) Traslado aseo desde producción")
    A(("sub", "Total costo de ventas (clase 6) y traslados", {"mas": list(c6_feed)}))
    A(("blank", "", {}))

    A(("sub", "TOTAL COSTO DE VENTAS Y DE PRODUCCIÓN",
       {"mas": ["Total costo de materia prima", "Total costo de mano de obra",
                "Total costos indirectos de fabricación", "Total costo de ventas (clase 6) y traslados"]}))
    A(("blank", "", {}))
    A(("sub", "UTILIDAD BRUTA",
       {"mas": ["Total ingresos operacionales (netos)"],
        "menos": ["TOTAL COSTO DE VENTAS Y DE PRODUCCIÓN"]}))
    A(("blank", "", {}))

    A(("header", "GASTOS OPERACIONALES DE ADMINISTRACIÓN", {}))
    adm = [("Aportes sobre la nómina", "5104"), ("Gastos de personal", "5105"),
           ("Honorarios", "5110"), ("Impuestos", "5115"), ("Arrendamientos", "5120"),
           ("Afiliaciones y sostenimiento", "5125"), ("Servicios", "5135"),
           ("Gastos legales", "5140"), ("Mantenimiento y reparaciones", "5145"),
           ("Adecuación e instalación", "5150"), ("Gastos de viaje", "5155"),
           ("Depreciación", "5160"), ("Amortización", "5165"), ("Diversos", "5195")]
    adm_feed = []
    for nom, cod in adm:
        A(("line", f"   {nom} [{cod}]", {"cod": [cod], "s": "egr"})); adm_feed.append(f"   {nom} [{cod}]")
    A(("line", "   Otros gastos de administración", {"cod": ["51"], "s": "egr",
                                                     "otros_menos": [c for _, c in adm]}))
    adm_feed.append("   Otros gastos de administración")
    if con_mil:
        A(("mil", f"   Gastos de administración {mil}", {"cod": ["51"], "s": "egr"})); adm_feed.append(f"   Gastos de administración {mil}")
    A(("sub", "Total gastos de administración", {"mas": list(adm_feed)}))
    A(("blank", "", {}))

    A(("header", "GASTOS OPERACIONALES DE VENTAS", {}))
    ven = [("Impuestos", "5215"), ("Arrendamientos", "5220"),
           ("Publicidad, propaganda", "5235"), ("Comisiones", "5295")]
    ven_feed = []
    for nom, cod in ven:
        A(("line", f"   {nom} [{cod}]", {"cod": [cod], "s": "egr"})); ven_feed.append(f"   {nom} [{cod}]")
    A(("line", "   Otros gastos de ventas", {"cod": ["52"], "s": "egr",
                                             "otros_menos": [c for _, c in ven]}))
    ven_feed.append("   Otros gastos de ventas")
    if con_mil:
        A(("mil", f"   Gastos de ventas {mil}", {"cod": ["52"], "s": "egr"})); ven_feed.append(f"   Gastos de ventas {mil}")
    A(("sub", "Total gastos de ventas", {"mas": list(ven_feed)}))
    A(("blank", "", {}))
    A(("sub", "Total gastos operacionales",
       {"mas": ["Total gastos de administración", "Total gastos de ventas"]}))
    A(("blank", "", {}))
    A(("sub", "UTILIDAD OPERACIONAL",
       {"mas": ["UTILIDAD BRUTA"], "menos": ["Total gastos operacionales"]}))
    A(("blank", "", {}))

    A(("header", "INGRESOS Y GASTOS NO OPERACIONALES", {}))
    A(("subhdr", "Ingresos no operacionales (42) e ingresos financieros (43)", {}))
    noop_feed = []
    noi = [("Otras ventas", "4205"), ("Servicios", "4235"), ("Recuperaciones", "4250"),
           ("Diversos", "4295"), ("Financieros", "4310")]
    for nom, cod in noi:
        A(("line", f"   {nom} [{cod}]", {"cod": [cod], "s": "noop"})); noop_feed.append(f"   {nom} [{cod}]")
    A(("line", "   Otros ingresos no operacionales", {"cod": ["42", "43"], "s": "noop",
                                                      "otros_menos": [c for _, c in noi]}))
    noop_feed.append("   Otros ingresos no operacionales")
    if con_mil:
        A(("mil", f"   Ingresos no operacionales {mil}", {"cod": ["42", "43"], "s": "noop"})); noop_feed.append(f"   Ingresos no operacionales {mil}")
    A(("subhdr", "Gastos no operacionales y financieros (53) y otros (55)", {}))
    nog = [("Gastos financieros", "5305"), ("Intereses de mora", "5505"),
           ("Gastos extraordinarios", "5515"), ("Gastos diversos", "5595")]
    for nom, cod in nog:
        A(("line", f"   {nom} [{cod}]", {"cod": [cod], "s": "noop"})); noop_feed.append(f"   {nom} [{cod}]")
    A(("line", "   Otros gastos no operacionales", {"cod": ["53", "55"], "s": "noop",
                                                    "otros_menos": [c for _, c in nog]}))
    noop_feed.append("   Otros gastos no operacionales")
    if con_mil:
        A(("mil", f"   Gastos financieros {mil}", {"cod": ["53"], "s": "noop"})); noop_feed.append(f"   Gastos financieros {mil}")
        A(("mil", f"   Otros no operacionales {mil}", {"cod": ["55"], "s": "noop"})); noop_feed.append(f"   Otros no operacionales {mil}")
    A(("sub", "Total no operacional (neto)", {"mas": list(noop_feed)}))
    A(("blank", "", {}))
    A(("sub", "UTILIDAD ANTES DE IMPUESTOS",
       {"mas": ["UTILIDAD OPERACIONAL", "Total no operacional (neto)"]}))
    A(("line", "   (–) Provisión impuesto de renta [54]", {"cod": ["54"], "s": "egr"}))
    A(("sub", "UTILIDAD (PÉRDIDA) NETA DEL EJERCICIO",
       {"mas": ["UTILIDAD ANTES DE IMPUESTOS"],
        "menos": ["   (–) Provisión impuesto de renta [54]"]}))
    A(("blank", "", {}))
    A(("ebitda", "EBITDA",
       {"mas": ["UTILIDAD OPERACIONAL", "   Depreciaciones [7360]", "   Amortización [7365]",
                "   Depreciación [5160]", "   Amortización [5165]"]}))
    return L


# ------------------------------------------------------------------
# Cálculo
# ------------------------------------------------------------------

def _signo(s: str) -> float:
    # "ing" y "noop" invierten el saldo (crédito -> positivo); "egr" lo deja
    return -1.0 if s in ("ing", "noop") else 1.0


def _agg_mes(bal: BalanceCC, cc: Optional[str]) -> pd.DataFrame:
    """Detalle del mes filtrado por CC (o todos), con columna mov = ns - sa."""
    d = bal.detalle
    if cc is not None:
        d = d[d["cc"] == cc]
    return d[["cuenta", "nuevo_saldo", "mov_periodo"]].copy()


def _suma_codigos(d: pd.DataFrame, codigos, otros_menos=None) -> float:
    """Suma 'mov_periodo' de cuentas cuyo código empieza por alguno de `codigos`.

    Si `otros_menos` se da, devuelve (suma de codigos) - (suma de otros_menos):
    el remanente del grupo no nombrado.
    """
    if d.empty:
        return 0.0
    cod = d["cuenta"]
    mask = pd.Series(False, index=d.index)
    for c in codigos:
        mask |= cod.str.startswith(c)
    total = d.loc[mask, "mov_periodo"].sum()
    if otros_menos:
        m2 = pd.Series(False, index=d.index)
        for c in otros_menos:
            m2 |= cod.str.startswith(c)
        total -= d.loc[m2, "mov_periodo"].sum()
    return float(total)


def construir_pyg(balances: List[BalanceCC], balances_milagros: Optional[List[BalanceCC]] = None,
                  cc: Optional[str] = None, inventarios: Optional[Dict] = None,
                  traslados: Optional[Dict] = None, mil_label: str = "Milagros") -> pd.DataFrame:
    """Construye el P&G detallado.

    `balances`: BalanceCC mensuales de la empresa principal (Jiper).
    `balances_milagros`: BalanceCC mensuales de la empresa de operación a
       incorporar por concepto (mismos códigos de CC).
    `cc`: código de centro de costo, o None para consolidado.
    `inventarios`: dict {(grupo, cc_code, mes_num): {"ini": x, "fin": y}} con el
       inventario inicial/final por centro y mes. Para una hoja de CC usa ese
       CC; para el consolidado suma todos los CC. grupo ∈ {"alim","aseo"}.
    `traslados`: dict {(grupo, cc_code, mes_num): valor} con el traslado desde
       producción capturado manualmente. grupo ∈ {"alim","aseo"}. Para una hoja
       de CC usa el valor de ese CC; para el consolidado suma todos los CC.
    `mil_label`: etiqueta de las líneas incorporadas.

    Devuelve DataFrame: Concepto | <mes1> | ... | Acumulado | A.V. | _tipo
    """
    inventarios = inventarios or {}
    traslados = traslados or {}
    con_mil = bool(balances_milagros)
    plantilla = _plantilla(con_mil=con_mil, mil=mil_label)

    bal_ord = sorted(balances, key=lambda b: _mes_de_periodo(b.periodo)[0])
    meses = [(_mes_de_periodo(b.periodo)) for b in bal_ord]
    nombres_mes = [m[1] for m in meses]
    nums_mes = [m[0] for m in meses]
    dets = [_agg_mes(b, cc) for b in bal_ord]

    # detalle Milagros indexado por número de mes (mismos CC)
    mil_por_mes: Dict[int, pd.DataFrame] = {}
    if con_mil:
        for b in balances_milagros:
            mn = _mes_de_periodo(b.periodo)[0]
            mil_por_mes[mn] = _agg_mes(b, cc)

    valores: Dict[str, List[float]] = {}
    filas = []

    for kind, label, opts in plantilla:
        if kind in ("header", "subhdr", "blank"):
            filas.append({"Concepto": label, "_tipo": kind,
                          **{nm: None for nm in nombres_mes},
                          "Acumulado": None, "A.V.": None})
            continue

        vals = [0.0] * len(bal_ord)

        if kind == "line":
            sgn = _signo(opts["s"])
            for i, d in enumerate(dets):
                vals[i] = sgn * _suma_codigos(d, opts["cod"], opts.get("otros_menos"))

        elif kind == "mil":
            sgn = _signo(opts["s"])
            for i, mnum in enumerate(nums_mes):
                d = mil_por_mes.get(mnum)
                if d is not None:
                    vals[i] = sgn * _suma_codigos(d, opts["cod"], opts.get("otros_menos"))

        elif kind == "inv":
            grupo, tipo = opts["grupo"], opts["tipo"]
            signo = 1.0 if tipo == "ini" else -1.0
            for i, mnum in enumerate(nums_mes):
                if cc is not None:
                    info = inventarios.get((grupo, cc, mnum), {})
                    vals[i] = signo * float(info.get(tipo, 0.0) or 0.0)
                else:
                    tot = sum(float(d.get(tipo, 0.0) or 0.0)
                              for (g, _c, m), d in inventarios.items()
                              if g == grupo and m == mnum)
                    vals[i] = signo * tot

        elif kind == "trasl":
            grupo = opts["grupo"]
            for i, mnum in enumerate(nums_mes):
                if cc is not None:
                    vals[i] = float(traslados.get((grupo, cc, mnum), 0.0) or 0.0)
                else:
                    vals[i] = float(sum(
                        v for (g, _cc, m), v in traslados.items()
                        if g == grupo and m == mnum))

        elif kind in ("sub", "ebitda"):
            for i in range(len(bal_ord)):
                s = 0.0
                for k in opts.get("mas", []):
                    s += valores.get(k, [0.0] * len(bal_ord))[i]
                for k in opts.get("menos", []):
                    s -= valores.get(k, [0.0] * len(bal_ord))[i]
                vals[i] = s

        valores[label] = vals
        acum = sum(vals)
        fila = {"Concepto": label, "_tipo": kind}
        for nm, v in zip(nombres_mes, vals):
            fila[nm] = v
        fila["Acumulado"] = acum
        fila["A.V."] = None  # se calcula al final
        filas.append(fila)

    df = pd.DataFrame(filas)

    # Análisis vertical sobre el total de ingresos netos (acumulado)
    base_av = 0.0
    fila_base = df[df["Concepto"] == "Total ingresos operacionales (netos)"]
    if not fila_base.empty:
        base_av = float(fila_base["Acumulado"].iloc[0]) or 0.0
    if base_av:
        df["A.V."] = df.apply(
            lambda r: (r["Acumulado"] / base_av) if r["_tipo"] in ("line", "mil", "trasl", "sub", "ebitda", "inv")
            and r["Acumulado"] is not None else None, axis=1)

    cols = ["Concepto"] + nombres_mes + ["Acumulado", "A.V.", "_tipo"]
    return df[cols]
