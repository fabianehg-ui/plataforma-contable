"""
28_Cargar_Plano_Contai.py — Subir información contable por archivo plano (Contai).

Sube un archivo plano de Contai (TXT/CSV, 11 columnas, SIN encabezado) o pégalo
como texto, se muestra la vista previa con el cuadre, y se puede:
  - **Agregar al movimiento del mes** (contabilizar en cn_movimientos), o
  - **Descargar el plano normalizado** (11 columnas).

Formato del plano (11 columnas, separadas por TAB):
  CUENTA · COMPROBANTE · FECHA · DOCUMENTO · DOC REFERENCIA · NIT · DETALLE ·
  TR (1=Débito, 2=Crédito) · VALOR · BASE · CENTRO DE COSTO
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from auth.guard import guard_empresa
from core.contable import integracion as integ
from core.contable import servicio_contable as cont
from core.contable.ui_contabilizar import render_contabilizar


st.title("📄 Cargar plano contable (Contai)")
emp, sb = guard_empresa(["admin", "operador"])
st.caption(f"Empresa activa: **{emp['razon_social']}** · sube el TXT de Contai → cn_movimientos")

try:
    from core.ayuda import render_ayuda
    render_ayuda("plano_contai")
except Exception:
    pass
st.markdown("---")

st.markdown(
    "Sube un **archivo plano de Contai** (TXT/CSV de 11 columnas, separadas por "
    "TAB, **sin encabezado**) o pega el contenido. Orden de columnas: "
    "`CUENTA · COMPROBANTE · FECHA · DOCUMENTO · DOC REFERENCIA · NIT · DETALLE · "
    "TR · VALOR · BASE · CENTRO DE COSTO` (TR: 1=Débito, 2=Crédito)."
)

modo = st.radio("¿Cómo quieres cargar el plano?",
                ["Subir archivo", "Pegar texto"], horizontal=True)

contenido = None
if modo == "Subir archivo":
    up = st.file_uploader("Archivo plano (.txt / .csv)", type=["txt", "csv"],
                          accept_multiple_files=False,
                          help="Arrastra y suelta el archivo aquí.")
    if up is not None:
        contenido = up.getvalue()
else:
    txt = st.text_area("Pega aquí el contenido del plano", height=200,
                       placeholder="1105\t1\t2026-06-30\t...\t1\t100000\t0\t")
    if txt.strip():
        contenido = txt

if not contenido:
    st.info("Carga un archivo o pega el texto para ver la vista previa.")
    st.stop()

# Parseo con el mismo helper que usan Bittal/Bancos
try:
    df = integ.plano_texto_a_df(contenido)
except Exception as e:
    st.error(f"No se pudo leer el plano: {e}")
    st.stop()

if df is None or len(df) == 0:
    st.warning("El plano está vacío o no tiene el formato esperado (11 columnas, TAB).")
    st.stop()

st.markdown("### 👁️ Vista previa")
st.caption(f"{len(df)} líneas leídas.")
st.dataframe(df, use_container_width=True, hide_index=True)

# Descargar el plano normalizado (opción "generar plano")
try:
    txt_norm = "\n".join(
        "\t".join(str(v) for v in fila) for fila in df.itertuples(index=False)
    )
    st.download_button(
        "⬇️ Descargar plano normalizado (11 columnas)",
        txt_norm.encode("utf-8"),
        file_name="plano_contai_normalizado.txt",
        mime="text/plain",
    )
except Exception:
    pass

st.markdown("---")
# Opción "agregar al movimiento del mes" (contabiliza en cn_movimientos)
render_contabilizar(sb, emp, df, origen="plano_contai",
                    titulo="💾 Agregar al movimiento del mes")
