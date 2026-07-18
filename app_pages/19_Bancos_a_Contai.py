"""
app_pages/19_Bancos_a_Contai.py
Sube los extractos bancarios en PDF (Bancolombia, Banco de Bogota, BBVA),
clasifica los gastos bancarios, muestra el resumen y genera el plano de Contai
repartido entre los centros de costo.

Depende de: core/procesadores/extractos_bancarios.py
requirements.txt: pdfplumber
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date

import pandas as pd
import streamlit as st

from core.procesadores import extractos_bancarios as eb

st.set_page_config(page_title="Bancos a Contai", page_icon="🏦", layout="wide")
st.title("🏦 Extractos bancarios → resumen y plano Contai")
st.caption("Sube los PDF de Bancolombia, Banco de Bogotá y BBVA. Se leen directo del PDF, "
           "sin Word ni programas externos.")

# ---------------------------------------------------------------- 1) los PDF
pdfs = st.file_uploader("Extractos del mes (PDF, puedes subir varios)",
                        type=["pdf"], accept_multiple_files=True)

if not pdfs:
    st.info("Sube los extractos para empezar.")
    st.stop()

movs, info = [], []
for f in pdfs:
    try:
        r = eb.leer_extracto(f)
    except Exception as e:  # noqa: BLE001
        info.append({"archivo": f.name, "banco": "—", "clasificados": 0,
                     "sin clasificar": 0, "estado": f"error: {e}"})
        continue
    if not r["banco"]:
        info.append({"archivo": f.name, "banco": "NO reconocido", "clasificados": 0,
                     "sin clasificar": 0, "estado": "revisa que sea un extracto de los 3 bancos"})
        continue
    movs += r["movimientos"]
    info.append({"archivo": f.name, "banco": r["banco"]["nombre"],
                 "clasificados": len(r["movimientos"]),
                 "sin clasificar": r["sin_clasificar"], "estado": "ok"})

st.dataframe(pd.DataFrame(info), use_container_width=True, hide_index=True)
if not movs:
    st.error("No se clasificó ningún movimiento.")
    st.stop()

# ---------------------------------------------------------------- 2) resumen
st.subheader("Resumen de gastos bancarios")
res = eb.resumen(movs)
NOM = {"53050501": "Gastos bancarios", "53050502": "IVA gastos bancarios",
       "53051501": "Comisiones", "53059501": "Gravamen 4x1000"}
bancos = list(res.keys())
filas = []
for cta in sorted(NOM):
    fila = {"Cuenta": cta, "Concepto": NOM[cta]}
    for b in bancos:
        fila[b] = round(res[b].get(cta, 0))
    fila["TOTAL"] = round(sum(res[b].get(cta, 0) for b in bancos))
    filas.append(fila)
tot = {"Cuenta": "", "Concepto": "TOTAL"}
for b in bancos:
    tot[b] = round(sum(res[b].values()))
tot["TOTAL"] = round(sum(sum(res[b].values()) for b in bancos))
filas.append(tot)
st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

st.warning("**Control:** compara el total de cada banco contra el que declara su propio extracto "
           "(Bancolombia: TOTAL CARGOS · BBVA: '4 POR MIL' e 'IVA' · Bogotá: 'Total 4x1000 GMF'). "
           "Los movimientos que no son gastos bancarios (nómina, proveedores, leasing, cuotas de "
           "crédito) quedan **fuera** del plano a propósito.")

with st.expander("Ver el detalle de los movimientos clasificados"):
    st.dataframe(pd.DataFrame(movs), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- 3) el plano
st.subheader("Plano Contai")
c = st.columns(4)
comprobante = c[0].text_input("Comprobante", "10")
documento = c[1].text_input("Documento", "1")
f_asiento = c[2].date_input("Fecha del asiento", value=date(date.today().year, date.today().month, 1))
divisor = c[3].number_input("Divisor base IVA", value=0.19, step=0.01, format="%.2f")

st.markdown("**Centros de costo** entre los que se reparte cada gasto (partes iguales, uno por línea):")
CC_DEFECTO = "\n".join([
    "001001", "001002", "001003", "001004",
    "001101", "001102", "001103", "001104", "001105", "001106", "001107", "001108", "001109",
    "001110", "001111", "001112", "001113", "001114", "001115", "001116", "001117", "001118", "001300",
    "001201", "001202", "001203", "001204", "001205", "001206", "001207",
])
txt_cc = st.text_area("Centros de costo", CC_DEFECTO, height=120)
centros = [x.strip() for x in txt_cc.splitlines() if x.strip()]
st.caption(f"{len(centros)} centros · cada gasto se divide entre ellos; los centavos del redondeo "
           "los absorbe el último centro para que el asiento cuadre al peso.")

if st.button("Generar plano", type="primary", disabled=not centros):
    p = eb.build_plano(movs, centros, comprobante, documento,
                       f_asiento.strftime("%m/%d/%Y"), divisor)
    if p["cuadra"]:
        st.success(f"Plano generado: {len(p['filas'])-1} líneas · "
                   f"Db = Cr = {p['debitos']:,}".replace(",", "."))
    else:
        st.error(f"DESCUADRE: Db {p['debitos']:,} vs Cr {p['creditos']:,}")
    st.dataframe(pd.DataFrame(p["filas"][1:], columns=p["filas"][0]).head(20),
                 use_container_width=True, hide_index=True)
    st.caption("(primeras 20 líneas)")
    st.download_button("⬇ Descargar plano.txt (tabulaciones)",
                       data=eb.plano_a_texto(p["filas"]).encode("utf-8"),
                       file_name=f"plano_gastos_bancarios_{f_asiento:%Y_%m}.txt",
                       mime="text/plain")

    # Opción: agregar al movimiento del mes
    from core.contable import servicio_contable as _cont
    from core.contable.ui_contabilizar import render_contabilizar_activa
    st.markdown("---")
    df_bancos = pd.DataFrame(p["filas"][1:], columns=_cont.COLUMNAS_PLANO)
    render_contabilizar_activa(df_bancos, "bancos",
                               anio_default=f_asiento.year, mes_default=f_asiento.month)
