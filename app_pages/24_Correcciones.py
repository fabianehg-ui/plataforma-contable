"""
24_Correcciones.py — Corrección de movimientos ya cargados en INTEGRAL.

Dos modos:
  1) Corrección por comprobante: trae un asiento (comprobante · documento),
     lo edita línea por línea y lo reemplaza validando el cuadre Db = Cr.
  2) Corrección por registros: filtra movimientos de cn_movimientos y edita o
     elimina filas individuales (por id).

Ambos respetan el período PROTEGIDO. Origen de las líneas corregidas: 'correccion'.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date, datetime

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

st.title("🛠️ Correcciones de movimiento")
st.caption(f"Empresa activa: **{emp['razon_social']}** · Corrige asientos o registros de cn_movimientos")
st.markdown("---")

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _sel_periodo(label, key):
    c1, c2 = st.columns(2)
    with c1:
        a = st.number_input(f"{label} · año", 2000, 2100, value=date.today().year,
                            step=1, key=f"{key}_a")
    with c2:
        m = st.selectbox(f"{label} · mes", list(range(1, 13)),
                         format_func=lambda i: f"{i:02d} — {MESES[i-1]}",
                         index=date.today().month - 1, key=f"{key}_m")
    return f"{int(a)}{int(m):02d}"


def _fecha_a_date(v, defecto=None):
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except Exception:
        return defecto or date.today()


tab_comp, tab_reg = st.tabs(["🧾 Corrección por comprobante", "📋 Corrección por registros"])


# =====================================================================
# 1) Corrección por comprobante
# =====================================================================
with tab_comp:
    st.markdown("### 🧾 Corrección por comprobante")
    st.caption("Trae el asiento completo, corrígelo y reemplázalo. Debe quedar cuadrado (Db = Cr).")

    per_c = _sel_periodo("Período", "cor_comp")
    if st.button("Cargar comprobantes del período", key="btn_cor_load"):
        st.session_state["cor_lista"] = cont.listar_comprobantes_periodo(sb, emp["id"], per_c)
        st.session_state["cor_periodo"] = per_c
        st.session_state.pop("cor_asiento", None)

    lista = st.session_state.get("cor_lista")
    if lista is not None and st.session_state.get("cor_periodo") == per_c:
        if not lista:
            st.info("No hay comprobantes en ese período.")
        else:
            opciones = {}
            for g in lista:
                etq = (f"{g['comprobante']} · doc {g['documento']} · {g['fecha'] or 's/f'} · "
                       f"$ {g['debitos']:,}".replace(",", ".")
                       + ("  ⚠️" if not g["cuadra"] else ""))
                opciones[etq] = (g["comprobante"], g["documento"])
            sel = st.selectbox("Asiento a corregir", list(opciones.keys()), key="cor_sel")
            if st.button("📂 Cargar asiento", key="btn_cor_asiento"):
                comp_cod, doc = opciones[sel]
                movs = cont.buscar_movimientos(sb, emp["id"], periodo=per_c,
                                               comprobante=comp_cod, documento=doc)
                df = pd.DataFrame([{
                    "Cuenta": m.get("cuenta") or "",
                    "Detalle": m.get("detalle") or "",
                    "NIT": m.get("nit") or "",
                    "Débito": int(m["valor"]) if str(m.get("tr")) == "1" else 0,
                    "Crédito": int(m["valor"]) if str(m.get("tr")) == "2" else 0,
                    "Base": int(m.get("base") or 0),
                    "Centro costo": m.get("centro_costo") or "",
                } for m in movs])
                fecha0 = movs[0].get("fecha") if movs else None
                st.session_state["cor_asiento"] = {
                    "comp": comp_cod, "doc": doc, "periodo": per_c,
                    "df": df, "fecha": fecha0,
                }

    asiento = st.session_state.get("cor_asiento")
    if asiento and asiento["periodo"] == per_c:
        st.markdown(f"#### Editando comprobante {asiento['comp']} · documento {asiento['doc']}")
        protegido = cont.periodo_protegido(sb, emp["id"], per_c)
        if protegido:
            st.error(f"🔒 El período {per_c} está PROTEGIDO. No se puede guardar la corrección.")

        f1, _ = st.columns([1, 2])
        with f1:
            fecha_doc = st.date_input("Fecha del comprobante",
                                      value=_fecha_a_date(asiento["fecha"]),
                                      format="DD/MM/YYYY", key="cor_fecha")

        ed = st.data_editor(
            asiento["df"], num_rows="dynamic", use_container_width=True, key="cor_editor",
            column_config={
                "Débito": st.column_config.NumberColumn(format="%d", min_value=0),
                "Crédito": st.column_config.NumberColumn(format="%d", min_value=0),
                "Base": st.column_config.NumberColumn(format="%d", min_value=0),
            })

        d = ed.copy()
        for c in ("Débito", "Crédito", "Base"):
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0).astype(int)
        val = d[(d["Cuenta"].astype(str).str.strip() != "") &
                ((d["Débito"] != 0) | (d["Crédito"] != 0))]
        tot_db, tot_cr = int(val["Débito"].sum()), int(val["Crédito"].sum())
        dif = tot_db - tot_cr

        m1, m2, m3 = st.columns(3)
        m1.metric("Débito", f"$ {tot_db:,}".replace(",", "."))
        m2.metric("Crédito", f"$ {tot_cr:,}".replace(",", "."))
        m3.metric("Diferencia", f"$ {dif:,}".replace(",", "."))
        ambas = val[(val["Débito"] != 0) & (val["Crédito"] != 0)]
        ok = (dif == 0 and len(val) > 0 and len(ambas) == 0 and not protegido)
        if len(ambas):
            st.warning(f"⚠️ {len(ambas)} línea(s) con débito y crédito a la vez.")
        if dif == 0 and len(val) > 0 and len(ambas) == 0:
            st.success(f"✅ Cuadra: Db = Cr = $ {tot_db:,}".replace(",", "."))
        elif dif != 0:
            st.warning(f"⚠️ No cuadra (diferencia $ {dif:,}).".replace(",", "."))

        cA, cB = st.columns([2, 1])
        with cA:
            if st.button("💾 Guardar corrección (reemplaza el asiento)", type="primary",
                         disabled=not ok, use_container_width=True, key="btn_cor_save"):
                filas = []
                for _, r in val.iterrows():
                    es_db = int(r["Débito"]) != 0
                    filas.append({
                        "CUENTA": str(r["Cuenta"]).strip(),
                        "COMPROBANTE": asiento["comp"],
                        "FECHA": fecha_doc,
                        "DOCUMENTO": asiento["doc"],
                        "DOC REFERENCIA": asiento["doc"],
                        "NIT": str(r["NIT"]).strip(),
                        "DETALLE": str(r["Detalle"]).strip(),
                        "TR": "1" if es_db else "2",
                        "VALOR": int(r["Débito"]) if es_db else int(r["Crédito"]),
                        "BASE": int(r["Base"]),
                        "CENTRO DE COSTO": str(r["Centro costo"]).strip(),
                    })
                df_plano = pd.DataFrame(filas, columns=cont.COLUMNAS_PLANO)
                try:
                    usr = current_user() or {}
                    n = cont.reemplazar_comprobante(
                        sb, emp["id"], per_c, asiento["comp"], asiento["doc"],
                        df_plano, user_id=usr.get("id"))
                    st.success(f"✅ Comprobante {asiento['comp']}-{asiento['doc']} "
                               f"corregido ({n} líneas).")
                    st.session_state.pop("cor_asiento", None)
                    st.session_state.pop("cor_lista", None)
                    st.rerun()
                except PermissionError as e:
                    st.error(f"🔒 {e}")
                except Exception as e:
                    st.error(f"No se pudo guardar: {e}")
        with cB:
            if st.button("🗑️ Eliminar asiento completo", use_container_width=True,
                         disabled=protegido, key="btn_cor_del"):
                try:
                    cont.eliminar_comprobante(sb, emp["id"], per_c,
                                              asiento["comp"], asiento["doc"])
                    st.success("Asiento eliminado.")
                    st.session_state.pop("cor_asiento", None)
                    st.session_state.pop("cor_lista", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo eliminar: {e}")


# =====================================================================
# 2) Corrección por registros
# =====================================================================
with tab_reg:
    st.markdown("### 📋 Corrección por registros")
    st.caption("Filtra y edita filas individuales. Marca 🗑️ para eliminar. "
               "Editar valores puede descuadrar el comprobante: revisa el resumen antes de guardar.")

    f1, f2, f3 = st.columns(3)
    with f1:
        fp = st.text_input("Período (AAAAMM)", key="reg_per")
        fcta = st.text_input("Cuenta", key="reg_cta")
    with f2:
        fcomp = st.text_input("Comprobante", key="reg_comp")
        fnit = st.text_input("NIT", key="reg_nit")
    with f3:
        fdoc = st.text_input("Documento", key="reg_doc")
        forig = st.text_input("Origen (nomina, captura, importado…)", key="reg_orig")

    if st.button("🔎 Buscar movimientos", key="btn_reg_buscar"):
        if not any([fp, fcta, fcomp, fnit, fdoc, forig]):
            st.warning("Indica al menos un filtro para no traer todo el libro.")
        else:
            regs = cont.buscar_movimientos(
                sb, emp["id"], periodo=fp or None, comprobante=fcomp or None,
                documento=fdoc or None, cuenta=fcta or None, nit=fnit or None,
                origen=forig or None)
            st.session_state["reg_orig"] = regs
            st.session_state["reg_df"] = pd.DataFrame([{
                "Fecha": r.get("fecha") or "", "Comp": r.get("comprobante") or "",
                "Documento": r.get("documento") or "", "Cuenta": r.get("cuenta") or "",
                "NIT": r.get("nit") or "", "Detalle": r.get("detalle") or "",
                "TR": str(r.get("tr") or ""), "Valor": int(r.get("valor") or 0),
                "Base": int(r.get("base") or 0), "C.Costo": r.get("centro_costo") or "",
                "🗑️": False,
            } for r in regs])

    regs = st.session_state.get("reg_orig")
    if regs is not None:
        if not regs:
            st.info("No se encontraron movimientos con esos filtros.")
        else:
            st.caption(f"{len(regs)} registro(s). Período protegido = no editable.")
            ed = st.data_editor(
                st.session_state["reg_df"], num_rows="fixed", use_container_width=True,
                hide_index=True, key="reg_editor",
                column_config={
                    "TR": st.column_config.SelectboxColumn(options=["1", "2"],
                          help="1 = débito · 2 = crédito"),
                    "Valor": st.column_config.NumberColumn(format="%d", min_value=0),
                    "Base": st.column_config.NumberColumn(format="%d", min_value=0),
                    "🗑️": st.column_config.CheckboxColumn(help="Marcar para eliminar"),
                })

            # Resumen de cuadre por comprobante (con los valores EDITADOS, sin borrados)
            tmp = ed.copy()
            tmp["Valor"] = pd.to_numeric(tmp["Valor"], errors="coerce").fillna(0).astype(int)
            vivos = tmp[~tmp["🗑️"]]
            resumen = []
            for (comp, doc), grp in vivos.groupby(["Comp", "Documento"]):
                db = int(grp[grp["TR"] == "1"]["Valor"].sum())
                cr = int(grp[grp["TR"] == "2"]["Valor"].sum())
                resumen.append({"Comp": comp, "Documento": doc, "Débito": db,
                                "Crédito": cr, "Cuadra": "✅" if db == cr else "❌"})
            if resumen:
                dfr = pd.DataFrame(resumen)
                descuadran = dfr[dfr["Cuadra"] == "❌"]
                if len(descuadran):
                    st.warning(f"⚠️ {len(descuadran)} comprobante(s) quedarían DESCUADRADOS "
                               "tras estos cambios.")
                with st.expander("Ver cuadre por comprobante"):
                    st.dataframe(dfr, use_container_width=True, hide_index=True,
                                 column_config={"Débito": st.column_config.NumberColumn(format="%d"),
                                                "Crédito": st.column_config.NumberColumn(format="%d")})

            if st.button("💾 Guardar cambios (registros)", type="primary", key="btn_reg_save"):
                orig = st.session_state["reg_orig"]
                edf = ed.reset_index(drop=True)
                n_upd = n_del = n_err = 0
                errores = []
                for i, row in edf.iterrows():
                    o = orig[i]
                    mid = o.get("id")
                    if not mid:
                        continue
                    try:
                        if bool(row["🗑️"]):
                            cont.eliminar_movimiento(sb, emp["id"], mid)
                            n_del += 1
                            continue
                        nuevos = {
                            "fecha": row["Fecha"], "comprobante": row["Comp"],
                            "documento": row["Documento"], "cuenta": row["Cuenta"],
                            "nit": row["NIT"], "detalle": row["Detalle"],
                            "tr": row["TR"], "valor": row["Valor"], "base": row["Base"],
                            "centro_costo": row["C.Costo"],
                        }
                        cambios = {}
                        mapa = {"fecha": "fecha", "comprobante": "comprobante",
                                "documento": "documento", "cuenta": "cuenta", "nit": "nit",
                                "detalle": "detalle", "tr": "tr", "valor": "valor",
                                "base": "base", "centro_costo": "centro_costo"}
                        for campo in mapa:
                            viejo = o.get(campo)
                            nuevo = nuevos[campo]
                            if campo in ("valor", "base"):
                                if int(viejo or 0) != int(nuevo or 0):
                                    cambios[campo] = nuevo
                            else:
                                if str(viejo or "") != str(nuevo or ""):
                                    cambios[campo] = nuevo
                        if cambios:
                            cont.actualizar_movimiento(sb, emp["id"], mid, cambios)
                            n_upd += 1
                    except PermissionError as e:
                        n_err += 1
                        errores.append(str(e))
                    except Exception as e:
                        n_err += 1
                        errores.append(str(e))
                st.success(f"✅ {n_upd} actualizado(s), {n_del} eliminado(s)."
                           + (f" {n_err} con error." if n_err else ""))
                for e in errores[:5]:
                    st.error(e)
                st.session_state.pop("reg_orig", None)
                st.session_state.pop("reg_df", None)
                st.rerun()
