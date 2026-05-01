"""
Plataforma Contable Web - Punto de entrada con navegación agrupada

Usa st.navigation() (Streamlit 1.36+) para agrupar las páginas en 3 secciones:
    - 🤖 Asistente Contable: módulos de procesamiento contable diario
    - 📊 Herramientas Tributarias: declaraciones e información tributaria
    - ⚙️ Sistema: configuración y panel de administración

Las páginas viven en pages/ con prefijos numéricos (1_, 2_, etc.).
Los nombres son ASCII para evitar problemas con GitHub web upload.
Los emojis los pone st.Page() vía el parámetro icon=, no el filename.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from auth.login import login_form, is_authenticated, current_user


# ============================================================
# Configuración global de la app (única llamada en todo el proyecto)
# ============================================================

st.set_page_config(
    page_title="Plataforma Contable",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# Si no hay sesión, mostrar login y detener
# ============================================================

if not is_authenticated():
    login_form()
    st.stop()


# ============================================================
# Página de inicio (dashboard de bienvenida)
# ============================================================

def home_page():
    """Dashboard de bienvenida con tarjetas de cada sección."""
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
            "🏢 No tienes empresas asignadas todavía.\n\n"
            "Si eres administrador, ve a **Configuración** o al **Panel Admin** "
            "para crear tu primera empresa. Si no, contacta a tu administrador."
        )
        return

    # Métricas superiores
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Empresas asignadas", len(empresas))
    with col2:
        st.metric("Módulos disponibles", "14")
    with col3:
        st.metric("Sesión", "Activa")

    st.markdown("### 📦 Secciones de la plataforma")

    col_a, col_b = st.columns(2)

    with col_a:
        with st.container(border=True):
            st.markdown("#### 🤖 Asistente Contable")
            st.markdown(
                "_Procesamiento contable diario y mensual._"
            )
            st.markdown(
                "- 💵 Caja Menor\n"
                "- 🛒 Compras DIAN\n"
                "- 📊 Compras y Egresos\n"
                "- 💼 Nómina\n"
                "- 📝 Provisiones\n"
                "- 🛍️ Ventas C13\n"
                "- 🧾 Ingresos POS\n"
                "- 📎 PILA\n"
                "- 📥 DIAN XML"
            )

    with col_b:
        with st.container(border=True):
            st.markdown("#### 📊 Herramientas Tributarias")
            st.markdown(
                "_Declaraciones e información tributaria periódica._"
            )
            st.markdown(
                "- 📑 Información Exógena\n"
                "- 📝 Declaración de Renta\n"
                "- 💸 IVA y reteIVA\n"
                "- 🧾 Retención en la Fuente\n"
                "- 🥤 Impuestos Saludables (INC, IBUA, ICUI)"
            )

    st.markdown("### ⚙️ Sistema")
    st.markdown(
        "- 🛡️ **Panel Admin** — gestión de superadmin (solo superadmins)\n"
        "- ⚙️ **Configuración** — empresas, archivos, usuarios, módulos"
    )

    st.markdown("---")
    st.info(
        "🛡️ Tu sesión está protegida por autenticación Supabase. "
        "Todos los archivos que subes quedan asociados solo a la empresa activa "
        "y no son visibles para usuarios de otras empresas."
    )


# ============================================================
# Definir las páginas con st.Page + st.navigation
# ============================================================

# Página de inicio
pagina_inicio = st.Page(
    home_page,
    title="Inicio",
    icon="🏠",
    default=True,
    url_path="inicio",
)

# ----- Sección: Asistente Contable -----
asistente_caja = st.Page(
    "app_pages/1_Caja_Menor.py",
    title="Caja Menor",
    icon="💵",
    url_path="caja-menor",
)
asistente_compras_dian = st.Page(
    "app_pages/2_Compras_DIAN.py",
    title="Compras DIAN",
    icon="🛒",
    url_path="compras-dian",
)
asistente_compras_eg = st.Page(
    "app_pages/3a_Compras_y_Egresos.py",
    title="Compras y Egresos",
    icon="📊",
    url_path="compras-egresos",
)
asistente_nomina = st.Page(
    "app_pages/3_Nomina.py",
    title="Nómina",
    icon="💼",
    url_path="nomina",
)
asistente_prov = st.Page(
    "app_pages/4_Provisiones.py",
    title="Provisiones",
    icon="📝",
    url_path="provisiones",
)
asistente_ventas_c13 = st.Page(
    "app_pages/4a_Ventas_C13.py",
    title="Ventas C13",
    icon="🛍️",
    url_path="ventas-c13",
)
asistente_pos = st.Page(
    "app_pages/4b_Ingresos_POS.py",
    title="Ingresos POS",
    icon="🧾",
    url_path="ingresos-pos",
)
asistente_pila = st.Page(
    "app_pages/5_PILA.py",
    title="PILA",
    icon="📎",
    url_path="pila",
)
asistente_dian_xml = st.Page(
    "app_pages/5a_DIAN_XML.py",
    title="DIAN XML",
    icon="📥",
    url_path="dian-xml",
)

# ----- Sección: Herramientas Tributarias -----
trib_exogena = st.Page(
    "app_pages/7_Informacion_Exogena.py",
    title="Información Exógena",
    icon="📑",
    url_path="exogena",
)
trib_renta = st.Page(
    "app_pages/8_Declaracion_Renta.py",
    title="Declaración de Renta",
    icon="📝",
    url_path="renta",
)
trib_iva = st.Page(
    "app_pages/9_IVA.py",
    title="IVA y reteIVA",
    icon="💸",
    url_path="iva",
)
trib_retencion = st.Page(
    "app_pages/10_Retencion_Fuente.py",
    title="Retención en la Fuente",
    icon="🧾",
    url_path="retencion",
)
trib_saludables = st.Page(
    "app_pages/11_Impuestos_Saludables.py",
    title="Impuestos Saludables",
    icon="🥤",
    url_path="saludables",
)

# ----- Sección: Sistema -----
sistema_panel_admin = st.Page(
    "app_pages/0_Panel_Admin.py",
    title="Panel Admin",
    icon="🛡️",
    url_path="panel-admin",
)
sistema_config = st.Page(
    "app_pages/6_Configuracion.py",
    title="Configuración",
    icon="⚙️",
    url_path="configuracion",
)


# ============================================================
# Navegación agrupada
# ============================================================

nav = st.navigation(
    {
        "": [pagina_inicio],
        "🤖 Asistente Contable": [
            asistente_caja,
            asistente_compras_dian,
            asistente_compras_eg,
            asistente_nomina,
            asistente_prov,
            asistente_ventas_c13,
            asistente_pos,
            asistente_pila,
            asistente_dian_xml,
        ],
        "📊 Herramientas Tributarias": [
            trib_exogena,
            trib_renta,
            trib_iva,
            trib_retencion,
            trib_saludables,
        ],
        "⚙️ Sistema": [
            sistema_panel_admin,
            sistema_config,
        ],
    },
    position="sidebar",
)


# Ejecutar la página seleccionada
nav.run()
