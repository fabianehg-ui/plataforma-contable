"""
Tests del agregador de terceros desde resultados de procesamiento XML.
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.procesadores.agregador_terceros_xml import (
    construir_maestro_desde_resultados,
    detectar_nits_nuevos,
)


# Mock de los dataclass que usa el agregador
@dataclass
class DocMock:
    nit_emisor: str
    nombre_emisor: str
    regimen_emisor: str = ""
    direccion_emisor: str = ""
    ciudad_emisor: str = ""
    codigo_ciudad_emisor: str = ""
    email_emisor: str = ""
    telefono_emisor: str = ""
    actividad_economica_emisor: str = ""


@dataclass
class ResMock:
    documentos: list = field(default_factory=list)


class TestConstruirMaestro:

    def test_un_solo_documento(self):
        res = ResMock(documentos=[
            DocMock(
                nit_emisor="900123456-1",
                nombre_emisor="EJEMPLO SAS",
                direccion_emisor="CRA 50 # 30-15",
                ciudad_emisor="MEDELLIN",
                codigo_ciudad_emisor="5001",
                email_emisor="ejemplo@ejemplo.com",
                telefono_emisor="3001234567",
                regimen_emisor="R-48",
                actividad_economica_emisor="4711",
            ),
        ])
        maestro = construir_maestro_desde_resultados([res])

        assert "900123456" in maestro["terceros"]
        datos = maestro["terceros"]["900123456"]
        assert datos["nombre"] == "EJEMPLO SAS"
        assert datos["direccion"] == "CRA 50 # 30-15"
        assert datos["ciudad"] == "MEDELLIN"
        assert datos["codigo_ciudad"] == "5001"
        assert datos["email"] == "ejemplo@ejemplo.com"
        assert datos["telefono"] == "3001234567"
        assert datos["tax_level_principal"] == "R-48"
        assert datos["actividad_economica"] == "4711"

    def test_multiples_documentos_mismo_nit(self):
        """Si el mismo NIT aparece varias veces, se conserva la info más rica."""
        res = ResMock(documentos=[
            DocMock(
                nit_emisor="900123456",
                nombre_emisor="EJEMPLO SAS",
                # Sin email ni telefono
            ),
            DocMock(
                nit_emisor="900123456",
                nombre_emisor="EJEMPLO SAS",
                email_emisor="ejemplo@ejemplo.com",
                telefono_emisor="3001234567",
            ),
        ])
        maestro = construir_maestro_desde_resultados([res])
        datos = maestro["terceros"]["900123456"]
        # Se debe haber rellenado con la info del segundo documento
        assert datos["email"] == "ejemplo@ejemplo.com"
        assert datos["telefono"] == "3001234567"

    def test_nit_vacio_se_ignora(self):
        res = ResMock(documentos=[
            DocMock(nit_emisor="", nombre_emisor="SIN NIT"),
        ])
        maestro = construir_maestro_desde_resultados([res])
        assert len(maestro["terceros"]) == 0

    def test_multiples_resultados(self):
        """Agregar terceros de varios ResultadoProcesamiento."""
        r1 = ResMock(documentos=[DocMock(nit_emisor="111", nombre_emisor="A")])
        r2 = ResMock(documentos=[DocMock(nit_emisor="222", nombre_emisor="B")])
        maestro = construir_maestro_desde_resultados([r1, r2])
        assert set(maestro["terceros"].keys()) == {"111", "222"}


class TestDetectarNitsNuevos:

    def test_sin_historico_todos_son_nuevos(self):
        maestro = {"terceros": {"111": {}, "222": {}}}
        nuevos = detectar_nits_nuevos(maestro, ruta_historico_compras=None)
        assert nuevos == {"111", "222"}

    def test_con_nits_extra_conocidos(self):
        maestro = {"terceros": {"111": {}, "222": {}, "333": {}}}
        nuevos = detectar_nits_nuevos(
            maestro,
            ruta_historico_compras=None,
            nits_extra_conocidos={"111", "222"},
        )
        assert nuevos == {"333"}

    def test_normalizacion_nit_con_dv(self):
        """NITs con DV deben matchearse: '900123456-1' = '900123456'."""
        maestro = {"terceros": {"900123456": {}}}
        nuevos = detectar_nits_nuevos(
            maestro,
            ruta_historico_compras=None,
            nits_extra_conocidos={"900123456-1"},
        )
        assert nuevos == set()
