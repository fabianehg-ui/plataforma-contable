# Parche consolidado v3 — JIPER (mayo 2026)

Este parche agrega/modifica:

- **Bloque 1**: terceros nuevos desde XMLs + propinas en POS (reportes)
- **Bloque 2**: nueva página unificada Descargador XML DIAN
- **Bloque 3** (este turno):
  - Modo "Excel del Token" dentro de Ventas POS, con CC y propinas
  - Propinas asentadas a cuenta `28150505` también en el procesador Token

⚠️ `Home.py` SOLO se cambia para agregar la página nueva del Descargador XML.
Todas las herramientas existentes siguen visibles.

## Cómo aplicar

Descomprime el ZIP encima del repo y commit.

---

## Bloque 1 — Terceros desde XMLs y propinas POS (reportes)

Ver detalle del turno anterior. Resumen:

- `core/procesadores/procesador_dian_xml.py` — parser extendido (dirección,
  ciudad, código DANE, email, teléfono, CIIU del emisor).
- `core/procesadores/agregador_terceros_xml.py` (NUEVO) — junta emisores y
  detecta NITs nuevos.
- `core/procesadores/exportador_nits_siigo.py` — acepta `codigo_ciudad` del XML.
- `core/procesadores/procesador_pos.py` — fórmula propinas con cuadre Db=Cr.

Fórmula propinas:
```
base_inc = INC / 0.08
propina  = Final - base_inc - INC
Cuenta propinas: 28150505 (PUC JIPER)
```

---

## Bloque 2 — Nueva página `5b_Descargador_XML.py`

Página simplificada de descarga y procesamiento de XMLs, **dentro** del
módulo Descargador XML DIAN.

Flujo (4 pasos):
1. Subir Excel del Token DIAN (referencia de los CUFEs).
2. Marcar tipos de documentos para recibidos (checkboxes) y prefijos para
   emitidos (multiselect). Application response y Nomina Individual OFF
   por default.
3. Pegar Token URL → descarga paralela en **hilos de hasta 500 documentos**.
4. Procesar → plano contable + plano de terceros nuevos.

**Tamaño de bloque**: 500 docs/hilo. Si descargas 1.234 docs → 3 hilos
(500 + 500 + 234) corriendo en paralelo.

Aparece en el sidebar como `📥 Descargador XML DIAN` al lado de las demás
herramientas, sin tocar nada del menú original.

---

## Bloque 3 (este turno) — Ventas POS con dos fuentes

### 3.1 Página `4b_Ingresos_POS.py` con selector de modo

Al entrar al módulo Ventas POS, ahora ves un selector arriba:

```
Elige la fuente de datos para generar el plano:
   ⦿ 📊 Reportes POS (CHILI, L3AF, HENKO)       ← flujo original sin tocar
   ⦿ 💾 Excel del Token DIAN                     ← flujo nuevo
```

**Modo A — Reportes POS**: igual que antes. Sube los 4 reportes, procesa,
descarga plano con propinas (las que vienen como diferencia
`Final − Neto − INC`).

**Modo B — Excel del Token DIAN**: sube el Excel del Token y la app:
- Lee y filtra por fecha.
- Detecta cada prefijo (STL, IND, OVI, VIV, MED, MMI, MTE, MRE, MVI, MLA,
  MFA, MMA, NCI, NCVI, NCT, etc. — los 50+ del repo).
- Mapea cada prefijo a su sucursal/CC/cuenta/comprobante usando
  `mapeo_prefijos_token.json`.
- Consolida por (día × prefijo) y asienta el plano con la misma fórmula
  de propinas que el flujo de reportes.
- Genera plano contable cuadrado Db=Cr listo para Siigo.

### 3.2 Propinas en el procesador Token

`core/procesadores/procesador_ventas_excel_token_v2.py` modificado:

**Antes:**
```python
total_bruto_contable = round(base + inc + iva + otros, 0)
# propina se acumulaba pero NO se asentaba (quedaba descuadrado)
```

**Ahora:**
```python
total_bruto_contable = round(base + inc + iva + otros + propina, 0)
# y se agrega línea:
Cr 28150505 (PROPINAS) = propina (si > $5)
```

Asiento POS Token (4-5 líneas según haya IVA y/o propina):
```
Db CUENTA DE CAJA   = base + INC + IVA + otros + propina
Cr 41401501         = base               (cta_base_v)
Cr 24800505         = INC                (cta_ico, solo si > 0)
Cr 24080501         = IVA                (solo si > 0)
Cr 28150505         = propina            (solo si > $5)
```

Cuadre Db=Cr garantizado por construcción.

CC propina = CC de la sucursal (igual que en histórico real de JIPER).

---

## Cambio en `Home.py`

Solo +11 líneas (registrar nueva página y agregarla al sidebar). Todas las
herramientas originales se conservan.

---

## Archivos modificados

```
Home.py                                                  (+11 líneas, 0 removidas)
app_pages/4b_Ingresos_POS.py                             (+ selector modo + flujo Token)
app_pages/5a_DIAN_XML.py                                 (modificado del bloque 1)
app_pages/5b_Descargador_XML.py                          (NUEVO — del bloque 2)
core/data/datos_punto.json                               (+cta_propinas)
core/procesadores/agregador_terceros_xml.py              (NUEVO)
core/procesadores/exportador_nits_siigo.py               (+codigo_ciudad)
core/procesadores/procesador_dian_xml.py                 (+campos extendidos emisor)
core/procesadores/procesador_pos.py                      (+propinas Modo Reportes)
core/procesadores/procesador_ventas_excel_token_v2.py    (+propinas Modo Token)  ← NUEVO
datos_punto.json                                         (+cta_propinas)
tests/test_pos_propinas.py                               (6 tests)
tests/test_pos_token_propinas.py                         (5 tests)  ← NUEVO
tests/test_agregador_terceros_xml.py                     (7 tests)
tests/test_filtros_descargador.py                        (7 tests)
```

## Tests

**43 tests pasan** (38 acumulados + 5 nuevos del modo Token POS). 0 regresiones.

```
tests/test_pos_propinas.py             6 passed   (Modo Reportes — propinas)
tests/test_pos_token_propinas.py       5 passed   (Modo Token — propinas)  ← NUEVO
tests/test_agregador_terceros_xml.py   7 passed   (terceros nuevos)
tests/test_pos_token.py               18 passed   (preexistente, sigue OK)
tests/test_filtros_descargador.py      7 passed   (filtros tipos/prefijos)
```

## Notas sobre hilos de descarga (pregunta del usuario)

Sí, en `5b_Descargador_XML.py` los hilos están configurados en **bloques de
hasta 500 documentos por hilo**:

```python
n_hilos_total = max(1, math.ceil(total_descargar / 500))
ctrl = dd.iniciar_descarga_paralela(
    token_url, cufes_pendientes,
    tam_bloque=500,  # ← 500 docs por hilo
    delay=0.15,
)
```

Ejemplos:
- 234 docs → 1 hilo
- 1.234 docs → 3 hilos paralelos (500 + 500 + 234)
- 2.500 docs → 5 hilos paralelos

Cada hilo es una sesión paralela; si el Token expira, los hilos restantes
siguen y los faltantes se pueden retomar con un Token nuevo (la página
detecta los ya descargados).

## Cómo se ve el menú

```
📊 Plataforma Contable
├── 🏠 Inicio
├── 🤖 Asistente Contable
│   ├── 💵 Caja Menor
│   ├── 📥 Procesar Token DIAN
│   ├── 💼 Nómina
│   ├── 📝 Provisiones
│   ├── 🛍️ Ventas C13
│   ├── 🧾 Ventas POS                    ← ahora con 2 modos adentro
│   ├── 📎 PILA
│   └── 📥 Descargador XML DIAN          ← agregado en el turno anterior
├── 📊 Herramientas Tributarias  (intacto)
└── ⚙️ Sistema  (intacto)
```
