"""
Gestión multi-empresa. Cada usuario puede pertenecer a varias empresas
con diferentes roles (admin, operador, consulta).

Funciones principales:
    - empresas_del_usuario(): lista de empresas a las que tiene acceso
    - seleccionar_empresa(): widget en sidebar para cambiar de empresa
    - empresa_activa(): retorna la empresa actualmente seleccionada
    - require_empresa(): se usa en páginas que requieren empresa activa
"""
import streamlit as st
from db.supabase_client import get_supabase
from auth.login import current_user


def empresas_del_usuario():
    """Retorna [{id, nit, razon_social, rol}, ...] para el usuario actual.

    Privacidad multi-empresa:
    - Usuario normal: SOLO las empresas a las que fue asignado (usuario_empresa).
    - Superadmin (usuario general): TODAS las empresas, y puede cambiar entre
      ellas en cualquier momento desde el sidebar.
    """
    user = current_user()
    if not user:
        return []

    sb = get_supabase()

    # Superadmin → acceso a todas las empresas (bypasa RLS con la función admin)
    try:
        from auth.superadmin import es_superadmin
        if es_superadmin():
            resp = sb.rpc("admin_listar_empresas").execute()
            todas = []
            for e in (resp.data or []):
                if e.get("activa") is False:
                    continue
                todas.append({
                    "id": e["id"], "nit": e.get("nit"),
                    "razon_social": e.get("razon_social"), "rol": "admin",
                })
            todas.sort(key=lambda x: (x.get("razon_social") or "").upper())
            return todas
    except Exception:
        pass

    try:
        resp = (
            sb.table("usuario_empresa")
              .select("rol, empresas(id, nit, razon_social)")
              .eq("usuario_id", user["id"])
              .execute()
        )
    except Exception as e:
        st.error(f"Error leyendo empresas: {e}")
        return []

    empresas = []
    for row in resp.data or []:
        emp = row.get("empresas") or {}
        if not emp:
            continue
        empresas.append({
            "id": emp["id"],
            "nit": emp["nit"],
            "razon_social": emp["razon_social"],
            "rol": row["rol"],
        })
    return empresas


def empresa_activa():
    """Retorna la empresa seleccionada en la sesión, o None."""
    return st.session_state.get("empresa_activa")


def seleccionar_empresa_sidebar():
    """Widget en el sidebar para seleccionar / cambiar empresa."""
    empresas = empresas_del_usuario()
    if not empresas:
        with st.sidebar:
            st.warning(
                "No tienes empresas asignadas. Contacta al administrador."
            )
        return None

    # Si solo hay una, seleccionarla automáticamente
    if len(empresas) == 1 and not empresa_activa():
        st.session_state["empresa_activa"] = empresas[0]

    _es_sa = False
    try:
        from auth.superadmin import es_superadmin
        _es_sa = es_superadmin()
    except Exception:
        _es_sa = False

    with st.sidebar:
        st.markdown("### 🏢 Empresa activa")
        if _es_sa:
            st.caption("🔑 Superadmin — acceso a todas las empresas")
        elif len(empresas) == 1:
            st.caption("Acceso restringido a tu empresa asignada")
        nombres = [f"{e['razon_social']} ({e['nit']})" for e in empresas]
        actual = empresa_activa()
        idx_default = 0
        if actual:
            for i, e in enumerate(empresas):
                if e["id"] == actual["id"]:
                    idx_default = i
                    break

        seleccion = st.selectbox(
            "Selecciona empresa",
            options=range(len(empresas)),
            format_func=lambda i: nombres[i],
            index=idx_default,
            key="sel_empresa",
            label_visibility="collapsed",
        )
        nueva = empresas[seleccion]
        if not actual or actual["id"] != nueva["id"]:
            st.session_state["empresa_activa"] = nueva
            st.rerun()

        st.caption(f"Rol: `{nueva['rol']}`")

    return nueva


def require_empresa():
    """Garantiza que hay una empresa activa. Detiene la página si no."""
    emp = empresa_activa()
    if not emp:
        st.warning("⚠️ Selecciona una empresa en el panel lateral para continuar.")
        st.stop()
    return emp


def require_rol(roles_permitidos):
    """Verifica que el usuario tiene uno de los roles dados en la empresa activa.

    Args:
        roles_permitidos: lista, ej ['admin', 'operador']
    """
    emp = require_empresa()
    if emp["rol"] not in roles_permitidos:
        st.error(
            f"⛔ No tienes permisos para usar este módulo. "
            f"Tu rol es '{emp['rol']}', se requiere uno de: {roles_permitidos}"
        )
        st.stop()
    return emp
