"""
Cliente Supabase — UN CLIENTE POR SESIÓN DE USUARIO.

Por qué no se cachea con @st.cache_resource
--------------------------------------------
@st.cache_resource crea un único objeto compartido por TODO el proceso del
servidor, es decir, entre todas las sesiones de usuario. Como el cliente de
Supabase guarda el token de auth DENTRO de sí mismo, compartirlo hace que el
login de un usuario pise el de otro: las queries de A terminan corriendo con
la identidad de B (y con RLS por empresa, eso filtra datos entre empresas).

Solución: el cliente vive en st.session_state, que es propio de cada sesión
de navegador. Las credenciales (url/keys) sí se leen una sola vez y se cachean,
porque son constantes y no tienen estado de usuario.

Funciones:
    get_supabase()       -> cliente para la sesión actual, con el token del
                            usuario aplicado si hay sesión iniciada.
    get_supabase_admin() -> cliente service_role (bypass RLS). Singleton:
                            no depende del usuario, solo para operaciones admin.
"""
import streamlit as st
from supabase import create_client, Client


# ============================================================
# Credenciales (constantes — sí se pueden cachear globalmente)
# ============================================================

@st.cache_data
def _credenciales():
    """Lee url / anon_key / service_key una sola vez."""
    try:
        url = st.secrets["supabase"]["url"]
        anon = st.secrets["supabase"]["anon_key"]
    except (KeyError, FileNotFoundError):
        st.error(
            "⚠️ No se encontraron credenciales de Supabase. "
            "Revisa .streamlit/secrets.toml o las variables de entorno."
        )
        st.stop()
    try:
        service = st.secrets["supabase"]["service_key"]
    except (KeyError, FileNotFoundError):
        service = None
    return {"url": url, "anon": anon, "service": service}


# ============================================================
# Cliente por sesión
# ============================================================

_SESSION_KEY = "_sb_client"


def get_supabase() -> Client:
    """
    Retorna el cliente Supabase de la SESIÓN ACTUAL.

    - Se crea uno por sesión y se guarda en st.session_state (no global).
    - Si hay token del usuario en sesión, se inyecta en PostgREST para que
      todas las queries (incluidos INSERT/UPDATE) viajen con el JWT del
      usuario y RLS lo reconozca como admin de su empresa.
    """
    cliente = st.session_state.get(_SESSION_KEY)
    if cliente is None:
        cred = _credenciales()
        cliente = create_client(cred["url"], cred["anon"])
        st.session_state[_SESSION_KEY] = cliente

    # Inyectar el token del usuario en PostgREST en CADA llamada.
    #
    # Este es el punto crítico para RLS: las políticas de las tablas f350_*
    # usan auth.uid() / es_admin_de_empresa(). Si el token no viaja en el
    # header Authorization, PostgREST actúa como 'anon' y los INSERT son
    # rechazados con APIError. postgrest.auth(token) fija ese header de forma
    # explícita y barata (no llama a la red), evitando depender del estado
    # interno de auth del cliente.
    access_token = st.session_state.get("access_token")
    if access_token:
        try:
            cliente.postgrest.auth(access_token)
        except Exception:
            pass

    return cliente


@st.cache_resource
def get_supabase_admin() -> Client:
    """
    Cliente con permisos de administrador (service_role).

    Este SÍ es singleton global: no lleva sesión de usuario, solo se usa para
    operaciones que requieren bypass de RLS (ej: crear empresa y asignar
    usuario en una transacción). NUNCA exponer al frontend.
    """
    cred = _credenciales()
    if not cred["service"]:
        return None
    return create_client(cred["url"], cred["service"])
