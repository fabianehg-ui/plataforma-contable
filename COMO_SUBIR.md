# CÓMO SUBIR — Puente contable (todo conectado a cn_movimientos)

Base para que cada módulo cause o lea de la contabilidad, + Centro Contable de
trazabilidad. Fecha: 18-jul-2026. **Sin migración.**

## Archivos

| Archivo | Estado | Qué hace |
|---|---|---|
| `core/contable/integracion.py` | **NUEVO** | `contabilizar`, `resumen_por_origen`, `reversar_origen`, `retenciones_practicadas`, registro `ORIGENES`. |
| `core/contable/ui_contabilizar.py` | **NUEVO** | `render_contabilizar(sb, empresa, df_plano, origen)` — bloque reusable para causar desde cualquier módulo. |
| `app_pages/26_Centro_Contable.py` | **NUEVO** | 🔗 Centro Contable: qué causó cada módulo por período + reversar. |
| `app_pages/4a_Ventas_C13.py` | **MOD** | Conectado: botón de causar el plano de ventas. |
| `app_pages/3a_Compras_y_Egresos.py` | **MOD** | Conectado: botón de causar el plano de compras. |
| `Home.py` | **MOD** | Registra 🔗 Centro Contable (en Reportes). |
| `tests/test_integracion.py` | **NUEVO** | Pruebas del puente (contabilizar, trazabilidad, reversar, retenciones). |
| `tests/test_correcciones.py` | **MOD** | Fake Supabase con `upsert` (para las pruebas). |

Sin migración: usa `cn_movimientos` del núcleo. **91 pruebas pasan.**

## Uso

- **Causar desde un módulo**: en Ventas C13 y Compras, tras generar el plano,
  aparece **💾 Contabilizar en INTEGRAL** (elige período → guarda). La nómina ya
  lo hacía.
- **Ver todo**: **📈 Reportes → 🔗 Centro Contable** muestra, por período, qué
  causó cada módulo (nómina, ventas, compras, captura, pagos…) y permite
  **reversar** lo de un módulo para reprocesar.

## Conectar el resto (POS, Bancos, Bittal) y módulos nuevos

Es de 1 línea donde el módulo tenga su `df_plano`:
```python
render_contabilizar(sb, emp, df_plano, "mi_origen")
```
Ver `ARQUITECTURA_PUENTE_CONTABLE.md` (POS usa la variable `empresa`; Bancos/Bittal
producen texto/filas y hay que pasarlos a DataFrame de 11 columnas primero).
