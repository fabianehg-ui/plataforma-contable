"""
26_Centro_Contable.py — Trazabilidad de la contabilidad por módulo (origen).

Muestra qué causó cada módulo (nómina, ventas, compras, captura, pagos…) en un
período, con su cuadre, y permite REVERSAR lo de un módulo sin tocar el resto.
Es la ventana central del "todo conectado a cn_movimientos".
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from db.supabase_client import get_supabase
from core.contable import servicio_contable as cont
from core.contable import integracion as integ


require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin", "operador", "consulta"])
sb = get_supabase()

st.title("🔗 Centro Contable")
st.caption(f"Empresa activa: **{emp['razon_social']}** · Qué causó cada módulo en cn_movimientos")
st.markdown("---")

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

c1, c2 = st.columns(2)
with c1:
    anio = st.number_input("Año", 2000, 2100, value=date.today().year, step=1)
with c2:
    mes = st.selectbox("Mes", list(range(1, 13)),
                       format_func=lambda i: f"{i:02d} — {MESES[i-1]}",
                       index=date.today().month - 1)
periodo = f"{int(anio)}{int(mes):02d}"

resumen = integ.resumen_por_origen(sb, emp["id"], periodo)
if not resumen:
    st.info(f"No hay movimiento causado en el período {periodo}.")
    st.stop()

# Totales del período
cq = cont.cuadre_periodo(sb, emp["id"], periodo)
t1, t2, t3 = st.columns(3)
t1.metric("Débitos del período", f"$ {cq['debitos']:,}".replace(",", "."))
t2.metric("Créditos del período", f"$ {cq['creditos']:,}".replace(",", "."))
t3.metric("Cuadra", "✅" if cq["cuadra"] else f"❌ {cq['diferencia']:,}".replace(",", "."))

st.markdown("### 📊 Por módulo (origen)")
df = pd.DataFrame([{
    "Módulo": r["etiqueta"], "origen": r["origen"], "Líneas": r["lineas"],
    "Débitos": r["debitos"], "Créditos": r["creditos"],
    "Cuadra": "✅" if r["cuadra"] else "❌",
} for r in resumen])
st.dataframe(
    df[["Módulo", "Líneas", "Débitos", "Créditos", "Cuadra"]],
    use_container_width=True, hide_index=True,
    column_config={"Débitos": st.column_config.NumberColumn(format="%d"),
                   "Créditos": st.column_config.NumberColumn(format="%d")})

st.markdown("### ↩️ Reversar lo de un módulo")
st.caption("Borra únicamente las líneas causadas por ese módulo en el período "
           "(por ejemplo, para reprocesar la nómina). Respeta el período protegido.")
op = {r["etiqueta"]: r["origen"] for r in resumen}
sel = st.selectbox("Módulo a reversar", list(op.keys()))
protegido = cont.periodo_protegido(sb, emp["id"], periodo)
if protegido:
    st.error(f"🔒 El período {periodo} está PROTEGIDO.")
if st.button("↩️ Reversar módulo del período", disabled=protegido, type="secondary"):
    try:
        integ.reversar_origen(sb, emp["id"], periodo, op[sel])
        st.success(f"✅ Se reversó '{sel}' del período {periodo}.")
        st.rerun()
    except PermissionError as e:
        st.error(f"🔒 {e}")
    except Exception as e:
        st.error(f"No se pudo reversar: {e}")
