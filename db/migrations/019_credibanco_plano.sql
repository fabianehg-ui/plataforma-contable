-- =====================================================================
-- 019_credibanco_plano.sql
--
-- Configuración por empresa para el módulo "Plano Credibanco":
--   - credibanco_maestro : código de establecimiento -> centro de costo
--   - credibanco_config  : cuentas de gastos/retenciones y divisores
--
-- Con esto el módulo deja de estar amarrado a JIPER: cada empresa define
-- sus propios códigos->centro de costo y sus cuentas desde la plataforma.
--
-- Las tablas se crean VACÍAS; cada empresa carga su maestro/cuentas desde la
-- UI (o siembra el de JIPER con el botón). RLS por empresa (011/014/015):
-- es_superadmin() / es_admin_de_empresa(empresa_id).
-- Aplica desde Supabase -> SQL Editor -> pegar -> Run.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Maestro: código de establecimiento -> centro de costo
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.credibanco_maestro (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id     uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    codigo         text NOT NULL,               -- CODIGO ESTABLECIMIENTO del reporte
    oasis          text,                         -- nombre del punto (opcional)
    centro_costo   text NOT NULL,               -- centro de costo, 6 dígitos (ej. 001110)
    activo         boolean DEFAULT true,
    creado_en      timestamptz DEFAULT now(),
    actualizado_en timestamptz DEFAULT now(),
    UNIQUE (empresa_id, codigo)
);
CREATE INDEX IF NOT EXISTS idx_credibanco_maestro_empresa
    ON public.credibanco_maestro (empresa_id);

-- ---------------------------------------------------------------------
-- 2. Config: cuentas de gastos/retenciones y divisores (una fila x empresa)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.credibanco_config (
    empresa_id          uuid PRIMARY KEY REFERENCES public.empresas(id) ON DELETE CASCADE,
    cuenta_comision     text,
    cuenta_retefuente   text,
    cuenta_rete_iva     text,
    cuenta_rete_ica     text,
    divisor_retefuente  numeric(7,4) DEFAULT 0.015,
    divisor_rete_iva    numeric(7,4) DEFAULT 0.15,
    divisor_rete_ica    numeric(7,4) DEFAULT 0.009,
    nit                 text DEFAULT '890903938',   -- tercero Credibanco/Bancolombia
    detalle             text DEFAULT 'CONCILIACION BANCARIA',
    tipo                text DEFAULT '1',
    comprobante         text DEFAULT '10',
    actualizado_en      timestamptz DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 3. RLS (misma convención de 016)
-- ---------------------------------------------------------------------
ALTER TABLE public.credibanco_maestro ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.credibanco_config  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "credibanco_maestro_acceso" ON public.credibanco_maestro;
CREATE POLICY "credibanco_maestro_acceso" ON public.credibanco_maestro FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

DROP POLICY IF EXISTS "credibanco_config_acceso" ON public.credibanco_config;
CREATE POLICY "credibanco_config_acceso" ON public.credibanco_config FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.credibanco_maestro TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.credibanco_config  TO authenticated;
