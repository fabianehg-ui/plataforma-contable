"""Sistema de enriquecimiento de terceros desde fuentes externas.

Estrategia: cascada de fuentes ordenadas de gratuita a paga.
Cuando una fuente devuelve datos, las siguientes no se llaman.

Fuentes disponibles:
    - CacheEnriquecedor   → caché en BD (gratis, instantáneo)
    - RUESEnriquecedor    → RUES Confecámaras (gratis, solo jurídicas)
    - ApitudeEnriquecedor → API paga (cubre todo)

Exporta:
    - Enriquecedor (interfaz base)
    - DatosEnriquecidos (resultado tipado)
    - EnriquecedorError
    - EnriquecedorStub (no hace nada, útil cuando no hay credenciales)
    - EnriquecedorEnCascada (compone varios)
    - CacheEnriquecedor
    - ApitudeEnriquecedor
    - RUESEnriquecedor
    - aplicar_enriquecimiento_a_tercero (helper)
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

__all__ = [
    'Enriquecedor',
    'DatosEnriquecidos',
    'EnriquecedorError',
    'EnriquecedorStub',
    'EnriquecedorEnCascada',
    'CacheEnriquecedor',
    'ApitudeEnriquecedor',
    'RUESEnriquecedor',
    'aplicar_enriquecimiento_a_tercero',
]
