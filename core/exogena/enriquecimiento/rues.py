"""
Enriquecedor que consulta RUES (Registro Único Empresarial - Confecámaras).

Usa el endpoint Elasticsearch del portal nuevo de RUES, que es público
y gratuito. Los datos del registro mercantil son de libre circulación
según la Ley 1727 de 2014 (que creó el RUES) y la Ley 1581 de 2012
art. 3 (clasifica datos comerciales como información pública).

ENDPOINT:
    POST https://elasticprd.rues.org.co/api/ConsultasRUES/BusquedaAvanzadaRM
    Body: {"Razon": null, "Nit": <numero>, "Dpto": null, "Cod_Camara": null, "Matricula": null}

RESPUESTA EJEMPLO:
    {
      "registros": [{
        "tipo_documento": "NIT",
        "nit": "901332568",
        "dv": "4",
        "id_rm": "410000112236",
        "razon_social": "QUANTUX S.A.S",
        "cod_camara": "41",
        "nom_camara": "FLORENCIA PARA EL CAQUETA",
        "matricula": "112236",
        "organizacion_juridica": "SOCIEDADES POR ACCIONES SIMPLIFICADAS SAS",
        "estado_matricula": "ACTIVA",
        "ultimo_ano_renovado": "2024",
        "categoria": "SOCIEDAD ó PERSONA JURIDICA PRINCIPAL ó ESAL"
      }],
      "cant_registros": 1,
      "error": {"code": "0000", "message": "OK"}
    }

LIMITACIONES:
    - Solo devuelve datos básicos: razón social, cámara de comercio, estado.
    - No devuelve dirección, email, teléfono ni representante legal (eso
      requiere el certificado pago).
    - Solo cubre personas jurídicas y comerciantes con matrícula mercantil.
      Personas naturales no comerciantes NO aparecen.
    - El endpoint es de uso interno del portal nuevo y puede cambiar sin aviso.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional

from .base import Enriquecedor, DatosEnriquecidos, EnriquecedorError


class RUESEnriquecedor(Enriquecedor):
    """Consulta RUES vía API Elasticsearch del portal."""

    nombre = 'rues'
    URL = 'https://elasticprd.rues.org.co/api/ConsultasRUES/BusquedaAvanzadaRM'
    URL_FALLBACK = 'https://ruesapi.rues.org.co/api/ConsultasRUES/BusquedaAvanzadaRM'

    def __init__(self, timeout: int = 15, user_agent: Optional[str] = None,
                 habilitado: bool = True):
        """
        Args:
            timeout: timeout HTTP en segundos
            user_agent: User-Agent para identificar el cliente. Recomendado
                        usar el dominio de tu plataforma para no parecer un
                        scraper anónimo.
            habilitado: si False, devuelve None sin hacer request.
        """
        self.timeout = timeout
        self.user_agent = user_agent or (
            'PlataformaContable/1.0 (modulo-exogena; '
            'consulta-rues-publica-ley-1727-2014)'
        )
        self.habilitado = habilitado

    def disponible(self) -> bool:
        return self.habilitado

    def enriquecer(self, nit: str) -> Optional[DatosEnriquecidos]:
        if not self.habilitado:
            return None

        try:
            import requests
        except ImportError:
            raise EnriquecedorError(
                "La librería 'requests' es necesaria para RUESEnriquecedor.",
                fuente='rues', recuperable=False,
            )

        # Limpiar NIT (RUES espera solo dígitos sin DV)
        nit_limpio = ''.join(c for c in str(nit) if c.isdigit())
        if not nit_limpio:
            return None

        # RUES recibe el NIT como integer en el body
        try:
            nit_int = int(nit_limpio)
        except ValueError:
            return None

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
        }
        body = {
            'Razon': None,
            'Nit': nit_int,
            'Dpto': None,
            'Cod_Camara': None,
            'Matricula': None,
        }

        # Intentar primero el endpoint nuevo, fallback al viejo si falla
        for url in (self.URL, self.URL_FALLBACK):
            try:
                resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
                if resp.ok:
                    return self._parsear(nit_limpio, resp.json())
                if resp.status_code in (502, 503, 504):
                    continue  # probar fallback
                if resp.status_code == 429:
                    raise EnriquecedorError(
                        "RUES rate limit", fuente='rues', recuperable=True,
                    )
            except requests.RequestException as e:
                continue  # probar fallback

        # Si ambos fallaron
        return None

    def _parsear(self, nit: str, payload: dict) -> Optional[DatosEnriquecidos]:
        """Convierte la respuesta de RUES en DatosEnriquecidos."""
        registros = payload.get('registros') or []
        if not registros:
            return None

        # Tomar el primer registro (RUES suele devolver uno por NIT)
        r = registros[0]

        # Mapear estado_matricula → estado normalizado
        estado_mat = (r.get('estado_matricula') or '').upper()
        if 'ACTIVA' in estado_mat:
            estado = 'activo'
        elif 'CANCELADA' in estado_mat:
            estado = 'cancelado'
        elif 'SUSPENDIDA' in estado_mat:
            estado = 'suspendido'
        else:
            estado = estado_mat.lower() or None

        # Inferir tipo_persona desde organizacion_juridica
        org = (r.get('organizacion_juridica') or '').upper()
        if any(s in org for s in ('SOCIEDAD', 'EMPRESA', 'FUNDACION', 'ASOCIACION',
                                   'COOPERATIVA', 'SAS', 'LTDA', 'S.A')):
            tipo_persona = 'juridica'
        elif 'PERSONA NATURAL' in org or 'PERSONA NATURAL COMERCIANTE' in org:
            tipo_persona = 'natural'
        else:
            tipo_persona = None

        return DatosEnriquecidos(
            nit=nit,
            fuente='rues',
            fecha_consulta=datetime.utcnow(),
            tipo_persona=tipo_persona,
            estado=estado,
            razon_social=r.get('razon_social'),
            payload_crudo=r,
            confiabilidad=0.85,  # alta para razón social, baja para detalle
            advertencias=[
                'RUES solo devuelve razón social y estado de matrícula. '
                'Para dirección, email, representante legal, consultar Apitude o eInforma.'
            ],
        )
