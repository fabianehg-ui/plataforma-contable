"""
Helpers para gestión de superadministradores del sistema.
"""
from __future__ import annotations
import streamlit as st

from db.supabase_client import get_supabase
from auth.login import current_user


def es_superadmin() -> bool:
    """Retorna True si el usuario actual es superadmin del sistema."""
    user = current_user()
    if not user:
        return False

    # Cache en session_state para no consultar cada vez
    cache_key = f"_es_superadmin_{user['id']}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    sb = get_supabase()
    try:
        resp = sb.table("superadmins").select("usuario_id").eq(
            "usuario_id", user["id"]
        ).execute()
        es_sa = len(resp.data or []) > 0
    except Exception:
        es_sa = False

    st.session_state[cache_key] = es_sa
    return es_sa


def require_superadmin():
    """Detiene la página si el usuario no es superadmin."""
    if not es_superadmin():
        st.error(
            "⛔ Acceso denegado. Esta sección es solo para administradores "
            "del sistema."
        )
        st.stop()
