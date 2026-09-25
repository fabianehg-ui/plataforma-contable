"""
app_pages/34_Estados_Financieros.py

ESTADOS FINANCIEROS NIIF — informe recurrente mensual (Grupo de Lolita).

Rellena la plantilla de EE.FF (que se maneja por SUMIF desde la hoja DATOS):
  · Balance del mes por NIT (año en curso)  -> hoja 'BCE 2026'
  · Balance del mismo mes del año anterior   -> hoja 'BCE 2025'
y deja que Excel recalcule (Estado de Resultados del mes y acumulado, ESF/
Balance, EFE, ECP, indicadores y notas — 2026 vs 2025 y acumulado del año).

Además ANEXA el resultado por centro de costo del mes (nivel amplio, con
desplegar/contraer), a partir del balance por NIT y CC, y lo memoriza para el
comparativo con el mes inmediatamente anterior.

Config: tabla eeff_resultado_cc (migración 025). Plantilla en plantillas/.
Depende de: core/eeff/eeff_niif.py · requirements: openpyxl
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Estados Financieros NIIF", page_icon="📊", layout="wide")
from auth.guard import guard_empresa
from core.eeff import eeff_niif as E

st.title("📊 Estados Financieros")
emp, sb = guard_empresa()
st.caption("Informe recurrente mensual: rellena la plantilla con el balance del mes "
           "y el del mismo mes del año anterior, y recalcula todos los estados. El "
           "balance se sube en pesos; cada plantilla usa su unidad automáticamente "
           "(la administrativa trabaja en miles, se convierte solo).")

# ------------------------------------------------------------------ 0. tipo de informe
st.markdown("#### 1. Tipo de informe")
tipo = st.radio("¿Qué informe generas?", list(E.PLANTILLAS.keys()),
                format_func=lambda t: E.PLANTILLAS[t]["titulo"], horizontal=True)
cfg = E.PLANTILLAS[tipo]
st.caption(cfg["descripcion"])
# El informe nativo (administrativo) no usa plantilla; solo el fiscal la necesita.
PLANTILLA_DEF = (ROOT / "plantillas" / cfg["archivo"]) if cfg.get("archivo") else None

# ------------------------------------------------------------------ 1. periodo
st.markdown("#### 2. Periodo")
hoy = date.today()
c = st.columns(3)
mes = c[0].selectbox("Mes", list(range(1, 13)), index=hoy.month - 2 if hoy.month > 1 else 0,
                     format_func=lambda m: f"{m:02d} — {E.MESES[m]}")
anio = c[1].number_input("Año", min_value=2020, max_value=2100, value=hoy.year, step=1)
anio_comp = c[2].number_input("Año comparativo", min_value=2019, max_value=2099,
                              value=int(anio) - 1, step=1)
periodo = f"{int(anio):04d}-{int(mes):02d}"

es_nativo = bool(cfg.get("nativo"))

# ------------------------------------------------------------------ 3. archivos
st.markdown("#### 3. Balance de prueba (por NIT y centro de costo)")
if es_nativo:
    st.caption("Sube el balance de prueba **por NIT y centro de costo** del año en "
               "curso, en PESOS. Opcional: el balance del año anterior (comparativo) "
               "y los informes de cartera del paquete administrativo para el "
               "comparativo vs contabilidad en la hoja OBSERVACIONES.")
    bp_act = st.file_uploader(f"Balance {int(anio)}", type=["xlsx", "xls"], key="bp_act")
    bp_ant = st.file_uploader(f"Balance {int(anio_comp)} (comparativo, opcional)",
                              type=["xlsx", "xls"], key="bp_ant")
    cc3 = st.columns(2)
    cart_cli = cc3[0].file_uploader("Cartera de CLIENTES (Análisis por NIT) — opcional",
                                    type=["xlsx", "xls"], key="cart_cli")
    cart_prov = cc3[1].file_uploader("Cartera de PROVEEDORES/ACREEDORES — opcional",
                                     type=["xlsx", "xls"], key="cart_prov")
    inv_costo = st.file_uploader(
        "Estado del Costo por punto de venta (traslado del costo) — opcional",
        type=["xlsx", "xls"], key="inv_costo",
        help="El inventario del balance viene casi todo global; con este archivo el "
             "inventario inicial, compras e inventario final POR CENTRO DE COSTO del "
             "juego de inventarios se toman reales (columnas CC | PUNTO DE VENTA | "
             "INVENTARIO INICIAL | (+) COMPRAS | (−) INV. FINAL | (=) COSTO).")
    with st.expander("📚 Meses anteriores del año (informe antiguo) — opcional"):
        st.caption("Sube el INFORME ANTIGUO (el Excel del paquete administrativo con la "
                   "hoja «2.E.R.I. MES-ACUMULADO») para SEMBRAR los meses ya trabajados "
                   "del año (p.ej. enero a junio) como columnas mes a mes en el "
                   "resultado. Solo se toman los meses ANTERIORES al que estás generando; "
                   "los que ya estén en memoria no se duplican. Marca la casilla si "
                   "además quieres dejarlos guardados en memoria para las próximas veces.")
        informe_ant = st.file_uploader("Informe antiguo (.xlsx) con «2.E.R.I. MES-ACUMULADO»",
                                       type=["xlsx"], key="informe_ant")
        sembrar_mem = st.checkbox("Guardar los meses sembrados en memoria", value=True,
                                  key="sembrar_mem")
    tpl_up = None
else:
    st.caption("Sube el balance de prueba **por NIT y centro de costo** de cada año, en "
               "PESOS. El mismo archivo alimenta todo el informe (los estados se colapsan "
               "por NIT). La conversión a miles, cuando aplica, es automática.")
    c2 = st.columns(2)
    bp_act = c2[0].file_uploader(f"Balance {int(anio)}", type=["xlsx", "xls"], key="bp_act")
    bp_ant = c2[1].file_uploader(f"Balance {int(anio_comp)}", type=["xlsx", "xls"], key="bp_ant")
    with st.expander("⚙️ Plantilla del informe (opcional)"):
        st.caption(f"Por defecto se usa la plantilla «{cfg['titulo']}» incluida en el "
                   "sistema. Puedes subir otra plantilla con la misma estructura "
                   "(hoja DATOS que mapea por SUMIF contra las hojas de balance).")
        tpl_up = st.file_uploader("Plantilla (.xlsx)", type=["xlsx"], key=f"tpl_up_{tipo}")

st.divider()

# ------------------------------------------------------------------ 4. generar
st.markdown("#### 4. Generar el informe")
if es_nativo:
    puede = bp_act is not None
else:
    puede = bp_act is not None and bp_ant is not None and (PLANTILLA_DEF.exists() or tpl_up is not None)
if st.button("📊 Generar informe", type="primary", disabled=not puede):
    try:
        balance = bp_act.getvalue()   # universal por NIT y CC (año en curso)
        if es_nativo:
            # MEMORIA: cargar los meses anteriores del año ya guardados
            historia = E.cargar_eri_historia(sb, emp["id"], int(anio), periodo)
            # El informe antiguo se pasa a generar: de él se extrae el resultado
            # POR CENTRO DE COSTO de los meses previos (enero..mes-1).
            rn = E.generar_pyg_nativo(
                balance, mes=int(mes), anio=int(anio),
                cartera=cart_cli.getvalue() if cart_cli is not None else None,
                cxp=cart_prov.getvalue() if cart_prov is not None else None,
                bp_ant=bp_ant.getvalue() if bp_ant is not None else None,
                anio_comp=int(anio_comp), historia=historia,
                informe_hist=informe_ant.getvalue() if informe_ant is not None else None,
                inventario=inv_costo.getvalue() if inv_costo is not None else None)
            # SEMBRAR en memoria los meses extraídos (por CC) para no volver a subir el informe
            n_sembrados = 0
            if sembrar_mem:
                for p, d in (rn.get("historia_seed") or {}).items():
                    try:
                        E.guardar_eri_mensual(sb, emp["id"], p, d)
                        n_sembrados += 1
                    except Exception:  # noqa: BLE001
                        pass
            # MEMORIA: guardar el mes en curso para el próximo informe
            n_guard = 0
            try:
                n_guard = E.guardar_eri_mensual(sb, emp["id"], rn["periodo"], rn["leafdata"])
            except Exception:  # noqa: BLE001
                pass
            res = {"bytes": rn["bytes"], "n_actual": rn["n_cuentas"], "n_anterior": 0,
                   "es_xlsm": rn.get("es_xlsm", False),
                   "anexo": {"n_links": rn["n_detalles"], "n_bloques": rn["n_detalles"],
                             "base_reparto": "ventas por CC", "meses": rn.get("meses", []),
                             "n_sembrados": n_sembrados,
                             "reparto_sin_cc": rn.get("reparto_acum", 0)}}
        else:
            template = tpl_up.getvalue() if tpl_up is not None else PLANTILLA_DEF.read_bytes()
            res = E.generar_informe(template, balance, bp_ant.getvalue(),
                                    mes=int(mes), anio=int(anio),
                                    bp_cc=balance,           # el mismo balance arma el anexo
                                    anio_comp=int(anio_comp), tipo=tipo)
        st.session_state["eeff_bytes"] = res["bytes"]
        st.session_state["eeff_meta"] = dict(periodo=periodo, tipo=tipo,
                                             n_act=res["n_actual"], n_ant=res["n_anterior"],
                                             es_xlsm=res.get("es_xlsm", False),
                                             anexo=res.get("anexo"))
        st.session_state["eeff_tot_cc"] = (E.totales_cc_por_clase(E.leer_bp(balance))
                                           if cfg.get("muestra_cc") else None)
    except Exception as e:  # noqa: BLE001
        st.error(f"No pude generar el informe: {e}")
        st.exception(e)

by = st.session_state.get("eeff_bytes")
if by:
    meta = st.session_state.get("eeff_meta", {})
    tcfg = E.PLANTILLAS.get(meta.get("tipo", "fiscal"), cfg)
    _pref = {"fiscal": "EEFF_Fiscal", "administrativo": "Balance_PyG_Admin",
             "pyg_nativo": "PyG_por_CC"}
    pref = _pref.get(meta.get("tipo"), "Informe")
    if tcfg.get("nativo"):
        st.success(f"«{tcfg['titulo']}» generado desde el balance: {meta.get('n_act')} "
                   "cuentas de resultado por centro de costo (mes y acumulado).")
    else:
        st.success(f"«{tcfg['titulo']}» generado. Balance {int(anio)}: {meta.get('n_act')} "
                   f"cuentas · Balance {int(anio_comp)}: {meta.get('n_ant')} cuentas. "
                   "Ábrelo en Excel: recalcula solo al abrir.")
    _xlsm = bool(meta.get("es_xlsm"))
    _ext = "xlsm" if _xlsm else "xlsx"
    _mime = ("application/vnd.ms-excel.sheet.macroEnabled.12" if _xlsm
             else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button(f"📥 {tcfg['titulo']} (Excel{' con macro' if _xlsm else ''})", by,
                       file_name=f"{pref}_{meta.get('periodo','')}_Grupo_de_Lolita.{_ext}",
                       mime=_mime, type="primary")
    if _xlsm:
        st.caption("📌 Es un libro **habilitado para macros (.xlsm)**: al abrirlo, "
                   "**Habilita las macros** y luego haz **clic en el número del mes** de "
                   "cualquier cuenta para que el detalle se filtre solo por esa cuenta "
                   "(centro de costo, NIT y terceros).")
    if tcfg.get("nativo") and meta.get("anexo"):
        ax = meta["anexo"]
        _ms = ax.get("meses", [])
        if _ms:
            st.caption(f"Resultado mes a mes: {', '.join(_ms)} "
                       f"(el último es el mes en curso, con centros de costo desplegables).")
        if ax.get("n_sembrados"):
            st.caption(f"📚 Sembré {ax['n_sembrados']} mes(es) del informe antiguo en la "
                       "memoria de la repo; ya no hará falta volver a subirlo. Cada mes "
                       "nuevo que generes se agrega solo a la secuencia.")
        st.caption(f"Incluye TODAS las cuentas de ingreso, costo y gasto por centro de "
                   f"costo (desplegar/contraer), con **clic al detalle por tercero** "
                   f"({ax.get('n_bloques', 0)} desgloses). Lo que no mueve CC (la 43 de "
                   f"intereses) se reparte proporcional a las ventas.")
    if tcfg.get("drill_cc") and meta.get("anexo"):
        ax = meta["anexo"]
        st.caption(f"En la hoja del P&G por centro de costo, las cuentas 5, 42, 43 y "
                   f"la fila de Compras (14) del mes actual se **calculan por CC** y "
                   f"quedan con **clic al detalle por tercero** ({ax.get('n_links', 0)} "
                   f"enlaces). El valor sin centro de costo se reparte entre los CC "
                   f"proporcional a las ventas ({ax.get('base_reparto','')}); reparto "
                   f"del mes: {ax.get('reparto_sin_cc',0):,.0f} (miles). La 41 se deja igual.")

    # ---- resultado por CC + comparativo mes anterior ----
    tot = st.session_state.get("eeff_tot_cc")
    if tot:
        st.markdown("##### Resultado por centro de costo del mes (miles de pesos)")
        prev = E.cargar_resultado_cc(sb, emp["id"], E.periodo_anterior(periodo))
        filas = []
        for cc, v in tot.items():
            uant = float(prev.get(cc, {}).get("utilidad", 0)) if prev else None
            fila = {"Centro de costo": v["nombre"],
                    "Ingresos": v["ingresos"] / 1000, "Costos": v["costos"] / 1000,
                    "Gastos": v["gastos"] / 1000, "Utilidad mes": v["utilidad"] / 1000}
            if prev:
                fila["Utilidad mes ant."] = uant / 1000
                fila["Variación"] = (v["utilidad"] - uant) / 1000
            filas.append(fila)
        df = pd.DataFrame(filas)
        numcols = [c for c in df.columns if c != "Centro de costo"]
        st.dataframe(df.style.format({c: "{:,.0f}" for c in numcols}),
                     hide_index=True, use_container_width=True)
        if not prev:
            st.caption(f"No hay resultado guardado de {E.periodo_anterior(periodo)}; "
                       "guarda este mes para tener el comparativo el próximo.")

        if st.button(f"💾 Guardar resultado por CC de {periodo} (memoria)"):
            try:
                n = E.guardar_resultado_cc(sb, emp["id"], periodo, tot)
                st.success(f"Guardado el resultado por CC de {periodo} ({n} centros). "
                           "Se usará como comparativo del mes siguiente.")
            except Exception as e:  # noqa: BLE001
                st.error(f"No pude guardar: {e}")
