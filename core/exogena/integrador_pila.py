"""
Integrador PILA → Motor de Clasificación.

Toma el ResultadoClasificacion del motor (después de procesar el balance) y:
  1. Agrega líneas F1001 5010/5011/5012 desde exogena_pila_movimientos
     (excluyendo cot del mes 12, que es el pasivo).
  2. Agrega línea F1001 5016 = total cesantías al fondo pagadas en el año.
  3. Agrega líneas F1009 2214 desde exogena_pila_movimientos cot mes 12.
  4. Reagrupa el F1009 2214 de cesantías al NIT del fondo (Protección).
  5. Agrega F2276 cesantías por empleado.
  6. EXCLUYE del resultado las cuentas que ya son representadas por PILA:
       - 25500502/25500602/25502002 (aportes pagados, ya cubiertos por F1001 5010/5011/5012)
       - 25501002 (parafiscales pagados)
       - 237xxx (aportes por pagar, ya cubiertos por F1009 2214)
       - 251010 cesantías consolidadas (se reagrupa al NIT del fondo)

Uso típico:
    from core.exogena.motor_clasificacion import MotorClasificacion
    from core.exogena.integrador_pila import integrar_pila_en_resultado
    
    res = motor.clasificar_balance(movimientos)
    res = integrar_pila_en_resultado(res, supabase, empresa_id, año_gravable)
    # res ahora tiene los registros PILA mezclados y los duplicados excluidos
"""
from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from core.exogena.motor_clasificacion import (
    MovimientoClasificado,
    ResultadoClasificacion,
)


# ============================================================
# Cuentas del balance que son REEMPLAZADAS por datos PILA
# ============================================================
# Cuando PILA está cargada para el año, estas cuentas se excluyen del
# resultado del motor para evitar doble-conteo, porque PILA reporta
# los mismos valores con mayor detalle (NIT real del fondo).
# ============================================================

CUENTAS_F1001_REEMPLAZADAS_POR_PILA = {
    # Aportes PAGADOS (cuentas 2550x — al fondo)
    '25500502',  # EPS empleador → reemplazado por PILA F1001 5011
    '25500602',  # ARL → reemplazado por PILA F1001 5011
    '25501002',  # Cajas/SENA/ICBF → reemplazado por PILA F1001 5010
    '25502002',  # Pensión → reemplazado por PILA F1001 5012
}

CUENTAS_F1009_REEMPLAZADAS_POR_PILA = {
    # Aportes POR PAGAR (cuentas 237xxx) — reemplazadas por PILA cot dic
    '237005', '237006', '237010', '237025', '237030', '237035',
    # Cesantías consolidadas — se reagrupan al NIT del fondo
    '251010',
}

# Para excluir por prefijo también
PREFIJOS_F1009_REEMPLAZADOS = ('237',)


# ============================================================
# Funciones de lectura desde Supabase
# ============================================================

def _obtener_movimientos_pila(supabase, empresa_id: str, año_gravable: int) -> list[dict]:
    """Devuelve todos los movimientos PILA del año con info de la planilla."""
    try:
        resp = supabase.table('exogena_pila_movimientos') \
            .select('*, exogena_pila_planillas!inner(periodo_cot, fecha_pago, numero_planilla)') \
            .eq('empresa_id', empresa_id) \
            .eq('año_gravable', año_gravable) \
            .execute()
        return resp.data or []
    except Exception:
        return []


def _obtener_cesantias_pila(supabase, empresa_id: str, año_gravable: int) -> list[dict]:
    """Devuelve las cesantías PILA del año (incluye detalle de empleados)."""
    try:
        resp = supabase.table('exogena_pila_cesantias') \
            .select('*, exogena_pila_cesantias_empleados(*)') \
            .eq('empresa_id', empresa_id) \
            .eq('año_gravable', año_gravable) \
            .execute()
        return resp.data or []
    except Exception:
        return []


def hay_datos_pila(supabase, empresa_id: str, año_gravable: int) -> bool:
    """Indica si la empresa tiene datos PILA cargados para el año."""
    movs = _obtener_movimientos_pila(supabase, empresa_id, año_gravable)
    ces = _obtener_cesantias_pila(supabase, empresa_id, año_gravable)
    return bool(movs) or bool(ces)


# ============================================================
# Construcción de MovimientoClasificado desde datos PILA
# ============================================================

def _construir_lineas_f1001_aportes(movimientos_pila: list[dict], año_gravable: int) -> list[MovimientoClasificado]:
    """F1001 5010/5011/5012 — aportes pagados durante el año (excluye cot dic = pasivo)."""
    periodo_pasivo = f'{año_gravable}12'
    agg: dict[tuple[int, str], dict] = {}

    for m in movimientos_pila:
        periodo = m.get('exogena_pila_planillas', {}).get('periodo_cot', '')
        if periodo == periodo_pasivo:
            continue
        cpto = int(m['concepto_dian'])
        if cpto not in (5010, 5011, 5012):
            continue
        nit = m['fondo_nit']
        key = (cpto, nit)
        if key not in agg:
            agg[key] = {
                'concepto': cpto,
                'nit': nit,
                'nombre': m['fondo_nombre'],
                'valor': 0.0,
            }
        agg[key]['valor'] += float(m['total_obligatorio'])

    lineas = []
    for (cpto, nit), v in agg.items():
        lineas.append(MovimientoClasificado(
            codigo_cuenta=f'PILA_F1001_{cpto}',
            nit=nit,
            formato_dian='1001',
            concepto_dian=cpto,
            valor=v['valor'],
            base_aplicable='pila_aportes',
            capa_resolucion='pila_aportes',
            nota=f'PILA AG{año_gravable}: aportes pagados a {v["nombre"]} en el año',
        ))
    return lineas


def _construir_lineas_f1001_5016_cesantias(cesantias_pila: list[dict], año_gravable: int) -> list[MovimientoClasificado]:
    """F1001 5016 — cesantías consignadas al fondo durante el año (es_pasivo=False)."""
    lineas = []
    for c in cesantias_pila:
        if c.get('es_pasivo'):
            continue
        lineas.append(MovimientoClasificado(
            codigo_cuenta=f'PILA_F1001_5016_CES{c["año_causado"]}',
            nit=c['fondo_nit'],
            formato_dian='1001',
            concepto_dian=5016,
            valor=float(c['total']),
            base_aplicable='pila_cesantias',
            capa_resolucion='pila_cesantias',
            nota=f'PILA AG{año_gravable}: cesantías {c["año_causado"]} consignadas al fondo {c["fondo_nombre"]} el {c.get("fecha_pago", "?")}',
        ))
    return lineas


def _construir_lineas_f1009_2214(
    movimientos_pila: list[dict],
    cesantias_pila: list[dict],
    año_gravable: int,
) -> list[MovimientoClasificado]:
    """F1009 2214 — pasivo aportes SS (cot dic) + cesantías consolidadas al NIT del fondo.

    Según Res. 000227/2025 art. 1.3.5.6.1 §4, el concepto 2214 cubre tanto
    aportes parafiscales/salud/pensión COMO cesantías. Doctrina mayoritaria
    AG2025 (Gerencie, Solución Integral): reportar al NIT del fondo.
    """
    periodo_pasivo = f'{año_gravable}12'
    lineas = []

    # 1) Aportes SS pendientes (cot diciembre)
    for m in movimientos_pila:
        periodo = m.get('exogena_pila_planillas', {}).get('periodo_cot', '')
        if periodo != periodo_pasivo:
            continue
        lineas.append(MovimientoClasificado(
            codigo_cuenta=f'PILA_F1009_2214_AP',
            nit=m['fondo_nit'],
            formato_dian='1009',
            concepto_dian=2214,
            valor=float(m['total_obligatorio']),
            base_aplicable='pila_pasivo_aportes',
            capa_resolucion='pila_pasivo_aportes',
            nota=f'PILA AG{año_gravable}: pasivo aporte {m["fondo_tipo"]} {m["fondo_nombre"]} cot {periodo}',
        ))

    # 2) Cesantías consolidadas al 31-dic (es_pasivo=True), agrupadas al NIT del fondo
    for c in cesantias_pila:
        if not c.get('es_pasivo'):
            continue
        lineas.append(MovimientoClasificado(
            codigo_cuenta=f'PILA_F1009_2214_CES',
            nit=c['fondo_nit'],
            formato_dian='1009',
            concepto_dian=2214,
            valor=float(c['total']),
            base_aplicable='pila_pasivo_cesantias',
            capa_resolucion='pila_pasivo_cesantias',
            nota=f'PILA AG{año_gravable}: cesantías {c["año_causado"]} consolidadas al fondo {c["fondo_nombre"]} (Res. 227/25 §4)',
        ))

    return lineas


def _construir_lineas_f2276_cesantias(cesantias_pila: list[dict], año_gravable: int) -> list[MovimientoClasificado]:
    """F2276 — cesantías individualizadas por empleado (las pagadas, no las consolidadas)."""
    lineas = []
    for c in cesantias_pila:
        if c.get('es_pasivo'):
            continue
        for emp in c.get('exogena_pila_cesantias_empleados', []):
            # Construir NIT del empleado
            nit_emp = emp['documento']
            # Para F2276, el "concepto_dian" no es como en F1001; el motor del XML
            # usa columnas específicas. Aquí ponemos un identificador que el
            # generador_xml debe interpretar como "cesantía e intereses".
            lineas.append(MovimientoClasificado(
                codigo_cuenta=f'PILA_F2276_CES_{emp["tipo_doc"]}{nit_emp}',
                nit=nit_emp,
                formato_dian='2276',
                concepto_dian=None,  # F2276 no usa concepto numérico, son columnas
                valor=float(emp['cesantia']),
                base_aplicable='pila_f2276_cesantia',
                capa_resolucion='pila_f2276_cesantia',
                nota=f'PILA AG{año_gravable}: cesantía {emp["apellidos"]} {emp["nombres"]} año causado {c["año_causado"]}',
            ))
    return lineas


# ============================================================
# Filtrado de movimientos REEMPLAZADOS por PILA
# ============================================================

def _es_movimiento_reemplazado_por_pila(mov: MovimientoClasificado) -> bool:
    """True si este movimiento del balance debe excluirse por estar cubierto por PILA."""
    cuenta = mov.codigo_cuenta

    # No filtramos las propias líneas PILA
    if cuenta.startswith('PILA_'):
        return False

    if mov.formato_dian == '1001':
        if cuenta in CUENTAS_F1001_REEMPLAZADAS_POR_PILA:
            return True

    if mov.formato_dian == '1009':
        if cuenta in CUENTAS_F1009_REEMPLAZADAS_POR_PILA:
            return True
        for prefix in PREFIJOS_F1009_REEMPLAZADOS:
            if cuenta.startswith(prefix):
                return True

    return False


# ============================================================
# API principal
# ============================================================

@dataclass
class ResumenIntegracionPila:
    """Resumen de qué se hizo al integrar PILA."""
    pila_disponible: bool = False
    lineas_agregadas_f1001: int = 0
    lineas_agregadas_f1009: int = 0
    lineas_agregadas_f2276: int = 0
    valor_agregado_f1001: float = 0.0
    valor_agregado_f1009: float = 0.0
    valor_agregado_f2276: float = 0.0
    movimientos_excluidos: int = 0
    valor_excluido: float = 0.0
    detalles_exclusion: list = field(default_factory=list)


def integrar_pila_en_resultado(
    resultado: ResultadoClasificacion,
    supabase,
    empresa_id: str,
    año_gravable: int,
) -> tuple[ResultadoClasificacion, ResumenIntegracionPila]:
    """Integra los datos PILA en el resultado del motor.

    Pasos:
      1. Verifica si hay datos PILA cargados. Si no, devuelve resultado sin tocar.
      2. Construye las líneas F1001/F1009/F2276 desde PILA.
      3. EXCLUYE los movimientos del balance que serían duplicados.
      4. Mezcla todo en un nuevo ResultadoClasificacion.

    Returns:
        (resultado_actualizado, resumen)
    """
    resumen = ResumenIntegracionPila()

    movs_pila = _obtener_movimientos_pila(supabase, empresa_id, año_gravable)
    ces_pila = _obtener_cesantias_pila(supabase, empresa_id, año_gravable)

    if not movs_pila and not ces_pila:
        return resultado, resumen

    resumen.pila_disponible = True

    # 1) Construir líneas PILA
    lineas_f1001_aportes = _construir_lineas_f1001_aportes(movs_pila, año_gravable)
    lineas_f1001_5016 = _construir_lineas_f1001_5016_cesantias(ces_pila, año_gravable)
    lineas_f1009_2214 = _construir_lineas_f1009_2214(movs_pila, ces_pila, año_gravable)
    lineas_f2276 = _construir_lineas_f2276_cesantias(ces_pila, año_gravable)

    todas_pila = lineas_f1001_aportes + lineas_f1001_5016 + lineas_f1009_2214 + lineas_f2276

    resumen.lineas_agregadas_f1001 = len(lineas_f1001_aportes) + len(lineas_f1001_5016)
    resumen.lineas_agregadas_f1009 = len(lineas_f1009_2214)
    resumen.lineas_agregadas_f2276 = len(lineas_f2276)
    resumen.valor_agregado_f1001 = sum(l.valor for l in (lineas_f1001_aportes + lineas_f1001_5016))
    resumen.valor_agregado_f1009 = sum(l.valor for l in lineas_f1009_2214)
    resumen.valor_agregado_f2276 = sum(l.valor for l in lineas_f2276)

    # 2) Filtrar movimientos del motor que serían duplicados
    movimientos_filtrados = []
    for m in resultado.movimientos:
        if _es_movimiento_reemplazado_por_pila(m):
            resumen.movimientos_excluidos += 1
            resumen.valor_excluido += abs(m.valor)
            resumen.detalles_exclusion.append({
                'cuenta': m.codigo_cuenta,
                'nit': m.nit,
                'formato': m.formato_dian,
                'concepto': m.concepto_dian,
                'valor': m.valor,
            })
            continue
        movimientos_filtrados.append(m)

    # 3) Crear nuevo resultado mezclado
    nuevo_resultado = ResultadoClasificacion(
        movimientos=movimientos_filtrados + todas_pila,
        sin_resolver=resultado.sin_resolver,
        estadisticas=dict(resultado.estadisticas),
        conciliacion_costos=resultado.conciliacion_costos,
        retenciones_por_nit=resultado.retenciones_por_nit,
    )
    nuevo_resultado.estadisticas['pila_lineas_agregadas'] = (
        resumen.lineas_agregadas_f1001 + resumen.lineas_agregadas_f1009 + resumen.lineas_agregadas_f2276
    )
    nuevo_resultado.estadisticas['pila_movimientos_excluidos'] = resumen.movimientos_excluidos

    return nuevo_resultado, resumen


# ============================================================
# CLI de prueba
# ============================================================

if __name__ == '__main__':
    print("Integrador PILA — módulo de utilidad, no se ejecuta directamente.")
    print("Uso: from core.exogena.integrador_pila import integrar_pila_en_resultado")
