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
                        empresa_forzada, modo_plano):
    """Orquesta el procesamiento de RECIBIDOS y muestra resultados."""
    with st.spinner("Procesando documentos recibidos..."):
        zip_inputs = [
            ZipInput(
                nombre=z.name,
                contenido=z.getbuffer().tobytes(),
                tipo_declarado=None  # ya no se usa: el detector identifica solo
            )
            for z in zips_recibidos
        ]
        try:
            resultado = procesar_multiples_zips(
                zip_inputs,
                registry,
                anio_contable=anio,
                mes_contable=mes,
                modo_filtro_fecha=modo_filtro,
                empresa_forzada=(
                    empresa_forzada.split(" — ")[0]
                    if empresa_forzada != "(detector por receptor NIT)"
                    else None
                ),
            )
        except Exception as e:
            st.error(f"⚠️ Error al procesar recibidos: {e}")
            st.exception(e)
            return

    st.success(f"✅ {len(resultado.documentos)} documentos recibidos procesados")
    mostrar_resultados_recibidos(resultado, modo_plano)


def mostrar_resultados_recibidos(resultado, modo_plano):
    """Muestra los resultados del procesamiento de recibidos (plano + KPIs)."""
    st.subheader("📋 Plano contable")
    st.info(
        "✏️ La integración del motor v0.3 (mapeo aprendido del BP, retenciones "
        "por concepto, CC por palabra clave) se completa cuando integremos "
        "`motor_mapeo_v03.py` dentro de `procesador_dian_xml.py`. "
        "Esto se hará en la próxima sesión."
    )
    # Por ahora reuso la lógica v0.2:
    if modo_plano == "Plano único consolidado":
        df_plano = pd.DataFrame([
            l.__dict__ for l in resultado.lineas_plano
        ])
    else:
        planos_separados = separar_lineas_por_comprobante(resultado.lineas_plano)
        df_plano = pd.concat([
            pd.DataFrame([l.__dict__ for l in lineas]).assign(comprobante=c)
            for c, lineas in planos_separados.items()
        ], ignore_index=True) if planos_separados else pd.DataFrame()

    if not df_plano.empty:
        st.dataframe(df_plano, use_container_width=True)


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
                                empresa_forzada, modo_plano)


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
