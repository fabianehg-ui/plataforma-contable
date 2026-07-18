# Marca INTEGRAL

Logo = **maquinaria de reloj** (tres engranajes engranados) rodeada por los tipos
de archivo que procesa (**PDF · IMG · XML · XLSX · TXT**), con flechas apuntando
hacia la maquinaria. Idea: los documentos entran y la máquina los convierte en
contabilidad.

## Archivos

| Archivo | Uso |
|---|---|
| `logo_integral.svg` | Logo completo con texto **INTEGRAL** — encabezados, portada, presentaciones. |
| `logo_integral_mark.svg` | Solo la marca (sin texto) — favicon, sidebar, esquina. Ya cargado en el login. |
| `logo_integral_animado.svg` | Versión con engranajes girando y flechas fluyendo. |
| `logo_integral.png` / `logo_integral_mark.png` | Versiones en imagen (fondo transparente) para Word/PPT/correo. |

## Paleta
- Engranajes: degradado `#2dd4bf → #0ea5e9 → #1e63c4`
- Eje/rubí central: `#0b1622` con punto `#2dd4bf`
- Texto: `#12324a` · acento `#0ea5e9`
- PDF `#e4572e` · XML `#5b8def` · XLSX `#1e9e63` · TXT `#6b7280` · IMG `#9b5de5`

## Ya integrado
`auth/login.py` → `_LOGO_SVG` ahora usa la marca de reloj (antes era un cuadro con “I”).
Para usarla como favicon en Streamlit:

```python
st.set_page_config(page_title="INTEGRAL", page_icon="assets/marca/logo_integral_mark.png")
```
