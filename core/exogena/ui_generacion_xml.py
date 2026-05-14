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
    # 2) Consecutivo inicial + asignación correlativa automática
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

    # Determinar el consecutivo de arranque sugerido
    # = (máximo último_usado entre todos los formatos) + 1
    # Esto garantiza que el correlativo no choque con nada previo.
    max_anterior = max((s.ultimo_usado for s in sugerencias.values()), default=0)
    consecutivo_inicial_sugerido = max_anterior + 1

    # Mensaje contextual
    if max_anterior == 0:
        _info_envio_inicial()
    else:
        _info_envio_continuacion(max_anterior)

    # Input único del consecutivo inicial
    col_inp, col_help = st.columns([1, 2])
    with col_inp:
        consecutivo_inicial = st.number_input(
            "Empezar desde consecutivo Nº",
            min_value=1,
            max_value=99_999_999,
            value=consecutivo_inicial_sugerido,
            step=1,
            key=f"consec_inicial_{cache_key}",
            help=(
                "Los formatos se numerarán correlativamente a partir de este número. "
                f"Sugerido: {consecutivo_inicial_sugerido} (mayor usado + 1)."
            ),
        )
    with col_help:
        st.write("")
        st.caption(
            "💡 Los 11 formatos se numerarán **consecutivamente** a partir del número que escribas. "
            "Ejemplo: si pones 5, F1001 será el 5, F1003 el 6, F1005 el 7, y así sucesivamente."
        )

    # Asignación correlativa automática
    consecutivos_elegidos: dict[str, int] = {
        fmt: int(consecutivo_inicial) + i
        for i, fmt in enumerate(formatos_disponibles)
    }

    # Vista previa de la asignación (tabla simple, NO editable, evita el bug de data_editor)
    with st.expander("👀 Ver vista previa de la asignación de consecutivos", expanded=False):
        filas_preview = []
        for fmt in formatos_disponibles:
            sug = sugerencias[fmt]
            cfg = FORMATOS_CONFIG[fmt]
            icono, nombre = FORMATOS_INFO[fmt]
            consec = consecutivos_elegidos[fmt]
            # Detectar si el consecutivo elegido CHOCA con uno ya usado
            choca = consec <= sug.ultimo_usado and sug.ultimo_usado > 0
            filas_preview.append({
                'Formato': f"{icono} F{fmt}",
                'Descripción': nombre[:50],
                'Versión': f"v.{cfg['version']}",
                'Último usado': sug.ultimo_usado if sug.ultimo_usado > 0 else '—',
                'Consecutivo a usar': consec,
                'Estado': '⚠️ Conflicto' if choca else '✅ OK',
            })

        df_preview = pd.DataFrame(filas_preview)
        st.dataframe(
            df_preview,
            hide_index=True,
            use_container_width=True,
            column_config={
                'Formato': st.column_config.TextColumn('Formato', width='small'),
                'Descripción': st.column_config.TextColumn('Descripción', width='medium'),
                'Versión': st.column_config.TextColumn('Versión', width='small'),
                'Último usado': st.column_config.TextColumn(
                    'Último usado', width='small',
                ),
                'Consecutivo a usar': st.column_config.NumberColumn(
                    'Consecutivo a usar', format='%d', width='small',
                ),
                'Estado': st.column_config.TextColumn('Estado', width='small'),
            },
        )

    # Detectar y avisar de conflictos antes de generar
    conflictos = []
    for fmt, consec in consecutivos_elegidos.items():
        sug = sugerencias[fmt]
        if sug.ultimo_usado > 0 and consec <= sug.ultimo_usado:
            conflictos.append((fmt, sug.ultimo_usado, consec))

    if conflictos:
        msg = "⚠️ **Conflictos detectados** — los siguientes formatos chocarían con consecutivos ya usados:\n\n"
        for fmt, ultimo, consec in conflictos:
            msg += f"- **F{fmt}**: último usado = {ultimo}, intentas usar = {consec}\n"
        msg += f"\n💡 Sube el consecutivo inicial hasta **{max_anterior + 1}** o más para evitar conflictos."
        st.error(msg)


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
        # Si hay resultados de una generación anterior, mostrarlos
        # para que el usuario pueda marcarlos como definitivos sin regenerar
        storage_key = f"exo_resultados_prueba_{empresa_id}_{ano_gravable}_{tipo_envio}"
        if storage_key in st.session_state:
            _render_resultados_previos(
                storage_key=storage_key,
                gestor=gestor,
                empresa_id=empresa_id,
                ano_gravable=ano_gravable,
                tipo_envio=tipo_envio,
                info_empresa=info_empresa,
            )
            _render_historico(gestor, empresa_id, ano_gravable)
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

    progreso.progress(15, text="Validando datos de terceros...")

    # --- 1b. VALIDACIÓN + AUTO-ENRIQUECIMIENTO de terceros
    try:
        from core.exogena.validador_pre_generacion import (
            validar_y_enriquecer, aplicar_terceros_a_registros,
        )
        from core.exogena.enriquecimiento import (
            CacheEnriquecedor, RUESEnriquecedor, DatosAbiertosEnriquecedor,
            EmpresiteEnriquecedor, EnriquecedorEnCascada,
        )

        # Cargar terceros actuales de la empresa (BD)
        from db.supabase_client import get_supabase
        sb_local = get_supabase()
        terceros_resp = sb_local.table("exogena_terceros").select(
            "nit, dv, tipo_documento, razon_social, "
            "primer_apellido, segundo_apellido, primer_nombre, otros_nombres, "
            "direccion, codigo_dpto, codigo_municipio, codigo_pais"
        ).eq("empresa_id", empresa_id).execute()
        terceros_dict_bd = {t['nit']: t for t in (terceros_resp.data or [])}

        # Construir cascada de enriquecedores
        cascada = EnriquecedorEnCascada([
            CacheEnriquecedor(sb_local),
            RUESEnriquecedor(),
            DatosAbiertosEnriquecedor(),
            EmpresiteEnriquecedor(),
            # GoogleEnriquecedor desactivado por defecto (riesgoso)
        ])

        resultado_validacion = validar_y_enriquecer(
            registros_por_formato=registros_filtrados,
            terceros_dict=terceros_dict_bd,
            info_empresa_informante={
                'direccion': info_empresa.get('direccion', ''),
                'codigo_dpto': info_empresa.get('codigo_dpto', ''),
                'codigo_municipio': info_empresa.get('codigo_municipio', ''),
                'codigo_pais': info_empresa.get('codigo_pais', '169'),
            },
            enriquecedor=cascada,
        )

        # Mensajes informativos del enriquecimiento
        if resultado_validacion.enriquecidos_auto > 0:
            st.info(
                f"🔎 {resultado_validacion.enriquecidos_auto} tercero(s) "
                f"enriquecido(s) automáticamente desde fuentes externas "
                f"({', '.join(f'{f}: {n}' for f, n in resultado_validacion.fuentes_usadas.items())})"
            )
        if resultado_validacion.enriquecidos_fallback > 0:
            st.info(
                f"🏢 {resultado_validacion.enriquecidos_fallback} persona(s) natural(es) "
                f"recibieron datos de ubicación de la empresa informante como fallback"
            )
        if resultado_validacion.bancos_inferidos > 0:
            st.info(
                f"🏦 {resultado_validacion.bancos_inferidos} cuenta(s) bancaria(s) "
                f"del F1012 con NIT del banco inferido automáticamente"
            )

        # Si hay pendientes, mostrar formulario y detener
        if resultado_validacion.tiene_pendientes:
            progreso.empty()
            _render_form_completar_terceros(
                resultado_validacion,
                empresa_id,
                sb=sb_local,
            )
            return

        # Si todo OK, aplicar terceros completos a los registros
        registros_filtrados = aplicar_terceros_a_registros(
            registros_filtrados, resultado_validacion.terceros_completos
        )

    except ImportError:
        # Si el módulo de validación no está disponible, continuar sin validar
        st.warning(
            "⚠️ Módulo de validación de terceros no disponible — "
            "generando sin verificar completitud de direcciones."
        )

    progreso.progress(30, text="Generando XMLs...")

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
            registrar_en_bd=False,   # ← MODO PRUEBA: no persistir en BD
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
        # IMPORTANTE: el generador de Excel espera claves con prefijo 'F'
        # ('F1001', 'F1003', ...). En el resto del pipeline se usan claves
        # sin prefijo ('1001', '1003', ...). Convertir aquí.
        generar_excel_prevalidador(
            ruta_xlsx, info_global, {
                (fmt if fmt.startswith('F') else f'F{fmt}'): {'registros': regs}
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

    # NO invalidamos el caché de consecutivos: como estamos en modo prueba,
    # la próxima generación debe sugerir EL MISMO consecutivo.
    # El caché solo se limpia cuando el usuario marca como DEFINITIVO.

    # --- 5. Guardar resultados en session_state para "Marcar definitivo"
    storage_key = f"exo_resultados_prueba_{empresa_id}_{ano_gravable}_{tipo_envio}"
    st.session_state[storage_key] = {
        'resultados': resultados,
        'consecutivos_elegidos': consecutivos_elegidos,
        'ano_envio': ano_envio,
        'tipo_envio': tipo_envio,
        'fecha_generacion': datetime.now(),
        'zip_bytes': zip_bytes.getvalue(),
        'nombre_zip': f"Exogena_{info_empresa.get('nit','EMPRESA')}_AG{ano_gravable}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
        'total_registros': sum(r.cantidad_registros for r in resultados.values()),
        'total_valor': sum(r.valor_total for r in resultados.values()),
        'cache_key': cache_key,
    }

    # --- 6. Banner MODO PRUEBA + mensaje claro
    st.success(f"✅ {len(resultados)} archivos XML generados (modo PRUEBA)")

    st.info(
        "🔍 **Modo PRUEBA activo** — Los consecutivos NO se han persistido. "
        "Puedes regenerar las veces que quieras y siempre arrancarán desde el mismo número. "
        "Cuando subas los archivos a DIAN y te los acepten, presiona "
        "**\"✅ Marcar como DEFINITIVO\"** abajo para que la plataforma "
        "registre el envío y avance los consecutivos."
    )

    # Métricas resumen
    total_registros = sum(r.cantidad_registros for r in resultados.values())
    total_valor = sum(r.valor_total for r in resultados.values())

    col1, col2, col3 = st.columns(3)
    col1.metric("Archivos generados", f"{len(resultados)}")
    col2.metric("Registros totales", f"{total_registros:,}")
    col3.metric("Valor total", f"${total_valor:,.0f}")

    # Botón descarga ZIP
    nombre_zip = st.session_state[storage_key]['nombre_zip']
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
            'Estado': '🔍 PRUEBA',
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

    # --- 7. Sección "Marcar como DEFINITIVO"
    _render_seccion_marcar_definitivo(
        storage_key=storage_key,
        gestor=gestor,
        empresa_id=empresa_id,
        ano_gravable=ano_gravable,
        info_empresa=info_empresa,
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


# ================================================================
# Formulario para completar terceros pendientes
# ================================================================

def _render_form_completar_terceros(resultado_validacion, empresa_id: str, sb=None):
    """
    Renderiza un formulario para que el contador complete los datos
    faltantes (dirección, dpto, mun) de los terceros que no se pudieron
    enriquecer automáticamente.

    Los cambios se guardan en exogena_terceros y luego el contador
    debe presionar "Generar" de nuevo para que se incluyan.
    """
    pendientes = resultado_validacion.terceros_pendientes
    total = len(pendientes)

    st.error(
        f"⚠️ **{total} tercero(s) tienen datos incompletos.** "
        f"Para evitar rechazos de DIAN, completa la información antes de generar."
    )

    st.markdown("#### 📝 Completar datos faltantes")
    st.caption(
        "Los siguientes terceros no pudieron enriquecerse desde RUES, "
        "Datos Abiertos, Empresite ni fallback de empresa. "
        "Por favor completa los campos faltantes y guarda los cambios."
    )

    # Cargar catálogo de departamentos y municipios para selectores
    try:
        dptos_resp = sb.table("exogena_cat_departamentos").select("*").execute()
        muns_resp = sb.table("exogena_cat_municipios").select("*").execute()
        dptos = {d['codigo']: d['nombre'] for d in (dptos_resp.data or [])}
        muns_por_dpto = {}
        for m in (muns_resp.data or []):
            muns_por_dpto.setdefault(m['codigo_dpto'], []).append(
                (m['codigo_mcp'], m['nombre'])
            )
    except Exception:
        dptos = {}
        muns_por_dpto = {}

    # Renderizar un formulario por tercero pendiente
    cambios = {}  # nit → dict de campos editados

    for nit, pend in pendientes.items():
        nombre = (pend.razon_social or
                  f"{pend.primer_nombre or ''} {pend.primer_apellido or ''}".strip() or
                  '(sin nombre)')
        with st.expander(
            f"🔧 {nit} — {nombre[:60]}  "
            f"({', '.join(f'F{f}' for f in pend.formatos_afectados)})",
            expanded=True,
        ):
            st.caption(f"Errores: {', '.join(pend.errores)}")

            col1, col2 = st.columns(2)
            with col1:
                new_dir = st.text_input(
                    "Dirección",
                    value=pend.direccion or '',
                    key=f"dir_{nit}",
                    placeholder="ej. CALLE 33 # 65-100",
                )
                new_dpto = st.selectbox(
                    "Departamento",
                    options=[''] + sorted(dptos.keys()),
                    format_func=lambda c: f"{c} — {dptos.get(c, '')}" if c else '— Selecciona —',
                    index=(sorted(dptos.keys()).index(pend.codigo_dpto) + 1)
                          if pend.codigo_dpto and pend.codigo_dpto in dptos else 0,
                    key=f"dpto_{nit}",
                )
            with col2:
                # Municipio depende del dpto elegido
                muns_disponibles = muns_por_dpto.get(new_dpto, []) if new_dpto else []
                opciones_mun = [''] + [c for c, _ in muns_disponibles]
                try:
                    idx_mun = opciones_mun.index(pend.codigo_municipio) if pend.codigo_municipio else 0
                except ValueError:
                    idx_mun = 0
                new_mun = st.selectbox(
                    "Municipio",
                    options=opciones_mun,
                    format_func=lambda c: (
                        f"{c} — {dict(muns_disponibles).get(c, '')}" if c else '— Selecciona —'
                    ),
                    index=idx_mun,
                    key=f"mun_{nit}",
                )
                st.text_input(
                    "País (default 169 Colombia)",
                    value=pend.codigo_pais or '169',
                    key=f"pais_{nit}",
                    disabled=True,
                )

            cambios[nit] = {
                'direccion': new_dir.strip() or None,
                'codigo_dpto': new_dpto or None,
                'codigo_municipio': new_mun or None,
                'codigo_pais': pend.codigo_pais or '169',
            }

    st.markdown("---")
    col_btn1, col_btn2 = st.columns([1, 2])
    with col_btn1:
        if st.button("💾 Guardar y reintentar", type="primary", use_container_width=True):
            _guardar_cambios_terceros(cambios, empresa_id, sb)
    with col_btn2:
        st.caption(
            "Los cambios se guardan en el maestro de terceros (exogena_terceros) "
            "y quedarán disponibles para futuros envíos. Después de guardar, "
            "vuelve a presionar 'Generar XMLs y Excel'."
        )


def _guardar_cambios_terceros(cambios: dict, empresa_id: str, sb):
    """Persiste los cambios manuales de terceros pendientes en BD."""
    if not cambios:
        st.warning("No hay cambios para guardar.")
        return
    if sb is None:
        st.error("No hay conexión con la BD")
        return

    actualizados = 0
    errores = []
    for nit, datos in cambios.items():
        # Filtrar campos vacíos
        datos_limpios = {k: v for k, v in datos.items() if v}
        if not datos_limpios:
            continue
        try:
            sb.table("exogena_terceros").update(datos_limpios).eq(
                "empresa_id", empresa_id
            ).eq("nit", nit).execute()
            actualizados += 1
        except Exception as e:
            errores.append(f"{nit}: {e}")

    if actualizados > 0:
        st.success(
            f"✅ {actualizados} tercero(s) actualizado(s). "
            "Presiona 'Generar XMLs y Excel' de nuevo para incluirlos."
        )
    if errores:
        st.error("Errores al guardar:\n" + "\n".join(errores))


# ================================================================
# Renderiza los resultados de una generación previa (al recargar la página)
# ================================================================

def _render_resultados_previos(
    storage_key: str,
    gestor: 'GestorConsecutivos',
    empresa_id: str,
    ano_gravable: int,
    tipo_envio: str,
    info_empresa: dict,
):
    """
    Cuando ya hay un resultado de prueba guardado en session_state, mostrarlo
    para que el usuario pueda descargar de nuevo y/o marcar como definitivo.
    """
    data = st.session_state[storage_key]
    resultados = data['resultados']
    fecha = data['fecha_generacion']

    st.markdown("---")
    st.markdown("### 📂 Última generación de prueba")
    st.info(
        f"🔍 **Modo PRUEBA** — Última generación: {fecha.strftime('%Y-%m-%d %H:%M')}. "
        f"Los consecutivos NO se han persistido. Cuando confirmes que DIAN aceptó "
        f"el envío, presiona **\"✅ Marcar como DEFINITIVO\"** abajo."
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Archivos generados", f"{len(resultados)}")
    col2.metric("Registros totales", f"{data['total_registros']:,}")
    col3.metric("Valor total", f"${data['total_valor']:,.0f}")

    # Re-descarga del ZIP
    st.download_button(
        "📦 Descargar ZIP de la última generación",
        data=data['zip_bytes'],
        file_name=data['nombre_zip'],
        mime='application/zip',
        use_container_width=True,
    )

    # Tabla detalle
    detalle = pd.DataFrame([
        {
            'Formato': _formato_label(fmt),
            'Versión': f"v.{res.version}",
            'Consecutivo': res.consecutivo_usado,
            'Archivo': res.nombre_archivo,
            'Registros': res.cantidad_registros,
            'Valor total': res.valor_total,
            'Estado': '🔍 PRUEBA',
        }
        for fmt, res in resultados.items()
    ])
    st.dataframe(
        detalle, hide_index=True, use_container_width=True,
        column_config={
            'Valor total': st.column_config.NumberColumn('Valor total', format='$%d'),
        },
    )

    _render_seccion_marcar_definitivo(
        storage_key=storage_key,
        gestor=gestor,
        empresa_id=empresa_id,
        ano_gravable=ano_gravable,
        info_empresa=info_empresa,
    )


# ================================================================
# Sección "Marcar como DEFINITIVO"
# ================================================================

def _render_seccion_marcar_definitivo(
    storage_key: str,
    gestor: 'GestorConsecutivos',
    empresa_id: str,
    ano_gravable: int,
    info_empresa: dict,
):
    """
    Después de generar, mostrar la sección con el botón "Marcar como DEFINITIVO".
    Cuando el contador confirma, registra los envíos en BD y avanza los consecutivos.
    """
    if storage_key not in st.session_state:
        return

    data = st.session_state[storage_key]
    resultados = data['resultados']

    st.markdown("---")
    st.markdown("### ✅ Confirmar envío DEFINITIVO")

    st.markdown(
        "Cuando hayas subido los archivos XML a DIAN y te los hayan **aceptado**, "
        "presiona el botón de abajo. Esto:\n\n"
        "- Registra los envíos en el histórico de la plataforma\n"
        "- Avanza los consecutivos en BD para la próxima generación\n"
        "- No se puede deshacer (los consecutivos no se pueden 'devolver')\n"
    )

    # Tabla previa de qué se va a registrar
    df_previa = pd.DataFrame([
        {
            'Formato': _formato_label(fmt),
            'Consecutivo': res.consecutivo_usado,
            'Archivo': res.nombre_archivo,
        }
        for fmt, res in resultados.items()
    ])
    with st.expander("👀 Ver qué se va a registrar al marcar definitivo"):
        st.dataframe(df_previa, hide_index=True, use_container_width=True)

    # Confirmación con checkbox + botón
    col_check, col_btn = st.columns([2, 1])
    with col_check:
        confirmar = st.checkbox(
            "✓ Confirmo que estos XMLs ya fueron aceptados por DIAN",
            key=f"confirmar_def_{storage_key}",
        )
    with col_btn:
        if st.button(
            "✅ Marcar como DEFINITIVO",
            type="primary",
            disabled=not confirmar,
            use_container_width=True,
            key=f"btn_def_{storage_key}",
        ):
            _marcar_definitivo(storage_key, gestor, empresa_id, info_empresa)


def _marcar_definitivo(
    storage_key: str,
    gestor: 'GestorConsecutivos',
    empresa_id: str,
    info_empresa: dict,
):
    """
    Persiste en BD los envíos generados en modo prueba.
    Llama a gestor.registrar_envio() por cada XML del lote.
    """
    if storage_key not in st.session_state:
        st.error("No hay datos de prueba para marcar como definitivos.")
        return

    data = st.session_state[storage_key]
    resultados = data['resultados']

    usuario_actual_id = (
        st.session_state.get('user', {}).get('id')
        if isinstance(st.session_state.get('user'), dict) else None
    )

    exitos = []
    errores = []
    progreso = st.progress(0, text="Registrando envíos en BD...")
    total = len(resultados)

    for i, (fmt, res) in enumerate(resultados.items(), 1):
        try:
            envio = gestor.registrar_envio(
                empresa_id=empresa_id,
                ano_gravable=res.fecha_generacion.year if res.fecha_generacion else 2025,
                formato=fmt,
                version=res.version,
                tipo_envio=res.tipo_envio,
                consecutivo=res.consecutivo_usado,
                nombre_archivo=res.nombre_archivo,
                cantidad_registros=res.cantidad_registros,
                valor_total=res.valor_total,
                xml_content=res.xml,
                archivo_xml_path=str(res.ruta_archivo) if res.ruta_archivo else None,
                generado_por=usuario_actual_id,
            )
            exitos.append((fmt, res.consecutivo_usado, envio.envio_id))
        except ValueError as e:
            errores.append((fmt, str(e)))
        except Exception as e:
            errores.append((fmt, f"Error inesperado: {e}"))

        progreso.progress(int(i * 100 / total), text=f"Registrando F{fmt}...")

    progreso.empty()

    if exitos:
        st.success(
            f"✅ {len(exitos)} envío(s) registrado(s) como DEFINITIVOS. "
            f"Los consecutivos avanzaron correctamente."
        )
        df_exitos = pd.DataFrame(
            [{'Formato': f'F{f}', 'Consecutivo': c, 'ID BD': eid} for f, c, eid in exitos]
        )
        st.dataframe(df_exitos, hide_index=True, use_container_width=True)

    if errores:
        msg = "⚠️ Algunos envíos no se pudieron registrar:\n"
        for fmt, err in errores:
            msg += f"\n- **F{fmt}**: {err}"
        st.error(msg)

    # Limpiar resultados de prueba e invalidar cachés de consecutivos
    if exitos:
        del st.session_state[storage_key]
        # Limpiar cualquier caché de consecutivos para forzar re-consulta a BD
        cache_key = data.get('cache_key')
        if cache_key and cache_key in st.session_state:
            del st.session_state[cache_key]

        st.info("🔄 Recarga la página o cambia de pestaña para ver los nuevos consecutivos sugeridos.")
