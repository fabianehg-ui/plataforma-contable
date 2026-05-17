"""
core/procesadores/cliente_token_dian.py

Cliente HTTP para el portal DIAN VPFE usando un link Token compartido
(`/User/AuthToken?pk=...&rk=...&token=...`). El Token es un mecanismo oficial
de la DIAN que da acceso temporal (~1 hora) sin requerir login ni captcha.

EXPONE:
    autenticar(token_url) -> SesionDIAN
    SesionDIAN.listar_documentos(...) -> Iterator[dict]
    SesionDIAN.descargar_zip(track_id) -> bytes
    SesionDIAN.descargar_lote(track_ids, callback) -> dict
"""
from __future__ import annotations

import io
import re
import time
import zipfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterator, List, Optional
from urllib.parse import parse_qs, urlparse

import requests

BASE_URL          = "https://catalogo-vpfe.dian.gov.co"
ENDPOINT_LIST     = f"{BASE_URL}/Document/GetDocumentsPageToken"
ENDPOINT_DOWNLOAD = f"{BASE_URL}/Document/DownloadZipFiles"
PAGE_SIZE         = 100
TIMEOUT_AUTH      = 30
TIMEOUT_LIST      = 30
TIMEOUT_DOWNLOAD  = 60
MAX_RETRIES       = 2
USER_AGENT        = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Tipos de documento que reconoce la DIAN
TIPOS_DOC = {
    "01": "Factura electrónica",
    "91": "Nota crédito",
    "92": "Nota débito",
    "05": "Documento soporte",
}


class TokenInvalido(Exception):
    """Token expirado, mal formado, o sin permisos."""


class ErrorDIAN(Exception):
    """Error del endpoint DIAN (HTTP 5xx, JSON malformado, etc.)."""


@dataclass
class SesionDIAN:
    """
    Sesión autenticada con el portal DIAN.

    Mantiene cookies y CSRF token. Una sesión es válida mientras dure el Token
    DIAN original (~1 hora). Si una request devuelve 401/403 hay que reautenticar.
    """
    session: requests.Session
    csrf_token: str
    nit_cuenta: str           # del query param rk del Token URL
    partition_key: str        # del query param pk
    autenticado_en: datetime = field(default_factory=datetime.utcnow)

    def __repr__(self):
        return (
            f"<SesionDIAN NIT={self.nit_cuenta} "
            f"autenticado={self.autenticado_en.isoformat()}>"
        )

    # ── Listar documentos ─────────────────────────────────────

    def listar_documentos(
        self,
        tipos: Optional[List[str]] = None,
        desde_ms: Optional[int] = None,
        hasta_ms: Optional[int] = None,
        on_progress: Optional[Callable[[str, int, int], None]] = None,
    ) -> List[dict]:
        """
        Lista TODOS los documentos del catálogo, opcionalmente filtrando por
        rango de fecha de emisión (filtro client-side, ya que la API DIAN
        ignora StartDate/EndDate).

        Args:
            tipos: lista de DocumentTypeId (['01','91','92','05']). Default: todos.
            desde_ms, hasta_ms: epoch ms para filtrar por EmissionDate. None = sin filtro.
            on_progress: callback(etiqueta, actual, total) para reportar avance.

        Returns:
            lista de dicts con la fila completa de la API, filtrados.

        Cómo funciona:
            La API devuelve documentos ordenados por fecha DESC (más recientes
            primero). Para evitar paginar las 17.241 facturas cuando solo
            necesitamos un mes, paginamos hasta que una página entera venga
            anterior al rango pedido — "corte temprano".
        """
        if tipos is None:
            tipos = list(TIPOS_DOC.keys())

        resultados: List[dict] = []
        for tipo in tipos:
            self._listar_un_tipo(
                tipo, desde_ms, hasta_ms, resultados, on_progress
            )
        return resultados

    def _listar_un_tipo(
        self,
        tipo: str,
        desde_ms: Optional[int],
        hasta_ms: Optional[int],
        out: List[dict],
        on_progress: Optional[Callable],
    ):
        etiqueta = TIPOS_DOC.get(tipo, tipo)
        primera = self._pedir_pagina(start=0, length=PAGE_SIZE, tipo=tipo)
        total = primera["recordsFiltered"]
        if total == 0:
            if on_progress:
                on_progress(etiqueta, 0, 0)
            return

        total_paginas = (total + PAGE_SIZE - 1) // PAGE_SIZE
        ya_en_rango = False

        def procesar_pagina(filas: List[dict]) -> dict:
            nonlocal ya_en_rango
            stats = {"matches": 0, "antiguos": 0, "nuevos": 0, "sin_fecha": 0}
            for fila in filas:
                emision = parsear_fecha_dian_ms(fila.get("EmissionDate"))
                if emision is None:
                    # Sin fecha confiable: lo incluimos por seguridad
                    out.append(fila)
                    stats["sin_fecha"] += 1
                    continue
                if desde_ms is not None and emision < desde_ms:
                    stats["antiguos"] += 1
                    continue
                if hasta_ms is not None and emision > hasta_ms:
                    stats["nuevos"] += 1
                    continue
                out.append(fila)
                stats["matches"] += 1
            return stats

        stats = procesar_pagina(primera["data"])
        if stats["matches"] > 0:
            ya_en_rango = True

        if on_progress:
            on_progress(etiqueta, 1, total_paginas)

        for p in range(1, total_paginas):
            try:
                r = self._pedir_pagina(start=p * PAGE_SIZE, length=PAGE_SIZE, tipo=tipo)
            except ErrorDIAN:
                # No reventar todo el listado por un error transitorio
                continue
            stats = procesar_pagina(r["data"])
            if stats["matches"] > 0:
                ya_en_rango = True
            if on_progress:
                on_progress(etiqueta, p + 1, total_paginas)

            # Corte temprano: ya pasamos el rango pedido
            todos_antiguos = (
                desde_ms is not None
                and len(r["data"]) > 0
                and stats["antiguos"] == len(r["data"])
            )
            if ya_en_rango and todos_antiguos:
                break

            # Respiro suave cada 5 páginas
            if p % 5 == 0:
                time.sleep(0.1)

    def _pedir_pagina(self, start: int, length: int, tipo: str) -> dict:
        """Una llamada a GetDocumentsPageToken. Devuelve dict con 'data' y 'recordsFiltered'."""
        body = {
            "draw": "1",
            "start": str(start),
            "length": str(length),
            "DocumentKey": "",
            "SerieAndNumber": "",
            "SenderCode": "",
            "ReceiverCode": "",
            "StartDate": "",   # la API ignora esto; filtramos client-side
            "EndDate": "",
            "DocumentTypeId": tipo,
            "Status": "0",
            "IsNextPage": "false",
            "FilterType": "2",
            "blockIndex": "0",
            "RadianStatus": "0",
            "__RequestVerificationToken": self.csrf_token,
        }
        last_err = None
        for intento in range(MAX_RETRIES + 1):
            try:
                r = self.session.post(
                    ENDPOINT_LIST,
                    data=body,
                    headers={"X-Requested-With": "XMLHttpRequest"},
                    timeout=TIMEOUT_LIST,
                )
                if r.status_code == 401 or r.status_code == 403:
                    raise TokenInvalido(
                        f"La sesión DIAN expiró o no tiene permisos (HTTP {r.status_code}). "
                        f"Genera un nuevo Token desde el portal."
                    )
                r.raise_for_status()
                data = r.json()
                return {
                    "data": data.get("data") or data.get("Data") or [],
                    "recordsFiltered": data.get("recordsFiltered", 0),
                }
            except TokenInvalido:
                raise
            except (requests.RequestException, ValueError) as e:
                last_err = e
                if intento < MAX_RETRIES:
                    time.sleep(0.5 * (intento + 1))
                    continue
        raise ErrorDIAN(f"GetDocumentsPageToken falló tras {MAX_RETRIES + 1} intentos: {last_err}")

    # ── Descargar XMLs ────────────────────────────────────────

    def descargar_zip(self, track_id: str) -> bytes:
        """Descarga el ZIP (XML+PDF) de un documento por su trackId."""
        url = f"{ENDPOINT_DOWNLOAD}?trackId={track_id}"
        last_err = None
        for intento in range(MAX_RETRIES + 1):
            try:
                r = self.session.get(url, timeout=TIMEOUT_DOWNLOAD)
                if r.status_code in (401, 403):
                    raise TokenInvalido(
                        f"Sesión DIAN expiró durante descarga (HTTP {r.status_code})."
                    )
                r.raise_for_status()
                if len(r.content) < 200:
                    raise ErrorDIAN(f"Descarga vacía ({len(r.content)} bytes)")
                if r.content[:2] != b"PK":
                    raise ErrorDIAN(f"No es ZIP válido (bytes iniciales: {r.content[:4].hex()})")
                return r.content
            except TokenInvalido:
                raise
            except (requests.RequestException, ErrorDIAN) as e:
                last_err = e
                if intento < MAX_RETRIES:
                    time.sleep(0.5 * (intento + 1))
                    continue
        raise ErrorDIAN(f"Descarga falló para {track_id[:16]}... tras {MAX_RETRIES + 1} intentos: {last_err}")

    def descargar_lote(
        self,
        track_ids: List[str],
        workers: int = 4,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> dict:
        """
        Descarga muchos ZIPs en paralelo.

        Returns:
            {
              'ok':       dict[track_id -> bytes],
              'fallidos': list[{'track_id', 'error'}],
            }
        """
        ok: dict = {}
        fallidos: list = []
        lock = threading.Lock()
        total = len(track_ids)
        completados = 0

        def _uno(tid: str):
            nonlocal completados
            try:
                blob = self.descargar_zip(tid)
                with lock:
                    ok[tid] = blob
            except Exception as e:
                with lock:
                    fallidos.append({"track_id": tid, "error": str(e)})
            with lock:
                completados += 1
                if on_progress:
                    on_progress(completados, total)

        with ThreadPoolExecutor(max_workers=workers) as ex:
            list(ex.map(_uno, track_ids))

        return {"ok": ok, "fallidos": fallidos}


# ── Autenticación ────────────────────────────────────────────

def autenticar(token_url: str, *, timeout: int = TIMEOUT_AUTH) -> SesionDIAN:
    """
    Toma un link Token DIAN y devuelve una SesionDIAN lista para usar.

    El Token URL tiene formato:
        https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=...&rk=NIT&token=UUID

    Levanta TokenInvalido si el link no autentica.
    """
    # Validación básica del URL
    parsed = urlparse(token_url)
    if parsed.netloc != "catalogo-vpfe.dian.gov.co":
        raise TokenInvalido(
            f"El link no es del dominio DIAN esperado (recibido: {parsed.netloc!r})."
        )
    if parsed.path.lower() != "/user/authtoken":
        raise TokenInvalido(
            f"El link no es un Token DIAN (path: {parsed.path!r}). "
            f"Debe ser /User/AuthToken."
        )
    params = parse_qs(parsed.query)
    if "token" not in params or "rk" not in params or "pk" not in params:
        raise TokenInvalido(
            "El link no tiene los parámetros esperados (pk, rk, token)."
        )
    nit_cuenta = params["rk"][0]
    partition_key = params["pk"][0]

    # GET al AuthToken → cookies + CSRF
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    })

    try:
        r = session.get(token_url, allow_redirects=True, timeout=timeout)
    except requests.RequestException as e:
        raise ErrorDIAN(f"No se pudo conectar al portal DIAN: {e}")

    if r.status_code == 200 and ("Iniciar sesi" in r.text or "/User/Login" in r.url):
        raise TokenInvalido(
            "El Token redirigió al login. Probablemente expiró (>1 hora) o nunca fue válido."
        )
    if r.status_code >= 400:
        raise TokenInvalido(
            f"AuthToken devolvió HTTP {r.status_code}. El Token puede estar expirado o ser inválido."
        )

    # Extraer CSRF token
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r.text)
    if not m:
        # Algunos endpoints ponen el token en cookies
        csrf_cookie = session.cookies.get("__RequestVerificationToken")
        if csrf_cookie:
            csrf = csrf_cookie
        else:
            raise TokenInvalido(
                "No se encontró __RequestVerificationToken en la respuesta. "
                "El Token no autenticó correctamente."
            )
    else:
        csrf = m.group(1)

    return SesionDIAN(
        session=session,
        csrf_token=csrf,
        nit_cuenta=nit_cuenta,
        partition_key=partition_key,
    )


# ── Utilidades ───────────────────────────────────────────────

def parsear_fecha_dian_ms(s) -> Optional[int]:
    """
    Convierte '/Date(1774915200000)/' a epoch ms.
    Devuelve None si no parsea.
    """
    if not s:
        return None
    m = re.search(r"/Date\((\d+)\)", str(s))
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def extraer_xml_de_zip_dian(zip_bytes: bytes) -> Optional[str]:
    """
    Cada doc DIAN viene como ZIP con 1 XML + 1 PDF. Extrae el XML como string.
    Devuelve None si no encuentra XML válido.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".xml"):
                    return zf.read(name).decode("utf-8", errors="replace")
    except zipfile.BadZipFile:
        pass
    return None


def extraer_pdf_de_zip_dian(zip_bytes: bytes) -> Optional[bytes]:
    """Extrae el PDF del ZIP DIAN. Devuelve None si no encuentra."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".pdf"):
                    return zf.read(name)
    except zipfile.BadZipFile:
        pass
    return None
