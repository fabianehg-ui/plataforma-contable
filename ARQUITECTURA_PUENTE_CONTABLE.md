# Puente contable — todo conectado a cn_movimientos

`cn_movimientos` es el **libro central** de INTEGRAL. Cada módulo (existente o
futuro) o **escribe** (causa su plano) o **lee** de la contabilidad.

## Base reusable

`core/contable/integracion.py`
- `contabilizar(sb, empresa_id, periodo, df_plano, origen, reemplazar=…)` — causa
  el plano de 11 columnas en `cn_movimientos` con período y etiqueta `origen`.
- `resumen_por_origen(sb, empresa_id, periodo)` — qué causó cada módulo (líneas,
  Db, Cr, cuadre).
- `reversar_origen(sb, empresa_id, periodo, origen)` — deshace lo de un módulo
  sin tocar el resto (respeta período protegido).
- `retenciones_practicadas(sb, empresa_id, desde, hasta)` — lee la 2365 por NIT y
  concepto (alimenta Retención en la Fuente / F350 / exógena 1003).
- `movimientos_cuenta(...)` — lectura genérica por prefijo de cuenta.

`core/contable/ui_contabilizar.py`
- `render_contabilizar(sb, empresa, df_plano, origen)` — bloque Streamlit con
  selector de período, cuadre y botón de causar. **Conectar un módulo = esto.**

`app_pages/26_Centro_Contable.py` (🔗 Centro Contable, en Reportes)
- Trazabilidad por período: qué causó cada módulo + botón **Reversar** por módulo.

## Cómo conectar CUALQUIER módulo (incluidos los nuevos)

Donde el módulo ya tiene su `df_plano` (11 columnas: CUENTA · COMPROBANTE · FECHA
· DOCUMENTO · DOC REFERENCIA · NIT · DETALLE · TR · VALOR · BASE · CENTRO DE COSTO):

```python
from db.supabase_client import get_supabase
from core.contable.ui_contabilizar import render_contabilizar
sb = get_supabase()
...
render_contabilizar(sb, emp, df_plano, "mi_origen")   # 1 línea
```

Registra la etiqueta del origen en `integracion.ORIGENES` para que se lea bonito
en el Centro Contable. Nada más: queda causado, con trazabilidad y reversa.

## Estado de conexión

| Módulo | Estado |
|---|---|
| **Nómina** | Ya causa (origen `nomina_mes`); se ve en Centro Contable |
| **Captura / Cruce (pagos, recaudos)** | Ya causan (origen captura/pago/recaudo) |
| **Ventas C13** | ✅ Conectado en esta entrega |
| **Compras y Egresos** | ✅ Conectado en esta entrega |
| **Ingresos POS** | Pendiente (usa var `empresa`; misma línea) |
| **Bancos / Bittal** | Pendiente: su salida es texto/filas, hay que pasarla a DataFrame 11-col antes del `render_contabilizar` |
| **Retención en la Fuente (F350)** | Helper `retenciones_practicadas` listo para alimentar el F350 desde la contabilidad |

## Lectura: Retención en la Fuente desde la contabilidad

`retenciones_practicadas(sb, empresa_id, desde, hasta)` devuelve, por NIT y
subcuenta 2365 (= concepto), la retención practicada (saldo crédito). Eso es
exactamente lo que necesita el F350 / el Formato 1003. Próximo paso: enchufarlo
en la página de Retención para que el borrador salga solo de la contabilidad.
