"""
Cliente Supabase compartido por toda la aplicacion.

Lee credenciales en este orden:
  1. Variables de entorno: SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY
     (ideal para produccion en Railway, Render, etc.)
  2. st.secrets con estructura [supabase] url/anon_key/service_key
     (ideal para desarrollo local con .streamlit/secrets.toml)
"""
import os
import streamlit as st
from supabase import create_client, Client


def _get_cred(env_name, secrets_section, secrets_key):
    """Busca una credencial primero en variables de entorno, luego en st.secrets."""
    val = os.environ.get(env_name)
    if val:
        return val.strip()
    try:
        return st.secrets[secrets_section][secrets_key]
    except (KeyError, FileNotFoundError, AttributeError):
        return None


@st.cache_resource
def get_supabase() -> Client:
    """Retorna el cliente Supabase. Se cachea para que sea unico."""
    url = _get_cred("SUPABASE_URL", "supabase", "url")
    key = _get_cred("SUPABASE_ANON_KEY", "supabase", "anon_key")

    if not url or not key:
        st.error(
            "No se encontraron credenciales de Supabase. "
            "Configura SUPABASE_URL y SUPABASE_ANON_KEY como variables de entorno, "
            "o revisa .streamlit/secrets.toml en desarrollo local."
        )
        st.stop()

    url = url.rstrip("/")
    return create_client(url, key)


@st.cache_resource
def get_supabase_admin() -> Client:
    """Cliente con permisos de administrador (service_role)."""
    url = _get_cred("SUPABASE_URL", "supabase", "url")
    key = _get_cred("SUPABASE_SERVICE_KEY", "supabase", "service_key")

    if not url or not key:
        return None

    url = url.rstrip("/")
    return create_client(url, key)