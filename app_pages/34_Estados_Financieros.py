"""
app_pages/34_Estados_Financieros.py

ESTADOS FINANCIEROS NIIF — informe recurrente mensual (Grupo de Lolita).

Rellena la plantilla de EE.FF (que se maneja por SUMIF desde la hoja DATOS):
  · Balance del mes por NIT (año en curso)  -> hoja 'BCE 2026'
  · Balance del mismo mes del año anterior   -> hoja 'BCE 2025'
y deja que Excel recalcule (Estado de Resultados del mes y acumulado, ESF/
Balance, EFE, ECP, indicadores y notas — 2026 vs 2025 y acumulado del año).

Además ANEXA el resultado por centro de costo del mes (nivel amplio, con
desplegar/contraer), a partir del balance por NIT y CC, y lo memoriza para el
comparativo con el mes inmediatamente anterior.

Config: tabla eeff_resultado_cc (migración 025). Plantilla en plantillas/.
Depende de: core/eeff/eeff_niif.py · requirements: openpyxl
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Estados Financieros NIIF", page_icon="📊", layout="wide")
from auth.guard import guard_empresa
from core.eeff import eeff_niif as E

st.title("📊 Estados Financieros")
emp, sb = guard_empresa()
st.caption("Informe recurrente mensual: rellena la plantilla con el balance del mes "
           "y el del mismo mes del año anterior, y recalcula todos los estados. El "
           "balance se sube en pesos; cada plantilla usa su unidad automáticamente "
           "(la administrativa trabaja en miles, se convierte solo).")

# ------------------------------------------------------------------ 0. tipo de informe
st.markdown("#### 1. Tipo de informe")
tipo = st.radio("¿Qué informe generas?", list(E.PLANTILLAS.keys()),
                format_func=lambda t: E.PLANTILLAS[t]["titulo"], horizontal=True)
cfg = E.PLANTILLAS[tipo]
st.caption(cfg["descripcion"])
PLANTILLA_DEF = ROOT / "plantillas" / cfg["archivo"]

# ------------------------------------------------------------------ 1. periodo
st.markdown("#### 2. Periodo")
hoy = date.today()
c = st.columns(3)
mes = c[0].selectbox("Mes", list(range(1, 13)), index=hoy.month - 2 if hoy.month > 1 else 0,
                     format_func=lambda m: f"{m:02d} — {E.MESES[m]}")
anio = c[1].number_input("Año", min_value=2020, max_value=2100, value=hoy.year, step=1)
anio_comp = c[2].number_input("Año comparativo", min_value=2019, max_value=2099,
                              value=int(anio) - 1, step=1)
periodo = f"{int(anio):04d}-{int(mes):02d}"

# ------------------------------------------------------------------ 3. archivos
st.markdown("#### 3. Balances de prueba (por NIT y centro de costo)")
st.caption("Sube el balance de prueba **por NIT y centro de costo** de cada año, en "
           "PESOS. El mismo archivo alimenta todo el informe (los estados se colapsan "
           "por NIT). La conversión a miles, cuando aplica, es automática.")
c2 = st.columns(2)
bp_act = c2[0].file_uploader(f"Balance {int(anio)}", type=["xlsx", "xls"], key="bp_act")
bp_ant = c2[1].file_uploader(f"Balance {int(anio_comp)}", type=["xlsx", "xls"], key="bp_ant")

with st.expander("⚙️ Plantilla del informe (opcional)"):
    st.caption(f"Por defecto se usa la plantilla «{cfg['titulo']}» incluida en el "
               "sistema. Puedes subir otra plantilla con la misma estructura "
               "(hoja DATOS que mapea por SUMIF contra las hojas de balance).")
    tpl_up = st.file_uploader("Plantilla (.xlsx)", type=["xlsx"], key=f"tpl_up_{tipo}")

st.divider()

# ------------------------------------------------------------------ 4. generar
st.markdown("#### 4. Generar el informe")
puede = bp_act is not None and bp_ant is not None and (PLANTILLA_DEF.exists() or tpl_up is not None)
if st.button("📊 Generar Estados Financieros", type="primary", disabled=not puede):
    try:
        template = tpl_up.getvalue() if tpl_up is not None else PLANTILLA_DEF.read_bytes()
        balance = bp_act.getvalue()   # universal por NIT y CC (año en curso)
        res = E.generar_informe(template, balance, bp_ant.getvalue(),
                                mes=int(mes), anio=int(anio),
                                bp_cc=balance,           # el mismo balance arma el anexo
                                anio_comp=int(anio_comp), tipo=tipo)
        st.session_state["eeff_bytes"] = res["bytes"]
        st.session_state["eeff_meta"] = dict(periodo=periodo, tipo=tipo,
                                             n_act=res["n_actual"], n_ant=res["n_anterior"],
                                             anexo=res.get("anexo"))
        st.session_state["eeff_tot_cc"] = E.totales_cc_por_clase(E.leer_bp(balance))
    except Exception as e:  # noqa: BLE001
        st.error(f"No pude generar el informe: {e}")
        st.exception(e)

by = st.session_state.get("eeff_bytes")
if by:
    meta = st.session_state.get("eeff_meta", {})
    tcfg = E.PLANTILLAS.get(meta.get("tipo", "fiscal"), cfg)
    pref = "EEFF_Fiscal" if meta.get("tipo") == "fiscal" else "Balance_PyG_Admin"
    st.success(f"«{tcfg['titulo']}» generado. Balance {int(anio)}: {meta.get('n_act')} "
               f"cuentas · Balance {int(anio_comp)}: {meta.get('n_ant')} cuentas. "
               "Ábrelo en Excel: recalcula solo al abrir.")
    st.download_button(f"📥 {tcfg['titulo']} (Excel)", by,
                       file_name=f"{pref}_{meta.get('periodo','')}_Grupo_de_Lolita.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       type="primary")

    # ---- resultado por CC + comparativo mes anterior ----
    tot = st.session_state.get("eeff_tot_cc")
    if tot:
        st.markdown("##### Resultado por centro de costo del mes (miles de pesos)")
        prev = E.cargar_resultado_cc(sb, emp["id"], E.periodo_anterior(periodo))
        filas = []
        for cc, v in tot.items():
            uant = float(prev.get(cc, {}).get("utilidad", 0)) if prev else None
            fila = {"Centro de costo": v["nombre"],
                    "Ingresos": v["ingresos"] / 1000, "Costos": v["costos"] / 1000,
                    "Gastos": v["gastos"] / 1000, "Utilidad mes": v["utilidad"] / 1000}
            if prev:
                fila["Utilidad mes ant."] = uant / 1000
                fila["Variación"] = (v["utilidad"] - uant) / 1000
            filas.append(fila)
        df = pd.DataFrame(filas)
        numcols = [c for c in df.columns if c != "Centro de costo"]
        st.dataframe(df.style.format({c: "{:,.0f}" for c in numcols}),
                     hide_index=True, use_container_width=True)
        if not prev:
            st.caption(f"No hay resultado guardado de {E.periodo_anterior(periodo)}; "
                       "guarda este mes para tener el comparativo el próximo.")

        if st.button(f"💾 Guardar resultado por CC de {periodo} (memoria)"):
            try:
                n = E.guardar_resultado_cc(sb, emp["id"], periodo, tot)
                st.success(f"Guardado el resultado por CC de {periodo} ({n} centros). "
                           "Se usará como comparativo del mes siguiente.")
            except Exception as e:  # noqa: BLE001
                st.error(f"No pude guardar: {e}")
