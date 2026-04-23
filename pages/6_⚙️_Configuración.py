import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from auth.login import require_auth, sidebar_user_info
from auth.empresas import (
    seleccionar_empresa_sidebar,
    require_empresa,
    empresas_del_usuario,
)

st.set_page_config(page_title="Configuración", page_icon="⚙️", layout="wide")
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()

st.title("⚙️ Configuración")
st.markdown("---")

tab1, tab2, tab3 = st.tabs(["🏢 Empresas", "📂 Archivos de configuración", "👥 Usuarios"])

with tab1:
    st.markdown("### Mis empresas")
    empresas = empresas_del_usuario()
    if not empresas:
        st.warning("No tienes empresas asignadas.")
    else:
        import pandas as pd
        df = pd.DataFrame(empresas)
        st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.markdown("### ➕ Crear nueva empresa")
    st.info("🚧 Funcionalidad en desarrollo. Por ahora las empresas se crean "
            "directamente en Supabase.")

with tab2:
    st.markdown("### Archivos de configuración por empresa")
    st.info(
        "🚧 En desarrollo: aquí podrás subir los archivos `cuentas.xlsx` y "
        "`mapeos.xlsx` de cada empresa, equivalentes a los del .exe actual."
    )

with tab3:
    st.markdown("### Usuarios con acceso")
    st.info("🚧 En desarrollo: invitar usuarios y asignarles roles por empresa.")
