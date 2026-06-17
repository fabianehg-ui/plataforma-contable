"""
core/bittal/cliente_bittal.py

Conector genérico Bittal (Globalbit) -> ContaTools.

Un SOLO descargador sirve para TODOS los informes del portal, porque todos son
la misma grilla Telerik con el mismo login, filtro de fechas y exportación.
Lo único que cambia entre informes es la URL (y va en el registro reportes.py).

Cómo funciona la exportación (deducido del tráfico real del portal):
    - La grilla se arma con un postback a 'btnRefreshGrid'.
    - La exportación es un postback a la barra 'radToolBar' con argumento '0:0',
      y la respuesta es el .xlsx con TODO el listado del rango (no solo la página
      visible: es exportación del lado del servidor).
    Por eso disparamos esos eventos con __doPostBack: es estable aunque cambien
    los íconos/botones del portal.

Seguridad:
    Las credenciales se leen de st.secrets['bittal'] o variables de entorno.
    Nunca van en el código ni en logs.

Requisitos: playwright>=1.44  +  python -m playwright install chromium
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

LOGIN_URL = "https://accounts.bittal.co/User/Login"

# Controles del portal (iguales en todos los reportes de listado vistos)
ID_CHK_USAR_FECHA = "ctl00_FilterPlaceHolder_RadToolBar1_i2_chkUseDate"
PICKER_FECHA_INI = "ctl00_FilterPlaceHolder_RadToolBar1_i2_rdpInvoiceStartDate"
PICKER_FECHA_FIN = "ctl00_FilterPlaceHolder_RadToolBar1_i2_rdpInvoiceEndDate"
TARGET_REFRESCAR = "ctl00$ListPlaceHolder$btnRefreshGrid"
TARGET_TOOLBAR = "ctl00$ToolbarPlaceHolder$moduleToolBar$radToolBar"
ARG_EXPORTAR_DEFAULT = "0:0"  # índice del botón "Exportar a Excel" en la barra

TIMEOUT_MS = 90_000


@dataclass
class BittalCreds:
    codigo_empresa: str
    usuario: str
    password: str

    @classmethod
    def desde_entorno(cls) -> "BittalCreds":
        try:
            import streamlit as st  # type: ignore
            s = dict(st.secrets.get("bittal", {}))
        except Exception:
            s = {}

        def _v(k_secret, k_env):
            return s.get(k_secret) or os.environ.get(k_env, "")

        return cls(
            codigo_empresa=_v("codigo_empresa", "BITTAL_CODIGO_EMPRESA"),
            usuario=_v("usuario", "BITTAL_USUARIO"),
            password=_v("password", "BITTAL_PASSWORD"),
        )


def descargar_reporte(
    creds: BittalCreds,
    report_url: str,
    fecha_ini: date,
    fecha_fin: date,
    *,
    arg_exportar: str = ARG_EXPORTAR_DEFAULT,
    headless: bool = True,
    log: Optional[list] = None,
) -> bytes:
    """Loguea, fija el rango, genera y exporta UN reporte de bittal. Devuelve el xlsx en bytes."""
    log = log if log is not None else []
    _l = log.append

    if not (creds.codigo_empresa and creds.usuario and creds.password):
        raise RuntimeError(
            "Faltan credenciales de bittal (st.secrets['bittal'] o BITTAL_*)."
        )

    with sync_playwright() as p:
        nav = p.chromium.launch(headless=headless)
        ctx = nav.new_context(accept_downloads=True)
        pag = ctx.new_page()
        pag.set_default_timeout(TIMEOUT_MS)
        try:
            # 1) Login
            _l("🔐 Login...")
            pag.goto(LOGIN_URL, wait_until="domcontentloaded")
            pag.get_by_label("Código/Nit de la Empresa").fill(creds.codigo_empresa)
            pag.get_by_label("Usuario").fill(creds.usuario)
            pag.get_by_label("Contraseña").fill(creds.password)
            # Botón de ingreso: si el texto difiere, ajústalo aquí.
            pag.get_by_role("button", name="/ingresar|entrar|iniciar|acceder/i").click()
            pag.wait_for_load_state("networkidle")

            # 2) Abrir el reporte
            _l(f"📄 Abriendo {report_url.rsplit('/', 1)[-1]} ...")
            pag.goto(report_url, wait_until="networkidle")

            # 3) Activar filtro por fecha y fijar el rango con la API de Telerik
            chk = pag.locator(f"#{ID_CHK_USAR_FECHA}")
            if chk.count() and not chk.is_checked():
                chk.check()
            _l(f"📆 {fecha_ini.isoformat()} a {fecha_fin.isoformat()}")
            pag.evaluate(
                """([idIni, idFin, ini, fin]) => {
                    const set = (id, d) => {
                        const pk = window.$find && window.$find(id);
                        if (pk && pk.set_selectedDate)
                            pk.set_selectedDate(new Date(d[0], d[1]-1, d[2]));
                    };
                    set(idIni, ini); set(idFin, fin);
                }""",
                [PICKER_FECHA_INI, PICKER_FECHA_FIN,
                 [fecha_ini.year, fecha_ini.month, fecha_ini.day],
                 [fecha_fin.year, fecha_fin.month, fecha_fin.day]],
            )

            # 4) Generar la grilla (arma todo el listado en el servidor)
            _l("⚙️ Generando listado...")
            pag.evaluate("(t) => __doPostBack(t, '')", TARGET_REFRESCAR)
            pag.wait_for_load_state("networkidle")

            # 5) Exportar: postback al toolbar -> descarga del xlsx completo
            _l("⬇️ Exportando a Excel (listado completo)...")
            with pag.expect_download() as info:
                pag.evaluate(
                    "([t, a]) => __doPostBack(t, a)", [TARGET_TOOLBAR, arg_exportar]
                )
            desc = info.value
            with open(desc.path(), "rb") as fh:
                data = fh.read()
            _l(f"✅ {desc.suggested_filename} ({len(data)} bytes)")
            return data

        except PWTimeout as e:
            raise RuntimeError(
                "Timeout en bittal. Revisa: login (botón Ingresar), o el argumento "
                f"de exportación arg_exportar='{arg_exportar}'. Detalle: {e}"
            ) from e
        finally:
            ctx.close()
            nav.close()
