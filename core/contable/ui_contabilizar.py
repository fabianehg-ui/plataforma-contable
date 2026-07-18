"""
core/contable/ui_contabilizar.py

Componente Streamlit REUSABLE para causar en la contabilidad desde cualquier
módulo. Un módulo genera su plano de 11 columnas y llama:

    from core.contable.ui_contabilizar import render_contabilizar
    render_contabilizar(sb, empresa, df_plano, origen="ventas")

Muestra: selector de período (año/mes), cuadre Db=Cr, opción de reemplazar lo
del módulo en ese período, y el botón de guardar. Devuelve True si guardó.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import streamlit as st

from core.contable import servicio_contable as cont
from core.contable import integracion as integ

_MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
          "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def render_contabilizar(sb, empresa, df_plano, origen: str,
                        titulo: str = "💾 Contabilizar en INTEGRAL",
                        key: Optional[str] = None,
                        anio_default: Optional[int] = None,
                        mes_default: Optional[int] = None) -> bool:
    """Bloque reusable de causación. Devuelve True si se guardó."""
    key = key or origen
    if df_plano is None or len(df_plano) == 0:
        return False

    st.markdown(f"#### {titulo}")
    st.caption(f"Módulo: **{integ.etiqueta_origen(origen)}** · queda en cn_movimientos "
               "(se ve en 📚 Contabilidad y 🔗 Centro Contable).")

    cua = integ.cuadre_plano(df_plano)
    c1, c2, c3 = st.columns(3)
    with c1:
        anio = st.number_input("Año del período", 2000, 2100,
                               value=anio_default or date.today().year, step=1,
                               key=f"{key}_ct_a")
    with c2:
        mes = st.selectbox("Mes del período", list(range(1, 13)),
                           format_func=lambda i: f"{i:02d} — {_MESES[i-1]}",
                           index=(mes_default or date.today().month) - 1,
                           key=f"{key}_ct_m")
    with c3:
        reemplazar = st.checkbox("Reemplazar lo de este módulo en el período",
                                 value=True, key=f"{key}_ct_rep",
                                 help="Evita duplicar si vuelves a causar el mismo mes.")
    periodo = f"{int(anio)}{int(mes):02d}"

    m1, m2, m3 = st.columns(3)
    m1.metric("Líneas", cua["lineas"])
    m2.metric("Débitos", f"$ {cua['debitos']:,}".replace(",", "."))
    m3.metric("Créditos", f"$ {cua['creditos']:,}".replace(",", "."))
    if cua["cuadra"]:
        st.success(f"✅ Cuadra: Db = Cr = $ {cua['debitos']:,}".replace(",", "."))
    else:
        st.warning(f"⚠️ El plano no cuadra (dif $ {cua['diferencia']:,}).".replace(",", "."))

    protegido = cont.periodo_protegido(sb, empresa["id"], periodo)
    if protegido:
        st.error(f"🔒 El período {periodo} está PROTEGIDO. No se puede causar.")

    guardado = False
    if st.button(f"💾 Contabilizar en período {periodo}", type="primary",
                 disabled=(not cua["cuadra"] or protegido), key=f"{key}_ct_save"):
        try:
            usr = {}
            try:
                from auth.login import current_user
                usr = current_user() or {}
            except Exception:
                usr = {}
            r = integ.contabilizar(sb, empresa["id"], periodo, df_plano, origen,
                                   user_id=usr.get("id"), reemplazar=reemplazar)
            st.success(f"✅ {r['insertados']} líneas causadas en INTEGRAL "
                       f"(período {periodo}, origen {integ.etiqueta_origen(origen)}).")
            guardado = True
        except PermissionError as e:
            st.error(f"🔒 {e}")
        except Exception as e:
            st.error(f"No se pudo contabilizar: {e}")
    return guardado
