"""
Página de Configuración.

Tabs:
    1. 🏢 Empresas              — listado de empresas del usuario
    2. 📂 Archivos              — info de configuración por empresa
    3. 📚 Balance de prueba     — cargar/ver/eliminar balance histórico (Fase 2)
    4. 👥 Usuarios              — gestión completa para admins de empresa
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

from auth.login import require_auth, sidebar_user_info, current_user
from auth.empresas import (
    seleccionar_empresa_sidebar,
    require_empresa,
    empresas_del_usuario,
)
from auth.superadmin import es_superadmin
from auth import admin_usuarios as adm
from auth import modulos as mod_sys
from core.utils import conocimiento_balance as cb


st.set_page_config(page_title="Configuración", page_icon="⚙️", layout="wide")
require_auth()
seleccionar_empresa_sidebar()
sidebar_user_info()

st.title("⚙️ Configuración")
st.markdown("---")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏢 Empresas",
    "📂 Archivos de configuración",
    "📚 Balance de prueba",
    "👥 Usuarios",
    "🧩 Módulos",
])


# ============================================================
# TAB 1: Empresas (info)
# ============================================================
with tab1:
    st.markdown("### Mis empresas")
    empresas = empresas_del_usuario()
    if not empresas:
        st.warning("No tienes empresas asignadas.")
    else:
        df = pd.DataFrame(empresas)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("### ➕ Crear nueva empresa")
    if es_superadmin():
        st.info("Para crear empresas usa el **🔧 Panel Admin**.")
    else:
        st.info("Para crear empresas, contacta al superadmin del sistema.")


# ============================================================
# TAB 2: Archivos de configuración
# ============================================================
with tab2:
    st.markdown("### Archivos de configuración por empresa")
    st.info(
        "🚧 En desarrollo: aquí podrás subir los archivos `cuentas.xlsx` y "
        "`mapeos.xlsx` de cada empresa.\n\n"
        "Por ahora súbelos manualmente al bucket `empresas-config` de "
        "Supabase Storage en la ruta `{empresa_id}/cuentas.xlsx` y "
        "`{empresa_id}/mapeos.xlsx`."
    )


# ============================================================
# TAB 3: Balance de prueba (Fase 2)
# ============================================================
with tab3:
    st.markdown("### 📚 Balance de prueba histórico")
    st.caption(
        "El balance permite que el procesador de Compras DIAN tome mejores "
        "decisiones contables: respeta el comportamiento histórico de "
        "retefuente por NIT y sugiere cuentas de gasto / IVA recurrentes."
    )

    emp_activa_dict = st.session_state.get("empresa_activa")
    if not emp_activa_dict:
        st.warning("Selecciona primero una empresa en el menú lateral.")
    else:
        empresa_id_balance = emp_activa_dict["id"]

        st.markdown("#### Estado actual")
        conocimiento_actual = cb.cargar_conocimiento_desde_storage(empresa_id_balance)

        if conocimiento_actual:
            estad = conocimiento_actual.get("estadisticas", {})
            col_a, col_b, col_c, col_d = st.columns(4)
            col_a.metric("Total NITs", estad.get("total_nits", 0))
            col_b.metric("Con retefuente histórica",
                         estad.get("con_retefuente_historica", 0))
            col_c.metric("IVA mercancía (24080201)",
                         estad.get("con_iva_mercancia", 0))
            col_d.metric("IVA servicios (24080308)",
                         estad.get("con_iva_servicios", 0))

            info_extra = []
            if conocimiento_actual.get("empresa"):
                info_extra.append(f"**Empresa:** {conocimiento_actual['empresa']}")
            if conocimiento_actual.get("fecha_balance"):
                info_extra.append(
                    f"**Fecha balance:** {conocimiento_actual['fecha_balance']}"
                )
            if conocimiento_actual.get("fecha_procesamiento"):
                info_extra.append(
                    f"**Procesado:** {conocimiento_actual['fecha_procesamiento']}"
                )
            if info_extra:
                st.caption(" · ".join(info_extra))

            if st.button("🗑️ Eliminar balance cargado", key="btn_eliminar_balance"):
                ok = cb.eliminar_conocimiento_de_storage(empresa_id_balance)
                if ok:
                    st.success("Balance eliminado.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("No se pudo eliminar.")
        else:
            st.info("📭 Esta empresa todavía no tiene balance cargado.")

        st.markdown("---")
        st.markdown("#### Cargar / actualizar balance")
        st.caption(
            "Sube el Excel del balance de prueba exportado del sistema "
            "contable. Estructura esperada: cabecera con nombre de empresa "
            "(fila 1) y fecha del balance (fila 2), y desde la fila 4 las "
            "columnas: Cuenta · Equivalente · Nombre cuenta · NIT · Nombre "
            "NIT · Saldo anterior · Débitos · Créditos."
        )

        archivo_balance = st.file_uploader(
            "Excel del balance de prueba",
            type=["xlsx"],
            key="file_balance",
        )

        if archivo_balance:
            col_p1, col_p2 = st.columns([1, 3])
            with col_p1:
                procesar_balance = st.button(
                    "📊 Procesar balance",
                    type="primary",
                    use_container_width=True,
                )
            with col_p2:
                st.caption(
                    "Al procesar, el archivo se analiza y se guarda como "
                    "`conocimiento_balance.json` en Supabase Storage. El Excel "
                    "no se conserva."
                )

            if procesar_balance:
                with st.spinner("Procesando balance..."):
                    try:
                        conocimiento_nuevo = cb.procesar_balance(archivo_balance)
                    except Exception as e:
                        st.error(f"❌ Error procesando el balance: {e}")
                        st.exception(e)
                        st.stop()

                    estad = conocimiento_nuevo.get("estadisticas", {})
                    if estad.get("total_nits", 0) == 0:
                        st.error(
                            "El archivo no contiene NITs procesables. Revisa "
                            "que el formato sea el balance de prueba completo "
                            "y que haya datos desde la fila 4."
                        )
                        st.stop()

                    try:
                        cb.guardar_conocimiento_en_storage(
                            empresa_id_balance, conocimiento_nuevo,
                        )
                    except Exception as e:
                        st.error(
                            "❌ No se pudo guardar en Supabase Storage. "
                            "Revisa que el bucket `empresas-config` exista y "
                            "que el usuario tenga permisos de escritura.\n\n"
                            f"Detalle: {e}"
                        )
                        st.exception(e)
                        st.stop()

                st.success(
                    f"✅ Balance procesado y guardado. "
                    f"{estad.get('total_nits', 0)} NITs registrados."
                )
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Total NITs", estad.get("total_nits", 0))
                col_b.metric("Con retefuente histórica",
                             estad.get("con_retefuente_historica", 0))
                col_c.metric("Con IVA descontable recurrente",
                             estad.get("con_iva_mercancia", 0)
                             + estad.get("con_iva_servicios", 0))

                st.cache_data.clear()

                with st.expander("Ver primeros 20 NITs procesados"):
                    nits_dict = conocimiento_nuevo.get("nits", {})
                    filas = []
                    for nit, info in list(nits_dict.items())[:20]:
                        filas.append({
                            "NIT": nit,
                            "Nombre": info.get("nombre", ""),
                            "Cuenta gasto": (info.get("cuentas_gasto") or [""])[0],
                            "Cuenta IVA": info.get("cuenta_iva_recurrente", ""),
                            "Retefuente histórica": "Sí" if info.get("tiene_retefuente_historica") else "No",
                        })
                    if filas:
                        st.dataframe(pd.DataFrame(filas),
                                     use_container_width=True, hide_index=True)


# ============================================================
# TAB 4: Usuarios — gestión completa para admins de empresa
# ============================================================
with tab4:
    st.markdown("### 👥 Gestión de usuarios")

    if not adm.puede_gestionar_usuarios():
        st.warning(
            "🔒 Esta sección está disponible solo para usuarios con rol "
            "**admin** en alguna empresa, o para el superadmin del sistema. "
            "Tu rol actual no incluye gestión de usuarios."
        )
    else:
        # Selector: empresas que el usuario administra
        if es_superadmin():
            from auth.empresas import empresas_del_usuario as _todas
            # El superadmin puede ver todas las empresas (incluso donde no es
            # admin formal). Tomamos las empresas del usuario, y si está vacío,
            # avisamos. Para acceso completo está el Panel Admin.
            mis_empresas = adm.listar_empresas_que_administro()
            if not mis_empresas:
                st.info(
                    "Eres superadmin pero no tienes el rol 'admin' asignado en "
                    "ninguna empresa. Para gestión global usa el "
                    "**🔧 Panel Admin**."
                )
        else:
            mis_empresas = adm.listar_empresas_que_administro()

        if not mis_empresas:
            st.info(
                "No administras ninguna empresa. Si crees que esto es un error, "
                "pide al superadmin que te asigne el rol `admin` en la empresa "
                "que corresponde."
            )
        else:
            opc_emp = {
                f"{e['razon_social']} ({e['nit']})": e["id"]
                for e in mis_empresas
            }
            emp_label = st.selectbox(
                "Empresa",
                options=list(opc_emp.keys()),
                key="sel_emp_users",
            )
            empresa_id_users = opc_emp[emp_label]

            st.markdown("---")

            # ---- Usuarios actualmente con acceso ----
            st.markdown(f"#### Usuarios con acceso a **{emp_label}**")

            usuarios = adm.listar_usuarios_de_empresa(empresa_id_users)

            if not usuarios:
                st.info("Ningún usuario tiene acceso a esta empresa todavía.")
            else:
                yo_id = current_user()["id"]

                for u in usuarios:
                    with st.container():
                        cols = st.columns([3, 2, 1, 1, 1])

                        with cols[0]:
                            email = u["email"]
                            if u["usuario_id"] == yo_id:
                                st.markdown(f"**{email}** 👈 _eres tú_")
                            else:
                                st.markdown(f"**{email}**")

                        with cols[1]:
                            roles_disponibles = ["admin", "operador", "consulta"]
                            rol_actual = u["rol"]
                            idx_actual = (roles_disponibles.index(rol_actual)
                                          if rol_actual in roles_disponibles else 0)
                            nuevo_rol = st.selectbox(
                                "rol",
                                options=roles_disponibles,
                                index=idx_actual,
                                key=f"rol_{u['usuario_id']}_{empresa_id_users}",
                                label_visibility="collapsed",
                                disabled=(u["usuario_id"] == yo_id),
                            )

                        with cols[2]:
                            if u["usuario_id"] != yo_id:
                                if (nuevo_rol != rol_actual and
                                    st.button(
                                        "💾",
                                        key=f"save_{u['usuario_id']}_{empresa_id_users}",
                                        help="Guardar cambio de rol",
                                        use_container_width=True,
                                    )):
                                    res = adm.asignar_usuario_a_empresa(
                                        u["usuario_id"], empresa_id_users, nuevo_rol,
                                    )
                                    if res["success"]:
                                        st.success(f"Rol actualizado: {email} → {nuevo_rol}")
                                        st.rerun()
                                    else:
                                        st.error(res["error"])

                        with cols[3]:
                            if (u["usuario_id"] != yo_id and
                                st.button(
                                    "🔑",
                                    key=f"reset_{u['usuario_id']}_{empresa_id_users}",
                                    help="Resetear contraseña",
                                    use_container_width=True,
                                )):
                                st.session_state[f"resetear_pwd_{u['usuario_id']}"] = True

                        with cols[4]:
                            if (u["usuario_id"] != yo_id and
                                st.button(
                                    "🗑️",
                                    key=f"rm_{u['usuario_id']}_{empresa_id_users}",
                                    help="Quitar acceso a esta empresa",
                                    use_container_width=True,
                                )):
                                st.session_state[f"confirmar_rm_{u['usuario_id']}"] = True

                        # Confirmación de eliminación inline
                        if st.session_state.get(f"confirmar_rm_{u['usuario_id']}"):
                            st.warning(
                                f"⚠️ ¿Confirmar quitar acceso de **{email}** a "
                                f"esta empresa? El usuario seguirá existiendo "
                                f"en el sistema y podrá usar otras empresas a "
                                f"las que tenga acceso."
                            )
                            cc1, cc2, _ = st.columns([1, 1, 4])
                            with cc1:
                                if st.button("Sí, quitar",
                                             key=f"si_rm_{u['usuario_id']}",
                                             type="primary"):
                                    res = adm.remover_usuario_de_empresa(
                                        u["usuario_id"], empresa_id_users,
                                    )
                                    st.session_state.pop(
                                        f"confirmar_rm_{u['usuario_id']}", None,
                                    )
                                    if res["success"]:
                                        st.success(f"Acceso removido para {email}")
                                        st.rerun()
                                    else:
                                        st.error(res["error"])
                            with cc2:
                                if st.button("Cancelar",
                                             key=f"no_rm_{u['usuario_id']}"):
                                    st.session_state.pop(
                                        f"confirmar_rm_{u['usuario_id']}", None,
                                    )
                                    st.rerun()

                        # Reseteo de contraseña inline
                        if st.session_state.get(f"resetear_pwd_{u['usuario_id']}"):
                            st.info(f"🔑 Resetear contraseña de **{email}**")
                            cc1, cc2, cc3 = st.columns([2, 1, 1])
                            with cc1:
                                nuevo_pwd_input = st.text_input(
                                    "Nueva contraseña (mínimo 8 caracteres)",
                                    key=f"new_pwd_{u['usuario_id']}",
                                    type="password",
                                )
                            with cc2:
                                if st.button("🎲 Generar",
                                             key=f"gen_{u['usuario_id']}",
                                             help="Generar contraseña segura",
                                             use_container_width=True):
                                    pwd_gen = adm.generar_password_temporal()
                                    st.session_state[f"pwd_generada_{u['usuario_id']}"] = pwd_gen
                                    st.rerun()
                            with cc3:
                                if st.button("Cancelar",
                                             key=f"cancel_pwd_{u['usuario_id']}",
                                             use_container_width=True):
                                    st.session_state.pop(
                                        f"resetear_pwd_{u['usuario_id']}", None,
                                    )
                                    st.session_state.pop(
                                        f"pwd_generada_{u['usuario_id']}", None,
                                    )
                                    st.rerun()

                            pwd_gen = st.session_state.get(f"pwd_generada_{u['usuario_id']}")
                            if pwd_gen:
                                st.code(pwd_gen, language=None)
                                st.caption(
                                    "👆 Copia esta contraseña antes de aplicar el cambio. "
                                    "No volverá a mostrarse."
                                )

                            pwd_a_usar = nuevo_pwd_input or pwd_gen or ""
                            if st.button(
                                "Aplicar cambio de contraseña",
                                key=f"apply_pwd_{u['usuario_id']}",
                                type="primary",
                                disabled=(len(pwd_a_usar) < 8),
                            ):
                                res = adm.resetear_password_usuario(
                                    u["usuario_id"], pwd_a_usar,
                                )
                                if res["success"]:
                                    st.success(
                                        f"✅ Contraseña de {email} actualizada. "
                                        "Pásasela al usuario."
                                    )
                                    st.session_state.pop(
                                        f"resetear_pwd_{u['usuario_id']}", None,
                                    )
                                    st.session_state.pop(
                                        f"pwd_generada_{u['usuario_id']}", None,
                                    )
                                else:
                                    st.error(res["error"])

            st.markdown("---")

            # ---- Asignar usuario existente ----
            st.markdown("#### ➕ Dar acceso a un usuario existente")
            st.caption(
                "Si el usuario YA tiene cuenta en la plataforma, escribe su "
                "correo aquí para darle acceso a esta empresa."
            )
            with st.form(f"form_asignar_existente_{empresa_id_users}",
                         clear_on_submit=True):
                col_e, col_r, col_b = st.columns([3, 2, 1])
                with col_e:
                    email_existente = st.text_input(
                        "Correo del usuario",
                        placeholder="usuario@ejemplo.com",
                        label_visibility="collapsed",
                    )
                with col_r:
                    rol_asignar = st.selectbox(
                        "Rol",
                        options=["operador", "consulta", "admin"],
                        label_visibility="collapsed",
                    )
                with col_b:
                    submit_asignar = st.form_submit_button(
                        "Asignar", type="primary", use_container_width=True,
                    )

                if submit_asignar:
                    if not email_existente:
                        st.error("Escribe el correo del usuario.")
                    else:
                        usuario = adm.buscar_usuario_por_email(email_existente)
                        if not usuario:
                            st.error(
                                f"No existe ningún usuario con el correo "
                                f"`{email_existente}`. Si quieres invitarlo, "
                                f"crea su cuenta abajo en **Crear usuario nuevo**."
                            )
                        else:
                            res = adm.asignar_usuario_a_empresa(
                                usuario["id"], empresa_id_users, rol_asignar,
                            )
                            if res["success"]:
                                st.success(
                                    f"✅ {email_existente} tiene ahora acceso "
                                    f"como **{rol_asignar}**."
                                )
                                st.rerun()
                            else:
                                st.error(res["error"])

            st.markdown("---")

            # ---- Crear usuario nuevo ----
            st.markdown("#### 🆕 Crear usuario nuevo")
            st.caption(
                "Crea una cuenta nueva en la plataforma con una contraseña "
                "inicial. La contraseña se mostrará UNA SOLA VEZ después de "
                "crear el usuario; cópiala y pásasela por WhatsApp / correo. "
                "El usuario podrá cambiarla desde su perfil cuando entre."
            )

            estado_pwd_nuevo = st.session_state.get("pwd_nuevo_usuario")

            if not estado_pwd_nuevo:
                with st.form(f"form_crear_nuevo_{empresa_id_users}",
                             clear_on_submit=False):
                    col_e, col_r = st.columns([3, 2])
                    with col_e:
                        email_nuevo = st.text_input(
                            "Correo del nuevo usuario",
                            placeholder="nuevo@ejemplo.com",
                            key="email_nuevo_input",
                        )
                    with col_r:
                        rol_nuevo = st.selectbox(
                            "Rol en esta empresa",
                            options=["operador", "consulta", "admin"],
                            key="rol_nuevo_input",
                        )

                    col_p1, col_p2 = st.columns([2, 1])
                    with col_p1:
                        pwd_manual = st.text_input(
                            "Contraseña inicial (déjalo vacío para generar una)",
                            key="pwd_nuevo_manual",
                            type="password",
                        )
                    with col_p2:
                        st.write("")
                        st.write("")
                        usar_generada = st.checkbox(
                            "🎲 Generar automática",
                            key="usar_pwd_gen_nuevo",
                            value=True,
                        )

                    if st.form_submit_button("Crear usuario", type="primary"):
                        email_clean = (email_nuevo or "").strip().lower()
                        if not email_clean or "@" not in email_clean:
                            st.error("Ingresa un correo válido.")
                        else:
                            # Determinar contraseña
                            if usar_generada:
                                pwd_inicial = adm.generar_password_temporal()
                            else:
                                pwd_inicial = (pwd_manual or "").strip()
                                if len(pwd_inicial) < 8:
                                    st.error(
                                        "La contraseña debe tener al menos 8 "
                                        "caracteres, o marca 'Generar automática'."
                                    )
                                    st.stop()

                            # Crear usuario en Auth
                            with st.spinner("Creando usuario..."):
                                res = adm.crear_usuario_con_password(
                                    email_clean, pwd_inicial,
                                )

                            if not res["success"]:
                                st.error(f"❌ {res['error']}")
                                st.stop()

                            # Asignar a la empresa
                            res_asign = adm.asignar_usuario_a_empresa(
                                res["user_id"], empresa_id_users, rol_nuevo,
                            )
                            if not res_asign["success"]:
                                st.warning(
                                    "Usuario creado pero falló la asignación a "
                                    f"la empresa: {res_asign['error']}. "
                                    "Asígnalo manualmente desde la sección de "
                                    "arriba."
                                )

                            # Guardar la contraseña en estado para mostrar
                            st.session_state["pwd_nuevo_usuario"] = {
                                "email": email_clean,
                                "pwd": pwd_inicial,
                                "rol": rol_nuevo,
                            }
                            st.rerun()

            else:
                # Mostrar la contraseña recién creada
                st.success(
                    f"✅ Usuario **{estado_pwd_nuevo['email']}** creado y "
                    f"asignado como **{estado_pwd_nuevo['rol']}**."
                )
                st.markdown("##### 🔑 Contraseña inicial (cópiala ahora)")
                st.code(estado_pwd_nuevo["pwd"], language=None)
                st.caption(
                    "Esta es la única vez que verás la contraseña. "
                    "Pásasela al usuario por un canal seguro (WhatsApp directo, "
                    "no grupo). El usuario debe cambiarla en su primer ingreso."
                )

                if st.button("Listo, ya la copié", type="primary"):
                    st.session_state.pop("pwd_nuevo_usuario", None)
                    st.rerun()


# ============================================================
# TAB 5: 🧩 Módulos por empresa (solo superadmin)
# ============================================================
with tab5:
    st.markdown("### 🧩 Módulos habilitados por empresa")

    if not es_superadmin():
        st.warning(
            "🔒 Esta sección está disponible solo para el **superadmin** del "
            "sistema. Si necesitas habilitar o deshabilitar módulos para "
            "alguna empresa, pídele al superadmin que lo haga."
        )
    else:
        st.caption(
            "Activa o desactiva módulos para cada empresa. Los módulos "
            "deshabilitados **no aparecen en el menú lateral** de los usuarios "
            "de esa empresa, así que la pantalla queda más limpia. La pestaña "
            "Configuración siempre está disponible."
        )

        # Selector de empresa: el superadmin puede elegir cualquiera
        from auth.empresas import empresas_del_usuario as _mis_empresas
        from db.supabase_client import get_supabase as _gsb

        @st.cache_data(ttl=60, show_spinner=False)
        def _todas_empresas():
            sb = _gsb()
            try:
                resp = sb.rpc("admin_listar_empresas").execute()
                return list(resp.data or [])
            except Exception:
                # Fallback: usar la tabla directa (puede fallar por RLS, pero
                # el superadmin la puede leer)
                try:
                    resp = sb.table("empresas").select("id, nit, razon_social, activa").execute()
                    return list(resp.data or [])
                except Exception as e:
                    st.error(f"Error listando empresas: {e}")
                    return []

        empresas_todas = _todas_empresas()
        if not empresas_todas:
            st.warning(
                "No se pudieron listar las empresas. Verifica que la RPC "
                "`admin_listar_empresas` exista o que tengas permisos."
            )
        else:
            opc = {
                f"{e['razon_social']} ({e.get('nit', '')})": e["id"]
                for e in empresas_todas
            }
            label_emp = st.selectbox(
                "Empresa",
                options=list(opc.keys()),
                key="sel_emp_modulos",
            )
            empresa_id_modulos = opc[label_emp]

            st.markdown("---")

            # Listar módulos del sistema con su estado actual para esta empresa
            modulos_actuales = mod_sys.modulos_de_empresa(empresa_id_modulos)

            if not modulos_actuales:
                st.warning(
                    "No se pudieron cargar los módulos. Verifica que el "
                    "script `setup_modulos.sql` se haya ejecutado en Supabase."
                )
            else:
                st.markdown(f"#### Módulos para **{label_emp}**")

                # Form con un checkbox por módulo
                with st.form(f"form_modulos_{empresa_id_modulos}"):
                    cambios = {}
                    for m in modulos_actuales:
                        emoji = m.get("emoji", "") or ""
                        nombre = m.get("nombre", m["codigo"])
                        descripcion = m.get("descripcion", "") or ""
                        habilitado_actual = bool(m.get("habilitado", False))

                        col_cb, col_desc = st.columns([2, 5])
                        with col_cb:
                            nuevo = st.checkbox(
                                f"{emoji} **{nombre}**",
                                value=habilitado_actual,
                                key=f"cb_mod_{empresa_id_modulos}_{m['codigo']}",
                            )
                        with col_desc:
                            st.caption(descripcion)

                        cambios[m["codigo"]] = nuevo

                    submit = st.form_submit_button(
                        "💾 Guardar cambios",
                        type="primary",
                    )

                    if submit:
                        # Construir el array para la RPC
                        payload = [
                            {"codigo": cod, "habilitado": val}
                            for cod, val in cambios.items()
                        ]
                        with st.spinner("Guardando..."):
                            res = mod_sys.actualizar_modulos_empresa(
                                empresa_id_modulos, payload,
                            )
                        if res["success"]:
                            n_activos = sum(1 for v in cambios.values() if v)
                            n_total = len(cambios)
                            st.success(
                                f"✅ Módulos actualizados para **{label_emp}**: "
                                f"{n_activos} de {n_total} habilitados."
                            )
                            st.rerun()
                        else:
                            st.error(f"❌ Error guardando: {res['error']}")

                # Resumen visual
                n_activos = sum(1 for m in modulos_actuales if m.get("habilitado"))
                st.caption(
                    f"📊 **{n_activos}** de **{len(modulos_actuales)}** módulos "
                    f"habilitados para esta empresa."
                )
