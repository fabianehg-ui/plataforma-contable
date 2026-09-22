"""
app_pages/19_Bancos_a_Contai.py
Sube los extractos bancarios en PDF, clasifica los GASTOS e INGRESOS bancarios,
los reparte en partes iguales entre los centros de costo elegidos y arma el
plano de Contai con la contrapartida contra la cuenta PUC del banco.

CONFIG-DRIVEN (multiempresa): los bancos, las reglas y los centros de costo se
configuran por empresa (tablas bancos_config / bancos_reglas / bancos_cc,
migración 020). Si la empresa no tiene bancos configurados, cae al modo clásico
(Bancolombia / Banco de Bogotá / BBVA) del procesador viejo.

Depende de: core/procesadores/extractos_bancarios_multi.py (nuevo)
            core/procesadores/extractos_bancarios.py     (clásico, fallback)
requirements.txt: pdfplumber
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Bancos a Contai", page_icon="🏦", layout="wide")
from auth.guard import guard_empresa
from core.procesadores import extractos_bancarios_multi as ebm
from core.procesadores import extractos_bancarios as eb_old

st.title("🏦 Bancos → gastos e ingresos → plano Contai")
emp, sb = guard_empresa()

bancos = ebm.cargar_bancos(sb, emp["id"])
reglas = ebm.cargar_reglas(sb, emp["id"])
centros = ebm.cargar_centros(sb, emp["id"])

tab_proc, tab_cfg = st.tabs(["🧾 Procesar extractos", "⚙️ Configuración de la empresa"])

# =====================================================================
# PROCESAR
# =====================================================================
with tab_proc:
    usar_config = bool(bancos)
    if usar_config:
        st.caption(f"Empresa **{emp['razon_social']}** · {len(bancos)} bancos configurados · "
                   f"{len(centros)} centros de costo para el reparto.")
        if not centros:
            st.warning("No hay centros de costo configurados para el reparto. "
                       "Ve a «Configuración de la empresa».")
    else:
        st.info("Esta empresa no tiene bancos configurados: se usa el **modo clásico** "
                "(Bancolombia, Banco de Bogotá, BBVA). Para Davivienda, Occidente, "
                "fiducuentas, etc., configúralos en «Configuración de la empresa».")

    pdfs = st.file_uploader("Extractos del mes (PDF, puedes subir varios)",
                            type=["pdf"], accept_multiple_files=True)

    if pdfs:
        movs, info = [], []
        for f in pdfs:
            try:
                if usar_config:
                    r = ebm.leer_extracto(f, bancos, reglas)
                    banco_nom = r["banco"]["nombre"] if r["banco"] else None
                else:
                    r0 = eb_old.leer_extracto(f)
                    banco_nom = r0["banco"]["nombre"] if r0["banco"] else None
                    r = {"movimientos": r0["movimientos"], "sin_clasificar": r0["sin_clasificar"]}
            except Exception as e:  # noqa: BLE001
                info.append({"archivo": f.name, "banco": "—", "clasificados": 0,
                             "sin clasificar": 0, "estado": f"error: {e}"})
                continue
            if not banco_nom:
                info.append({"archivo": f.name, "banco": "NO reconocido", "clasificados": 0,
                             "sin clasificar": 0, "estado": "revisa el 'detectar' del banco"})
                continue
            movs += r["movimientos"]
            info.append({"archivo": f.name, "banco": banco_nom,
                         "clasificados": len(r["movimientos"]),
                         "sin clasificar": r["sin_clasificar"], "estado": "ok"})

        st.dataframe(pd.DataFrame(info), use_container_width=True, hide_index=True)

        if movs:
            # ---- Resumen por concepto y cuenta bancaria (reporte) ----
            st.subheader("Resumen de gastos e ingresos por concepto y banco")
            _bcs, _filas = ebm.resumen_conceptos(movs)
            df_res = pd.DataFrame(_filas)
            _cols_num = [c for c in df_res.columns if c not in ("Concepto", "Cuenta", "Tipo")]
            st.dataframe(
                df_res.style.format({c: "{:,.2f}" for c in _cols_num}),
                use_container_width=True, hide_index=True,
            )
            try:
                import io as _io
                buf = _io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as xw:
                    df_res.to_excel(xw, index=False, sheet_name="Resumen")
                    pd.DataFrame(movs).to_excel(xw, index=False, sheet_name="Detalle")
                st.download_button("⬇ Descargar resumen (Excel)", data=buf.getvalue(),
                                   file_name="resumen_gastos_bancarios.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception:  # noqa: BLE001
                st.download_button("⬇ Descargar resumen (CSV)",
                                   data=df_res.to_csv(index=False).encode("utf-8-sig"),
                                   file_name="resumen_gastos_bancarios.csv", mime="text/csv")

            with st.expander("Ver movimientos clasificados"):
                st.dataframe(pd.DataFrame(movs), use_container_width=True, hide_index=True)

            st.subheader("Plano Contai")
            c = st.columns(4)
            comprobante = c[0].text_input("Comprobante", "10")
            documento = c[1].text_input("Documento", "1")
            f_asiento = c[2].date_input("Fecha del asiento",
                                        value=date(date.today().year, date.today().month, 1),
                                        format="MM/DD/YYYY")
            divisor = c[3].number_input("Divisor base IVA", value=0.19, step=0.01, format="%.2f")

            if usar_config:
                cc_proc = centros
                st.caption(f"Se repartirá entre {len(cc_proc)} centros de costo (config).")
            else:
                CC_DEF = ["001001", "001002", "001003", "001004"] + \
                    [f"0011{n:02d}" for n in range(1, 19)] + ["001300"] + \
                    [f"0012{n:02d}" for n in range(1, 8)]
                txt_cc = st.text_area("Centros de costo (uno por línea)", "\n".join(CC_DEF), height=120)
                cc_proc = [x.strip() for x in txt_cc.splitlines() if x.strip()]

            if st.button("Generar plano", type="primary", disabled=not cc_proc):
                if usar_config:
                    p = ebm.build_plano(movs, bancos, cc_proc, reglas, comprobante,
                                        documento, f_asiento.strftime("%m/%d/%Y"), divisor)
                    txt = ebm.plano_a_texto(p["filas"])
                    cols_plano = ebm.HDR
                else:
                    p = eb_old.build_plano(movs, cc_proc, comprobante, documento,
                                           f_asiento.strftime("%m/%d/%Y"), divisor)
                    txt = eb_old.plano_a_texto(p["filas"])
                    cols_plano = p["filas"][0]

                if p["cuadra"]:
                    st.success(f"Plano generado: {len(p['filas'])-1} líneas · "
                               f"Db = Cr = {p['debitos']:,.2f}")
                else:
                    st.error(f"DESCUADRE: Db {p['debitos']:,.2f} vs Cr {p['creditos']:,.2f}")
                st.dataframe(pd.DataFrame(p["filas"][1:], columns=cols_plano).head(25),
                             use_container_width=True, hide_index=True)
                st.download_button("⬇ Descargar plano.txt",
                                   data=txt.encode("latin-1", errors="replace"),
                                   file_name=f"plano_bancos_{f_asiento:%Y_%m}.txt",
                                   mime="text/plain")
        else:
            st.error("No se clasificó ningún movimiento (revisa las reglas de la empresa).")

# =====================================================================
# CONFIGURACIÓN
# =====================================================================
with tab_cfg:
    st.markdown("#### 🏦 Bancos de la empresa")
    st.caption("El **detectar** es un texto que aparezca en el extracto de ese banco "
               "(p.ej. el número de cuenta). El **formato** elige el lector. La "
               "**cuenta PUC** es la del banco (la contrapartida).")
    filas_b = bancos or [{"nombre": "", "detectar": "", "formato": "occidente",
                          "nit": "", "cuenta_puc": ""}]
    dfb = pd.DataFrame([{k: b.get(k, "") for k in
                         ["nombre", "detectar", "formato", "nit", "cuenta_puc"]} for b in filas_b])
    edb = st.data_editor(
        dfb, num_rows="dynamic", use_container_width=True, key="cfg_bancos",
        column_config={
            "nombre": st.column_config.TextColumn("Nombre", required=True),
            "detectar": st.column_config.TextColumn("Detectar (texto del extracto)", required=True),
            "formato": st.column_config.SelectboxColumn("Formato", options=ebm.FORMATOS, required=True),
            "nit": st.column_config.TextColumn("NIT banco"),
            "cuenta_puc": st.column_config.TextColumn("Cuenta PUC del banco", required=True),
        },
    )
    cbb = st.columns(2)
    if cbb[0].button("💾 Guardar bancos", type="primary"):
        n = ebm.guardar_bancos(sb, emp["id"], edb.to_dict("records"))
        st.success(f"{n} bancos guardados."); st.rerun()
    if cbb[1].button("🌱 Sembrar GRUPO DE LOLITA (bancos + reglas)"):
        nb, nr = ebm.sembrar_lolita(sb, emp["id"])
        st.success(f"Sembrados {nb} bancos y {nr} reglas de GRUPO DE LOLITA. "
                   "Revisa la cuenta PUC de cada banco y las cuentas de las reglas.")
        st.rerun()

    st.divider()
    st.markdown("#### 📋 Reglas de clasificación (lista blanca)")
    st.caption("El **orden manda**: gana la primera regla que casa. Lado: **D** gasto "
               "(débito concepto / crédito banco), **C** ingreso (débito banco / crédito "
               "concepto), **R** retención. **Base** = lleva base gravable (IVA).")
    filas_r = reglas or ebm.REGLAS_DEFECTO
    dfr = pd.DataFrame([{k: r.get(k, "") for k in
                         ["patron", "cuenta", "lado", "base", "etiqueta"]} for r in filas_r])
    edr = st.data_editor(
        dfr, num_rows="dynamic", use_container_width=True, key="cfg_reglas",
        column_config={
            "patron": st.column_config.TextColumn("Patrón (regex sobre la descripción)", required=True),
            "cuenta": st.column_config.TextColumn("Cuenta PUC", required=True),
            "lado": st.column_config.SelectboxColumn("Lado", options=["D", "C", "R"], required=True),
            "base": st.column_config.CheckboxColumn("Base IVA"),
            "etiqueta": st.column_config.TextColumn("Detalle"),
        },
    )
    cbr = st.columns(2)
    if cbr[0].button("💾 Guardar reglas", type="primary"):
        n = ebm.guardar_reglas(sb, emp["id"], edr.to_dict("records"))
        st.success(f"{n} reglas guardadas."); st.rerun()
    if cbr[1].button("🌱 Cargar reglas por defecto"):
        ebm.sembrar_reglas_defecto(sb, emp["id"])
        st.success("Reglas por defecto cargadas. Ajústalas si aplica."); st.rerun()

    st.divider()
    st.markdown("#### 🏷️ Centros de costo para el reparto (partes iguales)")
    st.caption("Cada gasto/ingreso se divide en partes iguales entre estos centros; "
               "el residuo lo absorbe el último para que el asiento cuadre.")
    try:
        from core.contable import servicio_contable as _cont
        cc_emp = [c["codigo"] for c in _cont.listar_centros_costo(sb, emp["id"])]
    except Exception:  # noqa: BLE001
        cc_emp = []
    if cc_emp:
        sel = st.multiselect("Elige los centros de costo", options=cc_emp,
                             default=[c for c in centros if c in cc_emp])
        extra = st.text_input("Agregar otros (separados por coma)", "")
        elegidos = list(dict.fromkeys(sel + [x.strip() for x in extra.split(",") if x.strip()]))
    else:
        txt = st.text_area("Centros de costo (uno por línea)", "\n".join(centros), height=120)
        elegidos = [x.strip() for x in txt.splitlines() if x.strip()]
    if st.button("💾 Guardar centros de costo", type="primary"):
        n = ebm.guardar_centros(sb, emp["id"], elegidos)
        st.success(f"{n} centros de costo guardados para el reparto."); st.rerun()
