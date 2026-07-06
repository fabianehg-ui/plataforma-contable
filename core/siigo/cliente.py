"""
core/siigo/cliente.py
Cliente de la API oficial de Siigo para ContaTools.

Portado de la extensión Chrome (siigo-api.js). Endpoints usados:
  POST /auth            -> token JWT (válido 24h)   (OJO: /auth va SIN /v1)
  GET  /v1/invoices     -> facturas de venta
  GET  /v1/vouchers     -> recibos de caja asentados
  GET  /v1/credit-notes -> notas crédito
  GET  /v1/customers    -> terceros (NITs)

Todas las peticiones GET requieren:
  Authorization: Bearer <token>
  Partner-Id: <nombreEnCamelCase>

El endpoint /v1/invoices es inestable con rangos amplios (500 unhandled_error),
por eso se consulta DÍA POR DÍA y con reintentos ante 429/5xx.
"""
from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Callable, Optional

import requests

BASE = "https://api.siigo.com"
DELAY_S = 0.7           # ~85 req/min (seguro para producción; sube a ~6.5 en pruebas)
MAX_RETRIES = 4
TIMEOUT = 120           # Siigo recomienda esperar 120s en picos altos


class SiigoError(Exception):
    """Error de la API de Siigo o de la integración."""


def authenticate(username: str, access_key: str, partner_id: str) -> str:
    """Genera el access_token (válido 24h)."""
    headers = {"Content-Type": "application/json"}
    if partner_id:
        headers["Partner-Id"] = partner_id  # Siigo lo pide también en el login
    r = requests.post(
        f"{BASE}/auth",
        headers=headers,
        json={"username": username, "access_key": access_key},
        timeout=TIMEOUT,
    )
    if not r.ok:
        raise SiigoError(f"Auth falló ({r.status_code}): {r.text or r.reason}")
    data = r.json()
    token = data.get("access_token")
    if not token:
        raise SiigoError("La respuesta de /auth no contiene access_token.")
    return token


def _get_all_paginated(
    path: str,
    token: str,
    partner_id: str,
    params: Optional[dict] = None,
    page_size: int = 100,
    on_progress: Optional[Callable] = None,
) -> list:
    """GET paginado. Siigo devuelve {pagination, results}. Reintenta 429/5xx."""
    params = dict(params or {})
    headers = {
        "Authorization": f"Bearer {token}",
        "Partner-Id": partner_id,
        "Content-Type": "application/json",
    }
    all_rows: list = []
    page = 1
    total = float("inf")
    retries = 0

    while len(all_rows) < total:
        q = dict(params)
        q["page"] = page
        q["page_size"] = page_size
        r = requests.get(f"{BASE}{path}", headers=headers, params=q, timeout=TIMEOUT)

        # 429 (rate limit) o 5xx (fallo pasajero): espera y reintenta la MISMA página.
        if r.status_code == 429 or r.status_code >= 500:
            if retries < MAX_RETRIES:
                retries += 1
                time.sleep(5 if r.status_code == 429 else 1.5 * retries)
                continue
            raise SiigoError(
                f"GET {path} falló ({r.status_code}) tras {MAX_RETRIES} reintentos: {r.text or r.reason}"
            )
        if not r.ok:
            raise SiigoError(f"GET {path} falló ({r.status_code}): {r.text or r.reason}")
        retries = 0

        data = r.json()
        results = data.get("results") or data.get("Results") or []
        pg = data.get("pagination") or {}
        if isinstance(pg, dict) and isinstance(pg.get("total_results"), int):
            total = pg["total_results"]
        elif not results:
            total = len(all_rows)

        all_rows.extend(results)
        if on_progress:
            on_progress(
                page=page,
                fetched=len(all_rows),
                total=(total if total != float("inf") else len(all_rows)),
            )

        if not results or len(results) < page_size:
            break
        page += 1
        time.sleep(DELAY_S)

    return all_rows


def _rfc_start(d: Optional[str]) -> Optional[str]:
    return f"{d}T00:00:00Z" if d else None


def _rfc_end(d: Optional[str]) -> Optional[str]:
    return f"{d}T23:59:59Z" if d else None


def _each_day(start_iso: str, end_iso: str) -> list:
    d0, d1 = date.fromisoformat(start_iso), date.fromisoformat(end_iso)
    days = []
    while d0 <= d1:
        days.append(d0.isoformat())
        d0 += timedelta(days=1)
    return days


def _get_daily(
    path: str,
    token: str,
    partner_id: str,
    date_start: Optional[str],
    date_end: Optional[str],
    on_progress: Optional[Callable] = None,
) -> list:
    """Descarga día por día un endpoint que filtra por date_start/date_end (RFC3339)."""
    if not date_start or not date_end:
        params = {}
        if date_start:
            params["date_start"] = _rfc_start(date_start)
        if date_end:
            params["date_end"] = _rfc_end(date_end)
        return _get_all_paginated(path, token, partner_id, params, on_progress=on_progress)

    days = _each_day(date_start, date_end)
    all_rows: list = []
    for i, day in enumerate(days, 1):
        params = {"date_start": _rfc_start(day), "date_end": _rfc_end(day)}

        def prog(page, fetched, total, _day=day, _i=i):
            if on_progress:
                on_progress(day=_day, day_index=_i, day_count=len(days), fetched=len(all_rows) + fetched)

        try:
            chunk = _get_all_paginated(path, token, partner_id, params, on_progress=prog)
        except SiigoError as e:
            raise SiigoError(f"Descargando {path} del día {day}: {e}")
        all_rows.extend(chunk)
    return all_rows


# ── API pública ──────────────────────────────────────────────────────
def get_invoices(token, partner_id, date_start, date_end, on_progress=None) -> list:
    """Facturas de venta (fuente del plano de ventas y de los recibos 'cancelar todo')."""
    return _get_daily("/v1/invoices", token, partner_id, date_start, date_end, on_progress)


def get_vouchers(token, partner_id, date_start, date_end, on_progress=None) -> list:
    """Recibos de caja YA asentados en Siigo."""
    return _get_daily("/v1/vouchers", token, partner_id, date_start, date_end, on_progress)


def get_credit_notes(token, partner_id, date_start, date_end, on_progress=None) -> list:
    """Notas crédito (cada una enlaza su factura en invoice.name / invoice.id)."""
    return _get_daily("/v1/credit-notes", token, partner_id, date_start, date_end, on_progress)


def get_customers(token, partner_id, date_start=None, date_end=None, on_progress=None) -> list:
    """Clientes / terceros (NITs)."""
    params = {}
    if date_start:
        params["created_start"] = date_start
    if date_end:
        params["created_end"] = date_end
    return _get_all_paginated("/v1/customers", token, partner_id, params, on_progress=on_progress)
