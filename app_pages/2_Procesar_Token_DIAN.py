"""
app_pages/2_Procesar_Token_DIAN.py

Módulo único de procesamiento de documentos DIAN.

Flujo:
  1. Usuario instala la extensión Chrome "Capturador DIAN" (1 vez por PC).
  2. Va al portal DIAN (con su sesión normal), hace clic en la extensión,
     define rango de fechas, clic en "Iniciar captura".
  3. La extensión pagina el portal con la sesión real y descarga un archivo
     dian_captura_*.json con los documentos + XMLs originales.
  4. Aquí en este módulo, sube ese JSON.
  5. El sistema procesa, clasifica y muestra resultados.

Reemplaza los antiguos:
  - 2_Compras_DIAN.py
  - 3a_Compras_y_Egresos.py
  - 4b_Ingresos_POS.py
  - 5a_DIAN_XML.py
"""
from __future__ import annotations

import base64
import io
import json
import sys
import zipfile
from datetime import datetime
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


# ─── Setup página ────────────────────────────────────────────
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

st.title("📥 Procesar Token DIAN")
st.caption(
    "Procesa documentos electrónicos DIAN (ventas POS, STL, compras, NCs, DS) "
    "desde una captura del portal hecha con la extensión Chrome."
)


# ─── Cargar mapeo de prefijos ────────────────────────────────
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


# ─── Sección 1: Instrucciones de la extensión ─────────────────
with st.expander("🧩 ¿Primera vez usando la extensión Chrome?", expanded=False):
    st.markdown("""
**Instalación (una sola vez por PC):**

1. Descarga el ZIP de la extensión (te lo pasamos aparte).
2. Descomprime en una carpeta permanente (ej. `C:\\contatools\\extension_dian\\`).
3. Abre Chrome → `chrome://extensions/`.
4. Activa el switch **"Modo de desarrollador"** (arriba a la derecha).
5. Clic en **"Cargar extensión descomprimida"** y selecciona la carpeta del paso 2.
6. Listo, aparece el icono 📥 en la barra de Chrome.

**Uso (cada vez que vas a procesar):**

1. Abre el portal DIAN: [catalogo-vpfe.dian.gov.co](https://catalogo-vpfe.dian.gov.co/) e inicia sesión.
2. Una vez dentro, clic en el icono **📥 Capturador DIAN** de la barra.
3. Define rango de fechas (ej. todo marzo 2026).
4. Marca los tipos (FE, NC, ND, DS) y los modos (emitidos y/o recibidos).
5. Clic en **🚀 Iniciar captura**.
6. Espera (varios minutos para meses con mucha operación).
7. Al terminar se descarga `dian_captura_2026-03-01_a_2026-03-31.json`.
8. Vuelve aquí y arrastra ese JSON al uploader de abajo.
""")


# ─── Sección 2: Uploader del JSON capturado ─────────────────
st.markdown("### 📤 Sube tu captura DIAN")
archivo = st.file_uploader(
    "Arrastra aquí el archivo `dian_captura_*.json` que generó la extensión",
    type=["json"],
    accept_multiple_files=False,
    help="Si no tienes el archivo, sigue las instrucciones de arriba para generarlo.",
)


# ─── Sección 3: Procesar el JSON ─────────────────────────────
def parsear_captura_json(archivo) -> dict:
    """Lee y valida el JSON capturado por la extensión."""
    try:
        contenido = archivo.read().decode("utf-8")
        captura = json.loads(contenido)
    except json.JSONDecodeError as e:
        raise ValueError(f"El archivo no es un JSON válido: {e}")

    if not isinstance(captura, dict):
        raise ValueError("El JSON no tiene la estructura esperada (debe ser un objeto).")
    if "documentos" not in captura:
        raise ValueError("El JSON no tiene la clave 'documentos'. ¿Es realmente una captura DIAN?")
    if not isinstance(captura["documentos"], list):
        raise ValueError("La clave 'documentos' debe ser una lista.")

    xmls = captura.get("xmls") or {}
    if not isinstance(xmls, dict):
        xmls = {}

    return {
        "meta": captura.get("meta", {}),
        "documentos": captura["documentos"],
        "xmls": xmls,
        "fallidos": captura.get("fallidos", []),
        "log": captura.get("log", []),
    }


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


if archivo is not None:
    with st.spinner("📖 Leyendo captura..."):
        try:
            captura = parsear_captura_json(archivo)
        except ValueError as e:
            st.error(f"❌ {e}")
            st.stop()

    meta = captura["meta"]
    documentos_raw = captura["documentos"]
    xmls_b64 = captura["xmls"]

    st.success(
        f"✅ Captura leída: **{len(documentos_raw)} documentos** "
        f"de {meta.get('fechaDesde','?')} a {meta.get('fechaHasta','?')}. "
        f"XMLs incluidos: {len(xmls_b64)}."
    )

    if captura["fallidos"]:
        with st.expander(f"⚠️ {len(captura['fallidos'])} fallos durante la captura", expanded=False):
            st.json(captura["fallidos"][:50])

    # Parsear XMLs si vinieron
    parsed_xmls = {}
    if xmls_b64:
        with st.spinner(f"🔍 Parseando {len(xmls_b64)} XMLs..."):
            for tid, b64 in xmls_b64.items():
                try:
                    zb = decodificar_zip_b64(b64)
                    xml_str = extraer_xml(zb)
                    if xml_str:
                        d = pxml.parsear_xml_dian(xml_str)
                        if d:
                            parsed_xmls[tid] = d
                except Exception:
                    continue
        st.caption(f"📑 Parseados {len(parsed_xmls)} XMLs correctamente.")

    # Clasificar
    with st.spinner("🔀 Clasificando documentos..."):
        resultado = clf.clasificar_documentos(
            documentos_raw=documentos_raw,
            nit_empresa=NIT_EMPRESA,
            mapeo_prefijos=MAPEO_PREFIJOS,
            parsed_xmls=parsed_xmls,
        )

    st.session_state["captura_resultado"] = resultado
    st.session_state["captura_xmls_b64"] = xmls_b64
    st.session_state["captura_meta"] = meta


# ─── Sección 4: Resultado ────────────────────────────────────
if "captura_resultado" in st.session_state:
    resultado: clf.ResultadoClasificacion = st.session_state["captura_resultado"]
    meta = st.session_state["captura_meta"]
    xmls_b64 = st.session_state.get("captura_xmls_b64", {})

    st.markdown("---")
    st.markdown("## 📊 Resultado")

    conteos = resultado.conteos()
    totales = resultado.totales()

    total_ventas = sum(totales.get(c, 0) for c in [
        clf.CAT_VENTA_POS, clf.CAT_VENTA_STL, clf.CAT_VENTA_OTRA
    ])
    total_compras = totales.get(clf.CAT_COMPRA, 0)
    total_ncs_emitidas = sum(totales.get(c, 0) for c in [
        clf.CAT_NC_POS, clf.CAT_NC_STL, clf.CAT_NC_OTRA
    ])
    total_ncs_recibidas = totales.get(clf.CAT_NC_COMPRA, 0)
    total_ds = totales.get(clf.CAT_DS_EMITIDO, 0)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("💰 Ventas (FE)", f"${total_ventas:,.0f}",
                f"{sum(conteos.get(c, 0) for c in [clf.CAT_VENTA_POS, clf.CAT_VENTA_STL, clf.CAT_VENTA_OTRA])} docs")
    col2.metric("🛒 Compras (FE)", f"${total_compras:,.0f}",
                f"{conteos.get(clf.CAT_COMPRA, 0)} docs")
    col3.metric("📤 NCs emitidas", f"${total_ncs_emitidas:,.0f}",
                f"{sum(conteos.get(c, 0) for c in [clf.CAT_NC_POS, clf.CAT_NC_STL, clf.CAT_NC_OTRA])} docs")
    col4.metric("📥 NCs recibidas", f"${total_ncs_recibidas:,.0f}",
                f"{conteos.get(clf.CAT_NC_COMPRA, 0)} docs")
    col5.metric("📄 Doc. soporte", f"${total_ds:,.0f}",
                f"{conteos.get(clf.CAT_DS_EMITIDO, 0)} docs")

    st.caption(
        f"NIT empresa: {NIT_EMPRESA} · Rango: "
        f"{meta.get('fechaDesde','?')} → {meta.get('fechaHasta','?')} · "
        f"Capturado en {meta.get('generadoEn','?')}"
    )

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

    visibles = [(cat, label) for cat, label in categorias_con_docs if conteos.get(cat, 0) > 0]

    if not visibles:
        st.info("No hay documentos clasificados en ninguna categoría.")
    else:
        tabs = st.tabs([f"{label} ({conteos.get(cat, 0)})" for cat, label in visibles])
        for (cat, _label), tab in zip(visibles, tabs):
            with tab:
                docs = resultado.por_categoria[cat]
                df = pd.DataFrame([
                    {
                        "Folio":     d.folio,
                        "Fecha":     d.fecha,
                        "Prefijo":   d.prefijo,
                        "Sucursal":  d.nombre_sucursal or "—",
                        "Emisor":    f"{d.nit_emisor} · {d.nombre_emisor[:30]}",
                        "Receptor":  f"{d.nit_receptor} · {d.nombre_receptor[:30]}",
                        "Valor":     d.valor_total,
                    }
                    for d in docs
                ])
                df_disp = df.copy()
                df_disp["Valor"] = df_disp["Valor"].apply(lambda v: f"${v:,.0f}")
                st.dataframe(df_disp, use_container_width=True, hide_index=True)

                csv = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    f"⬇️ Descargar {cat}.csv",
                    data=csv,
                    file_name=f"{cat}_{meta.get('fechaDesde','rango')}_{meta.get('fechaHasta','rango')}.csv",
                    mime="text/csv",
                    key=f"dl_csv_{cat}",
                )

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

    if resultado.advertencias:
        with st.expander(f"⚠️ Advertencias ({len(resultado.advertencias)})", expanded=False):
            for adv in resultado.advertencias[:50]:
                st.warning(adv)
            if len(resultado.advertencias) > 50:
                st.caption(f"... y {len(resultado.advertencias) - 50} más.")

    # ZIP consolidado con XMLs originales
    if xmls_b64:
        st.markdown("### 📦 Archivo de XMLs originales")
        st.caption(
            f"{len(xmls_b64)} ZIPs (XML+PDF) están dentro de la captura. "
            "Útil para archivado o auditoría."
        )
        if st.button("🗜️ Generar ZIP consolidado de XMLs"):
            with st.spinner("Empaquetando..."):
                buf = io.BytesIO()
                track_a_folio = {d.track_id: d.folio for d in resultado.documentos}
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                    for tid, b64 in xmls_b64.items():
                        folio = track_a_folio.get(tid, tid[:12])
                        try:
                            zb = decodificar_zip_b64(b64)
                            zout.writestr(f"{folio}_{tid[:8]}.zip", zb)
                        except Exception:
                            continue
                buf.seek(0)
            st.download_button(
                "⬇️ Descargar ZIP consolidado",
                data=buf.getvalue(),
                file_name=f"DIAN_XMLs_{meta.get('fechaDesde','rango')}_a_{meta.get('fechaHasta','rango')}.zip",
                mime="application/zip",
            )

    st.markdown("---")
    if st.button("🔄 Procesar otra captura"):
        for k in ["captura_resultado", "captura_xmls_b64", "captura_meta"]:
            st.session_state.pop(k, None)
        st.rerun()
