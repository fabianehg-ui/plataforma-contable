"""
1_RADIAN_Acuses_Recibidos.py
=============================
Página Streamlit para filtrar y reportar documentos electrónicos del
catálogo VPFE de la DIAN.

UBICACIÓN: app_pages/1_RADIAN_Acuses_Recibidos.py
  → Aparece como PRIMERA opción dentro de "Tributarios"

FLUJO:
  1. El usuario descarga el reporte Excel del catálogo VPFE de la DIAN
     (https://catalogo-vpfe.dian.gov.co) usando su token
  2. Sube el Excel a esta pantalla
  3. Aplica filtros (forma de pago, grupo, fechas, NIT)
  4. Visualiza métricas y detalle
  5. Descarga reporte limpio en Excel
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date

# Import del procesador
try:
    from core.radian.procesador_acuses import (
        cargar_excel_radian,
        resumir_acuses,
        filtrar,
        resumir_por_proveedor,
        resumir_por_cliente,
        exportar_a_excel,
        FORMA_PAGO_LABEL,
        TIPO_APPLICATION_RESPONSE,
    )
except ImportError:
    # Fallback para entorno standalone
    from procesador_acuses import (
        cargar_excel_radian,
        resumir_acuses,
        filtrar,
        resumir_por_proveedor,
        resumir_por_cliente,
        exportar_a_excel,
        FORMA_PAGO_LABEL,
        TIPO_APPLICATION_RESPONSE,
    )


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

st.set_page_config(
    page_title='RADIAN — Acuses Recibidos',
    page_icon='📑',
    layout='wide',
)


# =============================================================================
# HEADER
# =============================================================================

st.title('📑 Reporte Catálogo VPFE')
st.caption(
    'Filtra y exporta documentos del catálogo VPFE de la DIAN. '
    'Útil para identificar facturas a crédito recibidas y cruzar contra F1009/CxP. '
    '*(Nota: NO emite eventos RADIAN reales. Para envío de eventos 030/032/033 '
    'usar el módulo de RADIAN Eventos cuando esté disponible.)*'
)

with st.expander('ℹ️ ¿Cómo descargar el reporte del catálogo VPFE?'):
    st.markdown("""
    1. Ingresa al [catálogo VPFE de la DIAN](https://catalogo-vpfe.dian.gov.co/) con tu token.
    2. En el menú lateral, ir a **Reportes → Documentos electrónicos**.
    3. Selecciona el rango de fechas deseado.
    4. Clic en **Exportar a Excel**.
    5. El archivo se descarga con un nombre tipo `Rp_Doc_YYYYMMDD_HHMM.xlsx`.
    6. Súbelo en la sección de abajo. ⬇️
    
    **Códigos de Forma de Pago (DIAN):**
    - `1` = Contado
    - `2` = Crédito ← *facturas que se contabilizan en CxP*
    
    **Grupos:**
    - `Emitido` = facturas que TÚ emitiste (ventas → F1007/F1008)
    - `Recibido` = facturas que TÚ recibiste (compras → F1001/F1009)
    """)

st.divider()


# =============================================================================
# UPLOADER
# =============================================================================

st.subheader('📥 1. Cargar reporte DIAN')

archivo = st.file_uploader(
    'Sube el Excel exportado del catálogo VPFE',
    type=['xlsx', 'xls'],
    help='Archivo descargado desde catalogo-vpfe.dian.gov.co',
)

if not archivo:
    st.info('👆 Sube el Excel del catálogo VPFE para empezar.')
    st.stop()


# Cargar y validar
try:
    with st.spinner('Cargando archivo...'):
        df = cargar_excel_radian(archivo)
except ValueError as e:
    st.error(f'❌ {e}')
    st.stop()
except Exception as e:
    st.error(f'❌ Error inesperado al leer el archivo: {e}')
    st.stop()


# =============================================================================
# RESUMEN GENERAL
# =============================================================================

resumen = resumir_acuses(df)

st.success(f'✅ Archivo cargado correctamente: **{resumen.total_documentos:,} documentos**')

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric('📄 Documentos totales', f'{resumen.total_documentos:,}')
    st.metric('🔄 Application Response', f'{resumen.total_application_response:,}',
              help='Acuses automáticos, no son facturas reales')
with col2:
    st.metric('📤 Emitidos', f'{resumen.total_emitidos:,}')
    st.metric('📥 Recibidos', f'{resumen.total_recibidos:,}')
with col3:
    st.metric('💰 Contado (FP=1)', f'{resumen.total_contado:,}')
    st.metric('💳 Crédito (FP=2)', f'{resumen.total_credito:,}')
with col4:
    st.metric('🏢 Proveedores únicos', f'{resumen.proveedores_unicos:,}')
    st.metric('👥 Clientes únicos', f'{resumen.clientes_unicos:,}')

if resumen.fecha_min and resumen.fecha_max:
    st.caption(f'📅 Período: del **{resumen.fecha_min}** al **{resumen.fecha_max}**')

st.divider()


# =============================================================================
# FILTROS
# =============================================================================

st.subheader('🎚️ 2. Filtros')

col_a, col_b, col_c = st.columns(3)

with col_a:
    grupo = st.selectbox(
        'Grupo',
        options=['Recibido', 'Emitido', '(todos)'],
        index=0,
        help='Recibido = compras (F1009). Emitido = ventas (F1007/F1008).',
    )
    grupo_filtro = grupo if grupo != '(todos)' else None

with col_b:
    forma_pago_opt = st.selectbox(
        'Forma de Pago',
        options=[
            ('2 - Crédito', 2),
            ('1 - Contado', 1),
            ('(todos)', None),
        ],
        format_func=lambda x: x[0],
        index=0,
    )
    forma_pago_filtro = forma_pago_opt[1]

with col_c:
    estados_validos = st.checkbox(
        'Solo aprobados',
        value=True,
        help='Excluye documentos rechazados o en proceso',
    )

# Filtros avanzados (colapsable)
with st.expander('🔍 Filtros avanzados'):
    col_d, col_e, col_f = st.columns(3)
    
    with col_d:
        fecha_desde = st.date_input(
            'Desde (Fecha emisión)',
            value=None,
            format='DD/MM/YYYY',
        )
    with col_e:
        fecha_hasta = st.date_input(
            'Hasta (Fecha emisión)',
            value=None,
            format='DD/MM/YYYY',
        )
    with col_f:
        nit_busqueda = st.text_input(
            'NIT contraparte',
            placeholder='Ej: 900533491',
            help='Filtra por NIT del proveedor (si grupo=Recibido) o cliente (si Emitido)',
        )


# =============================================================================
# APLICAR FILTROS
# =============================================================================

with st.spinner('Aplicando filtros...'):
    resultado = filtrar(
        df,
        forma_pago=forma_pago_filtro,
        grupo=grupo_filtro,
        excluir_application_response=True,
        fecha_desde=fecha_desde.isoformat() if fecha_desde else None,
        fecha_hasta=fecha_hasta.isoformat() if fecha_hasta else None,
        nit_contraparte=nit_busqueda if nit_busqueda else None,
        solo_aprobados=estados_validos,
    )

st.divider()


# =============================================================================
# RESULTADO FILTRADO
# =============================================================================

st.subheader('📊 3. Resultado filtrado')

if resultado.advertencias:
    for adv in resultado.advertencias:
        st.warning(f'⚠ {adv}')

col_m1, col_m2, col_m3 = st.columns(3)
with col_m1:
    st.metric('Documentos filtrados', f'{resultado.filas_filtradas:,}',
              delta=f'-{resultado.filas_originales - resultado.filas_filtradas:,}',
              delta_color='off')
with col_m2:
    st.metric('Valor total', f'${resultado.total_valor:,.0f}')
with col_m3:
    if resultado.filas_filtradas > 0:
        promedio = resultado.total_valor / resultado.filas_filtradas
        st.metric('Valor promedio', f'${promedio:,.0f}')

# Tabla de filtros aplicados
with st.expander('📋 Filtros aplicados', expanded=False):
    for k, v in resultado.filtros_aplicados.items():
        st.write(f'• **{k}**: {v}')


# =============================================================================
# TABS DE RESULTADOS
# =============================================================================

if resultado.filas_filtradas > 0:
    tab1, tab2, tab3 = st.tabs(['📋 Detalle', '🏢 Por contraparte', '📥 Descargar'])
    
    # ---- TAB 1: DETALLE ----
    with tab1:
        st.caption(f'Mostrando {min(500, resultado.filas_filtradas):,} de {resultado.filas_filtradas:,} documentos')
        
        # Columnas más útiles primero
        cols_principales = [
            'Tipo de documento', 'Folio', 'Prefijo', 'Fecha Emisión',
            'NIT Emisor', 'Nombre Emisor', 'NIT Receptor', 'Nombre Receptor',
            'Forma de Pago', 'Total', 'IVA', 'Rete IVA', 'Rete Renta', 'Estado',
        ]
        cols_mostrar = [c for c in cols_principales if c in resultado.df.columns]
        
        st.dataframe(
            resultado.df[cols_mostrar].head(500),
            use_container_width=True,
            hide_index=True,
            column_config={
                'Total': st.column_config.NumberColumn('Total', format='$%d'),
                'IVA': st.column_config.NumberColumn('IVA', format='$%d'),
                'Rete IVA': st.column_config.NumberColumn('Rete IVA', format='$%d'),
                'Rete Renta': st.column_config.NumberColumn('Rete Renta', format='$%d'),
            },
        )
    
    # ---- TAB 2: POR CONTRAPARTE ----
    with tab2:
        if grupo_filtro == 'Recibido':
            df_resumen = resumir_por_proveedor(resultado.df)
            st.caption('📥 Resumen por proveedor (compras)')
        elif grupo_filtro == 'Emitido':
            df_resumen = resumir_por_cliente(resultado.df)
            st.caption('📤 Resumen por cliente (ventas)')
        else:
            df_resumen = pd.DataFrame()
            st.info('Selecciona un grupo (Recibido o Emitido) para ver el resumen.')
        
        if not df_resumen.empty:
            col_top, col_bottom = st.columns(2)
            with col_top:
                st.metric('Contrapartes únicas', f'{len(df_resumen):,}')
            with col_bottom:
                # Top 1 contraparte
                top1 = df_resumen.iloc[0]
                nombre_col = 'Nombre Emisor' if 'Nombre Emisor' in df_resumen.columns else 'Nombre Receptor'
                st.metric(
                    'Top contraparte',
                    f'${top1["total_general"]:,.0f}',
                    delta=top1[nombre_col][:30],
                    delta_color='off',
                )
            
            st.dataframe(
                df_resumen,
                use_container_width=True,
                hide_index=True,
                column_config={
                    'total_iva': st.column_config.NumberColumn('Total IVA', format='$%d'),
                    'total_rete_iva': st.column_config.NumberColumn('Rete IVA', format='$%d'),
                    'total_rete_renta': st.column_config.NumberColumn('Rete Renta', format='$%d'),
                    'total_rete_ica': st.column_config.NumberColumn('Rete ICA', format='$%d'),
                    'total_general': st.column_config.NumberColumn('Total general', format='$%d'),
                },
            )
    
    # ---- TAB 3: DESCARGAR ----
    with tab3:
        st.markdown('**📥 Descargar reporte Excel**')
        st.caption(
            'El Excel incluye: hoja Resumen con filtros y métricas, '
            'hoja Detalle con todos los documentos filtrados, y hoja Por Proveedor/Cliente.'
        )
        
        col_btn1, col_btn2 = st.columns([1, 3])
        
        with col_btn1:
            # Nombre de empresa (puede venir de session_state si está disponible)
            empresa = st.session_state.get('empresa_seleccionada', {}).get('razon_social', '')
            
            if st.button('🔨 Generar Excel', type='primary', use_container_width=True):
                with st.spinner('Generando Excel...'):
                    bytes_excel = exportar_a_excel(
                        resultado,
                        incluir_resumen=True,
                        nombre_empresa=empresa,
                    )
                    st.session_state['_radian_excel_bytes'] = bytes_excel
                    st.session_state['_radian_excel_ts'] = datetime.now()
        
        with col_btn2:
            if '_radian_excel_bytes' in st.session_state:
                ts = st.session_state.get('_radian_excel_ts', datetime.now())
                grupo_label = grupo_filtro or 'todos'
                fp_label = FORMA_PAGO_LABEL.get(forma_pago_filtro, 'todos')
                nombre_archivo = (
                    f'RADIAN_{grupo_label}_{fp_label}_'
                    f'{ts.strftime("%Y%m%d_%H%M")}.xlsx'
                )
                st.download_button(
                    label=f'⬇️ Descargar {nombre_archivo}',
                    data=st.session_state['_radian_excel_bytes'],
                    file_name=nombre_archivo,
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    use_container_width=True,
                )
                st.caption(f'Generado: {ts.strftime("%d/%m/%Y %H:%M:%S")}')


# =============================================================================
# FOOTER
# =============================================================================

st.divider()
with st.expander('🔗 Próximos pasos sugeridos'):
    st.markdown("""
    - **Cruzar con F1009**: una vez tengas el reporte de facturas a crédito recibidas, 
      compáralo con el F1009 (CxP) para detectar:
      - Facturas en RADIAN que NO se contabilizaron como CxP
      - CxP sin factura electrónica respaldo
      - Diferencias de valor por proveedor
    
    - **Cruzar con F1001**: las facturas a crédito eventualmente se pagan → deberían
      aparecer en el F1001 como pagos al proveedor cuando se liquiden.
    
    - **Validar fechas**: si el período de RADIAN no coincide con el del balance,
      hay facturas que no se reportarán en este AG.
    """)
