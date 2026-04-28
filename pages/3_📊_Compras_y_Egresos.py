"""
Módulo Compras y Egresos — Plataforma Web.

Procesa 3 archivos relacionados y genera 4 comprobantes contables:

    📁 TOKEN DIAN.xlsx           → Comp 3 (Facturas) + Comp 7 (NC Proveedores)
    📁 DOCUMENTO_SOPORTE.xlsx     → Comp 18 (DS)
    📁 EGRESOS_CAJA_MENOR.xls     → Comp 13 (CEG)

Los 3 archivos son OPCIONALES — puedes subir solo los que necesites.

REGLA IMPORTANTE: Todos los valores en el plano son POSITIVOS.
El signo lo determina el TR (1=Débito, 2=Crédito).
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
from core.procesadores.procesador_compras_egresos import (
    procesar_compras_y_egresos,
    dataframe_a_plano_tsv,
    info_catalogo,
    COMPROBANTE_COMPRAS,
    COMPROBANTE_NC_PROVEEDORES,
    COMPROBANTE_CEG,
    COMPROBANTE_DS,
)


# ============================================================
# Configuración
# ============================================================

st.set_page_config(
    page_title="Compras y Egresos",
    page_icon="📊",
    layout="wide",
)

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
require_modulo("compras_y_egresos")
emp = require_rol(["admin", "operador"])


# ============================================================
# Encabezado
# ============================================================

st.markdown("# 📊 COMPRAS Y EGRESOS")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    f"Módulo unificado: TOKEN DIAN, Documento Soporte y Egresos Caja Menor"
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
    )

    st.markdown("---")
    st.markdown("### 📐 Comprobantes generados")
    st.caption(
        f"""
        | Comp | Origen | Asiento típico |
        |---|---|---|
        | **{COMPROBANTE_COMPRAS}** | TOKEN (FE) | Db Compra+IVA · Cr Proveedor |
        | **{COMPROBANTE_NC_PROVEEDORES}** | TOKEN (NC) | Db Proveedor · Cr Devolución+IVA |
        | **{COMPROBANTE_CEG}** | EGRESOS | Db Acreedor · Cr Caja |
        | **{COMPROBANTE_DS}** | DS | Db Gasto · Cr Proveedor |
        """
    )

    st.markdown("---")
    st.markdown("### 🔧 Reglas clave")
    st.caption(
        """
        ✅ **Todos los valores son POSITIVOS** — el signo lo da el TR
        
        ✅ **Comp 3 (Compras):**
        - 620505 si la factura tiene IVA
        - 620510 si NO tiene IVA
        - INC para restaurantes (511575)
        
        ✅ **Comp 7 (NC):** 622505 (devolución en compra)
        
        ✅ **Comp 13 (CEG):**
        - Cancela DS → cuenta del proveedor del DS
        - Banco Caja Social → 11100501
        - Resto → 23359501
        
        ✅ **Comp 18 (DS):** según producto (catálogo)
        
        ⚠️ Las cuentas `2365xxxx` solo se usan para
        cálculo de retefuente, NO como pasivo en pagos.
        """
    )

    st.markdown("---")
    st.info(
        "💡 **Consecutivo numérico:**\n\n"
        "Los Comp 3 y Comp 7 usan numeración global "
        "**YYYYMMNNN** ordenada por fecha+folio. "
        "Comp 13 y Comp 18 mantienen su propio consecutivo del archivo."
    )


# ============================================================
# Pestañas
# ============================================================

tab_procesar, tab_catalogo = st.tabs([
    "📤 Procesar archivos",
    "📋 Catálogo",
])


# ------------------------------------------------------------
# Pestaña: Procesar
# ------------------------------------------------------------

with tab_procesar:
    st.markdown("### 📤 Subir archivos del periodo")
    st.info(
        "📋 **Los 3 archivos son OPCIONALES.** Sube solo los que necesites procesar."
    )

    # Selector de periodo
    col_p1, col_p2, col_p3 = st.columns([1, 1, 1])
    with col_p1:
        hoy = date.today()
        anio = st.number_input(
            "Año del periodo",
            min_value=2020, max_value=2100,
            value=hoy.year if hoy.month > 1 else hoy.year - 1,
            step=1,
        )
    with col_p2:
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        mes_default = hoy.month - 1 if hoy.month > 1 else 12
        mes_idx = st.selectbox(
            "Mes del periodo",
            options=list(range(1, 13)),
            format_func=lambda i: f"{i:02d} — {meses[i - 1]}",
            index=mes_default - 1,
        )
    with col_p3:
        consec_inicial = st.number_input(
            "Consecutivo inicial Comp 3+7",
            min_value=1, max_value=999,
            value=1,
            help="Número desde el cual empezar la numeración mensual NNN.",
        )

    st.markdown("##### Archivos del periodo")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown("**🛒 TOKEN DIAN (Comp 3 + 7)**")
        archivo_token = st.file_uploader(
            "TOKEN.xlsx",
            type=["xlsx", "xls"],
            help="Reporte DIAN: facturas y NC recibidas",
            key="archivo_token",
        )
    with col_b:
        st.markdown("**📄 Documento Soporte (Comp 18)**")
        archivo_ds = st.file_uploader(
            "DOCUMENTO_SOPORTE.xlsx",
            type=["xlsx", "xls"],
            help="Compras a personas naturales (DS)",
            key="archivo_ds",
        )
    with col_c:
        st.markdown("**💰 Egresos Caja Menor (Comp 13)**")
        archivo_egresos = st.file_uploader(
            "EGRESOS_CAJA_MENOR.xls",
            type=["xls", "xlsx", "html", "htm"],
            help="Reporte de egresos (HTML o Excel)",
            key="archivo_egresos",
        )

    if archivo_token or archivo_ds or archivo_egresos:
        st.markdown("---")
        with st.spinner("Procesando archivos..."):
            try:
                df_plano, log, resumen = procesar_compras_y_egresos(
                    archivo_token=archivo_token,
                    archivo_ds=archivo_ds,
                    archivo_egresos=archivo_egresos,
                    anio=int(anio),
                    mes=int(mes_idx),
                    consecutivo_token_inicial=int(consec_inicial),
                )
            except Exception as e:
                st.error(f"❌ Error procesando los archivos:\n\n```\n{e}\n```")
                df_plano = None
                log = []
                resumen = {}

        if df_plano is not None and len(df_plano) > 0:
            total_db = int(df_plano[df_plano["TR"] == "1"]["VALOR"].astype(int).sum())
            total_cr = int(df_plano[df_plano["TR"] == "2"]["VALOR"].astype(int).sum())
            cuadra = total_db == total_cr

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Facturas", resumen.get("n_facturas", 0))
            with col2:
                st.metric("NC Prov", resumen.get("n_nc_proveedores", 0))
            with col3:
                st.metric("DS", resumen.get("n_ds", 0))
            with col4:
                st.metric("CEG", resumen.get("n_egresos", 0))
            with col5:
                st.metric(
                    "Total Db",
                    f"$ {total_db:,}".replace(",", "."),
                )

            if cuadra:
                st.success(f"✅ **Cuadre perfecto Db = Cr = ${total_db:,}**".replace(",", "."))
            else:
                st.error(f"❌ **Descuadre:** ${total_db - total_cr:,}".replace(",", "."))

            # Verificar negativos
            n_negs = (df_plano["VALOR"].astype(int) < 0).sum()
            if n_negs > 0:
                st.error(f"❌ **{n_negs} líneas con valor negativo!** El TR debería definir el signo.")
            else:
                st.info("✅ Todos los valores son positivos. El signo lo define el TR (1=Db, 2=Cr).")

            # Resumen por comprobante
            st.markdown("#### 📒 Asientos por comprobante")
            asientos = []
            tipos = {
                COMPROBANTE_COMPRAS: "Compras DIAN (Facturas)",
                COMPROBANTE_NC_PROVEEDORES: "NC Proveedores",
                COMPROBANTE_CEG: "Egresos Caja Menor",
                COMPROBANTE_DS: "Documentos Soporte",
            }
            for comp in sorted(df_plano["COMPROBANTE"].unique()):
                sub = df_plano[df_plano["COMPROBANTE"] == comp]
                db = int(sub[sub["TR"] == "1"]["VALOR"].astype(int).sum())
                cr = int(sub[sub["TR"] == "2"]["VALOR"].astype(int).sum())
                asientos.append({
                    "Comp": comp,
                    "Tipo": tipos.get(comp, "—"),
                    "Documentos": sub["DOCUMENTO"].nunique(),
                    "Líneas": len(sub),
                    "Total Db": f"$ {db:,}".replace(",", "."),
                    "Total Cr": f"$ {cr:,}".replace(",", "."),
                    "Cuadra": "✅" if db == cr else "❌",
                })
            st.dataframe(pd.DataFrame(asientos), use_container_width=True, hide_index=True)

            with st.expander("📄 Ver plano completo"):
                st.dataframe(df_plano, use_container_width=True, hide_index=True)

            with st.expander("📜 Ver log de procesamiento"):
                st.code("\n".join(log), language="text")

            st.markdown("#### ⬇️ Descargas")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                tsv_bytes = dataframe_a_plano_tsv(
                    df_plano, incluir_encabezado_excel=incluir_enc_excel
                )
                st.download_button(
                    label="📥 Plano (.txt)",
                    data=tsv_bytes,
                    file_name=f"plano_compras_egresos_{int(anio)}_{int(mes_idx):02d}.txt",
                    mime="text/tab-separated-values",
                    use_container_width=True,
                )
            with col_d2:
                bio = io.BytesIO()
                with pd.ExcelWriter(bio, engine="openpyxl") as writer:
                    df_plano.to_excel(writer, sheet_name="PLANO", index=False)
                st.download_button(
                    label="📥 Plano (.xlsx)",
                    data=bio.getvalue(),
                    file_name=f"plano_compras_egresos_{int(anio)}_{int(mes_idx):02d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )


# ------------------------------------------------------------
# Pestaña: Catálogo
# ------------------------------------------------------------

with tab_catalogo:
    st.markdown("### 📋 Catálogo embebido")
    st.caption("Editable en `core/data/catalogo_compras.json` — commit y Railway redespliega.")

    try:
        info = info_catalogo()
    except Exception as e:
        st.error(f"❌ No se pudo cargar el catálogo: {e}")
        info = None

    if info:
        col_m1, col_m2, col_m3 = st.columns(3)
        with col_m1:
            st.metric("Productos DS", info["total_productos"])
        with col_m2:
            st.metric("Bancos", info["total_bancos"])
        with col_m3:
            st.metric("Prov. consumo", info.get("total_proveedores_consumo", 0))

        st.caption(f"UVT 2026: ${info['uvt_2026']:,} · Base mínima retefuente servicios: "
                   f"${info['base_minima_retefuente']:,}".replace(",", "."))

        st.markdown("#### Productos DS (Comp 18)")
        df_prod = pd.DataFrame(info["productos"])
        st.dataframe(df_prod, use_container_width=True, hide_index=True)

        st.markdown("#### Bancos (cuenta especial Comp 13)")
        df_b = pd.DataFrame(info["bancos"])
        st.dataframe(df_b, use_container_width=True, hide_index=True)

        st.info(
            "💡 **Cuentas contables clave del módulo:**\n"
            "- `620505` → compras gravadas con IVA (Comp 3)\n"
            "- `620510` → compras NO gravadas con IVA (Comp 3)\n"
            "- `622505` → devoluciones en compra / NC (Comp 7)\n"
            "- `22050501` → proveedores nacionales (Cr en facturas)\n"
            "- `23359501` → acreedores costos y gastos (Cr en CEG normales)\n"
            "- `24080201` → IVA descontable por compras\n"
            "- `24080204` → IVA descontable reverso (NC)\n"
            "- `2365xxxx` → SOLO para cálculo de retefuente sobre bases legales"
        )
