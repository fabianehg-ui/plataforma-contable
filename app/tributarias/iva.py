"""
Módulo IVA y reteIVA

Genera las declaraciones bimestrales/cuatrimestrales de IVA y la declaración
mensual de retención de IVA (Formulario 300 y 350).
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa
from core.utils.ui_tributarias import render_pagina_tributaria, render_proximamente


require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

render_pagina_tributaria(
    titulo="IVA y reteIVA",
    descripcion="Formulario 300 (IVA) y formulario 350 (retención de IVA)",
    icono="💸",
)


tab_periodo, tab_iva, tab_reteiva, tab_certif = st.tabs([
    "📅 Período",
    "📄 Formulario 300 - IVA",
    "📄 Formulario 350 - reteIVA",
    "📎 Certificados",
])

with tab_periodo:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.selectbox("Año", options=[2025, 2026], index=1, key="iva_ano")
    with col2:
        st.selectbox(
            "Periodicidad",
            options=["Bimestral", "Cuatrimestral"],
            index=0,
            key="iva_periodicidad",
        )
    with col3:
        st.selectbox(
            "Período",
            options=["Ene-Feb", "Mar-Abr", "May-Jun", "Jul-Ago", "Sep-Oct", "Nov-Dic"],
            key="iva_periodo",
        )

    st.markdown("---")
    render_proximamente(
        titulo="Configuración del período tributario",
        descripcion=(
            "El sistema detecta automáticamente la periodicidad correcta según los "
            "ingresos del año anterior (bimestral si > 92.000 UVT, cuatrimestral si menos)."
        ),
        fases=[
            "Detección automática de periodicidad según ingresos del año anterior",
            "Calendario de vencimientos por NIT",
            "Alerta de períodos pendientes de presentar",
        ],
    )

with tab_iva:
    render_proximamente(
        titulo="Formulario 300 - Declaración bimestral de IVA",
        descripcion=(
            "Calcula el IVA generado, IVA descontable, retenciones de IVA practicadas y "
            "saldo a pagar o favor por período. Genera el formulario oficial DIAN."
        ),
        fases=[
            "Mapeo de cuentas IVA por tarifa (19%, 5%, exento, excluido)",
            "Cálculo automático de IVA generado e IVA descontable",
            "Aplicación del prorrateo si hay operaciones excluidas",
            "Liquidación de anticipos y saldos a favor del período anterior",
        ],
        relacionados=[
            ("Compras DIAN", "Genera los registros de IVA descontable mes a mes"),
            ("Información Exógena", "Formato 1005 (descontable) y 1006 (generado)"),
        ],
    )

with tab_reteiva:
    render_proximamente(
        titulo="Formulario 350 - Declaración mensual de retenciones",
        descripcion=(
            "Liquida la retención en la fuente practicada a título de IVA. Para "
            "Silla Tres aplica RETEIVA Régimen Simple 15% (cuenta 23670515)."
        ),
        fases=[
            "Mapeo de cuentas de retención por tarifa",
            "Cálculo automático de retención por proveedor y por concepto",
            "Liquidación mensual conforme al calendario DIAN",
        ],
        relacionados=[
            ("Retención en la Fuente", "Comparte el formulario 350 con renta y timbre"),
        ],
    )

with tab_certif:
    render_proximamente(
        titulo="Certificados bimestrales de IVA",
        descripcion=(
            "Genera los certificados de retención de IVA practicada a cada proveedor, "
            "que deben entregarse antes del 31 de marzo del año siguiente."
        ),
        fases=[
            "Plantilla oficial de certificado bimestral",
            "Generación masiva en PDF firmado",
            "Envío automático por email a cada proveedor",
        ],
    )
