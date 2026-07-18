# CÓMO SUBIR — Atajos de Captura: Conceptos programados + Lectura de facturas (INTEGRAL)

Convierte la Captura en casi-sin-digitación: conceptos programados (IVA y
retención parametrizados) que auto-arman el asiento, y lectura de facturas
(XML DIAN, PDF, imagen) para prellenar valores. Fecha: 18-jul-2026.

## 1. Correr la migración (Supabase → SQL Editor → pegar → Run)

**`db/migrations/016_conceptos_iva_retencion.sql`** — crea 3 tablas con RLS:
`cn_tipos_iva`, `cn_tipos_retencion`, `cn_conceptos`. (Se crean vacías; el
juego estándar se siembra por empresa desde la UI, ver paso 4.)

> Recordatorio: la **015_terceros.sql** también sigue pendiente de correr.

## 2. Archivos (estructura del repo)

| Archivo | Estado | Qué hace |
|---|---|---|
| `db/migrations/016_conceptos_iva_retencion.sql` | **NUEVO** | Tablas de tipos IVA/retención y conceptos + RLS + grants. |
| `core/contable/conceptos.py` | **NUEVO** | CRUD de tipos y conceptos; `aplicar_concepto(base, tipo_iva, retenciones, …)` que genera el asiento cuadrado Db=Cr; `sembrar_estandar()` con el juego colombiano. |
| `core/contable/lector_factura.py` | **NUEVO** | `leer_factura(nombre, bytes)` → dict normalizado. XML reusa el parser UBL (`parsear_xml_dian`), PDF con pdfplumber+heurística, imagen con OCR (tesseract). |
| `app_pages/21_Captura.py` | **MOD** | Bloque **📄 Leer factura** (prellena cabecera y base) y **⚡ Concepto programado** (autollena las líneas, editables). |
| `app_pages/23_Conceptos.py` | **NUEVO** | Pantalla para administrar conceptos y tarifas + botón **⚡ Sembrar estándar**. |
| `Home.py` | **MOD** | Registra la página **🧩 Conceptos y tarifas** en el menú Sistema. |
| `tests/test_conceptos_lector.py` | **NUEVO** | 22 pruebas puras (cuadre de asientos, reteIVA sobre IVA, lectura XML, heurística de texto). |
| `requirements.txt` | **MOD** | + `pytesseract`, `Pillow` (para OCR de imagen). |
| `Dockerfile` | **MOD** | + `tesseract-ocr` y `tesseract-ocr-spa` (binario OCR). |

## 3. Desplegar

1. Copia todos los archivos en sus rutas.
2. `requirements.txt` y `Dockerfile` cambiaron: en el próximo deploy de Railway
   se instalan `pytesseract`/`Pillow` y el binario `tesseract`. **Sin ese deploy,
   XML y PDF funcionan igual; solo el OCR de imagen queda deshabilitado** (la app
   avisa con un mensaje claro, no se rompe).
3. `reportlab`, `pdfplumber` y `lxml` ya estaban; el parser UBL ya existía.

## 4. Primer uso

1. Menú **⚙️ Sistema → 🧩 Conceptos y tarifas** → botón **⚡ Sembrar estándar**.
   Crea tipos de IVA (19/5/0 y generados), retenciones (compras 2.5%, servicios
   4/6%, honorarios 10/11%, arrendamiento 3.5%, reteIVA 15%, reteICA) y conceptos
   comunes de compra/venta. **Revisa y ajusta las cuentas a tu PUC** (las cuentas
   sembradas son defaults del PUC comercial).
2. En **✍️ Captura**:
   - **📄 Leer factura**: sube el XML/PDF/imagen → prellena NIT, número, fecha y base.
   - **⚡ Concepto programado**: elige el concepto y confirma la base → **Generar
     líneas** arma el asiento (Db=Cr) ya editable. Ajusta y **Guardar**.

## Notas contables

- Cada retención define su **base de cálculo**: `base` (retefuente, reteICA) o
  `iva` (reteIVA = 15% del IVA). Editable por tarifa/cuenta.
- Un concepto de **compra** arma: Db cuenta_base + Db IVA − Cr retención(es) −
  Cr contrapartida (neto). El de **venta** es el simétrico. Todo cuadra Db=Cr.
- El lector de XML es exacto (confianza *alta*); PDF/imagen son *mejor esfuerzo*
  (confianza media/baja) y siempre quedan editables antes de guardar.
