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
                
                # 2. Limpiar balance previo del periodo (si lo hubiera)
                sb.table("exogena_balance").delete().eq(
                    "periodo_id", periodo["id"]
                ).execute()

                # 3. Insertar movimientos en lotes
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

                for i in range(0, len(registros), LOTE):
                    sb.table("exogena_balance").insert(registros[i:i+LOTE]).execute()

                obtener_periodo.clear()
                st.success(f"✅ Balance guardado: {len(res_bal.movimientos)} movimientos + "
                           f"{sum(1 for r in registros if r['es_totalizador'])} totalizadores")
                st.rerun()

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
                            formato_dian=r["formato_dian"],
                            concepto_dian=r.get("concepto_dian"),
                            nota=r.get("nota", ""),
                            id=r.get("id"),
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

                    # Distribución por formato
                    por_formato = {}
                    for mc in movs_clasif:
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

                    formatos_dian = _cargar_catalogo("exogena_formatos", "codigo_dian,nombre")
                    formatos_options = {
                        f["codigo_dian"]: f"{f['codigo_dian']} - {f['nombre'][:40]}"
                        for f in sorted(formatos_dian, key=lambda x: x["codigo_dian"])
                    }
                    formatos_options["__ignorar__"] = "❌ No aplica (ignorar)"

                    conceptos_dian = _cargar_catalogo(
                        "exogena_conceptos", "codigo_dian,formato_dian,descripcion"
                    )
                    conceptos_por_formato = {}
                    for c in conceptos_dian:
                        conceptos_por_formato.setdefault(c["formato_dian"], []).append(c)

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

                    for idx, ch in enumerate(cuentas_orden[:LIMIT]):
                        with st.container():
                            cols = st.columns([1.5, 3, 1.2, 1.5, 2, 2, 1.5])
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
                                fmt = st.selectbox(
                                    "Formato",
                                    options=list(formatos_options.keys()),
                                    format_func=lambda k: formatos_options[k],
                                    key=fmt_key,
                                    label_visibility="collapsed",
                                )
                            with cols[5]:
                                cpt_key = f"cpt_{ch['cuenta']}_{idx}"
                                if fmt and fmt != "__ignorar__":
                                    conceptos_disp = conceptos_por_formato.get(fmt, [])
                                    cpt_options = {
                                        c["codigo_dian"]: f"{c['codigo_dian']} - {c['descripcion'][:30]}"
                                        for c in conceptos_disp
                                    }
                                    cpt_options[None] = "(sin concepto)"
                                    cpt = st.selectbox(
                                        "Concepto",
                                        options=list(cpt_options.keys()),
                                        format_func=lambda k: cpt_options[k] if k else "(sin concepto)",
                                        key=cpt_key,
                                        label_visibility="collapsed",
                                    )
                                else:
                                    cpt = None
                                    st.text("—")
                            with cols[6]:
                                if st.button(
                                    "💾 Aplicar",
                                    key=f"apply_{ch['cuenta']}_{idx}",
                                    use_container_width=True,
                                ):
                                    if fmt == "__ignorar__":
                                        # Marcar como ignorada (regla con formato vacío)
                                        sb.table("exogena_mapeo_manual").upsert({
                                            "empresa_id": empresa["id"],
                                            "año_gravable": año_gravable,
                                            "codigo_cuenta": ch["cuenta"],
                                            "nit": None,
                                            "formato_dian": "__ignorar__",
                                            "concepto_dian": None,
                                            "nota": "Marcada como no aplica por usuario",
                                        }).execute()
                                        st.success(f"✓ Cuenta {ch['cuenta']} ignorada")
                                    elif fmt:
                                        sb.table("exogena_mapeo_manual").upsert({
                                            "empresa_id": empresa["id"],
                                            "año_gravable": año_gravable,
                                            "codigo_cuenta": ch["cuenta"],
                                            "nit": None,
                                            "formato_dian": fmt,
                                            "concepto_dian": cpt,
                                            "nota": "",
                                        }).execute()
                                        st.success(f"✓ {ch['cuenta']} → {fmt}")
                                    # Limpiar dictamen para que se reejecute
                                    if "exo_dictamen" in st.session_state:
                                        del st.session_state["exo_dictamen"]
                                    st.rerun()

                            # Mostrar ejemplos de NITs en esta cuenta (en una línea aparte)
                            if ch["ejemplos_nits"]:
                                st.caption(
                                    f"  Ejemplos: " + " | ".join(ch["ejemplos_nits"][:3])
                                )
                            st.markdown("")  # separador
                else:
                    if d["n_clasif"] > 0:
                        st.success("🎉 **¡Todas las cuentas están clasificadas!** Puedes pasar a generar XMLs.")


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
