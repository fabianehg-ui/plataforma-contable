"""
Módulo Información Exógena DIAN

Genera los 17 formatos del prevalidador DIAN AG 2025 a partir del balance auxiliar
y maestro de terceros importados. Conforme a Resolución 000227 de 2025.

Estado actual: estructura base. La lógica del motor está validada contra los XSD
oficiales pero falta integrar con la BD y el bucket de Supabase.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import (
    seleccionar_empresa_sidebar,
    require_empresa,
    require_rol,
)
from core.utils.ui_tributarias import render_pagina_tributaria, render_proximamente


# ============================================================
# Guardia de autenticación
# ============================================================

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()


# ============================================================
# Cabecera
# ============================================================

render_pagina_tributaria(
    titulo="Información Exógena DIAN",
    descripcion="Generación de los 17 formatos del prevalidador AG 2025 según Res. 000227/2025",
    icono="📑",
)


# ============================================================
# Estado: información sobre obligación
# ============================================================

st.subheader("📅 Estado de la obligación")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Año gravable", "2025")
with col2:
    st.metric("Vencimiento PJ", "14 mayo - 12 jun 2026")
with col3:
    st.metric("UVT 2025", "$49.799")

st.markdown("---")


# ============================================================
# Tabs principales del módulo
# ============================================================

tab_resumen, tab_mapeo, tab_generar, tab_envios, tab_hallazgos = st.tabs([
    "📊 Resumen",
    "🗂️ Mapeo PUC → DIAN",
    "⚙️ Generar XML",
    "📥 Envíos",
    "⚠️ Hallazgos",
])


# ============================================================
# Tab Resumen
# ============================================================

with tab_resumen:
    st.markdown("### Resumen del año gravable")

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("Formatos disponibles", "17")
    with col_b:
        st.metric("Generados", "—")
    with col_c:
        st.metric("Validados XSD", "—")
    with col_d:
        st.metric("Enviados DIAN", "—")

    st.markdown("---")
    st.markdown("### Formatos que genera el módulo")

    formatos = pd.DataFrame([
        {"Código": "1001", "Nombre": "Pagos o abonos en cuenta y retenciones practicadas", "Versión": "10"},
        {"Código": "1003", "Nombre": "Retenciones en la fuente que le practicaron", "Versión": "7"},
        {"Código": "1004", "Nombre": "Descuentos tributarios solicitados", "Versión": "8"},
        {"Código": "1005", "Nombre": "IVA por pagar - Descontable", "Versión": "8"},
        {"Código": "1006", "Nombre": "IVA por pagar - Generado e impuesto al consumo", "Versión": "8"},
        {"Código": "1007", "Nombre": "Ingresos recibidos", "Versión": "9"},
        {"Código": "1008", "Nombre": "Saldos cuentas por cobrar al 31 de diciembre", "Versión": "7"},
        {"Código": "1009", "Nombre": "Saldos cuentas por pagar al 31 de diciembre", "Versión": "7"},
        {"Código": "1010", "Nombre": "Información de socios, accionistas y cooperados", "Versión": "9"},
        {"Código": "1011", "Nombre": "Información de las declaraciones tributarias", "Versión": "6"},
        {"Código": "1012", "Nombre": "Declaraciones, acciones, aportes e inversiones", "Versión": "7"},
        {"Código": "1056", "Nombre": "Pagos por secretarios generales del tesoro", "Versión": "10"},
        {"Código": "1647", "Nombre": "Ingresos recibidos para terceros", "Versión": "2"},
        {"Código": "2275", "Nombre": "Ingresos no constitutivos de renta ni ganancia", "Versión": "2"},
        {"Código": "2276", "Nombre": "Información de rentas de trabajo y pensiones", "Versión": "4"},
        {"Código": "2278", "Nombre": "Compra de bonos electrónicos / papel servicio", "Versión": "1"},
        {"Código": "5253", "Nombre": "Información de beneficiarios efectivos", "Versión": "2"},
    ])
    st.dataframe(formatos, use_container_width=True, hide_index=True)


# ============================================================
# Tab Mapeo
# ============================================================

with tab_mapeo:
    render_proximamente(
        titulo="Configuración del mapeo cuenta PUC → concepto DIAN",
        descripcion=(
            "Cada cuenta del PUC del cliente se asocia a un concepto DIAN y formato destino. "
            "El sistema sugiere el mapeo automáticamente desde el PUC oficial DIAN (570 cuentas) "
            "y permite ajustes manuales por empresa."
        ),
        fases=[
            "Cargar catálogos DIAN (882 conceptos, 17 formatos, 1.114 municipios) — datos ya extraídos",
            "Importar PUC del cliente desde balance auxiliar",
            "Auto-mapear contra el PUC oficial DIAN",
            "UI para revisar y ajustar mapeos manualmente",
        ],
        relacionados=[
            ("Compras DIAN", "Comparte el balance auxiliar como fuente"),
            ("Configuración", "Aquí se cargan las cuentas y mapeos del cliente"),
        ],
    )


# ============================================================
# Tab Generar XML
# ============================================================

with tab_generar:
    render_proximamente(
        titulo="Generación de archivos XML conforme a XSD oficial DIAN",
        descripcion=(
            "Motor validado contra los XSD del prevalidador AG 2025 v3.3.0-26. "
            "Genera archivos `Dmuisca_*.xml` listos para subir a DIAN MUISCA."
        ),
        fases=[
            "Conectar el balance + maestro de terceros + mapeo a la BD de Supabase",
            "Edge Function en Supabase que genera y guarda los XML en el bucket",
            "Validación XSD en el cliente antes de la descarga",
            "Histórico de envíos por empresa/año",
        ],
        relacionados=[
            ("DIAN XML", "Comparte el patrón de descarga de archivos por empresa"),
        ],
    )


# ============================================================
# Tab Envíos
# ============================================================

with tab_envios:
    render_proximamente(
        titulo="Histórico de envíos a DIAN",
        descripcion=(
            "Cada generación queda registrada con: año gravable, número de envío, "
            "estado (borrador, generado, validado XSD, enviado, aceptado, rechazado), "
            "cantidad de registros y valor total reportado por formato."
        ),
        fases=[
            "Tabla `envios_exogena` y `envio_formatos` en Supabase",
            "Storage en bucket `exogena-xml/{empresa_id}/{año}/envio_{n}/`",
            "UI de descarga individual y ZIP completo",
            "Marca de envío aceptado por DIAN con número de radicado",
        ],
    )


# ============================================================
# Tab Hallazgos
# ============================================================

with tab_hallazgos:
    render_proximamente(
        titulo="Hallazgos de auditoría automática",
        descripcion=(
            "El motor detecta automáticamente cuentas sin mapear, terceros sin "
            "datos completos, balances descuadrados, NITs inválidos, conceptos "
            "no vigentes y otros problemas que impedirían la presentación."
        ),
        fases=[
            "Tabla `hallazgos` con severidad (crítica, alta, media, informativa)",
            "Detección automática durante cada generación de XML",
            "UI para marcar hallazgos como resueltos",
            "Export a Excel del resumen de hallazgos para entregar al cliente",
        ],
    )
