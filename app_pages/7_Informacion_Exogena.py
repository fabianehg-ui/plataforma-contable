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
ROOT = Path(__file__).resolve().parent
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

tab_resumen, tab_mapeo, tab_terceros, tab_balance, tab_clasificar, tab_conciliacion, tab_generar, tab_envios = st.tabs([
    "📊 Resumen",
    "🗂️ Mapeo nativo",
    "👥 Terceros",
    "📥 Balance",
    "⚙️ Clasificar",
    "🔍 Conciliación",
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
    # Editor de Reglas — agregado en sesión del 7 mayo 2026
    # Permite editar Capa 1 (global) y Capa 3 (override por empresa)
    # ============================================================
    try:
        from core.exogena.ui_editor_reglas import render_editor

        # Obtener email del usuario autenticado desde Supabase Auth
        sb_local = get_supabase()
        try:
            _user_resp = sb_local.auth.get_user()
            _user_email = (
                _user_resp.user.email
                if _user_resp and getattr(_user_resp, "user", None)
                else "desconocido"
            )
        except Exception:
            _user_email = "desconocido"

        render_editor(
            sb=sb_local,
            empresa_id=empresa["id"],
            empresa_nombre=empresa.get("razon_social", "Empresa"),
            usuario=_user_email,
            año_gravable=año_gravable,
        )
    except Exception as e:
        st.error(f"⚠️ Error cargando el Editor de Reglas: {e}")
        st.caption("Si persiste, revisar logs de Railway.")


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
# Tab: Balance / Equilibrio
# ============================================================

with tab_balance:
    st.markdown("### 📥 Balance auxiliar por NIT")
    st.caption(
        "Sube el balance de prueba con movimientos por NIT exportado del software "
        "contable. El parser limpia automáticamente: cuentas con guiones, NITs con "
        "puntos y dígito de verificación pegado."
    )

    archivo_balance = st.file_uploader(
        "Archivo de balance (xlsx)",
        type=["xlsx", "xls"],
        key="exo_archivo_balance",
        help="Estructura esperada: Cuenta | Equivalencia | Nombre | NIT | Nombre NIT | Saldo Anterior | Débitos | Créditos | Nuevo Saldo",
    )

    if archivo_balance:
        from core.exogena.cargador_balance import cargar_balance
        try:
            res_bal = cargar_balance(archivo_balance, año_gravable=año_gravable)

            # Mostrar cabecera detectada
            with st.expander("📋 Cabecera detectada", expanded=True):
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    st.text(f"Empresa: {res_bal.cabecera.empresa}")
                    st.text(f"NIT empresa: {res_bal.cabecera.nit_empresa}")
                with col_b2:
                    st.text(f"Período: {res_bal.cabecera.periodo}")
                    st.text(f"Fecha corte: {res_bal.cabecera.fecha_corte}")

                # Validar coincidencia de NIT
                if res_bal.cabecera.nit_empresa and empresa.get('nit'):
                    nit_empresa_limpio = ''.join(c for c in str(empresa['nit']) if c.isdigit())
                    nit_balance = res_bal.cabecera.nit_empresa
                    if nit_balance and nit_balance != nit_empresa_limpio.rstrip('0123456789')[:9] and not nit_empresa_limpio.startswith(nit_balance):
                        if not (nit_empresa_limpio.startswith(nit_balance) or nit_balance.startswith(nit_empresa_limpio[:9])):
                            st.warning(
                                f"⚠️ El NIT del balance ({nit_balance}) parece distinto al de la empresa activa "
                                f"({nit_empresa_limpio}). Verifica que estás cargando el archivo correcto."
                            )

            # Resumen
            col_a, col_b, col_c, col_d = st.columns(4)
            with col_a:
                st.metric("Movimientos", f"{len(res_bal.movimientos):,}")
            with col_b:
                st.metric("NITs únicos", f"{len(res_bal.nits_unicos):,}")
            with col_c:
                st.metric("Cuentas únicas", f"{len(res_bal.cuentas_unicas):,}")
            with col_d:
                st.metric("Totalizadores", f"{len(res_bal.totalizadores):,}")

            if res_bal.errores:
                st.error(f"❌ {len(res_bal.errores)} errores:")
                for e in res_bal.errores[:10]:
                    st.text(f"  - {e}")

            if res_bal.advertencias:
                with st.expander(f"⚠️ {len(res_bal.advertencias)} advertencias"):
                    for a in res_bal.advertencias:
                        st.text(a)

            # Vista previa
            if res_bal.movimientos:
                st.markdown("**Vista previa de movimientos (primeros 50):**")
                df_mov = pd.DataFrame([{
                    "Cuenta": m.codigo_cuenta,
                    "NIT": m.nit,
                    "Tercero": m.nombre_tercero,
                    "Saldo Anterior": float(m.saldo_anterior),
                    "Débitos": float(m.debitos),
                    "Créditos": float(m.creditos),
                    "Saldo Final": float(m.saldo_final),
                } for m in res_bal.movimientos[:50]])
                st.dataframe(df_mov, use_container_width=True, hide_index=True, height=400)

            # Botón guardar
            require_rol(["admin", "operador"])
            if res_bal.movimientos and st.button(
                "💾 Guardar balance en la base de datos",
                type="primary",
                key="btn_guardar_balance",
            ):
                sb = get_supabase()
                # 1. Crear o usar periodo
                periodo = crear_periodo_si_no_existe(empresa["id"], año_gravable)

                # ============================================================
                # 2. Limpieza en cascada del periodo
                #    Importante: borrar las tablas dependientes ANTES del balance
                #    para evitar referencias colgadas. Orden:
                #      a) Movimientos clasificados (apuntan a balance_id)
                #      b) Decisiones manuales pendientes (si las hubiera)
                #      c) Conciliaciones (PILA, GMF) si existen
                #      d) Por último, exogena_balance
                # ============================================================
                try:
                    # Contar lo que vamos a borrar para feedback
                    n_balance_old = sb.table("exogena_balance").select(
                        "id", count="exact"
                    ).eq("periodo_id", periodo["id"]).execute().count or 0

                    n_movs_old = 0
                    try:
                        n_movs_old = sb.table("exogena_movimientos_clasificados").select(
                            "id", count="exact"
                        ).eq("periodo_id", periodo["id"]).execute().count or 0
                    except Exception:
                        # Si la tabla no existe o no tiene esa columna, ignorar
                        pass

                    # 2a. Movimientos clasificados (clasificación se reinicia)
                    try:
                        sb.table("exogena_movimientos_clasificados").delete().eq(
                            "periodo_id", periodo["id"]
                        ).execute()
                    except Exception as e_cls:
                        st.warning(f"⚠️ No se pudieron borrar movimientos clasificados: {e_cls}")

                    # 2b. Conciliaciones PILA/GMF si existen
                    for tabla_dep in ["exogena_conciliacion_pila",
                                      "exogena_conciliacion_gmf",
                                      "exogena_conciliacion_ajustes"]:
                        try:
                            sb.table(tabla_dep).delete().eq(
                                "periodo_id", periodo["id"]
                            ).execute()
                        except Exception:
                            pass  # Tabla puede no existir, OK

                    # 2c. Balance previo
                    sb.table("exogena_balance").delete().eq(
                        "periodo_id", periodo["id"]
                    ).execute()

                    if n_balance_old > 0 or n_movs_old > 0:
                        st.info(
                            f"🧹 Limpieza previa: {n_balance_old:,} filas de balance "
                            f"y {n_movs_old:,} movimientos clasificados borrados."
                        )

                except Exception as e_clean:
                    st.error(f"❌ Error en limpieza previa: {e_clean}")
                    st.stop()

                # ============================================================
                # 3. Insertar movimientos en lotes — con manejo de errores
                # ============================================================
                LOTE = 200
                registros = [{
                    "periodo_id": periodo["id"],
                    "codigo_cuenta": m.codigo_cuenta,
                    "nombre_cuenta": m.nombre_cuenta,
                    "nit": m.nit,
                    "nombre_tercero": m.nombre_tercero,
                    "saldo_anterior": float(m.saldo_anterior),
                    "debitos": float(m.debitos),
                    "creditos": float(m.creditos),
                    "saldo_final": float(m.saldo_final),
                    "es_totalizador": False,
                    "fila_origen": m.fila_origen,
                } for m in res_bal.movimientos]

                # También guardar totalizadores de nivel alto (1, 2 dígitos) para validación
                registros += [{
                    "periodo_id": periodo["id"],
                    "codigo_cuenta": t.codigo_cuenta,
                    "nombre_cuenta": t.nombre_cuenta,
                    "nit": None,
                    "nombre_tercero": None,
                    "saldo_anterior": float(t.saldo_anterior),
                    "debitos": float(t.debitos),
                    "creditos": float(t.creditos),
                    "saldo_final": float(t.saldo_final),
                    "es_totalizador": True,
                    "fila_origen": t.fila_origen,
                } for t in res_bal.totalizadores if t.nivel <= 4]

                # Insertar con manejo de errores por lote
                total_lotes = (len(registros) + LOTE - 1) // LOTE
                lotes_ok = 0
                errores_insert = []
                progress = st.progress(0, text="Guardando balance...")

                for i in range(0, len(registros), LOTE):
                    try:
                        sb.table("exogena_balance").insert(registros[i:i+LOTE]).execute()
                        lotes_ok += 1
                    except Exception as e_ins:
                        errores_insert.append(f"Lote {i//LOTE + 1}: {str(e_ins)[:200]}")
                    progress.progress(
                        min(1.0, (i + LOTE) / max(1, len(registros))),
                        text=f"Guardando lote {lotes_ok}/{total_lotes}...",
                    )

                progress.empty()
                obtener_periodo.clear()

                # ============================================================
                # 4. Feedback al usuario — claro y verificable
                # ============================================================
                # Verificar lo que QUEDÓ realmente en BD (la prueba definitiva)
                try:
                    n_real_bd = sb.table("exogena_balance").select(
                        "id", count="exact"
                    ).eq("periodo_id", periodo["id"]).execute().count or 0
                except Exception:
                    n_real_bd = -1  # No se pudo verificar

                obtener_periodo.clear()

                if errores_insert:
                    st.error(
                        f"❌ Hubo errores al guardar {len(errores_insert)} de {total_lotes} lotes."
                    )
                    st.caption(
                        f"Se guardaron {len(registros) - len(errores_insert)*LOTE} de "
                        f"{len(registros)} registros previstos. "
                        f"En BD quedaron {n_real_bd:,} filas."
                    )
                    with st.expander(f"Ver {len(errores_insert)} errores"):
                        for err in errores_insert[:20]:
                            st.text(err)
                elif n_real_bd == 0:
                    # Lotes_ok dice que sí, pero BD dice que no — error silencioso
                    st.error(
                        "❌ Algo raro pasó: la BD no recibió ningún registro aunque "
                        "los lotes parecían procesarse. Posible RLS bloqueando inserts. "
                        "Revisar permisos en Supabase."
                    )
                elif n_real_bd != len(registros):
                    # Hay desfase — guardó parcial
                    st.warning(
                        f"⚠️ Guardado parcial: se intentaron insertar {len(registros):,} filas "
                        f"pero en BD quedaron {n_real_bd:,}. Diferencia: {len(registros) - n_real_bd:,}."
                    )
                else:
                    n_movs = len(res_bal.movimientos)
                    n_tot = sum(1 for r in registros if r['es_totalizador'])
                    st.success(
                        f"✅ Balance guardado correctamente: "
                        f"{n_movs:,} movimientos + {n_tot:,} totalizadores "
                        f"({n_real_bd:,} filas en BD)."
                    )
                    if n_balance_old > 0 or n_movs_old > 0:
                        st.caption(
                            f"♻️ Reemplazó {n_balance_old:,} filas de balance anterior "
                            f"y {n_movs_old:,} movimientos clasificados (clasificación reiniciada)."
                        )
                # NOTA: NO hacer st.rerun() aquí — borraría el mensaje verde.
                # El usuario verá el resultado y puede navegar a otro tab cuando quiera.

        except Exception as e:
            st.error(f"❌ Error procesando balance: {e}")
            st.exception(e)


# ============================================================
# Tab: Clasificar
# ============================================================

with tab_clasificar:
    st.markdown("### ⚙️ Clasificación de movimientos")
    st.caption(
        "Aplica las 3 capas de mapeo a los movimientos del balance: "
        "**Capa 3** (manual por NIT) → **Capa 2** (mapeo nativo de la empresa) → "
        "**Capa 1** (PUC genérico DIAN). Cuentas no clasificadas requieren asignación manual."
    )

    sb = get_supabase()

    # Verificar prerequisitos
    periodo_actual = obtener_periodo(empresa["id"], año_gravable)
    
    if not periodo_actual:
        st.warning("⚠️ Primero debes cargar el balance auxiliar en el tab anterior.")
    else:
        # Contar movimientos en BD
        try:
            n_movs = sb.table("exogena_balance").select("id", count="exact").eq(
                "periodo_id", periodo_actual["id"]
            ).eq("es_totalizador", False).execute().count or 0
        except Exception:
            n_movs = 0

        if n_movs == 0:
            st.warning("⚠️ No hay movimientos cargados para este periodo. Carga el balance primero.")
        else:
            col_h1, col_h2, col_h3 = st.columns([2, 1, 1])
            with col_h1:
                st.markdown(f"**Movimientos disponibles:** {n_movs:,}")
            with col_h2:
                ejecutar = st.button(
                    "▶️ Ejecutar clasificación",
                    type="primary",
                    use_container_width=True,
                )
            with col_h3:
                if st.button("🔄 Recargar dictamen", use_container_width=True):
                    if "exo_dictamen" in st.session_state:
                        del st.session_state["exo_dictamen"]
                    st.rerun()

            # ============================================================
            # Ejecutar clasificación cuando se da click
            # ============================================================
            if ejecutar:
                with st.spinner("Clasificando movimientos..."):
                    from core.exogena.motor_clasificacion import (
                        MotorClasificacion, Movimiento,
                        ReglaCapa1, ReglaCapa2, ReglaCapa3
                    )

                    # 1. Cargar reglas de las 3 capas desde BD
                    # Capa 1: PUC genérico (compartido todas las empresas)
                    capa1_data = sb.table("exogena_puc_generico").select("*").eq(
                        "año_gravable", año_gravable
                    ).execute().data or []
                    reglas_c1 = [
                        ReglaCapa1(
                            codigo_cuenta=r["codigo_cuenta"],
                            formato_dian=r["formato_dian"],
                            concepto_dian=r.get("concepto_dian"),
                            nombre_cuenta=r.get("nombre_cuenta", ""),
                        ) for r in capa1_data
                    ]

                    # Capa 2: Mapeo nativo de la empresa
                    capa2_data = sb.table("exogena_mapeo_empresa").select("*").eq(
                        "empresa_id", empresa["id"]
                    ).eq("año_gravable", año_gravable).execute().data or []
                    reglas_c2 = [
                        ReglaCapa2(
                            formato_dian=r["formato_dian"],
                            concepto_dian=r["concepto_dian"],
                            cuenta_inicial=r["cuenta_inicial"],
                            cuenta_final=r["cuenta_final"],
                            descripcion_concepto=r.get("descripcion_concepto", ""),
                            id=r.get("id"),
                            fila_origen=r.get("fila_origen", 0),
                        ) for r in capa2_data
                    ]

                    # Capa 3: Mapeo manual (overrides por cuenta+NIT)
                    capa3_data = sb.table("exogena_mapeo_manual").select("*").eq(
                        "empresa_id", empresa["id"]
                    ).eq("año_gravable", año_gravable).execute().data or []
                    reglas_c3 = [
                        ReglaCapa3(
                            codigo_cuenta=r["codigo_cuenta"],
                            nit=r.get("nit"),
                            formato_dian=r.get("formato_dian"),
                            concepto_dian=r.get("concepto_dian"),
                            nota=r.get("nota", ""),
                            id=r.get("id"),
                            excluir=bool(r.get("excluir", False)),
                            motivo_exclusion=r.get("motivo_exclusion"),
                        ) for r in capa3_data
                    ]

                    # 2. Cargar movimientos del balance
                    movs_data = sb.table("exogena_balance").select("*").eq(
                        "periodo_id", periodo_actual["id"]
                    ).eq("es_totalizador", False).execute().data or []
                    movimientos = [
                        Movimiento(
                            codigo_cuenta=m["codigo_cuenta"],
                            nit=m.get("nit"),
                            debitos=float(m.get("debitos", 0) or 0),
                            creditos=float(m.get("creditos", 0) or 0),
                            saldo_final=float(m.get("saldo_final", 0) or 0),
                            nombre_cuenta=m.get("nombre_cuenta", ""),
                            nombre_tercero=m.get("nombre_tercero", ""),
                            balance_id=m.get("id"),
                        ) for m in movs_data
                    ]

                    # 3. Ejecutar el motor
                    motor = MotorClasificacion(reglas_c1, reglas_c2, reglas_c3)
                    resultado = motor.clasificar_balance(movimientos)

                    # 4. Calcular estadísticas para el dictamen
                    n_total = len(movimientos)
                    n_huerf = len(resultado.sin_resolver)
                    # Los "clasificados" son los que NO terminaron como sin_resolver
                    movs_clasif = [m for m in resultado.movimientos
                                   if m.capa_resolucion != 'sin_resolver']
                    n_clasif = len(movs_clasif)
                    n_revisar = sum(1 for m in movs_clasif if m.requiere_revision)

                    # Distribución por capa
                    por_capa = {}
                    for mc in movs_clasif:
                        por_capa[mc.capa_resolucion] = por_capa.get(mc.capa_resolucion, 0) + 1

                    # Distribución por formato (sin contar exclusiones)
                    por_formato = {}
                    for mc in movs_clasif:
                        # Exclusiones manuales (capa 3 con excluir=TRUE) y "999999" legacy
                        # no se cuentan como un formato; van en su propia métrica.
                        if mc.capa_resolucion == 'excluido_manual':
                            continue
                        if mc.formato_dian == '999999':
                            continue
                        if mc.formato_dian:
                            por_formato.setdefault(mc.formato_dian, {"movs": 0, "valor": 0.0})
                            por_formato[mc.formato_dian]["movs"] += 1
                            por_formato[mc.formato_dian]["valor"] += abs(mc.valor)

                    # Cuentas huérfanas agrupadas
                    cuentas_huerfanas = {}
                    for m in resultado.sin_resolver:
                        c = m.codigo_cuenta
                        if c not in cuentas_huerfanas:
                            cuentas_huerfanas[c] = {
                                "cuenta": c,
                                "nombre_cuenta": m.nombre_cuenta,
                                "movs": 0,
                                "saldo_total": 0.0,
                                "ejemplos_nits": [],
                            }
                        cuentas_huerfanas[c]["movs"] += 1
                        cuentas_huerfanas[c]["saldo_total"] += abs(m.debitos) + abs(m.creditos)
                        if m.nit and len(cuentas_huerfanas[c]["ejemplos_nits"]) < 3:
                            cuentas_huerfanas[c]["ejemplos_nits"].append(
                                f"{m.nit} {m.nombre_tercero[:25]}"
                            )

                    # Guardar en session_state para que persista entre interacciones
                    st.session_state["exo_dictamen"] = {
                        "n_total": n_total,
                        "n_clasif": n_clasif,
                        "n_huerf": n_huerf,
                        "n_revisar": n_revisar,
                        "por_capa": por_capa,
                        "por_formato": por_formato,
                        "cuentas_huerfanas": list(cuentas_huerfanas.values()),
                    }

            # ============================================================
            # Mostrar dictamen si existe
            # ============================================================
            if "exo_dictamen" in st.session_state:
                d = st.session_state["exo_dictamen"]

                st.markdown("---")
                st.markdown("### 📊 Dictamen de clasificación")

                # Métricas principales
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    st.metric("Total movimientos", f"{d['n_total']:,}")
                with col_m2:
                    pct = (d["n_clasif"] / d["n_total"] * 100) if d["n_total"] else 0
                    st.metric("Clasificados", f"{d['n_clasif']:,}", f"{pct:.1f}%")
                with col_m3:
                    pct_h = (d["n_huerf"] / d["n_total"] * 100) if d["n_total"] else 0
                    st.metric("⚠️ Huérfanos", f"{d['n_huerf']:,}", f"{pct_h:.1f}%")
                with col_m4:
                    st.metric("Por revisar", f"{d['n_revisar']:,}")

                # Distribución por capa
                with st.expander("📚 Distribución por capa que clasificó", expanded=False):
                    capa_labels = {
                        "mapeo_manual": "🥇 Capa 3 — Manual (override por NIT)",
                        "mapeo_empresa": "🥈 Capa 2 — Mapeo nativo de la empresa",
                        "puc_generico": "🥉 Capa 1 — PUC genérico DIAN",
                    }
                    for capa, label in capa_labels.items():
                        n = d["por_capa"].get(capa, 0)
                        if n:
                            st.write(f"- **{label}**: {n:,} movs")

                # Distribución por formato
                if d["por_formato"]:
                    with st.expander("📊 Distribución por formato DIAN", expanded=True):
                        df_fmt = pd.DataFrame([
                            {
                                "Formato": fmt,
                                "Movimientos": info["movs"],
                                "Valor total": info["valor"],
                            }
                            for fmt, info in sorted(d["por_formato"].items())
                        ])
                        st.dataframe(df_fmt, use_container_width=True, hide_index=True)

                # ============================================================
                # Cuentas huérfanas: tabla interactiva para asignación manual
                # ============================================================
                if d["cuentas_huerfanas"]:
                    st.markdown("---")
                    st.markdown(f"### 🚨 {len(d['cuentas_huerfanas'])} cuentas sin clasificar")
                    st.caption(
                        "Estas cuentas tienen movimientos pero ninguna regla de las 3 capas las cubre. "
                        "Asigna **formato + concepto** y guarda para que el sistema las use el próximo año."
                    )

                    # Cargar opciones desde catálogos DIAN
                    # Robusto: prueba primero con año_gravable, si falla intenta sin filtro
                    def _cargar_catalogo(tabla, columnas):
                        """Carga un catálogo intentando con año_gravable, anio_gravable, o sin filtro."""
                        try:
                            return sb.table(tabla).select(columnas).eq(
                                "año_gravable", año_gravable
                            ).execute().data or []
                        except Exception:
                            try:
                                return sb.table(tabla).select(columnas).eq(
                                    "anio_gravable", año_gravable
                                ).execute().data or []
                            except Exception:
                                try:
                                    return sb.table(tabla).select(columnas).execute().data or []
                                except Exception as e:
                                    st.warning(f"No se pudo cargar {tabla}: {e}")
                                    return []

                    formatos_dian = _cargar_catalogo("exogena_cat_formatos", "codigo,nombre")
                    formatos_options = {
                        f["codigo"]: f"{f['codigo']} - {f['nombre'][:40]}"
                        for f in sorted(formatos_dian, key=lambda x: x["codigo"])
                    }
                    formatos_options["__ignorar__"] = "❌ No aplica (ignorar)"

                    # Cargar relación concepto ↔ formato (para filtrar dropdowns)
                    try:
                        conceptos_rel = sb.table("exogena_cat_concepto_formato").select(
                            "formato_dian,codigo_concepto,descripcion"
                        ).eq("año_gravable", año_gravable).execute().data or []
                    except Exception:
                        conceptos_rel = []
                    # Agrupar por formato
                    conceptos_por_formato = {}
                    for c in conceptos_rel:
                        conceptos_por_formato.setdefault(c["formato_dian"], []).append(c)
                    for fmt in conceptos_por_formato:
                        conceptos_por_formato[fmt].sort(key=lambda x: x["codigo_concepto"])

                    # Ordenar cuentas huérfanas por valor descendente (más impactantes primero)
                    cuentas_orden = sorted(
                        d["cuentas_huerfanas"],
                        key=lambda x: x["saldo_total"],
                        reverse=True,
                    )

                    # Mostrar las primeras 20 (limit para no saturar UI)
                    LIMIT = 20
                    if len(cuentas_orden) > LIMIT:
                        st.info(f"Mostrando las {LIMIT} cuentas con mayor valor. "
                                f"Hay {len(cuentas_orden) - LIMIT} adicionales.")

                    require_rol(["admin", "operador"])

                    # Inicializar storage de decisiones en session_state
                    if "exo_decisiones" not in st.session_state:
                        st.session_state["exo_decisiones"] = {}

                    # Reset si se pidió
                    if st.button("🔄 Limpiar selecciones", key="reset_decisiones"):
                        st.session_state["exo_decisiones"] = {}
                        st.rerun()

                    # Loop de cuentas con dropdowns sin botón individual
                    for idx, ch in enumerate(cuentas_orden[:LIMIT]):
                        with st.container():
                            cols = st.columns([1.5, 3, 1.2, 1.5, 2, 2])
                            with cols[0]:
                                st.text(ch["cuenta"])
                            with cols[1]:
                                st.text(ch["nombre_cuenta"][:35])
                            with cols[2]:
                                st.text(f"{ch['movs']} movs")
                            with cols[3]:
                                st.text(f"${ch['saldo_total']:,.0f}")
                            with cols[4]:
                                fmt_key = f"fmt_{ch['cuenta']}_{idx}"
                                # Opción "(sin asignar)" para no obligar
                                fmt_opts = {None: "— Sin asignar —", "999999": "❌ No aplica (ignorar)"}
                                fmt_opts.update(formatos_options)
                                # Quitar el __ignorar__ duplicado de formatos_options
                                fmt_opts.pop("__ignorar__", None)
                                fmt = st.selectbox(
                                    "Formato",
                                    options=list(fmt_opts.keys()),
                                    format_func=lambda k: fmt_opts.get(k, "— Sin asignar —"),
                                    key=fmt_key,
                                    label_visibility="collapsed",
                                )
                            with cols[5]:
                                cpt_key = f"cpt_{ch['cuenta']}_{idx}"
                                if fmt and fmt not in (None, "999999"):
                                    # Cargar conceptos solo del formato seleccionado
                                    conceptos_disp = conceptos_por_formato.get(fmt, [])
                                    cpt_options = {
                                        c["codigo_concepto"]: f"{c['codigo_concepto']} - {c['descripcion'][:40]}"
                                        for c in conceptos_disp
                                    }
                                    if not cpt_options:
                                        cpt_options = {None: "(sin conceptos para este formato)"}
                                    cpt = st.selectbox(
                                        "Concepto",
                                        options=list(cpt_options.keys()),
                                        format_func=lambda k: cpt_options.get(k, "(sin concepto)"),
                                        key=cpt_key,
                                        label_visibility="collapsed",
                                    )
                                else:
                                    cpt = None
                                    st.text("—")

                            # Guardar selección actual en session_state
                            if fmt is not None:
                                st.session_state["exo_decisiones"][ch["cuenta"]] = {
                                    "cuenta": ch["cuenta"],
                                    "formato": fmt,
                                    "concepto": cpt,
                                }
                            elif ch["cuenta"] in st.session_state["exo_decisiones"]:
                                del st.session_state["exo_decisiones"][ch["cuenta"]]

                            # Mostrar ejemplos de NITs
                            if ch["ejemplos_nits"]:
                                st.caption(
                                    "  Ejemplos: " + " | ".join(ch["ejemplos_nits"][:3])
                                )
                            st.markdown("")  # separador

                    # Botón unico "Aplicar TODAS las decisiones" al final
                    n_decisiones = len(st.session_state.get("exo_decisiones", {}))
                    if n_decisiones > 0:
                        st.markdown("---")
                        col_btn1, col_btn2 = st.columns([1, 3])
                        with col_btn1:
                            aplicar_todo = st.button(
                                f"💾 Guardar {n_decisiones} decisiones",
                                type="primary",
                                use_container_width=True,
                                key="btn_aplicar_todo",
                            )
                        with col_btn2:
                            st.caption(
                                f"Se guardarán {n_decisiones} reglas en la base de datos. "
                                "Las cuentas marcadas como 'Sin asignar' no se persistirán."
                            )

                        if aplicar_todo:
                            decisiones = list(st.session_state["exo_decisiones"].values())
                            errores_guardado = []
                            for dec in decisiones:
                                try:
                                    # Eliminar regla previa si existe
                                    sb.table("exogena_mapeo_manual").delete().eq(
                                        "empresa_id", empresa["id"]
                                    ).eq("año_gravable", año_gravable).eq(
                                        "codigo_cuenta", dec["cuenta"]
                                    ).is_("nit", "null").execute()
                                    # Construir el registro: si "999999" ⇒ exclusión con convención nueva
                                    es_excluida = dec["formato"] == "999999"
                                    motivo = (
                                        "🚫 Marcada como 'No aplica' desde dictamen"
                                        if es_excluida else None
                                    )
                                    sb.table("exogena_mapeo_manual").insert({
                                        "empresa_id": empresa["id"],
                                        "año_gravable": año_gravable,
                                        "codigo_cuenta": dec["cuenta"],
                                        "nit": None,
                                        "formato_dian": None if es_excluida else dec["formato"],
                                        "concepto_dian": None if es_excluida else dec["concepto"],
                                        "excluir": es_excluida,
                                        "motivo_exclusion": motivo,
                                        "nota": motivo if es_excluida else "Asignado manualmente desde dictamen",
                                    }).execute()
                                except Exception as e:
                                    errores_guardado.append(f"{dec['cuenta']}: {str(e)[:80]}")

                            if errores_guardado:
                                st.error(f"❌ {len(errores_guardado)} errores al guardar:")
                                for e in errores_guardado[:5]:
                                    st.text(e)
                            else:
                                st.success(f"✅ {len(decisiones)} decisiones guardadas. Re-ejecuta clasificación para ver el nuevo dictamen.")
                                st.session_state["exo_decisiones"] = {}
                                if "exo_dictamen" in st.session_state:
                                    del st.session_state["exo_dictamen"]
                                st.rerun()

                else:
                    if d["n_clasif"] > 0:
                        st.success("🎉 **¡Todas las cuentas están clasificadas!** Puedes pasar a generar XMLs.")


# ============================================================
# Tab: Conciliación
# ============================================================

with tab_conciliacion:
    st.markdown("### 🔍 Conciliación tributaria")
    st.caption(
        "Cruza los datos del balance con documentos externos (PILA, certificados bancarios) "
        "para determinar valores deducibles vs no deducibles antes de generar los formatos."
    )

    sb = get_supabase()
    periodo_actual = obtener_periodo(empresa["id"], año_gravable)

    if not periodo_actual:
        st.warning("⚠️ Primero debes cargar el balance auxiliar.")
    else:
        # ============================================================
        # 1. DICTAMEN PREVIO
        # ============================================================
        st.markdown("---")
        st.markdown("#### 📊 Dictamen: cuentas que requieren conciliación")

        col_d1, col_d2 = st.columns([2, 1])
        with col_d2:
            ejecutar_dictamen = st.button(
                "🔍 Generar dictamen",
                type="primary",
                use_container_width=True,
                key="btn_dictamen_concilia",
            )

        if ejecutar_dictamen:
            with st.spinner("Analizando movimientos..."):
                from core.exogena.conciliacion import construir_dictamen
                from core.exogena.motor_clasificacion import (
                    MotorClasificacion, Movimiento,
                    ReglaCapa1, ReglaCapa2, ReglaCapa3
                )

                # Cargar reglas
                capa1_data = sb.table("exogena_puc_generico").select("*").eq(
                    "año_gravable", año_gravable
                ).execute().data or []
                capa2_data = sb.table("exogena_mapeo_empresa").select("*").eq(
                    "empresa_id", empresa["id"]
                ).eq("año_gravable", año_gravable).execute().data or []
                capa3_data = sb.table("exogena_mapeo_manual").select("*").eq(
                    "empresa_id", empresa["id"]
                ).eq("año_gravable", año_gravable).execute().data or []

                reglas_c1 = [ReglaCapa1(codigo_cuenta=r["codigo_cuenta"],
                    formato_dian=r["formato_dian"], concepto_dian=r.get("concepto_dian"),
                    nombre_cuenta=r.get("nombre_cuenta", "")) for r in capa1_data]
                reglas_c2 = [ReglaCapa2(formato_dian=r["formato_dian"],
                    concepto_dian=r["concepto_dian"], cuenta_inicial=r["cuenta_inicial"],
                    cuenta_final=r["cuenta_final"]) for r in capa2_data]
                reglas_c3 = [ReglaCapa3(codigo_cuenta=r["codigo_cuenta"],
                    nit=r.get("nit"), formato_dian=r.get("formato_dian"),
                    concepto_dian=r.get("concepto_dian"),
                    excluir=bool(r.get("excluir", False)),
                    motivo_exclusion=r.get("motivo_exclusion")) for r in capa3_data]

                # Cargar movimientos clasificados
                movs_data = sb.table("exogena_balance").select("*").eq(
                    "periodo_id", periodo_actual["id"]
                ).eq("es_totalizador", False).execute().data or []
                
                movimientos = [Movimiento(
                    codigo_cuenta=m["codigo_cuenta"], nit=m.get("nit"),
                    debitos=float(m.get("debitos", 0) or 0),
                    creditos=float(m.get("creditos", 0) or 0),
                    saldo_final=float(m.get("saldo_final", 0) or 0),
                    nombre_cuenta=m.get("nombre_cuenta", ""),
                    nombre_tercero=m.get("nombre_tercero", ""),
                ) for m in movs_data]

                motor = MotorClasificacion(reglas_c1, reglas_c2, reglas_c3)
                resultado = motor.clasificar_balance(movimientos)

                # Convertir a lista de dicts para el detector
                movs_dict = []
                for mc in resultado.movimientos:
                    if mc.capa_resolucion == 'sin_resolver':
                        continue
                    # Buscar el movimiento original para obtener nombres
                    mov_orig = next((m for m in movimientos
                                     if m.codigo_cuenta == mc.codigo_cuenta and m.nit == mc.nit),
                                    None)
                    movs_dict.append({
                        'codigo_cuenta': mc.codigo_cuenta,
                        'nombre_cuenta': mov_orig.nombre_cuenta if mov_orig else '',
                        'nit': mc.nit,
                        'nombre_tercero': mov_orig.nombre_tercero if mov_orig else '',
                        'debitos': mov_orig.debitos if mov_orig else 0,
                        'creditos': mov_orig.creditos if mov_orig else 0,
                        'saldo_final': mov_orig.saldo_final if mov_orig else 0,
                        'formato_dian': mc.formato_dian,
                        'concepto_dian': mc.concepto_dian,
                    })

                dictamen = construir_dictamen(movs_dict)
                st.session_state["exo_dictamen_concilia"] = dictamen

        # Mostrar dictamen si existe
        if "exo_dictamen_concilia" in st.session_state:
            dc = st.session_state["exo_dictamen_concilia"]

            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("Cuentas Seguridad Social",
                          len(dc.cuentas_seguridad_social),
                          f"${dc.total_seguridad_social:,.0f}")
            with col_m2:
                st.metric("Cuentas GMF",
                          len(dc.cuentas_gmf),
                          f"${dc.total_gmf:,.0f}")
            with col_m3:
                st.metric("Total a conciliar",
                          f"{len(dc.cuentas_seguridad_social) + len(dc.cuentas_gmf)}",
                          f"${dc.total_general:,.0f}")

            # Tabla seguridad social
            if dc.cuentas_seguridad_social:
                st.markdown("**🏥 Cuentas de Seguridad Social** (separar empleador vs trabajador)")
                df_ss = pd.DataFrame([{
                    "Cuenta": c.codigo_cuenta,
                    "Nombre": c.nombre_cuenta,
                    "Concepto": f"{c.concepto_sugerido} - {c.descripcion_concepto}",
                    "Movs": c.cantidad_movimientos,
                    "NITs": c.cantidad_nits,
                    "Saldo": float(c.saldo_total),
                    "Separar Emp/Trab": "Sí" if c.requiere_separacion_emp_trab else "No (100% empleador)",
                } for c in dc.cuentas_seguridad_social])
                st.dataframe(df_ss, use_container_width=True, hide_index=True)

            # Tabla GMF
            if dc.cuentas_gmf:
                st.markdown("**🏦 Cuentas de GMF** (50% deducible)")
                df_gmf = pd.DataFrame([{
                    "Cuenta": c.codigo_cuenta,
                    "Nombre": c.nombre_cuenta,
                    "Movs": c.cantidad_movimientos,
                    "Saldo Total": float(c.saldo_total),
                    "Deducible (50%)": float(c.saldo_total) * 0.5,
                    "No Deducible (50%)": float(c.saldo_total) * 0.5,
                } for c in dc.cuentas_gmf])
                st.dataframe(df_gmf, use_container_width=True, hide_index=True)

            # ============================================================
            # 2. DESCARGAR EXCEL EDITABLE
            # ============================================================
            st.markdown("---")
            st.markdown("#### 📥 Excel editable para conciliación")
            st.caption(
                "Descarga este Excel, complete los aportes empleador/trabajador y los certificados "
                "GMF, y vuelve a subirlo al sistema."
            )

            from core.exogena.excel_conciliacion import generar_excel_conciliacion
            excel_buf = generar_excel_conciliacion(
                dc,
                {'razon_social': empresa.get('razon_social', ''), 'nit': empresa.get('nit', '')},
                año_gravable,
            )

            st.download_button(
                "📥 Descargar Excel de conciliación",
                data=excel_buf.getvalue(),
                file_name=f"conciliacion_{empresa.get('nit','empresa')}_{año_gravable}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=False,
            )

            # ============================================================
            # 3. CARGAR ARCHIVO PILA
            # ============================================================
            st.markdown("---")
            st.markdown("#### 📁 Cargar archivo PILA")
            st.caption(
                "Sube el archivo de la PILA (planilla de seguridad social) para que el sistema "
                "extraiga automáticamente el aporte empleador vs trabajador."
            )

            archivo_pila = st.file_uploader(
                "Archivo PILA (xlsx)",
                type=["xlsx"],
                key="exo_archivo_pila",
            )

            if archivo_pila:
                from core.exogena.cargador_pila import cargar_pila
                try:
                    res_pila = cargar_pila(archivo_pila)

                    if res_pila.errores:
                        for e in res_pila.errores:
                            st.error(f"❌ {e}")

                    if res_pila.advertencias:
                        with st.expander(f"⚠️ {len(res_pila.advertencias)} advertencias"):
                            for a in res_pila.advertencias:
                                st.text(a)

                    if res_pila.registros:
                        st.success(f"✅ {len(res_pila.registros)} registros parseados")
                        
                        # Consolidado
                        cons = res_pila.consolidado_por_concepto()
                        df_pila = pd.DataFrame([{
                            "Tipo": k.upper(),
                            "Concepto DIAN": v["concepto_dian"] or "—",
                            "Aporte Empleador": float(v["aporte_empleador"]),
                            "Aporte Trabajador": float(v["aporte_trabajador"]),
                            "Total": float(v["aporte_total"]),
                            "Filas": v["cantidad_filas"],
                        } for k, v in cons.items()])
                        st.dataframe(df_pila, use_container_width=True, hide_index=True)

                        require_rol(["admin", "operador"])
                        if st.button("💾 Guardar PILA en base de datos",
                                      type="primary", key="btn_save_pila"):
                            # Limpiar PILA previa
                            sb.table("exogena_conciliacion_pila").delete().eq(
                                "periodo_id", periodo_actual["id"]
                            ).execute()

                            # Insertar registros
                            registros = [{
                                "periodo_id": periodo_actual["id"],
                                "nro_planilla": r.nro_planilla,
                                "periodo_pago": r.periodo_pago,
                                "tipo_aporte": r.tipo_aporte,
                                "concepto_dian": r.concepto_dian,
                                "aporte_empleador": float(r.aporte_empleador),
                                "aporte_trabajador": float(r.aporte_trabajador),
                                "aporte_total": float(r.aporte_total),
                                "fila_origen": r.fila_origen,
                            } for r in res_pila.registros]
                            
                            sb.table("exogena_conciliacion_pila").insert(registros).execute()
                            st.success(f"✅ {len(registros)} registros PILA guardados")
                            st.rerun()
                except Exception as e:
                    st.error(f"❌ Error procesando PILA: {e}")
                    st.exception(e)

            # ============================================================
            # 4. CARGAR/INGRESAR GMF
            # ============================================================
            st.markdown("---")
            st.markdown("#### 🏦 GMF por banco")
            st.caption("Ingresa el total de GMF certificado por cada banco. El 50% es deducible.")

            # Mostrar GMF ya guardados
            try:
                gmf_existentes = sb.table("exogena_conciliacion_gmf").select("*").eq(
                    "periodo_id", periodo_actual["id"]
                ).execute().data or []
            except Exception:
                gmf_existentes = []

            if gmf_existentes:
                st.markdown("**GMF ya cargados:**")
                df_gmf_e = pd.DataFrame([{
                    "Banco": g.get("banco_nombre", ""),
                    "NIT": g.get("banco_nit", ""),
                    "GMF Certificado": float(g.get("gmf_total_certificado", 0)),
                    "Deducible 50%": float(g.get("gmf_total_certificado", 0)) * 0.5,
                    "Certificado": g.get("nro_certificado", ""),
                } for g in gmf_existentes])
                st.dataframe(df_gmf_e, use_container_width=True, hide_index=True)

            # Formulario para agregar nuevo
            with st.expander("➕ Agregar/actualizar GMF de un banco"):
                col_g1, col_g2 = st.columns(2)
                with col_g1:
                    gmf_banco_nit = st.text_input("NIT del banco", key="gmf_nit")
                    gmf_banco_nombre = st.text_input("Nombre del banco", key="gmf_nombre")
                with col_g2:
                    gmf_total = st.number_input("GMF Total Certificado",
                                                  min_value=0.0, step=1000.0, key="gmf_total")
                    gmf_certificado = st.text_input("Nro Certificado (opcional)", key="gmf_cert")

                if st.button("💾 Guardar GMF", key="btn_save_gmf"):
                    if not gmf_banco_nit or gmf_total <= 0:
                        st.error("Banco NIT y Total son obligatorios")
                    else:
                        require_rol(["admin", "operador"])
                        # Eliminar previo del mismo banco
                        sb.table("exogena_conciliacion_gmf").delete().eq(
                            "periodo_id", periodo_actual["id"]
                        ).eq("banco_nit", gmf_banco_nit).execute()
                        # Insertar
                        sb.table("exogena_conciliacion_gmf").insert({
                            "periodo_id": periodo_actual["id"],
                            "banco_nit": gmf_banco_nit,
                            "banco_nombre": gmf_banco_nombre,
                            "gmf_total_certificado": gmf_total,
                            "nro_certificado": gmf_certificado,
                        }).execute()
                        st.success(f"✅ GMF guardado para {gmf_banco_nombre or gmf_banco_nit}")
                        st.rerun()

            # ============================================================
            # 5. CUADRE BALANCE vs REPORTADO POR CONCEPTO
            #    (Validación preventiva antes de generar XML)
            # ============================================================
            st.markdown("---")
            st.markdown("#### 📐 Cuadre: Balance vs Valor a reportar")
            st.caption(
                "Comparación concepto a concepto del saldo del balance contra el valor "
                "que se reportará en el XML aplicando las conciliaciones (PILA, GMF, ajustes manuales)."
            )

            if st.button("🔍 Generar cuadre", key="btn_cuadre_concilia", type="primary"):
                with st.spinner("Calculando cuadre..."):
                    from core.exogena.conciliacion import construir_cuadre_balance_vs_formatos
                    from core.exogena.motor_clasificacion import (
                        MotorClasificacion, Movimiento,
                        ReglaCapa1, ReglaCapa2, ReglaCapa3
                    )

                    # Cargar reglas
                    capa1_data = sb.table("exogena_puc_generico").select("*").eq(
                        "año_gravable", año_gravable
                    ).execute().data or []
                    capa2_data = sb.table("exogena_mapeo_empresa").select("*").eq(
                        "empresa_id", empresa["id"]
                    ).eq("año_gravable", año_gravable).execute().data or []
                    capa3_data = sb.table("exogena_mapeo_manual").select("*").eq(
                        "empresa_id", empresa["id"]
                    ).eq("año_gravable", año_gravable).execute().data or []

                    reglas_c1 = [ReglaCapa1(codigo_cuenta=r["codigo_cuenta"],
                        formato_dian=r["formato_dian"], concepto_dian=r.get("concepto_dian"),
                        nombre_cuenta=r.get("nombre_cuenta", "")) for r in capa1_data]
                    reglas_c2 = [ReglaCapa2(formato_dian=r["formato_dian"],
                        concepto_dian=r["concepto_dian"], cuenta_inicial=r["cuenta_inicial"],
                        cuenta_final=r["cuenta_final"]) for r in capa2_data]
                    reglas_c3 = [ReglaCapa3(codigo_cuenta=r["codigo_cuenta"],
                        nit=r.get("nit"), formato_dian=r.get("formato_dian"),
                        concepto_dian=r.get("concepto_dian"),
                        excluir=bool(r.get("excluir", False)),
                        motivo_exclusion=r.get("motivo_exclusion")) for r in capa3_data]

                    # Cargar movimientos
                    movs_data = sb.table("exogena_balance").select("*").eq(
                        "periodo_id", periodo_actual["id"]
                    ).eq("es_totalizador", False).execute().data or []
                    
                    movimientos = [Movimiento(
                        codigo_cuenta=m["codigo_cuenta"], nit=m.get("nit"),
                        debitos=float(m.get("debitos", 0) or 0),
                        creditos=float(m.get("creditos", 0) or 0),
                        saldo_final=float(m.get("saldo_final", 0) or 0),
                        nombre_cuenta=m.get("nombre_cuenta", ""),
                        nombre_tercero=m.get("nombre_tercero", ""),
                    ) for m in movs_data]

                    motor = MotorClasificacion(reglas_c1, reglas_c2, reglas_c3)
                    resultado = motor.clasificar_balance(movimientos)

                    # Convertir a list de dicts para la función de cuadre
                    movs_clasif = []
                    for mc in resultado.movimientos:
                        if mc.capa_resolucion == 'sin_resolver':
                            continue
                        mov_orig = next((m for m in movimientos
                                         if m.codigo_cuenta == mc.codigo_cuenta
                                         and m.nit == mc.nit), None)
                        movs_clasif.append({
                            'codigo_cuenta': mc.codigo_cuenta,
                            'nombre_cuenta': mov_orig.nombre_cuenta if mov_orig else '',
                            'nit': mc.nit,
                            'nombre_tercero': mov_orig.nombre_tercero if mov_orig else '',
                            'debitos': mov_orig.debitos if mov_orig else 0,
                            'creditos': mov_orig.creditos if mov_orig else 0,
                            'formato_dian': mc.formato_dian,
                            'concepto_dian': mc.concepto_dian,
                        })

                    # Cargar PILA consolidada (si existe)
                    pila_data = sb.table("exogena_conciliacion_pila").select("*").eq(
                        "periodo_id", periodo_actual["id"]
                    ).execute().data or []
                    
                    pila_consolidado = {}
                    for p in pila_data:
                        tipo = p.get("tipo_aporte", "")
                        if tipo not in pila_consolidado:
                            pila_consolidado[tipo] = {
                                'aporte_empleador': 0,
                                'aporte_trabajador': 0,
                                'aporte_total': 0,
                            }
                        pila_consolidado[tipo]['aporte_empleador'] += float(p.get("aporte_empleador", 0) or 0)
                        pila_consolidado[tipo]['aporte_trabajador'] += float(p.get("aporte_trabajador", 0) or 0)
                        pila_consolidado[tipo]['aporte_total'] += float(p.get("aporte_total", 0) or 0)

                    # Cargar certificados GMF
                    gmf_data = sb.table("exogena_conciliacion_gmf").select("*").eq(
                        "periodo_id", periodo_actual["id"]
                    ).execute().data or []
                    gmf_certificados = {g["banco_nit"]: g for g in gmf_data}

                    # Cargar ajustes manuales (si existen)
                    try:
                        ajustes_data = sb.table("exogena_conciliacion_ajustes").select("*").eq(
                            "periodo_id", periodo_actual["id"]
                        ).execute().data or []
                    except Exception:
                        ajustes_data = []

                    # Construir cuadre
                    cuadre = construir_cuadre_balance_vs_formatos(
                        movs_clasif,
                        pila_consolidado=pila_consolidado,
                        gmf_certificados=gmf_certificados,
                        ajustes_manuales=ajustes_data,
                    )
                    
                    st.session_state["exo_cuadre"] = cuadre

            # Mostrar cuadre si existe
            if "exo_cuadre" in st.session_state:
                cuadre = st.session_state["exo_cuadre"]
                
                if not cuadre:
                    st.warning("⚠️ No hay movimientos clasificados para mostrar.")
                else:
                    # Resumen general
                    total_balance_general = sum(c.total_balance for c in cuadre.values())
                    total_reportado_general = sum(c.total_reportado for c in cuadre.values())
                    total_diferencia_general = sum(c.total_diferencia for c in cuadre.values())
                    
                    col_t1, col_t2, col_t3 = st.columns(3)
                    with col_t1:
                        st.metric("Total Balance", f"${total_balance_general:,.0f}")
                    with col_t2:
                        st.metric("Total a Reportar", f"${total_reportado_general:,.0f}",
                                  delta=f"${(total_reportado_general - total_balance_general):,.0f}")
                    with col_t3:
                        st.metric("Diferencia (No deducible)",
                                  f"${total_diferencia_general:,.0f}",
                                  delta="positivo" if total_diferencia_general > 0 else "negativo",
                                  delta_color="off")

                    # Por cada formato, mostrar tabla
                    for fmt_code, cf in sorted(cuadre.items()):
                        with st.expander(f"📋 {cf.nombre_formato} — Balance: ${cf.total_balance:,.0f} → Reportado: ${cf.total_reportado:,.0f}",
                                          expanded=True):
                            df_cuadre = pd.DataFrame([{
                                "Concepto": f.concepto_dian,
                                "Descripción": f.descripcion_concepto,
                                "Cuentas": f.cantidad_cuentas,
                                "Movs": f.cantidad_movimientos,
                                "Saldo Balance": float(f.saldo_balance),
                                "A Reportar": float(f.valor_reportado),
                                "Diferencia": float(f.diferencia),
                                "Estado": f.estado,
                                "Motivo": f.motivo,
                            } for f in cf.filas])
                            
                            # Aplicar formato de moneda
                            st.dataframe(
                                df_cuadre,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "Saldo Balance": st.column_config.NumberColumn(format="$%.0f"),
                                    "A Reportar": st.column_config.NumberColumn(format="$%.0f"),
                                    "Diferencia": st.column_config.NumberColumn(format="$%.0f"),
                                }
                            )
                            
                            # Resumen formato
                            col_r1, col_r2, col_r3 = st.columns(3)
                            with col_r1:
                                st.metric("Balance", f"${cf.total_balance:,.0f}")
                            with col_r2:
                                st.metric("A Reportar", f"${cf.total_reportado:,.0f}")
                            with col_r3:
                                st.metric("Diferencia", f"${cf.total_diferencia:,.0f}")

                    # Estado general
                    st.markdown("---")
                    if total_diferencia_general == 0:
                        st.success("✅ Balance y formatos cuadran perfectamente. Listo para generar XML.")
                    elif any(f.estado == 'DIFERENCIA' for cf in cuadre.values() for f in cf.filas):
                        st.error("❌ Hay diferencias inexplicadas. Revisa los conceptos marcados como 'DIFERENCIA'.")
                    else:
                        st.info(
                            f"ℹ️ Diferencia total esperada: ${total_diferencia_general:,.0f} "
                            "(corresponde a: parte trabajador de seguridad social + 50% no deducible de GMF)."
                        )

                    # ============================================================
                    # 6. EXCEL BORRADOR COMPLETO DE AUDITORÍA
                    # ============================================================
                    st.markdown("---")
                    st.markdown("#### 📊 Excel borrador completo (auditoría tributaria)")
                    st.caption(
                        "Genera un Excel con: hoja resumen + una hoja por cada formato "
                        "(detalle por NIT + conciliación) + hoja de cuentas no reportadas. "
                        "Documento maestro de auditoría tributaria."
                    )

                    if st.button("📊 Generar Excel borrador completo",
                                  key="btn_excel_borrador", type="primary"):
                        with st.spinner("Generando Excel borrador completo..."):
                            from core.exogena.excel_borrador_formatos import (
                                generar_excel_borrador_completo
                            )
                            
                            # Cargar terceros del periodo
                            try:
                                terceros_data = sb.table("exogena_terceros").select(
                                    "nit,tipo_documento,dv,razon_social,nombre_completo"
                                ).eq("periodo_id", periodo_actual["id"]).execute().data or []
                            except Exception:
                                terceros_data = []
                            
                            terceros_dict = {}
                            for t in terceros_data:
                                nit_clean = str(t.get('nit', '')).strip().replace('.', '').replace(' ', '')
                                if '-' in nit_clean:
                                    nit_clean = nit_clean.split('-')[0]
                                if nit_clean:
                                    terceros_dict[nit_clean] = t

                            # Cargar TODOS los movimientos del balance (para no reportadas)
                            try:
                                todos_movs_data = sb.table("exogena_balance").select("*").eq(
                                    "periodo_id", periodo_actual["id"]
                                ).eq("es_totalizador", False).execute().data or []
                            except Exception:
                                todos_movs_data = []

                            # Re-clasificar para obtener movs con formato/concepto
                            from core.exogena.motor_clasificacion import (
                                MotorClasificacion, Movimiento,
                                ReglaCapa1, ReglaCapa2, ReglaCapa3
                            )
                            
                            capa1_data = sb.table("exogena_puc_generico").select("*").eq(
                                "año_gravable", año_gravable
                            ).execute().data or []
                            capa2_data = sb.table("exogena_mapeo_empresa").select("*").eq(
                                "empresa_id", empresa["id"]
                            ).eq("año_gravable", año_gravable).execute().data or []
                            capa3_data = sb.table("exogena_mapeo_manual").select("*").eq(
                                "empresa_id", empresa["id"]
                            ).eq("año_gravable", año_gravable).execute().data or []

                            reglas_c1 = [ReglaCapa1(codigo_cuenta=r["codigo_cuenta"],
                                formato_dian=r["formato_dian"], concepto_dian=r.get("concepto_dian"),
                                nombre_cuenta=r.get("nombre_cuenta", "")) for r in capa1_data]
                            reglas_c2 = [ReglaCapa2(formato_dian=r["formato_dian"],
                                concepto_dian=r["concepto_dian"], cuenta_inicial=r["cuenta_inicial"],
                                cuenta_final=r["cuenta_final"]) for r in capa2_data]
                            reglas_c3 = [ReglaCapa3(codigo_cuenta=r["codigo_cuenta"],
                                nit=r.get("nit"), formato_dian=r.get("formato_dian"),
                                concepto_dian=r.get("concepto_dian"),
                                excluir=bool(r.get("excluir", False)),
                                motivo_exclusion=r.get("motivo_exclusion")) for r in capa3_data]

                            movimientos = [Movimiento(
                                codigo_cuenta=m["codigo_cuenta"], nit=m.get("nit"),
                                debitos=float(m.get("debitos", 0) or 0),
                                creditos=float(m.get("creditos", 0) or 0),
                                saldo_final=float(m.get("saldo_final", 0) or 0),
                                nombre_cuenta=m.get("nombre_cuenta", ""),
                                nombre_tercero=m.get("nombre_tercero", ""),
                            ) for m in todos_movs_data]

                            motor = MotorClasificacion(reglas_c1, reglas_c2, reglas_c3)
                            resultado = motor.clasificar_balance(movimientos)

                            movs_clasif = []
                            for mc in resultado.movimientos:
                                if mc.capa_resolucion == 'sin_resolver':
                                    continue
                                mov_orig = next((m for m in movimientos
                                                 if m.codigo_cuenta == mc.codigo_cuenta
                                                 and m.nit == mc.nit), None)
                                movs_clasif.append({
                                    'codigo_cuenta': mc.codigo_cuenta,
                                    'nombre_cuenta': mov_orig.nombre_cuenta if mov_orig else '',
                                    'nit': mc.nit,
                                    'nombre_tercero': mov_orig.nombre_tercero if mov_orig else '',
                                    'debitos': mov_orig.debitos if mov_orig else 0,
                                    'creditos': mov_orig.creditos if mov_orig else 0,
                                    'formato_dian': mc.formato_dian,
                                    'concepto_dian': mc.concepto_dian,
                                })

                            # Convertir todos_movs a dict simple
                            todos_movs_dict = [{
                                'codigo_cuenta': m["codigo_cuenta"],
                                'nombre_cuenta': m.get("nombre_cuenta", ""),
                                'nit': m.get("nit"),
                                'debitos': float(m.get("debitos", 0) or 0),
                                'creditos': float(m.get("creditos", 0) or 0),
                            } for m in todos_movs_data]

                            cabecera = {
                                'razon_social': empresa.get('razon_social', ''),
                                'nit': empresa.get('nit', ''),
                                'año_gravable': año_gravable,
                            }

                            excel_buf = generar_excel_borrador_completo(
                                movimientos_clasificados=movs_clasif,
                                todos_movimientos_balance=todos_movs_dict,
                                cuadre=cuadre,
                                terceros_dict=terceros_dict,
                                cabecera=cabecera,
                            )

                            st.session_state["exo_excel_borrador"] = excel_buf.getvalue()
                            st.success("✅ Excel generado correctamente.")

                    if "exo_excel_borrador" in st.session_state:
                        st.download_button(
                            "📥 Descargar Excel borrador completo",
                            data=st.session_state["exo_excel_borrador"],
                            file_name=f"borrador_exogena_{empresa.get('nit','empresa').replace('-','')}_{año_gravable}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=False,
                        )

    # ============================================================
    # Conciliación Enriquecida — agregada en sesión del 7 mayo 2026
    # Tabla detallada por (formato, concepto) con balance vs reportado
    # ============================================================
    try:
        from core.exogena.ui_conciliacion_enriquecida import render_conciliacion_enriquecida

        sb_local_cce = get_supabase()
        render_conciliacion_enriquecida(
            sb=sb_local_cce,
            empresa_id=empresa["id"],
            empresa_nombre=empresa.get("razon_social", "Empresa"),
            año_gravable=año_gravable,
        )
    except Exception as e:
        st.error(f"⚠️ Error cargando Conciliación Enriquecida: {e}")


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
