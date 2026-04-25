"""
Gestión multi-empresa. Cada usuario puede pertenecer a varias empresas
con diferentes roles (admin, operador, consulta).

Funciones principales:
    - empresas_del_usuario(): lista de empresas a las que tiene acceso
    - seleccionar_empresa(): widget en sidebar para cambiar de empresa
    - empresa_activa(): retorna la empresa actualmente seleccionada
    - require_empresa(): se usa en páginas que requieren empresa activa
    - filtrar_menu_por_modulos(): oculta del sidebar las páginas que la
      empresa activa no tiene habilitadas
"""
import streamlit as st
from db.supabase_client import get_supabase
from auth.login import current_user


# ============================================================
# Mapeo: nombre que muestra Streamlit en el menú → código de módulo
# ============================================================
# Streamlit toma el nombre del archivo de la página (sin emojis ni guiones bajos)
# y lo muestra en el menú. Aquí mapeamos esos nombres a su código de módulo.
#
# Ej: 'pages/2_🛒_Compras_DIAN.py' → 'Compras DIAN' en el menú.
#
# Para añadir un módulo nuevo, agrega su entrada aquí también.
# ============================================================

# Conjunto de módulos que ya viene con la plataforma
PAGINA_A_MODULO = {
    # texto-mostrado-en-menú: codigo_modulo
    "Caja Menor":      "caja_menor",
    "Compras DIAN":    "compras_dian",
    "PILA":            "pila",
    "Ingresos POS":    "ingresos_pos",
}

# Páginas que SIEMPRE se muestran sin importar los módulos asignados:
# - Configuración: el admin / superadmin debe poder gestionar siempre
# - Panel Admin: solo lo ve el superadmin (lo controla require_superadmin)
PAGINAS_SIEMPRE_VISIBLES = {
    "Configuración",
    "Panel Admin",
    "Plataforma Contable",
    "Home",
}


def empresas_del_usuario():
    """Retorna [{id, nit, razon_social, rol}, ...] para el usuario actual."""
    user = current_user()
    if not user:
        return []

    sb = get_supabase()
    try:
        resp = (
            sb.table("usuario_empresa")
              .select("rol, empresas(id, nit, razon_social)")
              .eq("usuario_id", user["id"])
              .execute()
        )
    except Exception as e:
        st.error(f"Error leyendo empresas: {e}")
        return []

    empresas = []
    for row in resp.data or []:
        emp = row.get("empresas") or {}
        if not emp:
            continue
        empresas.append({
            "id": emp["id"],
            "nit": emp["nit"],
            "razon_social": emp["razon_social"],
            "rol": row["rol"],
        })
    return empresas


def empresa_activa():
    """Retorna la empresa seleccionada en la sesión, o None."""
    return st.session_state.get("empresa_activa")


def seleccionar_empresa_sidebar():
    """Widget en el sidebar para seleccionar / cambiar empresa."""
    empresas = empresas_del_usuario()
    if not empresas:
        with st.sidebar:
            st.warning(
                "No tienes empresas asignadas. Contacta al administrador."
            )
        return None

    # Si solo hay una, seleccionarla automáticamente
    if len(empresas) == 1 and not empresa_activa():
        st.session_state["empresa_activa"] = empresas[0]

    with st.sidebar:
        st.markdown("### 🏢 Empresa activa")
        nombres = [f"{e['razon_social']} ({e['nit']})" for e in empresas]
        actual = empresa_activa()
        idx_default = 0
        if actual:
            for i, e in enumerate(empresas):
                if e["id"] == actual["id"]:
                    idx_default = i
                    break

        seleccion = st.selectbox(
            "Selecciona empresa",
            options=range(len(empresas)),
            format_func=lambda i: nombres[i],
            index=idx_default,
            key="sel_empresa",
            label_visibility="collapsed",
        )
        nueva = empresas[seleccion]
        cambio_empresa = (not actual) or (actual["id"] != nueva["id"])
        if cambio_empresa:
            # Limpiar el caché de módulos al cambiar de empresa
            from auth.modulos import invalidar_cache_modulos
            if actual:
                invalidar_cache_modulos(actual["id"])
            st.session_state["empresa_activa"] = nueva
            st.rerun()

        st.caption(f"Rol: `{nueva['rol']}`")

    # Aplicar filtrado del menú según los módulos de la empresa activa
    filtrar_menu_por_modulos(nueva)

    return nueva


def filtrar_menu_por_modulos(emp: dict):
    """Oculta del sidebar las páginas cuyo módulo no esté habilitado para
    la empresa activa.

    Estrategia: inyectar CSS que oculta los <a> del menú cuyo texto coincida
    con módulos NO habilitados.
    """
    if not emp:
        return

    # Importación tardía para evitar import circular
    from auth.modulos import codigos_modulos_habilitados
    from auth.superadmin import es_superadmin

    habilitados = codigos_modulos_habilitados(emp["id"])

    # El superadmin SIEMPRE ve todas las páginas (puede operar cualquier empresa)
    es_super = es_superadmin()

    paginas_a_ocultar = []
    for nombre_menu, codigo_modulo in PAGINA_A_MODULO.items():
        if codigo_modulo not in habilitados and not es_super:
            paginas_a_ocultar.append(nombre_menu)

    if not paginas_a_ocultar:
        return

    # Construir CSS que oculta cada item del menú lateral
    # El sidebar de Streamlit genera <a> con un span interno conteniendo el texto.
    # Ocultamos por contenido del span.
    selectors = []
    for nombre in paginas_a_ocultar:
        # Selector basado en el texto contenido en el span del item de navegación
        # Funciona para Streamlit >= 1.30 que usa el atributo data-testid
        # y también para versiones que usan estructura plana
        selectors.append(
            f'[data-testid="stSidebarNavLink"]:has(span:-webkit-any(:contains("{nombre}")))'
        )

    # Generar CSS más robusto usando el nombre como atributo
    # Estrategia segura: ocultar por texto del span dentro del enlace de navegación
    css_rules = []
    for nombre in paginas_a_ocultar:
        # Escapar comillas dobles en el nombre por si acaso
        nombre_safe = nombre.replace('"', '\\"')
        css_rules.append(f"""
            [data-testid="stSidebarNav"] a:has(span:contains("{nombre_safe}")),
            [data-testid="stSidebarNavLink"]:has(span:contains("{nombre_safe}")),
            section[data-testid="stSidebar"] a:has(span:contains("{nombre_safe}")) {{
                display: none !important;
            }}
        """)

    # JavaScript fallback (más robusto que :contains que no es CSS estándar)
    js_paginas = ", ".join([f'"{n}"' for n in paginas_a_ocultar])

    html = f"""
        <style>
        /* Intento por CSS (algunos navegadores soportan :has + :contains) */
        {"".join(css_rules)}
        </style>
        <script>
        (function() {{
            const ocultas = [{js_paginas}];
            function ocultarPaginas() {{
                // Buscar todos los items del menú lateral
                const links = document.querySelectorAll(
                    'section[data-testid="stSidebar"] a, ' +
                    '[data-testid="stSidebarNav"] a, ' +
                    '[data-testid="stSidebarNavLink"]'
                );
                links.forEach(link => {{
                    const txt = (link.textContent || "").trim();
                    for (const pageName of ocultas) {{
                        if (txt === pageName || txt.endsWith(pageName)) {{
                            // Ocultar el contenedor del item completo
                            let target = link;
                            // Subir hasta el li o el contenedor más cercano
                            while (target && target.tagName !== 'LI' &&
                                   target.parentElement &&
                                   target.parentElement.tagName !== 'NAV' &&
                                   target.parentElement.tagName !== 'UL') {{
                                target = target.parentElement;
                            }}
                            target.style.display = 'none';
                            break;
                        }}
                    }}
                }});
            }}
            // Ejecutar inmediatamente y en cada cambio del DOM
            ocultarPaginas();
            const observer = new MutationObserver(ocultarPaginas);
            observer.observe(document.body, {{ childList: true, subtree: true }});
        }})();
        </script>
    """
    st.markdown(html, unsafe_allow_html=True)


def require_empresa():
    """Garantiza que hay una empresa activa. Detiene la página si no."""
    emp = empresa_activa()
    if not emp:
        st.warning("⚠️ Selecciona una empresa en el panel lateral para continuar.")
        st.stop()
    return emp


def require_rol(roles_permitidos):
    """Verifica que el usuario tiene uno de los roles dados en la empresa activa.

    Args:
        roles_permitidos: lista, ej ['admin', 'operador']
    """
    emp = require_empresa()
    if emp["rol"] not in roles_permitidos:
        st.error(
            f"⛔ No tienes permisos para usar este módulo. "
            f"Tu rol es '{emp['rol']}', se requiere uno de: {roles_permitidos}"
        )
        st.stop()
    return emp
