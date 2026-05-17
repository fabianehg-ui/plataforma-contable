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
# PASO 6 — Listas de CUFEs para descarga XML (extensión Chrome)
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 6️⃣ Listas de CUFEs para extensión Chrome")
st.caption(
    "Compras y ventas MIXTAS (mezcla de tarifas IVA) + TODAS las STL emitidas "
    "(para parseo detallado de IVA por línea)."
)

if st.button("📋 Calcular listas"):
    with st.spinner("Analizando..."):
        from core.procesadores import procesador_stl_xml as stl_xml
        st.session_state["mix_compras"] = glc.generar_lista_compras_mixtas(df_token_filt)
        st.session_state["mix_ventas"] = glc.generar_lista_ventas_mixtas(df_token_filt)
        st.session_state["stl_cufes"] = stl_xml.generar_lista_cufes_stl(
            df_token_filt, f_desde, f_hasta
        )

if "mix_compras" in st.session_state:
    lc = st.session_state["mix_compras"]
    lv = st.session_state["mix_ventas"]
    ls = st.session_state.get("stl_cufes", [])

    cx, cy, cs = st.columns(3)
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

    with cs:
        st.metric("STL todas", f"{len(ls):,}")
        if ls:
            payload = {
                "meta": {
                    "rol": "stl_todas",
                    "descripcion": "Todas las STL emitidas (para parseo detallado de IVA por línea)",
                    "fecha_desde": str(f_desde),
                    "fecha_hasta": str(f_hasta),
                    "total_cufes": len(ls),
                },
                "cufes": ls,
            }
            st.download_button(
                "⬇️ Lista STL completa",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                file_name=f"cufes_stl_todas_{f_desde}_a_{f_hasta}.json",
                mime="application/json",
                use_container_width=True,
            )

    total_descargar = len(lc) + len(lv) + len(ls)
    if total_descargar > 0:
        st.info(
            f"💡 Total: {total_descargar:,} XMLs a descargar con la extensión Chrome "
            f"(~{total_descargar / 8 / 60:.1f} min)."
        )


# ════════════════════════════════════════════════════════════
# PASO 6B — Procesar XMLs de STL descargados
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 6️⃣B Procesar XMLs de STL descargados")
st.caption(
    "Sube el ZIP de la extensión Chrome con TODAS las STL emitidas. "
    "Genera plano contable con IVA discriminado real por línea (reemplaza el procesamiento STL desde Excel)."
)

stl_zip = st.file_uploader(
    "ZIP de XMLs de STL emitidas",
    type=["zip"],
    key="stl_xml_zip",
)

if stl_zip is not None:
    if st.button("⚙️ Procesar XMLs STL", use_container_width=True):
        from core.procesadores import procesador_stl_xml as stl_xml
        with st.spinner("Procesando XMLs de STL..."):
            try:
                zb = stl_zip.read()
                res_stl = stl_xml.procesar_zip_xmls_stl(zb)
                st.session_state["stl_res"] = res_stl
            except Exception as e:
                st.error(f"❌ Error: {e}")
                import traceback
                with st.expander("Detalle"):
                    st.code(traceback.format_exc())

if "stl_res" in st.session_state:
    res_stl = st.session_state["stl_res"]
    resumen_stl = res_stl.resumen()

    st.success(f"✅ {resumen_stl['facturas_procesadas']:,} STL procesadas")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Facturas STL", f"{resumen_stl['facturas_procesadas']:,}")
    c2.metric("Total base", f"${resumen_stl['total_base']:,.0f}")
    c3.metric("Total IVA", f"${resumen_stl['total_iva']:,.0f}")
    c4.metric("Total facturado", f"${resumen_stl['total_facturado']:,.0f}")

    if resumen_stl.get('errores', 0) > 0:
        with st.expander(f"⚠️ {resumen_stl['errores']} errores"):
            for e in res_stl.errores[:20]:
                st.text(e)

    # Descargar plano
    if res_stl.plano_df is not None and len(res_stl.plano_df) > 0:
        import io as _io2
        # TSV
        tsv = res_stl.plano_df.to_csv(sep="\t", index=False, encoding="utf-8")
        # Excel
        buf = _io2.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            res_stl.plano_df.to_excel(w, sheet_name="STL", index=False)

        s1, s2 = st.columns(2)
        with s1:
            st.download_button(
                f"⬇️ Plano STL TSV ({len(res_stl.plano_df):,} líneas)",
                data=tsv.encode("utf-8"),
                file_name=f"plano_stl_{f_desde}_a_{f_hasta}.txt",
                mime="text/tab-separated-values",
                use_container_width=True,
            )
        with s2:
            st.download_button(
                f"⬇️ Plano STL Excel",
                data=buf.getvalue(),
                file_name=f"plano_stl_{f_desde}_a_{f_hasta}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )


# ════════════════════════════════════════════════════════════
# PASO 7 — Maestro de Terceros (régimen + dirección)
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 7️⃣ Maestro de Terceros (régimen + dirección)")
st.caption(
    "Para que las retenciones excluyan correctamente a Grandes Contribuyentes, "
    "Autorretenedores y Régimen Simple, descarga UN XML por proveedor único. "
    "El sistema extrae régimen, ciudad, dirección y los guarda para el futuro."
)

from core.procesadores import maestro_terceros as mt

# Estado actual del maestro
maestro = mt.cargar_maestro_terceros(str(RUTA_MAESTRO)) if RUTA_MAESTRO.exists() else {"terceros": {}}
n_maestro = len(maestro.get("terceros", {}))

mcol1, mcol2 = st.columns(2)
mcol1.metric("Terceros en maestro", f"{n_maestro:,}")

# Lista de proveedores únicos sin maestro
lista_unicos = glc.generar_lista_proveedores_unicos(df_token_filt, maestro)
mcol2.metric("Proveedores nuevos por consultar", f"{len(lista_unicos):,}")

if lista_unicos:
    st.markdown("### 📥 Lista CUFEs únicos por proveedor para descargar con extensión Chrome")
    st.caption(
        f"Esta lista trae 1 CUFE por NIT proveedor nuevo. La extensión los descarga, "
        f"se sube el ZIP en el paso 8 y se actualiza el maestro automáticamente."
    )
    payload_unicos = {
        "meta": {
            "rol": "recibidos_por_proveedor_unico",
            "descripcion": "Un CUFE por NIT proveedor (extracción de régimen + dirección)",
            "fecha_desde": str(f_desde),
            "fecha_hasta": str(f_hasta),
            "total_cufes": len(lista_unicos),
        },
        "cufes": [item["cufe"] for item in lista_unicos],
    }
    st.download_button(
        f"⬇️ Descargar lista de {len(lista_unicos)} CUFEs proveedor-único",
        data=json.dumps(payload_unicos, ensure_ascii=False).encode("utf-8"),
        file_name=f"cufes_proveedores_unicos_{f_desde}_a_{f_hasta}.json",
        mime="application/json",
        use_container_width=True,
    )

# ════════════════════════════════════════════════════════════
# PASO 8 — Cargar XMLs y actualizar maestro
# ════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown("## 8️⃣ Cargar XMLs descargados y actualizar maestro de terceros")
st.caption("Sube el ZIP que descargó la extensión Chrome. Extrae régimen, ciudad y dirección de cada proveedor.")

xml_zip = st.file_uploader(
    "ZIP de XMLs descargados por extensión Chrome",
    type=["zip"],
    key="xml_maestro_zip",
)

if xml_zip is not None:
    if st.button("🔍 Procesar XMLs y actualizar maestro", use_container_width=True):
        import zipfile
        import io as _io

        nuevos = 0
        actualizados = 0
        errores = 0
        log_proc = []

        try:
            zb = xml_zip.read()
            with zipfile.ZipFile(_io.BytesIO(zb)) as zf:
                for nombre in zf.namelist():
                    # La extensión descarga ZIPs anidados (ZIP de ZIPs)
                    if not nombre.endswith(".zip"):
                        continue
                    try:
                        inner_bytes = zf.read(nombre)
                        with zipfile.ZipFile(_io.BytesIO(inner_bytes)) as inner_zf:
                            for inner_name in inner_zf.namelist():
                                if inner_name.endswith(".xml"):
                                    xml_bytes = inner_zf.read(inner_name)
                                    xml_str = xml_bytes.decode("utf-8", errors="ignore")
                                    parsed = mt.extraer_datos_tercero_de_xml(xml_str)
                                    if parsed:
                                        es_nuevo = mt.actualizar_maestro_desde_xml(maestro, parsed)
                                        if es_nuevo:
                                            nuevos += 1
                                        else:
                                            actualizados += 1
                                    break  # 1 XML por ZIP basta
                    except Exception as e:
                        errores += 1
                        log_proc.append(f"{nombre}: {e}")

            # Guardar maestro
            mt.guardar_maestro_terceros(maestro, str(RUTA_MAESTRO))

            st.success(
                f"✅ Maestro actualizado: {nuevos} terceros nuevos, "
                f"{actualizados} actualizados, {errores} errores."
            )
            st.info(
                f"💡 Total en maestro: **{len(maestro.get('terceros', {})):,}** terceros. "
                f"En el próximo procesamiento las retenciones se calcularán con el régimen real."
            )

            # Mostrar resumen por régimen
            from collections import Counter
            ctos_reg = Counter(
                t.get("tax_level_principal", "desconocido")
                for t in maestro.get("terceros", {}).values()
            )
            st.markdown("### 📊 Distribución de regímenes en el maestro")
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

            if errores > 0 and log_proc:
                with st.expander(f"⚠️ {errores} errores procesando"):
                    for e in log_proc[:20]:
                        st.text(e)

        except Exception as e:
            st.error(f"❌ Error procesando ZIP: {e}")
            with st.expander("Detalle"):
                import traceback
                st.code(traceback.format_exc())


# ─── Reset ──────────────────────────────────────────────────
st.markdown("---")
if st.button("🔄 Limpiar y procesar otro mes"):
    for k in list(st.session_state.keys()):
        if k.startswith(("token_", "pos_", "comp_", "mix_", "compras_")):
            st.session_state.pop(k, None)
    st.rerun()
