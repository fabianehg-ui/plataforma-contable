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

# Datos del login OAuth2 (Azure AD B2C) tomados del flujo real de Siigo Nube.
TOKEN_URL = "https://account.siigo.com/siigob2cco.onmicrosoft.com/b2c_1a_col_pd_ssosiigo/oauth2/v2.0/token"
CLIENT_ID = "c0f95d00-a5b7-4cfc-a84c-7fc1be2a6720"
SCOPE = "openid profile https://siigob2cco.onmicrosoft.com/shell-pd-col/basic offline_access"


class SiigoWebError(Exception):
    pass


def refresh_access_token(refresh_token: str) -> dict:
    """Con el REFRESH token (obtenido una vez de tu sesion), pide un access token
    nuevo, sin usuario ni contrasena. B2C suele ROTAR el refresh token, asi que
    guarda el 'refresh_token' devuelto para la proxima. Devuelve dict con
    access_token, refresh_token y expires_in."""
    rt = (refresh_token or "").strip()
    if not rt:
        raise SiigoWebError("Falta el refresh token.")
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": rt,
        "scope": SCOPE,
    }
    r = requests.post(TOKEN_URL, data=data,
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
    if not r.ok:
        raise SiigoWebError(f"No se pudo renovar el token ({r.status_code}): {r.text[:300]}")
    j = r.json()
    if not j.get("access_token"):
        raise SiigoWebError("La renovacion no devolvio access_token.")
    return {
        "access_token": j.get("access_token"),
        "refresh_token": j.get("refresh_token", rt),
        "expires_in": j.get("expires_in"),
    }


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


def login_headless(email: str, password: str, timeout_ms: int = 60000) -> dict:
    """MODO C (experimental). Inicia sesion en Siigo con un navegador headless
    (Playwright) y captura el token de la sesion — SIN guardar la contrasena:
    se usa aqui una sola vez y se devuelve el refresh_token para renovar despues.

    Requiere en el servidor:  pip install playwright  &&  playwright install chromium
    (en Railway, agregar esos pasos + dependencias del navegador al Dockerfile).

    LIMITES: si la cuenta tiene MFA/2FA o aparece un CAPTCHA, este metodo NO
    funciona (no se evaden). Los selectores del formulario pueden cambiar; si
    Siigo modifica su login, hay que ajustarlos. Va contra los terminos de Siigo.
    Devuelve dict con access_token_header y refresh_token.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise SiigoWebError("Falta Playwright. Instala: pip install playwright && playwright install chromium.")

    caught = {"auth": None, "refresh": None}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        def on_request(req):
            try:
                if "services.siigo.com" in req.url and not caught["auth"]:
                    a = req.headers.get("authorization")
                    if a:
                        caught["auth"] = a
            except Exception:
                pass

        def on_response(resp):
            try:
                if "oauth2/v2.0/token" in resp.url:
                    j = resp.json()
                    if j.get("refresh_token"):
                        caught["refresh"] = j["refresh_token"]
            except Exception:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        page.goto("https://siigonube.siigo.com/", wait_until="load", timeout=timeout_ms)
        # Formulario de correo/contrasena (selectores tolerantes; ajustar si cambian).
        try:
            page.fill("input[type='email'], input[name='Email'], input[placeholder*='Correo']", email, timeout=timeout_ms)
            page.fill("input[type='password'], input[name='Password'], input[placeholder*='Contrase']", password, timeout=timeout_ms)
            page.click("button:has-text('Continuar'), button[type='submit'], #continue")
        except Exception as e:
            browser.close()
            raise SiigoWebError(f"No se pudo completar el login (¿cambió el formulario, o hay MFA/CAPTCHA?): {e}")

        # Espera a que la app cargue y dispare llamadas con token.
        for _ in range(40):
            if caught["auth"] and caught["refresh"]:
                break
            page.wait_for_timeout(500)
        browser.close()

    if not caught["auth"] and not caught["refresh"]:
        raise SiigoWebError("No se capturó token. Posible MFA/CAPTCHA, credenciales erróneas o cambio del login.")
    return {"access_token_header": caught["auth"], "refresh_token": caught["refresh"]}


def _norm_empresas(data) -> list:
    arr = data if isinstance(data, list) else (data.get("results") or data.get("companies") or data.get("data") or [])
    out = []
    for c in arr or []:
        tid = (c.get("cloudTenantID") or c.get("CloudTenantID") or c.get("tenantId") or c.get("TenantId")
               or c.get("tenant_id") or c.get("companyKey") or c.get("id") or c.get("Id") or c.get("serial"))
        if not tid:
            continue
        out.append({
            "tenantId": tid,
            "nombre": (c.get("nameCompany") or c.get("name") or c.get("Name") or c.get("companyName")
                       or c.get("razonSocial") or "(sin nombre)"),
            "nit": c.get("nit") or c.get("Nit") or c.get("identification") or c.get("Identification") or "",
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
