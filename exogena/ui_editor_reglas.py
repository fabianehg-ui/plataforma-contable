"""
Editor de Reglas — UI Streamlit
================================

Función pública: render_editor(sb, empresa_id, usuario, año_gravable=2025)

Se inyecta dentro del tab "Mapeo nativo" de pages/7_Informacion_Exogena.py.
Diseñada para ser autocontenida — todo el estado vive en st.session_state
con prefijo 'er_' para no chocar con el resto del archivo.
"""

from __future__ import annotations
import streamlit as st
import pandas as pd
from typing import Optional

from core.exogena import editor_reglas as er


# ============================================================================
# Helpers de estado
# ============================================================================

def _state(key: str, default=None):
    """Wrapper sobre st.session_state con prefijo 'er_' para aislar el editor."""
    full_key = f'er_{key}'
    if full_key not in st.session_state:
        st.session_state[full_key] = default
    return st.session_state[full_key]


def _set_state(key: str, value):
    st.session_state[f'er_{key}'] = value


# ============================================================================
# Punto de entrada
# ============================================================================

def render_editor(
    sb,
    empresa_id: str,
    empresa_nombre: str,
    usuario: str,
    año_gravable: int = 2025,
):
    """
    Renderiza el Editor de Reglas completo. Esta es la función que se llama
    desde el tab Mapeo nativo del módulo de Información Exógena.
    """
    st.markdown('---')
    st.subheader('🛠️ Editor de Reglas')
    st.caption(
        'Edita reglas globales (Capa 1) o crea overrides específicos para esta empresa (Capa 3). '
        'La Capa 2 (mapeo nativo del software contable) se administra con el upload de arriba.'
    )

    # Tabs internos del editor
    sub_navegar, sub_buscar, sub_auditoria = st.tabs([
        '📂 Por formato',
        '🔍 Buscar cuenta',
        '📜 Historial',
    ])

    with sub_navegar:
        _vista_por_formato(sb, empresa_id, empresa_nombre, usuario, año_gravable)

    with sub_buscar:
        _vista_busqueda(sb, empresa_id, empresa_nombre, usuario, año_gravable)

    with sub_auditoria:
        _vista_auditoria(sb, empresa_id, año_gravable)


# ============================================================================
# Vista 1 — Navegador por formato
# ============================================================================

def _vista_por_formato(sb, empresa_id, empresa_nombre, usuario, año_gravable):
    """Selector de formato → tabla de cuentas → editor por fila."""

    # Cargar formatos disponibles
    try:
        formatos = er.listar_formatos_con_reglas(sb, año_gravable)
    except Exception as e:
        st.error(f'Error al cargar formatos: {e}')
        return

    if not formatos:
        st.warning('No hay reglas globales cargadas todavía. Carga el archivo de Codificación arriba.')
        return

    # Selector de formato
    col_f, col_emp = st.columns([2, 3])
    with col_f:
        opciones_fmt = [f"{f['formato_dian']} ({f['conteo']} reglas)" for f in formatos]
        idx_default = 0
        formato_sel = st.selectbox(
            'Formato DIAN',
            options=range(len(formatos)),
            format_func=lambda i: opciones_fmt[i],
            index=idx_default,
            key='er_formato_sel',
        )
        formato_dian = formatos[formato_sel]['formato_dian']

    with col_emp:
        st.info(f'**Empresa activa:** {empresa_nombre}', icon='🏢')

    # Cargar reglas de ese formato
    try:
        reglas = er.listar_reglas_por_formato(
            sb=sb,
            formato_dian=formato_dian,
            empresa_id=empresa_id,
            año_gravable=año_gravable,
            incluir_overrides=True,
        )
    except Exception as e:
        st.error(f'Error al cargar reglas: {e}')
        return

    if not reglas:
        st.info(f'No hay reglas para el formato {formato_dian}.')
        return

    # Filtro por concepto (si hay varios)
    conceptos_unicos = sorted({r.concepto_dian for r in reglas if r.concepto_dian})
    col_filt1, col_filt2 = st.columns([2, 3])
    with col_filt1:
        concepto_filtro = st.selectbox(
            'Filtrar por concepto',
            options=['(todos)'] + [str(c) for c in conceptos_unicos],
            key='er_concepto_filtro',
        )
    with col_filt2:
        texto_filtro = st.text_input(
            'Buscar en código o nombre',
            placeholder='Ej: 510303 o "salud"',
            key='er_texto_filtro',
        )

    # Aplicar filtros
    filtradas = reglas
    if concepto_filtro != '(todos)':
        filtradas = [r for r in filtradas if str(r.concepto_dian) == concepto_filtro]
    if texto_filtro.strip():
        t = texto_filtro.strip().lower()
        filtradas = [
            r for r in filtradas
            if t in r.codigo_cuenta.lower() or t in r.nombre_cuenta.lower()
        ]

    st.caption(f'Mostrando {len(filtradas)} de {len(reglas)} reglas')

    # Tabla de reglas
    if not filtradas:
        st.info('Ningún resultado con esos filtros.')
        return

    df = pd.DataFrame([{
        'Capa': f'C{r.capa}' + (' 🏢' if r.capa == 3 else ''),
        'Código': r.codigo_cuenta,
        'Nombre': r.nombre_cuenta,
        'Concepto': r.concepto_dian or '—',
        'Descripción': r.descripcion_concepto or '',
        'Modificado': (
            r.modificado_en.strftime('%Y-%m-%d') if hasattr(r.modificado_en, 'strftime')
            else (str(r.modificado_en)[:10] if r.modificado_en else '—')
        ),
        '_id_capa1': r.id_capa1,
        '_id_capa3': r.id_capa3,
        '_capa': r.capa,
    } for r in filtradas])

    # Tabla con selección
    seleccion = st.dataframe(
        df.drop(columns=['_id_capa1', '_id_capa3', '_capa']),
        use_container_width=True,
        hide_index=True,
        on_select='rerun',
        selection_mode='single-row',
        key='er_tabla_formato',
    )

    # Editor por fila seleccionada
    if seleccion and seleccion.get('selection', {}).get('rows'):
        idx = seleccion['selection']['rows'][0]
        regla_sel = filtradas[idx]
        _editor_de_regla(
            sb=sb,
            regla=regla_sel,
            empresa_id=empresa_id,
            empresa_nombre=empresa_nombre,
            usuario=usuario,
            año_gravable=año_gravable,
            key_prefix='fmt',
        )


# ============================================================================
# Vista 2 — Búsqueda libre por cuenta
# ============================================================================

def _vista_busqueda(sb, empresa_id, empresa_nombre, usuario, año_gravable):
    """Buscar cuenta por código o nombre → mostrar todas sus apariciones (3 capas)."""

    termino = st.text_input(
        'Buscar cuenta',
        placeholder='Código (ej: 510303 o 5103) o nombre (ej: "salud")',
        key='er_busqueda_termino',
    )

    if not termino.strip():
        st.caption('Ingresa al menos 3 caracteres para buscar.')
        return

    if len(termino.strip()) < 3:
        st.caption('Ingresa al menos 3 caracteres.')
        return

    try:
        resultados = er.buscar_cuenta(
            sb=sb,
            termino=termino,
            empresa_id=empresa_id,
            año_gravable=año_gravable,
        )
    except Exception as e:
        st.error(f'Error en búsqueda: {e}')
        return

    if not resultados:
        st.warning(f'Sin resultados para "{termino}".')
        st.markdown('¿Quieres **crear una nueva regla global** para esta cuenta?')
        if st.button('➕ Crear regla global nueva', key='er_crear_global_desde_busqueda'):
            _set_state('mostrar_form_crear', True)
            _set_state('codigo_cuenta_nuevo', termino.strip())

        if _state('mostrar_form_crear'):
            _form_crear_regla_global(sb, usuario, año_gravable)
        return

    st.caption(f'Encontradas {len(resultados)} apariciones en las 3 capas')

    # Agrupar por capa
    capas = {}
    for r in resultados:
        capas.setdefault(r.capa, []).append(r)

    # Mostrar la jerarquía aplicada
    if 3 in capas:
        st.success('🥇 Capa 3 (override) gana — esta cuenta usa la regla específica de la empresa.')
    elif 2 in capas:
        st.info('🥈 Capa 2 (mapeo nativo) gana — esta cuenta usa el rango del archivo de Codificación.')
    elif 1 in capas:
        st.info('🥉 Capa 1 (global) — esta cuenta usa la regla universal del PUC.')

    # Tabs por capa
    tab_labels = []
    if 3 in capas:
        tab_labels.append(f'🏢 Override empresa ({len(capas[3])})')
    if 2 in capas:
        tab_labels.append(f'📋 Mapeo nativo ({len(capas[2])})')
    if 1 in capas:
        tab_labels.append(f'🌐 Global ({len(capas[1])})')

    if tab_labels:
        tabs = st.tabs(tab_labels)
        idx_tab = 0
        for capa in [3, 2, 1]:
            if capa in capas:
                with tabs[idx_tab]:
                    _mostrar_reglas_de_capa(
                        sb, capas[capa], capa, empresa_id, empresa_nombre,
                        usuario, año_gravable
                    )
                idx_tab += 1


def _mostrar_reglas_de_capa(sb, reglas, capa, empresa_id, empresa_nombre, usuario, año_gravable):
    """Muestra las reglas de una capa específica con opción de editarlas."""
    df = pd.DataFrame([{
        'Código': r.codigo_cuenta,
        'Nombre': r.nombre_cuenta,
        'Formato': r.formato_dian or '(excluida)',
        'Concepto': r.concepto_dian or '—',
        'Descripción': r.descripcion_concepto or '',
        'NIT': r.nit or '—' if capa == 3 else '',
    } for r in reglas])

    if capa == 2:
        df = df.drop(columns=['NIT'])
        st.info(
            'Las reglas de Capa 2 vienen del archivo de Codificación y no se editan aquí. '
            'Para cambiarlas, crea un override en Capa 3 que las sobrescriba.',
            icon='ℹ️',
        )

    seleccion = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select='rerun' if capa != 2 else 'ignore',
        selection_mode='single-row' if capa != 2 else None,
        key=f'er_tabla_capa{capa}',
    )

    if capa == 2:
        return

    if seleccion and seleccion.get('selection', {}).get('rows'):
        idx = seleccion['selection']['rows'][0]
        _editor_de_regla(
            sb=sb,
            regla=reglas[idx],
            empresa_id=empresa_id,
            empresa_nombre=empresa_nombre,
            usuario=usuario,
            año_gravable=año_gravable,
            key_prefix=f'cap{capa}',
        )


# ============================================================================
# Editor por regla — formulario de edición
# ============================================================================

def _editor_de_regla(sb, regla, empresa_id, empresa_nombre, usuario, año_gravable, key_prefix):
    """
    Renderiza el formulario de edición para una regla seleccionada.
    Permite cambiar formato/concepto y elegir si es cambio global o override.
    """
    st.markdown('---')
    st.markdown(f'### ✏️ Editar regla: `{regla.codigo_cuenta}`')

    col1, col2 = st.columns(2)
    with col1:
        st.metric('Capa actual', regla.capa_nombre)
        st.metric('Formato actual', regla.formato_dian or '(excluida)')
    with col2:
        st.metric('Concepto actual', regla.concepto_dian or '—')
        st.caption(f'Última modificación: {regla.modificado_en or "—"}')

    if regla.descripcion_concepto:
        st.caption(f'**Descripción actual:** {regla.descripcion_concepto}')

    # Selector de destino: ¿editar regla original o crear override?
    st.markdown('#### ¿Cómo quieres aplicar el cambio?')

    if regla.capa == 1:
        opciones_destino = [
            ('global', f'🌐 Editar regla GLOBAL (afecta a TODAS las empresas)'),
            ('override', f'🏢 Crear OVERRIDE solo para {empresa_nombre}'),
        ]
    else:  # capa 3
        opciones_destino = [
            ('override', f'🏢 Editar este override de {empresa_nombre}'),
            ('eliminar_override', f'❌ Eliminar override (la cuenta vuelve a regla global)'),
        ]

    destino = st.radio(
        'Tipo de cambio',
        options=[op[0] for op in opciones_destino],
        format_func=lambda x: dict(opciones_destino)[x],
        key=f'er_destino_{key_prefix}',
    )

    if destino == 'eliminar_override':
        st.warning(f'Vas a eliminar el override. La cuenta {regla.codigo_cuenta} '
                   f'volverá a regirse por la regla global o de mapeo nativo.')
        motivo = st.text_input('Motivo (opcional)', key=f'er_motivo_del_{key_prefix}')
        if st.button('🗑️ Confirmar eliminación', type='primary', key=f'er_btn_del_{key_prefix}'):
            res = er.eliminar_override(sb, regla.id_capa3, usuario, motivo)
            if res.ok:
                st.success(res.mensaje)
                st.rerun()
            else:
                st.error(res.mensaje)
        return

    # Formulario de edición
    formatos_disponibles = ['1001', '1003', '1005', '1006', '1007', '1008', '1009',
                            '1011', '1012', '2276']
    formato_actual_idx = (
        formatos_disponibles.index(regla.formato_dian)
        if regla.formato_dian in formatos_disponibles else 0
    )

    col_a, col_b = st.columns(2)
    with col_a:
        formato_nuevo = st.selectbox(
            'Formato nuevo',
            options=formatos_disponibles,
            index=formato_actual_idx,
            key=f'er_fmt_nuevo_{key_prefix}',
        )

    # Cargar conceptos del formato seleccionado
    try:
        conceptos = er.listar_conceptos_de_formato(sb, formato_nuevo, año_gravable)
    except Exception as e:
        st.error(f'Error al cargar conceptos del formato {formato_nuevo}: {e}')
        return

    if not conceptos:
        st.warning(f'No hay conceptos en el catálogo para el formato {formato_nuevo}.')
        return

    with col_b:
        concepto_nuevo_idx = next(
            (i for i, c in enumerate(conceptos) if c['concepto_dian'] == regla.concepto_dian),
            0,
        )
        concepto_nuevo = st.selectbox(
            'Concepto nuevo',
            options=range(len(conceptos)),
            format_func=lambda i: f"{conceptos[i]['concepto_dian']} - {conceptos[i]['descripcion'][:60]}",
            index=concepto_nuevo_idx,
            key=f'er_con_nuevo_{key_prefix}',
        )

    concepto_dian_nuevo = conceptos[concepto_nuevo]['concepto_dian']
    descripcion_nueva = conceptos[concepto_nuevo]['descripcion']

    motivo = st.text_input(
        'Motivo del cambio (queda en el log de auditoría)',
        key=f'er_motivo_{key_prefix}',
        placeholder='Ej: "Reclasificación solicitada por contador" o "Corrección regla mal codificada"',
    )

    # Botón guardar
    if st.button('💾 Guardar cambio', type='primary', key=f'er_btn_save_{key_prefix}'):
        if destino == 'global':
            res = er.editar_regla_global(
                sb=sb,
                id_capa1=regla.id_capa1,
                formato_nuevo=formato_nuevo,
                concepto_nuevo=concepto_dian_nuevo,
                descripcion_nueva=descripcion_nueva,
                usuario=usuario,
                motivo=motivo,
                año_gravable=año_gravable,
            )
        else:  # override
            res = er.crear_o_actualizar_override(
                sb=sb,
                empresa_id=empresa_id,
                codigo_cuenta=regla.codigo_cuenta,
                nombre_cuenta=regla.nombre_cuenta,
                formato_dian=formato_nuevo,
                concepto_dian=concepto_dian_nuevo,
                descripcion_concepto=descripcion_nueva,
                usuario=usuario,
                motivo=motivo,
                año_gravable=año_gravable,
            )

        if res.ok:
            st.success(res.mensaje)
            st.rerun()
        else:
            st.error(res.mensaje)


# ============================================================================
# Crear regla global desde cero
# ============================================================================

def _form_crear_regla_global(sb, usuario, año_gravable):
    """Formulario para crear una regla global nueva (cuenta no-PUC)."""
    st.markdown('### ➕ Nueva regla global')

    with st.form('er_form_crear_global', clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            codigo = st.text_input(
                'Código de cuenta',
                value=_state('codigo_cuenta_nuevo', ''),
            )
            nombre = st.text_input('Nombre de la cuenta')
            naturaleza = st.selectbox('Naturaleza', ['Débito', 'Crédito'])

        with col2:
            formatos = ['1001', '1003', '1005', '1006', '1007', '1008', '1009',
                        '1011', '1012', '2276']
            formato = st.selectbox('Formato DIAN', formatos)
            try:
                conceptos = er.listar_conceptos_de_formato(sb, formato, año_gravable)
            except Exception as e:
                conceptos = []
                st.error(f'Error al cargar conceptos: {e}')

            if conceptos:
                concepto_idx = st.selectbox(
                    'Concepto',
                    options=range(len(conceptos)),
                    format_func=lambda i: f"{conceptos[i]['concepto_dian']} - {conceptos[i]['descripcion'][:50]}",
                )
            else:
                concepto_idx = None

        nota = st.text_area('Nota (opcional)', placeholder='Razón por la que esta cuenta no estándar va a este formato')
        motivo = st.text_input('Motivo (queda en log)', placeholder='Ej: Empresa con plan de cuentas no-PUC')

        submitted = st.form_submit_button('➕ Crear regla global', type='primary')

        if submitted:
            if not codigo or not nombre or concepto_idx is None:
                st.error('Faltan campos obligatorios.')
                return

            res = er.crear_regla_global(
                sb=sb,
                codigo_cuenta=codigo.strip(),
                nombre_cuenta=nombre.strip(),
                formato_dian=formato,
                concepto_dian=conceptos[concepto_idx]['concepto_dian'],
                descripcion_concepto=conceptos[concepto_idx]['descripcion'],
                naturaleza=naturaleza,
                usuario=usuario,
                motivo=motivo,
                nota=nota or None,
                año_gravable=año_gravable,
            )

            if res.ok:
                st.success(res.mensaje)
                _set_state('mostrar_form_crear', False)
                st.rerun()
            else:
                st.error(res.mensaje)


# ============================================================================
# Vista 3 — Auditoría / log
# ============================================================================

def _vista_auditoria(sb, empresa_id, año_gravable):
    """Tabla con los últimos cambios hechos a las reglas."""
    st.caption('Histórico de cambios hechos desde el editor (últimos 50)')

    try:
        log = er.listar_log_reciente(sb, limit=50, empresa_id=empresa_id)
    except Exception as e:
        st.error(f'Error al cargar log: {e}')
        return

    if not log:
        st.info('Sin cambios registrados aún.')
        return

    df = pd.DataFrame([{
        'Fecha': str(r.get('fecha', ''))[:19].replace('T', ' '),
        'Usuario': r.get('usuario', ''),
        'Capa': f"C{r['capa']}",
        'Acción': r.get('accion', ''),
        'Cuenta': r.get('codigo_cuenta', ''),
        'Antes': f"{r.get('formato_anterior') or '—'}/{r.get('concepto_anterior') or '—'}",
        'Después': f"{r.get('formato_nuevo') or '—'}/{r.get('concepto_nuevo') or '—'}",
        'Motivo': r.get('motivo') or '',
    } for r in log])

    st.dataframe(df, use_container_width=True, hide_index=True)
