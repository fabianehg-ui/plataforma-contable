"""
25_Cruce_Facturas.py — Pagos y recaudos con cruce de facturas (cartera abierta).

Al poner el NIT de un tercero, el sistema busca sus **facturas pendientes**
(calculadas de cn_movimientos por documento) y sugiere marcarlas para cancelar
total o parcialmente:

  - **Pagar** (comprobante de egreso): cuentas por pagar (2205, 2335, 2505…).
      Por cada factura marcada → Db la cuenta por pagar; Cr banco por el total.
  - **Recaudar** (recibo de caja): cuentas por cobrar (1305, 1330…).
      Por cada factura marcada → Cr la cuenta por cobrar; Db caja/banco.

El asiento queda cuadrado y cada línea referencia el documento cancelado.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info, current_user
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from db.supabase_client import get_supabase
from core.contable import servicio_contable as cont


require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin", "operador"])
sb = get_supabase()

st.title("💳 Cruce de facturas — pagos y recaudos")
st.caption(f"Empresa activa: **{emp['razon_social']}** · Cancela facturas pendientes por tercero")
st.markdown("---")

comprobantes = cont.listar_comprobantes(sb, emp["id"])
if not comprobantes:
    st.info("Primero crea tipos de comprobante en ✍️ Captura (egreso, recibo de caja).")
    st.stop()


def _preselect_comprobante(palabras):
    for i, c in enumerate(comprobantes):
        nom = (c.get("nombre") or "").lower()
        if any(p in nom for p in palabras):
            return i
    return 0


def render_cruce(modo: str, prefijos_def: str, comp_kw, contra_label: str,
                 contra_def: str):
    es_pago = modo == "pagar"
    verbo = "pagar" if es_pago else "recaudar"

    nit = st.text_input("NIT del tercero", key=f"{modo}_nit").strip()
    c1, c2 = st.columns([2, 1])
    with c1:
        pref = st.text_input("Cuentas a revisar (prefijos, separados por coma)",
                             value=prefijos_def, key=f"{modo}_pref")
    with c2:
        st.write("")
        buscar = st.button("🔎 Buscar facturas pendientes", key=f"{modo}_buscar",
                           use_container_width=True)
    if buscar:
        if not nit:
            st.warning("Indica el NIT del tercero.")
        else:
            prefijos = tuple(p.strip() for p in pref.split(",") if p.strip())
            st.session_state[f"pend_{modo}"] = cont.documentos_pendientes(
                sb, emp["id"], nit, prefijos=prefijos)
            st.session_state[f"pend_{modo}_nit"] = nit

    docs = st.session_state.get(f"pend_{modo}")
    if docs is None or st.session_state.get(f"pend_{modo}_nit") != nit or not nit:
        return
    if not docs:
        st.info("Ese tercero no tiene documentos pendientes en esas cuentas.")
        return

    st.markdown(f"#### Facturas pendientes de **{nit}**")
    df = pd.DataFrame([{
        "Cancelar": True, "Cuenta": d["cuenta"], "Documento": d["documento"],
        "Fecha": d["fecha"] or "", "Detalle": d["detalle"],
        "Pendiente": int(d["pendiente"]), "Valor a cruzar": int(d["pendiente"]),
    } for d in docs])
    ed = st.data_editor(
        df, num_rows="fixed", hide_index=True, use_container_width=True,
        key=f"{modo}_editor",
        disabled=["Cuenta", "Documento", "Fecha", "Detalle", "Pendiente"],
        column_config={
            "Cancelar": st.column_config.CheckboxColumn(),
            "Pendiente": st.column_config.NumberColumn(format="%d"),
            "Valor a cruzar": st.column_config.NumberColumn(format="%d", min_value=0),
        })

    sel = ed[ed["Cancelar"] == True].copy()
    sel["Valor a cruzar"] = pd.to_numeric(sel["Valor a cruzar"], errors="coerce").fillna(0).astype(int)
    sel = sel[sel["Valor a cruzar"] > 0]
    exceso = sel[sel["Valor a cruzar"] > sel["Pendiente"]]
    total = int(sel["Valor a cruzar"].sum())

    st.metric(f"Total a {verbo}", f"$ {total:,}".replace(",", "."))
    if len(exceso):
        st.warning(f"⚠️ {len(exceso)} línea(s) con valor mayor al pendiente. Ajusta antes de guardar.")

    st.markdown("##### Cabecera del comprobante")
    h1, h2, h3 = st.columns(3)
    with h1:
        op = {f"{c['codigo']} · {c['nombre']}": c["codigo"] for c in comprobantes}
        comp_lbl = st.selectbox("Comprobante", list(op.keys()),
                                index=_preselect_comprobante(comp_kw), key=f"{modo}_comp")
        comp_cod = op[comp_lbl]
    with h2:
        fecha = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY", key=f"{modo}_fecha")
    with h3:
        documento = st.text_input("Documento (consecutivo)", key=f"{modo}_doc")
    contra = st.text_input(contra_label, value=contra_def, key=f"{modo}_contra").strip()
    detalle = st.text_input(
        "Detalle", value=f"{'Pago' if es_pago else 'Recaudo'} tercero {nit}",
        key=f"{modo}_det")

    periodo = f"{fecha.year}{fecha.month:02d}"
    protegido = cont.periodo_protegido(sb, emp["id"], periodo)
    if protegido:
        st.error(f"🔒 El período {periodo} está PROTEGIDO.")

    puede = (total > 0 and contra and len(sel) > 0 and len(exceso) == 0 and not protegido)
    if st.button(f"💾 Generar y guardar {'egreso' if es_pago else 'recibo de caja'}",
                 type="primary", disabled=not puede, key=f"{modo}_save"):
        filas = []
        # Una línea por factura cancelada (contra la cuenta por pagar/cobrar)
        for _, r in sel.iterrows():
            filas.append({
                "CUENTA": str(r["Cuenta"]), "COMPROBANTE": comp_cod, "FECHA": fecha,
                "DOCUMENTO": documento, "DOC REFERENCIA": str(r["Documento"]),
                "NIT": nit, "DETALLE": detalle,
                "TR": "1" if es_pago else "2",          # pago: Db pasivo · recaudo: Cr activo
                "VALOR": int(r["Valor a cruzar"]), "BASE": 0, "CENTRO DE COSTO": "",
            })
        # Contrapartida (banco / caja) por el total
        filas.append({
            "CUENTA": contra, "COMPROBANTE": comp_cod, "FECHA": fecha,
            "DOCUMENTO": documento, "DOC REFERENCIA": documento, "NIT": nit,
            "DETALLE": detalle,
            "TR": "2" if es_pago else "1",              # pago: Cr banco · recaudo: Db caja/banco
            "VALOR": total, "BASE": 0, "CENTRO DE COSTO": "",
        })
        df_plano = pd.DataFrame(filas, columns=cont.COLUMNAS_PLANO)
        try:
            usr = current_user() or {}
            n = cont.guardar_plano(sb, emp["id"], periodo, df_plano,
                                   origen=("pago" if es_pago else "recaudo"),
                                   user_id=usr.get("id"), reemplazar=False)
            st.success(f"✅ {'Egreso' if es_pago else 'Recibo de caja'} guardado "
                       f"({n} líneas, $ {total:,})".replace(",", "."))
            st.session_state.pop(f"pend_{modo}", None)
            st.rerun()
        except PermissionError as e:
            st.error(f"🔒 {e}")
        except Exception as e:
            st.error(f"No se pudo guardar: {e}")


tab_pagar, tab_recaudar = st.tabs(["📤 Pagar (egreso)", "📥 Recaudar (recibo de caja)"])

with tab_pagar:
    st.markdown("### 📤 Pagar cuentas por pagar")
    st.caption("Cuentas por pagar típicas: 2205 proveedores · 2335 costos y gastos por "
               "pagar · 2505 salarios por pagar.")
    render_cruce("pagar", "2205,2335,2505", ["egreso", "pago"],
                 "Cuenta de pago (banco/caja)", "111005")

with tab_recaudar:
    st.markdown("### 📥 Recaudar cartera (recibo de caja)")
    st.caption("Cuentas por cobrar típicas: 1305 clientes · 1330 anticipos y avances.")
    render_cruce("recaudar", "1305,1330", ["recibo", "caja", "recaudo"],
                 "Cuenta de ingreso (caja/banco)", "110505")
