"""
Enriquecedor Empresite Colombia
================================

Scraping del directorio empresarial www.empresite.eleconomistaamerica.co
para personas jurídicas no encontradas en RUES.

LIMITACIONES:
- Sitio NO oficial: estructura HTML puede cambiar sin previo aviso
- Puede aplicar captcha o rate limit si abusamos
- Solo tiene empresas (no personas naturales)
- Datos a veces desactualizados (varios años atrás)

PRIORIDAD en la cascada: DESPUÉS de RUES, ANTES de Apitude (gratis).
"""

from __future__ import annotations
import re
import time
from typing import Optional
from urllib.parse import quote

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

try:
    from .base import Enriquecedor, DatosEnriquecidos, EnriquecedorError
    from .helpers_inferencia import inferir_dpto_municipio_desde_texto
except ImportError:
    from base import Enriquecedor, DatosEnriquecidos, EnriquecedorError
    from helpers_inferencia import inferir_dpto_municipio_desde_texto


URL_BUSQUEDA = 'https://empresite.eleconomistaamerica.co/Actividad/empresa-{nit}.html'
URL_BACKUP = 'https://www.einforma.co/servlet/app/portal/ENTP/prod/ETIQUETA_EMPRESA/nif/{nit}'
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)


class EmpresiteEnriquecedor(Enriquecedor):
    """
    Enriquecedor que hace scraping de Empresite Colombia.

    Es FRÁGIL: si el HTML cambia, deja de funcionar silenciosamente
    devolviendo None. No es un fallo crítico — la cascada continúa
    con el siguiente enriquecedor.
    """

    def __init__(self, timeout: int = 10, user_agent: Optional[str] = None,
                 rate_limit_seconds: float = 1.5):
        """
        Args:
            timeout: segundos máximo por request.
            user_agent: opcional, header User-Agent personalizado.
            rate_limit_seconds: pausa entre requests para no abusar.
        """
        self.timeout = timeout
        self.user_agent = user_agent or USER_AGENT
        self.rate_limit_seconds = rate_limit_seconds
        self._ultimo_request = 0.0

    @property
    def nombre(self) -> str:
        return 'empresite'

    def disponible(self) -> bool:
        return HAS_DEPS

    def enriquecer(self, nit: str) -> Optional[DatosEnriquecidos]:
        if not self.disponible():
            return None
        if not nit or not str(nit).isdigit():
            return None

        # Rate limit simple
        ahora = time.time()
        if ahora - self._ultimo_request < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - (ahora - self._ultimo_request))
        self._ultimo_request = time.time()

        try:
            url = URL_BUSQUEDA.format(nit=nit)
            resp = requests.get(
                url,
                headers={'User-Agent': self.user_agent},
                timeout=self.timeout,
                allow_redirects=True,
            )
            if resp.status_code != 200:
                return None

            return self._parsear(nit, resp.text)
        except (requests.RequestException, Exception):
            # Fallar silenciosamente — la cascada continúa
            return None

    def _parsear(self, nit: str, html: str) -> Optional[DatosEnriquecidos]:
        """Extrae datos del HTML de Empresite. Frágil ante cambios de DOM."""
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            return None

        # Razón social: del título o h1
        razon = None
        h1 = soup.find('h1')
        if h1:
            razon = h1.get_text(strip=True)
        if not razon:
            title = soup.find('title')
            if title:
                # "ACME SAS - Empresite Colombia" → "ACME SAS"
                razon = title.get_text().split(' - ')[0].strip()
        if not razon or 'Empresite' in razon:
            return None  # No se encontró info

        # Dirección y ciudad: buscar en tablas o párrafos con etiquetas conocidas
        direccion = None
        ciudad = None
        actividad_ciiu = None

        # Estrategia: buscar pares "label / valor" típicos del sitio
        for tag in soup.find_all(['p', 'span', 'td', 'div']):
            texto = tag.get_text(' ', strip=True)
            if not texto or len(texto) > 300:
                continue
            texto_low = texto.lower()

            # Dirección
            if 'dirección' in texto_low or 'direccion' in texto_low:
                # Tomar lo que sigue
                partes = re.split(r'[:|\n]', texto, maxsplit=1)
                if len(partes) > 1:
                    candidato = partes[1].strip()
                    if candidato and len(candidato) < 200:
                        direccion = candidato

            # Ciudad / Localidad
            if 'ciudad' in texto_low or 'localidad' in texto_low or 'municipio' in texto_low:
                partes = re.split(r'[:|\n]', texto, maxsplit=1)
                if len(partes) > 1:
                    candidato = partes[1].strip()
                    if candidato and len(candidato) < 80:
                        ciudad = candidato

            # CIIU
            m = re.search(r'\b(\d{4})\b.*ciiu|ciiu.*\b(\d{4})\b', texto_low)
            if m:
                actividad_ciiu = m.group(1) or m.group(2)

        # Si no se encontró nada útil, devolver None
        if not direccion and not ciudad:
            return None

        # Inferir dpto/mun desde ciudad o dirección
        codigos = inferir_dpto_municipio_desde_texto(direccion or '', ciudad or '')

        return DatosEnriquecidos(
            nit=str(nit),
            fuente='empresite',
            tipo_persona='juridica',
            estado='activo',
            razon_social=razon[:200] if razon else None,
            direccion=direccion[:200] if direccion else None,
            codigo_dpto=codigos[0] if codigos else None,
            codigo_municipio=codigos[1] if codigos else None,
            nombre_municipio=ciudad[:80] if ciudad else None,
            actividad_ciiu=actividad_ciiu,
            confiabilidad=0.6,  # menor que RUES, mayor que Google
            payload_crudo={'fuente_url': URL_BUSQUEDA.format(nit=nit)},
            advertencias=['Datos scrapeados; pueden estar desactualizados'],
        )
