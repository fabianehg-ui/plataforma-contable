"""
core/tema.py — Tema visual global de INTEGRAL.

Aplica en TODA la app (todas las ventanas y subventanas) los mismos colores y
efectos de la pantalla de inicio: degradado de marca en la barra lateral,
botones teal→azul, tarjetas con sombra, títulos con acento, y una animación
suave de aparición del contenido.

Se inyecta en UN solo punto (Home.py, justo antes de nav.run()), así cada
página hereda el tema sin tener que tocarla:

    from core.tema import aplicar_tema
    aplicar_tema()

Paleta (misma del login):
    Marca oscura : #0b1622 · #0a2233 · #12324a
    Teal         : #2dd4bf
    Azul cielo   : #0ea5e9
    Acento claro : #7dd3fc
"""
from __future__ import annotations

import streamlit as st


# CSS del tema. Fondo claro y legible para el trabajo contable (tablas, formas),
# con la marca oscura en la barra lateral y acentos teal/azul en todos lados.
_CSS_TEMA = """
<style>
:root{
  --ig-dark:#0b1622; --ig-dark2:#0a2233; --ig-ink:#12324a;
  --ig-teal:#2dd4bf; --ig-sky:#0ea5e9; --ig-sky2:#7dd3fc;
  --ig-bg:#f4f7fb; --ig-card:#ffffff; --ig-border:#e3e9f0;
}

/* ---- Lienzo general ---- */
.stApp{
  background:
    radial-gradient(1100px 520px at 100% -8%, rgba(14,165,233,.10), transparent 60%),
    radial-gradient(900px 500px at -8% 8%, rgba(45,212,191,.10), transparent 55%),
    var(--ig-bg);
}
[data-testid="stHeader"]{ background:transparent; }

/* Aparición suave del contenido en cada página/subventana.
   Solo espacio extra abajo para que el último control respire; NO se toca el
   overflow del contenedor (Streamlit maneja el scroll y overridearlo lo rompía). */
.block-container{ animation: igfade .5s ease both; padding-top:2.2rem; padding-bottom:5rem; }
@keyframes igfade{ from{opacity:0; transform:translateY(8px);} to{opacity:1; transform:none;} }

/* ---- Barra lateral: degradado de marca (como el fondo del inicio) ---- */
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg, var(--ig-dark) 0%, var(--ig-dark2) 100%);
  border-right:1px solid rgba(125,211,252,.12);
}
section[data-testid="stSidebar"] *{ color:#dfeaf5 !important; }
section[data-testid="stSidebar"] a{ color:var(--ig-sky2) !important; }
/* Ítems de navegación */
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover,
section[data-testid="stSidebar"] li a:hover{
  background:rgba(45,212,191,.14); border-radius:9px;
}
section[data-testid="stSidebar"] [aria-current="page"]{
  background:linear-gradient(90deg, rgba(45,212,191,.25), rgba(14,165,233,.15));
  border-radius:9px;
}

/* ---- Títulos con acento de marca ---- */
h1, h2, h3{ color:var(--ig-ink); letter-spacing:.2px; }
h1{ position:relative; padding-bottom:.35rem; }
h1::after{
  content:""; position:absolute; left:0; bottom:0; height:4px; width:74px;
  border-radius:4px; background:linear-gradient(90deg, var(--ig-teal), var(--ig-sky));
}

/* ---- Botones: degradado teal→azul ---- */
.stButton>button, .stDownloadButton>button, .stFormSubmitButton>button{
  border:0; border-radius:11px; font-weight:700; color:#04202a;
  background:linear-gradient(135deg, var(--ig-teal), var(--ig-sky));
  box-shadow:0 6px 16px rgba(14,165,233,.28); transition:transform .12s ease, box-shadow .12s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover, .stFormSubmitButton>button:hover{
  transform:translateY(-1px); box-shadow:0 10px 22px rgba(14,165,233,.38); color:#04202a;
}
/* Botón secundario (type="secondary"): contorno, no relleno */
.stButton>button[kind="secondary"]{
  background:#fff; color:var(--ig-ink); border:1.5px solid var(--ig-border);
  box-shadow:0 3px 10px rgba(20,40,70,.06);
}

/* ---- Métricas como tarjetas ---- */
[data-testid="stMetric"]{
  background:var(--ig-card); border:1px solid var(--ig-border); border-radius:14px;
  padding:.9rem 1rem; box-shadow:0 8px 22px rgba(20,40,70,.06);
}
[data-testid="stMetricValue"]{ color:var(--ig-ink); }

/* ---- Expanders, tabs, inputs, tablas ---- */
[data-testid="stExpander"]{
  border:1px solid var(--ig-border); border-radius:14px; overflow:hidden;
  box-shadow:0 6px 18px rgba(20,40,70,.05); background:var(--ig-card);
}
.stTabs [data-baseweb="tab-list"]{ gap:.3rem; }
.stTabs [data-baseweb="tab"]{ border-radius:10px 10px 0 0; }
.stTabs [aria-selected="true"]{
  background:linear-gradient(180deg, rgba(45,212,191,.14), transparent);
  border-bottom:3px solid var(--ig-sky);
}
[data-testid="stDataFrame"]{
  border:1px solid var(--ig-border); border-radius:12px; overflow:hidden;
  box-shadow:0 6px 18px rgba(20,40,70,.05);
}
.stTextInput input, .stNumberInput input, .stDateInput input,
[data-baseweb="select"]>div{ border-radius:10px !important; }

/* Alertas un poco más suaves */
[data-testid="stAlert"]{ border-radius:12px; }

/* Divisores con tinte de marca */
hr{ border-color:rgba(14,165,233,.18); }

/* ---- Legibilidad: en fondos blancos/claros, letras OSCURAS ----
   (solo el área principal; la barra lateral mantiene su texto claro) */
[data-testid="stMain"] p, [data-testid="stMain"] li, [data-testid="stMain"] label,
[data-testid="stMain"] span, [data-testid="stMain"] h4, [data-testid="stMain"] h5,
[data-testid="stMain"] .stMarkdown, [data-testid="stMain"] [data-testid="stWidgetLabel"],
.main p, .main li, .main label{ color:#1f2b38 !important; }
/* Texto dentro de campos y selects: oscuro */
[data-testid="stMain"] input, [data-testid="stMain"] textarea,
[data-testid="stMain"] [data-baseweb="select"] *{ color:#12324a !important; }
/* Captions y textos secundarios: gris oscuro legible (no gris claro) */
[data-testid="stMain"] [data-testid="stCaptionContainer"],
[data-testid="stMain"] small, [data-testid="stMain"] .stCaption{ color:#46586b !important; }
/* Editor de datos / tablas: texto oscuro sobre celdas claras */
[data-testid="stDataFrame"] *, [data-testid="stDataEditor"] *{ color:#1f2b38; }
</style>
"""


def aplicar_tema() -> None:
    """Inyecta el tema global. Llamar una vez por carga (en Home.py)."""
    st.markdown(_CSS_TEMA, unsafe_allow_html=True)


# ============================================================
# Hero de la página de inicio (logo animado + magia visual)
# ============================================================
import base64 as _b64h

# Marca animada (engranajes girando) — una sola línea, se incrusta como imagen.
_HERO_ANIM_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="-280.0 -280.0 560 560" width="150" height="150"><defs><linearGradient id="gearGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2dd4bf"/><stop offset="0.55" stop-color="#0ea5e9"/><stop offset="1" stop-color="#1e63c4"/></linearGradient><radialGradient id="halo" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#0ea5e9" stop-opacity="0.18"/><stop offset="1" stop-color="#0ea5e9" stop-opacity="0"/></radialGradient><marker id="arrow_PDF" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#e4572e"/></marker><marker id="arrow_XML" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#5b8def"/></marker><marker id="arrow_XLSX" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#1e9e63"/></marker><marker id="arrow_DIAN" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#1e6f5c"/></marker><marker id="arrow_TXT" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#6b7280"/></marker><marker id="arrow_IMG" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#9b5de5"/></marker><marker id="arrow_WWW" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#0891b2"/></marker></defs><circle cx="0" cy="0" r="250" fill="url(#halo)"/><path d="M 0.0,-185.0 Q 18.0,-138.5 0.0,-92.0" fill="none" stroke="#e4572e" stroke-width="4.5" stroke-linecap="round" marker-end="url(#arrow_PDF)" stroke-dasharray="9 8"><animate attributeName="stroke-dashoffset" from="34" to="0" dur="1.1s" begin="0.0s" repeatCount="indefinite"/></path><path d="M 126.7,-115.3 Q 110.5,-72.3 71.9,-57.4" fill="none" stroke="#5b8def" stroke-width="4.5" stroke-linecap="round" marker-end="url(#arrow_XML)" stroke-dasharray="9 8"><animate attributeName="stroke-dashoffset" from="34" to="0" dur="1.1s" begin="0.14s" repeatCount="indefinite"/></path><path d="M 157.9,41.2 Q 119.8,48.4 89.7,20.5" fill="none" stroke="#1e9e63" stroke-width="4.5" stroke-linecap="round" marker-end="url(#arrow_XLSX)" stroke-dasharray="9 8"><animate attributeName="stroke-dashoffset" from="34" to="0" dur="1.1s" begin="0.28s" repeatCount="indefinite"/></path><path d="M 70.3,166.7 Q 38.9,132.6 39.9,82.9" fill="none" stroke="#1e6f5c" stroke-width="4.5" stroke-linecap="round" marker-end="url(#arrow_DIAN)" stroke-dasharray="9 8"><animate attributeName="stroke-dashoffset" from="34" to="0" dur="1.1s" begin="0.42000000000000004s" repeatCount="indefinite"/></path><path d="M -70.3,166.7 Q -71.3,117.0 -39.9,82.9" fill="none" stroke="#6b7280" stroke-width="4.5" stroke-linecap="round" marker-end="url(#arrow_TXT)" stroke-dasharray="9 8"><animate attributeName="stroke-dashoffset" from="34" to="0" dur="1.1s" begin="0.56s" repeatCount="indefinite"/></path><path d="M -157.9,41.2 Q -127.8,13.3 -89.7,20.5" fill="none" stroke="#9b5de5" stroke-width="4.5" stroke-linecap="round" marker-end="url(#arrow_IMG)" stroke-dasharray="9 8"><animate attributeName="stroke-dashoffset" from="34" to="0" dur="1.1s" begin="0.7000000000000001s" repeatCount="indefinite"/></path><path d="M -126.7,-115.3 Q -88.1,-100.4 -71.9,-57.4" fill="none" stroke="#0891b2" stroke-width="4.5" stroke-linecap="round" marker-end="url(#arrow_WWW)" stroke-dasharray="9 8"><animate attributeName="stroke-dashoffset" from="34" to="0" dur="1.1s" begin="0.8400000000000001s" repeatCount="indefinite"/></path><g fill="url(#gearGrad)" fill-rule="evenodd" stroke="#0b1622" stroke-width="1.2"><path d="M 7.64,-11.83 L 17.66,-12.25 L 17.66,0.25 L 7.64,-0.17 L 6.25,6.85 L 15.67,10.29 L 10.88,21.84 L 1.79,17.62 L -2.19,23.57 L 5.19,30.35 L -3.65,39.19 L -10.43,31.81 L -16.38,35.79 L -12.16,44.88 L -23.71,49.67 L -27.15,40.25 L -34.17,41.64 L -33.75,51.66 L -46.25,51.66 L -45.83,41.64 L -52.85,40.25 L -56.29,49.67 L -67.84,44.88 L -63.62,35.79 L -69.57,31.81 L -76.35,39.19 L -85.19,30.35 L -77.81,23.57 L -81.79,17.62 L -90.88,21.84 L -95.67,10.29 L -86.25,6.85 L -87.64,-0.17 L -97.66,0.25 L -97.66,-12.25 L -87.64,-11.83 L -86.25,-18.85 L -95.67,-22.29 L -90.88,-33.84 L -81.79,-29.62 L -77.81,-35.57 L -85.19,-42.35 L -76.35,-51.19 L -69.57,-43.81 L -63.62,-47.79 L -67.84,-56.88 L -56.29,-61.67 L -52.85,-52.25 L -45.83,-53.64 L -46.25,-63.66 L -33.75,-63.66 L -34.17,-53.64 L -27.15,-52.25 L -23.71,-61.67 L -12.16,-56.88 L -16.38,-47.79 L -10.43,-43.81 L -3.65,-51.19 L 5.19,-42.35 L -2.19,-35.57 L 1.79,-29.62 L 10.88,-33.84 L 15.67,-22.29 L 6.25,-18.85 Z M -16.80,-6.00 L -17.38,-0.84 L -19.10,4.07 L -21.86,8.46 L -25.54,12.14 L -29.93,14.90 L -34.84,16.62 L -40.00,17.20 L -45.16,16.62 L -50.07,14.90 L -54.46,12.14 L -58.14,8.46 L -60.90,4.07 L -62.62,-0.84 L -63.20,-6.00 L -62.62,-11.16 L -60.90,-16.07 L -58.14,-20.46 L -54.46,-24.14 L -50.07,-26.90 L -45.16,-28.62 L -40.00,-29.20 L -34.84,-28.62 L -29.93,-26.90 L -25.54,-24.14 L -21.86,-20.46 L -19.10,-16.07 L -17.38,-11.16 Z"><animateTransform attributeName="transform" type="rotate" from="0 -40 -6" to="360 -40 -6" dur="14s" repeatCount="indefinite"/></path><path d="M 69.61,-44.85 L 77.61,-45.45 L 77.61,-34.55 L 69.61,-35.15 L 68.06,-29.40 L 75.29,-25.92 L 69.84,-16.47 L 63.22,-21.00 L 59.00,-16.78 L 63.53,-10.16 L 54.08,-4.71 L 50.60,-11.94 L 44.85,-10.39 L 45.45,-2.39 L 34.55,-2.39 L 35.15,-10.39 L 29.40,-11.94 L 25.92,-4.71 L 16.47,-10.16 L 21.00,-16.78 L 16.78,-21.00 L 10.16,-16.47 L 4.71,-25.92 L 11.94,-29.40 L 10.39,-35.15 L 2.39,-34.55 L 2.39,-45.45 L 10.39,-44.85 L 11.94,-50.60 L 4.71,-54.08 L 10.16,-63.53 L 16.78,-59.00 L 21.00,-63.22 L 16.47,-69.84 L 25.92,-75.29 L 29.40,-68.06 L 35.15,-69.61 L 34.55,-77.61 L 45.45,-77.61 L 44.85,-69.61 L 50.60,-68.06 L 54.08,-75.29 L 63.53,-69.84 L 59.00,-63.22 L 63.22,-59.00 L 69.84,-63.53 L 75.29,-54.08 L 68.06,-50.60 Z M 55.20,-40.00 L 54.82,-36.62 L 53.69,-33.40 L 51.88,-30.52 L 49.48,-28.12 L 46.60,-26.31 L 43.38,-25.18 L 40.00,-24.80 L 36.62,-25.18 L 33.40,-26.31 L 30.52,-28.12 L 28.12,-30.52 L 26.31,-33.40 L 25.18,-36.62 L 24.80,-40.00 L 25.18,-43.38 L 26.31,-46.60 L 28.12,-49.48 L 30.52,-51.88 L 33.40,-53.69 L 36.62,-54.82 L 40.00,-55.20 L 43.38,-54.82 L 46.60,-53.69 L 49.48,-51.88 L 51.88,-49.48 L 53.69,-46.60 L 54.82,-43.38 Z"><animateTransform attributeName="transform" type="rotate" from="0 40 -40" to="-360 40 -40" dur="10.5s" repeatCount="indefinite"/></path><path d="M 49.58,47.74 L 56.57,47.01 L 56.57,56.99 L 49.58,56.26 L 47.96,61.24 L 54.04,64.76 L 48.18,72.83 L 42.96,68.13 L 38.72,71.21 L 41.57,77.63 L 32.09,80.71 L 30.62,73.84 L 25.38,73.84 L 23.91,80.71 L 14.43,77.63 L 17.28,71.21 L 13.04,68.13 L 7.82,72.83 L 1.96,64.76 L 8.04,61.24 L 6.42,56.26 L -0.57,56.99 L -0.57,47.01 L 6.42,47.74 L 8.04,42.76 L 1.96,39.24 L 7.82,31.17 L 13.04,35.87 L 17.28,32.79 L 14.43,26.37 L 23.91,23.29 L 25.38,30.16 L 30.62,30.16 L 32.09,23.29 L 41.57,26.37 L 38.72,32.79 L 42.96,35.87 L 48.18,31.17 L 54.04,39.24 L 47.96,42.76 Z M 39.60,52.00 L 39.31,54.58 L 38.45,57.03 L 37.07,59.23 L 35.23,61.07 L 33.03,62.45 L 30.58,63.31 L 28.00,63.60 L 25.42,63.31 L 22.97,62.45 L 20.77,61.07 L 18.93,59.23 L 17.55,57.03 L 16.69,54.58 L 16.40,52.00 L 16.69,49.42 L 17.55,46.97 L 18.93,44.77 L 20.77,42.93 L 22.97,41.55 L 25.42,40.69 L 28.00,40.40 L 30.58,40.69 L 33.03,41.55 L 35.23,42.93 L 37.07,44.77 L 38.45,46.97 L 39.31,49.42 Z"><animateTransform attributeName="transform" type="rotate" from="0 28 52" to="-360 28 52" dur="8.75s" repeatCount="indefinite"/></path></g><circle cx="-40" cy="-6" r="11" fill="#0b1622"/><circle cx="40" cy="-40" r="9" fill="#0b1622"/><circle cx="28" cy="52" r="7" fill="#0b1622"/><circle cx="-40" cy="-6" r="5" fill="#2dd4bf"/><circle cx="40" cy="-40" r="4" fill="#7dd3fc"/><circle cx="28" cy="52" r="3.5" fill="#7dd3fc"/><g><rect x="-48.0" y="-239.0" width="96" height="50" rx="12" fill="#ffffff" stroke="#e4572e" stroke-width="3"/><rect x="-48.0" y="-239.0" width="10" height="50" rx="5" fill="#e4572e"/><text x="5.0" y="-214.0" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="800" fill="#e4572e" text-anchor="middle" dominant-baseline="central">PDF</text></g><g><rect x="119.3" y="-158.4" width="96" height="50" rx="12" fill="#ffffff" stroke="#5b8def" stroke-width="3"/><rect x="119.3" y="-158.4" width="10" height="50" rx="5" fill="#5b8def"/><text x="172.3" y="-133.4" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="800" fill="#5b8def" text-anchor="middle" dominant-baseline="central">XML</text></g><g><rect x="160.6" y="22.6" width="96" height="50" rx="12" fill="#ffffff" stroke="#1e9e63" stroke-width="3"/><rect x="160.6" y="22.6" width="10" height="50" rx="5" fill="#1e9e63"/><text x="213.6" y="47.6" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="800" fill="#1e9e63" text-anchor="middle" dominant-baseline="central">XLSX</text></g><g><rect x="44.9" y="167.8" width="96" height="50" rx="12" fill="#ffffff" stroke="#1e6f5c" stroke-width="3"/><path d="M 62.9 183.8 L 70.9 187.8 L 70.9 194.8 Q 70.9 200.8 62.9 202.8 Q 54.9 200.8 54.9 194.8 L 54.9 187.8 Z" fill="#1e6f5c"/><path d="M 59.9 192.8 L 61.9 195.8 L 66.9 189.8" stroke="#fff" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/><text x="101.9" y="192.8" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="800" fill="#1e6f5c" text-anchor="middle" dominant-baseline="central">DIAN</text></g><g><rect x="-140.9" y="167.8" width="96" height="50" rx="12" fill="#ffffff" stroke="#6b7280" stroke-width="3"/><rect x="-140.9" y="167.8" width="10" height="50" rx="5" fill="#6b7280"/><text x="-87.9" y="192.8" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="800" fill="#6b7280" text-anchor="middle" dominant-baseline="central">TXT</text></g><g><rect x="-256.6" y="22.6" width="96" height="50" rx="12" fill="#ffffff" stroke="#9b5de5" stroke-width="3"/><rect x="-256.6" y="22.6" width="10" height="50" rx="5" fill="#9b5de5"/><text x="-203.6" y="47.6" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="800" fill="#9b5de5" text-anchor="middle" dominant-baseline="central">IMG</text></g><g><rect x="-215.3" y="-158.4" width="96" height="50" rx="12" fill="#ffffff" stroke="#0891b2" stroke-width="3"/><g stroke="#0891b2" stroke-width="2.2" fill="none"><circle cx="-197.3" cy="-133.4" r="9"/><ellipse cx="-197.3" cy="-133.4" rx="4" ry="9"/><line x1="-206.3" y1="-133.4" x2="-188.3" y2="-133.4"/></g><text x="-158.3" y="-133.4" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="800" fill="#0891b2" text-anchor="middle" dominant-baseline="central">WWW</text></g></svg>"""
_HERO_LOGO_URI = "data:image/svg+xml;base64," + _b64h.b64encode(
    _HERO_ANIM_SVG.encode("utf-8")).decode("ascii")

_CSS_HERO = """
<style>
.ig-home-hero{
  position:relative; overflow:hidden; border-radius:22px; margin:.2rem 0 1.4rem;
  padding:1.6rem 1.8rem;
  background:
    radial-gradient(700px 260px at 88% -20%, rgba(45,212,191,.28), transparent 60%),
    radial-gradient(600px 240px at 8% 120%, rgba(14,165,233,.30), transparent 60%),
    linear-gradient(135deg, #0b1622 0%, #0a2233 60%, #0e2c3f 100%);
  box-shadow:0 18px 46px rgba(6,20,34,.45);
  display:flex; align-items:center; gap:1.6rem; flex-wrap:wrap;
  animation: ighero-in .7s ease both;
}
@keyframes ighero-in{ from{opacity:0; transform:translateY(14px);} to{opacity:1; transform:none;} }
.ig-home-hero::after{
  content:""; position:absolute; inset:0; pointer-events:none;
  background:linear-gradient(115deg, transparent 30%, rgba(255,255,255,.06) 45%, transparent 60%);
  transform:translateX(-100%); animation: igshine 5.5s ease-in-out 1s infinite;
}
@keyframes igshine{ 0%{transform:translateX(-100%);} 55%,100%{transform:translateX(100%);} }
.ig-home-logo{ width:132px; height:132px; flex:0 0 auto; animation: igfloat 5s ease-in-out infinite;
  filter:drop-shadow(0 10px 22px rgba(45,212,191,.35)); }
@keyframes igfloat{ 0%,100%{transform:translateY(0);} 50%{transform:translateY(-8px);} }
.ig-home-copy{ flex:1 1 320px; color:#e6eef7; }
.ig-home-title{ font-size:2.5rem; font-weight:800; letter-spacing:2px; line-height:1;
  background:linear-gradient(90deg,#2dd4bf,#7dd3fc,#0ea5e9); -webkit-background-clip:text;
  background-clip:text; color:transparent; }
.ig-home-sub{ color:#9fd0e6; font-weight:600; margin:.25rem 0 .1rem; }
.ig-home-hi{ color:#cfe0f0; font-size:.92rem; }
.ig-home-flow{ display:flex; align-items:center; gap:.4rem; flex-wrap:wrap; margin-top:.9rem; }
.ig-fc{ font-size:.68rem; font-weight:800; color:#04202a; padding:.16rem .5rem; border-radius:7px;
  background:#a5e8f5; box-shadow:0 4px 12px rgba(0,0,0,.25); animation: igfeed 3.4s ease-in-out infinite; }
.ig-fc.pdf{background:#ff9a9a;} .ig-fc.xml{background:#9be8dc;} .ig-fc.xls{background:#bfe3a6;}
.ig-fc.txt{background:#dcdcf0;} .ig-fc.img{background:#ffd59e;} .ig-fc.web{background:#a5e8f5;}
.ig-fc.dian{background:#bfe6d8;}
.ig-fc:nth-child(2){animation-delay:.25s;} .ig-fc:nth-child(3){animation-delay:.5s;}
.ig-fc:nth-child(4){animation-delay:.75s;} .ig-fc:nth-child(5){animation-delay:1s;}
.ig-fc:nth-child(6){animation-delay:1.25s;} .ig-fc:nth-child(7){animation-delay:1.5s;}
@keyframes igfeed{ 0%{opacity:.35; transform:translateX(-6px);} 50%{opacity:1; transform:translateX(5px);} 100%{opacity:.35; transform:translateX(-6px);} }
.ig-home-arrow{ color:#7dd3fc; font-weight:800; }
.ig-home-out{ color:#2dd4bf; font-weight:800; font-size:.85rem; }
</style>
"""


def render_hero_inicio(email: str = "", n_empresas=None, n_modulos="19") -> None:
    """Banner de bienvenida con el logo animado y la animación de fuentes.
    Llamar al comienzo de la página de inicio."""
    st.markdown(_CSS_HERO, unsafe_allow_html=True)
    hola = f"Bienvenido, <b>{email}</b>" if email else "Bienvenido"
    emp = f" &middot; {n_empresas} empresa(s)" if n_empresas is not None else ""
    st.markdown(
        f"""
<div class='ig-home-hero'>
  <img class='ig-home-logo' src='{_HERO_LOGO_URI}' alt='INTEGRAL'/>
  <div class='ig-home-copy'>
    <div class='ig-home-title'>INTEGRAL</div>
    <div class='ig-home-sub'>Contabilidad inteligente &middot; todo el ciclo, una sola empresa</div>
    <div class='ig-home-hi'>{hola}{emp}</div>
    <div class='ig-home-flow'>
      <span class='ig-fc pdf'>PDF</span><span class='ig-fc img'>IMG</span>
      <span class='ig-fc xml'>XML</span><span class='ig-fc xls'>XLSX</span>
      <span class='ig-fc txt'>TXT</span><span class='ig-fc web'>WWW</span>
      <span class='ig-fc dian'>DIAN</span>
      <span class='ig-home-arrow'>&#10142;</span>
      <span class='ig-home-out'>&#9881; contabilidad</span>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
