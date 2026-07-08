-- 013_f350_dian_credenciales.sql
-- Credenciales de acceso a Muisca (DIAN) por empresa, guardadas CIFRADAS.
-- El texto plano nunca se guarda: 'credencial_cifrada' es un token Fernet
-- que solo se puede descifrar con F350_FERNET_KEY (variable de entorno).

create table if not exists public.f350_dian_credenciales (
    id                uuid primary key default gen_random_uuid(),
    empresa_id        uuid not null references public.empresas(id) on delete cascade,
    tipo_doc          text not null,                 -- CC, CE, etc. (del representante/usuario DIAN)
    num_doc_enmasc    text,                           -- solo para mostrar (ej. ****4113), no sensible
    credencial_cifrada text not null,                 -- Fernet(json: tipo_doc, num_doc, password)
    actualizado_por   uuid,
    actualizado_en    timestamptz not null default now(),
    unique (empresa_id)
);

alter table public.f350_dian_credenciales enable row level security;

-- Ajusta esta policy a tu modelo (aquí: contador asignado a la empresa).
drop policy if exists f350_cred_rw on public.f350_dian_credenciales;
create policy f350_cred_rw on public.f350_dian_credenciales
    for all
    using (
        exists (
            select 1 from public.empresa_contadores ec
            where ec.empresa_id = f350_dian_credenciales.empresa_id
              and ec.user_id = auth.uid()
        )
    )
    with check (
        exists (
            select 1 from public.empresa_contadores ec
            where ec.empresa_id = f350_dian_credenciales.empresa_id
              and ec.user_id = auth.uid()
        )
    );
