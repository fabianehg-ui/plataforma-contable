"""
📥 DIAN XML — Procesamiento masivo multi-empresa, multi-zip
Página Streamlit v0.2

Flujo soportado:
1. Usuario sube N ZIPs descargados del bookmarklet (típicamente uno por tipo: FE, NC, ND, DS)
2. Sistema deduplica por CUFE, filtra por rango de fechas, detecta empresa por NIT receptor
3. Aplica mapeo NIT + reglas ítem (con auto-detección de servicios públicos)
4. Genera plano contable (consolidado o separado por comprobante)
5. Reporte ejecutivo con KPIs
"""
import io
import json
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st

from core.procesadores.procesador_dian_xml import (
    RegistryEmpresas,
    procesar_multiples_zips,
    separar_lineas_por_comprobante,
    generar_reporte_ejecutivo,
    exportar_plano_txt,
    es_servicio_publico,
    ZipInput,
)

EMPRESAS_DIR = Path("core/data/empresas")

st.set_page_config(page_title="DIAN XML", page_icon="📥", layout="wide")

st.title("📥 DIAN XML — Procesamiento masivo multi-empresa")
st.caption(
    "Sube los ZIPs descargados del bookmarklet (uno por tipo: FE, NC, ND, DS). "
    "El sistema los junta, deduplica, aplica mapeo NIT + reglas de ítem y genera el plano contable."
)

# ----------------------------------------------------------- Registry
@st.cache_resource
def cargar_registry():
    return RegistryEmpresas(EMPRESAS_DIR)


try:
    registry = cargar_registry()
    empresas = registry.listar()
except Exception as e:
    st.error(f"⚠️ No se pudo cargar el índice de empresas: {e}")
    st.stop()

# ----------------------------------------------------------- Tabs
tab_proc, tab_mapeo, tab_empresas = st.tabs(
    ["📥 Procesar XML", "🗂️ Editor de mapeo", "🏢 Empresas configuradas"]
)

# ============================================================================
# TAB 1: PROCESAR — UPLOADER MÚLTIPLE
# ============================================================================
with tab_proc:
    st.subheader("1️⃣ Sube los ZIPs (uno por tipo de documento)")

    col_fe, col_nc, col_nd, col_ds = st.columns(4)
    with col_fe:
        st.markdown("**📄 Facturas Electrónicas**")
        zip_fe = st.file_uploader("FE", type=["zip"], key="zip_fe", label_visibility="collapsed",
                                   accept_multiple_files=True, help="ZIP descargado del bookmarklet con tipo='Factura electrónica'")
    with col_nc:
        st.markdown("**🔻 Notas Crédito**")
        zip_nc = st.file_uploader("NC", type=["zip"], key="zip_nc", label_visibility="collapsed",
                                   accept_multiple_files=True, help="ZIP con notas crédito recibidas")
    with col_nd:
        st.markdown("**🔺 Notas Débito**")
        zip_nd = st.file_uploader("ND", type=["zip"], key="zip_nd", label_visibility="collapsed",
                                   accept_multiple_files=True, help="ZIP con notas débito recibidas")
    with col_ds:
        st.markdown("**🏛️ Servicios Públicos**")
        zip_ds = st.file_uploader("DS", type=["zip"], key="zip_ds", label_visibility="collapsed",
                                   accept_multiple_files=True,
                                   help="ZIP con FE de empresas de servicios públicos (EPM, Codensa, EAAB, Claro, etc.)")

    archivos_subidos = (
        [(f, "FE") for f in (zip_fe or [])] +
        [(f, "NC") for f in (zip_nc or [])] +
        [(f, "ND") for f in (zip_nd or [])] +
        [(f, "DS") for f in (zip_ds or [])]
    )

    if archivos_subidos:
        total_mb = sum(f.size for f, _ in archivos_subidos) / (1024 * 1024)
        st.success(f"📦 {len(archivos_subidos)} archivo(s) cargado(s) · {total_mb:.2f} MB total")

    # ----------------------------------------------------------- Configuración
    st.markdown("---")
    st.subheader("2️⃣ Configuración del procesamiento")

    c1, c2, c3 = st.columns(3)
    with c1:
        anio = st.number_input("Año contable", min_value=2020, max_value=2030, value=date.today().year)
        mes = st.number_input("Mes contable", min_value=1, max_value=12, value=date.today().month)
        anio_mes = f"{anio}{mes:02d}"

    with c2:
        modo_filtro = st.radio(
            "Filtrar por fecha",
            ["No filtrar (procesar todo)", "Por fecha de emisión", "Por fecha de recepción DIAN"],
            index=0,
            help=(
                "📌 Recomendado: 'No filtrar' la primera vez para ver todo lo que descargaste.\n\n"
                "**Emisión** = fecha en que el proveedor creó el documento.\n\n"
                "**Recepción DIAN** = fecha en que DIAN recibió el documento "
                "(se extrae del nombre del archivo descargado por el bookmarklet)."
            ),
        )
        modo_filtro_codigo = {
            "No filtrar (procesar todo)": "ninguno",
            "Por fecha de emisión": "emision",
            "Por fecha de recepción DIAN": "recepcion",
        }[modo_filtro]
        fecha_desde = ""
        fecha_hasta = ""
        if modo_filtro_codigo != "ninguno":
            ultimo_dia = (date(anio + (1 if mes == 12 else 0), (mes % 12) + 1, 1)
                          - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            fecha_desde = st.date_input("Desde", value=date(anio, mes, 1)).strftime("%Y-%m-%d")
            fecha_hasta = st.date_input("Hasta", value=date.fromisoformat(ultimo_dia)).strftime("%Y-%m-%d")

    with c3:
        forzar_empresa = st.selectbox(
            "Empresa",
            ["(detectar por NIT receptor)"] + [f"{e['razon_social']} (NIT {e['nit']})" for e in empresas],
            help="Por defecto se detecta por NIT receptor de cada XML."
        )
        modo_plano = st.radio(
            "Plano resultante",
            ["Plano único consolidado", "Separado por comprobante"],
            help="Algunos sistemas contables prefieren cargar un .txt por comprobante (COMP 7 separado de COMP 13, etc.)"
        )

    # ----------------------------------------------------------- BOTÓN PROCESAR
    st.markdown("---")
    if archivos_subidos and st.button("🚀 Procesar todos los ZIPs", type="primary", use_container_width=True):
        zips_input = []
        for f, tipo in archivos_subidos:
            zips_input.append(ZipInput(nombre=f.name, contenido=f.read(), tipo_declarado=tipo))

        emp_forzada = None
        if not forzar_empresa.startswith("("):
            for e in empresas:
                if e["razon_social"] in forzar_empresa:
                    emp_forzada = e["id"]
                    break

        with st.spinner(f"Procesando {len(zips_input)} ZIP(s)..."):
            try:
                resultados, resumen = procesar_multiples_zips(
                    zips_input, registry, anio_mes,
                    fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
                    empresa_id_forzada=emp_forzada,
                    modo_filtro_fecha=modo_filtro_codigo,
                )
            except Exception as ex:
                st.error(f"Error procesando: {ex}")
                st.exception(ex)
                st.stop()

        st.session_state["resultados"] = resultados
        st.session_state["resumen"] = resumen
        st.session_state["anio_mes"] = anio_mes
        st.session_state["modo_plano"] = modo_plano

    # ----------------------------------------------------------- RESULTADOS
    if "resultados" in st.session_state:
        resultados = st.session_state["resultados"]
        resumen = st.session_state["resumen"]
        modo_plano = st.session_state.get("modo_plano", "Plano único consolidado")

        st.markdown("---")
        st.subheader("3️⃣ Resumen de ingesta")

        col_r1, col_r2, col_r3, col_r4, col_r5 = st.columns(5)
        col_r1.metric("XMLs extraídos", resumen.total_xmls_extraidos)
        col_r2.metric("Duplicados descartados", resumen.duplicados_descartados,
                      delta_color="off" if resumen.duplicados_descartados == 0 else "inverse")
        col_r3.metric("Fuera de rango", resumen.fuera_de_rango_fecha,
                      delta_color="off" if resumen.fuera_de_rango_fecha == 0 else "inverse")
        col_r4.metric("Errores parseo", resumen.errores_parseo,
                      delta_color="off" if resumen.errores_parseo == 0 else "inverse")
        col_r5.metric("Empresas detectadas", len(resumen.por_empresa))

        # Distribución por tipo
        if resumen.por_tipo:
            st.markdown("**Distribución por tipo:**")
            tipos_label = {
                "factura_recibida": "📄 Facturas",
                "nota_credito_recibida": "🔻 NC",
                "nota_debito_recibida": "🔺 ND",
                "documento_soporte_recibido": "📋 DS",
            }
            cols = st.columns(len(resumen.por_tipo))
            for col, (tipo, n) in zip(cols, resumen.por_tipo.items()):
                col.metric(tipos_label.get(tipo, tipo), n)

        # Inconsistencias
        if resumen.inconsistencias_tipo:
            with st.expander(f"⚠️ {len(resumen.inconsistencias_tipo)} inconsistencia(s) tipo declarado vs real"):
                df_inc = pd.DataFrame(resumen.inconsistencias_tipo)
                st.dataframe(df_inc, use_container_width=True, hide_index=True)
                st.caption("Esto suele ocurrir si el ZIP descargado tenía 'Todos' como filtro. El sistema procesa los XMLs según su tipo real.")

        # Detalle de descartados (NUEVO en v0.2.1)
        if resumen.descartados_detalle:
            with st.expander(
                f"🔍 Ver detalle de los {len(resumen.descartados_detalle)} documento(s) descartado(s)",
                expanded=False,
            ):
                st.caption(
                    "Aquí puedes ver exactamente qué documentos NO entraron al plano y por qué. "
                    "Usa esta información para ajustar el filtro de fechas o detectar duplicados inesperados."
                )
                df_desc = pd.DataFrame(resumen.descartados_detalle)
                # Ordenar columnas para que sean legibles
                cols_orden = [c for c in [
                    "razon", "documento", "tipo", "fecha_emision", "fecha_recepcion",
                    "valor", "nit_emisor", "nombre_emisor", "modo_filtro", "cufe", "zip", "archivo", "error"
                ] if c in df_desc.columns]
                df_desc = df_desc[cols_orden]
                st.dataframe(df_desc, use_container_width=True, hide_index=True,
                             column_config={
                                 "valor": st.column_config.NumberColumn(format="$%d"),
                             })

                # Botón para descargar el detalle
                buf_desc = io.BytesIO()
                df_desc.to_excel(buf_desc, index=False)
                st.download_button(
                    "⬇️ Descargar detalle de descartados (.xlsx)",
                    data=buf_desc.getvalue(),
                    file_name=f"descartados_{st.session_state.get('anio_mes', 'XXXXXX')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

        # ----------------------------------------------------------- POR EMPRESA
        st.markdown("---")
        st.subheader(f"4️⃣ Resultados por empresa ({len(resultados)})")

        for r in resultados:
            cuadre_emoji = "✅" if r.cuadrado else "❌"
            with st.expander(
                f"{cuadre_emoji} {r.empresa_razon_social} — "
                f"{len(r.documentos)} doc(s) · {len(r.lineas_plano)} líneas · "
                f"Db ${r.cuadre_db:,.0f} = Cr ${r.cuadre_cr:,.0f}",
                expanded=True,
            ):
                if r.advertencias:
                    for adv in r.advertencias:
                        st.warning(f"⚠️ {adv}")

                if r.empresa_id == "(no identificada)":
                    st.error("Estos documentos no pueden generarse en plano hasta que se configure la empresa receptora.")
                    df = pd.DataFrame([
                        {
                            "NIT receptor": d.nit_receptor,
                            "Receptor": d.nombre_receptor,
                            "NIT emisor": d.nit_emisor,
                            "Emisor": d.nombre_emisor,
                            "Fecha": d.fecha_emision,
                            "Doc": f"{d.prefijo}{d.numero}",
                            "Valor": float(d.valor_total),
                        }
                        for d in r.documentos
                    ])
                    st.dataframe(df, use_container_width=True, hide_index=True)
                    continue

                t1, t2, t3, t4, t5 = st.tabs([
                    "📊 Reporte ejecutivo",
                    "📋 Plano contable",
                    "📄 Documentos",
                    "🆕 NITs pendientes",
                    "💾 Descargar"
                ])

                # --- TAB Reporte ejecutivo
                with t1:
                    rep = generar_reporte_ejecutivo(r)
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Compras netas", f"${rep['total_compras_netas']:,.0f}")
                    c2.metric("IVA descontable", f"${rep['total_iva_descontable']:,.0f}")
                    c3.metric("Retenciones practicadas", f"${rep['total_retenciones_practicadas']:,.0f}")
                    c4.metric("NITs sin mapear",
                              rep['nits_pendientes_mapeo'],
                              delta_color="off" if rep['nits_pendientes_mapeo'] == 0 else "inverse")

                    st.markdown("**Distribución por tipo de documento:**")
                    df_tipo = pd.DataFrame([
                        {"Tipo": k.replace("_", " ").title(),
                         "Cantidad": v["cantidad"],
                         "Valor neto": v["valor_total"],
                         "IVA": v["iva"]}
                        for k, v in rep["por_tipo"].items()
                    ])
                    st.dataframe(df_tipo, use_container_width=True, hide_index=True,
                                 column_config={
                                     "Valor neto": st.column_config.NumberColumn(format="$%d"),
                                     "IVA": st.column_config.NumberColumn(format="$%d"),
                                 })

                    st.markdown("**Top 10 proveedores:**")
                    df_prov = pd.DataFrame(rep["top_proveedores"])
                    if not df_prov.empty:
                        st.dataframe(df_prov, use_container_width=True, hide_index=True,
                                     column_config={
                                         "valor": st.column_config.NumberColumn("Valor", format="$%d"),
                                         "cantidad": st.column_config.NumberColumn("# Docs"),
                                     })

                # --- TAB Plano
                with t2:
                    if r.lineas_plano:
                        df = pd.DataFrame([
                            {
                                "Fecha": l.fecha,
                                "Comp": l.comprobante,
                                "Consec": l.consecutivo,
                                "Cuenta": l.cuenta,
                                "CC": l.centro_costo,
                                "NIT": l.nit_tercero,
                                "Descripción": l.descripcion,
                                "Doc": l.documento_referencia,
                                "Débito": float(l.debito),
                                "Crédito": float(l.credito),
                            }
                            for l in r.lineas_plano
                        ])
                        st.dataframe(df, use_container_width=True, hide_index=True,
                                     column_config={
                                         "Débito": st.column_config.NumberColumn(format="$%d"),
                                         "Crédito": st.column_config.NumberColumn(format="$%d"),
                                     })

                # --- TAB Documentos
                with t3:
                    df_docs = pd.DataFrame([
                        {
                            "Fecha": d.fecha_emision,
                            "Tipo": d.tipo_nombre.replace("_", " ").title(),
                            "ZIP origen": d.zip_origen,
                            "NIT": d.nit_emisor,
                            "Emisor": d.nombre_emisor,
                            "Doc": f"{d.prefijo}{d.numero}",
                            "Valor": float(d.valor_total),
                            "Ítems": len(d.items),
                            "Pendiente": "⚠️ Sí" if d.pendiente_revision else "",
                        }
                        for d in r.documentos
                    ])
                    st.dataframe(df_docs, use_container_width=True, hide_index=True,
                                 column_config={
                                     "Valor": st.column_config.NumberColumn(format="$%d"),
                                 })

                # --- TAB NITs pendientes
                with t4:
                    if r.nits_pendientes:
                        st.warning(
                            f"⚠️ {len(r.nits_pendientes)} NIT(s) sin mapeo. "
                            "Estos documentos van a la cuenta fallback (519095). "
                            "Catalogalos en la pestaña '🗂️ Editor de mapeo' y vuelve a procesar."
                        )
                        df_pend = pd.DataFrame([
                            {
                                "NIT": p["nit"],
                                "Razón social": p["nombre"],
                                "Documentos": p["documentos"],
                                "Valor total": float(p["valor_total"]),
                            }
                            for p in r.nits_pendientes
                        ])
                        st.dataframe(df_pend, use_container_width=True, hide_index=True,
                                     column_config={
                                         "Valor total": st.column_config.NumberColumn(format="$%d"),
                                     })

                        # Sugerencias automáticas para servicios públicos
                        sugerencias_sp = []
                        for p in r.nits_pendientes:
                            for d in r.documentos:
                                if d.nit_emisor == p["nit"]:
                                    es_sp, tipo_sp = es_servicio_publico(d)
                                    if es_sp:
                                        sugerencias_sp.append({
                                            "NIT": p["nit"],
                                            "Nombre": p["nombre"],
                                            "Tipo detectado": tipo_sp,
                                            "Cuenta sugerida": {
                                                "energia": "513525",
                                                "agua": "513530",
                                                "gas": "513540",
                                                "telecomunicaciones": "513535",
                                                "aseo": "513545",
                                            }.get(tipo_sp, "513525"),
                                        })
                                        break
                        if sugerencias_sp:
                            st.info("💡 **Sugerencias automáticas** — estos NITs parecen ser servicios públicos:")
                            df_sug = pd.DataFrame(sugerencias_sp)
                            st.dataframe(df_sug, use_container_width=True, hide_index=True)
                    else:
                        st.success("✅ Todos los NITs están catalogados.")

                # --- TAB Descargar
                with t5:
                    if not r.lineas_plano:
                        st.info("Sin líneas de plano para descargar.")
                    else:
                        nombre_base = f"plano_{r.empresa_id}_{st.session_state['anio_mes']}"

                        if modo_plano == "Plano único consolidado":
                            st.markdown("##### Plano único consolidado")
                            colA, colB = st.columns(2)
                            with colA:
                                st.download_button(
                                    "⬇️ Plano contable (.txt)",
                                    data=exportar_plano_txt(r.lineas_plano),
                                    file_name=f"{nombre_base}.txt",
                                    mime="text/plain",
                                    use_container_width=True,
                                )
                            with colB:
                                df_exp = pd.DataFrame([
                                    {
                                        "FECHA": l.fecha, "COMPROBANTE": l.comprobante,
                                        "CONSECUTIVO": l.consecutivo, "CUENTA": l.cuenta,
                                        "CENTRO_COSTO": l.centro_costo, "NIT_TERCERO": l.nit_tercero,
                                        "DESCRIPCION": l.descripcion, "DOCUMENTO_REF": l.documento_referencia,
                                        "DEBITO": float(l.debito), "CREDITO": float(l.credito),
                                    }
                                    for l in r.lineas_plano
                                ])
                                buf_xlsx = io.BytesIO()
                                df_exp.to_excel(buf_xlsx, index=False)
                                st.download_button(
                                    "⬇️ Plano contable (.xlsx)",
                                    data=buf_xlsx.getvalue(),
                                    file_name=f"{nombre_base}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True,
                                )
                        else:
                            st.markdown("##### Plano separado por comprobante")
                            separado = separar_lineas_por_comprobante(r.lineas_plano)
                            # ZIP con un .txt por comprobante
                            buf = io.BytesIO()
                            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                                for comp, lineas in separado.items():
                                    fname = f"{nombre_base}_{comp.replace(' ', '')}.txt"
                                    z.writestr(fname, exportar_plano_txt(lineas))
                            st.download_button(
                                f"⬇️ ZIP con {len(separado)} planos (uno por comprobante)",
                                data=buf.getvalue(),
                                file_name=f"{nombre_base}_separados.zip",
                                mime="application/zip",
                                use_container_width=True,
                            )
                            # Mostrar resumen
                            st.markdown("**Contenido del ZIP:**")
                            df_sep = pd.DataFrame([
                                {
                                    "Comprobante": comp,
                                    "Líneas": len(ls),
                                    "Débito total": sum(float(l.debito) for l in ls),
                                    "Crédito total": sum(float(l.credito) for l in ls),
                                    "Cuadra": "✅" if sum(l.debito for l in ls) == sum(l.credito for l in ls) else "❌",
                                }
                                for comp, ls in separado.items()
                            ])
                            st.dataframe(df_sep, use_container_width=True, hide_index=True,
                                         column_config={
                                             "Débito total": st.column_config.NumberColumn(format="$%d"),
                                             "Crédito total": st.column_config.NumberColumn(format="$%d"),
                                         })

                        # Reporte ejecutivo JSON
                        st.markdown("##### Reporte ejecutivo")
                        rep = generar_reporte_ejecutivo(r)
                        st.download_button(
                            "⬇️ Reporte ejecutivo (.json)",
                            data=json.dumps(rep, indent=2, ensure_ascii=False, default=str),
                            file_name=f"reporte_{r.empresa_id}_{st.session_state['anio_mes']}.json",
                            mime="application/json",
                            use_container_width=True,
                        )

# ============================================================================
# TAB 2: EDITOR DE MAPEO
# ============================================================================
with tab_mapeo:
    st.subheader("🗂️ Editor de mapeo NIT → Cuenta + Centro de Costo")

    emp_seleccionada = st.selectbox(
        "Empresa",
        empresas,
        format_func=lambda e: f"{e['razon_social']} (NIT {e['nit']})",
        key="mapeo_empresa",
    )

    bundle = registry.cargar(emp_seleccionada["id"])
    mapeo = bundle["mapeo"]["mapeo"]
    centros = bundle["centros_costo"]["centros_costo"]

    st.markdown(f"**Centros de costo válidos:** `{', '.join(centros.keys())}`")
    st.markdown(f"**Cuenta fallback (NIT no catalogado):** `{bundle['mapeo']['_fallback_global']['cuenta']}`")

    st.markdown("---")
    st.markdown(f"**NITs catalogados para {emp_seleccionada['razon_social']}: {len(mapeo)}**")

    if mapeo:
        df_map = pd.DataFrame([
            {
                "NIT": nit,
                "Razón social": data.get("razon_social", ""),
                "Tipo retención": data.get("tipo_retencion", ""),
                "Cuenta default": data.get("default", {}).get("cuenta", ""),
                "CC default": data.get("default", {}).get("centro_costo", ""),
                "Concepto": data.get("default", {}).get("concepto", ""),
                "Reglas ítem": len(data.get("reglas_item", [])),
            }
            for nit, data in mapeo.items()
        ])
        st.dataframe(df_map, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.info(
        "📝 La edición desde la UI está pendiente para v0.3. "
        f"Por ahora edita directamente: `{EMPRESAS_DIR / emp_seleccionada['carpeta'] / 'mapeo_nits.json'}`"
    )

    st.download_button(
        "⬇️ Descargar mapeo_nits.json (para editar)",
        data=json.dumps(bundle["mapeo"], indent=2, ensure_ascii=False, default=str),
        file_name=f"mapeo_nits_{emp_seleccionada['id']}.json",
        mime="application/json",
    )

    # Cargar catálogo de servicios públicos como referencia
    sp_path = EMPRESAS_DIR / "_servicios_publicos_base.json"
    if sp_path.exists():
        st.markdown("---")
        st.markdown("### 🏛️ Catálogo base de servicios públicos colombianos")
        st.caption(
            "Estos NITs y reglas son comunes a todas las empresas. Puedes copiarlos al "
            "`mapeo_nits.json` de tu empresa según los servicios públicos que recibe."
        )
        sp_data = json.loads(sp_path.read_text(encoding="utf-8"))
        df_sp = pd.DataFrame([
            {
                "NIT": nit,
                "Razón social": data["razon_social"],
                "Tipo": data["tipo_servicio"],
                "Cuenta default": data["default"]["cuenta"],
                "Concepto": data["default"]["concepto"],
            }
            for nit, data in sp_data["servicios_publicos"].items()
        ])
        st.dataframe(df_sp, use_container_width=True, hide_index=True)

# ============================================================================
# TAB 3: EMPRESAS
# ============================================================================
with tab_empresas:
    st.subheader("🏢 Empresas configuradas")

    df_emp = pd.DataFrame([
        {
            "Empresa": e["razon_social"],
            "NIT": e["nit"],
            "ID interno": e["id"],
            "Carpeta": e["carpeta"],
            "Activa": "✅" if e.get("activa", True) else "❌",
        }
        for e in empresas
    ])
    st.dataframe(df_emp, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### ➕ Agregar empresa nueva")
    st.markdown(f"""
1. Copiar la carpeta `{EMPRESAS_DIR / '_template_empresa'}/` a `{EMPRESAS_DIR}/<NIT>_<id>/`
2. Editar `empresa.json` con los datos reales
3. Editar `mapeo_nits.json` con proveedores recurrentes (puedes empezar copiando del catálogo de servicios públicos en la pestaña 🗂️)
4. Editar `centros_costo.json` con los CCs propios
5. Agregar al archivo `{EMPRESAS_DIR / '_empresas_index.json'}`
6. Recargar la página
""")
