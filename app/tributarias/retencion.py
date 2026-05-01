"""
Módulo Retención en la Fuente

Genera la declaración mensual de retención en la fuente (Formulario 350) y los
certificados de retención por concepto (renta, IVA, timbre, ICA).
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
    titulo="Retención en la Fuente",
    descripcion="Formulario 350 - declaración mensual + certificados anuales",
    icono="🧾",
)


tab_periodo, tab_form350, tab_certif_renta, tab_autorret = st.tabs([
    "📅 Período mensual",
    "📄 Formulario 350",
    "🧾 Certificados",
    "♻️ Autorretenciones",
])

with tab_periodo:
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("Año", options=[2025, 2026], index=1, key="rf_ano")
    with col2:
        st.selectbox(
            "Mes",
            options=[
                "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
            ],
            key="rf_mes",
        )

    st.markdown("---")
    render_proximamente(
        titulo="Detección automática de obligación de presentar",
        descripcion=(
            "Verifica si la empresa es agente retenedor según su clasificación DIAN, "
            "y si tiene operaciones en el mes que generen retención."
        ),
        fases=[
            "Lectura del estado de retenedor desde la tabla empresas",
            "Detección de movimientos en cuentas 2365 (retenciones practicadas)",
            "Alerta si hay retenciones pero no hay declaración del período",
        ],
    )

with tab_form350:
    render_proximamente(
        titulo="Formulario 350 - Retenciones del mes",
        descripcion=(
            "Liquida todas las retenciones practicadas: renta, IVA, timbre, ICA. "
            "Conforme al calendario DIAN según el último dígito del NIT."
        ),
        fases=[
            "Agrupación de retenciones por concepto (1301-1306) desde el balance",
            "Cálculo del total a pagar por título tributario",
            "Generación del formulario 350 en formato oficial DIAN",
            "Liquidación de sanciones por extemporaneidad si aplica",
        ],
        relacionados=[
            ("Información Exógena", "Formato 1001 - retenciones practicadas"),
            ("Compras DIAN", "Genera las retenciones cada vez que se procesa el mes"),
        ],
    )

with tab_certif_renta:
    render_proximamente(
        titulo="Certificados de retención por proveedor",
        descripcion=(
            "Genera los certificados anuales de retención que deben entregarse a "
            "cada proveedor antes del 31 de marzo del año siguiente al gravable. "
            "Incluye renta, IVA y CREE."
        ),
        fases=[
            "Plantilla oficial de certificado de retención",
            "Generación masiva en PDF por NIT",
            "Envío automático por email al proveedor",
            "Registro en la tabla procesamientos para trazabilidad",
        ],
    )

with tab_autorret:
    render_proximamente(
        titulo="Autorretenciones",
        descripcion=(
            "Si la empresa es autorretenedora (Decreto 2201/2016), liquida "
            "automáticamente las autorretenciones a título de renta."
        ),
        fases=[
            "Detección desde la tabla empresas (campo es_autorretenedor)",
            "Aplicación de tarifas según actividad económica",
            "Liquidación mensual conforme al formulario 350",
        ],
    )
