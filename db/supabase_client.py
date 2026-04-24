"""
Cliente Supabase - version robusta.

Maneja automaticamente problemas comunes con variables de entorno:
- Comillas que Railway agrega a veces: "valor" -> valor
- Espacios al inicio/final
- Barras al final de URLs: url/ -> url
"""
import os
import streamlit as st
from supabase import create_client, Client


def _limpiar_valor(val):
    """Limpia un valor de variable de entorno."""
    if val is None:
        return None
    val = str(val).strip()
    if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
        val = val[1:-1]
    if len(val) >= 2 and val.startswith("'") and val.endswith("'"):
        val = val[1:-1]
    return val.strip()


def _get_cred(env_name, secrets_section, secrets_key):
    """Busca una credencial primero en variables de entorno, luego en st.secrets."""
    val = os.environ.get(env_name)
    if val:
        return _limpiar_valor(val)
    try:
        return _limpiar_valor(st.secrets[secrets_section][secrets_key])
    except (KeyError, FileNotFoundError, AttributeError):
        return None


@st.cache_resource
def get_supabase() -> Client:
    """Retorna el cliente Supabase. Se cachea para que sea unico."""
    url = _get_cred("SUPABASE_URL", "supabase", "url")
    key = _get_cred("SUPABASE_ANON_KEY", "supabase", "anon_key")

    if not url or not key:
        diag = [
            "No se encontraron credenciales de Supabase.",
            "",
            f"- SUPABASE_URL: {'OK' if url else 'FALTA'}",
            f"- SUPABASE_ANON_KEY: {'OK' if key else 'FALTA'}",
            "",
            "Configura estas variables en Railway. Sin comillas alrededor.",
        ]
        st.error("\n".join(diag))
        st.stop()

    if not url.startswith("http"):
        st.error(f"SUPABASE_URL invalida: {url[:50]}...")
        st.stop()

    if not key.startswith("eyJ"):
        st.error(
            "SUPABASE_ANON_KEY no parece JWT valido (debe empezar con 'eyJ'). "
            f"Empieza con: '{key[:10]}...'"
        )
        st.stop()

    url = url.rstrip("/")
    return create_client(url, key)


@st.cache_resource
def get_supabase_admin() -> Client:
    """Cliente con permisos de administrador."""
    url = _get_cred("SUPABASE_URL", "supabase", "url")
    key = _get_cred("SUPABASE_SERVICE_KEY", "supabase", "service_key")

    if not url or not key:
        return None
    if not url.startswith("http") or not key.startswith("eyJ"):
        return None

    url = url.rstrip("/")
    return create_client(url, key)
