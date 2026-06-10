"""
core/procesadores/descargador_dian.py

Descarga XMLs directamente desde el portal DIAN usando la URL del Token
(sin extensión Chrome). El flujo es server-side: la plataforma recibe la
URL del Token, autentica una sesión con requests y descarga uno por uno
los XMLs por su trackId (la columna "CUFE/CUDE" del Excel del Token, que
en realidad es el `Id` interno de DIAN).

Restricciones reales observadas:
  • La sesión del Token DIAN expira a los ~30 minutos / ~500 documentos (margen seguridad reducido de 700).
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
    descargar_lote(session, cufes, max_docs=500, ...) -> ResultadoDescarga
    juntar_zips(lista_bytes_zip) -> bytes (ZIP plano consolidado)
"""
from __future__ import annotations

import io
import math
import re
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

# ─── Constantes ──────────────────────────────────────────────
BASE_DIAN = "https://catalogo-vpfe.dian.gov.co"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Bloque por defecto: 500 docs antes de renovar token (límite empírico)
DEFAULT_BLOCK_SIZE = 500

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


# Reintentos ante errores transitorios de DIAN (timeout, 5xx, ZIP corrupto)
DEFAULT_REINTENTOS = 3
DEFAULT_BACKOFF = 1.0  # segundos, creciente: 1s, 2s, ...


def descargar_xml_con_reintentos(
    session: requests.Session,
    cufe: str,
    timeout: int = DEFAULT_TIMEOUT,
    reintentos: int = DEFAULT_REINTENTOS,
    backoff: float = DEFAULT_BACKOFF,
) -> bytes:
    """Descarga un XML reintentando ante errores transitorios.

    Reintenta en ValueError / RequestException (timeout puntual, status 5xx,
    respuesta corta o ZIP corrupto). NO reintenta en SesionExpirada: si la
    sesión del Token murió, reintentar no ayuda y hay que renovar el Token.
    """
    ultimo_error: Exception | None = None
    for intento in range(1, max(1, reintentos) + 1):
        try:
            return descargar_xml(session, cufe, timeout=timeout)
        except SesionExpirada:
            raise
        except (ValueError, requests.RequestException) as e:
            ultimo_error = e
            if intento < reintentos:
                time.sleep(backoff * intento)
    # Agotados los reintentos: propagar el último error con contexto
    raise ValueError(f"{ultimo_error} (tras {reintentos} intentos)")
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
        max_docs: máximo a procesar en este bloque (default 500).
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
            zip_bytes = descargar_xml_con_reintentos(session, cufe, timeout=timeout)
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


# ─── Descarga paralela por bloques de 500 ──────────────────────
@dataclass
class ProgresoHilo:
    """Estado en vivo de un hilo de descarga."""
    hilo_id: int
    rango_desde: int       # 1-indexed para mostrar al usuario
    rango_hasta: int
    procesados: int = 0
    exitosos: int = 0
    fallidos: int = 0
    estado: str = "pendiente"   # "pendiente" | "descargando" | "ok" | "sesion_expirada" | "error"
    mensaje: str = ""


def descargar_paralelo_por_bloques(
    token_url: str,
    cufes: list[str],
    tam_bloque: int = DEFAULT_BLOCK_SIZE,
    delay: float = DEFAULT_DELAY,
    timeout: int = DEFAULT_TIMEOUT,
    on_progress: Optional[Callable[[list[ProgresoHilo]], None]] = None,
    parar_todos_si_uno_falla: bool = True,
) -> tuple[ResultadoDescarga, list[ProgresoHilo]]:
    """
    Descarga muchos CUFEs usando N hilos paralelos. El número de hilos se
    calcula automáticamente: ceil(total / tam_bloque).

    Cada hilo:
      - Autentica su propia sesión HTTP con el mismo token_url.
      - Procesa su slice de la lista (no se solapan).
      - Si detecta sesión expirada, marca un flag global y los demás paran.

    Args:
        token_url: URL del Token DIAN (la misma para todos los hilos).
        cufes: lista completa de CUFEs.
        tam_bloque: docs por hilo (default 500).
        delay: pausa entre descargas dentro de cada hilo.
        timeout: timeout por petición.
        on_progress: callback que recibe la lista actual de ProgresoHilo
                     cada vez que un hilo avanza.
        parar_todos_si_uno_falla: si True, sesión expirada en un hilo
                                  detiene a todos los demás.

    Returns:
        (ResultadoDescarga consolidado, lista de ProgresoHilo finales)
    """
    n_total = len(cufes)
    if n_total == 0:
        return ResultadoDescarga(motivo_parada="completo"), []

    n_hilos = math.ceil(n_total / tam_bloque)

    # Distribuir CUFEs en N slices sin solape
    bloques: list[list[str]] = []
    progresos: list[ProgresoHilo] = []
    for i in range(n_hilos):
        ini = i * tam_bloque
        fin = min(ini + tam_bloque, n_total)
        bloques.append(cufes[ini:fin])
        progresos.append(ProgresoHilo(
            hilo_id=i + 1,
            rango_desde=ini + 1,
            rango_hasta=fin,
        ))

    # Flag compartido para abortar
    abortar = threading.Event()
    lock_progreso = threading.Lock()
    inicio = time.time()

    def trabajador(hilo_id: int, cufes_slice: list[str]) -> dict:
        """
        Trabajador de un hilo. Autentica, descarga, actualiza su ProgresoHilo.
        Retorna dict con resultados parciales.
        """
        progreso = progresos[hilo_id - 1]
        resultado = {
            "hilo_id": hilo_id,
            "exitosos": {},        # cufe → zip_bytes
            "fallidos": [],
            "motivo": None,
        }

        # Autenticar sesión propia
        try:
            progreso.estado = "descargando"
            progreso.mensaje = "Autenticando..."
            if on_progress:
                with lock_progreso:
                    on_progress(list(progresos))
            sess = autenticar(token_url, timeout=30)
        except (SesionExpirada, ValueError, requests.RequestException) as e:
            progreso.estado = "error"
            progreso.mensaje = f"Error de autenticación: {e}"
            resultado["motivo"] = "auth_fallida"
            if on_progress:
                with lock_progreso:
                    on_progress(list(progresos))
            if parar_todos_si_uno_falla:
                abortar.set()
            return resultado

        # Descargar uno por uno
        for idx, cufe in enumerate(cufes_slice):
            if abortar.is_set():
                # Otro hilo nos pidió parar
                resultado["motivo"] = "abortado_por_otro_hilo"
                break

            if not cufe or not cufe.strip():
                progreso.procesados += 1
                continue

            try:
                zip_bytes = descargar_xml_con_reintentos(sess, cufe, timeout=timeout)
                resultado["exitosos"][cufe] = zip_bytes
                progreso.exitosos += 1
                progreso.procesados += 1
                progreso.mensaje = f"OK {cufe[:16]}..."
            except SesionExpirada as e:
                progreso.estado = "sesion_expirada"
                progreso.mensaje = f"Sesión expiró tras {progreso.exitosos} docs"
                resultado["fallidos"].append((cufe, f"Sesión expirada: {e}"))
                resultado["motivo"] = "sesion_expirada"
                if parar_todos_si_uno_falla:
                    abortar.set()
                break
            except (ValueError, requests.RequestException) as e:
                resultado["fallidos"].append((cufe, str(e)))
                progreso.fallidos += 1
                progreso.procesados += 1
                progreso.mensaje = f"⚠️ {cufe[:16]}...: {e}"
                # Errores aislados (timeout, ZIP corrupto): seguimos

            # Notificar progreso cada 10 docs para no saturar
            if on_progress and progreso.procesados % 10 == 0:
                with lock_progreso:
                    on_progress(list(progresos))

            if delay > 0:
                time.sleep(delay)

        # Notificación final del hilo
        if progreso.estado == "descargando":
            progreso.estado = "ok"
            progreso.mensaje = f"Listo: {progreso.exitosos} ok, {progreso.fallidos} fallidos"
            if resultado["motivo"] is None:
                resultado["motivo"] = "completo"

        if on_progress:
            with lock_progreso:
                on_progress(list(progresos))

        return resultado

    # ── Ejecutar todos los hilos en paralelo ──
    res = ResultadoDescarga()
    motivos_hilos = []

    with ThreadPoolExecutor(max_workers=n_hilos) as executor:
        futuros = {
            executor.submit(trabajador, prog.hilo_id, bloques[prog.hilo_id - 1]): prog
            for prog in progresos
        }
        for fut in as_completed(futuros):
            try:
                r = fut.result()
                res.exitosos.update(r["exitosos"])
                res.fallidos.extend(r["fallidos"])
                res.procesados += len(r["exitosos"]) + len(r["fallidos"])
                if r["motivo"]:
                    motivos_hilos.append(r["motivo"])
            except Exception as e:
                res.fallidos.append(("__hilo__", f"Hilo crasheó: {e}"))

    # Decidir motivo global de parada
    if "sesion_expirada" in motivos_hilos or "auth_fallida" in motivos_hilos:
        res.motivo_parada = "sesion_expirada"
    elif all(m == "completo" for m in motivos_hilos):
        res.motivo_parada = "completo"
    else:
        res.motivo_parada = "parcial"

    res.duracion_seg = time.time() - inicio
    return res, progresos


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


# ─── Dictamen: comparar lista Excel vs descargados ────────────
def generar_dictamen(
    lista_excel: list[dict],
    cufes_descargados: set[str],
    fallidos: list[tuple[str, str]],
) -> dict:
    """
    Compara la lista de documentos esperados (del Excel del Token) contra
    los que efectivamente se descargaron, produciendo un reporte detallado.

    Args:
        lista_excel: lista de dicts del Excel del Token (con campos
                     cufe, folio, prefijo, tipo_documento, nombre_emisor,
                     total, fecha_emision, ...).
        cufes_descargados: set de CUFEs que sí se bajaron exitosamente.
        fallidos: lista de (cufe, razon) de los que fallaron.

    Returns:
        dict con:
          totales: {total_esperado, descargados, faltantes, fallidos}
          tabla_faltantes: list[dict] de los que no llegaron, con razón
          tabla_descargados: list[dict] de los que sí llegaron
          desglose_tipos: Counter por tipo_documento de los faltantes
    """
    from collections import Counter

    cufes_descargados = set(cufes_descargados)
    razones_fallidos = dict(fallidos)  # cufe → razón

    faltantes = []
    descargados = []

    for item in lista_excel:
        cufe = item.get("cufe", "")
        if not cufe:
            continue
        if cufe in cufes_descargados:
            descargados.append(item)
        else:
            falt = dict(item)
            falt["razon_fallo"] = razones_fallidos.get(
                cufe, "No procesado (sesión interrumpida o pendiente)"
            )
            faltantes.append(falt)

    total_esperado = len(lista_excel)
    n_desc = len(descargados)
    n_falt = len(faltantes)
    n_fallidos = len(fallidos)

    # Sumas de valores para dictamen económico
    sum_esperado = sum(float(it.get("total", 0) or 0) for it in lista_excel)
    sum_descargado = sum(float(it.get("total", 0) or 0) for it in descargados)
    sum_faltante = sum(float(it.get("total", 0) or 0) for it in faltantes)

    desglose_tipos_faltantes = Counter(it.get("tipo_documento", "?") for it in faltantes)

    return {
        "totales": {
            "total_esperado":  total_esperado,
            "descargados":     n_desc,
            "faltantes":       n_falt,
            "fallidos":        n_fallidos,
            "pct_completado":  (n_desc / total_esperado * 100) if total_esperado else 0,
            "sum_esperado":    sum_esperado,
            "sum_descargado":  sum_descargado,
            "sum_faltante":    sum_faltante,
        },
        "tabla_faltantes":   faltantes,
        "tabla_descargados": descargados,
        "desglose_tipos_faltantes": dict(desglose_tipos_faltantes),
    }


# ─── Controlador background + polling para progreso en vivo ──
class DescargaParalelaController:
    """
    Lanza la descarga paralela en background y permite hacer polling
    desde el hilo principal para mostrar progreso en vivo (compatible
    con Streamlit, que no puede recibir llamadas st.* desde workers).

    Uso típico desde Streamlit:
        ctrl = iniciar_descarga_paralela(token_url, cufes)
        slot = st.empty()
        while ctrl.esta_corriendo():
            with slot.container():
                for p in ctrl.obtener_progreso():
                    st.progress(p.procesados / total_hilo, text=...)
            time.sleep(0.5)
        res, progresos_final = ctrl.esperar_resultado()
    """
    def __init__(
        self,
        token_url: str,
        cufes: list[str],
        tam_bloque: int = DEFAULT_BLOCK_SIZE,
        delay: float = DEFAULT_DELAY,
        timeout: int = DEFAULT_TIMEOUT,
        parar_todos_si_uno_falla: bool = True,
    ):
        self.token_url = token_url
        self.cufes = cufes
        self.tam_bloque = tam_bloque
        self.delay = delay
        self.timeout = timeout
        self.parar_todos_si_uno_falla = parar_todos_si_uno_falla

        # Estado interno
        self._progresos: list[ProgresoHilo] = []
        self._lock = threading.Lock()
        self._resultado_final: Optional[ResultadoDescarga] = None
        self._hilo_orquestador: Optional[threading.Thread] = None
        self._terminado = threading.Event()

    def obtener_progreso(self) -> list[ProgresoHilo]:
        """Retorna snapshot (copia) del progreso actual de todos los hilos."""
        with self._lock:
            # Copia superficial — los ProgresoHilo son dataclasses simples
            return [
                ProgresoHilo(
                    hilo_id=p.hilo_id,
                    rango_desde=p.rango_desde,
                    rango_hasta=p.rango_hasta,
                    procesados=p.procesados,
                    exitosos=p.exitosos,
                    fallidos=p.fallidos,
                    estado=p.estado,
                    mensaje=p.mensaje,
                )
                for p in self._progresos
            ]

    def esta_corriendo(self) -> bool:
        """True mientras la descarga sigue activa."""
        return not self._terminado.is_set()

    def iniciar(self):
        """Arranca la descarga en background. Retorna inmediato."""
        if self._hilo_orquestador is not None:
            raise RuntimeError("Ya se inició esta descarga")
        self._hilo_orquestador = threading.Thread(
            target=self._ejecutar,
            daemon=True,
        )
        self._hilo_orquestador.start()

    def esperar_resultado(
        self, timeout: Optional[float] = None
    ) -> tuple[ResultadoDescarga, list[ProgresoHilo]]:
        """
        Bloquea hasta que termine la descarga (o pasa el timeout).
        Retorna (ResultadoDescarga, lista de ProgresoHilo final).
        """
        self._terminado.wait(timeout=timeout)
        if self._resultado_final is None:
            # Aún no terminó (timeout)
            return ResultadoDescarga(motivo_parada="aun_corriendo"), self.obtener_progreso()
        return self._resultado_final, self.obtener_progreso()

    def _ejecutar(self):
        """Orquesta los workers en threads y consolida el resultado."""
        try:
            # Callback que actualiza nuestro estado interno (thread-safe)
            def _on_prog(progresos):
                with self._lock:
                    # Copia los objetos pasados al estado interno
                    self._progresos = [
                        ProgresoHilo(
                            hilo_id=p.hilo_id,
                            rango_desde=p.rango_desde,
                            rango_hasta=p.rango_hasta,
                            procesados=p.procesados,
                            exitosos=p.exitosos,
                            fallidos=p.fallidos,
                            estado=p.estado,
                            mensaje=p.mensaje,
                        )
                        for p in progresos
                    ]

            res, progresos_final = descargar_paralelo_por_bloques(
                self.token_url,
                self.cufes,
                tam_bloque=self.tam_bloque,
                delay=self.delay,
                timeout=self.timeout,
                on_progress=_on_prog,
                parar_todos_si_uno_falla=self.parar_todos_si_uno_falla,
            )
            self._resultado_final = res
            with self._lock:
                self._progresos = progresos_final
        except Exception as e:
            # Si falla algo grave, marcar resultado de error y dejar trace
            self._resultado_final = ResultadoDescarga(
                motivo_parada=f"error_orquestador: {type(e).__name__}: {e}"
            )
        finally:
            self._terminado.set()


def iniciar_descarga_paralela(
    token_url: str,
    cufes: list[str],
    tam_bloque: int = DEFAULT_BLOCK_SIZE,
    delay: float = DEFAULT_DELAY,
    timeout: int = DEFAULT_TIMEOUT,
) -> DescargaParalelaController:
    """Helper: crea el controlador y arranca la descarga. Retorna inmediato."""
    ctrl = DescargaParalelaController(
        token_url=token_url,
        cufes=cufes,
        tam_bloque=tam_bloque,
        delay=delay,
        timeout=timeout,
    )
    ctrl.iniciar()
    return ctrl


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
        max_docs_por_bloque: corte por bloque (default 500).
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
