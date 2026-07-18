# HOTFIX — Captura no debe crashear si falta la migración 016 + base de factura

## Qué pasó

El error `postgrest.exceptions.APIError` en la Captura (línea
`cp.listar_conceptos(...)`) ocurre porque la tabla **`cn_conceptos` aún no
existe**: falta correr la migración **016_conceptos_iva_retencion.sql** en
Supabase. La página crasheaba en vez de avisar.

## ▶️ Acción principal (esto habilita los conceptos)

En **Supabase → SQL Editor → New query**, pega y corre:
`db/migrations/016_conceptos_iva_retencion.sql` (venía en la entrega de
"Conceptos + lectura de facturas"). Luego, en **🧩 Conceptos y tarifas**,
pulsa **⚡ Sembrar estándar**.

## Archivos de este hotfix (reemplazan los de la entrega anterior)

| Archivo | Cambio |
|---|---|
| `core/contable/conceptos.py` | + `tablas_existen()`: detecta si la migración 016 está aplicada, sin reventar. |
| `app_pages/21_Captura.py` | El bloque **⚡ Concepto programado** ahora degrada con un aviso ("corre la migración 016…") si las tablas no existen; puedes seguir digitando a mano. |
| `app_pages/23_Conceptos.py` | Si faltan las tablas, muestra el aviso y no intenta cargar (sin crash). |
| `core/contable/lector_factura.py` | **Base recalculada**: cuando el total ya incluye IVA (ej. total 26.900, IVA 2.016 → base **24.884**), la base se ajusta a `total − IVA + retenciones`. |

## Notas

- Sin correr la 016, XML y PDF/imagen siguen leyéndose para prellenar la
  cabecera; solo los **conceptos programados** quedan en espera con su aviso.
- La base leída siempre es editable antes de guardar (PDF/imagen es mejor esfuerzo).
- 49 pruebas siguen pasando.
