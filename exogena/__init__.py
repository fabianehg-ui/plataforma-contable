"""Módulo de Información Exógena DIAN.

Estructura del paquete:
    - clasificador_nits.py        → Clasifica NITs por rangos oficiales DIAN
    - cargador_terceros.py        → Carga maestro de terceros desde Excel
    - cargador_codificacion_nativa.py → Carga reglas del software contable
    - motor_clasificacion.py      → Motor de las 3 capas de mapeo
    - validador_xsd.py            → Validador XML contra XSDs DIAN
    - enriquecimiento/            → Subpaquete: fuentes externas (RUES, Apitude)
    - xsd/                        → 15 XSDs oficiales del prevalidador AG 2025
"""
from pathlib import Path

# Ruta base de los XSDs (para que los tests y el validador la usen)
XSD_DIR = Path(__file__).parent / 'xsd'

__all__ = ['XSD_DIR']
