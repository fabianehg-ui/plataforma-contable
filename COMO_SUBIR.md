# CÓMO SUBIR — Login por NIT + correo + contraseña, y menú oculto sin sesión

Dos cambios de seguridad. Fecha: 18-jul-2026. **Sin migración.**

## 1. Ningún módulo se ve antes de iniciar sesión (anti-espionaje)

**Causa encontrada:** existe una carpeta `pages/` (con un `90_Siigo_a_Contai.py`
viejo, duplicado). Cuando el login cortaba la app antes de `st.navigation()`,
Streamlit mostraba esa carpeta **automáticamente** en el menú lateral.

**Solución:** `Home.py` ahora llama a `st.navigation()` **siempre** — cuando no
hay sesión, solo con la página de login y con el menú **oculto** — lo que suprime
la auto-detección de `pages/`. Además el formulario de login **oculta el sidebar**
por completo. Resultado: sin sesión NO se ve ningún módulo.

> **Recomendado:** borra la carpeta `pages/` del repo (es un Siigo duplicado; el
> real está en `app_pages/15_Siigo_a_Contai.py`). El arreglo funciona igual sin
> borrarla, pero deja el repo limpio.

## 2. Ingreso con NIT de la empresa + correo + contraseña

`auth/login.py` — el formulario ahora pide **NIT de la empresa**, correo y
contraseña. Al entrar:
1. Valida correo/contraseña.
2. Verifica que el usuario **tenga acceso a la empresa con ese NIT**. Si no,
   cierra la sesión y avisa ("No tienes acceso a una empresa con ese NIT").
3. Si sí, deja **esa empresa como activa** y entra.

- **Usuario normal**: solo entra a su(s) empresa(s) asignada(s).
- **Superadmin**: puede entrar con el NIT de cualquier empresa y luego cambiar
  desde el sidebar (como ya quedó).

## Archivos

| Archivo | Estado |
|---|---|
| `auth/login.py` | **MOD** — login con NIT; oculta sidebar; verifica acceso por NIT. |
| `Home.py` | **MOD** — `st.navigation` siempre (login oculto) → suprime `pages/`. |
| `pages/` (carpeta) | **BORRAR** (recomendado) — Siigo duplicado. |

Sin migración: usa `usuario_empresa` / `superadmins` que ya existen.
