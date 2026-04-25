"""
Plataforma Contable Web - Página principal

Esta es la entrada de la aplicación. Muestra:
    - Formulario de login si no hay sesión
    - Dashboard de bienvenida + selector de empresa si hay sesión
    - Lista de módulos disponibles SEGÚN la empresa activa

Las páginas de módulos están en pages/ y solo son accesibles cuando
hay sesión iniciada Y el módulo está habilitado para la empresa.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from auth.login import require_auth, sidebar_user_info, current_user
from auth.empresas import seleccionar_empresa_sidebar, empresas_del_usuario, empresa_activa
from auth import modulos as mod_sys
from auth.superadmin import es_superadmin


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
# Autenticación
# ============================================================

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()


# ============================================================
# Dashboard
# ============================================================

user = current_user()
st.title("📊 Plataforma Contable")
st.markdown(f"Bienvenido, **{user['email']}**")
st.markdown("---")

empresas = empresas_del_usuario()
emp = empresa_activa()

if not empresas:
    st.warning(
        "🏢 No tienes empresas asignadas todavía.\n\n"
        "Contacta al administrador del sistema."
    )
elif not emp:
    st.info("Selecciona una empresa en el panel lateral para ver tus módulos.")
else:
    # Cargar módulos del sistema y los habilitados para esta empresa
    catalogo = mod_sys.listar_modulos_sistema()
    habilitados = mod_sys.codigos_modulos_habilitados(emp["id"])
    superadm = es_superadmin()

    n_habilitados = len(habilitados)
    n_total = len(catalogo)

    # Métricas
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Empresas asignadas", len(empresas))
    with col2:
        st.metric(
            "Módulos habilitados",
            f"{n_habilitados} de {n_total}",
        )
    with col3:
        st.metric("Sesión", "Activa")

    # Tabla de módulos: marcamos cuáles están habilitados para esta empresa
    st.markdown(f"### 📦 Módulos para {emp['razon_social']}")

    if n_habilitados == 0 and not superadm:
        st.warning(
            "🔒 Esta empresa no tiene ningún módulo habilitado todavía. "
            "Pídele al superadmin que active al menos uno desde la "
            "sección Configuración."
        )
    else:
        st.caption(
            "Usa el menú lateral para entrar a cada módulo. "
            "Solo verás los módulos habilitados para tu empresa."
        )

        # Construir la tabla
        filas_md = ["| Módulo | Estado | Descripción |", "|---|---|---|"]
        for m in catalogo:
            emoji = m.get("emoji", "") or ""
            nombre = m.get("nombre", m["codigo"])
            descripcion = m.get("descripcion", "") or ""
            esta_habilitado = m["codigo"] in habilitados

            if esta_habilitado:
                estado = "✅ Disponible"
            elif superadm:
                estado = "⚪ No habilitado para esta empresa"
            else:
                # No mostrar a operadores los módulos no habilitados
                continue

            filas_md.append(f"| {emoji} **{nombre}** | {estado} | {descripcion} |")

        # Siempre mostrar Configuración como módulo accesible
        filas_md.append(
            "| ⚙️ **Configuración** | ✅ Disponible | Empresas, balance histórico, gestión de usuarios y módulos |"
        )

        st.markdown("\n".join(filas_md))

        if superadm:
            st.info(
                "👑 Eres **superadmin**: ves todos los módulos del sistema en "
                "el menú, aunque no estén habilitados para la empresa actual. "
                "Esto te permite gestionar todas las empresas."
            )

    st.markdown("### 🔒 Seguridad")
    st.info(
        "🛡️ Tu sesión está protegida por autenticación Supabase. "
        "Todos los archivos que subes quedan asociados solo a la empresa activa "
        "y no son visibles para usuarios de otras empresas."
    )
