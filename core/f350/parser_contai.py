"""
core/f350/parser_contai.py — parseo de los PDFs de Contai.

A diferencia del .exe original (que recibe rutas de archivo), estas funciones
aceptan TANTO rutas como bytes/file-like objects, para que Streamlit pueda
pasarles directamente el resultado de st.file_uploader sin tener que escribir
al disco.

Funciones:
    parsear_auxiliar_contai(fuente)  → auxiliar de retefuente
    parsear_balance_contai(fuente)   → balance de prueba

`fuente` puede ser:
    - str (ruta a archivo)
    - bytes (contenido del PDF)
    - file-like (objeto con .read() o que pdfplumber acepta)

Extraído de BorradorFácil 350 v2.1.5 con adaptación de E/S.
"""

import io
import re


def _abrir_pdf(fuente):
    """
    Devuelve un objeto pdfplumber.PDF abierto.
    Acepta ruta, bytes o file-like.
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber no está instalado. Instálalo con: pip install pdfplumber"
        )

    if isinstance(fuente, (bytes, bytearray)):
        return pdfplumber.open(io.BytesIO(fuente))
    if isinstance(fuente, str):
        return pdfplumber.open(fuente)
    # asumir file-like
    if hasattr(fuente, "read"):
        data = fuente.read()
        if isinstance(data, str):
            data = data.encode("latin-1", errors="ignore")
        return pdfplumber.open(io.BytesIO(data))
    raise TypeError(f"Tipo de fuente no soportado: {type(fuente)}")


def parsear_auxiliar_contai(fuente):
    """
    Parsea el reporte 'Análisis de % de Retención e IVA - Resumido' de Contai.

    Estructura del reporte:
    - Encabezado empresa: "NOMBRE S.A.S - NIT"
    - Encabezado cuenta: "CODIGO NOMBRE_CUENTA" (ej: "23-65-25-05 SERVICIOS DEL 4%")
    - Líneas movimiento: "[debitos?] creditos base tarifa NIT nombre_tercero"
    - Total Cuenta: cierra cada grupo

    Retorna dict con:
        empresa, nit_empresa, periodo, movimientos[]

    Cada movimiento tiene:
        cuenta, nombre_cuenta, tarifa_cuenta,
        debitos, creditos, base, tarifa_mov, retencion,
        nit, nombre_tercero
    """
    movimientos = []
    empresa = None
    nit_empresa = None
    periodo = None

    with _abrir_pdf(fuente) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto:
                continue
            lineas = texto.split('\n')

            cuenta_actual = None
            nombre_cuenta_actual = None
            tarifa_actual = None

            for linea in lineas:
                linea = linea.strip()
                if not linea:
                    continue

                # Detectar encabezado de empresa
                if 'S.A.S' in linea and '-' in linea and not empresa:
                    m = re.match(r'(.+?)\s*-\s*([\d\.]+-?\d?)', linea)
                    if m:
                        empresa = m.group(1).strip()
                        nit_empresa = m.group(2).strip()

                # Detectar período (ej: "Mar-3-2026")
                if not periodo:
                    m = re.search(r'([A-Z][a-z]{2}-\d{1,2}-\d{4})', linea)
                    if m:
                        periodo = m.group(1)

                # Saltar encabezados de página / decoración
                if (linea.startswith('---') or linea.startswith('===')
                    or 'PAGINA' in linea or 'Contai' in linea
                    or ('Cuenta' in linea and 'Nombre' in linea and 'NIT' in linea)):
                    continue

                # Cuando una cuenta se parte entre páginas, Contai repite el
                # encabezado precedido de "Continua con la cuenta : ". Si no se
                # normaliza, la línea no matchea el encabezado y se pierden TODOS
                # los movimientos de esa cuenta en las páginas siguientes.
                m_continua = re.match(
                    r'^Continua\s+con\s+la\s+cuenta\s*:?\s*(.+)$',
                    linea,
                    re.IGNORECASE,
                )
                if m_continua:
                    linea = m_continua.group(1).strip()

                # Detectar línea de encabezado de cuenta: "23-65-25-05 NOMBRE..."
                m_cuenta = re.match(r'^(\d{2}-\d{2}-\d{2}-\d{2})\s+(.+)$', linea)
                if m_cuenta:
                    cuenta_actual = m_cuenta.group(1)
                    nombre_completo = m_cuenta.group(2).strip()
                    # Extraer tarifa al final del nombre si la hay (ej: "...DEL 4%")
                    m_tarifa = re.search(r'(\d+(?:\.\d+)?)\s*%?\s*$', nombre_completo)
                    if m_tarifa:
                        try:
                            tarifa_actual = float(m_tarifa.group(1))
                            nombre_cuenta_actual = nombre_completo[:m_tarifa.start()].strip()
                        except ValueError:
                            tarifa_actual = None
                            nombre_cuenta_actual = nombre_completo
                    else:
                        tarifa_actual = None
                        nombre_cuenta_actual = nombre_completo
                    continue

                # Cerrar grupo de cuenta
                if linea.startswith('Total Cuenta') or linea.startswith('Total General'):
                    cuenta_actual = None
                    continue

                # Línea de movimiento dentro de una cuenta
                if cuenta_actual:
                    m_mov = re.match(
                        r'^([\d,\.]+(?:\s+[\d,\.]+){1,2})\s+(\d+(?:\.\d+)?)\s+(\d+)\s+(.+)$',
                        linea,
                    )
                    if m_mov:
                        try:
                            numeros_str = m_mov.group(1)
                            tarifa_mov = float(m_mov.group(2))
                            nit = m_mov.group(3)
                            nombre_tercero = m_mov.group(4).strip()

                            nums = [
                                float(n.replace(',', ''))
                                for n in re.findall(r'[\d,\.]+', numeros_str)
                            ]

                            # El encabezado del reporte es:
                            #   Débitos | Créditos | Base | % | NIT | Nombre
                            # La columna de RETENCIÓN es la que está
                            # inmediatamente antes de la base (la "Créditos").
                            #
                            #   2 números → "crédito base"          (débito = 0)
                            #   3 números → "débito crédito base"
                            #
                            # En las líneas de 3 números el débito es una
                            # REVERSIÓN/anulación de retención del mismo período
                            # (p.ej. una factura anulada). Para el F350 lo que se
                            # declara es la retención NETA = crédito - débito,
                            # porque a la DIAN solo se le entrega lo efectivamente
                            # retenido tras descontar lo reversado.
                            if len(nums) == 2:
                                debitos = 0.0
                                creditos, base = nums
                            elif len(nums) == 3:
                                debitos, creditos, base = nums
                            else:
                                continue

                            retencion = creditos - debitos

                            movimientos.append({
                                'cuenta': cuenta_actual,
                                'nombre_cuenta': nombre_cuenta_actual,
                                'tarifa_cuenta': tarifa_actual,
                                'debitos': debitos,
                                'creditos': creditos,
                                'base': base,
                                'tarifa_mov': tarifa_mov,
                                'retencion': retencion,
                                'nit': nit,
                                'nombre_tercero': nombre_tercero,
                            })
                        except (ValueError, IndexError):
                            continue

    return {
        'empresa':     empresa,
        'nit_empresa': nit_empresa,
        'periodo':     periodo,
        'movimientos': movimientos,
    }


def parsear_balance_contai(fuente):
    """
    Parsea 'Balance de Prueba por Cuenta (Normal)' de Contai.

    Estructura de línea de cuenta:
        CODIGO NOMBRE SALDO_ANT DEBITOS CREDITOS NUEVO_SALDO

    Códigos válidos: desde 1 dígito (clase) hasta 4 niveles (11-05-05-01).

    Retorna dict con:
        empresa, nit_empresa, cuentas[]

    Cada cuenta tiene:
        codigo, nivel, nombre, saldo_anterior, debitos, creditos, nuevo_saldo
    """
    empresa = None
    nit_empresa = None
    cuentas = []

    with _abrir_pdf(fuente) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto:
                continue
            lineas = texto.split('\n')

            for linea in lineas:
                linea = linea.strip()
                if not linea:
                    continue

                if 'S.A.S' in linea and '-' in linea and not empresa:
                    m = re.match(r'(.+?)\s*-\s*([\d\.]+-?\d?)', linea)
                    if m:
                        empresa = m.group(1).strip()
                        nit_empresa = m.group(2).strip()

                if (linea.startswith('---') or linea.startswith('===')
                    or 'PAGINA' in linea or 'Contai' in linea
                    or 'M o v i m' in linea
                    or ('Código' in linea and 'Nombre' in linea)
                    or linea.startswith('Débitos')
                    or linea.startswith('Créditos')
                    or linea.startswith('T o t a l e s')):
                    continue

                m = re.match(
                    r'^(\d{1,2}(?:-\d{2}){0,3})\s+(.+?)\s+'
                    r'(-?[\d,\.]+)\s+(-?[\d,\.]+)\s+(-?[\d,\.]+)\s+(-?[\d,\.]+)$',
                    linea,
                )
                if m:
                    codigo = m.group(1)
                    nombre = m.group(2).strip()
                    try:
                        saldo_ant = float(m.group(3).replace(',', ''))
                        debitos = float(m.group(4).replace(',', ''))
                        creditos = float(m.group(5).replace(',', ''))
                        nuevo_saldo = float(m.group(6).replace(',', ''))
                    except ValueError:
                        continue

                    cuentas.append({
                        'codigo':         codigo,
                        'nivel':          codigo.count('-') + 1,
                        'nombre':         nombre,
                        'saldo_anterior': saldo_ant,
                        'debitos':        debitos,
                        'creditos':       creditos,
                        'nuevo_saldo':    nuevo_saldo,
                    })

    return {
        'empresa':     empresa,
        'nit_empresa': nit_empresa,
        'cuentas':     cuentas,
    }
