# CÓMO SUBIR — Animación de procesamiento + servicio Conciliación de bancos

Agrega al login una animación "pipeline": formatos (PDF · IMG · XML · XLS · TXT)
→ engranajes girando (procesando) → cifras y gráfico de barras. Y suma el
servicio **Conciliación de bancos**. Fecha: 18-jul-2026. **Sin migración.**

## Archivo

- `auth/login.py` (MOD) — nueva animación (`_PIPELINE` + CSS con engranajes SVG
  y barras animadas), y `_SERVICIOS` incluye "🔄 Conciliación de bancos".
  La lógica de login no cambia.

## Personalizar

- La cifra/gráfico son decorativos (CSS puro, sin datos reales). Si quieres que
  muestren datos reales de la empresa tras entrar, eso iría en el dashboard.
- Colores: variables `--accent` / `--accent2` como antes.
- Todo el estilo aplica solo en la pantalla de acceso.

> Nota: la animación es CSS puro (sin JavaScript), así que funciona en cualquier
> navegador moderno dentro de Streamlit.
