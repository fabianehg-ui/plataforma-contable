-- =====================================================================
-- 011_modulo_retencion_fuente_f350.sql
--
-- Crea las tablas necesarias para el módulo de Retención en la Fuente
-- (Formulario 350) dentro de la plataforma multiempresa.
--
-- Diseño:
--   - Cada empresa-cliente (public.empresas) puede tener sus propias
--     declaraciones del F350.
--   - La habilitación del módulo se hace mediante la tabla existente
--     modulos_empresa (que maneja qué empresas tienen acceso a qué
--     módulos).
--   - Catálogos compartidos (CIIU, UVT) son globales — los ven todas
--     las empresas.
--   - Datos sensibles (terceros, declaraciones, movimientos) son por
--     empresa y protegidos con RLS.
--
-- Aplica desde Supabase → SQL Editor → New query → pegar todo → Run.
--
-- Fecha: 2026-05-15
-- =====================================================================


-- =====================================================================
-- 1. CATÁLOGOS COMPARTIDOS (globales, no por empresa)
-- =====================================================================

-- CIIU con tarifas de autorretención por vigencia normativa
-- Permite manejar varios decretos a la vez (Dec. 0261/2023, 0242/2024,
-- 0572/2025) eligiendo según fecha de la declaración.
CREATE TABLE IF NOT EXISTS public.f350_catalogo_ciiu (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo               text NOT NULL,
    actividad_economica  text NOT NULL,
    seccion_ciiu         text,
    tarifa_autorretencion numeric(7,4),         -- ej: 0.0110 = 1.10%
    vigencia_desde       date NOT NULL,
    vigencia_hasta       date,                  -- NULL = vigente hoy
    normativa            text,                  -- ej: "Dec. 0261/2023"
    creado_en            timestamp with time zone DEFAULT now(),
    UNIQUE (codigo, vigencia_desde)
);

CREATE INDEX IF NOT EXISTS idx_f350_ciiu_codigo
    ON public.f350_catalogo_ciiu (codigo);
CREATE INDEX IF NOT EXISTS idx_f350_ciiu_vigencia
    ON public.f350_catalogo_ciiu (vigencia_desde, vigencia_hasta);


-- UVT por año
CREATE TABLE IF NOT EXISTS public.f350_uvt_historico (
    anio              integer PRIMARY KEY,
    valor_uvt_pesos   integer NOT NULL,
    resolucion_dian   text,
    creado_en         timestamp with time zone DEFAULT now()
);

-- Datos UVT conocidos
INSERT INTO public.f350_uvt_historico (anio, valor_uvt_pesos, resolucion_dian) VALUES
    (2024, 47065, 'Res. DIAN 2023'),
    (2025, 49799, 'Res. DIAN 2024'),
    (2026, 52374, 'Res. DIAN 2025')
ON CONFLICT (anio) DO NOTHING;


-- =====================================================================
-- 2. TABLAS POR EMPRESA (multiempresa con empresa_id)
-- =====================================================================

-- Terceros que aparecen en las declaraciones de cada empresa
-- (NITs de proveedores, empleados, etc.).
CREATE TABLE IF NOT EXISTS public.f350_terceros (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id          uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    nit                 text NOT NULL,
    nombre_razon_social text NOT NULL,
    tipo_inferido       text,                   -- 'Persona Natural' | 'Persona Jurídica'
    es_extranjero       boolean DEFAULT false,
    es_residente_fiscal text,                   -- 'Sí' | 'No' | 'Desconocido'
    pais_origen         text,
    declarante_renta    text,
    regimen_iva         text,
    notas               text,
    creado_en           timestamp with time zone DEFAULT now(),
    actualizado_en      timestamp with time zone DEFAULT now(),
    UNIQUE (empresa_id, nit)
);

CREATE INDEX IF NOT EXISTS idx_f350_terceros_empresa
    ON public.f350_terceros (empresa_id);
CREATE INDEX IF NOT EXISTS idx_f350_terceros_nit
    ON public.f350_terceros (empresa_id, nit);


-- Configuración F350 por empresa (autorretención, exoneración, etc.)
-- Una sola fila por empresa que use el módulo.
CREATE TABLE IF NOT EXISTS public.f350_empresa_config (
    empresa_id              uuid PRIMARY KEY REFERENCES public.empresas(id) ON DELETE CASCADE,
    ciiu_principal          text,
    es_autorretenedor       boolean DEFAULT false,
    tarifa_autorretencion_manual numeric(7,4),   -- NULL = usar la del CIIU
    exonerado_art_114_1     boolean DEFAULT false,
    representante_legal     text,
    email_contacto          text,
    notas                   text,
    creado_en               timestamp with time zone DEFAULT now(),
    actualizado_en          timestamp with time zone DEFAULT now()
);


-- Historial de cambios de CIIU de la empresa (para auditoría)
CREATE TABLE IF NOT EXISTS public.f350_historial_ciiu (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id              uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    ciiu_anterior           text,
    ciiu_nuevo              text NOT NULL,
    fecha_vigencia_desde    date NOT NULL,
    motivo_cambio           text,
    numero_radicado_pqr     text,
    creado_por              uuid REFERENCES auth.users(id),
    creado_en               timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_f350_historial_ciiu_empresa
    ON public.f350_historial_ciiu (empresa_id, fecha_vigencia_desde DESC);


-- Declaraciones mensuales del F350 por empresa
CREATE TABLE IF NOT EXISTS public.f350_declaraciones (
    id                         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id                 uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    anio                       integer NOT NULL,
    mes                        integer NOT NULL CHECK (mes BETWEEN 1 AND 12),
    estado                     text DEFAULT 'Borrador' CHECK (estado IN ('Borrador', 'Revisada', 'Presentada')),
    base_autorretencion        numeric(18,2) DEFAULT 0,
    valor_autorretencion       numeric(18,2) DEFAULT 0,
    total_retenciones_renta    numeric(18,2) DEFAULT 0,
    total_retenciones_iva      numeric(18,2) DEFAULT 0,
    total_declaracion          numeric(18,2) DEFAULT 0,
    ciiu_aplicado              text,
    tarifa_aplicada            numeric(7,4),
    normativa_aplicada         text,
    fecha_presentacion         timestamp with time zone,
    notas                      text,
    creado_por                 uuid REFERENCES auth.users(id),
    creado_en                  timestamp with time zone DEFAULT now(),
    actualizado_en             timestamp with time zone DEFAULT now(),
    UNIQUE (empresa_id, anio, mes)
);

CREATE INDEX IF NOT EXISTS idx_f350_decl_empresa
    ON public.f350_declaraciones (empresa_id, anio DESC, mes DESC);
CREATE INDEX IF NOT EXISTS idx_f350_decl_estado
    ON public.f350_declaraciones (empresa_id, estado);


-- Movimientos individuales de cada declaración
-- (un movimiento = una línea del auxiliar de retefuente)
CREATE TABLE IF NOT EXISTS public.f350_movimientos_declaracion (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    declaracion_id      uuid NOT NULL REFERENCES public.f350_declaraciones(id) ON DELETE CASCADE,
    cuenta_puc          text NOT NULL,
    nit_tercero         text NOT NULL,
    nombre_tercero      text,
    tipo_inferido       text,
    es_extranjero       boolean DEFAULT false,
    base                numeric(18,2) NOT NULL,
    tarifa              numeric(7,4) NOT NULL,
    retencion           numeric(18,2) NOT NULL,
    casilla_destino     integer,
    concepto_asignado   text,
    confianza_clasif    text CHECK (confianza_clasif IN ('alta', 'media', 'baja')),
    regla_clasif        text,
    estado              text DEFAULT 'ok' CHECK (estado IN ('ok', 'revisar', 'excluido')),
    notas               text,
    creado_en           timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_f350_mov_declaracion
    ON public.f350_movimientos_declaracion (declaracion_id);
CREATE INDEX IF NOT EXISTS idx_f350_mov_estado
    ON public.f350_movimientos_declaracion (declaracion_id, estado);


-- Subcuentas usadas para el cálculo de la autorretención
-- (típicamente las subcuentas de la cuenta 4 — ingresos)
CREATE TABLE IF NOT EXISTS public.f350_subcuentas_autorretencion (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    declaracion_id      uuid NOT NULL REFERENCES public.f350_declaraciones(id) ON DELETE CASCADE,
    codigo_subcuenta    text NOT NULL,
    nombre_subcuenta    text,
    creditos            numeric(18,2) DEFAULT 0,
    debitos             numeric(18,2) DEFAULT 0,
    incluida            boolean DEFAULT true,
    creado_en           timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_f350_subcuentas_declaracion
    ON public.f350_subcuentas_autorretencion (declaracion_id);


-- =====================================================================
-- 3. SEGURIDAD: RLS — Row Level Security
-- =====================================================================
-- Cada tabla con empresa_id solo se puede ver/modificar si:
--   a) El usuario es súper admin (es_superadmin())
--   b) El usuario está vinculado a esa empresa vía usuario_empresa
-- =====================================================================

ALTER TABLE public.f350_terceros                     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.f350_empresa_config               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.f350_historial_ciiu               ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.f350_declaraciones                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.f350_movimientos_declaracion      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.f350_subcuentas_autorretencion    ENABLE ROW LEVEL SECURITY;

-- Catálogos compartidos: lectura para todos los autenticados, escritura
-- solo súper admin.
ALTER TABLE public.f350_catalogo_ciiu                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.f350_uvt_historico                ENABLE ROW LEVEL SECURITY;


-- --- Políticas para catálogos compartidos ---
DROP POLICY IF EXISTS "f350_ciiu_read_all" ON public.f350_catalogo_ciiu;
CREATE POLICY "f350_ciiu_read_all"
    ON public.f350_catalogo_ciiu FOR SELECT
    USING (true);  -- lectura libre para autenticados

DROP POLICY IF EXISTS "f350_ciiu_write_superadmin" ON public.f350_catalogo_ciiu;
CREATE POLICY "f350_ciiu_write_superadmin"
    ON public.f350_catalogo_ciiu FOR ALL
    USING (public.es_superadmin())
    WITH CHECK (public.es_superadmin());

DROP POLICY IF EXISTS "f350_uvt_read_all" ON public.f350_uvt_historico;
CREATE POLICY "f350_uvt_read_all"
    ON public.f350_uvt_historico FOR SELECT
    USING (true);

DROP POLICY IF EXISTS "f350_uvt_write_superadmin" ON public.f350_uvt_historico;
CREATE POLICY "f350_uvt_write_superadmin"
    ON public.f350_uvt_historico FOR ALL
    USING (public.es_superadmin())
    WITH CHECK (public.es_superadmin());


-- --- Políticas para tablas por empresa ---
-- Patrón: acceso si el usuario es admin de esa empresa O súper admin.

DROP POLICY IF EXISTS "f350_terceros_acceso" ON public.f350_terceros;
CREATE POLICY "f350_terceros_acceso"
    ON public.f350_terceros FOR ALL
    USING (
        public.es_superadmin()
        OR public.es_admin_de_empresa(empresa_id)
    )
    WITH CHECK (
        public.es_superadmin()
        OR public.es_admin_de_empresa(empresa_id)
    );

DROP POLICY IF EXISTS "f350_empresa_config_acceso" ON public.f350_empresa_config;
CREATE POLICY "f350_empresa_config_acceso"
    ON public.f350_empresa_config FOR ALL
    USING (
        public.es_superadmin()
        OR public.es_admin_de_empresa(empresa_id)
    )
    WITH CHECK (
        public.es_superadmin()
        OR public.es_admin_de_empresa(empresa_id)
    );

DROP POLICY IF EXISTS "f350_historial_ciiu_acceso" ON public.f350_historial_ciiu;
CREATE POLICY "f350_historial_ciiu_acceso"
    ON public.f350_historial_ciiu FOR ALL
    USING (
        public.es_superadmin()
        OR public.es_admin_de_empresa(empresa_id)
    )
    WITH CHECK (
        public.es_superadmin()
        OR public.es_admin_de_empresa(empresa_id)
    );

DROP POLICY IF EXISTS "f350_declaraciones_acceso" ON public.f350_declaraciones;
CREATE POLICY "f350_declaraciones_acceso"
    ON public.f350_declaraciones FOR ALL
    USING (
        public.es_superadmin()
        OR public.es_admin_de_empresa(empresa_id)
    )
    WITH CHECK (
        public.es_superadmin()
        OR public.es_admin_de_empresa(empresa_id)
    );

-- Movimientos y subcuentas: protegidos via la declaración a la que
-- pertenecen.
DROP POLICY IF EXISTS "f350_movimientos_acceso" ON public.f350_movimientos_declaracion;
CREATE POLICY "f350_movimientos_acceso"
    ON public.f350_movimientos_declaracion FOR ALL
    USING (
        public.es_superadmin()
        OR EXISTS (
            SELECT 1
            FROM public.f350_declaraciones d
            WHERE d.id = declaracion_id
              AND public.es_admin_de_empresa(d.empresa_id)
        )
    )
    WITH CHECK (
        public.es_superadmin()
        OR EXISTS (
            SELECT 1
            FROM public.f350_declaraciones d
            WHERE d.id = declaracion_id
              AND public.es_admin_de_empresa(d.empresa_id)
        )
    );

DROP POLICY IF EXISTS "f350_subcuentas_acceso" ON public.f350_subcuentas_autorretencion;
CREATE POLICY "f350_subcuentas_acceso"
    ON public.f350_subcuentas_autorretencion FOR ALL
    USING (
        public.es_superadmin()
        OR EXISTS (
            SELECT 1
            FROM public.f350_declaraciones d
            WHERE d.id = declaracion_id
              AND public.es_admin_de_empresa(d.empresa_id)
        )
    )
    WITH CHECK (
        public.es_superadmin()
        OR EXISTS (
            SELECT 1
            FROM public.f350_declaraciones d
            WHERE d.id = declaracion_id
              AND public.es_admin_de_empresa(d.empresa_id)
        )
    );


-- =====================================================================
-- 4. PERMISOS DE EJECUCIÓN
-- =====================================================================
-- Si más adelante creas funciones SQL para encapsular operaciones
-- complejas (ej. f350_calcular_totales(declaracion_id)), recuerda
-- darles GRANT EXECUTE TO authenticated después de crearlas.
-- Lo dejamos como recordatorio porque ese fue exactamente el problema
-- que tuvimos antes con las funciones admin_*.
--
-- Patrón a usar:
--   GRANT EXECUTE ON FUNCTION public.f350_xxx TO authenticated;
-- =====================================================================


-- =====================================================================
-- 5. HABILITACIÓN DEL MÓDULO EN modulos_sistema (si existe)
-- =====================================================================
-- Si tu plataforma usa una tabla modulos_sistema para listar los
-- módulos disponibles, registramos el F350. Si no existe esa tabla,
-- esta sección no hace nada (DO $$ ... $$ EXCEPTION).

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'modulos_sistema'
    ) THEN
        INSERT INTO public.modulos_sistema (codigo, nombre, descripcion, icono, orden)
        VALUES (
            'retencion_fuente_350',
            'Retención en la Fuente (F350)',
            'Generación del Formulario 350 a partir de auxiliar y balance de Contai',
            '📋',
            10
        )
        ON CONFLICT (codigo) DO NOTHING;
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        -- Si la estructura de modulos_sistema es diferente, ignorar.
        -- Tendrás que registrar el módulo manualmente desde el panel admin.
        RAISE NOTICE 'No se pudo registrar el módulo automáticamente: %', SQLERRM;
END $$;


-- =====================================================================
-- VERIFICACIÓN
-- =====================================================================
-- Ejecutar al final para confirmar que todo quedó creado:
--
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public' AND table_name LIKE 'f350_%'
-- ORDER BY table_name;
--
-- Deberías ver 8 tablas:
--   f350_catalogo_ciiu
--   f350_declaraciones
--   f350_empresa_config
--   f350_historial_ciiu
--   f350_movimientos_declaracion
--   f350_subcuentas_autorretencion
--   f350_terceros
--   f350_uvt_historico
-- =====================================================================
