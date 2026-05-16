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
from core.procesadores.parser_token_dian import parsear_token_dian
from core.procesadores.comparador_pos_token import (
    comparar_pos_token,
    resumen_comparacion,
    aplicar_elecciones_al_plano,
)


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

tab_separado, tab_unico, tab_token = st.tabs([
    "1️⃣ Procesar (subir reportes por separado)",
    "2️⃣ Procesar (Excel todo en uno)",
    "3️⃣ Conciliar con Token DIAN",
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
                    "nombre_token": archivo_token.name,
                    "tolerancia": int(tolerancia),
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
                        st.session_state["resultado_token"]["df_final"] = df_final
                    except Exception as e:
                        st.error(f"❌ Error generando el plano final: {e}")
                        st.exception(e)
                        st.stop()

            df_final = res_tk.get("df_final")
            if df_final is not None and len(df_final) > 0:
                st.markdown("#### 📋 Plano final")

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
