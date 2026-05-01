"""
Componentes UI compartidos entre páginas tributarias.

Provee:
    - render_pagina_tributaria(): cabecera estándar para módulos tributarios
    - render_proximamente(): placeholder para funcionalidades en desarrollo
"""
import streamlit as st


def render_pagina_tributaria(
    titulo: str,
    descripcion: str,
    icono: str = "📊",
):
    """Renderiza la cabecera estándar de un módulo tributario."""
    st.title(f"{icono} {titulo}")
    st.markdown(f"_{descripcion}_")
    st.markdown("---")


def render_proximamente(
    titulo: str,
    descripcion: str,
    fases: list[str] | None = None,
    relacionados: list[tuple[str, str]] | None = None,
):
    """Renderiza un bloque informativo elegante para funcionalidad en desarrollo.

    Args:
        titulo: Título de la sección en desarrollo
        descripcion: Texto explicativo
        fases: Lista de fases o pasos planificados
        relacionados: Lista de (nombre, descripción) de módulos relacionados
    """
    st.info(f"### 🚧 {titulo}\n\n{descripcion}")

    if fases:
        st.markdown("#### 📋 Plan de implementación")
        for i, fase in enumerate(fases, 1):
            st.markdown(f"**Fase {i}** — {fase}")

    if relacionados:
        st.markdown("#### 🔗 Módulos relacionados")
        for nombre, desc in relacionados:
            st.markdown(f"- **{nombre}** — {desc}")
