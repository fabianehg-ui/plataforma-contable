"""
Lector de Comprobante de Medios Magnéticos del operador SuAporte/Ceiba Software.

El archivo es un .xls (Composite Document File V2) con 4 hojas:
    - 'Seguridad Social'          → detalle por administradora (EPS, AFP, ARL)
    - 'Consolidado, Seguridad Social' → totales por subsistema
    - 'Parafiscales'              → detalle CCF, SENA, ICBF
    - 'Consolidado, Parafiscales' → totales por subsistema

Una sola planilla puede tener pagos a múltiples fondos. Una sola descarga
de SuAporte puede contener varias planillas (mes a mes del año gravable).

Requiere: xlrd
"""
from __future__ import annotations
import io
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Union, BinaryIO

import xlrd


# ============================================================
# Mapeo fondo → concepto DIAN F1001 (Resolución 000227/2025)
# ============================================================
# 5010 = Aportes parafiscales (SENA + Cajas de Compensación + ICBF)
# 5011 = Aportes a EPS y ARL (incluye empleador + trabajador)
# 5012 = Aportes obligatorios a Fondos de Pensiones (incluye emp + trab)
# ============================================================

def clasificar_fondo(codigo: str, nombre: str) -> tuple[int, str]:
    """Devuelve (concepto_dian, tipo_fondo) para un fondo dado.

    Args:
        codigo: Código del operador (ej '25-14', 'EPS010', 'CCF04')
        nombre: Nombre del fondo (ej 'COLPENSIONES', 'EPS SURA')

    Returns:
        (concepto_dian, tipo) — None si no se reconoce
    """
    nombre_u = (nombre or '').upper()
    codigo_u = (codigo or '').upper()

    # ARL primero (puede tener 'RIESGOS' o 'COLMENA')
    if 'RIESGOS' in nombre_u or 'ARL' in nombre_u or 'COLMENA' in nombre_u or 'POSITIVA' in nombre_u or 'SURATEP' in nombre_u or 'BOLIVAR' in nombre_u:
        return 5011, 'ARL'

    # EPS / Salud
    if 'EPS' in nombre_u or 'SALUD' in nombre_u or 'SANITAS' in nombre_u or 'SURA' in nombre_u and 'EPS' in nombre_u:
        return 5011, 'EPS'

    # Cajas de Compensación
    if 'CCF' in codigo_u or 'CAJA' in nombre_u or 'COMPENSACION' in nombre_u or 'COMPENSACIÓN' in nombre_u or 'COMFAMA' in nombre_u or 'COMFENALCO' in nombre_u or 'CAFAM' in nombre_u or 'COLSUBSIDIO' in nombre_u:
        return 5010, 'CCF'

    # SENA
    if 'SENA' in nombre_u:
        return 5010, 'SENA'

    # ICBF
    if 'ICBF' in nombre_u or 'BIENESTAR' in nombre_u:
        return 5010, 'ICBF'

    # AFP / Fondos de Pensiones (lo último porque PROTECCIÓN también es fondo de cesantías)
    afp_keywords = ['PORVENIR', 'COLPENSIONES', 'COLFONDOS', 'OLD MUTUAL', 'SKANDIA']
    if any(k in nombre_u for k in afp_keywords):
        return 5012, 'AFP'

    # PROTECCION es ambiguo (puede ser AFP o fondo cesantías). En este contexto
    # del Comprobante de Medios Magnéticos, siempre es AFP.
    if 'PROTECCION' in nombre_u or 'PROTECCIÓN' in nombre_u:
        return 5012, 'AFP'

    return None, None


@dataclass
class FondoMovimiento:
    """Movimiento de aporte a un fondo dentro de una planilla."""
    fondo_codigo: str = ''
    fondo_nit: str = ''
    fondo_nombre: str = ''
    fondo_tipo: str = ''           # 'EPS', 'AFP', 'ARL', 'CCF', 'SENA', 'ICBF'
    concepto_dian: int = 0         # 5010, 5011, 5012
    ibc: Decimal = Decimal('0')
    valor_empleador: Decimal = Decimal('0')
    valor_trabajador: Decimal = Decimal('0')
    total_obligatorio: Decimal = Decimal('0')


@dataclass
class PlanillaPila:
    """Una planilla PILA con su detalle por fondo."""
    numero_planilla: str = ''
    fecha_pago: str = ''           # 'YYYY-MM-DD'
    periodo_cot: str = ''          # 'YYYYMM'
    tipo_planilla: str = ''        # 'E', 'I', 'N'
    afiliados: int = 0
    total_pagado: Decimal = Decimal('0')
    movimientos: list = field(default_factory=list)


@dataclass
class ResultadoLecturaPilaXls:
    """Resultado de leer el .xls de SuAporte."""
    operador: str = 'SuAporte/Ceiba Software'
    nit_empresa: str = ''
    planillas: list = field(default_factory=list)
    archivo_origen: str = ''
    errores: list = field(default_factory=list)
    advertencias: list = field(default_factory=list)

    @property
    def total_planillas(self) -> int:
        return len(self.planillas)

    @property
    def total_pagado_global(self) -> Decimal:
        return sum((p.total_pagado for p in self.planillas), Decimal('0'))


# ============================================================
# Helpers
# ============================================================

def _safe_str(v) -> str:
    if v is None:
        return ''
    return str(v).strip()


def _safe_decimal(v) -> Decimal:
    if v is None or v == '':
        return Decimal('0')
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal('0')


def _limpiar_nit(nit_raw) -> str:
    """Quita prefijo 'N' del NIT que viene en SuAporte (ej 'N900336004' → '900336004')."""
    s = _safe_str(nit_raw).lstrip('N').strip()
    # Si trae DV con guión, devolvemos sin DV para uniformidad
    if '-' in s:
        s = s.split('-')[0]
    return s


def _abrir_workbook(archivo: Union[str, Path, bytes, BinaryIO]) -> xlrd.book.Book:
    """Abre un workbook xlrd desde varios tipos de entrada."""
    if isinstance(archivo, (str, Path)):
        return xlrd.open_workbook(str(archivo))
    if isinstance(archivo, (bytes, bytearray)):
        return xlrd.open_workbook(file_contents=bytes(archivo))
    if hasattr(archivo, 'read'):
        data = archivo.read()
        if hasattr(archivo, 'seek'):
            archivo.seek(0)
        return xlrd.open_workbook(file_contents=data)
    raise TypeError(f"Tipo de archivo no soportado: {type(archivo)}")


# ============================================================
# Parsing principal
# ============================================================

def leer_xls_suaporte(
    archivo: Union[str, Path, bytes, BinaryIO],
    nombre_archivo: str = '',
) -> ResultadoLecturaPilaXls:
    """Lee un Comprobante de Medios Magnéticos de SuAporte y devuelve las planillas.

    Args:
        archivo: ruta, bytes o file-like del archivo .xls
        nombre_archivo: nombre original para metadata (opcional)

    Returns:
        ResultadoLecturaPilaXls con todas las planillas parseadas
    """
    resultado = ResultadoLecturaPilaXls(archivo_origen=nombre_archivo)

    try:
        wb = _abrir_workbook(archivo)
    except Exception as e:
        resultado.errores.append(f"No se pudo abrir el archivo .xls: {e}")
        return resultado

    nombres_esperados = {'Seguridad Social', 'Parafiscales'}
    nombres_presentes = set(wb.sheet_names())
    if not nombres_esperados.issubset(nombres_presentes):
        resultado.errores.append(
            f"El archivo no tiene la estructura esperada de SuAporte. "
            f"Hojas presentes: {sorted(nombres_presentes)}. "
            f"Se requieren: {sorted(nombres_esperados)}."
        )
        return resultado

    # Diccionario provisional: numero_planilla → PlanillaPila
    planillas_dict: dict[str, PlanillaPila] = {}

    # --- 1) Hoja Seguridad Social (EPS, AFP, ARL) ------------------
    try:
        sheet_ss = wb.sheet_by_name('Seguridad Social')
        _parsear_hoja_ss(sheet_ss, planillas_dict, resultado)
    except Exception as e:
        resultado.errores.append(f"Error parseando Seguridad Social: {e}")

    # --- 2) Hoja Parafiscales (CCF, SENA, ICBF) --------------------
    try:
        sheet_para = wb.sheet_by_name('Parafiscales')
        _parsear_hoja_parafiscales(sheet_para, planillas_dict, resultado)
    except Exception as e:
        resultado.errores.append(f"Error parseando Parafiscales: {e}")

    # Convertir dict a lista ordenada por fecha_pago
    resultado.planillas = sorted(
        planillas_dict.values(),
        key=lambda p: (p.fecha_pago, p.numero_planilla),
    )

    # Calcular total_pagado por planilla
    for p in resultado.planillas:
        p.total_pagado = sum((m.total_obligatorio for m in p.movimientos), Decimal('0'))

    return resultado


def _parsear_hoja_ss(sheet, planillas_dict: dict, resultado: ResultadoLecturaPilaXls):
    """Parsea hoja 'Seguridad Social'.

    Columnas según SuAporte:
      0: Código Administradora    1: NIT          2: Administradora
      3: Referencia Pago (PIN)    4: Fecha pago   5: Periodo cotización
      6: Tipo Planilla            7: Afiliados    8: Registros
      9: IBC                     10: Tarifa      11: Tarifa Empleador
     12: Aporte Empleador        13: Tarifa Afil 14: Aporte Afiliado
     15: Total Aporte Obligatorio (emp + afil)
     21: Total Aportes (incluye voluntarios)
     23: Valor pagado menos descuentos sin mora
    """
    for r in range(1, sheet.nrows):
        codigo = _safe_str(sheet.cell_value(r, 0))
        nit_raw = sheet.cell_value(r, 1)
        nombre = _safe_str(sheet.cell_value(r, 2))
        num_planilla = sheet.cell_value(r, 3)
        fecha_pago = _safe_str(sheet.cell_value(r, 4))
        periodo = _safe_str(sheet.cell_value(r, 5))
        tipo_plan = _safe_str(sheet.cell_value(r, 6))
        afiliados = sheet.cell_value(r, 7)
        ibc = _safe_decimal(sheet.cell_value(r, 9))
        valor_emp = _safe_decimal(sheet.cell_value(r, 12)) if sheet.ncols > 12 else Decimal('0')
        valor_afil = _safe_decimal(sheet.cell_value(r, 14)) if sheet.ncols > 14 else Decimal('0')
        total_oblig = _safe_decimal(sheet.cell_value(r, 15)) if sheet.ncols > 15 else Decimal('0')

        if not codigo or not nombre or total_oblig == 0:
            continue

        concepto, tipo_fondo = clasificar_fondo(codigo, nombre)
        if not concepto:
            resultado.advertencias.append(
                f"Fila {r+1} Seg.Social: fondo no reconocido '{codigo}' / '{nombre}' — saltado"
            )
            continue

        num_planilla_str = str(int(num_planilla)) if isinstance(num_planilla, float) else _safe_str(num_planilla)
        if num_planilla_str not in planillas_dict:
            planillas_dict[num_planilla_str] = PlanillaPila(
                numero_planilla=num_planilla_str,
                fecha_pago=fecha_pago,
                periodo_cot=periodo,
                tipo_planilla=tipo_plan,
                afiliados=int(afiliados) if isinstance(afiliados, (int, float)) else 0,
            )

        planillas_dict[num_planilla_str].movimientos.append(FondoMovimiento(
            fondo_codigo=codigo,
            fondo_nit=_limpiar_nit(nit_raw),
            fondo_nombre=nombre,
            fondo_tipo=tipo_fondo,
            concepto_dian=concepto,
            ibc=ibc,
            valor_empleador=valor_emp,
            valor_trabajador=valor_afil,
            total_obligatorio=total_oblig,
        ))


def _parsear_hoja_parafiscales(sheet, planillas_dict: dict, resultado: ResultadoLecturaPilaXls):
    """Parsea hoja 'Parafiscales' (CCF, SENA, ICBF).

    Columnas:
      0: Código    1: NIT          2: Administradora
      3: Referencia Pago (Planilla)
      4: Fecha pago  5: Periodo    6: Tipo Planilla  7: Afiliados
      8: Valor aporte
      9: Días mora  10: Interés mora  11: Total a Pagar
    """
    for r in range(1, sheet.nrows):
        codigo = _safe_str(sheet.cell_value(r, 0))
        nit_raw = sheet.cell_value(r, 1)
        nombre = _safe_str(sheet.cell_value(r, 2))
        num_planilla = sheet.cell_value(r, 3)
        fecha_pago = _safe_str(sheet.cell_value(r, 4))
        periodo = _safe_str(sheet.cell_value(r, 5))
        tipo_plan = _safe_str(sheet.cell_value(r, 6))
        afiliados = sheet.cell_value(r, 7)
        valor = _safe_decimal(sheet.cell_value(r, 8))

        if not codigo or not nombre or valor == 0:
            continue

        concepto, tipo_fondo = clasificar_fondo(codigo, nombre)
        if not concepto:
            resultado.advertencias.append(
                f"Fila {r+1} Parafiscales: fondo no reconocido '{codigo}' / '{nombre}' — saltado"
            )
            continue

        num_planilla_str = str(int(num_planilla)) if isinstance(num_planilla, float) else _safe_str(num_planilla)
        if num_planilla_str not in planillas_dict:
            planillas_dict[num_planilla_str] = PlanillaPila(
                numero_planilla=num_planilla_str,
                fecha_pago=fecha_pago,
                periodo_cot=periodo,
                tipo_planilla=tipo_plan,
                afiliados=int(afiliados) if isinstance(afiliados, (int, float)) else 0,
            )

        # Parafiscales son 100% empleador
        planillas_dict[num_planilla_str].movimientos.append(FondoMovimiento(
            fondo_codigo=codigo,
            fondo_nit=_limpiar_nit(nit_raw),
            fondo_nombre=nombre,
            fondo_tipo=tipo_fondo,
            concepto_dian=concepto,
            ibc=Decimal('0'),
            valor_empleador=valor,
            valor_trabajador=Decimal('0'),
            total_obligatorio=valor,
        ))


# ============================================================
# Lector de Informe por Fondo (cesantías)
# ============================================================

@dataclass
class EmpleadoCesantia:
    """Detalle de cesantía de un empleado en el InformePorFondo."""
    tipo_doc: str = ''
    documento: str = ''
    apellidos: str = ''
    nombres: str = ''
    dias_base: int = 0
    salario_base: Decimal = Decimal('0')
    cesantia: Decimal = Decimal('0')


@dataclass
class InformeCesantias:
    """Resultado de leer un Informe por Fondo de cesantías."""
    fondo_nit: str = ''
    fondo_nombre: str = ''
    año_causado: int = 0
    fecha_pago: str = ''
    numero_planilla: str = ''
    nit_empresa: str = ''
    empleados: list = field(default_factory=list)
    total: Decimal = Decimal('0')
    archivo_origen: str = ''
    errores: list = field(default_factory=list)


def leer_xls_informe_cesantias(
    archivo: Union[str, Path, bytes, BinaryIO],
    nombre_archivo: str = '',
) -> InformeCesantias:
    """Lee un InformePorFondo de cesantías y devuelve el detalle.

    Args:
        archivo: ruta, bytes o file-like
        nombre_archivo: nombre original para metadata

    Returns:
        InformeCesantias con la planilla y los empleados
    """
    info = InformeCesantias(archivo_origen=nombre_archivo)

    try:
        wb = _abrir_workbook(archivo)
        sheet = wb.sheets()[0]
    except Exception as e:
        info.errores.append(f"No se pudo abrir el archivo: {e}")
        return info

    # Layout fijo del Informe por Fondo
    # R7  col 31 = año causado
    # R11 col 5  = fecha pago (también R12 col 31)
    # R8  col 31 = número planilla
    # R16 col 31 = nombre fondo (con NIT en el formato 'XXX N800XXXXXXXXX')
    # R18 col 31 = código fondo (02)
    # R21 col 8  = NIT empresa, R21 col 26 = documento empresa
    # R27-R34   = empleados (8 máximo)
    # R38 col 19 = total

    try:
        info.año_causado = int(sheet.cell_value(7, 31))
    except (ValueError, TypeError):
        info.errores.append(f"No se pudo leer año causado (R7,C31)")

    fecha_raw = sheet.cell_value(12, 31) if sheet.nrows > 12 else ''
    info.fecha_pago = _safe_str(fecha_raw)
    if not info.fecha_pago and sheet.nrows > 11:
        info.fecha_pago = _safe_str(sheet.cell_value(11, 5))

    info.numero_planilla = _safe_str(sheet.cell_value(8, 31))
    if info.numero_planilla.endswith('.0'):
        info.numero_planilla = info.numero_planilla[:-2]

    fondo_full = _safe_str(sheet.cell_value(16, 31))
    info.fondo_nombre = fondo_full
    # Extraer NIT del nombre (formato típico: 'Fondo de cesantías Protección N800170494')
    import re as _re
    m = _re.search(r'N(\d{8,11})', fondo_full)
    if m:
        info.fondo_nit = m.group(1)
        # Limpiar nombre quitando el NIT del final
        info.fondo_nombre = _re.sub(r'\s*N\d{8,11}\s*$', '', fondo_full).strip()

    # NIT empresa
    doc_empresa = sheet.cell_value(21, 26) if sheet.nrows > 21 else ''
    info.nit_empresa = _safe_str(doc_empresa)
    if info.nit_empresa.endswith('.0'):
        info.nit_empresa = info.nit_empresa[:-2]

    # Detalle empleados (filas 27-34)
    for r in range(27, min(35, sheet.nrows)):
        tipo_doc = _safe_str(sheet.cell_value(r, 2))
        if not tipo_doc:
            continue
        doc = sheet.cell_value(r, 7)
        if isinstance(doc, float):
            doc_str = str(int(doc))
        else:
            doc_str = _safe_str(doc)

        empleado = EmpleadoCesantia(
            tipo_doc=tipo_doc,
            documento=doc_str,
            apellidos=_safe_str(sheet.cell_value(r, 10)),
            nombres=_safe_str(sheet.cell_value(r, 20)),
            dias_base=int(sheet.cell_value(r, 24)) if isinstance(sheet.cell_value(r, 24), (int, float)) else 0,
            salario_base=_safe_decimal(sheet.cell_value(r, 27)),
            cesantia=_safe_decimal(sheet.cell_value(r, 32)),
        )
        info.empleados.append(empleado)

    # Total
    if sheet.nrows > 38:
        info.total = _safe_decimal(sheet.cell_value(38, 19))
    if info.total == 0 and info.empleados:
        info.total = sum((e.cesantia for e in info.empleados), Decimal('0'))

    return info


# ============================================================
# CLI para pruebas locales
# ============================================================

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Uso: python lector_pila_xls.py <archivo.xls>")
        sys.exit(1)

    path = sys.argv[1]
    if 'InformePorFondo' in path:
        info = leer_xls_informe_cesantias(path, nombre_archivo=path)
        print(f"=== Informe por Fondo ===")
        print(f"Fondo: {info.fondo_nombre} (NIT {info.fondo_nit})")
        print(f"Año causado: {info.año_causado}")
        print(f"Fecha pago: {info.fecha_pago}")
        print(f"Empresa NIT: {info.nit_empresa}")
        print(f"\nEmpleados ({len(info.empleados)}):")
        for e in info.empleados:
            print(f"  {e.tipo_doc} {e.documento:>12} {e.apellidos[:25]:<25} {e.nombres[:20]:<20} {e.cesantia:>14,.0f}")
        print(f"\nTotal: ${info.total:,.0f}")
    else:
        res = leer_xls_suaporte(path, nombre_archivo=path)
        print(f"=== Resultado: {res.total_planillas} planillas, ${res.total_pagado_global:,.0f} total ===")
        for p in res.planillas:
            print(f"\nPlanilla {p.numero_planilla} | Pago: {p.fecha_pago} | Cot: {p.periodo_cot}")
            print(f"  {len(p.movimientos)} movimientos | Total: ${p.total_pagado:,.0f}")
            for m in p.movimientos:
                print(f"    {m.fondo_tipo:<5} {m.concepto_dian} {m.fondo_nit:<14} {m.fondo_nombre[:30]:<30} ${m.total_obligatorio:>14,.0f}")

        if res.advertencias:
            print(f"\n⚠️ {len(res.advertencias)} advertencias")
            for a in res.advertencias[:5]:
                print(f"  {a}")
        if res.errores:
            print(f"\n❌ {len(res.errores)} errores")
            for e in res.errores:
                print(f"  {e}")
