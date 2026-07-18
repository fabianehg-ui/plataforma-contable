# 🎨 Tema visual global (mismos colores del inicio en toda la app)

Aplica en **todas las ventanas y subventanas** la paleta y los efectos de la
pantalla de inicio, desde **un solo punto** — no hay que tocar las páginas.

## Archivos del ZIP

| Archivo | Qué hace |
|---|---|
| `core/tema.py` | El tema: barra lateral con degradado de marca, botones teal→azul, títulos con acento, tarjetas de métricas, tabs/tablas/expanders con sombra y una aparición suave del contenido. |
| `Home.py` | Llama `aplicar_tema()` **justo antes de `nav.run()`**, así cada página lo hereda automáticamente. |
| `.streamlit/config.toml` | Paleta base de Streamlit (color primario y fondos) alineada a la marca. |

## Instalar
1. Copia los tres archivos a su misma ruta en el repo.
2. Commit + push y redepliega en Railway.
3. Listo: todas las páginas toman el tema. **No** hay que editar cada módulo.

## Cómo funciona (por qué cubre todo)
`Home.py` es el punto de entrada y se ejecuta en **cada** carga de página antes
de `nav.run()`. Al inyectar el CSS ahí, la página seleccionada se dibuja ya con
el tema aplicado. Cambiar un color = editar solo `core/tema.py`.

## Paleta
Marca oscura `#0b1622 · #0a2233 · #12324a` · Teal `#2dd4bf` · Azul `#0ea5e9` ·
Acento `#7dd3fc` · Fondo `#f4f7fb`.

> Decisión de diseño: el fondo de trabajo se mantiene **claro y legible** (son
> pantallas con muchas tablas y cifras) y la marca oscura del inicio va en la
> barra lateral + acentos. Si prefieres **todo oscuro** como el hero del login,
> avísame y te lo cambio.

> Nota: verificado con `py_compile` y con una maqueta visual. No pude correr
> Streamlit de punta a punta aquí (no hay Supabase en vivo); al subir, revisa
> que se vea como la maqueta.

---

## Novedades de esta versión
- **Página de inicio con hero animado**: `home_page()` ahora llama
  `render_hero_inicio(...)` — banner con el logo de engranajes girando y las
  fuentes (PDF·IMG·XML·XLSX·TXT·WWW·DIAN) fluyendo hacia "⚙ contabilidad".
- **Scroll asegurado**: se añadió `padding-bottom` y `overflow` para que SIEMPRE
  se pueda llegar al final de cada página (p. ej. el botón 💾 Guardar en Captura).
  Tip: si la rueda del mouse "no baja", es que está sobre un campo numérico y
  cambia el valor; usa la barra de scroll o la tecla Fin/AvPág.
