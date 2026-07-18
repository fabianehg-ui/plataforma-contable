"""
Autenticación contra Supabase Auth — con sesión PERSISTENTE en cookie.

Problema que resuelve
---------------------
Antes la sesión vivía solo en st.session_state, que se borra cuando se cae
el WebSocket de Streamlit (al suspender el equipo, cambiar de pestaña un
buen rato, o por inactividad). El usuario quedaba deslogueado "solo".

Ahora, además de st.session_state, los tokens se guardan en una COOKIE del
navegador. Al cargar la app, si session_state está vacío pero la cookie
sigue presente, se reconstruye la sesión de Supabase con el refresh_token
(rotándolo). Así el descanso o el cambio de proceso ya no cierran la sesión.

Funciones principales:
    - bootstrap_session(): restaura la sesión desde la cookie (llamar 1ª)
    - login_form(): muestra formulario de login y maneja la sesión
    - require_auth(): se llama al inicio de cada página protegida
    - logout(): cierra sesión (y borra la cookie)
    - current_user(): retorna el usuario actual (dict) o None

Llaves en st.session_state:
    - 'user': dict con info del usuario (id, email, metadata)
    - 'access_token': token JWT de acceso
    - 'refresh_token': token de refresco (para revivir la sesión)
"""
import json

import streamlit as st
from db.supabase_client import get_supabase


# ============================================================
# Cookie de sesión
# ============================================================
# Usamos streamlit-cookies-controller (liviano, sin componente visible).
# Añade a requirements.txt:  streamlit-cookies-controller>=0.0.4

_COOKIE_NAME = "pc_session"          # nombre de la cookie
_COOKIE_MAX_AGE_DAYS = 7             # cuántos días dura la sesión persistida


def _get_cookie_controller():
    """Controlador de cookies.

    NO se cachea con @st.cache_resource: CookieController monta internamente
    un componente/widget de Streamlit, y los widgets no pueden crearse dentro
    de funciones cacheadas (lanza CachedWidgetWarning). Debe instanciarse en
    cada ejecución del script.
    """
    from streamlit_cookies_controller import CookieController
    return CookieController()


def _guardar_cookie_sesion(access_token: str, refresh_token: str):
    """Escribe los tokens en una cookie del navegador."""
    try:
        ctrl = _get_cookie_controller()
        payload = json.dumps(
            {"access_token": access_token, "refresh_token": refresh_token}
        )
        ctrl.set(
            _COOKIE_NAME,
            payload,
            max_age=_COOKIE_MAX_AGE_DAYS * 24 * 3600,
            same_site="strict",
            secure=True,
        )
    except Exception:
        # Si las cookies fallan (p.ej. navegador muy restrictivo), la app
        # sigue funcionando con la sesión solo en memoria.
        pass


def _leer_cookie_sesion():
    """Lee los tokens de la cookie. Retorna dict o None."""
    try:
        ctrl = _get_cookie_controller()
        raw = ctrl.get(_COOKIE_NAME)
        if not raw:
            return None
        if isinstance(raw, dict):          # algunas versiones ya deserializan
            return raw
        return json.loads(raw)
    except Exception:
        return None


def _borrar_cookie_sesion():
    """Elimina la cookie de sesión."""
    try:
        ctrl = _get_cookie_controller()
        ctrl.remove(_COOKIE_NAME)
    except Exception:
        pass


# ============================================================
# Sesión
# ============================================================

def current_user():
    """Retorna el usuario actual o None si no hay sesión."""
    return st.session_state.get("user")


def is_authenticated() -> bool:
    return current_user() is not None


def _set_session_state(user_obj, session_obj):
    """Guarda usuario + tokens en session_state (y refleja en cookie)."""
    st.session_state["user"] = {
        "id": user_obj.id,
        "email": user_obj.email,
        "metadata": user_obj.user_metadata or {},
    }
    st.session_state["access_token"] = session_obj.access_token
    st.session_state["refresh_token"] = session_obj.refresh_token
    _guardar_cookie_sesion(session_obj.access_token, session_obj.refresh_token)


def _token_por_expirar(margen_seg: int = 120) -> bool:
    """True si el access_token vence dentro de `margen_seg` segundos."""
    import time
    import base64

    tok = st.session_state.get("access_token")
    if not tok:
        return True
    try:
        # JWT: header.payload.signature -> decodificar el payload (claim exp)
        payload_b64 = tok.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # padding
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = claims.get("exp", 0)
        return (exp - time.time()) < margen_seg
    except Exception:
        # Si no se puede leer, asumir que conviene refrescar.
        return True


def _refrescar_sesion():
    """Renueva la sesión con el refresh_token y actualiza estado + cookie."""
    refresh_token = st.session_state.get("refresh_token")
    if not refresh_token:
        return False
    sb = get_supabase()
    try:
        resp = sb.auth.refresh_session(refresh_token)
    except Exception:
        return False
    if getattr(resp, "user", None) and getattr(resp, "session", None):
        _set_session_state(resp.user, resp.session)
        return True
    return False


def bootstrap_session():
    """
    Garantiza una sesión válida al inicio de cada carga de página.

    Llamar al inicio de Home.py y vía require_auth(). Es idempotente:
      1. Si NO hay sesión en memoria, intenta restaurarla desde la cookie.
      2. Si SÍ hay sesión pero el access_token está por vencer, lo refresca
         (rota el refresh_token y actualiza la cookie).
    """
    # ---- Caso 1: sin sesión en memoria -> restaurar desde cookie ----
    if not is_authenticated():
        datos = _leer_cookie_sesion()
        if not datos:
            return
        refresh_token = datos.get("refresh_token")
        if not refresh_token:
            return

        sb = get_supabase()
        try:
            # set_session valida el access_token y, si expiró, lo renueva con
            # el refresh_token. Devuelve la sesión vigente.
            resp = sb.auth.set_session(
                datos.get("access_token", ""), refresh_token
            )
        except Exception:
            # refresh_token vencido o revocado -> limpiar cookie, pedir login.
            _borrar_cookie_sesion()
            return

        if getattr(resp, "user", None) and getattr(resp, "session", None):
            _set_session_state(resp.user, resp.session)
        return

    # ---- Caso 2: sesión en memoria pero token por vencer -> refrescar ----
    if _token_por_expirar():
        _refrescar_sesion()


# ============================================================
# Login / Logout
# ============================================================

def require_auth():
    """Llamar al inicio de cada página protegida.
    Intenta restaurar de cookie; si no, muestra login y detiene la página."""
    bootstrap_session()
    if not is_authenticated():
        login_form()
        st.stop()


def login_form():
    """Formulario de login: NIT de la empresa + correo + contraseña.

    Oculta el sidebar (anti-espionaje: no se ven módulos sin sesión).
    """
    # Ocultar sidebar y cualquier navegación mientras no haya sesión
    st.markdown(
        "<style>section[data-testid='stSidebar']{display:none!important;}"
        "div[data-testid='stSidebarNav']{display:none!important;}</style>",
        unsafe_allow_html=True,
    )
    st.markdown("## 🔐 Iniciar sesión")
    st.caption("Ingresa el NIT de la empresa en la que vas a trabajar, tu correo y tu contraseña.")

    with st.form("login_form", clear_on_submit=False):
        nit = st.text_input("NIT de la empresa", key="login_nit",
                            placeholder="901630218")
        email = st.text_input("Correo electrónico", key="login_email")
        password = st.text_input("Contraseña", type="password", key="login_pw")
        submit = st.form_submit_button("Entrar", type="primary", use_container_width=True)
        if submit:
            _hacer_login(nit, email, password)

    st.caption("El registro está restringido. Si necesitas una cuenta, contacta al "
               "administrador de la plataforma.")


def _solo_digitos(s) -> str:
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def _hacer_login(nit: str, email: str, password: str):
    if not nit or not email or not password:
        st.error("Ingresa el NIT de la empresa, el correo y la contraseña.")
        return

    sb = get_supabase()
    try:
        resp = sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:
        st.error(f"Error al iniciar sesión: {e}")
        return

    if resp.user is None or resp.session is None:
        st.error("Credenciales inválidas")
        return

    _set_session_state(resp.user, resp.session)

    # Verificar acceso a la empresa por NIT (privacidad multi-empresa)
    try:
        from auth.empresas import empresas_del_usuario
        nit_norm = _solo_digitos(nit)
        empresas = empresas_del_usuario()
        match = next((e for e in empresas if _solo_digitos(e.get("nit")) == nit_norm), None)
    except Exception as e:
        match = None

    if not match:
        # Sin acceso a esa empresa → cerrar la sesión recién abierta
        try:
            sb.auth.sign_out()
        except Exception:
            pass
        for k in ("user", "access_token", "refresh_token", "empresa_activa"):
            st.session_state.pop(k, None)
        st.error("No tienes acceso a una empresa con ese NIT, o el NIT es incorrecto.")
        return

    st.session_state["empresa_activa"] = match
    st.success(f"¡Sesión iniciada en {match['razon_social']}!")
    st.rerun()


def _hacer_registro(email: str, password: str):
    """Registro de usuario. Por defecto está deshabilitado en login_form()."""
    sb = get_supabase()
    try:
        resp = sb.auth.sign_up({"email": email, "password": password})
    except Exception as e:
        st.error(f"Error al crear cuenta: {e}")
        return

    if resp.user is None:
        st.error("No se pudo crear la cuenta")
        return

    st.success(
        "Cuenta creada. Revisa tu correo para confirmar tu dirección "
        "antes de iniciar sesión."
    )


def logout():
    """Cierra la sesión actual (memoria + cookie)."""
    sb = get_supabase()
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    _borrar_cookie_sesion()
    for k in ("user", "access_token", "refresh_token", "empresa_activa"):
        st.session_state.pop(k, None)
    st.rerun()


# ============================================================
# Widgets de UI
# ============================================================

def sidebar_user_info():
    """Muestra info del usuario logueado en el sidebar con botón de logout."""
    user = current_user()
    if not user:
        return
    with st.sidebar:
        st.markdown("---")
        st.caption(f"👤 {user['email']}")
        if st.button("Cerrar sesión", use_container_width=True):
            logout()
