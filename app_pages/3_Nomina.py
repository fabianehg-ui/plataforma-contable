"""
Módulo Nómina — Plataforma Web (con PILA integrada como insumo opcional).

Procesa un Excel mensual de nómina (1 hoja por empleada, 2 quincenas
apiladas) y genera el plano contable con:
    - Comp 11: causación quincenal de nómina (2 asientos)
    - Comp 9:  provisión mensual de aportes y prestaciones

Adicionalmente acepta opcionalmente la prefactura PILA del periodo
(Enlace Operativo / SuAporte) en PDF para mostrar la comparación
provisión vs aporte real pagado.

NOTA v3.x: en esta versión la PILA es solo INFORMATIVA (no genera líneas
de ajuste contable). Esa fase se hace en una iteración posterior.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import calendar
from datetime import date

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from auth.modulos import require_modulo

from core.procesadores.procesador_nomina import (
    procesar_nomina,
    info_empleados_embebido,
    cargar_empleados_embebido,
    COMPROBANTE_NOMINA,
    COMPROBANTE_PROVISION,
    dataframe_a_plano_tsv,
)

# Lectura de PILA (opcional — solo se importa si está disponible)
try:
    from core.procesadores.procesador_pila import leer_planilla_pila
    PILA_DISPONIBLE = True
except ImportError:
    PILA_DISPONIBLE = False

# Lectura de vacaciones / liquidaciones definitivas (opcional)
try:
    from core.lectores.lector_vacaciones import (
        leer_documento as leer_vac_liq,
        vacaciones_a_dataframe,
        definitiva_a_dataframe,
        exportar_excel as exportar_vac_liq_excel,
        generar_plano_vacaciones,
        plano_a_tsv as plano_vac_a_tsv,
    )
    VAC_LIQ_DISPONIBLE = True
except ImportError:
    VAC_LIQ_DISPONIBLE = False


# ============================================================
# Configuración
# ============================================================

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
require_modulo("nomina")
emp = require_rol(["admin", "operador"])


# ============================================================
# Encabezado
# ============================================================

st.markdown("# 💼 NÓMINA")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    f"Procesa nómina mensual con causación quincenal (Comp 11) "
    f"y provisión de aportes (Comp 9). "
    f"Acepta planilla PILA pagada como insumo opcional."
)
st.markdown("---")


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:
    st.markdown("### ⚙️ Opciones")
    incluir_enc_excel = st.checkbox(
        "Incluir 'sep=\\t' (compatible Excel)",
        value=True,
    )

    st.markdown("---")
    st.markdown("### 📐 Comprobantes generados")
    st.caption(
        f"""
        | Comp | Tipo | Frecuencia |
        |---|---|---|
        | **{COMPROBANTE_NOMINA}** | Causación nómina | Quincenal (día 15 y último) |
        | **{COMPROBANTE_PROVISION}** | Provisión aportes y prestaciones | Mensual (último día) |
        """
    )

    st.markdown("---")
    st.markdown("### 🔧 Reglas clave")
    st.caption(
        """
        ✅ **Empresa exonerada Art. 114-1 ET:**
        - NO Salud patronal 8.5%
        - NO SENA 2%
        - NO ICBF 3%
        - SÍ Pensión 12%, ARL, Caja 4%

        ✅ **Bases contables:**
        - IBC seguridad social = Devengado − AuxTpte − Incapacidad
        - Base prestaciones = Total Devengado
        - Base vacaciones = Devengado − AuxTpte

        ✅ **Cuentas por área:**
        - ADMIN → 510xxx
        - OPERACIÓN → 520xxx

        ⚠️ Las DEDUCCIONES del empleado se LEEN
        del Excel (no se recalculan).
        """
    )

    if PILA_DISPONIBLE:
        st.markdown("---")
        st.success("📎 Lector PILA activo")
    else:
        st.markdown("---")
        st.warning("📎 Lector PILA no instalado")


# ============================================================
# Pestañas
# ============================================================

tab_procesar, tab_empleados, tab_pila = st.tabs([
    "📤 Procesar nómina",
    "👥 Empleados",
    "📎 Acerca de PILA",
])


# ------------------------------------------------------------
# Pestaña: Procesar
# ------------------------------------------------------------

with tab_procesar:
    st.markdown("### 📤 Subir archivos del periodo")

    st.info(
        "📋 **Cómo funciona:**\n\n"
        "- La **planilla de nómina** (obligatoria) genera Comp 11 (causación quincenal) y "
        "Comp 9 (provisión del último día del mes).\n"
        "- La **prefactura PILA** (opcional) se usa para **comparar visualmente** lo "
        "provisionado vs lo realmente pagado en aportes.\n"
        "- Las **vacaciones y liquidaciones definitivas** (opcional) se suben cuando "
        "aparezcan en el movimiento del mes. A las vacaciones (no definitivas) se les "
        "deduce 4% pensión + 4% salud.\n"
        "- Si no subes PILA ni vacaciones, el sistema procesa solo la nómina y genera el "
        "plano normalmente."
    )

    # Selector de periodo
    col_p1, col_p2 = st.columns([1, 2])
    with col_p1:
        hoy = date.today()
        anio = st.number_input(
            "Año del periodo",
            min_value=2020, max_value=2100,
            value=hoy.year if hoy.month > 1 else hoy.year - 1,
            step=1,
        )
    with col_p2:
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                 "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        mes_default = hoy.month - 1 if hoy.month > 1 else 12
        mes_idx = st.selectbox(
            "Mes del periodo",
            options=list(range(1, 13)),
            format_func=lambda i: f"{i:02d} — {meses[i - 1]}",
            index=mes_default - 1,
        )

    # Uploaders en dos columnas
    col_n, col_pl = st.columns(2)
    with col_n:
        st.markdown("**📋 Planilla de Nómina** _(obligatorio)_")
        archivo_nomina = st.file_uploader(
            "NOMINA_CASATRECE_<MES>.xls",
            type=["xls", "xlsx"],
            help="Excel mensual con 1 hoja por empleada y 2 quincenas apiladas.",
            key="archivo_nomina",
        )
    with col_pl:
        st.markdown("**📎 Prefactura PILA pagada** _(opcional)_")
        archivo_pila = st.file_uploader(
            "Prefactura_<numero>.pdf",
            type=["pdf", "xlsx", "xls"],
            help="Prefactura SuAporte / Enlace Operativo del periodo. "
                 "Sirve para comparar lo provisionado vs lo pagado en aportes. "
                 "Por ahora solo se muestra; no genera líneas contables.",
            key="archivo_pila",
            disabled=not PILA_DISPONIBLE,
        )
        if not PILA_DISPONIBLE:
            st.caption("⚠️ El lector de PILA no está instalado en el servidor.")

    # Vacaciones y liquidaciones definitivas (opcional, cuando las haya en el mes)
    st.markdown("**🏖️ Vacaciones y liquidaciones definitivas** _(opcional)_")
    archivos_vac = st.file_uploader(
        "PDF de vacaciones y/o liquidaciones definitivas del mes",
        type=["pdf"],
        accept_multiple_files=True,
        key="archivos_vac_liq",
        help="Súbelos cuando en el movimiento del mes haya pago de vacaciones "
             "o liquidaciones definitivas. A las vacaciones (no definitivas) se les "
             "deduce 4% pensión + 4% salud; en liquidación definitiva las vacaciones "
             "NO llevan esa deducción.",
        disabled=not VAC_LIQ_DISPONIBLE,
    )
    if not VAC_LIQ_DISPONIBLE:
        st.caption("⚠️ El lector de vacaciones/liquidaciones no está instalado en el servidor.")

    # === Procesar nómina ===
    if archivo_nomina is not None:
        st.markdown("---")
        with st.spinner("Procesando planilla de nómina..."):
            try:
                df_plano, log, resumen = procesar_nomina(
                    archivo=archivo_nomina,
                    anio=int(anio),
                    mes=int(mes_idx),
                )
            except Exception as e:
                st.error(f"❌ Error procesando la nómina:\n\n```\n{e}\n```")
                df_plano = None
                log = []
                resumen = {}

        if df_plano is not None and len(df_plano) > 0:
            total_db = int(df_plano[df_plano["TR"] == "1"]["VALOR"].astype(int).sum())
            total_cr = int(df_plano[df_plano["TR"] == "2"]["VALOR"].astype(int).sum())
            cuadra = total_db == total_cr

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Empleadas", resumen.get("empleados_procesados", 0))
            with col2:
                st.metric("Líneas plano", len(df_plano))
            with col3:
                st.metric("Comprobantes", len(df_plano["COMPROBANTE"].unique()))
            with col4:
                st.metric(
                    "Total Db",
                    f"$ {total_db:,}".replace(",", "."),
                )

            if cuadra:
                st.success(f"✅ **Cuadre perfecto Db = Cr = ${total_db:,}**".replace(",", "."))
            else:
                st.error(f"❌ **Descuadre:** ${total_db - total_cr:,}".replace(",", "."))

            # Verificar valores negativos
            n_negs = (df_plano["VALOR"].astype(int) < 0).sum()
            if n_negs > 0:
                st.error(
                    f"❌ **{n_negs} líneas con valor negativo!** "
                    "El TR debería definir el signo."
                )

            # === Resumen por comprobante ===
            st.markdown("#### 📒 Asientos por comprobante")
            asientos = []
            tipos = {
                COMPROBANTE_NOMINA:    "Causación quincenal de nómina",
                COMPROBANTE_PROVISION: "Provisión mensual de aportes",
            }
            for comp in sorted(df_plano["COMPROBANTE"].unique()):
                sub = df_plano[df_plano["COMPROBANTE"] == comp]
                db = int(sub[sub["TR"] == "1"]["VALOR"].astype(int).sum())
                cr = int(sub[sub["TR"] == "2"]["VALOR"].astype(int).sum())
                asientos.append({
                    "Comp": comp,
                    "Tipo": tipos.get(comp, "—"),
                    "Documentos": sub["DOCUMENTO"].nunique(),
                    "Líneas": len(sub),
                    "Total Db": f"$ {db:,}".replace(",", "."),
                    "Total Cr": f"$ {cr:,}".replace(",", "."),
                    "Cuadra": "✅" if db == cr else "❌",
                })
            st.dataframe(
                pd.DataFrame(asientos),
                use_container_width=True,
                hide_index=True,
            )

            # === Resumen PILA si se subió ===
            if archivo_pila is not None and PILA_DISPONIBLE:
                st.markdown("---")
                st.markdown("#### 📎 Comparación con PILA pagada")
                try:
                    # Construir catálogo {cedula: nombre_correcto} para limpiar nombres
                    empleados_dict = cargar_empleados_embebido()
                    catalogo_nombres = {
                        cc: emp_obj.nombre
                        for cc, emp_obj in empleados_dict.items()
                    }
                    pila = leer_planilla_pila(
                        archivo_pila,
                        catalogo_empleados=catalogo_nombres,
                    )
                except Exception as e:
                    st.error(f"❌ Error leyendo PILA:\n\n```\n{e}\n```")
                    pila = None

                if pila is not None:
                    # Métricas globales
                    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                    with col_m1:
                        st.metric(
                            "Planilla",
                            f"#{pila.numero_planilla}" if pila.numero_planilla else "—",
                        )
                    with col_m2:
                        st.metric(
                            "Empleados PILA",
                            len(pila.por_empleado),
                        )
                    with col_m3:
                        st.metric(
                            "Total pagado",
                            f"$ {int(pila.totales.total_final):,}".replace(",", "."),
                        )
                    with col_m4:
                        # Validación exonerada
                        no_exon = int(pila.totales.aportes_sena + pila.totales.aportes_icbf)
                        if no_exon == 0:
                            st.metric("Exoneración Art.114-1", "✅ OK")
                        else:
                            st.metric(
                                "⚠️ SENA+ICBF",
                                f"$ {no_exon:,}".replace(",", "."),
                            )

                    # Detalle de aportes pagados por concepto
                    st.markdown("**Aportes pagados (sección III del PDF)**")
                    df_aportes = pd.DataFrame([
                        {
                            "Concepto": "Pensión",
                            "IBC":      f"$ {int(pila.totales.ibc_pension):,}".replace(",", "."),
                            "Aportes":  f"$ {int(pila.totales.aportes_pension):,}".replace(",", "."),
                        },
                        {
                            "Concepto": "Salud (4% empleado)",
                            "IBC":      f"$ {int(pila.totales.ibc_salud):,}".replace(",", "."),
                            "Aportes":  f"$ {int(pila.totales.aportes_salud):,}".replace(",", "."),
                        },
                        {
                            "Concepto": "ARL",
                            "IBC":      f"$ {int(pila.totales.ibc_riesgos):,}".replace(",", "."),
                            "Aportes":  f"$ {int(pila.totales.aportes_riesgos):,}".replace(",", "."),
                        },
                        {
                            "Concepto": "Caja Compensación",
                            "IBC":      f"$ {int(pila.totales.ibc_cajas):,}".replace(",", "."),
                            "Aportes":  f"$ {int(pila.totales.aportes_cajas):,}".replace(",", "."),
                        },
                        {
                            "Concepto": "FSP / FSS",
                            "IBC":      "—",
                            "Aportes":  f"$ {int(pila.totales.aportes_fsp + pila.totales.aportes_fss):,}".replace(",", "."),
                        },
                    ])
                    st.dataframe(
                        df_aportes,
                        use_container_width=True,
                        hide_index=True,
                    )

                    # Detalle por empleado
                    if pila.por_empleado:
                        st.markdown("**Aportes por empleado**")
                        filas_emp = []
                        for ced, e in pila.por_empleado.items():
                            filas_emp.append({
                                "Cédula": ced,
                                "Nombre": e.nombre,
                                "Días pens.": e.dias_pension,
                                "IBC":     f"$ {int(e.ibc_pension):,}".replace(",", "."),
                                "Pensión": f"$ {int(e.aporte_pension):,}".replace(",", "."),
                                "Salud":   f"$ {int(e.aporte_salud):,}".replace(",", "."),
                                "ARL":     f"$ {int(e.aporte_arl):,}".replace(",", "."),
                                "Caja":    f"$ {int(e.aporte_caja):,}".replace(",", "."),
                                "Pensión Adm.":  e.administradora_pension,
                                "EPS":           e.administradora_salud,
                                "ARL Adm.":      e.administradora_arl,
                            })
                        st.dataframe(
                            pd.DataFrame(filas_emp),
                            use_container_width=True,
                            hide_index=True,
                        )

                    # Validación cruzada empleado-vs-empleado entre PILA y Nómina
                    cedulas_pila = set(str(c) for c in pila.por_empleado.keys())
                    cedulas_nomina = set()
                    detalle_emp = resumen.get("detalle_empleados", [])
                    if isinstance(detalle_emp, list) and detalle_emp:
                        cedulas_nomina = set(
                            str(item.get("cc", "")) for item in detalle_emp
                            if item.get("cc")
                        )
                    else:
                        # Fallback: usar el catálogo embebido
                        cedulas_nomina = set(str(k) for k in empleados_dict.keys())

                    solo_pila = cedulas_pila - cedulas_nomina
                    solo_nomina = cedulas_nomina - cedulas_pila

                    if solo_pila:
                        st.warning(
                            "⚠️ Empleados en **PILA pero no en nómina**: " +
                            ", ".join(sorted(solo_pila))
                        )
                    if solo_nomina:
                        st.warning(
                            "⚠️ Empleados en **nómina pero no en PILA**: " +
                            ", ".join(sorted(solo_nomina))
                        )
                    if not solo_pila and not solo_nomina and cedulas_pila:
                        st.success(
                            "✅ Todos los empleados de nómina aparecen en PILA y viceversa."
                        )

                    # Log del lector PILA
                    with st.expander("📜 Ver log de lectura PILA"):
                        st.code("\n".join(pila.log), language="text")

                    st.info(
                        "ℹ️ En esta versión la PILA se muestra solo como **referencia visual**. "
                        "Las líneas de ajuste automático en Comp 9 (provisión vs pagado) "
                        "se implementarán en la próxima iteración."
                    )

            # === Plano completo ===
            with st.expander("📄 Ver plano completo"):
                st.dataframe(df_plano, use_container_width=True, hide_index=True)

            with st.expander("📜 Ver log de procesamiento"):
                st.code("\n".join(log), language="text")

            # === Descargas ===
            st.markdown("#### ⬇️ Descargas")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                tsv_bytes = dataframe_a_plano_tsv(
                    df_plano,
                    incluir_encabezado_excel=incluir_enc_excel,
                )
                st.download_button(
                    label="📥 Plano (.txt)",
                    data=tsv_bytes,
                    file_name=f"plano_nomina_{int(anio)}_{int(mes_idx):02d}.txt",
                    mime="text/tab-separated-values",
                    use_container_width=True,
                )
            with col_d2:
                bio = io.BytesIO()
                with pd.ExcelWriter(bio, engine="openpyxl") as writer:
                    df_plano.to_excel(writer, sheet_name="PLANO", index=False)
                st.download_button(
                    label="📥 Plano (.xlsx)",
                    data=bio.getvalue(),
                    file_name=f"plano_nomina_{int(anio)}_{int(mes_idx):02d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )


    # === Vacaciones y liquidaciones definitivas del mes ===
    if archivos_vac and VAC_LIQ_DISPONIBLE:
        st.markdown("---")
        st.markdown("### 🏖️ Vacaciones y liquidaciones definitivas del mes")
        st.caption(
            "Documentos opcionales del movimiento del mes. A las **vacaciones** "
            "(no definitivas) se les aplica 4% pensión + 4% salud; en una "
            "**liquidación definitiva** las vacaciones NO llevan esa deducción."
        )

        for archivo_vl in archivos_vac:
            with st.expander(f"📄 {archivo_vl.name}", expanded=len(archivos_vac) == 1):
                try:
                    dvl = leer_vac_liq(archivo_vl)
                except Exception as e:
                    st.error(f"❌ No se pudo leer {archivo_vl.name}: {e}")
                    continue

                # ---------- VACACIONES ----------
                if dvl.get("tipo") == "vacaciones":
                    st.success("Tipo: **Liquidación de vacaciones** (aplica 4% + 4%)")
                    cva, cvb, cvc = st.columns(3)
                    with cva:
                        st.metric("Empleado", dvl.get("nombre", "—") or "—")
                        st.caption(f"Cédula: {dvl.get('cedula', '—') or '—'}")
                    with cvb:
                        st.metric(
                            "Total vacaciones",
                            f"$ {dvl.get('total_vacaciones', 0):,}".replace(",", "."),
                        )
                        st.caption(f"{dvl.get('total_dias', 0)} días")
                    with cvc:
                        st.metric(
                            "Neto a pagar",
                            f"$ {dvl.get('neto_calculado', 0):,}".replace(",", "."),
                        )

                    st.dataframe(
                        vacaciones_a_dataframe(dvl),
                        use_container_width=True, hide_index=True,
                        column_config={
                            "Valor": st.column_config.NumberColumn(format="$ %d"),
                        },
                    )

                    dpa, dpb, dpc = st.columns(3)
                    with dpa:
                        st.metric("Pensión 4%", f"$ {dvl['deduccion_pension']:,}".replace(",", "."))
                    with dpb:
                        st.metric("Salud 4%", f"$ {dvl['deduccion_salud']:,}".replace(",", "."))
                    with dpc:
                        st.metric("Deducción 8%", f"$ {dvl['deduccion_total_calculada']:,}".replace(",", "."))

                    if dvl.get("deduccion_documento"):
                        if dvl.get("deduccion_cuadra"):
                            st.success("✅ La deducción 4%+4% coincide con la del documento.")
                        else:
                            st.warning("⚠️ La deducción del documento difiere de 4%+4%. Revísala.")

                    # --- Plano contable del pago de vacaciones (Comp 11) ---
                    st.markdown("**📄 Plano contable · pago de vacaciones (Comp 11)**")
                    ultimo_dia = calendar.monthrange(int(anio), int(mes_idx))[1]
                    fecha_plano = f"{int(mes_idx):02d}/{ultimo_dia:02d}/{int(anio)}"
                    df_vac_plano = generar_plano_vacaciones(
                        dvl,
                        comprobante="11",
                        documento=str(int(mes_idx)),
                        fecha=fecha_plano,
                        centro_costo="",
                    )
                    st.dataframe(
                        df_vac_plano, use_container_width=True, hide_index=True,
                        column_config={
                            "VALOR": st.column_config.NumberColumn(format="%d"),
                            "BASE": st.column_config.NumberColumn(format="%d"),
                        },
                    )
                    db_v = int(df_vac_plano[df_vac_plano["TR"] == "1"]["VALOR"].sum())
                    cr_v = int(df_vac_plano[df_vac_plano["TR"] == "2"]["VALOR"].sum())
                    if db_v == cr_v:
                        st.success(f"✅ Cuadra Db = Cr = $ {db_v:,}".replace(",", "."))
                    else:
                        st.error(f"❌ Descuadre: $ {db_v - cr_v:,}".replace(",", "."))

                    cpa, cpb = st.columns(2)
                    with cpa:
                        st.download_button(
                            "📥 Plano (.txt)",
                            data=plano_vac_a_tsv(df_vac_plano, incluir_enc_excel),
                            file_name=f"plano_vacaciones_{int(anio)}_{int(mes_idx):02d}_{dvl.get('cedula','')}.txt",
                            mime="text/tab-separated-values",
                            key=f"dlp_txt_{archivo_vl.name}",
                            use_container_width=True,
                        )
                    with cpb:
                        _bio = io.BytesIO()
                        with pd.ExcelWriter(_bio, engine="openpyxl") as _w:
                            df_vac_plano.to_excel(_w, sheet_name="PLANO", index=False)
                        st.download_button(
                            "📥 Plano (.xlsx)",
                            data=_bio.getvalue(),
                            file_name=f"plano_vacaciones_{int(anio)}_{int(mes_idx):02d}_{dvl.get('cedula','')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dlp_xlsx_{archivo_vl.name}",
                            use_container_width=True,
                        )

                # ---------- LIQUIDACIÓN DEFINITIVA ----------
                else:
                    st.info("Tipo: **Liquidación definitiva** (las vacaciones NO llevan deducción)")
                    ca, cb = st.columns(2)
                    with ca:
                        st.metric("Empleado", dvl.get("nombre", "—") or "—")
                        st.caption(f"Cédula: {dvl.get('cedula', '—') or '—'}")
                    with cb:
                        st.caption(f"Ingreso: {dvl.get('fecha_ingreso', '—') or '—'}")
                        st.caption(f"Retiro: {dvl.get('fecha_retiro', '—') or '—'}")

                    ddf = definitiva_a_dataframe(dvl)
                    if len(ddf):
                        st.dataframe(
                            ddf, use_container_width=True, hide_index=True,
                            column_config={
                                "Valor": st.column_config.NumberColumn(format="$ %d"),
                            },
                        )
                    else:
                        st.warning("No se detectaron conceptos con importe. Revisa el texto crudo.")

                    if dvl.get("valor_vacaciones"):
                        st.warning(
                            f"🏖️ Vacaciones dentro de la liquidación: "
                            f"$ {dvl['valor_vacaciones']:,}".replace(",", ".") +
                            " — **sin** deducción de 4% pensión ni 4% salud."
                        )

                    with st.expander("📄 Ver texto crudo del PDF"):
                        st.code(dvl.get("texto_crudo", ""), language="text")

                # ---------- Descarga ----------
                st.download_button(
                    "📊 Descargar Excel del desglose",
                    data=exportar_vac_liq_excel(dvl),
                    file_name=f"{archivo_vl.name.rsplit('.', 1)[0]}_desglose.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_vac_{archivo_vl.name}",
                )


# ------------------------------------------------------------
# Pestaña: Empleados
# ------------------------------------------------------------

with tab_empleados:
    st.markdown("### 👥 Maestro de empleados")
    st.caption(
        "Editable en `core/data/empleados.json` — commit y Railway redespliega."
    )
    try:
        info = info_empleados_embebido()
    except Exception as e:
        st.error(f"❌ No se pudo cargar el maestro de empleados: {e}")
        info = None

    if info:
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.metric("Total empleados", info.get("total", 0))
        with col_e2:
            st.metric(
                "Por tipo",
                ", ".join(
                    f"{tipo}: {cant}"
                    for tipo, cant in info.get("por_tipo", {}).items()
                ) or "—",
            )
        if "empleados" in info:
            st.dataframe(
                pd.DataFrame(info["empleados"]),
                use_container_width=True,
                hide_index=True,
            )


# ------------------------------------------------------------
# Pestaña: Acerca de PILA
# ------------------------------------------------------------

with tab_pila:
    st.markdown("### 📎 Sobre la planilla PILA")
    st.markdown(
        """
        La **planilla PILA** (Planilla Integrada de Liquidación de Aportes) es
        el reporte mensual de aportes a seguridad social y parafiscales. Para
        Casa UnoTres SAS se genera en la plataforma **SuAporte / Enlace
        Operativo**, con formato típico de **PDF** (también acepta XLSX).

        **¿Qué hace este módulo con la PILA?**

        - La lee y extrae automáticamente:
          - Datos del aportante (NIT, razón social, periodo, # planilla)
          - Detalle por empleado: IBC, aporte pensión, salud, ARL, caja,
            administradoras, días cotizados
          - Totales globales (sección III del PDF)
        - Muestra la información en pantalla para que puedas validar
          visualmente que coincide con tu provisión.

        **Validaciones automáticas:**
        - Suma de aportes por empleado ≈ totales reportados
        - SENA + ICBF deben ser **$0** (Casa UnoTres SAS está exonerada Art. 114-1 ET)
        - Empleados de PILA aparecen en nómina y viceversa

        **¿Y si hay diferencias entre lo provisionado y lo pagado?**

        En esta versión solo se **muestran** las cifras. La generación de
        líneas de ajuste contable automático en Comp 9 (con detalle
        `AJUSTE PILA <CONCEPTO>`) está planeada para una próxima iteración.

        **¿Qué archivo subir?**

        - El PDF original que descargas de SuAporte (ej: `Prefactura_84919326.pdf`)
        - O un Excel exportado de la misma planilla
        """
    )

    if PILA_DISPONIBLE:
        st.success("✅ El lector de PILA está activo en este servidor.")
    else:
        st.error(
            "❌ El lector de PILA NO está disponible. "
            "Verifica que `core/procesadores/procesador_pila.py` exista y que "
            "`pdfplumber` esté en `requirements.txt`."
        )
