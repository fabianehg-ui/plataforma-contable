# CÓMO SUBIR — Compra de productos agrícolas/pecuarios

Agrega el caso especial de **compra de productos agrícolas o pecuarios sin
procesamiento industrial**: retención **1.5%** con base mínima **92 UVT**
(≈ $4.818.408 con la UVT 2026), generalmente **excluidos de IVA**.
Fecha: 18-jul-2026. **Sin migración.**

## Qué trae

- Nuevo tipo de retención **RFAGRO** (agrícolas/pecuarios 1.5%, base 92 UVT) y
  **RFCAFE** (café pergamino/cereza 0.5%, base 160 UVT) en el catálogo estándar.
- Nuevo concepto **COMPRA_AGRICOLA** ("Compra productos agrícolas/pecuarios sin
  proceso", sin IVA por defecto, retención RFAGRO).
- El **clasificador** reconoce facturas agrícolas (café, ganado, agropecuaria,
  cosecha, hortalizas, avícola, porcícola…) y **sugiere el concepto agrícola**.
  Ahora ignora tildes, así "café/plátano" se detectan bien.
- Respeta la **base mínima de 92 UVT**: no retiene si la compra no la alcanza
  (con la misma casilla "Permitir retención" para el acumulado del día).

## Archivos

| Archivo | Cambio |
|---|---|
| `core/contable/conceptos.py` | + RFAGRO/RFCAFE y concepto COMPRA_AGRICOLA en el seed; clasificador con categoría "agricola" y normalización de tildes. |
| `tests/test_conceptos_lector.py` | + pruebas de clasificación agrícola, sugerencia y base mínima 92 UVT. **78 pruebas del paquete pasan.** |

## Cómo activarlo

Como el juego estándar cambió, en **🧩 Conceptos y tarifas** vuelve a pulsar
**⚡ Sembrar estándar** (es idempotente: no borra lo tuyo, agrega/actualiza).
Aparecerán RFAGRO, RFCAFE y el concepto COMPRA_AGRICOLA. Ajusta las cuentas a tu
PUC si hace falta.

> Recuerda que la base mínima solo se valida si `cn_valores_anuales` tiene la UVT
> del año (2026: 52.374).
