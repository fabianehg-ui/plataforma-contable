"""
Lector de planilla PILA (Prefactura SuAporte / Enlace Operativo).

Diseñado para integrarse en el módulo de Nómina como insumo opcional.
Extrae los aportes reales pagados por empleado y los totales de la planilla.

Casa UnoTres SAS está exonerada Art. 114-1 ET:
  - NO paga Salud patronal 8.5%
  - NO paga SENA 2%
  - NO paga ICBF 3%
  - SÍ paga: Pensión 12% empleador + 4% empleado, ARL, Caja 4%, FSP, FSS

Soporta archivos PDF (formato Enlace Operativo) y XLSX/XLS si la admin
exporta la planilla a Excel.

Uso:
    from procesador_pila import leer_planilla_pila
    aportes = leer_planilla_pila(archivo)
    # aportes.por_empleado[nit] = AporteEmpleado(...)
    # aportes.totales = TotalesPila(...)
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


# ============================================================
# Estructuras de datos
# ============================================================

@dataclass
class AporteEmpleado:
    """Aportes reales pagados por un empleado en la planilla PILA."""
    cedula: str
    nombre: str

    # Pensión (16% total = 12% empleador + 4% empleado)
    administradora_pension: str = ""
    ibc_pension: float = 0.0
    aporte_pension: float = 0.0  # total reportado en la planilla

    # Salud
    administradora_salud: str = ""
    ibc_salud: float = 0.0
    aporte_salud: float = 0.0  # 4% empleado (en empresa exonerada)

    # ARL
    administradora_arl: str = ""
    ibc_arl: float = 0.0
    aporte_arl: float = 0.0

    # Caja de Compensación (4%)
    administradora_caja: str = ""
    ibc_caja: float = 0.0
    aporte_caja: float = 0.0

    # SENA / ICBF / ESAP / Min Educ — 0 en exonerada
    aporte_sena: float = 0.0
    aporte_icbf: float = 0.0

    # FSP / FSS (solidaridad pensional, depende del IBC)
    aporte_fsp: float = 0.0
    aporte_fss: float = 0.0

    # Días reportados
    dias_pension: int = 0
    dias_salud: int = 0
    dias_arl: int = 0
    dias_caja: int = 0


@dataclass
class TotalesPila:
    """Totales reportados en la sección III del PDF."""
    ibc_pension: float = 0.0
    ibc_salud: float = 0.0
    ibc_riesgos: float = 0.0
    ibc_cajas: float = 0.0

    aportes_pension: float = 0.0
    aportes_salud: float = 0.0
    aportes_riesgos: float = 0.0
    aportes_cajas: float = 0.0

    aportes_sena: float = 0.0
    aportes_icbf: float = 0.0
    aportes_esap: float = 0.0
    aportes_min_educacion: float = 0.0

    aportes_fsp: float = 0.0
    aportes_fss: float = 0.0

    subtotal_sin_intereses: float = 0.0
    total_intereses: float = 0.0
    total_final: float = 0.0


@dataclass
class PilaLeida:
    """Resultado completo de la lectura de un archivo PILA."""
    numero_planilla: str = ""
    periodo_cotizacion: str = ""        # ej: "marzo de 2026"
    periodo_servicio: str = ""          # ej: "abril de 2026"
    fecha_creacion: Optional[date] = None
    fecha_limite_pago: Optional[date] = None
    razon_social: str = ""
    nit_empresa: str = ""
    total_afiliados: int = 0

    por_empleado: Dict[str, AporteEmpleado] = field(default_factory=dict)
    totales: TotalesPila = field(default_factory=TotalesPila)
    log: List[str] = field(default_factory=list)


# ============================================================
# Helpers
# ============================================================

def _to_float(s) -> float:
    """Convierte string con $ y separadores latinos a float."""
    if s is None:
        return 0.0
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace("$", "").replace(" ", "").replace("\xa0", "")
    if not s or s == "-":
        return 0.0
    # formato latino: punto miles, coma decimal
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        partes = s.split(",")
        if len(partes) == 2 and 0 < len(partes[1]) <= 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        # Solo puntos: si hay más de 1, son miles
        if s.count(".") > 1:
            s = s.replace(".", "")
        elif s.count(".") == 1:
            # Si la parte después del punto tiene 3 dígitos o más, es separador de miles
            partes = s.split(".")
            if len(partes[1]) >= 3:
                s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.upper().strip()


def _solo_digitos(s) -> str:
    if s is None:
        return ""
    return re.sub(r"\D", "", str(s))


def _limpiar_nombre_pdf(nombre_raw: str, catalogo_empleados: Optional[Dict[str, str]] = None, cedula: str = "") -> str:
    """Limpia el nombre extraído del PDF.

    pdfplumber a veces reordena letras por rotación (90°), produciendo
    nombres como 'M YO O R R L A A L D E I S S RAMOS MARIA' en lugar de
    'MORALES RAMOS MARIA YORLADIS'.

    Si se proporciona un catálogo {cedula: nombre_correcto}, se usa ese
    nombre. Si no, se devuelve el nombre raw con espacios normalizados.
    """
    if catalogo_empleados and cedula in catalogo_empleados:
        return catalogo_empleados[cedula]
    # Fallback: normalizar espacios
    return re.sub(r"\s+", " ", nombre_raw).strip()


def _parsear_dias(bloque: str) -> tuple:
    """Parsea el bloque de días de la sección II del PDF PILA.

    El bloque puede venir en 3 formas (siempre 5 valores: 0 + d_pens + d_ccf + d_afp + d_arp):
      - Pegado:        '030303030'    → 0,30,30,30,30 → (30,30,30,30)
      - Separado:      '0 30 30 30 30' → (30,30,30,30)
      - Mixto bajo:    '0 1 1 1 1'    → (1,1,1,1)
      - Pegado bajo:   '027272727'    → 0,27,27,27,27 → (27,27,27,27)

    Retorna: (dias_pension, dias_caja, dias_salud, dias_arl)
    """
    if not bloque:
        return (0, 0, 0, 0)

    # Si tiene espacios, parsear directamente
    if " " in bloque:
        partes = [int(p) for p in bloque.split() if p.strip().isdigit()]
        if len(partes) == 5:
            return (partes[1], partes[2], partes[3], partes[4])
        elif len(partes) == 4:
            return (partes[0], partes[1], partes[2], partes[3])
        else:
            return (0, 0, 0, 0)

    # Está pegado. Es '0' + 4 grupos iguales de 1-2 dígitos.
    if not bloque.startswith("0"):
        return (0, 0, 0, 0)

    resto = bloque[1:]
    n = len(resto)
    if n % 4 == 0 and n > 0:
        ancho = n // 4
        try:
            d1 = int(resto[0:ancho])
            d2 = int(resto[ancho:ancho*2])
            d3 = int(resto[ancho*2:ancho*3])
            d4 = int(resto[ancho*3:ancho*4])
            if all(0 <= d <= 31 for d in (d1, d2, d3, d4)):
                return (d1, d2, d3, d4)
        except ValueError:
            pass

    # Fallback: tomar grupos de hasta 2 dígitos
    grupos = re.findall(r"\d{1,2}", resto)
    grupos_int = [int(g) for g in grupos[:4]]
    while len(grupos_int) < 4:
        grupos_int.append(0)
    return tuple(grupos_int[:4])


# ============================================================
# Lectura de PDF (formato Enlace Operativo / SuAporte)
# ============================================================

def _leer_pdf(contenido: bytes) -> PilaLeida:
    """Extrae datos de un PDF de planilla PILA usando pdfplumber.

    El PDF de SuAporte es complejo (rotación 90°, tablas anidadas).
    Estrategia: extraer texto plano y parsear con regex.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "Para leer PILA en PDF instala: pip install pdfplumber"
        )

    pila = PilaLeida()
    pila.log.append("📄 Leyendo PDF PILA...")

    with pdfplumber.open(io.BytesIO(contenido)) as pdf:
        texto_total = ""
        for page in pdf.pages:
            texto_total += page.extract_text() or ""
            texto_total += "\n"

    return _parsear_texto_pila(texto_total, pila)


def _parsear_texto_pila(texto: str, pila: PilaLeida) -> PilaLeida:
    """Parsea el texto extraído del PDF PILA."""
    # === Datos del aportante ===
    m = re.search(r"N\u00famero Planilla:\s*(\d+)", texto)
    if m:
        pila.numero_planilla = m.group(1)

    m = re.search(r"Periodo Cotizaci[óo]n:\s*([^\n]+?)(?:\s+Periodo|$)", texto, re.IGNORECASE)
    if m:
        pila.periodo_cotizacion = m.group(1).strip()

    m = re.search(r"Periodo Servicio:\s*([^\n]+)", texto, re.IGNORECASE)
    if m:
        pila.periodo_servicio = m.group(1).strip().split("Fecha")[0].strip()

    m = re.search(r"Raz[óo]n Social\s+([A-ZÁÉÍÓÚÑ\.\s]+?)(?:Documento|Direcci|$)", texto, re.IGNORECASE)
    if m:
        pila.razon_social = m.group(1).strip()

    m = re.search(r"NI(\d{6,15})", texto)
    if m:
        pila.nit_empresa = m.group(1)

    m = re.search(r"Total\s+Afiliados\s+(\d+)", texto, re.IGNORECASE)
    if m:
        pila.total_afiliados = int(m.group(1))

    # === Empleados (sección II - DETALLE) ===
    # Nota: pdfplumber a veces reordena letras del nombre por rotación del PDF.
    # Estrategia: capturar SOLO los datos numéricos (que vienen en orden correcto)
    # y reconstruir el nombre desde un catálogo posterior si está disponible.
    #
    # Línea típica:
    # CC 39177488 <NOMBRE_DESORDENADO> 01 00 X 0 30 30 30 30 PROTECCION $ 3.680.679 $ 589.000 EPS SURA $ ...
    #
    # ⚠️ Días pueden venir PEGADOS (030303030) o SEPARADOS (0 30 30 30 30 / 0 1 1 1 1).
    # Por eso capturamos la zona de días como bloque opaco y la parseamos aparte.
    patron = re.compile(
        r"CC\s+(\d{6,15})\s+"                          # 1: cédula
        r"(.+?)\s+"                                    # 2: nombre (no greedy)
        r"(\d{2})\s+(\d{2})\s+"                        # 3,4: tipo cotizante, subtipo
        r"X\s+"                                        # marca novedad
        r"([\d\s]+?)\s*"                               # 5: bloque de días (opaco)
        r"([A-ZÁÉÍÓÚÑ]+)\s*"                            # 6: admin pensión
        r"\$\s*([\d\.,]+)\s*"                          # 7: IBC pensión
        r"\$\s*([\d\.,]+)\s*"                          # 8: aporte pensión
        r"([A-Z][A-Z\s]+?)\s+"                          # 9: admin salud
        r"\$\s*([\d\.,]+)\s*"                          # 10: IBC salud
        r"\$\s*([\d\.,]+)\s*"                          # 11: aporte salud
        r"([A-Z][A-Z\s]+?)\s+"                          # 12: admin ARL
        r"\$\s*([\d\.,]+)\s*"                          # 13: IBC riesgos
        r"\$\s*([\d\.,]+)\s*"                          # 14: aporte riesgos
        r"([A-Z]+)\s*"                                  # 15: admin caja
        r"\$\s*([\d\.,]+)\s*"                          # 16: IBC caja
        r"\$\s*([\d\.,]+)",                             # 17: aporte caja
        re.IGNORECASE,
    )

    for m in patron.finditer(texto):
        cedula = m.group(1).strip()
        nombre = m.group(2).strip()
        emp = pila.por_empleado.get(cedula)
        if emp is None:
            emp = AporteEmpleado(cedula=cedula, nombre=nombre)
            pila.por_empleado[cedula] = emp

        # Parsear bloque de días: puede venir pegado o separado
        bloque_dias = m.group(5).strip()
        d_pens, d_ccf, d_afp, d_arp = _parsear_dias(bloque_dias)
        emp.dias_pension += d_pens
        emp.dias_caja += d_ccf
        emp.dias_salud += d_afp
        emp.dias_arl += d_arp

        emp.administradora_pension = m.group(6).strip()
        emp.ibc_pension += _to_float(m.group(7))
        emp.aporte_pension += _to_float(m.group(8))

        emp.administradora_salud = m.group(9).strip()
        emp.ibc_salud += _to_float(m.group(10))
        emp.aporte_salud += _to_float(m.group(11))

        emp.administradora_arl = m.group(12).strip()
        emp.ibc_arl += _to_float(m.group(13))
        emp.aporte_arl += _to_float(m.group(14))

        emp.administradora_caja = m.group(15).strip()
        emp.ibc_caja += _to_float(m.group(16))
        emp.aporte_caja += _to_float(m.group(17))

    pila.log.append(f"   👥 Empleados detectados: {len(pila.por_empleado)}")

    # === Totales (sección III) ===
    # Buscar la sección "III.TOTALES" y extraer los valores en secuencia
    seccion = re.search(r"III\.\s*TOTALES(.+?)(?:Enlace Operativo|$)", texto, re.IGNORECASE | re.DOTALL)
    if seccion:
        cuerpo = seccion.group(1)
        # Capturar todos los valores monetarios en orden
        valores = re.findall(r"\$\s*([\d\.,]+)", cuerpo)
        valores_num = [_to_float(v) for v in valores]
        # El orden esperado en el PDF:
        # IBC Pensión, IBC Salud, IBC Riesgos, IBC Cajas, Aportes Pensión, Aportes FSP, Aportes FSS,
        # Aportes Salud, Aportes Riesgos, Aportes Cajas, Aportes Sena, Aportes ICBF,
        # Aportes ESAP, Aportes Min Educación, Incapacidades/Licencias, Incap ARP,
        # Subtotal sin intereses, Total intereses, Total Final
        if len(valores_num) >= 19:
            t = pila.totales
            t.ibc_pension = valores_num[0]
            t.ibc_salud = valores_num[1]
            t.ibc_riesgos = valores_num[2]
            t.ibc_cajas = valores_num[3]
            t.aportes_pension = valores_num[4]
            t.aportes_fsp = valores_num[5]
            t.aportes_fss = valores_num[6]
            t.aportes_salud = valores_num[7]
            t.aportes_riesgos = valores_num[8]
            t.aportes_cajas = valores_num[9]
            t.aportes_sena = valores_num[10]
            t.aportes_icbf = valores_num[11]
            t.aportes_esap = valores_num[12]
            t.aportes_min_educacion = valores_num[13]
            t.subtotal_sin_intereses = valores_num[16]
            t.total_intereses = valores_num[17]
            t.total_final = valores_num[18]
            pila.log.append(f"   💰 Total final PILA: ${int(t.total_final):,}".replace(",", "."))

    # Validación: si los totales por empleado suman parecido a los totales reportados, OK
    suma_pension = sum(e.aporte_pension for e in pila.por_empleado.values())
    if pila.totales.aportes_pension > 0:
        diff = abs(suma_pension - pila.totales.aportes_pension)
        tolerancia = max(100, pila.totales.aportes_pension * 0.001)
        if diff > tolerancia:
            pila.log.append(
                f"   ⚠️ Suma pensión por empleado ${int(suma_pension):,} "
                f"≠ total reportado ${int(pila.totales.aportes_pension):,} "
                f"(dif ${int(diff):,})".replace(",", ".")
            )
        else:
            pila.log.append(f"   ✅ Validación cruzada: suma por empleado ≈ total reportado")

    return pila


# ============================================================
# Lectura de XLSX/XLS (alternativa)
# ============================================================

def _leer_xlsx(contenido: bytes) -> PilaLeida:
    """Si la admin tiene la PILA en Excel, intentar leer.

    NOTA: la prefactura nativa es PDF; este path es para casos donde
    la admin haya copiado los datos a Excel manualmente.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas necesario para leer PILA en Excel")

    pila = PilaLeida()
    pila.log.append("📄 Leyendo PILA en Excel...")

    df = pd.read_excel(io.BytesIO(contenido), sheet_name=0, header=None)
    # Convertir a texto y reusar el parser
    texto = "\n".join(
        " ".join(str(c) if c is not None else "" for c in row)
        for row in df.itertuples(index=False)
    )
    return _parsear_texto_pila(texto, pila)


# ============================================================
# Función principal
# ============================================================

def leer_planilla_pila(archivo, catalogo_empleados: Optional[Dict[str, str]] = None) -> PilaLeida:
    """Lee una planilla PILA (PDF o Excel) y devuelve un PilaLeida.

    Args:
        archivo: file-like (Streamlit UploadedFile), bytes o path str.
        catalogo_empleados: opcional dict {cedula: nombre_correcto} para
            corregir nombres reordenados por rotación del PDF. Idealmente
            se pasa el mismo catálogo que usa el módulo de Nómina.

    Returns:
        PilaLeida con los aportes por empleado y los totales.
    """
    # Leer bytes
    if hasattr(archivo, "read"):
        contenido = archivo.read()
        if hasattr(archivo, "seek"):
            archivo.seek(0)
        nombre = getattr(archivo, "name", "")
    elif isinstance(archivo, (bytes, bytearray)):
        contenido = bytes(archivo)
        nombre = ""
    elif isinstance(archivo, str):
        with open(archivo, "rb") as f:
            contenido = f.read()
        nombre = archivo
    else:
        raise TypeError(f"Tipo de archivo no soportado: {type(archivo)}")

    # Detectar tipo
    es_pdf = contenido[:4] == b"%PDF" or nombre.lower().endswith(".pdf")
    if es_pdf:
        pila = _leer_pdf(contenido)
    else:
        pila = _leer_xlsx(contenido)

    # Aplicar catálogo si está disponible
    if catalogo_empleados:
        for cedula, emp in pila.por_empleado.items():
            emp.nombre = _limpiar_nombre_pdf(emp.nombre, catalogo_empleados, cedula)

    return pila


# ============================================================
# Ajuste contable: provisiones vs PILA pagada
# ============================================================

@dataclass
class LineaAjuste:
    """Una línea de ajuste para Comp 9 cuando hay diferencia
    entre provisión de nómina y aporte real pagado en PILA."""
    cuenta: str
    detalle: str
    nit: str
    valor: float
    tr: str           # '1' Db (provisión < pagado) o '2' Cr (provisión > pagado)
    base: float = 0.0


def calcular_ajustes_pila(
    provisiones_nomina: Dict[str, Dict[str, float]],
    pila: PilaLeida,
    cuentas_provision: Dict[str, str],
    tolerancia: int = 1,
) -> List[LineaAjuste]:
    """Compara lo provisionado en nómina vs lo pagado en PILA y genera
    líneas de ajuste para Comp 9.

    Args:
        provisiones_nomina: dict por cédula → {'pension': X, 'salud': Y, 'arl': Z, 'caja': W}
            con los montos PROVISIONADOS por el procesador de nómina.
        pila: resultado de leer_planilla_pila().
        cuentas_provision: mapeo concepto → cuenta contable. Ej:
            {
              'pension':  '23700501',  # aportes pensión por pagar
              'salud':    '23700502',
              'arl':      '23700503',
              'caja':     '23700504',
            }
        tolerancia: diferencia máxima en pesos para no generar ajuste.

    Returns:
        Lista de LineaAjuste. Si la lista está vacía, no hay diferencias.
    """
    ajustes: List[LineaAjuste] = []
    nit_empresa = pila.nit_empresa or ""

    for cedula, emp in pila.por_empleado.items():
        prov = provisiones_nomina.get(cedula, {})
        if not prov:
            continue  # empleado en PILA pero no en nómina (raro)

        pares = [
            ("pension", emp.aporte_pension),
            ("salud",   emp.aporte_salud),
            ("arl",     emp.aporte_arl),
            ("caja",    emp.aporte_caja),
        ]

        for concepto, pagado in pares:
            provisionado = prov.get(concepto, 0)
            diff = round(pagado - provisionado)
            if abs(diff) <= tolerancia:
                continue
            cuenta = cuentas_provision.get(concepto)
            if not cuenta:
                continue

            if diff > 0:
                # PILA pagó MÁS que lo provisionado → faltó provisión → Db gasto / Cr pasivo
                ajustes.append(LineaAjuste(
                    cuenta=cuenta,
                    detalle=f"AJUSTE PILA {concepto.upper()} - {emp.nombre}",
                    nit=cedula,
                    valor=abs(diff),
                    tr="2",  # Cr al pasivo (porque hay que pagar más)
                ))
            else:
                # PILA pagó MENOS que lo provisionado → sobró provisión → Db pasivo / Cr gasto
                ajustes.append(LineaAjuste(
                    cuenta=cuenta,
                    detalle=f"AJUSTE PILA {concepto.upper()} - {emp.nombre}",
                    nit=cedula,
                    valor=abs(diff),
                    tr="1",  # Db al pasivo (sobra)
                ))

    return ajustes


# ============================================================
# Diagnóstico rápido (CLI)
# ============================================================

def imprimir_resumen(pila: PilaLeida) -> None:
    """Imprime un resumen legible de una PILA leída."""
    print("=" * 70)
    print(f"PILA #{pila.numero_planilla} — {pila.razon_social} (NIT {pila.nit_empresa})")
    print(f"Periodo cotización: {pila.periodo_cotizacion}")
    print(f"Periodo servicio:   {pila.periodo_servicio}")
    print(f"Total afiliados:    {pila.total_afiliados}")
    print()
    print("--- Empleados ---")
    for cedula, e in pila.por_empleado.items():
        print(f"  CC {cedula} - {e.nombre}")
        print(f"    Pensión:  IBC=${int(e.ibc_pension):>12,} "
              f"aporte=${int(e.aporte_pension):>10,} ({e.administradora_pension})".replace(",", "."))
        print(f"    Salud:    IBC=${int(e.ibc_salud):>12,} "
              f"aporte=${int(e.aporte_salud):>10,} ({e.administradora_salud})".replace(",", "."))
        print(f"    ARL:      IBC=${int(e.ibc_arl):>12,} "
              f"aporte=${int(e.aporte_arl):>10,} ({e.administradora_arl})".replace(",", "."))
        print(f"    Caja:     IBC=${int(e.ibc_caja):>12,} "
              f"aporte=${int(e.aporte_caja):>10,} ({e.administradora_caja})".replace(",", "."))
    print()
    print("--- Totales ---")
    t = pila.totales
    print(f"  IBC Pensión:        ${int(t.ibc_pension):>15,}".replace(",", "."))
    print(f"  Aportes Pensión:    ${int(t.aportes_pension):>15,}".replace(",", "."))
    print(f"  Aportes Salud:      ${int(t.aportes_salud):>15,}".replace(",", "."))
    print(f"  Aportes Riesgos:    ${int(t.aportes_riesgos):>15,}".replace(",", "."))
    print(f"  Aportes Cajas:      ${int(t.aportes_cajas):>15,}".replace(",", "."))
    print(f"  SENA / ICBF:        ${int(t.aportes_sena + t.aportes_icbf):>15,} (debe ser $0 en exonerada)".replace(",", "."))
    print(f"  TOTAL FINAL:        ${int(t.total_final):>15,}".replace(",", "."))
    print()
    print("--- Log ---")
    for l in pila.log:
        print(l)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        archivo = sys.argv[1]
        pila = leer_planilla_pila(archivo)
        imprimir_resumen(pila)
    else:
        print("Uso: python procesador_pila.py <archivo.pdf|.xlsx>")
