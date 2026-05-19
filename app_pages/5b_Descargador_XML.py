"""
app_pages/5b_Descargador_XML.py

Descargador + Procesador XML DIAN (versión simplificada — mayo 2026).

Flujo:
  1️⃣  Subir Excel del Token DIAN (referencia para los CUFEs disponibles)
  2️⃣  Detectar tipos de documento para RECIBIDOS (checkboxes)
       Detectar prefijos disponibles para EMITIDOS (multiselect)
  3️⃣  Pegar Token URL y descargar
  4️⃣  Procesar XMLs → plano contable + plano terceros nuevos
"""
from __future__ import annotations

import io
import json
import math
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa

# Lectores / descargador
from core.procesadores import lector_excel_token as lex
from core.procesadores import descargador_dian as dd

# Procesador XML (con parser extendido para terceros)
from core.procesadores.procesador_dian_xml import (
    RegistryEmpresas,
    procesar_multiples_zips,
    separar_lineas_por_comprobante,
    ZipInput,
)
from core.procesadores.motor_mapeo_v03 import CatalogoEmpresa
from core.procesadores.exportador_silla_tres import (
    construir_dataframe_silla_tres,
    exportar_txt_silla_tres,
    exportar_csv_silla_tres,
    exportar_xlsx_silla_tres,
)
from core.procesadores import puente_motor_v03
from core.procesadores import exportador_nits_siigo as exp_nits
from core.procesadores import agregador_terceros_xml as agr_terc


EMPRESAS_DIR = ROOT / "core" / "data" / "empresas"
puente_motor_v03.activar(ruta_empresas=EMPRESAS_DIR)


# ═══════════════════════════════════════════════════════════════════════
# Setup
# ═══════════════════════════════════════════════════════════════════════

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

st.title("📥 Descargador XML DIAN")
st.caption(
    "Sube el Excel del Token como referencia, elige tipos de documentos "
    "(recibidos) y prefijos (emitidos), descarga directo de DIAN y procesa "
    "los XMLs al plano contable + plano de terceros nuevos para Siigo."
)


# ═══════════════════════════════════════════════════════════════════════
# PASO 1 — Subir Excel del Token DIAN
# ═══════════════════════════════════════════════════════════════════════

st.markdown("## 1️⃣ Sube el Excel del Token DIAN")
st.caption(
    "Descárgalo desde el portal DIAN (botón 'Exportar a Excel' después de "
    "generar un Token). Es la referencia maestra de qué documentos existen "
    "en el período."
)

archivo_token = st.file_uploader(
    "Excel del Token (.xlsx)",
    type=["xlsx"],
    key="up_token_xml",
)

if archivo_token is None:
    st.info("👆 Sube el Excel del Token para continuar.")
    st.stop()

# Leer el Excel
try:
    with st.spinner("Leyendo Excel del Token..."):
        df_token = lex.leer_excel_token(archivo_token)
except Exception as e:
    st.error(f"❌ Error leyendo el Excel: {e}")
    st.stop()

st.success(f"✅ Excel leído: {len(df_token):,} documentos en total.")


# ── Filtro de fechas ──────────────────────────────────────────────────
fechas_validas = df_token["fecha_emision"].dropna()
if len(fechas_validas) == 0:
    st.error("❌ El Excel no tiene fechas de emisión válidas.")
    st.stop()

f_min = fechas_validas.min().date()
f_max = fechas_validas.max().date()

col_fa, col_fb = st.columns(2)
with col_fa:
    f_desde = st.date_input(
        "Desde", value=f_min, min_value=f_min, max_value=f_max,
        format="YYYY-MM-DD", key="xml_fdesde",
    )
with col_fb:
    f_hasta = st.date_input(
        "Hasta", value=f_max, min_value=f_min, max_value=f_max,
        format="YYYY-MM-DD", key="xml_fhasta",
    )

df_filt = lex.filtrar_por_rango(df_token, f_desde, f_hasta)
st.caption(f"📅 Rango seleccionado: **{len(df_filt):,} documentos** entre {f_desde} y {f_hasta}.")

if len(df_filt) == 0:
    st.warning("No hay documentos en este rango de fechas.")
    st.stop()


# ═══════════════════════════════════════════════════════════════════════
# PASO 2 — Filtros: tipos para RECIBIDOS / prefijos para EMITIDOS
# ═══════════════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 2️⃣ Elige qué descargar")

df_recb = df_filt[df_filt["grupo"].str.lower() == "recibido"].copy()
df_emit = df_filt[df_filt["grupo"].str.lower() == "emitido"].copy()

col_r, col_e = st.columns(2)

# ───── RECIBIDOS: checkboxes por tipo de documento ─────────────────────
with col_r:
    st.markdown("### 📥 RECIBIDOS")
    st.metric("Total en rango", f"{len(df_recb):,}")

    # Tipos disponibles en el Excel para recibidos
    tipos_recb_disponibles = (
        df_recb["tipo_documento"].value_counts().to_dict()
    )

    if not tipos_recb_disponibles:
        st.info("No hay documentos recibidos en el rango.")
        tipos_recb_seleccionados = []
    else:
        st.caption("Marca los tipos a descargar:")
        tipos_recb_seleccionados = []
        for tipo, n in sorted(
            tipos_recb_disponibles.items(), key=lambda x: -x[1]
        ):
            # Default OFF para Application response (acuses) y Nomina Individual
            es_excluible = tipo in lex.TIPOS_EXCLUIBLES
            default_marcado = not es_excluible
            etiqueta_extra = " _(no contable)_" if es_excluible else ""
            chk = st.checkbox(
                f"**{tipo}** — {n:,} doc(s){etiqueta_extra}",
                value=default_marcado,
                key=f"chk_recb_{tipo}",
            )
            if chk:
                tipos_recb_seleccionados.append(tipo)

        df_recb_sel = df_recb[df_recb["tipo_documento"].isin(tipos_recb_seleccionados)]
        st.success(f"✅ A descargar: **{len(df_recb_sel):,} documentos recibidos**")


# ───── EMITIDOS: multiselect por prefijo ───────────────────────────────
with col_e:
    st.markdown("### 📤 EMITIDOS")
    st.metric("Total en rango", f"{len(df_emit):,}")

    # Excluir tipos no contables de los emitidos
    df_emit_util = df_emit[~df_emit["tipo_documento"].isin(lex.TIPOS_EXCLUIBLES)]

    # Listar todos los prefijos disponibles con conteos
    prefijos_emit = (
        df_emit_util["prefijo"]
        .astype(str)
        .str.strip()
        .str.upper()
        .replace("", "(sin prefijo)")
        .value_counts()
        .to_dict()
    )

    if not prefijos_emit:
        st.info("No hay documentos emitidos en el rango.")
        prefijos_emit_seleccionados = []
        df_emit_sel = df_emit.iloc[0:0]
    else:
        st.caption("Marca los prefijos a descargar:")

        # Opciones formato "STL (1,234 docs)" para que el usuario vea cuántos hay
        opciones = [
            f"{pref} — {n:,} doc(s)"
            for pref, n in sorted(prefijos_emit.items(), key=lambda x: -x[1])
        ]
        mapa_opcion_a_prefijo = {
            f"{pref} — {n:,} doc(s)": pref
            for pref, n in prefijos_emit.items()
        }

        # Defaults: STL y DSE (lo más usado históricamente en JIPER)
        defaults_recomendados = [
            opc for opc in opciones
            if mapa_opcion_a_prefijo[opc] in ("STL", "DSE")
        ]

        seleccion = st.multiselect(
            "Prefijos:",
            options=opciones,
            default=defaults_recomendados,
            key="ms_pref_emit",
        )
        prefijos_emit_seleccionados = [
            mapa_opcion_a_prefijo[s] for s in seleccion
        ]

        # Construir df de emitidos a descargar
        mascara = (
            df_emit_util["prefijo"]
            .astype(str).str.strip().str.upper()
            .replace("", "(sin prefijo)")
            .isin(prefijos_emit_seleccionados)
        )
        df_emit_sel = df_emit_util[mascara]
        st.success(f"✅ A descargar: **{len(df_emit_sel):,} documentos emitidos**")


# Consolidar lista de CUFEs total a descargar
df_recb_sel = (
    df_recb[df_recb["tipo_documento"].isin(tipos_recb_seleccionados)]
    if tipos_recb_seleccionados else df_recb.iloc[0:0]
)

# ───── Resumen total ───────────────────────────────────────────────────
st.markdown("---")
total_descargar = len(df_recb_sel) + len(df_emit_sel)
col_t1, col_t2, col_t3 = st.columns(3)
col_t1.metric("Total a descargar", f"{total_descargar:,}")
col_t2.metric("Recibidos", f"{len(df_recb_sel):,}")
col_t3.metric("Emitidos", f"{len(df_emit_sel):,}")

if total_descargar == 0:
    st.warning("⚠️ No hay documentos seleccionados. Marca tipos o prefijos arriba.")
    st.stop()

n_hilos_total = max(1, math.ceil(total_descargar / 500))
st.caption(f"Se descargarán en **{n_hilos_total} hilo(s) paralelo(s)** de hasta 500 docs.")


# ═══════════════════════════════════════════════════════════════════════
# PASO 3 — Pegar Token URL y descargar
# ═══════════════════════════════════════════════════════════════════════

st.markdown("---")
st.markdown("## 3️⃣ Token URL y descarga")

token_url = st.text_input(
    "URL completa del Token (de catalogo-vpfe.dian.gov.co)",
    placeholder="https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=...&rk=...&token=...",
    key="xml_token_url",
    type="password",
    help="Genera un Token desde el portal DIAN y pega aquí la URL completa.",
)

# Estado persistente de descargas
if "xml_descargas" not in st.session_state:
    st.session_state["xml_descargas"] = {
        "zips_por_cufe": {},     # cufe → bytes del ZIP DIAN
        "fallidos": [],          # lista de tuplas (cufe, motivo)
        "intentado": False,      # se intentó al menos una descarga
    }

estado_dl = st.session_state["xml_descargas"]
n_ya_descargados = len(estado_dl["zips_por_cufe"])
if n_ya_descargados > 0:
    st.caption(f"📦 Ya descargados en sesión actual: **{n_ya_descargados:,} XMLs**")


def _ejecutar_descarga():
    """Lanza la descarga paralela con los CUFEs seleccionados."""
    if not token_url:
        st.error("Pega primero la URL del Token DIAN.")
        return

    # Lista de CUFEs final (recibidos + emitidos) — solo los no descargados aún
    cufes_recb = df_recb_sel["cufe"].dropna().astype(str).tolist()
    cufes_emit = df_emit_sel["cufe"].dropna().astype(str).tolist()
    cufes_todos = [c for c in (cufes_recb + cufes_emit) if c]
    cufes_pendientes = [
        c for c in cufes_todos if c not in estado_dl["zips_por_cufe"]
    ]

    if not cufes_pendientes:
        st.info("✅ Ya están todos descargados. Pasa al paso 4.")
        return

    estado_dl["intentado"] = True
    n_hilos = max(1, math.ceil(len(cufes_pendientes) / 500))
    st.info(
        f"🚀 Descargando **{len(cufes_pendientes):,} XMLs** "
        f"en **{n_hilos} hilo(s) paralelo(s)** (max 500 docs/hilo)."
    )

    try:
        ctrl = dd.iniciar_descarga_paralela(
            token_url,
            cufes_pendientes,
            tam_bloque=500,
            delay=0.15,
        )
    except (dd.SesionExpirada, ValueError) as e:
        st.error(f"❌ Token inválido: {e}")
        return

    iconos = {
        "pendiente": "⏳", "descargando": "⬇️", "ok": "✅",
        "sesion_expirada": "⚠️", "error": "❌",
    }
    slot = st.empty()

    while ctrl.esta_corriendo():
        progresos = ctrl.obtener_progreso()
        with slot.container():
            if not progresos:
                st.caption("Inicializando hilos…")
            else:
                total_proc = sum(p.procesados for p in progresos)
                total_ok = sum(p.exitosos for p in progresos)
                total_lote = sum(
                    p.rango_hasta - p.rango_desde + 1 for p in progresos
                )
                st.markdown(
                    f"#### Progreso: **{total_proc:,} / {total_lote:,}** "
                    f"(✅ {total_ok:,} OK)"
                )
                for p in progresos:
                    total_h = p.rango_hasta - p.rango_desde + 1
                    pct = (p.procesados / total_h) if total_h else 0
                    st.progress(
                        pct,
                        text=(
                            f"{iconos.get(p.estado, '❓')} Hilo {p.hilo_id} "
                            f"({p.rango_desde:,}–{p.rango_hasta:,}): "
                            f"{p.procesados}/{total_h} "
                            f"· ok={p.exitosos} · fail={p.fallidos}"
                        ),
                    )
        time.sleep(0.5)

    res, _ = ctrl.esperar_resultado()
    slot.empty()

    # Acumular en sesión
    estado_dl["zips_por_cufe"].update(res.exitosos)
    estado_dl["fallidos"].extend(res.fallidos)

    if res.motivo_parada == "completo":
        st.success(
            f"🎉 Descarga COMPLETA: {res.total_exitosos:,} XMLs en "
            f"{res.duracion_seg:.0f}s "
            f"({res.total_exitosos/max(res.duracion_seg, 1):.1f} XMLs/s)"
        )
    elif res.motivo_parada == "sesion_expirada":
        st.warning(
            f"⚠️ Token expirado. {res.total_exitosos:,} descargados. "
            f"Genera un Token nuevo y dale al botón otra vez."
        )
    else:
        st.info(f"Descarga parcial: {res.total_exitosos:,} OK. Motivo: {res.motivo_parada}")


if st.button(
    "⬇️ Descargar seleccionados",
    type="primary",
    use_container_width=True,
    disabled=(not token_url or total_descargar == 0),
    key="btn_dl_xml_unified",
):
    _ejecutar_descarga()
    st.rerun()


# ═══════════════════════════════════════════════════════════════════════
# PASO 4 — Procesar XMLs descargados
# ═══════════════════════════════════════════════════════════════════════

if not estado_dl["intentado"] or not estado_dl["zips_por_cufe"]:
    st.stop()

st.markdown("---")
st.markdown("## 4️⃣ Procesar XMLs descargados")

n_zips = len(estado_dl["zips_por_cufe"])
st.caption(f"Listos para procesar **{n_zips:,} XMLs descargados**.")


# Año/mes contable
col_am1, col_am2 = st.columns(2)
with col_am1:
    anio = st.number_input(
        "Año contable", min_value=2020, max_value=2030,
        value=f_desde.year, step=1, key="xml_anio",
    )
with col_am2:
    mes = st.number_input(
        "Mes contable", min_value=1, max_value=12,
        value=f_desde.month, step=1, key="xml_mes",
    )

# Consecutivos iniciales
st.caption("Consecutivos iniciales por comprobante:")
c_a, c_b, c_c = st.columns(3)
with c_a:
    cons_3 = st.number_input("Compras (3)", min_value=1, value=1, step=1, key="xml_c3")
with c_b:
    cons_7 = st.number_input("ND (7)", min_value=1, value=1, step=1, key="xml_c7")
with c_c:
    cons_12 = st.number_input("NC (12)", min_value=1, value=1, step=1, key="xml_c12")

consecutivos_iniciales = {"3": int(cons_3), "7": int(cons_7), "12": int(cons_12)}


def _cargar_catalogo_para(empresa_id: str) -> CatalogoEmpresa:
    """Busca la carpeta de empresa por NIT o ID."""
    for p in EMPRESAS_DIR.iterdir():
        if not p.is_dir() or p.name.startswith("_"):
            continue
        if p.name.startswith(f"{empresa_id}_") or p.name == empresa_id:
            return CatalogoEmpresa.cargar(p)
    raise FileNotFoundError(f"No se encontró carpeta para empresa_id={empresa_id}")


if st.button("⚙️ Procesar XMLs", type="primary", use_container_width=True, key="btn_proc_xml"):
    try:
        registry = RegistryEmpresas(EMPRESAS_DIR)
    except Exception as e:
        st.error(f"❌ No se pudo cargar el registry de empresas: {e}")
        st.stop()

    # Consolidar todos los ZIPs descargados en un solo ZIP plano
    with st.spinner("Consolidando XMLs en un ZIP único..."):
        zip_unificado = dd.juntar_zips(estado_dl["zips_por_cufe"])

    anio_mes = f"{int(anio)}{int(mes):02d}"

    with st.spinner(f"Procesando {n_zips:,} XMLs..."):
        zips_input = [
            ZipInput(
                nombre="descarga_dian.zip",
                contenido=zip_unificado,
                tipo_declarado=None,
            )
        ]
        try:
            resultados, resumen = procesar_multiples_zips(
                zips_input, registry, anio_mes,
            )
        except Exception as e:
            st.error(f"❌ Error al procesar: {e}")
            import traceback
            with st.expander("Detalle"):
                st.code(traceback.format_exc())
            st.stop()

    # Post-procesar para agregar retenciones (motor v0.3)
    try:
        resultados = puente_motor_v03.agregar_retenciones_a_resultados(
            resultados, ruta_empresas=EMPRESAS_DIR,
            consecutivos_iniciales=consecutivos_iniciales,
        )
    except Exception as e:
        st.warning(f"⚠️ El motor v0.3 no aplicó retenciones: {e}")

    st.session_state["xml_resultados"] = resultados
    st.session_state["xml_resumen"] = resumen
    st.session_state["xml_anio_mes"] = anio_mes


# ── Mostrar resultados ────────────────────────────────────────────────
if "xml_resultados" in st.session_state:
    resultados = st.session_state["xml_resultados"]
    resumen = st.session_state["xml_resumen"]
    anio_mes = st.session_state.get("xml_anio_mes", "XXXXXX")

    st.markdown("---")
    st.markdown("### 📊 Resumen del procesamiento")

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("XMLs extraídos", resumen.total_xmls_extraidos)
    col_m2.metric("Duplicados", resumen.duplicados_descartados)
    col_m3.metric("Errores parseo", resumen.errores_parseo)
    col_m4.metric("Empresas", len(resumen.por_empresa))

    if resumen.por_tipo:
        st.caption("Por tipo:")
        st.write({
            tipo: f"{n:,}" for tipo, n in resumen.por_tipo.items()
        })

    # ── Plano contable por empresa ────────────────────────────────
    st.markdown("### 📄 Plano contable por empresa")
    for r in resultados:
        emoji = "✅" if r.cuadrado else "❌"
        with st.expander(
            f"{emoji} {r.empresa_razon_social} — "
            f"{len(r.documentos)} doc(s) · {len(r.lineas_plano)} líneas · "
            f"Db ${r.cuadre_db:,.0f} = Cr ${r.cuadre_cr:,.0f}",
            expanded=True,
        ):
            for adv in r.advertencias or []:
                st.warning(f"⚠️ {adv}")

            try:
                cat = _cargar_catalogo_para(r.empresa_id)
                cc_formato = cat.empresa_json.get("formato_salida", {}).get(
                    "cc_formato", "sin_guion"
                )
            except Exception:
                cc_formato = "sin_guion"

            df_plano = construir_dataframe_silla_tres(
                r.lineas_plano,
                cc_formato=cc_formato,
                consecutivo_inicial=min(consecutivos_iniciales.values()),
            )

            if df_plano.empty:
                st.info("No hay líneas en el plano.")
                continue

            st.dataframe(df_plano, use_container_width=True, height=300, hide_index=True)

            base = f"plano_{r.empresa_id}_{anio_mes}"
            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button(
                    "⬇️ TXT", data=exportar_txt_silla_tres(df_plano),
                    file_name=f"{base}.txt", mime="text/plain",
                    key=f"dl_t_{r.empresa_id}", use_container_width=True,
                )
            with col2:
                st.download_button(
                    "⬇️ CSV", data=exportar_csv_silla_tres(df_plano),
                    file_name=f"{base}.csv", mime="text/csv",
                    key=f"dl_c_{r.empresa_id}", use_container_width=True,
                )
            with col3:
                st.download_button(
                    "⬇️ Excel", data=exportar_xlsx_silla_tres(df_plano),
                    file_name=f"{base}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_x_{r.empresa_id}", use_container_width=True,
                )

    # ── Plano de TERCEROS NUEVOS ──────────────────────────────────
    st.markdown("---")
    st.markdown("### 👥 Plano de TERCEROS NUEVOS para Siigo")
    st.caption(
        "Emisores detectados en los XMLs que NO están en el histórico/mapeo "
        "de la empresa. Formato Siigo NITs (20 columnas)."
    )

    try:
        maestro_xml = agr_terc.construir_maestro_desde_resultados(resultados)
        total_em = len(maestro_xml.get("terceros", {}))

        if total_em == 0:
            st.info("No se detectaron emisores en los XMLs.")
        else:
            RUTA_HIST = ROOT / "mapeo_compras_historico.json"
            nits_extra = set()
            for r in resultados:
                try:
                    cat = _cargar_catalogo_para(r.empresa_id)
                    for n in cat.mapeo_nits.keys():
                        nits_extra.add(n)
                except Exception:
                    pass

            nits_nuevos = agr_terc.detectar_nits_nuevos(
                maestro_xml,
                ruta_historico_compras=RUTA_HIST if RUTA_HIST.exists() else None,
                nits_extra_conocidos=nits_extra,
            )

            col_e1, col_e2 = st.columns(2)
            col_e1.metric("Emisores vistos", f"{total_em:,}")
            col_e2.metric("Terceros nuevos", f"{len(nits_nuevos):,}")

            if nits_nuevos:
                df_terc = exp_nits.exportar_nits_desde_maestro(
                    maestro_xml, nits_filtrar=nits_nuevos,
                )

                nat = df_terc["NATURALEZA"].value_counts().to_dict()
                cn1, cn2 = st.columns(2)
                cn1.metric("Jurídicas (J)", f"{nat.get('J', 0):,}")
                cn2.metric("Naturales (N)", f"{nat.get('N', 0):,}")

                base_t = f"nits_xml_{anio_mes}"
                col_dt1, col_dt2 = st.columns(2)
                with col_dt1:
                    st.download_button(
                        f"⬇️ NITs Excel formato Siigo ({len(df_terc):,})",
                        data=exp_nits.generar_excel_nits_siigo(df_terc),
                        file_name=f"{base_t}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        type="primary",
                        key="dl_terc_xml_b",
                    )
                with col_dt2:
                    tsv = df_terc.to_csv(sep="\t", index=False, encoding="utf-8")
                    st.download_button(
                        f"⬇️ NITs TSV ({len(df_terc):,})",
                        data=tsv.encode("utf-8"),
                        file_name=f"{base_t}.txt",
                        mime="text/tab-separated-values",
                        use_container_width=True,
                        key="dl_terc_xml_tsv_b",
                    )

                with st.expander("Vista previa (primeros 10)"):
                    st.dataframe(df_terc.head(10), use_container_width=True, hide_index=True)
            else:
                st.success("✅ Todos los emisores ya están en el histórico.")
    except Exception as e:
        st.warning(f"⚠️ No se pudo generar el plano de terceros: {e}")


# ═══════════════════════════════════════════════════════════════════════
# Reset
# ═══════════════════════════════════════════════════════════════════════

st.markdown("---")
if st.button("🔄 Limpiar y procesar otro mes", key="btn_reset_xml"):
    for k in ["xml_descargas", "xml_resultados", "xml_resumen", "xml_anio_mes"]:
        st.session_state.pop(k, None)
    st.rerun()
