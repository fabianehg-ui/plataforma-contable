import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_empresa()

st.title("🛒 Compras DIAN")
st.caption(f"Empresa activa: **{emp['razon_social']}**")
st.markdown("---")

st.info(
    "🚧 **Módulo en desarrollo.**\n\n"
    "Este módulo replicará la lógica de `procesador_compras_dian.py` del "
    "ejecutable original. Incluirá el procesamiento de facturas electrónicas "
    "recibidas, cálculo de retenciones, y generación del plano contable."
)

st.markdown("### 📋 Funcionalidades previstas")
st.markdown("""
- Carga del Excel con facturas DIAN del mes
- Procesamiento de IVA por tarifa (19%, 5%, 0%)
- Cálculo automático de retenciones (Fuente, IVA, ICA)
- Triangulación a centros de costos
- Detección de nuevos proveedores
- Generación del plano TSV listo para importar
""")

st.markdown("### 🔄 Plan de migración")
st.markdown("""
1. Copiar `procesador_compras_dian.py` (827 líneas) a `core/procesadores/`
2. Adaptar para recibir archivo en memoria (igual que Caja Menor)
3. Adaptar la UI para formularios web (reemplazar Tkinter)
4. Agregar guardado del resultado en el histórico
""")
