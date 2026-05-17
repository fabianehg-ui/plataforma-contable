"""
app_pages/2_Procesar_Token_DIAN.py

Módulo único de procesamiento que reemplaza a los antiguos:
  - 2_Compras_DIAN.py
  - 3a_Compras_y_Egresos.py
  - 4b_Ingresos_POS.py
  - 5a_DIAN_XML.py

Flujo:
  1. Usuario pega el link Token DIAN (con sesión temporal de 1 hora)
  2. Define rango de fechas de emisión y filtros opcionales
  3. El módulo:
     - Lista documentos del catálogo paginando (con corte temprano por fecha)
     - Descarga ZIPs (XML+PDF) en paralelo
     - Parsea cada XML
     - Clasifica: ventas POS, ventas STL, compras, NCs, ND, DS, etc.
  4. Muestra resultado por categoría, con descargas de planos contables.

Tiempo aprox: 1-3 minutos para 1 mes de operación normal.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa

from core.procesadores import cliente_token_dian as cli
from core.procesadores import clasificador_documentos as clf
from core.procesadores import parser_xml_stl as pxml


# ─── Setup página ────────────────────────────────────────────
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

st.title("📥 Procesar Token DIAN")
st.caption(
    "Pega el link Token DIAN y el sistema lista todos tus documentos, "
    "los descarga, parsea y clasifica automáticamente (ventas POS, STL, compras, NCs)."
)


# ─── Cargar mapeo de prefijos ────────────────────────────────
def cargar_mapeo_prefijos() -> dict:
    """Lee datos_punto.json y construye mapeo prefijo→sucursal."""
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


# ─── Formulario ──────────────────────────────────────────────
with st.form("form_token_dian"):
    st.markdown("### 1️⃣ Link Token DIAN")
    st.caption(
        "El Token tiene una sesión válida de ~1 hora. Genéralo desde el portal "
        "DIAN y pégalo aquí. **No se guarda en ningún lado**: cada procesamiento "
        "requiere un Token nuevo."
    )
    token_url = st.text_input(
        "URL del Token",
        placeholder="https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=...&rk=...&token=...",
        type="password",  # oculta el link en pantalla
        help="El link entero, copiado tal cual del portal DIAN.",
    )

    st.markdown("### 2️⃣ Rango de fechas (emisión)")
    hoy = date.today()
    primer_mes_actual = hoy.replace(day=1)
    ult_mes_ant = primer_mes_actual - timedelta(days=1)
    prim_mes_ant = ult_mes_ant.replace(day=1)

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        fecha_desde = st.date_input("Desde", value=prim_mes_ant, format="YYYY-MM-DD")
    with col_f2:
        fecha_hasta = st.date_input("Hasta", value=ult_mes_ant, format="YYYY-MM-DD")

    st.markdown("### 3️⃣ Filtros (opcional)")
    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    tipo_fe = col_t1.checkbox("Facturas (FE)",      value=True)
    tipo_nc = col_t2.checkbox("Notas crédito (NC)", value=True)
    tipo_nd = col_t3.checkbox("Notas débito (ND)",  value=True)
    tipo_ds = col_t4.checkbox("Doc. soporte (DS)",  value=True)

    descargar_xmls = st.checkbox(
        "Descargar todos los XMLs (más lento, ~3s por cada 10 docs)",
        value=False,
        help=(
            "Si está desmarcado: solo lista y clasifica usando los datos del API. "
            "Más rápido pero sin línea por línea de IVA. "
            "Si está marcado: descarga cada ZIP y parsea cada XML — necesario para "
            "discriminación granular de IVA en STL."
        ),
    )

    submit = st.form_submit_button("🔍 Procesar")


# ─── Procesamiento ───────────────────────────────────────────
if submit:
    if not token_url:
        st.error("Debes pegar el link Token DIAN.")
        st.stop()
    if fecha_desde > fecha_hasta:
        st.error("La fecha 'Desde' es posterior a 'Hasta'.")
        st.stop()

    tipos_seleccionados = []
    if tipo_fe: tipos_seleccionados.append("01")
    if tipo_nc: tipos_seleccionados.append("91")
    if tipo_nd: tipos_seleccionados.append("92")
    if tipo_ds: tipos_seleccionados.append("05")
    if not tipos_seleccionados:
        st.error("Selecciona al menos un tipo de documento.")
        st.stop()

    desde_ms = int(datetime.combine(fecha_desde, datetime.min.time()).timestamp() * 1000)
    hasta_ms = int(datetime.combine(fecha_hasta, datetime.max.time()).timestamp() * 1000)

    # ── Paso 1: Autenticar ──
    with st.spinner("🔐 Autenticando con la DIAN..."):
        try:
            sesion = cli.autenticar(token_url)
            st.success(
                f"✅ Sesión DIAN autenticada para NIT **{sesion.nit_cuenta}**."
            )
        except cli.TokenInvalido as e:
            st.error(f"❌ Token inválido: {e}")
            st.stop()
        except cli.ErrorDIAN as e:
            st.error(f"❌ Error de conexión con DIAN: {e}")
            st.stop()
        except Exception as e:
            st.error(f"❌ Error inesperado en autenticación: {e}")
            st.stop()

    # ── Paso 2: Listar documentos ──
    st.markdown("### 📂 Listando documentos del catálogo...")
    log_listado = st.empty()
    prog_listado = st.progress(0.0)
    progreso_tipo = {"tipo": "", "act": 0, "tot": 0}

    def cb_listar(etiqueta, act, tot):
        progreso_tipo["tipo"] = etiqueta
        progreso_tipo["act"] = act
        progreso_tipo["tot"] = tot
        if tot > 0:
            prog_listado.progress(min(act / tot, 1.0))
        log_listado.caption(
            f"  📄 {etiqueta}: página {act}/{tot}"
        )

    try:
        with st.spinner("Listando del catálogo DIAN..."):
            t0 = datetime.now()
            documentos_raw = sesion.listar_documentos(
                tipos=tipos_seleccionados,
                desde_ms=desde_ms,
                hasta_ms=hasta_ms,
                on_progress=cb_listar,
            )
            tiempo_listado = (datetime.now() - t0).total_seconds()
    except cli.TokenInvalido as e:
        st.error(f"❌ La sesión DIAN expiró durante el listado: {e}")
        st.stop()
    except Exception as e:
        st.error(f"❌ Error listando documentos: {e}")
        with st.expander("Detalle del error"):
            import traceback
            st.code(traceback.format_exc())
        st.stop()

    log_listado.success(
        f"✅ {len(documentos_raw)} documentos encontrados en el rango "
        f"(en {tiempo_listado:.1f}s)"
    )
    prog_listado.progress(1.0)

    if len(documentos_raw) == 0:
        st.warning(
            "No se encontraron documentos en el rango pedido. Verifica las fechas "
            "o si el Token corresponde a la empresa correcta."
        )
        st.stop()

    # ── Paso 3: Descargar XMLs si el usuario lo pidió ──
    parsed_xmls = {}
    track_to_zipbytes = {}  # solo se llena si descargar_xmls
    if descargar_xmls:
        st.markdown("### ⬇️ Descargando XMLs...")
        log_descarga = st.empty()
        prog_descarga = st.progress(0.0)

        def cb_descarga(act, tot):
            prog_descarga.progress(min(act / tot, 1.0))
            log_descarga.caption(f"  📦 {act}/{tot} ZIPs descargados")

        track_ids = [d.get("Id") for d in documentos_raw if d.get("Id")]
        try:
            res_descarga = sesion.descargar_lote(
                track_ids, workers=4, on_progress=cb_descarga,
            )
            track_to_zipbytes = res_descarga["ok"]
            log_descarga.success(
                f"✅ Descargados {len(track_to_zipbytes)}/{len(track_ids)} ZIPs. "
                f"Fallidos: {len(res_descarga['fallidos'])}"
            )
        except cli.TokenInvalido as e:
            st.warning(f"⚠️ La sesión expiró durante descarga: {e}")
        except Exception as e:
            st.warning(f"⚠️ Error en descarga masiva: {e}")

        # Parsear XMLs
        if track_to_zipbytes:
            with st.spinner(f"Parseando {len(track_to_zipbytes)} XMLs..."):
                for tid, zb in track_to_zipbytes.items():
                    xml_str = cli.extraer_xml_de_zip_dian(zb)
                    if xml_str:
                        d = pxml.parsear_xml_dian(xml_str)
                        if d:
                            parsed_xmls[tid] = d
            st.success(f"✅ Parseados {len(parsed_xmls)} XMLs.")

    # ── Paso 4: Clasificar ──
    with st.spinner("🔀 Clasificando documentos..."):
        resultado = clf.clasificar_documentos(
            documentos_raw=documentos_raw,
            nit_empresa=NIT_EMPRESA,
            mapeo_prefijos=MAPEO_PREFIJOS,
            parsed_xmls=parsed_xmls,
        )

    # Guardar en sesión para descargas posteriores
    st.session_state["token_dian_resultado"] = resultado
    st.session_state["token_dian_zips"] = track_to_zipbytes
    st.session_state["token_dian_meta"] = {
        "fecha_desde": fecha_desde.isoformat(),
        "fecha_hasta": fecha_hasta.isoformat(),
        "nit_empresa": NIT_EMPRESA,
        "tiempo_listado_s": round(tiempo_listado, 1),
    }


# ─── Resultado (persistente entre interacciones) ─────────────
if "token_dian_resultado" in st.session_state:
    resultado: clf.ResultadoClasificacion = st.session_state["token_dian_resultado"]
    meta = st.session_state["token_dian_meta"]
    track_to_zipbytes = st.session_state.get("token_dian_zips", {})

    st.markdown("---")
    st.markdown("## 📊 Resultado")

    conteos = resultado.conteos()
    totales = resultado.totales()

    # Métricas principales: ventas vs compras
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
        f"NIT empresa: {meta['nit_empresa']} · Rango: "
        f"{meta['fecha_desde']} → {meta['fecha_hasta']} · "
        f"Listado en {meta['tiempo_listado_s']}s"
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

    # Filtrar solo las que tienen docs
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

                # Exportar como CSV
                csv = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    f"⬇️ Descargar {cat}.csv",
                    data=csv,
                    file_name=f"{cat}_{meta['fecha_desde']}_{meta['fecha_hasta']}.csv",
                    mime="text/csv",
                    key=f"dl_csv_{cat}",
                )

    # Prefijos sin mapear (oportunidad de configurar)
    if resultado.prefijos_no_mapeados:
        with st.expander(f"⚠️ Prefijos sin mapear ({len(resultado.prefijos_no_mapeados)})", expanded=False):
            st.caption(
                "Estos prefijos aparecen en tus documentos pero no están configurados "
                "en `datos_punto.json` con su sucursal. Por ahora van a 'Ventas otras'. "
                "Agrega `prefijo_token` y `prefijo_token_nc` a cada sucursal para "
                "clasificarlos automáticamente."
            )
            df_pref = pd.DataFrame(
                [{"Prefijo": p, "Documentos": c} for p, c in sorted(
                    resultado.prefijos_no_mapeados.items(),
                    key=lambda x: -x[1],
                )]
            )
            st.dataframe(df_pref, use_container_width=True, hide_index=True)

    # Advertencias del clasificador
    if resultado.advertencias:
        with st.expander(f"⚠️ Advertencias ({len(resultado.advertencias)})", expanded=False):
            for adv in resultado.advertencias[:50]:
                st.warning(adv)
            if len(resultado.advertencias) > 50:
                st.caption(f"... y {len(resultado.advertencias) - 50} más.")

    # Descarga del ZIP completo de XMLs (si se descargaron)
    if track_to_zipbytes:
        st.markdown("### 📦 Archivo de XMLs originales")
        st.caption(
            f"{len(track_to_zipbytes)} ZIPs descargados (cada uno trae XML + PDF). "
            "Útil para archivado o auditoría."
        )
        if st.button("🗜️ Generar ZIP consolidado de XMLs"):
            with st.spinner("Empaquetando..."):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
                    track_a_folio = {
                        d.track_id: d.folio for d in resultado.documentos
                    }
                    for tid, zb in track_to_zipbytes.items():
                        folio = track_a_folio.get(tid, tid[:12])
                        zout.writestr(f"{folio}_{tid[:8]}.zip", zb)
                buf.seek(0)
            st.download_button(
                "⬇️ Descargar ZIP consolidado",
                data=buf.getvalue(),
                file_name=f"DIAN_XMLs_{meta['fecha_desde']}_a_{meta['fecha_hasta']}.zip",
                mime="application/zip",
            )

    # Botón para limpiar resultado y procesar otro Token
    st.markdown("---")
    if st.button("🔄 Procesar otro Token"):
        for k in ["token_dian_resultado", "token_dian_zips", "token_dian_meta"]:
            st.session_state.pop(k, None)
        st.rerun()
