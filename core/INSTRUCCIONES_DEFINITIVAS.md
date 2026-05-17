# 🎯 FIX DEFINITIVO — Error de import en Railway

## El error real

```
ImportError: cannot import name 'parsear_notas_credito_token' from 
'core.procesadores.parser_token_dian'
```

**Causa:** el archivo `parser_token_dian.py` en GitHub/Railway está en una versión **antigua** que NO tiene las funciones `parsear_notas_credito_token` ni `generar_lineas_nc_pos` que necesita el módulo POS+NC.

Esas funciones se añadieron en la **sesión anterior** (módulo POS+Token+NC), pero al parecer ese archivo no se subió completo al repo.

## 📂 Archivos a subir al repo

Este ZIP contiene **TODOS los archivos del flujo completo**. Sube cada uno a su ruta exacta:

| Archivo del ZIP | Ruta en el repo | Status esperado |
|---|---|---|
| `parser_token_dian.py` | `core/procesadores/parser_token_dian.py` | **CRÍTICO - el que falta** ⚠️ |
| `procesador_pos.py` | `core/procesadores/procesador_pos.py` | Por si acaso |
| `comparador_pos_token.py` | `core/procesadores/comparador_pos_token.py` | Por si acaso |
| `procesador_stl.py` | `core/procesadores/procesador_stl.py` | NUEVO |
| `config_stl.json` | `core/data/config_stl.json` | NUEVO |
| `datos_punto.json` | `core/data/datos_punto.json` | Por si acaso |
| `4b_Ingresos_POS.py` | `app_pages/4b_Ingresos_POS.py` | NUEVO/MODIFICADO |
| `test_procesador_stl.py` | `tests/test_procesador_stl.py` | Tests |

## 🚀 Pasos

1. **Antes de subir**, verifica en GitHub que tu `parser_token_dian.py` actual NO tenga la función `parsear_notas_credito_token`:
   - Abre el archivo en GitHub
   - Ctrl+F → buscar `parsear_notas_credito_token`
   - Si NO aparece → es la versión vieja, hay que actualizar
   - Si SÍ aparece → es otro problema, mándame el log de nuevo

2. **Sube el parser_token_dian.py** del ZIP a `core/procesadores/parser_token_dian.py`

3. **Sube los demás archivos** que también faltan (mejor todos por seguridad)

4. **Commit + push** → Railway redesplegará en ~2 min

5. **Abre la app** y la pestaña Ingresos POS debería funcionar normal

## ✅ Verificación post-deploy

En la app deberías ver:
- Las 4 pestañas: Procesar separado, Procesar único, Conciliar Token DIAN, Ventas STL
- Sin error de ImportError
- La pestaña "4️⃣ Ventas STL (mayoristas)" abriendo correctamente

## 🤔 ¿Por qué ocurrió esto?

El flujo POS+Token+NC se implementó en la sesión anterior con varios archivos modificados:
- `parser_token_dian.py` (añadidas funciones NC)
- `procesador_pos.py` (mejoras)
- `comparador_pos_token.py` (nuevo)
- `4b_Ingresos_POS.py` (pestaña Token DIAN)
- `datos_punto.json` (mapeo prefijos_token_nc)

Al parecer, en el deploy de esa sesión, **el `parser_token_dian.py` no se subió** o se subió a otra ruta. El error solo afloró ahora porque ESTA versión del `4b_Ingresos_POS.py` (la del módulo STL) trata de importarlo al inicio, y antes ese error estaba "oculto" porque la pestaña Token DIAN nunca se abrió.
