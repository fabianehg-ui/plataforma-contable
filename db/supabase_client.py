"""
Cliente Supabase compartido por toda la aplicación.

Usa st.secrets para obtener las credenciales. En desarrollo local pueden
estar en .streamlit/secrets.toml; en Railway/Render, se configuran como
variables de entorno (Streamlit las lee automáticamente).
"""
import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_supabase() -> Client:
    """Retorna el cliente Supabase. Se cachea para que sea único."""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["anon_key"]
    except (KeyError, FileNotFoundError):
        st.error(
            "⚠️ No se encontraron credenciales de Supabase. "
            "Revisa .streamlit/secrets.toml o las variables de entorno."
        )
        st.stop()

    return create_client(url, key)


@st.cache_resource
def get_supabase_admin() -> Client:
    """Cliente con permisos de administrador (service_role).
    Usar SOLO para operaciones que requieren bypass de RLS (ej: crear empresa
    y asignar usuario en una transacción). Nunca exponer al frontend."""
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["service_key"]
    except (KeyError, FileNotFoundError):
        return None

    return create_client(url, key)
