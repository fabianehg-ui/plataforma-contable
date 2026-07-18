"""
23_Conceptos.py — Conceptos programados y tarifas de INTEGRAL.

Administra los atajos de captura:
    - Tipos de IVA (tarifa + cuenta)
    - Tipos de retención (tarifa, base de cálculo, cuenta)
    - Conceptos programados (plantillas de asiento que usa la Captura)

Incluye un botón para sembrar el catálogo estándar colombiano por empresa.
Requiere migración 016_conceptos_iva_retencion.sql.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from db.supabase_client import get_supabase
from core.contable import conceptos as cp


require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin"])
sb = get_supabase()

st.title("🧩 Conceptos y tarifas")
st.caption(f"Empresa activa: **{emp['razon_social']}** · Atajos para la Captura")
st.markdown("---")

# ---- Sembrar catálogo estándar -------------------------------------
with st.container():
    cs1, cs2 = st.columns([3, 1])
    with cs1:
        st.markdown("#### ⚡ Catálogo estándar")
        st.caption("Crea (o refresca) el juego estándar colombiano de tipos de IVA, "
                   "retenciones y conceptos comunes. No borra lo que ya tengas; puedes "
                   "editar las cuentas para que calcen con tu plan.")
    with cs2:
        st.write("")
        if st.button("⚡ Sembrar estándar", type="primary", use_container_width=True):
            try:
                r = cp.sembrar_estandar(sb, emp["id"])
                st.success(f"Sembrado: {r['tipos_iva']} IVA · {r['tipos_retencion']} "
                           f"retenciones · {r['conceptos']} conceptos.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo sembrar (¿corriste la migración 016 y tienes rol admin?): {e}")

st.markdown("---")

tab_con, tab_iva, tab_ret = st.tabs([
    "🧩 Conceptos", "🧾 Tipos de IVA", "✂️ Tipos de retención"])


def _guardar_editor(edit_df, campos_obligatorios, upsert_fn):
    """Recorre las filas del editor y hace upsert de las que tengan datos."""
    n = 0
    for _, r in edit_df.iterrows():
        vals = {k: (str(r.get(k, "")).strip() if r.get(k) is not None else "") for k in campos_obligatorios}
        if not all(vals.get(k) for k in campos_obligatorios):
            continue
        upsert_fn(r)
        n += 1
    return n


# ---------------------------------------------------------------------
# Conceptos
# ---------------------------------------------------------------------
with tab_con:
    st.markdown("### 🧩 Conceptos programados")
    st.caption("Cada concepto arma un asiento: cuenta base + IVA + retención(es) + "
               "contrapartida. En la Captura eliges el concepto y la base, y las líneas "
               "se generan solas (editables).")
    conc = cp.listar_conceptos(sb, emp["id"])
    iva_cods = [t["codigo"] for t in cp.listar_tipos_iva(sb, emp["id"])]
    ret_cods = [t["codigo"] for t in cp.listar_tipos_retencion(sb, emp["id"])]

    df_con = pd.DataFrame([{
        "Código": c["codigo"], "Nombre": c["nombre"],
        "Naturaleza": c.get("naturaleza") or "compra",
        "Comprobante": c.get("comprobante") or "",
        "Cuenta base": c.get("cuenta_base") or "",
        "Cuenta contrapartida": c.get("cuenta_contrapartida") or "",
        "Tipo IVA": c.get("tipo_iva_codigo") or "",
        "Tipo retención": c.get("tipo_retencion_codigo") or "",
        "Maneja IVA": bool(c.get("maneja_iva", True)),
        "Maneja retención": bool(c.get("maneja_retencion", True)),
        "Descripción": c.get("descripcion") or "",
    } for c in conc]) if conc else pd.DataFrame(
        columns=["Código", "Nombre", "Naturaleza", "Comprobante", "Cuenta base",
                 "Cuenta contrapartida", "Tipo IVA", "Tipo retención",
                 "Maneja IVA", "Maneja retención", "Descripción"])

    ed_con = st.data_editor(
        df_con, num_rows="dynamic", use_container_width=True, hide_index=True,
        key="ed_con",
        column_config={
            "Naturaleza": st.column_config.SelectboxColumn(options=["compra", "venta", "otro"]),
            "Tipo IVA": st.column_config.SelectboxColumn(options=[""] + iva_cods),
            "Tipo retención": st.column_config.SelectboxColumn(options=[""] + ret_cods),
            "Maneja IVA": st.column_config.CheckboxColumn(),
            "Maneja retención": st.column_config.CheckboxColumn(),
        })
    if st.button("💾 Guardar conceptos", type="primary", key="btn_save_con"):
        def _up(r):
            cp.upsert_concepto(
                sb, emp["id"], str(r["Código"]).strip(), str(r["Nombre"]).strip(),
                naturaleza=str(r["Naturaleza"] or "compra").strip(),
                comprobante=str(r["Comprobante"] or "").strip() or None,
                cuenta_base=str(r["Cuenta base"] or "").strip() or None,
                cuenta_contrapartida=str(r["Cuenta contrapartida"] or "").strip() or None,
                tipo_iva_codigo=str(r["Tipo IVA"] or "").strip() or None,
                tipo_retencion_codigo=str(r["Tipo retención"] or "").strip() or None,
                maneja_iva=bool(r["Maneja IVA"]),
                maneja_retencion=bool(r["Maneja retención"]),
                descripcion=str(r["Descripción"] or "").strip() or None,
            )
        try:
            n = _guardar_editor(ed_con, ["Código", "Nombre"], _up)
            st.success(f"{n} concepto(s) guardado(s).")
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo guardar: {e}")

    if conc:
        with st.expander("🗑️ Eliminar un concepto"):
            cod_del = st.selectbox("Código", [c["codigo"] for c in conc], key="del_con")
            if st.button("Eliminar", key="btn_del_con"):
                cp.eliminar_concepto(sb, emp["id"], cod_del)
                st.success(f"Concepto {cod_del} eliminado.")
                st.rerun()


# ---------------------------------------------------------------------
# Tipos de IVA
# ---------------------------------------------------------------------
with tab_iva:
    st.markdown("### 🧾 Tipos de IVA")
    iva = cp.listar_tipos_iva(sb, emp["id"])
    df_iva = pd.DataFrame([{
        "Código": t["codigo"], "Nombre": t["nombre"], "Tarifa %": float(t.get("tarifa") or 0),
        "Cuenta": t.get("cuenta") or "", "Tipo": t.get("tipo") or "C",
    } for t in iva]) if iva else pd.DataFrame(columns=["Código", "Nombre", "Tarifa %", "Cuenta", "Tipo"])
    ed_iva = st.data_editor(
        df_iva, num_rows="dynamic", use_container_width=True, hide_index=True, key="ed_iva",
        column_config={
            "Tarifa %": st.column_config.NumberColumn(format="%.2f", min_value=0),
            "Tipo": st.column_config.SelectboxColumn(options=["C", "V"],
                                                     help="C = descontable (compras) · V = generado (ventas)"),
        })
    if st.button("💾 Guardar tipos de IVA", type="primary", key="btn_save_iva"):
        def _up(r):
            cp.upsert_tipo_iva(sb, emp["id"], str(r["Código"]).strip(), str(r["Nombre"]).strip(),
                               r["Tarifa %"], str(r["Cuenta"] or "").strip(), str(r["Tipo"] or "C").strip())
        try:
            n = _guardar_editor(ed_iva, ["Código", "Nombre"], _up)
            st.success(f"{n} tipo(s) de IVA guardado(s).")
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo guardar: {e}")


# ---------------------------------------------------------------------
# Tipos de retención
# ---------------------------------------------------------------------
with tab_ret:
    st.markdown("### ✂️ Tipos de retención")
    st.caption("`base_calculo`: **base** = sobre la base gravable (retefuente, reteICA) · "
               "**iva** = sobre el valor del IVA (reteIVA).")
    ret = cp.listar_tipos_retencion(sb, emp["id"])
    df_ret = pd.DataFrame([{
        "Código": t["codigo"], "Nombre": t["nombre"], "Tarifa %": float(t.get("tarifa") or 0),
        "Base cálculo": t.get("base_calculo") or "base", "Base UVT": float(t.get("base_uvt") or 0),
        "Cuenta": t.get("cuenta") or "", "Clase": t.get("clase") or "fuente",
    } for t in ret]) if ret else pd.DataFrame(
        columns=["Código", "Nombre", "Tarifa %", "Base cálculo", "Base UVT", "Cuenta", "Clase"])
    ed_ret = st.data_editor(
        df_ret, num_rows="dynamic", use_container_width=True, hide_index=True, key="ed_ret",
        column_config={
            "Tarifa %": st.column_config.NumberColumn(format="%.4f", min_value=0),
            "Base cálculo": st.column_config.SelectboxColumn(options=["base", "iva"]),
            "Base UVT": st.column_config.NumberColumn(format="%.2f", min_value=0),
            "Clase": st.column_config.SelectboxColumn(options=["fuente", "iva", "ica"]),
        })
    if st.button("💾 Guardar tipos de retención", type="primary", key="btn_save_ret"):
        def _up(r):
            cp.upsert_tipo_retencion(
                sb, emp["id"], str(r["Código"]).strip(), str(r["Nombre"]).strip(),
                r["Tarifa %"], str(r["Base cálculo"] or "base").strip(), r["Base UVT"],
                str(r["Cuenta"] or "").strip(), str(r["Clase"] or "fuente").strip())
        try:
            n = _guardar_editor(ed_ret, ["Código", "Nombre"], _up)
            st.success(f"{n} tipo(s) de retención guardado(s).")
            st.rerun()
        except Exception as e:
            st.error(f"No se pudo guardar: {e}")
