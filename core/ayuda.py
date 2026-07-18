"""
core/ayuda.py — Ayuda por módulo (guías breves con animación).

- AYUDAS: registro central {clave: {titulo, icono, resumen, pasos, tips}}.
- render_ayuda(clave): panel plegable "¿Cómo se usa?" con pasos animados.
  Se agrega en una línea al inicio de cualquier módulo:

      from core.ayuda import render_ayuda
      render_ayuda("captura")

La página 📖 Ayuda muestra la guía de todos los módulos leyendo este registro.
"""
from __future__ import annotations

import streamlit as st


# ============================================================
# Registro de guías (breve y editable)
# pasos = [(título_paso, detalle), ...]
# ============================================================
AYUDAS: dict[str, dict] = {
    "captura": {
        "titulo": "Captura de comprobantes", "icono": "✍️",
        "resumen": "Arma un asiento en partida doble y guárdalo en la contabilidad.",
        "pasos": [
            ("Cabecera", "Elige el comprobante, la fecha y el documento (consecutivo)."),
            ("Leer factura (opcional)", "Sube XML/PDF/imagen/ZIP: prellena NIT, fecha y valores."),
            ("Concepto o líneas", "Elige un concepto programado (autollena) o escribe las líneas Db/Cr."),
            ("Cuadre y guardar", "Verifica que Db = Cr y pulsa Guardar. También puedes Imprimir el PDF."),
        ],
        "tips": ["El concepto respeta la base mínima de retención por UVT.",
                 "Si el tercero no existe, se crea solo al guardar."],
    },
    "contabilidad": {
        "titulo": "Contabilidad (Libros)", "icono": "📚",
        "resumen": "Consulta libros e informes a partir del movimiento del período.",
        "pasos": [
            ("Elige el reporte", "Balance de prueba, PyG, Balance general, Libro mayor, Auxiliar, Cartera."),
            ("Rango de períodos", "Selecciona desde/hasta (AAAAMM) y genera."),
            ("Revisa el cuadre", "El sistema marca si Db = Cr y permite descargar a Excel."),
            ("Comprobante de diario", "Imprime el asiento en PDF desde su pestaña."),
        ],
        "tips": ["El Libro Mayor permite agrupar por nivel (clase/grupo/cuenta)."],
    },
    "cruce": {
        "titulo": "Pagos y Recaudos (cruce de facturas)", "icono": "💳",
        "resumen": "Cancela facturas pendientes de un tercero (total o parcial).",
        "pasos": [
            ("NIT del tercero", "Escríbelo y pulsa Buscar facturas pendientes."),
            ("Marca facturas", "Elige cuáles cancelar y ajusta el valor (permite abono parcial)."),
            ("Banco/caja y comprobante", "Indica la cuenta y el consecutivo."),
            ("Generar", "Guarda el egreso (por pagar) o el recibo de caja (por cobrar)."),
        ],
        "tips": ["Las facturas ya canceladas dejan de aparecer; las abonadas muestran el saldo."],
    },
    "plano_contai": {
        "titulo": "Cargar plano contable (Contai)", "icono": "📄",
        "resumen": "Sube el TXT de Contai (11 columnas) y agrégalo al movimiento del mes.",
        "pasos": [
            ("Sube o pega el plano", "Archivo .txt/.csv de 11 columnas separadas por TAB, sin encabezado."),
            ("Revisa la vista previa", "Verifica las líneas y que el plano cuadre (Db = Cr)."),
            ("Elige el período", "Selecciona año y mes; marca 'reemplazar' para no duplicar."),
            ("Contabiliza", "Se guarda en cn_movimientos (se ve en Contabilidad y Centro Contable)."),
        ],
        "tips": ["Orden: CUENTA·COMPROBANTE·FECHA·DOCUMENTO·DOC REF·NIT·DETALLE·TR·VALOR·BASE·C.C.",
                 "TR = 1 débito, 2 crédito. También puedes descargar el plano normalizado."],
    },
    "correcciones": {
        "titulo": "Correcciones", "icono": "🛠️",
        "resumen": "Corrige asientos ya cargados por comprobante o por registro.",
        "pasos": [
            ("Por comprobante", "Trae el asiento, edítalo y reemplázalo (debe cuadrar)."),
            ("Por registros", "Filtra y edita/elimina filas puntuales."),
            ("Períodos protegidos", "No se puede corregir un período protegido."),
        ],
        "tips": ["Edita el detalle/NIT sin cambiar valores para no descuadrar."],
    },
    "conceptos": {
        "titulo": "Conceptos y tarifas", "icono": "🧩",
        "resumen": "Administra tipos de IVA, retención y conceptos programados.",
        "pasos": [
            ("Sembrar estándar", "Crea el juego colombiano por defecto de un clic."),
            ("Ajusta cuentas", "Cambia las cuentas a tu PUC y las tarifas."),
            ("Úsalos en Captura", "El concepto arma el asiento cuadrado automáticamente."),
        ],
        "tips": ["Cada retención define su base mínima en UVT y su base de cálculo."],
    },
    "maestros": {
        "titulo": "Maestros", "icono": "🗂️",
        "resumen": "Sube plan de cuentas, terceros y centros de costo desde un plano.",
        "pasos": [
            ("Elige el maestro", "Plan de cuentas, terceros o centros de costo."),
            ("Sube el archivo", "Acepta .txt/.csv/.xlsx; reconoce columnas por encabezado."),
            ("Importa", "Revisa la vista previa y confirma."),
        ],
    },
    "centro_contable": {
        "titulo": "Centro Contable", "icono": "🔗",
        "resumen": "Ve qué causó cada módulo en el período y revérsalo si hace falta.",
        "pasos": [
            ("Elige el período", "Año y mes."),
            ("Revisa por módulo", "Líneas, débitos, créditos y cuadre de cada origen."),
            ("Reversar", "Borra lo de un módulo para reprocesar (respeta protegido)."),
        ],
    },
    "nomina": {
        "titulo": "Nómina", "icono": "💼",
        "resumen": "Procesa la nómina del mes y causa el plano en la contabilidad.",
        "pasos": [
            ("Sube los archivos", "Nómina del período (+ PILA opcional)."),
            ("Procesa", "Genera el plano del mes (comprobante 11 + ajuste PILA)."),
            ("Contabiliza", "Guarda en INTEGRAL en el período que necesites."),
        ],
        "tips": ["Vacaciones y ajuste PILA se consolidan en el mismo plano del mes."],
    },
    "ventas": {
        "titulo": "Ventas C13", "icono": "🛍️",
        "resumen": "Convierte la facturación en plano y causa las ventas.",
        "pasos": [
            ("Sube el archivo", "Facturación electrónica (Siigo)."),
            ("Procesa", "Genera el plano por comprobante."),
            ("Descarga o contabiliza", "A Contai (.txt) o al movimiento del mes."),
        ],
    },
    "compras": {
        "titulo": "Compras y Egresos", "icono": "🧾",
        "resumen": "Procesa compras/egresos, aplica retenciones y causa el plano.",
        "pasos": [
            ("Sube el archivo", "Compras y egresos del período."),
            ("Revisa retenciones", "Retefuente/reteIVA/reteICA aplicadas."),
            ("Descarga o contabiliza", "A Contai o al movimiento del mes."),
        ],
    },
    "bancos": {
        "titulo": "Bancos / Conciliación", "icono": "🔄",
        "resumen": "Lee extractos en PDF y genera el asiento de gastos bancarios.",
        "pasos": [
            ("Sube los PDF", "Extractos de Bancolombia, Banco de Bogotá, BBVA."),
            ("Centros de costo", "Cada gasto se reparte entre los CC indicados."),
            ("Genera y contabiliza", "Descarga el plano o agrégalo al movimiento del mes."),
        ],
    },
    "bittal": {
        "titulo": "Bittal → Contai", "icono": "🔁",
        "resumen": "Trae informes de Bittal y genera el plano contable.",
        "pasos": [
            ("Elige el informe", "Ventas, compras u otros."),
            ("Rango y credenciales", "Fechas y acceso a Bittal."),
            ("Genera y contabiliza", "Descarga el plano o agrégalo al movimiento del mes."),
        ],
    },
    "retencion": {
        "titulo": "Retención en la Fuente", "icono": "📊",
        "resumen": "Arma la declaración de retención (F350).",
        "pasos": [
            ("Período", "Elige el mes a declarar."),
            ("Revisa conceptos", "Bases y retenciones por concepto."),
            ("Genera", "JSON para la extensión del F350 / borrador."),
        ],
    },
    "exogena": {
        "titulo": "Información Exógena", "icono": "📑",
        "resumen": "Genera los formatos de medios magnéticos DIAN.",
        "pasos": [
            ("Carga balance y terceros", "El motor clasifica los movimientos."),
            ("Concilia", "Revisa lo que quede sin resolver."),
            ("Genera XML", "Valida contra el XSD y descarga."),
        ],
    },
}


# ============================================================
# Componente visual
# ============================================================

_CSS = """
<style>
.ay-box{ animation: ayfade .5s ease both; }
.ay-res{ color:#1f6f6a; font-weight:600; margin:.1rem 0 .7rem; }
.ay-step{ display:flex; gap:.6rem; align-items:flex-start; padding:.35rem 0;
  animation: ayslide .45s ease both; }
.ay-step:nth-child(2){animation-delay:.05s;} .ay-step:nth-child(3){animation-delay:.12s;}
.ay-step:nth-child(4){animation-delay:.19s;} .ay-step:nth-child(5){animation-delay:.26s;}
.ay-n{ flex:0 0 auto; width:24px; height:24px; border-radius:50%; color:#fff; font-weight:800;
  font-size:.8rem; display:flex; align-items:center; justify-content:center;
  background: linear-gradient(135deg,#2dd4bf,#0ea5e9); box-shadow:0 3px 8px rgba(14,165,233,.35);
  animation: aypulse 2.4s ease-in-out infinite; }
.ay-step:nth-child(3) .ay-n{ animation-delay:.4s; } .ay-step:nth-child(4) .ay-n{ animation-delay:.8s; }
.ay-d{ color:#5a6b7b; font-size:.86rem; }
.ay-tips{ margin-top:.5rem; background:#f0fbfa; border:1px solid #cfeeeb; border-radius:10px;
  padding:.5rem .8rem; font-size:.85rem; }
.ay-tips ul{ margin:.25rem 0 0 .9rem; padding:0; }
@keyframes ayslide{ from{opacity:0; transform:translateX(-8px);} to{opacity:1; transform:none;} }
@keyframes ayfade{ from{opacity:0;} to{opacity:1;} }
@keyframes aypulse{ 0%,100%{ transform:scale(1);} 50%{ transform:scale(1.12);} }
</style>
"""


def _html(a: dict) -> str:
    pasos = "".join(
        f"<div class='ay-step'><span class='ay-n'>{i}</span>"
        f"<div><b>{t}</b><div class='ay-d'>{d}</div></div></div>"
        for i, (t, d) in enumerate(a.get("pasos", []), 1)
    )
    tips = a.get("tips") or []
    tips_html = ("<div class='ay-tips'><b>💡 Tips</b><ul>"
                 + "".join(f"<li>{t}</li>" for t in tips) + "</ul></div>") if tips else ""
    return (f"<div class='ay-box'><div class='ay-res'>{a.get('icono','')} "
            f"{a.get('resumen','')}</div>{pasos}{tips_html}</div>")


def render_ayuda(clave: str, expanded: bool = False):
    """Panel plegable de ayuda para un módulo (una línea por página)."""
    a = AYUDAS.get(clave)
    if not a:
        return
    st.markdown(_CSS, unsafe_allow_html=True)
    with st.expander(f"❓ ¿Cómo se usa **{a['titulo']}**?", expanded=expanded):
        st.markdown(_html(a), unsafe_allow_html=True)


def render_ayuda_bloque(clave: str):
    """Igual pero sin expander (para la página central de Ayuda)."""
    a = AYUDAS.get(clave)
    if not a:
        return
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(f"### {a.get('icono','')} {a['titulo']}")
    st.markdown(_html(a), unsafe_allow_html=True)
