"""
core/f350/dian_acceso.py
Guarda y recupera las credenciales DIAN por empresa, siempre CIFRADAS.
La contraseña nunca se guarda ni se devuelve en texto plano salvo en el momento
justo de usarla para el login (en memoria).
"""
from __future__ import annotations

import json

from .cifrado_dian import cifrar, descifrar

TABLA = "f350_dian_credenciales"


def _enmascarar(num_doc: str) -> str:
    s = str(num_doc or "")
    return ("*" * max(0, len(s) - 4)) + s[-4:] if s else ""


def guardar_credenciales(sb, empresa_id: str, tipo_doc: str, num_doc: str, password: str, user_id: str | None = None) -> None:
    payload = json.dumps({"tipo_doc": tipo_doc, "num_doc": str(num_doc), "password": password})
    fila = {
        "empresa_id": empresa_id,
        "tipo_doc": tipo_doc,
        "num_doc_enmasc": _enmascarar(num_doc),
        "credencial_cifrada": cifrar(payload),
        "actualizado_por": user_id,
    }
    sb.table(TABLA).upsert(fila, on_conflict="empresa_id").execute()


def estado_credenciales(sb, empresa_id: str) -> dict | None:
    """Devuelve {tipo_doc, num_doc_enmasc, actualizado_en} SIN la contraseña, o None."""
    r = sb.table(TABLA).select("tipo_doc,num_doc_enmasc,actualizado_en").eq("empresa_id", empresa_id).limit(1).execute()
    return r.data[0] if r.data else None


def obtener_credenciales(sb, empresa_id: str) -> dict | None:
    """Descifra y devuelve {tipo_doc, num_doc, password}. Úsalo solo al momento de loguear."""
    r = sb.table(TABLA).select("credencial_cifrada").eq("empresa_id", empresa_id).limit(1).execute()
    if not r.data:
        return None
    return json.loads(descifrar(r.data[0]["credencial_cifrada"]))


def borrar_credenciales(sb, empresa_id: str) -> None:
    sb.table(TABLA).delete().eq("empresa_id", empresa_id).execute()
