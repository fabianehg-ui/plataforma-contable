# CÓMO SUBIR — Compras: régimen del proveedor + retención sugerida + lectura de ZIP

Mejora la lectura de facturas de compra: detecta el **régimen del proveedor**
(del XML) para sugerir qué retención aplicar, y acepta **ZIP** con una o varias
facturas. Fecha: 18-jul-2026.

## Sin migración

No requiere migración nueva. (Sigue pendiente correr la **016** para habilitar
los conceptos, si aún no lo hiciste.)

## Archivos (reemplazan los de la entrega de Conceptos + el hotfix)

| Archivo | Cambio |
|---|---|
| `core/contable/lector_factura.py` | + `_extraer_regimen` (lee `cbc:TaxLevelCode`: responsable/no responsable de IVA, Gran contribuyente O-13, Autorretenedor O-15, Agente reteIVA O-23, RST O-47). `leer_xml` ahora devuelve `regimen`. + `leer_zip` y `leer_facturas` (ZIP con varias facturas, incluye sub-ZIPs del bookmarklet DIAN). |
| `core/contable/conceptos.py` | + `ajustar_por_regimen(concepto, tipos_ret, tipos_iva, regimen)` → sugiere IVA y retenciones según el régimen, con notas. |
| `app_pages/21_Captura.py` | El uploader acepta **.zip**; si trae varias facturas, muestra selector. Muestra el **régimen del proveedor** leído. El bloque de concepto **pre-selecciona** IVA y retenciones según el régimen (editable). |
| `tests/test_conceptos_lector.py` | + pruebas de régimen, `ajustar_por_regimen` y lectura de ZIP (77… en total 59 pruebas del paquete pasan). |

## Reglas de sugerencia (compras) — todas editables antes de guardar

- **Proveedor NO responsable de IVA** → sin IVA descontable ni ReteIVA.
- **Proveedor autorretenedor de renta (O-15)** o **Régimen Simple (O-47)** →
  **no** se le practica ReteFuente de renta.
- **ReteICA** depende del municipio/actividad → se deja manual.

Son *sugerencias*: se pre-seleccionan en la Captura y tú las confirmas o cambias.

## Uso

1. En **✍️ Captura → 📄 Leer factura**, sube el **XML**, **PDF**, **imagen** o un
   **ZIP**. Si el ZIP trae varias, elige cuál cargar.
2. Verás el **régimen del proveedor** (ej. "Responsable de IVA · Autorretenedor").
3. En **⚡ Concepto programado**, el IVA y las retenciones vienen ya ajustados al
   régimen (con una nota explicando por qué). Ajusta si hace falta y genera las
   líneas.

> Nota: `lector_factura.py` reusa `parsear_xml_dian` y `extraer_xmls_de_zip_maestro`
> de `core/procesadores/procesador_dian_xml.py` (ya en el repo). Estos archivos
> incluyen todo lo de la entrega de Conceptos y el hotfix; súbelos encima.
