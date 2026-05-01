# Reorganización Fase 1 — Navegación agrupada

## Qué cambió

Se reorganizó la navegación de la plataforma usando `st.navigation()` (API moderna de Streamlit 1.36+) que permite agrupar páginas en secciones. La estructura quedó así:

### 🤖 Asistente Contable
Procesamiento contable mensual (los módulos que ya tenías):
- 💵 Caja Menor
- 🛒 Compras DIAN
- 💼 Nómina
- 📝 Provisiones
- 📎 PILA

### 📊 Herramientas Tributarias *(nuevo)*
Declaraciones e información tributaria periódica:
- 📑 Información Exógena DIAN
- 📝 Declaración de Renta
- 💸 IVA y reteIVA
- 🧾 Retención en la Fuente
- 🥤 Impuestos Saludables (INC, IBUA, ICUI)

### ⚙️ Sistema
- ⚙️ Configuración

---

## Estructura de archivos

```
plataforma_web/
├── Home.py                          # ← REESCRITO con st.navigation()
├── requirements.txt                 # ← actualizado a streamlit>=1.36.0
├── auth/                            # sin cambios
├── core/
│   ├── procesadores/                # sin cambios
│   ├── lectores/                    # sin cambios
│   └── utils/
│       ├── configuracion_web.py     # sin cambios
│       └── ui_tributarias.py        # ← NUEVO: helpers UI compartidos
├── app/                             # ← NUEVA carpeta (reemplaza pages/)
│   ├── asistente/
│   │   ├── caja_menor.py
│   │   ├── compras_dian.py
│   │   ├── nomina.py
│   │   ├── provisiones.py
│   │   └── pila.py
│   ├── tributarias/                 # ← NUEVA sección completa
│   │   ├── exogena.py
│   │   ├── renta.py
│   │   ├── iva.py
│   │   ├── retencion.py
│   │   └── saludables.py
│   └── sistema/
│       └── configuracion.py
├── db/                              # sin cambios
└── data/                            # sin cambios
```

La carpeta `pages/` antigua se eliminó porque con `st.navigation()` no se usa (de hecho, si se mantiene, Streamlit duplica las entradas en el sidebar).

---

## Cambios técnicos importantes

### 1. `set_page_config` solo se llama una vez

Antes cada página tenía su propio `st.set_page_config(...)`. Con `st.navigation()` esto debe hacerse una sola vez en `Home.py`. Eliminé la llamada en cada página migrada.

### 2. Imports relativos ajustados

Las páginas movidas de `pages/` a `app/<seccion>/` quedaron una nivel más profundo. Cambié `parents[1]` → `parents[2]` en cada una para que la raíz se siga calculando correctamente.

### 3. Patrón de cada página

Cada página sigue siendo un módulo Streamlit normal con guardia de auth:

```python
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()  # solo si requiere empresa activa
```

`require_auth()` actúa como defensa secundaria. La validación primaria la hace `Home.py` antes de llamar `nav.run()`.

### 4. URLs amigables

Cada página tiene una URL bonita gracias a `url_path`:

| Página | URL |
|---|---|
| Inicio | `/` |
| Caja Menor | `/caja-menor` |
| Información Exógena | `/exogena` |
| Impuestos Saludables | `/saludables` |
| ... | ... |

---

## Despliegue (orden recomendado)

### Opción A: Reemplazar repo completo

1. Descomprime el ZIP entregado.
2. En tu repo de GitHub, **elimina** la carpeta `pages/` antigua.
3. **Sube** la nueva carpeta `app/` con todo su contenido.
4. **Reemplaza** `Home.py` y `requirements.txt`.
5. **Sube** `core/utils/ui_tributarias.py`.
6. Commit y push → Railway auto-despliega.

### Opción B: Cambios incrementales por GitHub web

Sigue el mismo orden pero archivo por archivo desde la UI de GitHub.

---

## Cómo probar localmente

```bash
cd plataforma_web
pip install -r requirements.txt
streamlit run Home.py
```

Debería ver:
1. Pantalla de login (si no hay sesión).
2. Tras login, la nueva navegación con las 3 secciones agrupadas en el sidebar.
3. Cada módulo del Asistente Contable funciona igual que antes.
4. Cada módulo de Herramientas Tributarias muestra estructura con "🚧 En desarrollo".

---

## Test que pasó en mi entorno

- ✅ Sintaxis Python válida en los 16 archivos
- ✅ Streamlit 1.57 arranca sin errores
- ✅ HTTP 200 en página principal
- ✅ Sin errores en logs durante arranque
- ✅ `st.Page` y `st.navigation` disponibles

---

## Lo que viene después

Con la navegación reorganizada, los siguientes pasos son:

### Fase 2 — Implementar Información Exógena (motor real)
- Agregar tablas DIAN al schema (catálogos, mapeo PUC, movimientos, envíos)
- Adaptar el motor de generación XML a Python/Streamlit
- UI funcional de mapeo de cuentas

### Fase 3 — Conectar la lógica de Compras DIAN con Exógena
- El balance auxiliar y maestro de terceros del Asistente alimentan Exógena
- Misma fuente de datos, dos productos diferentes

### Fase 4 — Impuestos Saludables conectados con Compras DIAN
- El procesador `puente_motor_v03.py` ya detecta IBUA/ICUI/INC
- Solo falta agregar la liquidación bimestral en la página

### Fase 5 — Renta, IVA, Retención
- Cada uno con su propio procesador y formularios oficiales

---

## Si algo sale mal

| Síntoma | Causa probable | Solución |
|---|---|---|
| El sidebar muestra páginas duplicadas | Quedó la carpeta `pages/` | Borrarla del repo |
| Error `st.navigation has no attribute` | Streamlit < 1.36 | Verificar que `requirements.txt` tenga `>=1.36.0` |
| Algunas páginas fallan al cargar | Imports incorrectos | Verificar `parents[2]` en imports |
| `set_page_config` aparece duplicado | Alguna página aún lo llama | Eliminarlo, solo `Home.py` lo usa |
