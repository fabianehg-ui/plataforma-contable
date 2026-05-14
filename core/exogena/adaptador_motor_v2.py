"""
Adaptador Motor v1 → Generador XML v2
========================================

Toma el output del motor de clasificación existente (`MovimientoClasificado` +
`retenciones_por_nit` + maestro de terceros) y produce los registros tipados
del generador XML v2 (`RegistroF1001`, `RegistroF1005`, etc).

Es el puente que conecta lo que ya existe en el repo con lo nuevo.

Uso:
    from core.exogena.adaptador_motor_v2 import construir_registros_v2

    # resultado: ResultadoClasificacion del motor (ya con PILA integrado)
    # terceros_dict: {nit: dict con datos del tercero (de exogena_terceros)}
    registros_por_formato = construir_registros_v2(resultado, terceros_dict)

    # registros_por_formato es:
    # {
    #   '1001': [RegistroF1001(...), ...],
    #   '1005': [RegistroF1005(...), ...],
    #   ...
    # }
"""

from __future__ import annotations
from collections import defaultdict
from typing import Optional

# Imports robustos (producción y tests locales)
try:
    from core.exogena.motor_clasificacion import (
        MovimientoClasificado,
        ResultadoClasificacion,
        RetencionAcumulada,
    )
    from core.exogena.generador_xml_v2 import (
        Tercero, TerceroDestino,
        TIPO_DOC_NIT, TIPO_DOC_CC, TIPO_DOC_NEX, PAIS_COLOMBIA,
        RegistroF1001, RegistroF1003, RegistroF1005, RegistroF1006, RegistroF1007,
        RegistroF1008, RegistroF1009, RegistroF1011, RegistroF1012,
        RegistroF1647, RegistroF2276,
    )
except ImportError:
    from motor_clasificacion import (
        MovimientoClasificado,
        ResultadoClasificacion,
        RetencionAcumulada,
    )
    from generador_xml_v2 import (
        Tercero, TerceroDestino,
        TIPO_DOC_NIT, TIPO_DOC_CC, TIPO_DOC_NEX, PAIS_COLOMBIA,
        RegistroF1001, RegistroF1003, RegistroF1005, RegistroF1006, RegistroF1007,
        RegistroF1008, RegistroF1009, RegistroF1011, RegistroF1012,
        RegistroF1647, RegistroF2276,
    )


# ================================================================
# NIT genérico cuando no hay tercero (cuantías menores)
# ================================================================

NIT_CUANTIAS_MENORES = '222222222'
DV_CUANTIAS_MENORES = '0'

# Conceptos especiales para F1001 desde retenciones 2365
CONCEPTO_EXCESO_ANIO_ANTERIOR = 5028   # F1001 concepto especial

# Tipo de documento por defecto si no hay dato
TIPO_DOC_DEFAULT = TIPO_DOC_NIT


# ================================================================
# Helpers
# ================================================================

def _build_tercero(nit: str, terceros_dict: dict) -> Tercero:
    """Construye un Tercero (v2) desde el dict de terceros de BD."""
    nit_str = str(nit or '').strip()
    if not nit_str:
        # Tercero genérico: cuantías menores
        return Tercero(
            nit=NIT_CUANTIAS_MENORES,
            tipo_documento=TIPO_DOC_NEX,
            razon_social='CUANTIAS MENORES',
            codigo_pais=PAIS_COLOMBIA,
        )

    t = terceros_dict.get(nit_str, {})

    tipo_doc = str(t.get('tipo_documento') or TIPO_DOC_NIT)
    # tipo_documento en BD viene como int; normalizar a string
    if isinstance(tipo_doc, int) or (isinstance(tipo_doc, str) and tipo_doc.isdigit()):
        tipo_doc = str(tipo_doc).zfill(2)

    return Tercero(
        nit=nit_str,
        tipo_documento=tipo_doc,
        razon_social=t.get('razon_social') or None,
        primer_apellido=t.get('primer_apellido') or None,
        segundo_apellido=t.get('segundo_apellido') or None,
        primer_nombre=t.get('primer_nombre') or None,
        otros_nombres=t.get('otros_nombres') or None,
        direccion=t.get('direccion') or None,
        codigo_departamento=t.get('codigo_dpto') or None,
        codigo_municipio=t.get('codigo_municipio') or None,
        codigo_pais=t.get('codigo_pais') or PAIS_COLOMBIA,
        digito_verificacion=(
            str(t.get('dv')) if t.get('dv') is not None else None
        ),
    )


def _tercero_cuantias_menores() -> Tercero:
    """Tercero genérico para movimientos sin NIT."""
    return Tercero(
        nit=NIT_CUANTIAS_MENORES,
        tipo_documento=TIPO_DOC_NEX,
        razon_social='CUANTIAS MENORES',
        codigo_pais=PAIS_COLOMBIA,
        digito_verificacion=DV_CUANTIAS_MENORES,
    )


# ================================================================
# Construcción por formato
# ================================================================

def _construir_f1001(
    movs: list[MovimientoClasificado],
    retenciones_por_nit: dict,
    terceros_dict: dict,
) -> list[RegistroF1001]:
    """
    Construye registros F1001 agrupando por (NIT, concepto) y sumando valores.
    Asocia las retenciones 2365 indexadas por NIT al primer registro del NIT.
    """
    # Agrupar por (nit, concepto)
    agrupados: dict[tuple, dict] = defaultdict(lambda: {
        'pago_deducible': 0.0,
        'pago_no_deducible': 0.0,
        'iva_mayor_deducible': 0.0,
        'iva_mayor_no_deducible': 0.0,
    })

    for m in movs:
        if m.formato_dian != '1001':
            continue
        if m.concepto_dian is None:
            continue
        nit = (m.nit or '').strip() or NIT_CUANTIAS_MENORES
        key = (nit, int(m.concepto_dian))

        # CASO PILA: si el movimiento trae split empleador/trabajador,
        # respetarlo (deducible = empleador, no deducible = trabajador).
        # Esto solo aplica a movs de PILA (capa_resolucion == 'pila_aportes').
        if m.valor_deducible is not None or m.valor_no_deducible is not None:
            agrupados[key]['pago_deducible'] += float(m.valor_deducible or 0)
            agrupados[key]['pago_no_deducible'] += float(m.valor_no_deducible or 0)
            continue

        # CASO NORMAL: usa base_aplicable
        base = (m.base_aplicable or 'deducible').lower()

        if 'iva_mayor' in base or 'ivamc' in base or base == 'iva_mc':
            if 'no_ded' in base or 'nded' in base:
                agrupados[key]['iva_mayor_no_deducible'] += float(m.valor or 0)
            else:
                agrupados[key]['iva_mayor_deducible'] += float(m.valor or 0)
        elif 'no_ded' in base or 'nded' in base:
            agrupados[key]['pago_no_deducible'] += float(m.valor or 0)
        else:
            agrupados[key]['pago_deducible'] += float(m.valor or 0)

    # Acumuladores de retenciones por NIT que NO han sido asignadas todavía
    # (las asignamos al PRIMER concepto del NIT que aparezca)
    nits_con_retencion_asignada = set()

    registros = []
    for (nit, concepto), vals in agrupados.items():
        reg = RegistroF1001(
            tercero=_build_tercero(nit, terceros_dict),
            concepto=concepto,
            pago_deducible=vals['pago_deducible'],
            pago_no_deducible=vals['pago_no_deducible'],
            iva_mayor_deducible=vals['iva_mayor_deducible'],
            iva_mayor_no_deducible=vals['iva_mayor_no_deducible'],
        )

        # Asignar las retenciones 2365 al primer registro del NIT
        if nit not in nits_con_retencion_asignada and nit in retenciones_por_nit:
            ret = retenciones_por_nit[nit]
            # `RetencionAcumulada` tiene f1001_retencion_practicada
            reg.retencion_renta_practicada = float(
                getattr(ret, 'f1001_retencion_practicada', 0) or 0
            )
            nits_con_retencion_asignada.add(nit)

        registros.append(reg)

    # Agregar registros especiales del concepto 5028 (exceso año anterior)
    # desde retenciones_por_nit
    for nit, ret in retenciones_por_nit.items():
        exceso = float(getattr(ret, 'exceso_periodos_anteriores', 0) or 0)
        if exceso > 0:
            registros.append(RegistroF1001(
                tercero=_build_tercero(nit, terceros_dict),
                concepto=CONCEPTO_EXCESO_ANIO_ANTERIOR,
                pago_deducible=0.0,
                retencion_renta_practicada=-exceso,  # resta como menor valor
            ))

    return registros


def _construir_f1003(
    movs: list[MovimientoClasificado],
    terceros_dict: dict,
) -> list[RegistroF1003]:
    """F1003: retenciones que le practicaron, agrupado por (NIT, concepto)."""
    agrupados: dict[tuple, dict] = defaultdict(lambda: {
        'valor_base': 0.0,
        'retencion': 0.0,
    })

    for m in movs:
        if m.formato_dian != '1003' or m.concepto_dian is None:
            continue
        nit = (m.nit or '').strip() or NIT_CUANTIAS_MENORES
        key = (nit, int(m.concepto_dian))
        # En F1003 el valor del motor es la retención practicada
        agrupados[key]['retencion'] += float(m.valor or 0)
        # base_aplicable puede traer la base; si no, queda 0
        # (el motor a veces lo guarda en nota o no lo guarda)

    return [
        RegistroF1003(
            tercero=_build_tercero(nit, terceros_dict),
            concepto=concepto,
            valor_base=vals['valor_base'],
            retencion=vals['retencion'],
        )
        for (nit, concepto), vals in agrupados.items()
    ]


def _construir_f1005(
    movs: list[MovimientoClasificado],
    terceros_dict: dict,
) -> list[RegistroF1005]:
    """F1005: IVA descontable agrupado por NIT (sin concepto)."""
    agrupados: dict[str, dict] = defaultdict(lambda: {
        'iva_descontable': 0.0,
        'iva_dev_ventas': 0.0,
    })

    for m in movs:
        if m.formato_dian != '1005':
            continue
        nit = (m.nit or '').strip() or NIT_CUANTIAS_MENORES
        base = (m.base_aplicable or 'descontable').lower()
        if 'dev' in base or 'devolucion' in base:
            agrupados[nit]['iva_dev_ventas'] += float(m.valor or 0)
        else:
            agrupados[nit]['iva_descontable'] += float(m.valor or 0)

    return [
        RegistroF1005(
            tercero=_build_tercero(nit, terceros_dict),
            iva_descontable=v['iva_descontable'],
            iva_dev_ventas=v['iva_dev_ventas'],
        )
        for nit, v in agrupados.items()
    ]


def _construir_f1006(
    movs: list[MovimientoClasificado],
    terceros_dict: dict,
) -> list[RegistroF1006]:
    """F1006: IVA generado + INC + IVA dev compras, agrupado por NIT."""
    agrupados: dict[str, dict] = defaultdict(lambda: {
        'iva_generado': 0.0,
        'iva_dev_compras': 0.0,
        'impuesto_consumo': 0.0,
    })

    for m in movs:
        if m.formato_dian != '1006':
            continue
        nit = (m.nit or '').strip() or NIT_CUANTIAS_MENORES
        base = (m.base_aplicable or 'generado').lower()
        if 'inc' in base or 'consumo' in base:
            agrupados[nit]['impuesto_consumo'] += float(m.valor or 0)
        elif 'dev' in base:
            agrupados[nit]['iva_dev_compras'] += float(m.valor or 0)
        else:
            agrupados[nit]['iva_generado'] += float(m.valor or 0)

    return [
        RegistroF1006(
            tercero=_build_tercero(nit, terceros_dict),
            iva_generado=v['iva_generado'],
            iva_dev_compras=v['iva_dev_compras'],
            impuesto_consumo=v['impuesto_consumo'],
        )
        for nit, v in agrupados.items()
    ]


def _construir_f1007(
    movs: list[MovimientoClasificado],
    terceros_dict: dict,
) -> list[RegistroF1007]:
    """F1007: ingresos recibidos por (NIT, concepto)."""
    agrupados: dict[tuple, dict] = defaultdict(lambda: {
        'ingresos_brutos': 0.0,
        'devoluciones_rebajas_descuentos': 0.0,
    })

    for m in movs:
        if m.formato_dian != '1007' or m.concepto_dian is None:
            continue
        nit = (m.nit or '').strip() or NIT_CUANTIAS_MENORES
        key = (nit, int(m.concepto_dian))
        base = (m.base_aplicable or 'ingresos').lower()
        if 'dev' in base or 'rebaja' in base:
            agrupados[key]['devoluciones_rebajas_descuentos'] += float(m.valor or 0)
        else:
            agrupados[key]['ingresos_brutos'] += float(m.valor or 0)

    return [
        RegistroF1007(
            tercero=_build_tercero(nit, terceros_dict),
            concepto=concepto,
            ingresos_brutos=v['ingresos_brutos'],
            devoluciones_rebajas_descuentos=v['devoluciones_rebajas_descuentos'],
        )
        for (nit, concepto), v in agrupados.items()
    ]


def _construir_saldos_por_nit_concepto(
    movs: list[MovimientoClasificado],
    formato_objetivo: str,
    clase_registro,
    terceros_dict: dict,
) -> list:
    """Helper para F1008/F1009: saldos por (NIT, concepto)."""
    agrupados: dict[tuple, float] = defaultdict(float)
    for m in movs:
        if m.formato_dian != formato_objetivo or m.concepto_dian is None:
            continue
        nit = (m.nit or '').strip() or NIT_CUANTIAS_MENORES
        key = (nit, int(m.concepto_dian))
        agrupados[key] += float(m.valor or 0)

    return [
        clase_registro(
            tercero=_build_tercero(nit, terceros_dict),
            concepto=concepto,
            saldo=valor,
        )
        for (nit, concepto), valor in agrupados.items()
    ]


def _construir_f1011(movs: list[MovimientoClasificado]) -> list[RegistroF1011]:
    """F1011: declaraciones tributarias agregadas por concepto (sin NIT)."""
    agrupados: dict[int, float] = defaultdict(float)
    for m in movs:
        if m.formato_dian != '1011' or m.concepto_dian is None:
            continue
        agrupados[int(m.concepto_dian)] += float(m.valor or 0)

    return [
        RegistroF1011(concepto=concepto, saldo=valor)
        for concepto, valor in agrupados.items()
    ]


def _construir_f1012(
    movs: list[MovimientoClasificado],
    terceros_dict: dict,
) -> list[RegistroF1012]:
    """F1012: saldos bancarios y declaraciones tributarias con tercero."""
    agrupados: dict[tuple, float] = defaultdict(float)
    for m in movs:
        if m.formato_dian != '1012' or m.concepto_dian is None:
            continue
        nit = (m.nit or '').strip() or NIT_CUANTIAS_MENORES
        key = (nit, int(m.concepto_dian))
        agrupados[key] += float(m.valor or 0)

    return [
        RegistroF1012(
            tercero=_build_tercero(nit, terceros_dict),
            concepto=concepto,
            valor=valor,
        )
        for (nit, concepto), valor in agrupados.items()
    ]


def _construir_f1647(
    movs: list[MovimientoClasificado],
    terceros_dict: dict,
) -> list[RegistroF1647]:
    """
    F1647: ingresos recibidos para terceros (estructura compleja con DOS terceros).
    
    El motor probablemente no maneja F1647 directamente. Este es un STUB que se
    activará cuando se modele en el motor. Por ahora devuelve [].
    """
    # TODO: integrar cuando el motor produzca movimientos F1647
    return []


def _construir_f2276(
    movs: list[MovimientoClasificado],
    retenciones_por_nit: dict,
    terceros_dict: dict,
) -> list[RegistroF2276]:
    """
    F2276: rentas de trabajo y pensiones por empleado.

    El integrador PILA produce líneas F2276 con:
      - codigo_cuenta = '_pila_f2276'
      - nit = cédula del empleado
      - concepto_dian: usado como sub-concepto interno (salarios, cesantías, etc.)
      - valor

    Aquí agrupamos por empleado (NIT) y sumamos campos por sub-concepto.
    """
    # Agrupar movs por empleado
    por_empleado: dict[str, dict] = defaultdict(lambda: {
        'salarios': 0.0,
        'cesantias_consignadas': 0.0,
        'cesantias_pagadas': 0.0,
        'honorarios': 0.0,
        'total_brutos': 0.0,
        'aportes_salud': 0.0,
        'aportes_pension': 0.0,
        'retencion': 0.0,
    })

    for m in movs:
        if m.formato_dian != '2276':
            continue
        nit = (m.nit or '').strip()
        if not nit:
            continue
        bucket = por_empleado[nit]
        base = (m.base_aplicable or '').lower()
        valor = float(m.valor or 0)

        if 'salario' in base or 'sueldo' in base:
            bucket['salarios'] += valor
        elif 'cesantia' in base and 'consig' in base:
            bucket['cesantias_consignadas'] += valor
        elif 'cesantia' in base:
            bucket['cesantias_pagadas'] += valor
        elif 'honorario' in base:
            bucket['honorarios'] += valor
        elif 'salud' in base:
            bucket['aportes_salud'] += valor
        elif 'pension' in base:
            bucket['aportes_pension'] += valor
        else:
            # Por defecto, contar como salario
            bucket['salarios'] += valor

        bucket['total_brutos'] += valor

    registros = []
    for nit, vals in por_empleado.items():
        t = terceros_dict.get(nit, {})
        # Retención de la fuente del empleado (de cuenta 236505/236510)
        ret = retenciones_por_nit.get(nit)
        retencion_fuente = float(
            getattr(ret, 'f2276_retencion_salarios', 0) or 0
        ) if ret else 0.0

        registros.append(RegistroF2276(
            entidad_informante=11,  # default: salarios
            tipo_doc_beneficiario=str(t.get('tipo_documento') or TIPO_DOC_CC).zfill(2),
            nit_beneficiario=nit,
            primer_apellido=t.get('primer_apellido') or '',
            segundo_apellido=t.get('segundo_apellido') or '',
            primer_nombre=t.get('primer_nombre') or '',
            otros_nombres=t.get('otros_nombres') or '',
            direccion=t.get('direccion') or '',
            codigo_departamento=t.get('codigo_dpto') or '',
            codigo_municipio=t.get('codigo_municipio') or '',
            codigo_pais=t.get('codigo_pais') or PAIS_COLOMBIA,
            pagos_salarios=vals['salarios'],
            pagos_honorarios=vals['honorarios'],
            cesantias_consignadas=vals['cesantias_consignadas'],
            cesantias_pagadas=vals['cesantias_pagadas'],
            total_ingresos_brutos=vals['total_brutos'],
            aportes_obligatorios_salud=vals['aportes_salud'],
            aportes_obligatorios_pension=vals['aportes_pension'],
            retencion_fuente=retencion_fuente,
            # ingreso_laboral_promedio_6m se podría calcular como total/12 * 0.5
            # pero requiere datos mensuales que no están en este flujo
            ingreso_laboral_promedio_6m=vals['total_brutos'] / 12 if vals['total_brutos'] > 0 else 0,
        ))

    return registros


# ================================================================
# API PRINCIPAL
# ================================================================

def construir_registros_v2(
    resultado: ResultadoClasificacion,
    terceros_dict: dict[str, dict],
) -> dict[str, list]:
    """
    Convierte un `ResultadoClasificacion` del motor a registros del v2.

    Args:
        resultado: ResultadoClasificacion (ya con PILA integrado si aplica).
        terceros_dict: {nit_str: {razon_social, primer_apellido, ..., codigo_dpto, ...}}
                       Tal como se guarda en exogena_terceros.

    Returns:
        dict {formato_str: [RegistroFXXXX...]} listo para `generar_lote_xmls`.

    Solo incluye formatos que tengan al menos 1 registro.
    """
    # Filtrar movimientos descartados
    movs = [
        m for m in resultado.movimientos
        if m.capa_resolucion not in ('sin_resolver', 'excluido_mayor_cerrado',
                                     'excluido_manual', 'excluido_conciliacion_6_72_73')
        and m.formato_dian  # tiene formato asignado
    ]

    retenciones = resultado.retenciones_por_nit or {}

    salida = {}

    # F1001 — Pagos a terceros (con retenciones 2365 asociadas)
    regs = _construir_f1001(movs, retenciones, terceros_dict)
    if regs:
        salida['1001'] = regs

    # F1003 — Retenciones que le practicaron
    regs = _construir_f1003(movs, terceros_dict)
    if regs:
        salida['1003'] = regs

    # F1005 — IVA descontable
    regs = _construir_f1005(movs, terceros_dict)
    if regs:
        salida['1005'] = regs

    # F1006 — IVA generado
    regs = _construir_f1006(movs, terceros_dict)
    if regs:
        salida['1006'] = regs

    # F1007 — Ingresos recibidos
    regs = _construir_f1007(movs, terceros_dict)
    if regs:
        salida['1007'] = regs

    # F1008 — CxC al 31-Dic
    regs = _construir_saldos_por_nit_concepto(movs, '1008', RegistroF1008, terceros_dict)
    if regs:
        salida['1008'] = regs

    # F1009 — CxP al 31-Dic
    regs = _construir_saldos_por_nit_concepto(movs, '1009', RegistroF1009, terceros_dict)
    if regs:
        salida['1009'] = regs

    # F1011 — Declaraciones tributarias (agregado)
    regs = _construir_f1011(movs)
    if regs:
        salida['1011'] = regs

    # F1012 — Saldos bancarios / declaraciones con tercero
    regs = _construir_f1012(movs, terceros_dict)
    if regs:
        salida['1012'] = regs

    # F1647 — Ingresos para terceros (stub)
    regs = _construir_f1647(movs, terceros_dict)
    if regs:
        salida['1647'] = regs

    # F2276 — Rentas de trabajo
    regs = _construir_f2276(movs, retenciones, terceros_dict)
    if regs:
        salida['2276'] = regs

    return salida
