"""Sistema de enriquecimiento de terceros desde fuentes externas.

Estrategia: cascada de fuentes ordenadas de gratuita a paga.
Cuando una fuente devuelve datos, las siguientes no se llaman.

Fuentes disponibles:
    - CacheEnriquecedor       → caché en BD (gratis, instantáneo)
    - RUESEnriquecedor        → RUES Confecámaras (gratis, solo jurídicas)
    - DatosAbiertosEnriquecedor → datos.gov.co (gratis, oficial pero lag)
    - EmpresiteEnriquecedor   → scraping eleconomistaamerica.co (gratis, frágil)
    - GoogleEnriquecedor      → Google search scraping (riesgoso, último recurso)
    - ApitudeEnriquecedor     → API paga (cubre todo)

Helpers:
    - inferir_dpto_municipio_desde_texto  → dpto/mun desde texto de dirección
    - obtener_nit_banco                   → NIT del banco según nombre cuenta
    - validar_tercero_completo            → check campos obligatorios por formato
    - aplicar_fallback_empresa            → rellenar con datos de empresa informante
"""
from .base import (
    Enriquecedor,
    DatosEnriquecidos,
    EnriquecedorError,
    EnriquecedorStub,
    EnriquecedorEnCascada,
    CacheEnriquecedor,
    aplicar_enriquecimiento_a_tercero,
)
from .apitude import ApitudeEnriquecedor
from .rues import RUESEnriquecedor
from .empresite import EmpresiteEnriquecedor
from .datos_abiertos import DatosAbiertosEnriquecedor
from .google_search import GoogleEnriquecedor
from .helpers_inferencia import (
    inferir_dpto_municipio_desde_texto,
    obtener_nit_banco,
    validar_tercero_completo,
    aplicar_fallback_empresa,
    auto_dividir_nombre_natural,
    corregir_tipo_documento,
    inferir_tipo_documento_real,
    es_persona_natural,
    FORMATOS_REQUIEREN_UBICACION,
    BANCOS_NITS,
    CIUDADES_CONOCIDAS,
)

__all__ = [
    'Enriquecedor',
    'DatosEnriquecidos',
    'EnriquecedorError',
    'EnriquecedorStub',
    'EnriquecedorEnCascada',
    'CacheEnriquecedor',
    'ApitudeEnriquecedor',
    'RUESEnriquecedor',
    'EmpresiteEnriquecedor',
    'DatosAbiertosEnriquecedor',
    'GoogleEnriquecedor',
    'aplicar_enriquecimiento_a_tercero',
    'inferir_dpto_municipio_desde_texto',
    'obtener_nit_banco',
    'validar_tercero_completo',
    'aplicar_fallback_empresa',
    'auto_dividir_nombre_natural',
    'corregir_tipo_documento',
    'inferir_tipo_documento_real',
    'es_persona_natural',
    'FORMATOS_REQUIEREN_UBICACION',
    'BANCOS_NITS',
    'CIUDADES_CONOCIDAS',
]
