"""
Certificados de Ventas Mensuales (JIPER / Milagros) - Plataforma Web

Fuente del valor (cualquiera de estas):
    A. Informe RESULTADOS por CC (.xlsx)  -> valor exacto por punto/mes.
    B. Resumen de ventas (imagen o Excel: NOMBRE + VALOR) -> se lee con OCR /
       Excel y se REVISA en una tabla editable antes de usar (el OCR puede
       confundir digitos).
    C. Manual: se escribe el valor a mano.

Genera el certificado en PDF (para firma manual) o Word, uno por uno o en lote.
Contadora unica: Luz Aida Hernandez Garcia (T.P. 159803-T).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import zipfile
import datetime

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from core.reportes.ventas_informe import cargar_ventas, combinar_ventas, _CATALOGO_CC
from core.reportes import certificados_ventas as cert
from core.reportes import resumen_ventas as resu

st.set_page_config(page_title="Certificados de Ventas", page_icon="📄", layout="wide")

require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
emp = require_rol(["admin", "operador", "consulta"])

st.title("📄 Certificados de Ventas Mensuales")
st.caption(
    f"Empresa activa: **{emp['razon_social']}** · "
    "Certificaciones JIPER y Milagros con el valor tomado del informe de ventas"
)
st.markdown("---")

_MESES_NUM = {
    "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
    "Julio": 7, "Agosto": 8, "Septiembre": 9, "Octubre": 10, "Noviembre": 11,
    "Diciembre": 12,
}
_MESES_LISTA = list(_MESES_NUM.keys())

# ============================================================
# 1) Fuente de las ventas
# ============================================================
st.markdown("### 1️⃣ ¿De dónde traigo el valor de las ventas?")

ventas_result = {}
with st.expander("📊 Opción A — Informe RESULTADOS por CC (.xlsx)", expanded=False):
    archivos = st.file_uploader(
        "Sube el informe administrativo por CC (.xlsx). Puedes subir varios meses.",
        type=["xlsx"], accept_multiple_files=True, key="cert_informes",
    )
    if archivos:
        dicts, errores = [], []
        for a in archivos:
            try:
                d = cargar_ventas(io.BytesIO(a.getvalue()))
                if d:
                    dicts.append(d)
                else:
                    errores.append(f"**{a.name}**: no encontré ventas (¿formato distinto?)")
            except Exception as e:  # noqa: BLE001
                errores.append(f"**{a.name}**: {e}")
        ventas_result = combinar_ventas(*dicts)
        if ventas_result:
            meses_disp = sorted({m for _c, m in ventas_result})
            st.success(f"Ventas cargadas: {len(ventas_result)} registros · "
                       f"meses {', '.join(str(m) for m in meses_disp)}")
        for e in errores:
            st.warning(e)

with st.expander("🖼️ Opción B — Resumen por imagen o Excel (con revisión)", expanded=True):
    st.caption(
        "Sube la **imagen** (pantallazo/foto) o el **Excel** del cuadro de ventas "
        "por punto. La plataforma lo lee y lo muestra abajo para que **revises y "
        "corrijas** antes de usarlo — el OCR puede confundir un dígito."
    )
    if not resu.ocr_disponible():
        st.info("Para leer imágenes se necesita tesseract en el servidor. "
                "El Excel sí funciona sin OCR.")
    arch_res = st.file_uploader(
        "Imagen (.png/.jpg) o Excel (.xlsx) del resumen de ventas",
        type=["png", "jpg", "jpeg", "xlsx"], key="cert_resumen",
    )
    if arch_res is not None:
        if st.button("🔍 Leer archivo", key="btn_leer_resumen"):
            try:
                filas = resu.leer_resumen(arch_res.getvalue(), arch_res.name)
                if not filas:
                    st.warning("No pude extraer filas. ¿La imagen está muy pequeña o borrosa?")
                else:
                    df = pd.DataFrame([
                        {"Punto (leído)": f["nombre"],
                         "CC": f["cc4"],
                         "Centro": _CATALOGO_CC.get(f["cc4"], ""),
                         "Valor": f["valor"]}
                        for f in filas
                    ])
                    st.session_state["cert_resumen_df"] = df
                    st.success(f"Leídas {len(filas)} filas. Revisa los valores abajo.")
            except Exception as e:  # noqa: BLE001
                st.error(f"No pude leer el archivo: {e}")

    if "cert_resumen_df" in st.session_state:
        st.caption("✏️ **Revisa y corrige** — sobre todo los valores. "
                   "Puedes ajustar el CC si algún punto quedó sin mapear.")
        df_edit = st.data_editor(
            st.session_state["cert_resumen_df"],
            num_rows="dynamic", use_container_width=True, key="cert_resumen_editor",
            column_config={
                "Valor": st.column_config.NumberColumn("Valor", format="%d"),
                "Centro": st.column_config.TextColumn("Centro", disabled=True),
            },
        )
        st.session_state["cert_resumen_df"] = df_edit

# reunir las filas revisadas (se convierten a ventas segun el mes elegido abajo)
filas_revisadas = []
if "cert_resumen_df" in st.session_state:
    for _, r in st.session_state["cert_resumen_df"].iterrows():
        filas_revisadas.append({"cc4": str(r.get("CC", "") or "").strip(),
                                "valor": r.get("Valor")})

# ============================================================
# 2) Datos del certificado
# ============================================================
st.markdown("### 2️⃣ Datos del certificado")

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    claves = [p["clave"] for p in cert.PUNTOS]
    clave = st.selectbox("Punto de venta", claves)
with col2:
    mes_nom = st.selectbox("Mes de la venta", _MESES_LISTA, index=6)
with col3:
    anio = st.number_input("Año", min_value=2020, max_value=2100,
                           value=datetime.date.today().year, step=1)

pt = cert.punto_por_clave(clave)
mes_num = _MESES_NUM[mes_nom]
mes_texto_def = f"{mes_nom.upper()} DE {int(anio)}"

# ventas combinadas: informe RESULTADOS + resumen revisado (para el mes elegido)
ventas = dict(ventas_result)
ventas.update(resu.filas_a_ventas(filas_revisadas, mes_num))

valor_auto = None
cc4 = (pt or {}).get("cc4", "")
if cc4 and (cc4, mes_num) in ventas:
    valor_auto = float(ventas[(cc4, mes_num)]["ventas"])

colv1, colv2 = st.columns([1, 1])
with colv1:
    valor = st.number_input(
        "Valor de la venta (antes de IVA)",
        min_value=0.0, step=1000.0,
        value=float(valor_auto) if valor_auto is not None else 0.0,
        format="%.0f",
    )
    if valor_auto is not None:
        st.caption(f"↑ Traído de las ventas para el CC {cc4}. Puedes ajustarlo.")
    elif cc4:
        st.caption(f"Sin dato para el CC {cc4} / mes {mes_num}. Escríbelo a mano.")
    else:
        st.caption("Este punto no está enlazado a un CC; escribe el valor a mano.")
with colv2:
    mes_texto = st.text_input("Texto del mes en el certificado", value=mes_texto_def)

if valor and valor > 0:
    st.info(
        f"**En letras:** {cert._titulo(cert.entero_en_letras(valor))} "
        f"{cert.peso_o_pesos(valor)} ML   ·   **$ {cert.formato_pesos(valor)}**"
    )

# ============================================================
# 3) Generar
# ============================================================
st.markdown("### 3️⃣ Generar certificado")

pdf_ok = cert.hay_pdf()
if not pdf_ok:
    st.warning(
        "Este servidor no tiene LibreOffice, así que solo puedo generar Word (.docx). "
        "Para PDF, instala LibreOffice en el servidor."
    )

nombre_base = clave.replace(" ", "_").replace("(", "").replace(")", "")

firmar = st.checkbox(
    "✍️ Incluir firma de Luz Aida (ya revisado)",
    value=False, disabled=(not cert.hay_firma()),
    help="Después de revisar el valor, marca esta casilla para que el certificado "
         "salga firmado. Si la dejas sin marcar, queda con la línea para firma manual.",
)
if not cert.hay_firma():
    st.caption("La imagen de la firma no está en el servidor "
               "(core/reportes/plantillas_certificados/firma_luz_aida.png).")

cga, cgb = st.columns(2)
with cga:
    if st.button("📄 Generar PDF", disabled=(not pdf_ok or not valor)):
        try:
            pdf = cert.generar_certificado_pdf(clave, mes_texto, valor, firmar=firmar)
            st.download_button(
                "⬇️ Descargar PDF", data=pdf,
                file_name=f"Certificado_{nombre_base}_{mes_nom}_{int(anio)}.pdf",
                mime="application/pdf",
            )
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude generar el PDF: {e}")
with cgb:
    if st.button("📝 Generar Word", disabled=(not valor)):
        docx = cert.generar_certificado_docx(clave, mes_texto, valor, firmar=firmar)
        st.download_button(
            "⬇️ Descargar Word", data=docx,
            file_name=f"Certificado_{nombre_base}_{mes_nom}_{int(anio)}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

# ============================================================
# 4) Lote: todos los puntos del mes
# ============================================================
st.markdown("### 4️⃣ Revisar todos los puntos y **firmar** el mes")
st.caption(
    f"Esta es la lista de certificados que se generarán para **{mes_nom} {int(anio)}** "
    "con su valor. Revisa cada valor; cuando estén bien, presiona **Firmar** y "
    "salen todos firmados en un ZIP."
)

# tabla de revision: un renglon por punto con su valor del mes
rev_rows = []
for p in cert.PUNTOS:
    c4 = p.get("cc4", "")
    v = 0.0
    if c4 and (c4, mes_num) in ventas:
        v = float(ventas[(c4, mes_num)]["ventas"])
    rev_rows.append({
        "Certificar": bool(v > 0),
        "Punto de venta": p["clave"],
        "Membrete": p["membrete"],
        "CC": c4,
        "Valor de la venta": float(v),
    })
df_rev = pd.DataFrame(rev_rows)

df_rev = st.data_editor(
    df_rev, use_container_width=True, hide_index=True, key="cert_lote_editor",
    column_config={
        "Certificar": st.column_config.CheckboxColumn("✓", help="Incluir este punto"),
        "Punto de venta": st.column_config.TextColumn("Punto de venta", disabled=True),
        "Membrete": st.column_config.TextColumn("Membrete", disabled=True),
        "CC": st.column_config.TextColumn("CC", disabled=True),
        "Valor de la venta": st.column_config.NumberColumn("Valor de la venta", format="%d"),
    },
)

n_marcados = int((df_rev["Certificar"] & (df_rev["Valor de la venta"] > 0)).sum())
firmar_lote = st.checkbox(
    "✍️ Firmar (insertar la firma de Luz Aida)", value=True,
    disabled=(not cert.hay_firma()),
    help="Marca esto para que salgan firmados. Sin marcar, quedan con línea para firma manual.",
)

if st.button(f"✍️ Firmar y generar {n_marcados} certificado(s) (ZIP)",
             type="primary", disabled=(n_marcados == 0)):
    buf = io.BytesIO()
    generados, saltados = 0, []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for _, row in df_rev.iterrows():
            if not row["Certificar"]:
                continue
            v = float(row["Valor de la venta"] or 0)
            clave_p = row["Punto de venta"]
            if v <= 0:
                saltados.append(clave_p)
                continue
            nb = clave_p.replace(" ", "_").replace("(", "").replace(")", "")
            try:
                if pdf_ok:
                    data = cert.generar_certificado_pdf(clave_p, mes_texto_def, v,
                                                        firmar=firmar_lote)
                    z.writestr(f"Certificado_{nb}_{mes_nom}_{int(anio)}.pdf", data)
                else:
                    data = cert.generar_certificado_docx(clave_p, mes_texto_def, v,
                                                         firmar=firmar_lote)
                    z.writestr(f"Certificado_{nb}_{mes_nom}_{int(anio)}.docx", data)
                generados += 1
            except Exception as e:  # noqa: BLE001
                saltados.append(f"{clave_p} ({e})")
    estado = "firmados" if firmar_lote else "generados"
    st.success(f"{generados} certificados {estado} para {mes_nom} {int(anio)}.")
    if saltados:
        st.caption("Sin generar: " + ", ".join(saltados))
    st.download_button(
        "⬇️ Descargar ZIP del mes", data=buf.getvalue(),
        file_name=f"Certificados_{mes_nom}_{int(anio)}.zip",
        mime="application/zip",
    )
