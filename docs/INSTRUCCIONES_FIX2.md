# 🔧 FIX v2 — Diagnóstico de error en Railway

## ¿Qué hace distinto esta versión?

`4b_Ingresos_POS.py` ahora muestra el **traceback COMPLETO** del error de import dentro de la pestaña STL. Así no necesitas ir a los logs de Railway — el mensaje aparece directamente en pantalla.

## ⚠️ IMPORTANTE: este FIX2 reemplaza el FIX anterior

Sube los **4 archivos** del ZIP a sus ubicaciones:

| Archivo | Destino en repo |
|---|---|
| `config_stl.json` | `core/data/config_stl.json` |
| `procesador_stl.py` | `core/procesadores/procesador_stl.py` |
| `4b_Ingresos_POS.py` | `app_pages/4b_Ingresos_POS.py` |
| `test_procesador_stl.py` | `tests/test_procesador_stl.py` |

## Qué hacer después de subir

1. **Push al repo** → Railway redespliega en ~2 minutos.
2. **Abre Ingresos POS** en la app.

### Caso A — Todo OK
La pestaña "4️⃣ Ventas STL (mayoristas)" funciona normal.

### Caso B — Si la pestaña STL muestra error
- Verás el **traceback exacto** en pantalla (sin tener que ir a Railway)
- Toma una captura y mándamela
- Con eso voy directo al fix

### Caso C — La página entera de Ingresos POS se rompe (como antes)
- Significa que el error es ANTES del import defensivo
- Ve a Railway → Deployments → último deployment → Logs
- Busca la línea con "Traceback" y mándame el log completo
