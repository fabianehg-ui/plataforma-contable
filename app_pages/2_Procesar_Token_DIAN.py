"""
app_pages/2_Procesar_Token_DIAN.py

Módulo unificado de procesamiento DIAN:
  - Sube Excel POS (Henko/Quinto Sentido) → procesa con procesador_pos antiguo
  - Sube Excel Token DIAN → procesa con procesador_ventas_excel_token
  - Genera plano contable: a elegir POS o Token
  - Genera comparativo de auditoría: Base POS vs Token Neto por sucursal y clase
  - Genera lista de CUFEs MIXTAS para descargar XMLs en la extensión Chrome
"""
from __future__ import annotations

import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa

from core.procesadores import lector_excel_token as lex
from core.procesadores import procesador_ventas_excel_token as pve     # v1, legacy
from core.procesadores import procesador_ventas_excel_token_v2 as pve2 # v2 nuevo
from core.procesadores import comparativo_pos_token_v2 as cmp_aud
from core.procesadores import generador_listas_cufes as glc

# Procesador POS antiguo (Henko/Quinto Sentido)
try:
    from core.procesadores.procesador_pos import procesar_pos as procesar_pos_antiguo
    POS_DISPONIBLE = True
except ImportError as e:
    POS_DISPONIBLE = False
    POS_ERROR = str(e)


# ─── Setup ───────────────────────────────────────────────────
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

st.title("📥 Procesar DIAN")
st.caption("Cierre contable mensual + comparativo de auditoría POS vs Token DIAN.")

NIT_EMPRESA = (empresa.get("nit") if empresa else None) or "901038325"

# Cargar mapeos
RUTA_MAPEO = ROOT / "mapeo_prefijos_token.json"
if not RUTA_MAPEO.exists():
    st.error(f"❌ No se encontró el archivo de mapeo: {RUTA_MAPEO}")
    st.stop()

MAPEO_VENTAS = pve.cargar_mapeo_desde_json(str(RUTA_MAPEO))
MAPEO_COMPLETO = pve.cargar_mapeo_completo(str(RUTA_MAPEO))


# ─── Helpers ─────────────────────────────────────────────────

def _ofrecer_descarga_plano(df, fuente, f_desde, f_hasta):
    """Genera TSV + XLSX y los ofrece para descarga. Valida cuadre."""
    plano = df.copy()
    plano["VALOR"] = pd.to_numeric(plano["VALOR"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
    deb = plano[plano["TR"].astype(str) == "1"]["VALOR"].sum()
    cre = plano[plano["TR"].astype(str) == "2"]["VALOR"].sum()
    diff = abs(deb - cre)
    if diff < 100:
        st.success(f"✅ Plano cuadra: Db ${deb:,.0f} = Cr ${cre:,.0f}")
    else:
        st.error(f"⚠️ Plano NO cuadra: Db ${deb:,.0f} ≠ Cr ${cre:,.0f} (dif ${diff:,.0f})")

    tsv = df.to_csv(sep="\t", index=False).encode("utf-8-sig")
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.download_button(
            f"⬇️ Plano TSV",
            data=tsv,
            file_name=f"plano_{fuente}_{f_desde}_a_{f_hasta}.tsv",
            mime="text/tab-separated-values",
            use_container_width=True,
            key=f"dl_tsv_{fuente}",
        )
    with col_d2:
        st.download_button(
            f"⬇️ Plano Excel",
            data=buf.getvalue(),
            file_name=f"plano_{fuente}_{f_desde}_a_{f_hasta}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"dl_xlsx_{fuente}",
        )


def _extraer_plano_pos(pos_obj):
    """Extrae el DataFrame del resultado del procesador POS (que puede tener varios formatos)."""
    if pos_obj is None:
        return None
    if isinstance(pos_obj, tuple):
        return pos_obj[0]
    if isinstance(pos_obj, pd.DataFrame):
        return pos_obj
    if hasattr(pos_obj, "plano_df"):
        return pos_obj.plano_df
    # Como último recurso, si es algo iterable buscar el primer DataFrame
    if hasattr(pos_obj, "__iter__"):
        for x in pos_obj:
            if isinstance(x, pd.DataFrame):
                return x
    return None


# ============================================================
# SECCIÓN 1: SUBIR ARCHIVOS
# ============================================================
st.markdown("## 📁 Paso 1 — Sube los archivos del mes")

col_a, col_b = st.columns(2)
with col_a:
    st.markdown("### 🏪 Excel POS")
    archivo_pos = st.file_uploader(
        "Henko / Quinto Sentido (multi-hoja)",
        type=["xlsx", "xlsm"],
        key="up_pos",
    )
    if archivo_pos:
        st.success(f"✅ POS: {archivo_pos.name}")

with col_b:
    st.markdown("### 🧾 Excel Token DIAN")
    archivo_token = st.file_uploader(
        "Exportar a Excel del portal DIAN",
        type=["xlsx"],
        key="up_token",
    )
    if archivo_token:
        st.success(f"✅ Token: {archivo_token.name}")


# Procesar POS si está subido
if archivo_pos is not None and "pos_resultado" not in st.session_state:
    if not POS_DISPONIBLE:
        st.error(f"❌ El procesador POS antiguo no está disponible: {POS_ERROR}")
    else:
        with st.spinner("Procesando reporte POS..."):
            try:
                # procesar_pos_antiguo recibe bytes y devuelve (df_plano, log)
                resultado_pos = procesar_pos_antiguo(archivo_pos.read())
                st.session_state["pos_resultado"] = resultado_pos
                st.success("✅ POS procesado")
            except Exception as e:
                st.error(f"❌ Error procesando POS: {e}")
                with st.expander("Detalle"):
                    import traceback
                    st.code(traceback.format_exc())

# Procesar Token si está subido
if archivo_token is not None and "token_df" not in st.session_state:
    with st.spinner("Leyendo Excel del Token..."):
        try:
            df_token = lex.leer_excel_token(archivo_token)
            st.session_state["token_df"] = df_token
            st.success(f"✅ Token leído: {len(df_token):,} documentos.")
        except Exception as e:
            st.error(f"❌ Error leyendo Token: {e}")

# Si nada está subido aún, detener acá
if "pos_resultado" not in st.session_state and "token_df" not in st.session_state:
    st.info("☝️ Sube al menos uno de los archivos para continuar.")
    st.stop()


# ============================================================
# SECCIÓN 2: FILTRO DE RANGO (si hay Token)
# ============================================================
st.markdown("---")
st.markdown("## 📅 Paso 2 — Rango de fechas a procesar")

if "token_df" in st.session_state:
    df_token = st.session_state["token_df"]
    fechas = df_token["fecha_emision"].dropna()
    fecha_min = fechas.min().date() if len(fechas) > 0 else date.today()
    fecha_max = fechas.max().date() if len(fechas) > 0 else date.today()
else:
    fecha_min = date(2026, 1, 1)
    fecha_max = date.today()

col_f1, col_f2 = st.columns(2)
with col_f1:
    f_desde = st.date_input("Desde", value=fecha_min, min_value=fecha_min, max_value=fecha_max, format="YYYY-MM-DD")
with col_f2:
    f_hasta = st.date_input("Hasta", value=fecha_max, min_value=fecha_min, max_value=fecha_max, format="YYYY-MM-DD")


# ============================================================
# SECCIÓN 3: PROCESAR TOKEN (si está)
# ============================================================
if "token_df" in st.session_state:
    df_token = st.session_state["token_df"]
    df_token_filt = lex.filtrar_por_rango(df_token, f_desde, f_hasta)
    df_token_emit = df_token_filt[df_token_filt["grupo"].str.lower() == "emitido"]

    st.markdown("---")
    st.markdown("## 🧾 Paso 3 — Procesar Token DIAN")

    if st.button("⚙️ Procesar Token", use_container_width=True, type="primary"):
        with st.spinner("Procesando con consolidación POS + STL + DSE..."):
            res_token = pve2.procesar_ventas_v2(
                df_token_filt,
                str(RUTA_MAPEO),
                str(ROOT / "mapeo_dse_conceptos.json"),
            )
        st.session_state["token_resultado"] = res_token
        st.session_state["token_emit_filt"] = df_token_filt[df_token_filt["grupo"].str.lower() == "emitido"]
        st.session_state["token_filt_full"] = df_token_filt

    if "token_resultado" in st.session_state:
        rv = st.session_state["token_resultado"]
        res = rv.resumen()

        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Asientos POS (consolidados)", f"{res['asientos_pos']:,}")
        col_m2.metric("STL detalladas", f"{res['stl_detalladas']:,}")
        col_m3.metric("NCs STL", f"{res['ncs_stl_detalladas']:,}")
        col_m4.metric("DSE procesados", f"{res['dse_procesados']:,}")

        col_m5, col_m6, col_m7, col_m8 = st.columns(4)
        col_m5.metric("Base POS", f"${res['total_base_pos']:,.0f}")
        col_m6.metric("Base STL", f"${res['total_base_stl']:,.0f}")
        col_m7.metric("Total DSE", f"${res['total_dse']:,.0f}")
        col_m8.metric("Líneas plano", f"{res['lineas_plano']:,}")

        st.caption(
            f"💡 Propina omitida (10%): ${res['total_propina_pos']:,.0f} · "
            f"NCs POS: ${res['total_nc_base_pos']:,.0f}"
        )

        if res["dse_sin_concepto"]:
            with st.expander(f"⚠️ {res['dse_sin_concepto']} DSE sin concepto mapeado", expanded=False):
                st.caption(
                    "Agrega estos NITs al archivo `mapeo_dse_conceptos.json` con su concepto correspondiente "
                    "(ARRENDAMIENTOS, SERVICIOS_PROFESIONALES, TRANSPORTE, etc.)"
                )
                nits_no_map = {}
                for f in rv.sin_concepto_dse:
                    k = (f.nit_receptor, f.nombre_receptor)
                    nits_no_map[k] = nits_no_map.get(k, 0) + 1
                df_no_map = pd.DataFrame([
                    {"NIT": nit, "Nombre": n, "Docs": c}
                    for (nit, n), c in sorted(nits_no_map.items(), key=lambda x: -x[1])
                ])
                st.dataframe(df_no_map, use_container_width=True, hide_index=True)

        if res["mixtas"]:
            st.warning(f"⚠️ {res['mixtas']} MIXTAS — descargar XML (sección al final)")
        if res["sin_sucursal"]:
            st.warning(f"⚠️ {res['sin_sucursal']} sin sucursal mapeada")


# ============================================================
# SECCIÓN 4: GENERAR PLANO CONTABLE
# ============================================================
hay_pos = "pos_resultado" in st.session_state
hay_token = "token_resultado" in st.session_state

if hay_pos or hay_token:
    st.markdown("---")
    st.markdown("## 📄 Paso 4 — Generar plano contable")

    opciones = []
    if hay_pos:    opciones.append("Desde POS (reporte Henko)")
    if hay_token:  opciones.append("Desde Token DIAN")
    if not opciones:
        st.info("Procesa al menos POS o Token para generar plano.")
    else:
        eleccion = st.radio("¿Qué fuente uso para el plano?", opciones, horizontal=True)

        if "Desde POS" in eleccion:
            plano_df = _extraer_plano_pos(st.session_state["pos_resultado"])
            if plano_df is None or len(plano_df) == 0:
                st.warning("El plano POS está vacío.")
            else:
                st.success(f"✅ Plano POS: {len(plano_df):,} líneas")
                _ofrecer_descarga_plano(plano_df, "pos", f_desde, f_hasta)
        else:  # Desde Token
            rv = st.session_state["token_resultado"]
            if rv.plano_df is None or len(rv.plano_df) == 0:
                st.warning("El plano Token está vacío.")
            else:
                st.success(f"✅ Plano Token: {len(rv.plano_df):,} líneas")
                _ofrecer_descarga_plano(rv.plano_df, "token", f_desde, f_hasta)


# ============================================================
# SECCIÓN 5: COMPARATIVO DE AUDITORÍA
# ============================================================
if hay_pos and hay_token:
    st.markdown("---")
    st.markdown("## 🔍 Paso 5 — Comparativo de auditoría POS vs Token")
    st.caption("Compara base POS (cajas) vs base Token neta (FE − NC) por sucursal, "
               "con subtotales por clase (SANTA LEÑA, RESTAURANTE MILAGROS, STL).")

    if st.button("🔍 Generar comparativo", use_container_width=True):
        plano_pos = _extraer_plano_pos(st.session_state["pos_resultado"])
        if plano_pos is None or len(plano_pos) == 0:
            st.error("No hay plano POS para extraer la base.")
        else:
            base_pos_por_cc = cmp_aud.extraer_base_pos_por_sucursal(plano_pos)
            df_token_emit = st.session_state["token_emit_filt"]
            with st.spinner("Construyendo comparativo..."):
                df_comp = cmp_aud.construir_comparativo(df_token_emit, base_pos_por_cc, MAPEO_COMPLETO)
            st.session_state["comparativo_df"] = df_comp

    if "comparativo_df" in st.session_state:
        df_comp = st.session_state["comparativo_df"]

        df_disp = df_comp.copy()
        for c in ["Base POS", "Base Token FE", "Base NC Token", "Token Neto", "Diferencia"]:
            df_disp[c] = df_disp[c].apply(lambda v: f"${v:,.0f}" if pd.notna(v) and v != "" else "")
        df_disp["Efectividad %"] = df_disp["Efectividad %"].apply(
            lambda v: f"{v:.2f}%" if pd.notna(v) else "—"
        )

        st.dataframe(df_disp, use_container_width=True, hide_index=True)

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


# ============================================================
# SECCIÓN 6: LISTAS DE CUFEs MIXTAS (para extensión Chrome)
# ============================================================
if "token_filt_full" in st.session_state:
    st.markdown("---")
    st.markdown("## 🗂️ Paso 6 — Lista de CUFEs MIXTAS para XML")
    st.caption("Compras y ventas que NO tienen tarifa de IVA deducible desde el Excel. "
               "Estas necesitan descargar XML para clasificación detallada.")

    if st.button("📋 Calcular MIXTAS"):
        with st.spinner("Analizando..."):
            df_filt = st.session_state["token_filt_full"]
            st.session_state["lista_compras_mixtas"] = glc.generar_lista_compras_mixtas(df_filt)
            st.session_state["lista_ventas_mixtas"] = glc.generar_lista_ventas_mixtas(df_filt)

    if "lista_compras_mixtas" in st.session_state:
        lc = st.session_state["lista_compras_mixtas"]
        lv = st.session_state["lista_ventas_mixtas"]

        col_x, col_y = st.columns(2)
        with col_x:
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
                    f"⬇️ Lista compras MIXTAS",
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    file_name=f"cufes_compras_mixtas_{f_desde}_a_{f_hasta}.json",
                    mime="application/json",
                    use_container_width=True,
                )

        with col_y:
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
                    f"⬇️ Lista ventas MIXTAS",
                    data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    file_name=f"cufes_ventas_mixtas_{f_desde}_a_{f_hasta}.json",
                    mime="application/json",
                    use_container_width=True,
                )

        st.info(
            f"💡 Esos {len(lc) + len(lv):,} XMLs son los que necesitas descargar "
            f"con la extensión Chrome (~{(len(lc) + len(lv)) / 8 / 60:.1f} min)."
        )


# ─── Reset ──────────────────────────────────────────────────
st.markdown("---")
if st.button("🔄 Limpiar y procesar otro mes"):
    for k in ["pos_resultado", "token_df", "token_resultado", "token_emit_filt",
              "token_filt_full", "comparativo_df", "lista_compras_mixtas",
              "lista_ventas_mixtas"]:
        st.session_state.pop(k, None)
    st.rerun()
