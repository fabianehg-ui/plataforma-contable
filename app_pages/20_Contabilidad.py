"""
20_Contabilidad.py — Libros y reportes contables de INTEGRAL.

Lee los movimientos guardados en cn_movimientos (núcleo contable) y produce:
    - Balance de prueba (saldo anterior · débitos · créditos · saldo final)
    - Libro auxiliar (movimiento detallado con saldo corriente)
    - Estado de cartera (saldo por tercero de las cuentas de cartera)
Además permite IMPORTAR históricos desde un plano (mismo formato de 11 columnas).
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
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
emp = require_rol(["admin", "operador", "consulta"])
sb = get_supabase()

st.title("📚 Contabilidad — Libros y reportes")
st.caption(f"Empresa activa: **{emp['razon_social']}** · Movimiento e históricos de INTEGRAL")
st.markdown("---")

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _sel_periodo(label, key, default_anio=None, default_mes=None):
    """Selector año+mes que devuelve 'AAAAMM'."""
    c1, c2 = st.columns(2)
    with c1:
        a = st.number_input(f"{label} · año", 2000, 2100,
                            value=default_anio or date.today().year, step=1, key=f"{key}_a")
    with c2:
        m = st.selectbox(f"{label} · mes", list(range(1, 13)),
                         format_func=lambda i: f"{i:02d} — {MESES[i-1]}",
                         index=(default_mes or date.today().month) - 1, key=f"{key}_m")
    return f"{int(a)}{int(m):02d}"


def _excel(df: pd.DataFrame, hoja="Reporte") -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=hoja, index=False)
    return bio.getvalue()


def _fmt_cols(df, cols):
    return {c: st.column_config.NumberColumn(format="%d") for c in cols if c in df.columns}


tab_bal, tab_aux, tab_cart, tab_import, tab_per = st.tabs([
    "⚖️ Balance de prueba",
    "📒 Libro auxiliar",
    "💳 Estado de cartera",
    "📥 Importar movimiento",
    "🗓️ Períodos",
])


# ---------------------------------------------------------------------
# Balance de prueba
# ---------------------------------------------------------------------
with tab_bal:
    st.markdown("### ⚖️ Balance de prueba")
    cA, cB = st.columns(2)
    with cA:
        desde = _sel_periodo("Desde", "bal_d")
    with cB:
        hasta = _sel_periodo("Hasta", "bal_h")
    if st.button("Generar balance", type="primary", key="btn_bal"):
        with st.spinner("Calculando…"):
            df = cont.balance_prueba(sb, emp["id"], desde, hasta)
        if len(df) == 0:
            st.info("No hay movimiento en ese rango.")
        else:
            tot_db = int(df["Débitos"].sum())
            tot_cr = int(df["Créditos"].sum())
            m1, m2, m3 = st.columns(3)
            m1.metric("Cuentas", len(df))
            m2.metric("Débitos", f"$ {tot_db:,}".replace(",", "."))
            m3.metric("Créditos", f"$ {tot_cr:,}".replace(",", "."))
            if tot_db == tot_cr:
                st.success(f"✅ Cuadra: Db = Cr = $ {tot_db:,}".replace(",", "."))
            else:
                st.warning(f"⚠️ Descuadre: $ {tot_db - tot_cr:,}".replace(",", "."))
            st.dataframe(df, use_container_width=True, hide_index=True,
                         column_config=_fmt_cols(df, ["Saldo anterior", "Débitos", "Créditos", "Saldo final"]))
            st.download_button("📊 Excel", _excel(df, "BalancePrueba"),
                               file_name=f"balance_prueba_{desde}_{hasta}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------------
# Libro auxiliar
# ---------------------------------------------------------------------
with tab_aux:
    st.markdown("### 📒 Libro auxiliar")
    c1, c2 = st.columns(2)
    with c1:
        cuenta = st.text_input("Cuenta (código, opcional)", key="aux_cta")
    with c2:
        nit = st.text_input("NIT / tercero (opcional)", key="aux_nit")
    c3, c4 = st.columns(2)
    with c3:
        desde_a = _sel_periodo("Desde", "aux_d")
    with c4:
        hasta_a = _sel_periodo("Hasta", "aux_h")
    if st.button("Generar auxiliar", type="primary", key="btn_aux"):
        if not cuenta and not nit:
            st.warning("Indica al menos una cuenta o un NIT.")
        else:
            with st.spinner("Consultando…"):
                df, saldo_ant = cont.libro_auxiliar(
                    sb, emp["id"], cuenta=cuenta or None, nit=nit or None,
                    desde=desde_a, hasta=hasta_a)
            st.caption(f"Saldo anterior: **$ {int(saldo_ant):,}**".replace(",", "."))
            if len(df) == 0:
                st.info("Sin movimiento para ese filtro/rango.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True,
                             column_config=_fmt_cols(df, ["Débito", "Crédito", "Saldo"]))
                st.download_button("📊 Excel", _excel(df, "Auxiliar"),
                                   file_name=f"auxiliar_{cuenta or nit}_{desde_a}_{hasta_a}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------------
# Estado de cartera
# ---------------------------------------------------------------------
with tab_cart:
    st.markdown("### 💳 Estado de cartera")
    st.caption("Saldo por tercero de las cuentas de cartera (por defecto, las que empiezan por 13).")
    c1, c2 = st.columns(2)
    with c1:
        corte = _sel_periodo("Corte a", "cart_h")
    with c2:
        pref = st.text_input("Prefijos de cuenta (coma)", value="13", key="cart_pref")
    if st.button("Generar cartera", type="primary", key="btn_cart"):
        prefijos = tuple(p.strip() for p in pref.split(",") if p.strip()) or ("13",)
        with st.spinner("Consultando…"):
            df = cont.estado_cartera(sb, emp["id"], hasta=corte, prefijos=prefijos)
        if len(df) == 0:
            st.info("No hay saldos de cartera en ese corte.")
        else:
            st.metric("Total cartera", f"$ {int(df['Saldo cartera'].sum()):,}".replace(",", "."))
            st.dataframe(df, use_container_width=True, hide_index=True,
                         column_config=_fmt_cols(df, ["Saldo cartera"]))
            st.download_button("📊 Excel", _excel(df, "Cartera"),
                               file_name=f"cartera_{corte}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.caption("ℹ️ El detalle de edades de mora (aging) requiere las fechas de "
                       "vencimiento por documento; se puede agregar cuando se importen.")


# ---------------------------------------------------------------------
# Importar movimiento (históricos)
# ---------------------------------------------------------------------
def _leer_plano(archivo) -> pd.DataFrame:
    """Lee un plano (.txt tab-delimitado o .xlsx) al layout de 11 columnas."""
    nombre = archivo.name.lower()
    if nombre.endswith((".xlsx", ".xls")):
        df = pd.read_excel(archivo, dtype=str)
    else:
        raw = archivo.read().decode("latin-1")
        lineas = [l for l in raw.splitlines() if l.strip() and not l.lower().startswith("sep=")]
        # ¿primera línea es encabezado?
        if lineas and "CUENTA" in lineas[0].upper():
            lineas = lineas[1:]
        filas = [l.split("\t") for l in lineas]
        df = pd.DataFrame(filas)
    # Ajustar a 11 columnas
    df = df.iloc[:, :11]
    df.columns = cont.COLUMNAS_PLANO[:df.shape[1]]
    return df.fillna("")


with tab_import:
    st.markdown("### 📥 Importar movimiento (históricos)")
    st.info(
        "Sube un plano contable (mismo formato de 11 columnas: CUENTA · COMPROBANTE · "
        "FECHA · DOCUMENTO · DOC REFERENCIA · NIT · DETALLE · TR · VALOR · BASE · "
        "CENTRO DE COSTO). El período de cada línea se toma de su FECHA. Sirve para "
        "cargar tus históricos exportados de otro sistema."
    )
    archivo = st.file_uploader("Plano (.txt o .xlsx)", type=["txt", "xlsx", "xls"], key="imp_file")
    origen = st.text_input("Etiqueta de origen", value="importado", key="imp_origen")
    if archivo is not None:
        try:
            df_imp = _leer_plano(archivo)
            st.markdown(f"**Vista previa** ({len(df_imp)} líneas)")
            st.dataframe(df_imp.head(20), use_container_width=True, hide_index=True)
            db = pd.to_numeric(df_imp[df_imp["TR"] == "1"]["VALOR"], errors="coerce").sum()
            cr = pd.to_numeric(df_imp[df_imp["TR"] == "2"]["VALOR"], errors="coerce").sum()
            st.caption(f"Débitos: $ {int(db):,} · Créditos: $ {int(cr):,} · {'cuadra ✅' if int(db)==int(cr) else 'descuadra ⚠️'}".replace(",", "."))
            if st.button("📥 Importar a INTEGRAL", type="primary", key="btn_imp"):
                usr = current_user() or {}
                with st.spinner("Importando…"):
                    r = cont.importar_movimientos(sb, emp["id"], df_imp,
                                                  origen=origen or "importado",
                                                  user_id=usr.get("id"))
                st.success(f"✅ {r['insertados']} líneas importadas en períodos: {', '.join(r['periodos']) or '—'}")
                if r["saltados_protegidos"]:
                    st.warning("🔒 Períodos protegidos (no se tocaron): " + ", ".join(r["saltados_protegidos"]))
        except Exception as e:
            st.error(f"No se pudo leer/importar el plano: {e}")


# ---------------------------------------------------------------------
# Períodos
# ---------------------------------------------------------------------
with tab_per:
    st.markdown("### 🗓️ Períodos contables")
    periodos = cont.listar_periodos(sb, emp["id"])
    if not periodos:
        st.info("Aún no hay períodos. Se crean al guardar/importar movimiento.")
    else:
        dfp = pd.DataFrame([{
            "Período": p["periodo"],
            "Nombre": p.get("nombre") or "",
            "Estado": "🔒 Protegido" if p["estado"] == "P" else "🟢 Abierto",
            "Débitos": None, "Créditos": None, "Cuadra": None,
        } for p in periodos])
        st.dataframe(dfp[["Período", "Nombre", "Estado"]], use_container_width=True, hide_index=True)

        st.markdown("#### Abrir / proteger")
        cod = st.selectbox("Período", [p["periodo"] for p in periodos], key="per_sel")
        cq = cont.cuadre_periodo(sb, emp["id"], cod)
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Débitos", f"$ {cq['debitos']:,}".replace(",", "."))
        cc2.metric("Créditos", f"$ {cq['creditos']:,}".replace(",", "."))
        cc3.metric("Cuadra", "✅" if cq["cuadra"] else f"❌ {cq['diferencia']:,}".replace(",", "."))
        b1, b2 = st.columns(2)
        with b1:
            if st.button("🔒 Proteger período", use_container_width=True, key="btn_prot"):
                cont.cambiar_estado_periodo(sb, emp["id"], cod, "P")
                st.success(f"Período {cod} protegido.")
                st.rerun()
        with b2:
            if st.button("🟢 Abrir período", use_container_width=True, key="btn_abrir"):
                cont.cambiar_estado_periodo(sb, emp["id"], cod, "A")
                st.success(f"Período {cod} abierto.")
                st.rerun()
