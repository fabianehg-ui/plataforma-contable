"""
Plataforma Contable Web - Punto de entrada simplificado.

SIMPLIFICACIÓN v0.4 (mayo 2026):
    El menú visible está reducido a 2 módulos operativos:
      1. 🧾 Ventas POS          → app_pages/4b_Ingresos_POS.py
      2. 📥 Descargador XML DIAN → app_pages/5b_Descargador_XML.py (NUEVO)

    El resto de páginas (Caja Menor, Compras, Nómina, RADIAN, Exógena, Renta,
    IVA, Retención, Saludables, Provisiones, Ventas C13, PILA, Token DIAN
    standalone, etc.) NO se incluyen en la navegación pero los archivos siguen
    en `app_pages/` para reactivación futura.

    Para reactivar alguna: agregarla a la sección de `nav` abajo.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from auth.login import login_form, is_authenticated, current_user


# ============================================================
# Configuración global
# ============================================================

st.set_page_config(
    page_title="Plataforma Contable",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# Login obligatorio
# ============================================================

if not is_authenticated():
    login_form()
    st.stop()


# ============================================================
# Página de inicio (versión simplificada)
# ============================================================

def home_page():
    """Dashboard de bienvenida con las 2 tarjetas activas."""
    from auth.login import sidebar_user_info
    from auth.empresas import (
        seleccionar_empresa_sidebar,
        empresas_del_usuario,
    )

    seleccionar_empresa_sidebar()
    sidebar_user_info()

    user = current_user()
    st.title("📊 Plataforma Contable")
    st.markdown(f"Bienvenido, **{user['email']}**")
    st.markdown("---")

    empresas = empresas_del_usuario()
    if not empresas:
        st.warning(
            "🏢 No tienes empresas asignadas todavía. "
            "Contacta al administrador."
        )
        return

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Empresas asignadas", len(empresas))
    with col2:
        st.metric("Módulos activos", "2")

    st.markdown("### 📦 Módulos activos")

    col_a, col_b = st.columns(2)

    with col_a:
        with st.container(border=True):
            st.markdown("#### 🧾 Ventas POS")
            st.markdown(
                "Sube los reportes POS del mes (CHILI, L3AF, HENKO) y "
                "genera el plano contable de ingresos por día por sucursal. "
                "Incluye desglose automático de propinas vía la fórmula "
                "del impuesto al consumo (INC ÷ 8%)."
            )

    with col_b:
        with st.container(border=True):
            st.markdown("#### 📥 Descargador XML DIAN")
            st.markdown(
                "Sube el Excel del Token DIAN como referencia, elige los "
                "tipos de documentos a descargar (FE, NC, ND, DSE) para "
                "recibidos y los prefijos para emitidos, descarga directo "
                "desde DIAN y procesa los XMLs al plano contable + plano "
                "de terceros nuevos para Siigo."
            )

    st.markdown("---")
    st.info(
        "ℹ️ El resto de módulos (Caja Menor, Nómina, Tributarios, etc.) "
        "están temporalmente ocultos pero conservados en el repo. "
        "Para reactivarlos, editar `Home.py`."
    )


# ============================================================
# Definir las 2 páginas VISIBLES
# ============================================================

pagina_inicio = st.Page(
    home_page,
    title="Inicio",
    icon="🏠",
    default=True,
    url_path="inicio",
)

asistente_pos = st.Page(
    "app_pages/4b_Ingresos_POS.py",
    title="Ventas POS",
    icon="🧾",
    url_path="ventas-pos",
)
asistente_xml = st.Page(
    "app_pages/5b_Descargador_XML.py",
    title="Descargador XML DIAN",
    icon="📥",
    url_path="descargador-xml",
)


# ============================================================
# Navegación: solo 2 módulos activos en el sidebar
# ============================================================

nav = st.navigation(
    {
        "": [pagina_inicio],
        "🤖 Asistente Contable": [
            asistente_pos,
            asistente_xml,
        ],
    },
    position="sidebar",
)

nav.run()
