"""
app_pages/13_Factura_Electronica.py

UI de emisión de Facturas Electrónicas de Venta (FE) ante DIAN.

Conecta con el backend core/dian_fe (ServicioFE) que reusa el certificado del
vault de core/dian_pt y envía vía SendBillSync. Dos pestañas:

  1. Emitir factura   — formulario de factura (cabecera + líneas) y envío
  2. Vista previa XML  — genera el XML UBL sin enviar, para inspección

ADVERTENCIA: el backend NO está habilitado por DIAN (requiere pasar el set de
pruebas y certificado .p12 real). Los envíos van al ambiente de HABILITACIÓN.
Notas crédito/débito y casos complejos (retenciones, multi-IVA) aún no están.
"""
from __future__ import annotations

import os
import sys
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa

from core.dian_fe import (
    Factura, LineaFactura, ParteFE, Resolucion, MedioPago, ImpuestoLinea,
    calcular_cufe_desde_factura, generar_xml_factura,
    TIPO_DOC_NIT, TIPO_DOC_CC, ORG_JURIDICA, ORG_NATURAL, RESP_IVA,
    TIPO_FACTURA_VENTA, FORMA_PAGO_CONTADO, MEDIO_PAGO_EFECTIVO,
)
from core.dian_fe.servicio_fe import ServicioFE


TZ = "America/Bogota"

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

st.title("🧾 Facturación Electrónica DIAN")
st.caption(
    "Emisión de Facturas Electrónicas de Venta (FE) como software propio ante DIAN."
)

st.warning(
    "⚠️ **Ambiente de HABILITACIÓN.** Conecta con el backend real (`core/dian_fe/`) "
    "pero DIAN aún no ha habilitado el software en producción. Notas crédito/débito, "
    "retenciones y múltiples tasas de IVA por factura todavía no están soportadas."
)


# ── Clave maestra del vault (secret/env si existe; si no, se pide) ──
def _master_desde_entorno():
    try:
        v = st.secrets.get("DIAN_MASTER_PWD")  # type: ignore[attr-defined]
        if v:
            return str(v)
    except Exception:
        pass
    return os.getenv("DIAN_MASTER_PWD")


def _obtener_master():
    env = _master_desde_entorno()
    if env:
        return env
    st.markdown("### 🔐 Clave maestra del vault")
    st.caption(
        "Descifra el certificado .p12. Solo vive en esta sesión. "
        "**Mínimo 8 caracteres** — usa siempre la misma."
    )
    pwd = st.text_input(
        "Clave maestra", type="password", key="_fe_master",
        placeholder="Al menos 8 caracteres…",
    )
    if not pwd:
        return None
    if len(pwd) < 8:
        st.error(
            f"La clave debe tener al menos 8 caracteres (tiene {len(pwd)})."
        )
        return None
    return pwd


MASTER = _obtener_master()
if not MASTER:
    st.info(
        "🔐 Escribe la **clave maestra del vault** arriba "
        "(o configura el secret `DIAN_MASTER_PWD`)."
    )
    st.stop()


@st.cache_resource(show_spinner=False)
def _servicio(master: str) -> ServicioFE:
    return ServicioFE(master_password=master)


try:
    servicio = _servicio(MASTER)
except ValueError as e:
    st.error(f"No se pudo iniciar el servicio: {e}")
    st.stop()


nit_emisor = str(empresa.get("nit", "")).split("-")[0].strip()
razon_emisor = empresa.get("razon_social", "")

# ¿Tiene credenciales registradas?
try:
    registrados = {c["nit"] for c in servicio.listar_clientes()}
except Exception:
    registrados = set()

if nit_emisor not in registrados:
    st.warning(
        f"La empresa activa (NIT {nit_emisor}) no tiene certificado registrado en "
        "el vault. Regístralo en la página **RADIAN Eventos → ⚙️ Configuración** "
        "(el certificado es compartido entre RADIAN y Facturación)."
    )


def _dec(v, campo):
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Valor numérico inválido en {campo}: {v!r}")


def _construir_factura(cab: dict, lineas_df: pd.DataFrame) -> Factura:
    reso = Resolucion(
        numero=cab["reso_numero"], prefijo=cab["reso_prefijo"],
        rango_desde=int(cab["reso_desde"]), rango_hasta=int(cab["reso_hasta"]),
        fecha_desde=cab["reso_fdesde"], fecha_hasta=cab["reso_fhasta"],
        clave_tecnica=cab.get("clave_tecnica", ""),
    )
    emisor = ParteFE(
        numero_documento=nit_emisor, tipo_documento_id=TIPO_DOC_NIT,
        dv=cab.get("emisor_dv", ""), razon_social=razon_emisor,
        tipo_organizacion=ORG_JURIDICA, responsabilidades=[RESP_IVA],
        municipio_codigo=cab.get("emisor_mun", "05001"),
    )
    adq = ParteFE(
        numero_documento=cab["adq_doc"],
        tipo_documento_id=cab["adq_tipo"],
        dv=cab.get("adq_dv", ""),
        razon_social=cab["adq_nombre"],
        tipo_organizacion=(ORG_JURIDICA if cab["adq_tipo"] == TIPO_DOC_NIT else ORG_NATURAL),
        municipio_codigo=cab.get("adq_mun", "05001"),
    )

    lineas = []
    for i, row in lineas_df.reset_index(drop=True).iterrows():
        desc = str(row.get("descripcion", "")).strip()
        if not desc:
            continue
        cant = _dec(row.get("cantidad", 1) or 1, f"línea {i+1} cantidad")
        precio = _dec(row.get("precio_unitario", 0) or 0, f"línea {i+1} precio")
        base = (cant * precio)
        tasa = str(row.get("impuesto", "INC 8%"))
        if tasa == "IVA 19%":
            imp = [ImpuestoLinea.iva_19_porciento(base)]
        elif tasa == "IVA 5%":
            imp = [ImpuestoLinea.iva_5_porciento(base)]
        elif tasa == "INC 8%":
            imp = [ImpuestoLinea.inc_8_porciento(base)]
        else:  # Exento / 0%
            imp = []
        lineas.append(LineaFactura(
            numero_linea=len(lineas) + 1,
            codigo_producto=str(row.get("codigo", f"P{i+1}")),
            descripcion=desc, cantidad=cant, precio_unitario=precio,
            subtotal_bruto=base, base_gravable=base, impuestos=imp,
        ))
    if not lineas:
        raise ValueError("La factura debe tener al menos una línea con descripción.")

    fact = Factura(
        tipo_factura=TIPO_FACTURA_VENTA, folio=int(cab["folio"]),
        fecha_emision=datetime.now(),
        resolucion=reso, emisor=emisor, adquiriente=adq, lineas=lineas,
        medio_pago=MedioPago(forma=FORMA_PAGO_CONTADO, medio=MEDIO_PAGO_EFECTIVO),
        software_id=cab.get("software_id", ""),
        software_security_code=cab.get("pin", ""),
        clave_tecnica=cab.get("clave_tecnica", ""),
        ambiente="2",
    )
    fact.calcular_totales()
    return fact


tab_emitir, tab_xml = st.tabs(["🧾 Emitir factura", "🔍 Vista previa XML"])

# Estado del formulario de líneas
if "fe_lineas" not in st.session_state:
    st.session_state["fe_lineas"] = pd.DataFrame([
        {"codigo": "P1", "descripcion": "", "cantidad": 1.0,
         "precio_unitario": 0.0, "impuesto": "INC 8%"},
    ])


def _form_cabecera(prefijo_key: str) -> dict:
    st.markdown("#### Resolución de numeración (DIAN)")
    c1, c2, c3 = st.columns(3)
    reso_numero = c1.text_input("Número resolución", "18760000001", key=f"{prefijo_key}_rn")
    reso_prefijo = c2.text_input("Prefijo", "SETP", key=f"{prefijo_key}_rp")
    folio = c3.number_input("Folio (consecutivo)", min_value=1, value=990000001,
                            step=1, key=f"{prefijo_key}_folio")
    c4, c5 = st.columns(2)
    reso_desde = c4.number_input("Rango desde", min_value=1, value=990000000,
                                 step=1, key=f"{prefijo_key}_rd")
    reso_hasta = c5.number_input("Rango hasta", min_value=1, value=995000000,
                                 step=1, key=f"{prefijo_key}_rh")
    c6, c7 = st.columns(2)
    reso_fdesde = c6.date_input("Vigencia desde", value=date(2019, 1, 19),
                                key=f"{prefijo_key}_fd")
    reso_fhasta = c7.date_input("Vigencia hasta", value=date(2030, 1, 19),
                                key=f"{prefijo_key}_fh")

    st.markdown("#### Credenciales DIAN del software")
    c8, c9, c10 = st.columns(3)
    software_id = c8.text_input("Software ID", key=f"{prefijo_key}_swid",
                                help="Si lo dejas vacío, se toma del vault.")
    pin = c9.text_input("PIN del software", type="password", key=f"{prefijo_key}_pin",
                        help="Si lo dejas vacío, se toma del vault.")
    clave_tecnica = c10.text_input("Clave técnica", type="password",
                                   key=f"{prefijo_key}_ct",
                                   help="Si lo dejas vacío, se toma del vault.")

    st.markdown("#### Adquiriente (cliente)")
    c11, c12, c13 = st.columns([1, 2, 1])
    adq_tipo = c11.selectbox("Tipo doc.", [TIPO_DOC_CC, TIPO_DOC_NIT],
                             format_func=lambda v: "Cédula" if v == TIPO_DOC_CC else "NIT",
                             key=f"{prefijo_key}_at")
    adq_doc = c12.text_input("Documento", key=f"{prefijo_key}_ad")
    adq_dv = c13.text_input("DV (si NIT)", key=f"{prefijo_key}_adv")
    adq_nombre = st.text_input("Nombre / Razón social del cliente", key=f"{prefijo_key}_an")

    return {
        "reso_numero": reso_numero, "reso_prefijo": reso_prefijo, "folio": folio,
        "reso_desde": reso_desde, "reso_hasta": reso_hasta,
        "reso_fdesde": reso_fdesde, "reso_fhasta": reso_fhasta,
        "software_id": software_id.strip(), "pin": pin.strip(),
        "clave_tecnica": clave_tecnica.strip(),
        "adq_tipo": adq_tipo, "adq_doc": adq_doc.strip(), "adq_dv": adq_dv.strip(),
        "adq_nombre": adq_nombre.strip(),
    }


def _form_lineas(prefijo_key: str) -> pd.DataFrame:
    st.markdown("#### Líneas de la factura")
    edited = st.data_editor(
        st.session_state["fe_lineas"],
        num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "codigo": st.column_config.TextColumn("Código"),
            "descripcion": st.column_config.TextColumn("Descripción", width="large"),
            "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0.0, format="%.2f"),
            "precio_unitario": st.column_config.NumberColumn("Precio unit.", min_value=0.0, format="%.2f"),
            "impuesto": st.column_config.SelectboxColumn(
                "Impuesto", options=["INC 8%", "IVA 19%", "IVA 5%", "Exento"]
            ),
        },
        key=f"{prefijo_key}_editor",
    )
    return edited


with tab_emitir:
    cab = _form_cabecera("emit")
    lineas_df = _form_lineas("emit")

    faltan = []
    if not cab["adq_doc"]:
        faltan.append("documento del cliente")
    if not cab["adq_nombre"]:
        faltan.append("nombre del cliente")
    puede = (not faltan) and (nit_emisor in registrados)

    if faltan:
        st.caption("Faltan datos: " + ", ".join(faltan))

    if st.button("📤 Generar, firmar y enviar a DIAN", type="primary",
                 disabled=not puede, key="emit_enviar"):
        try:
            fact = _construir_factura(cab, lineas_df)
        except ValueError as e:
            st.error(str(e))
        else:
            st.info(
                f"Factura **{fact.numero_factura}** · Total a pagar: "
                f"${fact.totales.payable:,.2f}"
            )
            with st.spinner("Generando, firmando y enviando a DIAN…"):
                res = servicio.emitir_factura(nit_emisor=nit_emisor, factura=fact)
            if res.exitoso:
                st.success(
                    f"✅ Enviada. TrackId: `{res.track_id}` · "
                    f"CUFE: `{(res.cufe or '')[:24]}…`"
                )
                if res.detalle_dian:
                    with st.expander("Detalle DIAN"):
                        st.json(res.detalle_dian)
            else:
                st.error(f"❌ No se pudo enviar: {res.error}")
                if res.cufe:
                    st.caption(f"CUFE calculado: {res.cufe[:24]}…")


with tab_xml:
    st.caption(
        "Genera el XML UBL 2.1 sin enviarlo, para revisarlo o validarlo contra "
        "un XSD externo. No requiere certificado."
    )
    cab2 = _form_cabecera("prev")
    lineas_df2 = _form_lineas("prev")

    if st.button("🔍 Generar XML (sin enviar)", key="prev_btn"):
        try:
            fact = _construir_factura(cab2, lineas_df2)
            # CUFE de vista previa (sin credenciales del vault)
            try:
                fact.cufe = calcular_cufe_desde_factura(fact, ambiente="habilitacion")
            except Exception:
                pass
            xml = generar_xml_factura(fact)
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Error generando XML: {e}")
        else:
            st.success(
                f"Factura {fact.numero_factura} · {len(xml):,} bytes · "
                f"Total ${fact.totales.payable:,.2f}"
            )
            st.download_button(
                "⬇️ Descargar XML", data=xml,
                file_name=f"{fact.numero_factura}.xml", mime="application/xml",
                key="prev_dl",
            )
            st.code(xml.decode("utf-8", "ignore")[:4000], language="xml")
            if len(xml) > 4000:
                st.caption("(Vista previa truncada a 4.000 caracteres.)")


with st.expander("ℹ️ Notas y limitaciones"):
    st.markdown(
        "- Usa el backend **`core/dian_fe/`** + el cliente SOAP `SendBillSync`.\n"
        "- El certificado .p12 se comparte con RADIAN (mismo vault).\n"
        "- Soporta INC 8%, IVA 19% y 5% por línea; **una** tasa por línea.\n"
        "- **Aún no**: notas crédito/débito, retenciones, descuentos globales, "
        "validación XSD, ni múltiples tasas en una misma línea.\n"
        "- Envíos a **habilitación**. Validez en producción requiere habilitación DIAN."
    )
