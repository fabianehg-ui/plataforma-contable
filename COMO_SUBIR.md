# CÓMO SUBIR — Cruce de facturas: pagos y recaudos por tercero

Cartera abierta: al poner el NIT, el sistema sugiere las **facturas pendientes**
del tercero para marcarlas y cancelarlas (total o parcial), y arma el egreso o
el recibo de caja cuadrado. Fecha: 18-jul-2026. **Sin migración.**

## Cómo funciona (sin tablas nuevas)

Los pendientes se calculan de `cn_movimientos`: se agrupa por tercero (NIT) y
por documento (usa `doc_referencia`, y si no, `documento`) sumando Db−Cr. El
documento con saldo ≠ 0 está pendiente. Por eso **basta con que al causar/vender
cada línea de la cuenta por pagar/cobrar lleve el número de factura** — que es
justo lo que ya hace la Captura (documento = consecutivo de la factura).

## Archivos

| Archivo | Estado | Qué hace |
|---|---|---|
| `core/contable/servicio_contable.py` | **MOD** | + `documentos_pendientes(nit, prefijos)` y su cálculo puro `_calc_documentos_pendientes`. |
| `app_pages/25_Cruce_Facturas.py` | **NUEVO** | Página **💳 Pagos y Recaudos** con dos tabs: Pagar (egreso, cuentas por pagar) y Recaudar (recibo de caja, por cobrar). |
| `Home.py` | **MOD** | Registra la página en **🤖 Asistente Contable**. |
| `tests/test_correcciones.py` | **MOD** | + pruebas de pendientes (abono parcial, factura saldada que desaparece, por cobrar). **81 pruebas del paquete pasan.** |

## Uso

1. **🤖 Asistente Contable → 💳 Pagos y Recaudos**.
2. Tab **Pagar** (o **Recaudar**): escribe el **NIT** → *Buscar facturas pendientes*.
   - Aparecen las facturas con su saldo. Marca las que vas a cancelar y ajusta el
     **valor a cruzar** (permite abono parcial).
3. Elige el comprobante (egreso / recibo de caja), la fecha, el consecutivo y la
   **cuenta de banco/caja**, y **Genera y guarda**. El sistema:
   - Por cada factura marcada: Db la cuenta por pagar (o Cr la por cobrar), con
     `doc_referencia` = el número de la factura cancelada.
   - Contrapartida por el total a banco/caja. Cuadra Db = Cr.
4. Al volver a buscar ese tercero, las facturas ya canceladas no aparecen; las
   abonadas parcialmente muestran el saldo restante.

Prefijos por defecto — Pagar: `2205,2335,2505`; Recaudar: `1305,1330` (editables).
