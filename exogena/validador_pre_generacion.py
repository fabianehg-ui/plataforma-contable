"""
Validador y auto-enriquecedor pre-generación
=============================================

Orquesta el flujo COMPLETO antes de generar XMLs:

  1. Recibe registros listos del adaptador (output del motor + v2)
  2. Identifica qué terceros tienen campos faltantes (dirección, dpto, mun)
  3. Auto-enriquece desde cascada (caché → RUES → datos.gov.co → Empresite → Google)
  4. Para F1012 (cuentas bancarias) infiere NIT del banco desde nombre cuenta
  5. Aplica fallback de empresa informante para personas naturales sin datos
  6. Devuelve:
       - registros_actualizados (lo que sí está completo)
       - terceros_pendientes (lo que requiere input manual)

La UI usa este módulo para:
  - Antes de generar: correr `validar_y_enriquecer()` y bloquear si hay pendientes
  - Mostrar formulario "Completar datos faltantes"
  - Re-validar al guardar
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Callable
from collections import defaultdict

try:
    from .enriquecimiento.base import Enriquecedor, DatosEnriquecidos
    from .enriquecimiento.helpers_inferencia import (
        validar_tercero_completo,
        aplicar_fallback_empresa,
        auto_dividir_nombre_natural,
        corregir_tipo_documento,
        es_persona_natural,
        obtener_nit_banco,
        inferir_dpto_municipio_desde_texto,
        FORMATOS_REQUIEREN_UBICACION,
    )
except ImportError:
    try:
        from core.exogena.enriquecimiento.base import Enriquecedor, DatosEnriquecidos
        from core.exogena.enriquecimiento.helpers_inferencia import (
            validar_tercero_completo,
            aplicar_fallback_empresa,
            auto_dividir_nombre_natural,
            corregir_tipo_documento,
            es_persona_natural,
            obtener_nit_banco,
            inferir_dpto_municipio_desde_texto,
            FORMATOS_REQUIEREN_UBICACION,
        )
    except ImportError:
        from enriquecimiento.base import Enriquecedor, DatosEnriquecidos
        from enriquecimiento.helpers_inferencia import (
            validar_tercero_completo,
            aplicar_fallback_empresa,
            auto_dividir_nombre_natural,
            corregir_tipo_documento,
            es_persona_natural,
            obtener_nit_banco,
            inferir_dpto_municipio_desde_texto,
            FORMATOS_REQUIEREN_UBICACION,
        )


# ================================================================
# Estructuras de salida
# ================================================================

@dataclass
class TerceroPendiente:
    """Tercero con datos faltantes que requiere intervención manual."""
    nit: str
    formatos_afectados: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    # Datos actuales (para mostrar lo que sí tiene)
    razon_social: Optional[str] = None
    primer_nombre: Optional[str] = None
    primer_apellido: Optional[str] = None
    direccion: Optional[str] = None
    codigo_dpto: Optional[str] = None
    codigo_municipio: Optional[str] = None
    codigo_pais: Optional[str] = None
    # Para personas naturales: ¿se aplicó fallback de empresa?
    fallback_empresa_aplicado: bool = False
    # Origen de los datos (para auditoría)
    fuente_enriquecimiento: Optional[str] = None


@dataclass
class ResultadoValidacion:
    """Resultado del flujo completo de validación + enriquecimiento."""
    terceros_completos: dict[str, dict] = field(default_factory=dict)
    terceros_pendientes: dict[str, TerceroPendiente] = field(default_factory=dict)
    # Estadísticas del flujo
    total_terceros: int = 0
    enriquecidos_auto: int = 0
    enriquecidos_fallback: int = 0
    bancos_inferidos: int = 0  # F1012
    ciudades_inferidas: int = 0
    tipos_documento_corregidos: int = 0
    fuentes_usadas: dict[str, int] = field(default_factory=dict)

    @property
    def tiene_pendientes(self) -> bool:
        return len(self.terceros_pendientes) > 0

    @property
    def total_pendientes(self) -> int:
        return len(self.terceros_pendientes)


# ================================================================
# API principal
# ================================================================

def validar_y_enriquecer(
    registros_por_formato: dict,
    terceros_dict: dict[str, dict],
    info_empresa_informante: dict,
    enriquecedor: Optional[Enriquecedor] = None,
    on_progress: Optional[Callable[[str, int, int], None]] = None,
    catalogo_municipios_dane: Optional[dict] = None,
) -> ResultadoValidacion:
    """
    Valida y enriquece los terceros referenciados por los registros antes
    de generar XMLs.

    Args:
        registros_por_formato: salida del adaptador motor → v2.
            {'1001': [RegistroF1001(...), ...], ...}
        terceros_dict: maestro actual {nit: dict_tercero} desde BD.
        info_empresa_informante: datos de la empresa para fallback de naturales.
            Debe tener: direccion, codigo_dpto, codigo_municipio, codigo_pais.
        enriquecedor: cascada de enriquecedores (RUES + datos.gov.co + ...).
            Si None, NO se hace enriquecimiento externo (solo fallback + inferencia local).
        on_progress: callback opcional para reportar progreso (texto, actual, total).
        catalogo_municipios_dane: opcional, dict {nombre_municipio_normalizado: (cod_dpto, cod_mun)}
            con todos los ~1100 municipios del DANE para inferencia exhaustiva.
            Si no se pasa, se usa solo el catálogo embebido de ~50 ciudades.

    Returns:
        ResultadoValidacion con terceros_completos y terceros_pendientes.
    """
    res = ResultadoValidacion()

    # 1. Identificar qué (nit, formato) se necesita revisar
    nits_por_formato: dict[str, set] = defaultdict(set)
    for fmt, registros in registros_por_formato.items():
        for reg in registros:
            # F2276 usa nit_beneficiario en vez de tercero.nit
            nit = getattr(reg, 'nit_beneficiario', None)
            if not nit and hasattr(reg, 'tercero'):
                nit = reg.tercero.nit
            if nit:
                nits_por_formato[fmt].add(nit)

    # Conjunto plano de todos los NITs
    todos_los_nits = set()
    for nits in nits_por_formato.values():
        todos_los_nits |= nits

    res.total_terceros = len(todos_los_nits)

    if on_progress:
        on_progress("Validando terceros…", 0, res.total_terceros)

    # 2. Para cada NIT, ver qué le falta y enriquecer si aplica
    for i, nit in enumerate(sorted(todos_los_nits)):
        if on_progress and i % 10 == 0:
            on_progress(f"Procesando {nit}…", i, res.total_terceros)

        tercero_actual = dict(terceros_dict.get(nit, {'nit': nit}))

        # ¿En qué formatos aparece y en cuáles necesita ubicación obligatoria?
        formatos_que_lo_usan = [
            f for f, nits in nits_por_formato.items() if nit in nits
        ]
        formatos_con_ubicacion_req = [
            f for f in formatos_que_lo_usan if f in FORMATOS_REQUIEREN_UBICACION
        ]

        # Validar SIEMPRE la identidad (apellidos/nombres o razón social),
        # independientemente de si el formato requiere ubicación o no.
        # El primer formato sirve como referencia para los chequeos.
        formato_ref = (
            formatos_con_ubicacion_req[0] if formatos_con_ubicacion_req
            else (formatos_que_lo_usan[0] if formatos_que_lo_usan else '1001')
        )

        # CORRECCIÓN DE TIPO DE DOCUMENTO: detectar cuando un NIT en realidad
        # parece cédula (caso típico: balance con CC cargada como NIT por
        # default). Hacer esto ANTES de auto-dividir para que la auto-división
        # funcione correctamente sobre personas naturales mal tipificadas.
        tercero_actual = corregir_tipo_documento(tercero_actual)
        if tercero_actual.get('_tipo_corregido'):
            tercero_actual.pop('_tipo_corregido', None)
            res.tipos_documento_corregidos += 1

        # AUTO-DIVISIÓN: si es persona natural y su nombre está en
        # razón social, intentar dividirlo automáticamente.
        tercero_actual = auto_dividir_nombre_natural(tercero_actual)
        if tercero_actual.get('_auto_dividido'):
            tercero_actual.pop('_auto_dividido', None)

        errores_iniciales = validar_tercero_completo(tercero_actual, formato_ref)

        if not errores_iniciales:
            # Tercero completo: pasa directo
            res.terceros_completos[nit] = tercero_actual
            continue

        # 3. Intentar enriquecer desde cascada (si falta cualquier dato y tenemos enriquecedor)
        if enriquecedor and enriquecedor.disponible():
            try:
                datos = enriquecedor.enriquecer(nit)
                if datos:
                    tercero_actual = _fusionar_enriquecimiento(tercero_actual, datos)
                    # Re-aplicar auto-división si el enriquecedor llenó razon_social
                    tercero_actual = auto_dividir_nombre_natural(tercero_actual)
                    tercero_actual.pop('_auto_dividido', None)
                    res.enriquecidos_auto += 1
                    res.fuentes_usadas[datos.fuente] = \
                        res.fuentes_usadas.get(datos.fuente, 0) + 1
            except Exception:
                pass  # falla silenciosa

        # 4. Inferir dpto/mun desde texto si todavía faltan
        if (not tercero_actual.get('codigo_dpto') or
                not tercero_actual.get('codigo_municipio')):
            textos_para_inferir = [
                tercero_actual.get('direccion', ''),
                tercero_actual.get('razon_social', ''),
            ]
            inferido = inferir_dpto_municipio_desde_texto(
                *textos_para_inferir,
                catalogo_extra=catalogo_municipios_dane,
            )
            if inferido:
                if not tercero_actual.get('codigo_dpto'):
                    tercero_actual['codigo_dpto'] = inferido[0]
                if not tercero_actual.get('codigo_municipio'):
                    tercero_actual['codigo_municipio'] = inferido[1]
                res.ciudades_inferidas += 1

        # 5. Re-validar después de enriquecer
        errores_post = validar_tercero_completo(tercero_actual, formato_ref)

        if not errores_post:
            res.terceros_completos[nit] = tercero_actual
            continue

        # 6. Fallback: si es persona natural y le falta ubicación, usar datos
        # de empresa informante. Esto se aplica SOLO para llenar la ubicación
        # (dirección/dpto/municipio); si también le faltan apellidos/nombres,
        # la persona queda pendiente para input manual.
        if es_persona_natural(tercero_actual):
            # Verificar qué le falta de ubicación
            falta_ubicacion = (
                not (tercero_actual.get('direccion') or '').strip() or
                not (tercero_actual.get('codigo_dpto') or '').strip() or
                not (tercero_actual.get('codigo_municipio') or '').strip()
            )
            if falta_ubicacion:
                tercero_actual = aplicar_fallback_empresa(
                    tercero_actual, info_empresa_informante
                )
                res.enriquecidos_fallback += 1

                # Re-validar (puede que TODAVÍA falten apellidos/nombres)
                errores_post = validar_tercero_completo(tercero_actual, formato_ref)
                if not errores_post:
                    res.terceros_completos[nit] = tercero_actual
                    continue

        # 7. Si llegamos acá, está pendiente: dejar para input manual
        res.terceros_pendientes[nit] = TerceroPendiente(
            nit=nit,
            formatos_afectados=formatos_que_lo_usan,
            errores=errores_post,
            razon_social=tercero_actual.get('razon_social'),
            primer_nombre=tercero_actual.get('primer_nombre'),
            primer_apellido=tercero_actual.get('primer_apellido'),
            direccion=tercero_actual.get('direccion'),
            codigo_dpto=tercero_actual.get('codigo_dpto'),
            codigo_municipio=tercero_actual.get('codigo_municipio'),
            codigo_pais=tercero_actual.get('codigo_pais'),
        )

    # 8. Inferir NITs de bancos en F1012 (cuentas 1110-1120)
    if '1012' in registros_por_formato:
        res.bancos_inferidos = _inferir_bancos_f1012(
            registros_por_formato['1012'],
            res.terceros_completos,
        )

    if on_progress:
        on_progress("Listo", res.total_terceros, res.total_terceros)

    return res


# ================================================================
# Helpers internos
# ================================================================

def _fusionar_enriquecimiento(tercero: dict, datos: DatosEnriquecidos) -> dict:
    """Fusiona datos enriquecidos al dict del tercero, sin sobreescribir lo que ya tiene."""
    out = dict(tercero)
    campos = [
        ('razon_social', datos.razon_social),
        ('primer_nombre', datos.primer_nombre),
        ('primer_apellido', datos.primer_apellido),
        ('segundo_apellido', datos.segundo_apellido),
        ('direccion', datos.direccion),
        ('codigo_dpto', datos.codigo_dpto),
        ('codigo_municipio', datos.codigo_municipio),
        ('codigo_pais', datos.codigo_pais if hasattr(datos, 'codigo_pais') else None),
        ('actividad_ciiu', datos.actividad_ciiu),
    ]
    for campo, valor in campos:
        if valor and not (out.get(campo) or '').strip():
            out[campo] = valor

    out['enriquecido_desde'] = datos.fuente
    return out


def _inferir_bancos_f1012(registros_f1012, terceros_completos: dict) -> int:
    """
    Para registros F1012 conceptos bancarios (1110-1120), siempre intenta
    inferir el NIT del banco desde 'nota' o 'razon_social' de la cuenta.

    El motivo: el NIT que viene del balance contable suele ser un código
    interno (ej. 860001234 inventado) o el NIT propio de la empresa, no
    el NIT real del banco. La DIAN exige que sea el NIT real de Bancolombia,
    Davivienda, etc.

    Modifica el registro IN-PLACE.
    """
    try:
        from .generador_xml_v2 import Tercero, TIPO_DOC_NIT, PAIS_COLOMBIA
    except ImportError:
        try:
            from core.exogena.generador_xml_v2 import Tercero, TIPO_DOC_NIT, PAIS_COLOMBIA
        except ImportError:
            from generador_xml_v2 import Tercero, TIPO_DOC_NIT, PAIS_COLOMBIA

    # NITs reales de bancos colombianos (extracto de BANCOS_NITS).
    # Si el NIT actual del registro YA es un banco real, no sobreescribir.
    try:
        from .enriquecimiento.helpers_inferencia import BANCOS_NITS
    except ImportError:
        try:
            from core.exogena.enriquecimiento.helpers_inferencia import BANCOS_NITS
        except ImportError:
            from enriquecimiento.helpers_inferencia import BANCOS_NITS
    nits_bancos_reales = {
        b['nit'] for b in BANCOS_NITS.values() if b is not None
    }

    contador = 0
    for reg in registros_f1012:
        # Solo aplica a conceptos bancarios (1110, 1115, 1120)
        if reg.concepto not in (1110, 1115, 1120):
            continue

        # Si el NIT actual YA es un banco real conocido, respetarlo
        nit_actual = (reg.tercero.nit or '').strip()
        if nit_actual in nits_bancos_reales:
            continue

        # Buscar el banco en la nota o en la razón social
        nombre_pista = (
            getattr(reg, 'nota', '') or
            reg.tercero.razon_social or ''
        )
        banco = obtener_nit_banco(nombre_pista)
        if banco:
            reg.tercero = Tercero(
                nit=banco['nit'],
                tipo_documento=TIPO_DOC_NIT,
                razon_social=banco['razon_social'],
                codigo_pais=PAIS_COLOMBIA,
                digito_verificacion=banco['dv'],
            )
            contador += 1

    return contador


# ================================================================
# Aplicar terceros actualizados a los registros
# ================================================================

def aplicar_terceros_a_registros(
    registros_por_formato: dict,
    terceros_completos: dict[str, dict],
) -> dict:
    """
    Toma los registros generados por el adaptador y les inyecta los terceros
    actualizados (después de validar y enriquecer).

    Modifica los registros IN-PLACE actualizando reg.tercero con los datos
    completos del dict.

    Returns:
        El mismo `registros_por_formato` (mutado) para encadenar.
    """
    try:
        from .generador_xml_v2 import Tercero, PAIS_COLOMBIA
    except ImportError:
        try:
            from core.exogena.generador_xml_v2 import Tercero, PAIS_COLOMBIA
        except ImportError:
            from generador_xml_v2 import Tercero, PAIS_COLOMBIA

    for fmt, registros in registros_por_formato.items():
        for reg in registros:
            # Determinar el NIT del registro
            nit = None
            if hasattr(reg, 'tercero'):
                nit = reg.tercero.nit
            elif hasattr(reg, 'nit_beneficiario'):
                nit = reg.nit_beneficiario

            if not nit:
                continue

            datos_actualizados = terceros_completos.get(nit)
            if not datos_actualizados:
                continue

            # Para F2276, los datos van directamente en los campos del registro
            if fmt == '2276':
                if datos_actualizados.get('primer_apellido'):
                    reg.primer_apellido = datos_actualizados['primer_apellido']
                if datos_actualizados.get('segundo_apellido'):
                    reg.segundo_apellido = datos_actualizados['segundo_apellido']
                if datos_actualizados.get('primer_nombre'):
                    reg.primer_nombre = datos_actualizados['primer_nombre']
                if datos_actualizados.get('otros_nombres'):
                    reg.otros_nombres = datos_actualizados['otros_nombres']
                if datos_actualizados.get('direccion'):
                    reg.direccion = datos_actualizados['direccion']
                if datos_actualizados.get('codigo_dpto'):
                    reg.codigo_departamento = datos_actualizados['codigo_dpto']
                if datos_actualizados.get('codigo_municipio'):
                    reg.codigo_municipio = datos_actualizados['codigo_municipio']
                if datos_actualizados.get('codigo_pais'):
                    reg.codigo_pais = datos_actualizados['codigo_pais']
                continue

            # Para el resto: reemplazar el Tercero
            if hasattr(reg, 'tercero'):
                tipo_doc = datos_actualizados.get('tipo_documento') or reg.tercero.tipo_documento
                if isinstance(tipo_doc, int):
                    tipo_doc = str(tipo_doc).zfill(2)

                # Helper: usa el valor del dict si la CLAVE existe (incluso si es None).
                # Esto es crítico cuando auto_dividir_nombre_natural pone razon_social=None
                # explícitamente — queremos que se borre, no que se preserve el viejo.
                def _toma(campo: str, fallback):
                    if campo in datos_actualizados:
                        return datos_actualizados[campo]
                    return fallback

                reg.tercero = Tercero(
                    nit=nit,
                    tipo_documento=tipo_doc,
                    razon_social=_toma('razon_social', reg.tercero.razon_social),
                    primer_apellido=_toma('primer_apellido', reg.tercero.primer_apellido),
                    segundo_apellido=_toma('segundo_apellido', reg.tercero.segundo_apellido),
                    primer_nombre=_toma('primer_nombre', reg.tercero.primer_nombre),
                    otros_nombres=_toma('otros_nombres', reg.tercero.otros_nombres),
                    direccion=_toma('direccion', reg.tercero.direccion),
                    codigo_departamento=(
                        datos_actualizados.get('codigo_dpto')
                        or reg.tercero.codigo_departamento
                    ),
                    codigo_municipio=(
                        datos_actualizados.get('codigo_municipio')
                        or reg.tercero.codigo_municipio
                    ),
                    codigo_pais=(
                        datos_actualizados.get('codigo_pais')
                        or reg.tercero.codigo_pais
                        or PAIS_COLOMBIA
                    ),
                    digito_verificacion=(
                        str(datos_actualizados.get('dv')) if datos_actualizados.get('dv') is not None
                        else reg.tercero.digito_verificacion
                    ),
                )

    return registros_por_formato
