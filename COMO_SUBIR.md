# CÓMO SUBIR — Libro Mayor y Balances + Comprobante de Diario (INTEGRAL)

Entrega del ítem de roadmap **#2: Libro mayor y libros oficiales + comprobante
de diario (impresión del asiento)**. Fecha: 18-jul-2026.

## Archivos (respetan la estructura del repo)

| Archivo | Estado | Qué hace |
|---|---|---|
| `core/contable/servicio_contable.py` | **MOD** | + `libro_mayor` / `_calc_libro_mayor` (con nivel de agregación), + `listar_comprobantes_periodo` / `_agrupar_comprobantes` (libro diario), + `comprobante_diario` / `_calc_comprobante` (arma el asiento). |
| `core/contable/pdf_comprobante.py` | **NUEVO** | `generar_pdf_comprobante(datos)` → bytes. Impresión del asiento con reportlab (encabezado empresa, líneas Db/Cr, totales, cuadre, firmas). |
| `app_pages/20_Contabilidad.py` | **MOD** | Dos tabs nuevos: **📓 Libro mayor** (y balances, por nivel) y **🧾 Comprobante de diario** (selector por período, asiento, PDF/Excel, y libro diario del período). |
| `tests/test_libro_mayor_comprobante.py` | **NUEVO** | 17 pruebas puras (agregación por nivel, saldo anterior/final, cuadre por asiento, PDF válido). |

## Pasos

1. Copia los 4 archivos en las mismas rutas del repo (reemplaza los MOD).
2. **No requiere migración nueva.** Todo se lee de `cn_movimientos` y
   `cn_plan_cuentas` / `cn_comprobantes` que ya existen (migración 014).
3. `reportlab` ya está en `requirements.txt` (se usa en el F350), no hay que
   agregar dependencias.
4. No hay cambios en `Home.py`: los tabs viven dentro de la página
   **Contabilidad (Libros)** que ya está registrada.
5. (Opcional) Corre las pruebas: `pytest tests/test_libro_mayor_comprobante.py -v`.

## Notas de uso

- **Libro Mayor y Balances**: elige rango Desde/Hasta y el *nivel de agregación*
  (Clase 1 díg · Grupo/Mayor 2 díg · Cuenta 4 díg · Subcuenta 6 díg · Auxiliar
  completo). Muestra saldo anterior, débitos, créditos y saldo final por cuenta,
  con verificación de cuadre y descarga a Excel. El nivel "Grupo/Mayor (2 díg)"
  es el libro mayor oficial clásico.
- **Comprobante de diario**: elige período → *Cargar comprobantes* → aparece el
  **libro diario** del período (lista cronológica de asientos con su cuadre) y un
  selector de asiento. Al *Ver/imprimir* se muestra el asiento (débitos primero)
  y se puede descargar el **PDF** del comprobante o el Excel.
- El PDF marca claramente si el asiento **cuadra** (Db = Cr) o descuadra.
