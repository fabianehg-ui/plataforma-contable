"""
Cargador de archivo PILA (Planilla Integrada de Liquidación de Aportes).

El archivo PILA puede venir en varios formatos según el operador:
    - Aportes en Línea (Davivienda)
    - MiPlanilla (Banco de Occidente)
    - Asopagos
    - SoftAportes
    - Reporte consolidado anual del software contable

Estrategia: parser tolerante que detecta columnas por palabras clave en
los encabezados, sin asumir orden fijo.

Conceptos DIAN mapeados a tipos de aporte:
    5010 → Salud
    5011 → Pensión
    5012 → ARL (Riesgos Laborales)
    5013 → Caja de Compensación Familiar (CCF)
    5014 → SENA
    5015 → ICBF

Lógica de deducibilidad:
    - Aporte EMPLEADOR → DEDUCIBLE → Sí se reporta en formato 1001
    - Aporte TRABAJADOR → NO DEDUCIBLE → NO se reporta en formato 1001
    - ARL, CCF, SENA, ICBF → 100% empleador (todo deducible)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re
from decimal import Decimal

import openpyxl


# Mapeo concepto → palabras clave para detectar tipo de aporte
CONCEPTO_KEYWORDS = {
    'salud': {'concepto': 5010, 'keywords': ['salud', 'eps', 'sgsss']},
    'pension': {'concepto': 5011, 'keywords': ['pension', 'pensión', 'pens.', 'cotpens']},
    'arl': {'concepto': 5012, 'keywords': ['arl', 'riesgos', 'arp', 'riesgos laborales']},
    'caja': {'concepto': 5013, 'keywords': ['caja', 'compensacion', 'compensación', 'ccf', 'comfamiliar']},
    'sena': {'concepto': 5014, 'keywords': ['sena']},
    'icbf': {'concepto': 5015, 'keywords': ['icbf', 'bienestar', 'cree']},
    'fsp': {'concepto': None, 'keywords': ['fondo', 'fsp', 'solidaridad']},
}


@dataclass
class RegistroPila:
    """Una fila procesada del archivo PILA."""
    tipo_aporte: str               # 'salud', 'pension', 'arl', 'caja', 'sena', 'icbf'
    concepto_dian: int | None
    aporte_empleador: Decimal = Decimal('0')
    aporte_trabajador: Decimal = Decimal('0')
    aporte_total: Decimal = Decimal('0')
    nro_planilla: str = ''
    periodo_pago: str = ''
    fila_origen: int = 0


@dataclass
class ResultadoCargaPila:
    registros: list[RegistroPila] = field(default_factory=list)
    columnas_detectadas: dict = field(default_factory=dict)
    advertencias: list = field(default_factory=list)
    errores: list = field(default_factory=list)
    
    def consolidado_por_concepto(self) -> dict:
        """Suma todos los registros por tipo de aporte."""
        consolidado = {}
        for r in self.registros:
            key = r.tipo_aporte
            if key not in consolidado:
                consolidado[key] = {
                    'tipo_aporte': r.tipo_aporte,
                    'concepto_dian': r.concepto_dian,
                    'aporte_empleador': Decimal('0'),
                    'aporte_trabajador': Decimal('0'),
                    'aporte_total': Decimal('0'),
                    'cantidad_filas': 0,
                }
            consolidado[key]['aporte_empleador'] += r.aporte_empleador
            consolidado[key]['aporte_trabajador'] += r.aporte_trabajador
            consolidado[key]['aporte_total'] += r.aporte_total
            consolidado[key]['cantidad_filas'] += 1
        return consolidado


def _normalize(s) -> str:
    """Normaliza un texto: minúsculas, sin tildes, sin caracteres especiales."""
    if s is None:
        return ''
    s = str(s).strip().lower()
    # Reemplazar tildes
    repl = {'á':'a', 'é':'e', 'í':'i', 'ó':'o', 'ú':'u', 'ñ':'n'}
    for k, v in repl.items():
        s = s.replace(k, v)
    return s


def _to_decimal(v) -> Decimal:
    """Convierte cualquier valor a Decimal seguro."""
    if v is None or v == '':
        return Decimal('0')
    try:
        s = str(v).strip().replace(',', '').replace('$', '')
        if not s:
            return Decimal('0')
        return Decimal(s)
    except Exception:
        return Decimal('0')


def _detectar_columnas(headers: list) -> dict:
    """Detecta índices de columnas por keywords en los headers.
    
    Retorna dict con keys: 'tipo_aporte', 'concepto', 'aporte_empleador',
    'aporte_trabajador', 'aporte_total', 'periodo'.
    """
    cols = {}
    for i, h in enumerate(headers):
        if h is None:
            continue
        h_norm = _normalize(h)
        
        # Tipo de aporte / concepto
        if not cols.get('tipo_aporte'):
            if any(k in h_norm for k in ['tipo aporte', 'aporte', 'subsistema', 'concepto', 'tipo cotizacion']):
                if 'empleador' not in h_norm and 'trabajador' not in h_norm and 'aporte' != h_norm:
                    cols['tipo_aporte'] = i
        
        # Aporte EMPLEADOR
        if not cols.get('aporte_empleador'):
            if ('empleador' in h_norm or 'patronal' in h_norm or 'empresa' in h_norm) \
                    and any(k in h_norm for k in ['aporte', 'valor', 'pago', 'cotizacion', 'pagado']):
                cols['aporte_empleador'] = i
            elif h_norm == 'empleador':
                cols['aporte_empleador'] = i
        
        # Aporte TRABAJADOR
        if not cols.get('aporte_trabajador'):
            if ('trabajador' in h_norm or 'empleado' in h_norm or 'cotizante' in h_norm) \
                    and any(k in h_norm for k in ['aporte', 'valor', 'pago', 'cotizacion', 'pagado']):
                cols['aporte_trabajador'] = i
            elif h_norm in ('trabajador', 'empleado'):
                cols['aporte_trabajador'] = i
        
        # Aporte TOTAL
        if not cols.get('aporte_total'):
            if 'total' in h_norm and any(k in h_norm for k in ['aporte', 'valor', 'pago']):
                cols['aporte_total'] = i
        
        # Periodo
        if not cols.get('periodo'):
            if any(k in h_norm for k in ['periodo', 'mes', 'fecha pago']):
                cols['periodo'] = i
        
        # Planilla
        if not cols.get('planilla'):
            if 'planilla' in h_norm or 'numero pila' in h_norm:
                cols['planilla'] = i
    
    return cols


def _identificar_tipo_aporte(valor) -> tuple[str, int | None]:
    """Identifica el tipo de aporte por el valor de la celda.
    
    Returns (tipo, concepto_dian) o (None, None).
    """
    if valor is None:
        return None, None
    valor_norm = _normalize(valor)
    
    # Si es un número, podría ser el concepto directamente
    try:
        num = int(str(valor).strip())
        for tipo, info in CONCEPTO_KEYWORDS.items():
            if info['concepto'] == num:
                return tipo, num
    except (ValueError, TypeError):
        pass
    
    # Buscar por keywords
    for tipo, info in CONCEPTO_KEYWORDS.items():
        for kw in info['keywords']:
            if kw in valor_norm:
                return tipo, info['concepto']
    
    return None, None


def cargar_pila(archivo) -> ResultadoCargaPila:
    """Lee un archivo PILA y devuelve los aportes consolidados.
    
    Acepta:
        - str / Path: ruta del archivo
        - UploadedFile / file-like: típico de Streamlit
    """
    res = ResultadoCargaPila()
    
    if isinstance(archivo, (str, Path)):
        archivo = Path(archivo)
        if not archivo.exists():
            res.errores.append(f"Archivo no existe: {archivo}")
            return res
    
    try:
        wb = openpyxl.load_workbook(archivo, data_only=True, read_only=True)
        ws = wb.active
    except Exception as e:
        res.errores.append(f"No se pudo abrir el archivo: {e}")
        return res
    
    # Buscar fila de encabezados (puede no ser la primera)
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    
    if not rows:
        res.errores.append("Archivo vacío")
        return res
    
    # Buscar la primera fila que parezca un header (tiene varias palabras)
    fila_header = -1
    for i, row in enumerate(rows):
        if not row:
            continue
        # Contar celdas con texto que parezcan headers
        texto_count = sum(1 for c in row if c and isinstance(c, str) and len(str(c).strip()) > 3)
        if texto_count >= 3:
            fila_header = i
            break
    
    if fila_header == -1:
        res.errores.append("No se detectó fila de encabezados")
        return res
    
    headers = list(rows[fila_header])
    cols = _detectar_columnas(headers)
    res.columnas_detectadas = {
        'fila_header': fila_header + 1,
        'columnas_detectadas': cols,
        'headers': [str(h) if h else '' for h in headers[:10]],
    }
    
    # Validar que detectó las columnas mínimas
    if not cols.get('tipo_aporte'):
        res.errores.append(
            "No se detectó columna de tipo de aporte (Salud/Pensión/ARL). "
            f"Headers encontrados: {headers[:8]}"
        )
        return res
    
    if not (cols.get('aporte_empleador') or cols.get('aporte_total')):
        res.errores.append(
            "No se detectó columna de aporte (empleador o total). "
            f"Headers encontrados: {headers[:8]}"
        )
        return res
    
    # Procesar filas de datos
    for i, row in enumerate(rows[fila_header + 1:], start=fila_header + 2):
        if not row or all(c is None for c in row):
            continue
        
        # Identificar tipo de aporte
        tipo_val = row[cols['tipo_aporte']] if cols['tipo_aporte'] < len(row) else None
        tipo, concepto = _identificar_tipo_aporte(tipo_val)
        if not tipo:
            continue  # Fila no reconocible, saltarla silenciosamente
        
        # Valores
        emp = _to_decimal(row[cols.get('aporte_empleador', -1)] if cols.get('aporte_empleador') is not None and cols['aporte_empleador'] < len(row) else 0)
        trab = _to_decimal(row[cols.get('aporte_trabajador', -1)] if cols.get('aporte_trabajador') is not None and cols['aporte_trabajador'] < len(row) else 0)
        total = _to_decimal(row[cols.get('aporte_total', -1)] if cols.get('aporte_total') is not None and cols['aporte_total'] < len(row) else 0)
        
        # Si solo hay total, asumir 100% empleador para ARL/CCF/SENA/ICBF
        if total > 0 and emp == 0 and trab == 0:
            if tipo in ('arl', 'caja', 'sena', 'icbf'):
                emp = total
            else:
                # Para salud/pensión, el split estándar 50/50 es una asunción
                # Mejor advertir
                emp = total / 2
                trab = total / 2
                res.advertencias.append(
                    f"Fila {i}: tipo='{tipo}' solo tenía Total ({total}). "
                    "Asumido split 50/50 empleador/trabajador. Verifica manualmente."
                )
        elif total == 0:
            total = emp + trab
        
        periodo = ''
        if cols.get('periodo') is not None and cols['periodo'] < len(row):
            periodo = str(row[cols['periodo']] or '').strip()
        
        planilla = ''
        if cols.get('planilla') is not None and cols['planilla'] < len(row):
            planilla = str(row[cols['planilla']] or '').strip()
        
        res.registros.append(RegistroPila(
            tipo_aporte=tipo,
            concepto_dian=concepto,
            aporte_empleador=emp,
            aporte_trabajador=trab,
            aporte_total=total if total > 0 else (emp + trab),
            nro_planilla=planilla,
            periodo_pago=periodo,
            fila_origen=i,
        ))
    
    if not res.registros:
        res.errores.append(
            "No se encontraron filas válidas con tipo de aporte reconocible. "
            "Verifica que el archivo tenga columnas como 'Tipo aporte', 'Salud', 'Pensión', etc."
        )
    
    return res


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Uso: python cargador_pila.py <archivo.xlsx>")
        sys.exit(1)
    
    res = cargar_pila(sys.argv[1])
    
    print("=== Columnas detectadas ===")
    for k, v in res.columnas_detectadas.items():
        print(f"  {k}: {v}")
    
    print(f"\n=== {len(res.registros)} registros parseados ===")
    
    print("\n=== Consolidado por concepto ===")
    cons = res.consolidado_por_concepto()
    print(f"{'Tipo':<10} {'Concepto':<10} {'Empleador':>15} {'Trabajador':>15} {'Total':>15}")
    for tipo, info in sorted(cons.items()):
        print(f"{tipo:<10} {info['concepto_dian'] or '-':<10} "
              f"{info['aporte_empleador']:>15,.2f} "
              f"{info['aporte_trabajador']:>15,.2f} "
              f"{info['aporte_total']:>15,.2f}")
    
    if res.advertencias:
        print(f"\n=== {len(res.advertencias)} advertencias ===")
        for a in res.advertencias[:5]:
            print(f"  ⚠️ {a}")
    
    if res.errores:
        print(f"\n=== {len(res.errores)} errores ===")
        for e in res.errores:
            print(f"  ❌ {e}")
