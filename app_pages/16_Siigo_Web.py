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

with st.expander("Como conectar (elige un modo)", expanded=not (ss.get("siigo_web_token") or ss.get("siigo_web_refresh"))):
    st.markdown(
        "**Modo A - Token de sesion (~1 hora):** en tu navegador logueado a "
        "**siigonube.siigo.com**, F12 -> Red -> una peticion a *services.siigo.com* -> "
        "Headers -> copia **authorization** (`Bearer eyJ...`) y pegalo abajo.\n\n"
        "**Modo B - Refresh token (entrar una vez, se renueva solo):** F12 -> Red, filtra "
        "**token**, abre la peticion `oauth2/v2.0/token` -> pestana **Response** -> copia el "
        "valor de **refresh_token** y pegalo abajo. El repo renueva el acceso solo, sin "
        "usuario ni contrasena. (Guardalo luego en Supabase, cifrado.)"
    )

modo = st.radio("Modo de conexion", ["Usuario y contrasena (C)", "Refresh token (B)", "Token de sesion (A)"], horizontal=True)

if modo.startswith("Usuario"):
    st.warning("Experimental: el servidor inicia sesion por ti (navegador headless). "
               "No funciona con MFA/CAPTCHA y va contra los terminos de Siigo. "
               "La contrasena NO se guarda: se usa una vez para obtener el refresh token.")
    c = st.columns(2)
    email = c[0].text_input("Correo electronico", key="c_email")
    pwd = c[1].text_input("Contrasena", type="password", key="c_pwd")
    if st.button("Ingresar a Siigo"):
        try:
            with st.spinner("Iniciando sesion en Siigo..."):
                res = web.login_headless(email, pwd)
            if res.get("refresh_token"):
                ss["siigo_web_refresh"] = res["refresh_token"]
                st.success("Sesion iniciada. Se guardo el refresh token (la contrasena NO).")
            elif res.get("access_token_header"):
                ss["siigo_web_token"] = res["access_token_header"]
                st.success("Sesion iniciada (token de ~1h; sin refresh token).")
            else:
                st.error("No se capturo token.")
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
elif modo.startswith("Refresh"):
    rt = st.text_area("Refresh token", value=ss.get("siigo_web_refresh", ""), height=70, placeholder="eyJ...")
    if rt:
        ss["siigo_web_refresh"] = rt.strip()
else:
    tok = st.text_area("Token de sesion (authorization)", value=ss.get("siigo_web_token", ""), height=70, placeholder="Bearer eyJ...")
    if tok:
        ss["siigo_web_token"] = tok.strip()
        ss.pop("siigo_web_refresh", None)


def token_activo() -> str:
    """Devuelve un access token vigente. En modo B lo renueva con el refresh token."""
    if ss.get("siigo_web_refresh"):
        res = web.refresh_access_token(ss["siigo_web_refresh"])
        ss["siigo_web_refresh"] = res["refresh_token"]  # B2C rota el refresh token
        ss["siigo_web_token"] = "Bearer " + res["access_token"]
    return ss.get("siigo_web_token", "")

col = st.columns(2)
if col[0].button("Listar empresas", type="primary"):
    try:
        with st.spinner("Consultando catalogo..."):
            ss["siigo_web_empresas"] = web.get_empresas(token_activo())
        st.success(f"{len(ss['siigo_web_empresas'])} empresa(s).")
    except Exception as e:  # noqa: BLE001
        st.error(str(e))

empresas = ss.get("siigo_web_empresas", [])
if empresas:
    op = {f"{e['nombre']} - {e['nit']}" if e['nit'] else e['nombre']: e['tenantId'] for e in empresas}
    sel = st.selectbox("Empresa", list(op.keys()))
    tenant = op[sel]
    if col[1].button("Elegir empresa"):
        ok, code = web.elegir_empresa(token_activo(), tenant)
        st.info("Empresa seleccionada." if ok else f"No se pudo (status {code}).")

st.markdown("---")
st.subheader("Facturas de venta")
if st.button("Traer facturas"):
    try:
        with st.spinner("Descargando facturas (paginando)..."):
            filas, cruda = web.get_facturas(token_activo())
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
