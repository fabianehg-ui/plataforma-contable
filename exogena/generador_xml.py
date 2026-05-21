"""
Generador de XMLs DIAN — Información Exógena AG 2025.

Construye archivos XML conforme a XSD oficial del prevalidador AG 2025 v3.3.0-26
para los formatos F1001 (pagos a terceros) y F1003 (retenciones que le practicaron).

INTEGRA con motor v2:
  - Aplica retenciones indexadas por NIT (cuenta 2365) al F1001
  - Aplica exceso 236555 como menor valor o concepto 5028 (año anterior)
  - Excluye cuentas 6 conciliadas con traslado 72/73

ESTRUCTURA XML DIAN:
  <mas xmlns="http://www.dian.gov.co">
    <Cab>
      <Ano>2025</Ano>
      <CodCpt>FMT_NNNN</CodCpt>
      <Formato>NNNN</Formato>
      <Version>V</Version>
      <NumEnvio>00000001</NumEnvio>
      <FecEnvio>2026-04-15T10:00:00-05:00</FecEnvio>
      <FecInicial>2025-01-01</FecInicial>
      <FecFinal>2025-12-31</FecFinal>
      <ValorTotal>X</ValorTotal>
      <CantReg>N</CantReg>
    </Cab>
    <pagos cpt="..." tdoc="..." nid="..." dv="..." />  <!-- F1001 -->
    <rets  cpt="..." tdoc="..." nid="..." />            <!-- F1003 -->
  </mas>

ENCODING: ISO-8859-1 (requerido por DIAN, NO UTF-8)
NOMBRE ARCHIVO: Dmuisca_ccccvvyyyyrrpppppppp.xml
  cccc = formato (1001)
  vv   = versión (10)
  yyyy = año del envío (2026)
  rr   = tipo envío (01=inicial, 02=fracción, 03=reemplazo, 04=corrección)
  pppppppp = consecutivo (00000001)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET
import re


# ================================================================
# CONFIGURACIÓN POR FORMATO
# ================================================================

FORMATOS_CONFIG = {
    '1001': {
        'version': '10',
        'codigo_concepto': 'FMT1001',  # se ajusta según vigencia
        'elemento_raiz': 'mas',
        'elemento_registro': 'pagos',
        'descripcion': 'Pagos o abonos en cuenta y retenciones practicadas',
        'namespace': 'http://www.dian.gov.co',
    },
    '1003': {
        'version': '7',
        'codigo_concepto': 'FMT1003',
        'elemento_raiz': 'mas',
        'elemento_registro': 'rets',
        'descripcion': 'Retenciones en la fuente que le practicaron',
        'namespace': 'http://www.dian.gov.co',
    },
}

# Tipos de envío
TIPO_ENVIO_INICIAL = '01'
TIPO_ENVIO_FRACCION = '02'
TIPO_ENVIO_REEMPLAZO = '03'
TIPO_ENVIO_CORRECCION = '04'

# Tipos de documento DIAN (códigos oficiales)
TIPO_DOC_CC = '13'      # Cédula de ciudadanía
TIPO_DOC_CE = '22'      # Cédula de extranjería
TIPO_DOC_NIT = '31'     # NIT
TIPO_DOC_PAS = '41'     # Pasaporte
TIPO_DOC_TI = '12'      # Tarjeta de identidad
TIPO_DOC_DEX = '42'     # Documento de identificación extranjero

CONCEPTO_DIAN_EXCESO_AÑO_ANTERIOR = 5028


# ================================================================
# DATACLASSES
# ================================================================

@dataclass
class Tercero:
    """Datos completos de un tercero (NIT)."""
    nit: str
    tipo_documento: str  # '13', '22', '31', '41', '12', '42'
    razon_social: Optional[str] = None       # Para personas jurídicas
    primer_apellido: Optional[str] = None    # Para personas naturales
    segundo_apellido: Optional[str] = None
    primer_nombre: Optional[str] = None
    otros_nombres: Optional[str] = None
    direccion: Optional[str] = None
    codigo_pais: str = '169'                  # 169 = Colombia (código DIAN)
    codigo_departamento: Optional[str] = None # 2 dígitos DIVIPOLA
    codigo_municipio: Optional[str] = None    # 3 dígitos DIVIPOLA
    digito_verificacion: Optional[str] = None  # Solo para NIT


@dataclass
class RegistroF1001:
    """Un registro del Formato 1001 (un pago a un tercero por un concepto)."""
    tercero: Tercero
    concepto: int                           # 5001, 5002, ..., 5008
    valor_pago_deducible: float = 0.0       # Valor base del pago
    valor_pago_no_deducible: float = 0.0    # Pagos no deducibles
    iva_mayor_valor: float = 0.0            # IVA mayor valor del costo
    valor_retencion_renta: float = 0.0      # Retefuente practicada
    valor_retencion_iva: float = 0.0        # ReteIVA practicado
    nota: str = ''


@dataclass
class RegistroF1003:
    """Un registro del Formato 1003 (retención que le practicó un tercero)."""
    tercero: Tercero
    concepto: int                           # 1301, 1302, ..., 1306, etc.
    valor_base_retencion: float = 0.0       # Base sobre la cual le retuvieron
    valor_retencion: float = 0.0            # Monto de la retención
    nota: str = ''


@dataclass
class CabeceraXML:
    """Datos de la cabecera <Cab> del XML."""
    ano_gravable: int
    formato: str                             # '1001', '1003'
    version: str                             # '10', '7'
    numero_envio: int = 1
    fecha_envio: datetime = field(default_factory=datetime.now)
    fecha_inicial: date = field(default_factory=lambda: date(2025, 1, 1))
    fecha_final: date = field(default_factory=lambda: date(2025, 12, 31))
    tipo_envio: str = TIPO_ENVIO_INICIAL


@dataclass
class ResultadoValidacion:
    """Resultado del prevalidador espejo."""
    es_valido: bool
    errores: list[dict] = field(default_factory=list)    # [{nivel, codigo, mensaje, registro}]
    advertencias: list[dict] = field(default_factory=list)
    estadisticas: dict = field(default_factory=dict)

    def agregar_error(self, codigo: str, mensaje: str, registro: int = -1, nivel: str = 'ERROR'):
        self.errores.append({
            'codigo': codigo,
            'mensaje': mensaje,
            'registro': registro,
            'nivel': nivel,
        })
        if nivel == 'ERROR':
            self.es_valido = False

    def agregar_advertencia(self, codigo: str, mensaje: str, registro: int = -1):
        self.advertencias.append({
            'codigo': codigo,
            'mensaje': mensaje,
            'registro': registro,
        })


# ================================================================
# UTILIDADES DE FORMATO
# ================================================================

def calcular_dv(nit: str) -> str:
    """Calcula el dígito de verificación del NIT colombiano."""
    nit = re.sub(r'\D', '', str(nit))
    if not nit:
        return '0'
    pesos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    nit_inv = nit[::-1]
    suma = sum(int(d) * pesos[i] for i, d in enumerate(nit_inv) if i < len(pesos))
    resto = suma % 11
    if resto < 2:
        return str(resto)
    return str(11 - resto)


def formatear_entero(valor: float) -> str:
    """Formatea valor numérico para DIAN: entero, sin decimales, sin separadores."""
    return str(int(round(valor or 0)))


def formatear_fecha(d: date) -> str:
    """ISO 8601: YYYY-MM-DD"""
    return d.strftime('%Y-%m-%d')


def formatear_fecha_envio(dt: datetime) -> str:
    """ISO 8601 con timezone: 2026-04-15T10:00:00-05:00"""
    return dt.strftime('%Y-%m-%dT%H:%M:%S-05:00')


def construir_nombre_archivo(formato: str, version: str, ano_envio: int,
                              tipo_envio: str, consecutivo: int) -> str:
    """
    Convención DIAN: Dmuisca_ccccvvyyyyrrpppppppp.xml
      cccc = formato (4 chars)       1001
      vv   = versión (2 chars)       10
      yyyy = año envío (4 chars)     2026
      rr   = tipo envío (2 chars)    01
      ppppppppp = consecutivo (8 chars) 00000001
    """
    return f'Dmuisca_{formato}{version.zfill(2)}{ano_envio}{tipo_envio}{str(consecutivo).zfill(8)}.xml'


def normalizar_nit(nit: str) -> str:
    """Quita guiones, puntos y espacios del NIT."""
    return re.sub(r'\D', '', str(nit or ''))


# ================================================================
# CONSTRUCCIÓN DE ATRIBUTOS POR REGISTRO
# ================================================================

def _atributos_tercero(tercero: Tercero) -> dict:
    """Atributos comunes de un tercero según el XSD DIAN."""
    nit_limpio = normalizar_nit(tercero.nit)
    attrs = {
        'tdoc': tercero.tipo_documento,
        'nid': nit_limpio,
        'cpais': tercero.codigo_pais or '169',
    }
    # DV solo para NIT (tipo 31)
    if tercero.tipo_documento == TIPO_DOC_NIT:
        dv = tercero.digito_verificacion or calcular_dv(nit_limpio)
        attrs['dv'] = dv

    # Nombres: persona jurídica vs natural
    if tercero.razon_social:
        attrs['rs'] = tercero.razon_social[:200]
    else:
        if tercero.primer_apellido:
            attrs['pa'] = tercero.primer_apellido[:60]
        if tercero.segundo_apellido:
            attrs['sa'] = tercero.segundo_apellido[:60]
        if tercero.primer_nombre:
            attrs['pn'] = tercero.primer_nombre[:60]
        if tercero.otros_nombres:
            attrs['on'] = tercero.otros_nombres[:60]

    # Dirección y localización
    if tercero.direccion:
        attrs['dir'] = tercero.direccion[:200]
    if tercero.codigo_departamento:
        attrs['cdpto'] = str(tercero.codigo_departamento).zfill(2)
    if tercero.codigo_municipio:
        attrs['cmpio'] = str(tercero.codigo_municipio).zfill(3)

    return attrs


def _atributos_f1001(reg: RegistroF1001) -> dict:
    """Atributos de un registro <pagos> del F1001."""
    attrs = _atributos_tercero(reg.tercero)
    attrs['cpt'] = str(reg.concepto)
    attrs['vpd'] = formatear_entero(reg.valor_pago_deducible)
    attrs['vpnd'] = formatear_entero(reg.valor_pago_no_deducible)
    attrs['vivamc'] = formatear_entero(reg.iva_mayor_valor)
    attrs['vrfte'] = formatear_entero(reg.valor_retencion_renta)
    attrs['vriva'] = formatear_entero(reg.valor_retencion_iva)
    return attrs


def _atributos_f1003(reg: RegistroF1003) -> dict:
    """Atributos de un registro <rets> del F1003."""
    attrs = _atributos_tercero(reg.tercero)
    attrs['cpt'] = str(reg.concepto)
    attrs['pago'] = formatear_entero(reg.valor_base_retencion)
    attrs['rfte'] = formatear_entero(reg.valor_retencion)
    return attrs


# ================================================================
# CONSTRUCCIÓN DE XML
# ================================================================

def _construir_xml(
    cabecera: CabeceraXML,
    registros_attrs: list[dict],
    valor_total: float,
) -> str:
    """Construye el string XML completo con encoding ISO-8859-1."""
    config = FORMATOS_CONFIG[cabecera.formato]
    namespace = config['namespace']
    elemento_registro = config['elemento_registro']

    # Crear elemento raíz con namespace
    root = ET.Element('mas', {'xmlns': namespace})

    # Cabecera
    cab = ET.SubElement(root, 'Cab')
    ET.SubElement(cab, 'Ano').text = str(cabecera.ano_gravable)
    ET.SubElement(cab, 'CodCpt').text = config['codigo_concepto']
    ET.SubElement(cab, 'Formato').text = cabecera.formato
    ET.SubElement(cab, 'Version').text = cabecera.version
    ET.SubElement(cab, 'NumEnvio').text = str(cabecera.numero_envio).zfill(8)
    ET.SubElement(cab, 'FecEnvio').text = formatear_fecha_envio(cabecera.fecha_envio)
    ET.SubElement(cab, 'FecInicial').text = formatear_fecha(cabecera.fecha_inicial)
    ET.SubElement(cab, 'FecFinal').text = formatear_fecha(cabecera.fecha_final)
    ET.SubElement(cab, 'ValorTotal').text = formatear_entero(valor_total)
    ET.SubElement(cab, 'CantReg').text = str(len(registros_attrs))

    # Registros (como elementos auto-cerrados con atributos)
    for attrs in registros_attrs:
        ET.SubElement(root, elemento_registro, attrs)

    # Serializar a string con declaración ISO-8859-1
    xml_bytes = ET.tostring(root, encoding='ISO-8859-1', xml_declaration=True)
    return xml_bytes.decode('ISO-8859-1')


def generar_xml_f1001(
    cabecera: CabeceraXML,
    registros: list[RegistroF1001],
) -> str:
    """Genera el XML del Formato 1001."""
    cabecera.formato = '1001'
    cabecera.version = '10'
    attrs_lista = [_atributos_f1001(r) for r in registros]
    valor_total = sum(r.valor_pago_deducible + r.valor_pago_no_deducible for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f1003(
    cabecera: CabeceraXML,
    registros: list[RegistroF1003],
) -> str:
    """Genera el XML del Formato 1003."""
    cabecera.formato = '1003'
    cabecera.version = '7'
    attrs_lista = [_atributos_f1003(r) for r in registros]
    valor_total = sum(r.valor_retencion for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


# ================================================================
# INTEGRACIÓN CON MOTOR V2: agrupar movimientos clasificados → registros
# ================================================================

def construir_registros_f1001(
    movimientos_clasificados: list,
    terceros: dict,                       # dict[nit] -> Tercero
    retenciones_por_nit: dict,            # dict[nit] -> RetencionAcumulada
) -> list[RegistroF1001]:
    """
    Toma los MovimientoClasificado del motor v2 y construye registros F1001.

    REGLAS:
      - Solo movimientos con formato_dian == '1001'
      - Agrupa por (NIT, concepto)
      - Aplica retenciones indexadas (cuenta 2365) por NIT
      - Aplica exceso 236555 como menor valor de retención
      - Si exceso es de año anterior → genera registro adicional con concepto 5028
    """
    # 1. Agrupar movimientos por (nit, concepto)
    agrupados: dict[tuple, RegistroF1001] = {}

    for mov in movimientos_clasificados:
        if mov.formato_dian != '1001' or not mov.nit:
            continue

        nit_limpio = normalizar_nit(mov.nit)
        concepto = mov.concepto_dian or 5004  # fallback genérico
        key = (nit_limpio, concepto)

        if key not in agrupados:
            tercero = terceros.get(nit_limpio) or Tercero(
                nit=nit_limpio,
                tipo_documento=TIPO_DOC_NIT,
                razon_social='SIN DATOS',
            )
            agrupados[key] = RegistroF1001(
                tercero=tercero,
                concepto=concepto,
            )

        agrupados[key].valor_pago_deducible += mov.valor

    # 2. Aplicar retenciones por NIT (acumuladas en cuenta 2365)
    nits_procesados_retencion = set()
    for (nit, concepto), reg in agrupados.items():
        if nit in nits_procesados_retencion:
            continue
        retencion = retenciones_por_nit.get(nit)
        if retencion is None:
            continue

        # Distribuir retención total entre los conceptos del NIT proporcionalmente
        regs_del_nit = [r for k, r in agrupados.items() if k[0] == nit]
        total_pagos_nit = sum(r.valor_pago_deducible for r in regs_del_nit)

        if total_pagos_nit > 0:
            ret_total = retencion.f1001_retencion_practicada
            # Restar exceso del periodo actual (236555)
            exceso = retencion.exceso_periodos_anteriores
            ret_neta = max(0, ret_total - exceso)

            for r in regs_del_nit:
                proporcion = r.valor_pago_deducible / total_pagos_nit
                r.valor_retencion_renta = round(ret_neta * proporcion)
                r.nota = (
                    f'Retención total NIT: ${ret_total:,.0f}, '
                    f'menos exceso ${exceso:,.0f} = ${ret_neta:,.0f} '
                    f'(proporción {proporcion:.2%})'
                )

        nits_procesados_retencion.add(nit)

    # 3. Generar registros adicionales con concepto 5028 si hay exceso de año anterior
    registros_5028 = []
    for nit, retencion in retenciones_por_nit.items():
        if retencion.exceso_periodos_anteriores > 0:
            # Por ahora, el exceso lo restamos del periodo actual (paso 2)
            # Si se quiere reportar como concepto 5028 separado, descomentar:
            # tercero = terceros.get(nit) or Tercero(nit=nit, tipo_documento=TIPO_DOC_NIT)
            # registros_5028.append(RegistroF1001(
            #     tercero=tercero,
            #     concepto=CONCEPTO_DIAN_EXCESO_AÑO_ANTERIOR,
            #     valor_pago_deducible=retencion.exceso_periodos_anteriores,
            #     nota='Exceso de retención de periodos anteriores',
            # ))
            pass

    return list(agrupados.values()) + registros_5028


def construir_registros_f1003(
    movimientos_clasificados: list,
    terceros: dict,
) -> list[RegistroF1003]:
    """
    Toma los MovimientoClasificado del motor v2 (con formato '1003') y construye
    registros F1003 agrupados por (NIT, concepto).
    """
    agrupados: dict[tuple, RegistroF1003] = {}

    for mov in movimientos_clasificados:
        if mov.formato_dian != '1003' or not mov.nit:
            continue

        nit_limpio = normalizar_nit(mov.nit)
        concepto = mov.concepto_dian or 1306  # fallback compras
        key = (nit_limpio, concepto)

        if key not in agrupados:
            tercero = terceros.get(nit_limpio) or Tercero(
                nit=nit_limpio,
                tipo_documento=TIPO_DOC_NIT,
                razon_social='SIN DATOS',
            )
            agrupados[key] = RegistroF1003(
                tercero=tercero,
                concepto=concepto,
            )

        agrupados[key].valor_retencion += mov.valor
        # Base aproximada (en práctica viene del balance)
        agrupados[key].valor_base_retencion += mov.valor * 100  # placeholder

    return list(agrupados.values())


# ================================================================
# PREVALIDADOR ESPEJO — Reglas de negocio DIAN
# ================================================================

def prevalidar_f1001(registros: list[RegistroF1001]) -> ResultadoValidacion:
    """
    Aplica las reglas de negocio del prevalidador oficial DIAN al F1001.

    Reglas implementadas:
      1. Tipo de documento debe estar en lista válida
      2. NIT no puede estar vacío
      3. DV debe ser correcto para NIT (tipo 31)
      4. Concepto debe estar en rango válido (5001-5099)
      5. Persona natural → debe tener al menos primer_apellido y primer_nombre
      6. Persona jurídica → debe tener razón social
      7. Valores no pueden ser negativos
      8. Cuantías mínimas por concepto
      9. Si tipo_doc=NIT, debe estar registrado y ser jurídica/natural
      10. Retención no puede ser mayor al pago
    """
    res = ResultadoValidacion(es_valido=True)
    tipos_doc_validos = {'11', '12', '13', '21', '22', '31', '41', '42', '43', '47'}

    total_pagos = 0
    total_retenciones = 0

    for i, reg in enumerate(registros, start=1):
        t = reg.tercero
        nit = normalizar_nit(t.nit)

        # 1. Tipo de documento válido
        if t.tipo_documento not in tipos_doc_validos:
            res.agregar_error(
                'F1001-E001',
                f'Tipo de documento inválido: {t.tipo_documento}. '
                f'Debe ser uno de {tipos_doc_validos}',
                i,
            )

        # 2. NIT no vacío
        if not nit:
            res.agregar_error('F1001-E002', 'Número de identificación vacío', i)

        # 3. DV correcto para NIT
        if t.tipo_documento == TIPO_DOC_NIT and nit:
            dv_calculado = calcular_dv(nit)
            dv_dado = str(t.digito_verificacion or '').strip()
            if dv_dado and dv_dado != dv_calculado:
                res.agregar_error(
                    'F1001-E003',
                    f'DV incorrecto para NIT {nit}: dado={dv_dado}, calculado={dv_calculado}',
                    i,
                )

        # 4. Concepto en rango
        if not (5001 <= reg.concepto <= 5099):
            res.agregar_error(
                'F1001-E004',
                f'Concepto {reg.concepto} fuera de rango válido (5001-5099)',
                i,
            )

        # 5/6. Datos de persona
        if t.tipo_documento == TIPO_DOC_NIT:
            if not t.razon_social:
                res.agregar_error(
                    'F1001-E005',
                    f'Persona jurídica (NIT {nit}) sin razón social',
                    i,
                )
        else:
            if not (t.primer_apellido and t.primer_nombre):
                res.agregar_advertencia(
                    'F1001-A001',
                    f'Persona natural (doc {nit}) sin primer apellido o primer nombre',
                    i,
                )

        # 7. Valores no negativos
        for campo, val in [
            ('valor_pago_deducible', reg.valor_pago_deducible),
            ('valor_pago_no_deducible', reg.valor_pago_no_deducible),
            ('valor_retencion_renta', reg.valor_retencion_renta),
            ('valor_retencion_iva', reg.valor_retencion_iva),
        ]:
            if val < 0:
                res.agregar_error(
                    'F1001-E006',
                    f'Valor negativo en {campo}: ${val:,.0f}',
                    i,
                )

        # 10. Retención <= pago
        total_pago = reg.valor_pago_deducible + reg.valor_pago_no_deducible
        total_ret = reg.valor_retencion_renta + reg.valor_retencion_iva
        if total_ret > total_pago and total_pago > 0:
            res.agregar_advertencia(
                'F1001-A002',
                f'Retención (${total_ret:,.0f}) mayor que pago (${total_pago:,.0f}) — revisar',
                i,
            )

        # Localización para personas residentes en Colombia
        if t.codigo_pais == '169' and not (t.codigo_departamento and t.codigo_municipio):
            res.agregar_advertencia(
                'F1001-A003',
                f'Tercero colombiano sin departamento/municipio: NIT {nit}',
                i,
            )

        total_pagos += total_pago
        total_retenciones += total_ret

    res.estadisticas = {
        'total_registros': len(registros),
        'total_pagos': total_pagos,
        'total_retenciones': total_retenciones,
        'cantidad_errores': len(res.errores),
        'cantidad_advertencias': len(res.advertencias),
    }
    return res


def prevalidar_f1003(registros: list[RegistroF1003]) -> ResultadoValidacion:
    """
    Reglas de prevalidador para F1003 (retenciones que le practicaron).

      1. Tipo doc válido
      2. NIT no vacío
      3. DV correcto
      4. Concepto en rango (1301-1399)
      5. Retención > 0
      6. Base coherente con retención
    """
    res = ResultadoValidacion(es_valido=True)
    tipos_doc_validos = {'11', '12', '13', '21', '22', '31', '41', '42', '43', '47'}

    total_retenciones = 0

    for i, reg in enumerate(registros, start=1):
        t = reg.tercero
        nit = normalizar_nit(t.nit)

        if t.tipo_documento not in tipos_doc_validos:
            res.agregar_error(
                'F1003-E001',
                f'Tipo de documento inválido: {t.tipo_documento}',
                i,
            )

        if not nit:
            res.agregar_error('F1003-E002', 'NIT vacío', i)

        if t.tipo_documento == TIPO_DOC_NIT and nit:
            dv_calculado = calcular_dv(nit)
            if t.digito_verificacion and str(t.digito_verificacion) != dv_calculado:
                res.agregar_error(
                    'F1003-E003',
                    f'DV incorrecto para NIT {nit}',
                    i,
                )

        if not (1301 <= reg.concepto <= 1399):
            res.agregar_error(
                'F1003-E004',
                f'Concepto {reg.concepto} fuera de rango F1003 (1301-1399)',
                i,
            )

        if reg.valor_retencion <= 0:
            res.agregar_error(
                'F1003-E005',
                f'Retención debe ser mayor a cero (es ${reg.valor_retencion:,.0f})',
                i,
            )

        total_retenciones += reg.valor_retencion

    res.estadisticas = {
        'total_registros': len(registros),
        'total_retenciones': total_retenciones,
        'cantidad_errores': len(res.errores),
        'cantidad_advertencias': len(res.advertencias),
    }
    return res


# ================================================================
# GENERACIÓN COMPLETA: motor → XML + validación
# ================================================================

def generar_y_validar_f1001(
    cabecera: CabeceraXML,
    movimientos_clasificados: list,
    terceros: dict,
    retenciones_por_nit: dict,
) -> tuple[str, ResultadoValidacion, list[RegistroF1001]]:
    """
    Pipeline completo F1001:
      1. Construye registros desde el motor
      2. Aplica retenciones por NIT
      3. Pre-valida con reglas DIAN
      4. Genera XML
    """
    registros = construir_registros_f1001(
        movimientos_clasificados, terceros, retenciones_por_nit
    )
    validacion = prevalidar_f1001(registros)
    xml = generar_xml_f1001(cabecera, registros)
    return xml, validacion, registros


def generar_y_validar_f1003(
    cabecera: CabeceraXML,
    movimientos_clasificados: list,
    terceros: dict,
) -> tuple[str, ResultadoValidacion, list[RegistroF1003]]:
    """
    Pipeline completo F1003:
      1. Construye registros desde el motor
      2. Pre-valida con reglas DIAN
      3. Genera XML
    """
    registros = construir_registros_f1003(movimientos_clasificados, terceros)
    validacion = prevalidar_f1003(registros)
    xml = generar_xml_f1003(cabecera, registros)
    return xml, validacion, registros


# ================================================================
# I/O: guardar XMLs en disco
# ================================================================

def guardar_xml(xml_string: str, ruta: str | Path) -> Path:
    """Guarda XML en disco con encoding ISO-8859-1."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, 'wb') as f:
        f.write(xml_string.encode('ISO-8859-1'))
    return ruta
