"""
Módulo Ingresos POS — Plataforma Web (versión 2: DATOS PUNTO embebido).

DATOS PUNTO viene incluido en el código (core/data/datos_punto.json) — el
operador NO tiene que subirlo. Solo sube los 4 reportes mensuales.

Pestañas:
    1️⃣ Procesar (subir reportes por separado)  ← modo principal
    2️⃣ Procesar (Excel todo en uno)             ← modo legacy

Asiento generado:
    Db CUENTA DE CAJA   = Total Final
    Cr CTA BASE V       = Neto
    Cr CTA ICO          = IC (Final − Neto)

Validación de CLASE DE SEDE:
    - REPORTE CHILI     → solo procesa SANTA LEÑA
    - HENKO MILAGROS    → solo procesa RESTAURANTE MILAGROS
    - HENKO REMEDIOS    → solo procesa RESTAURANTE MILAGROS
    - L3AF MILLA DE ORO → solo procesa RESTAURANTE MILAGROS
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import (
    seleccionar_empresa_sidebar,
    require_rol,
)
from auth.modulos import require_modulo
from core.procesadores.procesador_pos import (
    procesar_pos,
    dataframe_a_plano_tsv,
    combinar_archivos_pos,
    cargar_datos_punto_embebido,
    datos_punto_embebido_a_xlsx,
    info_datos_punto_embebido,
)


# ============================================================
# Configuración de la página
# ============================================================

st.set_page_config(
    page_title="Ingresos POS",
    page_icon="🧾",
    layout="wide",
)

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
require_modulo("ingresos_pos")
emp = require_rol(["admin", "operador"])


# ============================================================
# Encabezado
# ============================================================

st.title("🧾 Ingresos POS")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    f"Procesa reportes diarios de ventas POS y genera el plano contable"
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
    st.markdown("### 🛡️ Validación por clase")
    st.caption(
        """
        Cada hoja solo procesa sucursales de su clase:

        - 🥩 **REPORTE CHILI** → SANTA LEÑA
        - 🍝 **L3AF MILLA DE ORO** → RESTAURANTE MILAGROS
        - 🍝 **HENKO MILAGROS** → RESTAURANTE MILAGROS
        - 🍝 **HENKO REMEDIOS** → RESTAURANTE MILAGROS

        Si una sucursal aparece en una hoja con clase incorrecta,
        se descarta y se avisa.
        """
    )


# ============================================================
# Cargar info del DATOS PUNTO embebido
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def _info_dp():
    try:
        return info_datos_punto_embebido()
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=600, show_spinner=False)
def _xlsx_dp():
    return datos_punto_embebido_a_xlsx()


info_dp = _info_dp()
if "error" in info_dp:
    st.error(
        f"❌ No se pudo cargar el maestro de sucursales embebido: "
        f"{info_dp['error']}\n\n"
        "Verifica que el archivo `core/data/datos_punto.json` esté presente "
        "en el repositorio."
    )
    st.stop()


# ============================================================
# Banner del DATOS PUNTO embebido (informativo, no editable)
# ============================================================

n_sl = info_dp["por_clase"].get("SANTA LEÑA", 0)
n_rm = info_dp["por_clase"].get("RESTAURANTE MILAGROS", 0)

col_a, col_b, col_c = st.columns(3)
col_a.metric("📋 Sucursales registradas", info_dp["total"])
col_b.metric("🥩 SANTA LEÑA", n_sl)
col_c.metric("🍝 RESTAURANTE MILAGROS", n_rm)

with st.expander(
    f"👁️ Ver las {info_dp['total']} sucursales registradas (modo lectura)",
    expanded=False,
):
    st.caption(
        "Estas son las sucursales registradas en el sistema. **El maestro "
        "DATOS PUNTO viene incluido en el código** — no es editable desde "
        "la web. Si abren un punto nuevo o cambia una cuenta, contacta al "
        "desarrollador para actualizar el archivo."
    )
    df_suc = pd.DataFrame(info_dp["sucursales"])
    st.dataframe(
        df_suc,
        use_container_width=True,
        hide_index=True,
        column_config={
            "nombre_reporte": "Nombre en reporte",
            "sede": "Sede",
            "cc": "Centro de costo",
            "clase": "Clase de sede",
            "cuenta_caja": "Cuenta de caja",
            "cta_base_v": "Cta venta",
            "cta_ico": "Cta IC",
            "comprobante": "Comprob.",
        },
    )

st.markdown("---")


# ============================================================
# Tabs principales
# ============================================================

tab_separado, tab_unico = st.tabs([
    "1️⃣ Procesar (subir reportes por separado)",
    "2️⃣ Procesar (Excel todo en uno)",
])


# ============================================================
# Helper compartido: mostrar resultado
# ============================================================

def _mostrar_resultado(df, log, sucs_no_enc, nombre_entrada):
    """Muestra el resultado del procesamiento."""
    st.markdown("### 📊 Resultado")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Filas en plano", len(df))
    with col2:
        sucs_unicas = df["DETALLE"].nunique() if len(df) else 0
        st.metric("Sucursales", sucs_unicas)
    with col3:
        if len(df):
            suma_db = int(df[df["TR"] == "1"]["VALOR"].astype(int).sum())
        else:
            suma_db = 0
        st.metric("Total Débitos", f"$ {suma_db:,.0f}".replace(",", "."))
    with col4:
        if len(df):
            suma_cr = int(df[df["TR"] == "2"]["VALOR"].astype(int).sum())
        else:
            suma_cr = 0
        st.metric("Total Créditos", f"$ {suma_cr:,.0f}".replace(",", "."))

    if len(df) > 0:
        if suma_db == suma_cr:
            st.success(f"✅ Cuadre perfecto: Db = Cr = $ {suma_db:,.0f}".replace(",", "."))
        else:
            diff = suma_db - suma_cr
            st.error(f"❌ DESCUADRE: diferencia $ {diff:,.0f}".replace(",", "."))

    with st.expander("📝 Log de procesamiento", expanded=True):
        for linea in log:
            st.text(linea)

    if sucs_no_enc:
        with st.expander(
            f"⚠️ {len(sucs_no_enc)} sucursal(es) descartada(s)",
            expanded=True,
        ):
            st.caption(
                "Estas sucursales aparecieron en los reportes pero NO se "
                "incluyeron en el plano. Si es una sucursal nueva, el "
                "desarrollador debe agregarla a `core/data/datos_punto.json`."
            )
            df_no_enc = pd.DataFrame([
                {
                    "Sucursal detectada": s["nombre"],
                    "Hoja": s["hoja"],
                    "Motivo": s.get("motivo", "-"),
                    "Total ignorado": f"$ {s['total_aproximado']:,.0f}".replace(",", "."),
                }
                for s in sucs_no_enc
            ])
            st.dataframe(df_no_enc, use_container_width=True, hide_index=True)

    if len(df) > 0:
        with st.expander("📊 Resumen por sucursal", expanded=False):
            df_resumen = df[df["TR"] == "1"].groupby("DETALLE").agg(
                dias=("FECHA", "nunique"),
                total=("VALOR", lambda x: x.astype(int).sum()),
            ).reset_index()
            df_resumen["DETALLE"] = df_resumen["DETALLE"].str.replace("VENTAS POS ", "")
            df_resumen = df_resumen.sort_values("total", ascending=False)
            df_resumen["Total"] = df_resumen["total"].apply(
                lambda x: f"$ {x:,.0f}".replace(",", ".")
            )
            st.dataframe(
                df_resumen[["DETALLE", "dias", "Total"]].rename(
                    columns={"DETALLE": "Sucursal", "dias": "Días con venta"},
                ),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("#### Vista previa del plano")
    st.dataframe(df, use_container_width=True, height=400)

    # Descarga
    st.markdown("### 📥 Descargar")
    tsv_bytes = dataframe_a_plano_tsv(df, incluir_encabezado_excel=incluir_enc_excel)
    nombre_base = nombre_entrada.rsplit(".", 1)[0] if nombre_entrada else "ingresos_pos"
    nombre_salida = f"plano_pos_{nombre_base}.txt"

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
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        st.download_button(
            "📊 Descargar como Excel",
            data=buffer.getvalue(),
            file_name=nombre_salida.replace(".txt", ".xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


# ============================================================
# TAB 1: Subir reportes por separado (modo principal)
# ============================================================

with tab_separado:
    st.markdown("### 📂 Subir cada reporte como archivo aparte")
    st.caption(
        "Sube los 4 reportes que recibes cada mes de los sistemas POS. "
        "El sistema los combina automáticamente con el maestro de "
        "sucursales y genera el plano contable."
    )

    st.info(
        "💡 **No necesitas subir DATOS PUNTO** — viene incluido en el sistema "
        f"({info_dp['total']} sucursales registradas)."
    )

    st.markdown("#### Sube los reportes (puedes dejar los que no apliquen vacíos)")

    col_chi, col_l3 = st.columns(2)
    with col_chi:
        st.markdown("**🥩 REPORTE CHILI** (SANTA LEÑA)")
        archivo_chili = st.file_uploader(
            "Reporte CHILI (.xlsx)",
            type=["xlsx"],
            key="file_chili",
            label_visibility="collapsed",
        )
    with col_l3:
        st.markdown("**🍝 L3AF MILLA DE ORO** (RESTAURANTE MILAGROS)")
        archivo_l3af = st.file_uploader(
            "L3AF (.xlsx)",
            type=["xlsx"],
            key="file_l3af",
            label_visibility="collapsed",
        )

    col_hm, col_hr = st.columns(2)
    with col_hm:
        st.markdown("**🍝 HENKO MILAGROS** (RESTAURANTE MILAGROS)")
        archivo_henko_m = st.file_uploader(
            "HENKO Milagros (.xlsx)",
            type=["xlsx"],
            key="file_henko_m",
            label_visibility="collapsed",
        )
    with col_hr:
        st.markdown("**🍝 HENKO REMEDIOS** (RESTAURANTE MILAGROS)")
        archivo_henko_r = st.file_uploader(
            "HENKO Remedios (.xlsx)",
            type=["xlsx"],
            key="file_henko_r",
            label_visibility="collapsed",
        )

    archivos_subidos = {
        "REPORTE CHILI": archivo_chili,
        "L3AF MILLA DE ORO": archivo_l3af,
        "HENKO MILAGROS": archivo_henko_m,
        "HENKO REMEDIOS": archivo_henko_r,
    }
    archivos_validos = {k: v for k, v in archivos_subidos.items() if v is not None}

    if not archivos_validos:
        st.info("📂 Sube al menos un reporte para procesar.")
        st.stop()

    st.markdown("---")
    st.caption(
        f"Vas a procesar **{len(archivos_validos)}** reporte(s): "
        f"{', '.join(archivos_validos.keys())}"
    )

    procesar_sep = st.button(
        "🚀 Procesar reportes",
        type="primary",
        key="btn_procesar_separado",
    )

    if procesar_sep:
        with st.spinner("Combinando reportes con DATOS PUNTO embebido..."):
            try:
                xlsx_dp = _xlsx_dp()
                excel_combinado = combinar_archivos_pos(
                    archivo_datos_punto=xlsx_dp,
                    reportes=archivos_validos,
                )
            except Exception as e:
                st.error(f"❌ Error combinando archivos: {e}")
                st.exception(e)
                st.stop()

        with st.spinner("Generando plano contable..."):
            try:
                df, log, sucs_no = procesar_pos(excel_combinado)
            except Exception as e:
                st.error(f"❌ Error procesando: {e}")
                st.exception(e)
                st.stop()

        st.session_state["resultado_pos_separado"] = {
            "df": df,
            "log": log,
            "sucs_no": sucs_no,
            "nombre": "reportes_combinados",
        }

    res_sep = st.session_state.get("resultado_pos_separado")
    if res_sep:
        _mostrar_resultado(
            res_sep["df"], res_sep["log"], res_sep["sucs_no"], res_sep["nombre"],
        )
        if st.button("🔄 Procesar otros reportes", key="reset_sep"):
            st.session_state.pop("resultado_pos_separado", None)
            st.rerun()


# ============================================================
# TAB 2: Excel todo en uno (modo legacy)
# ============================================================

with tab_unico:
    st.markdown("### 📦 Subir Excel todo en uno")
    st.caption(
        "Si prefieres el formato antiguo donde DATOS PUNTO + todos los "
        "reportes están en un solo archivo Excel multi-hoja, súbelo aquí. "
        "Útil cuando alguien ya armó el archivo manualmente."
    )

    archivo_pos = st.file_uploader(
        "Excel multi-hoja con DATOS PUNTO + reportes",
        type=["xlsx"],
        key="file_pos_unico",
    )

    if archivo_pos:
        procesar_uni = st.button(
            "🚀 Procesar Excel completo",
            type="primary",
            key="btn_procesar_unico",
        )

        if procesar_uni:
            with st.spinner("Procesando..."):
                try:
                    df, log, sucs_no = procesar_pos(archivo_pos)
                    st.session_state["resultado_pos_unico"] = {
                        "df": df,
                        "log": log,
                        "sucs_no": sucs_no,
                        "nombre": archivo_pos.name,
                    }
                except Exception as e:
                    st.error(f"❌ Error al procesar: {e}")
                    st.exception(e)
                    st.stop()

    res_uni = st.session_state.get("resultado_pos_unico")
    if res_uni:
        _mostrar_resultado(
            res_uni["df"], res_uni["log"], res_uni["sucs_no"], res_uni["nombre"],
        )
        if st.button("🔄 Procesar otro archivo", key="reset_uni"):
            st.session_state.pop("resultado_pos_unico", None)
            st.rerun()
