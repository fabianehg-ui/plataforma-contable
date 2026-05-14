"""
Enriquecedor Google Search (último recurso)
============================================

ADVERTENCIA: Este enriquecedor hace scraping de resultados de Google.
Los Términos de Servicio de Google PROHÍBEN explícitamente el scraping
automatizado. Úsalo bajo tu propio riesgo:

  - Posible bloqueo de IP del servidor (Railway puede recibir 429 / captcha)
  - Resultados inconsistentes (Google cambia su HTML frecuentemente)
  - Datos no estructurados (extracción heurística)

ALTERNATIVAS PROFESIONALES:
  - Google Custom Search API (oficial, gratis hasta 100 req/día)
  - SerpAPI / Serper.dev (servicios pagos con scraping legal)
  - Bing Web Search API (microsoft.com/cognitive-services)

USO RECOMENDADO: solo como ÚLTIMO recurso después de RUES, Datos Abiertos
y Empresite. Confiabilidad baja (0.4).
"""

from __future__ import annotations
import re
import time
from typing import Optional
from urllib.parse import quote_plus

try:
    import requests
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

try:
    from .base import Enriquecedor, DatosEnriquecidos
    from .helpers_inferencia import inferir_dpto_municipio_desde_texto
except ImportError:
    from base import Enriquecedor, DatosEnriquecidos
    from helpers_inferencia import inferir_dpto_municipio_desde_texto


# Endpoint genérico de búsqueda. Sustituir por API oficial cuando sea posible.
GOOGLE_SEARCH_URL = 'https://www.google.com/search?q={query}&hl=es&gl=co'

# Endpoint de Bing como fallback (también restringido por TOS)
BING_SEARCH_URL = 'https://www.bing.com/search?q={query}&setlang=es-co'

USER_AGENT_DESKTOP = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


class GoogleEnriquecedor(Enriquecedor):
    """
    Búsqueda de empresa por NIT en Google. Extrae direccion/ciudad de los
    snippets de los primeros resultados.

    NO USAR en producción a gran escala. Para casos puntuales únicamente.
    """

    def __init__(self, timeout: int = 10, rate_limit_seconds: float = 3.0,
                 max_intentos: int = 1):
        self.timeout = timeout
        self.rate_limit_seconds = rate_limit_seconds
        self.max_intentos = max_intentos
        self._ultimo_request = 0.0

    @property
    def nombre(self) -> str:
        return 'google'

    def disponible(self) -> bool:
        return HAS_DEPS

    def enriquecer(self, nit: str) -> Optional[DatosEnriquecidos]:
        if not self.disponible():
            return None
        if not nit or not str(nit).isdigit():
            return None

        # Rate limit estricto (Google bloquea rápido)
        ahora = time.time()
        if ahora - self._ultimo_request < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - (ahora - self._ultimo_request))
        self._ultimo_request = time.time()

        # Query: NIT + Colombia + dirección
        query = f'"{nit}" Colombia direccion empresa'
        url = GOOGLE_SEARCH_URL.format(query=quote_plus(query))

        try:
            resp = requests.get(
                url,
                headers={
                    'User-Agent': USER_AGENT_DESKTOP,
                    'Accept-Language': 'es-CO,es;q=0.9',
                },
                timeout=self.timeout,
                allow_redirects=True,
            )
            # Google a menudo devuelve 200 con página de captcha; no podemos
            # diferenciarlo fácilmente sin parser robusto. Mejor detectar
            # palabras clave en el HTML.
            if resp.status_code != 200:
                return None
            if 'captcha' in resp.text.lower() or 'unusual traffic' in resp.text.lower():
                return None  # rate-limited

            return self._parsear_google(nit, resp.text)

        except (requests.RequestException, Exception):
            return None

    def _parsear_google(self, nit: str, html: str) -> Optional[DatosEnriquecidos]:
        """Extrae info heurística de snippets de Google."""
        # Quitar tags HTML rápido (no usamos BeautifulSoup para reducir deps)
        texto_plano = re.sub(r'<[^>]+>', ' ', html)
        texto_plano = re.sub(r'\s+', ' ', texto_plano)

        # Heurísticas para razón social: patrón típico "ACME SAS NIT 900XXX..."
        razon_match = re.search(
            r'([A-ZÑÁÉÍÓÚ][A-ZÑÁÉÍÓÚ\.\s&]+?(?:S\.?A\.?S?\.?|S\.?A\.?|LTDA\.?|E\.?U\.?))\s*'
            r'(?:NIT|nit|Nit)?\s*\.?\s*' + re.escape(nit),
            texto_plano,
            re.IGNORECASE,
        )
        razon = None
        if razon_match:
            razon = razon_match.group(1).strip()[:200]

        # Heurística para dirección: patrón "Calle/Carrera/Cra N°..."
        dir_match = re.search(
            r'((?:Calle|Carrera|Cra|Cll|Avenida|Av|Diagonal|Dg|Transversal|Tv)\.?\s*'
            r'[0-9]+[A-Z]?\s*(?:bis|sur|norte|este|oeste)?\s*'
            r'(?:[#N°nº]\s*)?[0-9]+\s*-\s*[0-9]+)',
            texto_plano,
            re.IGNORECASE,
        )
        direccion = dir_match.group(1).strip() if dir_match else None

        # Si no encontramos nada útil, abandonar
        if not razon and not direccion:
            return None

        # Inferir dpto/mun
        codigos = inferir_dpto_municipio_desde_texto(texto_plano[:3000])

        return DatosEnriquecidos(
            nit=str(nit),
            fuente='google',
            tipo_persona='juridica',  # asumimos jurídica si llegó hasta acá
            razon_social=razon,
            direccion=direccion,
            codigo_dpto=codigos[0] if codigos else None,
            codigo_municipio=codigos[1] if codigos else None,
            confiabilidad=0.4,  # baja: scraping heurístico
            advertencias=[
                'Datos extraídos de Google search por heurística. '
                'Verificar manualmente antes de usar.'
            ],
        )
