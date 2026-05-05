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
    ImportadorPILA,
    calcular_nomina_desde_balance,
    validar_pila_vs_balance,
    ImportadorCertificadosZIP,
    conciliar_certificados_vs_balance,
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

                # ==== PATRIMONIO (signo absoluto: pasivos vienen como crédito) ====
                # Cas 36 - Efectivo: cuenta 11 + algunos subgrupos de 12 (CDTs, fiducias)
                efectivo = balance.saldo_clase("11")
                # En el PUC oficial 1215, 1220, 1225, 1230, 1235, 1240, 1245, 1255 también
                # son "equivalentes" pero raramente aparecen en empresas comerciales pequeñas.
                # Para Quinto Sentidos solo aplica la 11 -> 72,242,897.

                # Cas 37 - Inversiones: solo subgrupos específicos de 12
                inversiones = balance.saldo_clase("12")

                # Cas 38 - Cuentas por cobrar: clase 13 EXCEPTO 1355 (anticipo impuestos -> Cas 43)
                cxc_total = balance.saldo_clase("13")
                anticipo_imptos = balance.saldo_grupo("1355")
                cxc = cxc_total - anticipo_imptos

                # Cas 39 - Inventarios: clase 14 EXCEPTO 1425, 1428, 1445 (biológicos)
                inv_total = balance.saldo_clase("14")
                biol_en_14 = (balance.saldo_grupo("1425")
                              + balance.saldo_grupo("1428")
                              + balance.saldo_grupo("1445"))
                inventarios = inv_total - biol_en_14

                # Cas 40 - Intangibles
                intangibles = balance.saldo_clase("16")

                # Cas 41 - Activos biológicos: cultivos/plantaciones/semovientes
                biologicos = (biol_en_14
                              + balance.saldo_grupo("1564")
                              + balance.saldo_grupo("1584"))

                # Cas 42 - PP&E: clase 15 EXCEPTO biológicos en 1564, 1584
                ppe_total = balance.saldo_clase("15")
                biol_en_15 = balance.saldo_grupo("1564") + balance.saldo_grupo("1584")
                ppe = ppe_total - biol_en_15

                # Cas 43 - Otros activos: 1355 + 17 + 18 + 19
                otros_activos = (anticipo_imptos
                                 + balance.saldo_clase("17")
                                 + balance.saldo_clase("18")
                                 + balance.saldo_clase("19"))

                pasivos = balance.saldo_clase("2")

                datos["patrimonio"]["efectivo"]      = abs(float(efectivo))
                datos["patrimonio"]["inversiones"]   = abs(float(inversiones))
                datos["patrimonio"]["cxc"]           = abs(float(cxc))
                datos["patrimonio"]["inventarios"]   = abs(float(inventarios))
                datos["patrimonio"]["intangibles"]   = abs(float(intangibles))
                datos["patrimonio"]["biologicos"]    = abs(float(biologicos))
                datos["patrimonio"]["ppe"]           = abs(float(ppe))
                datos["patrimonio"]["otros_activos"] = abs(float(otros_activos))
                datos["patrimonio"]["pasivos"]       = abs(float(pasivos))

                # ==== INGRESOS ====
                datos["ingresos"]["ingresos_ordinarios"] = abs(float(balance.saldo_clase("41")))
                # Cas 48: ingresos financieros (4210) + 43 si existe
                ing_fin = balance.saldo_grupo("4210") + balance.saldo_clase("43")
                datos["ingresos"]["ingresos_financieros"] = abs(float(ing_fin))
                # Cas 57: otros ingresos (clase 42 menos los financieros 4210)
                otros_ing = balance.saldo_clase("42") - balance.saldo_grupo("4210")
                datos["ingresos"]["otros_ingresos"] = abs(float(otros_ing))
                # Cas 59: devoluciones
                devs = (balance.saldo_grupo("4175")
                        + balance.saldo_grupo("4180")
                        + balance.saldo_grupo("4275"))
                datos["ingresos"]["devoluciones"] = abs(float(devs))

                # ==== COSTOS Y GASTOS ====
                # Cas 62: costos = clase 6 + clase 7 (costos de producción)
                costos = balance.saldo_clase("6") + balance.saldo_clase("7")
                datos["costos_gastos"]["costos"] = abs(float(costos))
                datos["costos_gastos"]["gastos_administracion"] = abs(float(balance.saldo_clase("51")))
                datos["costos_gastos"]["gastos_ventas"] = abs(float(balance.saldo_clase("52")))
                # Cas 65: gastos financieros (5305 son los financieros del PUC)
                datos["costos_gastos"]["gastos_financieros"] = abs(float(balance.saldo_grupo("5305")))
                # Cas 66: clase 53 EXCEPTO 5305 (financieros, ya van a Cas 65)
                otros_gtos = balance.saldo_clase("53") - balance.saldo_grupo("5305")
                datos["costos_gastos"]["otros_gastos"] = abs(float(otros_gtos))

                # ==== CONCILIACIÓN ====
                datos["conciliacion"]["provision_renta_5405"] = abs(float(balance.saldo_grupo("5405")))

                # ==== Validación cruzada: Cas 44 debe == cuenta 1 ====
                cuenta_1 = abs(float(balance.saldo_cuenta("1")))
                suma_36_43 = sum([
                    datos["patrimonio"]["efectivo"], datos["patrimonio"]["inversiones"],
                    datos["patrimonio"]["cxc"], datos["patrimonio"]["inventarios"],
                    datos["patrimonio"]["intangibles"], datos["patrimonio"]["biologicos"],
                    datos["patrimonio"]["ppe"], datos["patrimonio"]["otros_activos"],
                ])
                diferencia = cuenta_1 - suma_36_43
                if abs(diferencia) > 1:
                    st.warning(
                        f"⚠️ La suma de casillas 36–43 (${suma_36_43:,.0f}) no coincide con "
                        f"el activo total de la cuenta 1 (${cuenta_1:,.0f}). "
                        f"Diferencia: ${diferencia:,.0f}. Revisa cuentas no mapeadas."
                    )

                # Marcar balance importado y calcular nómina total (Cas. 33)
                datos["_balance_importado"] = True
                try:
                    nom = calcular_nomina_desde_balance(balance)
                    datos["informativos"]["nomina_total"] = float(nom["total"])
                    datos["_nomina_desglose"] = {
                        "admin": nom["admin"], "ventas": nom["ventas"],
                        "costos_72": nom["costos_72"], "costos_73": nom["costos_73"],
                    }
                except Exception as ex:
                    log.warning("No se pudo calcular nómina desde balance: %s", ex)

                # Las pestañas siguientes detectarán la flag _renta_just_imported
                # y reescribirán sus session_state desde datos[] al iniciar el render.

                # Guardar mensaje de éxito en session_state para que sobreviva al rerun
                st.session_state["_renta_import_msg"] = (
                    f"✓ Balance importado: {balance.razon_social} — "
                    f"{len(balance.cuentas)} cuentas. Patrimonio bruto: ${suma_36_43:,.0f}. "
                    "Revisa los valores en las pestañas siguientes."
                )
                # Flag para que las pestañas siguientes sepan que deben tomar
                # los valores nuevos de datos[] en vez de session_state
                st.session_state["_renta_just_imported"] = True
                st.rerun()

            except Exception as e:
                st.error(f"Error importando balance: {e}")
                log.exception("Error importando balance Siigo")

    # Mostrar mensaje persistente tras rerun
    if msg := st.session_state.pop("_renta_import_msg", None):
        st.success(msg)
    # Limpiar flag tras un render exitoso (para que próximas ediciones manuales
    # del usuario no se sobrescriban en el siguiente rerun)
    if st.session_state.get("_renta_just_imported"):
        st.session_state["_renta_just_imported"] = False

    # ========================================================
    # CARGADOR PILA (Planilla Integrada Liquidación de Aportes)
    # ========================================================
    st.divider()
    st.subheader("Importar PILA (opcional)")
    st.caption(
        "Sube el consolidado anual de planillas de seguridad social y "
        "parafiscales para auto-llenar las casillas 33, 34 y 35 del "
        "Formulario 110."
    )

    archivo_pila = st.file_uploader(
        "Planillas PILA (XLS/XLSX)",
        type=["xls", "xlsx"],
        key="pila_uploader",
        help="Archivo exportado del operador PILA (Aportes en Línea, SOI, etc.) "
             "con las hojas 'Consolidado, Seguridad Social' y 'Consolidado, Parafiscales'."
    )
    if archivo_pila is not None:
        if st.button("📥 Importar PILA", key="btn_importar_pila"):
            try:
                tmp_pila = Path("/tmp") / f"pila_{empresa_id}.{archivo_pila.name.rsplit('.',1)[-1]}"
                tmp_pila.write_bytes(archivo_pila.getvalue())

                imp_pila = ImportadorPILA()
                resumen_pila = imp_pila.importar(str(tmp_pila), ano_gravable=ano_gravable)

                # Llenar Cas. 34 y 35 (datos informativos)
                datos["informativos"]["seguridad_social"] = float(
                    resumen_pila.seguridad_social_empleador
                )
                datos["informativos"]["sena_icbf_caja"] = float(
                    resumen_pila.parafiscales
                )

                # Cas. 33: total nómina viene del balance, no de la PILA.
                # Si ya hay balance importado, lo calculamos automáticamente.
                # Si no, queda en 0 hasta que el usuario importe el balance.
                if datos.get("_balance_importado"):
                    # Re-importar balance para calcular nómina (cache simple)
                    try:
                        bal_path = Path("/tmp") / f"balance_{empresa_id}.xlsx"
                        if bal_path.exists():
                            bal = ImportadorBalanceSiigo().importar(str(bal_path))
                            nom = calcular_nomina_desde_balance(bal)
                            datos["informativos"]["nomina_total"] = float(nom["total"])
                            datos["_pila_validacion"] = validar_pila_vs_balance(resumen_pila, nom)
                            datos["_nomina_desglose"] = {
                                "admin": nom["admin"],
                                "ventas": nom["ventas"],
                                "costos_72": nom["costos_72"],
                                "costos_73": nom["costos_73"],
                            }
                    except Exception as ex:
                        log.warning("No se pudo cruzar PILA con balance: %s", ex)

                # Guardar resumen para mostrar detalle en la UI
                # Agrupar pagos por administradora para auditoría
                admins_dict = {}
                for p in resumen_pila.pagos:
                    key = (p.subsistema, p.administradora)
                    if key not in admins_dict:
                        admins_dict[key] = {"total": 0.0, "ibc": 0.0, "meses": 0}
                    admins_dict[key]["total"] += p.aporte_empleador
                    admins_dict[key]["ibc"] += p.ibc
                    admins_dict[key]["meses"] += 1
                admins_lista = [
                    {"subsistema": s, "administradora": a, **v}
                    for (s, a), v in sorted(admins_dict.items())
                ]

                datos["_pila_resumen"] = {
                    "pension": resumen_pila.pension,
                    "salud": resumen_pila.salud,
                    "riesgos": resumen_pila.riesgos,
                    "caja": resumen_pila.caja,
                    "sena": resumen_pila.sena,
                    "icbf": resumen_pila.icbf,
                    "total_planillas": resumen_pila.total_planillas,
                    "periodos": resumen_pila.periodos_cubiertos,
                    "por_mes_pension": resumen_pila.por_mes(["Pensión"]),
                    "por_mes_salud": resumen_pila.por_mes(["Salud"]),
                    "por_mes_arl": resumen_pila.por_mes(["Riesgos"]),
                    "por_mes_caja": resumen_pila.por_mes(["Cajas de compensación"]),
                    "administradoras": admins_lista,
                    "no_clasificadas": resumen_pila.administradoras_no_clasificadas,
                }

                # Mensaje de éxito persistente
                cas_34 = resumen_pila.seguridad_social_empleador
                cas_35 = resumen_pila.parafiscales
                if resumen_pila.total_planillas == 0:
                    st.session_state["_renta_pila_msg_warning"] = (
                        f"⚠️ El archivo PILA se procesó pero no se encontraron "
                        f"aportes para el año gravable {ano_gravable}. "
                        f"Verifica que el archivo cubra los períodos 202501 a 202512 "
                        f"(planillas pagadas entre febrero/{ano_gravable} y enero/{ano_gravable+1})."
                    )
                else:
                    st.session_state["_renta_pila_msg"] = (
                        f"✓ PILA importada: {resumen_pila.total_planillas} aportes individuales, "
                        f"{len(resumen_pila.periodos_cubiertos)} períodos. "
                        f"Cas. 34 (SS empleador): ${cas_34:,.0f}. "
                        f"Cas. 35 (parafiscales): ${cas_35:,.0f}."
                    )
                # Sincronizar widgets de informativos en la pestaña 3
                st.session_state["_renta_pila_imported"] = True
                st.rerun()

            except Exception as e:
                st.error(f"Error importando PILA: {e}")
                log.exception("Error importando PILA")

    # Mensajes persistentes PILA
    if msg := st.session_state.pop("_renta_pila_msg", None):
        st.success(msg)
    if msg := st.session_state.pop("_renta_pila_msg_warning", None):
        st.warning(msg)

    # Mostrar resumen + alertas si ya hay PILA cargada
    pila_resumen = datos.get("_pila_resumen")
    if pila_resumen:
        with st.expander("📋 Detalle de la PILA importada", expanded=False):
            colA, colB = st.columns(2)
            with colA:
                st.markdown("**Seguridad social (empleador)**")
                st.write(f"Pensión: ${pila_resumen['pension']:,.0f}")
                st.write(f"Salud: ${pila_resumen['salud']:,.0f}")
                st.write(f"ARL (Riesgos): ${pila_resumen['riesgos']:,.0f}")
                st.markdown(f"**Total Cas. 34: ${pila_resumen['pension']+pila_resumen['salud']+pila_resumen['riesgos']:,.0f}**")
            with colB:
                st.markdown("**Parafiscales**")
                st.write(f"Caja de Compensación: ${pila_resumen['caja']:,.0f}")
                st.write(f"SENA: ${pila_resumen['sena']:,.0f}")
                st.write(f"ICBF: ${pila_resumen['icbf']:,.0f}")
                st.markdown(f"**Total Cas. 35: ${pila_resumen['caja']+pila_resumen['sena']+pila_resumen['icbf']:,.0f}**")

            if pila_resumen['sena'] == 0 and pila_resumen['icbf'] == 0:
                st.info(
                    "ℹ️ SENA e ICBF en cero: empresa exonerada por la "
                    "Ley 1819/2016 (tarifa general de renta + empleados con salario "
                    "menor a 10 SMMLV)."
                )
            if pila_resumen.get('salud', 0) == 0 and pila_resumen.get('pension', 0) > 0:
                st.info(
                    "ℹ️ Salud en cero: empresa exonerada por la Ley 1819/2016. "
                    "El trabajador sigue aportando su 4% (descontado del salario), "
                    "pero ese aporte NO va en Cas. 34 porque no lo paga la empresa."
                )

            # Desglose por administradora (auditoría)
            admins = pila_resumen.get("administradoras", [])
            if admins:
                st.markdown("---")
                st.markdown("**Desglose por administradora**")
                try:
                    import pandas as pd
                    tabla_adm = pd.DataFrame([
                        {
                            "Subsistema": a["subsistema"],
                            "Administradora": a["administradora"],
                            "Meses": a["meses"],
                            "Aporte empleador": a["total"],
                        }
                        for a in admins
                    ])
                    fmt_adm = {"Aporte empleador": "${:,.0f}".format}
                    st.dataframe(
                        tabla_adm.style.format(fmt_adm),
                        use_container_width=True, hide_index=True
                    )
                except Exception:
                    pass

            # Administradoras no clasificadas (advertencia)
            no_clas = pila_resumen.get("no_clasificadas", [])
            if no_clas:
                st.warning(
                    "⚠️ Administradoras no clasificadas (revisar manualmente):\n"
                    + "\n".join(f"  - {a}" for a in no_clas)
                )

            # Tabla mensual estilo Anexo 21
            st.markdown("---")
            st.markdown("**Aportes por mes (estilo Anexo 21)**")
            try:
                import pandas as pd
                meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
                tabla = pd.DataFrame({
                    "Mes": meses,
                    "Pensión": [pila_resumen['por_mes_pension'].get(m, 0) for m in range(1,13)],
                    "Salud": [pila_resumen['por_mes_salud'].get(m, 0) for m in range(1,13)],
                    "ARL": [pila_resumen['por_mes_arl'].get(m, 0) for m in range(1,13)],
                    "Caja": [pila_resumen['por_mes_caja'].get(m, 0) for m in range(1,13)],
                })
                tabla["Total"] = tabla[["Pensión","Salud","ARL","Caja"]].sum(axis=1)
                # Formatear como pesos
                fmt = {c: "${:,.0f}".format for c in ["Pensión","Salud","ARL","Caja","Total"]}
                st.dataframe(tabla.style.format(fmt), use_container_width=True, hide_index=True)
            except Exception:
                pass

            # Validación cruzada con balance
            val = datos.get("_pila_validacion")
            if val:
                st.markdown("---")
                st.markdown("**Validación PILA vs Balance**")
                for info in val.get("info", []):
                    st.caption(info)
                for alerta in val.get("alertas", []):
                    st.warning(alerta)

    # ========================================================
    # CARGADOR ZIP DE CERTIFICADOS DE RETENCIÓN
    # ========================================================
    st.divider()
    st.subheader("Importar certificados de retención (ZIP)")
    st.caption(
        "Sube el ZIP con los certificados físicos (PDFs) y el Excel "
        "consolidado del contador. La app extrae las retenciones, las "
        "concilia contra la cuenta 195515 del balance y propone valores "
        "para Cas. 105 y 106 del Formulario 110."
    )

    archivo_zip = st.file_uploader(
        "Carpeta de certificados (ZIP)",
        type=["zip"],
        key="zip_certs_uploader",
        help="ZIP con PDFs de certificados de retención y Excel "
             "'LISTADO Y VALOR CERTIFICADOS'."
    )
    if archivo_zip is not None:
        if st.button("📥 Importar certificados", key="btn_importar_certs"):
            try:
                tmp_zip = Path("/tmp") / f"certs_{empresa_id}.zip"
                tmp_zip.write_bytes(archivo_zip.getvalue())

                imp_certs = ImportadorCertificadosZIP()
                resumen_certs = imp_certs.importar(str(tmp_zip))

                # Conciliar contra balance si está disponible
                conciliacion = None
                if datos.get("_balance_importado"):
                    bal_path = Path("/tmp") / f"balance_{empresa_id}.xlsx"
                    if bal_path.exists():
                        try:
                            bal = ImportadorBalanceSiigo().importar(str(bal_path))
                            conciliacion = conciliar_certificados_vs_balance(
                                resumen_certs, bal
                            )
                        except Exception as ex:
                            log.warning("No se pudo conciliar certificados: %s", ex)

                # Guardar todo en datos
                datos["_certs_resumen"] = {
                    "n_pdfs": len(resumen_certs.pdfs),
                    "n_pdfs_reteiva": len(resumen_certs.pdfs_reteiva),
                    "excel_encontrado": resumen_certs.excel_encontrado,
                    "n_certificados": len(resumen_certs.certificados),
                    "total_excel": resumen_certs.total_excel,
                    "total_excel_conciliado": resumen_certs.total_excel_conciliado,
                    "total_autorretencion": resumen_certs.total_autorretencion,
                    "total_retenciones": resumen_certs.total_retenciones,
                    "advertencias": resumen_certs.advertencias,
                    "nits_solo_pdf": sorted(resumen_certs.nits_solo_pdf),
                    "nits_solo_excel": sorted(resumen_certs.nits_solo_excel),
                    "certificados": [
                        {
                            "nit": c.nit_retenedor,
                            "retenedor": c.nombre_retenedor,
                            "concepto": c.concepto,
                            "valor": c.valor_retencion,
                            "puc": c.cuenta_puc or "",
                            "puc_origen": c.cuenta_puc_origen,
                            "saldo_contable": c.saldo_contable,
                            "total_certificado": c.total_certificado,
                            "diferencia": c.diferencia,
                            "accion": c.accion,
                        }
                        for c in resumen_certs.certificados
                    ],
                    "pdfs_lista": [
                        {
                            "nombre": p.nombre_archivo,
                            "tamano_kb": p.tamano_bytes / 1024,
                            "proveedor": p.proveedor_inferido,
                        }
                        for p in resumen_certs.pdfs
                    ],
                }
                if conciliacion:
                    datos["_certs_conciliacion"] = conciliacion

                # Pre-cargar valores sugeridos en datos["retenciones"]
                # Cas. 105: SIEMPRE del balance (Excel no trae autorretenciones)
                # Cas. 106: por defecto contable, usuario puede cambiar después
                if conciliacion:
                    datos["retenciones"]["autorretenciones"] = float(
                        conciliacion["total_105_contable"]
                    )
                    if "_cas_106_origen" not in datos:
                        datos["retenciones"]["otras_retenciones"] = float(
                            conciliacion["total_106_contable"]
                        )
                        datos["_cas_106_origen"] = "contable"

                # Mensaje de éxito
                cas_106 = conciliacion["total_106_contable"] if conciliacion else resumen_certs.total_retenciones
                cas_105 = conciliacion["total_105_contable"] if conciliacion else 0
                st.session_state["_renta_certs_msg"] = (
                    f"✓ Certificados importados: {len(resumen_certs.pdfs)} PDFs, "
                    f"{len(resumen_certs.certificados)} en Excel. "
                    f"Cas. 105 (autorretenciones, contable): ${cas_105:,.0f}. "
                    f"Cas. 106 (retenciones, contable): ${cas_106:,.0f}."
                )
                st.session_state["_renta_certs_imported"] = True
                st.rerun()

            except Exception as e:
                st.error(f"Error importando certificados: {e}")
                log.exception("Error importando certificados")

    # Mensajes persistentes certificados
    if msg := st.session_state.pop("_renta_certs_msg", None):
        st.success(msg)

    # Mostrar detalle si hay certificados cargados
    certs_data = datos.get("_certs_resumen")
    if certs_data:
        with st.expander("📑 Detalle de certificados de retención", expanded=False):
            colA, colB = st.columns(2)
            colA.metric("PDFs retención fuente", certs_data["n_pdfs"])
            colB.metric("PDFs reteIVA (excluidos)", certs_data["n_pdfs_reteiva"])
            if not certs_data["excel_encontrado"]:
                st.error(
                    "❌ No se encontró el Excel 'LISTADO Y VALOR CERTIFICADOS' "
                    "en el ZIP. Sin él no hay conciliación automática."
                )
            else:
                st.caption(f"✓ Excel del contador detectado con "
                           f"{certs_data['n_certificados']} certificados.")

            # Advertencias
            for a in certs_data.get("advertencias", []):
                st.warning(a)

            # Lista de certificados
            if certs_data.get("certificados"):
                st.markdown("**Certificados leídos del Excel**")
                try:
                    import pandas as pd
                    df_certs = pd.DataFrame(certs_data["certificados"])
                    df_certs["puc_display"] = df_certs.apply(
                        lambda r: f"{r['puc']} ({r['puc_origen']})" if r['puc'] else "Sin clasificar",
                        axis=1
                    )
                    df_show = df_certs[["nit", "retenedor", "concepto", "valor", "puc_display", "accion"]].copy()
                    df_show.columns = ["NIT", "Retenedor", "Concepto", "Valor", "Cuenta PUC", "Acción"]
                    st.dataframe(
                        df_show.style.format({"Valor": "${:,.0f}".format}),
                        use_container_width=True, hide_index=True,
                    )
                except Exception:
                    pass

            # Conciliación contra balance
            concil = datos.get("_certs_conciliacion")
            if concil:
                st.markdown("---")
                st.markdown("### 🔍 Conciliación contable vs certificados")

                # Tabla 106
                st.markdown("**Cas. 106 — Otras retenciones (cuenta 195515)**")
                try:
                    import pandas as pd
                    df_106 = pd.DataFrame(concil["conciliacion_106"])
                    df_106.columns = ["Cuenta PUC", "Saldo contable", "Suma certificados", "Diferencia"]
                    st.dataframe(
                        df_106.style.format({
                            "Saldo contable": "${:,.0f}".format,
                            "Suma certificados": "${:,.0f}".format,
                            "Diferencia": "${:,.0f}".format,
                        }),
                        use_container_width=True, hide_index=True,
                    )
                except Exception:
                    pass

                # Tres opciones para Cas. 106
                st.markdown("**Selecciona qué valor usar para Cas. 106:**")
                opciones_106 = {
                    "contable": (
                        "📊 Contable (balance 195515)",
                        concil["total_106_contable"],
                        "Suma directa del balance. Lo que dice tu contabilidad."
                    ),
                    "certificados": (
                        "📑 Certificados (Excel)",
                        concil["total_106_certificados"],
                        "Suma de los certificados físicos digitados en el Excel."
                    ),
                    "excel_conciliado": (
                        "✏️ Excel-conciliado (Total_Cert)",
                        concil["total_106_excel_conciliado"],
                        "Lo que el contador propone tras revisar los soportes."
                    ),
                }
                origen_actual = datos.get("_cas_106_origen", "contable")
                col_op = st.columns(3)
                for i, (key, (label, valor, descr)) in enumerate(opciones_106.items()):
                    with col_op[i]:
                        seleccionado = origen_actual == key
                        if st.button(
                            f"{label}\n${valor:,.0f}",
                            key=f"btn_106_{key}",
                            type="primary" if seleccionado else "secondary",
                            use_container_width=True,
                        ):
                            datos["retenciones"]["otras_retenciones"] = float(valor)
                            datos["_cas_106_origen"] = key
                            st.session_state["_renta_just_imported"] = True
                            st.rerun()
                        st.caption(descr)
                st.caption(f"Valor actualmente seleccionado: **{opciones_106[origen_actual][0]}** "
                           f"= ${opciones_106[origen_actual][1]:,.0f}")

                # Tabla 105 (autorretenciones)
                st.markdown("**Cas. 105 — Autorretenciones (cuenta 195519)**")
                try:
                    import pandas as pd
                    df_105 = pd.DataFrame(concil["conciliacion_105"])
                    if not df_105.empty:
                        df_105.columns = ["Cuenta PUC", "Saldo contable", "Suma certificados", "Diferencia"]
                        st.dataframe(
                            df_105.style.format({
                                "Saldo contable": "${:,.0f}".format,
                                "Suma certificados": "${:,.0f}".format,
                                "Diferencia": "${:,.0f}".format,
                            }),
                            use_container_width=True, hide_index=True,
                        )
                except Exception:
                    pass
                st.info(
                    f"ℹ️ Cas. 105 se carga directo del balance: "
                    f"**${concil['total_105_contable']:,.0f}**. "
                    "Las autorretenciones especiales rara vez se certifican externamente — "
                    "vienen del cálculo propio de la empresa."
                )

            # Inventario de PDFs
            if certs_data.get("pdfs_lista"):
                st.markdown("---")
                st.markdown(f"**Inventario de PDFs ({len(certs_data['pdfs_lista'])} archivos)**")
                try:
                    import pandas as pd
                    df_pdfs = pd.DataFrame(certs_data["pdfs_lista"])
                    df_pdfs.columns = ["Archivo", "Tamaño (KB)", "Proveedor inferido"]
                    st.dataframe(
                        df_pdfs.style.format({"Tamaño (KB)": "{:.1f}".format}),
                        use_container_width=True, hide_index=True,
                    )
                except Exception:
                    pass

    # ========================================================
    # PRÓXIMAMENTE: declaración año anterior
    # ========================================================
    st.divider()
    st.subheader("📑 Próximamente")
    st.caption("Esta funcionalidad se habilitará en próximas iteraciones:")
    st.markdown(
        "**Declaración de renta año anterior**  \n"
        "Para auto-llenar Cas. 104 (saldo a favor año anterior) "
        "directamente del Formulario 110 del año pasado."
    )


# ============================================================
# TAB 2: PATRIMONIO
# ============================================================
with tab_balance:
    st.subheader("Patrimonio al cierre")
    st.caption("Casillas 36 a 46 del Formulario 110")

    # Mapeo (widget_key, datos_key). Sincronizamos session_state desde datos[]
    # ANTES de renderizar los widgets, para que tras un import los inputs
    # muestren los valores nuevos en lugar de los anteriores cacheados.
    _pat_widgets = [
        ("p_efec", "efectivo"), ("p_inv", "inversiones"),
        ("p_cxc", "cxc"), ("p_inventarios", "inventarios"),
        ("p_intang", "intangibles"), ("p_biol", "biologicos"),
        ("p_ppe", "ppe"), ("p_otros", "otros_activos"),
        ("p_pasivos", "pasivos"),
    ]
    for wkey, dkey in _pat_widgets:
        if st.session_state.get("_renta_just_imported"):
            st.session_state[wkey] = float(datos["patrimonio"][dkey])
        elif wkey not in st.session_state:
            st.session_state[wkey] = float(datos["patrimonio"][dkey])

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Activos corrientes**")
        st.number_input("Cas. 36 — Efectivo y equivalentes",
            step=1000.0, format="%.2f", key="p_efec")
        st.number_input("Cas. 37 — Inversiones",
            step=1000.0, format="%.2f", key="p_inv")
        st.number_input("Cas. 38 — Cuentas y documentos por cobrar",
            step=1000.0, format="%.2f", key="p_cxc")
        st.number_input("Cas. 39 — Inventarios",
            step=1000.0, format="%.2f", key="p_inventarios")
    with col2:
        st.markdown("**Activos no corrientes**")
        st.number_input("Cas. 40 — Intangibles",
            step=1000.0, format="%.2f", key="p_intang")
        st.number_input("Cas. 41 — Activos biológicos",
            step=1000.0, format="%.2f", key="p_biol")
        st.number_input("Cas. 42 — Propiedades, planta y equipo",
            step=1000.0, format="%.2f", key="p_ppe")
        st.number_input("Cas. 43 — Otros activos",
            step=1000.0, format="%.2f", key="p_otros")

    st.divider()
    st.number_input("Cas. 45 — Pasivos",
        step=1000.0, format="%.2f", key="p_pasivos")

    # Después de renderizar, copiar valores desde session_state a datos[]
    # para que persistan entre tabs y reruns.
    for wkey, dkey in _pat_widgets:
        datos["patrimonio"][dkey] = float(st.session_state[wkey])

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
    # Sincronización pre-render para que tras un import los inputs se actualicen
    _ing_widgets = [
        ("i_ord", "ingresos_ordinarios"), ("i_fin", "ingresos_financieros"),
        ("i_otros", "otros_ingresos"), ("i_dev", "devoluciones"),
        ("i_incrngo", "incrngo"),
    ]
    _cg_widgets = [
        ("cg_costos", "costos"), ("cg_admin", "gastos_administracion"),
        ("cg_vtas", "gastos_ventas"), ("cg_fin", "gastos_financieros"),
        ("cg_otros", "otros_gastos"),
    ]
    just_imported = st.session_state.get("_renta_just_imported", False)
    for wkey, dkey in _ing_widgets:
        if just_imported:
            st.session_state[wkey] = float(datos["ingresos"][dkey])
        elif wkey not in st.session_state:
            st.session_state[wkey] = float(datos["ingresos"][dkey])
    for wkey, dkey in _cg_widgets:
        if just_imported:
            st.session_state[wkey] = float(datos["costos_gastos"][dkey])
        elif wkey not in st.session_state:
            st.session_state[wkey] = float(datos["costos_gastos"][dkey])

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Ingresos**")
        st.number_input("Cas. 47 — Ingresos brutos actividades ordinarias",
            step=1000.0, format="%.2f", key="i_ord")
        st.number_input("Cas. 48 — Ingresos financieros",
            step=1000.0, format="%.2f", key="i_fin")
        st.number_input("Cas. 57 — Otros ingresos",
            step=1000.0, format="%.2f", key="i_otros")
        st.number_input("Cas. 59 — Devoluciones, rebajas y descuentos",
            step=1000.0, format="%.2f", key="i_dev")
        st.number_input("Cas. 60 — Ingresos no constitutivos de renta",
            step=1000.0, format="%.2f", key="i_incrngo")
    with col2:
        st.markdown("**Costos y deducciones**")
        st.number_input("Cas. 62 — Costos",
            step=1000.0, format="%.2f", key="cg_costos")
        st.number_input("Cas. 63 — Gastos de administración",
            step=1000.0, format="%.2f", key="cg_admin")
        st.number_input("Cas. 64 — Gastos de distribución y ventas",
            step=1000.0, format="%.2f", key="cg_vtas")
        st.number_input("Cas. 65 — Gastos financieros",
            step=1000.0, format="%.2f", key="cg_fin")
        st.number_input("Cas. 66 — Otros gastos",
            step=1000.0, format="%.2f", key="cg_otros")

    # Copiar de vuelta a datos[] tras el render
    for wkey, dkey in _ing_widgets:
        datos["ingresos"][dkey] = float(st.session_state[wkey])
    for wkey, dkey in _cg_widgets:
        datos["costos_gastos"][dkey] = float(st.session_state[wkey])

    st.divider()
    st.markdown("**Datos informativos (33-35)**")

    # Sincronización pre-render (igual patrón que patrimonio/ingresos)
    _inf_widgets = [
        ("inf_nomina", "nomina_total"),
        ("inf_ss", "seguridad_social"),
        ("inf_para", "sena_icbf_caja"),
    ]
    _ret_widgets = [
        ("r_auto", "autorretenciones"),
        ("r_otras", "otras_retenciones"),
        ("r_sfa", "saldo_favor_anterior"),
    ]
    pila_imp = st.session_state.pop("_renta_pila_imported", False)
    certs_imp = st.session_state.pop("_renta_certs_imported", False)
    just_imp = just_imported or pila_imp or certs_imp
    for wkey, dkey in _inf_widgets:
        if just_imp or wkey not in st.session_state:
            st.session_state[wkey] = float(datos["informativos"][dkey])
    for wkey, dkey in _ret_widgets:
        if just_imp or wkey not in st.session_state:
            st.session_state[wkey] = float(datos["retenciones"].get(dkey, 0))

    cI, cII, cIII = st.columns(3)
    with cI:
        st.number_input("Cas. 33 — Nómina",
            step=1000.0, format="%.2f", key="inf_nomina")
    with cII:
        st.number_input("Cas. 34 — Seguridad social",
            step=1000.0, format="%.2f", key="inf_ss")
    with cIII:
        st.number_input("Cas. 35 — SENA, ICBF, Caja",
            step=1000.0, format="%.2f", key="inf_para")

    # Copiar de vuelta
    for wkey, dkey in _inf_widgets:
        datos["informativos"][dkey] = float(st.session_state[wkey])

    st.divider()
    st.markdown("**Retenciones (104-107)**")
    cR1, cR2, cR3 = st.columns(3)
    with cR1:
        st.number_input("Cas. 105 — Autorretenciones",
            step=1000.0, format="%.2f", key="r_auto")
    with cR2:
        st.number_input("Cas. 106 — Otras retenciones",
            step=1000.0, format="%.2f", key="r_otras")
    with cR3:
        st.number_input("Cas. 104 — Saldo a favor año anterior",
            step=1000.0, format="%.2f", key="r_sfa")

    # Copiar de vuelta retenciones
    for wkey, dkey in _ret_widgets:
        datos["retenciones"][dkey] = float(st.session_state[wkey])


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
