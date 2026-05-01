"""
Módulo Impuestos Saludables (INC, IBUA, ICUI)

Liquida los impuestos especiales sobre:
    - INC: Impuesto Nacional al Consumo (telefonía, restaurantes, vehículos)
    - IBUA: Impuesto a las Bebidas Ultraprocesadas Azucaradas (Ley 2277/2022)
    - ICUI: Impuesto a los alimentos Ultraprocesados Industrialmente

Vigente desde noviembre 2023, con incremento gradual hasta 2025.
Para Silla Tres aplica IBUA e ICUI sobre las facturas de proveedores que
entregan bebidas y alimentos ultraprocesados.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from auth.login import require_auth, sidebar_user_info
from auth.empresas import seleccionar_empresa_sidebar, require_empresa
from core.utils.ui_tributarias import render_pagina_tributaria, render_proximamente


require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()
empresa = require_empresa()

render_pagina_tributaria(
    titulo="Impuestos Saludables",
    descripcion="INC (consumo), IBUA (bebidas) e ICUI (alimentos ultraprocesados) - Ley 2277/2022",
    icono="🥤",
)


# ============================================================
# Información normativa
# ============================================================

with st.expander("📖 Marco normativo", expanded=False):
    st.markdown(
        """
        **Ley 2277 de diciembre 2022** (Reforma tributaria) creó los impuestos:

        - **IBUA** — Impuesto sobre Bebidas Ultraprocesadas Azucaradas (art. 513-1 a 513-6 ET)
          - Tarifa según gramos de azúcar por 100ml
          - 2023: tarifas reducidas (transición)
          - 2024: tarifas plenas
          - 2025: tarifas con ajuste por IPC

        - **ICUI** — Impuesto a los productos comestibles ultraprocesados industrialmente (art. 513-7 a 513-12 ET)
          - Tarifa ad valorem sobre el precio de venta al público
          - 2023: 10% (transición)
          - 2024: 15%
          - 2025: 20%

        - **INC** — Impuesto Nacional al Consumo (art. 512-1 ET)
          - Servicio de telefonía móvil: 4%
          - Restaurantes y bares: 8%
          - Vehículos, embarcaciones y aeronaves de lujo: 8% o 16%
        """
    )

st.markdown("---")


# ============================================================
# Tabs por tipo de impuesto
# ============================================================

tab_resumen, tab_ibua, tab_icui, tab_inc, tab_decl = st.tabs([
    "📊 Resumen mensual",
    "🥤 IBUA",
    "🍪 ICUI",
    "📱 INC",
    "📄 Declaración",
])


with tab_resumen:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total IBUA mes", "—")
    with col2:
        st.metric("Total ICUI mes", "—")
    with col3:
        st.metric("Total INC mes", "—")
    with col4:
        st.metric("Total a declarar", "—")

    st.markdown("---")
    render_proximamente(
        titulo="Resumen mensual de impuestos saludables",
        descripcion=(
            "Vista consolidada de los tres impuestos a partir de los movimientos "
            "del mes. Identifica facturas con productos gravados automáticamente "
            "según el procesador de Compras DIAN."
        ),
        fases=[
            "Detección de productos gravados por código UBL en facturas DIAN",
            "Acumulado mensual por tipo de impuesto",
            "Comparativo con período anterior",
        ],
        relacionados=[
            ("Compras DIAN", "El procesador detecta IBUA/ICUI/INC en la cuenta 14359505"),
        ],
    )


with tab_ibua:
    st.markdown("### 🥤 Impuesto a Bebidas Ultraprocesadas Azucaradas (IBUA)")
    st.markdown(
        "Aplica sobre **bebidas con azúcares añadidos**, edulcorantes calóricos o "
        "concentrados (jarabes, polvos, refrescos)."
    )

    st.markdown("#### Tarifas vigentes 2025 (por cada 100 ml)")
    st.dataframe(
        {
            "Contenido de azúcar": [
                "Menor a 6 g / 100 ml",
                "Entre 6 y 10 g / 100 ml",
                "Mayor o igual a 10 g / 100 ml",
            ],
            "Tarifa 2025 (COP)": ["$0", "$28", "$55"],
        },
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    render_proximamente(
        titulo="Liquidación automática de IBUA",
        descripcion=(
            "Identifica las facturas de proveedores de bebidas (Postobón, Coca Cola, "
            "Bavaria, etc.), determina el contenido de azúcar por producto y aplica "
            "la tarifa correspondiente al volumen comprado."
        ),
        fases=[
            "Catálogo de productos gravados con su contenido de azúcar",
            "Detección automática por NIT del proveedor (whitelist)",
            "Cruce con la cuenta contable 14359505 (impuesto saludable inventario)",
            "Liquidación mensual y anual",
        ],
        relacionados=[
            ("Compras DIAN", "Ya carga IBUA a la cuenta 14359505 para Silla Tres"),
            ("Información Exógena", "Reporta a través del formato 1001"),
        ],
    )


with tab_icui:
    st.markdown("### 🍪 Impuesto a Comestibles Ultraprocesados Industrialmente (ICUI)")
    st.markdown(
        "Aplica sobre **productos ultraprocesados industrialmente con altos contenidos "
        "de sodio, azúcares añadidos o grasas saturadas** (galletas, embutidos, papas fritas, "
        "cereales azucarados, etc.)."
    )

    st.markdown("#### Tarifas vigentes")
    st.dataframe(
        {
            "Año": ["2023", "2024", "2025"],
            "Tarifa": ["10%", "15%", "20%"],
        },
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    render_proximamente(
        titulo="Liquidación automática de ICUI",
        descripcion=(
            "Calcula el ICUI ad valorem sobre el precio de venta al público de los "
            "productos comestibles ultraprocesados gravados según la lista oficial."
        ),
        fases=[
            "Catálogo oficial de partidas arancelarias gravadas",
            "Detección por NIT de proveedor (Nutresa, Alpina, Colombina, etc.)",
            "Aplicación de tarifa 20% sobre precio venta",
            "Cruce con cuenta 14359505",
        ],
        relacionados=[
            ("Compras DIAN", "Ya detecta ICUI en facturas con códigos UBL específicos"),
        ],
    )


with tab_inc:
    st.markdown("### 📱 Impuesto Nacional al Consumo (INC)")
    st.markdown(
        "Aplica sobre **servicios de telefonía móvil, restaurantes, bares, y vehículos "
        "y embarcaciones de lujo**."
    )

    st.markdown("#### Tarifas vigentes")
    st.dataframe(
        {
            "Servicio o bien": [
                "Telefonía móvil",
                "Restaurantes y bares",
                "Vehículos lujo (>USD 30k)",
                "Embarcaciones y aeronaves",
            ],
            "Tarifa": ["4%", "8%", "8% o 16%", "8% o 16%"],
            "Cuenta Silla Tres": [
                "52159502",
                "52159501",
                "—",
                "—",
            ],
        },
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("---")
    render_proximamente(
        titulo="Liquidación automática de INC",
        descripcion=(
            "Identifica facturas de servicios gravados con INC. Para Silla Tres, "
            "el INC de telefonía va a la cuenta 52159502 y el INC de otros gastos "
            "(restaurantes, bares) a la cuenta 52159501."
        ),
        fases=[
            "Detección de telefonía por nombre del emisor (Tigo, Claro, Movistar, ETB)",
            "Detección de restaurantes/bares por código CIIU del NIT",
            "Aplicación automática de cuenta según el contexto",
            "Liquidación bimestral conforme al formulario DIAN",
        ],
        relacionados=[
            ("Compras DIAN", "Ya implementa la detección de telefonía en el puente_motor"),
        ],
    )


with tab_decl:
    render_proximamente(
        titulo="Declaración bimestral consolidada",
        descripcion=(
            "Genera el formulario oficial DIAN para cada uno de los tres impuestos "
            "(IBUA, ICUI, INC) según su periodicidad. Vencimiento bimestral."
        ),
        fases=[
            "Formularios oficiales DIAN para cada impuesto",
            "Calendario de vencimientos con alertas",
            "Liquidación de sanciones por extemporaneidad",
            "Histórico anual con comparativos",
        ],
    )
