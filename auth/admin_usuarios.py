"""
Helpers para gestión administrativa de usuarios.

Hay dos clientes Supabase distintos en juego:
    - get_supabase()       : cliente con la anon key (las RPC verifican
                             permisos del usuario logueado vía RLS).
    - get_supabase_admin() : cliente con la service key (bypassa RLS).
                             Solo se usa para operaciones de
                             auth.admin (crear/eliminar usuarios,
                             resetear contraseñas) que NO se pueden
                             hacer desde el cliente normal.

Permisos de uso:
    - Funciones que asignan/remueven roles → cualquier admin de empresa
      o superadmin (la verificación está dentro de las RPC).
    - Funciones que crean/eliminan usuarios o resetean contraseñas →
      cualquier admin de empresa o superadmin (verificamos con RPC
      es_admin_de_alguna_empresa() antes de usar la service key).
"""
from __future__ import annotations
import secrets
import string
from typing import Optional

import streamlit as st

from db.supabase_client import get_supabase, get_supabase_admin
from auth.login import current_user
from auth.superadmin import es_superadmin


# ============================================================
# Permisos
# ============================================================

def es_admin_de_alguna_empresa() -> bool:
    """True si el usuario actual es admin en al menos una empresa."""
    user = current_user()
    if not user:
        return False

    cache_key = f"_es_admin_alguna_{user['id']}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    sb = get_supabase()
    try:
        resp = sb.rpc("es_admin_de_alguna_empresa").execute()
        valor = bool(resp.data) if resp.data is not None else False
    except Exception:
        valor = False

    st.session_state[cache_key] = valor
    return valor


def puede_gestionar_usuarios() -> bool:
    """True si el usuario puede crear/asignar usuarios.
    (Es admin de al menos una empresa, o superadmin.)"""
    return es_superadmin() or es_admin_de_alguna_empresa()


def require_admin_o_superadmin():
    """Detiene la página si el usuario no es admin de empresa ni superadmin."""
    if not puede_gestionar_usuarios():
        st.error(
            "⛔ Acceso denegado. Esta sección es solo para administradores. "
            "Si necesitas gestionar usuarios, pídele a un administrador "
            "que te asigne el rol 'admin' en alguna empresa."
        )
        st.stop()


# ============================================================
# Generador de contraseñas
# ============================================================

def generar_password_temporal(longitud: int = 12) -> str:
    """Genera una contraseña aleatoria de la longitud dada.

    Mezcla de letras (mayúsculas y minúsculas), dígitos y símbolos seguros.
    Garantiza al menos un carácter de cada tipo.
    """
    if longitud < 8:
        longitud = 8

    # Excluimos caracteres ambiguos para que sea fácil leer/dictar:
    # 0/O, 1/l/I, etc. Tampoco usamos comillas ni \ ni espacios.
    minus = "abcdefghjkmnpqrstuvwxyz"
    mayus = "ABCDEFGHJKMNPQRSTUVWXYZ"
    digit = "23456789"
    simbolos = "!@#$%&*+="

    todos = minus + mayus + digit + simbolos

    while True:
        candidato = "".join(secrets.choice(todos) for _ in range(longitud))
        # Garantizar diversidad
        if (any(c in minus for c in candidato)
            and any(c in mayus for c in candidato)
            and any(c in digit for c in candidato)
            and any(c in simbolos for c in candidato)):
            return candidato


# ============================================================
# Operaciones que usan la SERVICE KEY (Auth Admin API)
# ============================================================

def crear_usuario_con_password(email: str, password: str) -> dict:
    """Crea un usuario en Supabase Auth con un password fijo.

    Args:
        email: correo del usuario.
        password: contraseña inicial (la que le dictarás por WhatsApp).

    Returns:
        dict con {'success': bool, 'user_id': str|None, 'error': str|None}.
    """
    if not puede_gestionar_usuarios():
        return {"success": False, "user_id": None,
                "error": "No tienes permisos para crear usuarios."}

    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return {"success": False, "user_id": None,
                "error": "Email inválido."}

    if not password or len(password) < 8:
        return {"success": False, "user_id": None,
                "error": "La contraseña debe tener al menos 8 caracteres."}

    sb_admin = get_supabase_admin()
    if sb_admin is None:
        return {"success": False, "user_id": None,
                "error": "El servidor no tiene configurada la SUPABASE_SERVICE_KEY. "
                         "Pide al superadmin que la añada en Railway."}

    try:
        resp = sb_admin.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,  # Marca el email como verificado
        })
    except Exception as e:
        msg = str(e)
        # Errores comunes legibles
        if "already" in msg.lower() and "registered" in msg.lower():
            return {"success": False, "user_id": None,
                    "error": f"Ya existe un usuario con el email '{email}'."}
        return {"success": False, "user_id": None,
                "error": f"Error al crear usuario: {msg}"}

    # supabase-py devuelve un objeto con .user
    user_obj = getattr(resp, "user", None) or resp
    user_id = getattr(user_obj, "id", None)

    if not user_id and isinstance(resp, dict):
        user_id = resp.get("user", {}).get("id") or resp.get("id")

    if not user_id:
        return {"success": False, "user_id": None,
                "error": "Usuario creado pero no se pudo obtener el ID. "
                         "Revisa Supabase manualmente."}

    return {"success": True, "user_id": str(user_id), "error": None}


def resetear_password_usuario(usuario_id: str, nuevo_password: str) -> dict:
    """Cambia el password de un usuario existente.

    Returns:
        dict con {'success': bool, 'error': str|None}.
    """
    if not puede_gestionar_usuarios():
        return {"success": False,
                "error": "No tienes permisos para resetear contraseñas."}

    if not nuevo_password or len(nuevo_password) < 8:
        return {"success": False,
                "error": "La nueva contraseña debe tener al menos 8 caracteres."}

    sb_admin = get_supabase_admin()
    if sb_admin is None:
        return {"success": False,
                "error": "El servidor no tiene configurada la SUPABASE_SERVICE_KEY."}

    try:
        sb_admin.auth.admin.update_user_by_id(
            usuario_id,
            {"password": nuevo_password},
        )
        return {"success": True, "error": None}
    except Exception as e:
        return {"success": False, "error": f"Error al resetear: {e}"}


# ============================================================
# Operaciones que usan RPCs (la lógica de permisos está en Postgres)
# ============================================================

def listar_empresas_que_administro() -> list[dict]:
    """Empresas en las que el usuario actual es admin (excluye superadmin).

    Returns:
        Lista de dicts: [{'id': ..., 'nit': ..., 'razon_social': ...}, ...]
    """
    sb = get_supabase()
    try:
        resp = sb.rpc("mis_empresas_como_admin").execute()
        return list(resp.data or [])
    except Exception as e:
        st.error(f"Error listando empresas: {e}")
        return []


def listar_usuarios_de_empresa(empresa_id: str) -> list[dict]:
    """Usuarios asignados a la empresa.

    El llamador debe ser admin de esa empresa o superadmin (la RPC valida).
    """
    sb = get_supabase()
    try:
        resp = sb.rpc(
            "admin_usuarios_de_empresa_v2",
            {"p_empresa_id": empresa_id},
        ).execute()
        return list(resp.data or [])
    except Exception as e:
        st.error(f"Error listando usuarios: {e}")
        return []


def buscar_usuario_por_email(email: str) -> Optional[dict]:
    """Busca un usuario por email exacto. Retorna None si no existe."""
    if not email:
        return None
    sb = get_supabase()
    try:
        resp = sb.rpc(
            "admin_buscar_usuario_por_email",
            {"p_email": email.strip()},
        ).execute()
        if resp.data:
            return resp.data[0]
        return None
    except Exception as e:
        st.error(f"Error buscando usuario: {e}")
        return None


def asignar_usuario_a_empresa(usuario_id: str, empresa_id: str, rol: str) -> dict:
    """Asigna un usuario a una empresa con el rol indicado.

    Si ya tenía un rol, lo actualiza al nuevo.
    """
    if rol not in ("admin", "operador", "consulta"):
        return {"success": False,
                "error": f"Rol inválido: {rol}. Debe ser admin, operador o consulta."}

    sb = get_supabase()
    try:
        sb.rpc(
            "admin_asignar_usuario_empresa",
            {
                "p_usuario_id": usuario_id,
                "p_empresa_id": empresa_id,
                "p_rol": rol,
            },
        ).execute()
        return {"success": True, "error": None}
    except Exception as e:
        return {"success": False, "error": f"Error asignando: {e}"}


def remover_usuario_de_empresa(usuario_id: str, empresa_id: str) -> dict:
    """Quita el acceso de un usuario a una empresa."""
    sb = get_supabase()
    try:
        sb.rpc(
            "admin_remover_usuario_empresa",
            {
                "p_usuario_id": usuario_id,
                "p_empresa_id": empresa_id,
            },
        ).execute()
        return {"success": True, "error": None}
    except Exception as e:
        return {"success": False, "error": f"Error removiendo: {e}"}
