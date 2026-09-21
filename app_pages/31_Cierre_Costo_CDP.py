"""
app_pages/31_Cierre_Costo_CDP.py

Cierre mensual de costo de JIPER SAS → planos de Contai:
  · Documento 4  — CIERRE DE COSTO   (71059501/502/503, 61400501, 61401001,
                                       14050501, 14050502)
  · Documento 5  — TRASLADOS DE CDP  (61409501, 61409502; netea a cero)

Sube el BP para costo y el RESULTADOS del mes; descarga los dos planos.

Depende de: core/reportes/cierre_costo_jiper.py
requirements.txt: openpyxl
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import calendar
from datetime import date

import streamlit as st

st.set_page_config(page_title="Cierre y traslado de costo", page_icon="🧮", layout="wide")
from auth.guard import guard_empresa
from core.reportes.cierre_costo_jiper import generar_cierre_costo, NIT_JIPER

st.title("🧮 Cierre y traslado de costo (JIPER)")
emp, sb = guard_empresa()
st.caption("Genera los planos de Contai del cierre de costo (documento 4) y los "
           "traslados de CDP (documento 5) a partir del BP para costo y el "
           "informe RESULTADOS del mes.")

# Este módulo está calibrado al formato de JIPER (RESULTADOS con puntos en
# columnas y su plan de cuentas). Avisar si la empresa activa no es JIPER.
if str(emp.get("nit", "")).replace(".", "").strip() != NIT_JIPER:
    st.warning("⚠️ Este cierre está calibrado para **JIPER SAS**. La empresa activa "
               f"es **{emp.get('razon_social','')}**; los resultados podrían no aplicar.")

# ------------------------------------------------------------------ entradas
st.markdown("#### 1. Sube los dos archivos del mes")
c1, c2 = st.columns(2)
with c1:
    bp = st.file_uploader("BP para costo (.xlsx)", type=["xlsx", "xls"], key="cc_bp")
    st.caption("Balance de Prueba con Saldo Anterior, Débitos, Créditos y Centro de Costos.")
with c2:
    res = st.file_uploader("RESULTADOS del mes (.xlsx)", type=["xlsx", "xls"], key="cc_res")
    st.caption("Informe RESULTADOS (hoja con los puntos en columnas).")

st.markdown("#### 2. Datos del asiento")
d1, d2, d3, d4c = st.columns(4)
with d1:
    comprobante = st.text_input("Comprobante", value="10", key="cc_comp")
with d2:
    doc_costo = st.text_input("Documento cierre costo", value="4", key="cc_d4")
with d3:
    doc_cdp = st.text_input("Documento traslados CDP", value="5", key="cc_d5")
with d4c:
    hoy = date.today()
    fin_mes = date(hoy.year, hoy.month, calendar.monthrange(hoy.year, hoy.month)[1])
    fecha = st.date_input("Fecha del asiento", value=fin_mes, key="cc_fecha",
                          format="MM/DD/YYYY")

# ------------------------------------------------------------------ generar
if st.button("🧮 Generar planos (doc 4 y doc 5)", type="primary",
             disabled=(bp is None or res is None)):
    with st.spinner("Procesando cierre de costo…"):
        try:
            doc4_txt, doc5_txt, r = generar_cierre_costo(
                bp.getvalue(), res.getvalue(),
                comprobante=comprobante, doc_costo=doc_costo, doc_cdp=doc_cdp,
                fecha=fecha.strftime("%m/%d/%Y"),
            )
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude generar los planos: {e}")
            st.stop()

    # ---- verificación visible ----
    ok4 = abs(r["doc4_dif"]) < 0.01
    ok5 = abs(r["doc5_dif"]) < 0.01
    if ok4 and ok5:
        st.success(f"Planos generados y cuadrados · fecha {r['fecha']}.")
    else:
        st.error("Se generaron pero **NO cuadran** (débitos ≠ créditos). Revisa las fuentes.")

    st.markdown("##### Documento 4 — Cierre de costo")
    m = st.columns(4)
    m[0].metric("Líneas", r["doc4_lineas"])
    m[1].metric("Compras cerradas (71)", f"${r['total_compras']:,.0f}")
    m[2].metric("Costo (cuenta 6)", f"${r['total_costo']:,.0f}")
    m[3].metric("Débitos = Créditos", "✅" if ok4 else f"❌ {r['doc4_dif']:,.2f}")
    st.download_button(
        "⬇️ Descargar documento 4 (cierre de costo)",
        data=doc4_txt.encode("latin-1", errors="replace"),
        file_name=f"plano_cierre_costo_doc{doc_costo}_{r['fecha'].replace('/','')}.txt",
        mime="text/plain", key="dl4",
    )

    st.markdown("##### Documento 5 — Traslados de CDP")
    n = st.columns(3)
    n[0].metric("Líneas", r["doc5_lineas"])
    n[1].metric("Traslados", f"${r['total_traslados']:,.0f}")
    n[2].metric("Netea a cero", "✅" if ok5 else f"❌ {r['doc5_dif']:,.2f}")
    st.download_button(
        "⬇️ Descargar documento 5 (traslados CDP)",
        data=doc5_txt.encode("latin-1", errors="replace"),
        file_name=f"plano_traslado_cdp_doc{doc_cdp}_{r['fecha'].replace('/','')}.txt",
        mime="text/plain", key="dl5",
    )

    with st.expander("Ver primeras líneas de cada plano"):
        st.markdown("**Documento 4**")
        st.code("\n".join(doc4_txt.split("\r\n")[:12]), language="text")
        st.markdown("**Documento 5**")
        st.code("\n".join(doc5_txt.split("\r\n")[:12]), language="text")
else:
    if bp is None or res is None:
        st.info("Sube el BP para costo y el RESULTADOS del mes para generar los planos.")
