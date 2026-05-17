"""
app_pages/4b_Ingresos_POS.py

Módulo Ventas POS — versión simplificada.

Flujo:
  1️⃣ Subir los 4 reportes POS por separado (CHILI, L3AF, HENKO Milagros, HENKO Remedios)
  2️⃣ Procesar → plano contable
  3️⃣ Descargar plano (TXT/XLSX)
  4️⃣ [OPCIONAL] Conciliar contra Excel del Token DIAN → reporte de auditoría

El maestro de sucursales (DATOS PUNTO) se lee de `core/data/datos_punto.json`
del repo. No es necesario incluir hoja DATOS PUNTO en los Excel.
"""
from __future__ import annotations

import io
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa

from core.procesadores.procesador_pos import (
    procesar_pos,
    combinar_archivos_pos,
    dataframe_a_plano_tsv,
    info_datos_punto_embebido,
    datos_punto_embebido_a_xlsx,
)


# ─── Setup ───────────────────────────────────────────────────
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

st.title("🧾 Ventas POS")
st.caption(
    "Sube los reportes de cada sistema POS, genera el plano contable, y opcionalmente "
    "concilia contra el Token DIAN para auditoría."
)


# ─── Cargar info del DATOS PUNTO embebido ───────────────────
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


# ─── Banner DATOS PUNTO ─────────────────────────────────────
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
        "Maestro DATOS PUNTO embebido en el código (`core/data/datos_punto.json`). "
        "Si abren un punto nuevo o cambia una cuenta, contacta al desarrollador."
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


# ════════════════════════════════════════════════════════════
# PASO 1 — Subir los 4 reportes POS
# ════════════════════════════════════════════════════════════
st.markdown("## 1️⃣ Sube los reportes POS del mes")
st.caption(
    "Sube los 4 reportes que recibes de los sistemas POS. Puedes dejar vacíos "
    "los que no apliquen ese mes."
)

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
    st.info("📂 Sube al menos un reporte para continuar.")
    st.stop()


# ════════════════════════════════════════════════════════════
# PASO 2 — Procesar y generar plano
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 2️⃣ Procesar")

st.caption(
    f"Listos para procesar **{len(archivos_validos)}** reporte(s): "
    f"{', '.join(archivos_validos.keys())}"
)

if st.button("🚀 Procesar reportes POS", type="primary", use_container_width=True):
    with st.spinner("Combinando reportes con DATOS PUNTO..."):
        try:
            xlsx_dp = _xlsx_dp()
            excel_combinado = combinar_archivos_pos(
                archivo_datos_punto=xlsx_dp,
                reportes=archivos_validos,
            )
        except Exception as e:
            st.error(f"❌ Error combinando archivos: {e}")
            with st.expander("Detalle del error"):
                import traceback
                st.code(traceback.format_exc())
            st.stop()

    with st.spinner("Generando plano contable POS..."):
        try:
            df, log, sucs_no = procesar_pos(excel_combinado)
        except Exception as e:
            st.error(f"❌ Error procesando: {e}")
            with st.expander("Detalle del error"):
                import traceback
                st.code(traceback.format_exc())
            st.stop()

    st.session_state["pos_df"] = df
    st.session_state["pos_log"] = log
    st.session_state["pos_sucs_no"] = sucs_no


# ════════════════════════════════════════════════════════════
# Mostrar resultado del POS
# ════════════════════════════════════════════════════════════
if "pos_df" in st.session_state:
    df = st.session_state["pos_df"]
    log = st.session_state["pos_log"]
    sucs_no = st.session_state["pos_sucs_no"]

    st.markdown("---")
    st.markdown("## 📊 Resultado del plano POS")

    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Filas en plano", len(df))
    with col2:
        sucs_unicas = df["DETALLE"].nunique() if len(df) else 0
        st.metric("Sucursales", sucs_unicas)
    with col3:
        suma_db = int(df[df["TR"] == "1"]["VALOR"].astype(int).sum()) if len(df) else 0
        st.metric("Total Débitos", f"$ {suma_db:,.0f}".replace(",", "."))
    with col4:
        suma_cr = int(df[df["TR"] == "2"]["VALOR"].astype(int).sum()) if len(df) else 0
        st.metric("Total Créditos", f"$ {suma_cr:,.0f}".replace(",", "."))

    if len(df) > 0:
        if suma_db == suma_cr:
            st.success(f"✅ Cuadre perfecto: Db = Cr = $ {suma_db:,.0f}".replace(",", "."))
        else:
            diff = suma_db - suma_cr
            st.error(f"❌ DESCUADRE: diferencia $ {diff:,.0f}".replace(",", "."))

    with st.expander("📝 Log de procesamiento", expanded=False):
        for linea in log:
            st.text(linea)

    if sucs_no:
        with st.expander(f"⚠️ {len(sucs_no)} sucursal(es) descartada(s)", expanded=True):
            st.caption(
                "Aparecieron en los reportes pero NO están en el maestro. "
                "Pídele al desarrollador que las agregue a `core/data/datos_punto.json`."
            )
            df_no_enc = pd.DataFrame([
                {
                    "Sucursal detectada": s["nombre"],
                    "Hoja": s["hoja"],
                    "Motivo": s.get("motivo", "-"),
                    "Total ignorado": f"$ {s['total_aproximado']:,.0f}".replace(",", "."),
                }
                for s in sucs_no
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

    # ════════════════════════════════════════════════════════
    # PASO 3 — Descargar plano POS
    # ════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 3️⃣ Descargar plano POS")

    tsv_bytes = dataframe_a_plano_tsv(df, incluir_encabezado_excel=False)
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.download_button(
            "📥 Plano (.txt)",
            data=tsv_bytes,
            file_name="plano_pos.txt",
            mime="text/tab-separated-values",
            type="primary",
            use_container_width=True,
        )
    with col_d2:
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        st.download_button(
            "📊 Plano (.xlsx)",
            data=buffer.getvalue(),
            file_name="plano_pos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    # ════════════════════════════════════════════════════════
    # PASO 4 — Conciliación opcional con Token DIAN
    # ════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 4️⃣ Auditoría comparativa contra Token DIAN")
    st.caption(
        "Opcional: sube el Excel del Token DIAN para generar el reporte de "
        "auditoría con base POS vs base Token Neta por sucursal y clase."
    )

    archivo_token = st.file_uploader(
        "Sube el archivo .xlsx exportado del portal DIAN con tu Token",
        type=["xlsx"],
        key="up_token_audit",
    )

    if archivo_token is not None:
        # Imports diferidos
        from core.procesadores import lector_excel_token as lex
        from core.procesadores import comparativo_pos_token_v2 as cmp_aud

        # Cargar mapeo completo
        RUTA_MAPEO = ROOT / "mapeo_prefijos_token.json"
        if not RUTA_MAPEO.exists():
            st.error(
                "❌ Falta archivo `mapeo_prefijos_token.json` en la raíz del repo. "
                "Sin ese archivo no se puede hacer la comparativa."
            )
        else:
            with open(RUTA_MAPEO) as _f:
                _mapeo_raw = json.load(_f)
            MAPEO_COMPLETO = {}
            for _item in _mapeo_raw.get("mapeos", []):
                MAPEO_COMPLETO[_item["prefijo"].upper()] = {
                    "cc": _item.get("cc", ""),
                    "nombre": _item.get("sede", ""),
                    "sede": _item.get("sede", ""),
                    "clase": _item.get("clase", ""),
                    "tipo": _item.get("tipo", "venta"),
                }

            try:
                with st.spinner("📖 Leyendo Excel del Token..."):
                    df_token = lex.leer_excel_token(archivo_token)
                st.success(f"✅ Token leído: {len(df_token):,} documentos.")
            except Exception as e:
                st.error(f"❌ Error leyendo Token: {e}")
                st.stop()

            # Filtro de fechas para el comparativo
            fechas = df_token["fecha_emision"].dropna()
            f_min = fechas.min().date() if len(fechas) > 0 else date.today()
            f_max = fechas.max().date() if len(fechas) > 0 else date.today()

            col_fa, col_fb = st.columns(2)
            with col_fa:
                f_desde = st.date_input(
                    "Desde",
                    value=f_min, min_value=f_min, max_value=f_max,
                    format="YYYY-MM-DD", key="audit_desde",
                )
            with col_fb:
                f_hasta = st.date_input(
                    "Hasta",
                    value=f_max, min_value=f_min, max_value=f_max,
                    format="YYYY-MM-DD", key="audit_hasta",
                )

            df_token_filt = lex.filtrar_por_rango(df_token, f_desde, f_hasta)
            df_emit = df_token_filt[df_token_filt["grupo"].str.lower() == "emitido"]

            if st.button("🔍 Generar reporte de auditoría", use_container_width=True):
                with st.spinner("Construyendo comparativo POS vs Token Neto..."):
                    try:
                        base_pos_cc = cmp_aud.extraer_base_pos_por_sucursal(df)
                        df_comp = cmp_aud.construir_comparativo(
                            df_emit, base_pos_cc, MAPEO_COMPLETO,
                        )
                        st.session_state["audit_df"] = df_comp
                        st.session_state["audit_fdesde"] = f_desde
                        st.session_state["audit_fhasta"] = f_hasta
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
                        with st.expander("Detalle"):
                            import traceback
                            st.code(traceback.format_exc())

            if "audit_df" in st.session_state:
                df_comp = st.session_state["audit_df"]
                fd = st.session_state["audit_fdesde"]
                fh = st.session_state["audit_fhasta"]

                st.markdown("### 📊 Reporte de auditoría")

                df_disp = df_comp.copy()
                for c in ["Base POS", "Base Token FE", "Base NC Token", "Token Neto", "Diferencia"]:
                    if c in df_disp.columns:
                        df_disp[c] = df_disp[c].apply(
                            lambda v: f"${v:,.0f}" if pd.notna(v) and v != "" else ""
                        )
                if "Efectividad %" in df_disp.columns:
                    df_disp["Efectividad %"] = df_disp["Efectividad %"].apply(
                        lambda v: f"{v:.2f}%" if pd.notna(v) else "—"
                    )

                st.dataframe(df_disp, use_container_width=True, hide_index=True, height=600)

                buf = io.BytesIO()
                df_comp.to_excel(buf, index=False, engine="openpyxl")
                buf.seek(0)
                st.download_button(
                    "⬇️ Descargar reporte de auditoría (Excel)",
                    data=buf.getvalue(),
                    file_name=f"auditoria_pos_vs_token_{fd}_a_{fh}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )


# ─── Reset ──────────────────────────────────────────────────
st.markdown("---")
if st.button("🔄 Limpiar y procesar otro mes"):
    for k in ["pos_df", "pos_log", "pos_sucs_no", "audit_df", "audit_fdesde", "audit_fhasta"]:
        st.session_state.pop(k, None)
    st.rerun()
