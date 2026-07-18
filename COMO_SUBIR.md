# CÓMO SUBIR — Auto-concepto + IVA diferencial + Imprimir comprobante

Tres mejoras en la Captura de compras. Fecha: 18-jul-2026. **Sin migración.**

## Qué trae

1. **Concepto automático.** Al leer una factura, INTEGRAL detecta la categoría
   (compra de bienes, servicios, honorarios o arrendamiento) por las palabras
   clave del proveedor y de los ítems, y **pre-selecciona el concepto** que calza.
2. **IVA diferencial → bases separadas.** Si la factura trae varias tarifas de
   IVA (19% + 5% + excluido…), el lector devuelve la **base y el IVA por tarifa**,
   y el asiento se arma con **una línea de base y una de IVA por cada tarifa**
   (cuadra Db = Cr). Ejemplo real probado: base 2.000.000 @19% + 1.000.000 @5%.
3. **Imprimir (PDF).** Junto a *Guardar* hay ahora un botón **🖨️ Imprimir (PDF)**
   que genera el comprobante de diario del asiento en pantalla (aunque sea
   borrador), con encabezado, líneas Db/Cr, totales, cuadre y firmas.

## Archivos (reemplazan los de las entregas anteriores)

| Archivo | Cambio |
|---|---|
| `core/contable/lector_factura.py` | + `bases_por_tarifa` en `leer_xml` (agrupa ítems por tarifa) y en el resultado de texto (PDF/imagen). |
| `core/contable/conceptos.py` | `aplicar_concepto` acepta `desglose_iva` (líneas de base e IVA separadas por tarifa); + `clasificar_factura` y `sugerir_concepto`. |
| `app_pages/21_Captura.py` | Auto-selección del concepto sugerido; desglose por tarifa cuando la factura es multi-tarifa; botón **🖨️ Imprimir (PDF)** junto a Guardar. Importa `generar_pdf_comprobante`. |
| `tests/test_conceptos_lector.py` | + pruebas de bases por tarifa, desglose en `aplicar_concepto` y sugeridor de concepto. **66 pruebas del paquete pasan.** |

> Requiere que ya exista `core/contable/pdf_comprobante.py` (entrega del Libro
> Mayor + Comprobante). Estos archivos incluyen todo lo previo de sus módulos.

## Uso

1. **✍️ Captura → 📄 Leer factura** (XML/PDF/imagen/ZIP). Al leerla:
   - El **concepto** se pre-selecciona solo (verás "🤖 sugerido por la factura").
   - Si trae **tarifas diferenciales**, aparece la tabla de bases por tarifa y el
     asiento generado separa las bases (una línea por tarifa).
2. Genera las líneas, revisa/ajusta, y usa **💾 Guardar** o **🖨️ Imprimir (PDF)**.

Todo sigue siendo editable antes de guardar; las sugerencias no obligan.
