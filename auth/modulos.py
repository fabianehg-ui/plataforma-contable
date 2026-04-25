"""
Sistema de módulos por empresa.

Cada empresa tiene un set específico de módulos habilitados. El menú lateral
se filtra automáticamente para mostrar solo los módulos habilitados de la
empresa activa, y cada página usa require_modulo() para bloquear el acceso
si la empresa no lo tiene.

Funciones principales:
    - listar_modulos_sistema()        : catálogo global de módulos
    - modulos_de_empresa(empresa_id)  : qué tiene habilitado una empresa
    - empresa_tiene_modulo(emp, mod)  : verificación rápida
    - require_modulo(codigo)          : guard para páginas
    - actualizar_modulos_empresa(...) : asignar módulos (solo superadmin)
"""
from __future__ import annotations
from typing import List, Optional

import streamlit as st

from db.supabase_client import get_supabase
from auth.empresas import empresa_activa


# ============================================================
# Catálogo de módulos
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def listar_modulos_sistema() -> List[dict]:
    """Retorna el catálogo de módulos disponibles del sistema.

    Cada item: {codigo, nombre, descripcion, emoji, orden, activo}
    """
    sb = get_supabase()
    try:
        resp = sb.rpc("listar_modulos_sistema").execute()
        return list(resp.data or [])
    except Exception as e:
        st.error(f"Error listando módulos del sistema: {e}")
        return []


# ============================================================
# Módulos de UNA empresa
# ============================================================

def modulos_de_empresa(empresa_id: str) -> List[dict]:
    """Retorna todos los módulos del sistema con flag habilitado=True/False
    para la empresa indicada.

    Cada item: {codigo, nombre, descripcion, emoji, orden, habilitado}
    """
    if not empresa_id:
        return []
    sb = get_supabase()
    try:
        resp = sb.rpc(
            "modulos_de_empresa",
            {"p_empresa_id": empresa_id},
        ).execute()
        return list(resp.data or [])
    except Exception as e:
        st.error(f"Error listando módulos de la empresa: {e}")
        return []


def codigos_modulos_habilitados(empresa_id: str) -> set:
    """Set de códigos de módulos habilitados para la empresa."""
    if not empresa_id:
        return set()

    # Caché por sesión: evita llamadas repetidas en cada rerun
    cache_key = f"_modulos_empresa_{empresa_id}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]

    modulos = modulos_de_empresa(empresa_id)
    codigos = {m["codigo"] for m in modulos if m.get("habilitado")}
    st.session_state[cache_key] = codigos
    return codigos


def empresa_tiene_modulo(empresa_id: str, codigo: str) -> bool:
    """True si la empresa tiene el módulo habilitado."""
    if not empresa_id or not codigo:
        return False
    return codigo in codigos_modulos_habilitados(empresa_id)


def invalidar_cache_modulos(empresa_id: Optional[str] = None):
    """Limpia la caché de módulos en session_state.

    Útil después de actualizar la asignación de módulos."""
    if empresa_id:
        st.session_state.pop(f"_modulos_empresa_{empresa_id}", None)
    else:
        # Limpiar para todas las empresas que estén en caché
        keys = [k for k in st.session_state.keys() if k.startswith("_modulos_empresa_")]
        for k in keys:
            st.session_state.pop(k, None)
    # También invalidar el cache_data de Streamlit
    try:
        st.cache_data.clear()
    except Exception:
        pass


# ============================================================
# Guard para páginas
# ============================================================

def require_modulo(codigo: str):
    """Detiene la página si la empresa activa no tiene el módulo habilitado.

    Uso típico al inicio de cada página:
        require_auth()
        seleccionar_empresa_sidebar()
        require_modulo("ingresos_pos")  ← detiene si la empresa no lo tiene
    """
    emp = empresa_activa()
    if not emp:
        st.warning("⚠️ Selecciona una empresa en el panel lateral para continuar.")
        st.stop()

    if not empresa_tiene_modulo(emp["id"], codigo):
        st.error(
            f"⛔ El módulo solicitado no está habilitado para "
            f"**{emp['razon_social']}**.\n\n"
            "Si crees que esto es un error, pídele al superadmin del sistema "
            "que habilite este módulo en la sección Configuración."
        )
        st.stop()


# ============================================================
# Operaciones administrativas (superadmin)
# ============================================================

def actualizar_modulos_empresa(empresa_id: str, modulos: List[dict]) -> dict:
    """Actualiza los módulos habilitados de una empresa.

    Args:
        empresa_id: UUID de la empresa.
        modulos: lista de dicts [{'codigo': str, 'habilitado': bool}, ...]

    Returns:
        {'success': bool, 'error': str|None}

    Solo el superadmin puede ejecutarla (la RPC valida).
    """
    sb = get_supabase()
    try:
        sb.rpc(
            "actualizar_modulos_empresa",
            {
                "p_empresa_id": empresa_id,
                "p_modulos": modulos,
            },
        ).execute()
        invalidar_cache_modulos(empresa_id)
        return {"success": True, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}
