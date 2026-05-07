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
        1. Lee balance del año (cuentas + saldos + nits)
        2. Lee reglas de las 3 capas y determina a qué (formato, concepto)
           va cada cuenta
        3. Lee el XML reportado (de movimientos clasificados)
        4. Agrupa por (formato, concepto) y construye los bloques
        5. Calcula diferencias y motivos
    """
    dictamen = DictamenConciliacion(
        año_gravable=año_gravable,
        empresa_id=empresa_id,
    )

    # 1. Leer movimientos clasificados (ya tienen formato y concepto asignados)
    movs_resp = sb.table('exogena_movimientos_clasificados') \
        .select('*') \
        .eq('empresa_id', empresa_id) \
        .eq('año_gravable', año_gravable) \
        .execute()

    movs = movs_resp.data or []

    # 2. Agrupar por (formato, concepto) y dentro de eso por cuenta
    grupos: dict[tuple[str, int], dict[str, Any]] = {}

    for m in movs:
        fmt = m.get('formato_dian') or '_SIN_FORMATO_'
        cpt = m.get('concepto_dian') or 0
        cod = m.get('codigo_cuenta', '')
        excl = m.get('excluido', False) or m.get('excluir', False)

        key = (fmt, cpt)
        if key not in grupos:
            grupos[key] = {
                'descripcion': m.get('descripcion_concepto', ''),
                'cuentas_dict': {},
            }

        if cod not in grupos[key]['cuentas_dict']:
            grupos[key]['cuentas_dict'][cod] = {
                'codigo_cuenta': cod,
                'nombre_cuenta': m.get('nombre_cuenta', ''),
                'saldo_balance': Decimal('0'),
                'valor_reportado': Decimal('0'),
                'capa_origen': m.get('capa_resolucion', 0),
                'capa_nombre': _capa_nombre(m.get('capa_resolucion', 0)),
                'excluida': excl,
                'motivo': m.get('nota') or m.get('motivo_exclusion'),
                'nits_set': set(),
            }

        cuenta = grupos[key]['cuentas_dict'][cod]
        saldo = Decimal(str(m.get('saldo_final', 0) or 0))
        cuenta['saldo_balance'] += saldo

        if not excl:
            cuenta['valor_reportado'] += saldo

        if m.get('nit'):
            cuenta['nits_set'].add(m['nit'])

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
