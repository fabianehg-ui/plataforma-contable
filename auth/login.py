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


# ============================================================
# Branding de la pantalla de login (logo + estilos)
# ============================================================

# Logo de INTEGRAL (SVG inline). Reemplaza este bloque por el logo real de la
# empresa cuando lo tengas (idealmente un SVG o un PNG en data URI).
_LOGO_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="-280.0 -280.0 560 560" width="120" height="120">

  <defs>
    <linearGradient id="gearGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#2dd4bf"/>
      <stop offset="0.55" stop-color="#0ea5e9"/>
      <stop offset="1" stop-color="#1e63c4"/>
    </linearGradient>
    <radialGradient id="halo" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#0ea5e9" stop-opacity="0.18"/>
      <stop offset="1" stop-color="#0ea5e9" stop-opacity="0"/>
    </radialGradient>
    
    <marker id="arrow_PDF" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#e4572e"/>
    </marker>
    <marker id="arrow_XML" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#5b8def"/>
    </marker>
    <marker id="arrow_XLSX" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#1e9e63"/>
    </marker>
    <marker id="arrow_DIAN" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#1e6f5c"/>
    </marker>
    <marker id="arrow_TXT" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#6b7280"/>
    </marker>
    <marker id="arrow_IMG" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#9b5de5"/>
    </marker>
    <marker id="arrow_WWW" viewBox="0 0 10 10" refX="8" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#0891b2"/>
    </marker>
  </defs>
  
  <circle cx="0" cy="0" r="250" fill="url(#halo)"/>
  
  <path d="M 0.0,-185.0 Q 18.0,-138.5 0.0,-92.0"
        fill="none" stroke="#e4572e" stroke-width="4.5" stroke-linecap="round"
        marker-end="url(#arrow_PDF)" stroke-dasharray="0"></path>
  <path d="M 126.7,-115.3 Q 110.5,-72.3 71.9,-57.4"
        fill="none" stroke="#5b8def" stroke-width="4.5" stroke-linecap="round"
        marker-end="url(#arrow_XML)" stroke-dasharray="0"></path>
  <path d="M 157.9,41.2 Q 119.8,48.4 89.7,20.5"
        fill="none" stroke="#1e9e63" stroke-width="4.5" stroke-linecap="round"
        marker-end="url(#arrow_XLSX)" stroke-dasharray="0"></path>
  <path d="M 70.3,166.7 Q 38.9,132.6 39.9,82.9"
        fill="none" stroke="#1e6f5c" stroke-width="4.5" stroke-linecap="round"
        marker-end="url(#arrow_DIAN)" stroke-dasharray="0"></path>
  <path d="M -70.3,166.7 Q -71.3,117.0 -39.9,82.9"
        fill="none" stroke="#6b7280" stroke-width="4.5" stroke-linecap="round"
        marker-end="url(#arrow_TXT)" stroke-dasharray="0"></path>
  <path d="M -157.9,41.2 Q -127.8,13.3 -89.7,20.5"
        fill="none" stroke="#9b5de5" stroke-width="4.5" stroke-linecap="round"
        marker-end="url(#arrow_IMG)" stroke-dasharray="0"></path>
  <path d="M -126.7,-115.3 Q -88.1,-100.4 -71.9,-57.4"
        fill="none" stroke="#0891b2" stroke-width="4.5" stroke-linecap="round"
        marker-end="url(#arrow_WWW)" stroke-dasharray="0"></path>
  
  <g fill="url(#gearGrad)" fill-rule="evenodd" stroke="#0b1622" stroke-width="1.2">
    <path d="M 7.64,-11.83 L 17.66,-12.25 L 17.66,0.25 L 7.64,-0.17 L 6.25,6.85 L 15.67,10.29 L 10.88,21.84 L 1.79,17.62 L -2.19,23.57 L 5.19,30.35 L -3.65,39.19 L -10.43,31.81 L -16.38,35.79 L -12.16,44.88 L -23.71,49.67 L -27.15,40.25 L -34.17,41.64 L -33.75,51.66 L -46.25,51.66 L -45.83,41.64 L -52.85,40.25 L -56.29,49.67 L -67.84,44.88 L -63.62,35.79 L -69.57,31.81 L -76.35,39.19 L -85.19,30.35 L -77.81,23.57 L -81.79,17.62 L -90.88,21.84 L -95.67,10.29 L -86.25,6.85 L -87.64,-0.17 L -97.66,0.25 L -97.66,-12.25 L -87.64,-11.83 L -86.25,-18.85 L -95.67,-22.29 L -90.88,-33.84 L -81.79,-29.62 L -77.81,-35.57 L -85.19,-42.35 L -76.35,-51.19 L -69.57,-43.81 L -63.62,-47.79 L -67.84,-56.88 L -56.29,-61.67 L -52.85,-52.25 L -45.83,-53.64 L -46.25,-63.66 L -33.75,-63.66 L -34.17,-53.64 L -27.15,-52.25 L -23.71,-61.67 L -12.16,-56.88 L -16.38,-47.79 L -10.43,-43.81 L -3.65,-51.19 L 5.19,-42.35 L -2.19,-35.57 L 1.79,-29.62 L 10.88,-33.84 L 15.67,-22.29 L 6.25,-18.85 Z M -16.80,-6.00 L -17.38,-0.84 L -19.10,4.07 L -21.86,8.46 L -25.54,12.14 L -29.93,14.90 L -34.84,16.62 L -40.00,17.20 L -45.16,16.62 L -50.07,14.90 L -54.46,12.14 L -58.14,8.46 L -60.90,4.07 L -62.62,-0.84 L -63.20,-6.00 L -62.62,-11.16 L -60.90,-16.07 L -58.14,-20.46 L -54.46,-24.14 L -50.07,-26.90 L -45.16,-28.62 L -40.00,-29.20 L -34.84,-28.62 L -29.93,-26.90 L -25.54,-24.14 L -21.86,-20.46 L -19.10,-16.07 L -17.38,-11.16 Z"></path>
    <path d="M 69.61,-44.85 L 77.61,-45.45 L 77.61,-34.55 L 69.61,-35.15 L 68.06,-29.40 L 75.29,-25.92 L 69.84,-16.47 L 63.22,-21.00 L 59.00,-16.78 L 63.53,-10.16 L 54.08,-4.71 L 50.60,-11.94 L 44.85,-10.39 L 45.45,-2.39 L 34.55,-2.39 L 35.15,-10.39 L 29.40,-11.94 L 25.92,-4.71 L 16.47,-10.16 L 21.00,-16.78 L 16.78,-21.00 L 10.16,-16.47 L 4.71,-25.92 L 11.94,-29.40 L 10.39,-35.15 L 2.39,-34.55 L 2.39,-45.45 L 10.39,-44.85 L 11.94,-50.60 L 4.71,-54.08 L 10.16,-63.53 L 16.78,-59.00 L 21.00,-63.22 L 16.47,-69.84 L 25.92,-75.29 L 29.40,-68.06 L 35.15,-69.61 L 34.55,-77.61 L 45.45,-77.61 L 44.85,-69.61 L 50.60,-68.06 L 54.08,-75.29 L 63.53,-69.84 L 59.00,-63.22 L 63.22,-59.00 L 69.84,-63.53 L 75.29,-54.08 L 68.06,-50.60 Z M 55.20,-40.00 L 54.82,-36.62 L 53.69,-33.40 L 51.88,-30.52 L 49.48,-28.12 L 46.60,-26.31 L 43.38,-25.18 L 40.00,-24.80 L 36.62,-25.18 L 33.40,-26.31 L 30.52,-28.12 L 28.12,-30.52 L 26.31,-33.40 L 25.18,-36.62 L 24.80,-40.00 L 25.18,-43.38 L 26.31,-46.60 L 28.12,-49.48 L 30.52,-51.88 L 33.40,-53.69 L 36.62,-54.82 L 40.00,-55.20 L 43.38,-54.82 L 46.60,-53.69 L 49.48,-51.88 L 51.88,-49.48 L 53.69,-46.60 L 54.82,-43.38 Z"></path>
    <path d="M 49.58,47.74 L 56.57,47.01 L 56.57,56.99 L 49.58,56.26 L 47.96,61.24 L 54.04,64.76 L 48.18,72.83 L 42.96,68.13 L 38.72,71.21 L 41.57,77.63 L 32.09,80.71 L 30.62,73.84 L 25.38,73.84 L 23.91,80.71 L 14.43,77.63 L 17.28,71.21 L 13.04,68.13 L 7.82,72.83 L 1.96,64.76 L 8.04,61.24 L 6.42,56.26 L -0.57,56.99 L -0.57,47.01 L 6.42,47.74 L 8.04,42.76 L 1.96,39.24 L 7.82,31.17 L 13.04,35.87 L 17.28,32.79 L 14.43,26.37 L 23.91,23.29 L 25.38,30.16 L 30.62,30.16 L 32.09,23.29 L 41.57,26.37 L 38.72,32.79 L 42.96,35.87 L 48.18,31.17 L 54.04,39.24 L 47.96,42.76 Z M 39.60,52.00 L 39.31,54.58 L 38.45,57.03 L 37.07,59.23 L 35.23,61.07 L 33.03,62.45 L 30.58,63.31 L 28.00,63.60 L 25.42,63.31 L 22.97,62.45 L 20.77,61.07 L 18.93,59.23 L 17.55,57.03 L 16.69,54.58 L 16.40,52.00 L 16.69,49.42 L 17.55,46.97 L 18.93,44.77 L 20.77,42.93 L 22.97,41.55 L 25.42,40.69 L 28.00,40.40 L 30.58,40.69 L 33.03,41.55 L 35.23,42.93 L 37.07,44.77 L 38.45,46.97 L 39.31,49.42 Z"></path>
  </g>
  
  <circle cx="-40" cy="-6"  r="11" fill="#0b1622"/>
  <circle cx="40"  cy="-40" r="9"  fill="#0b1622"/>
  <circle cx="28"  cy="52"  r="7"  fill="#0b1622"/>
  <circle cx="-40" cy="-6"  r="5"  fill="#2dd4bf"/>
  <circle cx="40"  cy="-40" r="4"  fill="#7dd3fc"/>
  <circle cx="28"  cy="52"  r="3.5" fill="#7dd3fc"/>

  
  <g>
    <rect x="-48.0" y="-239.0" width="96" height="50" rx="12"
          fill="#ffffff" stroke="#e4572e" stroke-width="3"/>
    <rect x="-48.0" y="-239.0" width="10" height="50" rx="5" fill="#e4572e"/>
    <text x="5.0" y="-214.0" font-family="Segoe UI, Arial, sans-serif"
          font-size="20" font-weight="800" fill="#e4572e"
          text-anchor="middle" dominant-baseline="central">PDF</text>
  </g>
  <g>
    <rect x="119.3" y="-158.4" width="96" height="50" rx="12"
          fill="#ffffff" stroke="#5b8def" stroke-width="3"/>
    <rect x="119.3" y="-158.4" width="10" height="50" rx="5" fill="#5b8def"/>
    <text x="172.3" y="-133.4" font-family="Segoe UI, Arial, sans-serif"
          font-size="20" font-weight="800" fill="#5b8def"
          text-anchor="middle" dominant-baseline="central">XML</text>
  </g>
  <g>
    <rect x="160.6" y="22.6" width="96" height="50" rx="12"
          fill="#ffffff" stroke="#1e9e63" stroke-width="3"/>
    <rect x="160.6" y="22.6" width="10" height="50" rx="5" fill="#1e9e63"/>
    <text x="213.6" y="47.6" font-family="Segoe UI, Arial, sans-serif"
          font-size="20" font-weight="800" fill="#1e9e63"
          text-anchor="middle" dominant-baseline="central">XLSX</text>
  </g>
  <g>
    <rect x="44.9" y="167.8" width="96" height="50" rx="12"
          fill="#ffffff" stroke="#1e6f5c" stroke-width="3"/>
    <path d="M 62.9 183.8 L 70.9 187.8 L 70.9 194.8 Q 70.9 200.8 62.9 202.8 Q 54.9 200.8 54.9 194.8 L 54.9 187.8 Z" fill="#1e6f5c"/><path d="M 59.9 192.8 L 61.9 195.8 L 66.9 189.8" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <text x="101.9" y="192.8" font-family="Segoe UI, Arial, sans-serif"
          font-size="20" font-weight="800" fill="#1e6f5c"
          text-anchor="middle" dominant-baseline="central">DIAN</text>
  </g>
  <g>
    <rect x="-140.9" y="167.8" width="96" height="50" rx="12"
          fill="#ffffff" stroke="#6b7280" stroke-width="3"/>
    <rect x="-140.9" y="167.8" width="10" height="50" rx="5" fill="#6b7280"/>
    <text x="-87.9" y="192.8" font-family="Segoe UI, Arial, sans-serif"
          font-size="20" font-weight="800" fill="#6b7280"
          text-anchor="middle" dominant-baseline="central">TXT</text>
  </g>
  <g>
    <rect x="-256.6" y="22.6" width="96" height="50" rx="12"
          fill="#ffffff" stroke="#9b5de5" stroke-width="3"/>
    <rect x="-256.6" y="22.6" width="10" height="50" rx="5" fill="#9b5de5"/>
    <text x="-203.6" y="47.6" font-family="Segoe UI, Arial, sans-serif"
          font-size="20" font-weight="800" fill="#9b5de5"
          text-anchor="middle" dominant-baseline="central">IMG</text>
  </g>
  <g>
    <rect x="-215.3" y="-158.4" width="96" height="50" rx="12"
          fill="#ffffff" stroke="#0891b2" stroke-width="3"/>
    <g stroke="#0891b2" stroke-width="2.2" fill="none"><circle cx="-197.3" cy="-133.4" r="9"/><ellipse cx="-197.3" cy="-133.4" rx="4" ry="9"/><line x1="-206.3" y1="-133.4" x2="-188.3" y2="-133.4"/></g>
    <text x="-158.3" y="-133.4" font-family="Segoe UI, Arial, sans-serif"
          font-size="20" font-weight="800" fill="#0891b2"
          text-anchor="middle" dominant-baseline="central">WWW</text>
  </g>
  
</svg>
"""

# Animación "pipeline": formatos → engranajes → cifras/gráficos
_GEAR_A = "M22.0,0.0 L29.5,5.3 L28.2,10.2 L19.1,11.0 L17.8,12.9 L20.8,21.6 L16.9,24.8 L9.0,20.1 L6.8,20.9 L4.1,29.7 L-0.9,30.0 L-4.5,21.5 L-6.8,20.9 L-14.1,26.5 L-18.4,23.7 L-16.3,14.8 L-17.8,12.9 L-27.0,13.1 L-28.8,8.4 L-21.9,2.3 L-22.0,0.0 L-29.5,-5.3 L-28.2,-10.2 L-19.1,-11.0 L-17.8,-12.9 L-20.8,-21.6 L-16.9,-24.8 L-9.0,-20.1 L-6.8,-20.9 L-4.1,-29.7 L0.9,-30.0 L4.5,-21.5 L6.8,-20.9 L14.1,-26.5 L18.4,-23.7 L16.3,-14.8 L17.8,-12.9 L27.0,-13.1 L28.8,-8.4 L21.9,-2.3 Z"
_GEAR_B = "M16.0,0.0 L21.5,4.8 L20.0,9.2 L12.7,9.7 L11.3,11.3 L11.8,18.6 L7.6,20.6 L2.1,15.9 L0.0,16.0 L-4.8,21.5 L-9.2,20.0 L-9.7,12.7 L-11.3,11.3 L-18.6,11.8 L-20.6,7.6 L-15.9,2.1 L-16.0,0.0 L-21.5,-4.8 L-20.0,-9.2 L-12.7,-9.7 L-11.3,-11.3 L-11.8,-18.6 L-7.6,-20.6 L-2.1,-15.9 L-0.0,-16.0 L4.8,-21.5 L9.2,-20.0 L9.7,-12.7 L11.3,-11.3 L18.6,-11.8 L20.6,-7.6 L15.9,-2.1 Z"

_PIPELINE = f"""
<div class='ig-pipe'>
  <div class='ig-in'>
    <span class='fchip pdf'>PDF</span><span class='fchip img'>IMG</span>
    <span class='fchip xml'>XML</span><span class='fchip xls'>XLS</span>
    <span class='fchip txt'>TXT</span><span class='fchip web'>🌐 WWW</span>
    <span class='fchip dian'>🛡 DIAN</span>
  </div>
  <div class='ig-arrow'>➜</div>
  <div class='ig-gearbox'>
    <svg viewBox='-60 -40 120 80' xmlns='http://www.w3.org/2000/svg'>
      <defs><linearGradient id='gg' x1='0' y1='0' x2='1' y2='1'>
        <stop offset='0' stop-color='#2dd4bf'/><stop offset='1' stop-color='#0ea5e9'/></linearGradient></defs>
      <g transform='translate(-14,2)'><path class='g1' d='{_GEAR_A}' fill='url(#gg)'/></g>
      <g transform='translate(24,9)'><path class='g2' d='{_GEAR_B}' fill='#7fdcd0'/></g>
    </svg>
  </div>
  <div class='ig-arrow'>➜</div>
  <div class='ig-out'>
    <div class='bars'><i></i><i></i><i></i><i></i><i></i></div>
    <div class='ig-num'>$ 2.480.000<br><span class='ig-numsub'>Db = Cr ✓</span></div>
  </div>
</div>
<div class='ig-cap'>Lee <b>PDF · imagen · XML · Excel · TXT</b> → engranajes que contabilizan → cifras y gráficos</div>
"""

_CSS_LOGIN = """
<style>
:root{ --brand1:#0b1f3a; --brand2:#123a5e; --accent:#2dd4bf; --accent2:#0ea5e9; }
/* Fondo con degradado + brillo */
.stApp{
  background:
    radial-gradient(1200px 600px at 15% -10%, rgba(45,212,191,.18), transparent 60%),
    radial-gradient(900px 500px at 110% 10%, rgba(14,165,233,.20), transparent 55%),
    linear-gradient(135deg, #081627 0%, #0b1f3a 45%, #0e2a44 100%);
  background-attachment: fixed;
}
header[data-testid="stHeader"], #MainMenu, footer{ display:none!important; }
section[data-testid='stSidebar'], div[data-testid='stSidebarNav']{ display:none!important; }
.block-container{ max-width: 1050px; padding-top: 3.2rem; }

/* Cabecera / logo */
.ig-hero{ text-align:center; animation: igfade .7s ease both; }
.ig-hero .ig-logo{ filter: drop-shadow(0 10px 24px rgba(45,212,191,.35)); }
.ig-title{ font-size: 2.4rem; font-weight:800; letter-spacing:.5px; margin:.4rem 0 0;
  background: linear-gradient(90deg,#e6f6ff,#9be8dc); -webkit-background-clip:text;
  background-clip:text; color:transparent; }
.ig-sub{ color:#9db6cf; font-size:1.02rem; margin-top:.15rem; }

/* Tarjeta del formulario (el st.form) */
[data-testid="stForm"]{
  background: rgba(255,255,255,.06);
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 18px; padding: 1.6rem 1.5rem;
  box-shadow: 0 24px 60px rgba(0,0,0,.35); backdrop-filter: blur(8px);
  animation: igfade .8s .05s ease both;
}
[data-testid="stForm"] label{ color:#cfe1f2!important; font-weight:600; }
.stTextInput input{
  background: rgba(255,255,255,.95)!important; border-radius:10px!important;
  border:1px solid rgba(255,255,255,.2)!important; color:#0b1f3a!important; }
.stTextInput input:focus{ box-shadow:0 0 0 3px rgba(45,212,191,.35)!important; }
[data-testid="stFormSubmitButton"] button{
  background: linear-gradient(90deg, var(--accent), var(--accent2))!important;
  color:#04202a!important; font-weight:800!important; border:0!important;
  border-radius:11px!important; padding:.6rem 1rem!important;
  box-shadow:0 10px 24px rgba(14,165,233,.35)!important; transition: transform .12s ease; }
[data-testid="stFormSubmitButton"] button:hover{ transform: translateY(-1px); }

/* Grid de servicios */
.ig-servicios{ display:grid; grid-template-columns: repeat(2, 1fr); gap:.7rem; }
.ig-serv{
  display:flex; gap:.7rem; align-items:center; padding:.75rem .85rem;
  background: rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.10);
  border-radius:13px; color:#dbe9f6; transition: transform .15s ease, background .2s ease;
  animation: igfade .8s .1s ease both; }
.ig-serv:hover{ transform: translateY(-2px); background: rgba(45,212,191,.12);
  border-color: rgba(45,212,191,.4); }
.ig-serv .ic{ font-size:1.25rem; }
.ig-serv .tt{ font-weight:700; font-size:.92rem; line-height:1.1; }
.ig-serv .ds{ color:#93aec9; font-size:.76rem; }
.ig-panel-title{ color:#bcd4ea; font-weight:700; letter-spacing:.4px;
  margin:.2rem 0 .6rem; font-size:.95rem; text-transform:uppercase; }
.ig-foot{ text-align:center; color:#6f8bab; font-size:.8rem; margin-top:1.6rem; }
@keyframes igfade{ from{opacity:0; transform: translateY(10px);} to{opacity:1; transform:none;} }

/* Animación pipeline: formatos → engranajes → cifras/gráficos */
.ig-pipe{ display:flex; align-items:center; justify-content:center; gap:.55rem; flex-wrap:wrap;
  margin:1.3rem auto .3rem; padding:.9rem 1rem; max-width:640px;
  background: rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.10);
  border-radius:16px; animation: igfade .8s .1s ease both; }
.ig-in{ display:flex; flex-direction:column; gap:.32rem; }
.fchip{ font-size:.7rem; font-weight:800; color:#04202a; padding:.18rem .5rem; border-radius:7px;
  box-shadow:0 4px 12px rgba(0,0,0,.25); animation: feed 3.2s ease-in-out infinite; }
.fchip.pdf{background:#ff9a9a;} .fchip.img{background:#ffd59e;} .fchip.xml{background:#9be8dc;}
.fchip.xls{background:#bfe3a6;} .fchip.txt{background:#dcdcf0;}
.fchip.web{background:#a5e8f5;} .fchip.dian{background:#bfe6d8;}
.fchip:nth-child(2){animation-delay:.30s;} .fchip:nth-child(3){animation-delay:.60s;}
.fchip:nth-child(4){animation-delay:.90s;} .fchip:nth-child(5){animation-delay:1.20s;}
.fchip:nth-child(6){animation-delay:1.50s;} .fchip:nth-child(7){animation-delay:1.80s;}
@keyframes feed{ 0%{opacity:.3; transform:translateX(-7px);} 50%{opacity:1; transform:translateX(7px);}
  100%{opacity:.3; transform:translateX(-7px);} }
.ig-arrow{ color:#5fd0c4; font-size:1.3rem; animation: apulse 1.6s ease-in-out infinite; }
@keyframes apulse{ 0%,100%{opacity:.35;} 50%{opacity:1;} }
.ig-gearbox svg{ width:150px; height:88px; filter: drop-shadow(0 8px 20px rgba(45,212,191,.4)); }
.g1,.g2{ transform-box: fill-box; transform-origin:center; }
.g1{ animation: spin 7s linear infinite; }
.g2{ animation: spin 4.5s linear infinite reverse; }
@keyframes spin{ to{ transform: rotate(360deg); } }
.ig-out{ display:flex; align-items:flex-end; gap:.55rem; }
.bars{ display:flex; align-items:flex-end; gap:3px; height:46px; }
.bars i{ width:7px; background: linear-gradient(180deg,#2dd4bf,#0ea5e9); border-radius:3px 3px 0 0;
  transform-origin:bottom; animation: grow 1.8s ease-in-out infinite; }
.bars i:nth-child(1){height:38%;} .bars i:nth-child(2){height:70%; animation-delay:.2s;}
.bars i:nth-child(3){height:28%; animation-delay:.4s;} .bars i:nth-child(4){height:92%; animation-delay:.6s;}
.bars i:nth-child(5){height:55%; animation-delay:.8s;}
@keyframes grow{ 0%,100%{transform:scaleY(.45); opacity:.7;} 50%{transform:scaleY(1); opacity:1;} }
.ig-num{ font-weight:800; color:#9be8dc; font-size:1rem; line-height:1.05; text-align:left; }
.ig-numsub{ font-size:.68rem; color:#7f9ab8; font-weight:600; }
.ig-cap{ text-align:center; color:#8fa8c4; font-size:.82rem; margin:.1rem auto 0; max-width:640px; }
</style>
"""

_SERVICIOS = [
    ("📚", "Contabilidad y libros", "Balance, PyG, auxiliar, mayor"),
    ("✍️", "Captura y comprobantes", "Partida doble e impresión"),
    ("💼", "Nómina y PILA", "Causación automática del mes"),
    ("🧾", "Compras y ventas", "Desde DIAN, Siigo o Excel"),
    ("💳", "Cartera y pagos", "Cruce de facturas por tercero"),
    ("📊", "Retención y exógena", "F350 y medios magnéticos"),
    ("🔄", "Conciliación de bancos", "Extractos vs libros, cuadre"),
    ("🔗", "Todo integrado", "Un solo movimiento por empresa"),
]


def login_form():
    """Pantalla de acceso con branding: logo, servicios y formulario elegante.

    Oculta el sidebar/menú (anti-espionaje) y pide NIT + correo + contraseña.
    """
    st.markdown(_CSS_LOGIN, unsafe_allow_html=True)

    # Cabecera con logo
    st.markdown(
        f"<div class='ig-hero'><div class='ig-logo'>{_LOGO_SVG}</div>"
        "<div class='ig-title'>INTEGRAL</div>"
        "<div class='ig-sub'>Plataforma contable integral · todo el ciclo, una sola empresa</div></div>",
        unsafe_allow_html=True,
    )

    # Animación: formatos → engranajes → cifras/gráficos
    st.markdown(_PIPELINE, unsafe_allow_html=True)
    st.write("")

    col_form, col_serv = st.columns([1, 1.15], gap="large")

    with col_form:
        st.markdown("<div class='ig-panel-title'>🔐 Iniciar sesión</div>", unsafe_allow_html=True)
        with st.form("login_form", clear_on_submit=False):
            nit = st.text_input("NIT de la empresa", key="login_nit", placeholder="901630218")
            email = st.text_input("Correo electrónico", key="login_email", placeholder="tucorreo@empresa.com")
            password = st.text_input("Contraseña", type="password", key="login_pw")
            submit = st.form_submit_button("Entrar →", type="primary", use_container_width=True)
            if submit:
                _hacer_login(nit, email, password)
        st.caption("Acceso restringido. Cada usuario entra solo a su empresa asignada.")

    with col_serv:
        st.markdown("<div class='ig-panel-title'>Servicios</div>", unsafe_allow_html=True)
        cards = "".join(
            f"<div class='ig-serv'><div class='ic'>{ic}</div>"
            f"<div><div class='tt'>{tt}</div><div class='ds'>{ds}</div></div></div>"
            for ic, tt, ds in _SERVICIOS
        )
        st.markdown(f"<div class='ig-servicios'>{cards}</div>", unsafe_allow_html=True)

    st.markdown("<div class='ig-foot'>INTEGRAL · reimplementación limpia · "
                "© 2026</div>", unsafe_allow_html=True)


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
