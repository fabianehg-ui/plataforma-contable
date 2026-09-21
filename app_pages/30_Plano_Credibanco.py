# -*- coding: utf-8 -*-
"""
Plano Credibanco (gastos y retenciones) — JIPER SAS

Reemplaza la macro de Excel: sube el reporte crudo de Credibanco y genera el
PLANO de Contai con la comisión, retefuente, reteIVA y reteICA por centro de
costo, listo para importar.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tempfile
import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar
from core.utils.ui_tributarias import render_pagina_tributaria
from core.reportes.plano_credibanco import (
    generar_plano_credibanco, CONFIG_DEF, MAESTRO,
)

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()

render_pagina_tributaria(
    titulo="Plano Credibanco (gastos y retenciones)",
    descripcion="Genera el plano de Contai con comisión, retefuente, reteIVA y "
                "reteICA por centro de costo, desde el reporte crudo de Credibanco.",
    icono="💳",
)

st.markdown("#### 1. Sube el reporte de Credibanco")
st.caption("El archivo tal como lo bajas de Credibanco (.xlsx). Reconoce los "
           "encabezados con espacio o con guion bajo — no hay que corregirlo.")
archivo = st.file_uploader("Reporte Credibanco (crudo)", type=["xlsx", "xls"], key="cb_file")

st.markdown("#### 2. Datos del asiento")
c1, c2 = st.columns(2)
with c1:
    comprobante = st.text_input("Comprobante", value=CONFIG_DEF["comprobante"], key="cb_comp")
with c2:
    documento = st.text_input("Documento / consecutivo", value="1", key="cb_doc")

with st.expander("⚙️ Cuentas y divisores (avanzado)"):
    cfg = {}
    cc1, cc2 = st.columns(2)
    with cc1:
        cfg["cuenta_comision"] = st.text_input("Cuenta comisión", CONFIG_DEF["cuenta_comision"])
        cfg["cuenta_retefuente"] = st.text_input("Cuenta retefuente", CONFIG_DEF["cuenta_retefuente"])
        cfg["cuenta_rete_iva"] = st.text_input("Cuenta reteIVA", CONFIG_DEF["cuenta_rete_iva"])
        cfg["cuenta_rete_ica"] = st.text_input("Cuenta reteICA", CONFIG_DEF["cuenta_rete_ica"])
    with cc2:
        cfg["divisor_retefuente"] = st.number_input("Divisor base retefuente", value=CONFIG_DEF["divisor_retefuente"], format="%.4f")
        cfg["divisor_rete_iva"] = st.number_input("Divisor base reteIVA", value=CONFIG_DEF["divisor_rete_iva"], format="%.4f")
        cfg["divisor_rete_ica"] = st.number_input("Divisor base reteICA", value=CONFIG_DEF["divisor_rete_ica"], format="%.4f")
        cfg["nit"] = st.text_input("NIT", CONFIG_DEF["nit"])
    cfg["detalle"] = st.text_input("Detalle", CONFIG_DEF["detalle"])
    st.caption(f"Maestro de establecimientos cargado: {len(MAESTRO)} códigos → centro de costo.")

if st.button("🧾 Generar plano", type="primary", disabled=(archivo is None)):
    with st.spinner("Procesando reporte de Credibanco…"):
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.write(archivo.getbuffer()); tmp.close()
        try:
            txt, res = generar_plano_credibanco(
                tmp.name, comprobante=comprobante, documento=documento, config=cfg,
            )
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude generar el plano: {e}")
            st.stop()

    st.success(f"Plano generado: {res['lineas']} líneas · {res['centros']} centros de costo · fecha {res['fecha']}.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Comisión", f"${-res['total_comision']:,.0f}")
    m2.metric("Retefuente", f"${-res['total_retefuente']:,.0f}")
    m3.metric("ReteIVA", f"${-res['total_rete_iva']:,.0f}")
    m4.metric("ReteICA", f"${-res['total_rete_ica']:,.0f}")

    st.download_button(
        "⬇️ Descargar plano (.txt)",
        data=txt.encode("latin-1", errors="replace"),
        file_name=f"PLANO_CREDIBANCO_{res['fecha'].replace('/','')}.txt",
        mime="text/plain",
    )
    with st.expander("Ver primeras líneas del plano"):
        st.code("\n".join(txt.split("\r\n")[:15]), language="text")
