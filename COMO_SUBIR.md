# CÓMO SUBIR — Retención respetando base mínima (UVT) + permitir por acumulado del día

Corrige la retención para que **respete la base mínima por normatividad** y no la
saque "al azar" cuando la base no la alcanza; anula por régimen (ya existía) y
agrega la opción de **permitir retención** por compras del día acumuladas.
Fecha: 18-jul-2026. **Sin migración.**

## El problema que corrige

En la captura, una compra de base **$17.435** sacaba ReteFuente de $436, cuando
la base mínima de retención por compras es **27 UVT (~$1.414.098 con la UVT 2026)**.
Ahora **no retiene** si la base no alcanza el mínimo.

## Reglas

- **Base mínima**: cada tipo de retención tiene `base_uvt`; el mínimo en pesos =
  `base_uvt × UVT` (la UVT se lee de `cn_valores_anuales` del año). Si la base
  gravable es menor, la retención **no se practica**.
- **Por régimen** (ya estaba): autorretenedor / Régimen Simple → sin retefuente;
  no responsable de IVA → sin IVA ni reteIVA.
- **Permitir retención**: casilla en la Captura para **forzar** la retención
  aunque la base no alcance el mínimo — para cuando una compra es parte de varias
  facturas del mismo tercero/día que **sí** suman la base.

## Archivos (reemplazan los de las entregas anteriores)

| Archivo | Cambio |
|---|---|
| `core/contable/conceptos.py` | `calcular_retencion(uvt, forzar)` respeta la base mínima; + `base_minima_pesos`, `evaluar_retenciones`; `aplicar_concepto(uvt, forzar_retencion)`. |
| `app_pages/21_Captura.py` | Lee la **UVT** del año (`cn_valores_anuales`); casilla **“Permitir retención…”**; avisos por retención (“no se aplica — base $X < mínimo $Y (27 UVT)”). |
| `tests/test_conceptos_lector.py` | + pruebas de base mínima, forzar y evaluación. **74 pruebas del paquete pasan.** |

## Uso

En **✍️ Captura → ⚡ Concepto programado**, al elegir base y retenciones verás,
por cada retención, si **aplica** o **no** (con el motivo y el mínimo). Si la
compra es parte de varias del día, marca **“Permitir retención…”** para forzarla.

> Requiere que `cn_valores_anuales` tenga la **UVT** del año (2026: 52.374). Si no
> la encuentra, avisa y no valida el mínimo (se comporta como antes). Estos
> archivos incluyen todo lo previo de sus módulos.
