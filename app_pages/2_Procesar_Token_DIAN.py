"""
app_pages/2_Procesar_Token_DIAN.py

Módulo unificado de procesamiento DIAN.

ARQUITECTURA FINAL:

  PASO 1 ─ Subir Excel del Token DIAN
           └─ Resumen + selectoras de qué descargar

  PASO 2 ─ Generar lista de CUFEs (emitidos / recibidos)
           └─ Descarga archivo .json con la lista
           └─ Usuario carga ese archivo en la extensión Chrome
           └─ Extensión descarga cada XML uno por uno

  PASO 3 ─ Subir el JSON con XMLs descargados
           └─ Procesa con parser_xml_stl, clasifica y muestra resultado

Reemplaza los módulos viejos (2_Compras_DIAN, 3a_Compras_y_Egresos,
4b_Ingresos_POS, 5a_DIAN_XML) que ya están movidos a app_pages/_legacy/.
"""
from __future__ import annotations

import base64
import io
import json
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa

from core.procesadores import clasificador_documentos as clf
from core.procesadores import parser_xml_stl as pxml
from core.procesadores import lector_excel_token as lex


# ─── Setup página ───────────────────────────────────────────
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

st.title("📥 Procesar DIAN")
st.caption(
    "Procesa documentos electrónicos DIAN combinando el Excel del Token "
    "(lista completa de docs) con la extensión Chrome (descarga de XMLs)."
)


# ─── Cargar mapeo de prefijos ───────────────────────────────
def cargar_mapeo_prefijos() -> dict:
    archivo = ROOT / "datos_punto.json"
    if not archivo.exists():
        return {}
    try:
        with open(archivo) as f:
            data = json.load(f)
        return clf.construir_mapeo_prefijos(data.get("sucursales", []))
    except Exception:
        return {}


MAPEO_PREFIJOS = cargar_mapeo_prefijos()
NIT_EMPRESA = (empresa.get("nit") if empresa else None) or "901038325"


def _tipo_dian_desde_nombre(nombre: str) -> str:
    """Mapea 'Factura electrónica' → '01', 'Nota de crédito electrónica' → '91', etc."""
    nombre_lower = (nombre or "").lower()
    if "factura" in nombre_lower:
        return "01"
    if "crédito" in nombre_lower or "credito" in nombre_lower:
        return "91"
    if "débito" in nombre_lower or "debito" in nombre_lower:
        return "92"
    if "soporte" in nombre_lower or "equivalente" in nombre_lower:
        return "05"
    return ""


# ============================================================
# PASO 1: Subir Excel del Token DIAN
# ============================================================
st.markdown("## 📄 Paso 1 — Subir Excel del Token DIAN")

with st.expander("📘 Cómo obtener el Excel del Token", expanded=False):
    st.markdown("""
1. Entra al portal DIAN con tu Token: `https://catalogo-vpfe.dian.gov.co/User/AuthToken?...`
2. En el portal hay un botón **"Exportar a Excel"** (parte superior derecha).
3. Define el rango de fechas que quieres exportar.
4. Espera a que se descargue el `.xlsx`.
5. Súbelo aquí abajo.

Ese Excel trae **el 100% de los documentos** del rango (no como el listado paginado que limita ~150-500). Pero tiene **límites**: IVA en una sola columna sin discriminar tarifas, sin direcciones de terceros. Para esos datos vamos al **Paso 2**.
""")

excel_token = st.file_uploader(
    "Sube el archivo .xlsx exportado del Token DIAN",
    type=["xlsx"],
    key="uploader_excel",
)


# Estado
if excel_token is not None:
    try:
        with st.spinner("📖 Leyendo Excel..."):
            df_completo = lex.leer_excel_token(excel_token)
        st.success(f"✅ Excel leído: **{len(df_completo):,}** documentos totales.")
        st.session_state["excel_df"] = df_completo
    except ValueError as e:
        st.error(f"❌ El Excel no es válido: {e}")
        st.stop()
    except Exception as e:
        st.error(f"❌ Error inesperado leyendo el Excel: {e}")
        with st.expander("Detalle"):
            import traceback
            st.code(traceback.format_exc())
        st.stop()


if "excel_df" in st.session_state:
    df_completo = st.session_state["excel_df"]

    # Detección automática de rango disponible
    fechas_validas = df_completo["fecha_emision"].dropna()
    if len(fechas_validas) > 0:
        fecha_min = fechas_validas.min().date()
        fecha_max = fechas_validas.max().date()
    else:
        fecha_min = date.today()
        fecha_max = date.today()

    st.caption(
        f"Rango disponible en el Excel: **{fecha_min}** → **{fecha_max}**"
    )

    # ============================================================
    # PASO 2: Filtrar y generar listas de CUFEs
    # ============================================================
    st.markdown("---")
    st.markdown("## 🎯 Paso 2 — Filtrar y generar lista de CUFEs a descargar")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        f_desde = st.date_input(
            "Desde", value=fecha_min, min_value=fecha_min, max_value=fecha_max,
            format="YYYY-MM-DD", key="filter_desde",
        )
    with col_f2:
        f_hasta = st.date_input(
            "Hasta", value=fecha_max, min_value=fecha_min, max_value=fecha_max,
            format="YYYY-MM-DD", key="filter_hasta",
        )

    df_filtrado = lex.filtrar_por_rango(df_completo, f_desde, f_hasta)
    st.caption(f"📦 En el rango: **{len(df_filtrado):,}** documentos")

    # Resumen visual
    conteo = lex.conteo_para_descarga(df_filtrado)

    col_e, col_r = st.columns(2)

    with col_e:
        st.markdown("### 📤 EMITIDOS")
        st.metric("Útiles para descargar", f"{conteo['emitidos_utiles']:,}",
                  f"{conteo['emitidos_brutos']:,} brutos")
        if conteo["emitidos_excluidos"]:
            with st.expander(f"Excluidos: {sum(conteo['emitidos_excluidos'].values()):,}", expanded=False):
                for tipo, n in conteo["emitidos_excluidos"].items():
                    st.caption(f"• {tipo}: {n:,}")
        st.caption("Desglose útiles:")
        if conteo["emitidos_desglose"]:
            for tipo, n in conteo["emitidos_desglose"].items():
                st.caption(f"   {tipo}: **{n:,}**")
        else:
            st.caption("(ninguno)")

    with col_r:
        st.markdown("### 📥 RECIBIDOS")
        st.metric("Útiles para descargar", f"{conteo['recibidos_utiles']:,}",
                  f"{conteo['recibidos_brutos']:,} brutos")
        if conteo["recibidos_excluidos"]:
            with st.expander(f"Excluidos: {sum(conteo['recibidos_excluidos'].values()):,}", expanded=False):
                for tipo, n in conteo["recibidos_excluidos"].items():
                    st.caption(f"• {tipo}: {n:,}")
        st.caption("Desglose útiles:")
        if conteo["recibidos_desglose"]:
            for tipo, n in conteo["recibidos_desglose"].items():
                st.caption(f"   {tipo}: **{n:,}**")
        else:
            st.caption("(ninguno)")

    st.markdown("---")
    st.markdown("### 📋 Generar listas de CUFEs para la extensión Chrome")

    col_btn_e, col_btn_r = st.columns(2)

    with col_btn_e:
        lista_emit = lex.generar_lista_cufes(df_filtrado, rol="emitido")
        if lista_emit:
            payload = {
                "meta": {
                    "rol": "emitidos",
                    "fecha_desde": str(f_desde),
                    "fecha_hasta": str(f_hasta),
                    "total_cufes": len(lista_emit),
                    "generado_en": datetime.now().isoformat(),
                    "nit_empresa": NIT_EMPRESA,
                },
                "cufes": lista_emit,
            }
            jsonstr = json.dumps(payload, ensure_ascii=False, indent=0)
            st.download_button(
                f"📤 Descargar lista EMITIDOS ({len(lista_emit):,} CUFEs)",
                data=jsonstr.encode("utf-8"),
                file_name=f"cufes_emitidos_{f_desde}_a_{f_hasta}.json",
                mime="application/json",
                use_container_width=True,
                key="dl_emit_list",
            )
        else:
            st.button("📤 EMITIDOS (sin docs)", disabled=True, use_container_width=True)

    with col_btn_r:
        lista_recb = lex.generar_lista_cufes(df_filtrado, rol="recibido")
        if lista_recb:
            payload = {
                "meta": {
                    "rol": "recibidos",
                    "fecha_desde": str(f_desde),
                    "fecha_hasta": str(f_hasta),
                    "total_cufes": len(lista_recb),
                    "generado_en": datetime.now().isoformat(),
                    "nit_empresa": NIT_EMPRESA,
                },
                "cufes": lista_recb,
            }
            jsonstr = json.dumps(payload, ensure_ascii=False, indent=0)
            st.download_button(
                f"📥 Descargar lista RECIBIDOS ({len(lista_recb):,} CUFEs)",
                data=jsonstr.encode("utf-8"),
                file_name=f"cufes_recibidos_{f_desde}_a_{f_hasta}.json",
                mime="application/json",
                use_container_width=True,
                key="dl_recb_list",
            )
        else:
            st.button("📥 RECIBIDOS (sin docs)", disabled=True, use_container_width=True)

    st.info("""
**Cómo usar las listas:**
1. Descarga la lista que quieras procesar (EMITIDOS y/o RECIBIDOS).
2. Abre el portal DIAN con tu Token activo.
3. Clic en la extensión 📥 Capturador DIAN.
4. Modo: **"Descargar desde lista de CUFEs"**.
5. Sube el archivo `cufes_*.json`.
6. La extensión descarga cada XML uno por uno (sin paginar, sin límites).
7. Al terminar te descarga `xmls_<rango>.json` con los XMLs en base64.
8. Vuelve aquí al **Paso 3** y sube ese archivo.
""")


# ============================================================
# PASO 3: Subir el JSON con XMLs descargados
# ============================================================
st.markdown("---")
st.markdown("## 🗂️ Paso 3 — Procesar XMLs descargados")

xmls_json = st.file_uploader(
    "Sube el archivo `xmls_*.json` que generó la extensión Chrome",
    type=["json"],
    key="uploader_xmls",
)


def decodificar_zip_b64(b64_str: str) -> bytes:
    return base64.b64decode(b64_str)


def extraer_xml(zip_bytes: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".xml"):
                    return zf.read(name).decode("utf-8", errors="replace")
    except zipfile.BadZipFile:
        return None
    return None


if xmls_json is not None:
    try:
        with st.spinner("📖 Leyendo XMLs..."):
            captura = json.loads(xmls_json.read().decode("utf-8"))
    except json.JSONDecodeError as e:
        st.error(f"❌ El archivo no es un JSON válido: {e}")
        st.stop()

    if not isinstance(captura, dict) or "xmls" not in captura:
        st.error("❌ El JSON no tiene la estructura esperada (falta clave 'xmls').")
        st.stop()

    xmls_b64 = captura.get("xmls", {})
    meta_captura = captura.get("meta", {})
    fallidos = captura.get("fallidos", [])
    documentos_meta = captura.get("documentos", [])  # CUFEs originales con metadata

    st.success(
        f"✅ Captura leída: **{len(xmls_b64)} XMLs**. "
        f"Fallidos: {len(fallidos)}."
    )

    if fallidos:
        with st.expander(f"⚠️ {len(fallidos)} fallos durante la descarga", expanded=False):
            df_fail = pd.DataFrame(fallidos[:50])
            st.dataframe(df_fail, use_container_width=True, hide_index=True)
            if len(fallidos) > 50:
                st.caption(f"... y {len(fallidos) - 50} más.")

    # Parsear cada XML
    parsed_xmls = {}
    documentos_raw_para_clasif = []

    progress = st.progress(0.0)
    log_caption = st.empty()
    total = len(xmls_b64)

    with st.spinner(f"🔍 Parseando {total} XMLs..."):
        for i, (cufe, b64) in enumerate(xmls_b64.items()):
            try:
                zb = decodificar_zip_b64(b64)
                xml_str = extraer_xml(zb)
                if xml_str:
                    d = pxml.parsear_xml_dian(xml_str)
                    if d:
                        parsed_xmls[cufe] = d
            except Exception:
                pass
            if (i + 1) % 50 == 0 or i + 1 == total:
                progress.progress((i + 1) / total)
                log_caption.caption(f"   Parseados: {i + 1}/{total}")

    progress.empty()
    log_caption.empty()
    st.success(f"📑 Parseados {len(parsed_xmls)}/{total} XMLs correctamente.")

    # Reconstruir documentos_raw para el clasificador (similar al formato del API)
    for doc_meta in documentos_meta:
        cufe = doc_meta.get("cufe")
        if not cufe:
            continue
        # Convertir fecha YYYY-MM-DD a /Date(ms)/
        fecha_ms = None
        try:
            d_emis = datetime.strptime(doc_meta.get("fecha_emision", ""), "%Y-%m-%d")
            fecha_ms = int(d_emis.timestamp() * 1000)
        except (ValueError, TypeError):
            pass

        tipo_dian = _tipo_dian_desde_nombre(doc_meta.get("tipo_documento", ""))
        documentos_raw_para_clasif.append({
            "Id": cufe,
            "SerieAndNumber": f"{doc_meta.get('prefijo', '')}{doc_meta.get('folio', '')}",
            "DocumentTypeId": tipo_dian,
            "SenderCode": doc_meta.get("nit_emisor", ""),
            "SenderName": doc_meta.get("nombre_emisor", ""),
            "ReceiverCode": doc_meta.get("nit_receptor", ""),
            "ReceiverName": doc_meta.get("nombre_receptor", ""),
            "TotalAmount": doc_meta.get("total", 0),
            "EmissionDate": f"/Date({fecha_ms})/" if fecha_ms else None,
        })

    # Clasificar
    with st.spinner("🔀 Clasificando documentos..."):
        resultado = clf.clasificar_documentos(
            documentos_raw=documentos_raw_para_clasif,
            nit_empresa=NIT_EMPRESA,
            mapeo_prefijos=MAPEO_PREFIJOS,
            parsed_xmls=parsed_xmls,
        )

    st.session_state["resultado_clasif"] = resultado
    st.session_state["resultado_xmls_b64"] = xmls_b64
    st.session_state["resultado_meta"] = meta_captura


# ============================================================
# Resultado
# ============================================================
if "resultado_clasif" in st.session_state:
    resultado: clf.ResultadoClasificacion = st.session_state["resultado_clasif"]
    meta = st.session_state.get("resultado_meta", {})
    xmls_b64 = st.session_state.get("resultado_xmls_b64", {})

    st.markdown("---")
    st.markdown("## 📊 Resultado de la clasificación")

    conteos = resultado.conteos()
    totales = resultado.totales()

    total_ventas = sum(totales.get(c, 0) for c in [clf.CAT_VENTA_POS, clf.CAT_VENTA_STL, clf.CAT_VENTA_OTRA])
    total_compras = totales.get(clf.CAT_COMPRA, 0)
    total_ncs_emit = sum(totales.get(c, 0) for c in [clf.CAT_NC_POS, clf.CAT_NC_STL, clf.CAT_NC_OTRA])
    total_ncs_rec = totales.get(clf.CAT_NC_COMPRA, 0)
    total_ds = totales.get(clf.CAT_DS_EMITIDO, 0)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("💰 Ventas (FE)", f"${total_ventas:,.0f}",
                f"{sum(conteos.get(c, 0) for c in [clf.CAT_VENTA_POS, clf.CAT_VENTA_STL, clf.CAT_VENTA_OTRA])} docs")
    col2.metric("🛒 Compras (FE)", f"${total_compras:,.0f}",
                f"{conteos.get(clf.CAT_COMPRA, 0)} docs")
    col3.metric("📤 NCs emitidas", f"${total_ncs_emit:,.0f}",
                f"{sum(conteos.get(c, 0) for c in [clf.CAT_NC_POS, clf.CAT_NC_STL, clf.CAT_NC_OTRA])} docs")
    col4.metric("📥 NCs recibidas", f"${total_ncs_rec:,.0f}",
                f"{conteos.get(clf.CAT_NC_COMPRA, 0)} docs")
    col5.metric("📄 Doc. soporte", f"${total_ds:,.0f}",
                f"{conteos.get(clf.CAT_DS_EMITIDO, 0)} docs")

    # Tabs por categoría
    st.markdown("### 🗂️ Detalle por categoría")

    categorias_con_docs = [
        (clf.CAT_VENTA_POS,    "🏪 Ventas POS"),
        (clf.CAT_VENTA_STL,    "📦 Ventas STL"),
        (clf.CAT_VENTA_OTRA,   "❓ Ventas otras"),
        (clf.CAT_NC_POS,       "📝 NC POS"),
        (clf.CAT_NC_STL,       "📝 NC STL"),
        (clf.CAT_NC_OTRA,      "📝 NC otras"),
        (clf.CAT_ND_EMITIDA,   "📈 ND emitidas"),
        (clf.CAT_DS_EMITIDO,   "📄 DS emitidos"),
        (clf.CAT_COMPRA,       "🛒 Compras"),
        (clf.CAT_NC_COMPRA,    "📥 NC compras"),
        (clf.CAT_ND_COMPRA,    "📥 ND compras"),
        (clf.CAT_DS_RECIBIDO,  "📥 DS recibidos"),
        (clf.CAT_DESCONOCIDO,  "⚠️ Desconocidos"),
    ]

    visibles = [(cat, lbl) for cat, lbl in categorias_con_docs if conteos.get(cat, 0) > 0]
    if visibles:
        tabs = st.tabs([f"{lbl} ({conteos.get(c, 0)})" for c, lbl in visibles])
        for (cat, _lbl), tab in zip(visibles, tabs):
            with tab:
                docs = resultado.por_categoria[cat]
                df_t = pd.DataFrame([
                    {
                        "Folio": d.folio, "Fecha": d.fecha, "Prefijo": d.prefijo,
                        "Sucursal": d.nombre_sucursal or "—",
                        "Emisor": f"{d.nit_emisor} · {d.nombre_emisor[:30]}",
                        "Receptor": f"{d.nit_receptor} · {d.nombre_receptor[:30]}",
                        "Valor": d.valor_total,
                    }
                    for d in docs
                ])
                df_disp = df_t.copy()
                df_disp["Valor"] = df_disp["Valor"].apply(lambda v: f"${v:,.0f}")
                st.dataframe(df_disp, use_container_width=True, hide_index=True)

                csv = df_t.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    f"⬇️ Descargar {cat}.csv",
                    data=csv,
                    file_name=f"{cat}.csv",
                    mime="text/csv",
                    key=f"dl_csv_{cat}",
                )
    else:
        st.info("No hay documentos clasificados en ninguna categoría.")

    if resultado.prefijos_no_mapeados:
        with st.expander(f"⚠️ Prefijos sin mapear ({len(resultado.prefijos_no_mapeados)})", expanded=False):
            st.caption(
                "Estos prefijos aparecen en tus documentos pero no están configurados "
                "en `datos_punto.json` con su sucursal. Agrega `prefijo_token` "
                "y `prefijo_token_nc` a cada sucursal para clasificarlos."
            )
            df_pref = pd.DataFrame(
                [{"Prefijo": p, "Documentos": c} for p, c in sorted(
                    resultado.prefijos_no_mapeados.items(),
                    key=lambda x: -x[1],
                )]
            )
            st.dataframe(df_pref, use_container_width=True, hide_index=True)

    # ZIP consolidado con XMLs originales
    if xmls_b64:
        st.markdown("### 📦 Archivo de XMLs originales")
        st.caption(f"{len(xmls_b64)} ZIPs (XML+PDF) están dentro de la captura.")
        if st.button("🗜️ Generar ZIP consolidado de XMLs"):
            with st.spinner("Empaquetando..."):
                buf = io.BytesIO()
                track_a_folio = {d.track_id: d.folio for d in resultado.documentos}
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                    for cufe, b64 in xmls_b64.items():
                        folio = track_a_folio.get(cufe, cufe[:12])
                        try:
                            zb = decodificar_zip_b64(b64)
                            zout.writestr(f"{folio}_{cufe[:8]}.zip", zb)
                        except Exception:
                            continue
                buf.seek(0)
            st.download_button(
                "⬇️ Descargar ZIP consolidado",
                data=buf.getvalue(),
                file_name="DIAN_XMLs.zip",
                mime="application/zip",
            )

    st.markdown("---")
    if st.button("🔄 Procesar otra captura"):
        for k in ["resultado_clasif", "resultado_xmls_b64", "resultado_meta"]:
            st.session_state.pop(k, None)
        st.rerun()
