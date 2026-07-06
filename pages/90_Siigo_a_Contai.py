"""
pages/90_Siigo_a_Contai.py
Pagina de ContaTools: opera Siigo directamente (API), con seleccion de EMPRESA.

La lista de empresas la administras aqui (cada una con su Access Key y un
Partner-Id comun). La API de Siigo usa usuario + Access Key, NO la contrasena web.

Ubica este archivo en tu carpeta de paginas y el paquete en core/siigo/.
Requiere: streamlit, requests, openpyxl, cryptography (para cifrar la Access Key).
Define SIIGO_STORE_KEY (clave Fernet) para cifrar en reposo. En produccion,
reemplaza core/siigo/empresas.py por tu tabla en Supabase.
"""
from __future__ import annotations

import io
from datetime import date

import streamlit as st

from core.siigo import cliente, planos
from core.siigo import empresas as store

st.title("Siigo -> Contai")
ss = st.session_state


def _nits_xlsx(matrix) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    wsx = wb.active
    wsx.title = "NITs"
    for row in matrix:
        wsx.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _progress_cb(box):
    def cb(**k):
        if k.get("day"):
            box.text(f"Dia {k['day_index']}/{k['day_count']} ({k['day']}) - {k['fetched']} facturas")
        else:
            box.text(f"Pagina {k.get('page')} - {k.get('fetched')}/{k.get('total')}")
    return cb


# -- Barra lateral: EMPRESAS ------------------------------------------
with st.sidebar:
    st.header("Empresas Siigo")
    if not store.encryption_active():
        st.warning("Sin cifrado: define la variable SIIGO_STORE_KEY para proteger las Access Keys.")

    empresas = store.list_empresas()
    opciones = {"+ Nueva empresa...": None}
    for e in empresas:
        opciones[e["nombre"]] = e["id"]
    sel = st.selectbox("Empresa activa", list(opciones.keys()), key="emp_sel")
    emp_id = opciones[sel]

    with st.expander("Agregar / editar empresa", expanded=(emp_id is None)):
        cur = store.get_credenciales(emp_id) if emp_id else {}
        nombre = st.text_input("Nombre", value=(sel if emp_id else ""), key="f_nombre")
        e_id = st.text_input("ID (sin espacios)", value=(emp_id or ""), key="f_id", disabled=bool(emp_id))
        username = st.text_input("Usuario API", value=(cur or {}).get("username", ""), key="f_user")
        access_key = st.text_input(
            "Access Key", type="password", key="f_key",
            placeholder="(vacio = conservar la actual)" if emp_id else "",
        )
        partner_id = st.text_input("Partner-Id (comun a tus empresas)", value=(cur or {}).get("partner_id", ""), key="f_partner")
        b = st.columns(2)
        if b[0].button("Guardar empresa", use_container_width=True):
            eid = (emp_id or e_id or nombre).strip().replace(" ", "_")
            if not eid or not nombre or not username or (not emp_id and not access_key):
                st.error("Completa nombre, id, usuario y Access Key.")
            else:
                store.upsert_empresa(eid, nombre, username, access_key, partner_id)
                st.success("Empresa guardada.")
                st.rerun()
        if emp_id and b[1].button("Eliminar", use_container_width=True):
            store.delete_empresa(emp_id)
            st.rerun()

if emp_id is None:
    st.info("Selecciona o crea una empresa en la barra lateral para empezar.")
    st.stop()

# Al cambiar de empresa, limpia lo descargado en sesion.
if ss.get("emp_active") != emp_id:
    for k in ("invoices", "inv_range", "prefijos", "plan_det", "outputs", "msgs", "token"):
        ss.pop(k, None)
    ss["emp_active"] = emp_id

cred = store.get_credenciales(emp_id)
username, access_key, partner_id = cred["username"], cred["access_key"], cred["partner_id"]
cfg = store.get_config(emp_id)  # {plan, mapeo} guardados de esta empresa
st.caption(f"Empresa activa: **{sel}** - usuario {username or '-'} - Partner-Id {partner_id or '-'}")

# -- Rango de fechas --------------------------------------------------
c = st.columns(2)
d_start = c[0].date_input("Desde", value=date.today().replace(day=1), key="d_start")
d_end = c[1].date_input("Hasta", value=date.today(), key="d_end")
ds, de = d_start.isoformat(), d_end.isoformat()

# -- Deteccion de prefijos y plan -------------------------------------
if st.button("Detectar prefijos del rango"):
    try:
        box = st.empty()
        with st.spinner("Autenticando y descargando facturas..."):
            token = cliente.authenticate(username, access_key, partner_id)
            invoices = cliente.get_invoices(token, partner_id, ds, de, _progress_cb(box))
        box.empty()
        ss["token"] = token
        ss["invoices"] = invoices
        ss["inv_range"] = (ds, de)
        ss["prefijos"] = planos.prefijos_de(invoices)
        ss["plan_det"] = planos.detectar_plan(invoices)
        st.success(f"{len(invoices)} facturas - {len(ss['prefijos'])} prefijo(s).")
    except Exception as e:  # noqa: BLE001
        st.error(str(e))

mapeo: dict = {}
plan: dict = {"bases": {}, "impuestos": {}}

if ss.get("prefijos"):
    st.subheader("Prefijos -> comprobante y centro")
    for p in ss["prefijos"]:
        guardado = (cfg["mapeo"] or {}).get(p["prefix"], {})
        cols = st.columns([1, 2, 2])
        cols[0].markdown(f"**{p['prefix']}**  \n<small>{p['count']} fact.</small>", unsafe_allow_html=True)
        comp = cols[1].text_input("comprobante", value=guardado.get("comprobante", p["comprobante"]), key=f"comp_{p['prefix']}", label_visibility="collapsed", placeholder="comprobante")
        cen = cols[2].text_input("centro", value=guardado.get("centro", p["centro"]), key=f"cen_{p['prefix']}", label_visibility="collapsed", placeholder="centro")
        mapeo[p["prefix"]] = {"comprobante": comp, "centro": cen}

    st.subheader("Plan de cuentas")
    gplan = cfg["plan"] or {}
    cols = st.columns(2)
    plan["cuentaPorCobrar"] = cols[0].text_input("Cuenta por cobrar (total)", value=gplan.get("cuentaPorCobrar", ""), key="cxc", placeholder="13050502")
    plan["cuentaEfectivo"] = cols[1].text_input("Efectivo (recibos)", value=gplan.get("cuentaEfectivo", ""), key="efe", placeholder="11050503")
    det = ss.get("plan_det") or {"bases": [], "taxes": []}
    for bb in det["bases"]:
        plan["bases"][bb["cat"]] = st.text_input(bb["label"], value=(gplan.get("bases", {}) or {}).get(bb["cat"], ""), key=f"base_{bb['cat']}", placeholder="cuenta")
    for t in det["taxes"]:
        plan["impuestos"][t["key"]] = st.text_input(f"{t['label']} ({t['count']})", value=(gplan.get("impuestos", {}) or {}).get(t["key"], ""), key=f"iva_{t['key']}", placeholder="cuenta")

    if st.button("Guardar plan de cuentas de esta empresa"):
        store.save_config(emp_id, plan, mapeo)
        st.success("Plan de cuentas guardado para " + sel)

# -- Que exportar -----------------------------------------------------
st.subheader("Que exportar")
want_v = st.checkbox("Ventas", value=True)
want_r = st.checkbox("Recibos de caja")
modo, cons = "cancelar", None
if want_r:
    modo = st.radio(
        "Modo de recibos", ["cancelar", "siigo"],
        format_func=lambda x: "Cancelar todas las facturas" if x == "cancelar" else "Solo los recibos asentados en Siigo",
        horizontal=True,
    )
    if modo == "cancelar":
        cons = st.number_input("Consecutivo inicial del recibo", min_value=1, value=1, step=1)
want_n = st.checkbox("NITs / terceros")

usar_plan = bool(plan.get("cuentaPorCobrar"))

if st.button("Generar planos", type="primary"):
    try:
        if not (want_v or want_r or want_n):
            st.warning("Selecciona al menos un tipo a exportar.")
            st.stop()
        if usar_plan and want_v:
            faltan = [b["label"] for b in (ss.get("plan_det") or {}).get("bases", []) if not plan["bases"].get(b["cat"])]
            faltan += [t["label"] for t in (ss.get("plan_det") or {}).get("taxes", []) if not plan["impuestos"].get(t["key"])]
            if faltan:
                st.warning("Faltan cuentas del plan: " + ", ".join(faltan))
                st.stop()
        if usar_plan and want_r and not plan.get("cuentaEfectivo"):
            st.warning("Falta la cuenta de efectivo para los recibos.")
            st.stop()

        token = cliente.authenticate(username, access_key, partner_id)
        outputs, msgs = [], []
        invoices = ss.get("invoices") if ss.get("inv_range") == (ds, de) else None
        need_inv = want_v or (want_r and modo == "cancelar")
        if need_inv and invoices is None:
            with st.spinner("Descargando facturas..."):
                invoices = cliente.get_invoices(token, partner_id, ds, de)

        plan_arg = plan if usar_plan else None
        if want_v:
            outputs.append(("ventas.txt", planos.build_ventas(invoices, mapeo, plan_arg).encode("utf-8")))
        if want_r:
            if modo == "siigo":
                with st.spinner("Descargando recibos de Siigo..."):
                    vch = cliente.get_vouchers(token, partner_id, ds, de)
                res = planos.build_recibos_siigo(vch, plan_arg)
                outputs.append(("recibos_siigo.txt", res["content"].encode("utf-8")))
                msgs.append(f"Recibos de Siigo: {res['count']}")
            else:
                res = planos.build_recibos_cancelar(invoices, cons, mapeo, plan_arg)
                r = res["rango"]
                outputs.append(("recibos_caja.txt", res["content"].encode("utf-8")))
                msgs.append(f"Recibos: {r['count']} ({r['desde']}-{r['hasta']}), {res['omitidas']} omitidas por saldo 0")
        if want_n:
            with st.spinner("Descargando NITs..."):
                custs = cliente.get_customers(token, partner_id, ds, de)
            outputs.append(("nits.txt", planos.build_terceros(custs).encode("utf-8")))
            outputs.append(("nits.xlsx", _nits_xlsx(planos.terceros_matrix(custs))))
            msgs.append(f"NITs: {len(custs)}")

        ss["outputs"] = outputs
        st.success("Listo. " + " - ".join(msgs))
    except Exception as e:  # noqa: BLE001
        st.error(str(e))

# -- Descargas --------------------------------------------------------
if ss.get("outputs"):
    st.subheader("Descargar")
    for fn, data in ss["outputs"]:
        mime = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                if fn.endswith(".xlsx") else "text/plain")
        st.download_button(f"Descargar {fn}", data=data, file_name=fn, mime=mime, key=f"dl_{fn}")
    st.caption("Importa los .txt en Contai: Procesos -> Intercambio de Datos -> Importar.")
