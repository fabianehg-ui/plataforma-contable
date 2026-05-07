"""
Conciliación Enriquecida — UI Streamlit
========================================

Función pública: render_conciliacion_enriquecida(sb, empresa_id, año_gravable)

Se inyecta dentro del tab "Conciliación" de pages/7_Informacion_Exogena.py.

Muestra:
    1. Resumen ejecutivo (cuántos conceptos cuadrados / con diferencia / pendientes)
    2. Filtros: por formato, por estado de cuadre, por monto
    3. Tabla expandible — un acordeón por (formato, concepto)
       que al abrirse muestra las cuentas que aportan y la diferencia
    4. Botón para exportar a Excel
"""

from __future__ import annotations
import io

import streamlit as st
import pandas as pd

from core.exogena import conciliacion_enriquecida as ce


# ============================================================================
# Punto de entrada
# ============================================================================

def render_conciliacion_enriquecida(
    sb,
    empresa_id: str,
    empresa_nombre: str,
    año_gravable: int = 2025,
):
    """Renderiza el componente completo de conciliación enriquecida."""

    st.markdown("---")
    st.subheader("📊 Conciliación detallada por concepto")
    st.caption(
        "Cada formato/concepto desagregado en sus cuentas componentes, "
        "con saldo del balance vs valor reportado y diferencias explicadas."
    )

    # Botón para construir/refrescar el dictamen
    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        if st.button("🔄 Construir dictamen", key="cce_btn_construir"):
            with st.spinner("Analizando movimientos..."):
                try:
                    dictamen = ce.construir_conciliacion_enriquecida(
                        sb=sb,
                        empresa_id=empresa_id,
                        año_gravable=año_gravable,
                    )
                    st.session_state["cce_dictamen"] = dictamen
                except Exception as e:
                    st.error(f"Error construyendo dictamen: {e}")
                    return

    if "cce_dictamen" not in st.session_state:
        with col_info:
            st.info(
                "Click 'Construir dictamen' para generar el análisis. "
                "Requiere que el motor de clasificación se haya ejecutado primero."
            )
        return

    dictamen = st.session_state["cce_dictamen"]

    # ============================================================
    # Resumen ejecutivo
    # ============================================================
    resumen = ce.dictamen_a_resumen_dict(dictamen)

    st.markdown("### Resumen ejecutivo")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total conceptos", resumen["total_conceptos"])
    col2.metric(
        "✅ Cuadrados",
        resumen["conceptos_cuadrados"],
        delta=f"{resumen['porcentaje_cuadrado']:.0f}%",
    )
    col3.metric(
        "⚠️ Con diferencia explicada",
        resumen["conceptos_con_diferencia_explicada"],
    )
    col4.metric(
        "❌ Pendientes",
        resumen["conceptos_pendientes"],
    )

    # ============================================================
    # Filtros
    # ============================================================
    st.markdown("### Filtros")
    col_f1, col_f2, col_f3 = st.columns(3)

    formatos_disponibles = sorted({b.formato_dian for b in dictamen.bloques})
    with col_f1:
        formato_filtro = st.selectbox(
            "Formato",
            options=["(todos)"] + formatos_disponibles,
            key="cce_filtro_formato",
        )

    with col_f2:
        estado_filtro = st.selectbox(
            "Estado",
            options=[
                "(todos)",
                "✅ Cuadrados",
                "⚠️ Con diferencia explicada",
                "❌ Pendientes",
            ],
            key="cce_filtro_estado",
        )

    with col_f3:
        monto_minimo = st.number_input(
            "Monto mínimo (filtra conceptos pequeños)",
            min_value=0,
            value=0,
            step=100_000,
            key="cce_filtro_monto",
        )

    # Aplicar filtros
    bloques_filtrados = []
    for b in dictamen.bloques:
        if formato_filtro != "(todos)" and b.formato_dian != formato_filtro:
            continue
        if estado_filtro != "(todos)":
            mapping = {
                "✅ Cuadrados": "cuadrado",
                "⚠️ Con diferencia explicada": "diferencia_explicada",
                "❌ Pendientes": "pendiente",
            }
            if b.estado != mapping[estado_filtro]:
                continue
        if abs(b.total_balance) < monto_minimo:
            continue
        bloques_filtrados.append(b)

    st.caption(f"Mostrando {len(bloques_filtrados)} de {len(dictamen.bloques)} bloques")

    # ============================================================
    # Botón de descarga Excel
    # ============================================================
    if bloques_filtrados:
        excel_buf = _generar_excel(dictamen, bloques_filtrados)
        st.download_button(
            "📥 Descargar conciliación detallada (Excel)",
            data=excel_buf,
            file_name=f"conciliacion_detallada_{año_gravable}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="cce_btn_excel",
        )

    # ============================================================
    # Tabla expandible — un expander por (formato, concepto)
    # ============================================================
    if not bloques_filtrados:
        st.info("No hay bloques con los filtros actuales.")
        return

    st.markdown("### Detalle por concepto")

    for bloque in bloques_filtrados:
        # Icono según estado
        icon = {
            "cuadrado": "✅",
            "diferencia_explicada": "⚠️",
            "pendiente": "❌",
            "inconsistente": "🚨",
        }.get(bloque.estado, "❓")

        # Encabezado del expander
        diff_str = (
            f" (dif ${bloque.diferencia:,.0f})"
            if bloque.estado != "cuadrado"
            else ""
        )

        with st.expander(
            f"{icon} **F{bloque.formato_dian} / Concepto {bloque.concepto_dian}** — "
            f"{bloque.descripcion_concepto[:50]} — "
            f"Balance: ${bloque.total_balance:,.0f} → "
            f"Reportado: ${bloque.total_reportado:,.0f}{diff_str}"
        ):
            # Tabla de cuentas
            df = pd.DataFrame([
                {
                    "Estado": "🚫" if c.excluida else "",
                    "Código": c.codigo_cuenta,
                    "Nombre": c.nombre_cuenta,
                    "Capa": c.capa_nombre,
                    "Saldo balance": f"${c.saldo_balance:,.0f}",
                    "Reportado": f"${c.valor_reportado:,.0f}",
                    "Diferencia": (
                        f"${c.diferencia:,.0f}" if c.diferencia != 0 else "—"
                    ),
                    "NITs": c.nits_distintos if c.nits_distintos > 0 else "",
                    "Motivo": c.motivo_diferencia or "",
                }
                for c in bloque.cuentas
            ])

            st.dataframe(df, use_container_width=True, hide_index=True)

            # Fila de totales
            col_t1, col_t2, col_t3 = st.columns(3)
            col_t1.metric("Total balance", f"${bloque.total_balance:,.0f}")
            col_t2.metric("Total reportado", f"${bloque.total_reportado:,.0f}")
            col_t3.metric(
                "Diferencia",
                f"${bloque.diferencia:,.0f}",
                delta=None if bloque.estado == "cuadrado" else "Revisar",
                delta_color="off" if bloque.estado == "cuadrado" else "inverse",
            )

            # Explicaciones
            if bloque.explicaciones:
                st.markdown("**Explicación de diferencias:**")
                for exp in bloque.explicaciones[:5]:
                    st.markdown(exp)
                if len(bloque.explicaciones) > 5:
                    st.caption(
                        f"...y {len(bloque.explicaciones) - 5} explicaciones más "
                        "(ver Excel descargable)"
                    )


# ============================================================================
# Generador de Excel
# ============================================================================

def _generar_excel(dictamen, bloques_filtrados) -> bytes:
    """Genera Excel multi-hoja con el dictamen completo."""
    buf = io.BytesIO()

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Hoja 1: Resumen
        resumen = ce.dictamen_a_resumen_dict(dictamen)
        df_resumen = pd.DataFrame([
            {"Métrica": "Año gravable", "Valor": resumen["año_gravable"]},
            {"Métrica": "Total conceptos", "Valor": resumen["total_conceptos"]},
            {"Métrica": "Cuadrados", "Valor": resumen["conceptos_cuadrados"]},
            {"Métrica": "Con diferencia explicada", "Valor": resumen["conceptos_con_diferencia_explicada"]},
            {"Métrica": "Pendientes", "Valor": resumen["conceptos_pendientes"]},
            {"Métrica": "% Cuadrado", "Valor": f"{resumen['porcentaje_cuadrado']:.1f}%"},
        ])
        df_resumen.to_excel(writer, sheet_name="Resumen", index=False)

        # Hoja 2: Detalle plano (todas las cuentas con su concepto)
        filas = ce.dictamen_a_filas_excel(dictamen)
        df_detalle = pd.DataFrame(filas)
        df_detalle.to_excel(writer, sheet_name="Detalle por concepto", index=False)

        # Hoja 3: Solo conceptos con diferencias (para revisión rápida)
        filas_diff = [
            f for f in filas
            if f["Cuenta"] == "TOTAL CONCEPTO" and f["Diferencia"] != 0
        ]
        if filas_diff:
            df_diff = pd.DataFrame(filas_diff)
            df_diff.to_excel(writer, sheet_name="Conceptos con diferencia", index=False)

    buf.seek(0)
    return buf.getvalue()
