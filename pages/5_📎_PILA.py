"""
Módulo PILA - Plataforma Web

Flujo:
    1. Usuario sube el PDF de planilla PILA (SuAporte / Enlace Operativo)
    2. El sistema extrae: datos del aportante, empleados, totales
    3. Muestra tabla de empleados y totales
    4. Descarga Excel con el desglose

Uso posterior: los datos extraídos quedan disponibles en session_state
para que el módulo de Provisiones los use como valores reales (reemplazando
los teóricos).
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from core.lectores.lector_pila import (
    extraer_pila,
    empleados_a_dataframe,
    totales_a_dataframe,
    resumen_texto,
    exportar_excel,
)


# ============================================================
# Configuración de la página
# ============================================================

st.set_page_config(
    page_title="PILA",
    page_icon="📎",
    layout="wide",
)

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin", "operador", "consulta"])


# ============================================================
# Encabezado
# ============================================================

st.title("📎 Lector de planilla PILA")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    f"Extrae datos del PDF de aportes de seguridad social"
)
st.markdown("---")


# ============================================================
# Sidebar: info
# ============================================================

with st.sidebar:
    st.markdown("### 📋 Formato esperado")
    st.caption(
        "PDF de planilla PILA generado por **Enlace Operativo (SuAporte)**. "
        "El sistema extrae automáticamente:\n\n"
        "- Datos del aportante (empresa, NIT, periodo)\n"
        "- Tabla de empleados con IBC y aportes\n"
        "- Totales consolidados"
    )
    st.markdown("---")
    st.markdown("### ℹ️ Nota")
    st.caption(
        "Los datos extraídos se guardan en tu sesión para que el módulo de "
        "**Provisiones** (cuando se active) pueda usarlos como valores reales."
    )


# ============================================================
# Subida del archivo
# ============================================================

st.markdown("### 1️⃣ Sube el PDF")

archivo_pdf = st.file_uploader(
    "PDF de planilla PILA",
    type=["pdf"],
    key="file_pila",
    help="Arrastra el archivo o haz click para seleccionar",
)

if not archivo_pdf:
    st.info("📂 Sube el PDF de planilla PILA para continuar.")

    # Si ya hay datos en sesión de un PDF anterior, mostrar aviso
    if "datos_pila" in st.session_state:
        datos_previos = st.session_state["datos_pila"]
        with st.expander("📄 Tienes un PILA cargado previamente en esta sesión"):
            st.text(resumen_texto(datos_previos))
            if st.button("🗑️ Eliminar datos previos"):
                st.session_state.pop("datos_pila", None)
                st.rerun()
    st.stop()


# ============================================================
# Procesar
# ============================================================

st.markdown("### 2️⃣ Procesar")

procesar = st.button("🚀 Extraer datos del PILA", type="primary")

# Si ya procesamos en esta sesión con este mismo archivo, no reprocesar
hash_archivo = f"{archivo_pdf.name}:{archivo_pdf.size}"
if procesar or (
    "datos_pila" in st.session_state
    and st.session_state.get("pila_hash") == hash_archivo
):
    if procesar or "datos_pila" not in st.session_state:
        with st.spinner("Extrayendo datos del PDF..."):
            try:
                datos = extraer_pila(archivo_pdf)
                st.session_state["datos_pila"] = datos
                st.session_state["pila_hash"] = hash_archivo
                st.session_state["pila_nombre"] = archivo_pdf.name
            except ImportError as e:
                st.error(
                    f"❌ **Falta una dependencia:** {e}\n\n"
                    f"Agrega `pdfplumber>=0.10.0` a tu `requirements.txt` "
                    f"y reinicia la aplicación."
                )
                st.stop()
            except Exception as e:
                st.error(f"❌ Error al leer el PDF: {e}")
                st.exception(e)
                st.stop()
else:
    st.stop()


# ============================================================
# Mostrar resultado
# ============================================================

datos = st.session_state["datos_pila"]

st.markdown("### 3️⃣ Datos extraídos")

# Header con info de la empresa
col_a, col_b, col_c = st.columns(3)
with col_a:
    raz = datos.get("razon_social", "—")
    st.metric("Empresa", raz[:30] + ("…" if len(raz) > 30 else ""))
    st.caption(f"NIT: {datos.get('nit_empresa', '—')}")
with col_b:
    st.metric("Número planilla", datos.get("numero_planilla", "—"))
    st.caption(f"Periodo cotización: {datos.get('periodo_cotizacion', '—')}")
with col_c:
    st.metric("Empleados", len(datos.get("empleados", [])))
    st.caption(f"Periodo servicio: {datos.get('periodo_servicio', '—')}")

# Validación visual: ¿la empresa del PDF coincide con la empresa activa?
nit_pila = (datos.get("nit_empresa") or "").replace(".", "").replace("-", "").strip()
nit_emp_raw = emp.get("nit") or ""
# Quitar puntos y guiones + dígito de verificación (ej: "900473959-3" → "900473959")
nit_emp_base = (
    nit_emp_raw.split("-")[0].replace(".", "").strip()
    if "-" in nit_emp_raw
    else nit_emp_raw.replace(".", "").strip()[:9]
)

if nit_pila and nit_emp_base and nit_pila != nit_emp_base:
    st.warning(
        f"⚠️ **El NIT del PILA ({nit_pila}) no coincide con la empresa activa "
        f"({emp['razon_social']} - {emp['nit']}).** "
        f"Verifica que estás en la empresa correcta."
    )

st.markdown("---")

# Tabs para empleados vs totales
tab_emp, tab_tot, tab_resumen = st.tabs([
    f"👥 Empleados ({len(datos.get('empleados', []))})",
    "💰 Totales",
    "📝 Resumen texto",
])

with tab_emp:
    df_emp = empleados_a_dataframe(datos)
    if len(df_emp) == 0:
        st.warning("No se extrajeron empleados. Revisa el formato del PDF.")
    else:
        st.dataframe(
            df_emp,
            use_container_width=True,
            height=500,
            column_config={
                col: st.column_config.NumberColumn(format="$ %d")
                for col in df_emp.columns
                if col not in ("Cédula", "Nombre")
            },
        )

        # Validación: suma de aportes por empleado vs total
        suma_pension = int(df_emp["Aporte Pensión"].sum())
        suma_salud = int(df_emp["Aporte Salud"].sum())

        tot = datos.get("totales", {})
        desajustes = []
        if tot.get("aporte_pension", 0) != suma_pension:
            desajustes.append(
                f"Pensión: empleados suman ${suma_pension:,} pero el "
                f"total en el PDF dice ${tot.get('aporte_pension', 0):,}"
            )
        if tot.get("aporte_salud", 0) != suma_salud:
            desajustes.append(
                f"Salud: empleados suman ${suma_salud:,} pero el "
                f"total en el PDF dice ${tot.get('aporte_salud', 0):,}"
            )

        if desajustes:
            with st.expander("⚠️ Diferencias entre suma de empleados y totales del PDF"):
                for d in desajustes:
                    st.text(f"- {d}")
                st.caption(
                    "Estas diferencias pueden ser normales si el PDF incluye "
                    "novedades (licencias, incapacidades) que no se sumaron "
                    "al empleado individualmente."
                )

with tab_tot:
    df_tot = totales_a_dataframe(datos)
    st.dataframe(
        df_tot,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Valor": st.column_config.NumberColumn(format="$ %d"),
        },
    )

    st.info(
        "💡 **Recordatorio sobre exoneraciones (art. 114-1 E.T.):** "
        "Si la empresa está exonerada del 8.5% de salud empleador, "
        "ICBF (3%) y SENA (2%), esos renglones deben aparecer en $0 "
        "o con solo el aporte del 4% del empleado (en el caso de salud)."
    )

with tab_resumen:
    st.code(resumen_texto(datos), language=None)


# ============================================================
# Descargar
# ============================================================

st.markdown("### 4️⃣ Descargar")

col_d1, col_d2 = st.columns(2)

with col_d1:
    excel_bytes = exportar_excel(datos)
    nombre_base = st.session_state.get("pila_nombre", "pila.pdf").rsplit(".", 1)[0]
    st.download_button(
        "📊 Descargar Excel con el desglose",
        data=excel_bytes,
        file_name=f"{nombre_base}_desglosado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )

with col_d2:
    if st.button("🔄 Procesar otro PDF", use_container_width=True):
        for k in ("datos_pila", "pila_hash", "pila_nombre"):
            st.session_state.pop(k, None)
        st.rerun()
