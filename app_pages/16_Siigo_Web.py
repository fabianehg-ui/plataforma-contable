"""
app_pages/16_Siigo_Web.py
Opera Siigo Nube (empresas SIN API) desde el repo, usando un TOKEN pegado de tu
sesion (no guarda contrasenas). Registrala en Home.py como las demas paginas.

Sirve tambien para CAPTURAR el ejemplo de facturas (sales_report) que hace falta
para armar el mapeo al plano de Contai.
"""
from __future__ import annotations

import io
import json

import streamlit as st

from core.siigo import web

st.title("Siigo Web (sin API)")
st.caption("Para empresas sin API habilitada. Pega el token de tu sesion de Siigo; el repo hace el resto.")
ss = st.session_state

with st.expander("Como obtener el token (1 minuto)", expanded=not ss.get("siigo_web_token")):
    st.markdown(
        "1. Entra normal a **siigonube.siigo.com** en tu navegador (pasa MFA como siempre).\n"
        "2. Abre **F12 -> Red (Network)**, filtra **Fetch/XHR** y recarga o abre cualquier pantalla.\n"
        "3. Clic en una peticion a **services.siigo.com** -> pestana **Headers** -> "
        "en *Request Headers* copia el valor de **authorization** (empieza por `Bearer eyJ...`).\n"
        "4. Pegalo abajo. Dura ~1 hora; cuando falle, pega uno nuevo."
    )

token = st.text_area("Token de sesion (authorization)", value=ss.get("siigo_web_token", ""), height=80, placeholder="Bearer eyJ...")
if token:
    ss["siigo_web_token"] = token.strip()

col = st.columns(2)
if col[0].button("Listar empresas", type="primary"):
    try:
        with st.spinner("Consultando catalogo..."):
            ss["siigo_web_empresas"] = web.get_empresas(ss.get("siigo_web_token", ""))
        st.success(f"{len(ss['siigo_web_empresas'])} empresa(s).")
    except Exception as e:  # noqa: BLE001
        st.error(str(e))

empresas = ss.get("siigo_web_empresas", [])
if empresas:
    op = {f"{e['nombre']} - {e['nit']}" if e['nit'] else e['nombre']: e['tenantId'] for e in empresas}
    sel = st.selectbox("Empresa", list(op.keys()))
    tenant = op[sel]
    if col[1].button("Elegir empresa"):
        ok, code = web.elegir_empresa(ss.get("siigo_web_token", ""), tenant)
        st.info("Empresa seleccionada." if ok else f"No se pudo (status {code}).")

st.markdown("---")
st.subheader("Facturas de venta")
if st.button("Traer facturas"):
    try:
        with st.spinner("Descargando facturas (paginando)..."):
            filas, cruda = web.get_facturas(ss.get("siigo_web_token", ""))
        ss["siigo_web_facturas"] = filas
        ss["siigo_web_cruda"] = cruda
        st.success(f"{len(filas)} facturas.")
        if filas:
            st.write("Columnas detectadas:", list(filas[0].keys()))
            st.dataframe(filas[:20])
    except Exception as e:  # noqa: BLE001
        st.error(str(e))

if ss.get("siigo_web_facturas"):
    data = json.dumps(ss["siigo_web_facturas"], ensure_ascii=False, indent=1).encode("utf-8")
    st.download_button("Descargar facturas (JSON)", data=data, file_name="siigo_web_facturas.json", mime="application/json")
    st.caption("Pasame este JSON: con las columnas reales armo el mapeo al plano de Contai (ventas, recibos, NITs).")
