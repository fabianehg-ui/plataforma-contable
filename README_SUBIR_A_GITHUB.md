# 📦 Paquete final — Subir a GitHub web (15 minutos)

## 📂 Contenido del paquete

```
paquete_subir_a_github/
├── Home.py                                       ← REEMPLAZAR (RADIAN agregado al menú)
├── app_pages/
│   └── 6_RADIAN_Acuses_DIAN.py                  ← NUEVO (UI pantalla)
└── core/
    ├── exogena/
    │   └── conciliacion.py                       ← REEMPLAZAR (F1009 al 100%)
    └── radian/
        ├── __init__.py                           ← NUEVO (módulo init)
        └── procesador_acuses.py                  ← NUEVO (lógica filtrado)
```

**Total: 5 archivos**, ninguno requiere modificación manual de tu parte.

> ⚠️ **El patch hilos 700→500** lo dejé fuera del paquete porque requiere modificar
> `descargador_dian.py` (archivo que no tengo en mi contexto). Si quieres aplicarlo,
> ver al final de este README la sección **"Patch opcional hilos"**.

---

## 🚀 Subida a GitHub web — paso a paso

> Todo se hace desde `https://github.com/tu-usuario/plataforma-contable` en rama `main`.
> **No necesitas Git Bash, terminal, ni descargas**. Solo navegador + Bloc de notas.

---

### 📄 Archivo 1/5 — `Home.py` (REEMPLAZAR)

1. En GitHub, click en **`Home.py`** (en la raíz del repo)
2. Click en el lápiz ✏️ (esquina superior derecha del editor)
3. **Borra todo el contenido** (Ctrl+A → Delete)
4. **Abre** con Bloc de Notas el archivo `Home.py` del paquete
5. Selecciona todo (Ctrl+A) → Copia (Ctrl+C)
6. Pega en GitHub (Ctrl+V)
7. Baja al final de la página, en **"Commit changes"**:
   - Mensaje: `feat(nav): registrar RADIAN como primera opción en Tributarias`
   - Selecciona: **"Commit directly to the `main` branch"**
   - Click **"Commit changes"**

---

### 📄 Archivo 2/5 — `core/exogena/conciliacion.py` (REEMPLAZAR)

1. Volver a la raíz del repo
2. Click **`core`** → **`exogena`** → **`conciliacion.py`**
3. Click en el lápiz ✏️
4. **Borra todo** (Ctrl+A → Delete)
5. **Abre** con Bloc de Notas `core/exogena/conciliacion.py` del paquete
6. Copia (Ctrl+A → Ctrl+C) y pega (Ctrl+V) en GitHub
7. Commit:
   - Mensaje: `fix(exogena): F1009 reporta 100% saldo (Res 000227/2025)`
   - **"Commit directly to the `main` branch"**
   - Click **"Commit changes"**

---

### 📄 Archivo 3/5 — `core/radian/__init__.py` (NUEVO)

1. Volver a la raíz del repo
2. Click en **`core`** (entra a la carpeta)
3. Click en **"Add file"** → **"Create new file"** (botón verde, arriba derecha)
4. En el campo del nombre del archivo escribe **EXACTAMENTE**:
   ```
   radian/__init__.py
   ```
   ⚠️ La `/` crea la carpeta `radian` automáticamente
5. **Abre** con Bloc de Notas `core/radian/__init__.py` del paquete
6. Copia y pega en GitHub
7. Commit:
   - Mensaje: `feat(radian): paquete init del módulo nuevo`
   - **"Commit directly to the `main` branch"**
   - Click **"Commit new file"**

---

### 📄 Archivo 4/5 — `core/radian/procesador_acuses.py` (NUEVO)

1. Volver al repo, click en **`core`** → **`radian`** (la carpeta nueva que acabas de crear)
2. Click en **"Add file"** → **"Create new file"**
3. Nombre del archivo: `procesador_acuses.py` (sin barras, ya estás dentro de `radian/`)
4. **Abre** con Bloc de Notas `core/radian/procesador_acuses.py` del paquete
5. Copia y pega en GitHub
6. Commit:
   - Mensaje: `feat(radian): procesador acuses con 9 tests validados`
   - **"Commit directly to the `main` branch"**
   - Click **"Commit new file"**

---

### 📄 Archivo 5/5 — `app_pages/6_RADIAN_Acuses_DIAN.py` (NUEVO)

1. Volver a la raíz del repo
2. Click en **`app_pages`**
3. Click en **"Add file"** → **"Create new file"**
4. Nombre del archivo: `6_RADIAN_Acuses_DIAN.py`
5. **Abre** con Bloc de Notas `app_pages/6_RADIAN_Acuses_DIAN.py` del paquete
6. Copia y pega en GitHub
7. Commit:
   - Mensaje: `feat(ui): pantalla RADIAN Acuses DIAN`
   - **"Commit directly to the `main` branch"**
   - Click **"Commit new file"**

---

## ⏱️ Esperar Railway (1-2 minutos)

Railway detecta el último push y redespliega automáticamente. Verifica en tu dashboard de Railway que el build esté en verde.

---

## ✅ Validación post-deploy

1. **Abrir la app y refrescar** (Ctrl+Shift+R para forzar recarga)

2. **En el menú lateral verifica:**
   ```
   📊 Herramientas Tributarias
      📑 RADIAN Acuses DIAN          ← NUEVO, PRIMERO ✅
      📑 Información Exógena
      📝 Declaración de Renta
      💸 IVA y reteIVA
      🧾 Retención en la Fuente
      🥤 Impuestos Saludables
   ```

3. **Click en "RADIAN Acuses DIAN"** → debe abrir la pantalla con:
   - Uploader para Excel del catálogo VPFE
   - Instrucciones colapsables
   - Sección de filtros (Forma de Pago, Grupo, etc.)

4. **Generar borrador exógena** de Quinto Sentido:
   - F1009 diferencia debería ser **$0** ✅
   - F1009 concepto 2208 debería estar al 100%

---

## 🎯 Resumen de los 5 commits

| # | Acción | Archivo | Mensaje commit |
|---|---|---|---|
| 1 | 🔄 Reemplazar | `Home.py` | feat(nav): registrar RADIAN como primera opción en Tributarias |
| 2 | 🔄 Reemplazar | `core/exogena/conciliacion.py` | fix(exogena): F1009 reporta 100% saldo |
| 3 | 🆕 Crear | `core/radian/__init__.py` | feat(radian): paquete init del módulo nuevo |
| 4 | 🆕 Crear | `core/radian/procesador_acuses.py` | feat(radian): procesador acuses con 9 tests |
| 5 | 🆕 Crear | `app_pages/6_RADIAN_Acuses_DIAN.py` | feat(ui): pantalla RADIAN Acuses DIAN |

---

## ⚠️ IMPORTANTE: orden y solapamiento

- **El orden de los 5 commits NO importa funcionalmente** — solo Railway redespliega al final
- **Pero recomiendo subirlos EN ORDEN** (1→2→3→4→5) para que cada commit tenga sentido en el historial
- **Después de los 5 commits, Railway puede haberse redesplegado varias veces** (es normal)

---

## 🆘 Si algo falla

### "Cannot create file - directory not found" al crear `radian/__init__.py`
- Asegúrate de estar **dentro de la carpeta `core`** antes de "Create new file"
- El nombre debe llevar la barra: `radian/__init__.py` (no `__init__.py` a secas)

### El menú no muestra "RADIAN Acuses DIAN" después del deploy
- Verifica que `Home.py` se subió bien: en GitHub, abrir `Home.py` y buscar `trib_radian` — debe aparecer
- Refrescar la app con Ctrl+Shift+R (hard refresh)
- Verificar que Railway terminó el deploy (botón verde en su dashboard)

### "ModuleNotFoundError: No module named 'core.radian'"
- Verifica que **AMBOS** archivos están en `core/radian/`: `__init__.py` Y `procesador_acuses.py`
- Refrescar Railway

### El borrador exógena sigue mostrando F1009 con diferencia
- Verifica que `conciliacion.py` se reemplazó: en GitHub, abrir `core/exogena/conciliacion.py`
- Buscar `FORMATOS_DE_SALDO` — debe aparecer 2 veces
- Limpiar caché de Streamlit en la app (menú "⋮ → Clear cache")

---

## 🔧 Patch opcional: hilos 700 → 500 docs

Si quieres aplicar el patch de los bloques de descarga (mejora estabilidad), hay que modificar `core/procesadores/descargador_dian.py` directamente en GitHub web:

1. Abrir el archivo en GitHub
2. Click en el lápiz ✏️
3. Presiona Ctrl+F dentro del editor de GitHub para buscar:
   - Buscar: `700` (aparecerá varias veces)
4. Localiza estas líneas (puede haber 1-2):
   ```python
   max_docs_por_hilo: int = 700,    # ← cambiar a 500
   ```
   ```python
   DEFAULT_BLOCK_SIZE = 700        # ← cambiar a 500
   ```
   ```python
   math.ceil(total / 700)           # ← cambiar a 500
   ```
5. **Cambia cada `700` por `500`**
6. Commit: `perf(descargador): bloques de 500 docs/hilo`

> ⚠️ **Solo si te animas**. No es crítico — puede esperar a la próxima sesión donde lo trabajemos con el módulo de retenciones.

---

¡Listo! En 15 minutos tienes todo subido y funcionando. Buena suerte 🚀
