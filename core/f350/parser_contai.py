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


_MONEY_RE = re.compile(r'^-?[\d,]+(?:\.\d+)?$')  # 69,600.00 · 1,740,000 · 4.00
_NIT_RE = re.compile(r'^\d{6,11}$')


def _agrupar_filas(words, tol=2.5):
    """Agrupa las palabras de una página en filas por su coordenada vertical."""
    filas = []
    for w in sorted(words, key=lambda x: (x['top'], x['x0'])):
        colocada = False
        for fila in filas:
            if abs(fila['top'] - w['top']) <= tol:
                fila['words'].append(w)
                fila['top'] = (fila['top'] * fila['n'] + w['top']) / (fila['n'] + 1)
                fila['n'] += 1
                colocada = True
                break
        if not colocada:
            filas.append({'top': w['top'], 'n': 1, 'words': [w]})
    for fila in filas:
        fila['words'].sort(key=lambda x: x['x0'])
    return filas


def _detectar_columnas(filas):
    """
    Localiza la fila de encabezado (Débitos | Créditos | Base | Retención | %)
    y devuelve los límites en X que separan las columnas numéricas.

    Los números de Contai están alineados a la derecha, así que la columna a la
    que pertenece un número se decide por su borde derecho (x1).
    """
    for fila in filas:
        txt = {w['text']: w for w in fila['words']}
        if 'Débitos' in txt and 'Créditos' in txt and 'Base' in txt:
            deb, cred, base = txt['Débitos'], txt['Créditos'], txt['Base']
            ret = txt.get('Retención')
            pct = txt.get('%')
            base_right = ret['x1'] if ret else base['x1'] + 40
            pct_left = pct['x0'] if pct else base_right + 20
            return {
                'deb_cred':  (deb['x1'] + cred['x0']) / 2,
                'cred_base': (cred['x1'] + base['x0']) / 2,
                'base_pct':  (base_right + pct_left) / 2,
            }
    return None


def parsear_auxiliar_contai(fuente):
    """
    Parsea el reporte 'Análisis de % de Retención e IVA - Resumido' de Contai.

    Estructura del reporte:
    - Encabezado empresa: "NOMBRE S.A.S - NIT"
    - Encabezado cuenta: "CODIGO NOMBRE_CUENTA" (ej: "23-65-25-05 SERVICIOS DEL 4%")
    - Columnas: Débitos | Créditos | Base | Retención | % | NIT | Nombre
    - Total Cuenta: cierra cada grupo

    IMPORTANTE — por qué se parsea por POSICIÓN de columna y no contando
    números:

    Una línea con SOLO débito (una devolución/nota crédito de retención sin
    ninguna retención nueva del mismo tercero en el período) queda en el texto
    plano EXACTAMENTE igual que una línea normal con solo crédito:

        Débito 13.852  (Crédito vacío)  Base 554.080  2.50  NIT  ABURRA LTDA
        (Crédito 52.000)(Débito vacío)  Base 1.300.000 4.00  NIT  FRANK BRAND

    ambas se extraen como "<un número> <base> <tarifa> <nit> <nombre>". Contar
    los números no permite distinguirlas, así que el parser viejo asumía que el
    único número era SIEMPRE un crédito y contabilizaba la devolución como
    retención POSITIVA, inflando el total. Aquí asignamos cada número a su
    columna real por su coordenada X, de modo que un débito-solo se registra
    como débito y la retención neta (crédito − débito) sale NEGATIVA, restando
    del total como debe ser.

    Si en alguna página no se logra ubicar el encabezado de columnas (PDF
    atípico), se cae de vuelta al parseo por texto de la versión anterior.

    Retorna dict con:
        empresa, nit_empresa, periodo, movimientos[], lineas_sospechosas[]

    Cada movimiento tiene:
        cuenta, nombre_cuenta, tarifa_cuenta,
        debitos, creditos, base, tarifa_mov, retencion,
        nit, nombre_tercero
    """
    estado = {
        'empresa': None,
        'nit_empresa': None,
        'periodo': None,
        'movimientos': [],
        'lineas_sospechosas': [],
        'cuenta_actual': None,
        'nombre_cuenta_actual': None,
        'tarifa_actual': None,
        'splits': None,   # se conserva entre páginas
    }

    with _abrir_pdf(fuente) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if words:
                filas = _agrupar_filas(words)
                splits = _detectar_columnas(filas)
                if splits:
                    estado['splits'] = splits
                if estado['splits']:
                    _procesar_pagina_por_columnas(filas, estado)
                    continue
            # Fallback: sin palabras posicionadas o sin encabezado → por texto.
            texto = page.extract_text()
            if texto:
                _procesar_pagina_por_texto(texto, estado)

    return {
        'empresa':     estado['empresa'],
        'nit_empresa': estado['nit_empresa'],
        'periodo':     estado['periodo'],
        'movimientos': estado['movimientos'],
        'lineas_sospechosas': estado['lineas_sospechosas'],
    }


def _procesar_cabeceras_linea(linea, estado):
    """
    Detecta empresa/período/cuenta/total en una línea de texto.
    Devuelve True si la línea era una cabecera/decoración (ya consumida),
    False si es una línea de movimiento que el llamador debe procesar.
    """
    # Encabezado de empresa. Acepta razones sociales con "S.A.S", "S.A.S.",
    # "SAS", "S.A." o "SA" (Contai las imprime de formas distintas según la
    # empresa; ATOCHA aparece como "GRUPO ATOCHA SAS - 900.380.500-5").
    if (not estado['empresa'] and '-' in linea
            and re.search(r'\bS\.?A\.?S?\.?\b', linea)):
        m = re.match(r'(.+?)\s*-\s*(\d[\d\.]+-?\d?)\s*$', linea)
        if m:
            estado['empresa'] = m.group(1).strip()
            estado['nit_empresa'] = m.group(2).strip()

    # Período (ej: "Mar-3-2026")
    if not estado['periodo']:
        m = re.search(r'([A-Z][a-z]{2}-\d{1,2}-\d{4})', linea)
        if m:
            estado['periodo'] = m.group(1)

    # Decoración / encabezados de página
    if (linea.startswith('---') or linea.startswith('===')
            or 'PAGINA' in linea or 'Contai' in linea
            or ('Cuenta' in linea and 'Nombre' in linea and 'NIT' in linea)
            or ('Débitos' in linea and 'Créditos' in linea)):
        return True

    # "Continua con la cuenta : 23-65-40-01 COMPRAS..."
    m_continua = re.match(r'^Continua\s+con\s+la\s+cuenta\s*:?\s*(.+)$',
                          linea, re.IGNORECASE)
    if m_continua:
        linea = m_continua.group(1).strip()

    # Encabezado de cuenta: "23-65-25-05 NOMBRE..."
    m_cuenta = re.match(r'^(\d{2}-\d{2}-\d{2}-\d{2})\s+(.+)$', linea)
    if m_cuenta:
        estado['cuenta_actual'] = m_cuenta.group(1)
        nombre_completo = m_cuenta.group(2).strip()
        m_tarifa = re.search(r'(\d+(?:\.\d+)?)\s*%?\s*$', nombre_completo)
        if m_tarifa:
            try:
                estado['tarifa_actual'] = float(m_tarifa.group(1))
                estado['nombre_cuenta_actual'] = nombre_completo[:m_tarifa.start()].strip()
            except ValueError:
                estado['tarifa_actual'] = None
                estado['nombre_cuenta_actual'] = nombre_completo
        else:
            estado['tarifa_actual'] = None
            estado['nombre_cuenta_actual'] = nombre_completo
        return True

    # Cierre de grupo
    if linea.startswith('Total Cuenta') or linea.startswith('Total General'):
        estado['cuenta_actual'] = None
        return True

    return False


def _registrar_movimiento(estado, debitos, creditos, base, tarifa_mov,
                          nit, nombre_tercero, linea_txt):
    """Valida y agrega un movimiento (o lo marca sospechoso)."""
    # Retención NETA: crédito (retención practicada) − débito (devolución).
    retencion = creditos - debitos

    # Una devolución (retención neta negativa) también reduce la BASE: se deja
    # con signo negativo para que no infle la base declarada del concepto.
    if retencion < 0:
        base = -abs(base)

    # Tarifa imposible (>=100%) → línea mal leída; se registra y se salta.
    if tarifa_mov is not None and tarifa_mov >= 100:
        estado['lineas_sospechosas'].append({
            'cuenta': estado['cuenta_actual'],
            'linea': linea_txt.strip(),
            'tarifa_leida': tarifa_mov,
        })
        return

    estado['movimientos'].append({
        'cuenta': estado['cuenta_actual'],
        'nombre_cuenta': estado['nombre_cuenta_actual'],
        'tarifa_cuenta': estado['tarifa_actual'],
        'debitos': debitos,
        'creditos': creditos,
        'base': base,
        'tarifa_mov': tarifa_mov if tarifa_mov is not None else estado['tarifa_actual'],
        'retencion': retencion,
        'nit': nit,
        'nombre_tercero': nombre_tercero,
    })


def _procesar_pagina_por_columnas(filas, estado):
    """Parseo posicional: cada número va a su columna real por coordenada X."""
    splits = estado['splits']
    for fila in filas:
        linea_txt = ' '.join(w['text'] for w in fila['words']).strip()
        if not linea_txt:
            continue
        if _procesar_cabeceras_linea(linea_txt, estado):
            continue
        if not estado['cuenta_actual']:
            continue

        debitos = creditos = base = 0.0
        tarifa_mov = None
        nit = None
        nombre_words = []

        for w in fila['words']:
            t = w['text']
            if nit is not None:
                # Todo lo que sigue al NIT es el nombre del tercero.
                nombre_words.append(t)
                continue
            if _NIT_RE.match(t) and w['x0'] > splits['base_pct']:
                nit = t
                continue
            if _MONEY_RE.match(t):
                try:
                    val = float(t.replace(',', ''))
                except ValueError:
                    continue
                xr = w['x1']
                if xr <= splits['deb_cred']:
                    debitos += val
                elif xr <= splits['cred_base']:
                    creditos += val
                elif xr <= splits['base_pct']:
                    base += val
                else:
                    tarifa_mov = val   # columna de %

        if nit is None:
            continue
        nombre_tercero = ' '.join(nombre_words).strip()
        _registrar_movimiento(estado, debitos, creditos, base, tarifa_mov,
                              nit, nombre_tercero, linea_txt)


def _procesar_pagina_por_texto(texto, estado):
    """
    Fallback histórico (parseo por conteo de números) para PDFs de los que
    pdfplumber no logra extraer palabras con posición o encabezado de columnas.
    """
    for linea in texto.split('\n'):
        linea = linea.strip()
        if not linea:
            continue
        if _procesar_cabeceras_linea(linea, estado):
            continue
        if not estado['cuenta_actual']:
            continue

        m_mov = re.match(
            r'^([\d,\.]+(?:\s+[\d,\.]+){1,2})\s+(\d+\.\d+)\s+(\d{6,11})\s+(.+)$',
            linea,
        )
        if not m_mov:
            continue
        try:
            numeros_str = m_mov.group(1)
            tarifa_mov = float(m_mov.group(2))
            nit = m_mov.group(3)
            nombre_tercero = m_mov.group(4).strip()
            nums = [float(n.replace(',', ''))
                    for n in re.findall(r'[\d,\.]+', numeros_str)]
            if len(nums) == 2:
                debitos = 0.0
                creditos, base = nums
            elif len(nums) == 3:
                debitos, creditos, base = nums
            else:
                continue
            _registrar_movimiento(estado, debitos, creditos, base, tarifa_mov,
                                  nit, nombre_tercero, linea)
        except (ValueError, IndexError):
            continue


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
