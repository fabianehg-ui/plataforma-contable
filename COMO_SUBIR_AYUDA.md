# 📖 Ayuda por módulo — cómo se instala y cómo se amplía

Este paquete agrega **ayuda breve y animada dentro de cada módulo** y una
**página central "📖 Ayuda"** que arma la guía de todos los módulos leyendo un
solo registro. Todo sale de `core/ayuda.py`.

## Archivos que trae el ZIP

| Archivo | Qué es |
|---|---|
| `core/ayuda.py` | **Motor.** Registro `AYUDAS` (14 módulos) + `render_ayuda()` + `render_ayuda_bloque()` + CSS con animación (pasos que entran deslizando y número que late). |
| `app_pages/27_Ayuda.py` | **Página central 📖 Ayuda.** Selector para ver un módulo o todas las guías. |
| `Home.py` | Registra la página `Ayuda` en el grupo **Sistema**. |
| `app_pages/21_Captura.py` | Ejemplo ya cableado — `render_ayuda("captura")`. |
| `app_pages/20_Contabilidad.py` | Ejemplo ya cableado — `render_ayuda("contabilidad")`. |
| `app_pages/25_Cruce_Facturas.py` | Ejemplo ya cableado — `render_ayuda("cruce")`. |
| `app_pages/26_Centro_Contable.py` | Ejemplo ya cableado — `render_ayuda("centro_contable")`. |

## Instalar (Railway / repo)

1. Copia los archivos a la misma ruta dentro de `plataforma-contable`.
2. Haz commit y push. No hay migración de base de datos: la ayuda es solo texto en el código.
3. Listo — no toca Supabase ni `cn_movimientos`.

## Agregar ayuda a **cualquier** módulo que falte (una sola línea)

Justo después del `st.title(...)`/`st.caption(...)` del módulo, y antes del
primer `st.markdown("---")`:

```python
from core.ayuda import render_ayuda
render_ayuda("bancos")     # usa la clave del módulo
```

Aparece un panel plegable **"❓ ¿Cómo se usa …?"** con los pasos animados. Nada más.

### Claves ya disponibles en el registro

`captura` · `contabilidad` · `cruce` · `correcciones` · `conceptos` ·
`maestros` · `centro_contable` · `nomina` · `ventas` · `compras` ·
`bancos` · `bittal` · `retencion` · `exogena`

Módulos ya cableados en este ZIP: **captura, contabilidad, cruce, centro_contable**.
Los demás solo necesitan la línea `render_ayuda("clave")` en su página; la guía ya existe en el registro.

## Crear la guía de un módulo nuevo

Abre `core/ayuda.py` y agrega una entrada al diccionario `AYUDAS`:

```python
"mi_modulo": {
    "titulo": "Nombre visible", "icono": "🧾",
    "resumen": "Una frase de qué hace el módulo.",
    "pasos": [
        ("Paso 1", "Qué hace el usuario primero."),
        ("Paso 2", "Lo siguiente."),
        ("Paso 3", "Y así."),
    ],
    "tips": ["Un consejo útil.", "Otro consejo (opcional)."],
},
```

Con eso, `render_ayuda("mi_modulo")` funciona en la página **y** la guía aparece
automáticamente en la página central **📖 Ayuda** (sale del mismo registro; no
hay que tocar `27_Ayuda.py`).

## Detalle técnico

- `render_ayuda(clave, expanded=False)` → panel plegable dentro del módulo.
- `render_ayuda_bloque(clave)` → guía "abierta" (sin plegar), usada por la página central.
- La animación es **solo CSS** (`@keyframes ayslide` / `aypulse`), inyectada una
  vez por sesión; no usa `localStorage` ni JavaScript, compatible con Streamlit Cloud/Railway.

> Nota: las páginas se verificaron con `py_compile` (sintaxis correcta). No pude
> ejecutar Streamlit de punta a punta aquí porque no hay Supabase en vivo, así
> que al subir revisa que el panel aparezca donde esperas.
