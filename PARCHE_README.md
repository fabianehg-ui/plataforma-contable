# Parche consolidado v5 — JIPER (mayo 2026)

Este parche incluye todo el trabajo acumulado de los turnos anteriores
**MÁS** los 3 cambios pedidos en este turno:

## 🆕 Cambios de este turno

En el flujo "POS desde Token" (modo del módulo Ventas POS):

1. **Solo ventas POS** — eliminados del plano:
   - DSE (Documentos Soporte Electrónicos)
   - STL detalladas (facturación con IVA 19%)
   - NCs STL detalladas

2. **Orden cronológico ascendente** — el plano sale de fecha más
   antigua arriba a fecha más reciente abajo.

3. **DOCUMENTO = día del mes** — para fecha `15/03/2026` el documento
   es simplemente `15` (sin prefijo, sin año). Esto reemplaza el
   formato anterior `POS-VIV-20260315`.

## Otros cambios técnicos en este turno

- **NCs POS** (NCVI, NCT, NCLU, NCFA...) ahora se cruzan correctamente
  con sus FE del mismo día/sucursal aunque tengan prefijo distinto.
  Antes el código indexaba por `(fecha, prefijo)` y como `VIV ≠ NCVI`,
  la NC quedaba "huérfana". Ahora indexa por `(fecha, cc)` para que
  las NCs POS se fusionen al asiento del día/sucursal correcto.

- **Detección de tipo de documento** más robusta: el procesador antes
  buscaba match exacto (`"Factura electrónica"` con acento) — si el
  Excel del Token traía `"Factura electronica"` sin acento, no
  reconocía. Ahora hace match case-insensitive con palabras clave
  (`"factura" + "electr"`, `"nota" + "credit"`, etc.).

- **Prefijos no mapeados** (ej. un prefijo nuevo que no esté en
  `mapeo_prefijos_token.json`) se descartan silenciosamente en
  modo solo_pos en vez de quedar sin sucursal.

## Validación del modo solo_pos

Con un Excel del Token sintético desordenado:

```
Día 20 - VIV 108k
Día 5  - IND 54k
Día 15 - VIV 108k
Día 15 - VIV 216k
Día 15 - NCVI 54k (NC de Viva Envigado)
Día 10 - STL 119k       ← se descarta
Día 12 - DSE 50k        ← se descarta
Día 8  - XXX 1k         ← prefijo no mapeado, se descarta
```

Plano resultante (12 líneas, ordenado):
```
401  03/05/2026  doc=5    ...IND  3 líneas (1 fac)
406  03/15/2026  doc=15   ...VIV  6 líneas (2 facs + 1 NC = 324k - 54k)
406  03/20/2026  doc=20   ...VIV  3 líneas (1 fac)
```

Cuadre Db $540k = Cr $540k ✓

## Modo "completo" preservado

El modo legacy ("completo") sigue intacto: STL, DSE y NCs STL se procesan
como antes. Solo la página `4b_Ingresos_POS.py` (modo Token POS) usa el
nuevo modo `solo_pos` por defecto.

## Tests

**51 tests pasan**, 0 regresiones.

- `tests/test_pos_propinas.py`             6 tests (propinas modo Reportes)
- `tests/test_pos_token_propinas.py`       5 tests (propinas modo Token)
- `tests/test_agregador_terceros_xml.py`   7 tests
- `tests/test_filtros_descargador.py`      7 tests
- `tests/test_modo_solo_pos.py`            8 tests ← NUEVO
- `tests/test_pos_token.py`                18 tests (preexistente sigue OK)

## Cómo se ve el plano POS desde Token

| COMPROBANTE | FECHA      | DOCUMENTO | CUENTA   | DETALLE                                | TR | VALOR    | CC      |
|-------------|------------|-----------|----------|----------------------------------------|----|----------|---------|
| 401         | 03/05/2026 | 5         | 11050510 | VENTAS POS Indiana 03/05/2026 (1 facs) | 1  | 54.000   | 001101  |
| 401         | 03/05/2026 | 5         | 41401501 | VENTAS POS Indiana 03/05/2026          | 2  | 50.000   | 001101  |
| 401         | 03/05/2026 | 5         | 24800505 | INC 8% - VENTAS POS Indiana 03/05/2026 | 2  | 4.000    | 001101  |
| 406         | 03/15/2026 | 15        | 11050515 | VENTAS POS Viva Envigado 03/15/2026... | 1  | 324.000  | 001106  |
| ...         | ...        | ...       | ...      | ...                                    |    |          |         |

## Cómo aplicar

Descomprime el ZIP encima del repo y commit. Reinicia Streamlit.
En el menú: Ventas POS → "💾 Excel del Token DIAN".
