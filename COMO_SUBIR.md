# HOTFIX — ZIP con XML+PDF ya no duplica valores + crea el tercero

Corrige el bug de importar un ZIP con el **XML y el PDF de la misma factura**:
antes sumaba los dos valores. Fecha: 18-jul-2026. **Sin migración.**

## Qué cambia

- **`leer_zip`**: por cada documento lee **uno solo, prefiriendo el XML** sobre su
  representación PDF/imagen. Agrupa por nombre de archivo (FE4587.xml / FE4587.pdf
  → solo el XML) y, como segunda red, **deduplica por (NIT, número)** conservando
  el XML. Ya no se duplican los valores.
- Además, si una factura del ZIP **solo trae PDF**, ya no se descarta (antes, si
  había algún XML, las de solo-PDF se perdían).
- **Crear tercero si no existe**: al guardar el comprobante, cada NIT que no esté
  en `cn_terceros` se crea automáticamente con el nombre y régimen de la factura
  leída (o del directorio global de terceros si está disponible).

## Archivos

| Archivo | Cambio |
|---|---|
| `core/contable/lector_factura.py` | `leer_zip` reescrito (prioriza XML, no pierde solo-PDF) + `_dedupe_facturas` por (NIT, número). |
| `app_pages/21_Captura.py` | Al guardar, `_asegurar_tercero()` crea el tercero faltante con datos de la factura/directorio. |
| `tests/test_conceptos_lector.py` | + pruebas: XML+PDF misma factura no duplica; dedupe prefiere XML. **84 pruebas pasan.** |

Súbelos encima de los anteriores. La creación de tercero es silenciosa si aún no
corriste 015 (terceros) / 017 (directorio) — no rompe nada.
