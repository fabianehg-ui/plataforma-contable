# Reparación del repo — Mayo 2026

## Qué se arregló

El repo tenía:
- Archivos duplicados entre `pages/` y `app/asistente/` y `app/sistema/`
- Nombres con emojis rotos por GitHub web (ej: `1_#L01f4b5_Caja_Menor.py`)
- Mi `Home.py` antiguo apuntando a `app/...` que ya no existe
- Páginas con `set_page_config` que rompía `st.navigation()`

## Qué se hizo

1. **Renombrados los 11 archivos de `pages/`** a nombres ASCII puros (sin emojis en filenames). Los emojis se ponen vía `st.Page(icon=...)` en `Home.py`.
2. **Eliminadas las carpetas `app/asistente/` y `app/sistema/`** que tenían duplicados y placeholders.
3. **Movidas las 5 páginas tributarias** de `app/tributarias/` a `pages/` con prefijos numéricos 7-11.
4. **Eliminada la carpeta `app/`** completa (todo unificado en `pages/`).
5. **Reescrito `Home.py`** para que `st.navigation()` apunte a las 16 páginas en `pages/` agrupadas en 3 secciones.
6. **Eliminado `set_page_config`** de las 11 páginas originales (con `st.navigation()` solo `Home.py` lo llama).

## Qué se preservó intacto

- `auth/` completo: `login.py`, `empresas.py`, `superadmin.py`, `admin_usuarios.py`, `modulos.py`
- `core/` completo: todos los procesadores, lectores, utils
- `core/data/empresas/` con datos de Silla Tres y Casa UnoTres
- `db/` completo: schema, migraciones, cliente Supabase
- `data/cuentas.xlsx` y `data/mapeos.xlsx`
- `docs/` completo
- Todos los tests y scripts

## Estructura final

```
plataforma_web/
├── Home.py                          ← REESCRITO con st.navigation
├── requirements.txt
├── pages/                           ← 16 páginas ASCII
│   ├── 0_Panel_Admin.py
│   ├── 1_Caja_Menor.py
│   ├── 2_Compras_DIAN.py
│   ├── 3_Compras_y_Egresos.py
│   ├── 3_Nomina.py
│   ├── 4_Ingresos_POS.py
│   ├── 4_Provisiones.py
│   ├── 4_Ventas_C13.py
│   ├── 5_DIAN_XML.py
│   ├── 5_PILA.py
│   ├── 6_Configuracion.py
│   ├── 7_Informacion_Exogena.py    ← Tributarias
│   ├── 8_Declaracion_Renta.py
│   ├── 9_IVA.py
│   ├── 10_Retencion_Fuente.py
│   └── 11_Impuestos_Saludables.py
├── auth/                            ← intacto
├── core/                            ← intacto
├── db/                              ← intacto
└── data/                            ← intacto
```

## Sidebar resultante

```
🏠 Inicio

🤖 Asistente Contable
   💵 Caja Menor
   🛒 Compras DIAN
   📊 Compras y Egresos
   💼 Nómina
   📝 Provisiones
   🛍️ Ventas C13
   🧾 Ingresos POS
   📎 PILA
   📥 DIAN XML

📊 Herramientas Tributarias
   📑 Información Exógena
   📝 Declaración de Renta
   💸 IVA y reteIVA
   🧾 Retención en la Fuente
   🥤 Impuestos Saludables

⚙️ Sistema
   🛡️ Panel Admin
   ⚙️ Configuración
```

## Cómo desplegar este repo a Railway

### Opción A — Reemplazar el repo completo en GitHub (recomendada)

1. **Backup primero**: en GitHub web, crea una rama `backup-pre-reparacion` desde tu rama actual antes de tocar nada.
2. Borra **TODOS** los archivos de tu rama `main` (sí, todos)
3. Sube todos los archivos de este ZIP a `main`
4. Commit con mensaje: "Reparación: nombres limpios + navegación agrupada"
5. Railway detecta el push y despliega

### Opción B — Sincronizar localmente con Git (si usas Git)

```bash
# 1. Clona tu repo
git clone https://github.com/tu-usuario/plataforma-contable.git
cd plataforma-contable

# 2. Crea backup del estado actual
git checkout -b backup-pre-reparacion
git push -u origin backup-pre-reparacion
git checkout main

# 3. Borra todo y reemplaza con el ZIP
git rm -r .
# Descomprime el ZIP aquí
unzip -o /ruta/al/zip/repo_reparado.zip

# 4. Commit y push
git add -A
git commit -m "Reparación: nombres limpios + navegación agrupada"
git push origin main
```

## Tests pasados

- ✅ Sintaxis Python válida en los 46 archivos del proyecto
- ✅ Streamlit 1.57 arranca sin errores
- ✅ HTTP 200 en `/_stcore/health`
- ✅ Sin errores en logs durante arranque
- ✅ Las 16 páginas se cargan via `st.navigation`
- ✅ Imports correctos en todas las páginas tributarias (`parents[1]`)
- ✅ Ningún `set_page_config` duplicado

## Si algo falla después de desplegar

| Síntoma | Causa probable | Solución |
|---|---|---|
| Sidebar muestra páginas duplicadas | Railway tiene cache | Forzar redeploy desde Railway |
| Algún módulo no carga | Imports rotos | Verificar que NO haya tocado `auth/` o `core/` |
| Login no funciona | Variables Supabase | Revisar `supabase__url`, `supabase__anon_key`, `supabase__service_key` en Railway |
| Nombres con `#L01...` siguen apareciendo | Subiste por web no por Git | Borrar archivos viejos manualmente en GitHub web |

## Validación post-despliegue

Después de desplegar, deberías ver:

1. ✅ Login funciona normalmente
2. ✅ Sidebar agrupado en 3 secciones (Asistente / Tributarias / Sistema)
3. ✅ Cada uno de los 11 módulos originales abre con su título correcto (con emoji)
4. ✅ Las 5 nuevas pestañas tributarias abren mostrando sus tabs internos
5. ✅ El selector de empresa en sidebar funciona como antes
6. ✅ Panel Admin aparece SOLO si eres super admin
