"""
Certificados de Ventas Mensuales (JIPER / Milagros) - Plataforma Web

Flujo:
    1. (Opcional) Sube el/los informe(s) de ventas por CC (.xlsx, RESULTADOS)
       para traer el valor automaticamente.
    2. Elige el punto de venta y el mes.
    3. El valor llega solo del informe (editable) o se escribe a mano.
    4. Genera el certificado en PDF (para firma manual) o en Word.
    5. Boton de lote: genera TODOS los puntos del mes en un ZIP.

Contadora unica: Luz Aida Hernandez Garcia (T.P. 159803-T).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import io
import zipfile

import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_rol
from core.reportes.ventas_informe import cargar_ventas, combinar_ventas
from core.reportes import certificados_ventas as cert

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
# 1) Informe de ventas (para traer el valor automaticamente)
# ============================================================
st.markdown("### 1️⃣ Informe de ventas (opcional, para traer el valor)")
archivos = st.file_uploader(
    "Sube el informe administrativo por CC (.xlsx). Puedes subir varios meses.",
    type=["xlsx"], accept_multiple_files=True, key="cert_informes",
)

ventas = {}
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
    ventas = combinar_ventas(*dicts)
    if ventas:
        meses_disp = sorted({m for _c, m in ventas})
        st.success(
            f"Ventas cargadas: {len(ventas)} registros · "
            f"meses {', '.join(str(m) for m in meses_disp)}"
        )
    for e in errores:
        st.warning(e)

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
    import datetime
    anio = st.number_input("Año", min_value=2020, max_value=2100,
                           value=datetime.date.today().year, step=1)

pt = cert.punto_por_clave(clave)
mes_num = _MESES_NUM[mes_nom]
mes_texto_def = f"{mes_nom.upper()} DE {int(anio)}"

# valor automatico si hay informe y el punto tiene CC
valor_auto = None
cc4 = (pt or {}).get("cc4", "")
if ventas and cc4 and (cc4, mes_num) in ventas:
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
        st.caption(f"↑ Traído del informe para el CC {cc4}. Puedes ajustarlo.")
    elif cc4:
        st.caption(f"Sin dato en el informe para el CC {cc4} / mes {mes_num}. Escríbelo a mano.")
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

cga, cgb = st.columns(2)
with cga:
    if st.button("📄 Generar PDF", disabled=(not pdf_ok or not valor)):
        try:
            pdf = cert.generar_certificado_pdf(clave, mes_texto, valor)
            st.download_button(
                "⬇️ Descargar PDF", data=pdf,
                file_name=f"Certificado_{nombre_base}_{mes_nom}_{int(anio)}.pdf",
                mime="application/pdf",
            )
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude generar el PDF: {e}")
with cgb:
    if st.button("📝 Generar Word", disabled=(not valor)):
        docx = cert.generar_certificado_docx(clave, mes_texto, valor)
        st.download_button(
            "⬇️ Descargar Word", data=docx,
            file_name=f"Certificado_{nombre_base}_{mes_nom}_{int(anio)}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

# ============================================================
# 4) Lote: todos los puntos del mes
# ============================================================
st.markdown("### 4️⃣ Lote del mes (todos los puntos con venta)")
st.caption(
    "Genera un certificado por cada punto que tenga valor en el informe cargado, "
    "para el mes elegido arriba, y los descarga en un ZIP."
)

if st.button("📦 Generar lote del mes (ZIP)"):
    if not ventas:
        st.warning("Primero sube el informe de ventas para el lote automático.")
    else:
        buf = io.BytesIO()
        generados, saltados = 0, []
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in cert.PUNTOS:
                c4 = p.get("cc4", "")
                if not c4 or (c4, mes_num) not in ventas:
                    saltados.append(p["clave"])
                    continue
                v = float(ventas[(c4, mes_num)]["ventas"])
                if v <= 0:
                    saltados.append(p["clave"])
                    continue
                nb = p["clave"].replace(" ", "_").replace("(", "").replace(")", "")
                try:
                    if pdf_ok:
                        data = cert.generar_certificado_pdf(p["clave"], mes_texto_def, v)
                        z.writestr(f"Certificado_{nb}_{mes_nom}_{int(anio)}.pdf", data)
                    else:
                        data = cert.generar_certificado_docx(p["clave"], mes_texto_def, v)
                        z.writestr(f"Certificado_{nb}_{mes_nom}_{int(anio)}.docx", data)
                    generados += 1
                except Exception as e:  # noqa: BLE001
                    saltados.append(f"{p['clave']} ({e})")
        st.success(f"Generados {generados} certificados para {mes_nom} {int(anio)}.")
        if saltados:
            st.caption("Sin certificado (sin CC o sin venta): " + ", ".join(saltados))
        st.download_button(
            "⬇️ Descargar ZIP del mes", data=buf.getvalue(),
            file_name=f"Certificados_{mes_nom}_{int(anio)}.zip",
            mime="application/zip",
        )
