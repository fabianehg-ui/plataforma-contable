-- ============================================================
-- Esquema inicial de la plataforma contable
-- Se ejecuta UNA SOLA VEZ en el SQL Editor de Supabase.
-- ============================================================
--
-- Supabase ya provee la tabla auth.users con los usuarios registrados.
-- Este script añade las tablas específicas del dominio de negocio.
-- Todas las tablas tienen Row Level Security (RLS) habilitado para que
-- un usuario solo vea los datos de empresas a las que pertenece.

-- ============================================================
-- Tabla: empresas
-- ============================================================
create table if not exists public.empresas (
    id uuid primary key default gen_random_uuid(),
    nit text not null,
    razon_social text not null,
    creada_por uuid references auth.users(id) on delete set null,
    creada_en timestamp with time zone default now(),
    activa boolean default true
);

comment on table public.empresas is 'Empresas sobre las que se hace contabilidad';


-- ============================================================
-- Tabla puente: usuario_empresa (permisos)
-- ============================================================
create table if not exists public.usuario_empresa (
    usuario_id uuid references auth.users(id) on delete cascade,
    empresa_id uuid references public.empresas(id) on delete cascade,
    rol text not null check (rol in ('admin', 'operador', 'consulta')),
    asignado_en timestamp with time zone default now(),
    primary key (usuario_id, empresa_id)
);

comment on table public.usuario_empresa is 'Qué usuarios tienen acceso a qué empresas y con qué rol';


-- ============================================================
-- Tabla: procesamientos (histórico de archivos procesados)
-- ============================================================
create table if not exists public.procesamientos (
    id uuid primary key default gen_random_uuid(),
    empresa_id uuid references public.empresas(id) on delete cascade,
    usuario_id uuid references auth.users(id) on delete set null,
    modulo text not null,
    fecha timestamp with time zone default now(),
    nombre_entrada text,
    nombre_salida text,
    archivo_entrada_path text,
    archivo_salida_path text,
    filas_generadas integer,
    estado text default 'ok' check (estado in ('ok', 'error')),
    notas text
);

create index if not exists idx_proc_empresa_fecha
    on public.procesamientos(empresa_id, fecha desc);

comment on table public.procesamientos is 'Histórico de archivos procesados por módulo';


-- ============================================================
-- Tabla: parametros_empresa
-- ============================================================
create table if not exists public.parametros_empresa (
    empresa_id uuid references public.empresas(id) on delete cascade,
    clave text not null,
    valor text,
    actualizado_en timestamp with time zone default now(),
    primary key (empresa_id, clave)
);

comment on table public.parametros_empresa is 'Parámetros simples por empresa (reemplaza el archivo parametros.xlsx)';


-- ============================================================
-- Row Level Security
-- ============================================================

alter table public.empresas enable row level security;
alter table public.usuario_empresa enable row level security;
alter table public.procesamientos enable row level security;
alter table public.parametros_empresa enable row level security;


-- Empresas: un usuario solo ve empresas a las que pertenece
create policy "empresas_select" on public.empresas
    for select using (
        id in (
            select empresa_id from public.usuario_empresa
            where usuario_id = auth.uid()
        )
    );

-- Usuario_empresa: cada usuario ve sus propias asignaciones
create policy "ue_select_propias" on public.usuario_empresa
    for select using (usuario_id = auth.uid());

-- Procesamientos: solo los de empresas a las que el usuario pertenece
create policy "proc_select" on public.procesamientos
    for select using (
        empresa_id in (
            select empresa_id from public.usuario_empresa
            where usuario_id = auth.uid()
        )
    );

create policy "proc_insert" on public.procesamientos
    for insert with check (
        empresa_id in (
            select empresa_id from public.usuario_empresa
            where usuario_id = auth.uid()
              and rol in ('admin', 'operador')
        )
    );

-- Parametros: lectura para cualquier miembro, escritura solo admin
create policy "param_select" on public.parametros_empresa
    for select using (
        empresa_id in (
            select empresa_id from public.usuario_empresa
            where usuario_id = auth.uid()
        )
    );

create policy "param_upsert" on public.parametros_empresa
    for all using (
        empresa_id in (
            select empresa_id from public.usuario_empresa
            where usuario_id = auth.uid() and rol = 'admin'
        )
    );


-- ============================================================
-- Bucket de Storage para archivos
-- ============================================================
-- Crear desde el panel Storage o con el siguiente SQL:
-- (Supabase maneja storage a través de su API; esto es documentación)
--
-- Buckets recomendados:
--   - empresas-config  : cuentas.xlsx, mapeos.xlsx (privado)
--   - procesamientos   : archivos entrada/salida del histórico (privado)
--
-- Crear desde la UI: Storage > New bucket > name: "empresas-config", public: OFF
-- Luego ir a Policies y pegar estas:

/*
-- Policy para leer archivos de empresas a las que pertenece el usuario
create policy "Storage config select" on storage.objects
    for select using (
        bucket_id = 'empresas-config'
        and (storage.foldername(name))[1] in (
            select empresa_id::text from public.usuario_empresa
            where usuario_id = auth.uid()
        )
    );

-- Policy para que admins suban archivos
create policy "Storage config insert" on storage.objects
    for insert with check (
        bucket_id = 'empresas-config'
        and (storage.foldername(name))[1] in (
            select empresa_id::text from public.usuario_empresa
            where usuario_id = auth.uid() and rol = 'admin'
        )
    );
*/


-- ============================================================
-- Función helper para crear empresa + asignar creador como admin
-- ============================================================
create or replace function public.crear_empresa_con_admin(
    p_nit text,
    p_razon_social text
) returns uuid
language plpgsql
security definer
as $$
declare
    nueva_id uuid;
begin
    insert into public.empresas (nit, razon_social, creada_por)
    values (p_nit, p_razon_social, auth.uid())
    returning id into nueva_id;

    insert into public.usuario_empresa (usuario_id, empresa_id, rol)
    values (auth.uid(), nueva_id, 'admin');

    return nueva_id;
end;
$$;

-- Permitir a usuarios autenticados llamar esta función
grant execute on function public.crear_empresa_con_admin(text, text) to authenticated;


-- ============================================================
-- Seed de ejemplo (opcional) - COMENTADO
-- ============================================================
-- Para probar rápidamente, descomenta y ejecuta este bloque DESPUÉS de
-- haber creado tu primer usuario en Supabase Auth. Reemplaza el email
-- con el tuyo real.
--
-- do $$
-- declare
--     mi_id uuid;
-- begin
--     select id into mi_id from auth.users where email = 'TU-EMAIL@example.com';
--     if mi_id is not null then
--         perform public.crear_empresa_con_admin('901.630.218-1', 'OASIS URBANOS S.A.S');
--         perform public.crear_empresa_con_admin('900.000.000-0', 'GRUPO DE LOLITA');
--     end if;
-- end $$;
