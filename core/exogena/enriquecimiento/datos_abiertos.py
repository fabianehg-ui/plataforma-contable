"""
Enriquecedor Datos Abiertos del Gobierno (datos.gov.co)
=======================================================

Usa el portal oficial de datos abiertos de Colombia. Hay varios datasets
útiles:

  - "Cámara de Comercio - Registro Mercantil" (dataset oficial,
    https://www.datos.gov.co/Comercio-Industria-y-Turismo/...)
  - "Registro Único Tributario" (subconjunto público)
  - "Establecimientos Comerciales por Departamento"

La API de datos.gov.co usa SODA (Socrata Open Data API) v2.1.
Es estable, rápida y gratuita (sin token para uso bajo).

LIMITACIONES:
- Datasets no se actualizan en tiempo real (lag de meses)
- Cobertura incompleta para empresas pequeñas o recientes
- Personas naturales NO están

PRIORIDAD en la cascada: DESPUÉS de RUES, JUNTO o ANTES de Empresite.
"""

from __future__ import annotations
from typing import Optional

try:
    import requests
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

try:
    from .base import Enriquecedor, DatosEnriquecidos, EnriquecedorError
    from .helpers_inferencia import inferir_dpto_municipio_desde_texto
except ImportError:
    from base import Enriquecedor, DatosEnriquecidos, EnriquecedorError
    from helpers_inferencia import inferir_dpto_municipio_desde_texto


# Dataset oficial de Cámaras de Comercio en datos.gov.co.
# Hay varios datasets de RM. Este es uno de los más completos a nivel nacional.
# Soporta filtros por NIT como columna 'nit_de_la_empresa' (string).
DATASET_REGISTRO_MERCANTIL_URL = (
    'https://www.datos.gov.co/resource/qhpu-8ixx.json'  # ejemplo, puede variar
)

# Datos.gov.co búsqueda genérica - búsqueda federada
DATASET_BUSQUEDA_URL = (
    'https://www.datos.gov.co/resource/{dataset}.json'
)

USER_AGENT = (
    'Mozilla/5.0 PlataformaContable/1.0 (DIAN Exógena enricher)'
)


class DatosAbiertosEnriquecedor(Enriquecedor):
    """
    Consulta datos.gov.co a través de la API SODA.

    Estrategia de búsqueda:
      1. Intenta el dataset oficial de Cámaras de Comercio (NIT como filtro)
      2. Si no encuentra, devuelve None y la cascada continúa
    """

    def __init__(self, timeout: int = 12, app_token: Optional[str] = None):
        """
        Args:
            timeout: segundos por request.
            app_token: opcional, token de Socrata para rate limit más alto.
                       Sin token funciona pero limitado a ~1000 req/hora.
        """
        self.timeout = timeout
        self.app_token = app_token

    @property
    def nombre(self) -> str:
        return 'datos_abiertos'

    def disponible(self) -> bool:
        return HAS_DEPS

    def enriquecer(self, nit: str) -> Optional[DatosEnriquecidos]:
        if not self.disponible():
            return None
        if not nit or not str(nit).isdigit():
            return None

        # Estrategia: probar varios datasets conocidos en orden de probabilidad
        datasets_a_probar = [
            # (dataset_id, columna_nit, parser)
            ('qhpu-8ixx', 'nit', self._parsear_registro_mercantil),
            ('5k28-bvhe', 'nit', self._parsear_registro_mercantil),
        ]

        headers = {'User-Agent': USER_AGENT}
        if self.app_token:
            headers['X-App-Token'] = self.app_token

        for dataset_id, columna_nit, parser in datasets_a_probar:
            try:
                url = DATASET_BUSQUEDA_URL.format(dataset=dataset_id)
                params = {columna_nit: str(nit), '$limit': 1}
                resp = requests.get(
                    url, headers=headers, params=params, timeout=self.timeout,
                )
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if not data or not isinstance(data, list):
                    continue
                resultado = parser(nit, data[0])
                if resultado is not None:
                    return resultado
            except (requests.RequestException, ValueError, Exception):
                continue

        return None

    def _parsear_registro_mercantil(self, nit: str, payload: dict) -> Optional[DatosEnriquecidos]:
        """
        Parser de un dataset estilo Registro Mercantil de Cámaras de Comercio.

        Los datasets varían en nombres de columnas. Esta función intenta
        ser flexible:
          - razón social: 'razon_social', 'nombre', 'denominacion'
          - dirección:    'direccion', 'direccion_comercial'
          - municipio:    'municipio', 'ciudad', 'cod_municipio'
          - dpto:         'departamento', 'cod_departamento'
        """
        # Búsqueda flexible de campos
        def get_field(keys):
            for k in keys:
                v = payload.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
            return None

        razon = get_field(['razon_social', 'nombre', 'denominacion',
                          'razon_social_o_nombre'])
        direccion = get_field(['direccion', 'direccion_comercial', 'direccion_notificacion'])
        municipio_txt = get_field(['municipio', 'ciudad', 'nombre_municipio'])
        departamento_txt = get_field(['departamento', 'nombre_departamento'])
        codigo_dpto = get_field(['cod_departamento', 'codigo_departamento'])
        codigo_mun = get_field(['cod_municipio', 'codigo_municipio'])
        ciiu = get_field(['actividad_ciiu', 'ciiu_principal', 'codigo_ciiu'])

        if not razon and not direccion:
            return None

        # Si no hay códigos pero sí hay nombres, intentar inferir
        if (not codigo_dpto or not codigo_mun) and (municipio_txt or departamento_txt):
            inferido = inferir_dpto_municipio_desde_texto(
                municipio_txt or '', departamento_txt or '',
            )
            if inferido:
                codigo_dpto = codigo_dpto or inferido[0]
                codigo_mun = codigo_mun or inferido[1]

        # Normalizar a 2/3 dígitos
        if codigo_dpto:
            codigo_dpto = str(codigo_dpto).zfill(2)[:2]
        if codigo_mun:
            codigo_mun = str(codigo_mun).zfill(3)[-3:]

        return DatosEnriquecidos(
            nit=str(nit),
            fuente='datos_abiertos',
            tipo_persona='juridica',
            estado='activo',
            razon_social=razon[:200] if razon else None,
            direccion=direccion[:200] if direccion else None,
            codigo_dpto=codigo_dpto,
            codigo_municipio=codigo_mun,
            nombre_municipio=municipio_txt,
            actividad_ciiu=str(ciiu)[:4] if ciiu else None,
            confiabilidad=0.7,  # dato oficial, pero a veces desactualizado
            payload_crudo=payload,
        )
