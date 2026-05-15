"""
10_Retencion_Fuente.py — Módulo de Retención en la Fuente (Formulario 350).

Estado actual (sesión 1 de migración):
  - Esta página muestra la descarga de la versión de escritorio
    (BorradorFácil 350 v2.1.5) mientras se completa la migración a web.
  - Las tablas en Supabase ya están creadas (db/migrations/011_*.sql).
  - Las próximas sesiones reemplazarán el contenido de esta página con
    el flujo completo: CRUD de configuración, carga de PDFs, procesamiento
    y generación del F350.

Cuando habilites este módulo a una empresa desde Configuración → Módulos,
el contador asignado a esa empresa lo verá en su menú lateral.
"""

import streamlit as st
from pathlib import Path

# =============================================================================
# CONFIGURACIÓN DE PÁGINA
# =============================================================================

st.set_page_config(
    page_title="Retención en la Fuente — F350",
    page_icon="📋",
    layout="wide",
)


# =============================================================================
# VERIFICACIÓN DE ACCESO
# =============================================================================
# NOTA: este bloque asume que tu app ya hace login con Supabase y deja
# el usuario en st.session_state. Si tu mecanismo es diferente, ajusta
# las llamadas para que coincidan con el de tus otros módulos.

# Ejemplo genérico — adapta a como lo manejas en otras páginas:
# if "usuario" not in st.session_state:
#     st.warning("Debes iniciar sesión.")
#     st.stop()
#
# if "empresa_seleccionada" not in st.session_state:
#     st.warning("Selecciona una empresa desde Configuración primero.")
#     st.stop()


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
    "Decretos 0261/2023 y 0242/2024 (DIAN Comunicado 070 del 08/05/2026). "
    "La herramienta de escritorio adjunta todavía usa las tarifas del "
    "Dec. 0572. Verifica las tarifas antes de presentar."
)

st.divider()

# ---------------------------------------------------------------------------
# Estado actual: descarga de la versión de escritorio
# ---------------------------------------------------------------------------

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("🖥️ Versión de escritorio disponible")
    st.markdown(
        """
        Mientras se completa la migración web, puedes usar la versión
        de escritorio del programa. Esta versión:

        - Lee automáticamente los PDFs del **auxiliar de retefuente** y
          **balance de prueba** de Contai.
        - Clasifica cada movimiento al concepto correcto del F350
          usando código PUC + reglas por palabras clave.
        - Calcula la autorretención sobre la cuenta 4 según la tarifa
          del CIIU configurado.
        - Genera un PDF tipo DIAN con marca de agua "BORRADOR" listo
          para verificar contra Muisca.
        - Funciona sin internet ni conexión a la plataforma web.

        **Requisitos:** Windows + Python 3.12 (o el `.exe` ya compilado).
        """
    )

with col2:
    st.subheader("⬇️ Descargar")

    # Ruta al zip dentro del repo. Ajusta si lo guardas en otro sitio.
    ruta_zip = Path(__file__).parent.parent / "descargables" / "borrador_facil_350" / "BorradorFacil350_v2.1.5.zip"

    if ruta_zip.exists():
        with open(ruta_zip, "rb") as f:
            datos = f.read()
        st.download_button(
            label="BorradorFácil 350 v2.1.5",
            data=datos,
            file_name="BorradorFacil350_v2.1.5.zip",
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )
        st.caption(f"Tamaño: {len(datos) / 1024 / 1024:.1f} MB")
    else:
        st.info(
            "El archivo de descarga aún no se ha subido al repositorio. "
            "Sube el zip a `descargables/borrador_facil_350/` para "
            "habilitar este botón."
        )

st.divider()

# ---------------------------------------------------------------------------
# Estado de la migración
# ---------------------------------------------------------------------------

st.subheader("🚧 Estado de la migración web")

st.markdown(
    """
    El módulo F350 se está integrando paso a paso a la plataforma web.
    Cuando esté completo, podrás generar declaraciones directamente
    desde el navegador, sin instalar nada, y los datos quedarán
    guardados por empresa en la plataforma.

    | Etapa | Estado |
    |---|---|
    | Tablas en Supabase | ✅ Creadas |
    | Catálogo CIIU compartido | ⏳ Por cargar tarifas vigentes |
    | CRUD de configuración por empresa | ⏳ Por hacer |
    | Carga de PDFs por web | ⏳ Por hacer |
    | Procesamiento y clasificación | ⏳ Por hacer |
    | Generación del F350 PDF | ⏳ Por hacer |
    | Historial de declaraciones | ⏳ Por hacer |

    Mientras tanto, usa la versión de escritorio para tus declaraciones
    de cada mes.
    """
)

st.divider()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### 📋 Módulo F350")
    st.caption("Versión web en construcción.")

    st.markdown("---")
    st.markdown("### 📚 Documentación")
    st.caption(
        "Una vez descargues el zip, revisa el README incluido para "
        "instrucciones de instalación y uso del programa."
    )

    st.markdown("---")
    st.markdown("### 💬 Soporte")
    st.caption("¿Encontraste un error o tienes una sugerencia? Escríbeme.")


# =============================================================================
# FIN — Las próximas sesiones reemplazarán todo lo de arriba con el flujo
# completo: selección de empresa, configuración, carga de PDFs, procesamiento,
# generación de F350 y exportación.
# =============================================================================
