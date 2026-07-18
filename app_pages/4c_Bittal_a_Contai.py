"""
app_pages/4c_Bittal_a_Contai.py

Pagina unica: elige informe + rango de fechas -> baja de bittal -> genera el
plano para Contai. Los informes vienen del registro core/bittal/reportes.py.

Credenciales: puedes escribirlas aqui (campos de abajo) o, si las dejas vacias,
se toman de st.secrets['bittal'] o de las variables de entorno BITTAL_*.
El login lo hace el conector (Playwright) en segundo plano; no hay que abrir
bittal a mano.
"""
import datetime as dt
import streamlit as st

from core.bittal.reportes import INFORMES, generar_plano
from core.bittal.cliente_bittal import BittalCreds

st.title("Bittal -> Contai")

# Informe (llaves del registro)
opciones = {v["nombre"]: k for k, v in INFORMES.items()}
nombre = st.selectbox("Informe", list(opciones.keys()))
informe_key = opciones[nombre]

c1, c2 = st.columns(2)
hoy = dt.date.today()
requiere_fechas = not INFORMES[informe_key].get("sin_fechas", False)
if requiere_fechas:
    fecha_ini = c1.date_input("Desde", value=hoy.replace(day=1))
    fecha_fin = c2.date_input("Hasta", value=hoy)
else:
    st.caption("Este informe descarga el listado completo; no usa rango de fechas.")
    fecha_ini = hoy.replace(day=1)
    fecha_fin = hoy

with st.expander("Credenciales de bittal", expanded=True):
    st.caption(
        "Si las dejas vacias, se usan las de st.secrets['bittal'] o las "
        "variables de entorno BITTAL_CODIGO_EMPRESA / BITTAL_USUARIO / BITTAL_PASSWORD."
    )
    cc1, cc2, cc3 = st.columns(3)
    codigo = cc1.text_input("Codigo / NIT empresa")
    usuario = cc2.text_input("Usuario")
    password = cc3.text_input("Contrasena", type="password")

if st.button("Generar plano", type="primary"):
    creds = None
    if codigo and usuario and password:
        creds = BittalCreds(codigo_empresa=codigo, usuario=usuario, password=password)
    try:
        with st.spinner("Conectando a bittal y generando..."):
            plano, log, resumen = generar_plano(
                informe_key, fecha_ini, fecha_fin, creds=creds
            )
        st.success("Plano generado.")
        with st.expander("Bitacora"):
            st.code("\n".join(log))
        if resumen:
            st.write("**Resumen**", resumen)

        salida = INFORMES[informe_key].get("salida") or {}
        ext = salida.get("ext", "txt")
        mime = salida.get("mime", "text/plain")
        base = salida.get("nombre", informe_key)
        etiqueta = salida.get("etiqueta", "Descargar plano para Contai")
        st.download_button(
            etiqueta,
            data=plano,
            file_name=f"{base}_{fecha_ini:%Y%m%d}_{fecha_fin:%Y%m%d}.{ext}",
            mime=mime,
        )

        # Opción: agregar al movimiento del mes (solo planos de texto Contai)
        if ext == "txt":
            from core.contable.integracion import plano_texto_a_df
            from core.contable.ui_contabilizar import render_contabilizar_activa
            st.markdown("---")
            render_contabilizar_activa(
                plano_texto_a_df(plano), "bittal",
                anio_default=fecha_fin.year, mes_default=fecha_fin.month)
    except NotImplementedError as e:
        st.warning(str(e))
    except Exception as e:
        st.error(f"Fallo: {e}")
