"""
core/siigo/web.py
Cliente de los endpoints INTERNOS de Siigo Nube (para empresas SIN API), operado
desde el repo con un TOKEN que pegas de tu sesión (no guarda contraseñas).

Endpoints mapeados del tráfico real de la web:
  GET  /accountantportal/api/accountant/getusedaccountantcompanies  -> empresas
  GET  /accountantportal/api/accountant/gettenantscompany           -> empresas
  POST /accountantportal/api/multilogin/last-login {tenantId}       -> elegir empresa
  GET  /entryvouchers/api/v1/management/sales_report?doc_class=FV&is_electronic=1
       &page=&page_size=                                            -> facturas de venta

⚠️ No documentados: pueden cambiar sin aviso. Úsalo solo en tus propias cuentas.
El token de Siigo dura ~1 hora; cuando devuelva 401, pega uno nuevo.
"""
from __future__ import annotations

from typing import Optional, Tuple

import requests

BASE = "https://services.siigo.com"
TIMEOUT = 90


class SiigoWebError(Exception):
    pass


def _headers(token: str) -> dict:
    # El token suele venir como "Bearer eyJ...". Si pegan solo el JWT, se antepone.
    t = token.strip()
    if t and not t.lower().startswith("bearer "):
        t = "Bearer " + t
    return {
        "Authorization": t,
        "Content-Type": "application/json",
        "Origin": "https://siigonube.siigo.com",
        "Referer": "https://siigonube.siigo.com/",
    }


def _norm_empresas(data) -> list:
    arr = data if isinstance(data, list) else (data.get("results") or data.get("companies") or data.get("data") or [])
    out = []
    for c in arr or []:
        tid = c.get("tenantId") or c.get("TenantId") or c.get("tenant_id") or c.get("id") or c.get("Id")
        if not tid:
            continue
        out.append({
            "tenantId": tid,
            "nombre": c.get("name") or c.get("Name") or c.get("companyName") or c.get("razonSocial") or "(sin nombre)",
            "nit": c.get("identification") or c.get("Identification") or c.get("nit") or c.get("Nit") or "",
        })
    return out


def get_empresas(token: str) -> list:
    """Catálogo de empresas asociadas al usuario (portal de contador)."""
    out = []
    for path in ("/accountantportal/api/accountant/getusedaccountantcompanies",
                 "/accountantportal/api/accountant/gettenantscompany"):
        try:
            r = requests.get(BASE + path, headers=_headers(token), timeout=TIMEOUT)
            if r.status_code == 401:
                raise SiigoWebError("Token vencido o inválido (401). Pega un token nuevo desde tu sesión de Siigo.")
            if r.ok:
                for c in _norm_empresas(r.json()):
                    if not any(o["tenantId"] == c["tenantId"] for o in out):
                        out.append(c)
        except SiigoWebError:
            raise
        except Exception:
            pass
    return out


def elegir_empresa(token: str, tenant_id: str) -> Tuple[bool, int]:
    """Selecciona la empresa activa (multilogin)."""
    r = requests.post(BASE + "/accountantportal/api/multilogin/last-login",
                      headers=_headers(token), json={"tenantId": tenant_id}, timeout=TIMEOUT)
    return r.ok, r.status_code


def _find_arr(o, depth=0):
    if depth > 7:
        return None
    if isinstance(o, list):
        return o if (o and isinstance(o[0], dict)) else None
    if isinstance(o, dict):
        for v in o.values():
            r = _find_arr(v, depth + 1)
            if r is not None:
                return r
    return None


def get_facturas(token: str, doc_class: str = "FV", is_electronic: int = 1,
                 page_size: int = 50, extra: Optional[dict] = None, max_pages: int = 300):
    """Facturas de venta (sales_report), paginadas hasta traerlas todas.
    `extra` permite pasar filtros adicionales (p. ej. fechas) cuando confirmemos
    los nombres de esos parámetros. Devuelve (filas, primera_respuesta_cruda)."""
    rows, page, first = [], 1, None
    while True:
        params = {"page": page, "page_size": page_size, "doc_class": doc_class, "is_electronic": is_electronic}
        if extra:
            params.update(extra)
        r = requests.get(BASE + "/entryvouchers/api/v1/management/sales_report",
                         headers=_headers(token), params=params, timeout=TIMEOUT)
        if r.status_code == 401:
            raise SiigoWebError("Token vencido o inválido (401). Pega un token nuevo.")
        if not r.ok:
            raise SiigoWebError(f"sales_report {r.status_code}: {r.text[:200]}")
        d = r.json()
        if first is None:
            first = d
        arr = _find_arr(d) or []
        rows.extend(arr)
        if len(arr) < page_size:
            break
        page += 1
        if page > max_pages:
            break
    return rows, first
