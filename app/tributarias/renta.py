"""
Módulo Declaración de Renta — Personas Jurídicas

Genera el Formulario 110 a partir del balance contable y la conciliación
fiscal. Se integra al menú de Herramientas Tributarias del repo.

Convenciones del repo plataforma-contable:
  - st.navigation desde Home.py
  - Auth con auth.login.require_auth y auth.empresas
  - Cliente Supabase desde db.supabase_client
  - UI helpers en core.utils.ui_tributarias
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
import logging

# Path setup (consistente con otros módulos del repo)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa
from core.utils.ui_tributarias import render_pagina_tributaria

from core.procesadores.renta import (
    LiquidadorRenta,
    ParametrosLiquidacion,
    PartidaConciliatoria,
    CATALOGO_PARTIDAS_PERMANENTES,
    UVT,
    PLAZOS_PJ_AG2025,
    ImportadorBalanceSiigo,
    generar_excel_comparativo,
    generar_dictamen_word,
)

# RepositorioRenta es opcional — solo se importa si Supabase está disponible
try:
    from core.procesadores.renta import RepositorioRenta
    from db.supabase_client import get_supabase_client
    SUPABASE_DISPONIBLE = True
except ImportError:
    RepositorioRenta = None
    get_supabase_client = lambda: None
    SUPABASE_DISPONIBLE = False

log = logging.getLogger(__name__)


# ============================================================
# AUTH Y EMPRESA
# ============================================================
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()


# ============================================================
# HEADER (consistente con otras páginas tributarias)
# ============================================================
render_pagina_tributaria(
    titulo="Declaración de Renta",
    descripcion=f"Formulario 110 — {empresa.get('razon_social', '')} (NIT {empresa.get('nit', '')})",
    icono="📝",
)


# ============================================================
# AÑO GRAVABLE Y PLAZO
# ============================================================
with st.sidebar:
    st.divider()
    st.subheader("⚙️ Año gravable")
    ano_gravable = st.selectbox(
        "Año a declarar",
        options=[2025, 2024],
        index=0,
        key="renta_ano_gravable",
    )

    # Mostrar plazo si tenemos último dígito del NIT
    nit = empresa.get('nit', '')
    nit_limpio = nit.split('-')[0] if '-' in nit else nit
    try:
        ultimo_digito = int(nit_limpio[-1])
        if ano_gravable == 2025 and isinstance(PLAZOS_PJ_AG2025, dict):
            plazo = PLAZOS_PJ_AG2025.get(ultimo_digito)
            if plazo:
                st.info(f"📅 Plazo: **{plazo}**\n\nÚltimo dígito NIT: {ultimo_digito}")
    except (ValueError, IndexError):
        pass

    # UVT del año
    if ano_gravable in UVT:
        st.caption(f"UVT {ano_gravable}: ${UVT[ano_gravable]:,}")


# ============================================================
# ESTADO DE SESIÓN
# ============================================================
empresa_id = empresa.get('id', empresa.get('nit', 'default'))
sesion_key = f"renta_{empresa_id}_{ano_gravable}"

if sesion_key not in st.session_state:
    st.session_state[sesion_key] = {
        "patrimonio": {
            "efectivo": 0, "inversiones": 0, "cxc": 0, "inventarios": 0,
            "intangibles": 0, "biologicos": 0, "ppe": 0, "otros_activos": 0,
            "pasivos": 0,
        },
        "ingresos": {
            "ingresos_ordinarios": 0, "ingresos_financieros": 0,
            "otros_ingresos": 0, "devoluciones": 0, "incrngo": 0,
        },
        "costos_gastos": {
            "costos": 0, "gastos_administracion": 0, "gastos_ventas": 0,
            "gastos_financieros": 0, "otros_gastos": 0,
        },
        "informativos": {
            "nomina_total": 0, "seguridad_social": 0, "sena_icbf_caja": 0,
        },
        "retenciones": {
            "autorretenciones": 0, "otras_retenciones": 0, "saldo_favor_anterior": 0,
        },
        "conciliacion": {
            "utilidad_contable": 0, "provision_renta_5405": 0,
            "gmf_total": 0, "partidas_personalizadas": [],
        },
    }

datos = st.session_state[sesion_key]


# ============================================================
# TABS
# ============================================================
tab_datos, tab_balance, tab_pyg, tab_concil, tab_f110, tab_persist = st.tabs([
    "1️⃣ Datos generales",
    "2️⃣ Patrimonio",
    "3️⃣ Ingresos y gastos",
    "4️⃣ Conciliación fiscal",
    "5️⃣ Formulario 110",
    "6️⃣ Histórico",
])


# ============================================================
# TAB 1: DATOS GENERALES + IMPORTACIÓN
# ============================================================
with tab_datos:
    st.subheader("Datos del declarante")
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Razón social", value=empresa.get('razon_social', ''), disabled=True)
        st.text_input("NIT", value=empresa.get('nit', ''), disabled=True)
        st.text_input("CIIU", value=empresa.get('ciiu_principal', ''), disabled=True)
    with col2:
        st.number_input("Año gravable", value=ano_gravable, disabled=True)
        st.text_input("Régimen", value="Ordinario", disabled=True)

    st.divider()
    st.subheader("Importar balance Siigo (opcional)")
    st.caption("Sube el balance de prueba exportado por Siigo Contador para auto-llenar las casillas.")

    archivo = st.file_uploader(
        "Balance de prueba (XLSX)",
        type=["xlsx"],
        key="balance_uploader",
    )
    if archivo is not None:
        if st.button("📥 Importar balance", key="btn_importar"):
            try:
                tmp_path = Path("/tmp") / f"balance_{empresa_id}.xlsx"
                tmp_path.write_bytes(archivo.getvalue())

                imp = ImportadorBalanceSiigo()
                balance = imp.importar(str(tmp_path))

                # Auto-llenar (valores absolutos por convención de Siigo)
                datos["patrimonio"]["efectivo"] = abs(float(balance.saldo_clase("11")))
                datos["patrimonio"]["cxc"] = abs(float(balance.saldo_clase("13")))
                datos["patrimonio"]["inventarios"] = abs(float(balance.saldo_clase("14")))
                datos["patrimonio"]["ppe"] = abs(float(balance.saldo_clase("15")))
                datos["patrimonio"]["otros_activos"] = abs(float(balance.saldo_clase("19")))
                datos["patrimonio"]["pasivos"] = abs(float(balance.saldo_clase("2")))

                datos["ingresos"]["ingresos_ordinarios"] = abs(float(balance.saldo_clase("41")))
                datos["ingresos"]["ingresos_financieros"] = abs(float(balance.saldo_grupo("4210")))

                datos["costos_gastos"]["costos"] = abs(float(balance.saldo_clase("6")))
                datos["costos_gastos"]["gastos_administracion"] = abs(float(balance.saldo_clase("51")))
                datos["costos_gastos"]["gastos_ventas"] = abs(float(balance.saldo_clase("52")))

                datos["conciliacion"]["provision_renta_5405"] = abs(float(balance.saldo_grupo("5405")))

                st.success(
                    f"✓ Balance importado: {balance.razon_social} — {len(balance.cuentas)} cuentas. "
                    "Revisa los valores en las pestañas siguientes y ajusta lo que sea necesario."
                )
            except Exception as e:
                st.error(f"Error importando balance: {e}")
                log.exception("Error importando balance Siigo")


# ============================================================
# TAB 2: PATRIMONIO
# ============================================================
with tab_balance:
    st.subheader("Patrimonio al cierre")
    st.caption("Casillas 36 a 46 del Formulario 110")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Activos corrientes**")
        datos["patrimonio"]["efectivo"] = st.number_input(
            "Cas. 36 — Efectivo y equivalentes",
            value=float(datos["patrimonio"]["efectivo"]), step=1000.0, format="%.2f", key="p_efec")
        datos["patrimonio"]["inversiones"] = st.number_input(
            "Cas. 37 — Inversiones",
            value=float(datos["patrimonio"]["inversiones"]), step=1000.0, format="%.2f", key="p_inv")
        datos["patrimonio"]["cxc"] = st.number_input(
            "Cas. 38 — Cuentas y documentos por cobrar",
            value=float(datos["patrimonio"]["cxc"]), step=1000.0, format="%.2f", key="p_cxc")
        datos["patrimonio"]["inventarios"] = st.number_input(
            "Cas. 39 — Inventarios",
            value=float(datos["patrimonio"]["inventarios"]), step=1000.0, format="%.2f", key="p_inventarios")
    with col2:
        st.markdown("**Activos no corrientes**")
        datos["patrimonio"]["intangibles"] = st.number_input(
            "Cas. 40 — Intangibles",
            value=float(datos["patrimonio"]["intangibles"]), step=1000.0, format="%.2f", key="p_intang")
        datos["patrimonio"]["biologicos"] = st.number_input(
            "Cas. 41 — Activos biológicos",
            value=float(datos["patrimonio"]["biologicos"]), step=1000.0, format="%.2f", key="p_biol")
        datos["patrimonio"]["ppe"] = st.number_input(
            "Cas. 42 — Propiedades, planta y equipo",
            value=float(datos["patrimonio"]["ppe"]), step=1000.0, format="%.2f", key="p_ppe")
        datos["patrimonio"]["otros_activos"] = st.number_input(
            "Cas. 43 — Otros activos",
            value=float(datos["patrimonio"]["otros_activos"]), step=1000.0, format="%.2f", key="p_otros")

    st.divider()
    datos["patrimonio"]["pasivos"] = st.number_input(
        "Cas. 45 — Pasivos",
        value=float(datos["patrimonio"]["pasivos"]), step=1000.0, format="%.2f", key="p_pasivos")

    p = datos["patrimonio"]
    total_pb = (p["efectivo"] + p["inversiones"] + p["cxc"] + p["inventarios"] +
                p["intangibles"] + p["biologicos"] + p["ppe"] + p["otros_activos"])
    total_pl = total_pb - p["pasivos"]

    col_a, col_b = st.columns(2)
    col_a.metric("Cas. 44 — Patrimonio bruto", f"${total_pb:,.0f}")
    col_b.metric("Cas. 46 — Patrimonio líquido", f"${total_pl:,.0f}")


# ============================================================
# TAB 3: INGRESOS Y GASTOS
# ============================================================
with tab_pyg:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Ingresos**")
        datos["ingresos"]["ingresos_ordinarios"] = st.number_input(
            "Cas. 47 — Ingresos brutos actividades ordinarias",
            value=float(datos["ingresos"]["ingresos_ordinarios"]), step=1000.0, format="%.2f", key="i_ord")
        datos["ingresos"]["ingresos_financieros"] = st.number_input(
            "Cas. 48 — Ingresos financieros",
            value=float(datos["ingresos"]["ingresos_financieros"]), step=1000.0, format="%.2f", key="i_fin")
        datos["ingresos"]["otros_ingresos"] = st.number_input(
            "Cas. 57 — Otros ingresos",
            value=float(datos["ingresos"]["otros_ingresos"]), step=1000.0, format="%.2f", key="i_otros")
        datos["ingresos"]["devoluciones"] = st.number_input(
            "Cas. 59 — Devoluciones, rebajas y descuentos",
            value=float(datos["ingresos"]["devoluciones"]), step=1000.0, format="%.2f", key="i_dev")
        datos["ingresos"]["incrngo"] = st.number_input(
            "Cas. 60 — Ingresos no constitutivos de renta",
            value=float(datos["ingresos"]["incrngo"]), step=1000.0, format="%.2f", key="i_incrngo")
    with col2:
        st.markdown("**Costos y deducciones**")
        datos["costos_gastos"]["costos"] = st.number_input(
            "Cas. 62 — Costos",
            value=float(datos["costos_gastos"]["costos"]), step=1000.0, format="%.2f", key="cg_costos")
        datos["costos_gastos"]["gastos_administracion"] = st.number_input(
            "Cas. 63 — Gastos de administración",
            value=float(datos["costos_gastos"]["gastos_administracion"]), step=1000.0, format="%.2f", key="cg_admin")
        datos["costos_gastos"]["gastos_ventas"] = st.number_input(
            "Cas. 64 — Gastos de distribución y ventas",
            value=float(datos["costos_gastos"]["gastos_ventas"]), step=1000.0, format="%.2f", key="cg_vtas")
        datos["costos_gastos"]["gastos_financieros"] = st.number_input(
            "Cas. 65 — Gastos financieros",
            value=float(datos["costos_gastos"]["gastos_financieros"]), step=1000.0, format="%.2f", key="cg_fin")
        datos["costos_gastos"]["otros_gastos"] = st.number_input(
            "Cas. 66 — Otros gastos",
            value=float(datos["costos_gastos"]["otros_gastos"]), step=1000.0, format="%.2f", key="cg_otros")

    st.divider()
    st.markdown("**Datos informativos (33-35)**")
    cI, cII, cIII = st.columns(3)
    with cI:
        datos["informativos"]["nomina_total"] = st.number_input(
            "Cas. 33 — Nómina",
            value=float(datos["informativos"]["nomina_total"]), step=1000.0, format="%.2f", key="inf_nomina")
    with cII:
        datos["informativos"]["seguridad_social"] = st.number_input(
            "Cas. 34 — Seguridad social",
            value=float(datos["informativos"]["seguridad_social"]), step=1000.0, format="%.2f", key="inf_ss")
    with cIII:
        datos["informativos"]["sena_icbf_caja"] = st.number_input(
            "Cas. 35 — SENA, ICBF, Caja",
            value=float(datos["informativos"]["sena_icbf_caja"]), step=1000.0, format="%.2f", key="inf_para")

    st.divider()
    st.markdown("**Retenciones (104-107)**")
    cR1, cR2, cR3 = st.columns(3)
    with cR1:
        datos["retenciones"]["autorretenciones"] = st.number_input(
            "Cas. 105 — Autorretenciones",
            value=float(datos["retenciones"]["autorretenciones"]), step=1000.0, format="%.2f", key="r_auto")
    with cR2:
        datos["retenciones"]["otras_retenciones"] = st.number_input(
            "Cas. 106 — Otras retenciones",
            value=float(datos["retenciones"]["otras_retenciones"]), step=1000.0, format="%.2f", key="r_otras")
    with cR3:
        datos["retenciones"]["saldo_favor_anterior"] = st.number_input(
            "Cas. 104 — Saldo a favor año anterior",
            value=float(datos["retenciones"]["saldo_favor_anterior"]), step=1000.0, format="%.2f", key="r_sfa")


# ============================================================
# TAB 4: CONCILIACIÓN FISCAL
# ============================================================
with tab_concil:
    st.subheader("Utilidad contable → Renta líquida fiscal")

    datos["conciliacion"]["utilidad_contable"] = st.number_input(
        "Utilidad contable antes de impuestos",
        value=float(datos["conciliacion"]["utilidad_contable"]),
        step=1000.0, format="%.2f", key="c_util",
        help="Estado de Resultados antes de la provisión 5405"
    )

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        datos["conciliacion"]["provision_renta_5405"] = st.number_input(
            "Provisión impuesto de renta (cuenta 5405)",
            value=float(datos["conciliacion"]["provision_renta_5405"]),
            step=1000.0, format="%.2f", key="c_5405",
            help="No deducible — Art. 115 ET"
        )
    with col2:
        datos["conciliacion"]["gmf_total"] = st.number_input(
            "GMF total certificado del año",
            value=float(datos["conciliacion"]["gmf_total"]),
            step=1000.0, format="%.2f", key="c_gmf",
            help="50% deducible — Art. 115 ET"
        )

    st.divider()
    st.markdown("**Partidas conciliatorias adicionales**")

    if datos["conciliacion"]["partidas_personalizadas"]:
        for i, partida in enumerate(datos["conciliacion"]["partidas_personalizadas"]):
            col_a, col_b, col_c, col_d = st.columns([3, 2, 1, 1])
            col_a.text(partida["nombre"])
            col_b.text(f"${partida['valor']:,.0f}")
            col_c.text("(+)" if partida["tipo"] == "aumenta" else "(-)")
            if col_d.button("🗑️", key=f"del_{i}"):
                datos["conciliacion"]["partidas_personalizadas"].pop(i)
                st.rerun()

    with st.expander("➕ Agregar partida"):
        catalogo_keys = list(CATALOGO_PARTIDAS_PERMANENTES.keys())
        opcion = st.selectbox("Tipo", ["Personalizada"] + catalogo_keys, key="np_opcion")

        if opcion in CATALOGO_PARTIDAS_PERMANENTES:
            tpl = CATALOGO_PARTIDAS_PERMANENTES[opcion]
            nombre = tpl["nombre"]
            tipo = tpl["direccion"]
            base_legal = tpl.get("base_legal", "")
            st.caption(f"Base legal: {base_legal}")
        else:
            nombre = st.text_input("Nombre", key="np_nombre")
            tipo = st.radio("Dirección", ["aumenta", "disminuye"], key="np_tipo", horizontal=True)
            base_legal = st.text_input("Base legal", key="np_base")

        valor = st.number_input("Valor", value=0.0, step=1000.0, format="%.2f", key="np_valor")

        if st.button("Agregar partida", key="btn_agregar") and nombre and valor > 0:
            datos["conciliacion"]["partidas_personalizadas"].append({
                "codigo": opcion if opcion != "Personalizada" else "CUSTOM",
                "nombre": nombre, "tipo": tipo, "valor": valor, "base_legal": base_legal,
            })
            st.rerun()


# ============================================================
# TAB 5: FORMULARIO 110
# ============================================================
with tab_f110:
    if st.button("🧮 Liquidar", type="primary", use_container_width=True):
        try:
            params = ParametrosLiquidacion()
            params.ano_gravable = ano_gravable
            liq = LiquidadorRenta(
                nit=empresa.get("nit", ""),
                razon_social=empresa.get("razon_social", ""),
                actividad_principal=empresa.get("ciiu_principal", ""),
                cod_seccional=empresa.get("cod_seccional_dian", ""),
                parametros=params,
            )

            liq.cargar_patrimonio(**datos["patrimonio"])
            liq.cargar_ingresos(**datos["ingresos"])
            liq.cargar_costos_y_gastos(**datos["costos_gastos"])
            liq.cargar_datos_informativos(**datos["informativos"])
            liq.cargar_retenciones(
                autorretenciones=datos["retenciones"]["autorretenciones"],
                otras_retenciones=datos["retenciones"]["otras_retenciones"],
            )
            liq.cargar_saldo_favor_ano_anterior(datos["retenciones"]["saldo_favor_anterior"])

            liq.set_utilidad_contable_antes_impuestos(datos["conciliacion"]["utilidad_contable"])
            if datos["conciliacion"]["provision_renta_5405"] > 0:
                liq.aplicar_provision_renta_no_deducible(datos["conciliacion"]["provision_renta_5405"])
            if datos["conciliacion"]["gmf_total"] > 0:
                liq.aplicar_gmf(datos["conciliacion"]["gmf_total"])

            for p in datos["conciliacion"]["partidas_personalizadas"]:
                liq.motor_conciliacion.agregar_partida(PartidaConciliatoria(
                    codigo=p["codigo"], nombre=p["nombre"], valor=p["valor"],
                    direccion=p["tipo"], base_legal=p.get("base_legal", ""),
                ))

            liq.liquidar()
            st.session_state[f"liq_{empresa_id}_{ano_gravable}"] = liq
            st.success("✓ Liquidación calculada")
        except Exception as e:
            st.error(f"Error en la liquidación: {e}")
            log.exception("Error liquidando")

    liq_key = f"liq_{empresa_id}_{ano_gravable}"
    if liq_key in st.session_state:
        liq = st.session_state[liq_key]
        d = liq.formulario.to_dict()

        kpi = st.columns(4)
        kpi[0].metric("Renta líquida gravable", f"${d['casilla_79_renta_liquida_gravable']:,.0f}")
        kpi[1].metric("Impuesto a cargo", f"${d['casilla_99_total_impuesto_a_cargo']:,.0f}")
        kpi[2].metric("Total retenciones", f"${d['casilla_107_total_retenciones']:,.0f}")
        sf = d['casilla_114_total_saldo_a_favor']
        sp = d['casilla_113_total_saldo_a_pagar']
        if sf > 0:
            kpi[3].metric("✅ Saldo a favor", f"${sf:,.0f}")
        else:
            kpi[3].metric("⚠️ Saldo a pagar", f"${sp:,.0f}")

        st.divider()
        import pandas as pd
        casillas = [
            ("44", "Total patrimonio bruto", d['casilla_44_total_patrimonio_bruto']),
            ("46", "Total patrimonio líquido", d['casilla_46_total_patrimonio_liquido']),
            ("58", "Total ingresos brutos", d['casilla_58_total_ingresos_brutos']),
            ("67", "Total costos y gastos deducibles", d['casilla_67_total_costos_gastos_deducibles']),
            ("72", "Renta líquida ordinaria", d['casilla_72_renta_liquida_ordinaria']),
            ("79", "Renta líquida gravable", d['casilla_79_renta_liquida_gravable']),
            ("99", "Total impuesto a cargo", d['casilla_99_total_impuesto_a_cargo']),
            ("107", "Total retenciones", d['casilla_107_total_retenciones']),
            ("113", "Total saldo a pagar", d['casilla_113_total_saldo_a_pagar']),
            ("114", "Total saldo a favor", d['casilla_114_total_saldo_a_favor']),
        ]
        df = pd.DataFrame(casillas, columns=["Casilla", "Concepto", "Valor"])
        df["Valor"] = df["Valor"].apply(lambda v: f"${v:,.0f}")
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            if st.button("📊 Generar Excel", use_container_width=True):
                ruta = Path(f"/tmp/Form110_{empresa_id}_{ano_gravable}.xlsx")
                generar_excel_comparativo(liquidador=liq, ruta_salida=ruta)
                with open(ruta, "rb") as f:
                    st.download_button(
                        "⬇️ Descargar Excel",
                        f.read(),
                        file_name=ruta.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
        with col_d2:
            if st.button("📄 Generar Word", use_container_width=True):
                ruta = Path(f"/tmp/Dictamen_{empresa_id}_{ano_gravable}.docx")
                try:
                    plazo = PLAZOS_PJ_AG2025.get(ultimo_digito) if isinstance(PLAZOS_PJ_AG2025, dict) else None
                    generar_dictamen_word(liquidador=liq, ruta_salida=ruta, plazo_fecha_limite=plazo)
                    with open(ruta, "rb") as f:
                        st.download_button(
                            "⬇️ Descargar Word",
                            f.read(),
                            file_name=ruta.name,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                        )
                except RuntimeError as e:
                    st.error(f"Word no disponible: {e}")
    else:
        st.info("Haz click en **Liquidar** para calcular el Formulario 110.")


# ============================================================
# TAB 6: HISTÓRICO (Supabase)
# ============================================================
with tab_persist:
    st.subheader("Histórico en Supabase")

    if not SUPABASE_DISPONIBLE:
        st.warning("Supabase no está disponible en este entorno.")
    else:
        sb = get_supabase_client()
        if sb is None:
            st.warning("Cliente Supabase no inicializado.")
        else:
            repo = RepositorioRenta(sb)
            liq_key = f"liq_{empresa_id}_{ano_gravable}"

            if liq_key not in st.session_state:
                st.info("Primero ejecuta la liquidación en la pestaña Formulario 110.")
            else:
                liq = st.session_state[liq_key]
                col_e1, col_e2 = st.columns([2, 1])
                with col_e1:
                    estado = st.selectbox("Estado", ["borrador", "revisado", "presentado"])
                    notas = st.text_area("Notas")
                with col_e2:
                    st.write("")
                    st.write("")
                    if st.button("💾 Guardar", type="primary", use_container_width=True):
                        try:
                            repo.guardar_liquidacion(
                                empresa_id=empresa_id,
                                nit=empresa.get("nit", ""),
                                ano_gravable=ano_gravable,
                                formulario=liq.formulario,
                                estado=estado,
                                notas=notas,
                            )
                            st.success("✓ Guardado en Supabase")
                        except Exception as e:
                            st.error(f"Error: {e}")

            st.divider()
            try:
                liquidaciones = repo.listar_liquidaciones(empresa_id)
                if liquidaciones:
                    import pandas as pd
                    df = pd.DataFrame([{
                        "Año": l.get("ano_gravable"),
                        "Estado": l.get("estado"),
                        "Saldo a favor": f"${l.get('casilla_114_total_saldo_a_favor', 0):,.0f}",
                        "Modificada": l.get("fecha_modificacion", "")[:10],
                    } for l in liquidaciones])
                    st.dataframe(df, use_container_width=True, hide_index=True)
                else:
                    st.info("Sin liquidaciones guardadas para esta empresa.")
            except Exception as e:
                st.error(f"Error consultando histórico: {e}")
