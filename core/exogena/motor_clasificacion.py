"""
Motor de clasificación de movimientos contables → formatos DIAN.

Aplica las 3 capas de mapeo en orden de prioridad (más específico → más genérico):
  1. exogena_mapeo_manual    (override por cuenta+NIT específico)
  2. exogena_mapeo_empresa   (codificación nativa por rangos)
  3. exogena_puc_generico    (PUC genérico compartido)

Uso típico:
    motor = MotorClasificacion(
        reglas_capa1=puc_generico,
        reglas_capa2=mapeo_empresa,
        reglas_capa3=mapeo_manual,
    )
    resultado = motor.clasificar_balance(movimientos_balance)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


def cuenta_en_rango(cuenta: str, inicial: str, final: str) -> bool:
    """Cuenta dentro del rango [inicial, final] con padding a 10 chars (0/9)."""
    c = str(cuenta).strip().ljust(10, '0')
    ini = str(inicial).strip().ljust(10, '0')
    fin = str(final).strip().ljust(10, '9')
    return ini <= c <= fin


@dataclass
class ReglaCapa1:
    """Regla del PUC genérico (capa 1): coincidencia exacta o por prefijo."""
    codigo_cuenta: str
    formato_dian: str
    concepto_dian: Optional[int]
    nombre_cuenta: str = ''


@dataclass
class ReglaCapa2:
    """Regla nativa de la empresa (capa 2): rango de cuentas."""
    formato_dian: str
    concepto_dian: int
    cuenta_inicial: str
    cuenta_final: str
    descripcion_concepto: str = ''
    id: Optional[int] = None
    fila_origen: int = 0


@dataclass
class ReglaCapa3:
    """Override manual (capa 3): cuenta + NIT específico."""
    codigo_cuenta: str
    nit: Optional[str]
    formato_dian: str
    concepto_dian: Optional[int]
    nota: str = ''
    id: Optional[int] = None


@dataclass
class Movimiento:
    """Movimiento contable a clasificar."""
    codigo_cuenta: str
    nit: Optional[str] = None
    debitos: float = 0.0
    creditos: float = 0.0
    saldo_final: float = 0.0
    nombre_cuenta: str = ''
    nombre_tercero: str = ''
    balance_id: Optional[int] = None  # FK a la tabla exogena_balance


@dataclass
class MovimientoClasificado:
    """Resultado de clasificar un movimiento contra una regla."""
    codigo_cuenta: str
    nit: Optional[str]
    formato_dian: str
    concepto_dian: Optional[int]
    valor: float
    base_aplicable: str                     # 'debitos', 'creditos', 'saldo_final'
    capa_resolucion: str                    # 'puc_generico' | 'mapeo_empresa' | 'mapeo_manual' | 'sin_resolver'
    regla_id: Optional[int] = None
    requiere_revision: bool = False
    nota: str = ''
    balance_id: Optional[int] = None


@dataclass
class ResultadoClasificacion:
    movimientos: list[MovimientoClasificado] = field(default_factory=list)
    sin_resolver: list[Movimiento] = field(default_factory=list)
    estadisticas: dict = field(default_factory=dict)


# ================================================================
# CONFIGURACIÓN: cómo determinar qué base usar (débitos/créditos/saldo)
# ================================================================
# Por formato, cuál columna del balance representa el valor a informar.
# Esto se basa en la lógica contable de la información exógena DIAN.
BASE_POR_FORMATO = {
    '1001': 'debitos',         # Pagos o abonos en cuenta → débitos del gasto
    '1003': 'creditos',        # Retenciones que le practicaron → créditos de la cta retención
    '1004': 'saldo_final',     # Descuentos tributarios solicitados
    '1005': 'debitos',         # IVA descontable
    '1006': 'creditos',        # IVA generado
    '1007': 'creditos',        # Ingresos recibidos → créditos de la cta de ingreso
    '1008': 'saldo_final',     # Saldos cuentas por cobrar al 31-dic
    '1009': 'saldo_final',     # Saldos cuentas por pagar al 31-dic
    '1010': 'saldo_final',     # Información socios (saldo aportes)
    '1011': 'debitos',         # Declaraciones tributarias (movimientos)
    '1012': 'saldo_final',     # Inversiones, cuentas bancarias al 31-dic
    '1056': 'debitos',         # Pagos sector público
    '1647': 'creditos',        # Ingresos para terceros
    '2275': 'creditos',        # Ingresos no constitutivos
    '2276': 'debitos',         # Rentas de trabajo (nómina)
    '2278': 'debitos',         # Bonos electrónicos
    '5253': 'saldo_final',     # Beneficiarios efectivos
}


class MotorClasificacion:
    def __init__(
        self,
        reglas_capa1: list[ReglaCapa1],
        reglas_capa2: list[ReglaCapa2],
        reglas_capa3: list[ReglaCapa3] | None = None,
    ):
        self.reglas_capa1 = reglas_capa1
        self.reglas_capa2 = reglas_capa2
        self.reglas_capa3 = reglas_capa3 or []

        # Índice de capa 1 por código exacto, para lookup O(1)
        self._capa1_por_codigo: dict[str, list[ReglaCapa1]] = {}
        for r in reglas_capa1:
            self._capa1_por_codigo.setdefault(r.codigo_cuenta, []).append(r)

        # Índice de capa 3 por (cuenta, nit)
        self._capa3_por_cuenta_nit: dict[tuple, list[ReglaCapa3]] = {}
        # Índice de capa 3 por (cuenta, NULL) para reglas globales por cuenta
        self._capa3_por_cuenta: dict[str, list[ReglaCapa3]] = {}
        for r in self.reglas_capa3:
            if r.nit:
                self._capa3_por_cuenta_nit.setdefault((r.codigo_cuenta, r.nit), []).append(r)
            else:
                self._capa3_por_cuenta.setdefault(r.codigo_cuenta, []).append(r)

    # ----------------------------------------------------------------
    # Búsquedas por capa
    # ----------------------------------------------------------------
    def _buscar_capa3(self, cuenta: str, nit: Optional[str]) -> list[ReglaCapa3]:
        """Capa 3: busca primero (cuenta, NIT específico), luego (cuenta, NULL)."""
        if nit and (cuenta, nit) in self._capa3_por_cuenta_nit:
            return self._capa3_por_cuenta_nit[(cuenta, nit)]
        return self._capa3_por_cuenta.get(cuenta, [])

    def _buscar_capa2(self, cuenta: str) -> list[ReglaCapa2]:
        """Capa 2: itera todas las reglas y devuelve las que contienen la cuenta en su rango."""
        return [
            r for r in self.reglas_capa2
            if cuenta_en_rango(cuenta, r.cuenta_inicial, r.cuenta_final)
        ]

    def _buscar_capa1(self, cuenta: str) -> list[ReglaCapa1]:
        """Capa 1: coincidencia exacta primero, luego por prefijos decrecientes."""
        if cuenta in self._capa1_por_codigo:
            return self._capa1_por_codigo[cuenta]
        # Buscar por prefijo: 8d → 6d → 4d → 2d
        for L in (8, 6, 4, 2):
            if len(cuenta) > L:
                prefix = cuenta[:L]
                if prefix in self._capa1_por_codigo:
                    return self._capa1_por_codigo[prefix]
        return []

    # ----------------------------------------------------------------
    # Selección de valor según formato
    # ----------------------------------------------------------------
    @staticmethod
    def _valor_para_formato(mov: Movimiento, formato: str) -> tuple[float, str]:
        base = BASE_POR_FORMATO.get(formato, 'debitos')
        if base == 'debitos':
            return mov.debitos, 'debitos'
        if base == 'creditos':
            return mov.creditos, 'creditos'
        return mov.saldo_final, 'saldo_final'

    # ----------------------------------------------------------------
    # Clasificación de un movimiento individual
    # ----------------------------------------------------------------
    def clasificar_movimiento(self, mov: Movimiento) -> list[MovimientoClasificado]:
        """Clasifica un movimiento aplicando las 3 capas en orden.
        
        Devuelve una lista porque:
          - Capa 2 puede dar múltiples reglas (ambigüedad) → marca requiere_revision
          - Capa 1 puede tener una cuenta en varios formatos
        """
        resultados: list[MovimientoClasificado] = []

        # CAPA 3: override manual (siempre gana, sea único o múltiple)
        capa3 = self._buscar_capa3(mov.codigo_cuenta, mov.nit)
        if capa3:
            for r in capa3:
                valor, base = self._valor_para_formato(mov, r.formato_dian)
                resultados.append(MovimientoClasificado(
                    codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
                    formato_dian=r.formato_dian,
                    concepto_dian=r.concepto_dian,
                    valor=abs(valor),
                    base_aplicable=base,
                    capa_resolucion='mapeo_manual',
                    regla_id=r.id,
                    requiere_revision=False,
                    nota=f'Override manual: {r.nota}' if r.nota else 'Override manual',
                    balance_id=mov.balance_id,
                ))
            return resultados

        # CAPA 2: mapeo nativo
        capa2 = self._buscar_capa2(mov.codigo_cuenta)
        if capa2:
            ambiguo = len(capa2) > 1
            for r in capa2:
                valor, base = self._valor_para_formato(mov, r.formato_dian)
                resultados.append(MovimientoClasificado(
                    codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
                    formato_dian=r.formato_dian,
                    concepto_dian=r.concepto_dian,
                    valor=abs(valor),
                    base_aplicable=base,
                    capa_resolucion='mapeo_empresa',
                    regla_id=r.id,
                    requiere_revision=ambiguo,
                    nota=(
                        f'Ambigüedad: {len(capa2)} reglas posibles. {r.descripcion_concepto}'
                        if ambiguo else r.descripcion_concepto
                    ),
                    balance_id=mov.balance_id,
                ))
            return resultados

        # CAPA 1: PUC genérico (fallback)
        capa1 = self._buscar_capa1(mov.codigo_cuenta)
        if capa1:
            for r in capa1:
                valor, base = self._valor_para_formato(mov, r.formato_dian)
                resultados.append(MovimientoClasificado(
                    codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
                    formato_dian=r.formato_dian,
                    concepto_dian=r.concepto_dian,
                    valor=abs(valor),
                    base_aplicable=base,
                    capa_resolucion='puc_generico',
                    requiere_revision=False,
                    nota=f'PUC genérico: {r.nombre_cuenta}',
                    balance_id=mov.balance_id,
                ))
            return resultados

        # Sin resolver
        return [MovimientoClasificado(
            codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
            formato_dian='', concepto_dian=None,
            valor=abs(mov.debitos or mov.creditos or mov.saldo_final),
            base_aplicable='',
            capa_resolucion='sin_resolver',
            requiere_revision=True,
            nota='No se encontró regla en ninguna capa',
            balance_id=mov.balance_id,
        )]

    # ----------------------------------------------------------------
    # Clasificación masiva
    # ----------------------------------------------------------------
    def clasificar_balance(self, movimientos: list[Movimiento]) -> ResultadoClasificacion:
        res = ResultadoClasificacion()
        contador = {'capa1': 0, 'capa2_unico': 0, 'capa2_ambiguo': 0,
                    'capa3': 0, 'sin_resolver': 0}

        for mov in movimientos:
            clasificaciones = self.clasificar_movimiento(mov)
            res.movimientos.extend(clasificaciones)

            primera = clasificaciones[0]
            if primera.capa_resolucion == 'sin_resolver':
                res.sin_resolver.append(mov)
                contador['sin_resolver'] += 1
            elif primera.capa_resolucion == 'mapeo_manual':
                contador['capa3'] += 1
            elif primera.capa_resolucion == 'mapeo_empresa':
                if primera.requiere_revision:
                    contador['capa2_ambiguo'] += 1
                else:
                    contador['capa2_unico'] += 1
            else:
                contador['capa1'] += 1

        res.estadisticas = {
            **contador,
            'total_movimientos': len(movimientos),
            'total_clasificaciones': len(res.movimientos),
            'requieren_revision': sum(1 for m in res.movimientos if m.requiere_revision),
        }
        return res
