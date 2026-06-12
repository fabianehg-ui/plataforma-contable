"""
Repositorio de archivos del módulo P&G en Supabase Storage.

Guarda los insumos del P&G (balances de prueba e informes administrativos)
por empresa, para que cada mes solo haya que subir los archivos nuevos y la
plataforma genere el acumulado con todo lo guardado.

Se reutiliza el bucket existente "empresas-config" bajo la carpeta:
    {empresa_id}/pyg/{tipo}/{nombre_archivo}
con tipo ∈ {"balances", "informes"}.

Todas las funciones degradan en silencio (devuelven [], None o False) si no
hay credenciales de Supabase o el bucket no está disponible, de modo que la
página siga funcionando en modo "solo sesión".
"""
from __future__ import annotations

import re
from typing import List, Optional

BUCKET = "empresas-config"
TIPOS = ("balances", "informes")


def _sb():
    """Cliente de Supabase con permisos de escritura, o None si no hay."""
    try:
        from db.supabase_client import get_supabase_admin, get_supabase
        return get_supabase_admin() or get_supabase()
    except Exception:
        return None


def _ruta(empresa_id: str, tipo: str, nombre: str = "") -> str:
    base = f"{empresa_id}/pyg/{tipo}"
    return f"{base}/{nombre}" if nombre else base


def limpiar_nombre(nombre: str) -> str:
    """Nombre de archivo seguro para Storage (sin rutas ni caracteres raros)."""
    nombre = str(nombre).replace("\\", "/").split("/")[-1]
    nombre = re.sub(r"[^A-Za-z0-9._ ()\-]", "_", nombre).strip()
    return nombre[:120] or "archivo.xlsx"


def listar_archivos(empresa_id: str, tipo: str) -> List[str]:
    """Nombres de archivos guardados para la empresa y tipo dados."""
    sb = _sb()
    if sb is None or not empresa_id:
        return []
    try:
        resp = sb.storage.from_(BUCKET).list(_ruta(empresa_id, tipo))
        nombres = []
        for item in resp or []:
            nombre = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
            if nombre and not str(nombre).startswith("."):
                nombres.append(str(nombre))
        return sorted(nombres)
    except Exception:
        return []


def descargar_archivo(empresa_id: str, tipo: str, nombre: str) -> Optional[bytes]:
    """Bytes del archivo guardado, o None si no existe / no hay acceso."""
    sb = _sb()
    if sb is None or not empresa_id:
        return None
    try:
        resp = sb.storage.from_(BUCKET).download(_ruta(empresa_id, tipo, nombre))
        if resp is None:
            return None
        return resp if isinstance(resp, (bytes, bytearray)) else getattr(resp, "content", None)
    except Exception:
        return None


def guardar_archivo(empresa_id: str, tipo: str, nombre: str, contenido: bytes) -> bool:
    """Sube (o reemplaza) un archivo en el repositorio de la empresa."""
    sb = _sb()
    if sb is None or not empresa_id or not contenido:
        return False
    nombre = limpiar_nombre(nombre)
    ruta = _ruta(empresa_id, tipo, nombre)
    opciones = {
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "upsert": "true",
    }
    try:
        sb.storage.from_(BUCKET).upload(path=ruta, file=bytes(contenido), file_options=opciones)
        return True
    except Exception:
        try:
            sb.storage.from_(BUCKET).update(
                path=ruta, file=bytes(contenido),
                file_options={"content-type": opciones["content-type"]},
            )
            return True
        except Exception:
            return False


def eliminar_archivo(empresa_id: str, tipo: str, nombre: str) -> bool:
    """Quita un archivo del repositorio."""
    sb = _sb()
    if sb is None or not empresa_id:
        return False
    try:
        sb.storage.from_(BUCKET).remove([_ruta(empresa_id, tipo, nombre)])
        return True
    except Exception:
        return False
