"""
Módulo Nómina — Plataforma Web.

Procesa el Excel mensual de nómina (1 hoja por empleada, 2 desprendibles
quincenales por hoja) y genera el plano contable con:

    - 2 asientos de causación (comprobante 11, documentos 1 y 2)
    - 1 asiento de provisión mensual (comprobante 9, documento = mes)

El maestro de empleados está embebido en el código
(core/data/empleados.json) — el operador NO lo sube.

Reglas contables (Casa UnoTres SAS):
    - IBC = Devengado − Aux Transporte − Incapacidad
    - Base prestaciones = Total Devengado
    - Base vacaciones   = Devengado − Aux Transporte
    - Solo aplican: Pensión 12%, ARL (variable), Caja 4%
    - Empresa exonerada de Salud patronal 8.5%, SENA y ICBF
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
from datetime import date

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from auth.modulos import require_modulo
from core.procesadores.procesador_nomina import (
    procesar_nomina,
    dataframe_a_plano_tsv,
    cargar_empleados_embebido,
    info_empleados_embebido,
    COMPROBANTE_NOMINA,
    COMPROBANTE_PROVISION,
)


# ============================================================
# Configuración de la página
# ============================================================

st.set_page_config(
    page_title="Nómina",
    page_icon="💼",
    layout="wide",
)

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
require_modulo("nomina")
emp = require_rol(["admin", "operador"])


# ============================================================
# Encabezado
# ============================================================

# Usamos st.markdown con HTML para asegurar el render correcto del título
# (st.title a veces interpreta mal los emojis seguidos de texto en la URL del slug).
st.markdown("# 💼 NÓMINA CASA 13")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    f"Procesa el Excel mensual de nómina y genera el plano contable"
)
st.markdown("---")


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:
    st.markdown("### ⚙️ Opciones")
    incluir_enc_excel = st.checkbox(
        "Incluir 'sep=\\t' (compatible Excel)",
        value=True,
        help="Agrega la directiva de separador para que Excel abra el TSV "
             "con las columnas alineadas.",
    )

    st.markdown("---")
    st.markdown("### 📐 Reglas contables")
    st.caption(
        f"""
        **Causación nómina** (comprobante {COMPROBANTE_NOMINA}):
        - Doc 1 = quincena del 15
        - Doc 2 = quincena del 30

        **Provisión mensual** (comprobante {COMPROBANTE_PROVISION}):
        - Documento = número del mes

        **Bases de cálculo:**
        - IBC = Devengado − Aux Tpte − Incapacidad
        - Prestaciones = Devengado total
        - Vacaciones = Devengado − Aux Tpte

        **Aportes patronales:**
        - Pensión 12% del IBC
        - ARL (tarifa por empleada)
        - Caja Compensación 4% del IBC
        - ❌ NO Salud 8.5%, NO SENA, NO ICBF (exonerada)
        """
    )


# ============================================================
# Pestañas
# ============================================================

tab_procesar, tab_empleados = st.tabs([
    "📤 Procesar nómina",
    "👤 Empleadas registradas",
])


# ------------------------------------------------------------
# Pestaña: Procesar
# ------------------------------------------------------------

with tab_procesar:
    st.markdown("### 📤 Subir Excel mensual de nómina")
    st.info(
        "📋 **Formato esperado:** un archivo Excel con UNA hoja por empleada. "
        "Cada hoja debe tener DOS desprendibles apilados verticalmente "
        "(quincena 1 y quincena 2)."
    )

    col_periodo1, col_periodo2 = st.columns(2)
    with col_periodo1:
        hoy = date.today()
        # Por defecto, el mes ANTERIOR al actual
        mes_default = hoy.month - 1 if hoy.month > 1 else 12
        anio_default = hoy.year if hoy.month > 1 else hoy.year - 1
        anio = st.number_input(
            "Año del periodo",
            min_value=2020, max_value=2100,
            value=anio_default, step=1,
        )
    with col_periodo2:
        meses_nombres = [
            "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
        ]
        mes_idx = st.selectbox(
            "Mes del periodo",
            options=list(range(1, 13)),
            format_func=lambda i: f"{i:02d} — {meses_nombres[i - 1]}",
            index=mes_default - 1,
        )

    archivo = st.file_uploader(
        "📎 Subir Excel de nómina (.xls o .xlsx)",
        type=["xls", "xlsx"],
        help="Excel con una hoja por empleada y dos desprendibles por hoja.",
        key="archivo_nomina",
    )

    if archivo is not None:
        st.markdown("---")
        with st.spinner("Procesando nómina..."):
            try:
                df_plano, log, resumen = procesar_nomina(
                    archivo, anio=int(anio), mes=int(mes_idx)
                )
            except Exception as e:
                st.error(f"❌ Error procesando el archivo:\n\n```\n{e}\n```")
                df_plano = None
                log = []
                resumen = {}

        if df_plano is not None and len(df_plano) > 0:
            # Métricas principales
            total_db = int(df_plano[df_plano["TR"] == "1"]["VALOR"].astype(int).sum())
            total_cr = int(df_plano[df_plano["TR"] == "2"]["VALOR"].astype(int).sum())
            cuadra = total_db == total_cr

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Empleados", resumen.get("empleados_procesados", 0))
            with col2:
                st.metric("Líneas plano", len(df_plano))
            with col3:
                st.metric(
                    "Total Db",
                    f"$ {total_db:,}".replace(",", "."),
                )
            with col4:
                st.metric(
                    "Total Cr",
                    f"$ {total_cr:,}".replace(",", "."),
                )

            if cuadra:
                st.success("✅ **Cuadre perfecto Db = Cr** en todos los asientos.")
            else:
                st.error(
                    f"❌ **Descuadre:** Db − Cr = "
                    f"${total_db - total_cr:,}".replace(",", ".")
                )

            # Resumen por empleado
            st.markdown("#### 👤 Resumen por empleada")
            detalle = resumen.get("detalle_empleados", [])
            if detalle:
                df_resumen = pd.DataFrame(detalle)
                df_resumen_formato = df_resumen.copy()
                for col in ("devengado_total", "aux_transporte", "incapacidad",
                            "ibc", "base_prestaciones", "base_vacaciones"):
                    if col in df_resumen_formato.columns:
                        df_resumen_formato[col] = df_resumen_formato[col].apply(
                            lambda v: f"$ {int(v):,}".replace(",", ".")
                        )
                st.dataframe(
                    df_resumen_formato.rename(columns={
                        "cc": "C.C.",
                        "nombre": "Nombre",
                        "tipo": "Tipo",
                        "tasa_arl_pct": "Tasa ARL",
                        "devengado_total": "Devengado total",
                        "aux_transporte": "Aux. Tpte.",
                        "incapacidad": "Incapacidad",
                        "ibc": "IBC",
                        "base_prestaciones": "Base prestac.",
                        "base_vacaciones": "Base vac.",
                    }),
                    use_container_width=True,
                    hide_index=True,
                )

            # Resumen por asiento
            st.markdown("#### 📒 Asientos generados")
            asientos_resumen = []
            for (comp, doc), grupo in df_plano.groupby(["COMPROBANTE", "DOCUMENTO"]):
                db = int(grupo[grupo["TR"] == "1"]["VALOR"].astype(int).sum())
                cr = int(grupo[grupo["TR"] == "2"]["VALOR"].astype(int).sum())
                tipo = "Causación nómina" if comp == COMPROBANTE_NOMINA else "Provisión mensual"
                fecha_asiento = grupo.iloc[0]["FECHA"]
                asientos_resumen.append({
                    "Comprobante": comp,
                    "Documento": doc,
                    "Tipo": tipo,
                    "Fecha": fecha_asiento,
                    "Líneas": len(grupo),
                    "Total Db": f"$ {db:,}".replace(",", "."),
                    "Total Cr": f"$ {cr:,}".replace(",", "."),
                    "Cuadra": "✅" if db == cr else "❌",
                })
            st.dataframe(
                pd.DataFrame(asientos_resumen),
                use_container_width=True,
                hide_index=True,
            )

            # Plano detallado
            with st.expander("📄 Ver plano completo"):
                st.dataframe(df_plano, use_container_width=True, hide_index=True)

            # Log
            with st.expander("📜 Ver log de procesamiento"):
                st.code("\n".join(log), language="text")

            # Descargas
            st.markdown("#### ⬇️ Descargas")

            col_d1, col_d2 = st.columns(2)
            with col_d1:
                tsv_bytes = dataframe_a_plano_tsv(
                    df_plano, incluir_encabezado_excel=incluir_enc_excel
                )
                st.download_button(
                    label="📥 Descargar plano (.txt)",
                    data=tsv_bytes,
                    file_name=f"plano_nomina_{int(anio)}_{int(mes_idx):02d}.txt",
                    mime="text/tab-separated-values",
                    use_container_width=True,
                )
            with col_d2:
                # Excel
                bio = io.BytesIO()
                with pd.ExcelWriter(bio, engine="openpyxl") as writer:
                    df_plano.to_excel(writer, sheet_name="PLANO", index=False)
                st.download_button(
                    label="📥 Descargar plano (.xlsx)",
                    data=bio.getvalue(),
                    file_name=f"plano_nomina_{int(anio)}_{int(mes_idx):02d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

        elif df_plano is not None:
            st.warning("⚠️ El procesamiento no generó líneas en el plano.")
            with st.expander("📜 Ver log"):
                st.code("\n".join(log), language="text")


# ------------------------------------------------------------
# Pestaña: Empleados registrados
# ------------------------------------------------------------

with tab_empleados:
    st.markdown("### 👤 Maestro embebido de empleadas")
    st.caption(
        "Este maestro vive en `core/data/empleados.json` y se carga al iniciar "
        "el módulo. Para añadir, modificar o retirar empleadas, edita el JSON "
        "en GitHub y haz commit. Railway desplegará automáticamente."
    )

    try:
        info = info_empleados_embebido()
    except Exception as e:
        st.error(f"❌ No se pudo cargar el maestro de empleadas: {e}")
        info = None

    if info:
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("Total empleadas", info["total"])
        with col_m2:
            por_tipo_str = " · ".join(
                f"{tipo}: {cnt}" for tipo, cnt in info["por_tipo"].items()
            )
            st.metric("Por tipo", por_tipo_str or "—")

        df_emp = pd.DataFrame(info["empleados"])

        # Re-ordenar columnas para mostrar las relevantes primero
        cols_orden = [
            "cc", "nombre", "tipo", "tasa_arl_pct",
            "fondo_pension", "eps", "arl", "caja",
        ]
        cols_disponibles = [c for c in cols_orden if c in df_emp.columns]
        df_emp = df_emp[cols_disponibles]

        st.dataframe(
            df_emp.rename(columns={
                "cc": "C.C.",
                "nombre": "Nombre",
                "tipo": "Tipo",
                "tasa_arl_pct": "Tasa ARL",
                "fondo_pension": "Fondo Pensión",
                "eps": "EPS",
                "arl": "ARL",
                "caja": "Caja",
            }),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")
        st.info(
            "💡 **Cómo agregar una empleada nueva:**\n\n"
            "1. Abre el archivo `core/data/empleados.json` en GitHub.\n"
            "2. Agrega un nuevo objeto al arreglo `empleados` con: "
            "`cc`, `nombre`, `tipo` (`ADMIN` o `OPERACION`), `tasa_arl`, "
            "`fondo_pension`, `eps`, `arl`, `caja`.\n"
            "3. Commit → Railway despliega automáticamente.\n\n"
            "**Tip:** la tarifa ARL exacta se calcula como "
            "`Aporte Riesgos / IBC Riesgos` de la planilla PILA del mes "
            "correspondiente."
        )
