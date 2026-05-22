"""
Tests del módulo F350 — lógica pura (no toca Supabase).

Cubre:
    - NIT: inferencia de tipo y DV
    - Casillas: mapeo concepto → casilla
    - Clasificador: reglas PUC, patrones y palabras clave
    - Autorretención: cálculo y aproximación a miles
    - Generación de PDF (sanity check, solo verifica que se produce un PDF válido)

No incluye tests de los parsers de PDF (parser_contai), porque requieren
PDFs reales de muestra. Esos se cubren en tests de integración aparte.

Ejecutar: pytest tests/test_f350.py -v
"""

import pytest


# =============================================================================
# nit_utils
# =============================================================================

class TestNitUtils:
    def test_persona_juridica(self):
        from core.f350 import inferir_tipo_persona
        tipo, ext, valido, rango = inferir_tipo_persona("900473959")
        assert tipo == "Persona Jurídica"
        assert ext is False
        assert valido is True

    def test_cedula_antigua(self):
        from core.f350 import inferir_tipo_persona
        tipo, ext, valido, _ = inferir_tipo_persona("12345678")
        assert tipo == "Persona Natural"
        assert valido is True

    def test_cedula_moderna(self):
        from core.f350 import inferir_tipo_persona
        tipo, ext, valido, _ = inferir_tipo_persona("1234567890")
        assert tipo == "Persona Natural"
        assert ext is False

    def test_extranjero(self):
        from core.f350 import inferir_tipo_persona
        tipo, ext, valido, _ = inferir_tipo_persona("700123456")
        assert ext is True
        assert valido is True

    def test_nit_invalido(self):
        from core.f350 import inferir_tipo_persona
        tipo, ext, valido, _ = inferir_tipo_persona("abc")
        assert valido is False

    def test_dv_900473959(self):
        from core.f350 import calcular_dv
        # DV oficial conocido
        assert calcular_dv("900473959") == "1"

    def test_dv_900451388(self):
        from core.f350 import calcular_dv
        assert calcular_dv("900451388") == "1"

    def test_formato_nit(self):
        from core.f350 import formato_nit
        assert formato_nit("900473959") == "900.473.959-1"

    def test_formato_moneda(self):
        from core.f350 import formato_moneda
        assert formato_moneda(1234567) == "$1.234.567"
        assert formato_moneda(0) == "$0"
        assert formato_moneda("abc") == "$0"


# =============================================================================
# clasificador
# =============================================================================

class TestClasificador:
    def test_codigo_puc_servicios(self):
        from core.f350 import clasificar_concepto_detallado
        r = clasificar_concepto_detallado("23-65-25", "SERVICIOS")
        assert r["concepto"] == "Servicios"
        assert r["confianza"] == "alta"
        assert r["origen"] == "codigo_puc"

    def test_codigo_puc_honorarios(self):
        from core.f350 import clasificar_concepto_detallado
        r = clasificar_concepto_detallado("236515", "RETENCION HONORARIOS")
        assert r["concepto"] == "Honorarios"
        assert r["confianza"] == "alta"

    def test_iva_por_codigo(self):
        from core.f350 import clasificar_concepto_detallado
        r = clasificar_concepto_detallado("23-67-01", "RETE IVA 15%")
        assert r["concepto"] == "IVA"

    def test_patron_combinado_revisoria_fiscal(self):
        from core.f350 import clasificar_concepto_detallado
        r = clasificar_concepto_detallado("", "REVISORIA FISCAL")
        assert r["concepto"] == "Honorarios"

    def test_patron_combinado_vigilancia_privada(self):
        from core.f350 import clasificar_concepto_detallado
        # "VIGILANCIA" + "PRIVADA" → Servicios (no Honorarios)
        r = clasificar_concepto_detallado("", "VIGILANCIA PRIVADA Y SEGURIDAD")
        assert r["concepto"] == "Servicios"

    def test_palabra_clave_arriendo(self):
        from core.f350 import clasificar_concepto_detallado
        r = clasificar_concepto_detallado("", "ARRENDAMIENTO LOCAL")
        assert r["concepto"] == "Arrendamientos"

    def test_pagos_exterior(self):
        from core.f350 import clasificar_concepto_detallado
        r = clasificar_concepto_detallado("23-65-50", "PAGOS AL EXTERIOR")
        assert r["concepto"] == "Otros pagos"

    def test_default_otros_pagos(self):
        from core.f350 import clasificar_concepto_detallado
        r = clasificar_concepto_detallado("99-99-99", "TEXTO ALEATORIO XYZ")
        assert r["concepto"] == "Otros pagos"
        assert r["confianza"] == "baja"
        assert r["origen"] == "default"


# =============================================================================
# casillas
# =============================================================================

class TestCasillas:
    def test_honorarios_pj(self):
        from core.f350 import obtener_casillas_f350
        assert obtener_casillas_f350("Honorarios", "Persona Jurídica") == (29, 42)

    def test_honorarios_pn(self):
        from core.f350 import obtener_casillas_f350
        assert obtener_casillas_f350("Honorarios", "Persona Natural") == (79, 95)

    def test_extranjero_otros_pagos(self):
        from core.f350 import obtener_casillas_f350
        # Cualquier concepto en extranjero va a 55/57
        cas = obtener_casillas_f350("Servicios", "Persona Jurídica", es_extranjero=True)
        assert cas == (55, 57)

    def test_rentas_trabajo_pj_no_aplica(self):
        from core.f350 import obtener_casillas_f350, MAPEO_CASILLAS_F350
        cas_b, cas_r = MAPEO_CASILLAS_F350["Rentas de trabajo"]["PJ"]
        assert cas_b is None and cas_r is None


# =============================================================================
# autorretencion
# =============================================================================

class TestAutorretencion:
    def test_calculo_cuenta_4(self):
        from core.f350 import calcular_autorretencion_cuenta_4
        balance = {
            "cuentas": [
                {"codigo": "4",  "nivel": 1, "creditos": 100_000_000, "debitos": 0},
                {"codigo": "41", "nivel": 2, "creditos":  90_000_000, "debitos": 0},
                {"codigo": "42", "nivel": 2, "creditos":  10_000_000, "debitos": 0},
            ]
        }
        r = calcular_autorretencion_cuenta_4(balance, 1.10)
        assert r["ingresos_netos"] == 100_000_000
        assert r["autorretencion"] == 1_100_000

    def test_sin_cuenta_4_retorna_none(self):
        from core.f350 import calcular_autorretencion_cuenta_4
        balance = {"cuentas": [{"codigo": "11", "creditos": 0, "debitos": 0}]}
        assert calcular_autorretencion_cuenta_4(balance, 1.10) is None

    def test_aproximar_redondeo_dian(self):
        from core.f350 import aproximar_a_miles
        # Regla Art. 577 ET
        assert aproximar_a_miles(450400) == 450000
        assert aproximar_a_miles(450500) == 451000   # 500 redondea arriba
        assert aproximar_a_miles(7993164) == 7993000
        assert aproximar_a_miles(726651300) == 726651000
        assert aproximar_a_miles(0) == 0
        assert aproximar_a_miles(None) == 0


# =============================================================================
# PDF F350 (smoke test)
# =============================================================================

class TestPdfF350:
    def test_genera_pdf_valido(self):
        from core.f350 import generar_pdf_formulario_350
        datos = {
            "año": 2026,
            "periodo": 3,
            "nit": "900473959",
            "dv": "1",
            "razon_social": "EMPRESA TEST SAS",
            "ciiu": "5611",
            "tarifa_autorret": 3.50,
            "retenciones": [
                {"concepto": "Honorarios", "tipo": "PN", "base": 5_000_000, "retencion": 550_000},
                {"concepto": "Servicios",  "tipo": "PJ", "base": 10_000_000, "retencion": 400_000},
            ],
            "autorretenciones": [
                {"concepto": "Ventas", "base": 200_000_000, "retencion": 7_000_000},
            ],
            "total_iva": 850_000,
        }
        pdf = generar_pdf_formulario_350(datos)
        assert isinstance(pdf, bytes)
        assert pdf[:4] == b"%PDF"  # firma PDF
        assert len(pdf) > 2000     # algo de contenido real


# =============================================================================
# parser_contai — regresión de los bugs de continuación de página y
# de interpretación de la columna de retención
# =============================================================================

class TestParserContaiRegresion:
    """
    Reproduce con un PDF sintético (formato Contai) los dos bugs que hacían
    que se perdieran/subvaluaran retenciones:

      1. Cuentas que continúan en la página siguiente con el prefijo
         "Continua con la cuenta : ..." perdían TODOS sus movimientos de
         las páginas posteriores.

      2. Las líneas con 3 columnas numéricas (débito, retención, base) se
         interpretaban como retención = créditos - débitos, subvaluando la
         retención real. La retención correcta es la columna inmediatamente
         anterior a la base.
    """

    def _construir_pdf_dos_paginas(self):
        """Genera en memoria un PDF que imita el auxiliar de Contai con una
        cuenta de arrendamientos partida entre dos páginas."""
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        import io

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.setFont("Courier", 9)

        def escribir(lineas):
            y = 750
            for ln in lineas:
                c.drawString(40, y, ln)
                y -= 12

        # ---- Página 1 ----
        escribir([
            "==============================================================",
            "May-22-2026 *** PAGINA : 1",
            "EMPRESA DE PRUEBA S.A.S - 900.307.969-5",
            "Analisis de % de Retencion e IVA - Resumido",
            "Cuenta Nombre Cuenta Debitos Creditos Base Retencion % NIT Nombre",
            "--------------------------------------------------------------",
            "23-65-30-01 ARRENDAMIENTOS 3.5%",
            # línea de 3 columnas: debito 150,512 / retencion 301,024 / base 4,300,339
            "150,512.00 301,024.00 4,300,339.00 3.50 42890751 ROSA VERONICA",
            # línea de 2 columnas: retencion 57,274 / base 1,636,413
            "57,274.00 1,636,413.00 3.50 43869549 ANA MARIA GIRALDO",
        ])
        c.showPage()

        # ---- Página 2 (la cuenta CONTINÚA) ----
        c.setFont("Courier", 9)
        escribir([
            "==============================================================",
            "May-22-2026 *** PAGINA : 2",
            "EMPRESA DE PRUEBA S.A.S - 900.307.969-5",
            "Cuenta Nombre Cuenta Debitos Creditos Base Retencion % NIT Nombre",
            "--------------------------------------------------------------",
            "Continua con la cuenta : 23-65-30-01 ARRENDAMIENTOS 3.5%",
            "262,570.00 7,502,000.00 3.50 800142245 CIUDADELA COMERCIAL",
            "284,052.00 8,115,768.00 3.50 901156140 RAZEM S.A.S",
            "--------------------------------------------------------------",
            "Total Cuenta 150,512.00 904,920.00 21,554,520.00",
        ])
        c.showPage()
        c.save()
        return buf.getvalue()

    def test_continuacion_pagina_no_pierde_movimientos(self):
        from core.f350.parser_contai import parsear_auxiliar_contai
        pdf = self._construir_pdf_dos_paginas()
        r = parsear_auxiliar_contai(pdf)
        movs = [m for m in r["movimientos"] if m["cuenta"] == "23-65-30-01"]
        # 2 de la página 1 + 2 de la página 2 = 4 (antes del fix solo salían 2)
        assert len(movs) == 4, f"Se esperaban 4 movimientos, salieron {len(movs)}"

    def test_retencion_columna_correcta(self):
        from core.f350.parser_contai import parsear_auxiliar_contai
        pdf = self._construir_pdf_dos_paginas()
        r = parsear_auxiliar_contai(pdf)
        por_nit = {m["nit"]: m for m in r["movimientos"]}

        # Línea de 3 columnas: la retención es la 2ª (301,024), NO 301,024-150,512
        assert por_nit["42890751"]["retencion"] == 301_024
        assert por_nit["42890751"]["base"] == 4_300_339

        # Línea de 2 columnas: la retención es la 1ª (57,274)
        assert por_nit["43869549"]["retencion"] == 57_274
        assert por_nit["43869549"]["base"] == 1_636_413

    def test_total_cuenta_cuadra(self):
        from core.f350.parser_contai import parsear_auxiliar_contai
        pdf = self._construir_pdf_dos_paginas()
        r = parsear_auxiliar_contai(pdf)
        movs = [m for m in r["movimientos"] if m["cuenta"] == "23-65-30-01"]
        suma_ret = sum(m["retencion"] for m in movs)
        suma_base = sum(m["base"] for m in movs)
        # 301,024 + 57,274 + 262,570 + 284,052 = 904,920 (= "Total Cuenta" créditos)
        assert suma_ret == 904_920
        assert suma_base == 21_554_520


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
