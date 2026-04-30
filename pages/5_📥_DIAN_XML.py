"""
📥 DIAN XML — Procesamiento masivo multi-empresa
Página Streamlit v0.3 (30-04-2026)

Cambios vs v0.2:
- UN SOLO uploader para "Recibidos" (el ZIP unificado del bookmarklet v0.3)
  reemplaza las 4 cajas anteriores (FE/NC/ND/SP).
- NUEVO uploader para "Emitidos" (XMLs emitidos por la empresa, opcional).
- El procesador detecta automáticamente el tipo de cada documento desde
  el prefijo del nombre (FE_, NC_, ND_, DS_, ??_) o desde el contenido del XML.
- Mapeo automático a comprobantes contables (3, 7, 12) según tipo.
"""
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

# Imports nuevos del motor v0.3
from core.procesadores.motor_mapeo_v03 import (
    CatalogoEmpresa,
    resolver_mapeo,
    calcular_retencion_renta,
    calcular_reteiva,
    calcular_reteica,
    formato_cc_salida,
)
from core.procesadores.detector_tipo_doc import (
    detectar_tipo_documento,
    mapear_a_comprobante,
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

st.set_page_config(page_title="DIAN XML", page_icon="📥", layout="wide")

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

    # ── EMITIDOS ───────────────────────────────────────────
    with col_emitidos:
        st.markdown("### 📤 Documentos emitidos")
        st.caption(
            "ZIP con los XMLs emitidos por la empresa a sus clientes "
            "(facturas de venta, NC, ND emitidas). **Opcional.**"
        )
        zips_emitidos = st.file_uploader(
            "Subir ZIP de emitidos",
            type=["zip"],
            accept_multiple_files=True,
            key="zips_emitidos",
            help="Por ahora solo se muestra resumen; el procesamiento contable de ventas viene en próxima versión"
        )
        if zips_emitidos:
            st.info(
                f"📊 {len(zips_emitidos)} archivo(s) cargado(s). "
                "**Función de ventas en construcción** — se mostrará un resumen por ahora."
            )
            for z in zips_emitidos:
                size_mb = z.size / (1024 * 1024)
                st.caption(f"  • {z.name} ({size_mb:.1f} MB)")

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
    if not zips_recibidos and not zips_emitidos:
        st.info("👆 Sube al menos un ZIP para continuar")
    else:
        if st.button("🚀 Procesar todos los ZIPs", type="primary", use_container_width=True,
                     key="btn_procesar_zips"):
            procesar_y_mostrar(zips_recibidos or [], zips_emitidos or [],
                                anio, mes, modo_filtro, empresa_forzada, modo_plano)


def procesar_y_mostrar(zips_recibidos, zips_emitidos, anio, mes, modo_filtro,
                        empresa_forzada, modo_plano):
    """Orquesta el procesamiento completo y muestra resultados."""

    # ── Procesar RECIBIDOS ────────────────────────────────
    if zips_recibidos:
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

    # ── Procesar EMITIDOS (placeholder) ───────────────────
    if zips_emitidos:
        st.divider()
        st.subheader("📤 Documentos emitidos (resumen)")
        with st.spinner("Inspeccionando emitidos..."):
            resumen = inspeccionar_emitidos(zips_emitidos)
        mostrar_resumen_emitidos(resumen)


def inspeccionar_emitidos(zips_emitidos):
    """
    Lee los ZIPs de emitidos y devuelve un resumen sin generar plano contable.
    Por ahora solo cuenta documentos por tipo y total facturado.
    """
    import xml.etree.ElementTree as ET
    NS = {
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    }

    docs = []
    for z_obj in zips_emitidos:
        zf = zipfile.ZipFile(io.BytesIO(z_obj.getbuffer().tobytes()))
        for name in zf.namelist():
            if name.endswith('.zip'):
                # ZIP anidado
                with zf.open(name) as f:
                    inner_zf = zipfile.ZipFile(io.BytesIO(f.read()))
                    for inner_name in inner_zf.namelist():
                        if inner_name.endswith('.xml'):
                            with inner_zf.open(inner_name) as fx:
                                try:
                                    xml_content = fx.read().decode('utf-8', errors='replace')
                                    info = _extraer_info_basica_emitido(
                                        xml_content, name, NS
                                    )
                                    if info:
                                        docs.append(info)
                                except Exception:
                                    pass
            elif name.endswith('.xml'):
                with zf.open(name) as f:
                    try:
                        xml_content = f.read().decode('utf-8', errors='replace')
                        info = _extraer_info_basica_emitido(xml_content, name, NS)
                        if info:
                            docs.append(info)
                    except Exception:
                        pass

    # Resumen agregado
    df = pd.DataFrame(docs) if docs else pd.DataFrame()
    return {
        'docs': docs,
        'df': df,
        'total_docs': len(docs),
        'total_facturado': df['total'].sum() if not df.empty and 'total' in df.columns else 0,
        'total_iva': df['iva'].sum() if not df.empty and 'iva' in df.columns else 0,
        'por_tipo': df['tipo'].value_counts().to_dict() if not df.empty and 'tipo' in df.columns else {},
        'top_clientes': (
            df.groupby(['nit_receptor', 'nombre_receptor'])['total']
            .sum().sort_values(ascending=False).head(10).reset_index()
            .to_dict('records')
            if not df.empty else []
        ),
    }


def _extraer_info_basica_emitido(xml_content, archivo_nombre, NS):
    """Extrae info mínima de un XML emitido (factura/NC/ND de venta)."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return None

    # Detectar tipo
    tipo, _ = detectar_tipo_documento(xml_root=root, nombre_archivo=archivo_nombre)
    if tipo == 'ACUSE':
        return None

    # Lo que en RECIBIDOS es "AccountingSupplierParty" (proveedor),
    # en EMITIDOS también lo es… pero ahora ESE proveedor SOMOS NOSOTROS.
    # El cliente está en "AccountingCustomerParty".
    inner = root
    # Si es AttachedDocument extraer el inner
    tag = root.tag.split('}')[-1]
    if tag == 'AttachedDocument':
        for desc in root.iter('{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}Description'):
            if desc.text and ('<Invoice' in desc.text or '<CreditNote' in desc.text or '<DebitNote' in desc.text):
                try:
                    inner = ET.fromstring(desc.text)
                    break
                except ET.ParseError:
                    pass

    cust = inner.find('.//cac:AccountingCustomerParty', NS)
    nit_receptor = ''
    nombre_receptor = ''
    if cust is not None:
        cid = cust.find('.//cbc:CompanyID', NS)
        if cid is not None and cid.text:
            nit_receptor = cid.text.strip()
        rn = cust.find('.//cbc:RegistrationName', NS)
        if rn is not None and rn.text:
            nombre_receptor = rn.text.strip()

    # Total
    total_node = inner.find('.//cac:LegalMonetaryTotal/cbc:PayableAmount', NS)
    total = float(total_node.text) if total_node is not None and total_node.text else 0.0

    # IVA
    iva_total = 0.0
    for ts in inner.findall('.//cac:TaxTotal//cac:TaxSubtotal', NS):
        cat = ts.find('.//cac:TaxCategory/cac:TaxScheme/cbc:ID', NS)
        amt = ts.find('.//cbc:TaxAmount', NS)
        if cat is not None and cat.text == '01' and amt is not None and amt.text:
            try:
                iva_total += float(amt.text)
            except ValueError:
                pass

    # Fecha
    fecha_node = inner.find('cbc:IssueDate', NS)
    fecha = fecha_node.text if fecha_node is not None else ''

    # Número
    numero_node = inner.find('cbc:ID', NS)
    numero = numero_node.text if numero_node is not None else ''

    return {
        'tipo': tipo,
        'archivo': archivo_nombre,
        'numero': numero,
        'fecha': fecha,
        'nit_receptor': nit_receptor,
        'nombre_receptor': nombre_receptor,
        'total': total,
        'iva': iva_total,
        'base': total - iva_total,
    }


def mostrar_resumen_emitidos(resumen):
    """Resumen ejecutivo de los emitidos (sin plano contable por ahora)."""
    if resumen['total_docs'] == 0:
        st.warning("⚠️ No se encontraron XMLs emitidos válidos en los ZIPs subidos.")
        return

    st.info(
        "ℹ️ Los documentos emitidos NO se incluyen en el plano contable "
        "todavía — esa función está en construcción. Por ahora se muestra un "
        "resumen ejecutivo y un Excel con el detalle."
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Documentos emitidos", resumen['total_docs'])
    col2.metric("Total facturado", f"${resumen['total_facturado']:,.0f}")
    col3.metric("IVA generado", f"${resumen['total_iva']:,.0f}")
    col4.metric("Tipos distintos", len(resumen['por_tipo']))

    # Por tipo
    if resumen['por_tipo']:
        st.markdown("**Distribución por tipo de documento:**")
        df_tipos = pd.DataFrame(
            list(resumen['por_tipo'].items()),
            columns=['Tipo', 'Cantidad']
        )
        df_tipos['Comprobante (sugerido)'] = df_tipos['Tipo'].map({
            'FE': '5 - Venta',
            'NC': '11 - NC venta',
            'ND': '8 - ND venta',
            'DS': 'N/A (no aplica para emisor)',
        }).fillna('—')
        st.dataframe(df_tipos, use_container_width=True, hide_index=True)

    # Top clientes
    if resumen['top_clientes']:
        st.markdown("**Top 10 clientes por facturación:**")
        df_top = pd.DataFrame(resumen['top_clientes'])
        st.dataframe(df_top, use_container_width=True, hide_index=True)

    # Excel descargable
    if not resumen['df'].empty:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            resumen['df'].to_excel(writer, sheet_name='Emitidos', index=False)
        st.download_button(
            "📥 Descargar Excel de emitidos",
            data=buffer.getvalue(),
            file_name=f"emitidos_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_emitidos_xlsx"
        )


def mostrar_resultados_recibidos(resultado, modo_plano):
    """Muestra los resultados del procesamiento de recibidos (plano + KPIs)."""
    # Aquí se mantiene la lógica de v0.2 — solo pasa el resultado adelante.
    # En la integración final se conectará al motor v0.3 para enriquecer con:
    #   - Comprobantes 3/7/12 según tipo detectado
    #   - CCs por palabra clave / dirección / NIT
    #   - Retenciones según concepto + régimen
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
