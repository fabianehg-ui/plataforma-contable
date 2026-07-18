# CÓMO SUBIR — Pantalla de acceso con branding (INTEGRAL)

Le da elegancia al login: logo, fondo con degradado, tarjeta de acceso pulida,
grid de servicios y animaciones sutiles. Fecha: 18-jul-2026. **Sin migración.**

## Archivo

- `auth/login.py` (MOD) — `login_form()` rediseñado. La **lógica de login no
  cambia** (NIT + correo + contraseña, verificación por empresa, sidebar oculto).

## Personalizar (fácil)

Dentro de `auth/login.py`:
- **Logo**: reemplaza el bloque `_LOGO_SVG` por el logo real de la empresa (un
  SVG inline, o un `<img src="data:image/png;base64,...">`). Si me pasas el PNG/SVG,
  lo dejo incrustado.
- **Colores**: en `_CSS_LOGIN`, las variables `--accent` (#2dd4bf) y `--accent2`
  (#0ea5e9) y el degradado del fondo (`.stApp{...}`) definen la paleta.
- **Servicios**: la lista `_SERVICIOS` (ícono, título, descripción) define las
  tarjetas de la derecha.

## Nota

El estilo solo aplica en la pantalla de login (antes de entrar); el resto de la
app queda igual. Si tu Streamlit es < 1.36 algún selector podría variar, pero el
formulario sigue funcionando (los estilos son cosméticos).
