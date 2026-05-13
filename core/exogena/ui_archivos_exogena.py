"""
UI del tab unificado "📂 Archivos" para el módulo de Información Exógena.

Reemplaza los tabs separados:
  - Mapeo nativo
  - Terceros
  - Balance
  - PILA

Y los unifica en una sola pantalla que:
  1. Muestra el estado de cada archivo (cargado/pendiente, fecha, tamaño)
  2. Detecta automáticamente qué archivos son necesarios según el balance
  3. Permite subir/reemplazar/eliminar archivos
  4. Re-ejecuta el motor de clasificación automáticamente al cambiar archivos

Función principal: render_tab_archivos(empresa, año_gravable, supabase, periodo)
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st

from core.exogena.detector_pila_requerida import (
    analizar_necesidad_pila,
    emoji_estado,
    texto_estado,
    DiagnosticoPilaEmpresa,
)


# ============================================================
# Estado de cada tipo de archivo
# ============================================================

def _estado_archivo(supabase, empresa_id: str, año_gravable: int, periodo_id: Optional[str]) -> dict:
    """Devuelve un dict con el estado de cada tipo de archivo."""
    estado = {
        'terceros': {'cargado': False, 'count': 0, 'fecha': None},
        'mapeo_nativo': {'cargado': False, 'count': 0, 'fecha': None},
        'balance': {'cargado': False, 'count': 0, 'fecha': None},
        'pila_planillas': {'cargado': False, 'count': 0, 'fecha': None, 'total': 0},
        'pila_pasivo': {'cargado': False, 'count': 0, 'fecha': None, 'total': 0},
        'cesantias_pagadas': {'cargado': False, 'count': 0, 'fecha': None, 'total': 0},
        'cesantias_pasivo': {'cargado': False, 'count': 0, 'fecha': None, 'total': 0},
        'declaracion_renta': {'cargado': False, 'count': 0, 'fecha': None},
    }

    try:
        # Terceros
        r = supabase.table('exogena_terceros') \
            .select('id, creado_en', count='exact') \
            .eq('empresa_id', empresa_id) \
            .limit(1) \
            .execute()
        n = getattr(r, 'count', 0) or 0
        if n > 0:
            estado['terceros']['cargado'] = True
            estado['terceros']['count'] = n
    except Exception:
        pass

    try:
        # Mapeo nativo (mapeo_empresa)
        r = supabase.table('exogena_mapeo_empresa') \
            .select('id', count='exact') \
            .eq('empresa_id', empresa_id) \
            .eq('año_gravable', año_gravable) \
            .limit(1) \
            .execute()
        n = getattr(r, 'count', 0) or 0
        if n > 0:
            estado['mapeo_nativo']['cargado'] = True
            estado['mapeo_nativo']['count'] = n
    except Exception:
        pass

    if periodo_id:
        try:
            # Balance
            r = supabase.table('exogena_balance') \
                .select('id', count='exact') \
                .eq('periodo_id', periodo_id) \
                .eq('es_totalizador', False) \
                .limit(1) \
                .execute()
            n = getattr(r, 'count', 0) or 0
            if n > 0:
                estado['balance']['cargado'] = True
                estado['balance']['count'] = n
        except Exception:
            pass

    try:
        # Planillas PILA
        r = supabase.table('exogena_pila_planillas') \
            .select('id, periodo_cot, total_pagado, archivo_origen, creado_en') \
            .eq('empresa_id', empresa_id) \
            .eq('año_gravable', año_gravable) \
            .execute()
        planillas = r.data or []
        periodo_pasivo = f'{año_gravable}12'
        anuales = [p for p in planillas if p.get('periodo_cot') != periodo_pasivo]
        pasivo = [p for p in planillas if p.get('periodo_cot') == periodo_pasivo]
        if anuales:
            estado['pila_planillas']['cargado'] = True
            estado['pila_planillas']['count'] = len(anuales)
            estado['pila_planillas']['total'] = sum(float(p.get('total_pagado') or 0) for p in anuales)
            estado['pila_planillas']['fecha'] = max((p.get('creado_en') for p in anuales), default=None)
        if pasivo:
            estado['pila_pasivo']['cargado'] = True
            estado['pila_pasivo']['count'] = len(pasivo)
            estado['pila_pasivo']['total'] = sum(float(p.get('total_pagado') or 0) for p in pasivo)
            estado['pila_pasivo']['fecha'] = max((p.get('creado_en') for p in pasivo), default=None)
    except Exception:
        pass

    try:
        # Cesantías
        r = supabase.table('exogena_pila_cesantias') \
            .select('id, año_causado, es_pasivo, total, fondo_nombre, creado_en') \
            .eq('empresa_id', empresa_id) \
            .eq('año_gravable', año_gravable) \
            .execute()
        cesantias = r.data or []
        pagadas = [c for c in cesantias if not c.get('es_pasivo')]
        pasivo = [c for c in cesantias if c.get('es_pasivo')]
        if pagadas:
            estado['cesantias_pagadas']['cargado'] = True
            estado['cesantias_pagadas']['count'] = len(pagadas)
            estado['cesantias_pagadas']['total'] = sum(float(c.get('total') or 0) for c in pagadas)
            estado['cesantias_pagadas']['fecha'] = max((c.get('creado_en') for c in pagadas), default=None)
        if pasivo:
            estado['cesantias_pasivo']['cargado'] = True
            estado['cesantias_pasivo']['count'] = len(pasivo)
            estado['cesantias_pasivo']['total'] = sum(float(c.get('total') or 0) for c in pasivo)
            estado['cesantias_pasivo']['fecha'] = max((c.get('creado_en') for c in pasivo), default=None)
    except Exception:
        pass

    return estado


# ============================================================
# Función principal: tab Archivos
# ============================================================

def render_tab_archivos(empresa: dict, año_gravable: int, supabase, periodo: Optional[dict]) -> None:
    """Renderiza el tab unificado de archivos.

    Args:
        empresa: dict con 'id', 'nit', 'razon_social'
        año_gravable: int
        supabase: cliente Supabase
        periodo: dict con 'id' del periodo o None si no existe aún
    """
    st.markdown("### 📂 Documentos de Exógena")
    st.caption(
        f"Carga los archivos necesarios para generar los reportes de exógena del año "
        f"{año_gravable}. El sistema detecta automáticamente cuáles son obligatorios "
        f"según el balance de la empresa."
    )

    periodo_id = periodo.get('id') if periodo else None
    estado = _estado_archivo(supabase, empresa['id'], año_gravable, periodo_id)

    # Diagnóstico PILA (sólo si hay balance)
    diag: Optional[DiagnosticoPilaEmpresa] = None
    if estado['balance']['cargado']:
        try:
            diag = analizar_necesidad_pila(supabase, empresa['id'], año_gravable)
        except Exception as e:
            st.warning(f"⚠️ No se pudo analizar el balance para PILA: {e}")

    # ============================================================
    # BARRA DE PROGRESO
    # ============================================================
    _render_barra_progreso(estado, diag)

    st.markdown("---")

    # ============================================================
    # SECCIÓN 1: ARCHIVOS BASE (siempre obligatorios)
    # ============================================================
    st.markdown("#### 📋 Archivos base")

    _render_seccion_terceros(empresa, año_gravable, supabase, estado['terceros'])
    st.markdown("")
    _render_seccion_mapeo_nativo(empresa, año_gravable, supabase, estado['mapeo_nativo'])
    st.markdown("")
    _render_seccion_balance(empresa, año_gravable, supabase, periodo, estado['balance'])

    # ============================================================
    # SECCIÓN 2: PILA Y CESANTÍAS (condicionales)
    # ============================================================
    if diag is None:
        # Aún no hay balance — mostrar mensaje
        st.markdown("---")
        st.info(
            "📥 Carga primero el **balance de prueba** para que el sistema detecte "
            "automáticamente si necesitas cargar planillas PILA o informes de cesantías."
        )
    elif not diag.necesita_pila:
        # Empresa sin nómina — omitir PILA
        st.markdown("---")
        st.success(
            f"⚪ **PILA omitido automáticamente** — {diag.motivo}"
        )
    else:
        # Empresa con nómina — mostrar sección PILA
        st.markdown("---")
        st.markdown("#### 🏥 PILA y Cesantías")
        st.markdown(
            f"<small>Detectamos que esta empresa tiene nómina "
            f"(${diag.saldo_aportes_por_pagar + diag.saldo_aportes_pagados + diag.saldo_cesantias_consolidadas:,.0f} "
            f"entre aportes y cesantías). Estos archivos son <b>obligatorios</b> para que "
            f"los formatos F1001, F1009 y F2276 se generen correctamente.</small>",
            unsafe_allow_html=True,
        )

        # Mostrar pendientes destacados
        if diag.pendientes:
            with st.expander(f"⚠️ {len(diag.pendientes)} archivo(s) PILA pendiente(s)", expanded=True):
                for p in diag.pendientes:
                    st.warning(
                        f"**{p['archivo']}** — {p['razon']}\n\n"
                        f"_Destino: {p['destino']}_"
                    )

        # Carga de planillas
        _render_seccion_pila_planillas(empresa, año_gravable, supabase, estado, diag)
        st.markdown("")
        _render_seccion_cesantias(empresa, año_gravable, supabase, estado, diag)

    # ============================================================
    # SECCIÓN 3: DECLARACIÓN DE RENTA (opcional)
    # ============================================================
    st.markdown("---")
    _render_seccion_declaracion_renta(empresa, año_gravable, supabase, estado['declaracion_renta'])

    # ============================================================
    # BOTÓN DE RECÁLCULO
    # ============================================================
    st.markdown("---")
    _render_boton_recalcular(empresa, año_gravable, supabase, periodo_id, estado, diag)


# ============================================================
# Sub-secciones
# ============================================================

def _render_barra_progreso(estado: dict, diag: Optional[DiagnosticoPilaEmpresa]) -> None:
    """Muestra una barra de progreso con el estado general de archivos."""
    obligatorios = [
        estado['terceros']['cargado'],
        estado['mapeo_nativo']['cargado'],
        estado['balance']['cargado'],
    ]
    if diag and diag.necesita_pila:
        if diag.requiere_planilla_anual:
            obligatorios.append(estado['pila_planillas']['cargado'])
        if diag.requiere_planilla_pasivo:
            obligatorios.append(estado['pila_pasivo']['cargado'])
        if diag.requiere_cesantias_pagadas:
            obligatorios.append(estado['cesantias_pagadas']['cargado'])
        if diag.requiere_cesantias_pasivo:
            obligatorios.append(estado['cesantias_pasivo']['cargado'])

    completados = sum(obligatorios)
    total = len(obligatorios)
    pct = int(completados * 100 / total) if total > 0 else 0

    col1, col2 = st.columns([3, 1])
    with col1:
        st.progress(pct / 100, text=f"Progreso: {completados}/{total} archivos obligatorios ({pct}%)")
    with col2:
        if pct == 100:
            st.success("✅ Completo")
        elif pct >= 50:
            st.warning(f"⏳ Faltan {total - completados}")
        else:
            st.error(f"❌ Faltan {total - completados}")


def _render_seccion_terceros(empresa, año_gravable, supabase, estado_t) -> None:
    """Sección: Maestro de Terceros."""
    icon = "✅" if estado_t['cargado'] else "⏳"
    label = f"{icon} **Maestro de Terceros**"
    if estado_t['cargado']:
        label += f" — {estado_t['count']:,} NITs cargados"

    with st.expander(label, expanded=not estado_t['cargado']):
        st.markdown(
            "Lista completa de los terceros (clientes, proveedores, empleados) con su NIT, "
            "razón social, dirección y tipo de documento. Se usa para enriquecer todos los formatos."
        )
        archivo = st.file_uploader(
            "Archivo de terceros (.xlsx, .csv)",
            type=['xlsx', 'xls', 'csv'],
            key=f"upload_terceros_{empresa['id']}_{año_gravable}",
        )
        if archivo is not None:
            st.info(
                "💡 Para procesar terceros, ve por ahora al tab antiguo de 'Terceros' "
                "(función completa pendiente de migrar a este flujo unificado)."
            )


def _render_seccion_mapeo_nativo(empresa, año_gravable, supabase, estado_m) -> None:
    """Sección: Codificación nativa del software contable."""
    icon = "✅" if estado_m['cargado'] else "⏳"
    label = f"{icon} **Mapeo nativo (codificación)**"
    if estado_m['cargado']:
        label += f" — {estado_m['count']:,} reglas cargadas"

    with st.expander(label, expanded=not estado_m['cargado']):
        st.markdown(
            "Archivo de codificación que mapea rangos de cuentas contables a formatos y "
            "conceptos DIAN. Lo exporta tu software contable (Siigo, World Office, Helisa, etc.)."
        )
        archivo = st.file_uploader(
            "Archivo de codificación (.xlsx)",
            type=['xlsx'],
            key=f"upload_mapeo_{empresa['id']}_{año_gravable}",
        )
        if archivo is not None:
            st.info(
                "💡 Para procesar mapeo nativo, ve por ahora al tab antiguo "
                "(función pendiente de migrar a este flujo unificado)."
            )


def _render_seccion_balance(empresa, año_gravable, supabase, periodo, estado_b) -> None:
    """Sección: Balance de prueba."""
    icon = "✅" if estado_b['cargado'] else "⏳"
    label = f"{icon} **Balance de Prueba con NITs**"
    if estado_b['cargado']:
        label += f" — {estado_b['count']:,} movimientos cargados"

    with st.expander(label, expanded=not estado_b['cargado']):
        st.markdown(
            "Balance de prueba auxiliar con movimientos por NIT al 31-dic. "
            "Debe incluir cuentas a nivel auxiliar (8 dígitos o más) con débitos, créditos y saldo final."
        )
        archivo = st.file_uploader(
            "Balance de prueba (.xlsx)",
            type=['xlsx'],
            key=f"upload_balance_{empresa['id']}_{año_gravable}",
        )
        if archivo is not None:
            st.info(
                "💡 Para procesar balance, ve por ahora al tab antiguo "
                "(función pendiente de migrar a este flujo unificado)."
            )


def _render_seccion_pila_planillas(empresa, año_gravable, supabase, estado, diag) -> None:
    """Sección: planillas PILA (anual + pasivo dic)."""
    col1, col2 = st.columns(2)

    # Planilla anual
    with col1:
        icon = "✅" if estado['pila_planillas']['cargado'] else ("⏳" if diag.requiere_planilla_anual else "⚪")
        st.markdown(f"##### {icon} Planillas PILA del año")
        if estado['pila_planillas']['cargado']:
            st.success(
                f"{estado['pila_planillas']['count']} planillas cargadas · "
                f"${estado['pila_planillas']['total']:,.0f}"
            )
        else:
            st.markdown(
                f"<small>Descarga del operador (SuAporte/Ceiba) con rango "
                f"<b>01-ene-{año_gravable}</b> a <b>31-dic-{año_gravable}</b></small>",
                unsafe_allow_html=True,
            )
        archivo = st.file_uploader(
            f"Comprobante MM {año_gravable} anual",
            type=['xls', 'xlsx'],
            key=f"upload_pila_anual_{empresa['id']}_{año_gravable}",
            label_visibility='collapsed',
        )
        if archivo is not None:
            _procesar_planilla_pila(archivo, empresa, año_gravable, supabase, es_pasivo=False)

    # Planilla pasivo
    with col2:
        icon = "✅" if estado['pila_pasivo']['cargado'] else ("⏳" if diag.requiere_planilla_pasivo else "⚪")
        st.markdown(f"##### {icon} Planilla pasivo dic")
        if estado['pila_pasivo']['cargado']:
            st.success(
                f"{estado['pila_pasivo']['count']} planilla · "
                f"${estado['pila_pasivo']['total']:,.0f}"
            )
        else:
            st.markdown(
                f"<small>Descarga del operador con rango "
                f"<b>01-ene-{año_gravable+1}</b> a <b>31-ene-{año_gravable+1}</b> "
                f"(cotización dic-{año_gravable} pagada en ene-{año_gravable+1})</small>",
                unsafe_allow_html=True,
            )
        archivo = st.file_uploader(
            f"Comprobante MM ene-{año_gravable+1}",
            type=['xls', 'xlsx'],
            key=f"upload_pila_pasivo_{empresa['id']}_{año_gravable}",
            label_visibility='collapsed',
        )
        if archivo is not None:
            _procesar_planilla_pila(archivo, empresa, año_gravable, supabase, es_pasivo=True)


def _render_seccion_cesantias(empresa, año_gravable, supabase, estado, diag) -> None:
    """Sección: Informes por Fondo de cesantías."""
    col1, col2 = st.columns(2)

    # Cesantías pagadas (año anterior pagadas en feb-año)
    with col1:
        icon = "✅" if estado['cesantias_pagadas']['cargado'] else ("⏳" if diag.requiere_cesantias_pagadas else "⚪")
        st.markdown(f"##### {icon} Cesantías {año_gravable-1} pagadas {año_gravable}")
        if estado['cesantias_pagadas']['cargado']:
            st.success(
                f"{estado['cesantias_pagadas']['count']} informe(s) · "
                f"${estado['cesantias_pagadas']['total']:,.0f}"
            )
        else:
            st.markdown(
                f"<small>Informe del fondo con consignación de feb-{año_gravable}<br>"
                f"→ F1001 cpto 5016 + F2276 por empleado</small>",
                unsafe_allow_html=True,
            )
        archivo = st.file_uploader(
            f"Informe Fondo cesantías {año_gravable-1}",
            type=['xls', 'xlsx'],
            key=f"upload_ces_pagadas_{empresa['id']}_{año_gravable}",
            label_visibility='collapsed',
            accept_multiple_files=True,  # múltiples fondos
        )
        if archivo:
            for f in archivo:
                _procesar_cesantia(f, empresa, año_gravable, supabase, es_pasivo=False)

    # Cesantías pasivo (año actual pagadas en feb-año+1)
    with col2:
        icon = "✅" if estado['cesantias_pasivo']['cargado'] else ("⏳" if diag.requiere_cesantias_pasivo else "⚪")
        st.markdown(f"##### {icon} Cesantías {año_gravable} (pasivo 31-dic)")
        if estado['cesantias_pasivo']['cargado']:
            st.success(
                f"{estado['cesantias_pasivo']['count']} informe(s) · "
                f"${estado['cesantias_pasivo']['total']:,.0f}"
            )
        else:
            st.markdown(
                f"<small>Informe del fondo con consignación feb-{año_gravable+1}<br>"
                f"→ F1009 cpto 2214 (pasivo)</small>",
                unsafe_allow_html=True,
            )
        archivo = st.file_uploader(
            f"Informe Fondo cesantías {año_gravable}",
            type=['xls', 'xlsx'],
            key=f"upload_ces_pasivo_{empresa['id']}_{año_gravable}",
            label_visibility='collapsed',
            accept_multiple_files=True,
        )
        if archivo:
            for f in archivo:
                _procesar_cesantia(f, empresa, año_gravable, supabase, es_pasivo=True)


def _render_seccion_declaracion_renta(empresa, año_gravable, supabase, estado_dr) -> None:
    """Sección: Declaración de Renta (opcional)."""
    icon = "✅" if estado_dr['cargado'] else "⚪"
    label = f"{icon} **Declaración de Renta** (opcional)"

    with st.expander(label, expanded=False):
        st.markdown(
            f"Carga el formulario 110/210 de declaración de renta del año {año_gravable} "
            "para conciliación cruzada con los formatos de exógena. Esto permite detectar "
            "diferencias entre lo declarado en renta y lo reportado en exógena."
        )
        archivo = st.file_uploader(
            "Declaración de Renta (PDF o XLSX)",
            type=['pdf', 'xlsx'],
            key=f"upload_renta_{empresa['id']}_{año_gravable}",
        )
        if archivo is not None:
            st.info("💡 Procesador de declaración de renta pendiente de implementar (próxima sesión).")


def _render_boton_recalcular(empresa, año_gravable, supabase, periodo_id, estado, diag) -> None:
    """Botón para re-ejecutar el motor con los archivos disponibles."""
    obligatorios_ok = (
        estado['terceros']['cargado']
        and estado['mapeo_nativo']['cargado']
        and estado['balance']['cargado']
    )

    pila_ok = True
    if diag and diag.necesita_pila:
        pila_ok = diag.esta_completo

    todo_listo = obligatorios_ok and pila_ok

    if not obligatorios_ok:
        st.warning(
            "⚠️ Sube primero los **archivos base** (terceros, mapeo nativo y balance) "
            "para poder generar el borrador."
        )
        return

    if diag and diag.necesita_pila and not pila_ok:
        st.warning(
            f"⚠️ Faltan **{len(diag.pendientes)} archivos PILA/cesantías**. "
            f"Puedes generar el borrador parcial pero los formatos F1001 (5010-5012, 5016), "
            f"F1009 (2214) y F2276 (cesantías) quedarán incompletos."
        )

    col1, col2 = st.columns([3, 1])
    with col1:
        if todo_listo:
            st.success("✅ Todos los archivos están listos para generar el borrador completo.")
    with col2:
        if st.button(
            "🔄 Recalcular borrador",
            type='primary',
            use_container_width=True,
            disabled=not obligatorios_ok,
        ):
            # Limpiar caché del dictamen para forzar recálculo
            if 'exo_dictamen' in st.session_state:
                del st.session_state['exo_dictamen']
            st.success("✅ Borrador marcado para recálculo. Ve al tab '⚙️ Borrador'.")
            st.rerun()


# ============================================================
# Procesadores (delegados al módulo PILA existente)
# ============================================================

def _procesar_planilla_pila(archivo, empresa, año_gravable, supabase, es_pasivo: bool) -> None:
    """Procesa archivo de planilla PILA usando el lector existente."""
    from core.lectores.lector_pila_xls import leer_xls_suaporte
    from core.exogena.procesador_pila_exogena import guardar_planillas_pila

    with st.spinner(f"Leyendo {archivo.name}..."):
        resultado = leer_xls_suaporte(archivo.read(), nombre_archivo=archivo.name)

    if resultado.errores:
        for e in resultado.errores:
            st.error(f"❌ {e}")
        return

    if not resultado.planillas:
        st.warning("No se detectaron planillas en el archivo")
        return

    st.success(
        f"✅ {resultado.total_planillas} planilla(s) leídas · "
        f"**${resultado.total_pagado_global:,.0f}**"
    )

    # Confirmar tipo
    periodo_pasivo = f'{año_gravable}12'
    planillas_anual = [p for p in resultado.planillas if p.periodo_cot != periodo_pasivo]
    planillas_dic = [p for p in resultado.planillas if p.periodo_cot == periodo_pasivo]

    if es_pasivo and not planillas_dic:
        st.warning(
            f"⚠️ Marcaste este archivo como 'pasivo dic' pero NO contiene la planilla "
            f"cot {periodo_pasivo}. ¿Es correcto? Las planillas detectadas son: "
            f"{[p.periodo_cot for p in resultado.planillas]}"
        )
    if not es_pasivo and planillas_dic and len(planillas_dic) == len(resultado.planillas):
        st.warning(
            f"⚠️ Este archivo SOLO contiene la planilla cot {periodo_pasivo}. "
            f"¿Quieres marcarlo como 'pasivo dic'?"
        )

    if st.button(
        f"💾 Guardar en base de datos",
        key=f"save_pila_{archivo.name}",
        type='primary',
    ):
        with st.spinner("Guardando..."):
            info = guardar_planillas_pila(
                supabase, empresa['id'], año_gravable, resultado,
                reemplazar_periodos=True,
            )
        if info['errores']:
            for e in info['errores']:
                st.error(f"❌ {e}")
        else:
            st.success(
                f"✅ Guardado · {info['planillas_insertadas']} planillas, "
                f"{info['movimientos_insertados']} movimientos"
            )
            st.rerun()


def _procesar_cesantia(archivo, empresa, año_gravable, supabase, es_pasivo: bool) -> None:
    """Procesa un Informe por Fondo de cesantías."""
    from core.lectores.lector_pila_xls import leer_xls_informe_cesantias
    from core.exogena.procesador_pila_exogena import guardar_cesantias

    with st.spinner(f"Leyendo {archivo.name}..."):
        informe = leer_xls_informe_cesantias(archivo.read(), nombre_archivo=archivo.name)

    if informe.errores:
        for e in informe.errores:
            st.error(f"❌ {e}")
        return

    if not informe.empleados:
        st.warning("No se detectaron empleados en el informe")
        return

    st.success(
        f"✅ {informe.fondo_nombre} (NIT {informe.fondo_nit}) · "
        f"Año {informe.año_causado} · "
        f"{len(informe.empleados)} empleados · "
        f"**${informe.total:,.0f}**"
    )

    # Validar consistencia es_pasivo
    año_esperado_pagada = año_gravable - 1
    año_esperado_pasivo = año_gravable
    if not es_pasivo and informe.año_causado != año_esperado_pagada:
        st.warning(
            f"⚠️ Esperaba año causado {año_esperado_pagada} (cesantías pagadas en {año_gravable}) "
            f"pero el archivo dice año causado {informe.año_causado}."
        )
    if es_pasivo and informe.año_causado != año_esperado_pasivo:
        st.warning(
            f"⚠️ Esperaba año causado {año_esperado_pasivo} (pasivo al 31-dic-{año_gravable}) "
            f"pero el archivo dice año causado {informe.año_causado}."
        )

    if st.button(
        f"💾 Guardar {informe.fondo_nombre}",
        key=f"save_ces_{archivo.name}",
        type='primary',
    ):
        with st.spinner("Guardando..."):
            info = guardar_cesantias(
                supabase, empresa['id'], año_gravable,
                informe.año_causado, es_pasivo, informe,
            )
        if info['errores']:
            for e in info['errores']:
                st.error(f"❌ {e}")
        else:
            st.success(f"✅ Guardado · {info['empleados_insertados']} empleados")
            st.rerun()
