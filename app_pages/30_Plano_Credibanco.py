# -*- coding: utf-8 -*-
"""
Plano Credibanco (gastos y retenciones) — multiempresa

Sube el reporte crudo de Credibanco y genera el PLANO de Contai con comisión,
retefuente, reteIVA y reteICA por centro de costo. El maestro (código →
centro de costo) y las cuentas se configuran POR EMPRESA desde esta misma
página (tablas credibanco_maestro / credibanco_config, migración 019).
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tempfile
import pandas as pd
import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa
from core.utils.ui_tributarias import render_pagina_tributaria
from db.supabase_client import get_supabase
from core.reportes.plano_credibanco import (
    generar_plano_credibanco, CONFIG_DEF,
    cargar_maestro, guardar_maestro, cargar_config, guardar_config, maestro_jiper_filas,
)

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_empresa()
sb = get_supabase()
empresa_id = emp["id"]

render_pagina_tributaria(
    titulo="Plano Credibanco (gastos y retenciones)",
    descripcion="Genera el plano de Contai con comisión, retefuente, reteIVA y "
                "reteICA por centro de costo, desde el reporte crudo de Credibanco.",
    icono="💳",
)

# --- cargar config y maestro de la empresa activa ---
cfg = cargar_config(sb, empresa_id)
maestro = cargar_maestro(sb, empresa_id)

tab_gen, tab_cfg = st.tabs(["🧾 Generar plano", "⚙️ Configuración de la empresa"])

# ======================= GENERAR =======================
with tab_gen:
    if not maestro:
        st.warning("Esta empresa aún no tiene el **maestro** (código → centro de costo) "
                   "configurado. Ve a la pestaña «Configuración de la empresa» para cargarlo.")
    st.markdown("#### 1. Sube el reporte de Credibanco")
    st.caption("El archivo tal como lo bajas de Credibanco (.xlsx). Reconoce encabezados "
               "con espacio o con guion bajo — no hay que corregirlo.")
    archivo = st.file_uploader("Reporte Credibanco (crudo)", type=["xlsx", "xls"], key="cb_file")

    st.markdown("#### 2. Datos del asiento")
    c1, c2 = st.columns(2)
    with c1:
        comprobante = st.text_input("Comprobante", value=str(cfg["comprobante"]), key="cb_comp")
    with c2:
        documento = st.text_input("Documento / consecutivo", value="1", key="cb_doc")

    if st.button("🧾 Generar plano", type="primary", disabled=(archivo is None or not maestro)):
        with st.spinner("Procesando reporte de Credibanco…"):
            tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
            tmp.write(archivo.getbuffer()); tmp.close()
            try:
                txt, res = generar_plano_credibanco(
                    tmp.name, comprobante=comprobante, documento=documento,
                    config=cfg, maestro=maestro,
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

# ======================= CONFIGURACIÓN =======================
with tab_cfg:
    st.markdown("#### Cuentas y divisores")
    with st.form("cfg_credibanco"):
        cc1, cc2 = st.columns(2)
        with cc1:
            v_com = st.text_input("Cuenta comisión (gasto)", str(cfg["cuenta_comision"]))
            v_ret = st.text_input("Cuenta retefuente", str(cfg["cuenta_retefuente"]))
            v_riva = st.text_input("Cuenta reteIVA", str(cfg["cuenta_rete_iva"]))
            v_rica = st.text_input("Cuenta reteICA", str(cfg["cuenta_rete_ica"]))
            v_nit = st.text_input("NIT tercero (Credibanco)", str(cfg["nit"]))
        with cc2:
            v_dret = st.number_input("Divisor base retefuente", value=float(cfg["divisor_retefuente"]), format="%.4f")
            v_driva = st.number_input("Divisor base reteIVA", value=float(cfg["divisor_rete_iva"]), format="%.4f")
            v_drica = st.number_input("Divisor base reteICA", value=float(cfg["divisor_rete_ica"]), format="%.4f")
            v_comp = st.text_input("Comprobante", str(cfg["comprobante"]))
            v_det = st.text_input("Detalle", str(cfg["detalle"]))
        if st.form_submit_button("💾 Guardar cuentas", type="primary"):
            guardar_config(sb, empresa_id, {
                "cuenta_comision": v_com, "cuenta_retefuente": v_ret,
                "cuenta_rete_iva": v_riva, "cuenta_rete_ica": v_rica,
                "divisor_retefuente": v_dret, "divisor_rete_iva": v_driva,
                "divisor_rete_ica": v_drica, "nit": v_nit, "detalle": v_det,
                "comprobante": v_comp,
            })
            st.success("Cuentas guardadas para esta empresa.")
            st.rerun()

    st.divider()
    st.markdown("#### Maestro: código de establecimiento → centro de costo")
    st.caption("Un renglón por establecimiento. El **código** es el que trae el reporte "
               "(CODIGO ESTABLECIMIENTO) y el **centro de costo** es el de tu Contai (6 dígitos).")

    filas = ([{"codigo": c, "oasis": o, "centro_costo": cc} for c, (o, cc) in maestro.items()]
             or [{"codigo": "", "oasis": "", "centro_costo": ""}])
    df = pd.DataFrame(filas, columns=["codigo", "oasis", "centro_costo"])
    ed = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, key="cb_maestro_ed",
        column_config={
            "codigo": st.column_config.TextColumn("Código establecimiento", required=True),
            "oasis": st.column_config.TextColumn("Punto / OASIS"),
            "centro_costo": st.column_config.TextColumn("Centro de costo (001xxx)", required=True),
        },
    )
    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("💾 Guardar maestro", type="primary"):
            n = guardar_maestro(sb, empresa_id, ed.to_dict("records"))
            st.success(f"Maestro guardado: {n} establecimientos.")
            st.rerun()
    with b2:
        if st.button("🌱 Sembrar maestro de JIPER"):
            guardar_maestro(sb, empresa_id, maestro_jiper_filas())
            st.success("Maestro de JIPER cargado para esta empresa. Ajústalo si aplica.")
            st.rerun()
