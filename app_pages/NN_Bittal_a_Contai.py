"""
app_pages/NN_Bittal_a_Contai.py  (ajusta el numero al orden de tu menu)

Pagina unica: elige informe + rango de fechas -> baja de bittal -> genera el
plano para Contai. Agregar informes nuevos NO toca esta pagina (vienen del
registro core/bittal/reportes.py).
"""
import datetime as dt
import streamlit as st

from core.bittal.reportes import INFORMES, generar_plano
from auth.guard import guard_empresa

st.title("Bittal → Contai")
emp, sb = guard_empresa()

# Seleccion de informe (las llaves del registro)
opciones = {v["nombre"]: k for k, v in INFORMES.items()}
nombre = st.selectbox("Informe", list(opciones.keys()))
informe_key = opciones[nombre]

c1, c2 = st.columns(2)
hoy = dt.date.today()
fecha_ini = c1.date_input("Desde", value=hoy.replace(day=1))
fecha_fin = c2.date_input("Hasta", value=hoy)

st.caption(
    "Credenciales de bittal en st.secrets['bittal'] (codigo_empresa, usuario, "
    "password). Para varias empresas, usa un bloque de secrets por empresa."
)

if st.button("Generar plano", type="primary"):
    try:
        with st.spinner("Conectando a bittal y generando..."):
            plano, log, resumen = generar_plano(informe_key, fecha_ini, fecha_fin)
        st.success("Plano generado.")
        with st.expander("Bitacora"):
            st.code("\n".join(log))
        if resumen:
            st.write("**Resumen**", resumen)
        st.download_button(
            "Descargar plano para Contai",
            data=plano,
            file_name=f"{informe_key}_{fecha_ini:%Y%m%d}_{fecha_fin:%Y%m%d}.txt",
            mime="text/plain",
        )
    except NotImplementedError as e:
        st.warning(str(e))
    except Exception as e:
        st.error(f"Fallo: {e}")
