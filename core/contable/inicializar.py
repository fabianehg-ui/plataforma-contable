"""
core/contable/inicializar.py

Siembra de catálogos por defecto en una empresa y directorio global de terceros.

- inicializar_empresa(sb, empresa_id): copia las plantillas (PUC, comprobantes,
  tipos IVA/retención, conceptos, terceros base) a la empresa. Es idempotente
  (ON CONFLICT DO NOTHING). Toda empresa NUEVA ya lo recibe por un trigger; esto
  sirve para (re)inicializar empresas existentes.  Requiere migración 017.
- Directorio global de terceros: autocompletar el nombre al digitar un NIT.
"""
from __future__ import annotations

from typing import Optional


def inicializar_empresa(sb, empresa_id: str) -> None:
    """Ejecuta la función SQL cn_inicializar_empresa(empresa_id)."""
    sb.rpc("cn_inicializar_empresa", {"p_empresa": str(empresa_id)}).execute()


def buscar_directorio(sb, nit: str) -> dict:
    """Busca un NIT en el directorio global. {} si no existe."""
    if not nit:
        return {}
    res = (sb.table("cn_directorio_terceros").select("*")
           .eq("nit", str(nit).strip()).limit(1).execute())
    return (res.data or [{}])[0]


def listar_directorio(sb, query: Optional[str] = None, limit: int = 50) -> list[dict]:
    q = sb.table("cn_directorio_terceros").select("*")
    if query:
        q = q.ilike("nombre", f"%{query}%")
    return q.order("nombre").limit(limit).execute().data or []


def upsert_directorio(sb, nit: str, nombre: str, **campos) -> dict:
    payload = {"nit": str(nit), "nombre": nombre, **campos}
    res = sb.table("cn_directorio_terceros").upsert(payload, on_conflict="nit").execute()
    return (res.data or [{}])[0]
