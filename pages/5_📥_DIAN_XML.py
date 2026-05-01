"""
📥 DIAN XML — Procesamiento masivo multi-empresa
Página Streamlit v0.3.5 (30-04-2026)

Cambios vs v0.2:
- UN SOLO uploader para "Recibidos" (el ZIP unificado del bookmarklet v0.3)
  reemplaza las 4 cajas anteriores (FE/NC/ND/SP).
- Caja "Emitidos" deshabilitada con mensaje "Próximamente" (FE de venta a comprob 4).
- El procesador detecta automáticamente el tipo de cada documento desde
  el prefijo del nombre (FE_, NC_, ND_, DS_, ??_) o desde el contenido del XML.
- Mapeo automático a comprobantes contables (3, 7, 12) según tipo.
- 🔒 Protegida con auth Supabase (require_auth + sidebar_user_info).
"""
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

# 🔒 Auth — debe ir ANTES de cualquier otra cosa de Streamlit visible
from auth.login import require_auth, sidebar_user_info

st.set_page_config(page_title="DIAN XML", page_icon="📥", layout="wide")

require_auth()        # corta la página si no hay sesión válida
sidebar_user_info()   # muestra usuario + botón de logout en el sidebar

# Imports nuevos del motor v0.3 (se conectarán al procesador en próxima sesión)
from core.procesadores.motor_mapeo_v03 import CatalogoEmpresa
from core.procesadores.exportador_silla_tres import (
    construir_dataframe_silla_tres,
    exportar_txt_silla_tres,
    exportar_csv_silla_tres,
    exportar_xlsx_silla_tres,
)

# Imports legacy del v0.2 (parser UBL, generador de plano)
from core.procesadores.procesador_dian_xml import (
    RegistryEmpresas,
    procesar_multiples_zips,
    separar_lineas_por_comprobante,
    generar_reporte_ejecutivo,
    exportar_plano_txt,
    ZipInput,
)

EMPRESAS_DIR = Path("core/data/empresas")

st.title("📥 DIAN XML — Procesamiento masivo multi-empresa")
st.caption(
    "Sube el ZIP descargado del bookmarklet (contiene FE + NC + ND + DS unificados). "
    "El sistema detecta el tipo de cada documento, aplica mapeo NIT, "
    "asigna CC desde dirección/notas y genera el plano contable."
)

# ----------------------------------------------------------- Registry
@st.cache_resource
def cargar_registry():
    return RegistryEmpresas(EMPRESAS_DIR)


def _cargar_catalogo_para(empresa_id: str) -> CatalogoEmpresa:
    """Carga el CatalogoEmpresa para un empresa_id dado, buscando la carpeta correcta."""
    for p in EMPRESAS_DIR.iterdir():
        if not p.is_dir() or p.name.startswith("_"):
            continue
        # Las carpetas siguen el patrón "<NIT>_<slug>"
        if p.name.startswith(f"{empresa_id}_") or p.name == empresa_id:
            return CatalogoEmpresa.cargar(p)
    raise FileNotFoundError(f"No se encontró carpeta para empresa_id={empresa_id}")


try:
    registry = cargar_registry()
    empresas = registry.listar()
except Exception as e:
    st.error(f"⚠️ No se pudo cargar el índice de empresas: {e}")
    st.stop()

# ----------------------------------------------------------- Funciones helper
# IMPORTANTE: deben declararse ANTES del bloque `with tab_proc:` porque
# Streamlit ejecuta el archivo de arriba abajo como un script normal.

def procesar_y_mostrar(zips_recibidos, anio, mes, modo_filtro,
                        empresa_forzada, modo_plano, consecutivo_inicial=1):
    """Orquesta el procesamiento de RECIBIDOS y muestra resultados."""
    # ── Convertir parámetros UI a los esperados por procesar_multiples_zips ──
    anio_mes = f"{anio}{int(mes):02d}"

    # modo_filtro UI → modo_filtro_codigo del procesador
    modo_filtro_codigo = {
        "No filtrar (procesar todo)": "ninguno",
        "Por fecha de emisión": "emision",
        "Por fecha de recepción DIAN": "recepcion",
    }.get(modo_filtro, "ninguno")

    # Si se filtra por fecha, fijar rango = mes contable completo
    fecha_desde = ""
    fecha_hasta = ""
    if modo_filtro_codigo != "ninguno":
        from datetime import date as _date
        primer_dia = _date(int(anio), int(mes), 1)
        # último día del mes
        if int(mes) == 12:
            ultimo_dia = _date(int(anio), 12, 31)
        else:
            ultimo_dia = _date(int(anio), int(mes) + 1, 1) - pd.Timedelta(days=1)
        fecha_desde = primer_dia.strftime("%Y-%m-%d")
        fecha_hasta = ultimo_dia.strftime("%Y-%m-%d")

    # empresa_forzada: viene como "900451388 — Silla Tres SAS" o "(detector por receptor NIT)"
    emp_forzada = None
    if empresa_forzada and not empresa_forzada.startswith("("):
        nit_sel = empresa_forzada.split(" — ")[0].strip()
        for e in empresas:
            if str(e.get("nit", "")) == nit_sel:
                emp_forzada = e.get("id") or nit_sel
                break

    with st.spinner(f"Procesando {len(zips_recibidos)} ZIP(s)..."):
        zips_input = [
            ZipInput(
                nombre=z.name,
                contenido=z.getbuffer().tobytes(),
                tipo_declarado=None  # detector identifica el tipo automáticamente
            )
            for z in zips_recibidos
        ]
        try:
            resultados, resumen = procesar_multiples_zips(
                zips_input, registry, anio_mes,
                fecha_desde=fecha_desde,
                fecha_hasta=fecha_hasta,
                empresa_id_forzada=emp_forzada,
                modo_filtro_fecha=modo_filtro_codigo,
            )
        except Exception as e:
            st.error(f"⚠️ Error al procesar recibidos: {e}")
            st.exception(e)
            return

    # Guardar en session_state para persistir entre re-renders
    # NOTA: NO guardamos modo_plano ni consecutivo_inicial porque sus widgets
    # (st.radio y st.number_input) ya manejan esa key automáticamente.
    # Asignar manualmente a una key reservada por un widget genera StreamlitAPIException.
    st.session_state["resultados"] = resultados
    st.session_state["resumen"] = resumen
    st.session_state["anio_mes"] = anio_mes

    mostrar_resultados_recibidos(resultados, resumen, modo_plano,
                                   int(consecutivo_inicial))


def mostrar_resultados_recibidos(resultados, resumen, modo_plano,
                                   consecutivo_inicial=1):
    """Muestra los resultados del procesamiento (resumen + plano por empresa)."""
    # ── Resumen de ingesta ─────────────────────────────────
    st.markdown("---")
    st.subheader("3️⃣ Resumen de ingesta")

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("XMLs extraídos", resumen.total_xmls_extraidos)
    col2.metric("Duplicados", resumen.duplicados_descartados,
                 delta_color="off" if resumen.duplicados_descartados == 0 else "inverse")
    col3.metric("Fuera de rango", resumen.fuera_de_rango_fecha,
                 delta_color="off" if resumen.fuera_de_rango_fecha == 0 else "inverse")
    col4.metric("Errores parseo", resumen.errores_parseo,
                 delta_color="off" if resumen.errores_parseo == 0 else "inverse")
    col5.metric("Empresas detectadas", len(resumen.por_empresa))

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

    # Detalle de descartados
    if resumen.descartados_detalle:
        with st.expander(
            f"🔍 Ver detalle de {len(resumen.descartados_detalle)} documento(s) descartado(s)"
        ):
            df_desc = pd.DataFrame(resumen.descartados_detalle)
            st.dataframe(df_desc, use_container_width=True, hide_index=True)

    # ── Resultados por empresa ─────────────────────────────
    st.markdown("---")
    st.subheader(f"4️⃣ Resultados por empresa ({len(resultados)})")

    st.info(
        "ℹ️ La integración del motor v0.3 (mapeo aprendido del BP, retenciones "
        "por concepto, CC por palabra clave) se hará en la próxima sesión. "
        "Por ahora el plano usa la lógica del procesador v0.2."
    )

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

            # ── Construir DataFrame en formato Silla Tres ─────
            # Determinar formato CC según empresa.json (sin_guion por defecto)
            try:
                cat = _cargar_catalogo_para(r.empresa_id)
                cc_formato = cat.empresa_json.get("formato_salida", {}).get(
                    "cc_formato", "sin_guion"
                )
            except Exception:
                cc_formato = "sin_guion"

            if modo_plano == "Plano único consolidado":
                df_plano = construir_dataframe_silla_tres(
                    r.lineas_plano,
                    cc_formato=cc_formato,
                    consecutivo_inicial=consecutivo_inicial,
                )
            else:
                planos_sep = separar_lineas_por_comprobante(r.lineas_plano)
                dfs = []
                for c, lineas in planos_sep.items():
                    df_c = construir_dataframe_silla_tres(
                        lineas,
                        cc_formato=cc_formato,
                        consecutivo_inicial=consecutivo_inicial,
                    )
                    df_c.insert(0, "_grupo_comprobante", c)
                    dfs.append(df_c)
                df_plano = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

            if df_plano.empty:
                st.info("No hay líneas en el plano para esta empresa.")
                continue

            st.dataframe(df_plano, use_container_width=True, height=350, hide_index=True)

            # ── 3 botones de descarga: TXT, CSV, XLSX ─────────
            anio_mes = st.session_state.get("anio_mes", "XXXXXX")
            base_nombre = f"plano_{r.empresa_id}_{anio_mes}"

            # Para los downloads usamos el df sin el grupo_comprobante (si lo agregamos)
            df_export = df_plano.drop(columns=["_grupo_comprobante"], errors="ignore")

            col_dl1, col_dl2, col_dl3 = st.columns(3)
            with col_dl1:
                st.download_button(
                    "⬇️ TXT (tab)",
                    data=exportar_txt_silla_tres(df_export),
                    file_name=f"{base_nombre}.txt",
                    mime="text/plain",
                    key=f"dl_txt_{r.empresa_id}",
                    use_container_width=True,
                )
            with col_dl2:
                st.download_button(
                    "⬇️ CSV",
                    data=exportar_csv_silla_tres(df_export),
                    file_name=f"{base_nombre}.csv",
                    mime="text/csv",
                    key=f"dl_csv_{r.empresa_id}",
                    use_container_width=True,
                )
            with col_dl3:
                st.download_button(
                    "⬇️ Excel",
                    data=exportar_xlsx_silla_tres(df_export),
                    file_name=f"{base_nombre}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_xlsx_{r.empresa_id}",
                    use_container_width=True,
                )


# ----------------------------------------------------------- Tabs
tab_proc, tab_mapeo, tab_empresas = st.tabs(
    ["📥 Procesar XML", "🗂️ Editor de mapeo", "🏢 Empresas configuradas"]
)

# ============================================================================
# TAB 1: PROCESAR — DOS UPLOADERS (RECIBIDOS + EMITIDOS)
# ============================================================================
with tab_proc:
    st.subheader("1️⃣ Sube los ZIPs descargados")

    col_recibidos, col_emitidos = st.columns(2)

    # ── RECIBIDOS ──────────────────────────────────────────
    with col_recibidos:
        st.markdown("### 📥 Documentos recibidos")
        st.caption(
            "ZIP único del bookmarklet con TODO: facturas, notas crédito, "
            "notas débito y documentos soporte recibidos. El sistema detecta "
            "automáticamente el tipo de cada uno."
        )
        zips_recibidos = st.file_uploader(
            "Subir ZIP de recibidos",
            type=["zip"],
            accept_multiple_files=True,
            key="zips_recibidos",
            help="Generado con el bookmarklet DIAN v0.3 (un solo ZIP con todo)"
        )
        if zips_recibidos:
            st.success(f"✅ {len(zips_recibidos)} archivo(s) cargado(s)")
            for z in zips_recibidos:
                size_mb = z.size / (1024 * 1024)
                st.caption(f"  • {z.name} ({size_mb:.1f} MB)")

    # ── EMITIDOS (placeholder por ahora) ──────────────────
    with col_emitidos:
        st.markdown("### 📤 Documentos emitidos")
        st.caption(
            "ZIP con los XMLs emitidos por la empresa a sus clientes "
            "(facturas de venta)."
        )
        st.info(
            "🚧 **Próximamente** — el procesamiento contable de las facturas "
            "de venta emitidas (comprobante 4 - Ingresos) se habilitará en la "
            "próxima versión. Por ahora esta caja está deshabilitada."
        )
        # Caja deshabilitada para indicar visualmente que viene después
        st.file_uploader(
            "Subir ZIP de emitidos (próximamente)",
            type=["zip"],
            accept_multiple_files=True,
            key="zips_emitidos_placeholder",
            disabled=True,
            help="Función en construcción"
        )
        zips_emitidos = []  # siempre vacío en esta versión

    st.divider()

    # ── CONFIGURACIÓN ─────────────────────────────────────
    st.subheader("2️⃣ Configuración del procesamiento")

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        anio = st.number_input("Año contable", min_value=2020, max_value=2030,
                                value=date.today().year, step=1, key="anio_proc")
        mes = st.number_input("Mes contable", min_value=1, max_value=12,
                               value=max(date.today().month - 1, 1), step=1, key="mes_proc")
        consecutivo_inicial = st.number_input(
            "Consecutivo inicial DOCUMENTO",
            min_value=1, max_value=999999999, value=1, step=1,
            key="consecutivo_inicial",
            help=(
                "Número desde el cual empieza el consecutivo de la columna "
                "DOCUMENTO. Cada factura/asiento contable lleva un número "
                "y se incrementa para el siguiente."
            )
        )
    with col_b:
        st.markdown("**Filtrar por fecha**")
        modo_filtro = st.radio(
            "Filtro de fechas",
            options=["No filtrar (procesar todo)", "Por fecha de emisión", "Por fecha de recepción DIAN"],
            index=0,
            label_visibility="collapsed",
            key="modo_filtro_fecha"
        )
    with col_c:
        empresa_forzada = st.selectbox(
            "Empresa",
            options=["(detector por receptor NIT)"] + [
                f"{e['nit']} — {e['razon_social']}" for e in empresas
            ],
            index=0,
            key="empresa_forzada",
            help="Por defecto detecta la empresa según el NIT receptor de cada XML"
        )
        modo_plano = st.radio(
            "Plano resultante",
            options=["Plano único consolidado", "Separado por comprobante"],
            index=0,
            key="modo_plano"
        )

    st.divider()

    # ── BOTÓN PROCESAR ────────────────────────────────────
    if not zips_recibidos:
        st.info("👆 Sube el ZIP de recibidos para continuar")
    else:
        if st.button("🚀 Procesar ZIPs", type="primary", use_container_width=True,
                     key="btn_procesar_zips"):
            procesar_y_mostrar(zips_recibidos, anio, mes, modo_filtro,
                                empresa_forzada, modo_plano, consecutivo_inicial)


# ============================================================================
# TAB 2: EDITOR DE MAPEO
# ============================================================================
with tab_mapeo:
    st.subheader("🗂️ Editor de mapeo NIT ↔ cuenta + CC")
    st.info(
        "Próximamente: editor visual del `mapeo_nits.json`. "
        "Por ahora editar el archivo directamente en GitHub."
    )

    if empresas:
        empresa_sel = st.selectbox(
            "Empresa",
            options=[f"{e['nit']} — {e['razon_social']}" for e in empresas],
            key="emp_mapeo"
        )
        nit_sel = empresa_sel.split(" — ")[0]
        try:
            cat = CatalogoEmpresa.cargar(EMPRESAS_DIR / f"{nit_sel}_*")
        except Exception:
            # Buscar la carpeta real
            for p in EMPRESAS_DIR.iterdir():
                if p.is_dir() and p.name.startswith(nit_sel):
                    cat = CatalogoEmpresa.cargar(p)
                    break

        st.metric("NITs catalogados", len(cat.mapeo_nits))
        st.metric("Centros de costo", len(cat.centros_costo))
        st.metric("Direcciones mapeadas",
                   len(cat.direcciones_locales.get('direcciones', {})))


# ============================================================================
# TAB 3: EMPRESAS CONFIGURADAS
# ============================================================================
with tab_empresas:
    st.subheader("🏢 Empresas configuradas")
    st.dataframe(pd.DataFrame(empresas), use_container_width=True, hide_index=True)

    st.markdown("**Para agregar una nueva empresa:**")
    st.markdown(
        "1. Copiar la carpeta `core/data/empresas/_template_empresa/` "
        "renombrándola a `<NIT>_<slug>/`\n"
        "2. Editar `empresa.json`, `mapeo_nits.json`, `centros_costo.json` "
        "según los datos de la nueva empresa\n"
        "3. Agregar la entrada en `_empresas_index.json`\n"
        "4. Reiniciar Railway"
    )
