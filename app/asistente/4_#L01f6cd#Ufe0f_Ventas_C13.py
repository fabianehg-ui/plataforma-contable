"""
Módulo Ventas Casa 13 — Plataforma Web.

Procesa el archivo RadGridExport.xlsx exportado del sistema de facturación
electrónica (Siigo) y genera el plano contable con MÚLTIPLES comprobantes
según el prefijo del documento.

Mapeo de prefijos a comprobantes:
    PVFE...   → COMP 19  (Venta POS, contado, NIT genérico)
    GBF...    → COMP 5   (Venta GBF, contado, NIT genérico)
    FE...     → COMP 4   (Venta a empresa, crédito, NIT real)
    DV4xxxx   → COMP 6   (NC de PVFE)
    DV3xxxx   → COMP 15  (NC de GBF)
    DW...     → COMP 16  (NC con IVA en 24080101)
    NCA...    → COMP 21  (NC misceláneas — vienen del archivo Documentos)
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
from core.procesadores.procesador_ventas_c13 import (
    procesar_ventas_c13,
    dataframe_a_plano_tsv,
    MAPEO_PREFIJO_COMPROBANTE,
)


# ============================================================
# Configuración de la página
# ============================================================

st.set_page_config(
    page_title="Ventas Casa 13",
    page_icon="🛍️",
    layout="wide",
)

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
require_modulo("ventas_c13")
emp = require_rol(["admin", "operador"])


# ============================================================
# Encabezado
# ============================================================

st.markdown("# 🛍️ VENTAS CASA 13")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    f"Procesa el archivo de facturación electrónica (Siigo) y genera el plano contable"
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
    st.markdown("### 📐 Mapeo de comprobantes")
    st.caption(
        """
        | Prefijo | Comp | Tipo |
        |---|---|---|
        | PVFE | **19** | Venta POS Siigo (contado) |
        | GBF | **5** | Venta GBF (contado) |
        | FE | **4** | Venta a empresa (crédito) |
        | DV4 | **6** | NC de PVFE |
        | DV3 | **15** | NC de GBF |
        | DW | **16** | NC con IVA generado |
        | NCA | **21** | NC misceláneas |
        """
    )

    st.markdown("---")
    st.markdown("### 🔧 Reglas")
    st.caption(
        """
        - **Anuladas (A=True)** se filtran automáticamente.
        - **PVFE/GBF**: contrapartida Db **11050500** (Caja).
        - **FE**: contrapartida Db **130506** (Clientes) + retenciones automáticas
          (Arrendamientos 3.5%, Comisiones 11%).
        - **NC**: contrapartida Cr **11050500** o **130506** según el caso.
        - **NCA** vienen del archivo **Documentos__3_** (no del RadGrid).
        """
    )


# ============================================================
# Pestañas
# ============================================================

tab_procesar, tab_info = st.tabs([
    "📤 Procesar facturación",
    "ℹ️ Información del módulo",
])


# ------------------------------------------------------------
# Pestaña: Procesar
# ------------------------------------------------------------

with tab_procesar:
    st.markdown("### 📤 Subir archivos de facturación")

    st.info(
        "📋 **Formatos esperados:**\n\n"
        "1. **RadGridExport** (obligatorio): archivo principal con todas las líneas "
        "contables del mes (ventas y notas crédito tipo PVFE, GBF, FE, DV, DW).\n\n"
        "2. **Documentos** (opcional pero recomendado): archivo con la cabecera "
        "de las notas crédito. Se usa para:\n"
        "   - Construir asientos NCA (que NO vienen en RadGrid).\n"
        "   - Llenar DOC REFERENCIA con la factura asociada de cada NC."
    )

    col_a, col_b = st.columns(2)

    with col_a:
        archivo_radgrid = st.file_uploader(
            "📎 RadGridExport.xlsx (obligatorio)",
            type=["xlsx", "xls"],
            help="Archivo principal con las líneas contables.",
            key="archivo_radgrid",
        )

    with col_b:
        archivo_notas = st.file_uploader(
            "📎 Documentos.xlsx (opcional pero recomendado)",
            type=["xlsx", "xls"],
            help="Archivo con cabecera de notas crédito. Necesario para "
                 "procesar NCA y enriquecer DOC REFERENCIA.",
            key="archivo_notas",
        )

    if archivo_radgrid is not None:
        st.markdown("---")
        with st.spinner("Procesando facturación..."):
            try:
                df_plano, log, resumen = procesar_ventas_c13(
                    archivo_radgrid,
                    archivo_notas=archivo_notas,
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
            descuadres = resumen.get("descuadres", 0)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Documentos", resumen.get("total_documentos", 0))
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

            if cuadra and descuadres == 0:
                st.success("✅ **Cuadre perfecto Db = Cr** en todos los documentos.")
            elif cuadra:
                st.warning(f"⚠️ Cuadre total OK pero hay {descuadres} documentos individuales con descuadres pequeños.")
            else:
                st.error(
                    f"❌ **Descuadre:** Db − Cr = "
                    f"${total_db - total_cr:,}".replace(",", ".")
                )

            # Resumen por comprobante
            st.markdown("#### 📒 Asientos por comprobante")
            asientos = []
            for comp in sorted(df_plano["COMPROBANTE"].unique()):
                sub = df_plano[df_plano["COMPROBANTE"] == comp]
                db = int(sub[sub["TR"] == "1"]["VALOR"].astype(int).sum())
                cr = int(sub[sub["TR"] == "2"]["VALOR"].astype(int).sum())
                # Buscar descripción del comprobante
                desc = ""
                for prefijo, c, _, descripcion in MAPEO_PREFIJO_COMPROBANTE:
                    if c == comp:
                        desc = descripcion
                        break
                asientos.append({
                    "Comprobante": comp,
                    "Tipo": desc,
                    "Documentos": sub["DOCUMENTO"].nunique(),
                    "Líneas": len(sub),
                    "Total Db": f"$ {db:,}".replace(",", "."),
                    "Total Cr": f"$ {cr:,}".replace(",", "."),
                    "Cuadra": "✅" if db == cr else "❌",
                })
            st.dataframe(
                pd.DataFrame(asientos),
                use_container_width=True,
                hide_index=True,
            )

            # Plano completo
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
                    file_name=f"plano_ventas_c13.txt",
                    mime="text/tab-separated-values",
                    use_container_width=True,
                )
            with col_d2:
                bio = io.BytesIO()
                with pd.ExcelWriter(bio, engine="openpyxl") as writer:
                    df_plano.to_excel(writer, sheet_name="PLANO", index=False)
                st.download_button(
                    label="📥 Descargar plano (.xlsx)",
                    data=bio.getvalue(),
                    file_name=f"plano_ventas_c13.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

        elif df_plano is not None:
            st.warning("⚠️ El procesamiento no generó líneas en el plano.")
            with st.expander("📜 Ver log"):
                st.code("\n".join(log), language="text")


# ------------------------------------------------------------
# Pestaña: Información del módulo
# ------------------------------------------------------------

with tab_info:
    st.markdown("### ℹ️ Cómo funciona este módulo")

    st.markdown("""
    Este módulo procesa la facturación electrónica de Casa 13 (sistema Siigo)
    y genera un plano contable con varios comprobantes según el prefijo del
    documento.

    #### 📦 Archivos necesarios

    1. **`RadGridExport.xlsx`** (obligatorio): exportación principal del sistema
       de facturación con TODAS las líneas contables del mes.
    2. **`Documentos.xlsx`** (recomendado): exportación complementaria con la
       cabecera de las notas crédito. Necesario para procesar **NCA** y para
       que el campo **DOC REFERENCIA** apunte a la factura original.

    #### 📐 Reglas contables

    **Ventas contado (PVFE / GBF):**
    """)
    st.code("""
Db 11050500 (CAJA)        $ Total
   Cr 41359501 (Ventas Gravadas)
   Cr 24080101 (IVA 19%)        BASE = Ventas
   Cr 41359602 (Exentas)         si aplica
   Cr 41359601 (Fletes)           si aplica
   Cr 415505   (Arrendamientos)   si aplica
NIT: 222222222 (consumidor final)
    """, language="text")

    st.markdown("**Ventas a empresas (FE):**")
    st.code("""
Db 130506   (CLIENTES)    $ Total
Db 19551503 (RTE Arrendamientos 3.5%)   si aplica
Db 19551510 (RTE Comisiones 11%)        si aplica
   Cr 41359501 (Ventas)                   o
   Cr 415505   (Arrendamientos)
   Cr 415030   (Comisiones)
   Cr 415555   (Publicidad)
   Cr 41559501 (Servicio Empaque)
   Cr 24080101 (IVA 19%)
NIT: NIT REAL del cliente
    """, language="text")

    st.markdown("**Notas crédito (DV / DW / NCA):**")
    st.code("""
Db 41750201 (DEVOLUCION EN VENTAS)
Db 24080102 (IVA NC)                    si DV/NCA
Db 24080101 (IVA generado normal)       si DW
   Cr 11050500 (CAJA)                    o
   Cr 130506   (CLIENTES)                si NCA con FE
    """, language="text")

    st.markdown("""
    #### 🔧 Comportamiento especial

    - **Documentos anulados** (columna A=True en RadGrid) se descartan automáticamente.
    - **Líneas con cuenta 0 / "Sin Cuenta"** se ignoran.
    - **DOC REFERENCIA en NC**: se usa la factura asociada del archivo Documentos.
      Si no se sube el archivo, queda igual al consecutivo NC.
    - **NCA** SIEMPRE deben venir en el archivo Documentos — RadGrid no las trae.
    - **Centro de costos**: PRINCIPAL (único actualmente).
    """)
