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
# Reutiliza los procesadores YA EXISTENTES del módulo (no duplica lógica):
from core.f350.procesador import procesar_declaracion          # parser + clasificador + nit_utils + autorretención
from core.f350.muisca_adapter import casillas_desde_procesado  # {concepto/tipo} -> {casilla: valor}


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
    st.caption("Ingresa el **NIT de la empresa** (arriba, empresa activa), y el **tipo y número de documento del REPRESENTANTE**. Se guardan **cifradas**. La contraseña nunca se muestra en texto plano. "
               "El borrador se genera para tu revisión; la firma y presentación las haces tú.")

    estado = acc.estado_credenciales(sb, empresa["id"])
    if estado:
        st.success(f"Configurado ✓ · Documento {estado.get('tipo_doc')} {estado.get('num_doc_enmasc')} · "
                   f"actualizado {str(estado.get('actualizado_en'))[:10]}")
    else:
        st.info("Aún no hay credenciales DIAN para esta empresa.")

    with st.form("cfg_dian"):
        c1, c2 = st.columns(2)
        tipo_doc = c1.selectbox("Tipo de documento del representante", ["CC", "CE", "TI", "PP", "NIT"], index=0)
        num_doc = c2.text_input("Número de documento del REPRESENTANTE (sin puntos)")
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

    st.markdown("**Reportes de Contai (PDF):**")
    cc1, cc2 = st.columns(2)
    aux_pdf = cc1.file_uploader("Auxiliar de retención (Análisis de % de Retención e IVA)", type=["pdf"], key="aux")
    bal_pdf = cc2.file_uploader("Balance de prueba (ingresos, para autorretención)", type=["pdf"], key="bal")

    cd1, cd2 = st.columns(2)
    tarifa = cd1.number_input("Tarifa autorretención 114-1 (%)", min_value=0.0, max_value=100.0,
                              value=float(empresa.get("tarifa_autorretencion", 0.0) or 0.0), step=0.01,
                              help="Tarifa del CIIU vigente. Si es 0 o no aplica, la autorretención queda en 0.")
    es_exonerado = cd2.checkbox("Empresa exonerada del Art. 114-1", value=bool(empresa.get("exonerado_114", False)))

    valores = {}
    if aux_pdf is not None:
        try:
            resultado = procesar_declaracion(
                auxiliar_fuente=aux_pdf.getvalue(),
                balance_fuente=(bal_pdf.getvalue() if bal_pdf is not None else None),
                tarifa_pct=float(tarifa),
                es_exonerado=es_exonerado,
            )
            adap = casillas_desde_procesado(resultado)
            valores = adap["casillas"]
            for a in adap.get("avisos", []):
                st.warning(a)
            for w in resultado.get("advertencias", []) or []:
                st.info(w)

            tot = resultado.get("totales", {})
            m1, m2, m3 = st.columns(3)
            m1.metric("Retención renta", f"{tot.get('total_retenciones_renta', 0):,}".replace(",", "."))
            m2.metric("Autorretención", f"{tot.get('valor_autorretencion', 0):,}".replace(",", "."))
            m3.metric("Retención IVA", f"{tot.get('total_retenciones_iva', 0):,}".replace(",", "."))

            if resultado.get("movimientos"):
                st.markdown("**Movimientos clasificados (revisa jurídica/natural y concepto):**")
                st.dataframe(resultado["movimientos"], use_container_width=True)
            st.markdown("**Casillas que se enviarán al F350:**")
            st.dataframe([{"Casilla": k, "Valor": v} for k, v in sorted(valores.items())], use_container_width=True)
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude procesar los reportes con el módulo F350: {e}")
    else:
        st.info("Sube al menos el **auxiliar de retención**. El **balance** es necesario para calcular la autorretención 114-1.")

    st.warning("Esto genera un **BORRADOR** para revisar. La firma y presentación en Muisca las haces tú. "
               "Verifica los movimientos (jurídica/natural y concepto) antes de enviar.")

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
