"""
UI Streamlit — Generación de XMLs Información Exógena DIAN
============================================================

Renderiza la pestaña "Generar XML" del módulo de exógena. Flujo:

  1. Configuración del envío (año gravable, tipo, fechas)
  2. Tabla editable de consecutivos por formato (sugeridos + sobreescribibles)
  3. Botón "Generar" → produce los XMLs + Excel maestro + ZIP descargable
  4. Resultado con métricas, descargas, validación XSD por archivo

Esta UI es agnóstica de cómo se obtienen los registros: recibe los datos
ya clasificados desde el motor (a través de los integradores PILA, motor v2,
etc.). Aquí solo se ocupa del flujo final de generación.
"""

from __future__ import annotations
import io
import zipfile
import traceback
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from core.exogena.gestor_consecutivos import (
    GestorConsecutivos,
    TIPO_ENVIO_INICIAL, TIPO_ENVIO_FRACCION, TIPO_ENVIO_REEMPLAZO, TIPO_ENVIO_CORRECCION,
    TIPOS_ENVIO_DESC,
)
from core.exogena.generar_xml_exogena import (
    sugerir_consecutivos_lote,
    generar_lote_xmls,
)
from core.exogena.generador_xml_v2 import FORMATOS_CONFIG, construir_nombre_archivo
from core.exogena.generador_excel_prevalidador import generar_excel_prevalidador


# ================================================================
# Configuración de los formatos disponibles
# ================================================================

FORMATOS_INFO = {
    '1001': ('📤', 'Pagos o abonos en cuenta y retenciones practicadas'),
    '1003': ('🧾', 'Retenciones en la fuente que le practicaron'),
    '1005': ('💸', 'IVA descontable'),
    '1006': ('💰', 'IVA generado'),
    '1007': ('📥', 'Ingresos recibidos'),
    '1008': ('🏦', 'Saldos de cuentas por cobrar'),
    '1009': ('🏦', 'Saldos de cuentas por pagar'),
    '1011': ('📑', 'Información de declaraciones tributarias'),
    '1012': ('💳', 'Saldos cuentas bancarias / inversiones'),
    '1647': ('🤝', 'Ingresos recibidos para terceros'),
    '2276': ('👥', 'Rentas de trabajo y pensiones'),
}


# ================================================================
# Helpers de UI
# ================================================================

def _formato_label(fmt: str) -> str:
    icono, nombre = FORMATOS_INFO.get(fmt, ('📄', f'Formato {fmt}'))
    return f"{icono} F{fmt} — {nombre}"


def _info_envio_inicial():
    """Mensaje cuando es primera generación para la empresa."""
    st.info(
        "🆕 **Primera generación** para esta empresa en el año gravable. "
        "Todos los consecutivos arrancan en 1. "
        "La plataforma recordará el último usado para sugerirte el siguiente la próxima vez."
    )


def _info_envio_continuacion(maximo_anterior: int):
    """Mensaje cuando ya hay envíos previos."""
    st.success(
        f"📊 Ya existen envíos previos para esta empresa "
        f"(último consecutivo usado: **{maximo_anterior}**). "
        f"Las sugerencias continúan desde el último usado."
    )


# ================================================================
# Pestaña principal
# ================================================================

def render_tab_generar_xml(
    empresa_id: str,
    ano_gravable: int,
    obtener_registros_por_formato: callable,
    info_empresa: dict,
):
    """
    Renderiza la pestaña completa de generación de XMLs.

    Args:
        empresa_id: UUID de la empresa activa.
        ano_gravable: año gravable seleccionado.
        obtener_registros_por_formato: callback que devuelve
            {formato_str: [Registros...]} listo para alimentar al generador.
            Se invoca solo cuando el usuario presiona "Generar".
        info_empresa: dict con datos de la empresa para la cabecera del Excel
            ({'nit_informante', 'razon_informante', ...}).
    """
    st.markdown("### 📤 Generar archivos XML para DIAN")
    st.caption(
        "Genera los XML oficiales conformes al prevalidador AG 2025 v3.3.0-26. "
        "Los consecutivos se controlan automáticamente, pero puedes sobreescribirlos."
    )

    # Necesitamos el cliente Supabase para el gestor
    from db.supabase_client import get_supabase
    sb = get_supabase()
    gestor = GestorConsecutivos(sb)

    # ============================================================
    # 1) Configuración del envío
    # ============================================================
    st.markdown("#### 1️⃣ Configuración del envío")

    col1, col2, col3 = st.columns([1.2, 1, 1])

    with col1:
        tipo_envio_opciones = {
            f"{cod} — {desc}": cod for cod, desc in TIPOS_ENVIO_DESC.items()
        }
        tipo_envio_label = st.selectbox(
            "Tipo de envío",
            options=list(tipo_envio_opciones.keys()),
            index=0,  # default Inicial (01)
            key="exo_tipo_envio",
            help=(
                "01 Inicial — primera vez que se reporta\n\n"
                "02 Fracción — envío parcial\n\n"
                "03 Reemplazo — sustituye un envío anterior completo\n\n"
                "04 Corrección — corrige registros específicos"
            ),
        )
        tipo_envio = tipo_envio_opciones[tipo_envio_label]

    with col2:
        ano_envio = st.number_input(
            "Año del envío",
            min_value=ano_gravable,
            max_value=ano_gravable + 5,
            value=ano_gravable + 1,
            key="exo_ano_envio",
            help="Año en que se hace la presentación (usualmente año_gravable + 1)",
        )

    with col3:
        st.write("")
        st.write("")
        recargar = st.button("🔄 Recargar consecutivos", help="Vuelve a consultar la BD")

    if recargar:
        # Limpiar caché de consecutivos
        if "exo_consecutivos_cache" in st.session_state:
            del st.session_state["exo_consecutivos_cache"]
        st.rerun()

    # ============================================================
    # 2) Tabla de consecutivos editables
    # ============================================================
    st.markdown("#### 2️⃣ Consecutivos por formato")

    formatos_disponibles = list(FORMATOS_INFO.keys())

    # Consultar sugerencias (cached en session_state)
    cache_key = f"exo_consecutivos_{empresa_id}_{ano_gravable}_{tipo_envio}"
    if cache_key not in st.session_state:
        with st.spinner("Consultando consecutivos anteriores..."):
            try:
                sugerencias = sugerir_consecutivos_lote(
                    gestor, empresa_id, ano_gravable,
                    formatos_disponibles, tipo_envio,
                )
                st.session_state[cache_key] = sugerencias
            except Exception as e:
                st.error(f"Error consultando consecutivos: {e}")
                return

    sugerencias = st.session_state[cache_key]

    # Mensaje contextual
    max_anterior = max((s.ultimo_usado for s in sugerencias.values()), default=0)
    if max_anterior == 0:
        _info_envio_inicial()
    else:
        _info_envio_continuacion(max_anterior)

    # Construir DataFrame para edición
    filas = []
    for fmt in formatos_disponibles:
        sug = sugerencias[fmt]
        cfg = FORMATOS_CONFIG[fmt]
        icono, nombre = FORMATOS_INFO[fmt]
        filas.append({
            'Formato': f"{icono} F{fmt}",
            'Descripción': nombre[:50],
            'Versión': f"v.{cfg['version']}",
            'Último usado': sug.ultimo_usado,
            'Consecutivo a usar': sug.siguiente,
            '_fmt': fmt,  # columna oculta para mapear
        })

    df = pd.DataFrame(filas)

    # data_editor: solo "Consecutivo a usar" es editable
    df_editado = st.data_editor(
        df,
        hide_index=True,
        column_config={
            'Formato': st.column_config.TextColumn('Formato', disabled=True, width='small'),
            'Descripción': st.column_config.TextColumn('Descripción', disabled=True, width='large'),
            'Versión': st.column_config.TextColumn('Versión', disabled=True, width='small'),
            'Último usado': st.column_config.NumberColumn(
                'Último usado', disabled=True, width='small',
                help='Mayor consecutivo encontrado en la base de datos',
            ),
            'Consecutivo a usar': st.column_config.NumberColumn(
                'Consecutivo a usar', min_value=1, max_value=99_999_999, step=1,
                width='medium',
                help='Editable. El sistema valida que no esté usado antes.',
            ),
            '_fmt': None,  # ocultar columna técnica
        },
        use_container_width=True,
        key=f"editor_consec_{cache_key}",
    )

    # Mapeo formato → consecutivo elegido
    consecutivos_elegidos: dict[str, int] = {}
    for _, row in df_editado.iterrows():
        fmt = row['_fmt']
        consecutivos_elegidos[fmt] = int(row['Consecutivo a usar'])

    # Detectar cambios respecto a sugerencias
    cambios = []
    for fmt, consec in consecutivos_elegidos.items():
        sugerido = sugerencias[fmt].siguiente
        if consec != sugerido:
            cambios.append((fmt, sugerido, consec))

    if cambios:
        with st.expander(f"ℹ️ {len(cambios)} consecutivo(s) editados manualmente"):
            for fmt, sug_val, elegido in cambios:
                st.markdown(f"- **F{fmt}**: sugerido {sug_val} → elegido **{elegido}**")

    # ============================================================
    # 3) Filtro de qué formatos generar
    # ============================================================
    st.markdown("#### 3️⃣ ¿Qué formatos generar?")
    formatos_a_generar = st.multiselect(
        "Selecciona los formatos a generar (por defecto todos los que tienen datos)",
        options=formatos_disponibles,
        default=formatos_disponibles,
        format_func=lambda f: _formato_label(f),
        key="exo_formatos_seleccionados",
    )

    # ============================================================
    # 4) Botón de generación
    # ============================================================
    st.markdown("#### 4️⃣ Generación")

    col_btn, col_info = st.columns([1, 2])
    with col_btn:
        boton_generar = st.button(
            "🚀 Generar XMLs y Excel",
            type="primary",
            use_container_width=True,
            disabled=len(formatos_a_generar) == 0,
        )
    with col_info:
        st.caption(
            f"Se generarán **{len(formatos_a_generar)}** archivos XML "
            f"y **1 Excel maestro** con todas las hojas para el prevalidador. "
            f"El sistema validará cada XML contra el XSD oficial y rechazará "
            f"consecutivos duplicados antes de guardar."
        )

    if not boton_generar:
        return

    # ============================================================
    # 5) EJECUCIÓN
    # ============================================================
    _ejecutar_generacion(
        empresa_id=empresa_id,
        ano_gravable=ano_gravable,
        ano_envio=int(ano_envio),
        tipo_envio=tipo_envio,
        consecutivos_elegidos=consecutivos_elegidos,
        formatos_a_generar=formatos_a_generar,
        obtener_registros_por_formato=obtener_registros_por_formato,
        info_empresa=info_empresa,
        gestor=gestor,
        cache_key=cache_key,
    )


# ================================================================
# Ejecutor de generación (separado para legibilidad)
# ================================================================

def _ejecutar_generacion(
    empresa_id: str,
    ano_gravable: int,
    ano_envio: int,
    tipo_envio: str,
    consecutivos_elegidos: dict[str, int],
    formatos_a_generar: list[str],
    obtener_registros_por_formato: callable,
    info_empresa: dict,
    gestor: GestorConsecutivos,
    cache_key: str,
):
    """
    Hace el trabajo real: obtiene registros, genera XMLs + Excel, valida XSD,
    arma ZIP descargable, muestra resultados.
    """
    progreso = st.progress(0, text="Preparando datos...")

    # --- 1. Obtener registros del motor (callback)
    try:
        registros_por_formato_completo = obtener_registros_por_formato(empresa_id, ano_gravable)
    except Exception as e:
        st.error(f"❌ Error obteniendo registros del motor:\n```\n{e}\n```")
        st.code(traceback.format_exc())
        return

    # Filtrar solo los formatos seleccionados que tengan datos
    registros_filtrados = {
        fmt: registros_por_formato_completo[fmt]
        for fmt in formatos_a_generar
        if fmt in registros_por_formato_completo and registros_por_formato_completo[fmt]
    }

    formatos_vacios = [
        fmt for fmt in formatos_a_generar
        if not registros_por_formato_completo.get(fmt)
    ]
    if formatos_vacios:
        st.warning(
            f"⚠️ Sin datos para: {', '.join(f'F{f}' for f in formatos_vacios)}. "
            "Se omiten."
        )

    if not registros_filtrados:
        st.error("❌ Ninguno de los formatos seleccionados tiene datos para reportar.")
        return

    progreso.progress(20, text="Generando XMLs...")

    # --- 2. Generar XMLs
    try:
        usuario_actual_id = st.session_state.get('user', {}).get('id') if isinstance(
            st.session_state.get('user'), dict) else None

        # Generar a tempdir
        import tempfile
        tmpdir = Path(tempfile.mkdtemp(prefix='exogena_'))
        xml_dir = tmpdir / 'xml'
        xml_dir.mkdir()

        resultados = generar_lote_xmls(
            gestor=gestor,
            empresa_id=empresa_id,
            ano_gravable=ano_gravable,
            registros_por_formato=registros_filtrados,
            consecutivos_elegidos=consecutivos_elegidos,
            tipo_envio=tipo_envio,
            ano_envio=ano_envio,
            fecha_envio=datetime.now(),
            ruta_salida=xml_dir,
            registrar_en_bd=True,
            generado_por=usuario_actual_id,
        )
    except ValueError as e:
        # Consecutivo duplicado u otro error de validación
        st.error(f"❌ {e}")
        # Sugerir acción
        st.info(
            "💡 Si el consecutivo ya fue usado, recarga la página o cambia "
            "el tipo de envío. Tus datos NO se perdieron."
        )
        return
    except Exception as e:
        st.error(f"❌ Error generando XMLs:\n```\n{e}\n```")
        st.code(traceback.format_exc())
        return

    progreso.progress(70, text="Generando Excel maestro...")

    # --- 3. Generar Excel maestro
    try:
        info_global = {
            'ano': ano_gravable,
            'nit_informante': info_empresa.get('nit', ''),
            'razon_informante': info_empresa.get('razon_social', info_empresa.get('nombre', '')),
            'fecha_generacion': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }

        ruta_xlsx = tmpdir / f"Exogena_{info_empresa.get('nit','EMPRESA')}_AG{ano_gravable}.xlsx"
        generar_excel_prevalidador(
            ruta_xlsx, info_global, {
                fmt: {'registros': regs}
                for fmt, regs in registros_filtrados.items()
            }
        )
    except Exception as e:
        st.warning(f"⚠️ XMLs generados, pero falló el Excel: {e}")
        ruta_xlsx = None

    progreso.progress(90, text="Empaquetando ZIP...")

    # --- 4. Armar ZIP descargable en memoria
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fmt, res in resultados.items():
            zf.writestr(res.nombre_archivo, res.xml.encode('ISO-8859-1'))
        if ruta_xlsx and ruta_xlsx.exists():
            zf.write(ruta_xlsx, ruta_xlsx.name)
    zip_bytes.seek(0)

    progreso.progress(100, text="¡Listo!")
    progreso.empty()

    # Invalidar caché de consecutivos para que la próxima vez sugiera los nuevos
    if cache_key in st.session_state:
        del st.session_state[cache_key]

    # --- 5. Mostrar resultados
    st.success(f"✅ {len(resultados)} archivos XML generados correctamente")

    # Métricas resumen
    total_registros = sum(r.cantidad_registros for r in resultados.values())
    total_valor = sum(r.valor_total for r in resultados.values())

    col1, col2, col3 = st.columns(3)
    col1.metric("Archivos generados", f"{len(resultados)}")
    col2.metric("Registros totales", f"{total_registros:,}")
    col3.metric("Valor total", f"${total_valor:,.0f}")

    # Botón descarga ZIP
    nombre_zip = f"Exogena_{info_empresa.get('nit','EMPRESA')}_AG{ano_gravable}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    st.download_button(
        "📦 Descargar ZIP completo (XMLs + Excel)",
        data=zip_bytes,
        file_name=nombre_zip,
        mime='application/zip',
        use_container_width=True,
        type='primary',
    )

    # Tabla detalle por formato
    st.markdown("#### Detalle de archivos generados")
    detalle = pd.DataFrame([
        {
            'Formato': _formato_label(fmt),
            'Versión': f"v.{res.version}",
            'Consecutivo': res.consecutivo_usado,
            'Archivo': res.nombre_archivo,
            'Registros': res.cantidad_registros,
            'Valor total': res.valor_total,
            'ID envío BD': res.envio_id if res.envio_id and res.envio_id > 0 else '—',
        }
        for fmt, res in resultados.items()
    ])
    st.dataframe(
        detalle,
        hide_index=True,
        use_container_width=True,
        column_config={
            'Valor total': st.column_config.NumberColumn(
                'Valor total', format='$%d',
            ),
        },
    )

    # Descargas individuales (expander)
    with st.expander("📥 Descargas individuales por archivo"):
        for fmt, res in resultados.items():
            cols = st.columns([3, 1])
            with cols[0]:
                st.markdown(f"**{_formato_label(fmt)}** — `{res.nombre_archivo}`")
            with cols[1]:
                st.download_button(
                    "⬇️ XML",
                    data=res.xml.encode('ISO-8859-1'),
                    file_name=res.nombre_archivo,
                    mime='application/xml',
                    key=f"dl_{fmt}_{res.consecutivo_usado}",
                )

        if ruta_xlsx and ruta_xlsx.exists():
            st.markdown(f"**📊 Excel maestro** — `{ruta_xlsx.name}`")
            with open(ruta_xlsx, 'rb') as f:
                st.download_button(
                    "⬇️ Excel maestro",
                    data=f.read(),
                    file_name=ruta_xlsx.name,
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    key='dl_excel_maestro',
                )

    # Histórico de envíos
    _render_historico(gestor, empresa_id, ano_gravable)


def _render_historico(gestor: GestorConsecutivos, empresa_id: str, ano_gravable: int):
    """Tabla con los últimos envíos registrados de la empresa."""
    st.markdown("---")
    st.markdown("#### 📜 Histórico de envíos")

    try:
        envios = gestor.listar_envios(empresa_id, ano_gravable=ano_gravable, limite=50)
    except Exception as e:
        st.caption(f"⚠️ No se pudo cargar el histórico: {e}")
        return

    if not envios:
        st.caption("No hay envíos previos registrados.")
        return

    df = pd.DataFrame(envios)
    columnas_mostrar = [
        'formato', 'version', 'tipo_envio', 'consecutivo',
        'nombre_archivo', 'cantidad_registros', 'valor_total',
        'fecha_generacion', 'estado',
    ]
    columnas_existentes = [c for c in columnas_mostrar if c in df.columns]
    df_view = df[columnas_existentes].copy()

    # Mejorar nombres
    df_view = df_view.rename(columns={
        'formato': 'Formato',
        'version': 'Versión',
        'tipo_envio': 'Tipo',
        'consecutivo': 'Consec.',
        'nombre_archivo': 'Archivo',
        'cantidad_registros': 'Registros',
        'valor_total': 'Valor',
        'fecha_generacion': 'Fecha',
        'estado': 'Estado',
    })

    st.dataframe(df_view, hide_index=True, use_container_width=True)
