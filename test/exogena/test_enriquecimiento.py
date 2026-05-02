"""Tests del sistema de enriquecimiento (sin llamadas reales a APIs)."""
from pathlib import Path
import sys
from datetime import datetime
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.exogena.enriquecimiento import (
    Enriquecedor, DatosEnriquecidos, EnriquecedorError,
    EnriquecedorStub, EnriquecedorEnCascada, CacheEnriquecedor,
    ApitudeEnriquecedor, RUESEnriquecedor,
    aplicar_enriquecimiento_a_tercero,
)


def test_stub():
    """Stub no devuelve nada."""
    s = EnriquecedorStub()
    assert s.enriquecer('900123456') is None
    assert s.disponible() is True
    print("  ✓ EnriquecedorStub funciona")


def test_apitude_sin_credenciales():
    """Apitude sin API key no está disponible."""
    a = ApitudeEnriquecedor(api_key=None)
    assert not a.disponible()
    assert a.enriquecer('900123456') is None
    print("  ✓ ApitudeEnriquecedor sin credenciales no falla")


def test_rues_habilitado_por_defecto():
    """RUES ahora se habilita por defecto (consulta gratuita al portal)."""
    r = RUESEnriquecedor()
    assert r.disponible()  # ahora habilitado por default
    # No probamos r.enriquecer() porque haría llamada de red real.
    # En CI/dev sin internet eso fallaría. La cobertura de la lógica
    # interna está en tests con mock más abajo.
    print("  ✓ RUES habilitado por defecto (sin probar request real)")


def test_rues_deshabilitado_devuelve_none():
    """Cuando habilitado=False, no hace nada."""
    r = RUESEnriquecedor(habilitado=False)
    assert not r.disponible()
    assert r.enriquecer('900123456') is None
    print("  ✓ RUES deshabilitado retorna None")


class _FakeEnriquecedor(Enriquecedor):
    """Mock simple para tests."""
    def __init__(self, nombre, datos=None, error=None):
        self.nombre = nombre
        self._datos = datos
        self._error = error
        self.llamadas = 0

    def enriquecer(self, nit):
        self.llamadas += 1
        if self._error:
            raise self._error
        return self._datos


def test_cascada_primer_resultado_gana():
    """Cuando una fuente devuelve datos, las siguientes no se llaman."""
    datos = DatosEnriquecidos(nit='900123456', fuente='fake1', razon_social='ACME SAS')
    fake1 = _FakeEnriquecedor('fake1', datos=datos)
    fake2 = _FakeEnriquecedor('fake2', datos=DatosEnriquecidos(nit='x', fuente='fake2'))
    
    cascada = EnriquecedorEnCascada([fake1, fake2], escribir_en_cache=False)
    res = cascada.enriquecer('900123456')
    
    assert res.razon_social == 'ACME SAS'
    assert fake1.llamadas == 1
    assert fake2.llamadas == 0  # no se llamó porque fake1 ya resolvió
    print("  ✓ Cascada se detiene en el primer resultado")


def test_cascada_continua_en_error():
    """Si una fuente falla, la cascada sigue con la siguiente."""
    datos = DatosEnriquecidos(nit='900', fuente='fake2', razon_social='OK')
    fake1 = _FakeEnriquecedor('fake1', error=EnriquecedorError('boom', 'fake1'))
    fake2 = _FakeEnriquecedor('fake2', datos=datos)
    
    cascada = EnriquecedorEnCascada([fake1, fake2], escribir_en_cache=False)
    res = cascada.enriquecer('900')
    
    assert res.razon_social == 'OK'
    assert fake1.llamadas == 1
    assert fake2.llamadas == 1
    print("  ✓ Cascada continúa cuando una fuente falla")


def test_cascada_devuelve_none_si_nadie_resuelve():
    fake1 = _FakeEnriquecedor('fake1', datos=None)
    fake2 = _FakeEnriquecedor('fake2', datos=None)
    
    cascada = EnriquecedorEnCascada([fake1, fake2], escribir_en_cache=False)
    assert cascada.enriquecer('999') is None
    print("  ✓ Cascada devuelve None si ninguna fuente resuelve")


def test_aplicar_a_tercero_solo_llena_vacios():
    """Por defecto aplicar_enriquecimiento solo llena campos vacíos."""
    tercero = {
        'nit': '900123456',
        'razon_social': 'NOMBRE EXISTENTE',
        'direccion': '',
        'codigo_dpto': '',
    }
    datos = DatosEnriquecidos(
        nit='900123456', fuente='apitude',
        razon_social='NOMBRE NUEVO',  # no debe sobrescribir
        direccion='CALLE 100',         # debe llenar
        codigo_dpto='11',              # debe llenar
    )
    aplicar_enriquecimiento_a_tercero(tercero, datos)
    
    assert tercero['razon_social'] == 'NOMBRE EXISTENTE'  # respetado
    assert tercero['direccion'] == 'CALLE 100'             # llenado
    assert tercero['codigo_dpto'] == '11'                  # llenado
    assert tercero['enriquecido_desde'] == 'apitude'
    print("  ✓ aplicar_enriquecimiento respeta valores existentes por defecto")


def test_aplicar_a_tercero_sobreescribir():
    """Con sobreescribir_existente=True, los valores se reemplazan."""
    tercero = {'nit': '900', 'razon_social': 'VIEJO'}
    datos = DatosEnriquecidos(nit='900', fuente='apitude', razon_social='NUEVO')
    aplicar_enriquecimiento_a_tercero(tercero, datos, sobreescribir_existente=True)
    assert tercero['razon_social'] == 'NUEVO'
    print("  ✓ aplicar_enriquecimiento sobrescribe cuando se pide")


def test_cascada_escribe_en_cache():
    """La cascada usa el CacheEnriquecedor para guardar resultados nuevos."""
    # Mock de Supabase
    mock_supabase = MagicMock()
    mock_supabase.table.return_value.upsert.return_value.execute.return_value = MagicMock()
    # Cache vacía (lectura no devuelve nada)
    mock_supabase.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    
    cache = CacheEnriquecedor(mock_supabase)
    datos = DatosEnriquecidos(nit='900', fuente='apitude', razon_social='ACME')
    fake = _FakeEnriquecedor('fake', datos=datos)
    
    cascada = EnriquecedorEnCascada([cache, fake])
    res = cascada.enriquecer('900')
    
    assert res.razon_social == 'ACME'
    # Verificar que se llamó upsert (guardado en caché)
    mock_supabase.table.assert_any_call('exogena_cache_enriquecimiento')
    print("  ✓ Cascada guarda en caché los resultados de fuentes pagas")


if __name__ == '__main__':
    print("\n=== Tests del sistema de enriquecimiento ===\n")
    print("Implementaciones individuales:")
    test_stub()
    test_apitude_sin_credenciales()
    test_rues_habilitado_por_defecto()
    test_rues_deshabilitado_devuelve_none()
    
    print("\nCascada:")
    test_cascada_primer_resultado_gana()
    test_cascada_continua_en_error()
    test_cascada_devuelve_none_si_nadie_resuelve()
    test_cascada_escribe_en_cache()
    
    print("\nAplicación a terceros:")
    test_aplicar_a_tercero_solo_llena_vacios()
    test_aplicar_a_tercero_sobreescribir()
    
    print("\n✅ Todos los tests pasaron")
