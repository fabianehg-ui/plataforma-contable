"""
Motor de clasificación v2 — Movimientos contables → formatos DIAN.

Aplica reglas en este orden de prioridad:

  Pre-procesamiento:
    P1. Validación de conciliación cuenta 6 ↔ cuentas 72/73 (cierre/traslado al costo)
        → marca cuentas 6 conciliadas como EXCLUIDAS de F1001
    P2. Indexación de retenciones cuenta 2365 por NIT
        → para asociar como columna del F1001 / F2276 después

  Por cada movimiento:
    1. exogena_mapeo_manual    (override por cuenta+NIT específico)
    2. Reglas especiales:
         - Activos fijos (15xx)        → F5008
         - Inventarios (14xx)          → F5007
         - Cartera clientes (1305-1315)→ F1008
         - Cuenta 6 conciliada         → EXCLUIDA
         - Cuentas F1003 (135515,
           195515, 2408)               → F1003 (con columna correcta)
         - Cuenta 2365 (no salarios)   → NO reporta (se asocia como columna)
         - Cuenta 236525/236505/236510 → NO reporta (asocia a F2276)
         - Cuenta 236555 (exceso)      → resta al F1001 del NIT
         - Cuenta 236599 (traslados)   → NO reporta
    3. exogena_mapeo_empresa   (codificación nativa por rangos)
    4. exogena_puc_generico    (PUC genérico compartido)

Uso típico:
    motor = MotorClasificacion(
        reglas_capa1=puc_generico,
        reglas_capa2=mapeo_empresa,
        reglas_capa3=mapeo_manual,
    )
    resultado = motor.clasificar_balance(movimientos_balance)
    
    # Acceder a resultados:
    resultado.movimientos          # MovimientoClasificado[]
    resultado.sin_resolver         # Movimiento[]
    resultado.conciliacion_costos  # ConciliacionCostos
    resultado.retenciones_por_nit  # dict[nit] -> RetencionAcumulada
    resultado.estadisticas         # dict
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ================================================================
# UTILIDADES
# ================================================================

def cuenta_en_rango(cuenta: str, inicial: str, final: str) -> bool:
    """Cuenta dentro del rango [inicial, final] con padding a 10 chars (0/9)."""
    c = str(cuenta).strip().ljust(10, '0')
    ini = str(inicial).strip().ljust(10, '0')
    fin = str(final).strip().ljust(10, '9')
    return ini <= c <= fin


def _normalize_text(s) -> str:
    """Normaliza texto: minúsculas + sin tildes."""
    if s is None:
        return ''
    s = str(s).strip().lower()
    repl = {'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ñ': 'n'}
    for k, v in repl.items():
        s = s.replace(k, v)
    return s


# ================================================================
# DATACLASSES
# ================================================================

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
    """Override manual (capa 3): cuenta + NIT específico.

    Si excluir=True, la cuenta NO se reporta. En ese caso formato_dian y
    concepto_dian son None y motivo_exclusion debe traer el texto legible
    que aparecerá en la hoja "Cuentas no reportadas" del borrador.
    """
    codigo_cuenta: str
    nit: Optional[str]
    formato_dian: Optional[str]
    concepto_dian: Optional[int]
    nota: str = ''
    id: Optional[int] = None
    excluir: bool = False
    motivo_exclusion: Optional[str] = None


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
    balance_id: Optional[int] = None


@dataclass
class MovimientoClasificado:
    """Resultado de clasificar un movimiento contra una regla."""
    codigo_cuenta: str
    nit: Optional[str]
    formato_dian: str
    concepto_dian: Optional[int]
    valor: float
    base_aplicable: str
    capa_resolucion: str
    regla_id: Optional[int] = None
    requiere_revision: bool = False
    nota: str = ''
    balance_id: Optional[int] = None


@dataclass
class RetencionAcumulada:
    """Retención (cuenta 2365) acumulada por NIT, para asociar como columna del F1001/F2276."""
    nit: str
    f1001_retencion_practicada: float = 0.0   # Cr de 2365 (excepto salarios y excepciones)
    f2276_retencion_salarios: float = 0.0     # Cr de 236505/236510 (salarios)
    exceso_periodos_anteriores: float = 0.0   # Db de 236555 (concepto 5028 aparte)
    detalles: list[str] = field(default_factory=list)


@dataclass
class ConciliacionCostos:
    """Resultado de validar la conciliación cuenta 6 ↔ cuentas 72/73."""
    concilia: bool
    db_cuenta_6: float
    cr_traslado_72_73: float
    diferencia: float
    mayor_72_en_cero: bool
    mayor_73_en_cero: bool
    mayor_72_existe: bool
    mayor_73_existe: bool
    cuentas_6_excluidas: set[str] = field(default_factory=set)
    cuentas_6_con_compras: set[str] = field(default_factory=set)
    detalles_72_73: list[dict] = field(default_factory=list)
    mensaje: str = ''


@dataclass
class ResultadoClasificacion:
    movimientos: list[MovimientoClasificado] = field(default_factory=list)
    sin_resolver: list[Movimiento] = field(default_factory=list)
    estadisticas: dict = field(default_factory=dict)
    conciliacion_costos: Optional[ConciliacionCostos] = None
    retenciones_por_nit: dict = field(default_factory=dict)


# ================================================================
# CONFIGURACIÓN: REGLAS ESPECIALES
# ================================================================

PALABRAS_CLAVE_TRASLADO = ['CIERRE', 'TRASLADO', 'COSTO TRASLADO', 'TRASLADO AL COSTO']
TOLERANCIA_CONCILIACION = 1.0  # $1 peso (centavos por redondeo)

# Subcuentas 2365 que NO reportan (van como columna o no reportan)
SUBCUENTAS_2365_SALARIOS = ['236505', '236510']  # → columna retención F2276
SUBCUENTAS_2365_EXCESO = '236555'                 # → resta del F1001 del NIT
SUBCUENTAS_2365_TRASLADOS = '236599'              # → NO reporta (pago a DIAN)
CONCEPTO_DIAN_EXCESO_AÑO_ANTERIOR = 5028          # F1001 concepto especial

# Cuentas que generan registro propio en F1003 (retenciones a favor)
# IMPORTANTE: estas reglas son fallback genérico cuando no hay regla en capa 2 o 3.
# La capa 2 (mapeo por rangos) y capa 3 (manual) tienen prioridad.
#
# Nota conceptual:
#   - 135515 / 195515: Retefuente que le practicaron a la empresa
#   - 240825: RETEIVA practicado a la empresa (concepto 1309 según Res. DIAN AG 2025)
#   - 240810 NO va aquí: es IVA DESCONTABLE → F1005 (lo manejan capa 1/2)
#   - 2408 (raíz) se quitó porque es ambiguo con 240810 / 240815 / 240825 etc.
CUENTAS_F1003 = {
    '135515': {'columna': 'debitos_netos', 'descripcion': 'Retefuente activo'},
    '195515': {'columna': 'debitos_netos', 'descripcion': 'Retefuente diferido (Db - Cr)'},
    '240825': {'columna': 'creditos', 'descripcion': 'ReteIVA practicado a la empresa'},
}

# Por formato, qué columna del balance se usa para el valor
BASE_POR_FORMATO = {
    '1001': 'debitos',
    '1003': 'creditos',
    '1004': 'saldo_final',
    '1005': 'debitos',
    '1006': 'creditos',
    '1007': 'creditos',
    '1008': 'saldo_final',
    '1009': 'saldo_final',
    '1010': 'saldo_final',
    '1011': 'debitos',
    '1012': 'saldo_final',
    '1056': 'debitos',
    '1647': 'creditos',
    '2275': 'creditos',
    '2276': 'debitos',
    '2278': 'debitos',
    '5253': 'saldo_final',
    '5007': 'debitos_netos',
    '5008': 'debitos_netos',
}


# ================================================================
# DETECTORES DE FAMILIAS DE CUENTAS
# ================================================================

def _es_cuenta_activos_fijos(codigo_cuenta: str, nombre_cuenta: str) -> bool:
    """Detecta cuentas de activos fijos (15xx) excluyendo depreciación."""
    cuenta = str(codigo_cuenta).strip()
    if not cuenta.startswith('15'):
        return False
    nombre_norm = _normalize_text(nombre_cuenta)
    palabras_excluir = ['depreciacion', 'amortizacion', 'agotamiento', 'desvalorizacion', 'provision']
    return not any(p in nombre_norm for p in palabras_excluir)


def _es_cuenta_inventario_compra(codigo_cuenta: str, nombre_cuenta: str) -> bool:
    """Detecta cuentas de inventario (14xx) excluyendo traslados/transferencias."""
    cuenta = str(codigo_cuenta).strip()
    if not cuenta.startswith('14'):
        return False
    nombre_norm = _normalize_text(nombre_cuenta)
    palabras_excluir = ['traslado', 'transferencia', 'bodega']
    return not any(p in nombre_norm for p in palabras_excluir)


def _es_cuenta_cartera_1008(codigo_cuenta: str) -> bool:
    """Detecta cuentas de cartera que van al formato 1008 (1305 a 1315)."""
    cuenta = str(codigo_cuenta).strip()
    if not cuenta.startswith('13') or len(cuenta) < 4:
        return False
    try:
        prefijo = int(cuenta[:4])
        return 1305 <= prefijo <= 1315
    except (ValueError, TypeError):
        return False


def _es_cuenta_f1003(codigo_cuenta: str) -> Optional[dict]:
    """Detecta si una cuenta genera registro propio en F1003. Retorna config o None."""
    cuenta = str(codigo_cuenta).strip()
    for prefijo, config in CUENTAS_F1003.items():
        if cuenta.startswith(prefijo):
            return {'prefijo': prefijo, **config}
    return None


def _es_cuenta_2365(codigo_cuenta: str) -> bool:
    """Cualquier subcuenta 2365 (retenciones que practicó la empresa)."""
    return str(codigo_cuenta).strip().startswith('2365')


def _es_2365_salarios(codigo_cuenta: str) -> bool:
    """Subcuentas de retefuente sobre salarios."""
    cuenta = str(codigo_cuenta).strip()
    return any(cuenta.startswith(s) for s in SUBCUENTAS_2365_SALARIOS)


def _es_2365_exceso(codigo_cuenta: str) -> bool:
    return str(codigo_cuenta).strip().startswith(SUBCUENTAS_2365_EXCESO)


def _es_2365_traslados(codigo_cuenta: str) -> bool:
    return str(codigo_cuenta).strip().startswith(SUBCUENTAS_2365_TRASLADOS)


def _es_cuenta_2273_excluida(codigo_cuenta: str) -> bool:
    """
    Excluye cualquier cuenta 2273xx (Obligaciones laborales / Provisiones
    para obligaciones laborales) del reporte a la DIAN.

    El grupo 2273 del PUC corresponde a provisiones para obligaciones
    laborales (cesantías por pagar consolidadas, etc.). Por su naturaleza
    son causaciones contables, no pagos efectivos a terceros, y por
    convención de Quinto Sentido NO se reportan a la DIAN.

    Cualquier subcuenta de 2273xx queda excluida sin revisar el nombre.
    """
    return str(codigo_cuenta).strip().startswith('2273')


def _es_cuenta_traslado_excluida(codigo_cuenta: str, nombre_cuenta: str) -> bool:
    """
    Detecta cuentas de traslado interno que NO se reportan en NINGÚN formato.

    Aplica únicamente a los grupos donde un traslado interno carece de tercero
    real (movimiento contable entre cuentas de la propia empresa):
      - 14xxxx  Inventarios
      - 2408xx  IVA descontable / generado
      - 2365xx  Retenciones practicadas

    En esos grupos, si el nombre contiene la palabra "traslado" (insensible a
    mayúsculas y acentos), el movimiento se descarta del reporte.

    No aplica a cuentas de gasto/costo (5xxx/6xxx/7xxx), cartera (13xx),
    proveedores (22xx, 23xx) ni activos fijos (15xx) aunque mencionen
    "traslado" — esas suelen referirse a servicios reales prestados por
    terceros y deben conservarse.
    """
    cuenta = str(codigo_cuenta).strip()
    en_grupo = (
        cuenta.startswith('14')
        or cuenta.startswith('2408')
        or cuenta.startswith('2365')
    )
    if not en_grupo:
        return False
    nombre_norm = _normalize_text(nombre_cuenta)
    return 'traslado' in nombre_norm


def _es_cuenta_provision_excluida(nombre_cuenta: str) -> bool:
    """
    Detecta cuentas de PROVISIÓN contable que NO se reportan en ningún formato.

    Las provisiones son causaciones contables (no pagos efectivos a terceros),
    por lo que no constituyen información reportable a la DIAN.

    Regla:
      - Si el nombre contiene 'provision' o 'prov' → EXCLUIR
      - EXCEPCIÓN: si el nombre contiene 'proveedor' → NO excluir
        (los pagos a proveedores sí se reportan)

    Ejemplos:
      'PROV CESANTIAS'           → excluir
      'PROVISION ARL'            → excluir
      'PROV VACACIONES'          → excluir
      'PROVEEDORES'              → NO excluir
      'PROVEEDORES NACIONALES'   → NO excluir

    Aplica a cualquier grupo PUC porque las provisiones contables pueden
    aparecer en distintos códigos según convención de cada empresa.
    """
    nombre_norm = _normalize_text(nombre_cuenta)
    if not nombre_norm:
        return False
    # Si menciona 'proveedor', es cuenta de tercero real, no provisión.
    if 'proveedor' in nombre_norm:
        return False
    # Limpiar puntuación pegada al texto (comillas, comas, puntos, etc.).
    # Algunos exports de balance traen nombres como '"""PROVISION CAJAS, ...'
    # con comillas o comas pegadas que rompen el split por espacios.
    nombre_limpio = nombre_norm.translate(str.maketrans('', '', '"\'`,.;:()[]{}'))
    # Detectar 'provision' o la abreviatura 'prov' como palabra independiente.
    # Buscar como token (rodeada de espacios o al inicio) para evitar falsos
    # positivos de palabras que contengan 'prov' por casualidad.
    tokens = nombre_limpio.split()
    return any(t == 'prov' or t.startswith('provision') for t in tokens)


def _concepto_f2276_pasivo_prestacion(codigo_cuenta: str) -> Optional[int]:
    """
    Detecta cuentas de PASIVO POR PRESTACIONES SOCIALES cuyos DÉBITOS del
    año (los pagos efectivamente realizados al empleado) deben reportarse
    en F2276, además de su saldo final que va a F1009.

    Esto resuelve el caso de DOBLE REPORTE:
      - Saldo final del pasivo  → F1009 (cuánto falta pagar al cierre)
      - Débitos del año         → F2276 (cuánto se pagó al empleado)

    Mapeo según convención de Quinto Sentido (concepto F2276 v4):
      - 2510xx  Cesantías al fondo            → concepto 26 'ceco'
      - 2515xx  Intereses sobre cesantías     → concepto 25 'cein'
      - 2525xx  Vacaciones consolidadas       → concepto 24 'potro'
      - 253005xx Cesantías por pagar          → concepto 25 'cein'
      - 253010xx Intereses cesantías por pagar → concepto 25 'cein'
      - 253015xx Vacaciones por pagar (QS)    → concepto 24 'potro'
      - 253020xx Prima servicios por pagar (QS) → concepto 19 'papre'

    Nota: la convención QS invierte el PUC estándar (en QS 253015=vacaciones
    y 253020=prima de servicios). Las reglas en BD ya están alineadas a esa
    convención. Esta función es solo backup defensivo cuando capa 2 (mapeo
    nativo) gana sobre capa 1 e impide que la regla F2276 se aplique.

    Retorna el número de concepto F2276 o None si la cuenta no califica.
    """
    cuenta = str(codigo_cuenta).strip()
    if not cuenta:
        return None
    # Por prefijo de cuenta (los más específicos primero)
    if cuenta.startswith('253020'):
        return 19  # papre - prima de servicios pagada (convención QS)
    if cuenta.startswith('253015'):
        return 24  # potro - vacaciones pagadas (convención QS)
    if cuenta.startswith('253010'):
        return 25  # cein - intereses cesantías pagados
    if cuenta.startswith('253005'):
        return 25  # cein - cesantías pagadas
    if cuenta.startswith('2525'):
        return 24  # potro - vacaciones consolidadas pagadas
    if cuenta.startswith('2515'):
        return 25  # cein - intereses cesantías consolidados pagados
    if cuenta.startswith('2510'):
        return 26  # ceco - cesantías al fondo pagadas
    return None


def _es_deduccion_trabajador_f2276(
    codigo_cuenta: str, nombre_cuenta: str
) -> Optional[int]:
    """
    Detecta cuentas que representan deducciones del SALARIO DEL TRABAJADOR
    (la parte que la empresa descuenta y gira a EPS / Fondos de Pensión).

    Estas cuentas reportan en F2276 con concepto:
      - 30 'apos': aporte salud DEL TRABAJADOR  (rango 25500x — EPS)
      - 31 'apof': aporte pensión DEL TRABAJADOR (rango 25502x — Fondos)

    Retorna el número de concepto (30 o 31) si aplica, o None si no.

    Detección por nombre (insensible a mayúsculas/acentos/puntuación):
      - 'DEDUCCION A EMPLEADO' / 'DEDUCCION A EMPLEADOS'
      - 'DEDUCCION AL TRABAJADOR' / 'DEDUCCION A TRABAJADORES'

    Distinción salud vs pensión por código de cuenta (PUC estándar):
      - 25500x → salud (EPS)        → concepto 30
      - 25502x → pensión (Fondos)   → concepto 31

    Si el nombre coincide pero el código no está en los rangos esperados,
    retorna None y la cuenta sigue su flujo normal (capa 2 / capa 1).
    """
    nombre_norm = _normalize_text(nombre_cuenta)
    if not nombre_norm:
        return None
    # Limpiar puntuación pegada al texto.
    nombre_limpio = nombre_norm.translate(
        str.maketrans('', '', '"\'`,.;:()[]{}')
    )
    # Patrones aceptados (palabras 'a/al' + 'empleado(s)/trabajador(es)')
    es_deduccion = (
        'deduccion a empleado' in nombre_limpio
        or 'deduccion al empleado' in nombre_limpio
        or 'deduccion a trabajador' in nombre_limpio
        or 'deduccion al trabajador' in nombre_limpio
    )
    if not es_deduccion:
        return None
    # Distinguir salud vs pensión por código de cuenta
    cuenta = str(codigo_cuenta).strip()
    if cuenta.startswith('255005'):
        return 30  # apos - salud trabajador
    if cuenta.startswith('255020'):
        return 31  # apof - pensión trabajador
    # Nombre coincide pero código no está en rango — devolver None
    # para no forzar un mapeo incorrecto. La cuenta seguirá su flujo
    # normal y caerá en capa 2 / 1 según corresponda.
    return None


def _nombre_dice_compras(nombre_cuenta: str) -> bool:
    """Detecta si el nombre de una cuenta menciona explícitamente 'compras'."""
    return 'compra' in _normalize_text(nombre_cuenta)


def _nombre_dice_traslado_costo(nombre_cuenta: str) -> bool:
    """Detecta si el nombre contiene CIERRE / TRASLADO / COSTO TRASLADO / TRASLADO AL COSTO."""
    n = (nombre_cuenta or '').upper().strip()
    return any(p in n for p in PALABRAS_CLAVE_TRASLADO)


# ================================================================
# CONCILIACIÓN CUENTA 6 ↔ CUENTAS 72/73
# ================================================================

def validar_conciliacion_costos_traslado(movimientos: list[Movimiento]) -> ConciliacionCostos:
    """
    Valida que las cuentas mayores 72 y 73 estén en cero y que sus créditos de
    cierre/traslado al costo concilien con los débitos de la cuenta 6 (no compras).

    Cuando concilia, las cuentas 6 (que no digan "compra") se EXCLUYEN del F1001
    porque son resultado de traslado interno desde 7xxx/14xx — sus terceros
    reales ya están en las cuentas 7xxx.
    """
    # 1. Validar mayor 72 y mayor 73 en cero
    db_72 = sum(m.debitos for m in movimientos if str(m.codigo_cuenta).strip() == '72')
    cr_72 = sum(m.creditos for m in movimientos if str(m.codigo_cuenta).strip() == '72')
    db_73 = sum(m.debitos for m in movimientos if str(m.codigo_cuenta).strip() == '73')
    cr_73 = sum(m.creditos for m in movimientos if str(m.codigo_cuenta).strip() == '73')

    mayor_72_existe = any(str(m.codigo_cuenta).strip() == '72' for m in movimientos)
    mayor_73_existe = any(str(m.codigo_cuenta).strip() == '73' for m in movimientos)
    mayor_72_en_cero = (not mayor_72_existe) or (abs(db_72 - cr_72) <= TOLERANCIA_CONCILIACION)
    mayor_73_en_cero = (not mayor_73_existe) or (abs(db_73 - cr_73) <= TOLERANCIA_CONCILIACION)

    # 2. Identificar cuentas 6 (SOLO hojas — sin doble conteo entre agregadores y detalle)
    codigos_existentes = {str(m.codigo_cuenta).strip() for m in movimientos}

    def es_hoja(codigo: str) -> bool:
        """Una cuenta es hoja si no hay otra que la prefije."""
        return not any(
            c != codigo and c.startswith(codigo) and len(c) > len(codigo)
            for c in codigos_existentes
        )

    db_cuenta_6 = 0.0
    cuentas_6_excluibles = set()
    cuentas_6_con_compras = set()
    cuentas_6_procesadas_para_suma = set()

    for m in movimientos:
        cta = str(m.codigo_cuenta).strip()
        if not cta.startswith('6') or len(cta) <= 1:
            continue
        if not es_hoja(cta):
            continue  # saltar agregadores (no son movimientos reales)
        nombre = m.nombre_cuenta or ''
        if _nombre_dice_compras(nombre):
            cuentas_6_con_compras.add(cta)
        else:
            cuentas_6_excluibles.add(cta)
            # Sumar la cuenta solo una vez. Para evitar doble conteo entre
            # totalizador (sin NIT) y movimientos (con NIT) del mismo código,
            # preferimos los movimientos con NIT. Si no hay, usamos los sin NIT.
            if cta not in cuentas_6_procesadas_para_suma:
                cuentas_6_procesadas_para_suma.add(cta)
                con_nit = [mm for mm in movimientos
                           if str(mm.codigo_cuenta).strip() == cta and mm.nit]
                sin_nit = [mm for mm in movimientos
                           if str(mm.codigo_cuenta).strip() == cta and not mm.nit]
                if con_nit:
                    db_cuenta_6 += sum(mm.debitos for mm in con_nit)
                else:
                    db_cuenta_6 += sum(mm.debitos for mm in sin_nit)

    # 3. Sumar Cr de cuentas 72/73 con palabras clave (sin doble conteo)

    cr_traslado = 0.0
    detalles_72_73 = []
    cuentas_traslado_procesadas = set()

    for m in movimientos:
        cta = str(m.codigo_cuenta).strip()
        if not (cta.startswith('72') or cta.startswith('73')) or len(cta) <= 2:
            continue
        if not _nombre_dice_traslado_costo(m.nombre_cuenta):
            continue
        if not es_hoja(cta):
            continue
        # Una vez por cuenta (sumando solo el primer movimiento que la representa)
        if cta in cuentas_traslado_procesadas:
            continue
        cuentas_traslado_procesadas.add(cta)
        # Para evitar doble conteo: preferir filas con NIT, si no hay usar sin NIT
        con_nit = [mm for mm in movimientos
                   if str(mm.codigo_cuenta).strip() == cta and mm.nit]
        sin_nit = [mm for mm in movimientos
                   if str(mm.codigo_cuenta).strip() == cta and not mm.nit]
        if con_nit:
            cr_codigo = sum(mm.creditos for mm in con_nit)
        else:
            cr_codigo = sum(mm.creditos for mm in sin_nit)
        cr_traslado += cr_codigo
        detalles_72_73.append({
            'codigo': cta,
            'nombre': m.nombre_cuenta,
            'creditos': cr_codigo,
        })

    # 4. Determinar conciliación
    diferencia = abs(db_cuenta_6 - cr_traslado)
    concilia = (
        diferencia <= TOLERANCIA_CONCILIACION
        and mayor_72_en_cero
        and mayor_73_en_cero
        and len(cuentas_6_excluibles) > 0
    )

    if concilia:
        mensaje = (
            f'✅ Cuentas 6 trasladadas internamente desde 72/73 — excluidas de F1001 '
            f'(${cr_traslado:,.2f}). Cuentas excluidas: {len(cuentas_6_excluibles)}'
        )
    elif len(cuentas_6_excluibles) == 0:
        mensaje = '✅ No hay cuentas 6 sin "compras" — todo va a F1001'
        cuentas_6_excluibles = set()
    else:
        mensaje = (
            f'❌ NO concilia: Db cuenta 6 ${db_cuenta_6:,.2f} ≠ Cr traslado ${cr_traslado:,.2f}. '
            f'Mayor 72 cero: {mayor_72_en_cero}, Mayor 73 cero: {mayor_73_en_cero}. '
            f'Las cuentas 6 se mantienen en F1001 — REVISAR MANUALMENTE.'
        )
        cuentas_6_excluibles = set()  # No excluir si no concilia

    return ConciliacionCostos(
        concilia=concilia,
        db_cuenta_6=db_cuenta_6,
        cr_traslado_72_73=cr_traslado,
        diferencia=diferencia,
        mayor_72_en_cero=mayor_72_en_cero,
        mayor_73_en_cero=mayor_73_en_cero,
        mayor_72_existe=mayor_72_existe,
        mayor_73_existe=mayor_73_existe,
        cuentas_6_excluidas=cuentas_6_excluibles,
        cuentas_6_con_compras=cuentas_6_con_compras,
        detalles_72_73=detalles_72_73,
        mensaje=mensaje,
    )


# ================================================================
# INDEXACIÓN DE RETENCIONES (cuenta 2365)
# ================================================================

def indexar_retenciones_2365(movimientos: list[Movimiento]) -> dict[str, RetencionAcumulada]:
    """
    Indexa las retenciones de la cuenta 2365 por NIT del tercero retenido.

    La cuenta 2365 NO genera registro propio. Su valor se asocia como columna
    al pago/salario correspondiente del mismo NIT en F1001 / F2276.

    Reglas:
      - 236505 / 236510 (salarios)        → suma a f2276_retencion_salarios
      - 236555 (exceso)                   → débitos van a exceso_periodos_anteriores
                                            (concepto 5028 en F1001)
      - 236599 (traslados a DIAN)         → NO se acumula (es pago)
      - resto (236520, 236525, etc.)      → suma a f1001_retencion_practicada
    """
    indice: dict[str, RetencionAcumulada] = {}

    for m in movimientos:
        cta = str(m.codigo_cuenta).strip()
        if not _es_cuenta_2365(cta) or not m.nit:
            continue

        # Excluir traslados (pagos a DIAN)
        if _es_2365_traslados(cta):
            continue

        nit = str(m.nit).strip()
        if nit not in indice:
            indice[nit] = RetencionAcumulada(nit=nit)
        retenciones = indice[nit]

        if _es_2365_exceso(cta):
            # 236555 - Retenciones practicadas en exceso (Db netos)
            retenciones.exceso_periodos_anteriores += (m.debitos - m.creditos)
            retenciones.detalles.append(
                f'{cta} {m.nombre_cuenta} (exceso): Db ${m.debitos:,.2f}'
            )
        elif _es_2365_salarios(cta):
            # 236505 / 236510 — retención sobre salarios → F2276
            retenciones.f2276_retencion_salarios += m.creditos
            retenciones.detalles.append(
                f'{cta} {m.nombre_cuenta} (salarios): Cr ${m.creditos:,.2f}'
            )
        else:
            # Resto: 236520, 236525, 236530, 236540, 236545, etc. → F1001
            retenciones.f1001_retencion_practicada += m.creditos
            retenciones.detalles.append(
                f'{cta} {m.nombre_cuenta}: Cr ${m.creditos:,.2f}'
            )

    return indice


def detectar_mayores_pasivos_cerrados(
    movimientos: list[Movimiento],
) -> set[str]:
    """
    Detecta los códigos de mayor de pasivos (4 dígitos) que CIERRAN EN CERO
    al final del año, mirando la suma de saldos finales de TODAS las
    subcuentas que comparten ese prefijo.

    Aplica solamente a los grupos `2365`, `2367` y `2369` del PUC. Si la
    suma de saldos finales de las subcuentas suma aproximadamente cero
    (dentro de la tolerancia de conciliación), todas esas subcuentas se
    excluyen del F1009 porque el pasivo en realidad ya fue cancelado al
    cierre del periodo.

    Caso típico (Quinto Sentido AG2025):
        23690199 TRASLADO         +$9,870,000
        23690101 AUTORRENTA 1.10% -$2,070,000
        23690102 AUTORRETENCION   -$7,800,000
                                  ───────────
        Saldo neto del mayor 2369:        $0   →  todas excluidas

    Returns:
        set[str] con los prefijos de mayor que cierran en cero
        (p.ej. {'2369'}). Si ningún mayor cierra en cero, set vacío.
    """
    prefijos_a_revisar = ('2365', '2367', '2369')
    saldos_por_mayor: dict[str, float] = {p: 0.0 for p in prefijos_a_revisar}
    existe: dict[str, bool] = {p: False for p in prefijos_a_revisar}

    for m in movimientos:
        cta = str(m.codigo_cuenta).strip()
        for prefijo in prefijos_a_revisar:
            # Solo subcuentas (más de 4 dígitos), no la raíz misma
            if cta.startswith(prefijo) and len(cta) > 4:
                saldos_por_mayor[prefijo] += float(m.saldo_final or 0)
                existe[prefijo] = True
                break

    cerrados = set()
    for prefijo in prefijos_a_revisar:
        if existe[prefijo] and abs(saldos_por_mayor[prefijo]) <= TOLERANCIA_CONCILIACION:
            cerrados.add(prefijo)

    return cerrados


# ================================================================
# REGLA ESPECIAL: aplicar cálculos especiales por familia de cuenta
# ================================================================

def aplicar_regla_especial(
    mov: Movimiento,
    cuentas_6_excluidas: set[str] = None,
) -> Optional[MovimientoClasificado]:
    """
    Aplica las reglas especiales de cálculo si la cuenta corresponde.

    Returns:
        MovimientoClasificado si aplica una regla especial, None en otro caso.
    """
    cuenta = str(mov.codigo_cuenta).strip()
    nombre = mov.nombre_cuenta or ''
    cuentas_6_excluidas = cuentas_6_excluidas or set()

    # 0. Cuenta 6 excluida por conciliación con traslado 72/73
    if cuenta in cuentas_6_excluidas:
        return MovimientoClasificado(
            codigo_cuenta=cuenta, nit=mov.nit,
            formato_dian='EXCLUIDO',
            concepto_dian=None,
            valor=mov.debitos,
            base_aplicable='ninguna',
            capa_resolucion='regla_especial_costos_traslado_conciliado',
            requiere_revision=False,
            nota='Cuenta 6 conciliada con traslado 72/73 (mayor=0, Cr traslado=Db cuenta 6)',
            balance_id=mov.balance_id,
        )

    # 0b. Cuenta 2365 — NO reporta como movimiento (se asocia como columna)
    if _es_cuenta_2365(cuenta):
        if _es_2365_traslados(cuenta):
            nota = 'Cuenta 236599 (traslados a DIAN): pago, no se reporta'
        elif _es_2365_exceso(cuenta):
            nota = f'Cuenta 236555 (exceso): se asocia al F1001 del NIT como menor valor o concepto {CONCEPTO_DIAN_EXCESO_AÑO_ANTERIOR}'
        elif _es_2365_salarios(cuenta):
            nota = 'Cuenta 2365 (salarios): se asocia como columna retención del F2276 del NIT'
        else:
            nota = 'Cuenta 2365 (no salarios): se asocia como columna retención del F1001 del NIT'
        return MovimientoClasificado(
            codigo_cuenta=cuenta, nit=mov.nit,
            formato_dian='COLUMNA_RETENCION',
            concepto_dian=None,
            valor=mov.creditos if not _es_2365_exceso(cuenta) else mov.debitos,
            base_aplicable='ninguna',
            capa_resolucion='regla_especial_2365_columna',
            requiere_revision=False,
            nota=nota,
            balance_id=mov.balance_id,
        )

    # 1. F1003 — cuentas que le practicaron retención a la empresa
    config_f1003 = _es_cuenta_f1003(cuenta)
    if config_f1003:
        if config_f1003['columna'] == 'debitos_netos':
            valor = mov.debitos - mov.creditos
        elif config_f1003['columna'] == 'creditos':
            valor = mov.creditos - mov.debitos
        else:
            valor = mov.debitos
        # Solo reportar si hay valor neto positivo
        if valor > 0:
            return MovimientoClasificado(
                codigo_cuenta=cuenta, nit=mov.nit,
                formato_dian='1003',
                concepto_dian=None,
                valor=abs(valor),
                base_aplicable=config_f1003['columna'],
                capa_resolucion='regla_especial_f1003',
                requiere_revision=False,
                nota=f'F1003 {config_f1003["descripcion"]}: {config_f1003["columna"]} = ${valor:,.2f}',
                balance_id=mov.balance_id,
            )
        return None

    # 2. Activos fijos → F1001 / 5008
    if _es_cuenta_activos_fijos(cuenta, nombre):
        valor = mov.debitos - mov.creditos
        if valor > 0:
            return MovimientoClasificado(
                codigo_cuenta=cuenta, nit=mov.nit,
                formato_dian='1001', concepto_dian=5008,
                valor=abs(valor),
                base_aplicable='debitos_menos_creditos',
                capa_resolucion='regla_especial_activos_fijos',
                requiere_revision=False,
                nota='Activos fijos: débitos - créditos (excluye depreciación)',
                balance_id=mov.balance_id,
            )
        return None

    # 3. Inventarios → F1001 / 5007
    if _es_cuenta_inventario_compra(cuenta, nombre):
        valor = mov.debitos - mov.creditos
        if valor > 0:
            return MovimientoClasificado(
                codigo_cuenta=cuenta, nit=mov.nit,
                formato_dian='1001', concepto_dian=5007,
                valor=abs(valor),
                base_aplicable='debitos_menos_creditos',
                capa_resolucion='regla_especial_inventarios',
                requiere_revision=False,
                nota='Inventarios: débitos - créditos (excluye traslados)',
                balance_id=mov.balance_id,
            )
        return None

    # 4. Cartera clientes (1305-1315) → F1008
    if _es_cuenta_cartera_1008(cuenta):
        valor = mov.debitos - mov.creditos
        if valor != 0:
            return MovimientoClasificado(
                codigo_cuenta=cuenta, nit=mov.nit,
                formato_dian='1008', concepto_dian=None,
                valor=abs(valor),
                base_aplicable='debitos_menos_creditos',
                capa_resolucion='regla_especial_cartera',
                requiere_revision=False,
                nota='Cartera clientes (1305-1315): saldo por cobrar',
                balance_id=mov.balance_id,
            )
        return None

    return None


# ================================================================
# MOTOR
# ================================================================

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

        # Índices para búsqueda O(1)
        self._capa1_por_codigo: dict[str, list[ReglaCapa1]] = {}
        for r in reglas_capa1:
            self._capa1_por_codigo.setdefault(r.codigo_cuenta, []).append(r)

        self._capa3_por_cuenta_nit: dict[tuple, list[ReglaCapa3]] = {}
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
        """Capa 3: override manual. Prioridad: (cuenta+nit) > (cuenta solo)."""
        if nit:
            r = self._capa3_por_cuenta_nit.get((cuenta, nit))
            if r:
                return r
        return self._capa3_por_cuenta.get(cuenta, [])

    def _buscar_capa2(self, cuenta: str) -> list[ReglaCapa2]:
        """Capa 2: mapeo nativo por rango. Devuelve todas las que aplican."""
        return [
            r for r in self.reglas_capa2
            if cuenta_en_rango(cuenta, r.cuenta_inicial, r.cuenta_final)
        ]

    def _buscar_capa1(self, cuenta: str) -> list[ReglaCapa1]:
        """Capa 1: PUC genérico. Coincidencia exacta o por prefijo más largo."""
        # Coincidencia exacta
        if cuenta in self._capa1_por_codigo:
            return self._capa1_por_codigo[cuenta]
        # Búsqueda por prefijo (el más largo gana)
        mejor: list[ReglaCapa1] = []
        mejor_len = 0
        for codigo_regla in self._capa1_por_codigo:
            if cuenta.startswith(codigo_regla) and len(codigo_regla) > mejor_len:
                mejor = self._capa1_por_codigo[codigo_regla]
                mejor_len = len(codigo_regla)
        return mejor

    def _valor_para_formato(self, mov: Movimiento, formato: str) -> tuple[float, str]:
        """Determina qué columna del balance usar según el formato."""
        base = BASE_POR_FORMATO.get(formato, 'debitos')
        if base == 'debitos':
            return (mov.debitos, 'debitos')
        if base == 'creditos':
            return (mov.creditos, 'creditos')
        if base == 'saldo_final':
            return (mov.saldo_final, 'saldo_final')
        if base == 'debitos_netos':
            return (mov.debitos - mov.creditos, 'debitos_netos')
        return (mov.debitos, 'debitos')

    # ----------------------------------------------------------------
    # Clasificación de un movimiento individual
    # ----------------------------------------------------------------
    def clasificar_movimiento(
        self,
        mov: Movimiento,
        cuentas_6_excluidas: set[str] = None,
        mayores_cerrados: set[str] = None,
    ) -> list[MovimientoClasificado]:
        """Clasifica un movimiento aplicando las capas en orden de prioridad."""
        resultados: list[MovimientoClasificado] = []
        cuentas_6_excluidas = cuentas_6_excluidas or set()
        mayores_cerrados = mayores_cerrados or set()

        # GUARD: cuentas de pasivos cuyo MAYOR (2365/2367/2369) cierra en
        # cero al final del año. Por convención contable, si el saldo neto
        # del mayor es cero, las subcuentas se entienden ya canceladas y
        # no se reportan en F1009 (saldo final del pasivo).
        # No aplica a 2365/2367/2369 que tienen otras reglas especiales
        # (retenciones que se asocian como columna), pero esas reglas se
        # ejecutan más adelante. Aquí solo aplicamos para el reporte F1009.
        cuenta_str_inicio = str(mov.codigo_cuenta).strip()
        prefijo_4 = cuenta_str_inicio[:4] if len(cuenta_str_inicio) >= 4 else ''
        if prefijo_4 in mayores_cerrados and len(cuenta_str_inicio) > 4:
            # La cuenta 2365xx tiene tratamiento especial (columna retención)
            # que NO debe ser bloqueado por este guard. Solo bloqueamos para
            # 2367 y 2369 que sí van a F1009 normalmente.
            if prefijo_4 in ('2367', '2369'):
                resultados.append(MovimientoClasificado(
                    codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
                    formato_dian='', concepto_dian=None,
                    valor=abs(mov.saldo_final or 0),
                    base_aplicable='',
                    capa_resolucion='excluido_mayor_cerrado',
                    requiere_revision=False,
                    nota=(
                        f'🚫 Mayor {prefijo_4} cierra en cero al final del año: '
                        f'subcuenta no se reporta en F1009'
                    ),
                    balance_id=mov.balance_id,
                ))
                return resultados

        # GUARD UNIVERSAL: cuentas de traslado interno (inventarios, IVA, ret.
        # practicadas) NO se reportan en ningún formato. Se documentan como
        # excluidas por regla universal para que aparezcan en el dictamen
        # con su motivo, sin contar contra ningún concepto DIAN.
        if _es_cuenta_traslado_excluida(mov.codigo_cuenta, mov.nombre_cuenta or ''):
            resultados.append(MovimientoClasificado(
                codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
                formato_dian='', concepto_dian=None,
                valor=abs(mov.debitos or mov.creditos or mov.saldo_final),
                base_aplicable='',
                capa_resolucion='excluido_traslado_universal',
                requiere_revision=False,
                nota='🚫 Traslado interno (14/2408/2365): no se reporta a la DIAN',
                balance_id=mov.balance_id,
            ))
            return resultados

        # GUARD UNIVERSAL: cuentas 2273xx (Obligaciones laborales /
        # provisiones para obligaciones laborales). Por convención, todas
        # las subcuentas de 2273 se excluyen del reporte a la DIAN, sin
        # importar el nombre. Son causaciones contables del pasivo laboral.
        if _es_cuenta_2273_excluida(mov.codigo_cuenta):
            resultados.append(MovimientoClasificado(
                codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
                formato_dian='', concepto_dian=None,
                valor=abs(mov.debitos or mov.creditos or mov.saldo_final),
                base_aplicable='',
                capa_resolucion='excluido_2273_universal',
                requiere_revision=False,
                nota='🚫 Cuenta 2273xx (obligaciones laborales / provisiones): no se reporta a la DIAN',
                balance_id=mov.balance_id,
            ))
            return resultados

        # GUARD UNIVERSAL: cuentas de PROVISIÓN contable. Las provisiones son
        # causaciones, no pagos efectivos a terceros, por lo que no se reportan
        # a la DIAN. Se excluye si el nombre contiene 'prov' o 'provision',
        # excepto si contiene 'proveedor' (esos sí son pagos reales).
        if _es_cuenta_provision_excluida(mov.nombre_cuenta or ''):
            resultados.append(MovimientoClasificado(
                codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
                formato_dian='', concepto_dian=None,
                valor=abs(mov.debitos or mov.creditos or mov.saldo_final),
                base_aplicable='',
                capa_resolucion='excluido_provision_universal',
                requiere_revision=False,
                nota='🚫 Provisión contable: causación, no pago efectivo. No se reporta a la DIAN',
                balance_id=mov.balance_id,
            ))
            return resultados

        # GUARD: DEDUCCION A EMPLEADO/TRABAJADOR → F2276 conceptos 30/31.
        # Las cuentas que en el balance dicen "DEDUCCION A EMPLEADO/TRABAJADOR"
        # representan los aportes a salud/pensión que la empresa descuenta del
        # salario del trabajador para girar al sistema. Estos pagos van al
        # F2276 (no al F1009 que sería pasivo de la empresa).
        #   - Subcuenta 25500x (EPS)    → concepto 30 'apos' (salud trabajador)
        #   - Subcuenta 25502x (Fondos) → concepto 31 'apof' (pensión trabajador)
        # Se aplica este guard antes de capa 3 / capa 2 para que tenga
        # precedencia sobre cualquier mapeo amplio que las lleve a F1009.
        concepto_deduccion = _es_deduccion_trabajador_f2276(
            mov.codigo_cuenta, mov.nombre_cuenta or ''
        )
        if concepto_deduccion is not None:
            # F2276 reporta el monto efectivamente girado a EPS / Fondo, que es
            # el lado DÉBITO de la cuenta (cuando la empresa paga al sistema).
            # Si por alguna razón los débitos vienen en cero, usamos créditos
            # como aproximación (lo descontado al empleado), pero NUNCA el
            # saldo final, que daría valores incorrectos al cierre.
            valor_reportar = abs(mov.debitos) if mov.debitos else abs(mov.creditos)
            if valor_reportar <= 0:
                # Sin valor del periodo: no se reporta a F2276
                return resultados
            resultados.append(MovimientoClasificado(
                codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
                formato_dian='2276',
                concepto_dian=concepto_deduccion,
                valor=valor_reportar,
                base_aplicable='debitos',
                capa_resolucion='deduccion_trabajador_f2276',
                requiere_revision=False,
                nota=(
                    f'Deducción trabajador → F2276 concepto {concepto_deduccion} '
                    f'({"salud (apos)" if concepto_deduccion == 30 else "pensión (apof)"})'
                ),
                balance_id=mov.balance_id,
            ))
            return resultados

        # GUARD DE DOBLE REPORTE: pasivos de prestaciones sociales.
        # Las cuentas 2510, 2515, 2525, 25300x, 25301x, 25302x se reportan
        # en DOS formatos:
        #   - F1009 con su saldo final (lo que falta pagar)
        #   - F2276 con sus débitos del año (lo efectivamente pagado al empleado)
        # Este guard se ejecuta a la PAR (sin return) para que capa 2 después
        # reporte normalmente el saldo final en F1009.
        # Solo agrega el movimiento F2276 si hay débitos > 0 en el año.
        concepto_pasivo = _concepto_f2276_pasivo_prestacion(mov.codigo_cuenta)
        if concepto_pasivo is not None and mov.debitos and mov.debitos > 0:
            descripcion_concepto = {
                19: 'papre - prestaciones sociales pagadas',
                24: 'potro - otros pagos (vacaciones)',
                25: 'cein - cesantías + intereses pagados al empleado',
                26: 'ceco - cesantías consignadas al fondo',
            }.get(concepto_pasivo, f'concepto {concepto_pasivo}')
            resultados.append(MovimientoClasificado(
                codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
                formato_dian='2276',
                concepto_dian=concepto_pasivo,
                valor=abs(mov.debitos),
                base_aplicable='debitos',
                capa_resolucion='pasivo_prestacion_doble_reporte',
                requiere_revision=False,
                nota=(
                    f'Doble reporte: débitos del año del pasivo prestacional '
                    f'→ F2276 concepto {concepto_pasivo} ({descripcion_concepto}). '
                    f'El saldo final se reporta en F1009 por flujo normal.'
                ),
                balance_id=mov.balance_id,
            ))
            # NO hacemos return: dejamos que capa 2 / capa 1 reporten el
            # saldo final en F1009 también.

        # CAPA 3: override manual (siempre gana)
        capa3 = self._buscar_capa3(mov.codigo_cuenta, mov.nit)
        if capa3:
            # Si alguna regla dice "excluir", se omite el reporte y se documenta el motivo.
            # La exclusión gana sobre cualquier override positivo concurrente.
            regla_excluyente = next((r for r in capa3 if r.excluir), None)
            if regla_excluyente is not None:
                motivo = (regla_excluyente.motivo_exclusion
                          or regla_excluyente.nota
                          or '🚫 Excluida por regla manual')
                resultados.append(MovimientoClasificado(
                    codigo_cuenta=mov.codigo_cuenta, nit=mov.nit,
                    formato_dian='', concepto_dian=None,
                    valor=abs(mov.debitos or mov.creditos or mov.saldo_final),
                    base_aplicable='',
                    capa_resolucion='excluido_manual',
                    regla_id=regla_excluyente.id,
                    requiere_revision=False,
                    nota=motivo,
                    balance_id=mov.balance_id,
                ))
                return resultados

            for r in capa3:
                if not r.formato_dian:
                    # Defensa: regla mal formada (sin formato y sin marca de exclusión).
                    # Se trata como exclusión silenciosa para no romper el motor.
                    continue
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
            if resultados:
                return resultados

        # REGLAS ESPECIALES (incluyen exclusión cuenta 6, 2365, activos, inventarios, cartera)
        # Nota: las reglas especiales F1003 (240825, 135515, 195515) cedan paso si
        # hay una regla específica en capa 2 con el concepto correcto. Esto permite
        # que la BD (capa 2) sea la fuente de verdad del concepto DIAN sin perder
        # la lógica de "valor neto" que aplica para esas cuentas.
        cuenta_str_pre = str(mov.codigo_cuenta).strip()
        config_f1003_pre = _es_cuenta_f1003(cuenta_str_pre)
        capa2_existe = bool(self._buscar_capa2(mov.codigo_cuenta)) if config_f1003_pre else False
        if not (config_f1003_pre and capa2_existe):
            regla_esp = aplicar_regla_especial(mov, cuentas_6_excluidas)
            if regla_esp is not None:
                return [regla_esp]

        # Si la cuenta cae en familia 14, 15, 1305-1315 pero no aplicó la regla
        # especial (saldo cero, depreciación, traslado, etc), NO seguir a las
        # otras capas. Las cuentas 14 (inventarios) y 15 (activos fijos) son
        # resorte EXCLUSIVO de la regla especial: si esta dijo "no reportar",
        # capa 2 / capa 1 no deben darles otra ruta.
        cuenta_str = cuenta_str_pre
        if cuenta_str.startswith('15'):
            return []  # Activos fijos: solo regla especial decide; depreciaciones se descartan
        if cuenta_str.startswith('14'):
            return []  # Inventarios: solo regla especial decide; traslados se descartan
        if _es_cuenta_cartera_1008(cuenta_str):
            return []
        if _es_cuenta_f1003(cuenta_str) and not capa2_existe:
            return []  # Sin valor neto positivo y sin regla en capa 2

        # CAPA 2: mapeo nativo por rangos
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

    def _filtrar_f2276_negativos(
        self, clasificaciones: list[MovimientoClasificado]
    ) -> list[MovimientoClasificado]:
        """
        Filtro defensivo: en F2276 (pagos al empleado) NO pueden haber valores
        negativos. Si una cuenta termina con valor ≤ 0 en F2276, se descarta
        ese movimiento (puede que la cuenta solo aparezca en F1009).

        Esto previene casos donde alguna capa reporta saldo final del pasivo
        (que es negativo, Cr) en F2276 en lugar de los débitos del año.
        """
        out = []
        for c in clasificaciones:
            if c.formato_dian == '2276' and (c.valor is None or c.valor <= 0):
                continue  # descartar
            # Asegurar valor positivo para F2276 incluso si vino con signo
            if c.formato_dian == '2276' and c.valor < 0:
                c.valor = abs(c.valor)
            out.append(c)
        return out

    # ----------------------------------------------------------------
    # Clasificación masiva
    # ----------------------------------------------------------------
    def clasificar_balance(self, movimientos: list[Movimiento]) -> ResultadoClasificacion:
        """
        Clasifica todos los movimientos del balance.
        
        Pasos:
          1. Pre-procesa: validar conciliación cuenta 6 ↔ 72/73
          2. Pre-procesa: indexar retenciones cuenta 2365 por NIT
          3. Procesa cada movimiento aplicando todas las reglas
          4. Compila estadísticas
        """
        res = ResultadoClasificacion()

        # 1. CONCILIACIÓN COSTOS (pre-proceso)
        res.conciliacion_costos = validar_conciliacion_costos_traslado(movimientos)
        cuentas_6_excluidas = res.conciliacion_costos.cuentas_6_excluidas

        # 2. INDEXAR RETENCIONES 2365 por NIT (pre-proceso)
        res.retenciones_por_nit = indexar_retenciones_2365(movimientos)

        # 2b. DETECTAR MAYORES (2365/2367/2369) que cierran en cero
        # Si suman ≈0, sus subcuentas se excluyen del F1009.
        mayores_cerrados = detectar_mayores_pasivos_cerrados(movimientos)

        # 3. CLASIFICAR cada movimiento
        contador = {
            'capa1': 0, 'capa2_unico': 0, 'capa2_ambiguo': 0,
            'capa3': 0, 'regla_especial': 0, 'sin_resolver': 0,
            'excluido_costo_traslado': 0, 'columna_retencion': 0,
            'sin_clasificar_filtrado': 0,
            'excluido_manual': 0,
        }

        for mov in movimientos:
            clasificaciones = self.clasificar_movimiento(
                mov, cuentas_6_excluidas, mayores_cerrados
            )

            # Filtro defensivo: descartar movimientos F2276 con valor ≤ 0
            clasificaciones = self._filtrar_f2276_negativos(clasificaciones)

            # Caso especial: lista vacía = filtrado intencional (saldo cero, no aplica)
            if not clasificaciones:
                contador['sin_clasificar_filtrado'] += 1
                continue

            res.movimientos.extend(clasificaciones)
            primera = clasificaciones[0]

            if primera.capa_resolucion == 'sin_resolver':
                res.sin_resolver.append(mov)
                contador['sin_resolver'] += 1
            elif primera.capa_resolucion == 'excluido_manual':
                contador['excluido_manual'] += 1
            elif primera.capa_resolucion == 'mapeo_manual':
                contador['capa3'] += 1
            elif primera.capa_resolucion == 'regla_especial_costos_traslado_conciliado':
                contador['excluido_costo_traslado'] += 1
            elif primera.capa_resolucion == 'regla_especial_2365_columna':
                contador['columna_retencion'] += 1
            elif primera.capa_resolucion.startswith('regla_especial'):
                contador['regla_especial'] += 1
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
            'conciliacion_concilia': res.conciliacion_costos.concilia,
            'nits_con_retencion': len(res.retenciones_por_nit),
        }
        return res
