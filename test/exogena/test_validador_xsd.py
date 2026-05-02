"""Tests rápidos del validador XSD."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core.exogena.validador_xsd import ValidadorExogena, FORMATOS_SOPORTADOS

from core.exogena import XSD_DIR


def test_formato_1009_valido():
    """XML válido del formato 1009 (saldos por pagar)."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<saldoscp>
  <saldo cpt="2201" tdoc="31" nid="900123456" dv="1"
         raz="PROVEEDOR EJEMPLO SAS"
         dir="CALLE 100 # 10-20" dpto="11" mun="001" pais="169"
         sal="50000000"/>
  <saldo cpt="2201" tdoc="13" nid="71234567"
         apl1="GARCIA" apl2="LOPEZ" nom1="JUAN" nom2="CARLOS"
         dpto="05" mun="001" pais="169"
         sal="3000000"/>
</saldoscp>"""
    v = ValidadorExogena(XSD_DIR)
    r = v.validar('1009', xml)
    assert r.es_valido, f"Debió ser válido. Errores: {r.errores}"
    assert r.cantidad_registros == 2
    print(f"  ✓ {r.cantidad_registros} registros válidos en 1009")


def test_formato_1001_falta_requerido():
    """XML inválido: falta atributo requerido 'cpt'."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<pagos>
  <pago tdoc="31" nid="900123456" raz="PROVEEDOR" pais="169"
        pago="1000000" pnded="0" ided="0" inded="0"
        retp="0" reta="0" comun="0" ndom="0"/>
</pagos>"""
    v = ValidadorExogena(XSD_DIR)
    r = v.validar('1001', xml)
    assert not r.es_valido, "Debió ser inválido (falta cpt)"
    assert any('cpt' in e for e in r.errores), f"Error de cpt no detectado: {r.errores}"
    print(f"  ✓ Error de atributo requerido detectado: {r.errores[0]}")


def test_formato_1001_excede_longitud():
    """XML inválido: razón social excede 450 caracteres."""
    razon_larga = 'A' * 500
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<pagos>
  <pago cpt="5001" tdoc="31" nid="900123456" raz="{razon_larga}" pais="169"
        pago="1000000" pnded="0" ided="0" inded="0"
        retp="0" reta="0" comun="0" ndom="0"/>
</pagos>"""
    v = ValidadorExogena(XSD_DIR)
    r = v.validar('1001', xml)
    assert not r.es_valido
    assert any('raz' in e and 'excede' in e for e in r.errores), f"No detectó exceso: {r.errores}"
    print(f"  ✓ Exceso de longitud detectado")


def test_todos_los_xsd_se_cargan():
    """Verificar que los 15 XSDs cargan sin errores."""
    v = ValidadorExogena(XSD_DIR)
    for fmt in sorted(FORMATOS_SOPORTADOS):
        schema = v._cargar_schema(fmt)
        assert len(schema['atributos']) > 0, f"Formato {fmt} sin atributos"
    print(f"  ✓ Los {len(FORMATOS_SOPORTADOS)} XSDs cargan correctamente")


def test_xml_mal_formado():
    """XML mal formado debe reportar error."""
    xml = "<no-cierra"
    v = ValidadorExogena(XSD_DIR)
    r = v.validar('1001', xml)
    assert not r.es_valido
    assert any('mal formado' in e for e in r.errores)
    print(f"  ✓ XML mal formado detectado")


if __name__ == '__main__':
    print("\nTests del validador XSD:\n")
    test_todos_los_xsd_se_cargan()
    test_formato_1009_valido()
    test_formato_1001_falta_requerido()
    test_formato_1001_excede_longitud()
    test_xml_mal_formado()
    print("\n✅ Todos los tests pasaron")
