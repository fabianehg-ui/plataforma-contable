-- ================================================================
-- Migración 001: Módulo Información Exógena DIAN
-- ================================================================
-- Se ejecuta UNA SOLA VEZ en el SQL Editor de Supabase, después del
-- schema.sql base. Crea todas las tablas del módulo de exógena.
--
-- IMPORTANTE: empresa_id es UUID porque referencia public.empresas(id),
-- consistente con el schema base de la plataforma.
-- ================================================================

-- ================================================================
-- 1. CATÁLOGOS DIAN (compartidos entre todas las empresas)
-- ================================================================

create table if not exists public.exogena_cat_formatos (
    codigo varchar(10) primary key,
    nombre text not null,
    version varchar(10),
    activo boolean default true,
    año_gravable integer not null
);

create table if not exists public.exogena_cat_tipos_documento (
    codigo integer primary key,
    descripcion text not null,
    activo boolean default true
);

create table if not exists public.exogena_cat_conceptos (
    id bigserial primary key,
    codigo integer not null,
    descripcion text not null,
    año_gravable integer not null,
    activo boolean default true,
    unique (codigo, descripcion, año_gravable)
);
create index if not exists idx_exogena_cat_conceptos_codigo
    on public.exogena_cat_conceptos(codigo);

create table if not exists public.exogena_cat_departamentos (
    codigo varchar(2) primary key,
    nombre text not null
);

create table if not exists public.exogena_cat_municipios (
    id bigserial primary key,
    codigo_dpto varchar(2) not null references public.exogena_cat_departamentos(codigo),
    codigo_mcp varchar(3) not null,
    nombre text not null,
    codigo_combo integer,
    unique (codigo_dpto, codigo_mcp)
);

create table if not exists public.exogena_cat_paises (
    codigo varchar(3) primary key,
    nombre text not null
);

create table if not exists public.exogena_cat_ciiu (
    codigo varchar(4) primary key,
    descripcion text not null,
    activo boolean default true
);

create table if not exists public.exogena_cat_plazos (
    id bigserial primary key,
    año_gravable integer not null,
    tipo_contribuyente varchar(50) not null,
    digitos_nit varchar(5) not null,
    fecha_limite date not null,
    unique (año_gravable, tipo_contribuyente, digitos_nit)
);

-- ================================================================
-- 2. CAPA 1: PUC GENÉRICO (reglas base compartidas)
-- ================================================================

create table if not exists public.exogena_puc_generico (
    id bigserial primary key,
    codigo_cuenta varchar(20) not null,
    nombre_cuenta text,
    formato_dian varchar(10) not null,
    concepto_dian integer,
    naturaleza varchar(10),
    nota text,
    activo boolean default true,
    año_gravable integer not null,
    -- Una cuenta puede tener múltiples reglas en el mismo formato si los conceptos
    -- son distintos (ej. cuenta 41 → formato 1007 → conceptos 4001, 4014, 4015, 4016).
    -- Por eso el UNIQUE incluye concepto_dian.
    unique (codigo_cuenta, formato_dian, concepto_dian, año_gravable)
);
create index if not exists idx_puc_gen_codigo on public.exogena_puc_generico(codigo_cuenta);
create index if not exists idx_puc_gen_formato on public.exogena_puc_generico(formato_dian);

-- ================================================================
-- 3. CAPA 2: MAPEO NATIVO POR EMPRESA (rangos de cuentas)
-- ================================================================

create table if not exists public.exogena_mapeo_empresa (
    id bigserial primary key,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    año_gravable integer not null,
    formato_dian varchar(10) not null,
    concepto_dian integer not null,
    cuenta_inicial varchar(20) not null,
    cuenta_final varchar(20) not null,
    descripcion_concepto text,
    tipo_contrato varchar(20),
    valor_aplicable integer default 1,
    nota text,
    activo boolean default true,
    fila_origen integer,
    creado_en timestamp with time zone default now()
);
create index if not exists idx_mapeo_emp_lookup
    on public.exogena_mapeo_empresa(empresa_id, año_gravable, activo);

comment on column public.exogena_mapeo_empresa.cuenta_inicial is
'Cuenta inicial del rango. Comparación con padding de 0s a 10 dígitos.';
comment on column public.exogena_mapeo_empresa.cuenta_final is
'Cuenta final del rango. Comparación con padding de 9s a 10 dígitos.';

-- ================================================================
-- 4. CAPA 3: OVERRIDES MANUALES (por cuenta+NIT)
-- ================================================================

create table if not exists public.exogena_mapeo_manual (
    id bigserial primary key,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    año_gravable integer not null,
    codigo_cuenta varchar(20) not null,
    nit varchar(20),
    formato_dian varchar(10) not null,
    concepto_dian integer,
    nota text,
    creado_por uuid references auth.users(id) on delete set null,
    creado_en timestamp with time zone default now()
);
create index if not exists idx_mapeo_man_lookup
    on public.exogena_mapeo_manual(empresa_id, año_gravable, codigo_cuenta, nit);

-- ================================================================
-- 5. PERÍODOS / EJERCICIOS (uno por empresa-año)
-- ================================================================

create table if not exists public.exogena_periodos (
    id bigserial primary key,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    año_gravable integer not null,
    estado varchar(30) default 'borrador',
    fecha_corte date,
    fecha_limite date,
    es_gran_contribuyente boolean default false,
    notas text,
    creado_en timestamp with time zone default now(),
    actualizado_en timestamp with time zone default now(),
    unique (empresa_id, año_gravable)
);
create index if not exists idx_periodos_empresa on public.exogena_periodos(empresa_id);

-- ================================================================
-- 6. BALANCE IMPORTADO
-- ================================================================

create table if not exists public.exogena_balance (
    id bigserial primary key,
    periodo_id bigint not null references public.exogena_periodos(id) on delete cascade,
    codigo_cuenta varchar(20) not null,
    nombre_cuenta text,
    nit varchar(20),
    nombre_tercero text,
    saldo_anterior numeric(18,2) default 0,
    debitos numeric(18,2) default 0,
    creditos numeric(18,2) default 0,
    saldo_final numeric(18,2) default 0,
    es_totalizador boolean default false,
    fila_origen integer,
    creado_en timestamp with time zone default now()
);
create index if not exists idx_balance_periodo on public.exogena_balance(periodo_id);
create index if not exists idx_balance_cuenta on public.exogena_balance(codigo_cuenta);
create index if not exists idx_balance_nit on public.exogena_balance(nit);

-- ================================================================
-- 7. MAESTRO DE TERCEROS POR EMPRESA
-- ================================================================

create table if not exists public.exogena_terceros (
    id bigserial primary key,
    empresa_id uuid not null references public.empresas(id) on delete cascade,
    nit varchar(20) not null,
    dv integer,
    tipo_documento integer default 31,
    tipo_persona varchar(15),
    razon_social text,
    primer_apellido text,
    segundo_apellido text,
    primer_nombre text,
    otros_nombres text,
    direccion text,
    codigo_dpto varchar(2),
    codigo_municipio varchar(3),
    codigo_pais varchar(3) default '169',
    email text,
    actividad_ciiu varchar(4),
    activo boolean default true,
    -- Trazabilidad de clasificación automática
    nit_original varchar(20),
    regla_clasificacion text,
    requiere_revision boolean default false,
    sugerencias text,
    -- Trazabilidad de enriquecimiento externo
    enriquecido_desde varchar(30),
    fecha_enriquecimiento timestamp with time zone,
    creado_en timestamp with time zone default now(),
    actualizado_en timestamp with time zone default now(),
    unique (empresa_id, nit)
);
create index if not exists idx_terceros_emp_nit on public.exogena_terceros(empresa_id, nit);
create index if not exists idx_terceros_revisar
    on public.exogena_terceros(empresa_id, requiere_revision)
    where requiere_revision = true;

-- ================================================================
-- 8. MOVIMIENTOS CLASIFICADOS (output del motor)
-- ================================================================

create table if not exists public.exogena_movimientos_clasificados (
    id bigserial primary key,
    periodo_id bigint not null references public.exogena_periodos(id) on delete cascade,
    balance_id bigint references public.exogena_balance(id) on delete cascade,
    codigo_cuenta varchar(20) not null,
    nit varchar(20),
    formato_dian varchar(10) not null,
    concepto_dian integer,
    valor numeric(18,2) not null,
    base_aplicable varchar(20),
    capa_resolucion varchar(20),
    regla_id bigint,
    requiere_revision boolean default false,
    decision_usuario varchar(30),
    nota text,
    creado_en timestamp with time zone default now()
);
create index if not exists idx_clasif_periodo_formato
    on public.exogena_movimientos_clasificados(periodo_id, formato_dian);
create index if not exists idx_clasif_revisar
    on public.exogena_movimientos_clasificados(periodo_id, requiere_revision);

-- ================================================================
-- 9. FORMATOS GENERADOS (snapshots)
-- ================================================================

create table if not exists public.exogena_formatos_generados (
    id bigserial primary key,
    periodo_id bigint not null references public.exogena_periodos(id) on delete cascade,
    formato_dian varchar(10) not null,
    cantidad_registros integer default 0,
    valor_total numeric(18,2) default 0,
    estado varchar(20) default 'borrador',
    archivo_xml_path text,
    archivo_excel_path text,
    hash_md5 varchar(32),
    fecha_generacion timestamp with time zone default now(),
    fecha_envio_dian timestamp with time zone,
    notas text,
    unique (periodo_id, formato_dian)
);

-- ================================================================
-- 10. CACHÉ DE ENRIQUECIMIENTO (compartido entre empresas)
-- ================================================================
-- No tiene empresa_id porque los datos del RUT son de identidad pública.
-- Cualquier empresa se beneficia de una consulta hecha por otra del mismo NIT.

create table if not exists public.exogena_cache_enriquecimiento (
    id bigserial primary key,
    nit varchar(20) not null unique,
    fuente_original varchar(30) not null,
    fecha_consulta timestamp with time zone not null default now(),
    tipo_persona varchar(15),
    estado varchar(30),
    razon_social text,
    primer_nombre text,
    segundo_nombre text,
    primer_apellido text,
    segundo_apellido text,
    direccion text,
    codigo_dpto varchar(2),
    codigo_municipio varchar(3),
    email text,
    telefono varchar(50),
    actividad_ciiu varchar(4),
    representante_legal text,
    payload_crudo jsonb,
    advertencias jsonb,
    consultas_count integer default 1,
    last_hit_at timestamp with time zone default now(),
    creado_en timestamp with time zone default now(),
    actualizado_en timestamp with time zone default now()
);
create index if not exists idx_cache_enriq_fecha
    on public.exogena_cache_enriquecimiento(fecha_consulta desc);

comment on table public.exogena_cache_enriquecimiento is
'Caché de respuestas de RUES y otras fuentes para evitar consultas repetidas.';

-- ================================================================
-- 11. LOG DE CONSULTAS A APIS EXTERNAS (auditoría)
-- ================================================================

create table if not exists public.exogena_log_apis_externas (
    id bigserial primary key,
    fuente varchar(30) not null,
    nit varchar(20) not null,
    exito boolean not null,
    tiempo_ms integer,
    costo_estimado_usd numeric(8, 4),
    error_mensaje text,
    empresa_id uuid references public.empresas(id) on delete set null,
    usuario_id uuid references auth.users(id) on delete set null,
    creado_en timestamp with time zone default now()
);
create index if not exists idx_log_apis_fecha
    on public.exogena_log_apis_externas(creado_en desc);

-- ================================================================
-- ROW LEVEL SECURITY
-- ================================================================

-- Catálogos: lectura para todo usuario autenticado, sin restricción por empresa
alter table public.exogena_cat_formatos enable row level security;
alter table public.exogena_cat_tipos_documento enable row level security;
alter table public.exogena_cat_conceptos enable row level security;
alter table public.exogena_cat_departamentos enable row level security;
alter table public.exogena_cat_municipios enable row level security;
alter table public.exogena_cat_paises enable row level security;
alter table public.exogena_cat_ciiu enable row level security;
alter table public.exogena_cat_plazos enable row level security;
alter table public.exogena_puc_generico enable row level security;
alter table public.exogena_cache_enriquecimiento enable row level security;

create policy "exogena_cat_formatos_select" on public.exogena_cat_formatos for select to authenticated using (true);
create policy "exogena_cat_tipos_documento_select" on public.exogena_cat_tipos_documento for select to authenticated using (true);
create policy "exogena_cat_conceptos_select" on public.exogena_cat_conceptos for select to authenticated using (true);
create policy "exogena_cat_departamentos_select" on public.exogena_cat_departamentos for select to authenticated using (true);
create policy "exogena_cat_municipios_select" on public.exogena_cat_municipios for select to authenticated using (true);
create policy "exogena_cat_paises_select" on public.exogena_cat_paises for select to authenticated using (true);
create policy "exogena_cat_ciiu_select" on public.exogena_cat_ciiu for select to authenticated using (true);
create policy "exogena_cat_plazos_select" on public.exogena_cat_plazos for select to authenticated using (true);
create policy "exogena_puc_generico_select" on public.exogena_puc_generico for select to authenticated using (true);
create policy "exogena_cache_select" on public.exogena_cache_enriquecimiento for select to authenticated using (true);
create policy "exogena_cache_insert" on public.exogena_cache_enriquecimiento for insert to authenticated with check (true);
create policy "exogena_cache_update" on public.exogena_cache_enriquecimiento for update to authenticated using (true);

-- Tablas por empresa: solo miembros de la empresa
alter table public.exogena_mapeo_empresa enable row level security;
alter table public.exogena_mapeo_manual enable row level security;
alter table public.exogena_periodos enable row level security;
alter table public.exogena_balance enable row level security;
alter table public.exogena_terceros enable row level security;
alter table public.exogena_movimientos_clasificados enable row level security;
alter table public.exogena_formatos_generados enable row level security;
alter table public.exogena_log_apis_externas enable row level security;

-- Helper macro: política de SELECT/ALL para tablas con empresa_id directa
create policy "mapeo_emp_all" on public.exogena_mapeo_empresa for all using (
    empresa_id in (select empresa_id from public.usuario_empresa where usuario_id = auth.uid())
);
create policy "mapeo_man_all" on public.exogena_mapeo_manual for all using (
    empresa_id in (select empresa_id from public.usuario_empresa where usuario_id = auth.uid())
);
create policy "periodos_all" on public.exogena_periodos for all using (
    empresa_id in (select empresa_id from public.usuario_empresa where usuario_id = auth.uid())
);
create policy "terceros_all" on public.exogena_terceros for all using (
    empresa_id in (select empresa_id from public.usuario_empresa where usuario_id = auth.uid())
);
create policy "log_apis_all" on public.exogena_log_apis_externas for all using (
    empresa_id is null or empresa_id in (
        select empresa_id from public.usuario_empresa where usuario_id = auth.uid()
    )
);

-- Tablas con periodo_id (acceso a través del periodo)
create policy "balance_all" on public.exogena_balance for all using (
    periodo_id in (
        select id from public.exogena_periodos where empresa_id in (
            select empresa_id from public.usuario_empresa where usuario_id = auth.uid()
        )
    )
);
create policy "movs_clasif_all" on public.exogena_movimientos_clasificados for all using (
    periodo_id in (
        select id from public.exogena_periodos where empresa_id in (
            select empresa_id from public.usuario_empresa where usuario_id = auth.uid()
        )
    )
);
create policy "formatos_gen_all" on public.exogena_formatos_generados for all using (
    periodo_id in (
        select id from public.exogena_periodos where empresa_id in (
            select empresa_id from public.usuario_empresa where usuario_id = auth.uid()
        )
    )
);
