"""
app_pages/2_Procesar_Token_DIAN.py

MÓDULO: Procesar DIAN

Flujo lineal:
  1️⃣ Cargar Excel del Token DIAN
  2️⃣ Filtrar rango de fechas
  3️⃣ Procesar Token VENTAS (plano contable consolidado)
  4️⃣ Descargar plano de VENTAS
  5️⃣ Procesar COMPRAS (con retenciones según régimen + concepto + fecha)
  6️⃣ Generar listas MIXTAS para extensión Chrome
  7️⃣ Maestro de Terceros - lista CUFEs únicos por proveedor
  8️⃣ Cargar XMLs y actualizar maestro (régimen, dirección, ciudad)

NOTA: la auditoría POS vs Token está en el módulo "Ventas POS" (4b).
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
from core.procesadores import procesador_compras_excel_token as pcom
from core.procesadores import generador_listas_cufes as glc
from core.procesadores import maestro_terceros as mt
from core.procesadores import procesador_xmls_zip as pxz


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
RUTA_COMPRAS = ROOT / "mapeo_compras_historico.json"
RUTA_TABLA_RET = ROOT / "tabla_retenciones.json"
RUTA_MAPEO_CONCEPTO = ROOT / "mapeo_cuenta_a_concepto_retencion.json"
RUTA_MAESTRO = ROOT / "maestro_terceros.json"

if not RUTA_MAPEO.exists():
    st.error(f"❌ Falta `mapeo_prefijos_token.json` en la raíz del repo.")
    st.stop()
if not RUTA_DSE.exists():
    st.error(f"❌ Falta `mapeo_dse_conceptos.json` en la raíz del repo.")
    st.stop()
COMPRAS_OK = RUTA_COMPRAS.exists()
RETENCIONES_OK = RUTA_TABLA_RET.exists() and RUTA_MAPEO_CONCEPTO.exists()
if not COMPRAS_OK:
    st.warning(
        "⚠️ Falta `mapeo_compras_historico.json`. Sin él no se procesan compras."
    )

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
# PASO 5 — Procesar COMPRAS desde Token
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 5️⃣ Procesar COMPRAS del Token")
st.caption(
    "Genera el plano contable de COMPRAS recibidas, con cuenta de gasto asignada "
    "automáticamente desde el balance histórico de proveedores. "
    "Las compras con tarifa MIXTA se separan para descargar XML."
)

if not COMPRAS_OK:
    st.info(
        "⚠️ No se ha cargado `mapeo_compras_historico.json` en el repo. "
        "Sube ese archivo a la raíz para activar el procesamiento de compras."
    )
else:
    if st.button("🛒 Procesar Compras", use_container_width=True):
        with st.spinner("Clasificando compras, asignando cuentas y calculando retenciones..."):
            try:
                if RETENCIONES_OK:
                    # v2 con retenciones
                    ruta_maestro = str(RUTA_MAESTRO) if RUTA_MAESTRO.exists() else None
                    res_compras = pcom.procesar_compras_v2(
                        df_token_filt,
                        str(RUTA_COMPRAS),
                        str(RUTA_TABLA_RET),
                        str(RUTA_MAPEO_CONCEPTO),
                        ruta_maestro,
                    )
                    st.session_state["compras_version"] = "v2"
                else:
                    # v1 sin retenciones (fallback)
                    res_compras = pcom.procesar_compras_v1(
                        df_token_filt,
                        str(RUTA_COMPRAS),
                    )
                    st.session_state["compras_version"] = "v1"
                st.session_state["compras_res"] = res_compras
            except Exception as e:
                st.error(f"❌ Error procesando compras: {e}")
                with st.expander("Detalle"):
                    import traceback
                    st.code(traceback.format_exc())

    if "compras_res" in st.session_state:
        rc = st.session_state["compras_res"]
        resc = rc.resumen()

        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("Procesadas", f"{resc['procesadas']:,}")
        cc2.metric("MIXTAS", f"{resc['mixtas']:,}", "XML pendiente")
        cc3.metric("Sin cuenta", f"{resc['sin_cuenta']:,}")
        cc4.metric("NCs recibidas", f"{resc['notas_credito']:,}")

        cc5, cc6, cc7, cc8 = st.columns(4)
        cc5.metric("Base", f"${resc['total_base']:,.0f}")
        cc6.metric("IVA descontable", f"${resc['total_iva']:,.0f}")
        cc7.metric("Total facturado", f"${resc['total_facturado']:,.0f}")
        cc8.metric("Líneas plano", f"{resc['lineas_plano']:,}")

        # Cuadre
        if rc.plano_df is not None and len(rc.plano_df) > 0:
            p = rc.plano_df.copy()
            p["V"] = pd.to_numeric(p["VALOR"], errors="coerce").fillna(0)
            deb = p[p["TR"] == "1"]["V"].sum()
            cre = p[p["TR"] == "2"]["V"].sum()
            diff = abs(deb - cre)
            if diff < 100:
                st.success(f"✅ Plano compras cuadra: Db ${deb:,.0f} = Cr ${cre:,.0f}")
            else:
                st.error(f"⚠️ Plano NO cuadra: dif ${diff:,.0f}")

            # Desglose por tarifa
            with st.expander("📊 Desglose por tarifa", expanded=False):
                tdf = pd.DataFrame([
                    {"Tarifa": t, "Docs": n}
                    for t, n in sorted(resc["por_tarifa"].items(), key=lambda x: -x[1])
                ])
                st.dataframe(tdf, use_container_width=True, hide_index=True)

            # Top proveedores y top cuentas
            with st.expander("📍 Top 20 proveedores", expanded=False):
                provs = sorted(resc["por_proveedor"].items(), key=lambda x: -x[1]["total"])[:20]
                df_prov = pd.DataFrame([
                    {
                        "NIT": nit,
                        "Proveedor": info["nombre"][:40],
                        "Docs": info["docs"],
                        "Base": f"${info['base']:,.0f}",
                        "IVA": f"${info['iva']:,.0f}",
                        "Total": f"${info['total']:,.0f}",
                        "Cuenta": info["cuenta"],
                        "Concepto": (info["cuenta_nombre"] or "")[:30],
                    }
                    for nit, info in provs
                ])
                st.dataframe(df_prov, use_container_width=True, hide_index=True)

            with st.expander("📊 Top cuentas de gasto utilizadas", expanded=False):
                cuentas = sorted(resc["por_cuenta"].items(), key=lambda x: -x[1]["total_base"])[:15]
                df_cta = pd.DataFrame([
                    {
                        "Cuenta": cta,
                        "Concepto": info["nombre"][:40],
                        "Docs": info["docs"],
                        "Base": f"${info['total_base']:,.0f}",
                    }
                    for cta, info in cuentas
                ])
                st.dataframe(df_cta, use_container_width=True, hide_index=True)

            # Sin cuenta — para que Luz los mapee
            if resc["sin_cuenta"] > 0:
                with st.expander(f"⚠️ {resc['sin_cuenta']} compras sin cuenta histórica", expanded=False):
                    st.caption(
                        "Estos NITs son nuevos (no aparecen en tu balance). "
                        "Agrégalos al archivo `mapeo_compras_historico.json` "
                        "para que se procesen automáticamente."
                    )
                    sc_data = {}
                    for c in rc.sin_cuenta:
                        k = (c.nit_emisor, c.nombre_emisor)
                        if k not in sc_data:
                            sc_data[k] = {"docs": 0, "total": 0}
                        sc_data[k]["docs"] += 1
                        sc_data[k]["total"] += c.total
                    df_sc = pd.DataFrame([
                        {
                            "NIT": nit,
                            "Nombre": nombre,
                            "Docs": v["docs"],
                            "Total": f"${v['total']:,.0f}",
                        }
                        for (nit, nombre), v in sorted(sc_data.items(),
                                                       key=lambda x: -x[1]["total"])
                    ])
                    st.dataframe(df_sc, use_container_width=True, hide_index=True)

            # Retenciones aplicadas (solo si usó v2)
            if st.session_state.get("compras_version") == "v2" and hasattr(rc, "retenciones_aplicadas"):
                st.markdown("### 🔻 Retenciones aplicadas")
                rcol1, rcol2, rcol3 = st.columns(3)
                rcol1.metric("Retefuente total", f"${rc.total_retefuente:,.0f}")
                rcol2.metric("ReteIVA total", f"${rc.total_reteiva:,.0f}")
                rcol3.metric("Docs con retención", f"{len(rc.retenciones_aplicadas):,}")

                if rc.retenciones_aplicadas:
                    with st.expander("📋 Detalle de retenciones por concepto", expanded=False):
                        from collections import Counter
                        ctos = Counter(r["concepto"] for r in rc.retenciones_aplicadas)
                        df_ret_c = pd.DataFrame([
                            {
                                "Concepto": c,
                                "Docs": n,
                                "Total retef": f"${sum(r['retefuente'] for r in rc.retenciones_aplicadas if r['concepto']==c):,.0f}",
                                "Total reteIVA": f"${sum(r['reteiva'] for r in rc.retenciones_aplicadas if r['concepto']==c):,.0f}",
                            }
                            for c, n in ctos.most_common()
                        ])
                        st.dataframe(df_ret_c, use_container_width=True, hide_index=True)

                    with st.expander("🔍 Top 30 retenciones aplicadas", expanded=False):
                        top_r = sorted(rc.retenciones_aplicadas,
                                       key=lambda r: -(r["retefuente"]+r["reteiva"]))[:30]
                        df_top_r = pd.DataFrame([
                            {
                                "NIT": r["nit"],
                                "Nombre": r["nombre"][:40],
                                "Régimen": r["regimen"],
                                "Concepto": r["concepto"],
                                "Retefuente": f"${r['retefuente']:,.0f}",
                                "ReteIVA": f"${r['reteiva']:,.0f}",
                            }
                            for r in top_r
                        ])
                        st.dataframe(df_top_r, use_container_width=True, hide_index=True)

                # Aviso si no hay maestro
                if not RUTA_MAESTRO.exists():
                    st.info(
                        "💡 **Para refinar retenciones**: el sistema asumió todos los proveedores "
                        "como **R-99-PN declarantes** (les retuvo a todos). Sube los XMLs de los "
                        "269 proveedores únicos en el paso 7 para identificar autorretenedores, "
                        "régimen simple y grandes contribuyentes — el siguiente mes ya las exclusiones "
                        "se aplican automáticamente."
                    )

            # Descargar plano de compras
            st.markdown("### 📥 Descargar plano de COMPRAS")
            tsv = rc.plano_df.to_csv(sep="\t", index=False).encode("utf-8-sig")
            buf = io.BytesIO()
            rc.plano_df.to_excel(buf, index=False, engine="openpyxl")
            buf.seek(0)

            d1, d2 = st.columns(2)
            with d1:
                st.download_button(
                    f"⬇️ Compras TSV ({len(rc.plano_df):,} líneas)",
                    data=tsv,
                    file_name=f"plano_compras_token_{f_desde}_a_{f_hasta}.tsv",
                    mime="text/tab-separated-values",
                    use_container_width=True,
                )
            with d2:
                st.download_button(
                    f"⬇️ Compras Excel ({len(rc.plano_df):,} líneas)",
                    data=buf.getvalue(),
                    file_name=f"plano_compras_token_{f_desde}_a_{f_hasta}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )


# ════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════
# PASO 6 — Generar listas JSON para extensión Chrome
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 6️⃣ (Opcional) Listas JSON para extensión Chrome")
st.caption(
    "📌 Esta sección es opcional. Solo úsala si vas a descargar los XMLs con la "
    "extensión Chrome (flujo antiguo). La descarga directa desde la plataforma "
    "está más abajo y es el flujo recomendado."
)
st.caption(
    "Las extensión descarga XMLs en un **ZIP plano** (sin anidación). "
    "Aquí generas las listas JSON con los CUFEs que la extensión necesita."
)

if st.button("📋 Calcular listas de CUFEs"):
    with st.spinner("Analizando..."):
        st.session_state["lista_compras_mixtas"] = glc.generar_lista_compras_mixtas(df_token_filt)
        st.session_state["lista_ventas_mixtas"] = glc.generar_lista_ventas_mixtas(df_token_filt)
        st.session_state["lista_stl_completa"] = glc.generar_lista_stl_completa(
            df_token_filt, f_desde, f_hasta
        )
        # Proveedores únicos: filtrar contra maestro Y contra histórico de compras
        maestro_actual = mt.cargar_maestro_terceros(str(RUTA_MAESTRO)) if RUTA_MAESTRO.exists() else {"terceros": {}}
        mapeo_historico_actual = {}
        if RUTA_COMPRAS.exists():
            with open(RUTA_COMPRAS, encoding="utf-8") as _f:
                mapeo_historico_actual = json.load(_f)
        st.session_state["lista_proveedores_unicos"] = glc.generar_lista_proveedores_unicos(
            df_token_filt, maestro_actual, mapeo_historico_actual
        )
        st.session_state["lista_todas_compras"] = glc.generar_lista_todas_compras_unicas(
            df_token_filt, f_desde, f_hasta, maestro_actual
        )
        st.session_state["lista_todos_recibidos"] = glc.generar_lista_todos_recibidos(
            df_token_filt, f_desde, f_hasta
        )

if "lista_compras_mixtas" in st.session_state:
    lc = st.session_state["lista_compras_mixtas"]
    lv = st.session_state["lista_ventas_mixtas"]
    ls = st.session_state["lista_stl_completa"]
    lp = st.session_state["lista_proveedores_unicos"]
    lt = st.session_state.get("lista_todas_compras", [])
    lr = st.session_state.get("lista_todos_recibidos", [])

    st.markdown("### Listas disponibles")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "🆕 **TODOS recibidos**",
        f"{len(lr):,}",
        help="100% de documentos recibidos del mes: FE, NC, ND, DSE, doc equivalentes. Lista nueva para descargar absolutamente todo lo que entra a contabilidad por compras.",
    )
    c2.metric("Compras MIXTAS", f"{len(lc):,}")
    c3.metric("Ventas MIXTAS", f"{len(lv):,}")
    c4, c5, c6 = st.columns(3)
    c4.metric("STL completas", f"{len(ls):,}")
    c5.metric("Proveedores nuevos", f"{len(lp):,}")
    c6.metric("Compras p/régimen", f"{len(lt):,}", help="Todas las compras únicas para detectar autorretenedores")

    # Lista 0 (NUEVA — flujo principal): TODOS los recibidos del mes
    if lr:
        # Breakdown por tipo de documento para que veas qué viene
        from collections import Counter
        tipos_count = Counter(item.get("tipo_documento", "?") for item in lr)
        tipos_resumen = ", ".join(f"{tipo}: {n}" for tipo, n in tipos_count.most_common())
        st.caption(f"📊 Desglose por tipo: {tipos_resumen}")

        payload = {
            "meta": {
                "rol": "todos_recibidos",
                "descripcion": "100% de documentos RECIBIDOS del mes (FE, NC, ND, DSE, doc equivalentes). Excluye Application Response y Nómina Individual.",
                "fecha_desde": str(f_desde),
                "fecha_hasta": str(f_hasta),
                "total_cufes": len(lr),
                "desglose_tipos": dict(tipos_count),
            },
            "cufes": [item["cufe"] for item in lr],
        }
        st.download_button(
            f"⬇️ **JSON TODOS Recibidos** ({len(lr)})",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            file_name=f"lista_todos_recibidos_{f_desde}_a_{f_hasta}.json",
            mime="application/json",
            use_container_width=True,
            type="primary",
            help="Descarga el 100% de XMLs recibidos del mes para procesarlos al detalle (incluye FE, NC, ND, DSE).",
        )

    # Lista 1: Compras MIXTAS
    if lc:
        payload = {
            "meta": {
                "rol": "compras_mixtas",
                "descripcion": "Compras con MIXTA tarifa IVA - requieren XML para discriminar",
                "fecha_desde": str(f_desde),
                "fecha_hasta": str(f_hasta),
                "total_cufes": len(lc),
            },
            "cufes": lc,
        }
        st.download_button(
            f"⬇️ JSON Compras MIXTAS ({len(lc)})",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            file_name=f"lista_compras_mixtas_{f_desde}_a_{f_hasta}.json",
            mime="application/json",
            use_container_width=True,
        )

    # Lista 2: Ventas MIXTAS
    if lv:
        payload = {
            "meta": {
                "rol": "ventas_mixtas",
                "descripcion": "Ventas con MIXTA tarifa IVA",
                "fecha_desde": str(f_desde),
                "fecha_hasta": str(f_hasta),
                "total_cufes": len(lv),
            },
            "cufes": lv,
        }
        st.download_button(
            f"⬇️ JSON Ventas MIXTAS ({len(lv)})",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            file_name=f"lista_ventas_mixtas_{f_desde}_a_{f_hasta}.json",
            mime="application/json",
            use_container_width=True,
        )

    # Lista 3: STL completas
    if ls:
        payload = {
            "meta": {
                "rol": "stl_completa",
                "descripcion": "TODAS las STL emitidas (parseo detallado IVA por línea)",
                "fecha_desde": str(f_desde),
                "fecha_hasta": str(f_hasta),
                "total_cufes": len(ls),
            },
            "cufes": ls,
        }
        st.download_button(
            f"⬇️ JSON STL completas ({len(ls)})",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            file_name=f"lista_stl_completa_{f_desde}_a_{f_hasta}.json",
            mime="application/json",
            use_container_width=True,
        )

    # Lista 4: Proveedores únicos
    if lp:
        payload = {
            "meta": {
                "rol": "proveedores_unicos",
                "descripcion": "1 CUFE por NIT proveedor nuevo (extracción de régimen + dirección)",
                "fecha_desde": str(f_desde),
                "fecha_hasta": str(f_hasta),
                "total_cufes": len(lp),
            },
            "cufes": [item["cufe"] for item in lp],
        }
        st.download_button(
            f"⬇️ JSON Proveedores únicos ({len(lp)})",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            file_name=f"lista_proveedores_unicos_{f_desde}_a_{f_hasta}.json",
            mime="application/json",
            use_container_width=True,
        )

    # Lista 5: TODAS las compras únicas para detectar régimen (autorretenedores)
    if lt:
        payload = {
            "meta": {
                "rol": "compras_regimen",
                "descripcion": "1 CUFE por NIT (TODOS los proveedores del mes) para detectar régimen real desde XML y evitar retef a autorretenedores como EPM/Postobón",
                "fecha_desde": str(f_desde),
                "fecha_hasta": str(f_hasta),
                "total_cufes": len(lt),
            },
            "cufes": [item["cufe"] for item in lt],
        }
        st.download_button(
            f"⬇️ JSON Compras p/régimen ({len(lt)})",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            file_name=f"lista_compras_regimen_{f_desde}_a_{f_hasta}.json",
            mime="application/json",
            use_container_width=True,
            help="Descarga TODOS los XML únicos de compras para detectar el régimen real de cada proveedor (O-15 autorretenedor, etc.). Imprescindible para evitar aplicar retef a EPM y similares.",
        )

    total = len(lc) + len(lv) + len(ls) + len(lp) + len(lt) + len(lr)
    if total > 0:
        st.info(
            f"💡 Total: {total:,} XMLs para descargar con la extensión Chrome "
            f"(~{total / 8 / 60:.1f} min)."
        )

# ════════════════════════════════════════════════════════════
# PASO 6.5 — Descarga DIRECTA desde DIAN (con paralelismo)
# ════════════════════════════════════════════════════════════
# Flujo simplificado:
#   1. Pegas la URL del Token DIAN
#   2. Eliges Emitidos (STL+DSE) o Recibidos (todos)
#   3. La plataforma calcula cuántos hilos paralelos necesita
#      (ceil(total / 700)) y descarga simultáneamente
#   4. Si un hilo detecta sesión expirada → todos paran y reportan
#   5. Se muestra DICTAMEN: lista Excel vs descargados (con faltantes)
#   6. Botón para procesar al plano contable o reintentar faltantes
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 🚀 Descarga DIRECTA desde DIAN")

if "lista_compras_mixtas" not in st.session_state:
    st.caption("⚠️ Primero genera las listas en el paso 6 ⬆️")
else:
    from core.procesadores import descargador_dian as dd

    # Estado por tipo de descarga (emitidos vs recibidos)
    # Cada tipo conserva su propio estado para no perder progreso al cambiar
    for _tipo in ("emitidos", "recibidos"):
        _key = f"dian_dl_{_tipo}"
        if _key not in st.session_state:
            st.session_state[_key] = {
                "zips_por_cufe": {},
                "fallidos": [],
                "progresos_hilos": [],
                "lista_origen": [],     # lista del Excel para el dictamen
                "dictamen": None,
            }

    # Generar las 2 listas siempre que haya df_token_filt
    lr = st.session_state.get("lista_todos_recibidos", [])
    le_stl_dse = glc.generar_lista_emitidos_stl_y_dse(df_token_filt, f_desde, f_hasta)
    st.session_state["lista_emitidos_stl_dse"] = le_stl_dse

    # ─── URL del Token ───
    st.markdown("### 1️⃣ Pega la URL del Token DIAN")
    token_url = st.text_input(
        "URL completa del Token (de catalogo-vpfe.dian.gov.co)",
        placeholder="https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=...&rk=...&token=...",
        key="dian_token_url_v2",
        type="password",
        help="Genera un Token desde el portal DIAN y pega aquí la URL completa.",
    )

    # ─── 2 botones lado a lado ───
    st.markdown("### 2️⃣ Elige qué descargar")

    import math as _math
    n_emit = len(le_stl_dse)
    n_recb = len(lr)
    hilos_emit = max(1, _math.ceil(n_emit / 700)) if n_emit else 0
    hilos_recb = max(1, _math.ceil(n_recb / 700)) if n_recb else 0

    col_em, col_rc = st.columns(2)

    # ─── Función reutilizable para ejecutar la descarga ───
    def _ejecutar_descarga(tipo_str, lista_excel_completa):
        """Ejecuta descarga paralela y guarda en session_state."""
        if not token_url:
            st.error("Pega primero la URL del Token DIAN")
            return
        cufes = [it["cufe"] for it in lista_excel_completa if it.get("cufe")]
        if not cufes:
            st.warning("No hay CUFEs para descargar.")
            return

        estado = st.session_state[f"dian_dl_{tipo_str}"]

        # Si hay descarga previa, descargar solo los faltantes del Excel
        ya_descargados = set(estado["zips_por_cufe"].keys())
        cufes_pendientes = [c for c in cufes if c not in ya_descargados]
        if not cufes_pendientes:
            st.info("Ya está todo descargado para este tipo. Limpia el progreso si quieres rehacer.")
            return

        # Placeholders para progreso en vivo
        progreso_placeholder = st.empty()

        def on_prog(progresos):
            with progreso_placeholder.container():
                st.markdown(f"#### Progreso en vivo — {len(progresos)} hilo(s)")
                for p in progresos:
                    rango_label = f"Hilo {p.hilo_id} ({p.rango_desde}-{p.rango_hasta})"
                    total_hilo = p.rango_hasta - p.rango_desde + 1
                    pct = (p.procesados / total_hilo) if total_hilo else 0
                    estado_icon = {
                        "pendiente": "⏳",
                        "descargando": "⬇️",
                        "ok": "✅",
                        "sesion_expirada": "⚠️",
                        "error": "❌",
                    }.get(p.estado, "❓")
                    st.progress(
                        pct,
                        text=f"{estado_icon} {rango_label}: {p.procesados}/{total_hilo} "
                             f"(ok={p.exitosos}, fail={p.fallidos}) {p.mensaje[:40]}"
                    )

        try:
            with st.spinner(f"Descargando {len(cufes_pendientes):,} XMLs en paralelo..."):
                res, progresos_final = dd.descargar_paralelo_por_bloques(
                    token_url,
                    cufes_pendientes,
                    tam_bloque=700,
                    delay=0.15,
                    on_progress=on_prog,
                    parar_todos_si_uno_falla=True,
                )

            # Acumular en el estado
            estado["zips_por_cufe"].update(res.exitosos)
            estado["fallidos"].extend(res.fallidos)
            estado["progresos_hilos"] = [
                {
                    "hilo_id": p.hilo_id,
                    "rango_desde": p.rango_desde,
                    "rango_hasta": p.rango_hasta,
                    "procesados": p.procesados,
                    "exitosos": p.exitosos,
                    "fallidos": p.fallidos,
                    "estado": p.estado,
                    "mensaje": p.mensaje,
                }
                for p in progresos_final
            ]
            estado["lista_origen"] = lista_excel_completa
            estado["dictamen"] = dd.generar_dictamen(
                lista_excel_completa,
                set(estado["zips_por_cufe"].keys()),
                estado["fallidos"],
            )

            progreso_placeholder.empty()

            if res.motivo_parada == "completo":
                st.success(
                    f"🎉 Descarga COMPLETA: {res.total_exitosos:,} XMLs "
                    f"({res.duracion_seg:.0f}s)"
                )
            elif res.motivo_parada == "sesion_expirada":
                st.warning(
                    f"⚠️ La sesión DIAN expiró en uno o más hilos. "
                    f"Total descargado: {len(estado['zips_por_cufe']):,}. "
                    f"Genera un Token nuevo y vuelve a darle al botón "
                    f"para descargar los faltantes."
                )
            else:
                st.info(f"Descarga parcial: {res.total_exitosos} OK. Motivo: {res.motivo_parada}")
            st.rerun()
        except dd.SesionExpirada as e:
            st.error(f"❌ Token inválido o expirado al autenticar: {e}")
        except ValueError as e:
            st.error(f"❌ URL inválida: {e}")
        except Exception as e:
            st.error(f"❌ Error inesperado: {e}")
            import traceback
            with st.expander("Detalle"):
                st.code(traceback.format_exc())

    with col_em:
        st.markdown(f"**📤 EMITIDOS (STL + DSE)**")
        st.metric("Documentos en Excel", f"{n_emit:,}")
        st.caption(f"→ {hilos_emit} hilo(s) paralelo(s) de hasta 700 docs")
        descargados_em = len(st.session_state["dian_dl_emitidos"]["zips_por_cufe"])
        if descargados_em > 0:
            st.caption(f"✅ Ya descargados: {descargados_em:,}")
        if st.button(
            "⬇️ Descargar emitidos",
            key="btn_dl_emitidos_v2",
            use_container_width=True,
            type="primary",
            disabled=not token_url or n_emit == 0,
        ):
            _ejecutar_descarga("emitidos", le_stl_dse)

    with col_rc:
        st.markdown(f"**📥 RECIBIDOS (todos)**")
        st.metric("Documentos en Excel", f"{n_recb:,}")
        st.caption(f"→ {hilos_recb} hilo(s) paralelo(s) de hasta 700 docs")
        descargados_rc = len(st.session_state["dian_dl_recibidos"]["zips_por_cufe"])
        if descargados_rc > 0:
            st.caption(f"✅ Ya descargados: {descargados_rc:,}")
        if st.button(
            "⬇️ Descargar recibidos",
            key="btn_dl_recibidos_v2",
            use_container_width=True,
            type="primary",
            disabled=not token_url or n_recb == 0,
        ):
            _ejecutar_descarga("recibidos", lr)

    # ─── Mostrar DICTAMEN para cada tipo que tenga descarga ───
    for tipo_str, label_emoji in [("emitidos", "📤 EMITIDOS"), ("recibidos", "📥 RECIBIDOS")]:
        estado = st.session_state[f"dian_dl_{tipo_str}"]
        if not estado["zips_por_cufe"] and not estado["fallidos"]:
            continue

        st.markdown(f"---")
        st.markdown(f"### 📋 Dictamen — {label_emoji}")

        dict_resultado = estado["dictamen"]
        if not dict_resultado:
            # Recalcular dictamen por si cambió el Excel
            dict_resultado = dd.generar_dictamen(
                estado["lista_origen"],
                set(estado["zips_por_cufe"].keys()),
                estado["fallidos"],
            )
            estado["dictamen"] = dict_resultado

        tot = dict_resultado["totales"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📋 Excel", f"{tot['total_esperado']:,}")
        c2.metric("✅ Descargados", f"{tot['descargados']:,}",
                  f"{tot['pct_completado']:.1f}%")
        c3.metric("❌ Faltantes", f"{tot['faltantes']:,}")
        c4.metric("💰 Valor descargado",
                  f"${tot['sum_descargado']:,.0f}",
                  f"de ${tot['sum_esperado']:,.0f}")

        # Tabla de faltantes (si los hay)
        if tot["faltantes"] > 0:
            with st.expander(f"📋 Ver {tot['faltantes']} documentos faltantes", expanded=True):
                if dict_resultado["desglose_tipos_faltantes"]:
                    desg = ", ".join(f"{t}: {n}" for t, n in dict_resultado["desglose_tipos_faltantes"].items())
                    st.caption(f"Desglose por tipo: {desg}")

                df_falt = pd.DataFrame(dict_resultado["tabla_faltantes"])
                if not df_falt.empty:
                    cols_mostrar = [c for c in
                                    ["cufe", "folio", "prefijo", "tipo_documento",
                                     "fecha_emision", "nombre_emisor", "total", "razon_fallo"]
                                    if c in df_falt.columns]
                    st.dataframe(df_falt[cols_mostrar], use_container_width=True, hide_index=True)

                # Descargar Excel del dictamen
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as xlw:
                    df_falt.to_excel(xlw, sheet_name="Faltantes", index=False)
                    pd.DataFrame([tot]).T.to_excel(xlw, sheet_name="Resumen", header=False)
                st.download_button(
                    f"⬇️ Excel del dictamen ({tipo_str})",
                    data=buf.getvalue(),
                    file_name=f"dictamen_{tipo_str}_{f_desde}_a_{f_hasta}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_dictamen_{tipo_str}",
                )

        # ─── Procesar al plano contable ───
        if tot["descargados"] > 0:
            st.markdown(f"#### ⚙️ Procesar al plano contable")
            if st.button(
                f"▶️ Procesar {tot['descargados']:,} XMLs descargados de {tipo_str}",
                key=f"btn_proc_{tipo_str}",
                use_container_width=True,
            ):
                with st.spinner("Generando ZIP consolidado y procesando..."):
                    zip_consol = dd.juntar_zips(estado["zips_por_cufe"])
                    try:
                        if tipo_str == "emitidos":
                            # STL emitidas → procesador STL
                            res_proc = pxz.procesar_zip_stl(
                                zip_consol,
                                str(RUTA_MAPEO),
                                str(RUTA_DSE),
                            )
                            st.session_state[f"res_proc_{tipo_str}"] = res_proc
                        else:
                            # Recibidos → procesador compras mixtas (incluye NC/ND/DSE)
                            # Primero actualizar maestro
                            maestro = mt.cargar_maestro_terceros(str(RUTA_MAESTRO)) if RUTA_MAESTRO.exists() else {"_meta": {}, "terceros": {}}
                            resumen_maestro = pxz.procesar_zip_para_maestro(zip_consol, maestro)
                            mt.guardar_maestro_terceros(maestro, str(RUTA_MAESTRO))

                            res_proc = pxz.procesar_zip_compras_mixtas(
                                zip_consol,
                                str(RUTA_COMPRAS),
                                str(RUTA_TABLA_RET),
                                str(RUTA_MAPEO_CONCEPTO),
                                str(RUTA_MAESTRO) if RUTA_MAESTRO.exists() else None,
                            )
                            st.session_state[f"res_proc_{tipo_str}"] = res_proc
                            st.session_state[f"resumen_maestro_{tipo_str}"] = resumen_maestro
                    except Exception as e:
                        st.error(f"❌ Error procesando: {e}")
                        import traceback
                        with st.expander("Detalle"):
                            st.code(traceback.format_exc())

            # Mostrar resultado del procesamiento si existe
            if f"res_proc_{tipo_str}" in st.session_state:
                res_proc = st.session_state[f"res_proc_{tipo_str}"]
                r_info = res_proc.resumen() if hasattr(res_proc, "resumen") else {}
                st.success(f"✅ {r_info.get('facturas_procesadas', 0):,} documentos procesados al plano contable")

                if res_proc.plano_df is not None and len(res_proc.plano_df) > 0:
                    tsv = res_proc.plano_df.to_csv(sep="\t", index=False, encoding="utf-8")
                    st.download_button(
                        f"⬇️ Plano contable {tipo_str} (TSV)",
                        data=tsv.encode("utf-8"),
                        file_name=f"plano_{tipo_str}_{f_desde}_a_{f_hasta}.tsv",
                        mime="text/tab-separated-values",
                        key=f"dl_plano_{tipo_str}",
                        use_container_width=True,
                    )

        # ─── Resetear ───
        with st.expander(f"🗑️ Limpiar descarga de {tipo_str}"):
            if st.button(f"⚠️ Borrar todo lo descargado de {tipo_str}",
                         key=f"reset_{tipo_str}"):
                st.session_state[f"dian_dl_{tipo_str}"] = {
                    "zips_por_cufe": {},
                    "fallidos": [],
                    "progresos_hilos": [],
                    "lista_origen": [],
                    "dictamen": None,
                }
                st.session_state.pop(f"res_proc_{tipo_str}", None)
                st.rerun()


# ════════════════════════════════════════════════════════════
# PASO 7 — Subir ZIPs descargados y procesar
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 7️⃣ (Opcional) Subir ZIPs descargados con extensión")
st.caption(
    "📌 Solo si descargaste con la extensión Chrome. Si usaste la descarga "
    "directa, el procesamiento ya se hace en esa misma sección."
)
st.caption(
    "Sube el ZIP plano que descargó la extensión Chrome. Cada ZIP tiene un rol "
    "diferente. La plataforma detecta el tipo y procesa en consecuencia."
)

tab1, tab2, tab3, tab4 = st.tabs([
    "🧾 STL completas",
    "🔀 Compras MIXTAS",
    "🔀 Ventas MIXTAS",
    "👥 Proveedores → Maestro",
])

# ─── Tab 1: STL ────────────────────────────────────────────
with tab1:
    st.markdown("**Procesar ZIP de STL emitidas** → genera plano contable detallado con IVA por línea.")
    stl_zip = st.file_uploader(
        "ZIP de XMLs de STL",
        type=["zip"],
        key="stl_zip",
    )
    if stl_zip and st.button("⚙️ Procesar STL", key="btn_stl", use_container_width=True):
        with st.spinner("Procesando..."):
            try:
                res = pxz.procesar_zip_stl(stl_zip.read())
                st.session_state["res_stl"] = res
            except Exception as e:
                st.error(f"❌ Error: {e}")
                import traceback
                with st.expander("Detalle"):
                    st.code(traceback.format_exc())

    if "res_stl" in st.session_state:
        res = st.session_state["res_stl"]
        r = res.resumen()
        st.success(f"✅ {r['facturas_procesadas']:,} STL procesadas")
        c1, c2, c3 = st.columns(3)
        c1.metric("Facturas", f"{r['facturas_procesadas']:,}")
        c2.metric("Total facturado", f"${r['total_facturado']:,.0f}")
        c3.metric("Total IVA", f"${r['total_iva']:,.0f}")
        if r.get("errores", 0) > 0:
            with st.expander(f"⚠️ {r['errores']} errores"):
                for e in res.errores[:20]:
                    st.text(e)
        if res.plano_df is not None and len(res.plano_df) > 0:
            import io as _io
            tsv = res.plano_df.to_csv(sep="\t", index=False, encoding="utf-8")
            buf = _io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                res.plano_df.to_excel(w, sheet_name="STL", index=False)
            s1, s2 = st.columns(2)
            with s1:
                st.download_button(
                    f"⬇️ Plano STL TSV ({len(res.plano_df):,})",
                    data=tsv.encode("utf-8"),
                    file_name=f"plano_stl_{f_desde}_a_{f_hasta}.txt",
                    mime="text/tab-separated-values",
                    use_container_width=True,
                )
            with s2:
                st.download_button(
                    "⬇️ Plano STL Excel",
                    data=buf.getvalue(),
                    file_name=f"plano_stl_{f_desde}_a_{f_hasta}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

# ─── Tab 2: Compras MIXTAS ─────────────────────────────────
with tab2:
    st.markdown(
        "**Procesar ZIP de compras MIXTAS** → genera plano contable detallado con "
        "IVA discriminado real por línea, aplicando retenciones según régimen."
    )
    cmix_zip = st.file_uploader("ZIP compras MIXTAS", type=["zip"], key="cmix_zip")
    if cmix_zip and st.button("⚙️ Procesar compras MIXTAS", key="btn_cmix", use_container_width=True):
        with st.spinner("Procesando..."):
            try:
                zb = cmix_zip.read()
                # 1) Actualizar maestro con datos de los proveedores
                maestro = mt.cargar_maestro_terceros(str(RUTA_MAESTRO)) if RUTA_MAESTRO.exists() else {"_meta":{}, "terceros":{}}
                resumen_maestro = pxz.procesar_zip_para_maestro(zb, maestro)
                mt.guardar_maestro_terceros(maestro, str(RUTA_MAESTRO))

                # 2) Generar plano contable detallado
                res_cmix = pxz.procesar_zip_compras_mixtas(
                    zb,
                    str(RUTA_COMPRAS),
                    str(RUTA_TABLA_RET),
                    str(RUTA_MAPEO_CONCEPTO),
                    str(RUTA_MAESTRO) if RUTA_MAESTRO.exists() else None,
                )
                st.session_state["res_cmix"] = res_cmix
                st.session_state["resumen_maestro_cmix"] = resumen_maestro
            except Exception as e:
                st.error(f"❌ Error: {e}")
                import traceback
                with st.expander("Detalle"):
                    st.code(traceback.format_exc())

    if "res_cmix" in st.session_state:
        res = st.session_state["res_cmix"]
        rmm = st.session_state.get("resumen_maestro_cmix", {})
        r = res.resumen()

        st.success(f"✅ {r['facturas_procesadas']:,} compras MIXTAS procesadas")
        if rmm:
            st.caption(
                f"Maestro: {rmm.get('nuevos',0)} nuevos, "
                f"{rmm.get('actualizados',0)} actualizados."
            )
        c1, c2, c3 = st.columns(3)
        c1.metric("Facturas", f"{r['facturas_procesadas']:,}")
        c2.metric("Total base", f"${r['total_base']:,.0f}")
        c3.metric("Total IVA", f"${r['total_iva']:,.0f}")

        if r.get('errores', 0) > 0:
            with st.expander(f"⚠️ {r['errores']} errores"):
                for e in res.errores[:20]:
                    st.text(e)

        if res.plano_df is not None and len(res.plano_df) > 0:
            tsv = res.plano_df.to_csv(sep="\t", index=False, encoding="utf-8")
            st.download_button(
                f"⬇️ Plano compras MIXTAS TSV ({len(res.plano_df):,} líneas)",
                data=tsv.encode("utf-8"),
                file_name=f"plano_compras_mixtas_{f_desde}_a_{f_hasta}.txt",
                mime="text/tab-separated-values",
                use_container_width=True,
            )

# ─── Tab 3: Ventas MIXTAS ──────────────────────────────────
with tab3:
    st.markdown(
        "**Procesar ZIP de ventas MIXTAS** → genera plano contable detallado con "
        "IVA discriminado por tarifa."
    )
    vmix_zip = st.file_uploader("ZIP ventas MIXTAS", type=["zip"], key="vmix_zip")
    if vmix_zip and st.button("⚙️ Procesar ventas MIXTAS", key="btn_vmix", use_container_width=True):
        with st.spinner("Procesando..."):
            try:
                res_vmix = pxz.procesar_zip_ventas_mixtas(vmix_zip.read(), str(RUTA_MAPEO))
                st.session_state["res_vmix"] = res_vmix
            except Exception as e:
                st.error(f"❌ Error: {e}")
                import traceback
                with st.expander("Detalle"):
                    st.code(traceback.format_exc())

    if "res_vmix" in st.session_state:
        res = st.session_state["res_vmix"]
        r = res.resumen()
        st.success(f"✅ {r['facturas_procesadas']:,} ventas MIXTAS procesadas")
        c1, c2, c3 = st.columns(3)
        c1.metric("Facturas", f"{r['facturas_procesadas']:,}")
        c2.metric("Total base", f"${r['total_base']:,.0f}")
        c3.metric("Total IVA", f"${r['total_iva']:,.0f}")
        if r.get('errores', 0) > 0:
            with st.expander(f"⚠️ {r['errores']} errores"):
                for e in res.errores[:20]:
                    st.text(e)
        if res.plano_df is not None and len(res.plano_df) > 0:
            tsv = res.plano_df.to_csv(sep="\t", index=False, encoding="utf-8")
            st.download_button(
                f"⬇️ Plano ventas MIXTAS TSV ({len(res.plano_df):,} líneas)",
                data=tsv.encode("utf-8"),
                file_name=f"plano_ventas_mixtas_{f_desde}_a_{f_hasta}.txt",
                mime="text/tab-separated-values",
                use_container_width=True,
            )

# ─── Tab 4: Proveedores → Maestro ──────────────────────────
with tab4:
    st.markdown(
        "**Procesar ZIP de proveedores únicos** → extrae régimen, ciudad, dirección "
        "y actualiza `maestro_terceros.json`."
    )
    maestro = mt.cargar_maestro_terceros(str(RUTA_MAESTRO)) if RUTA_MAESTRO.exists() else {"_meta":{}, "terceros":{}}
    st.metric("Terceros actualmente en maestro", f"{len(maestro.get('terceros', {})):,}")

    prov_zip = st.file_uploader("ZIP proveedores únicos", type=["zip"], key="prov_zip")
    if prov_zip and st.button("⚙️ Actualizar maestro", key="btn_prov", use_container_width=True):
        with st.spinner("Procesando..."):
            try:
                resumen = pxz.procesar_zip_para_maestro(prov_zip.read(), maestro)
                mt.guardar_maestro_terceros(maestro, str(RUTA_MAESTRO))
                st.success(
                    f"✅ Maestro actualizado: {resumen['nuevos']} nuevos, "
                    f"{resumen['actualizados']} actualizados, {resumen['errores']} errores."
                )
                st.info(
                    f"💡 Total en maestro: **{len(maestro.get('terceros', {})):,}** terceros."
                )

                # Distribución por régimen
                from collections import Counter
                ctos_reg = Counter(
                    t.get("tax_level_principal", "desconocido")
                    for t in maestro.get("terceros", {}).values()
                )
                if ctos_reg:
                    st.markdown("### Distribución por régimen")
                    df_reg = pd.DataFrame([
                        {"Régimen": r, "Cantidad": n,
                         "Significa": {
                             "O-13": "Gran Contribuyente",
                             "O-15": "Autorretenedor",
                             "O-23": "Agente Retención IVA",
                             "O-47": "Régimen Simple (RST)",
                             "R-99-PN": "No responsable / ordinario",
                         }.get(r, "Otro")}
                        for r, n in ctos_reg.most_common()
                    ])
                    st.dataframe(df_reg, use_container_width=True, hide_index=True)

                if resumen.get("errores", 0) > 0 and resumen.get("log"):
                    with st.expander(f"⚠️ {resumen['errores']} errores"):
                        for e in resumen["log"][:20]:
                            st.text(e)
            except Exception as e:
                st.error(f"❌ Error: {e}")
                import traceback
                with st.expander("Detalle"):
                    st.code(traceback.format_exc())


# ════════════════════════════════════════════════════════════
# PASO 8 — Plano CONSOLIDADO del mes (la cereza del pastel)
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 8️⃣ Plano CONSOLIDADO del mes")
st.caption(
    "Genera DOS planos finales (ventas y compras) listos para subir a Siigo. "
    "Cuando un documento aparezca en varios planos, gana el más detallado "
    "(XML > Token), evitando duplicaciones."
)

# Detectar qué piezas hay disponibles
piezas_ventas = []
piezas_compras = []

# Pieza 1: plano del paso 3 (ventas Token: POS+STL+DSE)
res_ventas_token = st.session_state.get("token_res")
if res_ventas_token is not None and hasattr(res_ventas_token, "plano_df"):
    if res_ventas_token.plano_df is not None and len(res_ventas_token.plano_df) > 0:
        piezas_ventas.append({
            "nombre": "Ventas Token (POS + STL + DSE)",
            "df": res_ventas_token.plano_df,
            "lineas": len(res_ventas_token.plano_df),
            "prioridad": 1,  # base
        })

# Pieza 2: plano del paso 5 (compras Token, sin MIXTAS)
res_compras_token = st.session_state.get("compras_res")
if res_compras_token is not None and hasattr(res_compras_token, "plano_df"):
    if res_compras_token.plano_df is not None and len(res_compras_token.plano_df) > 0:
        piezas_compras.append({
            "nombre": "Compras Token (sin MIXTAS)",
            "df": res_compras_token.plano_df,
            "lineas": len(res_compras_token.plano_df),
            "prioridad": 1,  # base
        })

# Pieza 3: STL del XML (reemplaza STL del Token si está)
res_stl = st.session_state.get("res_stl")
if res_stl is not None and res_stl.plano_df is not None and len(res_stl.plano_df) > 0:
    piezas_ventas.append({
        "nombre": "STL detalladas desde XML (reemplaza Token)",
        "df": res_stl.plano_df,
        "lineas": len(res_stl.plano_df),
        "prioridad": 2,  # gana sobre Token
    })

# Pieza 4: Ventas MIXTAS del XML
res_vmix = st.session_state.get("res_vmix")
if res_vmix is not None and res_vmix.plano_df is not None and len(res_vmix.plano_df) > 0:
    piezas_ventas.append({
        "nombre": "Ventas MIXTAS desde XML",
        "df": res_vmix.plano_df,
        "lineas": len(res_vmix.plano_df),
        "prioridad": 2,
    })

# Pieza 5: Compras MIXTAS del XML
res_cmix = st.session_state.get("res_cmix")
if res_cmix is not None and res_cmix.plano_df is not None and len(res_cmix.plano_df) > 0:
    piezas_compras.append({
        "nombre": "Compras MIXTAS desde XML",
        "df": res_cmix.plano_df,
        "lineas": len(res_cmix.plano_df),
        "prioridad": 2,
    })

# Mostrar resumen de piezas
st.markdown("### Piezas disponibles para consolidar")
if piezas_ventas:
    st.markdown("**🟢 Ventas:**")
    for p in piezas_ventas:
        st.markdown(f"  - {p['nombre']}: **{p['lineas']:,} líneas**")
else:
    st.warning("⚠️ No hay piezas de ventas. Procesa primero el paso 3 (ventas Token).")

if piezas_compras:
    st.markdown("**🟠 Compras:**")
    for p in piezas_compras:
        st.markdown(f"  - {p['nombre']}: **{p['lineas']:,} líneas**")
else:
    st.warning("⚠️ No hay piezas de compras. Procesa primero el paso 5 (compras Token).")

# Botón generar consolidado
if piezas_ventas or piezas_compras:
    if st.button("🎯 Generar planos consolidados del mes", use_container_width=True, type="primary"):
        with st.spinner("Consolidando y deduplicando..."):
            # Ordenar por prioridad ascendente (Token primero, XML al final → XML gana)
            piezas_ventas_ord = sorted(piezas_ventas, key=lambda x: x["prioridad"])
            piezas_compras_ord = sorted(piezas_compras, key=lambda x: x["prioridad"])

            resultado_consol = pxz.consolidar_planos(
                planos_ventas=[p["df"] for p in piezas_ventas_ord],
                planos_compras=[p["df"] for p in piezas_compras_ord],
            )
            st.session_state["consolidado"] = resultado_consol

if "consolidado" in st.session_state:
    consol = st.session_state["consolidado"]
    pv = consol["ventas"]
    pc = consol["compras"]

    st.markdown("### 📊 Resultado consolidado")
    cv, cc = st.columns(2)

    with cv:
        st.metric("Plano VENTAS", f"{len(pv):,} líneas")
        if len(pv) > 0:
            pv2 = pv.copy()
            pv2["V"] = pd.to_numeric(pv2["VALOR"], errors="coerce").fillna(0)
            db = pv2[pv2["TR"] == "1"]["V"].sum()
            cr = pv2[pv2["TR"] == "2"]["V"].sum()
            st.caption(f"Db ${db:,.0f}  /  Cr ${cr:,.0f}  /  dif ${abs(db-cr):,.0f}")
            tsv_v = pv.to_csv(sep="\t", index=False, encoding="utf-8")
            st.download_button(
                f"⬇️ PLANO VENTAS consolidado TSV",
                data=tsv_v.encode("utf-8"),
                file_name=f"plano_VENTAS_{f_desde}_a_{f_hasta}.txt",
                mime="text/tab-separated-values",
                use_container_width=True,
                type="primary",
            )

    with cc:
        st.metric("Plano COMPRAS", f"{len(pc):,} líneas")
        if len(pc) > 0:
            pc2 = pc.copy()
            pc2["V"] = pd.to_numeric(pc2["VALOR"], errors="coerce").fillna(0)
            db = pc2[pc2["TR"] == "1"]["V"].sum()
            cr = pc2[pc2["TR"] == "2"]["V"].sum()
            st.caption(f"Db ${db:,.0f}  /  Cr ${cr:,.0f}  /  dif ${abs(db-cr):,.0f}")
            tsv_c = pc.to_csv(sep="\t", index=False, encoding="utf-8")
            st.download_button(
                f"⬇️ PLANO COMPRAS consolidado TSV",
                data=tsv_c.encode("utf-8"),
                file_name=f"plano_COMPRAS_{f_desde}_a_{f_hasta}.txt",
                mime="text/tab-separated-values",
                use_container_width=True,
                type="primary",
            )

    # Plano de terceros nuevos (los que no estaban en histórico ni en maestro)
    st.markdown("### 👥 Plano de TERCEROS NUEVOS para Siigo")
    if RUTA_MAESTRO.exists():
        from core.procesadores import exportador_nits_siigo as exp_nits

        maestro_final = mt.cargar_maestro_terceros(str(RUTA_MAESTRO))

        # Calcular NITs nuevos (los que NO están en histórico)
        nits_historico = set()
        if RUTA_COMPRAS.exists():
            with open(RUTA_COMPRAS, encoding="utf-8") as _f:
                hist = json.load(_f)
            for e in hist.get("mapeo", []):
                nit = exp_nits.normalizar_nit(str(e.get("nit", "")))
                if nit:
                    nits_historico.add(nit)

        nits_maestro = {exp_nits.normalizar_nit(k) for k in maestro_final.get("terceros", {}).keys()}
        nits_nuevos = nits_maestro - nits_historico

        if nits_nuevos:
            df_terc = exp_nits.exportar_nits_desde_maestro(maestro_final, nits_filtrar=nits_nuevos)
            st.metric("Terceros nuevos a crear en Siigo", f"{len(df_terc):,}")
            st.caption(
                f"Formato Siigo NITs (20 columnas) con códigos DANE, naturaleza y "
                f"responsabilidad IVA deducidos automáticamente."
            )

            # Distribución de naturaleza
            nat_dist = df_terc["NATURALEZA"].value_counts().to_dict()
            naturales = nat_dist.get("N", 0)
            juridicas = nat_dist.get("J", 0)
            c1, c2 = st.columns(2)
            c1.metric("Jurídicas (J)", f"{juridicas:,}")
            c2.metric("Naturales (N)", f"{naturales:,}")

            # Excel formato Siigo
            xlsx_bytes = exp_nits.generar_excel_nits_siigo(df_terc)
            st.download_button(
                f"⬇️ NITs nuevos Excel formato Siigo ({len(df_terc):,})",
                data=xlsx_bytes,
                file_name=f"nits_jiper_{f_desde}_a_{f_hasta}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
            )

            # También TSV por si el usuario lo prefiere
            tsv_t = df_terc.to_csv(sep="\t", index=False, encoding="utf-8")
            st.download_button(
                f"⬇️ NITs nuevos TSV ({len(df_terc):,})",
                data=tsv_t.encode("utf-8"),
                file_name=f"nits_jiper_{f_desde}_a_{f_hasta}.txt",
                mime="text/tab-separated-values",
                use_container_width=True,
            )

            # Mostrar muestra
            with st.expander("Vista previa de los primeros 10 terceros"):
                st.dataframe(df_terc.head(10), use_container_width=True, hide_index=True)
        else:
            st.info("ℹ️ No hay terceros nuevos: todos los proveedores ya están en tu contabilidad.")
    else:
        st.info("ℹ️ Sube primero el ZIP de proveedores en el tab 'Proveedores → Maestro' para detectar terceros nuevos.")


# ─── Reset ──────────────────────────────────────────────────
st.markdown("---")
if st.button("🔄 Limpiar y procesar otro mes"):
    for k in list(st.session_state.keys()):
        if k.startswith(("token_", "pos_", "comp_", "mix_", "compras_")):
            st.session_state.pop(k, None)
    st.rerun()
