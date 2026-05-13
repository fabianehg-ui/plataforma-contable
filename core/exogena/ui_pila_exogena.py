"""
UI del tab PILA en el módulo de Información Exógena.

Función principal: render_tab_pila(empresa, año_gravable, supabase)
  - Sub-tab 1: Cargar planilla SuAporte (.xls)
  - Sub-tab 2: Cargar Informe por Fondo de cesantías
  - Sub-tab 3: Resumen y vista previa de líneas DIAN
  - Sub-tab 4: Conciliación contra balance contable
"""
from __future__ import annotations
from decimal import Decimal

import pandas as pd
import streamlit as st

from core.lectores.lector_pila_xls import (
    leer_xls_suaporte,
    leer_xls_informe_cesantias,
)
from core.exogena.procesador_pila_exogena import (
    guardar_planillas_pila,
    guardar_cesantias,
    obtener_planillas_pila,
    obtener_cesantias,
    construir_resumen_pila,
    CONCEPTOS_F1001_PILA,
    CONCEPTOS_F1009_PILA,
)


def render_tab_pila(empresa: dict, año_gravable: int, supabase) -> None:
    """Renderiza el contenido del tab PILA dentro de Información Exógena."""

    st.markdown("### 🏥 PILA — Planilla Integrada de Liquidación de Aportes")
    st.caption(
        "Carga los reportes oficiales del operador (SuAporte/Ceiba Software, "
        "Aportes en Línea, etc.) y los Informes por Fondo de cesantías. "
        "Los datos alimentarán automáticamente los conceptos **5010, 5011, 5012, 5016** "
        "del F1001, **2214, 2204** del F1009 y la columna de cesantías del F2276."
    )

    sub_carga, sub_cesantias, sub_resumen, sub_conciliar = st.tabs([
        "📥 Cargar planillas",
        "💰 Cargar cesantías",
        "📊 Resumen",
        "🔍 Conciliación",
    ])

    with sub_carga:
        _render_subtab_cargar_planillas(empresa, año_gravable, supabase)

    with sub_cesantias:
        _render_subtab_cargar_cesantias(empresa, año_gravable, supabase)

    with sub_resumen:
        _render_subtab_resumen(empresa, año_gravable, supabase)

    with sub_conciliar:
        _render_subtab_conciliacion(empresa, año_gravable, supabase)


# ============================================================
# Sub-tab 1: Cargar planillas SuAporte
# ============================================================

def _render_subtab_cargar_planillas(empresa: dict, año_gravable: int, supabase) -> None:
    st.markdown("#### Cargar Comprobante de Medios Magnéticos (SuAporte)")
    st.markdown(
        "Descarga el archivo desde el portal SuAporte para todo el año gravable "
        f"**{año_gravable}** (o por mes individual). El archivo debe ser **.xls** "
        "y contener las hojas *Seguridad Social* y *Parafiscales*."
    )
    st.info(
        "💡 **Recomendación:** descarga el comprobante con rango 01-01 al 31-12 "
        f"del año gravable {año_gravable} (cubre las planillas pagadas durante el año) "
        f"y un segundo archivo del 01-01 al 31-01 del año {año_gravable + 1} "
        f"(planilla del pasivo cot {año_gravable}-12 que va al F1009 concepto 2214)."
    )

    archivo = st.file_uploader(
        f"Archivo .xls del Comprobante SuAporte",
        type=['xls'],
        key=f"pila_uploader_{año_gravable}_{empresa['id']}",
    )

    if archivo is None:
        # Mostrar planillas ya cargadas
        _mostrar_planillas_existentes(empresa, año_gravable, supabase)
        return

    with st.spinner("Leyendo archivo..."):
        resultado = leer_xls_suaporte(archivo.read(), nombre_archivo=archivo.name)

    if resultado.errores:
        st.error("Errores al leer el archivo:")
        for e in resultado.errores:
            st.error(f"  • {e}")
        return

    if not resultado.planillas:
        st.warning("No se detectaron planillas válidas en el archivo")
        return

    # Mostrar preview
    st.success(
        f"✅ {resultado.total_planillas} planilla(s) detectada(s) · "
        f"Total: **${resultado.total_pagado_global:,.0f}**"
    )

    if resultado.advertencias:
        with st.expander(f"⚠️ {len(resultado.advertencias)} advertencias"):
            for a in resultado.advertencias[:20]:
                st.warning(a)

    # Tabla resumen
    filas_resumen = []
    for p in resultado.planillas:
        filas_resumen.append({
            'Planilla': p.numero_planilla,
            'Fecha pago': p.fecha_pago,
            'Cot.': p.periodo_cot,
            'Tipo': p.tipo_planilla,
            'Afil.': p.afiliados,
            'Movs.': len(p.movimientos),
            'Total': f"${p.total_pagado:,.0f}",
        })
    st.dataframe(pd.DataFrame(filas_resumen), use_container_width=True, hide_index=True)

    # Detalle de movimientos
    with st.expander(f"Ver detalle por fondo ({sum(len(p.movimientos) for p in resultado.planillas)} movimientos)"):
        filas_mov = []
        for p in resultado.planillas:
            for m in p.movimientos:
                filas_mov.append({
                    'Planilla': p.numero_planilla,
                    'Periodo': p.periodo_cot,
                    'Tipo fondo': m.fondo_tipo,
                    'Concepto F1001': m.concepto_dian,
                    'NIT': m.fondo_nit,
                    'Administradora': m.fondo_nombre,
                    'Total': f"${m.total_obligatorio:,.0f}",
                })
        st.dataframe(pd.DataFrame(filas_mov), use_container_width=True, hide_index=True)

    # Botón guardar
    st.markdown("---")
    if st.button("💾 Guardar en base de datos", type='primary', use_container_width=True):
        with st.spinner("Guardando..."):
            info = guardar_planillas_pila(
                supabase, empresa['id'], año_gravable, resultado,
                reemplazar_periodos=True,
            )
        if info['errores']:
            st.error("Errores al guardar:")
            for e in info['errores']:
                st.error(f"  • {e}")
        else:
            st.success(
                f"✅ Guardado: {info['planillas_insertadas']} planillas, "
                f"{info['movimientos_insertados']} movimientos"
            )
            if info['periodos_reemplazados']:
                st.caption(
                    f"♻️ Se reemplazaron {len(info['periodos_reemplazados'])} planillas previas"
                )
            st.rerun()


def _mostrar_planillas_existentes(empresa: dict, año_gravable: int, supabase) -> None:
    """Muestra las planillas ya cargadas en base de datos."""
    planillas = obtener_planillas_pila(supabase, empresa['id'], año_gravable)
    if not planillas:
        st.info("No hay planillas cargadas todavía.")
        return

    st.markdown(f"##### Planillas ya cargadas ({len(planillas)})")
    filas = []
    for p in planillas:
        filas.append({
            'Planilla': p['numero_planilla'],
            'Fecha pago': p['fecha_pago'],
            'Periodo cot.': p['periodo_cot'],
            'Tipo': p.get('tipo_planilla', ''),
            'Afil.': p.get('afiliados', 0),
            'Total': f"${float(p.get('total_pagado') or 0):,.0f}",
            'Archivo': p.get('archivo_origen', ''),
        })
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)


# ============================================================
# Sub-tab 2: Cargar cesantías
# ============================================================

def _render_subtab_cargar_cesantias(empresa: dict, año_gravable: int, supabase) -> None:
    st.markdown("#### Cargar Informe por Fondo de Cesantías")
    st.markdown(
        "Carga el archivo del fondo (Protección, Porvenir, Colfondos, Skandia, Old Mutual) "
        "que detalla las cesantías consignadas o pendientes de consignar. "
        "Se necesitan **dos archivos** según el destino DIAN:"
    )

    st.markdown(
        f"""
        | Archivo | Año causado | Va a | Concepto DIAN |
        |---|---|---|---|
        | Cesantías **pagadas en {año_gravable}** (de feb-{año_gravable}) | {año_gravable - 1} | F1001 (al fondo) + F2276 (por empleado) | 5016 |
        | Cesantías **pagadas en {año_gravable + 1}** (de feb-{año_gravable + 1}) — pasivo 31-dic | {año_gravable} | F1009 (al fondo) | 2204 |
        """
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown(f"##### 🟢 Pagadas en {año_gravable} (F1001 + F2276)")
        archivo_pagadas = st.file_uploader(
            f"Informe del fondo — cesantías {año_gravable - 1} pagadas {año_gravable}",
            type=['xls'],
            key=f"pila_ces_pagadas_{año_gravable}",
        )
        if archivo_pagadas is not None:
            _procesar_archivo_cesantias(
                archivo_pagadas, empresa, año_gravable,
                es_pasivo_default=False, supabase=supabase,
            )

    with col2:
        st.markdown(f"##### 🟡 Pasivo al 31-dic-{año_gravable} (F1009 cpto 2204)")
        archivo_pasivo = st.file_uploader(
            f"Informe del fondo — cesantías {año_gravable} pagadas {año_gravable + 1}",
            type=['xls'],
            key=f"pila_ces_pasivo_{año_gravable}",
        )
        if archivo_pasivo is not None:
            _procesar_archivo_cesantias(
                archivo_pasivo, empresa, año_gravable,
                es_pasivo_default=True, supabase=supabase,
            )

    # Mostrar cesantías ya cargadas
    st.markdown("---")
    cesantias = obtener_cesantias(supabase, empresa['id'], año_gravable)
    if cesantias:
        st.markdown(f"##### Cesantías cargadas ({len(cesantias)})")
        filas = []
        for c in cesantias:
            filas.append({
                'Año causado': c['año_causado'],
                'Tipo': '🟡 Pasivo' if c['es_pasivo'] else '🟢 Pagada',
                'Fecha pago': c.get('fecha_pago', '—'),
                'Fondo': c['fondo_nombre'],
                'NIT Fondo': c['fondo_nit'],
                'Empleados': len(c.get('exogena_pila_cesantias_empleados', [])),
                'Total': f"${float(c['total']):,.0f}",
            })
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)


def _procesar_archivo_cesantias(
    archivo, empresa: dict, año_gravable: int,
    es_pasivo_default: bool, supabase
) -> None:
    with st.spinner("Leyendo informe..."):
        informe = leer_xls_informe_cesantias(archivo.read(), nombre_archivo=archivo.name)

    if informe.errores:
        for e in informe.errores:
            st.error(e)
        return

    if not informe.empleados:
        st.warning("No se detectaron empleados")
        return

    st.success(
        f"✅ Fondo: {informe.fondo_nombre} (NIT {informe.fondo_nit}) · "
        f"Año causado: {informe.año_causado} · "
        f"{len(informe.empleados)} empleados · "
        f"**${informe.total:,.0f}**"
    )

    # Permitir corregir si está marcado mal
    es_pasivo = st.checkbox(
        "Es pasivo al 31-dic (va al F1009 concepto 2204)",
        value=es_pasivo_default,
        key=f"es_pasivo_{archivo.name}",
        help="Si está marcado: F1009 cpto 2204. Si no: F1001 cpto 5016 + F2276",
    )

    # Tabla empleados
    df_emp = pd.DataFrame([
        {
            'Tipo Doc': e.tipo_doc, 'Documento': e.documento,
            'Apellidos': e.apellidos, 'Nombres': e.nombres,
            'Días': e.dias_base,
            'Salario base': f"${e.salario_base:,.0f}",
            'Cesantía': f"${e.cesantia:,.0f}",
        }
        for e in informe.empleados
    ])
    st.dataframe(df_emp, use_container_width=True, hide_index=True)

    if st.button(
        "💾 Guardar cesantías",
        key=f"guardar_ces_{archivo.name}",
        type='primary',
    ):
        with st.spinner("Guardando..."):
            info = guardar_cesantias(
                supabase, empresa['id'], año_gravable,
                informe.año_causado, es_pasivo, informe,
            )
        if info['errores']:
            for e in info['errores']:
                st.error(e)
        else:
            st.success(f"✅ Guardado · {info['empleados_insertados']} empleados")
            st.rerun()


# ============================================================
# Sub-tab 3: Resumen
# ============================================================

def _render_subtab_resumen(empresa: dict, año_gravable: int, supabase) -> None:
    st.markdown("#### Resumen de líneas DIAN generadas desde PILA")

    try:
        resumen = construir_resumen_pila(supabase, empresa['id'], año_gravable)
    except Exception as e:
        st.error(f"Error construyendo resumen: {e}")
        return

    totales = resumen['totales_generales']

    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("F1001 aportes (5010+5011+5012)", f"${totales['f1001_aportes']:,.0f}")
    with col2:
        st.metric("F1001 cesantías (5016)", f"${totales['f1001_cesantias']:,.0f}")
    with col3:
        st.metric("F1009 (2214 + 2204)", f"${totales['f1009_total']:,.0f}")
    with col4:
        st.metric("F2276 cesantías", f"${totales['f2276_total']:,.0f}")

    st.markdown("---")

    # F1001 - aportes
    st.markdown("##### 📋 F1001 — Aportes SS y parafiscales")
    for concepto in [5010, 5011, 5012]:
        seccion = resumen['f1001'][str(concepto)]
        if seccion['total'] == 0:
            continue
        st.markdown(
            f"**Concepto {concepto}** — {CONCEPTOS_F1001_PILA[concepto]}: "
            f"${seccion['total']:,.0f}"
        )
        if seccion['lineas']:
            df = pd.DataFrame([
                {'NIT': l.nit, 'Administradora': l.nombre, 'Valor': f"${l.valor:,.0f}"}
                for l in seccion['lineas']
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)

    # F1001 cesantías
    if resumen['f1001']['5016']['total'] > 0:
        st.markdown("---")
        st.markdown("##### 📋 F1001 — Cesantías al fondo (concepto 5016)")
        df = pd.DataFrame([
            {'NIT Fondo': l.nit, 'Fondo': l.nombre, 'Valor': f"${l.valor:,.0f}"}
            for l in resumen['f1001']['5016']['lineas']
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    # F1009
    st.markdown("---")
    st.markdown("##### 📋 F1009 — Pasivos al 31-dic")
    for concepto in [2214, 2204]:
        seccion = resumen['f1009'][str(concepto)]
        if seccion['total'] == 0:
            continue
        st.markdown(
            f"**Concepto {concepto}** — {CONCEPTOS_F1009_PILA[concepto]}: "
            f"${seccion['total']:,.0f}"
        )
        if seccion['lineas']:
            df = pd.DataFrame([
                {
                    'NIT': l.nit,
                    'Tercero': l.nombre,
                    'Valor': f"${l.valor:,.0f}",
                }
                for l in seccion['lineas']
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)

    # F2276 cesantías
    if resumen['f2276']['empleados']:
        st.markdown("---")
        st.markdown(
            f"##### 📋 F2276 — Cesantías por empleado "
            f"({len(resumen['f2276']['empleados'])} trabajadores)"
        )
        df = pd.DataFrame([
            {
                'Tipo Doc': e.tipo_doc, 'Documento': e.documento,
                'Apellidos': e.apellidos, 'Nombres': e.nombres,
                'Cesantía e intereses': f"${e.cesantia:,.0f}",
            }
            for e in resumen['f2276']['empleados']
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)


# ============================================================
# Sub-tab 4: Conciliación contra balance contable
# ============================================================

def _render_subtab_conciliacion(empresa: dict, año_gravable: int, supabase) -> None:
    st.markdown("#### Conciliación PILA vs Balance contable")
    st.caption(
        "Compara los totales PILA contra los saldos de las cuentas contables "
        "para detectar diferencias antes de generar el borrador DIAN."
    )

    try:
        resumen = construir_resumen_pila(supabase, empresa['id'], año_gravable)
    except Exception as e:
        st.error(f"Error: {e}")
        return

    # Obtener saldos del balance
    try:
        # Cuentas 237xxx (aportes por pagar) → comparar contra F1009 2214
        resp_237 = supabase.table('exogena_balance') \
            .select('codigo_cuenta,nombre_cuenta,saldo_final') \
            .eq('empresa_id', empresa['id']) \
            .eq('año_gravable', año_gravable) \
            .like('codigo_cuenta', '237%') \
            .execute()
        saldos_237 = resp_237.data or []

        # Cuenta 2510 (cesantías consolidadas) → comparar contra F1009 2204
        resp_2510 = supabase.table('exogena_balance') \
            .select('codigo_cuenta,nombre_cuenta,saldo_final') \
            .eq('empresa_id', empresa['id']) \
            .eq('año_gravable', año_gravable) \
            .like('codigo_cuenta', '2510%') \
            .execute()
        saldos_2510 = resp_2510.data or []
    except Exception as e:
        st.warning(f"No se pudo cargar el balance: {e}")
        saldos_237 = []
        saldos_2510 = []

    # F1009 2214 — Aportes SS
    st.markdown("##### F1009 concepto 2214 — Aportes SS por pagar")
    total_237 = sum(Decimal(str(s.get('saldo_final') or 0)) for s in saldos_237)
    total_pila_2214 = resumen['f1009']['2214']['total']
    dif_2214 = total_pila_2214 - total_237

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Balance (cuentas 237xxx)", f"${total_237:,.0f}")
    with col2:
        st.metric("PILA (cot dic)", f"${total_pila_2214:,.0f}")
    with col3:
        st.metric("Diferencia", f"${dif_2214:,.0f}", delta=f"{dif_2214:,.0f}")

    if saldos_237:
        with st.expander("Ver detalle cuentas 237xxx"):
            df = pd.DataFrame([
                {
                    'Cuenta': s['codigo_cuenta'],
                    'Nombre': s['nombre_cuenta'],
                    'Saldo final': f"${float(s.get('saldo_final') or 0):,.0f}",
                }
                for s in saldos_237
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)

    # F1009 2204 — Cesantías
    st.markdown("---")
    st.markdown("##### F1009 concepto 2204 — Cesantías consolidadas")
    total_2510 = sum(Decimal(str(s.get('saldo_final') or 0)) for s in saldos_2510)
    total_pila_2204 = resumen['f1009']['2204']['total']
    dif_2204 = total_pila_2204 - total_2510

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Balance (cuentas 2510xx)", f"${total_2510:,.0f}")
    with col2:
        st.metric("PILA (cesantías feb sig.)", f"${total_pila_2204:,.0f}")
    with col3:
        st.metric("Diferencia", f"${dif_2204:,.0f}", delta=f"{dif_2204:,.0f}")

    if saldos_2510:
        with st.expander("Ver detalle cuentas 2510xx"):
            df = pd.DataFrame([
                {
                    'Cuenta': s['codigo_cuenta'],
                    'Nombre': s['nombre_cuenta'],
                    'Saldo final': f"${float(s.get('saldo_final') or 0):,.0f}",
                }
                for s in saldos_2510
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)

    # Aviso si hay diferencias significativas
    st.markdown("---")
    if abs(dif_2214) > Decimal('10000') or abs(dif_2204) > Decimal('10000'):
        st.warning(
            "⚠️ Hay diferencias entre balance y PILA superiores a $10,000. "
            "Revisa antes de generar el borrador DIAN."
        )
    else:
        st.success(
            "✅ Balance y PILA cuadran dentro de la tolerancia de $10,000."
        )
