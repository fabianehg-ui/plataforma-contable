"""
Clasificador de NITs según reglas oficiales DIAN/Registraduría.

Aplica una regla híbrida que combina:
  1. Rangos numéricos oficiales del NIT
  2. Detección de palabras societarias en el nombre (SAS, LTDA, etc.)

Rangos oficiales (Resolución DIAN para asignación de NIT):
  10.000        – 99.999.999    → Cédula de ciudadanía vieja (CC=13, Natural)
  100.000.000   – 599.999.999   → Cédula nueva (CC=13, Natural)
  600.000.000   – 799.999.999   → NIT DIAN para residentes naturales (NIT=31, Natural)
  800.000.000   – 999.999.999   → NIT empresarial (NIT=31, Jurídica)
  1.000.000.000 – ∞             → Cédula nueva post-2000 (CC=13, Natural)
"""

from __future__ import annotations
from dataclasses import dataclass
import re


# Palabras y siglas que indican persona jurídica en el nombre/razón social
PALABRAS_JURIDICAS = re.compile(
    r'\b(S\.?A\.?S\.?|S\.?A\.?|LTDA\.?|EU|S\s*EN\s*C|CIA|COMPAÑIA|COMPANIA|'
    r'SOCIEDAD|EMPRESA|FUNDACION|FUNDACIÓN|ASOCIACION|ASOCIACIÓN|'
    r'CORPORACION|CORPORACIÓN|COOPERATIVA|COOP|HOLDING|GRUPO|'
    r'INVERSIONES|CONSTRUCTORA|COMERCIALIZADORA|DISTRIBUIDORA|'
    r'DISTRIBUIDORES|IMPORTADORA|EXPORTADORA|EDITORIAL|'
    r'INDUSTRIAS|INDUSTRIAL|TECNOLOGIA|TECNOLOGÍA|TRANSPORTES|'
    r'HOTEL|HOTELES|CLINICA|CLÍNICA|HOSPITAL|UNIVERSIDAD|COLEGIO|'
    r'INSTITUTO|FONDO|MUNICIPIO|SECRETARIA|SECRETARÍA|ALCALDIA|'
    r'ALCALDÍA|GOBERNACION|GOBERNACIÓN|MINISTERIO|BANCO|BANCOLOMBIA|'
    r'INC\.?|CORP\.?|LLC|LTD|GMBH|AG)\b',
    re.IGNORECASE
)


@dataclass
class ResultadoClasificacionNIT:
    tipo_documento: int          # código DIAN: 13=CC, 22=CE, 31=NIT, 41=Pasaporte
    tipo_persona: str            # 'natural' | 'juridica'
    regla_aplicada: str
    requiere_revision: bool = False
    sugerencias: list = None

    def __post_init__(self):
        if self.sugerencias is None:
            self.sugerencias = []


def calc_dv(nit_str: str) -> int:
    """Calcula el dígito de verificación del NIT (algoritmo DIAN)."""
    primos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    suma = sum(
        int(d) * primos[i]
        for i, d in enumerate(nit_str[::-1])
        if i < len(primos)
    )
    residuo = suma % 11
    return 11 - residuo if residuo > 1 else residuo


def detectar_nit_con_dv_pegado(nit_str: str) -> tuple[str, bool]:
    """Detecta el caso común donde el NIT viene con el DV pegado al final.
    
    Ej: 8903241775 → en realidad es NIT 890324177 con DV 5.
    
    Heurística: si el NIT tiene 10 dígitos y empieza por 8 ó 9 (rango empresarial),
    probablemente sea un NIT empresarial con DV pegado. Verificamos calculando el
    DV del NIT sin el último dígito y viendo si coincide.
    
    Returns:
        (nit_corregido, fue_corregido)
    """
    if not nit_str.isdigit() or len(nit_str) != 10:
        return nit_str, False
    
    if not nit_str.startswith(('8', '9')):
        return nit_str, False
    
    nit_sin_dv = nit_str[:-1]
    dv_pegado = int(nit_str[-1])
    dv_calculado = calc_dv(nit_sin_dv)
    
    if dv_calculado == dv_pegado:
        return nit_sin_dv, True
    return nit_str, False


def clasificar_nit(nit_str: str, nombre_pista: str = '') -> ResultadoClasificacionNIT:
    """
    Clasifica un NIT en tipo de documento y persona usando reglas oficiales.

    Args:
        nit_str: NIT como string (sin DV, sin puntos, sin guiones)
        nombre_pista: nombre completo o razón social del tercero
                      (se usa para detectar palabras societarias)

    Returns:
        ResultadoClasificacionNIT con tipo_documento, tipo_persona,
        regla_aplicada, requiere_revision y sugerencias.
    """
    nombre_upper = (nombre_pista or '').upper()
    tiene_palabra_juridica = bool(PALABRAS_JURIDICAS.search(nombre_upper))

    try:
        n = int(nit_str)
    except (ValueError, TypeError):
        return ResultadoClasificacionNIT(
            tipo_documento=13, tipo_persona='natural',
            regla_aplicada='NIT no numérico - default natural',
            requiere_revision=True,
            sugerencias=['REVISAR: NIT no es número válido'],
        )

    # ----------------------------------------------------------------
    # CASO 1: el nombre tiene palabra societaria → es jurídica seguro
    # ----------------------------------------------------------------
    if tiene_palabra_juridica:
        if 800_000_000 <= n <= 999_999_999:
            return ResultadoClasificacionNIT(
                tipo_documento=31, tipo_persona='juridica',
                regla_aplicada='Jurídica confirmada (rango 800M-999M + nombre societario)',
            )
        elif n < 800_000_000:
            return ResultadoClasificacionNIT(
                tipo_documento=31, tipo_persona='juridica',
                regla_aplicada=f'Jurídica por nombre - NIT={n:,} fuera de rango empresarial',
                requiere_revision=True,
                sugerencias=[
                    f'POSIBLE NIT INCOMPLETO: nombre tiene palabra societaria pero NIT={n:,} '
                    f'está fuera del rango 800M-999M. Verificar si faltan dígitos a la izquierda.'
                ],
            )
        else:
            return ResultadoClasificacionNIT(
                tipo_documento=31, tipo_persona='juridica',
                regla_aplicada='Jurídica por nombre societario (NIT >=1G)',
                requiere_revision=True,
                sugerencias=['NIT muy grande para empresa colombiana, verificar'],
            )

    # ----------------------------------------------------------------
    # CASO 2: aplicar rangos numéricos oficiales
    # ----------------------------------------------------------------
    if 10_000 <= n <= 99_999_999:
        return ResultadoClasificacionNIT(
            tipo_documento=13, tipo_persona='natural',
            regla_aplicada='CC vieja (10K-99.99M)',
        )
    elif 100_000_000 <= n <= 599_999_999:
        return ResultadoClasificacionNIT(
            tipo_documento=13, tipo_persona='natural',
            regla_aplicada='CC nueva (100M-599.99M)',
        )
    elif 600_000_000 <= n <= 799_999_999:
        return ResultadoClasificacionNIT(
            tipo_documento=31, tipo_persona='natural',
            regla_aplicada='NIT DIAN residentes (600M-799.99M)',
        )
    elif 800_000_000 <= n <= 999_999_999:
        return ResultadoClasificacionNIT(
            tipo_documento=31, tipo_persona='juridica',
            regla_aplicada='NIT empresarial (800M-999.99M)',
        )
    elif 1_000_000_000 <= n <= 9_999_999_999:
        return ResultadoClasificacionNIT(
            tipo_documento=13, tipo_persona='natural',
            regla_aplicada='CC nueva post-2000 (1G-9.99G)',
        )
    elif n > 9_999_999_999:
        return ResultadoClasificacionNIT(
            tipo_documento=22, tipo_persona='natural',
            regla_aplicada='NIT >10 dígitos - probable cédula de extranjería',
            requiere_revision=True,
            sugerencias=[f'NIT atípico ({len(str(n))} dígitos) - probable cédula de extranjería'],
        )
    else:
        # n < 10_000
        return ResultadoClasificacionNIT(
            tipo_documento=13, tipo_persona='natural',
            regla_aplicada=f'NIT muy pequeño ({n})',
            requiere_revision=True,
            sugerencias=[f'NIT muy pequeño ({n}) - probable error de carga'],
        )


def reclasificar_tercero(tercero: dict) -> dict:
    """
    Aplica la reclasificación a un dict de tercero existente.
    
    Modifica:
      - tipo_documento (si aplica)
      - tipo_persona
      - Agrega claves: regla_aplicada, requiere_revision, sugerencias
    
    Si el tipo cambia de natural→jurídica o viceversa, también ajusta
    los campos de nombre (mueve a razón social o separa nombres/apellidos).
    """
    nombre_completo = ' '.join(filter(None, [
        tercero.get('razon_social', ''),
        tercero.get('primer_nombre', ''),
        tercero.get('otros_nombres', ''),
        tercero.get('primer_apellido', ''),
        tercero.get('segundo_apellido', ''),
    ])).strip()

    # Intentar detectar NIT con DV pegado al final (caso común de error de carga)
    nit_original = tercero['nit']
    nit_corregido, fue_corregido = detectar_nit_con_dv_pegado(nit_original)
    if fue_corregido:
        tercero['nit'] = nit_corregido
        tercero['nit_original'] = nit_original  # guardar referencia

    res = clasificar_nit(tercero['nit'], nombre_completo)
    
    tipo_persona_anterior = tercero.get('tipo_persona', 'natural')
    cambio_tipo = res.tipo_persona != tipo_persona_anterior

    tercero['tipo_documento'] = res.tipo_documento
    tercero['tipo_persona'] = res.tipo_persona
    tercero['regla_aplicada'] = res.regla_aplicada
    tercero['requiere_revision'] = res.requiere_revision
    sugerencias_lista = list(res.sugerencias)
    if fue_corregido:
        sugerencias_lista.append(
            f'NIT corregido automáticamente: {nit_original} → {nit_corregido} '
            f'(DV pegado al final). Verificar.'
        )
    tercero['sugerencias'] = '; '.join(sugerencias_lista) if sugerencias_lista else ''

    # Reacomodar nombres si cambió el tipo de persona
    if cambio_tipo:
        if res.tipo_persona == 'juridica':
            # Mover todos los nombres a razón social
            if not tercero.get('razon_social'):
                tercero['razon_social'] = nombre_completo
            tercero['primer_apellido'] = ''
            tercero['segundo_apellido'] = ''
            tercero['primer_nombre'] = ''
            tercero['otros_nombres'] = ''
        else:
            # natural: parsear razón social en nombres/apellidos si están vacíos
            if (not tercero.get('primer_nombre') and not tercero.get('primer_apellido')
                    and tercero.get('razon_social')):
                partes = [p for p in tercero['razon_social'].split() if len(p) >= 2]
                if len(partes) >= 4:
                    tercero['primer_nombre'] = partes[0]
                    tercero['otros_nombres'] = partes[1]
                    tercero['primer_apellido'] = partes[-2]
                    tercero['segundo_apellido'] = partes[-1]
                elif len(partes) == 3:
                    tercero['primer_nombre'] = partes[0]
                    tercero['primer_apellido'] = partes[1]
                    tercero['segundo_apellido'] = partes[2]
                elif len(partes) == 2:
                    tercero['primer_nombre'] = partes[0]
                    tercero['primer_apellido'] = partes[1]
                elif len(partes) == 1:
                    tercero['primer_nombre'] = partes[0]
                tercero['razon_social'] = ''

    # Recalcular DV
    if str(tercero['nit']).isdigit():
        tercero['dv'] = calc_dv(tercero['nit'])

    return tercero


def reclasificar_lote(terceros: list[dict]) -> dict:
    """Aplica reclasificación a una lista completa, devuelve estadísticas."""
    estadisticas = {
        'total': len(terceros),
        'cambios_a_natural': 0,
        'cambios_a_juridica': 0,
        'requieren_revision': 0,
        'distribucion_final': {'natural': 0, 'juridica': 0},
    }

    for t in terceros:
        tipo_anterior = t.get('tipo_persona', 'natural')
        reclasificar_tercero(t)
        tipo_nuevo = t['tipo_persona']

        if tipo_anterior != tipo_nuevo:
            if tipo_nuevo == 'natural':
                estadisticas['cambios_a_natural'] += 1
            else:
                estadisticas['cambios_a_juridica'] += 1

        if t.get('requiere_revision'):
            estadisticas['requieren_revision'] += 1

        estadisticas['distribucion_final'][tipo_nuevo] = (
            estadisticas['distribucion_final'].get(tipo_nuevo, 0) + 1
        )

    return estadisticas


if __name__ == '__main__':
    # Tests rápidos
    casos = [
        ('71234567', 'JUAN PEREZ', 13, 'natural'),
        ('900123456', 'EMPRESA SAS', 31, 'juridica'),
        ('900123456', 'JUAN PEREZ', 31, 'juridica'),  # rango sin palabra societaria
        ('1234567890', 'ANA GARCIA', 13, 'natural'),
        ('700123456', 'JOSE LOPEZ', 31, 'natural'),  # NIT DIAN residente
        ('00228987', 'NEF DIGITAL PUBLICIDAD S.A.S.', 31, 'juridica'),  # NIT incompleto
        ('10000000000', 'CARLOS MUÑOZ', 22, 'natural'),  # NIT extranjero
        ('43108696', 'DIANA BETANCUR', 13, 'natural'),  # CC vieja
    ]
    print("\nTests de clasificación:\n")
    for nit, nombre, td_esperado, tp_esperado in casos:
        r = clasificar_nit(nit, nombre)
        ok = '✓' if (r.tipo_documento == td_esperado and r.tipo_persona == tp_esperado) else '✗'
        rev = ' (REVISAR)' if r.requiere_revision else ''
        print(f"  {ok} NIT {nit:>11} '{nombre[:30]}' → {r.tipo_documento}/{r.tipo_persona}{rev}")
        print(f"       {r.regla_aplicada}")
