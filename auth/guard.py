"""
auth/guard.py — guarda estándar de página para INTEGRAL.

Una sola línea al inicio de CUALQUIER página garantiza: login, empresa activa
seleccionada (sidebar), usuario visible y un banner "Empresa activa: X". Así
ninguna página opera sin saber a qué empresa pertenece lo que se hace.

Uso:
    from auth.guard import guard_empresa
    emp, sb = guard_empresa()                       # roles por defecto
    emp, sb = guard_empresa(("admin", "operador"))  # restringir rol

Para páginas multi-empresa (procesan varias a la vez, p.ej. DIAN XML masivo):
    from auth.guard import guard_login
    guard_login()   # exige login pero NO fija una sola empresa
"""
from __future__ import annotations

import streamlit as st


def guard_login():
    """Solo login + usuario en el sidebar (para páginas multi-empresa)."""
    from auth.login import require_auth, sidebar_user_info
    require_auth()
    sidebar_user_info()


def guard_empresa(roles=("admin", "operador", "consulta"), banner: bool = True):
    """Login + empresa activa fija + banner. Devuelve (empresa, sb).

    Corta la página (st.stop) si no hay sesión, empresa o rol válido.
    """
    from auth.login import require_auth, sidebar_user_info
    from auth.empresas import seleccionar_empresa_sidebar, require_rol
    from db.supabase_client import get_supabase

    require_auth()
    seleccionar_empresa_sidebar()
    sidebar_user_info()
    emp = require_rol(list(roles))
    sb = get_supabase()
    if banner:
        st.info(f"🏢 Empresa activa: **{emp.get('razon_social', '')}**"
                + (f" · NIT {emp['nit']}" if emp.get("nit") else ""))
    return emp, sb
