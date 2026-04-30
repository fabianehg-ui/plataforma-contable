"""Tests v0.2.1 — modo de filtro de fecha + reporte detallado de descartes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core" / "procesadores"))
sys.path.insert(0, str(Path(__file__).parent))

from procesador_dian_xml import (
    RegistryEmpresas,
    procesar_multiples_zips,
    ZipInput,
)
from test_procesador_dian_xml import xml_invoice, empaquetar_zip_maestro

EMPRESAS_DIR = Path(__file__).parent.parent / "core" / "data" / "empresas"


class TestModoFiltroFecha(unittest.TestCase):
    """Verifica que el filtro funcione en sus 3 modos: ninguno / emision / recepcion."""

    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)

    def test_modo_ninguno_no_descarta_nada_por_fecha(self):
        # 3 facturas con fechas muy diferentes, todas deben pasar
        zip_bytes = empaquetar_zip_maestro([
            ("fe_2024", xml_invoice(fecha="2024-01-15", cufe="a" * 96)),
            ("fe_2025", xml_invoice(fecha="2025-06-15", cufe="b" * 96)),
            ("fe_2026", xml_invoice(fecha="2026-03-15", cufe="c" * 96)),
        ])
        zips = [ZipInput(nombre="todo.zip", contenido=zip_bytes)]

        # Con modo "ninguno" + rango marzo 2026 NO descarta nada
        resultados, resumen = procesar_multiples_zips(
            zips, self.reg, "202603",
            fecha_desde="2026-03-01", fecha_hasta="2026-03-31",
            modo_filtro_fecha="ninguno",
        )

        self.assertEqual(resumen.fuera_de_rango_fecha, 0)
        self.assertEqual(len(resultados[0].documentos), 3)

    def test_modo_emision_filtra_por_emision(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe_feb", xml_invoice(fecha="2026-02-15", cufe="a" * 96)),
            ("fe_mar", xml_invoice(fecha="2026-03-15", cufe="b" * 96)),
        ])
        zips = [ZipInput(nombre="x.zip", contenido=zip_bytes)]

        resultados, resumen = procesar_multiples_zips(
            zips, self.reg, "202603",
            fecha_desde="2026-03-01", fecha_hasta="2026-03-31",
            modo_filtro_fecha="emision",
        )

        self.assertEqual(resumen.fuera_de_rango_fecha, 1)
        self.assertEqual(len(resultados[0].documentos), 1)


class TestDescartadosDetalle(unittest.TestCase):
    """Verifica que se reporte el detalle de cada descarte para diagnosticar."""

    def setUp(self):
        self.reg = RegistryEmpresas(EMPRESAS_DIR)

    def test_descartes_por_fecha_aparecen_en_detalle(self):
        zip_bytes = empaquetar_zip_maestro([
            ("fe_feb", xml_invoice(fecha="2026-02-15", cufe="a" * 96, prefijo="FE", numero="200")),
            ("fe_mar", xml_invoice(fecha="2026-03-15", cufe="b" * 96, prefijo="FE", numero="300")),
        ])
        zips = [ZipInput(nombre="m.zip", contenido=zip_bytes)]

        _, resumen = procesar_multiples_zips(
            zips, self.reg, "202603",
            fecha_desde="2026-03-01", fecha_hasta="2026-03-31",
            modo_filtro_fecha="emision",
        )

        descartes_fecha = [d for d in resumen.descartados_detalle if d["razon"] == "fuera_de_rango_fecha"]
        self.assertEqual(len(descartes_fecha), 1)
        # El descarte debe tener metadata útil para debugging
        self.assertEqual(descartes_fecha[0]["fecha_emision"], "2026-02-15")
        self.assertEqual(descartes_fecha[0]["documento"], "FE200")
        self.assertEqual(descartes_fecha[0]["modo_filtro"], "emision")

    def test_descartes_por_duplicado_aparecen_en_detalle(self):
        cufe_dup = "x" * 96
        zip_bytes = empaquetar_zip_maestro([
            ("fe1", xml_invoice(cufe=cufe_dup, prefijo="FE", numero="100")),
            ("fe1_dup", xml_invoice(cufe=cufe_dup, prefijo="FE", numero="100")),
        ])
        zips = [ZipInput(nombre="m.zip", contenido=zip_bytes)]

        _, resumen = procesar_multiples_zips(zips, self.reg, "202603", modo_filtro_fecha="ninguno")

        descartes_dup = [d for d in resumen.descartados_detalle if d["razon"] == "duplicado_cufe"]
        self.assertEqual(len(descartes_dup), 1)
        self.assertIn("cufe", descartes_dup[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
