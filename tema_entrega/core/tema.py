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

/* Aparición suave del contenido en cada página/subventana */
.block-container{ animation: igfade .5s ease both; padding-top:2.2rem; }
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
</style>
"""


def aplicar_tema() -> None:
    """Inyecta el tema global. Llamar una vez por carga (en Home.py)."""
    st.markdown(_CSS_TEMA, unsafe_allow_html=True)
