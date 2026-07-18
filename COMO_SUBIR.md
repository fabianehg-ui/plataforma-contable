# CÓMO SUBIR — Arrastrar y soltar facturas (drag & drop)

Mejora de UX en la Captura. Fecha: 18-jul-2026. **Sin migración.**

## Qué cambia

El cargador de facturas ahora:
- Deja **arrastrar y soltar** una o varias facturas (o un ZIP) directamente sobre
  la caja — el texto lo indica ("Arrastra y suelta las facturas o el ZIP").
- Acepta **varios archivos a la vez** (`accept_multiple_files`): puedes soltar
  varias facturas juntas; se leen todas y, si hay más de una, aparece el selector
  para elegir cuál cargar en el asiento.
- Si algún archivo falla, avisa cuál y sigue con los demás.

## Archivo

| Archivo | Cambio |
|---|---|
| `app_pages/21_Captura.py` | `st.file_uploader` con `accept_multiple_files=True` + textos de drag & drop; lee todos los archivos soltados y usa el selector cuando hay varias facturas. |

Súbelo encima del anterior. Nada más cambia.
