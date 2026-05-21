"""
Generador XML v2 — Información Exógena DIAN AG 2025
====================================================

Reemplazo correcto del `generador_xml.py` antiguo. Las diferencias críticas:

1. ATRIBUTOS XSD OFICIALES — usa los nombres EXACTOS del XSD oficial DIAN
   (verificados contra el prevalidador AG2025 v3.3.0-26):
   
   F1001:  cpt, tdoc, nid, apl1/apl2/nom1/nom2/raz, dir, dpto, mun, pais,
           pago, pnded, ided, inded, retp, reta, comun, ndom
   F1003:  cpt, tdoc, nid, dv, apl1/apl2/nom1/nom2/raz, dir, dpto, mcpo,
           valor, ret
   F1005:  tdoc, nid, dv, apl1/apl2/nom1/nom2/raz, vimp, ivade, ivavcg
   F1006:  tdoc, nid, dv, apl1/apl2/nom1/nom2/raz, imp, iva, icon
   F1008:  cpt, tdoc, nid, dv, apl1/apl2/nom1/nom2/raz, dir, dpto, mun,
           pais, sal
   F1011:  cpt, sal
   F1012:  cpt, tdoc, nid, dv, apl1/apl2/nom1/nom2/raz, pais, val

2. SIN NAMESPACE — los XSDs DIAN no declaran targetNamespace, así que
   el elemento raíz <mas> va sin namespace para validar estricto con lxml.

3. ENCODING ISO-8859-1 — requerido por DIAN.

4. CONVENCIÓN DE ARCHIVO — Dmuisca_ccccvvyyyyrrpppppppp.xml

VERIFICADO: los 7 formatos pasan validación XSD oficial estricta.
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
        'codigo_concepto': '1',
        'elemento_registro': 'pagos',
        'descripcion': 'Pagos o abonos en cuenta y retenciones practicadas',
    },
    '1003': {
        'version': '7',
        'codigo_concepto': '1',
        'elemento_registro': 'rets',
        'descripcion': 'Retenciones en la fuente que le practicaron',
    },
    '1005': {
        'version': '8',
        'codigo_concepto': '1',
        'elemento_registro': 'impventas',
        'descripcion': 'Impuestos a las ventas por pagar (Descontable)',
    },
    '1006': {
        'version': '8',
        'codigo_concepto': '1',
        'elemento_registro': 'impoventas',
        'descripcion': 'Impuestos a las ventas por pagar (Generado)',
    },
    '1007': {
        'version': '9',
        'codigo_concepto': '1',
        'elemento_registro': 'ingresos',
        'descripcion': 'Ingresos recibidos',
    },
    '1008': {
        'version': '7',
        'codigo_concepto': '1',
        'elemento_registro': 'saldoscc',
        'descripcion': 'Saldos de cuentas por cobrar al 31 de diciembre',
    },
    '1009': {
        'version': '7',
        'codigo_concepto': '1',
        'elemento_registro': 'saldoscp',
        'descripcion': 'Saldos de cuentas por pagar al 31 de diciembre',
    },
    '1011': {
        'version': '6',
        'codigo_concepto': '1',
        'elemento_registro': 'decl',
        'descripcion': 'Información de las declaraciones tributarias',
    },
    '1012': {
        'version': '7',
        'codigo_concepto': '1',
        'elemento_registro': 'dectri',
        'descripcion': 'Información de las declaraciones tributarias (con tercero)',
    },
    '1647': {
        'version': '2',
        'codigo_concepto': '1',
        'elemento_registro': 'ingresos',
        'descripcion': 'Ingresos recibidos para terceros',
    },
    '2276': {
        'version': '4',
        'codigo_concepto': '1',
        'elemento_registro': 'rentra',
        'descripcion': 'Información de rentas de trabajo y pensiones',
    },
}

# Tipos de envío
TIPO_ENVIO_INICIAL    = '01'
TIPO_ENVIO_FRACCION   = '02'
TIPO_ENVIO_REEMPLAZO  = '03'
TIPO_ENVIO_CORRECCION = '04'

# Tipos de documento DIAN (códigos oficiales)
TIPO_DOC_CC  = '13'   # Cédula de ciudadanía
TIPO_DOC_CE  = '22'   # Cédula de extranjería
TIPO_DOC_NIT = '31'   # NIT
TIPO_DOC_NIUP = '41'  # No identificado en el exterior
TIPO_DOC_TI   = '12'  # Tarjeta de identidad
TIPO_DOC_PAS  = '42'  # Pasaporte
TIPO_DOC_NEX  = '43'  # Sin documento (cuantías menores)

# País Colombia
PAIS_COLOMBIA = '169'


# ================================================================
# DATACLASSES — Tercero, Cabecera, Registros por formato
# ================================================================

@dataclass
class Tercero:
    """Datos completos de un tercero (NIT, CC, etc)."""
    nit: str
    tipo_documento: str
    razon_social: Optional[str] = None
    primer_apellido: Optional[str] = None
    segundo_apellido: Optional[str] = None
    primer_nombre: Optional[str] = None
    otros_nombres: Optional[str] = None
    direccion: Optional[str] = None
    codigo_pais: str = PAIS_COLOMBIA
    codigo_departamento: Optional[str] = None
    codigo_municipio: Optional[str] = None
    digito_verificacion: Optional[str] = None  # solo para NIT


@dataclass
class CabeceraXML:
    """Datos de la cabecera <Cab> del XML."""
    ano_gravable: int
    formato: str
    version: str
    numero_envio: int = 1
    fecha_envio: datetime = field(default_factory=datetime.now)
    fecha_inicial: date = field(default_factory=lambda: date(2025, 1, 1))
    fecha_final: date = field(default_factory=lambda: date(2025, 12, 31))
    tipo_envio: str = TIPO_ENVIO_INICIAL


@dataclass
class RegistroF1001:
    """
    Un registro <pagos> del Formato 1001 v.10.
    
    Estructura completa según XSD oficial:
    - cpt: concepto (5001, 5002, ..., 5008, etc.)
    - pais: REQUERIDO (default 169 Colombia)
    - pago: pago/abono deducible
    - pnded: pago/abono no deducible
    - ided: IVA mayor valor, deducible (Art. 491 ET)
    - inded: IVA mayor valor, no deducible
    - retp: retención fuente Renta PRACTICADA
    - reta: retención fuente Renta ASUMIDA
    - comun: retención fuente IVA a responsables (common)
    - ndom: retención fuente IVA a no residentes/no domiciliados
    """
    tercero: Tercero
    concepto: int
    pago_deducible: float = 0.0         # pago
    pago_no_deducible: float = 0.0      # pnded
    iva_mayor_deducible: float = 0.0    # ided
    iva_mayor_no_deducible: float = 0.0 # inded
    retencion_renta_practicada: float = 0.0  # retp
    retencion_renta_asumida: float = 0.0     # reta
    retencion_iva_responsables: float = 0.0  # comun
    retencion_iva_no_dom: float = 0.0        # ndom
    nota: str = ''


@dataclass
class RegistroF1003:
    """Un registro <rets> del Formato 1003 v.7."""
    tercero: Tercero
    concepto: int
    valor_base: float = 0.0     # valor (acumulado del pago/abono)
    retencion: float = 0.0       # ret (retención practicada)
    nota: str = ''


@dataclass
class RegistroF1005:
    """Un registro <impventas> del Formato 1005 v.8 (IVA descontable)."""
    tercero: Tercero
    iva_descontable: float = 0.0      # vimp
    iva_dev_ventas: float = 0.0       # ivade
    iva_mayor_costo: float = 0.0      # ivavcg (opcional)
    nota: str = ''


@dataclass
class RegistroF1006:
    """Un registro <impoventas> del Formato 1006 v.8 (IVA generado)."""
    tercero: Tercero
    iva_generado: float = 0.0          # imp
    iva_dev_compras: float = 0.0       # iva
    impuesto_consumo: float = 0.0      # icon
    nota: str = ''


@dataclass
class RegistroF1008:
    """Un registro <saldoscc> del Formato 1008 v.7 (CxC al 31-Dic)."""
    tercero: Tercero
    concepto: int      # cpt: 1315, 1320, 1325...
    saldo: float = 0.0 # sal
    nota: str = ''


@dataclass
class RegistroF1011:
    """
    Un registro <decl> del Formato 1011 v.6.
    SIN tercero — totalmente agregado por concepto.
    """
    concepto: int       # cpt
    saldo: float = 0.0  # sal
    nota: str = ''


@dataclass
class RegistroF1012:
    """Un registro <dectri> del Formato 1012 v.7."""
    tercero: Tercero
    concepto: int       # cpt
    valor: float = 0.0  # val
    nota: str = ''


@dataclass
class RegistroF1007:
    """
    Un registro <ingresos> del Formato 1007 v.9 (Ingresos recibidos).
    Atributos XSD: cpt, tdoc, nid, apl1/.../raz, pais, ibru, dred
    """
    tercero: Tercero
    concepto: int                       # cpt: 4001, 4002...
    ingresos_brutos: float = 0.0        # ibru
    devoluciones_rebajas_descuentos: float = 0.0  # dred
    nota: str = ''


@dataclass
class RegistroF1009:
    """
    Un registro <saldoscp> del Formato 1009 v.7 (CxP al 31-Dic).
    Estructura idéntica a F1008 pero con elemento 'saldoscp' y conceptos distintos.
    Atributos XSD: cpt, tdoc, nid, dv, apl1/.../raz, dir, dpto, mun, pais, sal
    """
    tercero: Tercero
    concepto: int       # cpt: 2201, 2202, 2214 (proveedores), etc.
    saldo: float = 0.0  # sal
    nota: str = ''


@dataclass
class TerceroDestino:
    """
    Tercero destino para F1647 (a quien se transfiere el ingreso).
    Solo identificación + dirección, sin DV separado.
    """
    nit: str
    tipo_documento: str
    razon_social: Optional[str] = None
    primer_apellido: Optional[str] = None
    segundo_apellido: Optional[str] = None
    primer_nombre: Optional[str] = None
    otros_nombres: Optional[str] = None
    direccion: Optional[str] = None
    codigo_pais: str = PAIS_COLOMBIA
    codigo_departamento: Optional[str] = None
    codigo_municipio: Optional[str] = None


@dataclass
class RegistroF1647:
    """
    Un registro <ingresos> del Formato 1647 v.2 (Ingresos recibidos para terceros).
    
    Tiene DOS terceros:
      - "tercero" = quien paga al informante (de quien se recibe)
      - "tercero_destino" = a quien se transfiere el ingreso
    
    Atributos XSD:
      con, tdoc, nid, dv, apl1/.../raz, pais, vtotal, ving, vret,
      tdoc2, nid2i, apl1i/.../razi, dir, cdpt, cmcp, paist
    """
    tercero: Tercero              # de quien se recibe
    tercero_destino: TerceroDestino  # para quien se recibió
    concepto: int                 # con
    valor_total: float = 0.0      # vtotal
    valor_ingreso_transferido: float = 0.0  # ving
    valor_retencion_transferida: float = 0.0  # vret
    nota: str = ''


@dataclass
class RegistroF2276:
    """
    Un registro <rentra> del Formato 2276 v.4 (Rentas de trabajo y pensiones).
    El formato más complejo: 45 atributos.
    
    El "tercero" es el beneficiario (empleado). NO usa la dataclass Tercero
    estándar porque los nombres de atributos son distintos (pap, sap, pno, ono).
    """
    # Identificación del beneficiario (empleado)
    entidad_informante: int       # entinfo: 11=salarios (default)
    tipo_doc_beneficiario: str    # tdocb
    nit_beneficiario: str         # nitb
    primer_apellido: str = ''     # pap (REQUERIDO)
    segundo_apellido: str = ''    # sap (opcional)
    primer_nombre: str = ''       # pno (REQUERIDO)
    otros_nombres: str = ''       # ono (opcional)
    direccion: str = ''           # dir (opcional)
    codigo_departamento: str = '' # dpto (opcional)
    codigo_municipio: str = ''    # mun (opcional)
    codigo_pais: str = PAIS_COLOMBIA  # pais (REQUERIDO)
    
    # Pagos rentas de trabajo (todos REQUERIDOS)
    pagos_salarios: float = 0.0          # pasa
    pagos_emolumentos_ecles: float = 0.0 # paec
    pagos_bonos_papel: float = 0.0       # pabop
    valor_exceso_alimentacion: float = 0.0  # vaex
    pagos_honorarios: float = 0.0        # paho
    pagos_servicios: float = 0.0         # pase
    pagos_comisiones: float = 0.0        # paco
    pagos_prestaciones: float = 0.0      # papre
    pagos_viaticos: float = 0.0          # pavia
    pagos_gastos_repres: float = 0.0     # paga
    pagos_compensaciones_coop: float = 0.0  # patra
    valor_apoyos_estado: float = 0.0     # vapo
    otros_pagos: float = 0.0             # potro
    
    # Cesantías
    cesantias_pagadas: float = 0.0       # cein (efectivamente pagadas al empleado)
    cesantias_consignadas: float = 0.0   # ceco (al fondo)
    auxilio_cesantias_tradicional: float = 0.0  # auce
    
    # Pensiones
    pensiones_juvi: float = 0.0          # peju (jubilación/vejez/invalidez)
    
    # Total ingresos
    total_ingresos_brutos: float = 0.0   # tingbtp
    
    # Aportes y deducciones
    aportes_obligatorios_salud: float = 0.0    # apos
    aportes_obligatorios_pension: float = 0.0  # apof
    aportes_voluntarios_rais: float = 0.0      # aprais
    aportes_voluntarios_pension: float = 0.0   # apov
    aportes_afc: float = 0.0                   # apafc
    aportes_avc: float = 0.0                   # apavc
    
    # Retenciones e IVA
    retencion_fuente: float = 0.0        # vare
    iva_mayor_valor: float = 0.0         # ivav
    retencion_iva: float = 0.0           # rfiva
    pagos_alimentacion_41uvt: float = 0.0  # pagahuvt
    ingreso_laboral_promedio_6m: float = 0.0  # vilap
    
    # Dependientes y contratos (opcionales)
    tipo_doc_dependiente: str = ''       # tdocde
    nit_dependiente: str = ''            # nitde
    identificacion_fideicomiso: str = '' # identfc
    tipo_doc_partic_contrato: str = ''   # tdocpcc
    nit_partic_contrato: str = ''        # nitpcc
    
    nota: str = ''


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
    """
    return f'Dmuisca_{formato}{version.zfill(2)}{ano_envio}{tipo_envio}{str(consecutivo).zfill(8)}.xml'


def normalizar_nit(nit: str) -> str:
    """Quita guiones, puntos y espacios del NIT."""
    return re.sub(r'\D', '', str(nit or ''))


# ================================================================
# HELPERS DE TERCERO POR PERFIL
# ================================================================
# Perfiles:
#   "simple":   solo identificación (F1005, F1006)
#   "con_pais": identificación + país (F1007, F1012)
#   "completo": identificación + dirección + dpto + municipio + país (F1001, F1003, F1008, F1009)

def _identificacion_basica(tercero: Tercero, incluir_dv: bool = True) -> dict:
    """Atributos de identificación: tdoc, nid, [dv], apl/nom o raz."""
    nit_limpio = normalizar_nit(tercero.nit)
    attrs = {
        'tdoc': tercero.tipo_documento,
        'nid': nit_limpio,
    }
    if incluir_dv and tercero.tipo_documento == TIPO_DOC_NIT:
        dv = tercero.digito_verificacion or calcular_dv(nit_limpio)
        attrs['dv'] = dv

    if tercero.razon_social:
        attrs['raz'] = tercero.razon_social[:450]
    else:
        if tercero.primer_apellido:
            attrs['apl1'] = tercero.primer_apellido[:60]
        if tercero.segundo_apellido:
            attrs['apl2'] = tercero.segundo_apellido[:60]
        if tercero.primer_nombre:
            attrs['nom1'] = tercero.primer_nombre[:60]
        if tercero.otros_nombres:
            attrs['nom2'] = tercero.otros_nombres[:60]
    return attrs


def _ubicacion(tercero: Tercero,
               incluir_dir: bool = True,
               nombre_dpto: str = 'dpto',
               nombre_mun: str = 'mun',
               incluir_pais: bool = True) -> dict:
    """Dirección + dpto + mun + país (con nombres de atributo configurables)."""
    attrs = {}
    if incluir_dir and tercero.direccion:
        attrs['dir'] = tercero.direccion[:200]
    if tercero.codigo_departamento:
        attrs[nombre_dpto] = str(tercero.codigo_departamento).zfill(2)
    if tercero.codigo_municipio:
        attrs[nombre_mun] = str(tercero.codigo_municipio).zfill(3)
    if incluir_pais:
        attrs['pais'] = tercero.codigo_pais or PAIS_COLOMBIA
    return attrs


# ================================================================
# ATRIBUTOS POR FORMATO
# ================================================================
# Importante: el orden de los atributos en el dict importa, openpyxl/lxml los
# emiten en orden de inserción. Aunque XSD acepta cualquier orden, mantener
# el orden oficial facilita comparar con el prevalidador.

def atributos_f1001(reg: RegistroF1001) -> dict:
    """<pagos cpt tdoc nid apl1/apl2/nom1/nom2/raz dir dpto mun pais pago pnded ided inded retp reta comun ndom/>"""
    attrs = {'cpt': str(reg.concepto)}
    attrs.update(_identificacion_basica(reg.tercero, incluir_dv=False))
    attrs.update(_ubicacion(reg.tercero, nombre_dpto='dpto', nombre_mun='mun', incluir_pais=True))
    attrs['pago']  = formatear_entero(reg.pago_deducible)
    attrs['pnded'] = formatear_entero(reg.pago_no_deducible)
    attrs['ided']  = formatear_entero(reg.iva_mayor_deducible)
    attrs['inded'] = formatear_entero(reg.iva_mayor_no_deducible)
    attrs['retp']  = formatear_entero(reg.retencion_renta_practicada)
    attrs['reta']  = formatear_entero(reg.retencion_renta_asumida)
    attrs['comun'] = formatear_entero(reg.retencion_iva_responsables)
    attrs['ndom']  = formatear_entero(reg.retencion_iva_no_dom)
    return attrs


def atributos_f1003(reg: RegistroF1003) -> dict:
    """<rets cpt tdoc nid dv apl1/.../raz dir dpto mcpo valor ret/>"""
    attrs = {'cpt': str(reg.concepto)}
    attrs.update(_identificacion_basica(reg.tercero, incluir_dv=True))
    # F1003 usa 'mcpo' (no 'mun') y NO lleva 'pais'
    if reg.tercero.direccion:
        attrs['dir'] = reg.tercero.direccion[:200]
    else:
        attrs['dir'] = ''  # REQ
    attrs['dpto'] = str(reg.tercero.codigo_departamento or '').zfill(2) if reg.tercero.codigo_departamento else ''
    attrs['mcpo'] = str(reg.tercero.codigo_municipio or '').zfill(3) if reg.tercero.codigo_municipio else ''
    attrs['valor'] = formatear_entero(reg.valor_base)
    attrs['ret']   = formatear_entero(reg.retencion)
    return attrs


def atributos_f1005(reg: RegistroF1005) -> dict:
    """<impventas tdoc nid dv apl1/.../raz vimp ivade ivavcg/>"""
    attrs = _identificacion_basica(reg.tercero, incluir_dv=True)
    attrs['vimp']  = formatear_entero(reg.iva_descontable)
    attrs['ivade'] = formatear_entero(reg.iva_dev_ventas)
    if reg.iva_mayor_costo > 0:
        attrs['ivavcg'] = formatear_entero(reg.iva_mayor_costo)
    return attrs


def atributos_f1006(reg: RegistroF1006) -> dict:
    """<impoventas tdoc nid dv apl1/.../raz imp iva icon/>"""
    attrs = _identificacion_basica(reg.tercero, incluir_dv=True)
    attrs['imp']  = formatear_entero(reg.iva_generado)
    attrs['iva']  = formatear_entero(reg.iva_dev_compras)
    attrs['icon'] = formatear_entero(reg.impuesto_consumo)
    return attrs


def atributos_f1008(reg: RegistroF1008) -> dict:
    """<saldoscc cpt tdoc nid dv apl1/.../raz dir dpto mun pais sal/>"""
    attrs = {'cpt': str(reg.concepto)}
    attrs.update(_identificacion_basica(reg.tercero, incluir_dv=True))
    attrs.update(_ubicacion(reg.tercero, nombre_dpto='dpto', nombre_mun='mun', incluir_pais=True))
    attrs['sal'] = formatear_entero(reg.saldo)
    return attrs


def atributos_f1011(reg: RegistroF1011) -> dict:
    """<decl cpt sal/>"""
    return {
        'cpt': str(reg.concepto),
        'sal': formatear_entero(reg.saldo),
    }


def atributos_f1012(reg: RegistroF1012) -> dict:
    """<dectri cpt tdoc nid dv apl1/.../raz pais val/>"""
    attrs = {'cpt': str(reg.concepto)}
    attrs.update(_identificacion_basica(reg.tercero, incluir_dv=True))
    attrs['pais'] = reg.tercero.codigo_pais or PAIS_COLOMBIA
    attrs['val']  = formatear_entero(reg.valor)
    return attrs


def atributos_f1007(reg: RegistroF1007) -> dict:
    """<ingresos cpt tdoc nid apl1/.../raz pais ibru dred/>
    
    F1007 NO lleva dv ni dirección/dpto/mun. Solo identidad + país + valores.
    """
    attrs = {'cpt': str(reg.concepto)}
    attrs.update(_identificacion_basica(reg.tercero, incluir_dv=False))
    attrs['pais'] = reg.tercero.codigo_pais or PAIS_COLOMBIA
    attrs['ibru'] = formatear_entero(reg.ingresos_brutos)
    attrs['dred'] = formatear_entero(reg.devoluciones_rebajas_descuentos)
    return attrs


def atributos_f1009(reg: RegistroF1009) -> dict:
    """<saldoscp cpt tdoc nid dv apl1/.../raz dir dpto mun pais sal/>
    
    Estructura idéntica a F1008 pero el elemento es 'saldoscp'.
    """
    attrs = {'cpt': str(reg.concepto)}
    attrs.update(_identificacion_basica(reg.tercero, incluir_dv=True))
    attrs.update(_ubicacion(reg.tercero, nombre_dpto='dpto', nombre_mun='mun', incluir_pais=True))
    attrs['sal'] = formatear_entero(reg.saldo)
    return attrs


def atributos_f1647(reg: RegistroF1647) -> dict:
    """
    <ingresos con tdoc nid dv apl1/.../raz pais vtotal ving vret
              tdoc2 nid2i apl1i/.../razi dir cdpt cmcp paist/>
    
    F1647 tiene DOS terceros: el que paga y a quien se transfiere.
    """
    # Tercero 1: quien paga (de quien se recibe)
    attrs = {'con': str(reg.concepto)}
    attrs.update(_identificacion_basica(reg.tercero, incluir_dv=True))
    attrs['pais'] = reg.tercero.codigo_pais or PAIS_COLOMBIA
    
    # Valores
    attrs['vtotal'] = formatear_entero(reg.valor_total)
    attrs['ving']   = formatear_entero(reg.valor_ingreso_transferido)
    attrs['vret']   = formatear_entero(reg.valor_retencion_transferida)
    
    # Tercero 2: a quien se transfiere (con sufijo "i" o "2")
    dest = reg.tercero_destino
    nit_dest = normalizar_nit(dest.nit)
    attrs['tdoc2']  = dest.tipo_documento
    attrs['nid2i']  = nit_dest
    
    if dest.razon_social:
        attrs['razi'] = dest.razon_social[:450]
    else:
        if dest.primer_apellido:
            attrs['apl1i'] = dest.primer_apellido[:60]
        if dest.segundo_apellido:
            attrs['apl2i'] = dest.segundo_apellido[:60]
        if dest.primer_nombre:
            attrs['nom1i'] = dest.primer_nombre[:60]
        if dest.otros_nombres:
            attrs['nom2i'] = dest.otros_nombres[:60]
    
    if dest.direccion:
        attrs['dir'] = dest.direccion[:200]
    if dest.codigo_departamento:
        attrs['cdpt'] = str(dest.codigo_departamento).zfill(2)
    if dest.codigo_municipio:
        attrs['cmcp'] = str(dest.codigo_municipio).zfill(3)
    
    attrs['paist'] = dest.codigo_pais or PAIS_COLOMBIA
    return attrs


def atributos_f2276(reg: RegistroF2276) -> dict:
    """
    <rentra entinfo tdocb nitb pap sap pno ono dir dpto mun pais
            pasa paec pabop vaex paho pase paco papre pavia paga patra vapo potro
            cein ceco auce peju tingbtp
            apos apof aprais apov apafc apavc
            vare ivav rfiva pagahuvt vilap
            tdocde nitde identfc tdocpcc nitpcc/>
    
    El formato más complejo: 45 atributos, 28 obligatorios.
    """
    nit_limpio = normalizar_nit(reg.nit_beneficiario)
    
    attrs = {
        'entinfo': str(reg.entidad_informante),
        'tdocb': reg.tipo_doc_beneficiario,
        'nitb': nit_limpio,
    }
    
    # Nombres del beneficiario (pap/pno son REQ, sap/ono son opt)
    attrs['pap'] = reg.primer_apellido[:60] if reg.primer_apellido else ''
    if reg.segundo_apellido:
        attrs['sap'] = reg.segundo_apellido[:60]
    attrs['pno'] = reg.primer_nombre[:60] if reg.primer_nombre else ''
    if reg.otros_nombres:
        attrs['ono'] = reg.otros_nombres[:60]
    
    # Ubicación
    if reg.direccion:
        attrs['dir'] = reg.direccion[:200]
    if reg.codigo_departamento:
        attrs['dpto'] = str(reg.codigo_departamento).zfill(2)
    if reg.codigo_municipio:
        attrs['mun'] = str(reg.codigo_municipio).zfill(3)
    attrs['pais'] = reg.codigo_pais or PAIS_COLOMBIA
    
    # Pagos rentas de trabajo (todos REQ)
    attrs['pasa']  = formatear_entero(reg.pagos_salarios)
    attrs['paec']  = formatear_entero(reg.pagos_emolumentos_ecles)
    attrs['pabop'] = formatear_entero(reg.pagos_bonos_papel)
    attrs['vaex']  = formatear_entero(reg.valor_exceso_alimentacion)
    attrs['paho']  = formatear_entero(reg.pagos_honorarios)
    attrs['pase']  = formatear_entero(reg.pagos_servicios)
    attrs['paco']  = formatear_entero(reg.pagos_comisiones)
    attrs['papre'] = formatear_entero(reg.pagos_prestaciones)
    attrs['pavia'] = formatear_entero(reg.pagos_viaticos)
    attrs['paga']  = formatear_entero(reg.pagos_gastos_repres)
    attrs['patra'] = formatear_entero(reg.pagos_compensaciones_coop)
    attrs['vapo']  = formatear_entero(reg.valor_apoyos_estado)
    attrs['potro'] = formatear_entero(reg.otros_pagos)
    
    # Cesantías y pensiones
    attrs['cein'] = formatear_entero(reg.cesantias_pagadas)
    attrs['ceco'] = formatear_entero(reg.cesantias_consignadas)
    attrs['auce'] = formatear_entero(reg.auxilio_cesantias_tradicional)
    attrs['peju'] = formatear_entero(reg.pensiones_juvi)
    
    # Total
    attrs['tingbtp'] = formatear_entero(reg.total_ingresos_brutos)
    
    # Aportes
    attrs['apos']   = formatear_entero(reg.aportes_obligatorios_salud)
    attrs['apof']   = formatear_entero(reg.aportes_obligatorios_pension)
    attrs['aprais'] = formatear_entero(reg.aportes_voluntarios_rais)
    attrs['apov']   = formatear_entero(reg.aportes_voluntarios_pension)
    attrs['apafc']  = formatear_entero(reg.aportes_afc)
    attrs['apavc']  = formatear_entero(reg.aportes_avc)
    
    # Retenciones y otros
    attrs['vare']     = formatear_entero(reg.retencion_fuente)
    attrs['ivav']     = formatear_entero(reg.iva_mayor_valor)
    attrs['rfiva']    = formatear_entero(reg.retencion_iva)
    attrs['pagahuvt'] = formatear_entero(reg.pagos_alimentacion_41uvt)
    attrs['vilap']    = formatear_entero(reg.ingreso_laboral_promedio_6m)
    
    # Dependientes y contratos (opcionales)
    if reg.tipo_doc_dependiente:
        attrs['tdocde'] = reg.tipo_doc_dependiente
    if reg.nit_dependiente:
        attrs['nitde'] = normalizar_nit(reg.nit_dependiente)
    if reg.identificacion_fideicomiso:
        attrs['identfc'] = reg.identificacion_fideicomiso
    if reg.tipo_doc_partic_contrato:
        attrs['tdocpcc'] = reg.tipo_doc_partic_contrato
    if reg.nit_partic_contrato:
        attrs['nitpcc'] = normalizar_nit(reg.nit_partic_contrato)
    
    return attrs


# ================================================================
# CONSTRUCCIÓN DE XML
# ================================================================

def _construir_xml(cabecera: CabeceraXML,
                    registros_attrs: list[dict],
                    valor_total: float) -> str:
    """
    Construye el string XML completo con encoding ISO-8859-1, SIN namespace.
    Sigue exactamente la estructura del XSD oficial DIAN.
    """
    config = FORMATOS_CONFIG[cabecera.formato]
    elemento_registro = config['elemento_registro']

    # Elemento raíz SIN namespace (los XSDs DIAN no declaran targetNamespace)
    root = ET.Element('mas')

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

    # Registros
    for attrs in registros_attrs:
        ET.SubElement(root, elemento_registro, attrs)

    # Serializar con declaración ISO-8859-1
    xml_bytes = ET.tostring(root, encoding='ISO-8859-1', xml_declaration=True)
    return xml_bytes.decode('ISO-8859-1')


# ================================================================
# GENERADORES DE XML POR FORMATO
# ================================================================

def generar_xml_f1001(cabecera: CabeceraXML, registros: list[RegistroF1001]) -> str:
    cabecera.formato = '1001'
    cabecera.version = '10'
    attrs_lista = [atributos_f1001(r) for r in registros]
    valor_total = sum(r.pago_deducible + r.pago_no_deducible for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f1003(cabecera: CabeceraXML, registros: list[RegistroF1003]) -> str:
    cabecera.formato = '1003'
    cabecera.version = '7'
    attrs_lista = [atributos_f1003(r) for r in registros]
    valor_total = sum(r.retencion for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f1005(cabecera: CabeceraXML, registros: list[RegistroF1005]) -> str:
    cabecera.formato = '1005'
    cabecera.version = '8'
    attrs_lista = [atributos_f1005(r) for r in registros]
    valor_total = sum(r.iva_descontable + r.iva_dev_ventas + r.iva_mayor_costo for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f1006(cabecera: CabeceraXML, registros: list[RegistroF1006]) -> str:
    cabecera.formato = '1006'
    cabecera.version = '8'
    attrs_lista = [atributos_f1006(r) for r in registros]
    valor_total = sum(r.iva_generado + r.iva_dev_compras + r.impuesto_consumo for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f1008(cabecera: CabeceraXML, registros: list[RegistroF1008]) -> str:
    cabecera.formato = '1008'
    cabecera.version = '7'
    attrs_lista = [atributos_f1008(r) for r in registros]
    valor_total = sum(r.saldo for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f1011(cabecera: CabeceraXML, registros: list[RegistroF1011]) -> str:
    cabecera.formato = '1011'
    cabecera.version = '6'
    attrs_lista = [atributos_f1011(r) for r in registros]
    valor_total = sum(r.saldo for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f1012(cabecera: CabeceraXML, registros: list[RegistroF1012]) -> str:
    cabecera.formato = '1012'
    cabecera.version = '7'
    attrs_lista = [atributos_f1012(r) for r in registros]
    valor_total = sum(r.valor for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f1007(cabecera: CabeceraXML, registros: list[RegistroF1007]) -> str:
    cabecera.formato = '1007'
    cabecera.version = '9'
    attrs_lista = [atributos_f1007(r) for r in registros]
    valor_total = sum(r.ingresos_brutos for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f1009(cabecera: CabeceraXML, registros: list[RegistroF1009]) -> str:
    cabecera.formato = '1009'
    cabecera.version = '7'
    attrs_lista = [atributos_f1009(r) for r in registros]
    valor_total = sum(r.saldo for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f1647(cabecera: CabeceraXML, registros: list[RegistroF1647]) -> str:
    cabecera.formato = '1647'
    cabecera.version = '2'
    attrs_lista = [atributos_f1647(r) for r in registros]
    valor_total = sum(r.valor_total for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def generar_xml_f2276(cabecera: CabeceraXML, registros: list[RegistroF2276]) -> str:
    cabecera.formato = '2276'
    cabecera.version = '4'
    attrs_lista = [atributos_f2276(r) for r in registros]
    valor_total = sum(r.total_ingresos_brutos for r in registros)
    return _construir_xml(cabecera, attrs_lista, valor_total)


def guardar_xml(xml_string: str, ruta: str | Path) -> Path:
    """Guarda el XML en disco con encoding ISO-8859-1."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(xml_string.encode('ISO-8859-1'))
    return ruta
