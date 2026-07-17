"""
Módulo Vacaciones y Liquidaciones Definitivas — Plataforma Web.

Complemento del módulo de Nómina. Sirve para **abrir** (leer) los documentos
de vacaciones o de liquidación definitiva que aparezcan en el movimiento del
mes y ver su desglose contable.

Regla clave (dada por el usuario):
    A las **vacaciones** — cuando NO hacen parte de una liquidación definitiva —
    se les deduce **4% de pensión + 4% de salud** (8%) sobre el valor de las
    vacaciones. En una **liquidación definitiva** las vacaciones NO llevan esa
    deducción.

Flujo:
    1. Subes uno o varios PDF (vacaciones y/o liquidaciones definitivas).
    2. El sistema detecta el tipo, extrae los datos y muestra el desglose.
    3. Para vacaciones calcula el 4% + 4% y verifica contra el documento.
    4. Descargas un Excel con el desglose.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from core.lectores.lector_vacaciones import (
    leer_documento,
    encabezado_vacaciones,
    vacaciones_a_dataframe,
    definitiva_a_dataframe,
    resumen_texto,
    exportar_excel,
    PORC_PENSION,
    PORC_SALUD,
)


# ============================================================
# Configuración
# ============================================================

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin", "operador", "consulta"])


# ============================================================
# Encabezado
# ============================================================

st.title("🏖️ Vacaciones y Liquidaciones Definitivas")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    f"Abre las liquidaciones de vacaciones o definitivas que aparezcan en el "
    f"movimiento del mes y revisa su desglose."
)
st.markdown("---")


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:
    st.markdown("### 🔧 Regla de deducción")
    st.caption(
        f"""
        **Vacaciones (no definitiva):**
        - Pensión **{PORC_PENSION:.0%}**
        - Salud **{PORC_SALUD:.0%}**
        - Total **{(PORC_PENSION + PORC_SALUD):.0%}** sobre el valor de las
          vacaciones.

        **Liquidación definitiva:**
        - Las vacaciones **NO** llevan deducción de seguridad social.
        """
    )
    st.markdown("---")
    st.markdown("### 📋 Formato esperado")
    st.caption(
        "PDF de *LIQUIDACION DE VACACIONES* (con TOTAL VACACIONES y MENOS "
        "SALUD Y PENSION) o de liquidación definitiva de contrato. Si el PDF "
        "es una imagen escaneada, no se puede extraer texto."
    )


# ============================================================
# Subida de archivos
# ============================================================

st.markdown("### 1️⃣ Sube los PDF del mes")

archivos = st.file_uploader(
    "PDF de vacaciones y/o liquidaciones definitivas",
    type=["pdf"],
    accept_multiple_files=True,
    key="files_vacaciones",
    help="Puedes subir varios a la vez.",
)

col_opt1, col_opt2 = st.columns(2)
with col_opt1:
    forzar = st.selectbox(
        "Tipo de documento",
        options=["Detectar automáticamente", "Vacaciones", "Liquidación definitiva"],
        help="Déjalo en automático salvo que la detección falle.",
    )
mapa_forzar = {
    "Detectar automáticamente": None,
    "Vacaciones": "vacaciones",
    "Liquidación definitiva": "definitiva",
}

if not archivos:
    st.info("📂 Sube al menos un PDF para continuar.")
    st.stop()


# ============================================================
# Procesar cada archivo
# ============================================================

st.markdown("### 2️⃣ Documentos leídos")

for archivo in archivos:
    with st.expander(f"📄 {archivo.name}", expanded=len(archivos) == 1):
        try:
            datos = leer_documento(archivo, forzar_tipo=mapa_forzar[forzar])
        except ImportError as e:
            st.error(
                f"❌ **Falta una dependencia:** {e}\n\n"
                "Agrega `pdfplumber>=0.10.0` a `requirements.txt` y reinicia."
            )
            continue
        except Exception as e:
            st.error(f"❌ No se pudo leer el PDF: {e}")
            with st.expander("Ver detalle técnico"):
                st.exception(e)
            continue

        # ---------- VACACIONES ----------
        if datos.get("tipo") == "vacaciones":
            st.success("Tipo detectado: **Liquidación de vacaciones** (aplica 4% + 4%)")

            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Empleado", datos.get("nombre", "—") or "—")
                st.caption(f"Cédula: {datos.get('cedula', '—') or '—'}")
            with c2:
                st.metric("Total días", datos.get("total_dias", 0))
                st.caption(
                    f"{datos.get('dias_habiles', 0)} hábiles + "
                    f"{datos.get('dias_festivos', 0)} festivos"
                )
            with c3:
                st.metric(
                    "Total vacaciones",
                    f"$ {datos.get('total_vacaciones', 0):,}".replace(",", "."),
                )

            st.markdown("**Datos del documento**")
            st.dataframe(
                encabezado_vacaciones(datos),
                use_container_width=True, hide_index=True,
            )

            st.markdown("**Desglose y deducción 4% + 4%**")
            st.dataframe(
                vacaciones_a_dataframe(datos),
                use_container_width=True, hide_index=True,
                column_config={
                    "Valor": st.column_config.NumberColumn(format="$ %d"),
                },
            )

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Pensión 4%", f"$ {datos['deduccion_pension']:,}".replace(",", "."))
            with m2:
                st.metric("Salud 4%", f"$ {datos['deduccion_salud']:,}".replace(",", "."))
            with m3:
                st.metric("Deducción total 8%", f"$ {datos['deduccion_total_calculada']:,}".replace(",", "."))
            with m4:
                st.metric("Neto a pagar", f"$ {datos['neto_calculado']:,}".replace(",", "."))

            # Verificación contra el documento
            if datos.get("deduccion_documento"):
                if datos.get("deduccion_cuadra"):
                    st.success(
                        f"✅ La deducción calculada (4%+4% = "
                        f"$ {datos['deduccion_total_calculada']:,}".replace(",", ".") +
                        f") coincide con la del documento "
                        f"($ {datos['deduccion_documento']:,}".replace(",", ".") + ")."
                    )
                else:
                    st.warning(
                        f"⚠️ La deducción del documento "
                        f"($ {datos['deduccion_documento']:,}".replace(",", ".") +
                        f") difiere de la calculada 4%+4% "
                        f"($ {datos['deduccion_total_calculada']:,}".replace(",", ".") + "). Revísala."
                    )
                neto_doc = datos.get("neto_documento", 0)
                if abs(neto_doc - datos["neto_calculado"]) > 2:
                    st.caption(
                        f"ℹ️ Neto impreso en el documento: "
                        f"$ {neto_doc:,}".replace(",", ".") +
                        f" (diferencia por redondeo del Excel origen)."
                    )

        # ---------- LIQUIDACIÓN DEFINITIVA ----------
        else:
            st.info("Tipo detectado: **Liquidación definitiva** (las vacaciones NO llevan deducción)")

            c1, c2 = st.columns(2)
            with c1:
                st.metric("Empleado", datos.get("nombre", "—") or "—")
                st.caption(f"Cédula: {datos.get('cedula', '—') or '—'}")
            with c2:
                st.caption(f"Ingreso: {datos.get('fecha_ingreso', '—') or '—'}")
                st.caption(f"Retiro: {datos.get('fecha_retiro', '—') or '—'}")

            df_def = definitiva_a_dataframe(datos)
            if len(df_def):
                st.markdown("**Conceptos detectados**")
                st.dataframe(
                    df_def, use_container_width=True, hide_index=True,
                    column_config={"Valor": st.column_config.NumberColumn(format="$ %d")},
                )
            else:
                st.warning(
                    "No se detectaron conceptos con importe automáticamente. "
                    "Revisa el texto crudo abajo."
                )

            if datos.get("valor_vacaciones"):
                st.warning(
                    f"🏖️ Vacaciones dentro de la liquidación: "
                    f"$ {datos['valor_vacaciones']:,}".replace(",", ".") +
                    f" — **sin** deducción de 4% pensión ni 4% salud."
                )

            with st.expander("📄 Ver texto crudo del PDF"):
                st.code(datos.get("texto_crudo", ""), language="text")

        # ---------- Descargas y resumen ----------
        st.markdown("**Resumen**")
        st.code(resumen_texto(datos), language="text")

        nombre_base = archivo.name.rsplit(".", 1)[0]
        st.download_button(
            "📊 Descargar Excel con el desglose",
            data=exportar_excel(datos),
            file_name=f"{nombre_base}_desglose.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_{archivo.name}",
        )


st.markdown("---")
st.caption(
    "ℹ️ Este módulo lee y desglosa los documentos. La generación del plano "
    "contable (con las cuentas del PUC de la empresa) puede añadirse como "
    "siguiente paso una vez confirmadas las cuentas de pasivo y gasto."
)
