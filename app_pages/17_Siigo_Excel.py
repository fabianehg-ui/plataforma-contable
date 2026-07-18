"""
app_pages/17_Siigo_Excel.py
Sube el Excel "Movimiento ventas y compras" de Siigo (que trae base, IVA y
retenciones) y genera los planos de Contai con el asiento completo. Para empresas
SIN API. Registrala en Home.py como las demas paginas.
"""
from __future__ import annotations

import streamlit as st

from core.siigo import excel_planos as E
from auth.guard import guard_empresa

st.title("Siigo Excel → Contai (con IVA y retención)")
emp, sb = guard_empresa()
st.caption("Para empresas sin API. Exporta en Siigo el informe 'Movimiento ventas' a Excel y subelo aqui.")
ss = st.session_state

up = st.file_uploader("Excel de Movimiento de ventas (.xlsx)", type=["xlsx"])
if up is not None:
    try:
        ss["xls_docs"] = E.leer_excel(up)
    except Exception as e:  # noqa: BLE001
        st.error(f"No pude leer el Excel: {e}")

docs = ss.get("xls_docs")
if not docs:
    st.info("Sube el Excel para empezar.")
    st.stop()

r = E.resumen(docs)
st.success(f"{len(docs)} documentos · {r['facturas']} facturas · {r['notas']} notas credito")
st.write("Prefijos:", r["prefijos"], "· Tarifas IVA:", r["ivas"], "· Retenciones:", r["retenciones"])

st.subheader("Comprobante y centro por prefijo")
mapeo = {}
for p in r["prefijos"]:
    c = st.columns([1, 2, 2])
    c[0].markdown(f"**{p}**")
    comp = c[1].text_input("comprobante", key=f"xc_{p}", label_visibility="collapsed", placeholder="comprobante")
    cen = c[2].text_input("centro", key=f"xcen_{p}", label_visibility="collapsed", placeholder="centro (opcional)")
    mapeo[p] = {"comprobante": comp, "centro": cen}

st.subheader("Plan de cuentas")
cc = st.columns(2)
cta_cartera = cc[0].text_input("Cartera / clientes", value="13050502")
cta_efe = cc[1].text_input("Efectivo (recibos)", value="11050503")

st.markdown("**Ventas e IVA por tarifa**")
ventas, iva = {}, {}
for il in r["ivas"]:
    c = st.columns([2, 2, 2])
    c[0].markdown(f"`{il}`")
    ventas[il] = c[1].text_input(f"Cuenta ventas {il}", key=f"xv_{il}", placeholder="cuenta ventas")
    iva[il] = c[2].text_input(f"Cuenta IVA {il}", key=f"xi_{il}", placeholder="cuenta IVA")

reten = {}
if r["retenciones"]:
    st.markdown("**Cuentas de retencion**")
    for rl in r["retenciones"]:
        c = st.columns([2, 3])
        c[0].markdown(f"`{rl}`")
        reten[rl] = c[1].text_input(f"Cuenta {rl}", key=f"xr_{rl}", label_visibility="collapsed", placeholder="cuenta retencion")

cc2 = st.columns(2)
comp_rec = cc2[0].text_input("Comprobante recibos", value="1")
cons_rec = cc2[1].number_input("Consecutivo inicial recibos", min_value=1, value=1, step=1)

exportar = st.multiselect("Que generar", ["Ventas (IVA + retencion)", "Recibos de caja", "NITs"],
                          default=["Ventas (IVA + retencion)", "NITs"])

if st.button("Generar planos", type="primary"):
    cuentas = {"cartera": cta_cartera, "ventas": ventas, "iva": iva, "retencion": reten}
    outs = []
    if "Ventas (IVA + retencion)" in exportar:
        v = E.build_ventas(docs, mapeo, cuentas)
        if v["faltan"]:
            st.warning("Faltan cuentas: " + ", ".join(v["faltan"]))
        estado = "cuadra ✓" if v["cuadra"] else f"DESCUADRE Db {v['db']} vs Cr {v['cr']}"
        outs.append(("ventas_iva_retencion.txt", v["content"], f"{v['count']} facturas · {estado}"))
    if "Recibos de caja" in exportar:
        rc = E.build_recibos(docs, cons_rec, mapeo, cta_efe, cta_cartera, comp_rec)
        outs.append(("recibos_caja.txt", rc["content"], f"{rc['count']} recibos ({rc['desde']}-{rc['hasta']})"))
    if "NITs" in exportar:
        outs.append(("nits.txt", E.build_terceros(docs), "terceros"))
    ss["xls_outs"] = [(fn, c.encode("utf-8"), nota) for fn, c, nota in outs]

if ss.get("xls_outs"):
    st.subheader("Descargar")
    for fn, data, nota in ss["xls_outs"]:
        st.download_button(f"⬇ {fn} — {nota}", data=data, file_name=fn, mime="text/plain", key=f"xdl_{fn}")
    st.caption("Importa los .txt en Contai: Procesos -> Intercambio de Datos -> Importar.")
