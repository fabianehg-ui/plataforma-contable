"""
core/contable/pdf_comprobante.py — impresión del COMPROBANTE DE DIARIO de INTEGRAL.

Toma el asiento armado por servicio_contable.comprobante_diario() y produce un
PDF profesional (encabezado de la empresa, datos del comprobante, tabla de
líneas con débito/crédito, totales con cuadre y espacio de firmas).

Función:
    generar_pdf_comprobante(datos, ruta=None) → bytes (o ruta si se da)

`datos` esperado:
    {
        "empresa": "JIPER SAS",
        "nit_empresa": "901038325",
        "comprobante_cod": "1",
        "comprobante_nombre": "Egreso",     # opcional
        "documento": "1234",
        "fecha": "2026-06-30",              # ISO
        "periodo": "202606",
        "detalle": "Pago proveedor ...",     # opcional
        "lineas": [
            {"cuenta": "51...", "nombre": "...", "nit": "900...",
             "detalle": "...", "cc": "01", "debito": 100000, "credito": 0},
            ...
        ],
        "total_debito": 100000,
        "total_credito": 100000,
    }
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import Optional


MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fmt(n) -> str:
    """1.234.567 sin signo $. '' si es 0/None (para no ensuciar la columna)."""
    try:
        v = int(round(float(n or 0)))
    except (ValueError, TypeError):
        return ""
    if v == 0:
        return ""
    return f"{v:,}".replace(",", ".")


def _fecha_larga(v) -> str:
    if not v:
        return ""
    if isinstance(v, (date, datetime)):
        d = v
    else:
        try:
            d = datetime.strptime(str(v)[:10], "%Y-%m-%d")
        except ValueError:
            return str(v)
    return f"{d.day:02d} de {MESES_ES[d.month - 1]} de {d.year}"


def generar_pdf_comprobante(datos: dict, ruta: Optional[str] = None):
    """Genera el PDF del comprobante de diario. Devuelve bytes (o ruta)."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
        )
    except ImportError:
        raise RuntimeError(
            "reportlab no está instalado. Instala con: pip install reportlab"
        )

    # Paleta suave: azules/grises claros con texto NEGRO (mejor lectura).
    AZUL_TX = colors.HexColor("#24506E")   # texto azul suave (nombre/título)
    AZUL_BG = colors.HexColor("#E3ECF7")   # fondo encabezado de tabla (azul claro)
    GRIS = colors.HexColor("#F4F6F9")      # franjas y zebra
    GRIS_TOT = colors.HexColor("#EAF0F7")  # fila de totales (gris azulado claro)
    GRIS_LINEA = colors.HexColor("#C9D4E0")

    ss = getSampleStyleSheet()
    st_empresa = ParagraphStyle("emp", parent=ss["Normal"], fontName="Helvetica-Bold",
                                fontSize=13, textColor=AZUL_TX, leading=15)
    st_sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=8.5, textColor=colors.black)
    st_titulo = ParagraphStyle("tit", parent=ss["Normal"], fontName="Helvetica-Bold",
                               fontSize=12, alignment=TA_RIGHT, textColor=AZUL_TX)
    st_titsub = ParagraphStyle("titsub", parent=ss["Normal"], fontSize=8.5,
                               alignment=TA_RIGHT, textColor=colors.black)
    st_cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=7.5, leading=9,
                             textColor=colors.black)
    st_cell_b = ParagraphStyle("cellb", parent=ss["Normal"], fontSize=7.5, leading=9,
                               fontName="Helvetica-Bold", textColor=colors.black)
    st_num = ParagraphStyle("num", parent=ss["Normal"], fontSize=7.5, leading=9,
                            alignment=TA_RIGHT, textColor=colors.black)
    # Encabezado de tabla: texto NEGRO sobre fondo azul claro
    st_head = ParagraphStyle("head", parent=ss["Normal"], fontSize=7.5, leading=9,
                             fontName="Helvetica-Bold", textColor=colors.black)
    st_head_r = ParagraphStyle("headr", parent=st_head, alignment=TA_RIGHT)

    bio = io.BytesIO()
    doc = SimpleDocTemplate(
        bio, pagesize=letter,
        leftMargin=1.6 * cm, rightMargin=1.6 * cm,
        topMargin=1.4 * cm, bottomMargin=1.6 * cm,
        title=f"Comprobante {datos.get('comprobante_cod','')}-{datos.get('documento','')}",
    )
    elems = []

    # ---- Encabezado: empresa (izq) + título comprobante (der) --------------
    comp_cod = str(datos.get("comprobante_cod") or "")
    comp_nom = str(datos.get("comprobante_nombre") or "")
    comp_label = f"{comp_cod} — {comp_nom}" if comp_nom else comp_cod
    izq = [
        Paragraph(str(datos.get("empresa") or "Empresa"), st_empresa),
        Paragraph(f"NIT {datos.get('nit_empresa') or '—'}", st_sub),
    ]
    # Datos de contacto de la empresa (solo los que existan)
    _ubic = " · ".join([str(x) for x in
                        (datos.get("direccion_empresa"), datos.get("ciudad_empresa")) if x])
    if _ubic:
        izq.append(Paragraph(_ubic, st_sub))
    _cont = " · ".join([str(x) for x in
                        (datos.get("tel_empresa") and f"Tel. {datos.get('tel_empresa')}",
                         datos.get("email_empresa")) if x])
    if _cont:
        izq.append(Paragraph(_cont, st_sub))
    izq.append(Paragraph("INTEGRAL · Contabilidad", st_sub))
    der = [
        Paragraph("COMPROBANTE DE DIARIO", st_titulo),
        Paragraph(f"Comprobante: {comp_label}", st_titsub),
        Paragraph(f"Documento N.º {datos.get('documento') or '—'}", st_titsub),
    ]
    cab = Table([[izq, der]], colWidths=[10.0 * cm, 8.0 * cm])
    cab.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elems.append(cab)
    elems.append(Spacer(1, 6))

    # ---- Franja de datos: fecha · período -----------------------------------
    fecha_txt = _fecha_larga(datos.get("fecha"))
    periodo = str(datos.get("periodo") or "")
    per_txt = f"{periodo[:4]}-{periodo[4:6]}" if len(periodo) >= 6 else periodo
    franja = Table(
        [[Paragraph(f"<b>Fecha:</b> {fecha_txt or '—'}", st_sub),
          Paragraph(f"<b>Período:</b> {per_txt or '—'}", st_sub)]],
        colWidths=[10.0 * cm, 8.0 * cm],
    )
    franja.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS),
        ("BOX", (0, 0), (-1, -1), 0.5, GRIS_LINEA),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elems.append(franja)

    # ---- Franja del tercero (cliente / proveedor) ---------------------------
    ter_nit = str(datos.get("tercero_nit") or "").strip()
    ter_nom = str(datos.get("tercero_nombre") or "").strip()
    if ter_nit or ter_nom:
        etq = "Cliente / Proveedor"
        cuerpo = " · ".join([x for x in
                            (ter_nom, (f"NIT {ter_nit}" if ter_nit else "")) if x])
        franja_ter = Table(
            [[Paragraph(f"<b>{etq}:</b> {cuerpo}", st_sub)]],
            colWidths=[18.0 * cm],
        )
        franja_ter.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF4FB")),
            ("BOX", (0, 0), (-1, -1), 0.5, GRIS_LINEA),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, GRIS_LINEA),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        elems.append(franja_ter)

    if datos.get("detalle"):
        elems.append(Spacer(1, 3))
        elems.append(Paragraph(f"<b>Concepto:</b> {datos['detalle']}", st_sub))
    elems.append(Spacer(1, 8))

    # ---- Tabla del asiento --------------------------------------------------
    header = [
        Paragraph("Cuenta", st_head), Paragraph("Nombre", st_head),
        Paragraph("NIT", st_head), Paragraph("Detalle", st_head),
        Paragraph("C.C.", st_head),
        Paragraph("Débito", st_head_r), Paragraph("Crédito", st_head_r),
    ]
    filas = [header]
    for ln in datos.get("lineas", []):
        filas.append([
            Paragraph(str(ln.get("cuenta") or ""), st_cell_b),
            Paragraph(str(ln.get("nombre") or ""), st_cell),
            Paragraph(str(ln.get("nit") or ""), st_cell),
            Paragraph(str(ln.get("detalle") or ""), st_cell),
            Paragraph(str(ln.get("cc") or ""), st_cell),
            Paragraph(_fmt(ln.get("debito")), st_num),
            Paragraph(_fmt(ln.get("credito")), st_num),
        ])
    # fila de totales
    filas.append([
        Paragraph("TOTALES", st_cell_b), "", "", "", "",
        Paragraph(_fmt(datos.get("total_debito")), st_num),
        Paragraph(_fmt(datos.get("total_credito")), st_num),
    ])

    col_w = [1.9 * cm, 4.2 * cm, 2.0 * cm, 4.6 * cm, 1.0 * cm, 2.15 * cm, 2.15 * cm]
    t = Table(filas, colWidths=col_w, repeatRows=1)
    n = len(filas)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, GRIS_LINEA),
        ("GRID", (0, 0), (-1, -2), 0.4, GRIS_LINEA),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        # zebra en las filas de detalle
        ("ROWBACKGROUNDS", (0, 1), (-1, n - 2), [colors.white, GRIS]),
        # fila de totales: gris azulado claro con texto NEGRO
        ("SPAN", (0, n - 1), (4, n - 1)),
        ("BACKGROUND", (0, n - 1), (-1, n - 1), GRIS_TOT),
        ("TEXTCOLOR", (0, n - 1), (-1, n - 1), colors.black),
        ("LINEABOVE", (0, n - 1), (-1, n - 1), 0.8, AZUL_TX),
        ("ALIGN", (0, n - 1), (0, n - 1), "RIGHT"),
    ]))
    # totales en NEGRO negrita
    st_tot = ParagraphStyle("tot", parent=st_num, textColor=colors.black,
                            fontName="Helvetica-Bold")
    filas[n - 1][0] = Paragraph("TOTALES", ParagraphStyle(
        "totl", parent=st_cell_b, textColor=colors.black, alignment=TA_RIGHT))
    filas[n - 1][5] = Paragraph(_fmt(datos.get("total_debito")), st_tot)
    filas[n - 1][6] = Paragraph(_fmt(datos.get("total_credito")), st_tot)
    elems.append(t)
    elems.append(Spacer(1, 6))

    # ---- Cuadre -------------------------------------------------------------
    td = int(round(float(datos.get("total_debito") or 0)))
    tc = int(round(float(datos.get("total_credito") or 0)))
    if td == tc:
        cuadre = Paragraph(
            f"<b>Comprobante cuadrado</b> · Débitos = Créditos = "
            f"{_fmt(td) or '0'}",
            ParagraphStyle("ok", parent=st_sub, textColor=colors.HexColor("#1E7A34")))
    else:
        cuadre = Paragraph(
            f"<b>DESCUADRE</b> · Débitos {_fmt(td) or '0'} − Créditos "
            f"{_fmt(tc) or '0'} = {_fmt(td - tc) or '0'}",
            ParagraphStyle("bad", parent=st_sub, textColor=colors.HexColor("#B00020")))
    elems.append(cuadre)
    elems.append(Spacer(1, 26))

    # ---- Firmas -------------------------------------------------------------
    linea = "_______________________________"
    firmas = Table(
        [[Paragraph(linea, st_cell), "", Paragraph(linea, st_cell), "",
          Paragraph(linea, st_cell)],
         [Paragraph("Elaboró", st_cell), "", Paragraph("Revisó", st_cell), "",
          Paragraph("Aprobó", st_cell)]],
        colWidths=[5.0 * cm, 0.8 * cm, 5.0 * cm, 0.8 * cm, 5.0 * cm],
    )
    firmas.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
    ]))
    elems.append(firmas)

    doc.build(elems)
    pdf = bio.getvalue()
    bio.close()

    if ruta:
        with open(ruta, "wb") as f:
            f.write(pdf)
        return ruta
    return pdf
