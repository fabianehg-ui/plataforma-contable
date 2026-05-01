"""
Módulo Caja Menor - Plataforma Web

Flujo:
    1. Usuario sube el Excel de egresos exportado del sistema contable
    2. (Opcional) Sube también el Excel de compras del mes para resolver
       egresos Tipo 2 (CEG que cancelan DSxxx)
    3. Click en "Procesar"
    4. Ve el resultado en pantalla y descarga el plano TSV
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import (
    seleccionar_empresa_sidebar,
    require_empresa,
    require_rol,
)
from core.utils.configuracion_web import Configuracion
from core.procesadores.procesador_caja_menor import (
    procesar_caja_menor,
    dataframe_a_plano_tsv,
)


# ============================================================
# Configuración de la página
# ============================================================

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin", "operador"])


# ============================================================
# Encabezado
# ============================================================

st.title("💵 Caja Menor")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    f"Genera el plano contable de egresos de caja menor"
)
st.markdown("---")


# ============================================================
# Sidebar: opciones
# ============================================================

with st.sidebar:
    st.markdown("### ⚙️ Opciones")
    incluir_enc_excel = st.checkbox(
        "Incluir 'sep=\\t' (compatible Excel)",
        value=True,
        help="Agrega la directiva de separador para que Excel abra el TSV "
             "con las columnas correctamente alineadas.",
    )

    st.markdown("---")
    st.markdown("### 📋 Formato esperado")
    st.caption(
        """
        El archivo debe ser el export de **RadGrid de egresos** con estas
        columnas:
        - Consecutivo (ej: CEG4739)
        - Cancela (CEG o DS)
        - Identificación
        - Nombres
        - Fecha (dd/mm/yyyy)
        - Sucursal
        - Valor
        """
    )


# ============================================================
# Cargar configuración de la empresa
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_config_empresa(empresa_id: str):
    """Carga archivos cuentas.xlsx y mapeos.xlsx de la empresa desde
    Supabase Storage. Por ahora es un placeholder; cuando implementes
    la carga en el módulo de Configuración, este método lee lo subido.
    """
    # TODO: descargar de Supabase Storage los archivos de la empresa.
    # Ejemplo de estructura en storage:
    #   bucket "empresas-config" / {empresa_id} / cuentas.xlsx
    #   bucket "empresas-config" / {empresa_id} / mapeos.xlsx
    return Configuracion.vacia()


cfg = cargar_config_empresa(emp["id"])


# ============================================================
# Subida de archivos
# ============================================================

st.markdown("### 1️⃣ Sube los archivos")

col_a, col_b = st.columns(2)

with col_a:
    st.markdown("**Archivo de caja menor** (obligatorio)")
    archivo_cm = st.file_uploader(
        "Egresos exportados del sistema",
        type=["xlsx", "xls", "xlsm"],
        key="file_cm",
        label_visibility="collapsed",
    )

with col_b:
    st.markdown("**Archivo de compras del mes** (opcional)")
    archivo_compras = st.file_uploader(
        "Para resolver egresos Tipo 2 (CEG que cancelan DSxxx)",
        type=["xlsx", "xls", "xlsm"],
        key="file_compras",
        label_visibility="collapsed",
    )


# ============================================================
# Procesar
# ============================================================

st.markdown("### 2️⃣ Procesar")

if not archivo_cm:
    st.info("📂 Sube el archivo de caja menor para continuar.")
    st.stop()

procesar = st.button("🚀 Procesar caja menor", type="primary", use_container_width=False)

if not procesar and "resultado_cm" not in st.session_state:
    st.stop()

if procesar:
    with st.spinner("Procesando..."):
        try:
            df_plano, log = procesar_caja_menor(
                archivo_cm,
                cfg,
                archivo_compras=archivo_compras,
            )
            st.session_state["resultado_cm"] = {
                "df": df_plano,
                "log": log,
                "nombre_entrada": archivo_cm.name,
            }
        except Exception as e:
            st.error(f"❌ Error al procesar: {e}")
            st.exception(e)
            st.stop()


# ============================================================
# Mostrar resultado
# ============================================================

resultado = st.session_state.get("resultado_cm")
if not resultado:
    st.stop()

df = resultado["df"]
log = resultado["log"]

st.markdown("### 3️⃣ Resultado")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Filas generadas", len(df))
with col2:
    docs_unicos = df["DOCUMENTO"].nunique() if len(df) else 0
    st.metric("Documentos únicos", docs_unicos)
with col3:
    suma_debitos = df[df["TIPO DE TRANSACCION"] == "1"]["VALOR"].astype(int).sum() if len(df) else 0
    st.metric("Total egresos", f"$ {abs(suma_debitos):,.0f}".replace(",", "."))

# Log
with st.expander("📝 Log de procesamiento", expanded=True):
    for linea in log:
        st.text(linea)

# Preview
st.markdown("#### Vista previa del plano")
st.dataframe(df, use_container_width=True, height=400)

# Descarga
st.markdown("### 4️⃣ Descargar")

tsv_bytes = dataframe_a_plano_tsv(df, incluir_encabezado_excel=incluir_enc_excel)
nombre_base = resultado["nombre_entrada"].rsplit(".", 1)[0]
nombre_salida = f"plano_caja_menor_{nombre_base}.txt"

col_d1, col_d2 = st.columns(2)
with col_d1:
    st.download_button(
        "📥 Descargar plano (.txt)",
        data=tsv_bytes,
        file_name=nombre_salida,
        mime="text/tab-separated-values",
        type="primary",
        use_container_width=True,
    )
with col_d2:
    import io
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    st.download_button(
        "📊 Descargar como Excel",
        data=buffer.getvalue(),
        file_name=nombre_salida.replace(".txt", ".xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

if st.button("🔄 Procesar otro archivo"):
    st.session_state.pop("resultado_cm", None)
    st.rerun()
