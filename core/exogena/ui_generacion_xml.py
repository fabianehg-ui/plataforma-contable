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

    # === Banner de estado PILA ===
    pila_key = f'exo_pila_resumen_{empresa_id}_{ano_gravable}'
    pila_info = st.session_state.get(pila_key)
    if pila_info is None:
        # Verificar si hay datos PILA cargados (consulta directa)
        try:
            from db.supabase_client import get_supabase
            sb_check = get_supabase()
            from core.exogena.integrador_pila import hay_datos_pila
            if hay_datos_pila(sb_check, empresa_id, ano_gravable):
                st.success(
                    "✅ **PILA disponible** — los aportes a salud, pensión y "
                    "parafiscales se reportarán automáticamente en F1001 "
                    "(conceptos 5010/5011/5012) y F1009 (concepto 2214)."
                )
            else:
                st.warning(
                    "⚠️ **No hay datos PILA cargados** para este año gravable. "
                    "Si tu empresa tiene empleados, los aportes a salud, pensión "
                    "y parafiscales **no aparecerán** en los conceptos F1001 "
                    "5010/5011/5012. Carga las planillas PILA en la pestaña PILA "
                    "antes de generar."
                )
        except Exception:
            pass  # No bloquear si falla la verificación
    elif pila_info.get('integrada'):
        st.success(
            f"✅ **PILA integrada** — agregadas "
            f"{pila_info['lineas_f1001']} líneas F1001 (${pila_info['valor_f1001']:,.0f}), "
            f"{pila_info['lineas_f1009']} líneas F1009 (${pila_info['valor_f1009']:,.0f}). "
            f"Excluidas del balance: {pila_info.get('movimientos_excluidos_balance', 0)} movimientos "
            f"(evitar doble conteo)."
        )
    elif pila_info.get('motivo', '').startswith('error:'):
        st.error(f"❌ Error integrando PILA: {pila_info['motivo']}")

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

    saltar_enriquecimiento_web = st.checkbox(
        "⚡ Saltar enriquecimiento web (más rápido, usa solo maestro local)",
        value=False,
        key="exo_saltar_enriquecimiento_web",
        help=(
            "Cuando está activado, el sistema NO consulta RUES/Datos Abiertos/Empresite "
            "para completar datos de terceros faltantes. Solo usa el maestro local "
            "de la BD. Mucho más rápido si tu maestro de terceros ya está completo."
        ),
    )

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
        saltar_enriquecimiento_web=saltar_enriquecimiento_web,
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
    saltar_enriquecimiento_web: bool = False,
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

    # --- 1b. VALIDACIÓN + AUTO-ENRIQUECIMIENTO de terceros ---
    # Este bloque DEBE correr SIEMPRE. Cualquier fallo se reporta visiblemente.
    try:
        from core.exogena.validador_pre_generacion import (
            validar_y_enriquecer, aplicar_terceros_a_registros,
        )
    except ImportError as e_imp:
        st.error(
            f"❌ **No se pudo cargar el validador de terceros** (`{e_imp}`). "
            f"La generación se detendrá por seguridad. Reporta este error."
        )
        return

    # Cliente Supabase
    try:
        from db.supabase_client import get_supabase
        sb_local = get_supabase()
    except Exception as e:
        st.error(f"❌ No se pudo conectar a la base de datos: {e}")
        return

    # Construir cascada de enriquecedores: cada uno por separado para que
    # un fallo de un enriquecedor no detenga el resto.
    cascada_enriquecedores = []
    fuentes_disponibles = []
    fuentes_no_disponibles = []

    try:
        from core.exogena.enriquecimiento import CacheEnriquecedor, EnriquecedorEnCascada
        cascada_enriquecedores.append(CacheEnriquecedor(sb_local))
        fuentes_disponibles.append('Caché local')
    except Exception as e:
        fuentes_no_disponibles.append(f'Caché: {type(e).__name__}')

    if saltar_enriquecimiento_web:
        st.info(
            "⚡ Modo rápido activado: se omite enriquecimiento web "
            "(RUES / Datos Abiertos / Empresite). Los terceros con datos "
            "incompletos en BD quedarán pendientes para revisión."
        )
    else:
        for nombre_clase, label in [
            ('RUESEnriquecedor', 'RUES Confecámaras'),
            ('DatosAbiertosEnriquecedor', 'Datos Abiertos del Gobierno'),
            ('EmpresiteEnriquecedor', 'Empresite Colombia'),
        ]:
            try:
                from core.exogena.enriquecimiento import (
                    RUESEnriquecedor, DatosAbiertosEnriquecedor, EmpresiteEnriquecedor,
                )
                clases = {
                    'RUESEnriquecedor': RUESEnriquecedor,
                    'DatosAbiertosEnriquecedor': DatosAbiertosEnriquecedor,
                    'EmpresiteEnriquecedor': EmpresiteEnriquecedor,
                }
                instancia = clases[nombre_clase]()
                if instancia.disponible():
                    cascada_enriquecedores.append(instancia)
                    fuentes_disponibles.append(label)
                else:
                    fuentes_no_disponibles.append(f'{label}: dependencias faltantes (instala requests/bs4)')
            except Exception as e:
                fuentes_no_disponibles.append(f'{label}: {type(e).__name__}: {e}')

    cascada = (
        EnriquecedorEnCascada(cascada_enriquecedores)
        if cascada_enriquecedores else None
    )

    # Mostrar al usuario qué fuentes están activas
    if fuentes_disponibles:
        st.caption(
            f"🔎 Buscando datos faltantes en: {', '.join(fuentes_disponibles)}"
        )
    if fuentes_no_disponibles:
        with st.expander(f"⚠️ {len(fuentes_no_disponibles)} fuente(s) de enriquecimiento no disponible(s) (clic para ver)"):
            for f in fuentes_no_disponibles:
                st.caption(f"- {f}")

    # Cargar terceros actuales de la empresa (BD)
    # IMPORTANTE: Supabase limita a 1000 filas por consulta por defecto.
    # Si la empresa tiene más terceros, hay que paginar con .range().
    try:
        terceros_dict_bd = {}
        offset = 0
        page_size = 1000
        while True:
            terceros_resp = sb_local.table("exogena_terceros").select(
                "nit, dv, tipo_documento, razon_social, "
                "primer_apellido, segundo_apellido, primer_nombre, otros_nombres, "
                "direccion, codigo_dpto, codigo_municipio, codigo_pais"
            ).eq("empresa_id", empresa_id).range(offset, offset + page_size - 1).execute()
            batch = terceros_resp.data or []
            if not batch:
                break
            for t in batch:
                terceros_dict_bd[t['nit']] = t
            if len(batch) < page_size:
                break  # última página
            offset += page_size
        st.caption(f"📋 {len(terceros_dict_bd)} tercero(s) cargado(s) del maestro BD")
    except Exception as e:
        st.error(f"❌ Error consultando maestro de terceros: {e}")
        return

    # Cargar catálogo DANE completo de municipios para inferencia exhaustiva
    # (clave normalizada → (cod_dpto, cod_mun)). Se cachea en session_state.
    catalogo_dane_key = f"_exo_cat_dane_municipios_{empresa_id}"
    if catalogo_dane_key not in st.session_state:
        try:
            import unicodedata
            muns_resp = sb_local.table("exogena_cat_municipios").select(
                "codigo_dpto, codigo_mcp, nombre"
            ).execute()
            catalogo_dane = {}
            for m in (muns_resp.data or []):
                clave_norm = ''.join(
                    c for c in unicodedata.normalize('NFKD', m['nombre'].upper())
                    if unicodedata.category(c) != 'Mn'
                ).strip()
                catalogo_dane[clave_norm] = (m['codigo_dpto'], m['codigo_mcp'])
            st.session_state[catalogo_dane_key] = catalogo_dane
        except Exception:
            st.session_state[catalogo_dane_key] = {}
    catalogo_dane = st.session_state[catalogo_dane_key]

    # Ejecutar el validador
    try:
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
            catalogo_municipios_dane=catalogo_dane,
        )
    except Exception as e:
        st.error(f"❌ Error ejecutando validador: {e}")
        st.code(traceback.format_exc())
        return

    # === Resumen de validación SIEMPRE visible ===
    col_v1, col_v2, col_v3, col_v4 = st.columns(4)
    col_v1.metric("Terceros procesados", resultado_validacion.total_terceros)
    col_v2.metric("✅ Completos", len(resultado_validacion.terceros_completos))
    col_v3.metric("⚠️ Pendientes", resultado_validacion.total_pendientes)
    col_v4.metric("🔎 Enriquecidos", resultado_validacion.enriquecidos_auto)

    if resultado_validacion.enriquecidos_auto > 0:
        fuentes_str = ', '.join(
            f'{f}: {n}' for f, n in resultado_validacion.fuentes_usadas.items()
        )
        st.info(f"🔎 Enriquecidos automáticamente desde: {fuentes_str}")
    if resultado_validacion.tipos_documento_corregidos > 0:
        st.info(
            f"🆔 {resultado_validacion.tipos_documento_corregidos} tercero(s) "
            f"con tipo de documento corregido automáticamente "
            f"(NITs reclasificados como cédulas según patrón del número)"
        )
    if resultado_validacion.enriquecidos_fallback > 0:
        st.info(
            f"🏢 {resultado_validacion.enriquecidos_fallback} persona(s) natural(es) "
            f"recibieron datos de ubicación de la empresa informante como fallback "
            f"(dirección: {info_empresa.get('direccion', '')})"
        )
    if resultado_validacion.bancos_inferidos > 0:
        st.info(
            f"🏦 {resultado_validacion.bancos_inferidos} cuenta(s) bancaria(s) "
            f"del F1012 con NIT del banco inferido automáticamente"
        )

    # === Persistir auto-correcciones a BD ===
    _persistir_correcciones_terceros(
        resultado_validacion.terceros_completos,
        terceros_dict_bd,
        empresa_id,
        sb_local,
    )

    # === Si hay pendientes: DETENER y mostrar formulario ===
    if resultado_validacion.tiene_pendientes:
        progreso.empty()
        st.error(
            f"⛔ **Generación detenida**: "
            f"{resultado_validacion.total_pendientes} tercero(s) con datos incompletos. "
            f"Complete los datos en el formulario de abajo y vuelva a presionar "
            f"'Generar XMLs y Excel' para continuar."
        )
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
    faltantes de los terceros que no se pudieron enriquecer automáticamente.

    Diseño robusto:
      - Usa st.form para agrupar TODO el input y procesar en un solo submit
        (evita re-renders intermedios que causaban NotFoundError de Streamlit)
      - Auto-infiere dpto/municipio desde la dirección escrita usando el
        catálogo DANE local (sin queries adicionales a BD)
      - Búsqueda de dpto/municipio por NOMBRE en lugar de selectbox encadenado
    """
    pendientes = resultado_validacion.terceros_pendientes
    total = len(pendientes)

    # Importar helpers
    try:
        from core.exogena.enriquecimiento.helpers_inferencia import (
            inferir_dpto_municipio_desde_texto,
            CIUDADES_CONOCIDAS,
            es_persona_natural,
        )
    except ImportError:
        CIUDADES_CONOCIDAS = {}
        inferir_dpto_municipio_desde_texto = lambda *a: None
        es_persona_natural = lambda d: False

    st.markdown("#### 📝 Completar datos faltantes")
    st.caption(
        f"Los siguientes **{total} tercero(s)** no pudieron enriquecerse automáticamente. "
        "Complete los campos faltantes. Si solo escribes la **dirección con ciudad** "
        "(ej. 'Calle 33 Medellín'), el sistema deducirá el dpto y municipio."
    )

    # Botón para descargar la lista completa de pendientes en CSV
    try:
        import io as _io
        import csv as _csv
        buf = _io.StringIO()
        w = _csv.writer(buf)
        w.writerow([
            'nit', 'tipo_detectado', 'razon_social', 'primer_apellido',
            'segundo_apellido', 'primer_nombre', 'otros_nombres',
            'direccion', 'codigo_dpto', 'codigo_municipio', 'codigo_pais',
            'errores', 'formatos_afectados',
        ])
        for nit_p, pend_p in pendientes.items():
            w.writerow([
                nit_p,
                getattr(pend_p, 'tipo_documento', '') or '',
                getattr(pend_p, 'razon_social', '') or '',
                getattr(pend_p, 'primer_apellido', '') or '',
                getattr(pend_p, 'segundo_apellido', '') or '',
                getattr(pend_p, 'primer_nombre', '') or '',
                getattr(pend_p, 'otros_nombres', '') or '',
                getattr(pend_p, 'direccion', '') or '',
                getattr(pend_p, 'codigo_dpto', '') or '',
                getattr(pend_p, 'codigo_municipio', '') or '',
                getattr(pend_p, 'codigo_pais', '') or '',
                ' | '.join(pend_p.errores) if pend_p.errores else '',
                ', '.join(pend_p.formatos_afectados) if pend_p.formatos_afectados else '',
            ])
        st.download_button(
            label=f"📋 Descargar lista de los {total} pendientes (CSV)",
            data=buf.getvalue(),
            file_name=f"pendientes_{empresa_id[:8]}.csv",
            mime="text/csv",
        )
    except Exception as _e:
        st.caption(f"⚠️ No se pudo generar CSV de pendientes: {_e}")

    # Cargar catálogo de departamentos y mapa nombre→código de municipios
    # (una sola query, cacheada en session_state)
    cache_key = f"_exo_cat_dane_{empresa_id}"
    if cache_key not in st.session_state:
        try:
            dptos_resp = sb.table("exogena_cat_departamentos").select("*").execute()
            muns_resp = sb.table("exogena_cat_municipios").select("*").execute()
            dptos = {d['codigo']: d['nombre'] for d in (dptos_resp.data or [])}
            muns_por_dpto = {}
            mun_lookup = {}  # nombre_municipio_normalizado → (codigo_dpto, codigo_mcp)
            for m in (muns_resp.data or []):
                cod_dpto = m['codigo_dpto']
                cod_mcp = m['codigo_mcp']
                nombre_mun = m['nombre']
                muns_por_dpto.setdefault(cod_dpto, []).append((cod_mcp, nombre_mun))
                # Lookup por nombre (normalizado)
                import unicodedata
                clave_norm = ''.join(
                    c for c in unicodedata.normalize('NFKD', nombre_mun.upper())
                    if unicodedata.category(c) != 'Mn'
                ).strip()
                mun_lookup[clave_norm] = (cod_dpto, cod_mcp)
            st.session_state[cache_key] = {
                'dptos': dptos,
                'muns_por_dpto': muns_por_dpto,
                'mun_lookup': mun_lookup,
            }
        except Exception as e:
            st.warning(f"⚠️ No se pudo cargar catálogo DANE: {e}")
            st.session_state[cache_key] = {
                'dptos': {}, 'muns_por_dpto': {}, 'mun_lookup': {}
            }

    cat = st.session_state[cache_key]
    dptos = cat['dptos']
    muns_por_dpto = cat['muns_por_dpto']

    # ============================================================
    # FORMULARIO ÚNICO con st.form (evita re-renders intermedios)
    # ============================================================
    with st.form(key=f"form_completar_{empresa_id}", clear_on_submit=False):
        st.caption(
            "💡 Tip: en el campo **Dirección** escribe la ciudad junto con la "
            "dirección (ej. *'Calle 33 #65-100, Medellín'*). El sistema "
            "deducirá automáticamente departamento y municipio al guardar."
        )

        # Inputs por tercero (todos van al diccionario `cambios`)
        # Importar helper de inferencia para determinar si es natural por patrón NIT
        try:
            from core.exogena.enriquecimiento.helpers_inferencia import (
                inferir_tipo_documento_real,
            )
        except ImportError:
            inferir_tipo_documento_real = lambda _: None

        for nit, pend in pendientes.items():
            tipo_inferido = inferir_tipo_documento_real(nit)
            if tipo_inferido == 13:
                es_nat = True
            elif tipo_inferido == 31:
                es_nat = False
            else:
                es_nat = es_persona_natural({
                    'tipo_documento': 13 if pend.primer_apellido or pend.primer_nombre else 31
                })
            nombre = (pend.razon_social or
                      f"{pend.primer_nombre or ''} {pend.primer_apellido or ''}".strip() or
                      '(sin nombre)')
            tipo_label = "👤 Natural" if es_nat else "🏢 Jurídica"

            st.markdown(f"---")
            st.markdown(
                f"**{tipo_label} · {nit}** — {nombre[:60]}  \n"
                f"<small style='color:#888'>Errores: {', '.join(pend.errores)} · "
                f"Formatos: {', '.join('F'+f for f in pend.formatos_afectados)}</small>",
                unsafe_allow_html=True,
            )

            col1, col2 = st.columns(2)
            with col1:
                # Si es natural: pedir apellidos/nombres
                if es_nat:
                    st.text_input(
                        "Primer apellido",
                        value=pend.primer_apellido or '',
                        key=f"papl_{nit}",
                        placeholder="ej. GONZALEZ",
                    )
                    st.text_input(
                        "Segundo apellido (opcional)",
                        value='',
                        key=f"sapl_{nit}",
                    )
                else:
                    # Jurídica: pedir razón social
                    st.text_input(
                        "Razón social",
                        value=pend.razon_social or '',
                        key=f"raz_{nit}",
                        placeholder="ej. EMPRESA SAS",
                    )

                # Dirección — campo libre, se infiere ciudad al guardar
                st.text_input(
                    "Dirección (incluye ciudad si la sabes)",
                    value=pend.direccion or '',
                    key=f"dir_{nit}",
                    placeholder="ej. CALLE 33 #65-100, MEDELLIN",
                )

            with col2:
                if es_nat:
                    st.text_input(
                        "Primer nombre",
                        value=pend.primer_nombre or '',
                        key=f"pnom_{nit}",
                        placeholder="ej. JORGE",
                    )
                    st.text_input(
                        "Otros nombres (opcional)",
                        value='',
                        key=f"onom_{nit}",
                    )

                # Dpto + Municipio: campos de texto con buscador (no selectbox encadenado)
                st.text_input(
                    "Departamento (código o nombre, deja vacío para inferir)",
                    value=(f"{pend.codigo_dpto} — {dptos.get(pend.codigo_dpto, '')}"
                           if pend.codigo_dpto and pend.codigo_dpto in dptos else ''),
                    key=f"dpto_txt_{nit}",
                    placeholder="ej. 05 — ANTIOQUIA  o  ANTIOQUIA",
                )
                st.text_input(
                    "Municipio (código o nombre, deja vacío para inferir)",
                    value=pend.codigo_municipio or '',
                    key=f"mun_txt_{nit}",
                    placeholder="ej. 001 — MEDELLIN  o  MEDELLIN",
                )

        st.markdown("---")
        col_btn1, col_btn2 = st.columns([1, 2])
        with col_btn1:
            submitted = st.form_submit_button(
                "💾 Guardar y reintentar",
                type="primary",
                use_container_width=True,
            )
        with col_btn2:
            st.caption(
                "Los cambios se guardan en el maestro de terceros (`exogena_terceros`). "
                "Después de guardar, vuelve a presionar 'Generar XMLs y Excel'."
            )

    # ============================================================
    # PROCESAR submit (fuera del form, después del submit)
    # ============================================================
    if submitted:
        cambios = _construir_cambios_desde_form(
            pendientes, dptos, muns_por_dpto, cat.get('mun_lookup', {}),
            inferir_dpto_municipio_desde_texto,
        )
        _guardar_cambios_terceros(cambios, empresa_id, sb)


def _construir_cambios_desde_form(
    pendientes,
    dptos,
    muns_por_dpto,
    mun_lookup,
    inferir_dpto_municipio_desde_texto,
):
    """
    Construye el dict {nit: cambios} a partir de los valores del form.
    Hace la inferencia de dpto/municipio aquí, después del submit.
    """
    import unicodedata
    cambios = {}

    def _normalizar(s):
        if not s:
            return ''
        s2 = ''.join(
            c for c in unicodedata.normalize('NFKD', str(s).upper())
            if unicodedata.category(c) != 'Mn'
        )
        return s2.strip()

    def _resolver_dpto(texto_input):
        """Acepta '05', '05 — ANTIOQUIA', 'ANTIOQUIA' → devuelve código '05' o None."""
        if not texto_input:
            return None
        t = _normalizar(texto_input)
        # ¿Es un código de 2 dígitos?
        codigo_extraido = t.split('—')[0].split('-')[0].strip()
        if codigo_extraido in dptos:
            return codigo_extraido
        # Buscar por nombre
        for cod, nom in dptos.items():
            if _normalizar(nom) == t or _normalizar(nom) in t:
                return cod
        return None

    def _resolver_municipio(texto_input, codigo_dpto):
        """Acepta código '001', nombre 'MEDELLIN', etc."""
        if not texto_input:
            return None
        t = _normalizar(texto_input)
        codigo_extraido = t.split('—')[0].split('-')[0].strip()
        if codigo_dpto and codigo_dpto in muns_por_dpto:
            # ¿Código directo dentro del dpto?
            for cod, nom in muns_por_dpto[codigo_dpto]:
                if cod == codigo_extraido:
                    return cod
                if _normalizar(nom) == t or _normalizar(nom) in t:
                    return cod
        # Búsqueda global por nombre (fallback)
        if t in mun_lookup:
            cod_d, cod_m = mun_lookup[t]
            return cod_m
        return None

    for nit, pend in pendientes.items():
        # Recuperar valores del session_state (los inputs los guardaron con esos keys)
        razon = st.session_state.get(f"raz_{nit}", '') or None
        papl = st.session_state.get(f"papl_{nit}", '') or None
        sapl = st.session_state.get(f"sapl_{nit}", '') or None
        pnom = st.session_state.get(f"pnom_{nit}", '') or None
        onom = st.session_state.get(f"onom_{nit}", '') or None
        direccion = (st.session_state.get(f"dir_{nit}", '') or '').strip() or None
        dpto_txt = st.session_state.get(f"dpto_txt_{nit}", '')
        mun_txt = st.session_state.get(f"mun_txt_{nit}", '')

        # Resolver códigos dpto/municipio
        codigo_dpto = _resolver_dpto(dpto_txt)
        codigo_mun = _resolver_municipio(mun_txt, codigo_dpto)

        # Si dpto o mun siguen vacíos, intentar inferir desde la dirección
        if not codigo_dpto or not codigo_mun:
            inferido = inferir_dpto_municipio_desde_texto(direccion or '', razon or '')
            if inferido:
                if not codigo_dpto:
                    codigo_dpto = inferido[0]
                if not codigo_mun:
                    codigo_mun = inferido[1]

        cambios[nit] = {
            k: v for k, v in {
                'razon_social': razon,
                'primer_apellido': (papl or '').strip().upper() if papl else None,
                'segundo_apellido': (sapl or '').strip().upper() if sapl else None,
                'primer_nombre': (pnom or '').strip().upper() if pnom else None,
                'otros_nombres': (onom or '').strip().upper() if onom else None,
                'direccion': direccion,
                'codigo_dpto': codigo_dpto,
                'codigo_municipio': codigo_mun,
                'codigo_pais': pend.codigo_pais or '169',
            }.items() if v
        }

    return cambios


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


# ================================================================
# Persistir correcciones automáticas a la BD
# ================================================================

def _persistir_correcciones_terceros(
    terceros_completos: dict,
    terceros_bd_original: dict,
    empresa_id: str,
    sb,
) -> None:
    """
    Persiste a BD las correcciones automáticas hechas a terceros, comparando
    los datos completos (post-validación + auto-división + enriquecimiento)
    contra los datos originales en BD.

    Se actualiza un tercero solo si tiene cambios reales en al menos uno
    de los campos relevantes. La actualización es silenciosa.

    Args:
        terceros_completos: dict {nit: dict_con_datos_corregidos}
        terceros_bd_original: dict {nit: dict_original_de_BD}
        empresa_id: UUID empresa
        sb: cliente Supabase
    """
    if not sb:
        return

    campos_persistir = [
        'tipo_documento',  # ← incluido para persistir correcciones CC vs NIT
        'razon_social', 'primer_apellido', 'segundo_apellido',
        'primer_nombre', 'otros_nombres',
        'direccion', 'codigo_dpto', 'codigo_municipio', 'codigo_pais',
    ]

    actualizaciones_realizadas = 0
    errores = []
    for nit, datos_completos in terceros_completos.items():
        original = terceros_bd_original.get(nit, {})
        cambios = {}
        for campo in campos_persistir:
            valor_nuevo = datos_completos.get(campo)
            valor_original = original.get(campo)
            # Normalizar para comparar (None == '' == 0)
            v_nuevo_norm = (valor_nuevo or '').strip() if isinstance(valor_nuevo, str) else valor_nuevo
            v_orig_norm = (valor_original or '').strip() if isinstance(valor_original, str) else valor_original

            if v_nuevo_norm != v_orig_norm:
                # Si valor_nuevo es None y valor_original es '' o None → no contar
                if not v_nuevo_norm and not v_orig_norm:
                    continue
                cambios[campo] = valor_nuevo

        if cambios:
            try:
                sb.table("exogena_terceros").update(cambios).eq(
                    "empresa_id", empresa_id
                ).eq("nit", nit).execute()
                actualizaciones_realizadas += 1
            except Exception as e:
                errores.append(f"{nit}: {e}")

    if actualizaciones_realizadas > 0:
        st.success(
            f"💾 {actualizaciones_realizadas} tercero(s) corregido(s) "
            f"automáticamente y guardado(s) en BD para futuros envíos."
        )
    if errores:
        st.warning(
            f"⚠️ {len(errores)} actualización(es) fallaron silenciosamente. "
            f"Detalles en logs."
        )
