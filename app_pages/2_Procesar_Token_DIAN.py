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
st.markdown("## 6️⃣ Generar listas JSON para la extensión Chrome")
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
# PASO 6.5 — Descarga DIRECTA desde DIAN (sin extensión Chrome)
# ════════════════════════════════════════════════════════════
# Flujo alternativo al de la extensión:
#   1. Pegas la URL del Token DIAN
#   2. Eliges qué descargar (Lista A = STL+DSE emitidos, Lista B = todos
#      los recibidos)
#   3. La plataforma descarga en bloques de 700 (límite empírico antes
#      de que la sesión expire)
#   4. Si la sesión se cierra a mitad, pides un Token nuevo y continúas
#      donde quedaste — el progreso NO se pierde
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 6.5 🚀 Descarga DIRECTA desde DIAN")

with st.expander("ℹ️ ¿Cuándo usar esto vs la extensión Chrome?", expanded=False):
    st.markdown(
        "**Descarga directa (esta sección):**\n"
        "- Pegas la URL del Token y la plataforma descarga sola.\n"
        "- No necesitas instalar nada.\n"
        "- Bloques automáticos de 700 documentos (la sesión DIAN cierra a "
        "los ~30 min). Cuando se acabe el bloque, te pide otro Token y sigue.\n"
        "- Ideal para volúmenes grandes desatendidos.\n\n"
        "**Extensión Chrome (sección anterior y siguiente):**\n"
        "- Sigue funcionando como antes; queda como respaldo.\n"
        "- Útil si la descarga directa falla por bloqueos de DIAN.\n"
    )

if "lista_compras_mixtas" not in st.session_state:
    st.caption("⚠️ Primero genera las listas en el paso 6 ⬆️")
else:
    from core.procesadores import descargador_dian as dd

    # ─── Estado de la descarga (sobrevive a reruns) ───
    if "dian_dl_estado" not in st.session_state:
        st.session_state["dian_dl_estado"] = {
            "zips_por_cufe": {},     # acumulado entre bloques
            "fallidos": [],
            "pendientes": [],
            "lista_origen": "",      # "emitidos" | "recibidos"
            "total_inicial": 0,
            "bloques_completados": 0,
        }

    estado_dl = st.session_state["dian_dl_estado"]

    # ─── Selección de qué descargar ───
    st.markdown("### 1️⃣ Elige qué descargar")
    lr = st.session_state.get("lista_todos_recibidos", [])
    le_stl_dse = glc.generar_lista_emitidos_stl_y_dse(df_token_filt, f_desde, f_hasta)
    st.session_state["lista_emitidos_stl_dse"] = le_stl_dse

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Lista A — Emitidos (STL + DSE)", f"{len(le_stl_dse):,}")
    with col_b:
        st.metric("Lista B — Recibidos (todos)", f"{len(lr):,}")

    opcion = st.radio(
        "¿Qué quieres descargar?",
        ["Lista A: Emitidos (STL + DSE)", "Lista B: Recibidos (todos)"],
        horizontal=True,
        key="dian_dl_opcion",
    )

    if opcion.startswith("Lista A"):
        lista_a_descargar = [item["cufe"] for item in le_stl_dse if item.get("cufe")]
        nombre_lista = "emitidos"
    else:
        lista_a_descargar = [item["cufe"] for item in lr if item.get("cufe")]
        nombre_lista = "recibidos"

    # Si cambió la lista que se va a descargar, resetear estado
    if estado_dl.get("lista_origen") != nombre_lista and estado_dl.get("lista_origen"):
        if st.button("🔄 La selección cambió. Limpiar progreso anterior"):
            st.session_state["dian_dl_estado"] = {
                "zips_por_cufe": {},
                "fallidos": [],
                "pendientes": [],
                "lista_origen": "",
                "total_inicial": 0,
                "bloques_completados": 0,
            }
            st.rerun()

    # Si no hay descarga en curso, inicializar
    if not estado_dl["pendientes"] and not estado_dl["zips_por_cufe"]:
        estado_dl["pendientes"] = list(lista_a_descargar)
        estado_dl["lista_origen"] = nombre_lista
        estado_dl["total_inicial"] = len(lista_a_descargar)

    pendientes_n = len(estado_dl["pendientes"])
    completados_n = len(estado_dl["zips_por_cufe"])
    fallidos_n = len(estado_dl["fallidos"])

    st.markdown("### 2️⃣ Estado de la descarga")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total a descargar", f"{estado_dl['total_inicial']:,}")
    c2.metric("✅ Completados", f"{completados_n:,}")
    c3.metric("❌ Fallidos", f"{fallidos_n:,}")
    c4.metric("⏳ Pendientes", f"{pendientes_n:,}")

    if estado_dl["total_inicial"] > 0:
        pct = (completados_n / estado_dl["total_inicial"]) * 100
        st.progress(pct / 100, text=f"{pct:.1f}% completado")

    # ─── URL del Token ───
    st.markdown("### 3️⃣ Pega la URL del Token DIAN")
    token_url = st.text_input(
        "URL completa del Token (de catalogo-vpfe.dian.gov.co)",
        placeholder="https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=...&rk=...&token=...",
        key="dian_token_url",
        type="password",
        help="Genera un Token desde el portal DIAN y pega aquí la URL completa. "
             "Es una credencial: no la compartas.",
    )

    # ─── Tamaño del bloque ───
    col_bs1, col_bs2 = st.columns([2, 1])
    with col_bs1:
        max_docs = st.number_input(
            "Máximo de documentos por bloque",
            min_value=50, max_value=1500, value=700, step=50,
            help="La sesión DIAN cierra a los ~30 min / ~700 docs. "
                 "Si te aparece 'sesión expirada' baja este número.",
        )
    with col_bs2:
        delay = st.number_input(
            "Delay (seg)",
            min_value=0.0, max_value=2.0, value=0.15, step=0.05,
            help="Pausa entre descargas para no saturar DIAN.",
        )

    # ─── Botón de descarga del bloque ───
    st.markdown("### 4️⃣ Descargar el siguiente bloque")
    if pendientes_n == 0 and completados_n > 0:
        st.success(f"🎉 Descarga completa: {completados_n:,} XMLs descargados.")
    else:
        boton_label = f"⬇️ Descargar próximo bloque ({min(pendientes_n, int(max_docs)):,} docs)"
        if st.button(boton_label, type="primary", disabled=not token_url, use_container_width=True):
            try:
                with st.spinner(f"Autenticando con DIAN..."):
                    sess = dd.autenticar(token_url)
                st.success("✅ Sesión DIAN autenticada")

                # Descarga con progreso visible
                progress_bar = st.progress(0.0, text="Descargando...")
                status_text = st.empty()

                def on_prog(i, total, msg):
                    if total > 0:
                        progress_bar.progress(i / total, text=f"{i}/{total} — {msg}")

                with st.spinner(f"Descargando {min(pendientes_n, int(max_docs)):,} XMLs (puede tomar ~5-10 min)..."):
                    res = dd.descargar_lote(
                        sess,
                        estado_dl["pendientes"],
                        max_docs=int(max_docs),
                        delay=float(delay),
                        on_progress=on_prog,
                    )

                # Acumular en el estado
                estado_dl["zips_por_cufe"].update(res.exitosos)
                estado_dl["fallidos"].extend(res.fallidos)
                estado_dl["pendientes"] = res.cufes_pendientes(estado_dl["pendientes"])
                estado_dl["bloques_completados"] += 1

                progress_bar.empty()
                status_text.empty()

                # Mensaje según motivo de parada
                if res.motivo_parada == "completo":
                    st.success(
                        f"🎉 Descarga COMPLETA. "
                        f"Total: {len(estado_dl['zips_por_cufe']):,} XMLs."
                    )
                elif res.motivo_parada == "sesion_expirada":
                    st.warning(
                        f"⚠️ La sesión DIAN expiró tras {res.total_exitosos} docs de este bloque. "
                        f"**Genera un Token nuevo** y pégalo arriba para continuar. "
                        f"El progreso está guardado: te quedan **{len(estado_dl['pendientes']):,} pendientes**."
                    )
                elif res.motivo_parada == "limite_bloque":
                    st.info(
                        f"✅ Bloque completado ({res.total_exitosos} XMLs). "
                        f"Quedan **{len(estado_dl['pendientes']):,} pendientes**. "
                        f"Puedes pegar el mismo Token (si todavía es vigente) o uno nuevo "
                        f"y darle al botón otra vez."
                    )

                if res.duracion_seg > 0:
                    rate = res.total_exitosos / res.duracion_seg
                    st.caption(
                        f"⏱️ {res.duracion_seg:.0f}s ({rate:.1f} XMLs/seg) · "
                        f"este bloque: {res.total_exitosos} ok, {res.total_fallidos} fallidos"
                    )

                st.rerun()
            except dd.SesionExpirada as e:
                st.error(f"❌ Token inválido o expirado: {e}")
            except ValueError as e:
                st.error(f"❌ URL inválida: {e}")
            except Exception as e:
                st.error(f"❌ Error inesperado: {e}")
                import traceback
                with st.expander("Detalle"):
                    st.code(traceback.format_exc())

    # ─── Descargar el ZIP consolidado ───
    if completados_n > 0:
        st.markdown("### 5️⃣ ZIP consolidado")
        if st.button("📦 Generar ZIP consolidado para procesar", use_container_width=True):
            with st.spinner("Consolidando..."):
                zip_consol = dd.juntar_zips(estado_dl["zips_por_cufe"])
            st.session_state["dian_dl_zip_consolidado"] = zip_consol
            st.success(f"✅ ZIP consolidado: {len(zip_consol):,} bytes "
                       f"({len(estado_dl['zips_por_cufe']):,} XMLs)")

        if "dian_dl_zip_consolidado" in st.session_state:
            from datetime import date as _date
            hoy = _date.today().strftime("%Y%m%d")
            st.download_button(
                f"⬇️ Descargar ZIP consolidado ({len(estado_dl['zips_por_cufe']):,} XMLs)",
                data=st.session_state["dian_dl_zip_consolidado"],
                file_name=f"dian_directo_{estado_dl['lista_origen']}_{hoy}.zip",
                mime="application/zip",
                use_container_width=True,
            )
            st.caption(
                "👇 Sube este ZIP en la sección 7 para procesarlo "
                "(igual que un ZIP de la extensión)."
            )

    # ─── Errores detallados ───
    if fallidos_n > 0:
        with st.expander(f"❌ Ver {fallidos_n} errores"):
            for cufe, razon in estado_dl["fallidos"][:50]:
                st.text(f"{cufe[:40]}... → {razon}")
            if fallidos_n > 50:
                st.caption(f"... y {fallidos_n - 50} más")

    # ─── Resetear todo ───
    if completados_n > 0 or fallidos_n > 0:
        with st.expander("🗑️ Limpiar progreso y empezar de cero"):
            if st.button("⚠️ Resetear descarga (perderás lo descargado en memoria)"):
                st.session_state["dian_dl_estado"] = {
                    "zips_por_cufe": {},
                    "fallidos": [],
                    "pendientes": [],
                    "lista_origen": "",
                    "total_inicial": 0,
                    "bloques_completados": 0,
                }
                st.session_state.pop("dian_dl_zip_consolidado", None)
                st.rerun()


# ════════════════════════════════════════════════════════════
# PASO 7 — Subir ZIPs descargados y procesar
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 7️⃣ Subir ZIPs de XMLs descargados")
st.caption(
    "Sube el ZIP plano que descargó la extensión Chrome. Cada ZIP tiene un rol "
    "diferente. La plataforma detecta el tipo y procesa en consecuencia."
)

from core.procesadores import procesador_xmls_zip as pxz

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
