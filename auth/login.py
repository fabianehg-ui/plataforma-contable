"""
Autenticación contra Supabase Auth.

Funciones principales:
    - login_form(): muestra formulario de login y maneja la sesión
    - require_auth(): se llama al inicio de cada página protegida
    - logout(): cierra sesión
    - current_user(): retorna el usuario actual (dict) o None

La sesión se guarda en st.session_state con dos llaves:
    - 'user': dict con info del usuario (id, email, metadata)
    - 'access_token': token JWT para llamadas autenticadas a Supabase
"""
import streamlit as st
from db.supabase_client import get_supabase


# ============================================================
# Sesión
# ============================================================

def current_user():
    """Retorna el usuario actual o None si no hay sesión."""
    return st.session_state.get("user")


def is_authenticated() -> bool:
    return current_user() is not None


def require_auth():
    """Llamar al inicio de cada página protegida.
    Si no hay sesión, muestra el formulario de login y detiene la página."""
    if not is_authenticated():
        login_form()
        st.stop()


# ============================================================
# Login / Logout
# ============================================================

def login_form():
    """Muestra el formulario de login centrado en la página."""
    st.markdown("## 🔐 Iniciar sesión")
    st.caption("Accede con tu usuario y contraseña para usar la plataforma.")

    tab_login, tab_registro = st.tabs(["Iniciar sesión", "Crear cuenta"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Correo electrónico", key="login_email")
            password = st.text_input("Contraseña", type="password", key="login_pw")
            submit = st.form_submit_button("Entrar", type="primary", use_container_width=True)

            if submit:
                _hacer_login(email, password)

    with tab_registro:
        st.info(
            "El registro está restringido. Si necesitas una cuenta, "
            "contacta al administrador de la plataforma."
        )
        # Descomenta este bloque si quieres permitir auto-registro:
        #
        # with st.form("registro_form"):
        #     email_r = st.text_input("Correo electrónico", key="reg_email")
        #     pw_r = st.text_input("Contraseña", type="password", key="reg_pw")
        #     pw_r2 = st.text_input("Repetir contraseña", type="password", key="reg_pw2")
        #     ok = st.form_submit_button("Crear cuenta", type="primary")
        #     if ok:
        #         if pw_r != pw_r2:
        #             st.error("Las contraseñas no coinciden")
        #         elif len(pw_r) < 8:
        #             st.error("La contraseña debe tener al menos 8 caracteres")
        #         else:
        #             _hacer_registro(email_r, pw_r)


def _hacer_login(email: str, password: str):
    if not email or not password:
        st.error("Ingresa correo y contraseña")
        return

    sb = get_supabase()
    try:
        resp = sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:
        st.error(f"Error al iniciar sesión: {e}")
        return

    if resp.user is None:
        st.error("Credenciales inválidas")
        return

    st.session_state["user"] = {
        "id": resp.user.id,
        "email": resp.user.email,
        "metadata": resp.user.user_metadata or {},
    }
    st.session_state["access_token"] = resp.session.access_token
    st.session_state["refresh_token"] = resp.session.refresh_token
    st.success("¡Sesión iniciada!")
    st.rerun()


def _hacer_registro(email: str, password: str):
    """Registro de usuario. Por defecto está deshabilitado en login_form().
    Si lo habilitas, Supabase envía un correo de confirmación."""
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
    """Cierra la sesión actual."""
    sb = get_supabase()
    try:
        sb.auth.sign_out()
    except Exception:
        pass
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
