"""
Módulo Compras DIAN - Plataforma Web (Fase 2).

Flujo:
    1. Usuario sube el Excel exportado del portal DIAN
    2. La página descarga del Storage los archivos de configuración:
       - cuentas.xlsx, mapeos.xlsx (PUC y reglas)
       - conocimiento_balance.json (histórico del balance, si existe)
    3. Click en "Procesar"
    4. Resultado en pantalla y descarga del plano TSV

Notas:
    - Pagos desde banco (comp 2) NO se generan aquí. Va en módulo
      "💳 Egresos DIAN" aparte (Fase 4).
    - La regla histórica del balance está activa cuando hay
      conocimiento_balance.json en Storage. Se desactiva poniendo
      RESPETAR_HISTORICO_BALANCE = NO en mapeos.xlsx.
    - La UI de proveedores nuevos solo muestra la lista informativa.
      La confirmación + auto-update de mapeos.xlsx va en Fase 3.
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
from core.utils import conocimiento_balance as cb
from core.procesadores.procesador_compras_dian import (
    procesar_compras_dian,
    dataframe_a_plano_tsv,
)
from db.supabase_client import get_supabase


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

st.title("🛒 Compras DIAN")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    f"Genera el plano contable de facturas electrónicas recibidas (FDI/NDI)"
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
        El archivo debe ser el reporte de **Documentos Electrónicos
        recibidos** descargado del portal DIAN, sin modificar. Columnas
        clave:
        - Tipo de documento (Factura / Nota crédito)
        - Folio, Prefijo
        - Fecha Emisión
        - NIT Emisor, Nombre Emisor
        - Total
        - IVA, ICA, IC, INC, Timbre, etc.
        """
    )

    st.markdown("---")
    st.markdown("### 🧾 Comprobantes que genera")
    st.caption(
        """
        - **3 (FDI)** — Facturas electrónicas
        - **7 (NDI)** — Notas crédito electrónicas
        
        Los pagos desde banco (comp 2) se generan en el módulo
        **Egresos DIAN** aparte cuando esté disponible.
        """
    )


# ============================================================
# Cargar configuración + conocimiento de la empresa
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_config_empresa(empresa_id: str):
    """Descarga cuentas.xlsx y mapeos.xlsx desde Supabase Storage y los
    convierte en una Configuracion. Si no existen, devuelve Configuracion
    vacía para no bloquear el flujo."""
    sb = get_supabase()
    bucket = sb.storage.from_("empresas-config")

    cuentas_bytes = None
    mapeos_bytes = None
    try:
        cuentas_bytes = bucket.download(f"{empresa_id}/cuentas.xlsx")
    except Exception:
        pass
    try:
        mapeos_bytes = bucket.download(f"{empresa_id}/mapeos.xlsx")
    except Exception:
        pass

    if not cuentas_bytes and not mapeos_bytes:
        return Configuracion.vacia()

    return Configuracion.desde_excel(
        cuentas_bytes=cuentas_bytes,
        mapeos_bytes=mapeos_bytes,
    )


@st.cache_data(ttl=300, show_spinner=False)
def cargar_conocimiento_empresa(empresa_id: str):
    """Descarga el conocimiento_balance.json del Storage (Fase 2).
    Retorna None si la empresa todavía no ha cargado un balance."""
    return cb.cargar_conocimiento_desde_storage(empresa_id)


cfg = cargar_config_empresa(emp["id"])
conocimiento = cargar_conocimiento_empresa(emp["id"])

# Mostrar estado del balance al usuario
if conocimiento:
    estad = conocimiento.get("estadisticas", {})
    fecha = conocimiento.get("fecha_balance", "")
    fecha_str = f" ({fecha})" if fecha else ""
    st.success(
        f"📚 **Balance histórico cargado**{fecha_str} · "
        f"{estad.get('total_nits', 0)} NITs · "
        f"{estad.get('con_retefuente_historica', 0)} con retefuente histórica"
    )
else:
    st.warning(
        "⚠️ No hay balance de prueba cargado para esta empresa. "
        "El procesador funcionará SIN la regla histórica de retefuente. "
        "Carga un balance desde **Configuración → Balance de prueba** "
        "para activarla."
    )


# ============================================================
# Subida del archivo
# ============================================================

st.markdown("### 1️⃣ Sube el archivo")

archivo_dian = st.file_uploader(
    "Excel del portal DIAN (Documentos Electrónicos recibidos)",
    type=["xlsx"],
    key="file_dian",
    help="El archivo que descargas del portal MUISCA, sin renombrarlo.",
)


# ============================================================
# Procesar
# ============================================================

st.markdown("### 2️⃣ Procesar")

if not archivo_dian:
    st.info("📂 Sube el archivo DIAN para continuar.")
    st.stop()

procesar = st.button(
    "🚀 Procesar compras DIAN",
    type="primary",
    use_container_width=False,
)

if not procesar and "resultado_dian" not in st.session_state:
    st.stop()

if procesar:
    with st.spinner("Procesando documentos DIAN..."):
        try:
            df_plano, log, prov_nuevos = procesar_compras_dian(
                archivo_dian,
                cfg,
                conocimiento=conocimiento,
            )
            st.session_state["resultado_dian"] = {
                "df": df_plano,
                "log": log,
                "prov_nuevos": prov_nuevos,
                "nombre_entrada": archivo_dian.name,
            }
        except Exception as e:
            st.error(f"❌ Error al procesar: {e}")
            st.exception(e)
            st.stop()


# ============================================================
# Mostrar resultado
# ============================================================

resultado = st.session_state.get("resultado_dian")
if not resultado:
    st.stop()

df = resultado["df"]
log = resultado["log"]
prov_nuevos = resultado["prov_nuevos"]

st.markdown("### 3️⃣ Resultado")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Filas generadas", len(df))
with col2:
    docs_unicos = df["DOCUMENTO"].nunique() if len(df) else 0
    st.metric("Documentos únicos", docs_unicos)
with col3:
    suma_debitos = (
        df[df["TIPO DE TRANSACCION"] == "1"]["VALOR"].astype(int).sum()
        if len(df) else 0
    )
    st.metric("Total causado", f"$ {abs(suma_debitos):,.0f}".replace(",", "."))

with st.expander("📝 Log de procesamiento", expanded=True):
    for linea in log:
        st.text(linea)

if prov_nuevos:
    with st.expander(
        f"⚠️ {len(prov_nuevos)} proveedor(es) nuevo(s) detectado(s)",
        expanded=True,
    ):
        st.caption(
            "Estos proveedores no están en `DIAN_Proveedores` ni en el "
            "balance histórico. Se procesaron con cuentas por defecto. "
            "Para clasificarlos correctamente, edítalos en `mapeos.xlsx` "
            "desde la página de Configuración."
        )
        df_nuevos = pd.DataFrame([
            {
                "NIT": p["nit"],
                "Nombre": p["nombre"],
                "Facturas": p["num_facturas"],
                "Total": f"$ {p['total_acumulado']:,.0f}".replace(",", "."),
                "Tipo retención sugerido": p["tipo_retencion_sugerido"],
            }
            for p in prov_nuevos
        ])
        st.dataframe(df_nuevos, use_container_width=True, hide_index=True)

st.markdown("#### Vista previa del plano")
st.dataframe(df, use_container_width=True, height=400)


# ============================================================
# Descarga
# ============================================================

st.markdown("### 4️⃣ Descargar")

tsv_bytes = dataframe_a_plano_tsv(df, incluir_encabezado_excel=incluir_enc_excel)
nombre_base = resultado["nombre_entrada"].rsplit(".", 1)[0]
nombre_salida = f"plano_dian_{nombre_base}.txt"

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
    st.session_state.pop("resultado_dian", None)
    st.rerun()
