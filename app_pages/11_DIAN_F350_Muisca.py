"""
app_pages/11_DIAN_F350_Muisca.py
Configuración del acceso a la DIAN (Muisca) por empresa y generación del BORRADOR
del Formulario 350 directamente en el portal, con descarga del PDF.

Depende de:
  core/f350/dian_acceso.py     (guardar/leer credenciales cifradas)
  core/f350/muisca_client.py   (login + llenar borrador + descargar PDF)
  Variable de entorno F350_FERNET_KEY (clave de cifrado).
  Tabla f350_dian_credenciales (db/migrations/013_*.sql).
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
from datetime import date

import streamlit as st

from auth.login import require_auth, sidebar_user_info, current_user
from auth.empresas import seleccionar_empresa_sidebar, require_empresa
from db.supabase_client import get_supabase

from core.f350 import dian_acceso as acc
from core.f350.muisca_client import MuiscaF350Client, MuiscaError
# Hook a tu módulo: debe devolver {numero_renglon: valor} para la empresa/periodo.
# Ajusta el import al nombre real de tu servicio que ya calcula los renglones del F350.
try:
    from core.f350.servicios import obtener_valores_renglones  # type: ignore
except Exception:  # noqa: BLE001
    obtener_valores_renglones = None


st.set_page_config(page_title="DIAN — Borrador F350 (Muisca)", page_icon="🏛️", layout="wide")

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()
sb = get_supabase()
user = current_user()

st.title("🏛️ DIAN — Borrador F350 en Muisca")
st.caption(f"Empresa: **{empresa['razon_social']}** · NIT {empresa['nit']}")

if not os.environ.get("F350_FERNET_KEY"):
    st.error("Falta la variable de entorno **F350_FERNET_KEY** (clave de cifrado). "
             "Genérala con: `python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
             "y cárgala en el entorno (Railway).")
    st.stop()

tab_cfg, tab_gen = st.tabs(["🔐 Acceso DIAN", "📄 Generar borrador"])

# =============================================================================
# TAB 1 — CONFIGURACIÓN DE ACCESO DIAN (credenciales cifradas)
# =============================================================================
with tab_cfg:
    st.subheader("Credenciales de acceso a Muisca")
    st.caption("Se guardan **cifradas**. La contraseña nunca se muestra ni se almacena en texto plano. "
               "El borrador se genera para tu revisión; la firma y presentación las haces tú.")

    estado = acc.estado_credenciales(sb, empresa["id"])
    if estado:
        st.success(f"Configurado ✓ · Documento {estado.get('tipo_doc')} {estado.get('num_doc_enmasc')} · "
                   f"actualizado {str(estado.get('actualizado_en'))[:10]}")
    else:
        st.info("Aún no hay credenciales DIAN para esta empresa.")

    with st.form("cfg_dian"):
        c1, c2 = st.columns(2)
        tipo_doc = c1.selectbox("Tipo de documento (usuario DIAN)", ["CC", "CE", "TI", "PP", "NIT"], index=0)
        num_doc = c2.text_input("Número de documento (cédula del usuario)")
        password = st.text_input("Contraseña DIAN", type="password",
                                 help="Se cifra antes de guardar. Solo se usa en el momento de iniciar sesión.")
        col_a, col_b = st.columns(2)
        guardar = col_a.form_submit_button("Guardar credenciales", type="primary")
        borrar = col_b.form_submit_button("Borrar credenciales")

    if guardar:
        if not num_doc or not password:
            st.warning("Completa número de documento y contraseña.")
        else:
            acc.guardar_credenciales(sb, empresa["id"], tipo_doc, num_doc, password,
                                     user_id=user.get("id") if isinstance(user, dict) else None)
            st.success("Credenciales guardadas (cifradas) ✓")
            st.rerun()
    if borrar:
        acc.borrar_credenciales(sb, empresa["id"])
        st.info("Credenciales eliminadas.")
        st.rerun()

# =============================================================================
# TAB 2 — GENERAR BORRADOR EN MUISCA Y DESCARGAR PDF
# =============================================================================
with tab_gen:
    st.subheader("Diligenciar borrador del F350 y descargar PDF")

    if not acc.estado_credenciales(sb, empresa["id"]):
        st.warning("Primero configura el acceso DIAN en la pestaña anterior.")
        st.stop()

    c1, c2, c3 = st.columns(3)
    anio = c1.number_input("Año", min_value=2020, max_value=2100, value=date.today().year, step=1)
    periodo = c2.number_input("Periodo (mes 1-12)", min_value=1, max_value=12, value=max(1, date.today().month - 1), step=1)
    actividad = c3.text_input("Actividad económica (CIIU, renglón 27)",
                              value=str(empresa.get("ciiu_principal", "") or ""))

    st.markdown("**Valores por renglón** que se van a diligenciar:")
    valores = None
    if obtener_valores_renglones is not None:
        try:
            valores = obtener_valores_renglones(sb, empresa["id"], int(anio), int(periodo))
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude traer los renglones calculados por el módulo: {e}")
    if not valores:
        st.info("Conecta aquí la función de tu módulo que devuelve {renglón: valor}. "
                "Mientras tanto puedes cargarlos manualmente para probar (formato: renglón=valor por línea).")
        texto = st.text_area("Renglones manuales (ej. `29=1200000`)", height=120)
        valores = {}
        for ln in texto.splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                try:
                    valores[int(k.strip())] = float(v.strip().replace(".", "").replace(",", "."))
                except ValueError:
                    pass

    if valores:
        st.dataframe([{"Renglón": k, "Valor": v} for k, v in sorted(valores.items())], use_container_width=True)

    st.warning("Esto genera un **BORRADOR** para revisar. La firma y presentación en Muisca las haces tú.")

    if st.button("Generar borrador en Muisca y descargar PDF", type="primary", disabled=not valores):
        cred = acc.obtener_credenciales(sb, empresa["id"])
        salida = f"/tmp/F350_{empresa['nit']}_{anio}_{periodo}.pdf"
        try:
            with st.spinner("Ingresando a la DIAN, diligenciando el borrador y generando el PDF…"):
                cli = MuiscaF350Client()
                ruta, form_id = cli.diligenciar_y_descargar(
                    tipo_doc=cred["tipo_doc"], num_doc=cred["num_doc"],
                    nit_empresa=empresa["nit"], password=cred["password"],
                    nit=empresa["nit"], dv=str(empresa.get("dv", "")),
                    razon_social=empresa["razon_social"],
                    anio=int(anio), periodo=int(periodo),
                    actividad_economica=actividad or None,
                    valores_por_renglon=valores, ruta_pdf=salida,
                )
            st.success(f"Borrador generado en Muisca ✓ · Formulario {form_id}")
            with open(ruta, "rb") as fh:
                st.download_button("⬇ Descargar PDF del borrador", data=fh.read(),
                                   file_name=f"F350_{empresa['nit']}_{anio}_{periodo}.pdf",
                                   mime="application/pdf")
        except MuiscaError as e:
            st.error(f"Muisca: {e}")
        except Exception as e:  # noqa: BLE001
            st.error(f"Error inesperado: {e}")
