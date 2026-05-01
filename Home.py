"""
Plataforma Contable Web - Punto de entrada con navegación agrupada

Usa st.navigation() (Streamlit 1.36+) para agrupar las páginas en secciones:
    - 🤖 Asistente Contable: módulos de procesamiento contable diario
    - 📊 Herramientas Tributarias: declaraciones e información tributaria
    - ⚙️ Sistema: configuración y administración

A diferencia del modo automático con pages/, aquí controlamos explícitamente
qué páginas se ven, en qué orden, y bajo qué grupo. Las páginas de cada
módulo viven en app/<seccion>/<modulo>.py
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
            "Si eres administrador, ve a la sección **Configuración** para "
            "crear tu primera empresa. Si no, contacta a tu administrador."
        )
        return

    # Métricas superiores
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Empresas asignadas", len(empresas))
    with col2:
        st.metric("Módulos disponibles", "11 totales")
    with col3:
        st.metric("Sesión", "Activa")

    st.markdown("### 📦 Secciones de la plataforma")

    col_a, col_b = st.columns(2)

    with col_a:
        with st.container(border=True):
            st.markdown("#### 🤖 Asistente Contable")
            st.markdown(
                "_Procesamiento contable mensual: facturas, pagos, nómina._"
            )
            st.markdown(
                "- 💵 Caja Menor\n"
                "- 🛒 Compras DIAN\n"
                "- 💼 Nómina\n"
                "- 📝 Provisiones\n"
                "- 📎 PILA"
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

    st.markdown("### 🔒 Seguridad")
    st.info(
        "🛡️ Tu sesión está protegida por autenticación Supabase. "
        "Todos los archivos que subes quedan asociados solo a la empresa activa "
        "y no son visibles para usuarios de otras empresas."
    )


# ============================================================
# Definir las páginas y sus grupos con st.Page + st.navigation
# ============================================================

# Página de inicio (sin grupo, va arriba del todo)
pagina_inicio = st.Page(
    home_page,
    title="Inicio",
    icon="🏠",
    default=True,
    url_path="/",
)

# Sección: Asistente Contable
asistente_caja = st.Page(
    "app/asistente/caja_menor.py",
    title="Caja Menor",
    icon="💵",
    url_path="/caja-menor",
)
asistente_compras = st.Page(
    "app/asistente/compras_dian.py",
    title="Compras DIAN",
    icon="🛒",
    url_path="/compras-dian",
)
asistente_nomina = st.Page(
    "app/asistente/nomina.py",
    title="Nómina",
    icon="💼",
    url_path="/nomina",
)
asistente_prov = st.Page(
    "app/asistente/provisiones.py",
    title="Provisiones",
    icon="📝",
    url_path="/provisiones",
)
asistente_pila = st.Page(
    "app/asistente/pila.py",
    title="PILA",
    icon="📎",
    url_path="/pila",
)

# Sección: Herramientas Tributarias
trib_exogena = st.Page(
    "app/tributarias/exogena.py",
    title="Información Exógena",
    icon="📑",
    url_path="/exogena",
)
trib_renta = st.Page(
    "app/tributarias/renta.py",
    title="Declaración de Renta",
    icon="📝",
    url_path="/renta",
)
trib_iva = st.Page(
    "app/tributarias/iva.py",
    title="IVA y reteIVA",
    icon="💸",
    url_path="/iva",
)
trib_retencion = st.Page(
    "app/tributarias/retencion.py",
    title="Retención en la Fuente",
    icon="🧾",
    url_path="/retencion",
)
trib_saludables = st.Page(
    "app/tributarias/saludables.py",
    title="Impuestos Saludables",
    icon="🥤",
    url_path="/saludables",
)

# Sección: Sistema
sistema_config = st.Page(
    "app/sistema/configuracion.py",
    title="Configuración",
    icon="⚙️",
    url_path="/configuracion",
)


# Navegación agrupada
nav = st.navigation(
    {
        "": [pagina_inicio],
        "🤖 Asistente Contable": [
            asistente_caja,
            asistente_compras,
            asistente_nomina,
            asistente_prov,
            asistente_pila,
        ],
        "📊 Herramientas Tributarias": [
            trib_exogena,
            trib_renta,
            trib_iva,
            trib_retencion,
            trib_saludables,
        ],
        "⚙️ Sistema": [sistema_config],
    },
    position="sidebar",
)


# Ejecutar la página seleccionada
nav.run()
