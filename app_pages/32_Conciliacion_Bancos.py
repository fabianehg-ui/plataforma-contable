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

st.title("🔁 Conciliación de bancos")
emp, sb = guard_empresa()
bancos = C.cargar_bancos(sb, emp["id"])

tab_c, tab_cfg = st.tabs(["🔁 Conciliar", "⚙️ Configuración"])

# ---- Configuración primero: así SIEMPRE se dibuja aunque no haya bancos ----
with tab_cfg:
    st.markdown("#### 🏦 Bancos a conciliar")
    st.caption("Por cada banco: el prefijo de la **cuenta del auxiliar** (la cuenta "
               "puente, p.ej. 11-10-05-99) y el **nombre de la hoja** del reporte del "
               "banco donde están sus movimientos con N COMPROBANTE.")
    filas = bancos or [{"nombre": "", "cuenta_auxiliar": "", "hoja_reporte": ""}]
    df = pd.DataFrame([{k: b.get(k, "") for k in ["nombre", "cuenta_auxiliar", "hoja_reporte"]}
                       for b in filas])
    ed = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="cfg_conc",
                        column_config={
                            "nombre": st.column_config.TextColumn("Banco / cuenta", required=True),
                            "cuenta_auxiliar": st.column_config.TextColumn("Cuenta auxiliar (prefijo)", required=True),
                            "hoja_reporte": st.column_config.TextColumn("Hoja del reporte", required=True),
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
    with d2:
        saldo_banco = st.number_input("Saldo según extracto del banco", value=0.0,
                                      step=1000.0, format="%.2f")

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
            st.error(f"No pude conciliar: {e}")
            st.stop()

        # aviso si se subió el datáfono pero no se leyó nada
        if f_data is not None and not data.get("por_cc"):
            st.warning("Subiste el archivo del datáfono pero no pude calcular el "
                       "resumen. Debe ser el **archivo original de Credibanco** "
                       "(hoja «Reporte Conciliar» con CODIGO ESTABLECIMIENTO y "
                       "VALOR COMISION / RETEFUENTE / RETE IVA / RTE ICA) o la macro "
                       "con la hoja «RESUMEN MENSUAL». Revisa también el MAESTRO en "
                       "«Configuración» para mapear los establecimientos a centros de costo.")
        elif f_data is not None and data.get("hoja"):
            st.caption(f"Datáfono leído de la hoja «{data['hoja']}»: "
                       f"{data['n_filas']} centros · comisión {data['comision']:,.2f} · "
                       f"retenciones {data['retefuente']+data['reteiva']+data['reteica']:,.2f}.")

        # ---- cuadro de conciliación ----
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
            st.info(f"Ajuste al peso cargado a gasto bancario: "
                    f"{r['ajuste_al_peso']:,.2f} (por acumulación de redondeos, "
                    f"dentro de la tolerancia de ±{tolerancia:,.0f}).")
        if r["cuadra"]:
            st.success(f"Cuadra: saldo a cierre − tránsito = saldo del banco. "
                       f"Documentos que cruzan: {r['n_cruzan']}.")
        else:
            st.warning("El cuadro no cierra contra el saldo del banco; revisa el saldo "
                       "del extracto o las partidas en tránsito. Si diste el tránsito "
                       "real, la diferencia superó la tolerancia del ajuste al peso.")

        m1, m2 = st.columns(2)
        with m1:
            st.markdown("**En banco sin libros (no están en contabilidad)**")
            st.dataframe(pd.DataFrame(r["solo_banco"]), use_container_width=True,
                         hide_index=True, height=220)
        with m2:
            st.markdown("**En libros sin banco (pagos no salidos)**")
            st.dataframe(pd.DataFrame(r["solo_libros"]), use_container_width=True,
                         hide_index=True, height=220)

        # ---- descargar Excel ----
        try:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as xw:
                pd.DataFrame(cuadro, columns=["Concepto", "Valor"]).to_excel(xw, index=False, sheet_name="Conciliacion")
                pd.DataFrame(r["solo_banco"]).to_excel(xw, index=False, sheet_name="No en contabilidad")
                pd.DataFrame(r["solo_libros"]).to_excel(xw, index=False, sheet_name="Pagos no salidos")
                if r["datafono_cc"]:
                    pd.DataFrame(r["datafono_cc"]).to_excel(xw, index=False, sheet_name="Datafono por CC")
            st.download_button("⬇ Descargar conciliación (Excel)", data=buf.getvalue(),
                               file_name=f"conciliacion_{nom.replace(' ','_')}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception:  # noqa: BLE001
            pass
