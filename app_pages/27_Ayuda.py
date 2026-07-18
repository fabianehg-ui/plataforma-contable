"""
27_Ayuda.py — Centro de ayuda: guía breve de cada módulo (con animación).
Lee el registro central core/ayuda.AYUDAS.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar
from core.ayuda import AYUDAS, render_ayuda_bloque


require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()

st.title("📖 Ayuda")
st.caption("Guía breve de cada módulo. Elige uno o mira todas las guías.")
st.markdown("---")

opciones = {f"{a.get('icono','')} {a['titulo']}": k for k, a in AYUDAS.items()}
etqs = ["— Todas las guías —"] + list(opciones.keys())
sel = st.selectbox("Módulo", etqs)

if sel == "— Todas las guías —":
    for k in AYUDAS:
        render_ayuda_bloque(k)
        st.markdown("---")
else:
    render_ayuda_bloque(opciones[sel])
