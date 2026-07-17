"""
21_Captura.py — Captura manual de comprobantes contables en INTEGRAL.

Permite armar un documento de partida doble (egreso, causación de gasto,
recibo de caja, o cualquier comprobante) línea por línea, validar el cuadre
Db = Cr y guardarlo en cn_movimientos.
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

st.title("✍️ Captura de comprobantes")
st.caption(f"Empresa activa: **{emp['razon_social']}** · Partida doble → cn_movimientos")
st.markdown("---")

# Comprobantes típicos que se pueden crear de un clic si no existen
COMP_SUGERIDOS = [
    ("1", "Recibo de caja"),
    ("2", "Comprobante de egreso"),
    ("3", "Causación / factura de compra"),
    ("4", "Nota de contabilidad"),
]


# ============================================================
# Tipos de comprobante
# ============================================================
comprobantes = cont.listar_comprobantes(sb, emp["id"])

# --- Gestión de tipos de comprobante (en el cuerpo, dentro del flujo) ---
st.markdown("### 🧾 Tipos de comprobante")
with st.expander("➕ Crear / gestionar tipos de comprobante",
                 expanded=(len(comprobantes) == 0)):
    if comprobantes:
        st.dataframe(
            pd.DataFrame([{"Código": c["codigo"], "Nombre": c["nombre"]}
                         for c in comprobantes]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("Aún no tienes comprobantes. Créalos aquí para poder hacer el asiento.")

    cc1, cc2, cc3 = st.columns([1, 2, 1])
    with cc1:
        nc_cod = st.text_input("Código", key="nc_cod", placeholder="ej. 2")
    with cc2:
        nc_nom = st.text_input("Nombre", key="nc_nom", placeholder="ej. Comprobante de egreso")
    with cc3:
        st.write("")
        crear1 = st.button("➕ Crear / actualizar", key="btn_nc", use_container_width=True)

    if crear1:
        if nc_cod and nc_nom:
            try:
                cont.upsert_comprobante(sb, emp["id"], nc_cod, nc_nom)
                st.success(f"Comprobante {nc_cod} guardado.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo crear el comprobante (¿tu rol tiene permiso de admin?): {e}")
        else:
            st.warning("Código y nombre son obligatorios.")

    if st.button("⚡ Crear los 4 sugeridos (recibo de caja, egreso, causación, nota)",
                 key="btn_sug"):
        try:
            for cod, nom in COMP_SUGERIDOS:
                cont.upsert_comprobante(sb, emp["id"], cod, nom)
            st.success("Comprobantes sugeridos creados.")
            st.rerun()
        except Exception as e:
            st.error(f"No se pudieron crear (¿tu rol tiene permiso de admin?): {e}")

if not comprobantes:
    st.info("Crea al menos un tipo de comprobante arriba para empezar el asiento.")
    st.stop()


# ============================================================
# Cabecera del documento
# ============================================================
st.markdown("### 1️⃣ Cabecera")
c1, c2, c3 = st.columns(3)
with c1:
    opciones = {f"{c['codigo']} · {c['nombre']}": c["codigo"] for c in comprobantes}
    comp_label = st.selectbox("Comprobante", list(opciones.keys()))
    comp_cod = opciones[comp_label]
with c2:
    fecha = st.date_input("Fecha", value=date.today(), format="DD/MM/YYYY")
with c3:
    documento = st.text_input("Documento (consecutivo)", value="")

c4, c5 = st.columns([1, 2])
with c4:
    nit_cab = st.text_input("NIT / tercero (opcional)", value="")
with c5:
    detalle_cab = st.text_input("Detalle / concepto", value="")

periodo_cod = f"{fecha.year}{fecha.month:02d}"
if cont.periodo_protegido(sb, emp["id"], periodo_cod):
    st.error(f"🔒 El período {periodo_cod} está PROTEGIDO. No se puede grabar en esa fecha.")


# ============================================================
# Líneas (partida doble)
# ============================================================
st.markdown("### 2️⃣ Líneas")
st.caption("Escribe la cuenta y el valor en **Débito** o en **Crédito** (uno de los dos por línea).")

if "captura_lineas" not in st.session_state:
    st.session_state["captura_lineas"] = pd.DataFrame(
        [{"Cuenta": "", "Detalle": "", "NIT": "", "Débito": 0, "Crédito": 0,
          "Base": 0, "Centro costo": ""} for _ in range(4)]
    )

edit = st.data_editor(
    st.session_state["captura_lineas"],
    num_rows="dynamic",
    use_container_width=True,
    key="editor_captura",
    column_config={
        "Cuenta": st.column_config.TextColumn(width="medium"),
        "Detalle": st.column_config.TextColumn(width="large"),
        "NIT": st.column_config.TextColumn(width="small"),
        "Débito": st.column_config.NumberColumn(format="%d", min_value=0),
        "Crédito": st.column_config.NumberColumn(format="%d", min_value=0),
        "Base": st.column_config.NumberColumn(format="%d", min_value=0),
        "Centro costo": st.column_config.TextColumn(width="small"),
    },
)

# Totales en vivo
df = edit.copy()
for col in ("Débito", "Crédito", "Base"):
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
lineas = df[(df["Cuenta"].astype(str).str.strip() != "") &
            ((df["Débito"] != 0) | (df["Crédito"] != 0))]

tot_db = int(lineas["Débito"].sum())
tot_cr = int(lineas["Crédito"].sum())
dif = tot_db - tot_cr

m1, m2, m3, m4 = st.columns(4)
m1.metric("Líneas", len(lineas))
m2.metric("Total débito", f"$ {tot_db:,}".replace(",", "."))
m3.metric("Total crédito", f"$ {tot_cr:,}".replace(",", "."))
m4.metric("Diferencia", f"$ {dif:,}".replace(",", "."))

# Validaciones
errores = []
ambas = lineas[(lineas["Débito"] != 0) & (lineas["Crédito"] != 0)]
if len(ambas):
    errores.append(f"{len(ambas)} línea(s) tienen débito Y crédito a la vez.")
if len(lineas) == 0:
    errores.append("No hay líneas con cuenta y valor.")
if dif != 0:
    errores.append(f"El comprobante no cuadra (diferencia $ {dif:,}).".replace(",", "."))

if dif == 0 and len(lineas) > 0 and not errores:
    st.success(f"✅ Cuadra: Db = Cr = $ {tot_db:,}".replace(",", "."))
else:
    for e in errores:
        st.warning(f"⚠️ {e}")


# ============================================================
# Guardar
# ============================================================
st.markdown("### 3️⃣ Guardar")
protegido = cont.periodo_protegido(sb, emp["id"], periodo_cod)
puede = (dif == 0 and len(lineas) > 0 and not errores and not protegido)

col_g1, col_g2 = st.columns([2, 1])
with col_g1:
    if st.button("💾 Guardar comprobante en INTEGRAL", type="primary",
                 disabled=not puede, use_container_width=True):
        # Construir el plano de 11 columnas
        filas = []
        for _, r in lineas.iterrows():
            es_db = int(r["Débito"]) != 0
            filas.append({
                "CUENTA": str(r["Cuenta"]).strip(),
                "COMPROBANTE": comp_cod,
                "FECHA": fecha,  # el servicio la convierte a ISO
                "DOCUMENTO": documento,
                "DOC REFERENCIA": documento,
                "NIT": str(r["NIT"]).strip() or nit_cab,
                "DETALLE": str(r["Detalle"]).strip() or detalle_cab,
                "TR": "1" if es_db else "2",
                "VALOR": int(r["Débito"]) if es_db else int(r["Crédito"]),
                "BASE": int(r["Base"]),
                "CENTRO DE COSTO": str(r["Centro costo"]).strip(),
            })
        df_plano = pd.DataFrame(filas, columns=cont.COLUMNAS_PLANO)
        try:
            usr = current_user() or {}
            n = cont.guardar_plano(
                sb, emp["id"], periodo_cod, df_plano,
                origen="captura", user_id=usr.get("id"), reemplazar=False,
            )
            st.success(
                f"✅ Comprobante {comp_cod}-{documento} guardado "
                f"({n} líneas, período {periodo_cod})."
            )
            # Limpiar para el siguiente documento
            st.session_state["captura_lineas"] = pd.DataFrame(
                [{"Cuenta": "", "Detalle": "", "NIT": "", "Débito": 0, "Crédito": 0,
                  "Base": 0, "Centro costo": ""} for _ in range(4)]
            )
            st.rerun()
        except PermissionError as e:
            st.error(f"🔒 {e}")
        except Exception as e:
            st.error(f"No se pudo guardar: {e}")
with col_g2:
    if st.button("🧹 Limpiar líneas", use_container_width=True):
        st.session_state["captura_lineas"] = pd.DataFrame(
            [{"Cuenta": "", "Detalle": "", "NIT": "", "Débito": 0, "Crédito": 0,
              "Base": 0, "Centro costo": ""} for _ in range(4)]
        )
        st.rerun()

if protegido:
    st.caption("🔒 Guardado deshabilitado: el período de la fecha está protegido.")

st.markdown("---")
st.caption(
    "Ejemplos: **Egreso** → Db gasto/pasivo, Cr banco. **Causación** → Db gasto + "
    "Db IVA, Cr proveedor + Cr retenciones. **Recibo de caja** → Db caja/banco, "
    "Cr cartera/ingreso. Todo se guarda en cn_movimientos y se ve en 📚 Contabilidad."
)
