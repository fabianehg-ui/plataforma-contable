# -*- coding: utf-8 -*-
"""
Reporte Recurrente (Token DIAN)

Genera el reporte mensual recurrente de facturación electrónica de la empresa
activa a partir del Token de la DIAN, con el diseño estándar de 3 hojas:
    1. Resumen IVA   (ventas netas, compras netas, IVA a pagar a la fecha)
    2. Ventas diarias (por fecha, con día de la semana y devoluciones)
    3. Compras + IVA por proveedor
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tempfile
import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa
from core.utils.ui_tributarias import render_pagina_tributaria
from core.reportes.reporte_recurrente_token import generar_reporte_bytes


require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

render_pagina_tributaria(
    titulo="Reporte Recurrente (Token DIAN)",
    descripcion="Resumen de IVA, ventas diarias y compras por proveedor desde el Token DIAN",
    icono="📊",
)

nit = str(empresa.get("nit", "")).strip()
razon = empresa.get("razon_social", "")
# NIT formateado 900.451.388
nit_fmt = ".".join([nit[max(0, i - 3):i] for i in range(len(nit), 0, -3)][::-1]) if nit else nit

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

st.markdown("#### 1. Sube el Token DIAN")
token_file = st.file_uploader(
    "Archivo del Token DIAN (.xlsx descargado del portal)", type=["xlsx"], key="rr_token"
)

st.markdown("#### 2. Período")
c1, c2, c3, c4 = st.columns(4)
with c1:
    anio = st.selectbox("Año", options=[2025, 2026, 2027], index=1, key="rr_anio")
with c2:
    mes = st.selectbox("Mes", options=list(range(1, 13)),
                       format_func=lambda m: MESES[m - 1], key="rr_mes")
with c3:
    dia_ini = st.number_input("Día inicial", min_value=1, max_value=31, value=1, key="rr_dini")
with c4:
    dia_fin = st.number_input("Día final", min_value=1, max_value=31, value=31, key="rr_dfin")

st.caption("Deja Día inicial=1 y Día final=31 para el mes completo. El reporte usa la Fecha de Emisión del token.")

if st.button("🔄 Generar reporte", type="primary", disabled=(token_file is None)):
    if not nit:
        st.error("No hay empresa activa con NIT válido.")
    else:
        with st.spinner("Procesando token…"):
            tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
            tmp.write(token_file.getbuffer())
            tmp.close()
            rango = f" ({int(dia_ini)} al {int(dia_fin)})" if not (dia_ini == 1 and dia_fin == 31) else ""
            periodo_txt = f"{MESES[mes - 1].upper()} {anio}{rango}"
            data, resumen = generar_reporte_bytes(
                token_path=tmp.name,
                nit_empresa=nit,
                anio=int(anio), mes=int(mes),
                dia_ini=int(dia_ini), dia_fin=int(dia_fin),
                titulo_empresa=razon or nit,
                nit_formateado=nit_fmt,
                periodo_texto=periodo_txt,
            )

        st.success("Reporte generado.")
        m1, m2, m3 = st.columns(3)
        m1.metric("IVA generado", f"${resumen['iva_generado']:,.0f}")
        m2.metric("IVA descontable", f"${resumen['iva_descontable']:,.0f}")
        m3.metric("Saldo IVA a pagar", f"${resumen['iva_a_pagar']:,.0f}")
        st.caption(f"{resumen['dias']} días · {resumen['proveedores']} proveedores · "
                   f"ventas netas base ${resumen['ventas_netas_base']:,.0f}")

        slug = (razon or nit).split()[0].upper()
        st.download_button(
            "⬇️ Descargar reporte (.xlsx)",
            data=data,
            file_name=f"Reporte_{slug}_{anio}-{mes:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
