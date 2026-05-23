"""
10_Retencion_Fuente.py — Módulo de Retención en la Fuente (Formulario 350).

Flujo completo del módulo:
  1. Configuración por empresa — CIIU, autorretenedor, exonerado 114-1.
  2. Listado de declaraciones — todas las del histórico de la empresa.
  3. Nueva declaración — sube PDFs, clasifica, calcula y guarda.
  4. Revisión y edición — reclasificación manual, marcar como presentada.
  5. Generación del PDF F350 — descarga del borrador con marca de agua.

La lógica de negocio está en core/f350/ y aquí solo se orquesta la UI.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date, datetime

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info, current_user
from auth.empresas import seleccionar_empresa_sidebar, require_empresa
from db.supabase_client import get_supabase

# Lógica pura del F350
from core.f350 import (
    inferir_tipo_persona,
    calcular_dv,
    formato_nit,
    formato_moneda,
    aproximar_a_miles,
    AUTORRET_CASILLAS_F350,
    generar_pdf_formulario_350,
)
from core.f350.procesador import procesar_declaracion
from core.f350 import servicios as svc


# =============================================================================
# CONFIGURACIÓN DE PÁGINA
# =============================================================================

st.set_page_config(
    page_title="Retención en la Fuente — F350",
    page_icon="📋",
    layout="wide",
)


# =============================================================================
# GUARDAS DE AUTENTICACIÓN
# =============================================================================

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

sb = get_supabase()
user = current_user()


# =============================================================================
# CABECERA
# =============================================================================

st.title("📋 Retención en la Fuente — Formulario 350")
st.caption(f"Empresa activa: **{empresa['razon_social']}** · NIT {empresa['nit']}")

# Aviso normativo persistente
with st.expander("⚠️ Aviso normativo (08 mayo 2026) — Suspensión Decreto 0572/2025", expanded=False):
    st.markdown(
        """
        El **Consejo de Estado** suspendió provisionalmente los artículos
        2 al 8 del **Decreto 0572 de 2025** mediante auto del 7 de mayo
        de 2026.

        **Desde el 8 de mayo de 2026** aplican las tarifas y bases de los
        **Decretos 0261/2023 y 0242/2024** (DIAN Comunicado 070 del 08/05/2026).

        El módulo carga las tarifas del Dec. 0572/2025 con vigencia hasta el
        7 de mayo de 2026. Para declaraciones del período mayo 2026 en
        adelante, deberás configurar manualmente la tarifa vigente en la
        pestaña **Configuración**, hasta que se publique aquí el listado
        oficial del Dec. 0261/2023 + 0242/2024.
        """
    )

st.divider()


# =============================================================================
# CARGAR CONFIGURACIÓN DE LA EMPRESA
# =============================================================================

config = svc.leer_config_empresa(sb, empresa["id"]) or {}

# Aviso si la empresa todavía no tiene CIIU configurado
if not config.get("ciiu_principal"):
    st.warning(
        "🔧 Esta empresa todavía no tiene configurado su CIIU. "
        "Ve a la pestaña **Configuración** y diligéncialo antes de "
        "crear declaraciones."
    )


# =============================================================================
# TABS
# =============================================================================

tab_decl, tab_nueva, tab_config, tab_catalogo = st.tabs([
    "📊 Declaraciones",
    "➕ Nueva declaración",
    "⚙️ Configuración",
    "📖 Catálogo CIIU",
])


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Listado de declaraciones
# ─────────────────────────────────────────────────────────────────────────────

with tab_decl:
    st.subheader("Declaraciones del histórico")

    declaraciones = svc.listar_declaraciones(sb, empresa["id"])

    if not declaraciones:
        st.info(
            "Aún no hay declaraciones registradas para esta empresa. "
            "Crea la primera desde la pestaña **Nueva declaración**."
        )
    else:
        # Tabla resumen
        meses_nombre = {
            1:"Ene",2:"Feb",3:"Mar",4:"Abr",5:"May",6:"Jun",
            7:"Jul",8:"Ago",9:"Sep",10:"Oct",11:"Nov",12:"Dic",
        }
        rows = []
        for d in declaraciones:
            rows.append({
                "ID":            d["id"],
                "Período":       f"{meses_nombre[d['mes']]}-{d['anio']}",
                "Estado":        d["estado"],
                "Total":         formato_moneda(d.get("total_declaracion") or 0),
                "CIIU aplicado": d.get("ciiu_aplicado") or "—",
                "Tarifa":        f"{(d.get('tarifa_aplicada') or 0)*100:.2f}%" if d.get('tarifa_aplicada') else "—",
                "Actualizado":   (d.get("actualizado_en") or "")[:10],
            })
        df_decl = pd.DataFrame(rows)

        # Sin la columna ID en la vista
        st.dataframe(
            df_decl.drop(columns=["ID"]),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("##### Abrir una declaración")
        opciones = {f"{r['Período']} — {r['Estado']}": r["ID"] for r in rows}
        elegida_label = st.selectbox("Selecciona", list(opciones.keys()))
        elegida_id = opciones[elegida_label]

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            ver = st.button("👁️ Ver detalle", use_container_width=True)
        with col_b:
            generar_pdf = st.button("📄 Generar PDF", use_container_width=True)
        with col_c:
            eliminar = st.button("🗑️ Eliminar", use_container_width=True, type="secondary")

        if eliminar:
            st.session_state["__confirmar_eliminar"] = elegida_id

        if st.session_state.get("__confirmar_eliminar") == elegida_id:
            st.warning(
                f"¿Estás seguro de eliminar la declaración **{elegida_label}**? "
                "Se borrarán también todos sus movimientos."
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Sí, eliminar definitivamente"):
                    svc.eliminar_declaracion(sb, elegida_id)
                    st.session_state.pop("__confirmar_eliminar", None)
                    st.success("Declaración eliminada.")
                    st.rerun()
            with c2:
                if st.button("❌ Cancelar"):
                    st.session_state.pop("__confirmar_eliminar", None)
                    st.rerun()

        if ver:
            st.session_state["__decl_seleccionada"] = elegida_id

        if generar_pdf:
            st.session_state["__decl_pdf"] = elegida_id

        # Vista de detalle
        if st.session_state.get("__decl_seleccionada") == elegida_id:
            decl = svc.obtener_declaracion(sb, elegida_id)
            st.divider()
            st.markdown(f"### Detalle: {elegida_label}")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Estado", decl["estado"])
            with col2:
                st.metric(
                    "Total retenciones renta",
                    formato_moneda(decl.get("total_retenciones_renta") or 0),
                )
            with col3:
                st.metric(
                    "Total retenciones IVA",
                    formato_moneda(decl.get("total_retenciones_iva") or 0),
                )
            with col4:
                st.metric(
                    "Total declaración",
                    formato_moneda(decl.get("total_declaracion") or 0),
                )

            movs = svc.listar_movimientos(sb, elegida_id)
            if movs:
                st.markdown("##### Movimientos")
                df_movs = pd.DataFrame([
                    {
                        "Cuenta":     m["cuenta_puc"],
                        "NIT":        m["nit_tercero"],
                        "Tercero":    (m.get("nombre_tercero") or "")[:40],
                        "Tipo":       "PN" if m.get("tipo_inferido") == "Persona Natural" else "PJ",
                        "Base":       formato_moneda(m["base"]),
                        "Retención":  formato_moneda(m["retencion"]),
                        "Concepto":   m.get("concepto_asignado") or "—",
                        "Casilla":    m.get("casilla_destino") or "—",
                        "Confianza":  m.get("confianza_clasif") or "—",
                        "Estado":     m.get("estado") or "—",
                    }
                    for m in movs
                ])
                st.dataframe(df_movs, use_container_width=True, hide_index=True)

                # Resaltar los de baja confianza
                rev = sum(1 for m in movs if m.get("confianza_clasif") == "baja")
                if rev:
                    st.warning(
                        f"⚠️ {rev} movimientos quedaron clasificados con "
                        "confianza BAJA. Revísalos antes de presentar."
                    )
            else:
                st.info("Esta declaración aún no tiene movimientos.")

            # Cambiar estado
            st.markdown("##### Cambiar estado")
            estado_nuevo = st.selectbox(
                "Nuevo estado",
                ["Borrador", "Revisada", "Presentada"],
                index=["Borrador","Revisada","Presentada"].index(decl["estado"]),
                key=f"estado_{elegida_id}",
            )
            if st.button("Actualizar estado"):
                svc.cambiar_estado_declaracion(sb, elegida_id, estado_nuevo)
                st.success(f"Estado actualizado a **{estado_nuevo}**.")
                st.rerun()

        # Botón PDF
        if st.session_state.get("__decl_pdf") == elegida_id:
            decl = svc.obtener_declaracion(sb, elegida_id)
            movs = svc.listar_movimientos(sb, elegida_id)

            # Armar el payload para el generador
            retenciones = []
            iva_total = 0
            for m in movs:
                if m.get("concepto_asignado") == "IVA":
                    iva_total += m["retencion"]
                    continue
                tipo_key = "PN" if m.get("tipo_inferido") == "Persona Natural" else "PJ"
                retenciones.append({
                    "concepto":  m.get("concepto_asignado") or "Otros pagos",
                    "tipo":      tipo_key,
                    "base":      m["base"],
                    "retencion": m["retencion"],
                })

            concepto_autorret = (
                "Contribuyentes exonerados 114-1"
                if config.get("exonerado_art_114_1")
                else "Ventas"
            )
            autorretenciones = [{
                "concepto":  concepto_autorret,
                "base":      decl.get("base_autorretencion") or 0,
                "retencion": decl.get("valor_autorretencion") or 0,
            }]

            datos_pdf = {
                "año":             decl["anio"],
                "periodo":         decl["mes"],
                "nit":             empresa["nit"],
                "dv":              calcular_dv(empresa["nit"]),
                "razon_social":    empresa["razon_social"],
                "ciiu":            decl.get("ciiu_aplicado") or (config.get("ciiu_principal") or ""),
                "tarifa_autorret": (decl.get("tarifa_aplicada") or 0) * 100,
                "retenciones":     retenciones,
                "autorretenciones":autorretenciones,
                "total_iva":       iva_total,
                "total_timbre":    0,
            }

            try:
                pdf_bytes = generar_pdf_formulario_350(datos_pdf)
                periodo_nombre = f"{decl['anio']}-{decl['mes']:02d}"
                st.download_button(
                    "⬇️ Descargar PDF del F350",
                    data=pdf_bytes,
                    file_name=f"F350_{empresa['nit']}_{periodo_nombre}.pdf",
                    mime="application/pdf",
                )
                st.success("PDF generado. Haz clic en el botón de arriba para descargarlo.")
            except Exception as e:
                st.error(f"No se pudo generar el PDF: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Nueva declaración
# ─────────────────────────────────────────────────────────────────────────────

with tab_nueva:
    st.subheader("Crear nueva declaración mensual")

    if not config.get("ciiu_principal"):
        st.error(
            "❌ Falta el CIIU principal de la empresa. "
            "Ve a la pestaña **Configuración** primero."
        )
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            anio = st.number_input(
                "Año",
                min_value=2023,
                max_value=2030,
                value=date.today().year,
                step=1,
            )
        with col_b:
            mes = st.selectbox(
                "Mes",
                list(range(1, 13)),
                format_func=lambda m: f"{m:02d} — {['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'][m-1]}",
                index=date.today().month - 1,
            )

        # Tarifa aplicable
        fecha_periodo = date(int(anio), int(mes), 1)
        tarifa_catalogo = svc.obtener_tarifa_vigente(
            sb, config["ciiu_principal"], fecha_periodo,
        )
        tarifa_manual = config.get("tarifa_autorretencion_manual")

        if tarifa_manual:
            tarifa_efectiva = float(tarifa_manual)
            fuente = "configurada manualmente para esta empresa"
        elif tarifa_catalogo is not None:
            tarifa_efectiva = float(tarifa_catalogo)
            fuente = f"del catálogo CIIU {config['ciiu_principal']}"
        else:
            tarifa_efectiva = None
            fuente = None

        if tarifa_efectiva is not None:
            st.info(
                f"🧮 Tarifa de autorretención aplicable: "
                f"**{tarifa_efectiva*100:.2f}%** ({fuente})."
            )
        else:
            st.error(
                f"⚠️ No hay tarifa vigente cargada para el CIIU "
                f"**{config['ciiu_principal']}** en {fecha_periodo}. "
                "Ve a **Configuración** y diligencia la tarifa manual, "
                "o solicita al administrador que cargue las tarifas vigentes."
            )

        st.markdown("##### Sube los PDFs de Contai")
        col1, col2 = st.columns(2)
        with col1:
            pdf_aux = st.file_uploader(
                "Auxiliar de retefuente (Análisis de % de Retención e IVA)",
                type=["pdf"],
                key="pdf_aux",
            )
        with col2:
            pdf_bal = st.file_uploader(
                "Balance de prueba por cuenta",
                type=["pdf"],
                key="pdf_bal",
            )

        st.markdown("##### Opciones avanzadas")
        excluir_input = st.text_input(
            "Subcuentas a excluir de la autorretención (separadas por coma)",
            placeholder="ej. 4295,425005",
            help="Códigos de subcuentas de la cuenta 4 cuyos ingresos NO deben sumarse a la base.",
        )

        if st.button("▶️ Procesar declaración", type="primary", disabled=(tarifa_efectiva is None)):
            if not pdf_aux or not pdf_bal:
                st.error("Debes subir los DOS PDFs antes de procesar.")
                st.stop()

            with st.spinner("Procesando los PDFs..."):
                try:
                    excluir = [s.strip() for s in (excluir_input or "").split(",") if s.strip()]
                    resultado = procesar_declaracion(
                        auxiliar_fuente=pdf_aux.getvalue(),
                        balance_fuente=pdf_bal.getvalue(),
                        tarifa_pct=tarifa_efectiva * 100,  # función espera porcentaje
                        es_exonerado=bool(config.get("exonerado_art_114_1")),
                        subcuentas_excluidas=excluir,
                    )
                    # Guardar en session_state para que sobreviva el rerun
                    st.session_state["__resultado_proc"] = resultado
                    st.session_state["__resultado_anio"] = int(anio)
                    st.session_state["__resultado_mes"]  = int(mes)
                    st.session_state["__resultado_tarifa"] = tarifa_efectiva
                    st.session_state["__resultado_normativa"] = (
                        "Manual" if tarifa_manual else "Dec. 0572/2025 (vigente hasta 7-may-2026)"
                    )
                except Exception as e:
                    st.error(f"❌ Error procesando los PDFs: {e}")
                    st.stop()

        # Mostrar resultado si existe en sesión
        resultado = st.session_state.get("__resultado_proc")
        if resultado:
            st.divider()

            # Advertencias del procesador
            for adv in resultado["advertencias"]:
                st.warning(f"⚠️ {adv}")

            t = resultado["totales"]
            st.success(
                f"✅ Procesado: **{len(resultado['movimientos'])} movimientos** clasificados."
            )

            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            with col_m1:
                st.metric("Base autorretención", formato_moneda(t["base_autorretencion"]))
            with col_m2:
                st.metric("Valor autorretención", formato_moneda(t["valor_autorretencion"]))
            with col_m3:
                st.metric("Retenciones renta", formato_moneda(t["total_retenciones_renta"]))
            with col_m4:
                st.metric("Total declaración", formato_moneda(t["total_declaracion"]))

            # Tabla de movimientos
            df_movs = pd.DataFrame([
                {
                    "Cuenta":    m["cuenta_puc"],
                    "NIT":       m["nit_tercero"],
                    "Tercero":   (m["nombre_tercero"] or "")[:40],
                    "Tipo":      "PN" if m["tipo_inferido"] == "Persona Natural" else "PJ",
                    "Base":      formato_moneda(m["base"]),
                    "Retención": formato_moneda(m["retencion"]),
                    "Concepto":  m["concepto_asignado"],
                    "Casilla":   m["casilla_destino"],
                    "Conf.":     m["confianza_clasif"],
                }
                for m in resultado["movimientos"]
            ])
            st.dataframe(df_movs, use_container_width=True, hide_index=True)

            baja_conf = sum(1 for m in resultado["movimientos"] if m["confianza_clasif"] == "baja")
            if baja_conf:
                st.warning(
                    f"⚠️ {baja_conf} movimientos quedaron con confianza BAJA. "
                    "Después de guardar, podrás reclasificarlos manualmente."
                )

            # Botón de guardar
            st.markdown("##### Guardar en la plataforma")
            anio_g = st.session_state["__resultado_anio"]
            mes_g  = st.session_state["__resultado_mes"]
            st.caption(
                f"Al guardar, se creará/actualizará la declaración del período "
                f"**{anio_g}-{mes_g:02d}** con estos datos."
            )

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                if st.button("💾 Guardar declaración", type="primary"):
                  try:
                    with st.spinner("Guardando..."):
                        decl = svc.crear_declaracion(
                            sb, empresa["id"], anio_g, mes_g,
                            user_id=user["id"] if user else None,
                        )
                        svc.actualizar_totales_declaracion(sb, decl["id"], {
                            **t,
                            "ciiu_aplicado":      config["ciiu_principal"],
                            "tarifa_aplicada":    st.session_state["__resultado_tarifa"],
                            "normativa_aplicada": st.session_state["__resultado_normativa"],
                        })
                        movs_payload = [
                            {
                                "cuenta_puc":        m["cuenta_puc"],
                                "nit_tercero":       m["nit_tercero"],
                                "nombre_tercero":    m["nombre_tercero"],
                                "tipo_inferido":     m["tipo_inferido"],
                                "es_extranjero":     bool(m["es_extranjero"]),
                                "base":              float(m["base"]),
                                "tarifa":            float(m["tarifa"]),
                                "retencion":         float(m["retencion"]),
                                "casilla_destino":   m["casilla_destino"] if isinstance(m["casilla_destino"], int) else None,
                                "concepto_asignado": m["concepto_asignado"],
                                "confianza_clasif":  m["confianza_clasif"],
                                "regla_clasif":      m["regla_clasif"],
                                "estado":            m["estado"],
                            }
                            for m in resultado["movimientos"]
                        ]
                        svc.guardar_movimientos(sb, decl["id"], movs_payload)

                        # Subcuentas (si vienen con detalle)
                        detalle = resultado.get("autorret_detalle") or {}
                        if isinstance(detalle, dict) and "detalle_subcuentas" in detalle:
                            subc_payload = [
                                {
                                    "codigo_subcuenta": s["codigo"],
                                    "nombre_subcuenta": s.get("nombre"),
                                    "creditos":         float(s.get("creditos") or 0),
                                    "debitos":          float(s.get("debitos") or 0),
                                    "incluida":         True,
                                }
                                for s in detalle["detalle_subcuentas"]
                            ]
                            excluidas = [
                                {
                                    "codigo_subcuenta": s["codigo"],
                                    "nombre_subcuenta": s.get("nombre"),
                                    "creditos":         float(s.get("creditos") or 0),
                                    "debitos":          float(s.get("debitos") or 0),
                                    "incluida":         False,
                                }
                                for s in detalle.get("subcuentas_excluidas", [])
                            ]
                            svc.guardar_subcuentas(sb, decl["id"], subc_payload + excluidas)

                    st.success(
                        "✅ Declaración guardada. "
                        "Puedes verla en la pestaña **Declaraciones**."
                    )
                    st.balloons()
                    # Limpiar el resultado para no volver a guardar
                    st.session_state.pop("__resultado_proc", None)
                  except Exception as e:
                    # Mostrar el mensaje real (incluido APIError de PostgREST/RLS)
                    # de forma controlada, sin desactivar showErrorDetails global.
                    msg = getattr(e, "message", None) or str(e)
                    st.error(f"No se pudo guardar la declaración: {msg}")
                    detalles = getattr(e, "details", None) or getattr(e, "hint", None)
                    if detalles:
                        st.caption(f"Detalle: {detalles}")
            with col_g2:
                if st.button("🗑️ Descartar resultado"):
                    st.session_state.pop("__resultado_proc", None)
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Configuración por empresa
# ─────────────────────────────────────────────────────────────────────────────

with tab_config:
    st.subheader("Configuración F350 de la empresa")
    st.caption(
        "Estos datos se usan para clasificar movimientos y calcular la "
        "autorretención. Se aplican a todas las declaraciones futuras."
    )

    with st.form("form_config_f350"):
        col1, col2 = st.columns(2)
        with col1:
            ciiu_actual = config.get("ciiu_principal") or ""
            ciiu_input = st.text_input(
                "CIIU principal",
                value=ciiu_actual,
                placeholder="ej. 5611",
                help="Código CIIU Rev. 4 A.C. 2020. Búscalo en la pestaña Catálogo CIIU.",
            )
            es_autorret = st.checkbox(
                "¿Es autorretenedor especial?",
                value=bool(config.get("es_autorretenedor")),
                help="Sociedades obligadas al art. 1.2.6.6 ET — la mayoría de S.A.S. lo son.",
            )
            exonerado_114 = st.checkbox(
                "¿Está exonerado del Art. 114-1 (aportes parafiscales)?",
                value=bool(config.get("exonerado_art_114_1")),
                help="Si lo está, la autorretención va a la casilla 'Contribuyentes exonerados 114-1' (68).",
            )
        with col2:
            tarifa_actual = config.get("tarifa_autorretencion_manual")
            tarifa_input = st.number_input(
                "Tarifa autorretención manual (%)",
                min_value=0.00,
                max_value=10.00,
                value=float(tarifa_actual * 100) if tarifa_actual else 0.0,
                step=0.01,
                format="%.2f",
                help="Solo úsala si la del catálogo CIIU no aplica o quieres sobreescribirla. Deja 0 para usar la del catálogo.",
            )
            representante = st.text_input(
                "Representante legal",
                value=config.get("representante_legal") or "",
            )
            email_contacto = st.text_input(
                "Email de contacto",
                value=config.get("email_contacto") or "",
            )

        notas = st.text_area(
            "Notas internas",
            value=config.get("notas") or "",
            help="Notas para el contador. No aparecen en el F350.",
        )

        submitted = st.form_submit_button("💾 Guardar configuración", type="primary")

    if submitted:
        # Si cambió el CIIU, registramos en el historial
        if ciiu_input and ciiu_input != ciiu_actual:
            try:
                svc.registrar_cambio_ciiu(
                    sb,
                    empresa_id=empresa["id"],
                    ciiu_anterior=(ciiu_actual or None),
                    ciiu_nuevo=ciiu_input,
                    fecha_vigencia_desde=date.today(),
                    motivo="Cambio desde el módulo F350",
                    user_id=user["id"] if user else None,
                )
            except Exception as e:
                st.warning(f"No se pudo registrar el historial de CIIU: {e}")

        payload = {
            "ciiu_principal":                ciiu_input or None,
            "es_autorretenedor":             bool(es_autorret),
            "tarifa_autorretencion_manual":  (tarifa_input / 100) if tarifa_input > 0 else None,
            "exonerado_art_114_1":           bool(exonerado_114),
            "representante_legal":           representante or None,
            "email_contacto":                email_contacto or None,
            "notas":                         notas or None,
        }
        try:
            svc.guardar_config_empresa(sb, empresa["id"], payload)
            st.success("✅ Configuración guardada.")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error guardando: {e}")

    # Historial de CIIU
    st.divider()
    st.markdown("##### Historial de cambios de CIIU")
    historial = svc.historial_ciiu(sb, empresa["id"])
    if historial:
        df_hist = pd.DataFrame([
            {
                "Desde":     (h["fecha_vigencia_desde"] or "")[:10],
                "Anterior":  h.get("ciiu_anterior") or "—",
                "Nuevo":     h["ciiu_nuevo"],
                "Motivo":    h.get("motivo_cambio") or "—",
                "Radicado":  h.get("numero_radicado_pqr") or "—",
                "Registrado":(h.get("creado_en") or "")[:10],
            }
            for h in historial
        ])
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
    else:
        st.caption("Sin cambios registrados.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — Catálogo CIIU (búsqueda)
# ─────────────────────────────────────────────────────────────────────────────

with tab_catalogo:
    st.subheader("Buscar en el catálogo CIIU")
    st.caption(
        "Catálogo de actividades económicas con tarifas de autorretención. "
        "Las marcadas como 'SUSPENDIDO' corresponden al Dec. 0572/2025 que "
        "fue suspendido por el Consejo de Estado el 7 de mayo de 2026."
    )

    query = st.text_input(
        "Buscar por código o nombre de actividad",
        placeholder="ej. 5611 o 'comidas'",
    )

    if query:
        ciius = svc.listar_ciiu(sb, query=query, limit=30)
    else:
        ciius = svc.listar_ciiu(sb, limit=30)

    if not ciius:
        st.info("Sin resultados.")
    else:
        df_ciiu = pd.DataFrame([
            {
                "Código":      c["codigo"],
                "Actividad":   c["actividad_economica"],
                "Sección":     c.get("seccion_ciiu") or "—",
                "Tarifa":      f"{c['tarifa_autorretencion']*100:.2f}%" if c.get("tarifa_autorretencion") else "—",
                "Desde":       c.get("vigencia_desde") or "—",
                "Hasta":       c.get("vigencia_hasta") or "Vigente",
                "Normativa":   c.get("normativa") or "—",
            }
            for c in ciius
        ])
        st.dataframe(df_ciiu, use_container_width=True, hide_index=True)


# =============================================================================
# SIDEBAR — info del módulo
# =============================================================================

with st.sidebar:
    st.divider()
    st.markdown("### 📋 Módulo F350")
    if config.get("ciiu_principal"):
        st.success(f"CIIU: **{config['ciiu_principal']}**")
        if config.get("es_autorretenedor"):
            st.caption("🟢 Autorretenedor especial")
        if config.get("exonerado_art_114_1"):
            st.caption("🟢 Exonerado Art. 114-1")
    else:
        st.warning("CIIU sin configurar")

    uvt_actual = svc.obtener_uvt(sb, date.today().year)
    if uvt_actual:
        st.caption(
            f"UVT {date.today().year}: "
            f"${uvt_actual['valor_uvt_pesos']:,}".replace(",", ".")
        )
