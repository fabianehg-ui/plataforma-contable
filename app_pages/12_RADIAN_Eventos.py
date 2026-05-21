"""
app_pages/12_RADIAN_Eventos.py

UI de emisión de eventos RADIAN (030 / 031 / 032 / 033) ante DIAN.

Conecta la interfaz Streamlit con el backend ya existente en core/dian_pt/
(ServicioDIAN multi-tenant). Cuatro pestañas:

  1. Configuración  — registrar/ver/eliminar credenciales DIAN por empresa (vault)
  2. Emisión        — seleccionar facturas recibidas y enviar eventos
  3. Seguimiento    — consultar estado de un envío por TrackId
  4. Auditoría      — ver histórico de envíos del mes

ADVERTENCIA: el backend NO está habilitado por DIAN (requiere pasar el set de
pruebas y tener certificado .p12 real). Mientras tanto, esta UI envía contra el
ambiente de HABILITACIÓN. Ver core/dian_pt/README.md.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa

from core.dian_pt import (
    ServicioDIAN,
    EVENTOS,
    CODIGOS_RECLAMO,
    ErrorVault,
    PasswordIncorrecto,
    CertificadoInvalido,
    CertificadoVencido,
)
from core.dian_pt.auditoria import AuditorDIAN


EMPRESAS_DIR = ROOT / "core" / "data" / "empresas"
TZ_BOGOTA = timezone(timedelta(hours=-5))

# ═══════════════════════════════════════════════════════════════════════
# Setup
# ═══════════════════════════════════════════════════════════════════════

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

st.title("📨 RADIAN Eventos — Emisión de Acuses")
st.caption(
    "Envío de eventos RADIAN (030 Acuse de recibo · 031 Reclamo · "
    "032 Recibo del bien · 033 Aceptación expresa) ante DIAN."
)

st.warning(
    "⚠️ **Ambiente de HABILITACIÓN.** Este módulo conecta con el backend real "
    "(`core/dian_pt/`) pero DIAN aún no ha habilitado el envío en producción. "
    "Los envíos van al ambiente de pruebas `vpfe-hab.dian.gov.co` y no constituyen "
    "eventos válidos hasta pasar el set de habilitación."
)


# ═══════════════════════════════════════════════════════════════════════
# Clave maestra del vault (secret/env si existe; si no, se pide en sesión)
# ═══════════════════════════════════════════════════════════════════════

def _master_password_desde_entorno():
    try:
        val = st.secrets.get("DIAN_MASTER_PWD")  # type: ignore[attr-defined]
        if val:
            return str(val)
    except Exception:
        pass
    return os.getenv("DIAN_MASTER_PWD")


def _obtener_master_password():
    env_pwd = _master_password_desde_entorno()
    if env_pwd:
        return env_pwd

    # Campo en el CUERPO de la página (visible siempre, no solo en la barra lateral)
    st.markdown("### 🔐 Clave maestra del vault")
    st.caption(
        "Cifra/descifra los certificados .p12. No se guarda en disco; solo vive "
        "en esta sesión. **Mínimo 8 caracteres** — defínela una vez y usa siempre "
        "la misma (con otra clave no podrás abrir los certificados ya guardados)."
    )
    pwd = st.text_input(
        "Clave maestra", type="password", key="_dian_master_input",
        placeholder="Al menos 8 caracteres…",
    )
    if not pwd:
        return None
    if len(pwd) < 8:
        st.error(
            f"La clave debe tener al menos 8 caracteres (tiene {len(pwd)}). "
            "Escribe una más larga para continuar."
        )
        return None
    return pwd


MASTER = _obtener_master_password()

if not MASTER:
    st.info(
        "🔐 Escribe la **clave maestra del vault** arriba para operar este módulo. "
        "(O configura el secret `DIAN_MASTER_PWD` en Streamlit Cloud para no "
        "tener que escribirla.)"
    )
    st.stop()


@st.cache_resource(show_spinner=False)
def _servicio(master: str) -> ServicioDIAN:
    return ServicioDIAN(master_password=master)


try:
    servicio = _servicio(MASTER)
except ValueError as e:
    st.error(f"No se pudo iniciar el servicio: {e}")
    st.stop()


nit_empresa = str(empresa.get("nit", "")).split("-")[0].strip()
razon_empresa = empresa.get("razon_social", "")


# ═══════════════════════════════════════════════════════════════════════
# Pestañas
# ═══════════════════════════════════════════════════════════════════════

tab_cfg, tab_emision, tab_seguimiento, tab_audit = st.tabs(
    ["⚙️ Configuración", "📨 Emisión de eventos", "🔎 Seguimiento", "📜 Auditoría"]
)


# ───────────────────────────────────────────────────────────────────────
# TAB 1 — Configuración (vault de credenciales)
# ───────────────────────────────────────────────────────────────────────
with tab_cfg:
    st.subheader("Credenciales DIAN registradas")

    try:
        clientes = servicio.listar_clientes()
    except Exception as e:
        clientes = []
        st.error(f"Error leyendo el vault: {e}")

    if clientes:
        st.dataframe(pd.DataFrame(clientes), use_container_width=True, hide_index=True)
    else:
        st.info("No hay credenciales registradas todavía. Regístralas abajo.")

    st.markdown("---")
    st.subheader(f"Registrar / actualizar credenciales — {razon_empresa}")
    st.caption(
        "El certificado .p12 se valida y se cifra (AES-256) antes de guardarse en "
        f"`core/data/empresas/{nit_empresa}_.../credenciales_dian.enc`."
    )

    col1, col2 = st.columns(2)
    with col1:
        in_razon = st.text_input("Razón social", value=razon_empresa, key="cfg_razon")
        in_nit = st.text_input(
            "NIT (sin dígito de verificación)", value=nit_empresa, key="cfg_nit"
        )
        in_ambiente = st.selectbox(
            "Ambiente", ["habilitacion", "produccion"], index=0, key="cfg_amb"
        )
    with col2:
        in_software_id = st.text_input(
            "Software ID (UUID de DIAN)", key="cfg_swid",
            help="Lo asigna DIAN al habilitar el software.",
        )
        in_pin = st.text_input(
            "PIN del software (SoftwareSecurityCode)", key="cfg_pin", type="password"
        )
        in_clave_tecnica = st.text_input(
            "Clave técnica (CUDE/CUFE)", key="cfg_ct", type="password"
        )

    p12_file = st.file_uploader(
        "Certificado digital .p12 / .pfx", type=["p12", "pfx"], key="cfg_p12"
    )
    p12_pwd = st.text_input(
        "Contraseña del certificado .p12", type="password", key="cfg_p12pwd"
    )

    st.warning(
        "🔒 El certificado .p12 y su contraseña se procesan en el servidor para "
        "cifrarlos en el vault. Opera solo sobre un despliegue de confianza."
    )

    if st.button("💾 Guardar credenciales", type="primary", key="cfg_guardar"):
        faltan = []
        if not in_nit:
            faltan.append("NIT")
        if not in_software_id:
            faltan.append("Software ID")
        if not in_pin:
            faltan.append("PIN del software")
        if not in_clave_tecnica:
            faltan.append("Clave técnica")
        if not p12_file:
            faltan.append("Certificado .p12")
        if not p12_pwd:
            faltan.append("Contraseña del .p12")

        if faltan:
            st.error("Faltan campos obligatorios: " + ", ".join(faltan))
        else:
            try:
                with st.spinner("Validando certificado y cifrando…"):
                    info = servicio.registrar_cliente(
                        nit=in_nit.strip(),
                        razon_social=in_razon.strip(),
                        p12_bytes=p12_file.getvalue(),
                        p12_password=p12_pwd,
                        software_id=in_software_id.strip(),
                        software_security_code=in_pin.strip(),
                        clave_tecnica=in_clave_tecnica.strip(),
                        ambiente=in_ambiente,
                    )
                st.success(
                    f"Credenciales guardadas para NIT {info['nit']}. "
                    f"El certificado vence en {info['dias_para_vencer']} días "
                    f"({info['fecha_vencimiento_cert'][:10]})."
                )
                if info["dias_para_vencer"] < 30:
                    st.warning("⚠️ El certificado vence pronto. Renuévalo.")
                st.rerun()
            except PasswordIncorrecto as e:
                st.error(f"La contraseña del certificado .p12 es incorrecta. {e}")
            except CertificadoVencido as e:
                st.error(f"El certificado está vencido. {e}")
            except CertificadoInvalido as e:
                st.error(f"El certificado no es válido. {e}")
            except ValueError as e:
                st.error(f"Datos incompletos: {e}")
            except ErrorVault as e:
                st.error(f"No se pudo guardar en el vault: {e}")
            except Exception as e:
                st.error(f"Error inesperado: {e}")

    st.markdown("---")
    with st.expander("🗑️ Eliminar credenciales de una empresa"):
        st.caption("Elimina el archivo cifrado. No afecta envíos ya realizados.")
        nit_del = st.text_input("NIT a eliminar", key="cfg_del_nit")
        confirmar = st.checkbox(
            f"Confirmo eliminar credenciales de {nit_del or '...'}", key="cfg_del_chk"
        )
        if st.button(
            "Eliminar", key="cfg_del_btn", disabled=not (nit_del and confirmar)
        ):
            try:
                ok = servicio.eliminar_cliente(nit_del.strip())
                if ok:
                    st.success(f"Credenciales de {nit_del} eliminadas.")
                    st.rerun()
                else:
                    st.info("No había credenciales para ese NIT.")
            except Exception as e:
                st.error(f"Error eliminando: {e}")


# ───────────────────────────────────────────────────────────────────────
# TAB 2 — Emisión de eventos
# ───────────────────────────────────────────────────────────────────────
with tab_emision:
    st.subheader("Facturas recibidas a acusar")

    nits_registrados = {c["nit"] for c in (clientes or [])}
    if nit_empresa not in nits_registrados:
        st.warning(
            f"La empresa activa (NIT {nit_empresa}) no tiene credenciales DIAN "
            "registradas. Ve a la pestaña **⚙️ Configuración** primero."
        )

    facturas: list = []
    origen = None

    resultados_xml = st.session_state.get("xml_resultados")
    if resultados_xml:
        for r in resultados_xml:
            if getattr(r, "empresa_nit", None) != nit_empresa:
                continue
            for d in getattr(r, "documentos", []):
                if getattr(d, "tipo_nombre", "") != "factura_recibida":
                    continue
                facturas.append({
                    "Seleccionar": False,
                    "numero": getattr(d, "numero", ""),
                    "cufe": getattr(d, "cufe", ""),
                    "fecha": str(getattr(d, "fecha_emision", "")),
                    "nit_proveedor": getattr(d, "nit_emisor", ""),
                    "proveedor": getattr(d, "nombre_emisor", ""),
                    "monto": float(getattr(d, "valor_total", 0) or 0),
                })
        if facturas:
            origen = "sesión (Contabilidad con XML DIAN)"

    st.caption(
        "Fuente: facturas recibidas en sesión de **Contabilidad con XML DIAN**. "
        "Si no hay nada en sesión, sube el Excel del Token DIAN abajo."
    )

    excel_token = st.file_uploader(
        "Excel del Token DIAN (opcional)", type=["xlsx", "xls"], key="emis_excel"
    )
    if excel_token is not None and not facturas:
        try:
            df_tok = pd.read_excel(excel_token)
            cols = {c.lower().strip(): c for c in df_tok.columns}

            def _col(*opts):
                for o in opts:
                    if o in cols:
                        return cols[o]
                return None

            c_cufe = _col("cufe/cude", "cufe", "cude")
            c_num = _col("folio", "número", "numero", "prefijo y número")
            c_fecha = _col("fecha emisión", "fecha emision", "fecha")
            c_nit = _col("nit emisor", "nit", "nit del emisor")
            c_prov = _col("nombre emisor", "emisor", "razón social emisor")
            c_monto = _col("total", "valor total", "monto")

            for _, row in df_tok.iterrows():
                facturas.append({
                    "Seleccionar": False,
                    "numero": str(row.get(c_num, "")) if c_num else "",
                    "cufe": str(row.get(c_cufe, "")) if c_cufe else "",
                    "fecha": str(row.get(c_fecha, "")) if c_fecha else "",
                    "nit_proveedor": (
                        str(row.get(c_nit, "")).split("-")[0].strip() if c_nit else ""
                    ),
                    "proveedor": str(row.get(c_prov, "")) if c_prov else "",
                    "monto": float(row.get(c_monto, 0) or 0) if c_monto else 0.0,
                })
            origen = "Excel del Token subido"
        except Exception as e:
            st.error(f"No se pudo leer el Excel del Token: {e}")

    if not facturas:
        st.info(
            "No hay facturas para mostrar. Procesa XML en **Contabilidad con XML "
            "DIAN** o sube el Excel del Token aquí."
        )
    else:
        st.success(f"{len(facturas)} factura(s) recibida(s) — origen: {origen}.")

        colA, colB = st.columns([2, 1])
        with colA:
            tipo_evento = st.selectbox(
                "Tipo de evento a emitir",
                options=list(EVENTOS.keys()),
                format_func=lambda k: f"{k} — {EVENTOS[k]['descripcion']}",
                key="emis_tipo",
            )
        with colB:
            codigo_reclamo = None
            if tipo_evento == "031":
                codigo_reclamo = st.selectbox(
                    "Código de reclamo",
                    options=list(CODIGOS_RECLAMO.keys()),
                    format_func=lambda k: f"{k} — {CODIGOS_RECLAMO[k]}",
                    key="emis_reclamo",
                )

        df_fact = pd.DataFrame(facturas)
        edited = st.data_editor(
            df_fact,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Seleccionar": st.column_config.CheckboxColumn("✓", width="small"),
                "monto": st.column_config.NumberColumn("monto", format="%.2f"),
                "cufe": st.column_config.TextColumn("CUFE", width="medium"),
            },
            disabled=["numero", "cufe", "fecha", "nit_proveedor", "proveedor", "monto"],
            key="emis_editor",
        )

        seleccionadas = edited[edited["Seleccionar"]].to_dict("records")
        st.caption(
            f"{len(seleccionadas)} factura(s) seleccionada(s). "
            "DIAN exige al menos 030 + 032 + (033 o 036) para soporte de IVA/costos."
        )
        st.info(
            "ℹ️ El **dígito de verificación** del proveedor no viene en el XML; "
            "el servicio lo calcula automáticamente."
        )

        puede_enviar = bool(seleccionadas) and nit_empresa in nits_registrados
        if st.button(
            f"📨 Enviar evento {tipo_evento} a {len(seleccionadas)} factura(s)",
            type="primary", disabled=not puede_enviar, key="emis_enviar",
        ):
            barra = st.progress(0.0, text="Enviando…")
            filas_resultado = []
            total = len(seleccionadas)
            for i, f in enumerate(seleccionadas, start=1):
                try:
                    fecha_str = str(f.get("fecha", ""))[:10]
                    try:
                        fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d").replace(
                            tzinfo=TZ_BOGOTA
                        )
                    except ValueError:
                        fecha_dt = datetime.now(TZ_BOGOTA)

                    res = servicio.enviar_evento(
                        nit_cliente=nit_empresa,
                        tipo_evento=tipo_evento,
                        cufe_factura=str(f.get("cufe", "")),
                        numero_factura=str(f.get("numero", "")),
                        fecha_factura=fecha_dt,
                        monto_factura=float(f.get("monto", 0) or 0),
                        nit_proveedor=str(f.get("nit_proveedor", "")),
                        dv_proveedor="",
                        razon_social_proveedor=str(f.get("proveedor", "")),
                        codigo_reclamo=codigo_reclamo,
                    )
                    filas_resultado.append({
                        "factura": f.get("numero", ""),
                        "proveedor": f.get("proveedor", ""),
                        "estado": "✅ OK" if res.exitoso else "❌ Error",
                        "track_id": res.track_id or "",
                        "detalle": res.error or "",
                    })
                except Exception as e:
                    filas_resultado.append({
                        "factura": f.get("numero", ""),
                        "proveedor": f.get("proveedor", ""),
                        "estado": "❌ Excepción",
                        "track_id": "",
                        "detalle": str(e),
                    })
                barra.progress(i / total, text=f"Enviando… {i}/{total}")

            barra.empty()
            st.session_state["radian_ultimos_resultados"] = filas_resultado

        if "radian_ultimos_resultados" in st.session_state:
            st.markdown("#### Resultado del último envío")
            res_df = pd.DataFrame(st.session_state["radian_ultimos_resultados"])
            st.dataframe(res_df, use_container_width=True, hide_index=True)
            ok = int((res_df["estado"] == "✅ OK").sum())
            st.caption(f"{ok}/{len(res_df)} enviadas correctamente.")


# ───────────────────────────────────────────────────────────────────────
# TAB 3 — Seguimiento por TrackId
# ───────────────────────────────────────────────────────────────────────
with tab_seguimiento:
    st.subheader("Consultar estado de un envío")
    st.caption("Pega el TrackId que devolvió DIAN para ver su estado actual.")

    track_id = st.text_input("TrackId", key="seg_track")
    if st.button("🔎 Consultar", key="seg_btn", disabled=not track_id):
        try:
            with st.spinner("Consultando a DIAN…"):
                estado = servicio.consultar_estado(
                    nit_cliente=nit_empresa, track_id=track_id.strip()
                )
            if estado.get("error"):
                st.error(estado["error"])
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Estado", str(estado.get("estado", "—")))
                c2.metric("¿Válido?", "Sí" if estado.get("es_valido") else "No")
                c3.metric("Recepción", str(estado.get("fecha_recepcion", "—"))[:10])
                if estado.get("errores"):
                    st.markdown("**Errores reportados por DIAN:**")
                    for err in estado["errores"]:
                        st.write(f"- {err}")
                with st.expander("Ver respuesta completa"):
                    st.json(estado)
        except Exception as e:
            st.error(f"Error consultando: {e}")


# ───────────────────────────────────────────────────────────────────────
# TAB 4 — Auditoría
# ───────────────────────────────────────────────────────────────────────
with tab_audit:
    st.subheader(f"Auditoría de envíos — NIT {nit_empresa}")

    mes = st.text_input(
        "Mes (YYYY-MM)", value=datetime.now(timezone.utc).strftime("%Y-%m"),
        key="aud_mes",
    )

    auditor = AuditorDIAN()
    try:
        resumen = auditor.resumen_cliente(nit_empresa, mes=mes)
        c1, c2, c3 = st.columns(3)
        c1.metric("Total envíos", resumen.get("total", 0))
        c2.metric("Exitosos", resumen.get("exitosos", 0))
        c3.metric("Fallidos", resumen.get("fallidos", 0))
        por_tipo = resumen.get("por_tipo", {})
        if por_tipo:
            st.caption("Por tipo: " + ", ".join(f"{k}={v}" for k, v in por_tipo.items()))
    except Exception as e:
        st.info(f"Sin resumen disponible para {mes}. ({e})")

    st.markdown("---")
    if st.button("📋 Cargar detalle del mes", key="aud_cargar"):
        try:
            desde = datetime.strptime(mes + "-01", "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            if desde.month == 12:
                hasta = desde.replace(year=desde.year + 1, month=1)
            else:
                hasta = desde.replace(month=desde.month + 1)
            registros = auditor.consultar_por_cliente(
                nit_cliente=nit_empresa, desde=desde, hasta=hasta, limit=1000
            )
            if registros:
                st.dataframe(
                    pd.DataFrame(registros), use_container_width=True, hide_index=True
                )
                st.caption(f"{len(registros)} registro(s).")
            else:
                st.info("No hay registros de auditoría para ese mes.")
        except Exception as e:
            st.error(f"Error leyendo auditoría: {e}")


with st.expander("ℹ️ Notas y limitaciones"):
    st.markdown(
        "- Usa el backend **`core/dian_pt/`** (certificado .p12, CUDE, XML UBL 2.1, "
        "firma XAdES-EPES, SOAP a DIAN).\n"
        "- Envíos van a **habilitación** salvo que la credencial sea `produccion`.\n"
        "- Para validez en producción, DIAN debe haber habilitado el software.\n"
        "- El DV del proveedor se calcula automáticamente.\n"
        "- La clave maestra del vault nunca se guarda en disco."
    )
