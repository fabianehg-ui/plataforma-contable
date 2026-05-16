"""
core.f350 — Lógica pura del módulo de Retención en la Fuente (Formulario 350).

Este paquete contiene las funciones que NO dependen de Streamlit ni de Supabase.
Se puede importar desde cualquier lugar (UI web, scripts, tests) y siempre se
comporta igual.

Estructura:
    casillas.py       → mapeo de conceptos F350 a casillas oficiales
    clasificador.py   → clasificación de cuentas PUC a conceptos F350
    parser_contai.py  → parseo de PDFs de Contai (auxiliar y balance)
    autorretencion.py → cálculo de autorretención sobre cuenta 4
    pdf_f350.py       → generación del PDF estilo DIAN
    nit_utils.py      → utilidades de NIT colombiano (DV, tipo persona, formato)

Origen: extraído de BorradorFácil 350 v2.1.5 (programa de escritorio) y
adaptado para trabajar con bytes (Streamlit upload) en vez de rutas de archivo.
"""

from core.f350.nit_utils import (
    inferir_tipo_persona,
    calcular_dv,
    formato_nit,
    formato_moneda,
)
from core.f350.casillas import (
    MAPEO_CASILLAS_F350,
    AUTORRET_CASILLAS_F350,
    obtener_casillas_f350,
)
from core.f350.clasificador import (
    clasificar_concepto_detallado,
    clasificar_concepto_por_cuenta,
    REGLAS_CODIGO_PUC,
    REGLAS_PATRON_COMBINADO,
    REGLAS_PALABRA_CLAVE,
)
from core.f350.parser_contai import (
    parsear_auxiliar_contai,
    parsear_balance_contai,
)
from core.f350.autorretencion import (
    calcular_autorretencion_cuenta_4,
    aproximar_a_miles,
)
from core.f350.pdf_f350 import generar_pdf_formulario_350

__all__ = [
    "inferir_tipo_persona",
    "calcular_dv",
    "formato_nit",
    "formato_moneda",
    "MAPEO_CASILLAS_F350",
    "AUTORRET_CASILLAS_F350",
    "obtener_casillas_f350",
    "clasificar_concepto_detallado",
    "clasificar_concepto_por_cuenta",
    "REGLAS_CODIGO_PUC",
    "REGLAS_PATRON_COMBINADO",
    "REGLAS_PALABRA_CLAVE",
    "parsear_auxiliar_contai",
    "parsear_balance_contai",
    "calcular_autorretencion_cuenta_4",
    "aproximar_a_miles",
    "generar_pdf_formulario_350",
]
