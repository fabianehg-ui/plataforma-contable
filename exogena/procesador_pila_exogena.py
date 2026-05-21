"""
Procesador PILA para Información Exógena.

Recibe los datos parseados por core/lectores/lector_pila_xls.py y:
  1. Los persiste en las tablas exogena_pila_planillas, exogena_pila_movimientos,
     exogena_pila_cesantias, exogena_pila_cesantias_empleados.
  2. Provee funciones para construir las líneas F1001, F1009 y F2276 a partir
     de los datos guardados.

Conceptos DIAN F1001 según Resolución 000227 de 2025:
  - 5010: Aportes parafiscales (SENA + Cajas + ICBF)
  - 5011: Aportes a EPS y ARL (empleador + trabajador)
  - 5012: Aportes obligatorios a Fondos de Pensiones (empleador + trabajador)
  - 5016: Demás costos y deducciones (cesantías consignadas al fondo)

Conceptos DIAN F1009 (saldos cuentas por pagar al 31-dic):
  - 2204: Cesantías consolidadas (cuenta PUC 2510)
  - 2214: Aportes a seg.social y parafiscales por pagar (cuentas 237xxx)
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from core.lectores.lector_pila_xls import (
    ResultadoLecturaPilaXls,
    InformeCesantias,
    PlanillaPila,
)


# ============================================================
# Conceptos DIAN
# ============================================================
CONCEPTOS_F1001_PILA = {
    5010: 'Aportes parafiscales (SENA + Cajas + ICBF)',
    5011: 'Aportes a EPS y ARL',
    5012: 'Aportes obligatorios a Fondos de Pensiones',
    5016: 'Demás costos y deducciones (cesantías al fondo)',
}

CONCEPTOS_F1009_PILA = {
    2204: 'Cesantías consolidadas',
    2214: 'Aportes seg.social y parafiscales por pagar',
}


# ============================================================
# Persistencia en Supabase
# ============================================================

def guardar_planillas_pila(
    supabase,
    empresa_id: str,
    año_gravable: int,
    resultado: ResultadoLecturaPilaXls,
    reemplazar_periodos: bool = True,
) -> dict:
    """Guarda las planillas leídas en exogena_pila_planillas y _movimientos.

    Args:
        supabase: cliente Supabase
        empresa_id: UUID de la empresa
        año_gravable: año donde se reporta
        resultado: salida de leer_xls_suaporte()
        reemplazar_periodos: si True, borra planillas con los mismos números_planilla
                             y períodos antes de insertar. Evita duplicados.

    Returns:
        dict con planillas_insertadas, movimientos_insertados, errores
    """
    info = {
        'planillas_insertadas': 0,
        'movimientos_insertados': 0,
        'periodos_reemplazados': [],
        'errores': [],
    }

    if not resultado.planillas:
        info['errores'].append("No hay planillas para guardar")
        return info

    if reemplazar_periodos:
        # Borrar planillas con los mismos números de planilla del año
        numeros = [p.numero_planilla for p in resultado.planillas]
        try:
            # Primero obtener los IDs de las planillas a borrar (los movimientos
            # caen en cascada por la FK ON DELETE CASCADE)
            existentes = supabase.table('exogena_pila_planillas') \
                .select('id, numero_planilla') \
                .eq('empresa_id', empresa_id) \
                .eq('año_gravable', año_gravable) \
                .in_('numero_planilla', numeros) \
                .execute()
            if existentes.data:
                ids_a_borrar = [p['id'] for p in existentes.data]
                supabase.table('exogena_pila_planillas') \
                    .delete() \
                    .in_('id', ids_a_borrar) \
                    .execute()
                info['periodos_reemplazados'] = [p['numero_planilla'] for p in existentes.data]
        except Exception as e:
            info['errores'].append(f"Error limpiando planillas previas: {e}")

    # Insertar cada planilla y sus movimientos
    for planilla in resultado.planillas:
        try:
            # 1) Insertar planilla
            row_planilla = {
                'empresa_id': empresa_id,
                'año_gravable': año_gravable,
                'numero_planilla': planilla.numero_planilla,
                'operador': resultado.operador,
                'fecha_pago': planilla.fecha_pago or None,
                'periodo_cot': planilla.periodo_cot,
                'tipo_planilla': planilla.tipo_planilla,
                'afiliados': planilla.afiliados,
                'total_pagado': float(planilla.total_pagado),
                'archivo_origen': resultado.archivo_origen,
            }
            resp = supabase.table('exogena_pila_planillas').insert(row_planilla).execute()
            if not resp.data:
                info['errores'].append(f"No se pudo insertar planilla {planilla.numero_planilla}")
                continue
            planilla_id = resp.data[0]['id']
            info['planillas_insertadas'] += 1

            # 2) Insertar movimientos en bulk
            rows_mov = []
            for m in planilla.movimientos:
                rows_mov.append({
                    'planilla_id': planilla_id,
                    'empresa_id': empresa_id,
                    'año_gravable': año_gravable,
                    'fondo_tipo': m.fondo_tipo,
                    'fondo_nit': m.fondo_nit,
                    'fondo_nombre': m.fondo_nombre,
                    'fondo_codigo': m.fondo_codigo,
                    'concepto_dian': str(m.concepto_dian),
                    'ibc': float(m.ibc),
                    'valor_empleador': float(m.valor_empleador),
                    'valor_trabajador': float(m.valor_trabajador),
                    'total_obligatorio': float(m.total_obligatorio),
                })
            if rows_mov:
                supabase.table('exogena_pila_movimientos').insert(rows_mov).execute()
                info['movimientos_insertados'] += len(rows_mov)
        except Exception as e:
            info['errores'].append(f"Error con planilla {planilla.numero_planilla}: {e}")

    return info


def guardar_cesantias(
    supabase,
    empresa_id: str,
    año_gravable: int,
    año_causado: int,
    es_pasivo: bool,
    informe: InformeCesantias,
) -> dict:
    """Guarda un informe de cesantías al fondo.

    Args:
        empresa_id: UUID empresa
        año_gravable: año donde se reporta (ej. 2025)
        año_causado: año al que corresponden las cesantías
        es_pasivo: True si va al F1009 (pasivo 31-dic),
                   False si va al F1001+F2276 (pagadas durante el año)
        informe: salida de leer_xls_informe_cesantias()
    """
    info = {
        'cesantia_id': None,
        'empleados_insertados': 0,
        'errores': [],
    }

    if not informe.empleados or informe.total == 0:
        info['errores'].append("Informe sin empleados o total cero")
        return info

    # Borrar cesantías existentes con misma combinación (UNIQUE constraint)
    try:
        supabase.table('exogena_pila_cesantias') \
            .delete() \
            .eq('empresa_id', empresa_id) \
            .eq('año_gravable', año_gravable) \
            .eq('año_causado', año_causado) \
            .eq('es_pasivo', es_pasivo) \
            .execute()
    except Exception:
        pass  # No existía, está bien

    # Insertar cesantía
    try:
        row = {
            'empresa_id': empresa_id,
            'año_gravable': año_gravable,
            'año_causado': año_causado,
            'es_pasivo': es_pasivo,
            'fecha_pago': informe.fecha_pago or None,
            'fondo_nit': informe.fondo_nit,
            'fondo_nombre': informe.fondo_nombre,
            'numero_planilla': informe.numero_planilla,
            'total': float(informe.total),
            'archivo_origen': informe.archivo_origen,
        }
        resp = supabase.table('exogena_pila_cesantias').insert(row).execute()
        if not resp.data:
            info['errores'].append("No se pudo insertar el encabezado de cesantías")
            return info
        cesantia_id = resp.data[0]['id']
        info['cesantia_id'] = cesantia_id

        # Insertar empleados
        rows_emp = []
        for e in informe.empleados:
            rows_emp.append({
                'cesantia_id': cesantia_id,
                'tipo_doc': e.tipo_doc,
                'documento': e.documento,
                'apellidos': e.apellidos,
                'nombres': e.nombres,
                'dias_base': e.dias_base,
                'salario_base': float(e.salario_base),
                'cesantia': float(e.cesantia),
            })
        if rows_emp:
            supabase.table('exogena_pila_cesantias_empleados').insert(rows_emp).execute()
            info['empleados_insertados'] = len(rows_emp)
    except Exception as e:
        info['errores'].append(f"Error guardando cesantías: {e}")

    return info


# ============================================================
# Lectura desde Supabase (para construir borradores)
# ============================================================

def obtener_planillas_pila(supabase, empresa_id: str, año_gravable: int) -> list[dict]:
    """Devuelve todas las planillas PILA del año."""
    resp = supabase.table('exogena_pila_planillas') \
        .select('*') \
        .eq('empresa_id', empresa_id) \
        .eq('año_gravable', año_gravable) \
        .order('fecha_pago') \
        .execute()
    return resp.data or []


def obtener_movimientos_pila(
    supabase,
    empresa_id: str,
    año_gravable: int,
    excluir_periodo: Optional[str] = None,
) -> list[dict]:
    """Devuelve los movimientos PILA. Si excluir_periodo se especifica, los excluye.

    Args:
        excluir_periodo: ej '202512' para no contar el pasivo en el F1001 normal
    """
    q = supabase.table('exogena_pila_movimientos') \
        .select('*, exogena_pila_planillas!inner(periodo_cot)') \
        .eq('empresa_id', empresa_id) \
        .eq('año_gravable', año_gravable)
    resp = q.execute()
    if not resp.data:
        return []
    if excluir_periodo:
        return [
            m for m in resp.data
            if m.get('exogena_pila_planillas', {}).get('periodo_cot') != excluir_periodo
        ]
    return resp.data


def obtener_cesantias(
    supabase,
    empresa_id: str,
    año_gravable: int,
    es_pasivo: Optional[bool] = None,
) -> list[dict]:
    """Devuelve las cesantías del año, filtrando por tipo si se indica."""
    q = supabase.table('exogena_pila_cesantias') \
        .select('*, exogena_pila_cesantias_empleados(*)') \
        .eq('empresa_id', empresa_id) \
        .eq('año_gravable', año_gravable)
    if es_pasivo is not None:
        q = q.eq('es_pasivo', es_pasivo)
    return q.execute().data or []


# ============================================================
# Agregaciones para construir el borrador DIAN
# ============================================================

@dataclass
class LineaF1001:
    concepto: int
    nit: str
    nombre: str
    valor: Decimal


@dataclass
class LineaF1009:
    concepto: int
    nit: str
    nombre: str
    valor: Decimal


@dataclass
class LineaF2276Cesantia:
    """Línea para F2276 columna 'Pagos por concepto de cesantías e intereses'."""
    tipo_doc: str
    documento: str
    apellidos: str
    nombres: str
    cesantia: Decimal


def agregar_f1001_aportes(supabase, empresa_id: str, año_gravable: int) -> list[LineaF1001]:
    """Construye líneas F1001 conceptos 5010, 5011, 5012 desde PILA.

    Excluye automáticamente la planilla con periodo_cot == '{año}12'
    (que corresponde al pasivo al 31-dic y va al F1009 2214).
    """
    periodo_pasivo = f'{año_gravable}12'
    movs = obtener_movimientos_pila(supabase, empresa_id, año_gravable, excluir_periodo=periodo_pasivo)

    agg: dict[tuple[int, str], dict] = {}
    for m in movs:
        cpto = int(m['concepto_dian'])
        nit = m['fondo_nit']
        key = (cpto, nit)
        if key not in agg:
            agg[key] = {
                'concepto': cpto,
                'nit': nit,
                'nombre': m['fondo_nombre'],
                'valor': Decimal('0'),
            }
        agg[key]['valor'] += Decimal(str(m['total_obligatorio']))

    return [LineaF1001(**v) for v in agg.values()]


def agregar_f1001_cesantias(supabase, empresa_id: str, año_gravable: int) -> list[LineaF1001]:
    """Construye líneas F1001 concepto 5016 (cesantías al fondo durante el año)."""
    cesantias = obtener_cesantias(supabase, empresa_id, año_gravable, es_pasivo=False)
    lineas = []
    for c in cesantias:
        lineas.append(LineaF1001(
            concepto=5016,
            nit=c['fondo_nit'],
            nombre=c['fondo_nombre'],
            valor=Decimal(str(c['total'])),
        ))
    return lineas


def agregar_f1009_2214(supabase, empresa_id: str, año_gravable: int) -> list[LineaF1009]:
    """Construye líneas F1009 concepto 2214 (pasivo aportes SS al 31-dic).

    Toma SOLO la planilla con periodo_cot == '{año}12'.
    """
    periodo = f'{año_gravable}12'
    resp = supabase.table('exogena_pila_movimientos') \
        .select('*, exogena_pila_planillas!inner(periodo_cot)') \
        .eq('empresa_id', empresa_id) \
        .eq('año_gravable', año_gravable) \
        .execute()
    movs = [
        m for m in (resp.data or [])
        if m.get('exogena_pila_planillas', {}).get('periodo_cot') == periodo
    ]
    agg: dict[str, dict] = {}
    for m in movs:
        nit = m['fondo_nit']
        if nit not in agg:
            agg[nit] = {
                'concepto': 2214,
                'nit': nit,
                'nombre': m['fondo_nombre'],
                'valor': Decimal('0'),
            }
        agg[nit]['valor'] += Decimal(str(m['total_obligatorio']))
    return [LineaF1009(**v) for v in agg.values()]


def agregar_f1009_2204(supabase, empresa_id: str, año_gravable: int) -> list[LineaF1009]:
    """Construye líneas F1009 concepto 2204 (cesantías consolidadas al 31-dic)."""
    cesantias = obtener_cesantias(supabase, empresa_id, año_gravable, es_pasivo=True)
    lineas = []
    for c in cesantias:
        lineas.append(LineaF1009(
            concepto=2204,
            nit=c['fondo_nit'],
            nombre=c['fondo_nombre'],
            valor=Decimal(str(c['total'])),
        ))
    return lineas


def agregar_f2276_cesantias(supabase, empresa_id: str, año_gravable: int) -> list[LineaF2276Cesantia]:
    """Devuelve detalle por empleado de cesantías pagadas (es_pasivo=FALSE)."""
    cesantias = obtener_cesantias(supabase, empresa_id, año_gravable, es_pasivo=False)
    lineas = []
    for c in cesantias:
        for e in c.get('exogena_pila_cesantias_empleados', []):
            lineas.append(LineaF2276Cesantia(
                tipo_doc=e['tipo_doc'],
                documento=e['documento'],
                apellidos=e['apellidos'],
                nombres=e['nombres'],
                cesantia=Decimal(str(e['cesantia'])),
            ))
    return lineas


# ============================================================
# Resumen ejecutivo para UI
# ============================================================

def construir_resumen_pila(supabase, empresa_id: str, año_gravable: int) -> dict:
    """Devuelve un dict resumen para la UI."""
    f1001_aportes = agregar_f1001_aportes(supabase, empresa_id, año_gravable)
    f1001_cesantias = agregar_f1001_cesantias(supabase, empresa_id, año_gravable)
    f1009_2214 = agregar_f1009_2214(supabase, empresa_id, año_gravable)
    f1009_2204 = agregar_f1009_2204(supabase, empresa_id, año_gravable)
    f2276 = agregar_f2276_cesantias(supabase, empresa_id, año_gravable)

    total_5010 = sum((l.valor for l in f1001_aportes if l.concepto == 5010), Decimal('0'))
    total_5011 = sum((l.valor for l in f1001_aportes if l.concepto == 5011), Decimal('0'))
    total_5012 = sum((l.valor for l in f1001_aportes if l.concepto == 5012), Decimal('0'))
    total_5016 = sum((l.valor for l in f1001_cesantias), Decimal('0'))
    total_2214 = sum((l.valor for l in f1009_2214), Decimal('0'))
    total_2204 = sum((l.valor for l in f1009_2204), Decimal('0'))

    return {
        'f1001': {
            '5010': {'total': total_5010, 'lineas': [l for l in f1001_aportes if l.concepto == 5010]},
            '5011': {'total': total_5011, 'lineas': [l for l in f1001_aportes if l.concepto == 5011]},
            '5012': {'total': total_5012, 'lineas': [l for l in f1001_aportes if l.concepto == 5012]},
            '5016': {'total': total_5016, 'lineas': f1001_cesantias},
        },
        'f1009': {
            '2214': {'total': total_2214, 'lineas': f1009_2214},
            '2204': {'total': total_2204, 'lineas': f1009_2204},
        },
        'f2276': {
            'total': sum((l.cesantia for l in f2276), Decimal('0')),
            'empleados': f2276,
        },
        'totales_generales': {
            'f1001_aportes': total_5010 + total_5011 + total_5012,
            'f1001_cesantias': total_5016,
            'f1001_total': total_5010 + total_5011 + total_5012 + total_5016,
            'f1009_total': total_2214 + total_2204,
            'f2276_total': sum((l.cesantia for l in f2276), Decimal('0')),
        },
    }
