# Parche consolidado v4 — JIPER (mayo 2026)

Este parche incluye:

- **Bloque 1**: terceros nuevos desde XMLs + propinas en POS (reportes)
- **Bloque 2**: nueva página unificada Descargador XML DIAN
- **Bloque 3**: modo "Excel del Token" dentro de Ventas POS
- **Bloque 4** (este turno): **configuración multi-empresa JIPER**
  + fix del procesador para que respete cuentas/CC propios de cada empresa

## Cómo aplicar

Descomprime el ZIP encima del repo y commit.

---

## Bloque 4 — Configuración multi-empresa JIPER

### Problema diagnosticado (de la captura del usuario)

La descarga de 2.886 XMLs funcionó bien, pero al procesar:
```
❌ NIT receptor no coincide con ninguna empresa configurada:
   79719025, 811045607, 890900608, 900480569, 900522508, 900539719,
   900665107, 901038325, 901446831, 901760889
```

Causa: el motor requiere una carpeta `core/data/empresas/<NIT>_<slug>/` con
los archivos JSON de configuración. Solo Silla Tres estaba configurada.

### Solución

Se crea la carpeta `core/data/empresas/901038325_jiper/` con los 6 archivos
de configuración base de JIPER, lista para que el descargador procese sus
XMLs. Las otras 8 NITs siguen marcándose como "no configurada" (son ruido
o empresas que se agregarán después).

### Archivos creados para JIPER

```
core/data/empresas/901038325_jiper/
├── empresa.json              ← datos fiscales, cuentas, comprobantes
├── centros_costo.json        ← 30 CCs reales del histórico
├── mapeo_nits.json           ← {} (vacío, se llena después)
├── direcciones_locales.json  ← {} (vacío, se llena después)
├── palabras_clave_cc.json    ← {} (vacío, se llena después)
└── retenciones.json          ← tabla DIAN 2026 + config JIPER
```

Y se actualiza `core/data/empresas/_empresas_index.json` para registrar
JIPER al lado de Silla Tres.

### Datos clave de JIPER

| Campo                     | Valor                                           |
|---------------------------|-------------------------------------------------|
| NIT                       | 901038325                                       |
| Razón social              | JIPER SAS                                       |
| Régimen                   | Ordinario, responsable IVA                      |
| Comprobante FE recibida   | 3 (Causación factura compra)                    |
| Comprobante NC recibida   | 12                                              |
| Comprobante ND recibida   | 7                                               |
| Comprobante DS recibido   | 3                                               |
| Cuenta proveedores default| 22050505                                        |
| Cuenta pendiente revisión | 519095                                          |
| CC default                | 001001 (ADMINISTRACION)                         |
| Formato CC en plano       | `tal_cual` (6 dígitos, sin guion)               |
| Cuenta INC ventas POS     | 24800505                                        |
| Cuenta propinas           | 28150505                                        |
| ICA municipio             | MEDELLIN                                        |

### Centros de costo (30 CCs reales)

```
ADMINISTRATIVOS:
  001001  ADMINISTRACION
  001002  CDP LA REGIONAL
  001003  CDP MEDELLIN
  001004  LINEA INSTITUCIONAL

SUCURSALES SANTA LEÑA (SL):
  001101  SL INDIANA              001112  SL FABRICATO
  001102  SL OVIEDO               001113  SL LOS MOLINOS
  001103  SL EL TESORO            001114  SL UNICENTRO
  001104  SL SAN LUCAS            001115  SL LAS VEGAS
  001105  SL DEL ESTE             001116  SL MEDICAL TOWER
  001106  SL VIVA ENVIGADO        001117  SL MILLA DE ORO
  001107  SL LAURELES             001118  SL HOTEL NOCK
  001108  SL LLANOGRANDE          001300  SL VENDING
  001109  SL BURBUJA POBLADO
  001110  SL MIXY LOS COLORES
  001111  SL CIUDAD DEL RIO

SUCURSALES MILAGROS (ML):
  001201  ML EL TESORO            001205  ML FABRICATO
  001202  ML REMEDIOS             001206  ML MANILA
  001203  ML VIVA ENVIGADO        001207  ML MILLA DE ORO
  001204  ML LAURELES
```

### Fix del procesador legacy v0.2

`core/procesadores/procesador_dian_xml.py` tenía 2 hardcoded que rompían
el funcionamiento multi-empresa:

1. **Cuenta de contrapartida**: estaba `22050501` literal en el código.
   Ahora lee `empresa.cuentas_proveedores.default` (JIPER usa `22050505`).

2. **CC default**: usaba `empresa.get("centro_costo_default", "ADMIN")`,
   pero JIPER tiene `cc_default` (no `centro_costo_default`).
   Ahora hace fallback: primero `centro_costo_default`, luego `cc_default`,
   luego `"ADMIN"` literal como último recurso.

**Validación**: con un XML cuyo receptor es JIPER:
```
Comp 3 | cta=519095   cc=001001 | NIT=900xxxxxx | Db $100,000  Cr $0       ← Gasto pendiente
Comp 3 | cta=22050505 cc=001001 | NIT=900xxxxxx | Db $0       Cr $100,000  ← Proveedor JIPER ✓
```

Y con un XML de Silla Tres:
```
Comp 3 | cta=519095   cc=10-10  | NIT=900xxxxxx | Db $100,000  Cr $0
Comp 3 | cta=22050501 cc=10-10  | NIT=900xxxxxx | Db $0       Cr $100,000  ← Proveedor Silla Tres ✓
```

Cada empresa con su propia configuración.

### Cómo agregar más empresas después

El usuario mencionó que va a agregar más empresas. El procedimiento es:

1. Crear carpeta `core/data/empresas/<NIT>_<slug>/`.
2. Copiar los 6 archivos JSON de JIPER (o de Silla Tres) como plantilla.
3. Ajustar en `empresa.json`:
   - NIT, DV, razón social
   - Comprobantes propios
   - Cuentas IVA, propinas, proveedores, pendiente revisión
   - `cc_default`
4. Llenar `centros_costo.json` con los CCs reales.
5. `mapeo_nits.json`, `direcciones_locales.json` y `palabras_clave_cc.json`
   pueden quedar vacíos al inicio (se llenan después).
6. Copiar `retenciones.json` de cualquier empresa existente (tabla DIAN 2026
   es la misma).
7. Registrar en `_empresas_index.json`.

El procesador detecta automáticamente la empresa por NIT receptor y aplica
su configuración propia.

---

## Bloque 3 — Ventas POS con dos fuentes (recap del turno anterior)

`app_pages/4b_Ingresos_POS.py` ahora tiene un selector:

```
⦿ 📊 Reportes POS (CHILI, L3AF, HENKO)       ← flujo original
⦿ 💾 Excel del Token DIAN                     ← flujo nuevo
```

Modo Token: lee el Excel, detecta prefijos, mapea a sucursal/CC/cuenta
con `mapeo_prefijos_token.json` y asienta propinas a `28150505`.

---

## Bloque 2 — Página `5b_Descargador_XML.py` (recap)

Subir Excel del Token → marcar tipos recibidos / prefijos emitidos →
descargar en hilos de 500 docs → procesar a plano contable +
plano de terceros nuevos para Siigo.

---

## Bloque 1 — Terceros + propinas POS reportes (recap)

Parser extendido, agregador de terceros, propinas con fórmula
`base = INC/0.08` y `propina = total − base − INC`.

---

## Archivos modificados/nuevos en este parche v4

```
Home.py                                                  (+11 líneas, sin remover nada)

# Bloque 1
app_pages/5a_DIAN_XML.py                                 (modificado)
core/procesadores/agregador_terceros_xml.py              (NUEVO)
core/procesadores/exportador_nits_siigo.py               (modificado)
core/procesadores/procesador_pos.py                      (modificado — propinas)
datos_punto.json                                         (modificado — cta_propinas)
core/data/datos_punto.json                               (modificado — cta_propinas)

# Bloque 2
app_pages/5b_Descargador_XML.py                          (NUEVO)

# Bloque 3
app_pages/4b_Ingresos_POS.py                             (+ selector modo)
core/procesadores/procesador_ventas_excel_token_v2.py    (modificado — propinas Token)

# Bloque 4 (este turno)
core/data/empresas/901038325_jiper/empresa.json          (NUEVO)
core/data/empresas/901038325_jiper/centros_costo.json    (NUEVO — 30 CCs)
core/data/empresas/901038325_jiper/mapeo_nits.json       (NUEVO — vacío)
core/data/empresas/901038325_jiper/direcciones_locales.json (NUEVO — vacío)
core/data/empresas/901038325_jiper/palabras_clave_cc.json   (NUEVO — vacío)
core/data/empresas/901038325_jiper/retenciones.json      (NUEVO — tabla DIAN 2026)
core/data/empresas/_empresas_index.json                  (modificado — +JIPER)
core/procesadores/procesador_dian_xml.py                 (modificado — fix multi-empresa)

# Tests
tests/test_pos_propinas.py                               (NUEVO — 6 tests)
tests/test_pos_token_propinas.py                         (NUEVO — 5 tests)
tests/test_agregador_terceros_xml.py                     (NUEVO — 7 tests)
tests/test_filtros_descargador.py                        (NUEVO — 7 tests)
```

## Tests

**43 tests pasan**, 0 regresiones.

```
tests/test_pos_propinas.py             6 passed
tests/test_pos_token_propinas.py       5 passed
tests/test_agregador_terceros_xml.py   7 passed
tests/test_pos_token.py               18 passed   (preexistente, sigue OK)
tests/test_filtros_descargador.py      7 passed
```

Validaciones manuales adicionales:
- ✅ JIPER detectado correctamente, plano cuadrado con cuenta 22050505 y CC 001001.
- ✅ Silla Tres sin cambios: plano cuadrado con cuenta 22050501 y CC 10-10.
- ✅ Sintaxis válida en todos los archivos.
- ✅ Carga del CatalogoEmpresa funciona para JIPER (30 CCs, 26 conceptos retención).

## Resumen para usar

1. Aplicar este ZIP encima del repo. Commit.
2. Reiniciar la app Streamlit.
3. En el sidebar verás `📥 Descargador XML DIAN` (en Asistente Contable).
4. Subir el Excel del Token, marcar lo que quieras descargar, descargar
   con 500 docs/hilo paralelo, procesar.
5. El plano de JIPER saldrá cuadrado con su comprobante 3 (FE/DS), 12 (NC),
   7 (ND), su cuenta 22050505 de proveedores y CC 001001 por defecto.
6. Conforme vayas mapeando proveedores específicos (que ahora caen a 519095
   por pendiente_revision), agregarlos a `mapeo_nits.json` con su cuenta de
   gasto y CC correspondiente.
