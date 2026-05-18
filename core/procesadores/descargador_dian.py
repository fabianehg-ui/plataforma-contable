"""
core/procesadores/descargador_dian.py

Descarga XMLs directamente desde el portal DIAN usando la URL del Token
(sin extensión Chrome). El flujo es server-side: la plataforma recibe la
URL del Token, autentica una sesión con requests y descarga uno por uno
los XMLs por su trackId (la columna "CUFE/CUDE" del Excel del Token, que
en realidad es el `Id` interno de DIAN).

Restricciones reales observadas:
  • La sesión del Token DIAN expira a los ~30 minutos / ~700 documentos.
  • Cuando expira, la próxima descarga falla y hay que renovar el Token
    con un link nuevo del usuario.
  • El portal puede tener rate-limit; se usa un delay configurable.

Por eso este descargador trabaja por BLOQUES de tamaño configurable.
Cada bloque se completa o falla, y al final se reporta el estado para
que la UI pueda pedir renovación del Token al usuario sin perder
progreso.

EXPONE:
    autenticar(token_url) -> Session
    descargar_xml(session, cufe) -> bytes (ZIP)
    descargar_lote(session, cufes, max_docs=700, ...) -> ResultadoDescarga
    juntar_zips(lista_bytes_zip) -> bytes (ZIP plano consolidado)
"""
from __future__ import annotations

import io
import re
import time
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

# ─── Constantes ──────────────────────────────────────────────
BASE_DIAN = "https://catalogo-vpfe.dian.gov.co"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Bloque por defecto: 700 docs antes de renovar token (límite empírico)
DEFAULT_BLOCK_SIZE = 700

# Delay entre descargas para no saturar DIAN (segundos)
DEFAULT_DELAY = 0.15  # ~6-7 docs/seg, conservador

# Timeout por petición individual
DEFAULT_TIMEOUT = 60


# ─── Estructuras de resultado ────────────────────────────────
@dataclass
class ResultadoDescarga:
    """Resumen de un lote de descarga."""
    exitosos: dict[str, bytes] = field(default_factory=dict)   # cufe → bytes_zip
    fallidos: list[tuple[str, str]] = field(default_factory=list)  # [(cufe, razon)]
    motivo_parada: Optional[str] = None  # "completo" | "sesion_expirada" | "limite_bloque" | "error_inesperado"
    procesados: int = 0
    saltados: int = 0
    duracion_seg: float = 0.0

    @property
    def total_exitosos(self) -> int:
        return len(self.exitosos)

    @property
    def total_fallidos(self) -> int:
        return len(self.fallidos)

    def cufes_pendientes(self, lista_original: list[str]) -> list[str]:
        """Cufes que no se procesaron (ni exitosos ni fallidos)."""
        procesados = set(self.exitosos.keys()) | {c for c, _ in self.fallidos}
        return [c for c in lista_original if c not in procesados]


# ─── Autenticación ───────────────────────────────────────────
class SesionExpirada(Exception):
    """Se levanta cuando detectamos que la sesión DIAN venció."""
    pass


def autenticar(token_url: str, timeout: int = 30) -> requests.Session:
    """
    Abre una sesión autenticada en DIAN usando la URL del Token.

    Args:
        token_url: URL completa estilo
                   https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=...&rk=...&token=...

    Returns:
        Una requests.Session lista para hacer peticiones autenticadas.
        El CSRF token se guarda en `session._csrf` para uso interno.

    Levanta:
        ValueError: si la URL no es del dominio DIAN esperado.
        SesionExpirada: si la respuesta no contiene el CSRF (sesión inválida).
        requests.RequestException: errores de red.
    """
    if not token_url or BASE_DIAN not in token_url:
        raise ValueError(
            f"La URL no parece del portal DIAN. Esperaba algo con '{BASE_DIAN}'."
        )

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    r = session.get(token_url, allow_redirects=True, timeout=timeout)
    if r.status_code != 200:
        raise SesionExpirada(
            f"Status {r.status_code} al autenticar. Token posiblemente expirado."
        )

    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r.text)
    if not m:
        raise SesionExpirada(
            "No se encontró el CSRF token en la respuesta. "
            "El Token probablemente expiró o es inválido."
        )

    # Guardar CSRF en la sesión para reutilizarlo
    session._csrf = m.group(1)  # type: ignore[attr-defined]
    return session


def sesion_activa(session: requests.Session) -> bool:
    """
    Heurística rápida: verifica si la sesión todavía responde.
    Hace una petición ligera al listado pidiendo solo 1 documento.
    """
    csrf = getattr(session, "_csrf", None)
    if not csrf:
        return False
    try:
        r = session.post(
            f"{BASE_DIAN}/Document/GetDocumentsPageToken",
            data={
                "draw": "1", "start": "0", "length": "1",
                "DocumentKey": "", "SerieAndNumber": "",
                "SenderCode": "", "ReceiverCode": "",
                "StartDate": "", "EndDate": "",
                "DocumentTypeId": "01", "Status": "0",
                "IsNextPage": "false", "FilterType": "2",
                "blockIndex": "0", "RadianStatus": "0",
                "__RequestVerificationToken": csrf,
            },
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=10,
        )
        return r.status_code == 200 and r.headers.get("Content-Type", "").startswith("application/json")
    except Exception:
        return False


# ─── Descarga de un XML ──────────────────────────────────────
def descargar_xml(
    session: requests.Session,
    cufe: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> bytes:
    """
    Descarga el ZIP de un documento por su trackId/CUFE.

    Args:
        session: sesión autenticada (de `autenticar`).
        cufe: el `Id` de DIAN (lo que el Excel llama "CUFE/CUDE").

    Returns:
        bytes del ZIP descargado.

    Levanta:
        SesionExpirada: si el portal redirige a login.
        ValueError: si la respuesta no es un ZIP válido.
        requests.RequestException: errores de red.
    """
    if not cufe or not cufe.strip():
        raise ValueError("CUFE vacío")

    r = session.get(
        f"{BASE_DIAN}/Document/DownloadZipFiles",
        params={"trackId": cufe.strip()},
        timeout=timeout,
        allow_redirects=False,  # importante: detectar redirects a login
    )

    # Si DIAN nos redirige al login, la sesión murió
    if r.status_code in (301, 302, 303, 307, 308):
        location = r.headers.get("Location", "")
        if "login" in location.lower() or "authtoken" in location.lower():
            raise SesionExpirada(f"DIAN redirigió a login: {location}")
        raise SesionExpirada(f"Redirect inesperado: {r.status_code} → {location}")

    if r.status_code != 200:
        raise ValueError(f"Status {r.status_code} para CUFE {cufe[:20]}...")

    contenido = r.content
    if len(contenido) < 100:
        raise ValueError(f"Respuesta demasiado corta ({len(contenido)} bytes)")

    # Verificar magic bytes de ZIP
    if contenido[:2] != b"PK":
        # Quizá nos devolvió HTML de error / sesión expirada
        snippet = contenido[:200].decode("utf-8", errors="ignore")
        if "login" in snippet.lower() or "<html" in snippet.lower():
            raise SesionExpirada("Respuesta HTML en lugar de ZIP — sesión expirada")
        raise ValueError(f"No es un ZIP válido. Primeros bytes: {contenido[:30]!r}")

    return contenido


# ─── Descarga de un lote completo ────────────────────────────
def descargar_lote(
    session: requests.Session,
    cufes: list[str],
    max_docs: int = DEFAULT_BLOCK_SIZE,
    delay: float = DEFAULT_DELAY,
    timeout: int = DEFAULT_TIMEOUT,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    parar_si_falla: bool = True,
) -> ResultadoDescarga:
    """
    Descarga un lote de XMLs. Para cuando:
      • completa toda la lista
      • alcanza max_docs
      • la sesión expira (SesionExpirada en una descarga)
      • si parar_si_falla=True y hay un error no recuperable

    Args:
        session: sesión autenticada.
        cufes: lista de CUFEs (trackIds) a descargar.
        max_docs: máximo a procesar en este bloque (default 700).
        delay: segundos entre descargas para no saturar.
        timeout: timeout por petición.
        on_progress: callback (procesados, total_lote, mensaje) opcional.
        parar_si_falla: si True, para al primer error de sesión.

    Returns:
        ResultadoDescarga con los exitosos, fallidos y motivo de parada.
    """
    res = ResultadoDescarga()
    inicio = time.time()
    tope = min(len(cufes), max_docs)

    if tope == 0:
        res.motivo_parada = "completo"
        return res

    for i, cufe in enumerate(cufes[:tope]):
        if not cufe or not cufe.strip():
            res.saltados += 1
            continue

        try:
            zip_bytes = descargar_xml(session, cufe, timeout=timeout)
            res.exitosos[cufe] = zip_bytes
            res.procesados += 1
            if on_progress:
                on_progress(i + 1, tope, f"OK {cufe[:20]}...")
        except SesionExpirada as e:
            # Esto es lo más importante: si la sesión murió, paramos limpio
            res.motivo_parada = "sesion_expirada"
            res.fallidos.append((cufe, f"Sesión expirada: {e}"))
            if on_progress:
                on_progress(i + 1, tope, f"⚠️ Sesión expirada en {cufe[:20]}...")
            if parar_si_falla:
                break
        except (ValueError, requests.RequestException) as e:
            res.fallidos.append((cufe, str(e)))
            res.procesados += 1
            if on_progress:
                on_progress(i + 1, tope, f"❌ Error en {cufe[:20]}...: {e}")
            # Para errores aislados (timeout puntual, ZIP corrupto), seguimos

        # Delay entre peticiones
        if delay > 0 and i < tope - 1:
            time.sleep(delay)

    if res.motivo_parada is None:
        if tope == len(cufes):
            res.motivo_parada = "completo"
        else:
            res.motivo_parada = "limite_bloque"

    res.duracion_seg = time.time() - inicio
    return res


# ─── Consolidar ZIPs descargados en uno solo ─────────────────
def juntar_zips(zips_por_cufe: dict[str, bytes]) -> bytes:
    """
    Toma todos los ZIPs descargados y los une en un ZIP plano de XMLs.

    Cada ZIP de DIAN típicamente trae 1 XML adentro (la factura UBL).
    Este consolidador extrae los XMLs y los pone planos en un único ZIP,
    que es el formato que el procesador del repo ya entiende
    (`iter_xmls_de_zip` en procesador_xmls_zip.py).

    Args:
        zips_por_cufe: {cufe: bytes_del_zip_de_dian}

    Returns:
        bytes del ZIP consolidado plano.
    """
    salida = io.BytesIO()
    nombres_usados: set[str] = set()

    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as zout:
        for cufe, zip_bytes in zips_por_cufe.items():
            try:
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zin:
                    for nombre in zin.namelist():
                        if not nombre.lower().endswith(".xml"):
                            continue
                        # Evitar Application Response (acuse) si viene mezclado
                        # con la factura — nos quedamos con el primero "fact-"
                        # o todos si hay varios.
                        xml_bytes = zin.read(nombre)

                        # Nombre único basado en CUFE para evitar choques
                        base_name = nombre.replace("/", "_").replace("\\", "_")
                        nombre_final = f"{cufe[:30]}_{base_name}"
                        suffix = 1
                        while nombre_final in nombres_usados:
                            nombre_final = f"{cufe[:30]}_{suffix}_{base_name}"
                            suffix += 1
                        nombres_usados.add(nombre_final)

                        zout.writestr(nombre_final, xml_bytes)
            except zipfile.BadZipFile:
                # ZIP corrupto, ignoramos esa entrada
                continue

    return salida.getvalue()


# ─── Helper: descargar TODO con renovación interactiva ────────
# (Pensado para uso desde la UI con sesiones de Streamlit, no para
#  scripts batch. La UI maneja la pausa entre bloques.)
def descargar_con_bloques(
    token_url_inicial: str,
    cufes: list[str],
    max_docs_por_bloque: int = DEFAULT_BLOCK_SIZE,
    delay: float = DEFAULT_DELAY,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
    renovar_token_fn: Optional[Callable[[], Optional[str]]] = None,
) -> ResultadoDescarga:
    """
    Versión orquestadora: descarga todos los CUFEs por bloques, renovando
    el Token cuando la sesión expira. Pensado para llamarse una sola vez
    desde un script o test (no para la UI de Streamlit que prefiere
    manejar los bloques manualmente).

    Args:
        token_url_inicial: primer link de Token.
        cufes: lista completa de CUFEs a descargar.
        max_docs_por_bloque: corte por bloque (default 700).
        delay: segundos entre peticiones.
        on_progress: callback de progreso.
        renovar_token_fn: función que pide al usuario un nuevo token URL.
                          Si retorna None, se aborta. Si no se pasa, se
                          aborta al primer bloque que termine.

    Returns:
        ResultadoDescarga consolidado (todos los bloques sumados).
    """
    total = ResultadoDescarga()
    pendientes = list(cufes)
    token_actual = token_url_inicial
    bloque_num = 0

    while pendientes:
        bloque_num += 1
        try:
            session = autenticar(token_actual)
        except SesionExpirada:
            total.motivo_parada = "token_invalido"
            break

        res = descargar_lote(
            session,
            pendientes,
            max_docs=max_docs_por_bloque,
            delay=delay,
            on_progress=on_progress,
            parar_si_falla=True,
        )

        # Acumular
        total.exitosos.update(res.exitosos)
        total.fallidos.extend(res.fallidos)
        total.procesados += res.procesados
        total.saltados += res.saltados
        total.duracion_seg += res.duracion_seg

        # Actualizar pendientes
        pendientes = res.cufes_pendientes(pendientes)

        if not pendientes:
            total.motivo_parada = "completo"
            break

        # ¿Renovar token?
        if renovar_token_fn is None:
            total.motivo_parada = res.motivo_parada
            break

        nuevo_token = renovar_token_fn()
        if not nuevo_token:
            total.motivo_parada = "usuario_cancelo"
            break
        token_actual = nuevo_token

    return total
