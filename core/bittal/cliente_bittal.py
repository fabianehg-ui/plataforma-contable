"""
core/bittal/cliente_bittal.py

Conector genérico Bittal (Globalbit) -> ContaTools.

Un SOLO descargador sirve para TODOS los informes del portal, porque todos son
la misma grilla Telerik con el mismo login, filtro de fechas y exportación.
Lo único que cambia entre informes es la URL (y va en el registro reportes.py).

Cómo funciona la exportación (deducido del tráfico real del portal):
    - La grilla se arma con un postback a 'btnRefreshGrid'.
    - La exportación es un postback a la barra 'radToolBar' con argumento '1:0',
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

LOGIN_URL = "https://accounts.bittal.co/User/Login"

# Controles del portal (iguales en todos los reportes de listado vistos)
ID_CHK_USAR_FECHA = "ctl00_FilterPlaceHolder_RadToolBar1_i2_chkUseDate"
PICKER_FECHA_INI = "ctl00_FilterPlaceHolder_RadToolBar1_i2_rdpInvoiceStartDate"
PICKER_FECHA_FIN = "ctl00_FilterPlaceHolder_RadToolBar1_i2_rdpInvoiceEndDate"
TARGET_REFRESCAR = "ctl00$ListPlaceHolder$btnRefreshGrid"
TARGET_TOOLBAR = "ctl00$ToolbarPlaceHolder$moduleToolBar$radToolBar"
ARG_EXPORTAR_DEFAULT = "1:0"  # indice del boton "Exportar a Excel" (confirmado en HAR)

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


def _frame_con_postback(pag, intentos: int = 12, espera_ms: int = 1000):
    """Devuelve el frame (o la pagina) donde esta definido __doPostBack.

    El reporte de bittal carga dentro de un iframe; ASP.NET define __doPostBack
    y Telerik $find DENTRO de ese marco, no en la pagina de afuera. Probamos
    cada frame hasta encontrar el que tiene la funcion.
    """
    for _ in range(intentos):
        for fr in pag.frames:
            try:
                if fr.evaluate("() => typeof window.__doPostBack === 'function'"):
                    return fr
            except Exception:
                pass
        pag.wait_for_timeout(espera_ms)
    return None


def descargar_reporte(
    creds: BittalCreds,
    report_url: str,
    fecha_ini: date,
    fecha_fin: date,
    *,
    arg_exportar: str = ARG_EXPORTAR_DEFAULT,
    refrescar: bool = True,
    headless: bool = True,
    log: Optional[list] = None,
) -> bytes:
    """Loguea, fija el rango, genera y exporta UN reporte de bittal. Devuelve el xlsx en bytes."""
    log = log if log is not None else []
    _l = log.append

    # Import perezoso: la página puede cargar aunque Playwright no esté instalado;
    # solo se exige al momento de descargar.
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Falta Playwright. Instálalo: pip install playwright && "
            "python -m playwright install chromium"
        ) from e

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
            # 1) Login. IDs reales del form de bittal: #c (codigo), #u (usuario),
            #    #p (password). El boton INGRESAR es <input type=button onclick=sendLogin()>;
            #    sendLogin() guarda la empresa y hace login-form.submit() a /User/Prevalidate.
            _l("🔐 Login...")
            pag.goto(LOGIN_URL, wait_until="domcontentloaded")
            pag.wait_for_selector("#p", timeout=TIMEOUT_MS)

            # Llenar por ID via JS (robusto aunque el campo codigo se vuelva
            # dropdown/hidden cuando el navegador tiene empresas guardadas).
            pag.evaluate(
                """([c, u, p]) => {
                    const set = (id, v) => {
                        const e = document.getElementById(id);
                        if (e) {
                            e.value = v;
                            e.dispatchEvent(new Event('input', {bubbles: true}));
                            e.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                    };
                    set('c', c); set('u', u); set('p', p);
                }""",
                [creds.codigo_empresa, creds.usuario, creds.password],
            )

            def _en_login() -> bool:
                return "User/Login" in pag.url or "Prevalidate" in pag.url

            # Enviar: usar sendLogin() del portal; si no existe, submit del form;
            # como respaldo, clic en INGRESAR.
            try:
                pag.evaluate(
                    "() => { if (typeof sendLogin === 'function') { sendLogin(); }"
                    " else { const f = document.getElementById('login-form')"
                    " || document.querySelector('form'); if (f) f.submit(); } }"
                )
                _l("  (envio via sendLogin/submit)")
            except Exception:
                try:
                    pag.locator(
                        "input[value='INGRESAR'], .btnaction"
                    ).first.click(timeout=5000)
                    _l("  (clic en INGRESAR)")
                except Exception:
                    pass

            try:
                pag.wait_for_url(
                    lambda u: "User/Login" not in u and "Prevalidate" not in u,
                    timeout=40_000,
                )
            except PWTimeout:
                pass

            _l(f"  URL tras login: {pag.url}")

            # Si AUN sigue en login, reportar con el texto visible de la pagina
            if _en_login():
                try:
                    txt = pag.locator("body").inner_text()
                    txt = " ".join(txt.split())[:400]
                except Exception:
                    txt = ""
                raise RuntimeError(
                    "El login de bittal no avanzo (sigue en la pagina de acceso). "
                    "Revisa Codigo/Usuario/Contrasena. "
                    f"Texto de la pagina: {txt!r}"
                )

            # 2) Abrir el reporte
            _l(f"📄 Abriendo {report_url.rsplit('/', 1)[-1]} ...")
            pag.goto(report_url, wait_until="networkidle")
            _l(f"  URL del reporte: {pag.url}")

            # 2b) Ubicar el marco (iframe) donde vive el reporte ASP.NET.
            marco = _frame_con_postback(pag)
            if marco is None:
                urls = []
                for fr in pag.frames:
                    try:
                        urls.append(fr.url)
                    except Exception:
                        pass
                try:
                    titulo = pag.title()
                except Exception:
                    titulo = ""
                raise RuntimeError(
                    "No se encontro el reporte en bittal (no aparece __doPostBack). "
                    f"URL actual: {pag.url} | titulo: {titulo!r} | frames: {urls}. "
                    "Si la URL es la de login, el acceso no quedo iniciado; "
                    "si es otra, el reporte abre distinto."
                )
            if marco is not pag.main_frame:
                _l("  (reporte dentro de un iframe)")

            # 3) Fijar el rango de fechas. Hay dos mecanismos según el reporte:
            #    (a) RadDatePicker de Telerik + chkUseDate  -> Ventas / Compras DS
            #    (b) control de rango con inputs ocultos hdnStartDate/hdnEndDate
            #        en formato ISO (YYYY-MM-DD)            -> Caja menor / tesorería
            #    Aplicamos el que exista en la página (sin romper el otro).
            chk = marco.locator(f"#{ID_CHK_USAR_FECHA}")
            if chk.count() and not chk.is_checked():
                chk.check()
            _l(f"📆 {fecha_ini.isoformat()} a {fecha_fin.isoformat()}")
            aplicados = marco.evaluate(
                """([idIni, idFin, ini, fin, iniISO, finISO]) => {
                    const out = [];
                    // (a) Telerik RadDatePicker
                    const setPk = (id, d) => {
                        const pk = window.$find && window.$find(id);
                        if (pk && pk.set_selectedDate) {
                            pk.set_selectedDate(new Date(d[0], d[1]-1, d[2]));
                            return true;
                        }
                        return false;
                    };
                    if (setPk(idIni, ini)) { setPk(idFin, fin); out.push('telerik'); }
                    // (b) Rango con inputs ocultos (hdnStartDate / hdnEndDate)
                    const setHid = (suf, val) => {
                        const el = document.querySelector(
                            'input[id$="' + suf + '"], input[name$="$' + suf + '"]');
                        if (el) {
                            el.value = val;
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                            return true;
                        }
                        return false;
                    };
                    if (setHid('hdnStartDate', iniISO)) {
                        setHid('hdnEndDate', finISO); out.push('rango-oculto');
                    }
                    return out;
                }""",
                [PICKER_FECHA_INI, PICKER_FECHA_FIN,
                 [fecha_ini.year, fecha_ini.month, fecha_ini.day],
                 [fecha_fin.year, fecha_fin.month, fecha_fin.day],
                 fecha_ini.isoformat(), fecha_fin.isoformat()],
            )
            if aplicados:
                _l(f"  filtro de fecha aplicado vía: {', '.join(aplicados)}")
            else:
                _l("  ⚠️ No se encontró control de fecha conocido; "
                   "se exportaría la vista por defecto.")

            # 4) Generar la grilla (aplica el filtro en el servidor). Algunos
            #    reportes (p. ej. Terceros) no tienen botón de refrescar y solo
            #    exportan la vista cargada: en esos se omite este paso.
            if refrescar:
                _l("⚙️ Generando listado...")
                marco.evaluate("window.__doPostBack(" + repr(TARGET_REFRESCAR) + ", '')")
                pag.wait_for_load_state("networkidle")
                pag.wait_for_timeout(1500)
                # Tras el postback el iframe puede recargarse: re-ubicar el marco.
                marco = _frame_con_postback(pag) or marco
            else:
                _l("  (sin refrescar: se exporta la vista cargada)")

            # 5) Exportar: postback al toolbar -> descarga del xlsx completo
            _l("⬇️ Exportando a Excel (listado completo)...")
            with pag.expect_download() as info:
                marco.evaluate(
                    "window.__doPostBack(" + repr(TARGET_TOOLBAR)
                    + ", " + repr(arg_exportar) + ")"
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
