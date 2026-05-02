"""
Módulo Información Exógena DIAN

Genera los 17 formatos del prevalidador DIAN AG 2025 a partir del balance
auxiliar y maestro de terceros importados. Conforme a Resolución 000227/2025.

Arquitectura del módulo:
    - core/exogena/clasificador_nits.py     → Clasifica NITs por rangos oficiales
    - core/exogena/cargador_terceros.py     → Carga maestro de terceros
    - core/exogena/cargador_codificacion_nativa.py → Carga reglas del software
    - core/exogena/motor_clasificacion.py   → Motor de las 3 capas
    - core/exogena/validador_xsd.py         → Validador XML contra XSDs
    - core/exogena/enriquecimiento/         → Fuentes externas (RUES, Apitude)
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa, require_rol
from db.supabase_client import get_supabase
from core.utils.ui_tributarias import render_pagina_tributaria, render_proximamente


# ============================================================
# Guardia de autenticación
# ============================================================

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()


# ============================================================
# Cabecera
# ============================================================

render_pagina_tributaria(
    titulo="Información Exógena DIAN",
    descripcion="Generación de los 17 formatos del prevalidador AG 2025 según Res. 000227/2025",
    icono="📑",
)


# ============================================================
# Sidebar: selección del periodo
# ============================================================

with st.sidebar:
    st.markdown("### 📅 Periodo de trabajo")
    año_gravable = st.selectbox(
        "Año gravable",
        options=[2025, 2024, 2023],
        index=0,
        key="exo_año",
    )


# ============================================================
# Helpers de BD (cached para minimizar consultas)
# ============================================================

@st.cache_data(ttl=60, show_spinner=False)
def obtener_periodo(empresa_id: str, año: int) -> dict | None:
    """Devuelve el periodo activo o None si no existe aún."""
    sb = get_supabase()
    try:
        resp = sb.table("exogena_periodos").select("*").eq(
            "empresa_id", empresa_id
        ).eq("año_gravable", año).limit(1).execute()
        return resp.data[0] if resp.data else None
    except Exception:
        return None


@st.cache_data(ttl=60, show_spinner=False)
def contar_terceros(empresa_id: str) -> dict:
    """Cuenta totales y por tipo del maestro de terceros."""
    sb = get_supabase()
    try:
        resp = sb.table("exogena_terceros").select(
            "tipo_persona, requiere_revision", count="exact"
        ).eq("empresa_id", empresa_id).execute()
        rows = resp.data or []
        return {
            "total": len(rows),
            "naturales": sum(1 for r in rows if r.get("tipo_persona") == "natural"),
            "juridicas": sum(1 for r in rows if r.get("tipo_persona") == "juridica"),
            "revisar": sum(1 for r in rows if r.get("requiere_revision")),
        }
    except Exception:
        return {"total": 0, "naturales": 0, "juridicas": 0, "revisar": 0}


@st.cache_data(ttl=60, show_spinner=False)
def contar_reglas_mapeo(empresa_id: str, año: int) -> int:
    """Cuenta reglas activas del mapeo nativo."""
    sb = get_supabase()
    try:
        resp = sb.table("exogena_mapeo_empresa").select(
            "id", count="exact"
        ).eq("empresa_id", empresa_id).eq("año_gravable", año).eq("activo", True).execute()
        return len(resp.data or [])
    except Exception:
        return 0


def crear_periodo_si_no_existe(empresa_id: str, año: int) -> dict:
    """Crea el periodo si no existe y lo retorna."""
    sb = get_supabase()
    periodo = obtener_periodo(empresa_id, año)
    if periodo:
        return periodo
    resp = sb.table("exogena_periodos").insert({
        "empresa_id": empresa_id,
        "año_gravable": año,
        "estado": "borrador",
    }).execute()
    obtener_periodo.clear()
    return resp.data[0]


# ============================================================
# Estado: información sobre obligación
# ============================================================

st.subheader("📅 Estado de la obligación")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Año gravable", str(año_gravable))
with col2:
    periodo_actual = obtener_periodo(empresa["id"], año_gravable)
    estado_label = periodo_actual["estado"] if periodo_actual else "no iniciado"
    st.metric("Estado", estado_label)
with col3:
    n_terceros = contar_terceros(empresa["id"])
    st.metric("Terceros maestro", n_terceros["total"])
with col4:
    n_reglas = contar_reglas_mapeo(empresa["id"], año_gravable)
    st.metric("Reglas de mapeo", n_reglas)

st.markdown("---")


# ============================================================
# Tabs principales del módulo
# ============================================================

tab_resumen, tab_mapeo, tab_terceros, tab_balance, tab_clasificar, tab_generar, tab_envios = st.tabs([
    "📊 Resumen",
    "🗂️ Mapeo nativo",
    "👥 Terceros",
    "📥 Balance",
    "⚙️ Clasificar",
    "📤 Generar XML",
    "📦 Envíos",
])


# ============================================================
# Tab: Resumen
# ============================================================

with tab_resumen:
    st.markdown("### Resumen del año gravable")

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("Formatos disponibles", "17")
    with col_b:
        st.metric("Reglas nativas", n_reglas)
    with col_c:
        st.metric("NITs a revisar", n_terceros["revisar"])
    with col_d:
        st.metric("Generados", "—")

    st.markdown("---")
    st.markdown("### Flujo recomendado")
    st.markdown(
        "1. **Mapeo nativo** — Cargar el archivo de codificación del software contable (rangos cuenta→formato).\n"
        "2. **Terceros** — Importar maestro de NITs, clasificar con reglas oficiales y enriquecer con RUES.\n"
        "3. **Balance** — Subir el balance de prueba con movimientos por NIT.\n"
        "4. **Clasificar** — Cruzar balance × mapeo × terceros, resolver ambigüedades.\n"
        "5. **Generar XML** — Producir los archivos para el prevalidador.\n"
        "6. **Envíos** — Histórico y descarga ZIP."
    )

    st.markdown("---")
    st.markdown("### Formatos que genera el módulo")
    formatos = pd.DataFrame([
        {"Código": "1001", "Nombre": "Pagos o abonos en cuenta y retenciones practicadas", "V": "10"},
        {"Código": "1003", "Nombre": "Retenciones en la fuente que le practicaron", "V": "7"},
        {"Código": "1004", "Nombre": "Descuentos tributarios solicitados", "V": "8"},
        {"Código": "1005", "Nombre": "IVA por pagar - Descontable", "V": "8"},
        {"Código": "1006", "Nombre": "IVA por pagar - Generado e impuesto al consumo", "V": "8"},
        {"Código": "1007", "Nombre": "Ingresos recibidos", "V": "9"},
        {"Código": "1008", "Nombre": "Saldos cuentas por cobrar al 31 de diciembre", "V": "7"},
        {"Código": "1009", "Nombre": "Saldos cuentas por pagar al 31 de diciembre", "V": "7"},
        {"Código": "1010", "Nombre": "Información de socios, accionistas y cooperados", "V": "9"},
        {"Código": "1011", "Nombre": "Información de las declaraciones tributarias", "V": "6"},
        {"Código": "1012", "Nombre": "Declaraciones, acciones, aportes e inversiones", "V": "7"},
        {"Código": "1056", "Nombre": "Pagos por secretarios generales del tesoro", "V": "10"},
        {"Código": "1647", "Nombre": "Ingresos recibidos para terceros", "V": "2"},
        {"Código": "2275", "Nombre": "Ingresos no constitutivos de renta ni ganancia", "V": "2"},
        {"Código": "2276", "Nombre": "Información de rentas de trabajo y pensiones", "V": "4"},
        {"Código": "2278", "Nombre": "Compra de bonos electrónicos / papel servicio", "V": "1"},
        {"Código": "5253", "Nombre": "Información de beneficiarios efectivos", "V": "2"},
    ])
    st.dataframe(formatos, use_container_width=True, hide_index=True)


# ============================================================
# Tab: Mapeo nativo (carga del archivo de codificación)
# ============================================================

with tab_mapeo:
    st.markdown("### 🗂️ Codificación nativa del software contable")
    st.caption(
        "Sube el archivo de codificación de formatos (Excel) que exporta tu software "
        "contable. Define rangos de cuentas → formato DIAN → concepto."
    )

    if n_reglas > 0:
        st.success(f"✅ {n_reglas} reglas nativas cargadas para AG {año_gravable}.")

    archivo_cod = st.file_uploader(
        "Archivo de codificación (xlsx)",
        type=["xlsx", "xls"],
        key="exo_archivo_codificacion",
        help="Estructura esperada: Código Formato | Cuenta Inicial | Cuenta Final | Concepto | Tipo Contrato | Valor",
    )

    if archivo_cod:
        from core.exogena.cargador_codificacion_nativa import cargar_codificacion_nativa
        try:
            res = cargar_codificacion_nativa(archivo_cod)
            st.success(f"✅ Archivo parseado: {res.reglas_validas} reglas válidas")
            
            if res.errores:
                with st.expander(f"⚠️ {len(res.errores)} advertencias"):
                    for e in res.errores[:20]:
                        st.text(e)

            # Distribución por formato
            df_dist = pd.DataFrame([
                {"Formato": f, "Reglas": n}
                for f, n in sorted(res.formatos_detectados.items())
            ])
            st.markdown("**Distribución por formato:**")
            st.dataframe(df_dist, use_container_width=True, hide_index=True)

            # Vista previa
            df_reglas = pd.DataFrame([{
                "Formato": r.formato_dian,
                "Concepto": r.concepto_dian,
                "Cuenta Inicial": r.cuenta_inicial,
                "Cuenta Final": r.cuenta_final,
                "Descripción": r.descripcion_concepto[:60],
            } for r in res.reglas[:50]])
            with st.expander("Vista previa (primeras 50 reglas)"):
                st.dataframe(df_reglas, use_container_width=True, hide_index=True, height=400)

            # Botón para guardar
            require_rol(["admin", "operador"])
            if st.button("💾 Guardar reglas en la base de datos", type="primary"):
                from core.exogena.cargador_codificacion_nativa import cargar_a_supabase
                try:
                    sb = get_supabase()
                    cargar_a_supabase(
                        archivo_cod, empresa["id"], año_gravable, sb,
                        reemplazar_existente=True,
                    )
                    contar_reglas_mapeo.clear()
                    st.success(f"✅ {res.reglas_validas} reglas guardadas en BD")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error guardando: {e}")
        except Exception as e:
            st.error(f"❌ Error parseando archivo: {e}")


# ============================================================
# Tab: Terceros
# ============================================================

with tab_terceros:
    st.markdown("### 👥 Maestro de terceros")
    
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("Total", n_terceros["total"])
    with col_b:
        st.metric("Naturales", n_terceros["naturales"])
    with col_c:
        st.metric("Jurídicas", n_terceros["juridicas"])
    with col_d:
        st.metric("⚠️ Revisar", n_terceros["revisar"])
    
    st.markdown("---")
    
    sub_t_carga, sub_t_revisar, sub_t_enriquecer = st.tabs([
        "📥 Cargar maestro",
        "🔍 Revisar dudosos",
        "🌐 Enriquecer (RUES)",
    ])
    
    # --- Subtab: Cargar maestro
    with sub_t_carga:
        st.caption(
            "Sube el Excel del maestro de terceros del software contable. "
            "El sistema aplica reglas oficiales DIAN (clasificación por rangos de NIT) "
            "y detecta NITs con DV pegado."
        )
        archivo_terceros = st.file_uploader(
            "Excel de terceros",
            type=["xlsx", "xls"],
            key="exo_archivo_terceros",
        )
        
        if archivo_terceros:
            from core.exogena.cargador_terceros import parsear_excel_terceros
            try:
                terceros = parsear_excel_terceros(archivo_terceros, aplicar_clasificador=True)
                st.success(f"✅ {len(terceros)} terceros parseados y clasificados")
                
                from collections import Counter
                tipos = Counter(t["tipo_persona"] for t in terceros)
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Naturales", tipos.get("natural", 0))
                with col2:
                    st.metric("Jurídicas", tipos.get("juridica", 0))
                with col3:
                    n_rev = sum(1 for t in terceros if t.get("requiere_revision"))
                    st.metric("⚠️ Requieren revisión", n_rev)
                
                require_rol(["admin", "operador"])
                if st.button("💾 Cargar a la base de datos", type="primary", key="btn_cargar_terceros"):
                    sb = get_supabase()
                    # Insertar en lotes
                    LOTE = 100
                    for i in range(0, len(terceros), LOTE):
                        chunk = []
                        for t in terceros[i:i+LOTE]:
                            t_db = {**t, "empresa_id": empresa["id"]}
                            # Limpiar campos extra que no van en BD
                            t_db.pop("sugerencias", None)
                            chunk.append(t_db)
                        sb.table("exogena_terceros").upsert(
                            chunk, on_conflict="empresa_id,nit"
                        ).execute()
                    contar_terceros.clear()
                    st.success(f"✅ {len(terceros)} terceros guardados")
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")
                st.exception(e)
    
    # --- Subtab: Revisar dudosos
    with sub_t_revisar:
        if n_terceros["revisar"] == 0:
            st.info("✅ No hay terceros marcados como dudosos.")
        else:
            sb = get_supabase()
            resp = sb.table("exogena_terceros").select("*").eq(
                "empresa_id", empresa["id"]
            ).eq("requiere_revision", True).limit(100).execute()
            
            df_rev = pd.DataFrame(resp.data or [])
            if len(df_rev):
                cols = ["nit", "nit_original", "tipo_persona", "razon_social",
                        "primer_nombre", "primer_apellido", "regla_clasificacion", "sugerencias"]
                cols_existentes = [c for c in cols if c in df_rev.columns]
                st.dataframe(df_rev[cols_existentes], use_container_width=True, hide_index=True)
                st.caption(
                    "Para resolver: actualizar manualmente en BD, o usar el subtab "
                    "**Enriquecer (RUES)** para autocompletar con datos públicos."
                )
    
    # --- Subtab: Enriquecer
    with sub_t_enriquecer:
        st.markdown("#### 🌐 Enriquecimiento con datos públicos")
        st.caption(
            "Consulta gratuita al RUES de Confecámaras para autocompletar razón social, "
            "estado de matrícula y tipo de persona. Solo cubre **personas jurídicas y "
            "comerciantes registrados**. La consulta es legalmente válida según Ley "
            "1727 de 2014 y Ley 1581 de 2012 art. 3."
        )
        
        # Configuración
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            usar_rues = st.checkbox("✅ Usar RUES (gratis)", value=True)
        with col_e2:
            apitude_disponible = bool(os.getenv("APITUDE_API_KEY"))
            usar_apitude = st.checkbox(
                f"💵 Usar Apitude {'(disponible)' if apitude_disponible else '(falta APITUDE_API_KEY)'}",
                value=False, disabled=not apitude_disponible,
            )
        
        # Selección de target
        st.markdown("**¿Qué terceros enriquecer?**")
        opciones_target = {
            "solo_revisar": f"Solo los marcados para revisar ({n_terceros['revisar']})",
            "solo_juridicas": f"Solo jurídicas ({n_terceros['juridicas']})",
            "todos": f"Todos ({n_terceros['total']})",
        }
        target = st.radio(
            "Selección",
            options=list(opciones_target.keys()),
            format_func=lambda k: opciones_target[k],
            label_visibility="collapsed",
            key="exo_enriquecer_target",
        )
        
        if st.button("🚀 Enriquecer", type="primary", key="btn_enriquecer"):
            from core.exogena.enriquecimiento import (
                EnriquecedorEnCascada, CacheEnriquecedor,
                RUESEnriquecedor, ApitudeEnriquecedor,
                aplicar_enriquecimiento_a_tercero,
            )
            
            sb = get_supabase()
            
            # Filtrar terceros según selección
            query = sb.table("exogena_terceros").select("*").eq("empresa_id", empresa["id"])
            if target == "solo_revisar":
                query = query.eq("requiere_revision", True)
            elif target == "solo_juridicas":
                query = query.eq("tipo_persona", "juridica")
            
            terceros_db = query.execute().data or []
            
            if not terceros_db:
                st.warning("No hay terceros que enriquecer en esa selección.")
            else:
                # Armar la cascada
                cadena = [CacheEnriquecedor(sb, ttl_dias=90)]
                if usar_rues:
                    cadena.append(RUESEnriquecedor())
                if usar_apitude and apitude_disponible:
                    cadena.append(ApitudeEnriquecedor(api_key=os.getenv("APITUDE_API_KEY")))
                
                enriquecedor = EnriquecedorEnCascada(cadena)
                
                progress = st.progress(0.0, text=f"Enriqueciendo 0 / {len(terceros_db)}...")
                resultados = {"enriquecidos": 0, "no_encontrados": 0, "errores": 0}
                
                for i, t in enumerate(terceros_db):
                    try:
                        datos = enriquecedor.enriquecer(t["nit"])
                        if datos:
                            # Construir el update: solo campos que el enriquecedor devolvió
                            updates = {
                                "enriquecido_desde": datos.fuente,
                                "fecha_enriquecimiento": datos.fecha_consulta.isoformat(),
                            }
                            # Solo sobrescribir si el campo actual está vacío
                            if datos.razon_social and not t.get("razon_social"):
                                updates["razon_social"] = datos.razon_social
                            if datos.tipo_persona and t.get("tipo_persona") != datos.tipo_persona:
                                # RUES afirma con buena confianza
                                updates["tipo_persona"] = datos.tipo_persona
                            if datos.direccion and not t.get("direccion"):
                                updates["direccion"] = datos.direccion
                            if datos.email and not t.get("email"):
                                updates["email"] = datos.email
                            if datos.actividad_ciiu and not t.get("actividad_ciiu"):
                                updates["actividad_ciiu"] = datos.actividad_ciiu

                            sb.table("exogena_terceros").update(updates).eq(
                                "empresa_id", empresa["id"]
                            ).eq("nit", t["nit"]).execute()
                            resultados["enriquecidos"] += 1
                        else:
                            resultados["no_encontrados"] += 1
                    except Exception:
                        resultados["errores"] += 1
                    
                    progress.progress(
                        (i + 1) / len(terceros_db),
                        text=f"Enriqueciendo {i+1} / {len(terceros_db)}... "
                             f"({resultados['enriquecidos']} OK)",
                    )
                
                contar_terceros.clear()
                st.success(
                    f"✅ Enriquecidos: {resultados['enriquecidos']} · "
                    f"No encontrados: {resultados['no_encontrados']} · "
                    f"Errores: {resultados['errores']}"
                )


# ============================================================
# Tab: Balance
# ============================================================

with tab_balance:
    render_proximamente(
        titulo="Carga del balance auxiliar",
        descripcion=(
            "Subir el balance de prueba con movimientos por NIT exportado del software "
            "contable. El sistema cruza cada movimiento con el mapeo nativo + el maestro "
            "de terceros para clasificarlo en formatos DIAN."
        ),
        fases=[
            "Parser para los formatos típicos del balance (cuenta, NIT, débitos, créditos, saldo)",
            "Detección automática de filas resumen vs movimientos por tercero",
            "Validación de cuadre Db = Cr antes de aceptar la carga",
            "Vista previa antes de persistir en BD",
        ],
    )


# ============================================================
# Tab: Clasificar
# ============================================================

with tab_clasificar:
    render_proximamente(
        titulo="Motor de clasificación de movimientos",
        descripcion=(
            "Aplica las 3 capas de mapeo (manual → nativo empresa → PUC genérico) "
            "a cada movimiento del balance. Los movimientos con múltiples reglas "
            "aplicables se marcan como 'requiere revisión' para decisión del usuario."
        ),
        fases=[
            "Procesamiento masivo del balance contra las 3 capas",
            "UI de revisión de ambigüedades con opciones del usuario",
            "Distribución de monto entre formatos cuando aplique",
            "Persistencia de decisiones para reutilizar en próximos años",
        ],
        relacionados=[
            ("Mapeo nativo", "Capa 2 del motor"),
            ("Terceros", "Source de datos demográficos para los formatos"),
        ],
    )


# ============================================================
# Tab: Generar XML
# ============================================================

with tab_generar:
    render_proximamente(
        titulo="Generación de archivos XML",
        descripcion=(
            "Motor validado contra los XSD del prevalidador AG 2025 v3.3.0-26. "
            "Genera archivos `Dmuisca_*.xml` listos para subir a DIAN MUISCA."
        ),
        fases=[
            "Builder de XML por formato usando los XSDs como esquema",
            "Validación XSD en cliente antes de la descarga",
            "Edge Function en Supabase que genera y guarda los XML en bucket",
            "Histórico de envíos por empresa/año",
        ],
    )


# ============================================================
# Tab: Envíos
# ============================================================

with tab_envios:
    render_proximamente(
        titulo="Histórico de envíos a DIAN",
        descripcion=(
            "Cada generación queda registrada con: año gravable, número de envío, "
            "estado, cantidad de registros y valor total reportado por formato."
        ),
        fases=[
            "Tabla `exogena_formatos_generados` ya creada en BD",
            "Storage en bucket `exogena-xml/{empresa_id}/{año}/envio_{n}/`",
            "UI de descarga individual y ZIP completo",
            "Marca de envío aceptado por DIAN con número de radicado",
        ],
    )
