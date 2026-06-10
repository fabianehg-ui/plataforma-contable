"""
P&G Detallado Mensual por Centro de Costos - Plataforma Web

Flujo:
    1. El usuario sube los Balances de Prueba por CC de varios meses (.xlsx).
    2. (Opcional) Captura inventario inicial/final por mes y grupo
       (alimentos/bebidas y aseo/cafetería) para el costo de materia prima
       del consolidado.
    3. La plataforma genera un Excel con:
        - Índice de centros.
        - Consolidado (aplica el inventario capturado).
        - Una hoja por centro de costo (formato plantilla: meses + acumulado + A.V.).
    4. Previsualiza el consolidado o un centro en pantalla.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from core.reportes.reporte_centros_costos import cargar_balance, fusionar_prr
from core.reportes.pyg_detallado import construir_pyg, _mes_de_periodo
from core.reportes.exportador_pyg import exportar_pyg_excel
from core.reportes.plantilla_datos import generar_plantilla_datos, leer_plantilla_datos


st.set_page_config(page_title="P&G Detallado por CC", page_icon="📑", layout="wide")

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin", "operador", "consulta"])

st.title("📑 P&G Detallado Mensual por Centro de Costos")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    "Estado de resultados detallado, mensual y acumulado, por centro de costo"
)
st.markdown("---")

# ============================================================
# 1) Carga de balances mensuales
# ============================================================

st.markdown("### 1️⃣ Sube los Balances de Prueba por CC (uno por mes)")
archivos = st.file_uploader(
    "Puedes subir varios meses a la vez (.xlsx)",
    type=["xlsx"], accept_multiple_files=True,
)

if not archivos:
    st.info("👆 Sube al menos un balance mensual para empezar.")
    st.stop()


@st.cache_data(show_spinner="Leyendo balances...")
def _cargar(nombres_y_bytes):
    bals = []
    for nombre, contenido in nombres_y_bytes:
        try:
            b = cargar_balance(io.BytesIO(contenido))
            bals.append(b)
        except Exception as e:  # noqa: BLE001
            st.warning(f"No pude leer **{nombre}**: {e}")
    return bals


bals_all = _cargar([(a.name, a.getvalue()) for a in archivos])
if not bals_all:
    st.error("Ningún archivo se pudo leer.")
    st.stop()

# Agrupar por empresa (NIT)
from collections import defaultdict
por_nit = defaultdict(list)
for b in bals_all:
    por_nit[b.nit].append(b)
nits = list(por_nit.keys())
nombre_nit = {nit: por_nit[nit][0].empresa for nit in nits}

# Elegir empresa principal: la que coincide con la empresa activa, o la de más CC
nit_emp = str(emp.get("nit", "")).replace(".", "").replace("-", "").strip()[:9]
def _norm(n): return str(n).replace(".", "").replace("-", "").strip()[:9]
principal_nit = None
for nit in nits:
    if nit_emp and _norm(nit) == nit_emp:
        principal_nit = nit
if principal_nit is None:
    principal_nit = max(nits, key=lambda n: max(len(b.detalle["cc"].unique()) for b in por_nit[n]))

if len(nits) > 1:
    st.markdown("**Empresas detectadas:**")
    principal_nit = st.selectbox(
        "Empresa principal (las demás se incorporan por concepto, como Milagros)",
        nits, index=nits.index(principal_nit),
        format_func=lambda n: f"{nombre_nit[n]} ({n})",
    )

bals = sorted(por_nit[principal_nit], key=lambda b: _mes_de_periodo(b.periodo)[0])

# Las demás empresas = operación a incorporar (Milagros)
otros = [b for nit in nits if nit != principal_nit for b in por_nit[nit]]
bals_milagros = sorted(otros, key=lambda b: _mes_de_periodo(b.periodo)[0]) if otros else None
mil_label = (nombre_nit[[n for n in nits if n != principal_nit][0]].split()[0]
             if otros else "Milagros")

meses_info = [(_mes_de_periodo(b.periodo)[1], b.empresa) for b in bals]
msg = ("Empresa principal: **" + bals[-1].empresa + "** · Meses: "
       + ", ".join(m for m, _ in meses_info))
if bals_milagros:
    msg += f"  ·  Incorporando operación: **{mil_label}** ({len(bals_milagros)} meses)"
st.success(msg)

# Fusionar centros PRR / PRR MMTO en su punto principal
fusionar = st.checkbox(
    "Fusionar centros PRR y PRR MMTO en su punto principal",
    value=True,
    help="Suma los centros 'PRR ...' y 'PRR MMTO ...' dentro del punto del mismo "
         "nombre, en su cuenta de gasto correspondiente.",
)
if fusionar:
    bals = [fusionar_prr(b)[0] for b in bals]
    _, ne = fusionar_prr(sorted(bals, key=lambda b: _mes_de_periodo(b.periodo)[0])[-1])
    if bals_milagros:
        bals_milagros = [fusionar_prr(b)[0] for b in bals_milagros]
    if ne:
        st.warning("Centros PRR sin punto principal (quedaron separados): "
                   + ", ".join(f"{c} {n}" for c, n in ne))

# ============================================================
# 2) Plantilla de datos manuales (inventario + traslados) por CC
# ============================================================

st.markdown("### 2️⃣ Inventario y traslados por centro de costo (plantilla)")
st.caption(
    "El inventario y los traslados desde producción van por centro de costo, así "
    "que se capturan en una plantilla de Excel: descárgala con tus centros y meses, "
    "diligénciala y vuelve a subirla. Lo que dejes en 0 no afecta."
)

etq_t = bals[-1].etiqueta_cc()
ccs_t = sorted(bals[-1].detalle["cc"].unique())
mes_noms = [_mes_de_periodo(b.periodo)[1] for b in bals]
centros_plant = [(c, etq_t.get(c, c)) for c in ccs_t]

colp1, colp2 = st.columns(2)
with colp1:
    st.markdown("**a) Descargar plantilla en blanco**")
    plantilla_bytes = generar_plantilla_datos(centros_plant, mes_noms)
    st.download_button(
        "⬇️ Descargar plantilla de inventario y traslados",
        data=plantilla_bytes,
        file_name=f"Plantilla_datos_{bals[-1].empresa.split()[0]}.xlsx".replace(" ", "_"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
with colp2:
    st.markdown("**b) Subir plantilla diligenciada**")
    archivo_plant = st.file_uploader(
        "Plantilla diligenciada (.xlsx)", type=["xlsx"], key="plant_datos",
    )

inventarios, traslados = {}, {}
if archivo_plant is not None:
    try:
        inventarios, traslados = leer_plantilla_datos(io.BytesIO(archivo_plant.getvalue()))
        st.success(
            f"Plantilla leída: {len(inventarios)} datos de inventario y "
            f"{len(traslados)} traslados cargados."
        )
    except Exception as e:  # noqa: BLE001
        st.error(f"No pude leer la plantilla: {e}")

# ============================================================
# 3) Previsualización
# ============================================================

st.markdown("### 3️⃣ Previsualización")

etq = bals[-1].etiqueta_cc()
ccs = sorted(bals[-1].detalle["cc"].unique())
opciones = ["CONSOLIDADO (todos los centros)"] + [etq.get(c, c) for c in ccs]
nombre_a_cod = {etq.get(c, c): c for c in ccs}
sel = st.selectbox("Centro de costo a previsualizar", opciones)

cc_sel = None if sel.startswith("CONSOLIDADO") else nombre_a_cod[sel]
df = construir_pyg(bals, balances_milagros=bals_milagros, cc=cc_sel,
                   inventarios=inventarios, traslados=traslados, mil_label=mil_label)


def _fmt(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return v
    if abs(v) < 0.5:
        return "-"
    return f"({abs(v):,.0f})" if v < 0 else f"{v:,.0f}"


def _fmt_pct(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return f"{float(v)*100:.1f}%"


meses_cols = [c for c in df.columns if c not in ("Concepto", "Acumulado", "A.V.", "_tipo")]
df_show = df.drop(columns="_tipo").copy()
tipos = df["_tipo"].reset_index(drop=True)


def _estilo(row):
    t = tipos.iloc[row.name]
    if t == "header":
        return ["font-weight: bold; color: #1F4E78"] * len(row)
    if t == "subhdr":
        return ["font-weight: bold; font-style: italic"] * len(row)
    if t in ("sub", "ebitda"):
        return ["font-weight: bold; background-color: #D9E1F2"] * len(row)
    if t == "inv":
        return ["color: #0000FF"] * len(row)
    if t == "trasl":
        return ["color: #0000FF"] * len(row)
    if t == "mil":
        return ["font-style: italic; background-color: #FCE4D6"] * len(row)
    return [""] * len(row)


sty = (
    df_show.style
    .format(_fmt, subset=meses_cols + ["Acumulado"])
    .format(_fmt_pct, subset=["A.V."])
    .apply(_estilo, axis=1)
)
st.dataframe(sty, use_container_width=True, hide_index=True, height=700)

# ============================================================
# 4) Descarga del Excel completo
# ============================================================

st.markdown("### 4️⃣ Descargar Excel (Índice + Consolidado + una hoja por CC)")
col_a, col_b = st.columns(2)
solo_act = col_a.checkbox("Generar solo centros con actividad", value=True)
con_formulas = col_b.checkbox(
    "Excel con fórmulas (recalcula al editar a mano)", value=True,
    help="Los subtotales, utilidades, EBITDA, Acumulado y A.V. salen como "
         "fórmulas. Las celdas de inventario y traslados son las entradas: "
         "al cambiarlas en Excel, todo se recalcula solo.",
)

if st.button("⚙️ Generar Excel", type="primary"):
    with st.spinner("Generando hojas por centro de costo..."):
        xls = exportar_pyg_excel(bals, balances_milagros=bals_milagros,
                                 inventarios=inventarios, traslados=traslados,
                                 mil_label=mil_label, fusionar_prr_cc=False,
                                 con_formulas=con_formulas,
                                 solo_con_actividad=solo_act)
    nombre = f"PYG_Detallado_CC_{bals[-1].empresa.split()[0]}.xlsx".replace(" ", "_")
    st.download_button(
        "⬇️ Descargar Excel",
        data=xls, file_name=nombre,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
