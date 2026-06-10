"""
Reportes por Centro de Costos - Plataforma Web

Flujo:
    1. El usuario sube el "Balance de Prueba por Cuenta con CC" exportado
       del software contable (.xlsx).
    2. La plataforma muestra:
        - Estado de Resultados por centro de costos (una columna por CC).
        - Resumen por CC (ingresos / costos / gastos / utilidad).
        - Balance de prueba por CC (detalle de cuentas hoja).
    3. Descarga el reporte completo en Excel.

El usuario elige la base del estado de resultados:
    - Acumulado del año (Nuevo Saldo).
    - Movimiento del periodo (Débitos - Créditos).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import (
    seleccionar_empresa_sidebar,
    require_rol,
)
from core.reportes.reporte_centros_costos import (
    cargar_balance,
    estado_resultados_por_cc,
    resumen_por_cc,
    balance_por_cc,
    ETIQUETA_TOTAL,
)
from core.reportes.exportador_excel import exportar_excel


# ============================================================
# Configuración de la página
# ============================================================

st.set_page_config(
    page_title="Reportes por Centro de Costos",
    page_icon="📊",
    layout="wide",
)

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin", "operador", "consulta"])


# ============================================================
# Encabezado
# ============================================================

st.title("📊 Reportes por Centro de Costos")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    "Balance de prueba y estado de resultados por centro de costos"
)
st.markdown("---")


# ============================================================
# Sidebar: opciones
# ============================================================

with st.sidebar:
    st.markdown("### ⚙️ Opciones del reporte")
    base_label = st.radio(
        "Base del Estado de Resultados",
        ["Acumulado del año", "Movimiento del periodo"],
        help=(
            "Acumulado usa el 'Nuevo Saldo' (resultado del año a la fecha). "
            "Periodo usa el movimiento del mes (Débitos − Créditos)."
        ),
    )
    base = "acumulado" if base_label.startswith("Acumulado") else "periodo"

    clase6_en_costos = st.checkbox(
        "Incluir clase 6 dentro de Costos",
        value=True,
        help=(
            "La clase 6 (p. ej. 6140 Costo de Alimentos) se suma a 'Costos' "
            "junto con 71/72/73. Desactívalo para llevarla a 'Otros gastos'."
        ),
    )

    nivel_label = st.radio(
        "Nivel de detalle del balance",
        ["6 dígitos (subcuenta)", "8 dígitos (auxiliar)"],
        help="Nivel al que se agregan las cuentas en el Balance de Prueba por CC.",
    )
    nivel_detalle = 6 if nivel_label.startswith("6") else 8


# ============================================================
# Carga del archivo
# ============================================================

st.markdown("### 1️⃣ Sube el Balance de Prueba por Cuenta con CC")
archivo = st.file_uploader(
    "Archivo .xlsx exportado del software contable",
    type=["xlsx"],
    help=(
        "Debe ser el 'Balance de Prueba por Cuenta con CC'. "
        "Columnas esperadas: Cuenta, Equivalencia, Nombre, Centro de Costos, "
        "Nombre CC, Saldo Anterior, Débitos, Créditos, Nuevo Saldo."
    ),
)

if archivo is None:
    st.info("👆 Sube un archivo para generar los reportes.")
    st.stop()


# ------------------------------------------------------------
# Procesar
# ------------------------------------------------------------

@st.cache_data(show_spinner="Procesando balance...")
def _procesar(contenido: bytes):
    import io
    bal = cargar_balance(io.BytesIO(contenido))
    return bal


try:
    bal = _procesar(archivo.getvalue())
except Exception as e:  # noqa: BLE001
    st.error(f"No pude leer el archivo: {e}")
    st.stop()

# Aviso si el NIT del archivo no coincide con la empresa activa
nit_emp = str(emp.get("nit", "")).replace(".", "").replace("-", "").strip()
nit_arch = bal.nit.replace(".", "").replace("-", "").strip()
if nit_emp and nit_arch and nit_emp[:9] != nit_arch[:9]:
    st.warning(
        f"⚠️ El NIT del archivo (**{bal.nit} – {bal.empresa}**) no coincide con "
        f"la empresa activa (**{emp['razon_social']}**). Verifica que subiste "
        "el balance correcto."
    )

c1, c2, c3 = st.columns(3)
c1.metric("Empresa (archivo)", bal.empresa)
c2.metric("Periodo", bal.periodo)
c3.metric("Centros de costo", bal.detalle["cc"].nunique())

st.markdown("---")


# ============================================================
# Helpers de formato para pantalla
# ============================================================

def _fmt_num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return v
    if abs(v) < 0.5:
        return "-"
    if v < 0:
        return f"({abs(v):,.0f})"
    return f"{v:,.0f}"


# ============================================================
# Tabs
# ============================================================

tab_er, tab_resumen, tab_balance = st.tabs([
    "📈 Estado de Resultados por CC",
    "🧮 Resumen por CC",
    "📋 Balance de Prueba por CC",
])

# ---------- Tab 1: Estado de resultados ----------
with tab_er:
    base_txt = "Acumulado del año" if base == "acumulado" else "Movimiento del periodo"
    st.subheader(f"Estado de Resultados · {base_txt}")

    er = estado_resultados_por_cc(bal, base=base, clase6_en_costos=clase6_en_costos)
    centros = [c for c in er.columns if c not in ("Concepto", ETIQUETA_TOTAL, "_tipo")]

    # Selector de centros a mostrar (para no saturar con 80 columnas)
    opciones_cc = [f"{c}" for c in centros]
    sel = st.multiselect(
        "Centros de costo a mostrar (vacío = todos)",
        opciones_cc,
        default=[],
    )
    cols_mostrar = ["Concepto"] + (sel if sel else centros) + [ETIQUETA_TOTAL]

    er_show = er[cols_mostrar].copy()
    tipos = er["_tipo"].reset_index(drop=True)

    def _estilo_fila(row):
        t = tipos.iloc[row.name]
        if t in ("subtotal", "ebitda"):
            return ["font-weight: bold; background-color: #D9E1F2"] * len(row)
        if t == "memo":
            return ["font-style: italic; color: #808080"] * len(row)
        return [""] * len(row)

    sty = (
        er_show.style
        .format(_fmt_num, subset=[c for c in cols_mostrar if c != "Concepto"])
        .apply(_estilo_fila, axis=1)
    )
    st.dataframe(sty, use_container_width=True, hide_index=True,
                 height=min(60 + 35 * len(er_show), 700))

# ---------- Tab 2: Resumen ----------
with tab_resumen:
    st.subheader("Resumen por Centro de Costo")
    res = resumen_por_cc(bal, base=base, clase6_en_costos=clase6_en_costos,
                         usar_nombre_cc=True)
    es_total = res["Centro de Costo"] == ETIQUETA_TOTAL
    num_cols = ["Ingresos", "Utilidad bruta", "Utilidad operacional",
                "Utilidad neta", "EBITDA"]
    sty = (
        res.style
        .format(_fmt_num, subset=num_cols)
        .format("{:.1f}%", subset=["Margen neto %"])
        .apply(lambda row: ["font-weight: bold; background-color: #D9E1F2"
                            if es_total.iloc[row.name] else "" for _ in row], axis=1)
    )
    st.dataframe(sty, use_container_width=True, hide_index=True,
                 height=min(60 + 35 * len(res), 700))

    # Gráfico de EBITDA por CC (sin el total)
    graf = res[~es_total][["Centro de Costo", "EBITDA"]].set_index("Centro de Costo")
    st.markdown("##### EBITDA por centro de costo")
    st.bar_chart(graf)

# ---------- Tab 3: Balance de prueba ----------
with tab_balance:
    st.subheader("Balance de Prueba por Centro de Costo")
    etq = bal.etiqueta_cc()
    centros_cod = list(bal.detalle["cc"].drop_duplicates().sort_values())
    opciones = ["(Todos)"] + [etq.get(c, c) for c in centros_cod]
    nombre_a_cod = {etq.get(c, c): c for c in centros_cod}
    cc_nombre = st.selectbox(
        "Centro de costo",
        opciones,
        help="Filtra el balance a un centro de costo específico.",
    )
    cc_sel = None if cc_nombre == "(Todos)" else nombre_a_cod[cc_nombre]
    solo_res = st.checkbox("Solo cuentas de resultado (clases 4 a 7)", value=False)

    df_bal = balance_por_cc(
        bal,
        cc=cc_sel,
        solo_resultado=solo_res,
        nivel_detalle=nivel_detalle,
        usar_nombre_cc=True,
    )
    df_show = df_bal.rename(columns={
        "cuenta": "Cuenta", "nombre": "Nombre",
        "saldo_ant": "Saldo Anterior",
        "debitos": "Débitos", "creditos": "Créditos", "nuevo_saldo": "Nuevo Saldo",
    })
    st.caption(f"{len(df_show):,} filas · nivel de detalle: {nivel_detalle} dígitos")
    st.dataframe(
        df_show.style.format(_fmt_num,
                             subset=["Saldo Anterior", "Débitos", "Créditos", "Nuevo Saldo"]),
        use_container_width=True, hide_index=True, height=600,
    )


# ============================================================
# Descarga
# ============================================================

st.markdown("---")
st.markdown("### 2️⃣ Descargar reporte en Excel")

xls = exportar_excel(bal, base=base, clase6_en_costos=clase6_en_costos,
                     nivel_detalle=nivel_detalle)
nombre = f"Reporte_CC_{bal.empresa.split()[0]}_{bal.periodo}.xlsx".replace(" ", "_")
st.download_button(
    "⬇️ Descargar Excel (Estado de Resultados + Resumen + Balance)",
    data=xls,
    file_name=nombre,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
)
