"""Cliente Supabase compartido."""
import os
import streamlit as st
from supabase import create_client, Client


def _get_cred(env_name, section, key):
    val = os.environ.get(env_name)
    if val:
        return val.strip()
    try:
        return st.secrets[section][key]
    except (KeyError, FileNotFoundError, AttributeError):
        return None


@st.cache_resource
def get_supabase() -> Client:
    url = _get_cred("SUPABASE_URL", "supabase", "url")
    key = _get_cred("SUPABASE_ANON_KEY", "supabase", "anon_key")
    if not url or not key:
        st.error("No se encontraron credenciales de Supabase.")
        st.stop()
    url = url.rstrip("/")
    return create_client(url, key)


@st.cache_resource
def get_supabase_admin() -> Client:
    url = _get_cred("SUPABASE_URL", "supabase", "url")
    key = _get_cred("SUPABASE_SERVICE_KEY", "supabase", "service_key")
    if not url or not key:
        return None
    url = url.rstrip("/")
    return create_client(url, key)
