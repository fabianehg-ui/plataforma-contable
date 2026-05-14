"""
Conciliación Enriquecida — Información Exógena
================================================

Construye una vista detallada de la conciliación entre el balance auxiliar
y los valores reportados en cada formato/concepto del XML generado.

Para cada combinación (formato, concepto) muestra:
    - Lista de cuentas del balance que aportan a ese concepto
    - Saldo de cada cuenta del balance
    - Valor reportado al concepto en el XML
    - Diferencia entre uno y otro
    - Razón de la diferencia (cuenta excluida, cuenta transitoria,
      override, etc.)

Esta es la herramienta clave para que el contador valide que el reporte
está cuadrado y entienda CADA peso que hay en cada concepto.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Any


# ============================================================================
# Modelos
# ============================================================================

@dataclass
class CuentaConciliacion:
    """Una cuenta del balance que aporta a un concepto específico."""
    codigo_cuenta: str
    nombre_cuenta: str
    saldo_balance: Decimal           # Saldo o movimiento del balance auxiliar
    valor_reportado: Decimal         # Lo que efectivamente fue al XML
    diferencia: Decimal              # saldo - reportado
    capa_origen: int                 # 1, 2 o 3 (qué capa asignó la regla)
    capa_nombre: str                 # 'Global', 'Mapeo nativo', 'Override empresa'
    excluida: bool = False
    motivo_diferencia: Optional[str] = None
    nits_distintos: int = 0          # Cuántos NITs aportan a esta cuenta


@dataclass
class ConciliacionConcepto:
    """Bloque de conciliación de un (formato, concepto)."""
    formato_dian: str
    concepto_dian: int
    descripcion_concepto: str

    # Cuentas que aportan a este concepto
    cuentas: list[CuentaConciliacion] = field(default_factory=list)

    # Totales (calculados a partir de cuentas)
    total_balance: Decimal = Decimal('0')
    total_reportado: Decimal = Decimal('0')
    diferencia: Decimal = Decimal('0')

    # Estado y explicaciones
    estado: str = 'pendiente'        # 'cuadrado' | 'diferencia_explicada' | 'pendiente' | 'inconsistente'
    explicaciones: list[str] = field(default_factory=list)

    def calcular_totales(self):
        """Recalcula los totales a partir de la lista de cuentas."""
        self.total_balance = sum((c.saldo_balance for c in self.cuentas), Decimal('0'))
        self.total_reportado = sum((c.valor_reportado for c in self.cuentas), Decimal('0'))
        self.diferencia = self.total_balance - self.total_reportado

        # Determinar estado
        if abs(self.diferencia) < Decimal('1'):  # Tolerancia de $1
            self.estado = 'cuadrado'
        elif all(c.motivo_diferencia for c in self.cuentas if c.diferencia != 0):
            # Toda diferencia tiene explicación
            self.estado = 'diferencia_explicada'
        else:
            self.estado = 'pendiente'


@dataclass
class DictamenConciliacion:
    """Dictamen completo: lista de bloques por (formato, concepto)."""
    año_gravable: int
    empresa_id: str
    bloques: list[ConciliacionConcepto] = field(default_factory=list)

    # Resumen ejecutivo
    total_conceptos: int = 0
    conceptos_cuadrados: int = 0
    conceptos_con_diferencia_explicada: int = 0
    conceptos_pendientes: int = 0

    def calcular_resumen(self):
        self.total_conceptos = len(self.bloques)
        self.conceptos_cuadrados = sum(1 for b in self.bloques if b.estado == 'cuadrado')
        self.conceptos_con_diferencia_explicada = sum(
            1 for b in self.bloques if b.estado == 'diferencia_explicada'
        )
        self.conceptos_pendientes = sum(
            1 for b in self.bloques if b.estado == 'pendiente'
        )


# ============================================================================
# Construcción del dictamen
# ============================================================================

def construir_conciliacion_enriquecida(
    sb,
    empresa_id: str,
    año_gravable: int = 2025,
) -> DictamenConciliacion:
    """
    Construye el dictamen completo.

    Pasos:
        1. Resuelve el periodo_id a partir de (empresa_id, año_gravable)
        2. Lee balance crudo desde exogena_balance (cuentas + saldos + nits)
        3. Lee reglas de las 3 capas y clasifica los movimientos en memoria
        4. Agrupa por (formato, concepto) y dentro de eso por cuenta
        5. Calcula totales, diferencias y motivos por bloque
    """
    dictamen = DictamenConciliacion(
        año_gravable=año_gravable,
        empresa_id=empresa_id,
    )

    # 1. Resolver periodo_id (la tabla exogena_movimientos_clasificados / balance
    #    NO tienen empresa_id ni año_gravable; viven detrás de periodo_id).
    periodo_resp = sb.table('exogena_periodos') \
        .select('id') \
        .eq('empresa_id', empresa_id) \
        .eq('año_gravable', año_gravable) \
        .limit(1) \
        .execute()
    if not periodo_resp.data:
        # No hay periodo creado todavía → dictamen vacío
        dictamen.calcular_resumen()
        return dictamen
    periodo_id = periodo_resp.data[0]['id']

    # 2. Leer balance crudo (no totalizadores) — esta tabla SÍ existe poblada.
    bal_resp = sb.table('exogena_balance') \
        .select('codigo_cuenta,nombre_cuenta,nit,nombre_tercero,'
                'debitos,creditos,saldo_final') \
        .eq('periodo_id', periodo_id) \
        .eq('es_totalizador', False) \
        .execute()
    bal_rows = bal_resp.data or []
    if not bal_rows:
        dictamen.calcular_resumen()
        return dictamen

    # 3. Cargar reglas de las 3 capas y clasificar en memoria.
    #    Se hace import diferido para evitar ciclos.
    from core.exogena.motor_clasificacion import (
        MotorClasificacion, Movimiento,
        ReglaCapa1, ReglaCapa2, ReglaCapa3,
    )

    capa1_data = sb.table('exogena_puc_generico').select('*').eq(
        'año_gravable', año_gravable
    ).eq('activo', True).execute().data or []
    capa2_data = sb.table('exogena_mapeo_empresa').select('*').eq(
        'empresa_id', empresa_id
    ).eq('año_gravable', año_gravable).eq('activo', True).execute().data or []
    capa3_data = sb.table('exogena_mapeo_manual').select('*').eq(
        'empresa_id', empresa_id
    ).eq('año_gravable', año_gravable).execute().data or []

    reglas_c1 = [ReglaCapa1(
        codigo_cuenta=r['codigo_cuenta'],
        formato_dian=r['formato_dian'],
        concepto_dian=r.get('concepto_dian'),
        nombre_cuenta=r.get('nombre_cuenta', ''),
    ) for r in capa1_data]
    reglas_c2 = [ReglaCapa2(
        formato_dian=r['formato_dian'],
        concepto_dian=r['concepto_dian'],
        cuenta_inicial=r['cuenta_inicial'],
        cuenta_final=r['cuenta_final'],
    ) for r in capa2_data]
    reglas_c3 = [ReglaCapa3(
        codigo_cuenta=r['codigo_cuenta'],
        nit=r.get('nit'),
        formato_dian=r.get('formato_dian'),
        concepto_dian=r.get('concepto_dian'),
        excluir=bool(r.get('excluir', False)),
        motivo_exclusion=r.get('motivo_exclusion'),
    ) for r in capa3_data]

    movimientos = [Movimiento(
        codigo_cuenta=b['codigo_cuenta'],
        nit=b.get('nit'),
        debitos=float(b.get('debitos', 0) or 0),
        creditos=float(b.get('creditos', 0) or 0),
        saldo_final=float(b.get('saldo_final', 0) or 0),
        nombre_cuenta=b.get('nombre_cuenta', '') or '',
        nombre_tercero=b.get('nombre_tercero', '') or '',
    ) for b in bal_rows]

    motor = MotorClasificacion(reglas_c1, reglas_c2, reglas_c3)
    resultado = motor.clasificar_balance(movimientos)

    # Index para recuperar metadatos del balance al armar la salida
    idx_bal = {(m.codigo_cuenta, m.nit): m for m in movimientos}

    # Mapa rápido capa3 (codigo, nit) → motivo de exclusión, si aplica
    motivos_c3 = {
        (r['codigo_cuenta'], r.get('nit')): r.get('motivo_exclusion')
        for r in capa3_data
    }

    # 4. Agrupar por (formato, concepto) y dentro de eso por cuenta
    grupos: dict[tuple[str, int], dict[str, Any]] = {}

    for mc in resultado.movimientos:
        if mc.capa_resolucion == 'sin_resolver':
            continue

        fmt = mc.formato_dian or '_SIN_FORMATO_'
        cpt = mc.concepto_dian or 0
        cod = mc.codigo_cuenta
        excl = bool(getattr(mc, 'excluido', False))

        # Capa numérica (1/2/3) a partir del string que devuelve el motor
        capa_num = {
            'capa1': 1, 'capa1_global': 1, 'global': 1,
            'capa2': 2, 'capa2_empresa': 2, 'mapeo_empresa': 2,
            'capa3': 3, 'capa3_manual': 3, 'manual': 3,
        }.get(str(mc.capa_resolucion).lower(), 0)

        mov_orig = idx_bal.get((cod, mc.nit))

        # saldo_balance siempre viene del balance real (puede ser negativo en pasivos).
        # Para reportar al XML, usamos lo que el motor decidió en `mc.valor`:
        #   - Para flujos normales (F1001, F1005, etc): mc.valor coincide con saldo_final
        #   - Para F2276 doble-reporte (cuentas 251010, 251505, 252501, 25500502, etc.):
        #     mc.valor son los DÉBITOS del año (lo efectivamente pagado al empleado),
        #     mientras que saldo_final puede ser un crédito residual (negativo en
        #     pasivos no completamente liquidados al cierre).
        #   - Para deducciones 25500x: mc.valor son los débitos (giros a EPS/Fondo).
        # La columna "valor reportado" debe reflejar lo que va al XML = mc.valor.
        saldo = Decimal(str(mov_orig.saldo_final if mov_orig else 0))
        valor_efectivo_reportado = Decimal(str(mc.valor or 0))

        key = (fmt, cpt)
        if key not in grupos:
            grupos[key] = {
                'descripcion': '',
                'cuentas_dict': {},
            }

        if cod not in grupos[key]['cuentas_dict']:
            grupos[key]['cuentas_dict'][cod] = {
                'codigo_cuenta': cod,
                'nombre_cuenta': (mov_orig.nombre_cuenta if mov_orig else ''),
                'saldo_balance': Decimal('0'),
                'valor_reportado': Decimal('0'),
                'capa_origen': capa_num,
                'capa_nombre': _capa_nombre(capa_num),
                'excluida': excl,
                'motivo': motivos_c3.get((cod, mc.nit)),
                'nits_set': set(),
            }

        cuenta = grupos[key]['cuentas_dict'][cod]
        cuenta['saldo_balance'] += saldo
        if not excl:
            # valor_reportado = lo que efectivamente fue al XML para esta línea
            # (mc.valor — diferente de saldo_final para F2276 doble-reporte y deducciones)
            cuenta['valor_reportado'] += valor_efectivo_reportado
        if mc.nit:
            cuenta['nits_set'].add(mc.nit)

    # 3. Construir bloques de conciliación
    for (fmt, cpt), info in grupos.items():
        if fmt == '_SIN_FORMATO_':
            continue  # Las cuentas sin formato son aparte (omitir)

        bloque = ConciliacionConcepto(
            formato_dian=fmt,
            concepto_dian=cpt,
            descripcion_concepto=info['descripcion'],
        )

        for cuenta_data in info['cuentas_dict'].values():
            saldo = cuenta_data['saldo_balance']
            reportado = cuenta_data['valor_reportado']

            cuenta_obj = CuentaConciliacion(
                codigo_cuenta=cuenta_data['codigo_cuenta'],
                nombre_cuenta=cuenta_data['nombre_cuenta'],
                saldo_balance=saldo,
                valor_reportado=reportado,
                diferencia=saldo - reportado,
                capa_origen=cuenta_data['capa_origen'],
                capa_nombre=cuenta_data['capa_nombre'],
                excluida=cuenta_data['excluida'],
                motivo_diferencia=cuenta_data['motivo'] if cuenta_data['excluida'] else None,
                nits_distintos=len(cuenta_data['nits_set']),
            )
            bloque.cuentas.append(cuenta_obj)

        # Ordenar cuentas por saldo descendente
        bloque.cuentas.sort(key=lambda c: c.saldo_balance, reverse=True)

        bloque.calcular_totales()

        # Generar explicaciones legibles
        for c in bloque.cuentas:
            if c.excluida:
                bloque.explicaciones.append(
                    f"• Cuenta {c.codigo_cuenta} ({c.nombre_cuenta}) excluida: "
                    f"{c.motivo_diferencia or 'sin motivo registrado'} "
                    f"(saldo balance ${c.saldo_balance:,.0f} no reportado)"
                )
            elif c.diferencia != 0:
                bloque.explicaciones.append(
                    f"• Cuenta {c.codigo_cuenta} ({c.nombre_cuenta}) tiene diferencia "
                    f"de ${c.diferencia:,.0f} entre balance y reportado — revisar"
                )

        dictamen.bloques.append(bloque)

    # Ordenar bloques por formato y concepto
    dictamen.bloques.sort(key=lambda b: (b.formato_dian, b.concepto_dian))

    dictamen.calcular_resumen()

    return dictamen


def _capa_nombre(capa: int) -> str:
    return {
        1: 'Global',
        2: 'Mapeo nativo',
        3: 'Override empresa',
    }.get(capa, 'Sin clasificar')


# ============================================================================
# Helpers de presentación (para Streamlit y Excel)
# ============================================================================

def dictamen_a_filas_excel(dictamen: DictamenConciliacion) -> list[dict]:
    """
    Aplana el dictamen en filas tipo tabla para volcar a Excel.
    Cada fila es UNA cuenta dentro de un (formato, concepto).
    """
    filas = []
    for bloque in dictamen.bloques:
        for c in bloque.cuentas:
            filas.append({
                'Formato': bloque.formato_dian,
                'Concepto': bloque.concepto_dian,
                'Descripción concepto': bloque.descripcion_concepto,
                'Cuenta': c.codigo_cuenta,
                'Nombre cuenta': c.nombre_cuenta,
                'Capa': c.capa_nombre,
                'Saldo balance': float(c.saldo_balance),
                'Valor reportado': float(c.valor_reportado),
                'Diferencia': float(c.diferencia),
                'NITs distintos': c.nits_distintos,
                'Estado': '🚫 Excluida' if c.excluida else '✓ Activa',
                'Motivo': c.motivo_diferencia or '',
            })
        # Fila de totales por concepto
        filas.append({
            'Formato': bloque.formato_dian,
            'Concepto': bloque.concepto_dian,
            'Descripción concepto': bloque.descripcion_concepto,
            'Cuenta': 'TOTAL CONCEPTO',
            'Nombre cuenta': '',
            'Capa': '',
            'Saldo balance': float(bloque.total_balance),
            'Valor reportado': float(bloque.total_reportado),
            'Diferencia': float(bloque.diferencia),
            'NITs distintos': '',
            'Estado': bloque.estado.upper(),
            'Motivo': '; '.join(bloque.explicaciones[:2]) if bloque.explicaciones else '',
        })
    return filas


def dictamen_a_resumen_dict(dictamen: DictamenConciliacion) -> dict:
    """Resumen ejecutivo para mostrar al inicio."""
    return {
        'año_gravable': dictamen.año_gravable,
        'total_conceptos': dictamen.total_conceptos,
        'conceptos_cuadrados': dictamen.conceptos_cuadrados,
        'conceptos_con_diferencia_explicada': dictamen.conceptos_con_diferencia_explicada,
        'conceptos_pendientes': dictamen.conceptos_pendientes,
        'porcentaje_cuadrado': (
            (dictamen.conceptos_cuadrados / dictamen.total_conceptos * 100)
            if dictamen.total_conceptos > 0 else 0
        ),
    }


# ============================================================================
# Test / smoke
# ============================================================================

if __name__ == '__main__':
    # Ejemplo de uso (necesita cliente Supabase real)
    print("Conciliación enriquecida — módulo cargado correctamente")
    print("Funciones disponibles:")
    print("  - construir_conciliacion_enriquecida(sb, empresa_id, año_gravable)")
    print("  - dictamen_a_filas_excel(dictamen)")
    print("  - dictamen_a_resumen_dict(dictamen)")
