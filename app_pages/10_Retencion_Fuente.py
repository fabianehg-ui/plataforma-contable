"""
10_Retencion_Fuente.py — Módulo de Retención en la Fuente (Formulario 350).

Estado actual: módulo en construcción.
  - Las tablas en Supabase ya están creadas (db/migrations/011_*.sql).
  - Las próximas sesiones van a agregar:
      * Configuración por empresa (CIIU, autorretenedor, etc.)
      * Carga de PDFs (auxiliar de retefuente + balance de prueba)
      * Procesamiento y clasificación de movimientos
      * Generación del Formulario 350 estilo DIAN

Cuando habilites este módulo a una empresa desde Configuración → Módulos,
el contador asignado a esa empresa lo verá en su menú lateral.
"""

import streamlit as st


# =============================================================================
# CONFIGURACIÓN DE PÁGINA
# =============================================================================

st.set_page_config(
    page_title="Retención en la Fuente — F350",
    page_icon="📋",
    layout="wide",
)


# =============================================================================
# CONTENIDO
# =============================================================================

st.title("📋 Retención en la Fuente — Formulario 350")
st.caption("Generación del borrador del F350 a partir de auxiliar y balance de Contai")

# Aviso normativo importante
st.warning(
    "**Aviso normativo:** El Consejo de Estado suspendió provisionalmente "
    "los artículos 2 al 8 del Decreto 0572 de 2025 mediante auto del 7 de mayo "
    "de 2026. Desde el 8 de mayo de 2026 aplican las tarifas y bases de los "
    "Decretos 0261/2023 y 0242/2024 (DIAN Comunicado 070 del 08/05/2026)."
)

st.divider()

# ---------------------------------------------------------------------------
# Estado de la migración
# ---------------------------------------------------------------------------

st.info(
    "🚧 **Módulo en construcción.** El flujo completo del F350 se está "
    "integrando paso a paso a la plataforma. Cuando esté listo, podrás "
    "generar declaraciones directamente desde aquí, sin instalar nada."
)

st.subheader("Lo que tendrá este módulo")

st.markdown(
    """
    - **Configuración por empresa** — CIIU principal, si es autorretenedor,
      si tiene exoneración del Art. 114-1, historial de cambios de CIIU.
    - **Carga de PDFs por web** — sube directamente desde el navegador el
      auxiliar de retefuente y el balance de prueba de Contai.
    - **Clasificación automática** — cada movimiento se asigna al concepto
      F350 correcto usando código PUC + patrones por palabras clave.
    - **Cálculo de autorretención** — sobre la cuenta 4 según la tarifa
      del CIIU vigente en la fecha de la declaración.
    - **Generación del Formulario 350** — PDF con marca de agua "BORRADOR"
      listo para verificar contra Muisca y firmar con IFE.
    - **Historial de declaraciones** — todas guardadas por empresa para
      tus papeles de trabajo.
    """
)

st.divider()

st.subheader("Estado por etapa")

st.markdown(
    """
    | Etapa | Estado |
    |---|---|
    | Tablas en Supabase | ✅ Creadas |
    | Catálogo CIIU con tarifas vigentes | ⏳ Por cargar |
    | CRUD de configuración por empresa | ⏳ Por hacer |
    | Carga de PDFs por web | ⏳ Por hacer |
    | Procesamiento y clasificación | ⏳ Por hacer |
    | Generación del F350 PDF | ⏳ Por hacer |
    | Historial de declaraciones | ⏳ Por hacer |
    """
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 📋 Módulo F350")
    st.caption("Módulo en construcción.")
