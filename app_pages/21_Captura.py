"""
21_Captura.py — Captura manual de comprobantes contables en INTEGRAL.

Permite armar un documento de partida doble (egreso, causación de gasto,
recibo de caja, o cualquier comprobante) línea por línea, validar el cuadre
Db = Cr y guardarlo en cn_movimientos.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import date

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info, current_user
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from db.supabase_client import get_supabase
from core.contable import servicio_contable as cont
from core.contable import conceptos as cp
from core.contable import lector_factura as lector
from core.contable.pdf_comprobante import generar_pdf_comprobante


COLS_EDITOR = ["Cuenta", "Detalle", "NIT", "Débito", "Crédito", "Base", "Centro costo"]


def _lineas_vacias(n: int = 4) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Cuenta": "", "Detalle": "", "NIT": "", "Débito": 0, "Crédito": 0,
          "Base": 0, "Centro costo": ""} for _ in range(n)],
        columns=COLS_EDITOR,
    )


def _a_editor_df(lineas: list[dict]) -> pd.DataFrame:
    """Convierte las líneas de aplicar_concepto() al layout del editor."""
    filas = []
    for l in lineas:
        filas.append({
            "Cuenta": l.get("cuenta", ""),
            "Detalle": l.get("detalle", ""),
            "NIT": l.get("nit", ""),
            "Débito": l["valor"] if l["tr"] == "1" else 0,
            "Crédito": l["valor"] if l["tr"] == "2" else 0,
            "Base": l.get("base", 0),
            "Centro costo": "",
        })
    df = pd.DataFrame(filas, columns=COLS_EDITOR)
    return pd.concat([df, _lineas_vacias(1)], ignore_index=True)


def _prefill_factura(datos: dict):
    """Vuelca los datos de una factura leída en la cabecera de la Captura."""
    import streamlit as _st
    from datetime import date as _date
    _st.session_state["factura_leida"] = datos
    _st.session_state["cap_autoselect"] = True   # sugerir concepto según la factura
    if datos.get("nit"):
        _st.session_state["cap_nit"] = datos["nit"]
    if datos.get("numero"):
        _st.session_state["cap_doc"] = str(datos["numero"])
    nom = datos.get("nombre") or ""
    _st.session_state["cap_det"] = (f"Factura {datos.get('numero', '')} {nom}").strip()
    base_sug = datos.get("base") or max(0, int(datos.get("total", 0)) - int(datos.get("iva", 0)))
    _st.session_state["cap_base"] = int(base_sug)
    f = datos.get("fecha")
    if f and isinstance(f, str) and len(f) == 10:
        try:
            y, m, d = (int(x) for x in f.split("-"))
            _st.session_state["cap_fecha"] = _date(y, m, d)
        except Exception:
            pass


require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin", "operador"])
sb = get_supabase()

st.title("✍️ Captura de comprobantes")
st.caption(f"Empresa activa: **{emp['razon_social']}** · Partida doble → cn_movimientos")
st.markdown("---")

# Comprobantes típicos que se pueden crear de un clic si no existen
COMP_SUGERIDOS = [
    ("1", "Recibo de caja"),
    ("2", "Comprobante de egreso"),
    ("3", "Causación / factura de compra"),
    ("4", "Nota de contabilidad"),
]


# ============================================================
# Tipos de comprobante
# ============================================================
comprobantes = cont.listar_comprobantes(sb, emp["id"])

# --- Gestión de tipos de comprobante (en el cuerpo, dentro del flujo) ---
st.markdown("### 🧾 Tipos de comprobante")
with st.expander("➕ Crear / gestionar tipos de comprobante",
                 expanded=(len(comprobantes) == 0)):
    if comprobantes:
        st.dataframe(
            pd.DataFrame([{"Código": c["codigo"], "Nombre": c["nombre"]}
                         for c in comprobantes]),
            use_container_width=True, hide_index=True,
        )
    else:
        st.caption("Aún no tienes comprobantes. Créalos aquí para poder hacer el asiento.")

    cc1, cc2, cc3 = st.columns([1, 2, 1])
    with cc1:
        nc_cod = st.text_input("Código", key="nc_cod", placeholder="ej. 2")
    with cc2:
        nc_nom = st.text_input("Nombre", key="nc_nom", placeholder="ej. Comprobante de egreso")
    with cc3:
        st.write("")
        crear1 = st.button("➕ Crear / actualizar", key="btn_nc", use_container_width=True)

    if crear1:
        if nc_cod and nc_nom:
            try:
                cont.upsert_comprobante(sb, emp["id"], nc_cod, nc_nom)
                st.success(f"Comprobante {nc_cod} guardado.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo crear el comprobante (¿tu rol tiene permiso de admin?): {e}")
        else:
            st.warning("Código y nombre son obligatorios.")

    if st.button("⚡ Crear los 4 sugeridos (recibo de caja, egreso, causación, nota)",
                 key="btn_sug"):
        try:
            for cod, nom in COMP_SUGERIDOS:
                cont.upsert_comprobante(sb, emp["id"], cod, nom)
            st.success("Comprobantes sugeridos creados.")
            st.rerun()
        except Exception as e:
            st.error(f"No se pudieron crear (¿tu rol tiene permiso de admin?): {e}")

if not comprobantes:
    st.info("Crea al menos un tipo de comprobante arriba para empezar el asiento.")
    st.stop()


# ============================================================
# Estado de atajos
# ============================================================
st.session_state.setdefault("captura_ver", 0)
if "captura_lineas" not in st.session_state:
    st.session_state["captura_lineas"] = _lineas_vacias()


# ============================================================
# 📄 Leer factura (XML / PDF / imagen) — prellenar
# ============================================================
with st.expander("📄 Leer factura (XML DIAN · PDF · imagen · ZIP) para prellenar", expanded=False):
    st.caption("**Arrastra y suelta** aquí una o varias facturas (o un **ZIP**), o "
               "usa *Browse files*. Acepta XML de la DIAN, PDF, imagen y ZIP. "
               "Extraigo NIT, número, fecha, valores y el **régimen del proveedor** "
               "para sugerir la retención. El XML es exacto; PDF/imagen es mejor esfuerzo.")
    ups = st.file_uploader(
        "Arrastra y suelta las facturas o el ZIP",
        type=["xml", "pdf", "png", "jpg", "jpeg", "tiff", "tif", "webp", "zip"],
        accept_multiple_files=True, key="fac_file")
    if ups and st.button("📥 Leer y prellenar", key="btn_leer_fac"):
        try:
            facturas = []
            errores = []
            for f in ups:
                try:
                    facturas.extend(lector.leer_facturas(f.name, f.read()))
                except Exception as e:
                    errores.append(f"{f.name}: {e}")
            for msg in errores:
                st.warning(f"⚠️ {msg}")
            if not facturas:
                st.warning("No se encontraron facturas legibles en los archivos/ZIP.")
            elif len(facturas) == 1:
                _prefill_factura(facturas[0])
                st.rerun()
            else:
                st.session_state["facturas_multi"] = facturas
                st.session_state.pop("factura_leida", None)
                st.rerun()
        except Exception as e:
            st.error(f"No se pudo leer: {e}")

    multi = st.session_state.get("facturas_multi")
    if multi:
        st.info(f"📦 Se leyeron **{len(multi)}** facturas. Elige cuál cargar:")
        op = {
            f"{i+1}. {f.get('numero') or 's/n'} · NIT {f.get('nit') or '—'} · "
            f"$ {int(f.get('total', 0)):,}".replace(",", "."): i
            for i, f in enumerate(multi)
        }
        lbl = st.selectbox("Factura leída", list(op.keys()), key="fac_multi_sel")
        cM1, cM2 = st.columns([1, 1])
        with cM1:
            if st.button("✅ Usar esta factura", key="btn_use_multi"):
                _prefill_factura(multi[op[lbl]])
                st.session_state.pop("facturas_multi", None)
                st.rerun()
        with cM2:
            if st.button("✖️ Descartar", key="btn_drop_multi"):
                st.session_state.pop("facturas_multi", None)
                st.rerun()

    fl = st.session_state.get("factura_leida")
    if fl:
        st.success(
            f"Leída ({fl['formato']}, confianza **{fl['confianza']}**): "
            f"NIT {fl.get('nit') or '—'} · base $ {int(fl.get('base', 0)):,} · "
            f"IVA $ {int(fl.get('iva', 0)):,} · reteFte $ {int(fl.get('rete_fuente', 0)):,} · "
            f"total $ {int(fl.get('total', 0)):,}".replace(",", "."))
        reg = fl.get("regimen")
        if reg and reg.get("texto") and reg["texto"] != "Régimen no detectado":
            st.info(f"🏷️ Régimen del proveedor: **{reg['texto']}**")
        for a in fl.get("advertencias", []):
            st.warning("⚠️ " + a)


# ============================================================
# Cabecera del documento
# ============================================================
st.markdown("### 1️⃣ Cabecera")
st.session_state.setdefault("cap_fecha", date.today())
st.session_state.setdefault("cap_doc", "")
st.session_state.setdefault("cap_nit", "")
st.session_state.setdefault("cap_det", "")
st.session_state.setdefault("cap_base", 0)

c1, c2, c3 = st.columns(3)
with c1:
    opciones = {f"{c['codigo']} · {c['nombre']}": c["codigo"] for c in comprobantes}
    comp_label = st.selectbox("Comprobante", list(opciones.keys()), key="cap_comp")
    comp_cod = opciones[comp_label]
with c2:
    fecha = st.date_input("Fecha", key="cap_fecha", format="DD/MM/YYYY")
with c3:
    documento = st.text_input("Documento (consecutivo)", key="cap_doc")

c4, c5 = st.columns([1, 2])
with c4:
    nit_cab = st.text_input("NIT / tercero (opcional)", key="cap_nit")
with c5:
    detalle_cab = st.text_input("Detalle / concepto", key="cap_det")

periodo_cod = f"{fecha.year}{fecha.month:02d}"
if cont.periodo_protegido(sb, emp["id"], periodo_cod):
    st.error(f"🔒 El período {periodo_cod} está PROTEGIDO. No se puede grabar en esa fecha.")


# ============================================================
# ⚡ Concepto programado — autollenar las líneas
# ============================================================
st.markdown("### ⚡ Concepto programado")
_tablas_ok = cp.tablas_existen(sb, emp["id"])
conceptos_lst = cp.listar_conceptos(sb, emp["id"]) if _tablas_ok else []
if not _tablas_ok:
    st.info("Para usar conceptos programados corre la migración "
            "**016_conceptos_iva_retencion.sql** en Supabase (SQL Editor) y luego "
            "siembra el catálogo estándar en **🧩 Conceptos y tarifas** (menú Sistema). "
            "Mientras tanto puedes digitar las líneas abajo a mano.")
elif not conceptos_lst:
    st.info("Aún no hay conceptos. Créalos en **🧩 Conceptos y tarifas** (menú Sistema) "
            "o siembra el catálogo estándar desde allí.")
else:
    tipos_iva = cp.listar_tipos_iva(sb, emp["id"])
    tipos_ret = cp.listar_tipos_retencion(sb, emp["id"])
    iva_by = {t["codigo"]: t for t in tipos_iva}
    ret_by = {t["codigo"]: t for t in tipos_ret}

    c_op = {f"{c['codigo']} · {c['nombre']}": c for c in conceptos_lst}

    # Auto-selección del concepto según la factura recién leída
    if st.session_state.pop("cap_autoselect", False):
        fac = st.session_state.get("factura_leida") or {}
        sug = cp.sugerir_concepto(fac, conceptos_lst)
        if sug:
            for label, c in c_op.items():
                if c["codigo"] == sug:
                    st.session_state["cap_concepto"] = label
                    st.session_state["cap_concepto_sug"] = c["nombre"]
                    break

    cc1, cc2 = st.columns([3, 2])
    with cc1:
        c_lbl = st.selectbox("Concepto", list(c_op.keys()), key="cap_concepto")
        concepto = c_op[c_lbl]
    with cc2:
        base_val = st.number_input("Base gravable", min_value=0, step=1000, key="cap_base")
    _sug_nom = st.session_state.get("cap_concepto_sug")
    if _sug_nom and concepto.get("nombre") == _sug_nom:
        st.caption(f"🤖 Concepto sugerido automáticamente por la factura: **{_sug_nom}**")

    # Defaults sugeridos según el régimen del proveedor (si se leyó una factura)
    regimen = (st.session_state.get("factura_leida") or {}).get("regimen")
    iva_def, ret_def, notas_reg = cp.ajustar_por_regimen(concepto, tipos_ret, tipos_iva, regimen)
    for nota in notas_reg:
        st.caption("🏷️ " + nota)

    ci1, ci2 = st.columns(2)
    with ci1:
        iva_ops = ["(sin IVA)"] + [t["codigo"] for t in tipos_iva]
        iva_idx = iva_ops.index(iva_def) if iva_def in iva_ops else 0
        iva_sel = st.selectbox(
            "Tipo de IVA", iva_ops, index=iva_idx,
            format_func=lambda k: k if k == "(sin IVA)"
            else f"{k} · {iva_by[k]['tarifa']}%")
    with ci2:
        ret_sel = st.multiselect(
            "Retenciones", [t["codigo"] for t in tipos_ret],
            default=[r for r in ret_def if r in ret_by],
            format_func=lambda k: f"{k} · {ret_by[k]['tarifa']}% ({ret_by[k].get('base_calculo')})")

    # ¿La factura trae tarifas diferenciales de IVA? → desglose por tarifa
    bases_tar = (st.session_state.get("factura_leida") or {}).get("bases_por_tarifa") or []
    buckets_val = [b for b in bases_tar if int(b.get("base") or 0)]
    multi_tarifa = len(buckets_val) > 1
    tiva = iva_by.get(iva_sel) if iva_sel != "(sin IVA)" else None
    rets = [ret_by[r] for r in ret_sel]

    desglose = None
    if multi_tarifa and concepto.get("maneja_iva", True):
        st.info("🧾 Factura con **tarifas diferenciales de IVA**: se generarán bases "
                "separadas por tarifa.")
        st.dataframe(
            pd.DataFrame([{"Tarifa %": b["tarifa"], "Base": int(b["base"]),
                           "IVA": int(b["iva"])} for b in buckets_val]),
            use_container_width=True, hide_index=True,
            column_config={"Base": st.column_config.NumberColumn(format="%d"),
                           "IVA": st.column_config.NumberColumn(format="%d")})
        cta_por_tarifa = {float(t["tarifa"]): t.get("cuenta") for t in tipos_iva}
        cta_fallback = (tiva or {}).get("cuenta") or "240820"
        desglose = [{
            "tarifa": b["tarifa"], "base": int(b["base"]), "iva": int(b["iva"]),
            "cuenta": cta_por_tarifa.get(float(b["tarifa"])) or cta_fallback,
        } for b in buckets_val]

    # Base gravable e IVA estimado (para validar la base mínima de retención)
    if desglose:
        base_grav = sum(int(b["base"]) for b in desglose)
        iva_est = sum(int(b["iva"]) for b in desglose)
    else:
        base_grav = int(base_val)
        iva_est = int(base_val * float(tiva["tarifa"]) / 100) if tiva else 0

    # UVT del año (para la base mínima por normatividad)
    try:
        _val_anio = cont.obtener_valores_anuales(sb, fecha.year)
        uvt = int(float(_val_anio.get("uvt") or 0))
    except Exception:
        uvt = 0

    forzar_ret = False
    if rets:
        forzar_ret = st.checkbox(
            "Permitir retención aunque la base no alcance el mínimo "
            "(compra ligada a varias facturas del día que sí suman la base)",
            value=False, key="cap_forzar_ret")
        evaluacion = cp.evaluar_retenciones(base_grav, iva_est, rets, uvt=uvt, forzar=forzar_ret)
        for e in evaluacion:
            if e["aplicada"]:
                st.caption(f"⚖️ {e['codigo']}: aplica $ {e['valor']:,}".replace(",", "."))
            elif e["motivo"]:
                st.caption(f"⚖️ {e['codigo']}: **no se aplica** — {e['motivo']}. "
                           "Marca la casilla de arriba si esta compra es parte de varias del día.")
        if uvt == 0:
            st.caption("ℹ️ No encontré la UVT del año en el núcleo; no puedo validar la "
                       "base mínima. Verifica cn_valores_anuales.")

    # Vista previa del asiento
    prev = cp.aplicar_concepto(
        concepto, base_val, tipo_iva=tiva, retenciones=rets,
        nit=st.session_state.get("cap_nit", ""),
        detalle=st.session_state.get("cap_det", "") or (concepto.get("nombre") or ""),
        desglose_iva=desglose, uvt=uvt, forzar_retencion=forzar_ret)
    if prev:
        rp = cp.resumen_asiento(prev)
        st.caption(
            f"Vista previa: {len(prev)} líneas · Db $ {rp['debitos']:,} · Cr $ {rp['creditos']:,} · "
            f"{'cuadra ✅' if rp['cuadra'] else 'descuadra ⚠️'}".replace(",", "."))
    puede_generar = (base_val > 0) or bool(desglose)
    if st.button("⚡ Generar líneas del asiento", type="secondary",
                 key="btn_gen_concepto", disabled=not puede_generar):
        st.session_state["captura_lineas"] = _a_editor_df(prev)
        st.session_state["captura_ver"] += 1
        st.rerun()


# ============================================================
# Líneas (partida doble)
# ============================================================
st.markdown("### 2️⃣ Líneas")
st.caption("Escribe la cuenta y el valor en **Débito** o en **Crédito** (uno de los dos por línea). "
           "Si usaste un concepto, aquí aparecen las líneas ya armadas y editables.")

edit = st.data_editor(
    st.session_state["captura_lineas"],
    num_rows="dynamic",
    use_container_width=True,
    key=f"editor_captura_{st.session_state['captura_ver']}",
    column_config={
        "Cuenta": st.column_config.TextColumn(width="medium"),
        "Detalle": st.column_config.TextColumn(width="large"),
        "NIT": st.column_config.TextColumn(width="small"),
        "Débito": st.column_config.NumberColumn(format="%d", min_value=0),
        "Crédito": st.column_config.NumberColumn(format="%d", min_value=0),
        "Base": st.column_config.NumberColumn(format="%d", min_value=0),
        "Centro costo": st.column_config.TextColumn(width="small"),
    },
)

# Totales en vivo
df = edit.copy()
for col in ("Débito", "Crédito", "Base"):
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
lineas = df[(df["Cuenta"].astype(str).str.strip() != "") &
            ((df["Débito"] != 0) | (df["Crédito"] != 0))]

tot_db = int(lineas["Débito"].sum())
tot_cr = int(lineas["Crédito"].sum())
dif = tot_db - tot_cr

m1, m2, m3, m4 = st.columns(4)
m1.metric("Líneas", len(lineas))
m2.metric("Total débito", f"$ {tot_db:,}".replace(",", "."))
m3.metric("Total crédito", f"$ {tot_cr:,}".replace(",", "."))
m4.metric("Diferencia", f"$ {dif:,}".replace(",", "."))

# Validaciones
errores = []
ambas = lineas[(lineas["Débito"] != 0) & (lineas["Crédito"] != 0)]
if len(ambas):
    errores.append(f"{len(ambas)} línea(s) tienen débito Y crédito a la vez.")
if len(lineas) == 0:
    errores.append("No hay líneas con cuenta y valor.")
if dif != 0:
    errores.append(f"El comprobante no cuadra (diferencia $ {dif:,}).".replace(",", "."))

if dif == 0 and len(lineas) > 0 and not errores:
    st.success(f"✅ Cuadra: Db = Cr = $ {tot_db:,}".replace(",", "."))
else:
    for e in errores:
        st.warning(f"⚠️ {e}")


# ============================================================
# Guardar
# ============================================================
st.markdown("### 3️⃣ Guardar")
protegido = cont.periodo_protegido(sb, emp["id"], periodo_cod)
puede = (dif == 0 and len(lineas) > 0 and not errores and not protegido)

col_g1, col_g2, col_g3 = st.columns([2, 1, 1])
with col_g1:
    if st.button("💾 Guardar comprobante en INTEGRAL", type="primary",
                 disabled=not puede, use_container_width=True):
        # Construir el plano de 11 columnas
        filas = []
        for _, r in lineas.iterrows():
            es_db = int(r["Débito"]) != 0
            filas.append({
                "CUENTA": str(r["Cuenta"]).strip(),
                "COMPROBANTE": comp_cod,
                "FECHA": fecha,  # el servicio la convierte a ISO
                "DOCUMENTO": documento,
                "DOC REFERENCIA": documento,
                "NIT": str(r["NIT"]).strip() or nit_cab,
                "DETALLE": str(r["Detalle"]).strip() or detalle_cab,
                "TR": "1" if es_db else "2",
                "VALOR": int(r["Débito"]) if es_db else int(r["Crédito"]),
                "BASE": int(r["Base"]),
                "CENTRO DE COSTO": str(r["Centro costo"]).strip(),
            })
        df_plano = pd.DataFrame(filas, columns=cont.COLUMNAS_PLANO)
        try:
            usr = current_user() or {}
            n = cont.guardar_plano(
                sb, emp["id"], periodo_cod, df_plano,
                origen="captura", user_id=usr.get("id"), reemplazar=False,
            )
            st.success(
                f"✅ Comprobante {comp_cod}-{documento} guardado "
                f"({n} líneas, período {periodo_cod})."
            )
            # Limpiar para el siguiente documento
            st.session_state["captura_lineas"] = _lineas_vacias()
            st.session_state["captura_ver"] += 1
            st.rerun()
        except PermissionError as e:
            st.error(f"🔒 {e}")
        except Exception as e:
            st.error(f"No se pudo guardar: {e}")
with col_g2:
    if st.button("🧹 Limpiar líneas", use_container_width=True):
        st.session_state["captura_lineas"] = _lineas_vacias()
        st.session_state["captura_ver"] += 1
        st.rerun()
with col_g3:
    if len(lineas) > 0:
        comp_nombre = {c["codigo"]: c["nombre"] for c in comprobantes}.get(comp_cod, "")
        datos_pdf = {
            "empresa": emp["razon_social"], "nit_empresa": emp.get("nit"),
            "comprobante_cod": comp_cod, "comprobante_nombre": comp_nombre,
            "documento": documento or "(borrador)", "fecha": fecha,
            "periodo": periodo_cod, "detalle": detalle_cab,
            "lineas": [{
                "cuenta": str(r["Cuenta"]).strip(), "nombre": "",
                "nit": str(r["NIT"]).strip() or nit_cab,
                "detalle": str(r["Detalle"]).strip() or detalle_cab,
                "cc": str(r["Centro costo"]).strip(),
                "debito": int(r["Débito"]), "credito": int(r["Crédito"]),
            } for _, r in lineas.iterrows()],
            "total_debito": tot_db, "total_credito": tot_cr,
        }
        try:
            pdf_bytes = generar_pdf_comprobante(datos_pdf)
            st.download_button(
                "🖨️ Imprimir (PDF)", pdf_bytes,
                file_name=f"comprobante_{comp_cod}_{documento or 'borrador'}.pdf",
                mime="application/pdf", use_container_width=True, key="btn_print_cap")
        except Exception as e:
            st.caption(f"PDF no disponible: {e}")
    else:
        st.button("🖨️ Imprimir (PDF)", disabled=True, use_container_width=True,
                  key="btn_print_cap_dis")

if protegido:
    st.caption("🔒 Guardado deshabilitado: el período de la fecha está protegido.")

st.markdown("---")
st.caption(
    "Ejemplos: **Egreso** → Db gasto/pasivo, Cr banco. **Causación** → Db gasto + "
    "Db IVA, Cr proveedor + Cr retenciones. **Recibo de caja** → Db caja/banco, "
    "Cr cartera/ingreso. Todo se guarda en cn_movimientos y se ve en 📚 Contabilidad."
)
