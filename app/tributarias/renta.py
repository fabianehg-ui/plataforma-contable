"""
Módulo Declaración de Renta

Genera los formularios 110 (personas jurídicas) y 210 (personas naturales)
a partir del balance fiscal y la conciliación contable-fiscal.
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
    titulo="Declaración de Renta",
    descripcion="Formularios 110 (PJ) y 210 (PN) con conciliación contable-fiscal",
    icono="📝",
)


tab_general, tab_concil, tab_form110, tab_form210, tab_anexos = st.tabs([
    "📊 Datos generales",
    "🔄 Conciliación fiscal",
    "📄 Formulario 110",
    "📄 Formulario 210",
    "📎 Anexos",
])

with tab_general:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Año gravable", "2025")
    with col2:
        st.metric("UVT 2025", "$49.799")
    with col3:
        st.metric("Tipo persona", empresa.get("razon_social", "—"))

    st.markdown("---")

    render_proximamente(
        titulo="Configuración inicial de la declaración",
        descripcion=(
            "Aquí se define el tipo de declarante, régimen tributario, actividad "
            "económica principal, y se cargan los saldos iniciales del patrimonio."
        ),
        fases=[
            "Detección automática de tipo persona desde la tabla empresas",
            "Cargue de patrimonio inicial al 1° de enero del año gravable",
            "Selector de régimen ordinario / régimen simple",
        ],
    )

with tab_concil:
    render_proximamente(
        titulo="Conciliación contable a fiscal (ESF/ERI fiscal)",
        descripcion=(
            "Convierte los saldos contables en saldos fiscales aplicando ajustes: "
            "depreciaciones fiscales, gastos no deducibles, ingresos no constitutivos, "
            "rentas exentas, descuentos tributarios."
        ),
        fases=[
            "Importar saldos contables desde el balance",
            "Aplicar reglas de conciliación configurables por empresa",
            "Reporte de diferencias contable vs fiscal",
            "Conexión con Información Exógena (F1011, F1012)",
        ],
        relacionados=[
            ("Información Exógena", "Comparte el balance fiscal anual"),
            ("IVA y reteIVA", "Las declaraciones bimestrales alimentan el agregado anual"),
        ],
    )

with tab_form110:
    render_proximamente(
        titulo="Formulario 110 - Personas jurídicas y asimiladas",
        descripcion=(
            "Genera el formulario oficial DIAN para personas jurídicas. Incluye "
            "renglones de patrimonio, ingresos, costos, deducciones, descuentos, "
            "anticipos y saldos a pagar/favor."
        ),
        fases=[
            "Mapeo cuenta PUC → casilla del formulario 110",
            "Cálculo automático de impuesto sobre renta y complementarios",
            "Liquidación de anticipo del año siguiente",
            "Generación del formulario en formato oficial DIAN (PDF/XML)",
        ],
    )

with tab_form210:
    render_proximamente(
        titulo="Formulario 210 - Personas naturales residentes",
        descripcion=(
            "Genera el formulario oficial DIAN para personas naturales. Maneja las "
            "5 cédulas tributarias (general, pensiones, dividendos, ganancias ocasionales)."
        ),
        fases=[
            "Cargue del Formato 2276 (rentas trabajo) desde Información Exógena",
            "Cédula general: rentas de trabajo, capital y no laborales",
            "Aplicación de rentas exentas y deducciones por tope UVT",
            "Cálculo de tarifa progresiva",
        ],
        relacionados=[
            ("Información Exógena", "El formato 2276 alimenta directamente la cédula laboral"),
        ],
    )

with tab_anexos:
    render_proximamente(
        titulo="Anexos y documentos soporte",
        descripcion=(
            "Genera el conjunto de anexos que respaldan la declaración: "
            "informe de gestión, certificados de retención, conciliación bancaria, "
            "formato 1732 (estados financieros para fines fiscales)."
        ),
        fases=[
            "Formato 1732 - Información con relevancia tributaria",
            "Certificados de retención emitidos automáticamente",
            "Conciliación bancaria del último mes",
        ],
    )
