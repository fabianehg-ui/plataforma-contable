"""
Plataforma Contable Web - Página principal

Esta es la entrada de la aplicación. Muestra:
    - Formulario de login si no hay sesión
    - Dashboard de bienvenida + selector de empresa si hay sesión

Las páginas de módulos están en app/pages/ y solo son accesibles
cuando hay sesión iniciada (cada una llama require_auth()).
"""
import sys
from pathlib import Path

# Añadir la raíz del proyecto al path para que los imports funcionen
# tanto en local como en Railway/Render
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from auth.login import require_auth, sidebar_user_info, current_user
from auth.empresas import seleccionar_empresa_sidebar, empresas_del_usuario


# ============================================================
# Configuración de la página
# ============================================================

st.set_page_config(
    page_title="Plataforma Contable",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# Guardia de autenticación
# ============================================================

require_auth()   # Si no hay sesión, muestra login y detiene aquí


# ============================================================
# Sidebar: info del usuario + selector de empresa
# ============================================================

seleccionar_empresa_sidebar()
sidebar_user_info()


# ============================================================
# Dashboard de bienvenida
# ============================================================

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
else:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Empresas asignadas", len(empresas))
    with col2:
        st.metric("Módulos disponibles", "4 activos + 2 próximos")
    with col3:
        st.metric("Sesión", "Activa")

    st.markdown("### 📦 Módulos disponibles")
    st.markdown(
        """
        Usa el menú lateral para navegar entre los módulos:

        | Módulo | Estado | Descripción |
        |---|---|---|
        | 💵 **Caja Menor** | ✅ Disponible | Genera asientos de egresos de caja menor |
        | 📎 **PILA** | ✅ Disponible | Lee PDF de planilla y extrae empleados/totales |
        | 🛒 **Compras DIAN** | ✅ Disponible | Procesa facturas de proveedores DIAN con regla histórica del balance |
        | ⚙️ **Configuración** | ✅ Disponible | Empresas, balance histórico, gestión de usuarios |
        | 💼 **Nómina** | 🚧 En desarrollo | Genera asiento mensual de nómina |
        | 📝 **Provisiones** | 🚧 En desarrollo | Provisión de prestaciones sociales |
        """
    )

    st.markdown("### 🔒 Seguridad")
    st.info(
        "🛡️ Tu sesión está protegida por autenticación Supabase. "
        "Todos los archivos que subes quedan asociados solo a la empresa activa "
        "y no son visibles para usuarios de otras empresas."
    )
