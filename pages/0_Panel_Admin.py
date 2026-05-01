"""
🔧 Panel de Super Administrador

Solo accesible para usuarios marcados como superadmin en la tabla
public.superadmins.

Permite:
    - Ver todas las empresas del sistema
    - Crear, editar, desactivar empresas
    - Ver todos los usuarios
    - Asignar usuarios a empresas con diferentes roles
    - Remover usuarios de empresas
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from auth.login import require_auth, sidebar_user_info, current_user
from auth.empresas import seleccionar_empresa_sidebar
from auth.superadmin import require_superadmin, es_superadmin
from db.supabase_client import get_supabase


require_auth()
require_superadmin()

seleccionar_empresa_sidebar()
sidebar_user_info()


# ============================================================
# Encabezado
# ============================================================

st.title("🔧 Panel de Super Administrador")
st.caption(
    f"Conectado como: **{current_user()['email']}** · "
    f"Acceso global al sistema"
)
st.markdown("---")


# ============================================================
# Helpers para llamar a las funciones RPC de Supabase
# ============================================================

def listar_empresas_admin() -> pd.DataFrame:
    """Usa la función SQL admin_listar_empresas() que bypasa RLS."""
    sb = get_supabase()
    try:
        resp = sb.rpc("admin_listar_empresas").execute()
        if not resp.data:
            return pd.DataFrame(columns=[
                "id", "nit", "razon_social", "creada_en", "activa",
                "cantidad_usuarios"
            ])
        return pd.DataFrame(resp.data)
    except Exception as e:
        st.error(f"Error al listar empresas: {e}")
        return pd.DataFrame()


def listar_usuarios_admin() -> pd.DataFrame:
    """Lista todos los usuarios del sistema."""
    sb = get_supabase()
    try:
        resp = sb.rpc("admin_listar_usuarios").execute()
        if not resp.data:
            return pd.DataFrame()
        return pd.DataFrame(resp.data)
    except Exception as e:
        st.error(f"Error al listar usuarios: {e}")
        return pd.DataFrame()


def listar_usuarios_empresa(empresa_id: str) -> pd.DataFrame:
    sb = get_supabase()
    try:
        resp = sb.rpc(
            "admin_usuarios_de_empresa",
            {"p_empresa_id": empresa_id}
        ).execute()
        if not resp.data:
            return pd.DataFrame()
        return pd.DataFrame(resp.data)
    except Exception as e:
        st.error(f"Error al listar usuarios de empresa: {e}")
        return pd.DataFrame()


def crear_empresa(nit: str, razon_social: str) -> bool:
    sb = get_supabase()
    try:
        sb.table("empresas").insert({
            "nit": nit,
            "razon_social": razon_social,
            "creada_por": current_user()["id"],
            "activa": True,
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error al crear empresa: {e}")
        return False


def actualizar_empresa(empresa_id: str, nit: str, razon_social: str, activa: bool) -> bool:
    sb = get_supabase()
    try:
        sb.table("empresas").update({
            "nit": nit,
            "razon_social": razon_social,
            "activa": activa,
        }).eq("id", empresa_id).execute()
        return True
    except Exception as e:
        st.error(f"Error al actualizar empresa: {e}")
        return False


def asignar_usuario_empresa(usuario_id: str, empresa_id: str, rol: str) -> bool:
    sb = get_supabase()
    try:
        # Si ya existe la asignación, actualiza el rol
        existe = sb.table("usuario_empresa").select("usuario_id").eq(
            "usuario_id", usuario_id
        ).eq("empresa_id", empresa_id).execute()
        if existe.data:
            sb.table("usuario_empresa").update({"rol": rol}).eq(
                "usuario_id", usuario_id
            ).eq("empresa_id", empresa_id).execute()
        else:
            sb.table("usuario_empresa").insert({
                "usuario_id": usuario_id,
                "empresa_id": empresa_id,
                "rol": rol,
            }).execute()
        return True
    except Exception as e:
        st.error(f"Error al asignar usuario: {e}")
        return False


def remover_usuario_empresa(usuario_id: str, empresa_id: str) -> bool:
    sb = get_supabase()
    try:
        sb.table("usuario_empresa").delete().eq(
            "usuario_id", usuario_id
        ).eq("empresa_id", empresa_id).execute()
        return True
    except Exception as e:
        st.error(f"Error al remover usuario: {e}")
        return False


# ============================================================
# Tabs del panel
# ============================================================

tab_emp, tab_users, tab_asign = st.tabs([
    "🏢 Empresas",
    "👥 Usuarios",
    "🔗 Asignaciones",
])


# ============================================================
# TAB 1 — EMPRESAS
# ============================================================

with tab_emp:
    col_head, col_btn = st.columns([3, 1])
    with col_head:
        st.markdown("### Empresas del sistema")
    with col_btn:
        if st.button("🔄 Recargar", key="reload_emp", use_container_width=True):
            st.rerun()

    df_emp = listar_empresas_admin()

    if df_emp.empty:
        st.info("No hay empresas registradas todavía.")
    else:
        # Métricas
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Total empresas", len(df_emp))
        with m2:
            activas = int(df_emp["activa"].sum()) if "activa" in df_emp.columns else 0
            st.metric("Activas", activas)
        with m3:
            total_users = int(df_emp["cantidad_usuarios"].sum()) if "cantidad_usuarios" in df_emp.columns else 0
            st.metric("Asignaciones totales", total_users)

        # Tabla
        st.dataframe(
            df_emp[["razon_social", "nit", "activa", "cantidad_usuarios", "creada_en"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "razon_social": "Razón Social",
                "nit": "NIT",
                "activa": st.column_config.CheckboxColumn("Activa"),
                "cantidad_usuarios": "Usuarios",
                "creada_en": st.column_config.DatetimeColumn("Creada", format="YYYY-MM-DD"),
            },
        )

    st.markdown("---")

    # Crear empresa
    st.markdown("### ➕ Crear nueva empresa")
    with st.form("form_crear_empresa", clear_on_submit=True):
        col_n, col_r = st.columns([1, 2])
        with col_n:
            nit_nuevo = st.text_input("NIT", placeholder="901.630.218-1")
        with col_r:
            razon_nueva = st.text_input("Razón Social", placeholder="EJEMPLO S.A.S")

        if st.form_submit_button("Crear empresa", type="primary"):
            if not nit_nuevo or not razon_nueva:
                st.error("Completa NIT y Razón Social")
            elif crear_empresa(nit_nuevo.strip(), razon_nueva.strip().upper()):
                st.success(f"✅ Empresa '{razon_nueva}' creada")
                st.rerun()

    st.markdown("---")

    # Editar empresa existente
    if not df_emp.empty:
        st.markdown("### ✏️ Editar empresa existente")
        opciones = {
            f"{r['razon_social']} ({r['nit']})": r["id"]
            for _, r in df_emp.iterrows()
        }
        empresa_sel = st.selectbox(
            "Selecciona empresa a editar",
            options=[""] + list(opciones.keys()),
            key="sel_editar_emp",
        )

        if empresa_sel:
            emp_id = opciones[empresa_sel]
            emp_data = df_emp[df_emp["id"] == emp_id].iloc[0]

            with st.form("form_editar_empresa"):
                col_n, col_r, col_a = st.columns([1, 2, 1])
                with col_n:
                    nit_edit = st.text_input("NIT", value=emp_data["nit"])
                with col_r:
                    razon_edit = st.text_input("Razón Social", value=emp_data["razon_social"])
                with col_a:
                    activa_edit = st.checkbox("Activa", value=bool(emp_data["activa"]))

                if st.form_submit_button("Guardar cambios", type="primary"):
                    if actualizar_empresa(emp_id, nit_edit, razon_edit, activa_edit):
                        st.success("✅ Empresa actualizada")
                        st.rerun()


# ============================================================
# TAB 2 — USUARIOS
# ============================================================

with tab_users:
    col_head, col_btn = st.columns([3, 1])
    with col_head:
        st.markdown("### Usuarios del sistema")
    with col_btn:
        if st.button("🔄 Recargar", key="reload_users", use_container_width=True):
            st.rerun()

    df_users = listar_usuarios_admin()

    if df_users.empty:
        st.info("No hay usuarios registrados.")
    else:
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Total usuarios", len(df_users))
        with m2:
            if "es_superadmin" in df_users.columns:
                sa_count = int(df_users["es_superadmin"].sum())
                st.metric("Super admins", sa_count)
        with m3:
            if "cantidad_empresas" in df_users.columns:
                promedio = float(df_users["cantidad_empresas"].mean())
                st.metric("Empresas/usuario (prom.)", f"{promedio:.1f}")

        st.dataframe(
            df_users[["email", "es_superadmin", "cantidad_empresas", "creado_en", "ultimo_login"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "email": "Email",
                "es_superadmin": st.column_config.CheckboxColumn("Super Admin"),
                "cantidad_empresas": "Empresas asignadas",
                "creado_en": st.column_config.DatetimeColumn("Registrado", format="YYYY-MM-DD"),
                "ultimo_login": st.column_config.DatetimeColumn("Último login", format="YYYY-MM-DD HH:mm"),
            },
        )

    st.markdown("---")
    st.info(
        "ℹ️ La creación de usuarios nuevos se hará en la próxima fase. "
        "Por ahora, los usuarios deben registrarse ellos mismos o crearlos "
        "desde Supabase → Authentication → Users."
    )


# ============================================================
# TAB 3 — ASIGNACIONES USUARIO-EMPRESA
# ============================================================

with tab_asign:
    st.markdown("### 🔗 Gestión de accesos por empresa")
    st.caption(
        "Asigna usuarios a empresas con diferentes roles "
        "(admin / operador / consulta)."
    )

    df_emp = listar_empresas_admin()
    df_users = listar_usuarios_admin()

    if df_emp.empty:
        st.warning("Primero crea al menos una empresa en la pestaña 'Empresas'.")
    elif df_users.empty:
        st.warning("No hay usuarios en el sistema.")
    else:
        # Selector de empresa
        opc_emp = {
            f"{r['razon_social']} ({r['nit']})": r["id"]
            for _, r in df_emp.iterrows()
        }
        emp_sel = st.selectbox(
            "Selecciona empresa",
            options=list(opc_emp.keys()),
            key="sel_emp_asign",
        )
        emp_id = opc_emp[emp_sel]

        # Mostrar usuarios actualmente asignados
        st.markdown(f"#### Usuarios con acceso a **{emp_sel}**")
        df_asign = listar_usuarios_empresa(emp_id)

        if df_asign.empty:
            st.info("Ningún usuario tiene acceso a esta empresa todavía.")
        else:
            for _, row in df_asign.iterrows():
                cols = st.columns([3, 2, 1])
                with cols[0]:
                    st.text(row["email"])
                with cols[1]:
                    st.text(f"Rol: {row['rol']}")
                with cols[2]:
                    if st.button(
                        "🗑️ Remover",
                        key=f"rm_{row['usuario_id']}_{emp_id}",
                        use_container_width=True,
                    ):
                        if remover_usuario_empresa(row["usuario_id"], emp_id):
                            st.success("Usuario removido")
                            st.rerun()

        st.markdown("---")

        # Asignar nuevo usuario
        st.markdown("#### ➕ Asignar nuevo usuario")

        # Filtrar usuarios que NO están ya asignados
        usuarios_asignados_ids = set(df_asign["usuario_id"].tolist()) if not df_asign.empty else set()
        df_users_disponibles = df_users[~df_users["id"].isin(usuarios_asignados_ids)]

        if df_users_disponibles.empty:
            st.info("Todos los usuarios ya tienen acceso a esta empresa.")
        else:
            with st.form(f"form_asign_{emp_id}", clear_on_submit=True):
                col_u, col_r, col_b = st.columns([3, 2, 1])
                with col_u:
                    opc_users = {
                        r["email"]: r["id"]
                        for _, r in df_users_disponibles.iterrows()
                    }
                    user_sel = st.selectbox(
                        "Usuario",
                        options=list(opc_users.keys()),
                        label_visibility="collapsed",
                    )
                with col_r:
                    rol_sel = st.selectbox(
                        "Rol",
                        options=["admin", "operador", "consulta"],
                        label_visibility="collapsed",
                    )
                with col_b:
                    submit = st.form_submit_button("Asignar", type="primary", use_container_width=True)

                if submit:
                    user_id = opc_users[user_sel]
                    if asignar_usuario_empresa(user_id, emp_id, rol_sel):
                        st.success(f"✅ {user_sel} asignado como {rol_sel}")
                        st.rerun()
