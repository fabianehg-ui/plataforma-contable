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
    empresas_del_usuario,
)
from core.utils import conocimiento_balance as cb


st.set_page_config(page_title="Configuración", page_icon="⚙️", layout="wide")
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()

st.title("⚙️ Configuración")
st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs([
    "🏢 Empresas",
    "📂 Archivos de configuración",
    "📚 Balance de prueba",
    "👥 Usuarios",
])


# ============================================================
# TAB 1: Empresas
# ============================================================
with tab1:
    st.markdown("### Mis empresas")
    empresas = empresas_del_usuario()
    if not empresas:
        st.warning("No tienes empresas asignadas.")
    else:
        df = pd.DataFrame(empresas)
        st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.markdown("### ➕ Crear nueva empresa")
    st.info("🚧 Funcionalidad en desarrollo. Por ahora las empresas se crean "
            "directamente en Supabase.")


# ============================================================
# TAB 2: Archivos de configuración
# ============================================================
with tab2:
    st.markdown("### Archivos de configuración por empresa")
    st.info(
        "🚧 En desarrollo: aquí podrás subir los archivos `cuentas.xlsx` y "
        "`mapeos.xlsx` de cada empresa, equivalentes a los del .exe actual.\n\n"
        "Por ahora súbelos manualmente al bucket `empresas-config` de "
        "Supabase Storage en la ruta `{empresa_id}/cuentas.xlsx` y "
        "`{empresa_id}/mapeos.xlsx`."
    )


# ============================================================
# TAB 3: Balance de prueba (Fase 2)
# ============================================================
with tab3:
    st.markdown("### 📚 Balance de prueba histórico")
    st.caption(
        "El balance permite que el procesador de Compras DIAN tome mejores "
        "decisiones contables: respeta el comportamiento histórico de "
        "retefuente por NIT y sugiere cuentas de gasto / IVA recurrentes."
    )

    emp_activa = st.session_state.get("empresa_activa")
    if not emp_activa:
        st.warning("Selecciona primero una empresa en el menú lateral.")
        st.stop()

    empresa_id = emp_activa["id"]

    # ---- Estado actual ----
    st.markdown("#### Estado actual")
    conocimiento_actual = cb.cargar_conocimiento_desde_storage(empresa_id)

    if conocimiento_actual:
        estad = conocimiento_actual.get("estadisticas", {})
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Total NITs", estad.get("total_nits", 0))
        col_b.metric("Con retefuente histórica",
                     estad.get("con_retefuente_historica", 0))
        col_c.metric("IVA mercancía (24080201)",
                     estad.get("con_iva_mercancia", 0))
        col_d.metric("IVA servicios (24080308)",
                     estad.get("con_iva_servicios", 0))

        info_extra = []
        if conocimiento_actual.get("empresa"):
            info_extra.append(f"**Empresa:** {conocimiento_actual['empresa']}")
        if conocimiento_actual.get("fecha_balance"):
            info_extra.append(
                f"**Fecha balance:** {conocimiento_actual['fecha_balance']}"
            )
        if conocimiento_actual.get("fecha_procesamiento"):
            info_extra.append(
                f"**Procesado:** {conocimiento_actual['fecha_procesamiento']}"
            )
        if info_extra:
            st.caption(" · ".join(info_extra))

        if st.button("🗑️ Eliminar balance cargado", key="btn_eliminar_balance"):
            ok = cb.eliminar_conocimiento_de_storage(empresa_id)
            if ok:
                st.success("Balance eliminado.")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("No se pudo eliminar.")
    else:
        st.info("📭 Esta empresa todavía no tiene balance cargado.")

    st.markdown("---")

    # ---- Cargar nuevo balance ----
    st.markdown("#### Cargar / actualizar balance")
    st.caption(
        "Sube el Excel del balance de prueba exportado del sistema "
        "contable. Estructura esperada: cabecera con nombre de empresa "
        "(fila 1) y fecha del balance (fila 2), y desde la fila 4 las "
        "columnas: Cuenta · Equivalente · Nombre cuenta · NIT · Nombre "
        "NIT · Saldo anterior · Débitos · Créditos."
    )

    archivo_balance = st.file_uploader(
        "Excel del balance de prueba",
        type=["xlsx"],
        key="file_balance",
    )

    if archivo_balance:
        col_p1, col_p2 = st.columns([1, 3])
        with col_p1:
            procesar_balance = st.button(
                "📊 Procesar balance",
                type="primary",
                use_container_width=True,
            )
        with col_p2:
            st.caption(
                "Al procesar, el archivo se analiza y se guarda como "
                "`conocimiento_balance.json` en Supabase Storage. El Excel "
                "no se conserva."
            )

        if procesar_balance:
            with st.spinner("Procesando balance..."):
                try:
                    conocimiento_nuevo = cb.procesar_balance(archivo_balance)
                except Exception as e:
                    st.error(f"❌ Error procesando el balance: {e}")
                    st.exception(e)
                    st.stop()

                estad = conocimiento_nuevo.get("estadisticas", {})
                if estad.get("total_nits", 0) == 0:
                    st.error(
                        "El archivo no contiene NITs procesables. Revisa "
                        "que el formato sea el balance de prueba completo "
                        "y que haya datos desde la fila 4."
                    )
                    st.stop()

                # Guardar en Storage
                try:
                    cb.guardar_conocimiento_en_storage(
                        empresa_id, conocimiento_nuevo,
                    )
                except Exception as e:
                    st.error(
                        "❌ No se pudo guardar en Supabase Storage. "
                        "Revisa que el bucket `empresas-config` exista y "
                        "que el usuario tenga permisos de escritura.\n\n"
                        f"Detalle: {e}"
                    )
                    st.exception(e)
                    st.stop()

            st.success(
                f"✅ Balance procesado y guardado. "
                f"{estad.get('total_nits', 0)} NITs registrados."
            )

            # Mostrar resumen
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Total NITs", estad.get("total_nits", 0))
            col_b.metric("Con retefuente histórica",
                         estad.get("con_retefuente_historica", 0))
            col_c.metric("Con IVA descontable recurrente",
                         estad.get("con_iva_mercancia", 0)
                         + estad.get("con_iva_servicios", 0))

            # Limpiar caché para que la página de Compras DIAN lea el nuevo
            st.cache_data.clear()

            with st.expander("Ver primeros 20 NITs procesados"):
                nits_dict = conocimiento_nuevo.get("nits", {})
                filas = []
                for nit, info in list(nits_dict.items())[:20]:
                    filas.append({
                        "NIT": nit,
                        "Nombre": info.get("nombre", ""),
                        "Cuenta gasto": (info.get("cuentas_gasto") or [""])[0],
                        "Cuenta IVA": info.get("cuenta_iva_recurrente", ""),
                        "Retefuente histórica": "Sí" if info.get("tiene_retefuente_historica") else "No",
                    })
                if filas:
                    st.dataframe(pd.DataFrame(filas),
                                 use_container_width=True, hide_index=True)


# ============================================================
# TAB 4: Usuarios
# ============================================================
with tab4:
    st.markdown("### Usuarios con acceso")
    st.info("🚧 En desarrollo: invitar usuarios y asignarles roles por empresa.")
