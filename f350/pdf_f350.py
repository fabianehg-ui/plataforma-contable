"""
core/f350/pdf_f350.py — generación del PDF del Formulario 350 estilo DIAN.

A diferencia del .exe original (que escribe a una ruta), esta función puede
devolver bytes para que Streamlit lo ofrezca como descarga directamente.

Funciones:
    generar_pdf_formulario_350(datos, ruta=None) → str (ruta) o bytes

Extraído de BorradorFácil 350 v2.1.5 con adaptación de E/S.
"""

import io
from core.f350.autorretencion import aproximar_a_miles
from core.f350.casillas import (
    MAPEO_CASILLAS_F350,
    AUTORRET_CASILLAS_F350,
    CONCEPTOS_ORDEN_F350,
)


def _fmt_num_f350(n):
    """Formato 1.234.567 (sin signo $). Devuelve '0' si es nulo o cero."""
    if n is None or n == 0:
        return "0"
    try:
        return f"{int(round(n)):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "0"


def generar_pdf_formulario_350(datos, ruta=None):
    """
    Genera el PDF del F350 con marca de agua "BORRADOR" y layout estilo DIAN.

    Args:
        datos: dict con los campos:
            año (int), periodo (int), nit (str), dv (str),
            razon_social (str), ciiu (str), tarifa_autorret (float),
            retenciones [{concepto, tipo, base, retencion}, ...],
            autorretenciones [{concepto, base, retencion}, ...],
            total_iva (opcional), total_timbre (opcional).
        ruta: si se da, escribe el PDF al disco y devuelve la ruta.
              Si es None, devuelve los bytes del PDF (útil para Streamlit).

    Returns:
        str (ruta) si `ruta` fue dado, o bytes si `ruta` es None.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import cm
        from reportlab.lib.colors import HexColor, white, black, grey
        from reportlab.pdfgen import canvas
    except ImportError:
        raise RuntimeError(
            "reportlab no está instalado. Instala con: pip install reportlab"
        )

    AZUL_DIAN = HexColor("#1F4E78")
    GRIS_CLARO = HexColor("#F2F2F2")
    AMARILLO = HexColor("#FFF9E6")

    # Destino: archivo o buffer en memoria
    if ruta:
        buffer = ruta
    else:
        buffer = io.BytesIO()

    c = canvas.Canvas(buffer, pagesize=letter)
    ancho, alto = letter

    # ====== Marca de agua "BORRADOR" diagonal ======
    c.saveState()
    c.setFont("Helvetica-Bold", 64)
    c.setFillColor(HexColor("#FFE5E5"))
    c.translate(ancho / 2, alto / 2)
    c.rotate(45)
    c.drawCentredString(0, 0, "BORRADOR")
    c.restoreState()

    # ====== Encabezado DIAN ======
    y = alto - 1.2 * cm
    c.setFillColor(AZUL_DIAN)
    c.setStrokeColor(AZUL_DIAN)
    c.setLineWidth(1.5)
    c.rect(1.5 * cm, y - 0.9 * cm, 3 * cm, 0.9 * cm, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(3 * cm, y - 0.65 * cm, "DIAN")

    c.setFillColor(AZUL_DIAN)
    c.rect(ancho - 3.5 * cm, y - 0.9 * cm, 2 * cm, 0.9 * cm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(ancho - 2.5 * cm, y - 0.7 * cm, "350")

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(ancho / 2, y - 0.4 * cm, "Declaración retenciones en la fuente")
    c.setFont("Helvetica", 8)
    c.drawRightString(ancho - 4 * cm, y - 0.75 * cm, "PRIVADA")

    y -= 1.4 * cm
    c.setStrokeColor(black)
    c.setLineWidth(0.5)

    # ====== Período / formulario ======
    c.rect(1.5 * cm, y - 1.2 * cm, 2.5 * cm, 1.2 * cm)
    c.setFont("Helvetica", 7)
    c.drawString(1.6 * cm, y - 0.25 * cm, "1. Año")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1.8 * cm, y - 0.85 * cm, str(datos['año']))

    c.rect(4 * cm, y - 1.2 * cm, 2 * cm, 1.2 * cm)
    c.setFont("Helvetica", 7)
    c.drawString(4.1 * cm, y - 0.25 * cm, "3. Período")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(4.8 * cm, y - 0.85 * cm, str(datos['periodo']))

    c.rect(6 * cm, y - 1.2 * cm, ancho - 7.5 * cm, 1.2 * cm)
    c.setFont("Helvetica", 7)
    c.drawString(6.1 * cm, y - 0.25 * cm, "4. Número de formulario")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(6.1 * cm, y - 0.85 * cm, "(Borrador - no asignado)")

    y -= 1.4 * cm

    # ====== Datos del declarante ======
    c.setFillColor(HexColor("#D9D9D9"))
    c.rect(1.5 * cm, y - 0.5 * cm, ancho - 3 * cm, 0.5 * cm, fill=1, stroke=1)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(1.6 * cm, y - 0.33 * cm, "Datos del declarante")

    y -= 0.5 * cm
    c.rect(1.5 * cm, y - 1 * cm, 5 * cm, 1 * cm)
    c.setFont("Helvetica", 7)
    c.drawString(1.6 * cm, y - 0.2 * cm, "5. NIT")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2.5 * cm, y - 0.75 * cm, datos['nit'])

    c.rect(6.5 * cm, y - 1 * cm, 1.2 * cm, 1 * cm)
    c.setFont("Helvetica", 7)
    c.drawString(6.6 * cm, y - 0.2 * cm, "6. DV")
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(7.1 * cm, y - 0.75 * cm, str(datos.get('dv', '')))

    c.rect(7.7 * cm, y - 1 * cm, ancho - 9.2 * cm, 1 * cm)
    c.setFont("Helvetica", 7)
    c.drawString(7.8 * cm, y - 0.2 * cm, "11. Razón social")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(7.8 * cm, y - 0.75 * cm, str(datos.get('razon_social', ''))[:40])

    y -= 1.2 * cm
    c.rect(1.5 * cm, y - 1 * cm, 4 * cm, 1 * cm)
    c.setFont("Helvetica", 7)
    c.drawString(1.6 * cm, y - 0.2 * cm, "27. CIIU principal")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1.8 * cm, y - 0.75 * cm, str(datos.get('ciiu', '')))

    c.rect(5.5 * cm, y - 1 * cm, 3 * cm, 1 * cm)
    c.setFont("Helvetica", 7)
    c.drawString(5.6 * cm, y - 0.2 * cm, "28. Tarifa autorret.")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(5.8 * cm, y - 0.75 * cm, f"{datos.get('tarifa_autorret', 0):.2f} %")

    y -= 1.4 * cm

    # ====== Sección retenciones a terceros ======
    c.setFillColor(AZUL_DIAN)
    c.rect(1.5 * cm, y - 0.5 * cm, ancho - 3 * cm, 0.5 * cm, fill=1, stroke=1)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(ancho / 2, y - 0.33 * cm, "Retenciones a título de renta y complementario")

    y -= 0.5 * cm
    c.setFillColor(black)

    ancho_concepto = 7 * cm
    x_inicio = 1.5 * cm
    alto_fila = 0.5 * cm
    ancho_total = ancho - 3 * cm
    ancho_seccion = (ancho_total - ancho_concepto) / 2
    mitad_sec = ancho_seccion / 2
    x_pj = x_inicio + ancho_concepto
    x_pn = x_pj + ancho_seccion

    # Encabezado columnas
    c.setFillColor(GRIS_CLARO)
    c.rect(x_inicio, y - alto_fila, ancho_concepto, alto_fila, fill=1, stroke=1)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_inicio + 0.1 * cm, y - 0.32 * cm, "Concepto")

    c.setFillColor(HexColor("#E8EEF4"))
    c.rect(x_pj, y - alto_fila, ancho_seccion, alto_fila, fill=1, stroke=1)
    c.setFillColor(black)
    c.drawCentredString(x_pj + ancho_seccion / 2, y - 0.32 * cm, "A personas jurídicas")

    c.setFillColor(HexColor("#FDF2E8"))
    c.rect(x_pn, y - alto_fila, ancho_seccion, alto_fila, fill=1, stroke=1)
    c.setFillColor(black)
    c.drawCentredString(x_pn + ancho_seccion / 2, y - 0.32 * cm, "A personas naturales")

    y -= alto_fila
    c.setFont("Helvetica", 6)
    c.rect(x_inicio, y - alto_fila, ancho_concepto, alto_fila)
    for x_ini in [x_pj, x_pn]:
        c.rect(x_ini, y - alto_fila, mitad_sec, alto_fila)
        c.drawCentredString(x_ini + mitad_sec / 2, y - 0.32 * cm, "Base")
        c.rect(x_ini + mitad_sec, y - alto_fila, mitad_sec, alto_fila)
        c.drawCentredString(x_ini + mitad_sec + mitad_sec / 2, y - 0.32 * cm, "Retención")

    y -= alto_fila

    # Agrupar retenciones por (concepto, tipo)
    retenciones_map = {}
    for r in datos.get('retenciones', []):
        key = (r['concepto'], r['tipo'])
        if key not in retenciones_map:
            retenciones_map[key] = {'base': 0, 'retencion': 0}
        retenciones_map[key]['base'] += r['base']
        retenciones_map[key]['retencion'] += r['retencion']

    total_ret_renta = 0
    c.setFont("Helvetica", 7)

    for concepto in CONCEPTOS_ORDEN_F350:
        if concepto not in MAPEO_CASILLAS_F350:
            continue

        pj_b, pj_r = MAPEO_CASILLAS_F350[concepto]["PJ"]
        pn_b, pn_r = MAPEO_CASILLAS_F350[concepto]["PN"]

        pj_raw = retenciones_map.get((concepto, "PJ"), {'base': 0, 'retencion': 0})
        pn_raw = retenciones_map.get((concepto, "PN"), {'base': 0, 'retencion': 0})
        pj_data = {
            'base':      aproximar_a_miles(pj_raw['base']),
            'retencion': aproximar_a_miles(pj_raw['retencion']),
        }
        pn_data = {
            'base':      aproximar_a_miles(pn_raw['base']),
            'retencion': aproximar_a_miles(pn_raw['retencion']),
        }
        total_ret_renta += pj_data['retencion'] + pn_data['retencion']

        c.rect(x_inicio, y - alto_fila, ancho_concepto, alto_fila)
        c.setFont("Helvetica", 7)
        c.drawString(x_inicio + 0.1 * cm, y - 0.32 * cm, concepto)

        for (x_col, casilla, valor) in [
            (x_pj,             pj_b, pj_data['base']),
            (x_pj + mitad_sec, pj_r, pj_data['retencion']),
            (x_pn,             pn_b, pn_data['base']),
            (x_pn + mitad_sec, pn_r, pn_data['retencion']),
        ]:
            if casilla is None:
                c.setFillColor(GRIS_CLARO)
                c.rect(x_col, y - alto_fila, mitad_sec, alto_fila, fill=1, stroke=1)
                c.setFillColor(black)
                continue
            if valor > 0:
                c.setFillColor(AMARILLO)
                c.rect(x_col, y - alto_fila, mitad_sec, alto_fila, fill=1, stroke=1)
                c.setFillColor(black)
            else:
                c.rect(x_col, y - alto_fila, mitad_sec, alto_fila)
            c.setFont("Helvetica", 6)
            c.setFillColor(grey)
            c.drawString(x_col + 0.08 * cm, y - 0.18 * cm, str(casilla))
            c.setFillColor(black)
            c.setFont("Helvetica-Bold" if valor > 0 else "Helvetica", 8)
            c.drawRightString(x_col + mitad_sec - 0.1 * cm, y - 0.35 * cm, _fmt_num_f350(valor))

        y -= alto_fila

    # ====== Sección autorretenciones ======
    y -= 0.2 * cm
    c.setFillColor(AZUL_DIAN)
    c.rect(1.5 * cm, y - 0.5 * cm, ancho - 3 * cm, 0.5 * cm, fill=1, stroke=1)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(ancho / 2, y - 0.33 * cm, "Autorretenciones")

    y -= 0.5 * cm
    c.setFillColor(black)

    autorret_map = {a['concepto']: a for a in datos.get('autorretenciones', [])}
    total_autorret = 0
    c.setFont("Helvetica", 7)

    for concepto, (cas_base, cas_ret) in AUTORRET_CASILLAS_F350.items():
        raw = autorret_map.get(concepto, {'base': 0, 'retencion': 0})
        data = {
            'base':      aproximar_a_miles(raw['base']),
            'retencion': aproximar_a_miles(raw['retencion']),
        }
        total_autorret += data['retencion']

        c.rect(x_inicio, y - alto_fila, ancho_concepto, alto_fila)
        c.drawString(x_inicio + 0.1 * cm, y - 0.32 * cm, concepto)

        if data['base'] > 0:
            c.setFillColor(AMARILLO)
            c.rect(x_pj, y - alto_fila, ancho_seccion, alto_fila, fill=1, stroke=1)
            c.setFillColor(black)
        else:
            c.rect(x_pj, y - alto_fila, mitad_sec, alto_fila)
            c.rect(x_pj + mitad_sec, y - alto_fila, mitad_sec, alto_fila)

        c.setFont("Helvetica", 6)
        c.setFillColor(grey)
        c.drawString(x_pj + 0.08 * cm, y - 0.18 * cm, str(cas_base))
        c.drawString(x_pj + mitad_sec + 0.08 * cm, y - 0.18 * cm, str(cas_ret))
        c.setFillColor(black)
        c.setFont("Helvetica-Bold" if data['base'] > 0 else "Helvetica", 8)
        c.drawRightString(x_pj + mitad_sec - 0.1 * cm, y - 0.35 * cm, _fmt_num_f350(data['base']))
        c.drawRightString(x_pj + ancho_seccion - 0.1 * cm, y - 0.35 * cm, _fmt_num_f350(data['retencion']))

        c.setFillColor(GRIS_CLARO)
        c.rect(x_pn, y - alto_fila, ancho_seccion, alto_fila, fill=1, stroke=1)
        c.setFillColor(black)

        y -= alto_fila

    # ====== Totales ======
    y -= 0.2 * cm
    total_retenciones = total_ret_renta + total_autorret

    def _fila_total(etiqueta, casilla, valor, resaltar=False):
        nonlocal y
        color_fondo = HexColor("#FFF2CC") if resaltar else GRIS_CLARO
        ancho_valor = 1.8 * cm
        c.setFillColor(color_fondo)
        c.rect(x_inicio, y - alto_fila, ancho - 3 * cm - ancho_valor, alto_fila, fill=1, stroke=1)
        c.setFillColor(black)
        c.setFont("Helvetica-Bold" if resaltar else "Helvetica", 8)
        c.drawString(x_inicio + 0.1 * cm, y - 0.32 * cm, etiqueta)
        c.setFillColor(color_fondo)
        c.rect(ancho - 1.5 * cm - ancho_valor, y - alto_fila, ancho_valor, alto_fila, fill=1, stroke=1)
        c.setFillColor(grey)
        c.setFont("Helvetica", 6)
        c.drawString(ancho - 1.5 * cm - ancho_valor + 0.08 * cm, y - 0.18 * cm, str(casilla))
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(ancho - 1.6 * cm, y - 0.35 * cm, _fmt_num_f350(valor))
        y -= alto_fila

    _fila_total("Total retenciones renta y complementario", 130, total_retenciones, resaltar=True)
    iva = aproximar_a_miles(datos.get('total_iva', 0))
    timbre = aproximar_a_miles(datos.get('total_timbre', 0))
    _fila_total("A responsables del impuesto sobre las ventas", 131, iva)
    _fila_total("Practicadas por servicios a no residentes", 132, 0)
    _fila_total("Menos retenciones IVA en exceso o indebidas", 133, 0)
    _fila_total("Total retenciones IVA", 134, iva)
    _fila_total("Retenciones impuesto timbre nacional", 135, timbre)
    total_general = total_retenciones + iva + timbre
    _fila_total("Total retenciones", 136, total_general)
    _fila_total("Sanciones", 137, 0)
    _fila_total("Total retenciones más sanciones", 138, total_general, resaltar=True)

    y -= 0.5 * cm
    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(grey)
    c.drawString(1.5 * cm, y, "Generado por la plataforma · Este documento es un borrador de referencia")
    c.drawString(1.5 * cm, y - 0.35 * cm,
                 "La declaración oficial debe presentarse por Muisca (DIAN) con el IFE del contador.")

    c.save()

    if ruta:
        return ruta
    return buffer.getvalue()
