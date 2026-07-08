"""
core/f350/muisca_client.py
Cliente para diligenciar el BORRADOR del Formulario 350 (Retención en la Fuente)
en el portal Muisca de la DIAN, reutilizando el login del contribuyente.

Flujo (observado del portal, api.dian.gov.co):
  1. login()            -> POST weblogin (clave en base64) y establece la sesión (cookies).
  2. obtener_borrador() -> GET borrador vacío del año/periodo (plantilla de casillas).
  3. construir_doc()    -> coloca cada valor EN SU RENGLÓN: cs_id_{renglon} = valor.
  4. guardar_borrador() -> POST /formularios  -> devuelve el id del formulario.
  5. descargar_pdf()    -> GET /formularios/{id}/descargar -> PDF del borrador.

SEGURIDAD Y ALCANCE (importante):
  - Las credenciales NO se guardan en este archivo; se pasan al llamar login().
    Si las persistes por empresa en Supabase, guárdalas CIFRADAS (ver cifrado_dian.py).
  - Este cliente llega hasta DESCARGAR EL BORRADOR en PDF y ahí para.
    La firma y presentación las hace el contador manualmente, tras revisar.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import requests

MUISCA = "https://muisca.dian.gov.co"
API = "https://api.dian.gov.co"
F350_BASE = API + "/documentos/retefuente350v10/v1"
CLIENT_ID = "Wo0aKAlB7vRP_16frPI1x9ZphBEa"          # clientId del portal (verificar si cambia)
# URL de callback completa que el portal envia en redirectUri (verificar si cambia)
CALLBACK = ("http://muisca.dian.gov.co/IdentidadRest_LoginFiltro/api/sts/v1/auth/callback"
            "?redirect_uri=http%3A%2F%2Fmuisca.dian.gov.co%2FWebArquitectura%2FDefLogin.faces")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
_PLANTILLA = Path(__file__).with_name("plantilla_f350_v10.json")


class MuiscaError(Exception):
    pass


class MuiscaF350Client:
    def __init__(self, timeout: int = 60):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": _UA, "Accept": "application/json, text/plain, */*"})
        self.timeout = timeout

    # ---------- 1) LOGIN ----------
    def login(self, tipo_doc: str, num_doc: str, nit_empresa: str, password: str, a_nombre_de: str = "0") -> bool:
        """tipo_doc/num_doc: del REPRESENTANTE; nit_empresa: NIT de la empresa (numDocumentoOrg)."""
        ide = {
            "clientId": CLIENT_ID, "redirect_uri": CALLBACK,
            "responseType": "", "scope": "", "state": "", "nonce": "",
            "params": {"tipoUsuario": "muisca"},
        }
        ide_request = base64.b64encode(json.dumps(ide).encode("utf-8")).decode("ascii")
        login_page = MUISCA + "/WebIdentidadLogin/?ideRequest=" + ide_request

        # 1) Cargar la página de login (establece cookies de sesión, como el navegador)
        try:
            self.s.get(login_page, timeout=self.timeout,
                       headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
        except Exception:  # noqa: BLE001
            pass

        data = {
            "aNombreDe": a_nombre_de,
            "numDocumentoOrg": str(nit_empresa),
            "tipoDoc": tipo_doc,
            "numDoc": str(num_doc),
            "password": base64.b64encode(password.encode("utf-8")).decode("ascii"),
            "clientId": CLIENT_ID,
            "redirectUri": CALLBACK,
            "ideRequest": ide_request,
        }
        # 2) Headers que el servidor EXIGE (Origin + Referer con el ideRequest)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": MUISCA,
            "Referer": login_page,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Upgrade-Insecure-Requests": "1",
        }
        r = self.s.post(MUISCA + "/IdentidadRest_Acceso/api/sts/v1/auth/weblogin",
                        data=data, headers=headers, timeout=self.timeout, allow_redirects=True)
        if r.status_code >= 400:
            raise MuiscaError(f"Login falló (HTTP {r.status_code}). Revisa NIT de la empresa, "
                              f"tipo/número de documento del representante y la clave.")
        self.s.post(API + "/identidad/sts/v2/cookies/token", timeout=self.timeout)
        chk = self.s.get(F350_BASE + "/anios", timeout=self.timeout)
        if chk.status_code >= 400:
            raise MuiscaError("Login OK pero no se estableció la sesión con la API del 350. "
                              f"(anios -> HTTP {chk.status_code}).")
        return True

    # ---------- 2) BORRADOR (plantilla de casillas) ----------
    def obtener_borrador(self, anio: int, periodo: int, periodicidad: str = "mensual") -> dict:
        try:
            r = self.s.get(F350_BASE + "/formularios/borrador",
                           params={"modo": "inicial", "anio": anio, "periodicidad": periodicidad, "periodo": periodo},
                           timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            if _PLANTILLA.exists():   # respaldo local si la API falla
                return json.loads(_PLANTILLA.read_text(encoding="utf-8"))
            raise MuiscaError(f"No pude obtener el borrador vacío: {e}")

    # ---------- 3) COLOCAR CADA VALOR EN SU RENGLÓN ----------
    def construir_doc(self, borrador: dict, *, nit, dv, razon_social, anio, periodo,
                      actividad_economica, valores_por_renglon: dict) -> dict:
        """valores_por_renglon: {numero_renglon: valor}. Cada uno va a cs_id_{renglon}."""
        doc = borrador.get("doc", borrador)
        cab, cuerpo, pie = doc["cab"], doc["cuerpo"], doc.get("pie", {})
        cab["id"] = -1
        cab["cs_id_1"] = int(anio)
        cab["cs_id_3"] = int(periodo)
        cab["cs_id_5"] = str(nit)
        cab["cs_id_6"] = str(dv)
        cab["cs_id_11"] = razon_social
        if actividad_economica is not None:
            cuerpo["cs_id_27"] = str(actividad_economica)

        no_existen = []
        for renglon, valor in valores_por_renglon.items():
            casilla = f"cs_id_{int(renglon)}"
            v = int(round(float(valor or 0)))
            if casilla in cuerpo:
                cuerpo[casilla] = v
            elif casilla in pie:
                pie[casilla] = v
            else:
                no_existen.append(renglon)
        if no_existen:
            raise MuiscaError(f"Estos renglones no existen en el F350 v10: {no_existen}. "
                              f"Revisa el mapeo renglón->casilla.")
        return {"doc": doc, "status": borrador.get("status"), "statusText": borrador.get("statusText")}

    # ---------- 4) GUARDAR BORRADOR ----------
    def guardar_borrador(self, doc_payload: dict) -> str:
        r = self.s.post(F350_BASE + "/formularios", json=doc_payload, timeout=self.timeout,
                        headers={"Content-Type": "application/json;charset=UTF-8"})
        if r.status_code not in (200, 201):
            raise MuiscaError(f"No se guardó el borrador (HTTP {r.status_code}): {r.text[:200]}")
        j = r.json()
        d = j.get("doc", j)
        form_id = (d.get("cab", {}) or {}).get("id") or (d.get("cab", {}) or {}).get("cs_id_4") or _buscar_id(j)
        if not form_id:
            raise MuiscaError("El borrador se guardó pero no hallé el id del formulario en la respuesta.")
        return str(form_id)

    # ---------- 5) DESCARGAR PDF ----------
    def descargar_pdf(self, form_id: str, ruta_salida: str) -> str:
        r = self.s.get(f"{F350_BASE}/formularios/{form_id}/descargar", timeout=self.timeout)
        if r.status_code != 200 or "pdf" not in r.headers.get("Content-Type", "").lower():
            raise MuiscaError(f"No se descargó el PDF (HTTP {r.status_code}, {r.headers.get('Content-Type')}).")
        Path(ruta_salida).write_bytes(r.content)
        return ruta_salida

    # ---------- FLUJO COMPLETO ----------
    def diligenciar_y_descargar(self, *, tipo_doc, num_doc, nit_empresa, password,
                                nit, dv, razon_social, anio, periodo, actividad_economica,
                                valores_por_renglon, ruta_pdf, periodicidad="mensual") -> tuple:
        self.login(tipo_doc, num_doc, nit_empresa, password)
        borrador = self.obtener_borrador(anio, periodo, periodicidad)
        doc = self.construir_doc(borrador, nit=nit, dv=dv, razon_social=razon_social,
                                 anio=anio, periodo=periodo, actividad_economica=actividad_economica,
                                 valores_por_renglon=valores_por_renglon)
        form_id = self.guardar_borrador(doc)
        ruta = self.descargar_pdf(form_id, ruta_pdf)
        return ruta, form_id


def _buscar_id(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("id", "cs_id_4") and str(v).isdigit() and len(str(v)) > 6:
                return v
            r = _buscar_id(v)
            if r:
                return r
    elif isinstance(o, list):
        for x in o:
            r = _buscar_id(x)
            if r:
                return r
    return None
