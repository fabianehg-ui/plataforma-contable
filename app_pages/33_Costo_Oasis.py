"""
app_pages/33_Costo_Oasis.py

TRASLADO DEL COSTO de GRUPO DE LOLITA a partir de los SALDOS de inventario.

Entradas del mes:
  1) INFORME DE INVENTARIOS (archivo grande con la data cruda por producto)
     -> inventario FINAL por centro de costo, versión sin IVA (SUBTOTAL + ICUI)
        por defecto, o con IVA.
  2) BALANCE de la CUENTA 14 por centro de costo (Balance de Prueba)
     -> COMPRAS del mes = débitos de la cuenta 14 por CC.

Inventario INICIAL = el inventario FINAL guardado del mes anterior (la app lo
MEMORIZA para que no haya descuadres). El primer mes se siembra a mano.

Costo por CC = inventario inicial + compras − inventario final.
Plano: deja el final en la cuenta 14 (crédito 143599) y lleva a la cuenta 61 lo
consumido (débito 613599). Comprobante 20, DETALLE «TRASLADO DEL COSTO».

Config: tabla costo_inventario_final (migración 024).
Depende de: core/costo/costo_oasis.py · requirements: openpyxl
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import calendar
from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Costo Oasis",
                   page_icon="📦", layout="wide")
from auth.guard import guard_empresa
from core.costo import costo_oasis as T

st.title("📦 Costo Oasis — Traslado del costo")
emp, sb = guard_empresa()
st.caption("Traslado del costo por centro de costo usando los SALDOS de inventario. "
           "El inventario **final** de cada mes se guarda y se reutiliza como "
           "inventario **inicial** del mes siguiente, para que no haya descuadres.")

# ------------------------------------------------------------------ 1. entradas
st.markdown("#### 1. Periodo y archivos")
c = st.columns([1.1, 1.1, 1, 1])
hoy = date.today()
per_def = f"{hoy.year:04d}-{hoy.month:02d}"
periodo = c[0].text_input("Periodo del costo (YYYY-MM)", value=per_def,
                          help="Mes al que corresponde el costo. El inicial se toma "
                               "del final guardado del mes anterior.")
documento = c[1].text_input("Documento (Contai)", value=str(hoy.month))
version = c[2].selectbox("Versión de inventario", ["sin_iva", "con_iva"],
                         format_func=lambda v: "Sin IVA (SUBTOTAL + ICUI)" if v == "sin_iva"
                         else "Con IVA", index=0)
comprobante = c[3].text_input("Comprobante", value=T.COMPROBANTE)

c2 = st.columns(2)
informe = c2[0].file_uploader("Informe de inventarios (archivo grande .xlsx)",
                              type=["xlsx"], key="tc_inf")
balance = c2[1].file_uploader("Balance de la cuenta 14 por CC (.xlsx)",
                              type=["xlsx", "xls"], key="tc_bp")

# fecha de corte del inventario final (del propio informe)
fecha_corte = None
if informe is not None:
    try:
        fechas = T.fechas_informe(informe.getvalue())
    except Exception:  # noqa: BLE001
        fechas = []
    if fechas:
        # sugerir el 1° del mes SIGUIENTE al periodo (corte del inventario final)
        sug = None
        try:
            y, m = periodo.split("-"); y, m = int(y), int(m)
            m2 = 1 if m == 12 else m + 1
            y2 = y + 1 if m == 12 else y
            sug = f"{y2:04d}-{m2:02d}-01"
        except Exception:  # noqa: BLE001
            pass
        idx = fechas.index(sug) if sug in fechas else len(fechas) - 1
        fecha_corte = st.selectbox("Fecha de corte del inventario final (del informe)",
                                   fechas, index=idx,
                                   help="Normalmente el 1° del mes siguiente al periodo.")
    else:
        st.warning("No pude leer fechas del informe; revisa que sea el archivo grande "
                   "con la data cruda (columnas TOTAL PRECIO SIN IVA, ICUI, FECHA, OASIS).")

# fecha del plano (MM/DD/AAAA) — último día del periodo por defecto
try:
    y, m = periodo.split("-"); y, m = int(y), int(m)
    ult = calendar.monthrange(y, m)[1]
    fecha_plano_def = f"{m:02d}/{ult:02d}/{y:04d}"
except Exception:  # noqa: BLE001
    fecha_plano_def = hoy.strftime("%m/%d/%Y")
fecha_plano = st.text_input("Fecha del plano (MM/DD/AAAA)", value=fecha_plano_def)

st.divider()

# ------------------------------------------------------------------ 2. inicial (memoria)
st.markdown("#### 2. Inventario inicial (memoria del mes anterior)")
per_ant = T.periodo_anterior(periodo)
guardado = T.cargar_inventario_final(sb, emp["id"], per_ant, version) if per_ant else {}

ccs = list(T.NOMBRES_CC.keys())
if guardado:
    st.success(f"Inicial tomado del inventario final guardado de **{per_ant}** "
               f"({len(guardado)} centros).")
else:
    st.info(f"No hay inventario final guardado de **{per_ant}**. Es el primer mes o "
            "aún no se ha guardado: escribe el inventario inicial a mano (semilla).")

df_ini = pd.DataFrame([{"CC": cc, "PUNTO": T.NOMBRES_CC[cc],
                        "INVENTARIO INICIAL": float(guardado.get(cc, 0))} for cc in ccs])
ed_ini = st.data_editor(df_ini, hide_index=True, use_container_width=True, key="tc_ini",
                        disabled=["CC", "PUNTO"],
                        column_config={"INVENTARIO INICIAL":
                                       st.column_config.NumberColumn(format="%.0f")})
inicial = {str(r["CC"]): float(r["INVENTARIO INICIAL"] or 0) for _, r in ed_ini.iterrows()}

st.divider()

# ------------------------------------------------------------------ 3. calcular
st.markdown("#### 3. Calcular el costo")
if st.button("🧮 Calcular traslado del costo", type="primary",
             disabled=not (informe and balance and fecha_corte)):
    try:
        final = T.inventario_final_informe(informe.getvalue(), fecha_corte, version)
        bp = T.compras_balance14(balance.getvalue())
        compras = {cc: bp.get(cc, {}).get("compras", 0.0) for cc in ccs}
        res = T.generar_traslado(inicial, compras, final, comprobante=comprobante,
                                 documento=documento, fecha=fecha_plano, ccs=ccs)
        st.session_state["tc_res"] = res
        st.session_state["tc_final"] = final
        st.session_state["tc_meta"] = dict(periodo=periodo, version=version,
                                            documento=documento, fecha=fecha_plano)
    except Exception as e:  # noqa: BLE001
        st.error(f"No pude calcular: {e}")

res = st.session_state.get("tc_res")
if res:
    meta = st.session_state.get("tc_meta", {})
    est = pd.DataFrame(res["estado"]).rename(columns={
        "cc": "CC", "nombre": "PUNTO", "inicial": "INV. INICIAL", "compras": "+ COMPRAS",
        "disponible": "= DISPONIBLE", "final": "− INV. FINAL", "costo": "= COSTO"})
    st.dataframe(est.style.format({c: "{:,.0f}" for c in
                 ["INV. INICIAL", "+ COMPRAS", "= DISPONIBLE", "− INV. FINAL", "= COSTO"]}),
                 hide_index=True, use_container_width=True)
    t = res["totales"]
    m = st.columns(4)
    m[0].metric("Inventario inicial", f"{t['inicial']:,.0f}")
    m[1].metric("Compras", f"{t['compras']:,.0f}")
    m[2].metric("Inventario final", f"{t['final']:,.0f}")
    m[3].metric("COSTO del mes", f"{t['costo']:,.0f}")
    st.caption(f"Plano: {res['n']} líneas · débitos {res['debitos']:,.0f} = "
               f"créditos {res['creditos']:,.0f} · "
               + ("✅ cuadra" if res["cuadra"] else "⚠️ NO cuadra"))

    d = st.columns(2)
    xls = T.estado_costo_excel(res, periodo=meta.get("periodo", periodo),
                               version=meta.get("version", version),
                               documento=meta.get("documento", documento),
                               fecha=meta.get("fecha", fecha_plano))
    d[0].download_button("📥 Estado del costo (Excel)", xls,
                         file_name=f"Estado_Costo_{meta.get('periodo','')}_Grupo_de_Lolita.xlsx",
                         mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    plano_txt = T.plano_a_texto(res["filas"]).encode("latin-1", "replace")
    d[1].download_button("📥 Plano Contai (.txt)", plano_txt,
                         file_name=f"traslado_costo_{meta.get('periodo','')}_grupo.txt",
                         mime="text/plain")

    st.divider()
    # -------------------------------------------------- 4. memorizar el final
    st.markdown("#### 4. Guardar el inventario final del mes (memoria)")
    st.caption("Guarda el inventario **final** de este periodo. El próximo mes se "
               "usará automáticamente como inventario **inicial**.")
    if st.button("💾 Guardar inventario final de " + meta.get("periodo", periodo)):
        try:
            n = T.guardar_inventario_final(sb, emp["id"], meta.get("periodo", periodo),
                                           st.session_state.get("tc_final", {}),
                                           meta.get("version", version))
            st.success(f"Guardado el inventario final de {meta.get('periodo', periodo)} "
                       f"({n} centros). Se usará como inicial de "
                       f"{T.periodo_siguiente(meta.get('periodo', periodo))}.")
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude guardar: {e}")
