-- =====================================================================
-- 010_restaurar_grants_funciones.sql
--
-- Restaura permisos EXECUTE sobre las funciones de la plataforma para
-- el rol "authenticated". Útil si Supabase (Security Advisor u otro
-- mecanismo) revoca los permisos por defecto.
--
-- Contexto:
-- Todas estas funciones son SECURITY DEFINER y tienen verificación
-- interna mediante public.es_superadmin() o public.es_admin_de_empresa(),
-- por lo que dar GRANT a "authenticated" no expone datos a usuarios
-- no autorizados; la función se rechaza sola si el llamador no cumple
-- el rol requerido.
--
-- Cómo aplicar:
--   1. Abrir Supabase → SQL Editor → New query.
--   2. Pegar este archivo completo.
--   3. Ejecutar (Run).
--   4. Cerrar sesión y volver a iniciar sesión en la app para refrescar
--      el token de autenticación.
--
-- Última actualización: 2026-05-15
-- =====================================================================

-- Funciones del panel de súper administrador
GRANT EXECUTE ON FUNCTION public.admin_listar_empresas TO authenticated;
GRANT EXECUTE ON FUNCTION public.admin_listar_usuarios TO authenticated;
GRANT EXECUTE ON FUNCTION public.admin_asignar_usuario_empresa TO authenticated;
GRANT EXECUTE ON FUNCTION public.admin_buscar_usuario_por_email TO authenticated;
GRANT EXECUTE ON FUNCTION public.admin_remover_usuario_empresa TO authenticated;
GRANT EXECUTE ON FUNCTION public.admin_usuarios_de_empresa TO authenticated;
GRANT EXECUTE ON FUNCTION public.admin_usuarios_de_empresa_v2 TO authenticated;

-- Funciones de gestión de empresas y módulos
GRANT EXECUTE ON FUNCTION public.actualizar_modulos_empresa TO authenticated;
GRANT EXECUTE ON FUNCTION public.crear_empresa_con_admin TO authenticated;
GRANT EXECUTE ON FUNCTION public.empresa_tiene_modulo TO authenticated;
GRANT EXECUTE ON FUNCTION public.es_admin_de_alguna_empresa TO authenticated;
GRANT EXECUTE ON FUNCTION public.es_admin_de_empresa TO authenticated;
GRANT EXECUTE ON FUNCTION public.listar_modulos_sistema TO authenticated;
GRANT EXECUTE ON FUNCTION public.mis_empresas_como_admin TO authenticated;
GRANT EXECUTE ON FUNCTION public.modulos_de_empresa TO authenticated;

-- Funciones de módulos específicos
GRANT EXECUTE ON FUNCTION public.obtener_liquidacion_renta_actual TO authenticated;

-- =====================================================================
-- VERIFICACIÓN
-- Ejecutar al final para confirmar que todas las funciones quedaron
-- con permiso para "authenticated":
-- =====================================================================
-- SELECT
--     routine_name AS funcion,
--     string_agg(DISTINCT grantee, ', ' ORDER BY grantee) AS roles
-- FROM information_schema.routine_privileges
-- WHERE routine_schema = 'public'
--   AND privilege_type = 'EXECUTE'
-- GROUP BY routine_name
-- ORDER BY routine_name;
