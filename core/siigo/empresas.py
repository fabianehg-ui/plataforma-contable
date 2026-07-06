"""
core/siigo/empresas.py
Almacén de las empresas Siigo asociadas al usuario, con su credencial API y su
plan de cuentas. Cada empresa se registra UNA vez (usuario + Access Key); el
Partner-Id suele ser el mismo para todas (así lo indica Siigo para aliados).

La API de Siigo NO usa la contraseña web: usa usuario + Access Key (Siigo Nube →
Alianzas → Mi Credencial API). Este módulo guarda esas credenciales; la Access Key
se cifra en reposo si defines la variable de entorno SIIGO_STORE_KEY (una clave
Fernet). En producción, reemplaza este almacén por tu tabla en Supabase.

Genera una clave Fernet así (una sola vez) y ponla en SIIGO_STORE_KEY / st.secrets:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

try:
    from cryptography.fernet import Fernet
    _HAS_CRYPTO = True
except Exception:  # pragma: no cover
    _HAS_CRYPTO = False

STORE_PATH = os.environ.get("SIIGO_STORE_PATH", "siigo_empresas.json")


def _fernet():
    key = os.environ.get("SIIGO_STORE_KEY")
    if key and _HAS_CRYPTO:
        return Fernet(key.encode() if isinstance(key, str) else key)
    return None


def encryption_active() -> bool:
    return _fernet() is not None


def _enc(s: str) -> str:
    f = _fernet()
    return f.encrypt((s or "").encode()).decode() if f else (s or "")


def _dec(s: str) -> str:
    f = _fernet()
    if not f:
        return s or ""
    try:
        return f.decrypt((s or "").encode()).decode()
    except Exception:
        return s or ""  # valor sin cifrar (migración) o clave distinta


def _load_raw() -> dict:
    p = Path(STORE_PATH)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _save_raw(d: dict) -> None:
    Path(STORE_PATH).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ── API pública ──────────────────────────────────────────────────────
def list_empresas() -> list:
    """[{id, nombre}] sin exponer secretos, ordenadas por nombre."""
    d = _load_raw()
    return [
        {"id": k, "nombre": v.get("nombre", k)}
        for k, v in sorted(d.items(), key=lambda kv: (kv[1].get("nombre") or "").lower())
    ]


def get_credenciales(emp_id: str) -> Optional[dict]:
    e = _load_raw().get(emp_id)
    if not e:
        return None
    return {
        "username": e.get("username", ""),
        "access_key": _dec(e.get("access_key", "")),
        "partner_id": e.get("partner_id", ""),
    }


def upsert_empresa(emp_id: str, nombre: str, username: str, access_key: str, partner_id: str) -> None:
    d = _load_raw()
    prev = d.get(emp_id, {})
    # Si no reescriben la Access Key (vacía en el form), conserva la anterior.
    ak = _enc(access_key) if access_key else prev.get("access_key", "")
    d[emp_id] = {
        "nombre": nombre,
        "username": username,
        "access_key": ak,
        "partner_id": partner_id,
        "plan": prev.get("plan", {}),
        "mapeo": prev.get("mapeo", {}),
    }
    _save_raw(d)


def delete_empresa(emp_id: str) -> None:
    d = _load_raw()
    d.pop(emp_id, None)
    _save_raw(d)


def get_config(emp_id: str) -> dict:
    """Plan de cuentas y mapeo de prefijos guardados para la empresa."""
    e = _load_raw().get(emp_id) or {}
    return {"plan": e.get("plan", {}) or {}, "mapeo": e.get("mapeo", {}) or {}}


def save_config(emp_id: str, plan: dict, mapeo: dict) -> None:
    d = _load_raw()
    if emp_id not in d:
        return
    d[emp_id]["plan"] = plan or {}
    d[emp_id]["mapeo"] = mapeo or {}
    _save_raw(d)
