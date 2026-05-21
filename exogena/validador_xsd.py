"""
Validador de XMLs de información exógena DIAN contra los XSDs oficiales.

Uso típico:
    from validador_xsd import ValidadorExogena
    
    validador = ValidadorExogena(xsd_dir='ruta/a/xsd')
    resultado = validador.validar('1001', xml_string)
    if not resultado.es_valido:
        for error in resultado.errores:
            print(error)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET


# Formatos soportados (los 15 XSDs incluidos en el prevalidador v3.3)
FORMATOS_SOPORTADOS = {
    '1001', '1003', '1004', '1005', '1006', '1007', '1008',
    '1009', '1010', '1011', '1012', '1056', '1647', '2275', '2276',
}

# Formatos que aún no tienen XSD oficial (presentación distinta)
FORMATOS_SIN_XSD = {'2278', '5253'}


@dataclass
class ResultadoValidacion:
    """Resultado de validar un XML contra su XSD correspondiente."""
    formato: str
    es_valido: bool
    errores: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    cantidad_registros: int = 0


class ValidadorExogena:
    """Valida XMLs de exógena contra los XSDs oficiales de la DIAN."""

    def __init__(self, xsd_dir: str | Path):
        self.xsd_dir = Path(xsd_dir)
        if not self.xsd_dir.exists():
            raise FileNotFoundError(f"Directorio XSD no encontrado: {xsd_dir}")
        self._schemas_cache: dict[str, dict] = {}

    def _cargar_schema(self, formato: str) -> dict:
        """Carga el esquema del formato (parseado del XSD a un dict de atributos).
        
        Los XSDs del prevalidador definen dos elementos top-level:
          1. El elemento de datos repetitivo (ej: saldoscp, pagos, etc) con los atributos
          2. El elemento 'mas' (envelope) que contiene Cab + N registros
        
        Buscamos el elemento que tenga atributos (el de datos), no el envelope.
        """
        if formato in self._schemas_cache:
            return self._schemas_cache[formato]

        xsd_path = self.xsd_dir / f"{formato}.xsd"
        if not xsd_path.exists():
            raise FileNotFoundError(f"XSD no encontrado: {xsd_path}")

        tree = ET.parse(xsd_path)
        root = tree.getroot()
        ns = {'xs': 'http://www.w3.org/2001/XMLSchema'}

        # Buscar el elemento que tiene atributos (el de datos del registro)
        elemento_datos = None
        for elem in root.findall('xs:element', ns):
            ct = elem.find('xs:complexType', ns)
            if ct is not None and ct.find('xs:attribute', ns) is not None:
                elemento_datos = elem
                break
        
        if elemento_datos is None:
            raise ValueError(f"XSD {formato}: no se encontró elemento de datos con atributos")

        nombre_root = elemento_datos.get('name')
        complex_type = elemento_datos.find('xs:complexType', ns)
        atributos = {}

        for attr in complex_type.findall('xs:attribute', ns):
            nombre = attr.get('name')
            uso = attr.get('use', 'optional')
            tipo_attr = attr.get('type')
            
            simple_type = attr.find('xs:simpleType', ns)
            restricciones = {}
            if simple_type is not None:
                restriction = simple_type.find('xs:restriction', ns)
                if restriction is not None:
                    restricciones['base'] = restriction.get('base')
                    for child in restriction:
                        tag = child.tag.split('}')[-1]
                        valor = child.get('value')
                        if tag == 'pattern':
                            restricciones['pattern'] = valor
                        elif tag == 'minInclusive':
                            restricciones['minInclusive'] = valor
                        elif tag == 'maxInclusive':
                            restricciones['maxInclusive'] = valor
                        elif tag == 'minLength':
                            restricciones['minLength'] = int(valor) if valor else 0
                        elif tag == 'maxLength':
                            restricciones['maxLength'] = int(valor) if valor else 0
                        elif tag == 'fractionDigits':
                            restricciones['fractionDigits'] = int(valor)
                        elif tag == 'totalDigits':
                            restricciones['totalDigits'] = int(valor)

            atributos[nombre] = {
                'requerido': uso == 'required',
                'tipo': tipo_attr,
                'restricciones': restricciones,
            }

        schema = {
            'formato': formato,
            'elemento_raiz': nombre_root,
            'atributos': atributos,
        }
        self._schemas_cache[formato] = schema
        return schema

    def obtener_atributos(self, formato: str) -> dict:
        """Devuelve el dict de atributos esperados por el formato."""
        return self._cargar_schema(formato)['atributos']

    def validar(self, formato: str, xml_content: str | bytes) -> ResultadoValidacion:
        """Valida un XML completo contra el XSD del formato."""
        if formato not in FORMATOS_SOPORTADOS:
            if formato in FORMATOS_SIN_XSD:
                return ResultadoValidacion(
                    formato=formato, es_valido=False,
                    errores=[f"Formato {formato} no tiene XSD oficial en este paquete"],
                )
            return ResultadoValidacion(
                formato=formato, es_valido=False,
                errores=[f"Formato {formato} no soportado"],
            )

        schema = self._cargar_schema(formato)
        resultado = ResultadoValidacion(formato=formato, es_valido=True)

        try:
            if isinstance(xml_content, bytes):
                xml_content = xml_content.decode('utf-8')
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            resultado.es_valido = False
            resultado.errores.append(f"XML mal formado: {e}")
            return resultado

        # Validar cada registro
        registros = list(root)
        resultado.cantidad_registros = len(registros)

        for idx, registro in enumerate(registros, start=1):
            self._validar_registro(idx, registro, schema, resultado)

        if resultado.errores:
            resultado.es_valido = False

        return resultado

    def _validar_registro(self, idx: int, registro, schema: dict, resultado: ResultadoValidacion):
        """Valida un registro individual contra el esquema."""
        atributos_esperados = schema['atributos']
        atributos_xml = registro.attrib

        # Verificar atributos requeridos
        for nombre, info in atributos_esperados.items():
            if info['requerido'] and nombre not in atributos_xml:
                resultado.errores.append(
                    f"Registro {idx}: falta atributo requerido '{nombre}'"
                )

        # Verificar restricciones de cada atributo presente
        for nombre, valor in atributos_xml.items():
            if nombre not in atributos_esperados:
                resultado.advertencias.append(
                    f"Registro {idx}: atributo desconocido '{nombre}'"
                )
                continue
            self._validar_valor(idx, nombre, valor, atributos_esperados[nombre], resultado)

    def _validar_valor(self, idx: int, nombre: str, valor: str, info_attr: dict,
                       resultado: ResultadoValidacion):
        """Valida un valor individual contra sus restricciones."""
        restr = info_attr.get('restricciones', {})

        # MaxLength
        if 'maxLength' in restr and len(valor) > restr['maxLength']:
            resultado.errores.append(
                f"Registro {idx}: '{nombre}' excede máximo "
                f"({len(valor)} > {restr['maxLength']})"
            )

        # MinLength
        if 'minLength' in restr and len(valor) < restr['minLength']:
            resultado.errores.append(
                f"Registro {idx}: '{nombre}' por debajo del mínimo"
            )

        # Pattern
        import re
        if 'pattern' in restr:
            if not re.fullmatch(restr['pattern'], valor):
                resultado.errores.append(
                    f"Registro {idx}: '{nombre}' no coincide con patrón {restr['pattern']}"
                )

        # Rangos numéricos
        if 'minInclusive' in restr or 'maxInclusive' in restr:
            try:
                num = float(valor) if '.' in valor else int(valor)
                if 'minInclusive' in restr and num < float(restr['minInclusive']):
                    resultado.errores.append(
                        f"Registro {idx}: '{nombre}'={num} menor al mínimo "
                        f"({restr['minInclusive']})"
                    )
                if 'maxInclusive' in restr and num > float(restr['maxInclusive']):
                    resultado.errores.append(
                        f"Registro {idx}: '{nombre}'={num} mayor al máximo "
                        f"({restr['maxInclusive']})"
                    )
            except ValueError:
                resultado.errores.append(
                    f"Registro {idx}: '{nombre}' debe ser numérico"
                )


def listar_atributos_de_formato(formato: str, xsd_dir: str | Path) -> list[dict]:
    """Devuelve los atributos del formato como lista plana."""
    validador = ValidadorExogena(xsd_dir)
    schema = validador._cargar_schema(formato)
    return [
        {
            'nombre': nom,
            'requerido': info['requerido'],
            'tipo': info['tipo'],
            **info['restricciones'],
        }
        for nom, info in schema['atributos'].items()
    ]


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Uso: python validador_xsd.py <formato>")
        print("Ejemplo: python validador_xsd.py 1001")
        sys.exit(1)

    formato = sys.argv[1]
    xsd_dir = Path(__file__).parent.parent / 'xsd'

    print(f"\nAtributos del formato {formato}:\n")
    print(f"{'Atributo':<10} {'Req':<5} {'Tipo':<15} {'Restricciones'}")
    print("-" * 90)
    for attr in listar_atributos_de_formato(formato, xsd_dir):
        nom = attr['nombre']
        req = '✓' if attr['requerido'] else ''
        tipo = attr.get('tipo', '')
        rest = []
        if 'maxLength' in attr:
            rest.append(f"max={attr['maxLength']}")
        if 'minInclusive' in attr:
            rest.append(f"min={attr['minInclusive']}")
        if 'maxInclusive' in attr:
            rest.append(f"max={attr['maxInclusive']}")
        print(f"{nom:<10} {req:<5} {str(tipo):<15} {', '.join(rest)}")
