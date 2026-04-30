"""
Tests para las funcionalidades nuevas v0.2:
- Multi-ZIP (procesar varios ZIPs en una sola pasada)
- Deduplicación por CUFE
- Filtrado por rango de fechas
- Detección de inconsistencia tipo declarado vs real
- Reporte ejecutivo
- Detección de servicios públicos
- Separación de plano por comprobante
"""
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core" / "procesadores"))
sys.path.insert(0, str(Path(__file__).parent))

from procesador_dian_xml import (  # type: ignore
    RegistryEmpresas,
    procesar_multiples_zips,
    separar_lineas_por_comprobante,
    generar_reporte_ejecutivo,
    es_servicio_publico,
    parsear_xml_dian,
    ZipInput,
)
from test_procesador_dian_xml import xml_invoice, empaquetar_zip_maestro

EMPRESAS_DIR = Path(__file__).parent.parent / "core" / "data" / "empresas"


class TestMultiZip(unittest.TestCase):
    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)

    def test_dos_zips_separados_por_tipo(self):
        # ZIP 1: facturas
        zip_fe = empaquetar_zip_maestro([
            ("fe1", xml_invoice(prefijo="FE", numero="100", cufe="a" * 96)),
            ("fe2", xml_invoice(prefijo="FE", numero="101", cufe="b" * 96)),
        ])
        # ZIP 2: notas crédito
        zip_nc = empaquetar_zip_maestro([
            ("nc1", xml_invoice(tipo="CreditNote", prefijo="NC", numero="50", cufe="c" * 96)),
        ])

        zips = [
            ZipInput(nombre="FE_marzo.zip", contenido=zip_fe, tipo_declarado="FE"),
            ZipInput(nombre="NC_marzo.zip", contenido=zip_nc, tipo_declarado="NC"),
        ]
        resultados, resumen = procesar_multiples_zips(zips, self.reg, "202603")

        self.assertEqual(resumen.total_xmls_extraidos, 3)
        self.assertEqual(resumen.duplicados_descartados, 0)
        self.assertEqual(resumen.por_tipo["factura_recibida"], 2)
        self.assertEqual(resumen.por_tipo["nota_credito_recibida"], 1)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0].empresa_id, "silla_tres")

    def test_deduplicacion_por_cufe(self):
        # El mismo CUFE en dos ZIPs → solo se procesa una vez
        cufe_compartido = "x" * 96
        zip_a = empaquetar_zip_maestro([
            ("fe1", xml_invoice(prefijo="FE", numero="100", cufe=cufe_compartido)),
        ])
        zip_b = empaquetar_zip_maestro([
            ("fe1_dup", xml_invoice(prefijo="FE", numero="100", cufe=cufe_compartido)),
            ("fe2", xml_invoice(prefijo="FE", numero="200", cufe="y" * 96)),
        ])

        zips = [
            ZipInput(nombre="A.zip", contenido=zip_a, tipo_declarado="FE"),
            ZipInput(nombre="B.zip", contenido=zip_b, tipo_declarado="FE"),
        ]
        resultados, resumen = procesar_multiples_zips(zips, self.reg, "202603")

        self.assertEqual(resumen.total_xmls_extraidos, 3)
        self.assertEqual(resumen.duplicados_descartados, 1)
        # Solo 2 docs únicos en el resultado
        self.assertEqual(len(resultados[0].documentos), 2)

    def test_filtro_por_rango_fechas(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe_marzo", xml_invoice(fecha="2026-03-15", cufe="a" * 96)),
            ("fe_febrero", xml_invoice(fecha="2026-02-15", cufe="b" * 96)),
            ("fe_abril", xml_invoice(fecha="2026-04-15", cufe="c" * 96)),
        ])
        zips = [ZipInput(nombre="mix.zip", contenido=zip_bytes, tipo_declarado="FE")]

        # Filtrar solo marzo
        resultados, resumen = procesar_multiples_zips(
            zips, self.reg, "202603",
            fecha_desde="2026-03-01", fecha_hasta="2026-03-31",
        )

        self.assertEqual(resumen.total_xmls_extraidos, 3)
        self.assertEqual(resumen.fuera_de_rango_fecha, 2)
        self.assertEqual(len(resultados[0].documentos), 1)

    def test_inconsistencia_tipo_declarado(self):
        # Usuario declara que es ZIP de FE pero contiene una NC
        zip_bytes = empaquetar_zip_maestro([
            ("ok_fe", xml_invoice(prefijo="FE", numero="100", cufe="a" * 96)),
            ("infiltrada_nc", xml_invoice(
                tipo="CreditNote", prefijo="NC", numero="50", cufe="b" * 96
            )),
        ])
        zips = [ZipInput(nombre="FE.zip", contenido=zip_bytes, tipo_declarado="FE")]
        resultados, resumen = procesar_multiples_zips(zips, self.reg, "202603")

        self.assertEqual(len(resumen.inconsistencias_tipo), 1)
        self.assertEqual(resumen.inconsistencias_tipo[0]["tipo_declarado"], "FE")
        self.assertIn("nota_credito", resumen.inconsistencias_tipo[0]["tipo_real"])
        # Pero AÚN ASÍ se procesa correctamente (el sistema confía en el XML, no en la declaración)
        self.assertEqual(len(resultados[0].documentos), 2)

    def test_zips_de_distintas_empresas_se_separan(self):
        zip_silla = empaquetar_zip_maestro([
            ("fe1", xml_invoice(nit_receptor="900451388", cufe="a" * 96)),
        ])
        zip_casa = empaquetar_zip_maestro([
            ("fe2", xml_invoice(nit_receptor="900473959", cufe="b" * 96)),
        ])
        zips = [
            ZipInput(nombre="Silla.zip", contenido=zip_silla, tipo_declarado="FE"),
            ZipInput(nombre="Casa.zip", contenido=zip_casa, tipo_declarado="FE"),
        ]
        resultados, resumen = procesar_multiples_zips(zips, self.reg, "202603")

        ids = {r.empresa_id for r in resultados}
        self.assertIn("silla_tres", ids)
        self.assertIn("casa_unotres", ids)
        self.assertEqual(resumen.por_empresa["silla_tres"], 1)
        self.assertEqual(resumen.por_empresa["casa_unotres"], 1)

    def test_4_tipos_documentos_juntos(self):
        # Caso real: usuario sube los 4 tipos en ZIPs separados
        zip_fe = empaquetar_zip_maestro([
            ("fe1", xml_invoice(prefijo="FE", numero="100", cufe="a" * 96)),
            ("fe2", xml_invoice(prefijo="FE", numero="101", cufe="b" * 96)),
        ])
        zip_nc = empaquetar_zip_maestro([
            ("nc1", xml_invoice(tipo="CreditNote", prefijo="NC", numero="50", cufe="c" * 96)),
        ])
        zip_nd = empaquetar_zip_maestro([
            ("nd1", xml_invoice(tipo="DebitNote", prefijo="ND", numero="10", cufe="d" * 96)),
        ])
        # DS = FE recibida de servicios públicos (lo que entendimos del usuario)
        zip_ds = empaquetar_zip_maestro([
            ("epm1", xml_invoice(
                nit_emisor="830037946",
                nombre_emisor="Empresas Públicas de Medellín ESP",
                items=[{"desc": "Energía eléctrica marzo 2026 - 250 kWh",
                        "cantidad": 1, "precio": 85000, "iva_pct": 19}],
                cufe="e" * 96,
            )),
        ])

        zips = [
            ZipInput(nombre="FE.zip", contenido=zip_fe, tipo_declarado="FE"),
            ZipInput(nombre="NC.zip", contenido=zip_nc, tipo_declarado="NC"),
            ZipInput(nombre="ND.zip", contenido=zip_nd, tipo_declarado="ND"),
            ZipInput(nombre="DS.zip", contenido=zip_ds, tipo_declarado="DS"),
        ]
        resultados, resumen = procesar_multiples_zips(zips, self.reg, "202603")

        self.assertEqual(resumen.total_xmls_extraidos, 5)
        self.assertEqual(resumen.por_tipo["factura_recibida"], 3)  # FE + DS (que en realidad es FE 01)
        self.assertEqual(resumen.por_tipo["nota_credito_recibida"], 1)
        self.assertEqual(resumen.por_tipo["nota_debito_recibida"], 1)


class TestSeparacionPorComprobante(unittest.TestCase):
    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)

    def test_separa_comp7_comp13(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice(prefijo="FE", numero="100", cufe="a" * 96)),
            ("nc1", xml_invoice(tipo="CreditNote", prefijo="NC", numero="50", cufe="b" * 96)),
        ])
        zips = [ZipInput(nombre="all.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603")

        separado = separar_lineas_por_comprobante(resultados[0].lineas_plano)
        self.assertIn("COMP 7", separado)
        self.assertIn("COMP 13", separado)
        # COMP 7 solo tiene líneas de la FE; COMP 13 solo de la NC
        for l in separado["COMP 7"]:
            self.assertEqual(l.comprobante, "COMP 7")
        for l in separado["COMP 13"]:
            self.assertEqual(l.comprobante, "COMP 13")

    def test_cuadre_se_mantiene_al_separar(self):
        # Cada plano separado debe cuadrar Db = Cr por sí solo
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice(prefijo="FE", numero="100", cufe="a" * 96)),
            ("fe2", xml_invoice(prefijo="FE", numero="101", cufe="b" * 96)),
            ("nc1", xml_invoice(tipo="CreditNote", prefijo="NC", numero="50", cufe="c" * 96)),
        ])
        zips = [ZipInput(nombre="all.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603")

        separado = separar_lineas_por_comprobante(resultados[0].lineas_plano)
        for comp, lineas in separado.items():
            db = sum((l.debito for l in lineas), Decimal(0))
            cr = sum((l.credito for l in lineas), Decimal(0))
            self.assertEqual(db, cr, f"Comprobante {comp} no cuadra: Db={db} Cr={cr}")


class TestReporteEjecutivo(unittest.TestCase):
    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)

    def test_kpis_basicos(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice(
                nit_emisor="891301549", nombre_emisor="NUTRIENTES AVICOLAS S.A.S.",
                items=[{"desc": "Alimento", "cantidad": 10, "precio": 100000, "iva_pct": 0}],
                cufe="a" * 96,
            )),
            ("fe2", xml_invoice(
                nit_emisor="890900099", nombre_emisor="Industrias Estra",
                items=[{"desc": "Café", "cantidad": 5, "precio": 30000, "iva_pct": 19}],
                cufe="b" * 96,
            )),
            ("nc1", xml_invoice(
                tipo="CreditNote",
                nit_emisor="891301549", nombre_emisor="NUTRIENTES AVICOLAS S.A.S.",
                items=[{"desc": "Devolución", "cantidad": 1, "precio": 100000, "iva_pct": 0}],
                cufe="c" * 96,
            )),
        ])
        zips = [ZipInput(nombre="m.zip", contenido=zip_bytes)]
        resultados, _ = procesar_multiples_zips(zips, self.reg, "202603")

        rep = generar_reporte_ejecutivo(resultados[0])

        self.assertEqual(rep["documentos_validos"], 3)
        # Compras brutas = 1.000.000 (alimento, sin IVA) + 178.500 (café 150k + IVA 19%) = 1.178.500
        self.assertEqual(rep["total_compras_brutas"], 1178500.0)
        # NC = 100.000 (alimento sin IVA)
        self.assertEqual(rep["total_notas_credito"], 100000.0)
        # Netas = 1.178.500 - 100.000 = 1.078.500
        self.assertEqual(rep["total_compras_netas"], 1078500.0)
        # Top proveedores: el primero debe ser Nutrientes (1M-100k=900k) y el segundo Estra (178.500)
        self.assertEqual(rep["top_proveedores"][0]["nit"], "891301549")
        self.assertEqual(rep["top_proveedores"][0]["valor"], 900000.0)


class TestServiciosPublicos(unittest.TestCase):
    def test_detecta_epm(self):
        xml = xml_invoice(
            nit_emisor="830037946",
            nombre_emisor="Empresas Públicas de Medellín ESP",
            items=[{"desc": "Energía eléctrica residencial 250 kWh",
                    "cantidad": 1, "precio": 85000, "iva_pct": 0}],
        )
        doc = parsear_xml_dian(xml)
        es_sp, tipo = es_servicio_publico(doc)
        self.assertTrue(es_sp)
        self.assertEqual(tipo, "energia")

    def test_detecta_acueducto(self):
        xml = xml_invoice(
            nit_emisor="899999094",
            nombre_emisor="EAAB - Empresa de Acueducto y Alcantarillado de Bogotá",
            items=[{"desc": "Consumo agua m3", "cantidad": 1, "precio": 25000, "iva_pct": 0}],
        )
        doc = parsear_xml_dian(xml)
        es_sp, tipo = es_servicio_publico(doc)
        self.assertTrue(es_sp)
        self.assertEqual(tipo, "agua")

    def test_detecta_internet_claro(self):
        xml = xml_invoice(
            nit_emisor="800153993",
            nombre_emisor="COMUNICACIÓN CELULAR S.A. ESP",
            items=[{"desc": "Plan internet hogar fibra óptica 100 megas",
                    "cantidad": 1, "precio": 80000, "iva_pct": 19}],
        )
        doc = parsear_xml_dian(xml)
        es_sp, tipo = es_servicio_publico(doc)
        self.assertTrue(es_sp)
        self.assertEqual(tipo, "telecomunicaciones")

    def test_no_es_servicio_publico(self):
        xml = xml_invoice(
            nit_emisor="891301549",
            nombre_emisor="NUTRIENTES AVICOLAS S.A.S.",
            items=[{"desc": "Alimento concentrado", "cantidad": 1, "precio": 100000, "iva_pct": 0}],
        )
        doc = parsear_xml_dian(xml)
        es_sp, tipo = es_servicio_publico(doc)
        self.assertFalse(es_sp)
        self.assertEqual(tipo, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
