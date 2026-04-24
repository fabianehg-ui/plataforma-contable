-- ============================================================
-- MIGRACIÓN: Agregar rol superadmin + ajustar RLS
-- ============================================================
-- Ejecutar UNA SOLA VEZ en SQL Editor de Supabase.
-- Seguro de ejecutar: todos los cambios usan IF NOT EXISTS / DROP IF EXISTS.
-- ============================================================


-- ------------------------------------------------------------
-- 1. Actualizar el CHECK constraint de usuario_empresa para
--    aceptar el nuevo rol 'superadmin'
-- ------------------------------------------------------------
alter table public.usuario_empresa
    drop constraint if exists usuario_empresa_rol_check;

alter table public.usuario_empresa
    add constraint usuario_empresa_rol_check
    check (rol in ('superadmin', 'admin', 'operador', 'consulta'));


-- ------------------------------------------------------------
-- 2. Crear tabla 'superadmins' (lista de super-usuarios globales)
--    Es más limpio que usar 'rol=superadmin' en usuario_empresa
--    porque superadmin no pertenece a una empresa específica,
--    tiene acceso global.
-- ------------------------------------------------------------
create table if not exists public.superadmins (
    usuario_id uuid primary key references auth.users(id) on delete cascade,
    asignado_en timestamp with time zone default now(),
    notas text
);

comment on table public.superadmins is
    'Usuarios con permisos globales (ven y gestionan todo el sistema)';


-- ------------------------------------------------------------
-- 3. Función helper: ¿el usuario actual es superadmin?
-- ------------------------------------------------------------
create or replace function public.es_superadmin()
returns boolean
language sql
stable
security definer
as $$
    select exists (
        select 1 from public.superadmins
        where usuario_id = auth.uid()
    );
$$;

grant execute on function public.es_superadmin() to authenticated;


-- ------------------------------------------------------------
-- 4. Actualizar políticas RLS: superadmin ve todo
-- ------------------------------------------------------------

-- EMPRESAS: superadmin ve todas
drop policy if exists "empresas_select" on public.empresas;
create policy "empresas_select" on public.empresas
    for select using (
        public.es_superadmin()
        or id in (
            select empresa_id from public.usuario_empresa
            where usuario_id = auth.uid()
        )
    );

-- EMPRESAS: solo superadmin puede crear/editar/desactivar
drop policy if exists "empresas_insert" on public.empresas;
create policy "empresas_insert" on public.empresas
    for insert with check (public.es_superadmin());

drop policy if exists "empresas_update" on public.empresas;
create policy "empresas_update" on public.empresas
    for update using (public.es_superadmin());

drop policy if exists "empresas_delete" on public.empresas;
create policy "empresas_delete" on public.empresas
    for delete using (public.es_superadmin());


-- USUARIO_EMPRESA: superadmin ve todas las asignaciones
drop policy if exists "ue_select_propias" on public.usuario_empresa;
create policy "ue_select" on public.usuario_empresa
    for select using (
        public.es_superadmin()
        or usuario_id = auth.uid()
    );

-- USUARIO_EMPRESA: solo superadmin crea/edita/borra asignaciones
drop policy if exists "ue_insert" on public.usuario_empresa;
create policy "ue_insert" on public.usuario_empresa
    for insert with check (public.es_superadmin());

drop policy if exists "ue_update" on public.usuario_empresa;
create policy "ue_update" on public.usuario_empresa
    for update using (public.es_superadmin());

drop policy if exists "ue_delete" on public.usuario_empresa;
create policy "ue_delete" on public.usuario_empresa
    for delete using (public.es_superadmin());


-- SUPERADMINS: solo superadmins ven y gestionan esta tabla
alter table public.superadmins enable row level security;

drop policy if exists "sa_select" on public.superadmins;
create policy "sa_select" on public.superadmins
    for select using (public.es_superadmin());


-- ------------------------------------------------------------
-- 5. ⚠️ PASO CRÍTICO: marcarte a TI como superadmin
--    Reemplaza el email si es necesario
-- ------------------------------------------------------------
insert into public.superadmins (usuario_id, notas)
select id, 'Creador del sistema'
from auth.users
where email = 'fabianehg@gmail.com'
on conflict (usuario_id) do nothing;


-- ------------------------------------------------------------
-- 6. Función helper: listar todas las empresas del sistema
--    (útil para el panel admin, bypasa RLS)
-- ------------------------------------------------------------
create or replace function public.admin_listar_empresas()
returns table (
    id uuid,
    nit text,
    razon_social text,
    creada_en timestamp with time zone,
    activa boolean,
    cantidad_usuarios bigint
)
language sql
stable
security definer
as $$
    select
        e.id,
        e.nit,
        e.razon_social,
        e.creada_en,
        e.activa,
        (select count(*) from public.usuario_empresa ue where ue.empresa_id = e.id)
            as cantidad_usuarios
    from public.empresas e
    where public.es_superadmin()
    order by e.creada_en desc;
$$;

grant execute on function public.admin_listar_empresas() to authenticated;


-- ------------------------------------------------------------
-- 7. Función helper: listar todos los usuarios del sistema
--    (útil para el panel admin)
-- ------------------------------------------------------------
create or replace function public.admin_listar_usuarios()
returns table (
    id uuid,
    email text,
    creado_en timestamp with time zone,
    ultimo_login timestamp with time zone,
    es_superadmin boolean,
    cantidad_empresas bigint
)
language sql
stable
security definer
as $$
    select
        u.id,
        u.email::text,
        u.created_at,
        u.last_sign_in_at,
        exists(select 1 from public.superadmins sa where sa.usuario_id = u.id),
        (select count(*) from public.usuario_empresa ue where ue.usuario_id = u.id)
    from auth.users u
    where public.es_superadmin()
    order by u.created_at desc;
$$;

grant execute on function public.admin_listar_usuarios() to authenticated;


-- ------------------------------------------------------------
-- 8. Función helper: ver usuarios de una empresa específica
-- ------------------------------------------------------------
create or replace function public.admin_usuarios_de_empresa(p_empresa_id uuid)
returns table (
    usuario_id uuid,
    email text,
    rol text,
    asignado_en timestamp with time zone
)
language sql
stable
security definer
as $$
    select
        ue.usuario_id,
        u.email::text,
        ue.rol,
        ue.asignado_en
    from public.usuario_empresa ue
    join auth.users u on u.id = ue.usuario_id
    where ue.empresa_id = p_empresa_id
      and public.es_superadmin()
    order by ue.asignado_en desc;
$$;

grant execute on function public.admin_usuarios_de_empresa(uuid) to authenticated;


-- ============================================================
-- VERIFICACIÓN (ejecutar después, debe salir tu email)
-- ============================================================
-- select u.email, 'Eres superadmin' as status
-- from public.superadmins sa
-- join auth.users u on u.id = sa.usuario_id;
