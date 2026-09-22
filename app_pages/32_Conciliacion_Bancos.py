"""
app_pages/32_Conciliacion_Bancos.py

Conciliación bancaria: cruza el AUXILIAR general (libros) con el REPORTE del
banco (con N COMPROBANTE) y el DATÁFONO (Credibanco), y arma el cuadro de
conciliación por cuenta (saldo libros ± consignaciones/pagos/notas débito =
saldo a cierre − consignaciones en tránsito = saldo del banco).

Config por empresa (tabla conciliacion_bancos, migración 021).
Depende de: core/conciliacion/conciliador.py · requirements: openpyxl
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Conciliación de bancos", page_icon="🔁", layout="wide")
from auth.guard import guard_empresa
from core.conciliacion import conciliador as C
try:
    from core.procesadores import extractos_bancarios_multi as ebm  # config Bancos a Contai
except Exception:  # noqa: BLE001
    ebm = None

st.title("🔁 Conciliación de bancos")
emp, sb = guard_empresa()
bancos = C.cargar_bancos(sb, emp["id"])

tab_c, tab_todo, tab_cfg = st.tabs(["🔁 Conciliar (uno)", "🧮 Conciliar todo", "⚙️ Configuración"])

# ---- Configuración primero: así SIEMPRE se dibuja aunque no haya bancos ----
with tab_cfg:
    st.markdown("#### 🏦 Bancos a conciliar")
    st.caption("Por cada banco: el prefijo de la **cuenta del auxiliar** (la cuenta "
               "puente, p.ej. 11-10-05-99) y el **nombre de la hoja** del reporte del "
               "banco. Marca **usa datáfono** solo en la cuenta que recibe el recaudo "
               "de Credibanco (la 4451); los demás se concilian sin datáfono.")
    filas = bancos or [{"nombre": "", "cuenta_auxiliar": "", "hoja_reporte": "", "usa_datafono": False}]
    df = pd.DataFrame([{"nombre": b.get("nombre", ""), "cuenta_auxiliar": b.get("cuenta_auxiliar", ""),
                        "hoja_reporte": b.get("hoja_reporte", ""),
                        "usa_datafono": C.usa_datafono(b)} for b in filas])
    ed = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="cfg_conc",
                        column_config={
                            "nombre": st.column_config.TextColumn("Banco / cuenta", required=True),
                            "cuenta_auxiliar": st.column_config.TextColumn("Cuenta auxiliar (prefijo)", required=True),
                            "hoja_reporte": st.column_config.TextColumn("Hoja del reporte", required=True),
                            "usa_datafono": st.column_config.CheckboxColumn("Usa datáfono (Credibanco)"),
                        })
    cbb = st.columns(2)
    if cbb[0].button("💾 Guardar bancos", type="primary"):
        n = C.guardar_bancos(sb, emp["id"], ed.to_dict("records"))
        st.success(f"{n} bancos guardados."); st.rerun()
    if cbb[1].button("🌱 Sembrar GRUPO DE LOLITA"):
        n = C.sembrar_lolita(sb, emp["id"])
        st.success(f"Sembrados {n} bancos. Ajusta la cuenta auxiliar / hoja si aplica."); st.rerun()

    st.divider()
    st.markdown("#### 💳 Datáfono Credibanco — MAESTRO (establecimiento → centro de costo)")
    st.caption("Con este maestro INTEGRAL calcula la comisión y las retenciones "
               "**directamente desde el archivo original de Credibanco**, agrupando "
               "cada CÓDIGO DE ESTABLECIMIENTO en su centro de costo. Es la misma "
               "relación de la macro (hoja MAESTRO).")
    maes_filas = C.cargar_maestro_filas(sb, emp["id"])
    dfm = pd.DataFrame(maes_filas or [{"establecimiento": "", "cc": "", "oasis": ""}])
    edm = st.data_editor(dfm, num_rows="dynamic", use_container_width=True, key="cfg_maestro",
                         column_config={
                             "establecimiento": st.column_config.TextColumn("Código establecimiento", required=True),
                             "cc": st.column_config.TextColumn("Centro de costo", required=True),
                             "oasis": st.column_config.TextColumn("Punto / OASIS"),
                         })
    cm = st.columns(3)
    if cm[0].button("💾 Guardar maestro", type="primary"):
        n = C.guardar_maestro(sb, emp["id"], edm.to_dict("records"))
        st.success(f"{n} establecimientos guardados."); st.rerun()
    if cm[1].button("🌱 Sembrar GRUPO DE LOLITA (maestro)"):
        n = C.sembrar_maestro_lolita(sb, emp["id"])
        st.success(f"Sembrados {n} establecimientos."); st.rerun()
    f_macro = cm[2].file_uploader("Importar maestro desde la macro (.xlsm)",
                                  type=["xlsm", "xlsx"], key="cfg_macro_maestro",
                                  label_visibility="collapsed")
    if f_macro is not None:
        try:
            m = C.maestro_desde_bytes(f_macro.getvalue())
            if m:
                n = C.guardar_maestro_dict(sb, emp["id"], m)
                st.success(f"Importados {n} establecimientos desde la macro."); st.rerun()
            else:
                st.warning("No encontré la hoja MAESTRO (CODIGO ESTABLECIMIENTO / "
                           "CENTRO DE COSTO) en ese archivo.")
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude importar el maestro: {e}")
    st.caption("💡 Si tu archivo original ya trae el centro de costo en la columna "
               "«NO TERMINAL», el cálculo funciona aunque el maestro esté vacío; el "
               "maestro sirve para forzar el mapeo y mostrar el nombre del punto.")

# ===================================================================
# CONCILIAR TODO (todos los bancos de una sola vez)
# ===================================================================
with tab_todo:
  if not bancos:
    st.info("Esta empresa no tiene bancos configurados. Ve a «Configuración».")
  else:
    st.markdown("#### 1. Sube los archivos del mes (una sola vez para todos)")
    ta, tb, tc = st.columns(3)
    with ta:
        f_aux_t = st.file_uploader("Auxiliar general (.xlsx)", type=["xlsx"], key="ct_aux")
    with tb:
        f_rep_t = st.file_uploader("Reportes de los bancos (.xlsx, varios)",
                                   type=["xlsx"], accept_multiple_files=True, key="ct_rep")
        st.caption("Sube uno o varios archivos; cada banco se busca por el **nombre de "
                   "su hoja** configurada.")
    with tc:
        f_data_t = st.file_uploader("Datáfono Credibanco (solo 4451)",
                                    type=["xlsm", "xlsx"], key="ct_data")
        st.caption("El recaudo por datáfono **solo se aplica** a los bancos marcados "
                   "«usa datáfono» en Configuración (la 4451).")

    periodo_t = st.text_input("Periodo (encabezado de los documentos)", "", key="ct_per")

    # índice hoja -> archivo y saldo del extracto (FINAL) detectado al pie de cada hoja
    hoja_idx, saldo_map = {}, {}
    if f_rep_t:
        for f in f_rep_t:
            data = f.getvalue()
            for h in C.hojas_de(data):
                hoja_idx.setdefault(h.strip().upper(), data)
    # tabla editable con saldo y tránsito por banco
    st.markdown("#### 2. Saldo del extracto y tránsito por banco")
    st.caption("El **saldo del extracto** se detecta automáticamente del pie de "
               "cada hoja (bloque INICIAL/DÉBITOS/CRÉDITOS/FINAL); puedes ajustarlo.")
    base = []
    for b in bancos:
        hoja = b.get("hoja_reporte", "").strip()
        fbytes = hoja_idx.get(hoja.upper())
        sal = 0.0
        if fbytes is not None:
            det = C.saldo_extracto_de(fbytes, hoja)
            if det.get("final") is not None:
                sal = round(det["final"], 2)
        base.append({"banco": b["nombre"], "cuenta_auxiliar": b.get("cuenta_auxiliar", ""),
                     "hoja_reporte": hoja, "usa_datafono": C.usa_datafono(b),
                     "saldo_extracto": sal, "transito_real": 0.0})
    dft = pd.DataFrame(base)
    edt = st.data_editor(
        dft, use_container_width=True, key="ct_tabla", hide_index=True,
        column_config={
            "banco": st.column_config.TextColumn("Banco", disabled=True),
            "cuenta_auxiliar": st.column_config.TextColumn("Cuenta aux.", disabled=True),
            "hoja_reporte": st.column_config.TextColumn("Hoja reporte", disabled=True),
            "usa_datafono": st.column_config.CheckboxColumn("Datáfono"),
            "saldo_extracto": st.column_config.NumberColumn("Saldo extracto", format="%.2f"),
            "transito_real": st.column_config.NumberColumn("Tránsito real (0=auto)", format="%.2f"),
        })
    tol_t = st.number_input("Tolerancia ajuste al peso (±)", value=10000.0, step=1000.0,
                            format="%.2f", key="ct_tol")

    if st.button("🧮 Conciliar todo", type="primary",
                 disabled=(f_aux_t is None or not f_rep_t)):
        aux_bytes = f_aux_t.getvalue()
        maestro = C.cargar_maestro(sb, emp["id"])
        data_df = f_data_t.getvalue() if f_data_t else None
        resultados, avisos = [], []
        for row in edt.to_dict("records"):
            hoja = str(row["hoja_reporte"]).strip()
            fbytes = hoja_idx.get(hoja.upper())
            if fbytes is None:
                avisos.append(f"• {row['banco']}: no encontré la hoja «{hoja}» en los archivos subidos.")
                continue
            try:
                aux = C.leer_auxiliar(aux_bytes, row["cuenta_auxiliar"])
                banco = C.leer_banco(fbytes, hoja)
                usa_df = bool(row.get("usa_datafono"))
                data = C.leer_datafono(data_df, maestro=maestro) if (usa_df and data_df) else \
                    {"por_cc": [], "comision": 0.0, "retefuente": 0.0, "reteiva": 0.0, "reteica": 0.0}
                tr = float(row.get("transito_real") or 0) or None
                r = C.conciliar(aux, banco, data, float(row.get("saldo_extracto") or 0),
                                transito_real=tr, tolerancia=tol_t)
                resultados.append({"banco": row["banco"], "cuenta": row["cuenta_auxiliar"], "r": r})
            except Exception as e:  # noqa: BLE001
                avisos.append(f"• {row['banco']}: error — {e}")
        st.session_state["ct_res"] = resultados
        st.session_state["ct_avisos"] = avisos
        st.session_state["ct_periodo"] = periodo_t

    resultados = st.session_state.get("ct_res")
    if resultados is not None:
        for a in st.session_state.get("ct_avisos", []):
            st.warning(a)
        if resultados:
            resumen = []
            for res in resultados:
                r = res["r"]
                dif = round((r["saldo_cierre"] - r["consignaciones_transito"]) - r["saldo_banco"], 2)
                resumen.append({"Banco": res["banco"], "Saldo libros": r["saldo_ant"],
                                "Consignaciones (abonos)": r["consignaciones"],
                                "Pagos": -r["pagos"], "Notas débito": -r["notas_debito"],
                                "Saldo a cierre": r["saldo_cierre"],
                                "Tránsito": -r["consignaciones_transito"], "Saldo extracto": r["saldo_banco"],
                                "Diferencia": dif, "Cuadra": "SÍ" if r["cuadra"] else "NO"})
            dfr = pd.DataFrame(resumen)
            numcols = [c for c in dfr.columns if c not in ("Banco", "Cuadra")]
            st.markdown("#### Resumen consolidado")
            st.dataframe(dfr.style.format({c: "{:,.2f}" for c in numcols}),
                         use_container_width=True, hide_index=True)
            per = st.session_state.get("ct_periodo", "")
            dd = st.columns(2)
            try:
                xlsx = C.exportar_excel_consolidado(resultados, empresa=emp.get("razon_social", ""), periodo=per)
                dd[0].download_button("⬇ Consolidado (Excel)", data=xlsx, type="primary",
                                      use_container_width=True,
                                      file_name=f"conciliacion_consolidada_{per or 'mes'}.xlsx",
                                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception as e:  # noqa: BLE001
                dd[0].error(f"Excel: {e}")
            try:
                pdfb = C.exportar_pdf_consolidado(resultados, empresa=emp.get("razon_social", ""),
                                                  periodo=per, usuario=st.session_state.get("user_email", ""))
                dd[1].download_button("⬇ Consolidado (PDF con firma)", data=pdfb,
                                      use_container_width=True,
                                      file_name=f"conciliacion_consolidada_{per or 'mes'}.pdf",
                                      mime="application/pdf")
            except Exception as e:  # noqa: BLE001
                dd[1].error(f"PDF: {e}")
            for res in resultados:
                with st.expander(f"Detalle — {res['banco']}"):
                    rr = res["r"]
                    st.dataframe(pd.DataFrame([
                        ("SALDO EN LIBROS", rr["saldo_ant"]),
                        ("(−) NOTAS DÉBITO", -rr["notas_debito"]),
                        ("(=) SALDO A CIERRE", rr["saldo_cierre"]),
                        ("(−) CONSIGNACIONES EN TRÁNSITO", -rr["consignaciones_transito"]),
                        ("(=) SALDO SEGÚN EXTRACTO", rr["saldo_banco"]),
                    ], columns=["Concepto", "Valor"]).style.format({"Valor": "{:,.2f}"}),
                        use_container_width=True, hide_index=True)
                    if rr.get("pend_transito"):
                        st.caption("Consignaciones en tránsito (libros → mes siguiente):")
                        dt = pd.DataFrame(rr["pend_transito"])[
                            ["documento", "tipo", "centro_costo", "punto", "fecha", "valor"]]
                        st.dataframe(dt.style.format({"valor": "{:,.2f}"}),
                                     use_container_width=True, hide_index=True)

            # ---- PLANO DE GASTOS CONSOLIDADO (todos los bancos) ----
            st.markdown("#### 🧾 Plano de gastos consolidado (todos los bancos)")
            st.caption("Extrae los gastos bancarios de **todos** los bancos y los "
                       "reparte en partes iguales entre los centros de costo; el "
                       "datáfono va por centro de costo solo donde aplica (4451). "
                       "Cada banco se acredita contra **su propia cuenta puente**.")
            centros_rep, cuentas_g, puc_map = [], dict(C.CUENTAS_GASTO_DEF), {}
            if ebm is not None:
                try:
                    centros_rep = ebm.cargar_centros(sb, emp["id"])
                    cuentas_g = C.cuentas_gasto_desde_reglas(ebm.cargar_reglas(sb, emp["id"]))
                    for bb in ebm.cargar_bancos(sb, emp["id"]):
                        puc_map[bb.get("nombre", "").strip().upper()] = str(bb.get("cuenta_puc") or "").strip()
                except Exception:  # noqa: BLE001
                    pass
            # tabla editable banco -> cuenta puente
            puc_rows = [{"banco": res["banco"],
                         "cuenta_puc": puc_map.get(res["banco"].strip().upper(), "")}
                        for res in resultados]
            st.caption("Cuenta puente (contrapartida) por banco — de «Bancos a Contai»; edítala si hace falta:")
            edp = st.data_editor(pd.DataFrame(puc_rows), hide_index=True,
                                 use_container_width=True, key="ct_puc",
                                 column_config={
                                     "banco": st.column_config.TextColumn("Banco", disabled=True),
                                     "cuenta_puc": st.column_config.TextColumn("Cuenta puente"),
                                 })
            pcol = st.columns(4)
            comp_c = pcol[0].text_input("Comprobante", "10", key="ct_pl_comp")
            doc_c = pcol[1].text_input("Documento", "1", key="ct_pl_doc")
            fec_c = pcol[2].date_input("Fecha del asiento", format="MM/DD/YYYY", key="ct_pl_fec")
            cc_ctxt = pcol[3].text_input("Centros (coma) — vacío usa config", "", key="ct_pl_cc")
            cc_list = [x.strip() for x in cc_ctxt.split(",") if x.strip()] or centros_rep or \
                ["100401", "100501", "100601", "100901", "101201", "101301", "101801", "103001"]
            if st.button("🧾 Generar plano consolidado", key="ct_pl_btn"):
                puc_por_banco = {r["banco"]: r["cuenta_puc"] for r in edp.to_dict("records")}
                pc = C.generar_plano_gastos_consolidado(
                    resultados, cc_list, puc_por_banco, cuentas_gasto=cuentas_g,
                    comprobante=comp_c, documento=doc_c, fecha=fec_c.strftime("%m/%d/%Y"))
                st.session_state["ct_plano"] = {
                    "pc": pc, "txt": C.plano_a_texto(pc["filas"]),
                    "fname": f"plano_gastos_consolidado_{per or 'mes'}.txt"}
            planoc = st.session_state.get("ct_plano")
            if planoc:
                pc = planoc["pc"]
                faltan = [b["banco"] for b in pc["por_banco"] if b["sin_puc"]]
                if faltan:
                    st.warning("Sin cuenta puente (no se acreditó la contrapartida): "
                               + ", ".join(faltan) + ". Complétala arriba y regenera.")
                st.success(f"Plano consolidado: {pc['n']} líneas · Débitos = Créditos = "
                           f"{pc['debitos']:,.2f}.")
                st.dataframe(pd.DataFrame(
                    [{"banco": b["banco"], "cuenta_puc": b["cuenta_puc"],
                      "líneas": b["lineas"], "débitos": b["debitos"]} for b in pc["por_banco"]]
                ).style.format({"débitos": "{:,.2f}"}), use_container_width=True, hide_index=True)
                st.download_button("⬇ Descargar plano consolidado (.txt)",
                                   data=planoc["txt"].encode("latin-1", errors="replace"),
                                   file_name=planoc["fname"], mime="text/plain")

with tab_c:
  if not bancos:
    st.info("Esta empresa no tiene bancos configurados para conciliar. "
            "Ve a «Configuración» y agrégalos (o siembra los de GRUPO DE LOLITA).")
  else:
    st.markdown("#### 1. Sube los archivos del mes")
    c1, c2, c3 = st.columns(3)
    with c1:
        f_aux = st.file_uploader("Auxiliar general (.xlsx)", type=["xlsx"], key="cc_aux")
    with c2:
        f_banco = st.file_uploader("Reporte del banco (.xlsx)", type=["xlsx"], key="cc_banco")
    with c3:
        f_data = st.file_uploader("Datáfono Credibanco — archivo ORIGINAL o macro (opcional)",
                                  type=["xlsm", "xlsx"], key="cc_data")
        st.caption("Puedes subir el **archivo original de Credibanco** (hoja "
                   "«Reporte Conciliar»): INTEGRAL calcula comisión y retenciones "
                   "por centro de costo con el MAESTRO configurado. También acepta "
                   "la macro con «RESUMEN MENSUAL».")

    st.markdown("#### 2. Elige la cuenta y el saldo del banco")
    d1, d2 = st.columns([2, 1])
    with d1:
        nom = st.selectbox("Banco / cuenta", [b["nombre"] for b in bancos])
        banco_cfg = next(b for b in bancos if b["nombre"] == nom)
        st.caption(f"Cuenta auxiliar: `{banco_cfg['cuenta_auxiliar']}` · "
                   f"Hoja del reporte: `{banco_cfg['hoja_reporte']}`")
    # saldo del extracto detectado del pie de la hoja (FINAL)
    saldo_auto = 0.0
    if f_banco is not None:
        try:
            det = C.saldo_extracto_de(f_banco.getvalue(), banco_cfg["hoja_reporte"])
            if det.get("final") is not None:
                saldo_auto = round(det["final"], 2)
        except Exception:  # noqa: BLE001
            pass
    with d2:
        saldo_banco = st.number_input("Saldo según extracto del banco",
                                      value=float(saldo_auto), step=1000.0, format="%.2f",
                                      help="Se detecta del pie de la hoja del reporte "
                                           "(FINAL). Puedes ajustarlo.")
        if saldo_auto:
            st.caption(f"Detectado del pie de la hoja: {saldo_auto:,.2f}")
        periodo = st.text_input("Periodo (para el encabezado del Excel)", "")

    st.markdown("#### 3. Partidas en tránsito y ajuste al peso (opcional)")
    e1, e2 = st.columns(2)
    with e1:
        transito_txt = st.text_input(
            "Consignaciones en tránsito reales (deja vacío para calcularlas)",
            value="", placeholder="p.ej. 18049006",
            help="Valor de las consignaciones/datáfonos que quedaron en puente "
                 "para el próximo mes. Si lo dejas vacío, el sistema calcula el "
                 "tránsito como cuadre exacto.")
    with e2:
        tolerancia = st.number_input(
            "Tolerancia ajuste al peso (±)", value=10000.0, step=1000.0, format="%.2f",
            help="Si al usar el tránsito real queda una diferencia mínima por "
                 "acumulación de redondeos, se carga a GASTO BANCARIO como "
                 "«ajuste al peso» siempre que no supere esta tolerancia.")

    # El resultado se guarda en session_state para que NO se pierda al accionar
    # otros botones (Streamlit re-ejecuta el script en cada clic).
    if st.button("🔁 Conciliar", type="primary", disabled=(f_aux is None or f_banco is None)):
        try:
            transito_real = None
            _t = (transito_txt or "").replace(",", "").replace("$", "").strip()
            if _t not in ("", "-"):
                transito_real = float(_t)
            maestro = C.cargar_maestro(sb, emp["id"])
            aux = C.leer_auxiliar(f_aux.getvalue(), banco_cfg["cuenta_auxiliar"])
            banco = C.leer_banco(f_banco.getvalue(), banco_cfg["hoja_reporte"])
            data = C.leer_datafono(f_data.getvalue() if f_data else None, maestro=maestro)
            r = C.conciliar(aux, banco, data, saldo_banco,
                            transito_real=transito_real, tolerancia=tolerancia)
        except Exception as e:  # noqa: BLE001
            st.session_state.pop("cc_r", None)
            st.error(f"No pude conciliar: {e}")
            st.stop()
        nota_df = ""
        if f_data is not None and not data.get("por_cc"):
            nota_df = ("⚠️ Subiste el datáfono pero no pude calcular el resumen. "
                       "Debe ser el archivo original de Credibanco (hoja «Reporte "
                       "Conciliar») o la macro con «RESUMEN MENSUAL»; revisa el MAESTRO "
                       "en «Configuración».")
        elif f_data is not None and data.get("hoja"):
            nota_df = (f"Datáfono leído de «{data['hoja']}»: {data['n_filas']} centros · "
                       f"comisión {data['comision']:,.2f} · retenciones "
                       f"{data['retefuente']+data['reteiva']+data['reteica']:,.2f}.")
        # guardar todo el contexto necesario para dibujar y exportar
        st.session_state["cc_r"] = r
        st.session_state["cc_ctx"] = {
            "nom": nom, "cuenta": banco_cfg.get("cuenta_auxiliar", ""),
            "periodo": periodo, "empresa": emp.get("razon_social", ""),
            "tolerancia": tolerancia, "nota_df": nota_df}
        st.session_state.pop("cc_plano", None)   # limpiar plano anterior

    # ---------------------------------------------------------------
    # RENDER desde session_state (persiste entre clics de botones)
    # ---------------------------------------------------------------
    r = st.session_state.get("cc_r")
    if r:
        ctx = st.session_state.get("cc_ctx", {})
        nom = ctx.get("nom", nom if 'nom' in dir() else "")
        if ctx.get("nota_df"):
            st.caption(ctx["nota_df"])

        st.subheader(f"Conciliación — {nom}")
        cuadro = [
            ("SALDO EN LIBROS", r["saldo_ant"]),
            ("(+) CONSIGNACIONES", r["consignaciones"]),
            ("(−) PAGOS", -r["pagos"]),
            ("(−) NOTAS DÉBITO", -r["notas_debito"]),
            ("      Gasto bancario", -r["gasto_bancario"]),
            ("         (incl. ajuste al peso)", -r["ajuste_al_peso"]),
            ("      Comisiones", -r["comisiones"]),
            ("      Comisión datáfono", -r["comision_datafono"]),
            ("      IVA", -r["iva"]),
            ("      GMF", -r["gmf"]),
            ("      ReteIVA", -r["reteiva"]),
            ("      Retefuente", -r["retefuente"]),
            ("      ReteICA", -r["reteica"]),
            ("(=) SALDO EN LIBROS A CIERRE", r["saldo_cierre"]),
            ("(−) CONSIGNACIONES EN TRÁNSITO", -r["consignaciones_transito"]),
            ("(=) SALDO SEGÚN EXTRACTO", r["saldo_banco"]),
        ]
        st.dataframe(pd.DataFrame(cuadro, columns=["Concepto", "Valor"])
                     .style.format({"Valor": "{:,.2f}"}),
                     use_container_width=True, hide_index=True)
        if abs(r["ajuste_al_peso"]) > 0:
            st.info(f"Ajuste al peso cargado a gasto bancario: {r['ajuste_al_peso']:,.2f} "
                    f"(por acumulación de redondeos, dentro de la tolerancia de "
                    f"±{ctx.get('tolerancia', 10000):,.0f}).")
        if r["cuadra"]:
            st.success(f"Cuadra: saldo a cierre − tránsito = saldo del banco. "
                       f"Documentos que cruzan: {r['n_cruzan']}.")
        else:
            st.warning("El cuadro no cierra contra el saldo del banco; revisa el saldo "
                       "del extracto o las partidas en tránsito. Si diste el tránsito "
                       "real, la diferencia superó la tolerancia del ajuste al peso.")

        st.caption(f"Cruce por documento: **{r['n_cruzan']}** documentos cruzan "
                   "(los renglones del banco que agrupan varios comprobantes, "
                   "p.ej. «28637-28638-5664-5665», se expanden y cruzan cada uno).")

        cols_pend = ["documento", "tipo", "centro_costo", "punto", "fecha", "valor"]
        renom = {"documento": "Documento", "tipo": "Tipo de abono",
                 "centro_costo": "Centro de costo", "punto": "Punto / OASIS",
                 "fecha": "Fecha", "valor": "Valor"}

        def _tabla_pend(regs):
            df = pd.DataFrame(regs)
            if df.empty:
                return df
            df = df[[c for c in cols_pend if c in df.columns]].rename(columns=renom)
            return df.style.format({"Valor": "{:,.2f}"})

        st.markdown("**Consignaciones en tránsito — lo que quedó en libros y entra el mes siguiente**")
        st.caption("Consignaciones/datáfonos de los últimos días registrados en LIBROS, "
                   "acumulados de la fecha más reciente hacia atrás hasta cubrir el "
                   "tránsito, detallados por documento, tipo de abono y centro de costo. "
                   f"Suman {r.get('transito_detalle_total', 0):,.2f} · tránsito del cuadro "
                   f"{r['consignaciones_transito']:,.2f}.")
        st.dataframe(_tabla_pend(r["pend_transito"]), use_container_width=True,
                     hide_index=True, height=260)
        if r["pend_libros"]:
            st.markdown("**Pagos en libros que no salieron del banco**")
            st.dataframe(_tabla_pend(r["pend_libros"]), use_container_width=True,
                         hide_index=True, height=180)

        # ---- descargas: Excel, PDF ----
        st.markdown("#### Descargas")
        dcol = st.columns(2)
        try:
            xlsx = C.exportar_excel(r, nombre_banco=nom, cuenta=ctx.get("cuenta", ""),
                                    periodo=ctx.get("periodo", ""), empresa=ctx.get("empresa", ""))
            dcol[0].download_button("⬇ Conciliación (Excel con formato y fórmulas)",
                               data=xlsx, type="primary", use_container_width=True,
                               file_name=f"conciliacion_{nom.replace(' ','_')}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:  # noqa: BLE001
            dcol[0].error(f"Excel: {e}")
        try:
            pdfb = C.exportar_pdf(r, nombre_banco=nom, cuenta=ctx.get("cuenta", ""),
                                  periodo=ctx.get("periodo", ""), empresa=ctx.get("empresa", ""),
                                  usuario=st.session_state.get("user_email", ""))
            dcol[1].download_button("⬇ Conciliación (PDF con firma del software)",
                               data=pdfb, use_container_width=True,
                               file_name=f"conciliacion_{nom.replace(' ','_')}.pdf",
                               mime="application/pdf")
        except Exception as e:  # noqa: BLE001
            dcol[1].error(f"PDF: {e}")

        # ---- plano de gastos para Contai ----
        st.markdown("#### 🧾 Plano de gastos para Contai")
        st.caption("Gastos bancarios repartidos en **partes iguales** entre los centros "
                   "de costo; los gastos de **Credibanco** por centro de costo según la "
                   "tabla de establecimientos. Reutiliza la configuración de «Bancos a "
                   "Contai» (centros del reparto, cuentas y cuenta puente del banco).")
        centros_rep, cuentas_g, cuenta_puc = [], dict(C.CUENTAS_GASTO_DEF), ""
        if ebm is not None:
            try:
                centros_rep = ebm.cargar_centros(sb, emp["id"])
                cuentas_g = C.cuentas_gasto_desde_reglas(ebm.cargar_reglas(sb, emp["id"]))
                for b in ebm.cargar_bancos(sb, emp["id"]):
                    if b.get("nombre", "").strip().upper() == nom.strip().upper():
                        cuenta_puc = str(b.get("cuenta_puc") or "").strip()
                        break
            except Exception:  # noqa: BLE001
                pass
        pc = st.columns(4)
        comprob = pc[0].text_input("Comprobante", "10", key="pl_comp")
        docpl = pc[1].text_input("Documento", "1", key="pl_doc")
        f_pl = pc[2].date_input("Fecha del asiento", format="MM/DD/YYYY", key="pl_fec")
        cuenta_puc = pc[3].text_input("Cuenta puente (contrapartida)",
                                      cuenta_puc or "11100599", key="pl_puc")
        cc_txt = st.text_area(
            "Centros de costo del reparto igualitario (uno por línea)",
            "\n".join(centros_rep) if centros_rep else
            "100401\n100501\n100601\n100901\n101201\n101301\n101801\n103001",
            height=110, key="pl_cc")
        cc_rep = [x.strip() for x in cc_txt.splitlines() if x.strip()]
        st.caption(f"Cuentas de gasto (de Bancos a Contai): gasto bancario "
                   f"`{cuentas_g['gasto_bancario']}` · comisiones `{cuentas_g['comisiones']}` · "
                   f"IVA `{cuentas_g['iva']}` · GMF `{cuentas_g['gmf']}`. Datáfono: comisión "
                   f"`{C.CUENTAS_DATAFONO['comision']}` · retefuente `{C.CUENTAS_DATAFONO['retefuente']}` "
                   f"· reteIVA `{C.CUENTAS_DATAFONO['reteiva']}` · reteICA `{C.CUENTAS_DATAFONO['reteica']}`.")
        if st.button("🧾 Generar plano de gastos", disabled=not cc_rep):
            p = C.generar_plano_gastos(
                r, cc_rep, cuenta_puc=cuenta_puc, cuentas_gasto=cuentas_g,
                comprobante=comprob, documento=docpl, fecha=f_pl.strftime("%m/%d/%Y"))
            st.session_state["cc_plano"] = {
                "p": p, "txt": C.plano_a_texto(p["filas"]),
                "fname": f"plano_gastos_{nom.replace(' ','_')}_{f_pl:%Y_%m}.txt",
                "notas_debito": r["notas_debito"]}

        plano = st.session_state.get("cc_plano")
        if plano:
            p = plano["p"]
            if abs(p["debitos"] - plano["notas_debito"]) < 0.5:
                st.success(f"Plano generado: {p['n']} líneas · Débitos = Créditos = "
                           f"{p['debitos']:,.2f} (= notas débito de la conciliación).")
            else:
                st.warning(f"Plano generado ({p['n']} líneas), pero los débitos "
                           f"{p['debitos']:,.2f} no igualan las notas débito "
                           f"{plano['notas_debito']:,.2f}; revisa.")
            st.dataframe(pd.DataFrame(p["filas"][1:], columns=p["filas"][0]).head(30),
                         use_container_width=True, hide_index=True)
            st.download_button(
                "⬇ Descargar plano de gastos (.txt)",
                data=plano["txt"].encode("latin-1", errors="replace"),
                file_name=plano["fname"], mime="text/plain")
