"""
Módulo Ingresos POS — Plataforma Web (versión 2: DATOS PUNTO embebido).

DATOS PUNTO viene incluido en el código (core/data/datos_punto.json) — el
operador NO tiene que subirlo. Solo sube los 4 reportes mensuales.

Pestañas:
    1️⃣ Procesar (subir reportes por separado)  ← modo principal
    2️⃣ Procesar (Excel todo en uno)             ← modo legacy

Asiento generado:
    Db CUENTA DE CAJA   = Total Final
    Cr CTA BASE V       = Neto
    Cr CTA ICO          = IC (Final − Neto)

Validación de CLASE DE SEDE:
    - REPORTE CHILI     → solo procesa SANTA LEÑA
    - HENKO MILAGROS    → solo procesa RESTAURANTE MILAGROS
    - HENKO REMEDIOS    → solo procesa RESTAURANTE MILAGROS
    - L3AF MILLA DE ORO → solo procesa RESTAURANTE MILAGROS
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
from datetime import date
import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import (
    seleccionar_empresa_sidebar,
    require_rol,
)
from auth.modulos import require_modulo
from core.procesadores.procesador_pos import (
    procesar_pos,
    dataframe_a_plano_tsv,
    combinar_archivos_pos,
    cargar_datos_punto_embebido,
    datos_punto_embebido_a_xlsx,
    info_datos_punto_embebido,
)
from core.procesadores.parser_token_dian import (
    parsear_token_dian,
    parsear_notas_credito_token,
    generar_lineas_nc_pos,
)
from core.procesadores.comparador_pos_token import (
    comparar_pos_token,
    resumen_comparacion,
    aplicar_elecciones_al_plano,
)

# ── Import defensivo del procesador STL ──
# Si por algún motivo no está disponible (deploy parcial, falta config_stl.json),
# la pestaña STL mostrará un mensaje en lugar de tirar la página entera.
_STL_DISPONIBLE = True
_STL_ERROR = None
_STL_TRACEBACK = None
try:
    from core.procesadores.procesador_stl import (
        procesar_stl,
        cargar_config_stl,
        plano_a_tsv_bytes as stl_plano_tsv,
        plano_a_csv_bytes as stl_plano_csv,
        plano_a_xlsx_bytes as stl_plano_xlsx,
    )
except Exception as _e:
    import traceback as _tb
    _STL_DISPONIBLE = False
    _STL_ERROR = f"{type(_e).__name__}: {_e}"
    _STL_TRACEBACK = _tb.format_exc()


# ============================================================
# Configuración de la página
# ============================================================

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
require_modulo("ingresos_pos")
emp = require_rol(["admin", "operador"])


# ============================================================
# Encabezado
# ============================================================

st.title("🧾 Ingresos POS")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    f"Procesa reportes diarios de ventas POS y genera el plano contable"
)
st.markdown("---")


# ============================================================
# Sidebar
# ============================================================

with st.sidebar:
    st.markdown("### ⚙️ Opciones")
    incluir_enc_excel = st.checkbox(
        "Incluir 'sep=\\t' (compatible Excel)",
        value=True,
        help="Agrega la directiva de separador para que Excel abra el TSV "
             "con las columnas alineadas.",
    )

    st.markdown("---")
    st.markdown("### 🛡️ Validación por clase")
    st.caption(
        """
        Cada hoja solo procesa sucursales de su clase:

        - 🥩 **REPORTE CHILI** → SANTA LEÑA
        - 🍝 **L3AF MILLA DE ORO** → RESTAURANTE MILAGROS
        - 🍝 **HENKO MILAGROS** → RESTAURANTE MILAGROS
        - 🍝 **HENKO REMEDIOS** → RESTAURANTE MILAGROS

        Si una sucursal aparece en una hoja con clase incorrecta,
        se descarta y se avisa.
        """
    )


# ============================================================
# Cargar info del DATOS PUNTO embebido
# ============================================================

@st.cache_data(ttl=600, show_spinner=False)
def _info_dp():
    try:
        return info_datos_punto_embebido()
    except Exception as e:
        return {"error": str(e)}


@st.cache_data(ttl=600, show_spinner=False)
def _xlsx_dp():
    return datos_punto_embebido_a_xlsx()


info_dp = _info_dp()
if "error" in info_dp:
    st.error(
        f"❌ No se pudo cargar el maestro de sucursales embebido: "
        f"{info_dp['error']}\n\n"
        "Verifica que el archivo `core/data/datos_punto.json` esté presente "
        "en el repositorio."
    )
    st.stop()


# ============================================================
# Banner del DATOS PUNTO embebido (informativo, no editable)
# ============================================================

n_sl = info_dp["por_clase"].get("SANTA LEÑA", 0)
n_rm = info_dp["por_clase"].get("RESTAURANTE MILAGROS", 0)

col_a, col_b, col_c = st.columns(3)
col_a.metric("📋 Sucursales registradas", info_dp["total"])
col_b.metric("🥩 SANTA LEÑA", n_sl)
col_c.metric("🍝 RESTAURANTE MILAGROS", n_rm)

with st.expander(
    f"👁️ Ver las {info_dp['total']} sucursales registradas (modo lectura)",
    expanded=False,
):
    st.caption(
        "Estas son las sucursales registradas en el sistema. **El maestro "
        "DATOS PUNTO viene incluido en el código** — no es editable desde "
        "la web. Si abren un punto nuevo o cambia una cuenta, contacta al "
        "desarrollador para actualizar el archivo."
    )
    df_suc = pd.DataFrame(info_dp["sucursales"])
    st.dataframe(
        df_suc,
        use_container_width=True,
        hide_index=True,
        column_config={
            "nombre_reporte": "Nombre en reporte",
            "sede": "Sede",
            "cc": "Centro de costo",
            "clase": "Clase de sede",
            "cuenta_caja": "Cuenta de caja",
            "cta_base_v": "Cta venta",
            "cta_ico": "Cta IC",
            "comprobante": "Comprob.",
        },
    )

st.markdown("---")


# ============================================================
# Tabs principales
# ============================================================

tab_separado, tab_unico, tab_token, tab_stl = st.tabs([
    "1️⃣ Procesar (subir reportes por separado)",
    "2️⃣ Procesar (Excel todo en uno)",
    "3️⃣ Conciliar con Token DIAN",
    "4️⃣ Ventas STL (mayoristas)",
])


# ============================================================
# Helper compartido: mostrar resultado
# ============================================================

def _mostrar_resultado(df, log, sucs_no_enc, nombre_entrada):
    """Muestra el resultado del procesamiento."""
    st.markdown("### 📊 Resultado")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Filas en plano", len(df))
    with col2:
        sucs_unicas = df["DETALLE"].nunique() if len(df) else 0
        st.metric("Sucursales", sucs_unicas)
    with col3:
        if len(df):
            suma_db = int(df[df["TR"] == "1"]["VALOR"].astype(int).sum())
        else:
            suma_db = 0
        st.metric("Total Débitos", f"$ {suma_db:,.0f}".replace(",", "."))
    with col4:
        if len(df):
            suma_cr = int(df[df["TR"] == "2"]["VALOR"].astype(int).sum())
        else:
            suma_cr = 0
        st.metric("Total Créditos", f"$ {suma_cr:,.0f}".replace(",", "."))

    if len(df) > 0:
        if suma_db == suma_cr:
            st.success(f"✅ Cuadre perfecto: Db = Cr = $ {suma_db:,.0f}".replace(",", "."))
        else:
            diff = suma_db - suma_cr
            st.error(f"❌ DESCUADRE: diferencia $ {diff:,.0f}".replace(",", "."))

    with st.expander("📝 Log de procesamiento", expanded=True):
        for linea in log:
            st.text(linea)

    if sucs_no_enc:
        with st.expander(
            f"⚠️ {len(sucs_no_enc)} sucursal(es) descartada(s)",
            expanded=True,
        ):
            st.caption(
                "Estas sucursales aparecieron en los reportes pero NO se "
                "incluyeron en el plano. Si es una sucursal nueva, el "
                "desarrollador debe agregarla a `core/data/datos_punto.json`."
            )
            df_no_enc = pd.DataFrame([
                {
                    "Sucursal detectada": s["nombre"],
                    "Hoja": s["hoja"],
                    "Motivo": s.get("motivo", "-"),
                    "Total ignorado": f"$ {s['total_aproximado']:,.0f}".replace(",", "."),
                }
                for s in sucs_no_enc
            ])
            st.dataframe(df_no_enc, use_container_width=True, hide_index=True)

    if len(df) > 0:
        with st.expander("📊 Resumen por sucursal", expanded=False):
            df_resumen = df[df["TR"] == "1"].groupby("DETALLE").agg(
                dias=("FECHA", "nunique"),
                total=("VALOR", lambda x: x.astype(int).sum()),
            ).reset_index()
            df_resumen["DETALLE"] = df_resumen["DETALLE"].str.replace("VENTAS POS ", "")
            df_resumen = df_resumen.sort_values("total", ascending=False)
            df_resumen["Total"] = df_resumen["total"].apply(
                lambda x: f"$ {x:,.0f}".replace(",", ".")
            )
            st.dataframe(
                df_resumen[["DETALLE", "dias", "Total"]].rename(
                    columns={"DETALLE": "Sucursal", "dias": "Días con venta"},
                ),
                use_container_width=True,
                hide_index=True,
            )

    st.markdown("#### Vista previa del plano")
    st.dataframe(df, use_container_width=True, height=400)

    # Descarga
    st.markdown("### 📥 Descargar")
    tsv_bytes = dataframe_a_plano_tsv(df, incluir_encabezado_excel=incluir_enc_excel)
    nombre_base = nombre_entrada.rsplit(".", 1)[0] if nombre_entrada else "ingresos_pos"
    nombre_salida = f"plano_pos_{nombre_base}.txt"

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.download_button(
            "📥 Descargar plano (.txt)",
            data=tsv_bytes,
            file_name=nombre_salida,
            mime="text/tab-separated-values",
            type="primary",
            use_container_width=True,
        )
    with col_d2:
        buffer = io.BytesIO()
        df.to_excel(buffer, index=False, engine="openpyxl")
        st.download_button(
            "📊 Descargar como Excel",
            data=buffer.getvalue(),
            file_name=nombre_salida.replace(".txt", ".xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


# ============================================================
# TAB 1: Subir reportes por separado (modo principal)
# ============================================================

with tab_separado:
    st.markdown("### 📂 Subir cada reporte como archivo aparte")
    st.caption(
        "Sube los 4 reportes que recibes cada mes de los sistemas POS. "
        "El sistema los combina automáticamente con el maestro de "
        "sucursales y genera el plano contable."
    )

    st.info(
        "💡 **No necesitas subir DATOS PUNTO** — viene incluido en el sistema "
        f"({info_dp['total']} sucursales registradas)."
    )

    st.markdown("#### Sube los reportes (puedes dejar los que no apliquen vacíos)")

    col_chi, col_l3 = st.columns(2)
    with col_chi:
        st.markdown("**🥩 REPORTE CHILI** (SANTA LEÑA)")
        archivo_chili = st.file_uploader(
            "Reporte CHILI (.xlsx)",
            type=["xlsx"],
            key="file_chili",
            label_visibility="collapsed",
        )
    with col_l3:
        st.markdown("**🍝 L3AF MILLA DE ORO** (RESTAURANTE MILAGROS)")
        archivo_l3af = st.file_uploader(
            "L3AF (.xlsx)",
            type=["xlsx"],
            key="file_l3af",
            label_visibility="collapsed",
        )

    col_hm, col_hr = st.columns(2)
    with col_hm:
        st.markdown("**🍝 HENKO MILAGROS** (RESTAURANTE MILAGROS)")
        archivo_henko_m = st.file_uploader(
            "HENKO Milagros (.xlsx)",
            type=["xlsx"],
            key="file_henko_m",
            label_visibility="collapsed",
        )
    with col_hr:
        st.markdown("**🍝 HENKO REMEDIOS** (RESTAURANTE MILAGROS)")
        archivo_henko_r = st.file_uploader(
            "HENKO Remedios (.xlsx)",
            type=["xlsx"],
            key="file_henko_r",
            label_visibility="collapsed",
        )

    archivos_subidos = {
        "REPORTE CHILI": archivo_chili,
        "L3AF MILLA DE ORO": archivo_l3af,
        "HENKO MILAGROS": archivo_henko_m,
        "HENKO REMEDIOS": archivo_henko_r,
    }
    archivos_validos = {k: v for k, v in archivos_subidos.items() if v is not None}

    if not archivos_validos:
        st.info("📂 Sube al menos un reporte para procesar.")
        st.stop()

    st.markdown("---")
    st.caption(
        f"Vas a procesar **{len(archivos_validos)}** reporte(s): "
        f"{', '.join(archivos_validos.keys())}"
    )

    procesar_sep = st.button(
        "🚀 Procesar reportes",
        type="primary",
        key="btn_procesar_separado",
    )

    if procesar_sep:
        with st.spinner("Combinando reportes con DATOS PUNTO embebido..."):
            try:
                xlsx_dp = _xlsx_dp()
                excel_combinado = combinar_archivos_pos(
                    archivo_datos_punto=xlsx_dp,
                    reportes=archivos_validos,
                )
            except Exception as e:
                st.error(f"❌ Error combinando archivos: {e}")
                st.exception(e)
                st.stop()

        with st.spinner("Generando plano contable..."):
            try:
                df, log, sucs_no = procesar_pos(excel_combinado)
            except Exception as e:
                st.error(f"❌ Error procesando: {e}")
                st.exception(e)
                st.stop()

        st.session_state["resultado_pos_separado"] = {
            "df": df,
            "log": log,
            "sucs_no": sucs_no,
            "nombre": "reportes_combinados",
        }

    res_sep = st.session_state.get("resultado_pos_separado")
    if res_sep:
        _mostrar_resultado(
            res_sep["df"], res_sep["log"], res_sep["sucs_no"], res_sep["nombre"],
        )
        if st.button("🔄 Procesar otros reportes", key="reset_sep"):
            st.session_state.pop("resultado_pos_separado", None)
            st.rerun()


# ============================================================
# TAB 2: Excel todo en uno (modo legacy)
# ============================================================

with tab_unico:
    st.markdown("### 📦 Subir Excel todo en uno")
    st.caption(
        "Si prefieres el formato antiguo donde DATOS PUNTO + todos los "
        "reportes están en un solo archivo Excel multi-hoja, súbelo aquí. "
        "Útil cuando alguien ya armó el archivo manualmente."
    )

    archivo_pos = st.file_uploader(
        "Excel multi-hoja con DATOS PUNTO + reportes",
        type=["xlsx"],
        key="file_pos_unico",
    )

    if archivo_pos:
        procesar_uni = st.button(
            "🚀 Procesar Excel completo",
            type="primary",
            key="btn_procesar_unico",
        )

        if procesar_uni:
            with st.spinner("Procesando..."):
                try:
                    df, log, sucs_no = procesar_pos(archivo_pos)
                    st.session_state["resultado_pos_unico"] = {
                        "df": df,
                        "log": log,
                        "sucs_no": sucs_no,
                        "nombre": archivo_pos.name,
                    }
                except Exception as e:
                    st.error(f"❌ Error al procesar: {e}")
                    st.exception(e)
                    st.stop()

    res_uni = st.session_state.get("resultado_pos_unico")
    if res_uni:
        _mostrar_resultado(
            res_uni["df"], res_uni["log"], res_uni["sucs_no"], res_uni["nombre"],
        )
        if st.button("🔄 Procesar otro archivo", key="reset_uni"):
            st.session_state.pop("resultado_pos_unico", None)
            st.rerun()


# ============================================================
# TAB 3: Conciliación POS vs Token DIAN
# ============================================================

with tab_token:
    st.markdown("### 🔄 Conciliar ventas POS vs Token DIAN")
    st.caption(
        "Sube el archivo del Token DIAN para cruzarlo contra el plano POS "
        "procesado en las pestañas anteriores. Detectamos las diferencias "
        "por día y sucursal, y tú decides qué fuente usar."
    )

    # ----- Paso 0: validar que hay un plano POS procesado -----
    plano_pos_actual = None
    nombre_plano = ""
    res_sep_actual = st.session_state.get("resultado_pos_separado")
    res_uni_actual = st.session_state.get("resultado_pos_unico")
    if res_sep_actual is not None:
        plano_pos_actual = res_sep_actual["df"]
        nombre_plano = res_sep_actual["nombre"]
    elif res_uni_actual is not None:
        plano_pos_actual = res_uni_actual["df"]
        nombre_plano = res_uni_actual["nombre"]

    if plano_pos_actual is None or len(plano_pos_actual) == 0:
        st.warning(
            "⚠️ Primero procesa el POS en la pestaña 1 o 2. Después regresa "
            "aquí para cargar el Token DIAN y conciliarlos."
        )
    else:
        st.success(
            f"✅ Plano POS cargado de la pestaña anterior: "
            f"**{len(plano_pos_actual)}** líneas · "
            f"**{plano_pos_actual['FECHA'].nunique()}** días distintos"
        )

        # ----- Paso 1: subir el Token -----
        st.markdown("#### 📥 Sube el reporte del Token DIAN")
        st.caption(
            "Es el Excel que descargas desde el portal DIAN > Reportes > "
            "Token. Debe traer todas las facturas electrónicas emitidas "
            "por la empresa en el período."
        )

        archivo_token = st.file_uploader(
            "Excel del Token DIAN (.xlsx)",
            type=["xlsx"],
            key="file_token_dian",
        )

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            tolerancia = st.number_input(
                "Tolerancia en pesos para considerar 'cuadran'",
                min_value=0,
                max_value=10000,
                value=100,
                step=10,
                help="Diferencias menores a este monto se consideran "
                     "redondeos y no se marcan como conflicto. Default $100.",
            )
        with col_t2:
            omitir_stl = st.checkbox(
                "Omitir prefijo STL (recomendado)",
                value=True,
                help="STL son facturas con IVA variable que se procesan "
                     "por flujo Henko separado.",
            )

        prefijos_omitidos = ("STL",) if omitir_stl else ()

        if archivo_token is not None:
            procesar_token = st.button(
                "🚀 Procesar Token y comparar",
                type="primary",
                key="btn_procesar_token",
            )

            if procesar_token:
                with st.spinner("Leyendo el Token DIAN..."):
                    try:
                        sucursales = cargar_datos_punto_embebido()
                        nit_empresa = emp.get("nit", "").strip()
                        if not nit_empresa:
                            st.error("❌ No se encontró el NIT de la empresa activa.")
                            st.stop()
                        resultado_tk = parsear_token_dian(
                            fuente=archivo_token.getvalue(),
                            nit_empresa=nit_empresa,
                            sucursales=sucursales,
                            prefijos_omitidos=prefijos_omitidos,
                        )
                        # También parsear las NC del mismo archivo
                        resultado_nc = parsear_notas_credito_token(
                            fuente=archivo_token.getvalue(),
                            nit_empresa=nit_empresa,
                            sucursales=sucursales,
                        )
                    except Exception as e:
                        st.error(f"❌ Error procesando el Token: {e}")
                        st.exception(e)
                        st.stop()

                with st.spinner("Comparando POS vs Token..."):
                    try:
                        df_cmp = comparar_pos_token(
                            plano_pos_actual,
                            resultado_tk["agregado_fecha_prefijo"],
                            tolerancia_pesos=int(tolerancia),
                        )
                    except Exception as e:
                        st.error(f"❌ Error comparando: {e}")
                        st.exception(e)
                        st.stop()

                st.session_state["resultado_token"] = {
                    "df_cmp": df_cmp,
                    "resultado_tk": resultado_tk,
                    "resultado_nc": resultado_nc,
                    "nombre_token": archivo_token.name,
                    "tolerancia": int(tolerancia),
                    "incluir_nc": True,  # default: incluir NC en plano final
                }
                # Limpiar elecciones previas
                st.session_state.pop("token_elecciones", None)

        # ----- Paso 2: mostrar resultado de la comparación -----
        res_tk = st.session_state.get("resultado_token")
        if res_tk:
            df_cmp = res_tk["df_cmp"]
            resultado_tk = res_tk["resultado_tk"]

            st.markdown("---")
            st.markdown("### 📊 Resultado de la conciliación")

            resumen = resumen_comparacion(df_cmp)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Celdas comparadas", f"{resumen['total_celdas']:,}")
            c2.metric("✅ Coinciden", f"{resumen['coincide']:,}")
            c3.metric("⚠️ Difieren", f"{resumen['difiere']:,}")
            c4.metric(
                "🔴 Solo en una fuente",
                f"{resumen['solo_pos'] + resumen['solo_token']:,}",
            )

            c5, c6, c7 = st.columns(3)
            c5.metric(
                "Total POS",
                f"$ {resumen['total_pos']:,.0f}".replace(",", "."),
            )
            c6.metric(
                "Total Token",
                f"$ {resumen['total_token']:,.0f}".replace(",", "."),
            )
            c7.metric(
                "Diferencia total",
                f"$ {resumen['diferencia']:,.0f}".replace(",", "."),
                delta=None,
            )

            with st.expander("📝 Log del Token", expanded=False):
                for l in resultado_tk["log"]:
                    st.text(l)
                if resultado_tk["prefijos_no_mapeados"]:
                    st.warning(
                        f"Prefijos no mapeados (ignorados): "
                        f"{resultado_tk['prefijos_no_mapeados']}"
                    )

            # ----- Filtros y modo de visualización -----
            st.markdown("### 🔍 Decisión y revisión de diferencias")

            col_modo, col_f3 = st.columns([2, 3])
            with col_modo:
                modo_vista = st.radio(
                    "Modo de visualización",
                    options=[
                        "Por día (detallado)",
                        "Por sucursal-mes (consolidado)",
                    ],
                    horizontal=False,
                    help=(
                        "Detallado: una fila por día y sucursal. Aquí eliges la fuente. "
                        "Consolidado: una fila por sucursal con los totales del período."
                    ),
                    key="modo_vista_token",
                )
            with col_f3:
                # Para el rango de fechas, asegurarse de tener fechas válidas
                fechas_validas = pd.to_datetime(df_cmp["fecha"], errors="coerce").dropna()
                if len(fechas_validas) > 0:
                    f_min = fechas_validas.min().date()
                    f_max = fechas_validas.max().date()
                    rango = st.date_input(
                        "Rango de fechas a incluir",
                        value=(f_min, f_max),
                        min_value=f_min,
                        max_value=f_max,
                    )
                else:
                    rango = None

            col_f1, col_f2 = st.columns(2)
            with col_f1:
                mostrar_coincidencias = st.checkbox(
                    "Mostrar también las sucursales/días sin diferencias",
                    value=False,
                    help="Por defecto solo se ven los casos que difieren o están en una sola fuente.",
                )
            with col_f2:
                filtro_sucursal = st.multiselect(
                    "Filtrar por sucursal",
                    options=sorted(df_cmp["sucursal_nombre"].dropna().unique().tolist()),
                    default=[],
                )

            # ----- Aplicar filtros COMUNES -----
            df_filt = df_cmp.copy()
            if filtro_sucursal:
                df_filt = df_filt[df_filt["sucursal_nombre"].isin(filtro_sucursal)]
            if rango and isinstance(rango, tuple) and len(rango) == 2:
                f_ini, f_fin = rango
                df_filt = df_filt[
                    (pd.to_datetime(df_filt["fecha"]).dt.date >= f_ini) &
                    (pd.to_datetime(df_filt["fecha"]).dt.date <= f_fin)
                ]

            # ============================================================
            # MODO CONSOLIDADO (por sucursal-mes)
            # ============================================================
            if modo_vista == "Por sucursal-mes (consolidado)":
                # Consolidar: una fila por sucursal con totales del período
                df_consol_base = df_filt.copy()
                # Agregar columna "dias_con_diferencia"
                df_consol_base["_difiere"] = (
                    df_consol_base["estado"].isin(["difiere", "solo_pos", "solo_token"])
                ).astype(int)
                df_consol_base["_coincide"] = (
                    df_consol_base["estado"] == "coincide"
                ).astype(int)

                df_consol = (
                    df_consol_base.groupby(
                        ["sucursal_cc", "sucursal_nombre", "prefijo"],
                        dropna=False,
                    ).agg(
                        dias_totales=("fecha", "nunique"),
                        dias_coinciden=("_coincide", "sum"),
                        dias_difieren=("_difiere", "sum"),
                        total_pos=("total_pos", "sum"),
                        total_token=("total_token", "sum"),
                        diferencia=("diferencia", "sum"),
                    ).reset_index()
                )
                df_consol = df_consol.sort_values(
                    "diferencia",
                    key=lambda s: s.abs(),
                    ascending=False,
                ).reset_index(drop=True)

                # Filtrar las que coinciden 100% si el contador no las quiere
                if not mostrar_coincidencias:
                    df_consol = df_consol[df_consol["dias_difieren"] > 0].reset_index(drop=True)

                if len(df_consol) == 0:
                    st.success(
                        "👍 No hay sucursales con diferencias en el rango seleccionado. "
                        "Marca '🗸 Mostrar también las sucursales/días sin diferencias' "
                        "si quieres ver todas."
                    )
                else:
                    st.caption(
                        f"Mostrando **{len(df_consol)}** sucursales. "
                        f"Para elegir qué fuente usar día por día, cambia al modo 'Por día'."
                    )

                    df_show = df_consol.copy()
                    df_show["total_pos"] = df_show["total_pos"].astype(int)
                    df_show["total_token"] = df_show["total_token"].astype(int)
                    df_show["diferencia"] = df_show["diferencia"].astype(int)

                    st.dataframe(
                        df_show,
                        use_container_width=True,
                        hide_index=True,
                        height=450,
                        column_config={
                            "sucursal_cc":     st.column_config.TextColumn("CC", width="small"),
                            "sucursal_nombre": st.column_config.TextColumn("Sucursal"),
                            "prefijo":         st.column_config.TextColumn("Prefijo", width="small"),
                            "dias_totales":    st.column_config.NumberColumn("Días en período", width="small"),
                            "dias_coinciden":  st.column_config.NumberColumn("Días ✅ ok", width="small"),
                            "dias_difieren":   st.column_config.NumberColumn("Días ⚠️ revisar", width="small"),
                            "total_pos":       st.column_config.NumberColumn("Total POS", format="$ %d"),
                            "total_token":     st.column_config.NumberColumn("Total Token", format="$ %d"),
                            "diferencia":      st.column_config.NumberColumn("Diferencia", format="$ %d"),
                        },
                    )

                    # Botones de descarga (consolidado)
                    st.markdown("##### 📥 Descargar consolidado por sucursal")
                    col_d1, col_d2 = st.columns(2)
                    nombre_periodo = ""
                    if rango and isinstance(rango, tuple) and len(rango) == 2:
                        nombre_periodo = f"_{rango[0].strftime('%Y%m')}"

                    with col_d1:
                        # CSV
                        csv_bytes = df_show.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                        st.download_button(
                            "📥 CSV (por sucursal-mes)",
                            data=csv_bytes,
                            file_name=f"diferencias_pos_token_sucursales{nombre_periodo}.csv",
                            mime="text/csv",
                            use_container_width=True,
                        )
                    with col_d2:
                        # Excel
                        buffer_xls = io.BytesIO()
                        df_show.to_excel(buffer_xls, index=False, engine="openpyxl",
                                          sheet_name="Por sucursal-mes")
                        st.download_button(
                            "📊 Excel (por sucursal-mes)",
                            data=buffer_xls.getvalue(),
                            file_name=f"diferencias_pos_token_sucursales{nombre_periodo}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                        )

                    # Resumen del período (totales globales del consolidado)
                    st.markdown("##### 🧮 Totales del período mostrado")
                    cc1, cc2, cc3 = st.columns(3)
                    cc1.metric(
                        "Total POS",
                        f"$ {int(df_show['total_pos'].sum()):,}".replace(",", "."),
                    )
                    cc2.metric(
                        "Total Token",
                        f"$ {int(df_show['total_token'].sum()):,}".replace(",", "."),
                    )
                    cc3.metric(
                        "Diferencia",
                        f"$ {int(df_show['diferencia'].sum()):,}".replace(",", "."),
                    )

            # ============================================================
            # MODO DETALLADO (por día) — el original
            # ============================================================
            else:
                # En modo detallado SÍ se ocultan los coincidentes por defecto
                if not mostrar_coincidencias:
                    df_filt = df_filt[df_filt["estado"] != "coincide"]

                if len(df_filt) == 0:
                    st.info(
                        "👍 No hay diferencias en el rango seleccionado. "
                        "Marca '🗸 Mostrar también las sucursales/días sin diferencias' "
                        "si quieres ver todo."
                    )
                else:
                    st.caption(
                        f"Mostrando **{len(df_filt)}** celdas (día × sucursal). "
                        f"La columna 'fuente_elegida' es la que el sistema usará "
                        f"para generar el plano final. Puedes cambiar cada valor."
                    )

                    # Editor con dropdowns para elegir fuente
                    df_editar = df_filt[[
                        "fecha", "sucursal_nombre", "prefijo",
                        "total_pos", "total_token", "diferencia",
                        "estado", "fuente_recomendada", "fuente_elegida",
                    ]].copy()

                    df_editar["fecha"] = pd.to_datetime(df_editar["fecha"]).dt.strftime("%Y-%m-%d")
                    df_editar["total_pos"] = df_editar["total_pos"].astype(int)
                    df_editar["total_token"] = df_editar["total_token"].astype(int)
                    df_editar["diferencia"] = df_editar["diferencia"].astype(int)

                    editado = st.data_editor(
                        df_editar,
                        use_container_width=True,
                        hide_index=True,
                        height=400,
                        disabled=[
                            "fecha", "sucursal_nombre", "prefijo",
                            "total_pos", "total_token", "diferencia",
                            "estado", "fuente_recomendada",
                        ],
                        column_config={
                            "fecha":              st.column_config.TextColumn("Fecha", width="small"),
                            "sucursal_nombre":    st.column_config.TextColumn("Sucursal"),
                            "prefijo":            st.column_config.TextColumn("Prefijo", width="small"),
                            "total_pos":          st.column_config.NumberColumn("Total POS", format="$ %d"),
                            "total_token":        st.column_config.NumberColumn("Total Token", format="$ %d"),
                            "diferencia":         st.column_config.NumberColumn("Diferencia", format="$ %d"),
                            "estado":             st.column_config.TextColumn("Estado"),
                            "fuente_recomendada": st.column_config.TextColumn("Recomendada"),
                            "fuente_elegida":     st.column_config.SelectboxColumn(
                                "✏️ Fuente elegida",
                                options=["pos", "token"],
                                required=True,
                                help="Elige qué fuente contabilizar para esta celda",
                            ),
                        },
                        key="editor_token",
                    )

                    # Descarga del detalle (sin las elecciones, datos crudos)
                    st.markdown("##### 📥 Descargar detalle por día")
                    nombre_periodo = ""
                    if rango and isinstance(rango, tuple) and len(rango) == 2:
                        nombre_periodo = f"_{rango[0].strftime('%Y%m')}"

                    col_dd1, col_dd2 = st.columns(2)
                    with col_dd1:
                        csv_det = df_editar.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                        st.download_button(
                            "📥 CSV (detalle por día)",
                            data=csv_det,
                            file_name=f"diferencias_pos_token_detalle{nombre_periodo}.csv",
                            mime="text/csv",
                            use_container_width=True,
                            key="dl_csv_detalle",
                        )
                    with col_dd2:
                        buffer_xd = io.BytesIO()
                        df_editar.to_excel(buffer_xd, index=False, engine="openpyxl",
                                            sheet_name="Detalle por día")
                        st.download_button(
                            "📊 Excel (detalle por día)",
                            data=buffer_xd.getvalue(),
                            file_name=f"diferencias_pos_token_detalle{nombre_periodo}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key="dl_xls_detalle",
                        )

                    # Aplicar las elecciones editadas al df_cmp original
                    # (sólo afecta las filas que están en el df filtrado)
                    if editado is not None:
                        # mapear (fecha_str, sucursal_nombre) → fuente_elegida
                        elecciones = {}
                        for _, r in editado.iterrows():
                            elecciones[(r["fecha"], r["sucursal_nombre"])] = r["fuente_elegida"]
                        # actualizar df_cmp en sesión
                        df_cmp_act = df_cmp.copy()
                        df_cmp_act["fecha_str"] = pd.to_datetime(df_cmp_act["fecha"]).dt.strftime("%Y-%m-%d")
                        df_cmp_act["fuente_elegida"] = df_cmp_act.apply(
                            lambda r: elecciones.get(
                                (r["fecha_str"], r["sucursal_nombre"]),
                                r["fuente_elegida"],
                            ),
                            axis=1,
                        )
                        df_cmp_act = df_cmp_act.drop(columns=["fecha_str"])
                        st.session_state["resultado_token"]["df_cmp"] = df_cmp_act
                        df_cmp = df_cmp_act

            # ----- Paso 2.5: Notas Crédito POS -----
            resultado_nc = res_tk.get("resultado_nc")
            if resultado_nc is not None:
                st.markdown("---")
                st.markdown("### 🔄 Notas Crédito POS")

                df_nc = resultado_nc.get("detalle_nc")
                df_omitidas = resultado_nc.get("nc_omitidas")
                nc_no_map = resultado_nc.get("nc_no_mapeadas", {})

                # Métricas
                cn1, cn2, cn3 = st.columns(3)
                cn1.metric(
                    "✅ NC contabilizables",
                    f"{len(df_nc) if df_nc is not None else 0:,}",
                )
                if df_nc is not None and len(df_nc):
                    total_nc = int(df_nc["total_bruto"].sum())
                else:
                    total_nc = 0
                cn2.metric(
                    "Total a devolver",
                    f"$ {total_nc:,.0f}".replace(",", "."),
                )
                cantidad_no_map = sum(len(v) for v in nc_no_map.values())
                cn3.metric(
                    "⚠️ Sin mapear",
                    f"{cantidad_no_map:,}",
                )

                if cantidad_no_map > 0:
                    st.warning(
                        f"Hay {cantidad_no_map} NC con prefijo que NO está mapeado "
                        f"en el maestro de sucursales. No se contabilizarán "
                        f"automáticamente. Prefijos: "
                        f"{', '.join(nc_no_map.keys())}"
                    )

                if df_omitidas is not None and len(df_omitidas) > 0:
                    total_omit = int(df_omitidas['total_bruto'].sum())
                    with st.expander(
                        f"📦 {len(df_omitidas)} NC omitidas sin prefijo "
                        f"(${total_omit:,}".replace(",", ".") + ") — "
                        f"se suben manualmente",
                        expanded=False,
                    ):
                        st.caption(
                            "Estas NC vienen sin prefijo en el Token DIAN. NO se "
                            "contabilizan automáticamente. El contador las sube "
                            "manualmente al sistema interno. Se muestran aquí solo "
                            "como referencia/control."
                        )
                        # Métricas por motivo
                        motivos = df_omitidas.groupby("motivo").agg(
                            docs=("folio", "count"),
                            total=("total_bruto", "sum"),
                        ).reset_index()
                        st.dataframe(motivos, hide_index=True, use_container_width=True)

                        st.markdown("**Detalle:**")
                        df_omit_show = df_omitidas.copy()
                        if hasattr(df_omit_show["fecha"].iloc[0] if len(df_omit_show) else None, "strftime"):
                            df_omit_show["fecha"] = pd.to_datetime(df_omit_show["fecha"]).dt.strftime("%Y-%m-%d")
                        df_omit_show["total_bruto"] = df_omit_show["total_bruto"].astype(int)
                        st.dataframe(
                            df_omit_show,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "fecha":        st.column_config.TextColumn("Fecha", width="small"),
                                "folio":        st.column_config.TextColumn("Folio"),
                                "nit_receptor": st.column_config.TextColumn("NIT"),
                                "cliente":      st.column_config.TextColumn("Cliente"),
                                "total_bruto":  st.column_config.NumberColumn("Total", format="$ %d"),
                                "motivo":       st.column_config.TextColumn("Motivo"),
                            },
                        )

                # Vista detallada vs consolidada
                if df_nc is not None and len(df_nc) > 0:
                    modo_nc = st.radio(
                        "Vista de Notas Crédito",
                        ["Por sucursal-mes (consolidado)", "Detalle por NC"],
                        horizontal=True,
                        key="modo_vista_nc",
                    )

                    if modo_nc == "Por sucursal-mes (consolidado)":
                        df_nc_consol = (
                            df_nc.groupby(
                                ["sucursal_cc", "sucursal_nombre", "prefijo"],
                                dropna=False,
                            ).agg(
                                docs=("folio", "count"),
                                total_devuelto=("total_bruto", "sum"),
                                base_total=("base_teorica", "sum"),
                                inc_total=("inc_teorico", "sum"),
                            ).reset_index()
                            .sort_values("total_devuelto", ascending=False)
                        )
                        df_nc_show = df_nc_consol.copy()
                        df_nc_show["total_devuelto"] = df_nc_show["total_devuelto"].astype(int)
                        df_nc_show["base_total"] = df_nc_show["base_total"].astype(int)
                        df_nc_show["inc_total"] = df_nc_show["inc_total"].astype(int)
                        st.dataframe(
                            df_nc_show,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "sucursal_cc":    st.column_config.TextColumn("CC", width="small"),
                                "sucursal_nombre":st.column_config.TextColumn("Sucursal"),
                                "prefijo":        st.column_config.TextColumn("Prefijo NC", width="small"),
                                "docs":           st.column_config.NumberColumn("# NC", width="small"),
                                "total_devuelto": st.column_config.NumberColumn("Total devuelto", format="$ %d"),
                                "base_total":     st.column_config.NumberColumn("Base", format="$ %d"),
                                "inc_total":      st.column_config.NumberColumn("INC", format="$ %d"),
                            },
                        )

                        # Descarga consolidada NC
                        col_nc1, col_nc2 = st.columns(2)
                        with col_nc1:
                            csv_nc = df_nc_show.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                            st.download_button(
                                "📥 CSV NC por sucursal",
                                data=csv_nc,
                                file_name="notas_credito_pos_sucursales.csv",
                                mime="text/csv",
                                use_container_width=True,
                                key="dl_csv_nc_consol",
                            )
                        with col_nc2:
                            buf = io.BytesIO()
                            df_nc_show.to_excel(buf, index=False, engine="openpyxl",
                                                sheet_name="NC por sucursal")
                            st.download_button(
                                "📊 Excel NC por sucursal",
                                data=buf.getvalue(),
                                file_name="notas_credito_pos_sucursales.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                                key="dl_xls_nc_consol",
                            )

                    else:
                        # Detalle por NC
                        df_nc_show = df_nc[[
                            "fecha", "prefijo", "folio", "sucursal_nombre",
                            "nit_receptor", "cliente",
                            "total_bruto", "base_teorica", "inc_teorico",
                        ]].copy()
                        df_nc_show["fecha"] = pd.to_datetime(df_nc_show["fecha"]).dt.strftime("%Y-%m-%d")
                        for c in ["total_bruto", "base_teorica", "inc_teorico"]:
                            df_nc_show[c] = df_nc_show[c].astype(int)
                        df_nc_show = df_nc_show.sort_values(["fecha", "prefijo", "folio"])
                        st.dataframe(
                            df_nc_show,
                            use_container_width=True,
                            hide_index=True,
                            height=400,
                            column_config={
                                "fecha":          st.column_config.TextColumn("Fecha", width="small"),
                                "prefijo":        st.column_config.TextColumn("Prefijo", width="small"),
                                "folio":          st.column_config.TextColumn("Folio", width="small"),
                                "sucursal_nombre":st.column_config.TextColumn("Sucursal"),
                                "nit_receptor":   st.column_config.TextColumn("NIT", width="small"),
                                "cliente":        st.column_config.TextColumn("Cliente"),
                                "total_bruto":    st.column_config.NumberColumn("Total", format="$ %d"),
                                "base_teorica":   st.column_config.NumberColumn("Base", format="$ %d"),
                                "inc_teorico":    st.column_config.NumberColumn("INC", format="$ %d"),
                            },
                        )

                        # Descarga detalle NC
                        col_nc1, col_nc2 = st.columns(2)
                        with col_nc1:
                            csv_nc = df_nc_show.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                            st.download_button(
                                "📥 CSV detalle NC",
                                data=csv_nc,
                                file_name="notas_credito_pos_detalle.csv",
                                mime="text/csv",
                                use_container_width=True,
                                key="dl_csv_nc_det",
                            )
                        with col_nc2:
                            buf = io.BytesIO()
                            df_nc_show.to_excel(buf, index=False, engine="openpyxl",
                                                sheet_name="Detalle NC")
                            st.download_button(
                                "📊 Excel detalle NC",
                                data=buf.getvalue(),
                                file_name="notas_credito_pos_detalle.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True,
                                key="dl_xls_nc_det",
                            )

                # Checkbox para incluir o no las NC en el plano final
                incluir_nc = st.checkbox(
                    "✏️ Incluir Notas Crédito en el plano final",
                    value=res_tk.get("incluir_nc", True),
                    help="Si activas, las NC POS se sumarán al plano contable con "
                         "asiento Db 41754001 (devoluciones), Db INC, Cr caja sucursal. "
                         "El comprobante es '498' (distinto del POS '497').",
                    key="chk_incluir_nc",
                )
                st.session_state["resultado_token"]["incluir_nc"] = incluir_nc

            # ----- Paso 3: generar plano final -----
            st.markdown("---")
            st.markdown("### 🎯 Generar plano final con las elecciones")

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                cuenta_token = (df_cmp["fuente_elegida"] == "token").sum()
                st.metric("Celdas que usarán Token", f"{cuenta_token:,}")
            with col_g2:
                cuenta_pos = (df_cmp["fuente_elegida"] == "pos").sum()
                st.metric("Celdas que usarán POS", f"{cuenta_pos:,}")

            generar_final = st.button(
                "✨ Generar plano final",
                type="primary",
                key="btn_generar_final",
            )

            if generar_final:
                with st.spinner("Generando plano final..."):
                    try:
                        sucursales = cargar_datos_punto_embebido()
                        df_final = aplicar_elecciones_al_plano(
                            plano_pos_actual, df_cmp, sucursales,
                        )

                        # Si el contador activó el checkbox, sumar las líneas NC
                        incluir_nc = res_tk.get("incluir_nc", False)
                        nc_lineas_agregadas = 0
                        nc_monto_agregado = 0
                        if incluir_nc and res_tk.get("resultado_nc"):
                            df_nc_detalle = res_tk["resultado_nc"].get("detalle_nc")
                            if df_nc_detalle is not None and len(df_nc_detalle) > 0:
                                df_lineas_nc = generar_lineas_nc_pos(
                                    df_nc_detalle, sucursales,
                                )
                                if len(df_lineas_nc) > 0:
                                    df_lineas_nc["VALOR"] = pd.to_numeric(
                                        df_lineas_nc["VALOR"], errors="coerce"
                                    ).fillna(0).astype(int)
                                    nc_lineas_agregadas = len(df_lineas_nc)
                                    nc_monto_agregado = int(
                                        df_lineas_nc[df_lineas_nc["TR"] == "2"]["VALOR"].sum()
                                    )
                                    df_final = pd.concat(
                                        [df_final, df_lineas_nc],
                                        ignore_index=True,
                                    )
                                    df_final = df_final.sort_values(
                                        ["FECHA", "CENTRO DE COSTO", "TR"]
                                    ).reset_index(drop=True)

                        st.session_state["resultado_token"]["df_final"] = df_final
                        st.session_state["resultado_token"]["nc_lineas_agregadas"] = nc_lineas_agregadas
                        st.session_state["resultado_token"]["nc_monto_agregado"] = nc_monto_agregado
                    except Exception as e:
                        st.error(f"❌ Error generando el plano final: {e}")
                        st.exception(e)
                        st.stop()

            df_final = res_tk.get("df_final")
            if df_final is not None and len(df_final) > 0:
                st.markdown("#### 📋 Plano final")

                # Mensaje si se incluyeron NC
                nc_agregadas = res_tk.get("nc_lineas_agregadas", 0)
                if nc_agregadas > 0:
                    st.info(
                        f"📌 Se incluyeron **{nc_agregadas}** líneas de Notas Crédito "
                        f"(devoluciones por $ {res_tk.get('nc_monto_agregado', 0):,.0f}"
                        .replace(",", ".") + ") en el plano final."
                    )

                df_final_int = df_final.copy()
                df_final_int["VALOR"] = pd.to_numeric(df_final_int["VALOR"], errors="coerce").fillna(0).astype(int)
                total_db = int(df_final_int[df_final_int["TR"] == "1"]["VALOR"].sum())
                total_cr = int(df_final_int[df_final_int["TR"] == "2"]["VALOR"].sum())

                c1, c2, c3 = st.columns(3)
                c1.metric("Líneas plano final", f"{len(df_final):,}")
                c2.metric("Total Db", f"$ {total_db:,.0f}".replace(",", "."))
                c3.metric("Total Cr", f"$ {total_cr:,.0f}".replace(",", "."))

                if total_db == total_cr:
                    st.success(
                        f"✅ Cuadre perfecto: Db = Cr = $ {total_db:,.0f}".replace(",", ".")
                    )
                else:
                    st.error(
                        f"❌ DESCUADRE: diferencia $ {total_db - total_cr:,.0f}".replace(",", ".")
                    )

                st.dataframe(df_final, use_container_width=True, height=400)

                # Descarga
                tsv_bytes = dataframe_a_plano_tsv(
                    df_final, incluir_encabezado_excel=incluir_enc_excel,
                )
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.download_button(
                        "📥 Descargar plano final (.txt)",
                        data=tsv_bytes,
                        file_name=f"plano_pos_conciliado_{nombre_plano}.txt",
                        mime="text/tab-separated-values",
                        type="primary",
                        use_container_width=True,
                    )
                with col_d2:
                    buffer = io.BytesIO()
                    df_final.to_excel(buffer, index=False, engine="openpyxl")
                    st.download_button(
                        "📊 Descargar como Excel",
                        data=buffer.getvalue(),
                        file_name=f"plano_pos_conciliado_{nombre_plano}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )

            if st.button("🔄 Procesar otro Token", key="reset_token"):
                st.session_state.pop("resultado_token", None)
                st.rerun()

    # ============================================================
    # REPORTE COMPARATIVO TOTAL POS vs DIAN
    # ============================================================
    st.markdown("---")
    st.markdown("### 📊 Reporte Comparativo Total — POS vs DIAN")
    st.caption(
        "Cuadro comparativo: lo reportado por POS vs lo emitido a DIAN "
        "(facturas - notas crédito). La diferencia debería ser ≈ $0. "
        "Si supera el umbral configurado, se marca como ALERTA."
    )

    with st.expander("ℹ️ ¿Cómo funciona este reporte?", expanded=False):
        st.markdown(
            "**Compara, por sucursal:**\n"
            "- **[A] POS reportado** = créditos de cuentas de venta en el plano POS\n"
            "- **[B] FE POS DIAN** = facturas electrónicas en el Token (prefijo POS)\n"
            "- **[C] NC POS DIAN** = notas crédito en el Token (prefijo NC POS)\n"
            "- **[D] NETO DIAN** = B − C\n"
            "- **[E] DIFERENCIA** = A − D\n\n"
            "**Idealmente E ≈ $0.** Si hay diferencias grandes, indica:\n"
            "- Ventas POS no facturadas electrónicamente\n"
            "- Diferencias de redondeo\n"
            "- Reportes POS que incluyen montos no facturables\n"
            "- Facturas DIAN no reflejadas en el POS"
        )

    try:
        from core.procesadores.reporte_comparativo_pos import (
            construir_reporte_comparativo, reporte_a_xlsx
        )
        _REPORTE_COMP_DISPONIBLE = True
    except Exception as _e_rep:
        _REPORTE_COMP_DISPONIBLE = False
        st.error(f"⚠️ El módulo de reporte comparativo no está disponible: {_e_rep}")

    if _REPORTE_COMP_DISPONIBLE:
        # Recoger inputs: plano POS y Token
        plano_disponible = st.session_state.get("df_plano_pos_actual")
        if plano_disponible is None:
            # buscar el plano en otras claves de sesión
            for key in ["resultado_pos_separado", "resultado_pos_unico", "resultado_token"]:
                if key in st.session_state and isinstance(st.session_state[key], dict):
                    if "df_plano" in st.session_state[key]:
                        plano_disponible = st.session_state[key]["df_plano"]
                        break
                    if "df" in st.session_state[key]:
                        plano_disponible = st.session_state[key]["df"]
                        break

        col_rep1, col_rep2 = st.columns(2)
        with col_rep1:
            archivo_token_rep = st.file_uploader(
                "📂 Excel del Token DIAN",
                type=["xlsx", "xls"],
                key="reporte_comp_token",
                help="Mismo Token DIAN del mes a comparar"
            )
        with col_rep2:
            if plano_disponible is not None and not plano_disponible.empty:
                st.success(f"✅ Plano POS detectado ({len(plano_disponible)} líneas)")
                usar_plano_sesion = True
            else:
                st.info("👆 Procesa primero el POS en las pestañas 1 o 2 (o sube el plano)")
                usar_plano_sesion = False
                plano_uploaded = st.file_uploader(
                    "📂 O sube un plano POS (.xlsx o .csv)",
                    type=["xlsx", "csv"],
                    key="reporte_comp_plano",
                )
                if plano_uploaded:
                    if plano_uploaded.name.lower().endswith(".xlsx"):
                        plano_disponible = pd.read_excel(plano_uploaded)
                    else:
                        plano_disponible = pd.read_csv(plano_uploaded)
                    st.success(f"✅ Plano cargado ({len(plano_disponible)} líneas)")

        col_per1, col_per2, col_per3 = st.columns(3)
        with col_per1:
            anio_rep = st.number_input(
                "Año", min_value=2020, max_value=2030,
                value=date.today().year, key="rep_anio"
            )
        with col_per2:
            mes_rep = st.selectbox(
                "Mes",
                options=list(range(1, 13)),
                index=max(0, date.today().month - 2),
                format_func=lambda m: [
                    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
                    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
                ][m-1],
                key="rep_mes",
            )
        with col_per3:
            umbral_alerta = st.number_input(
                "Umbral alerta ($)",
                min_value=0, value=50_000, step=10_000,
                key="rep_umbral",
                help="Si la diferencia supera este monto, se marca como alerta"
            )

        if st.button("📊 Generar reporte comparativo", type="primary",
                     key="generar_reporte_comp", disabled=archivo_token_rep is None or plano_disponible is None):
            with st.spinner("Generando reporte..."):
                try:
                    # Cargar datos_punto
                    import json
                    from pathlib import Path
                    dp_path = Path(__file__).resolve().parents[1] / "core" / "data" / "datos_punto.json"
                    with open(dp_path) as f:
                        datos_punto_json = json.load(f)

                    reporte = construir_reporte_comparativo(
                        df_plano_pos=plano_disponible,
                        fuente_token=archivo_token_rep.getvalue(),
                        datos_punto=datos_punto_json["sucursales"],
                        nit_empresa=str(emp.get("nit", "901038325")),
                        anio=int(anio_rep), mes=int(mes_rep),
                        umbral_alerta=float(umbral_alerta),
                    )
                    st.session_state["reporte_comp_resultado"] = reporte
                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    import traceback
                    with st.expander("Traceback"):
                        st.code(traceback.format_exc())

        # Mostrar resultado
        if "reporte_comp_resultado" in st.session_state:
            rep = st.session_state["reporte_comp_resultado"]
            totales = rep["totales"]

            st.markdown("---")

            # Alerta principal si descuadre
            if totales["alerta_total"]:
                st.error(
                    f"🔴 **ALERTA: Diferencia total significativa**\n\n"
                    f"La diferencia entre POS reportado y DIAN es de "
                    f"**${abs(totales['diferencia_total']):,.0f}**, que supera "
                    f"el umbral de ${rep['umbral_alerta']:,.0f}.\n\n"
                    f"⚠️ Esto NO debería pasar. Revisa las sucursales con mayor diferencia."
                )
            else:
                st.success(
                    f"✅ **Cuadre dentro del umbral**\n\n"
                    f"Diferencia total: ${totales['diferencia_total']:,.0f} "
                    f"(umbral: ${rep['umbral_alerta']:,.0f})"
                )

            # Métricas globales
            st.markdown("#### 💼 Totales globales")
            col_g1, col_g2, col_g3, col_g4, col_g5 = st.columns(5)
            col_g1.metric("[A] POS Reportado",       f"${totales['pos_total']:,.0f}")
            col_g2.metric("[B] FE POS DIAN",         f"${totales['fe_total']:,.0f}")
            col_g3.metric("[C] NC POS DIAN",         f"${totales['nc_total']:,.0f}")
            col_g4.metric("[D] Neto DIAN",           f"${totales['neto_dian_total']:,.0f}")
            col_g5.metric("[E] Diferencia",          f"${totales['diferencia_total']:,.0f}",
                          delta="🔴" if totales["alerta_total"] else "✅")

            # Tabla por sucursal
            st.markdown("#### 🏬 Por sucursal")
            df_rep = rep["df_comparativo"].copy()
            if len(df_rep) == 0 or "POS_REPORTADO" not in df_rep.columns:
                st.warning(
                    "⚠️ El comparativo se generó vacío. Esto suele pasar cuando "
                    "el Token y el plano POS no comparten ningún Centro de Costo. "
                    "Verifica que el período y los CC del plano coincidan con los del Token."
                )
            else:
                # Formato bonito de moneda (defensivo: solo columnas presentes)
                for col in ["POS_REPORTADO", "FE_DIAN", "NC_DIAN", "NETO_DIAN", "DIFERENCIA"]:
                    if col in df_rep.columns:
                        df_rep[col] = df_rep[col].apply(lambda v: f"${v:,.0f}" if pd.notna(v) else "—")
                st.dataframe(df_rep, use_container_width=True, hide_index=True)

            # Alertas detalladas
            if rep["alertas"]:
                st.markdown(f"#### 🚨 Sucursales con diferencias > umbral ({len(rep['alertas'])})")
                df_alertas = pd.DataFrame(rep["alertas"])
                df_alertas["diferencia"] = df_alertas["diferencia"].apply(lambda v: f"${v:,.0f}")
                st.dataframe(df_alertas, use_container_width=True, hide_index=True)

            # Prefijos huérfanos (STL, NC STL)
            if rep["fe_huerfanas"] or rep["nc_huerfanas"]:
                with st.expander("📦 Prefijos NO mapeados como POS (STL, etc.)", expanded=False):
                    st.caption("Estos prefijos están en el Token pero NO son del flujo POS. Son procesados aparte (ej. STL, DSE).")
                    df_huer = pd.DataFrame([
                        {"Tipo": "FE", "Prefijo": p, "Docs": d["docs"], "Total": f"${d['total']:,.0f}"}
                        for p, d in rep["fe_huerfanas"].items()
                    ] + [
                        {"Tipo": "NC", "Prefijo": p or "(sin prefijo)", "Docs": d["docs"], "Total": f"${d['total']:,.0f}"}
                        for p, d in rep["nc_huerfanas"].items()
                    ])
                    if len(df_huer):
                        st.dataframe(df_huer, use_container_width=True, hide_index=True)

            # Descarga
            st.markdown("---")
            st.markdown("#### 📥 Descargar reporte")
            xlsx_bytes = reporte_a_xlsx(rep)
            st.download_button(
                "📊 Descargar Excel completo",
                data=xlsx_bytes,
                file_name=f"reporte_comparativo_POS_DIAN_{rep['periodo']['anio']}-{rep['periodo']['mes']:02d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

            if st.button("🔄 Generar otro reporte", key="reset_reporte_comp"):
                st.session_state.pop("reporte_comp_resultado", None)
                st.rerun()


# ============================================================
# PESTAÑA 4: VENTAS STL (mayoristas)
# ============================================================

with tab_stl:
    if not _STL_DISPONIBLE:
        st.error(
            "🚫 **Módulo STL no disponible**\n\n"
            f"**Error:** `{_STL_ERROR}`\n\n"
            "Verifica que estos archivos existan en el repo:\n"
            "- `core/procesadores/procesador_stl.py`\n"
            "- `core/data/config_stl.json`"
        )
        if _STL_TRACEBACK:
            with st.expander("📋 Traceback completo", expanded=True):
                st.code(_STL_TRACEBACK, language="python")
        st.stop()

    st.markdown("### 🏢 Ventas STL — Flujo mayorista")
    st.caption(
        "Procesa las ventas STL (Jerónimo Martins, Éxito, Vaquita, Euro, etc.) "
        "y las NC STL (NC2xxx) directamente desde el Excel del Token DIAN. "
        "Detecta automáticamente las tarifas de IVA (19%, 5%, sin IVA, mixto) "
        "y genera el plano con discriminación por tarifa."
    )

    # Configuración cargada
    try:
        config_stl = cargar_config_stl()
    except Exception as e:
        st.error(f"❌ No se pudo cargar config_stl.json: {e}")
        st.stop()

    with st.expander("⚙️ Configuración actual (config_stl.json)", expanded=False):
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown(
                f"**Comprobante venta:** `{config_stl['comprobante_stl']}`  \n"
                f"**Comprobante NC:** `{config_stl['comprobante_nc_stl']}`  \n"
                f"**Centro de costos:** `{config_stl['cc_default']}`  \n"
                f"**Cartera (CxC):** `{config_stl['cta_cxc']}`  \n"
                f"**NIT empresa:** `{config_stl['nit_empresa']}`"
            )
        with col_b:
            st.markdown("**Cuentas por tarifa de IVA:**")
            for tarifa, ctas in config_stl["cuentas_por_tarifa_iva"].items():
                st.markdown(
                    f"- **{ctas['etiqueta']}**: Ingreso `{ctas['cta_ingreso']}`, "
                    f"IVA `{ctas['cta_iva'] or '—'}`, IVA Dev `{ctas.get('cta_iva_dev') or '—'}`"
                )
        st.caption(
            "Para editar: modifica `core/data/config_stl.json` y reinicia la app."
        )

    # Subir Token (obligatorio) + ZIP de XMLs (opcional, más preciso)
    st.markdown("---")
    st.markdown("### 📂 Cargar fuentes de datos")

    col_fuente1, col_fuente2 = st.columns(2)
    with col_fuente1:
        archivo_stl = st.file_uploader(
            "📄 Excel del Token DIAN (.xlsx)",
            type=["xlsx", "xls"],
            key="stl_token_uploader",
            help="Fuente base — calcula tarifas por estimación"
        )
    with col_fuente2:
        archivo_zip_xml = st.file_uploader(
            "📦 ZIP de XMLs DIAN (opcional, más preciso)",
            type=["zip"],
            key="stl_zip_xml_uploader",
            help="Si subes el ZIP de XMLs descargados manualmente del portal, "
                 "se procesarán línea por línea con tarifas REALES (sin estimación)."
        )

    # Mostrar info de qué se va a usar
    if archivo_zip_xml is not None:
        st.success(
            "🎯 **Modo preciso activado**: se usará el ZIP de XMLs (línea por línea con tarifas reales). "
            "El Token DIAN solo se usará para validación cruzada."
        )
    elif archivo_stl is not None:
        st.info(
            "📊 **Modo estándar**: se usará el Token DIAN. "
            "Para mayor precisión sube también el ZIP de XMLs (las tarifas se leerán línea por línea)."
        )

    if archivo_stl is None and archivo_zip_xml is None:
        st.info("👆 Sube al menos el Token DIAN para empezar.")
    else:
        # Selector de mes/año
        col_periodo1, col_periodo2 = st.columns(2)
        with col_periodo1:
            anio_stl = st.number_input(
                "Año", min_value=2020, max_value=2030, value=date.today().year,
                key="stl_anio",
            )
        with col_periodo2:
            mes_stl = st.selectbox(
                "Mes",
                options=list(range(1, 13)),
                index=max(0, date.today().month - 2),  # mes anterior por defecto
                format_func=lambda m: [
                    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
                    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
                ][m-1],
                key="stl_mes",
            )

        if st.button("🚀 Procesar STL del mes", type="primary", key="stl_procesar"):
            with st.spinner("Procesando..."):
                try:
                    if archivo_zip_xml is not None:
                        # Modo preciso: usar XMLs
                        from core.procesadores.procesador_stl import procesar_stl_desde_xmls
                        resultado_stl = procesar_stl_desde_xmls(
                            fuente_zip=archivo_zip_xml.getvalue(),
                            config=config_stl,
                            anio=int(anio_stl),
                            mes=int(mes_stl),
                        )
                    else:
                        # Modo estándar: usar Token
                        resultado_stl = procesar_stl(
                            fuente_token=archivo_stl.getvalue(),
                            config=config_stl,
                            anio=int(anio_stl),
                            mes=int(mes_stl),
                        )
                    st.session_state["resultado_stl"] = resultado_stl
                    st.session_state["resultado_stl_periodo"] = f"{int(anio_stl)}-{int(mes_stl):02d}"
                except Exception as e:
                    st.error(f"❌ Error procesando: {e}")
                    import traceback
                    st.code(traceback.format_exc())

        # Mostrar resultado si existe
        if "resultado_stl" in st.session_state:
            r = st.session_state["resultado_stl"]
            periodo = st.session_state.get("resultado_stl_periodo", "?")

            st.markdown("---")
            st.markdown(f"### 📊 Resultado — período {periodo}")

            # Fuente usada
            if r.get("fuente") == "xmls":
                st.success("🎯 Procesado desde **XMLs reales** (línea por línea, tarifas exactas)")
                if r.get("duplicados_zip", 0) > 0:
                    st.warning(
                        f"⚠️ El ZIP contenía {r['duplicados_zip']} XMLs duplicados "
                        f"(mismo folio repetido). Se ignoraron los duplicados."
                    )
            else:
                st.info("📊 Procesado desde **Token DIAN** (tarifas estimadas por aproximación)")

            # Métricas principales
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Facturas STL", r["metadatos"]["facturas_procesadas"])
            col2.metric("NC STL", r["metadatos"]["ncs_procesadas"])
            col3.metric("Líneas plano", r["metadatos"]["lineas_plano"])
            col4.metric(
                "Cuadre",
                "✅ Cuadra" if r["cuadre"]["cuadra"] else "❌ NO cuadra",
                delta=f"${r['cuadre']['diferencia']:,.2f}" if not r["cuadre"]["cuadra"] else None,
            )

            # Totales
            col_a, col_b = st.columns(2)
            col_a.metric("Total débitos",  f"${r['cuadre']['debitos']:,.0f}")
            col_b.metric("Total créditos", f"${r['cuadre']['creditos']:,.0f}")

            # Resumen por tarifa
            st.markdown("#### 🧾 Distribución por tarifa de IVA")
            rt = r["resumen_por_tarifa"]

            # Helper: lee una tarifa de forma defensiva
            def _t(key, campo, default=0):
                return (rt.get(key) or {}).get(campo, default)

            filas_rt = [
                {"Tarifa": "Sin IVA",
                 "Facturas": _t("sin_iva", "facs"),
                 "Base":     _t("sin_iva", "base"),
                 "IVA":      0},
                {"Tarifa": "IVA 19% puro",
                 "Facturas": _t("iva_19", "facs"),
                 "Base":     _t("iva_19", "base"),
                 "IVA":      _t("iva_19", "iva")},
                {"Tarifa": "IVA 5% puro",
                 "Facturas": _t("iva_5", "facs"),
                 "Base":     _t("iva_5", "base"),
                 "IVA":      _t("iva_5", "iva")},
                {"Tarifa": "Mixto (19% + s/IVA)",
                 "Facturas": _t("mixto", "facs"),
                 "Base":     "—",
                 "IVA":      "—"},
            ]
            # Mostrar INC 8% y "Otro" solo si tienen movimientos (solo
            # las trae el procesador desde XMLs; las STL puras de Token no)
            if _t("inc_8", "facs") or _t("inc_8", "iva"):
                filas_rt.append({
                    "Tarifa":   "INC 8%",
                    "Facturas": _t("inc_8", "facs"),
                    "Base":     _t("inc_8", "base"),
                    "IVA":      _t("inc_8", "iva"),
                })
            if _t("otro", "facs") or _t("otro", "iva"):
                filas_rt.append({
                    "Tarifa":   "Otro",
                    "Facturas": _t("otro", "facs"),
                    "Base":     _t("otro", "base"),
                    "IVA":      _t("otro", "iva"),
                })
            df_rt = pd.DataFrame(filas_rt)
            st.dataframe(df_rt, use_container_width=True, hide_index=True)

            # Resumen por cliente
            st.markdown("#### 👥 Por cliente")
            rc = r["resumen_por_cliente"]
            if rc:
                df_rc = pd.DataFrame([
                    {"NIT": nit,
                     "Cliente": datos["nombre"][:40],
                     "Facturas": datos["facturas"],
                     "$ Facturas": datos["total"],
                     "$ IVA": datos["iva"],
                     "NCs": datos["ncs"],
                     "$ NC": datos["total_nc"]}
                    for nit, datos in rc.items()
                ]).sort_values("$ Facturas", ascending=False)
                st.dataframe(df_rc, use_container_width=True, hide_index=True)

            # NC STL
            if r["resumen_nc"]["facs"] > 0:
                st.markdown("#### 📝 Notas crédito STL")
                st.info(
                    f"**{r['resumen_nc']['facs']} NC STL** detectadas — "
                    f"Total: **${r['resumen_nc']['total']:,.0f}** "
                    f"(IVA: ${r['resumen_nc']['iva']:,.0f}). "
                    f"Cada NC reversa la misma cuenta de venta original."
                )

            # Alertas
            if r["alertas"]:
                st.markdown("#### ⚠️ Alertas")
                st.warning(
                    f"Se detectaron {len(r['alertas'])} facturas con problemas "
                    f"(no se incluyeron en el plano)."
                )
                st.dataframe(pd.DataFrame(r["alertas"]),
                             use_container_width=True, hide_index=True)

            # Vista previa del plano
            with st.expander("👀 Vista previa del plano (primeras 30 líneas)", expanded=False):
                st.dataframe(r["plano"].head(30), use_container_width=True,
                             hide_index=True)

            # Descargas
            st.markdown("---")
            st.markdown("### 📥 Descargar plano")

            nombre_archivo = f"plano_STL_{periodo}"
            col_d1, col_d2, col_d3 = st.columns(3)
            with col_d1:
                st.download_button(
                    "📄 TXT (TAB)",
                    data=stl_plano_tsv(r["plano"]),
                    file_name=f"{nombre_archivo}.txt",
                    mime="text/tab-separated-values",
                    use_container_width=True,
                )
            with col_d2:
                st.download_button(
                    "📄 CSV (coma)",
                    data=stl_plano_csv(r["plano"]),
                    file_name=f"{nombre_archivo}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with col_d3:
                st.download_button(
                    "📊 Excel (con resumen)",
                    data=stl_plano_xlsx(r["plano"], resumen=r),
                    file_name=f"{nombre_archivo}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    use_container_width=True,
                )

            if st.button("🔄 Procesar otro mes", key="reset_stl"):
                st.session_state.pop("resultado_stl", None)
                st.session_state.pop("resultado_stl_periodo", None)
                st.rerun()
