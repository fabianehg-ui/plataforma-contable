"""
app_pages/2_Procesar_Token_DIAN.py

MÓDULO ÚNICO: Procesar DIAN

Flujo lineal:
  1️⃣ Cargar Excel del Token DIAN (obligatorio)
  2️⃣ Filtrar rango de fechas
  3️⃣ Procesar Token (genera plano contable consolidado)
  4️⃣ Descargar plano contable Token (TSV o Excel)
  5️⃣ [Opcional] Cargar Excel POS para AUDITORÍA comparativa
  6️⃣ Generar listas MIXTAS para extensión Chrome
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

from core.procesadores import lector_excel_token as lex
from core.procesadores import procesador_ventas_excel_token_v2 as pve2
from core.procesadores import comparativo_pos_token_v2 as cmp_aud
from core.procesadores import generador_listas_cufes as glc

# Importar procesador POS antiguo (puede fallar si faltan dependencias)
try:
    from core.procesadores.procesador_pos import procesar_pos as procesar_pos_antiguo
    POS_OK = True
    POS_ERR = ""
except Exception as e:
    POS_OK = False
    POS_ERR = str(e)


# ─── Auth y setup ────────────────────────────────────────────
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()
NIT_EMPRESA = (empresa.get("nit") if empresa else None) or "901038325"

st.title("📥 Procesar DIAN")
st.caption("Cierre contable mensual desde el Excel del Token DIAN, con auditoría opcional contra POS.")


# ─── Verificar archivos de configuración ─────────────────────
RUTA_MAPEO = ROOT / "mapeo_prefijos_token.json"
RUTA_DSE = ROOT / "mapeo_dse_conceptos.json"

if not RUTA_MAPEO.exists():
    st.error(f"❌ Falta archivo de configuración: `mapeo_prefijos_token.json` (debe estar en la raíz del repo, al nivel de Home.py).")
    st.stop()
if not RUTA_DSE.exists():
    st.error(f"❌ Falta archivo de configuración: `mapeo_dse_conceptos.json` (debe estar en la raíz del repo).")
    st.stop()

# Cargar mapeo completo (ventas + NCs) para el comparativo
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
        "comprobante": _item.get("comprobante", ""),
        "cuenta_caja": _item.get("cuenta_caja", ""),
        "cta_base_v": _item.get("cta_base_v", ""),
        "cta_ico": _item.get("cta_ico", ""),
    }


# ════════════════════════════════════════════════════════════
# PASO 1 — Cargar Excel Token DIAN
# ════════════════════════════════════════════════════════════
st.markdown("## 1️⃣ Excel del Token DIAN")

archivo_token = st.file_uploader(
    "Sube el archivo .xlsx exportado del portal DIAN con tu Token",
    type=["xlsx"],
    key="up_token_v6",
)

if archivo_token is not None and "token_df" not in st.session_state:
    try:
        with st.spinner("📖 Leyendo Excel..."):
            df_token = lex.leer_excel_token(archivo_token)
        st.session_state["token_df"] = df_token
    except Exception as e:
        st.error(f"❌ Error leyendo Token: {e}")
        st.stop()

if "token_df" not in st.session_state:
    st.info("⬆️ Sube el Excel del Token para continuar.")
    st.stop()

df_token = st.session_state["token_df"]
st.success(f"✅ Excel cargado: **{len(df_token):,}** documentos totales.")


# ════════════════════════════════════════════════════════════
# PASO 2 — Rango de fechas
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 2️⃣ Rango de fechas")

fechas = df_token["fecha_emision"].dropna()
fecha_min = fechas.min().date() if len(fechas) > 0 else date.today()
fecha_max = fechas.max().date() if len(fechas) > 0 else date.today()

col_f1, col_f2 = st.columns(2)
with col_f1:
    f_desde = st.date_input("Desde", value=fecha_min, min_value=fecha_min, max_value=fecha_max, format="YYYY-MM-DD")
with col_f2:
    f_hasta = st.date_input("Hasta", value=fecha_max, min_value=fecha_min, max_value=fecha_max, format="YYYY-MM-DD")

df_token_filt = lex.filtrar_por_rango(df_token, f_desde, f_hasta)
df_emit = df_token_filt[df_token_filt["grupo"].str.lower() == "emitido"]
df_recb = df_token_filt[df_token_filt["grupo"].str.lower() == "recibido"]

st.caption(f"📦 En rango: **{len(df_token_filt):,}** docs ({len(df_emit):,} emitidos, {len(df_recb):,} recibidos)")


# ════════════════════════════════════════════════════════════
# PASO 3 — Procesar Token
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 3️⃣ Procesar Token DIAN")

if st.button("⚙️ Procesar Token (consolidado POS + STL + DSE)", type="primary", use_container_width=True):
    with st.spinner("Procesando..."):
        try:
            res = pve2.procesar_ventas_v2(df_token_filt, str(RUTA_MAPEO), str(RUTA_DSE))
            st.session_state["token_res"] = res
        except Exception as e:
            st.error(f"❌ Error: {e}")
            with st.expander("Detalle"):
                import traceback
                st.code(traceback.format_exc())


if "token_res" in st.session_state:
    rv = st.session_state["token_res"]
    res = rv.resumen()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Asientos POS", f"{res['asientos_pos']:,}")
    c2.metric("STL detalladas", f"{res['stl_detalladas']:,}")
    c3.metric("DSE procesados", f"{res['dse_procesados']:,}")
    c4.metric("Líneas plano", f"{res['lineas_plano']:,}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Base POS", f"${res['total_base_pos']:,.0f}")
    c6.metric("INC 8%", f"${res['total_inc_pos']:,.0f}")
    c7.metric("Base STL", f"${res['total_base_stl']:,.0f}")
    c8.metric("Total DSE", f"${res['total_dse']:,.0f}")

    st.caption(
        f"Propina omitida: ${res['total_propina_pos']:,.0f} · "
        f"NCs POS: ${res['total_nc_base_pos']:,.0f} · "
        f"MIXTAS: {res['mixtas']}"
    )

    if res["dse_sin_concepto"]:
        with st.expander(f"⚠️ {res['dse_sin_concepto']} DSE sin concepto mapeado", expanded=False):
            st.caption("Agrega estos NITs a `mapeo_dse_conceptos.json` con su concepto.")
            nits = {}
            for f in rv.sin_concepto_dse:
                k = (f.nit_receptor, f.nombre_receptor)
                nits[k] = nits.get(k, 0) + 1
            df_no = pd.DataFrame([
                {"NIT": nit, "Nombre": n, "Docs": c}
                for (nit, n), c in sorted(nits.items(), key=lambda x: -x[1])
            ])
            st.dataframe(df_no, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════
# PASO 4 — Descargar plano contable Token
# ════════════════════════════════════════════════════════════
if "token_res" in st.session_state:
    rv = st.session_state["token_res"]
    if rv.plano_df is not None and len(rv.plano_df) > 0:
        st.markdown("---")
        st.markdown("## 4️⃣ Descargar plano contable Token")

        # Validar cuadre
        plano = rv.plano_df.copy()
        plano["V"] = pd.to_numeric(plano["VALOR"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
        deb = plano[plano["TR"] == "1"]["V"].sum()
        cre = plano[plano["TR"] == "2"]["V"].sum()
        diff = abs(deb - cre)
        if diff < 100:
            st.success(f"✅ Plano cuadra: Db ${deb:,.0f} = Cr ${cre:,.0f}  (dif ${diff:,.0f} de redondeo)")
        else:
            st.error(f"⚠️ Plano NO cuadra: dif ${diff:,.0f}")

        tsv = rv.plano_df.to_csv(sep="\t", index=False).encode("utf-8-sig")
        buf = io.BytesIO()
        rv.plano_df.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)

        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                f"⬇️ Plano TSV ({len(rv.plano_df):,} líneas)",
                data=tsv,
                file_name=f"plano_token_{f_desde}_a_{f_hasta}.tsv",
                mime="text/tab-separated-values",
                use_container_width=True,
            )
        with d2:
            st.download_button(
                f"⬇️ Plano Excel ({len(rv.plano_df):,} líneas)",
                data=buf.getvalue(),
                file_name=f"plano_token_{f_desde}_a_{f_hasta}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )


# ════════════════════════════════════════════════════════════
# PASO 5 — Auditoría comparativa POS vs Token (OPCIONAL)
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 5️⃣ Auditoría comparativa POS vs Token")
st.caption(
    "Sube el Excel POS (Henko/Quinto Sentido) para generar el reporte de auditoría. "
    "**Solo se usa para el comparativo** — no genera plano contable POS aquí."
)

if not POS_OK:
    st.error(f"⚠️ Procesador POS no disponible: {POS_ERR}")
else:
    archivo_pos = st.file_uploader(
        "Excel POS multi-hoja (Henko / Quinto Sentido / Milagros)",
        type=["xlsx", "xlsm"],
        key="up_pos_v6",
    )

    if archivo_pos is not None and "pos_res" not in st.session_state:
        with st.spinner("Procesando POS para extraer bases por sucursal..."):
            try:
                df_plano_pos, log_pos, sucs_no = procesar_pos_antiguo(archivo_pos)
                st.session_state["pos_res"] = {
                    "plano": df_plano_pos,
                    "log": log_pos,
                    "sucs_no": sucs_no,
                }
            except Exception as e:
                st.error(f"❌ Error procesando POS: {e}")
                with st.expander("Detalle del error", expanded=True):
                    import traceback
                    st.code(traceback.format_exc())

    if "pos_res" in st.session_state:
        pos_data = st.session_state["pos_res"]
        df_plano_pos = pos_data["plano"]

        if df_plano_pos is None or len(df_plano_pos) == 0:
            st.warning("⚠️ El procesador POS no generó líneas. Revisa el log.")
            with st.expander("Log del procesador POS", expanded=True):
                st.code("\n".join(pos_data.get("log", [])))
        else:
            st.success(f"✅ POS procesado: {len(df_plano_pos):,} líneas")

            if pos_data.get("sucs_no"):
                with st.expander(f"⚠️ {len(pos_data['sucs_no'])} sucursales POS no encontradas en DATOS PUNTO"):
                    st.json(pos_data["sucs_no"][:30])

            with st.expander("📋 Log del procesador POS"):
                st.code("\n".join(pos_data.get("log", [])))

            # Generar comparativo si tenemos ambos
            if "token_res" in st.session_state:
                if st.button("🔍 Generar reporte de auditoría", use_container_width=True):
                    with st.spinner("Construyendo comparativo..."):
                        base_pos_cc = cmp_aud.extraer_base_pos_por_sucursal(df_plano_pos)
                        df_comp = cmp_aud.construir_comparativo(df_emit, base_pos_cc, MAPEO_COMPLETO)
                        st.session_state["comp_df"] = df_comp

                if "comp_df" in st.session_state:
                    df_comp = st.session_state["comp_df"]
                    st.markdown("### 📊 Reporte de auditoría")

                    # Mostrar tabla formateada
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

                    # Descargar Excel
                    buf = io.BytesIO()
                    df_comp.to_excel(buf, index=False, engine="openpyxl")
                    buf.seek(0)
                    st.download_button(
                        "⬇️ Descargar reporte auditoría (Excel)",
                        data=buf.getvalue(),
                        file_name=f"auditoria_pos_vs_token_{f_desde}_a_{f_hasta}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
            else:
                st.info("☝️ Procesa primero el Token (paso 3) para habilitar el comparativo.")


# ════════════════════════════════════════════════════════════
# PASO 6 — Lista CUFEs MIXTAS (descarga XML por extensión Chrome)
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 6️⃣ Lista de CUFEs MIXTAS (para extensión Chrome)")
st.caption("Compras y ventas con mezcla de tarifas IVA. Necesitan XML para clasificación detallada.")

if st.button("📋 Calcular MIXTAS"):
    with st.spinner("Analizando..."):
        st.session_state["mix_compras"] = glc.generar_lista_compras_mixtas(df_token_filt)
        st.session_state["mix_ventas"] = glc.generar_lista_ventas_mixtas(df_token_filt)

if "mix_compras" in st.session_state:
    lc = st.session_state["mix_compras"]
    lv = st.session_state["mix_ventas"]

    cx, cy = st.columns(2)
    with cx:
        st.metric("Compras MIXTAS", f"{len(lc):,}")
        if lc:
            payload = {
                "meta": {
                    "rol": "recibidos_mixtas",
                    "fecha_desde": str(f_desde),
                    "fecha_hasta": str(f_hasta),
                    "total_cufes": len(lc),
                },
                "cufes": lc,
            }
            st.download_button(
                "⬇️ Lista compras MIXTAS",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                file_name=f"cufes_compras_mixtas_{f_desde}_a_{f_hasta}.json",
                mime="application/json",
                use_container_width=True,
            )

    with cy:
        st.metric("Ventas MIXTAS", f"{len(lv):,}")
        if lv:
            payload = {
                "meta": {
                    "rol": "emitidos_mixtas",
                    "fecha_desde": str(f_desde),
                    "fecha_hasta": str(f_hasta),
                    "total_cufes": len(lv),
                },
                "cufes": lv,
            }
            st.download_button(
                "⬇️ Lista ventas MIXTAS",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                file_name=f"cufes_ventas_mixtas_{f_desde}_a_{f_hasta}.json",
                mime="application/json",
                use_container_width=True,
            )

    if lc or lv:
        st.info(
            f"💡 Total: {len(lc) + len(lv):,} XMLs a descargar con la extensión Chrome "
            f"(~{(len(lc) + len(lv)) / 8 / 60:.1f} min)."
        )


# ─── Reset ──────────────────────────────────────────────────
st.markdown("---")
if st.button("🔄 Limpiar y procesar otro mes"):
    for k in list(st.session_state.keys()):
        if k.startswith(("token_", "pos_", "comp_", "mix_")):
            st.session_state.pop(k, None)
    st.rerun()
