import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_empresa()

st.title("📝 Provisiones")
st.caption(f"Empresa activa: **{emp['razon_social']}**")
st.markdown("---")

st.info(
    "🚧 **Módulo en desarrollo.**\n\n"
    "Replicará `procesador_provisiones.py` (690 líneas). "
    "Genera el asiento mensual de provisión de prestaciones sociales "
    "(cesantías, intereses, prima, vacaciones)."
)
