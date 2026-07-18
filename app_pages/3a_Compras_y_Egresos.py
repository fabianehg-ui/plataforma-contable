"""
Módulo Compras y Egresos — Plataforma Web (v3.0 con FASE 2 retenciones).

Procesa 3 archivos relacionados y genera 4 comprobantes contables:

    📁 TOKEN DIAN.xlsx           → Comp 3 (Facturas) + Comp 7 (NC Proveedores)
    📁 DOCUMENTO_SOPORTE.xlsx     → Comp 18 (DS)
    📁 EGRESOS_CAJA_MENOR.xls     → Comp 13 (CEG)

Los 3 archivos son OPCIONALES — puedes subir solo los que necesites.

REGLA IMPORTANTE: Todos los valores en el plano son POSITIVOS.
El signo lo determina el TR (1=Débito, 2=Crédito).

NOVEDAD v3.0 — FASE 2:
  Retenciones automáticas en Compras DIAN. El sistema respeta lo que venga
  en el TOKEN (TOKEN manda) y, si no, calcula desde catálogo según el tipo
  de proveedor. Activable con el flag `aplicar_calculo_retenciones` del
  catálogo.
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
from db.supabase_client import get_supabase
from core.contable.ui_contabilizar import render_contabilizar
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

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
require_modulo("compras_y_egresos")
emp = require_rol(["admin", "operador"])
sb = get_supabase()


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
        | **{COMPROBANTE_COMPRAS}** | TOKEN (FE) | Db Compra+IVA · Cr Proveedor (neto) · Cr Retenciones |
        | **{COMPROBANTE_NC_PROVEEDORES}** | TOKEN (NC) | Db Proveedor · Db Reversos · Cr Devolución+IVA |
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
        - **🆕 Retefuente y ReteIVA automáticos**
        - **🆕 IVA por tipo:**
            - 24080201 → bienes (jurídica/natural)
            - 24080308 → servicios (honorarios, arrendamiento, etc.)

        ✅ **Comp 7 (NC):** 622505 (devolución en compra)
        - Reverso IVA siempre a 24080204
        - Reversos de retenciones cuando aplica

        ✅ **Comp 13 (CEG):**
        - Cancela DS → cuenta del proveedor del DS
        - Banco Caja Social → 11100501
        - Resto → 23359501

        ✅ **Comp 18 (DS):** según producto (catálogo)

        ⚠️ Las cuentas `2365xxxx` solo se usan como Cr
        en cálculo de retefuente sobre bases legales.
        """
    )

    st.markdown("---")
    st.info(
        "💡 **Consecutivo numérico:**\n\n"
        "Comp 3 (Facturas) y Comp 7 (NC) tienen "
        "**numeración independiente** desde v3.2. "
        "Cada uno usa **YYYYMMNNN** ordenado por fecha+folio dentro de su grupo. "
        "Comp 13 y Comp 18 mantienen su propio consecutivo del archivo."
    )


# ============================================================
# Pestañas
# ============================================================

tab_procesar, tab_catalogo, tab_retenciones = st.tabs([
    "📤 Procesar archivos",
    "📋 Catálogo",
    "💰 Retenciones (FASE 2)",
])


# ------------------------------------------------------------
# Pestaña: Procesar
# ------------------------------------------------------------

with tab_procesar:
    st.markdown("### 📤 Subir archivos del periodo")
    st.info(
        "📋 **Los 3 archivos son OPCIONALES.** Sube solo los que necesites procesar."
    )

    # Mostrar el modo actual de retenciones
    try:
        _info_quick = info_catalogo()
        _flag_calc = _info_quick.get("aplicar_calculo_retenciones", False)
        if _flag_calc:
            st.warning(
                "💰 **Cálculo automático de retenciones ACTIVO.** "
                "El sistema calculará retefuente/reteIVA desde catálogo "
                "cuando el TOKEN no las traiga."
            )
        else:
            st.caption(
                "ℹ️ Cálculo automático de retenciones **DESACTIVADO** (modo seguro). "
                "Solo se respetarán retenciones que vengan en el TOKEN. "
                "Para activar, edita `aplicar_calculo_retenciones: true` en el catálogo."
            )
    except Exception:
        pass

    # Selector de periodo
    col_p1, col_p2 = st.columns([1, 2])
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

    # Consecutivos independientes Comp 3 y Comp 7
    col_c3, col_c7 = st.columns(2)
    with col_c3:
        consec_c3 = st.number_input(
            "Consecutivo inicial Comp 3 (Facturas)",
            min_value=1, max_value=999,
            value=1,
            help="Numeración independiente para Compras DIAN. "
                 "Formato resultante: AAAAMMNNN (ej: 202604001).",
        )
    with col_c7:
        consec_c7 = st.number_input(
            "Consecutivo inicial Comp 7 (NC Proveedores)",
            min_value=1, max_value=999,
            value=1,
            help="Numeración independiente para Notas Crédito de proveedores. "
                 "Formato resultante: AAAAMMNNN (ej: 202604001).",
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
                    consecutivo_inicial_c3=int(consec_c3),
                    consecutivo_inicial_c7=int(consec_c7),
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

            # === Resumen de retenciones (FASE 2) ===
            total_rete = (
                resumen.get("total_retefuente", 0)
                + resumen.get("total_reteiva", 0)
                + resumen.get("total_reteica", 0)
            )
            if total_rete > 0:
                st.markdown("#### 💰 Retenciones aplicadas")
                col_r1, col_r2, col_r3 = st.columns(3)
                with col_r1:
                    st.metric(
                        "Retefuente",
                        f"$ {resumen.get('total_retefuente', 0):,}".replace(",", "."),
                    )
                with col_r2:
                    st.metric(
                        "ReteIVA",
                        f"$ {resumen.get('total_reteiva', 0):,}".replace(",", "."),
                    )
                with col_r3:
                    st.metric(
                        "ReteICA",
                        f"$ {resumen.get('total_reteica', 0):,}".replace(",", "."),
                    )

                detalle_ret = resumen.get("retenciones_detalle", [])
                if detalle_ret:
                    with st.expander(f"📋 Ver detalle por documento ({len(detalle_ret)} docs)"):
                        df_ret = pd.DataFrame(detalle_ret)
                        # Formatear columnas de monto
                        for col in ["subtotal", "iva", "rete_renta", "rete_iva", "rete_ica"]:
                            if col in df_ret.columns:
                                df_ret[col] = df_ret[col].apply(
                                    lambda v: f"$ {int(v):,}".replace(",", ".") if v else "—"
                                )
                        st.dataframe(df_ret, use_container_width=True, hide_index=True)

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

            # Causar en la contabilidad de la empresa (INTEGRAL)
            st.markdown("---")
            render_contabilizar(sb, emp, df_plano, "compras",
                                anio_default=int(anio), mes_default=int(mes_idx))


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
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("Productos DS", info["total_productos"])
        with col_m2:
            st.metric("Bancos", info["total_bancos"])
        with col_m3:
            st.metric("Prov. consumo", info.get("total_proveedores_consumo", 0))
        with col_m4:
            st.metric("Prov. retención", info.get("total_proveedores_retencion", 0))

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


# ------------------------------------------------------------
# Pestaña: Retenciones (FASE 2)
# ------------------------------------------------------------

with tab_retenciones:
    st.markdown("### 💰 Retenciones automáticas (FASE 2)")

    try:
        info = info_catalogo()
    except Exception as e:
        st.error(f"❌ No se pudo cargar el catálogo: {e}")
        info = None

    if info:
        flag = info.get("aplicar_calculo_retenciones", False)
        tipo_default = info.get("tipo_retencion_default", "juridica")
        n_provs = info.get("total_proveedores_retencion", 0)

        # Estado del modo
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            if flag:
                st.success("✅ Cálculo automático\n**ACTIVADO**")
            else:
                st.info("⏸️ Cálculo automático\n**DESACTIVADO** (modo seguro)")
        with col_s2:
            st.metric("Tipo default", tipo_default)
        with col_s3:
            st.metric("Proveedores catalogados", n_provs)

        st.markdown("---")

        # Explicación del flujo
        st.markdown("#### 🔄 Cómo funciona")
        st.markdown(
            """
            **Regla 1 — TOKEN manda.** Si el TOKEN DIAN ya trae valores en
            `rete_renta`, `rete_iva` o `rete_ica`, esos valores se respetan
            sin modificación (la DIAN es la fuente de verdad).

            **Regla 2 — Catálogo es el fallback.** Cuando el TOKEN no trae
            retención y el flag `aplicar_calculo_retenciones` está activo,
            el sistema busca el NIT del proveedor en el catálogo, identifica
            su tipo (jurídica, natural, honorarios, etc.) y aplica la tasa
            correspondiente — siempre que la base supere el mínimo legal.

            **Regla 3 — Default seguro.** Si un proveedor no aparece en el
            catálogo, se aplica el tipo default (`juridica` 2.5%) y se
            muestra una advertencia para que se catalogue.

            **Regla 4 — ICA del TOKEN.** El ReteICA siempre viene del
            TOKEN porque depende del municipio, no del tipo de proveedor.

            **Regla 5 — NC reversa.** Las notas crédito reversan
            correctamente las retenciones que se le aplicaron a la factura
            original (Db a 2365xxxx en lugar de Cr).

            **Regla 6 — Cuenta de IVA según tipo (v3.1).** El IVA descontable
            de la factura va a:
            - `24080201` para **bienes** (jurídica, natural, no catalogado)
            - `24080308` para **servicios** (honorarios, comisiones,
              arrendamiento, servicios_natural)

            En NC el reverso del IVA siempre va a `24080204`.
            """
        )

        st.markdown("---")
        st.markdown("#### 📋 Tipos de retención disponibles")

        tipos = info.get("tipos_retencion", [])
        if tipos:
            df_tipos = pd.DataFrame(tipos)
            df_tipos["base_min_pesos"] = df_tipos["base_min_pesos"].apply(
                lambda v: f"$ {int(v):,}".replace(",", ".") if v else "Sin mínimo"
            )
            st.dataframe(df_tipos, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### 🏢 Proveedores catalogados")

        provs = info.get("proveedores_retencion", [])
        if provs:
            df_provs = pd.DataFrame(provs)
            st.dataframe(df_provs, use_container_width=True, hide_index=True)
        else:
            st.warning(
                "⚠️ **El catálogo de proveedores está vacío.** "
                "Para que el cálculo automático funcione bien, edita "
                "`catalogo_compras.json` y agrega los NITs de tus proveedores "
                "principales en la sección `proveedores_retencion`. "
                "Los no catalogados recibirán el tipo default."
            )

        st.markdown("---")
        st.markdown("#### 📝 Cómo activar el cálculo automático")
        st.code(
            """// En core/data/catalogo_compras.json:

{
  "aplicar_calculo_retenciones": true,   // ← cambia a true
  "tipo_retencion_default": "juridica",
  "proveedores_retencion": [
    {
      "nit": "900123456",
      "nombre": "PROVEEDOR EJEMPLO SAS",
      "tipo": "juridica"
    },
    {
      "nit": "12345678",
      "nombre": "JUAN PEREZ",
      "tipo": "natural"
    },
    {
      "nit": "900987654",
      "nombre": "CONTADORA SAS",
      "tipo": "honorarios"
    }
    // ... agrega los proveedores principales
  ]
}""",
            language="json",
        )

        st.info(
            "💡 **Estrategia recomendada de migración:**\n\n"
            "1. **Mes 1:** Mantén `aplicar_calculo_retenciones: false`. Procesa el TOKEN normalmente. "
            "Identifica los NITs que aparecen recurrentemente en tus retes manuales.\n"
            "2. **Mes 2:** Catalógalos en `proveedores_retencion`. Sigue con flag en `false`.\n"
            "3. **Mes 3:** Activa `aplicar_calculo_retenciones: true`. Verifica que el plano "
            "resultante coincida con tus retenciones manuales habituales.\n"
            "4. **Mes 4 en adelante:** Sistema 100% automatizado. Solo agrega proveedores "
            "nuevos cuando aparezcan."
        )
