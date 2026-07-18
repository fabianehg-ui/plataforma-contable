# CÓMO SUBIR — Correcciones de movimiento (INTEGRAL)

Corrección de movimientos ya cargados, en dos modos: **por comprobante**
(traes el asiento y lo reemplazas cuadrado) y **por registros** (editas o
eliminas filas individuales de `cn_movimientos`). Fecha: 18-jul-2026.

## Sin migración

No requiere migración: usa `cn_movimientos` (núcleo 014). La corrección por
registros usa la columna `id` de `cn_movimientos` (presente en el 014).

## Archivos (estructura del repo)

| Archivo | Estado | Qué hace |
|---|---|---|
| `core/contable/servicio_contable.py` | **MOD** | + `buscar_movimientos` (filtros), `actualizar_movimiento(id)`, `eliminar_movimiento(id)`, `eliminar_comprobante(periodo,comp,doc)`, `reemplazar_comprobante(...)`. Todas respetan el período **protegido**. |
| `app_pages/24_Correcciones.py` | **NUEVO** | Página con 2 tabs: corrección por comprobante y por registros. |
| `Home.py` | **MOD** | Registra **🛠️ Correcciones** en el menú Sistema. *(Este Home.py también deja registrada la página 🧩 Conceptos y tarifas de la entrega anterior; si aún no subiste esa, este archivo cubre ambas.)* |
| `tests/test_correcciones.py` | **NUEVO** | 10 pruebas con un Supabase falso en memoria (update/delete por id, reemplazo de comprobante, respeto a período protegido, filtros). |

> Nota: `app_pages/24_Correcciones.py` referencia `listar_comprobantes_periodo`
> y `buscar_movimientos`, que viven en `servicio_contable.py`. Sube el
> `servicio_contable.py` de esta entrega (o el de la entrega del Libro Mayor +
> este MOD) para que ambos existan.

## Uso

**🧾 Corrección por comprobante** — Elige período → *Cargar comprobantes* →
selecciona el asiento → *Cargar asiento*. Edita las líneas (agregar/quitar),
ajusta la fecha, y **Guardar corrección** reemplaza el asiento entero validando
que quede **Db = Cr**. También puedes **eliminar el asiento completo**.

**📋 Corrección por registros** — Filtra por período / comprobante / documento /
cuenta / NIT / origen → *Buscar*. Edita cualquier campo (fecha, cuenta, NIT,
detalle, TR, valor, base, centro de costo) y marca **🗑️** para eliminar filas.
Antes de guardar, un resumen muestra qué comprobantes quedarían **descuadrados**
(editar un valor suelto puede desbalancear el asiento; el aviso te deja verlo).

## Seguridad

- Si el período está **protegido** (🔒), no se puede corregir ni eliminar; la
  app lo bloquea y avisa. Ábrelo desde 📚 Contabilidad → Períodos si necesitas.
- Las líneas corregidas se guardan con `origen = 'correccion'`.
