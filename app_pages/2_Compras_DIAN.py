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
    f"Genera el plano contable de facturas electrónicas recibidas (FDI/NDI) "
    f"y de Documentos Soporte (no obligados)"
)
st.markdown("---")


# ============================================================
# PESTAÑAS
# ============================================================

tab_compras, tab_dse = st.tabs([
    "🛒 Compras DIAN (FDI/NDI)",
    "📋 Documentos Soporte (no obligados a FE)",
])


# ============================================================
# PESTAÑA 1: Compras DIAN (lógica original)
# ============================================================
with tab_compras:


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

    # Opción: agregar al movimiento del mes
    from core.contable.ui_contabilizar import render_contabilizar_activa
    st.markdown("---")
    render_contabilizar_activa(df, "compras_dian")

    if st.button("🔄 Procesar otro archivo"):
        st.session_state.pop("resultado_dian", None)
        st.rerun()


# ============================================================
# PESTAÑA 2: Documentos Soporte (DSE)
# ============================================================
with tab_dse:
    from datetime import date as _date

    st.markdown("### 📋 Documentos Soporte Electrónicos (DSE)")
    st.caption(
        "Compras a personas naturales NO obligadas a emitir factura electrónica. "
        "JIPER las emite a sí misma como soporte contable. "
        "Sube el ZIP descargado del portal DIAN con los DSE del mes."
    )

    # Import defensivo
    try:
        from core.procesadores.procesador_dse import (
            procesar_dse, cargar_config_dse,
            plano_dse_a_tsv, plano_dse_a_csv, plano_dse_a_xlsx,
        )
        _DSE_DISPONIBLE = True
    except Exception as _e_dse:
        _DSE_DISPONIBLE = False
        st.error(f"🚫 Módulo DSE no disponible: {_e_dse}")
        st.stop()

    config_dse = cargar_config_dse()

    with st.expander("⚙️ Configuración DSE", expanded=False):
        st.markdown(
            f"**Comprobante:** `{config_dse['comprobante_dse']}`  \n"
            f"**Centro de costos:** `{config_dse['cc_default']}`  \n"
            f"**Cuenta proveedor (Cr):** `{config_dse['cta_proveedor']}`"
        )
        st.markdown("**Mapeo de conceptos → cuenta gasto:**")
        for concepto, c in config_dse["cuentas_por_concepto"].items():
            st.markdown(f"- **{c['etiqueta']}** (`{concepto}`) → `{c['cta_gasto']}`")
        st.markdown("**Proveedores con cuenta especial:**")
        for nit, c in config_dse["proveedores_especiales"].items():
            st.markdown(f"- NIT `{nit}` → `{c['cta_gasto']}` ({c['concepto']})")
        st.caption(
            "Para añadir proveedores especiales o cambiar mapeo: editar "
            "`core/data/config_dse.json` (si existe) o el default en "
            "`core/procesadores/procesador_dse.py`."
        )

    st.markdown("---")
    st.markdown("### 📂 Cargar ZIP de DSE")
    archivo_dse_zip = st.file_uploader(
        "ZIP descargado del portal DIAN (con todos los DSE del mes)",
        type=["zip"],
        key="dse_zip_uploader",
    )

    if archivo_dse_zip is None:
        st.info("👆 Sube el ZIP de DSE descargado del portal DIAN.")
    else:
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            anio_dse = st.number_input(
                "Año", min_value=2020, max_value=2030,
                value=_date.today().year, key="dse_anio"
            )
        with col_p2:
            mes_dse = st.selectbox(
                "Mes",
                options=list(range(1, 13)),
                index=max(0, _date.today().month - 2),
                format_func=lambda m: [
                    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
                    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
                ][m-1],
                key="dse_mes",
            )

        if st.button("🚀 Procesar DSE", type="primary", key="dse_procesar"):
            with st.spinner("Procesando DSE..."):
                try:
                    r_dse = procesar_dse(
                        fuente_zip=archivo_dse_zip.getvalue(),
                        config=config_dse,
                        anio=int(anio_dse),
                        mes=int(mes_dse),
                    )
                    st.session_state["resultado_dse"] = r_dse
                    st.session_state["resultado_dse_periodo"] = f"{int(anio_dse)}-{int(mes_dse):02d}"
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    import traceback
                    with st.expander("Traceback"):
                        st.code(traceback.format_exc())

        # Mostrar resultado
        if "resultado_dse" in st.session_state:
            r = st.session_state["resultado_dse"]
            periodo = st.session_state.get("resultado_dse_periodo", "?")

            st.markdown("---")
            st.markdown(f"### 📊 Resultado — período {periodo}")

            # Métricas
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("DSE procesados", r["metadatos"]["dses_procesados"])
            col2.metric("Líneas plano", r["metadatos"]["lineas_plano"])
            col3.metric("Total Db", f"${r['cuadre']['debitos']:,.0f}")
            col4.metric("Cuadre",
                       "✅ Cuadra" if r["cuadre"]["cuadra"] else f"❌ ${r['cuadre']['diferencia']:,.0f}")

            # Por concepto
            st.markdown("#### 📁 Por concepto")
            if r["resumen_concepto"]:
                df_c = pd.DataFrame([
                    {"Concepto": k, "Docs": v["docs"], "Total": f"${v['total']:,.0f}"}
                    for k, v in r["resumen_concepto"].items()
                ])
                st.dataframe(df_c, use_container_width=True, hide_index=True)

            # Por proveedor
            st.markdown("#### 🏪 Por proveedor (top 20)")
            if r["resumen_proveedor"]:
                df_p = pd.DataFrame([
                    {"NIT": k, "Nombre": v["nombre"][:40],
                     "Docs": v["docs"], "Total": v["total"]}
                    for k, v in r["resumen_proveedor"].items()
                ]).sort_values("Total", ascending=False).head(20)
                df_p["Total"] = df_p["Total"].apply(lambda x: f"${x:,.0f}")
                st.dataframe(df_p, use_container_width=True, hide_index=True)

            # Alertas
            if r["alertas"]:
                st.markdown(f"#### ⚠️ Alertas ({len(r['alertas'])})")
                st.warning(
                    "Algunos DSE tienen conceptos no mapeados. "
                    "Revisa el JSON `config_dse.json` para añadir cuentas específicas."
                )
                st.dataframe(pd.DataFrame(r["alertas"]),
                            use_container_width=True, hide_index=True)

            # Vista previa
            with st.expander("👀 Vista previa del plano", expanded=False):
                st.dataframe(r["plano"].head(30),
                            use_container_width=True, hide_index=True)

            # Descargas
            st.markdown("---")
            st.markdown("#### 📥 Descargar plano")
            nombre_dse = f"plano_DSE_{periodo}"
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                st.download_button(
                    "📄 TXT (TAB)",
                    data=plano_dse_a_tsv(r["plano"]),
                    file_name=f"{nombre_dse}.txt",
                    mime="text/tab-separated-values",
                    use_container_width=True,
                )
            with col_d2:
                st.download_button(
                    "📄 CSV (coma)",
                    data=plano_dse_a_csv(r["plano"]),
                    file_name=f"{nombre_dse}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with col_d3:
                st.download_button(
                    "📊 Excel (resumen)",
                    data=plano_dse_a_xlsx(r["plano"], resumen=r),
                    file_name=f"{nombre_dse}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    use_container_width=True,
                )

            if st.button("🔄 Procesar otro mes", key="reset_dse"):
                st.session_state.pop("resultado_dse", None)
                st.session_state.pop("resultado_dse_periodo", None)
                st.rerun()
