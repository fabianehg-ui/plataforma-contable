-- =====================================================================
-- 020_bancos_config.sql
--
-- Configuración por empresa del módulo "Bancos a Contai" (extractos):
--   - bancos_config  : bancos de la empresa (cómo detectar, formato, NIT,
--                      y la cuenta PUC del banco = contrapartida)
--   - bancos_reglas  : reglas de clasificación (lista blanca)
--                      patrón -> cuenta + lado (D gasto / C ingreso / R retención)
--   - bancos_cc      : centros de costo entre los que se reparte (partes iguales)
--
-- Con esto el módulo deja de estar quemado para 3 bancos: cada empresa define
-- sus bancos, sus cuentas y sus centros de costo desde la plataforma.
-- RLS por empresa (es_superadmin() / es_admin_de_empresa(empresa_id)).
-- Aplica desde Supabase -> SQL Editor -> pegar -> Run.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. Bancos de la empresa
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.bancos_config (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id     uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    nombre         text NOT NULL,               -- etiqueta (DAVIVIENDA 7872)
    detectar       text NOT NULL,               -- texto que identifica el extracto
    formato        text NOT NULL,               -- parser: davivienda / occidente / ...
    nit            text,                         -- NIT del banco
    cuenta_puc     text NOT NULL,               -- cuenta del banco en el PUC
    orden          int DEFAULT 0,
    activo         boolean DEFAULT true,
    creado_en      timestamptz DEFAULT now(),
    UNIQUE (empresa_id, nombre)
);
CREATE INDEX IF NOT EXISTS idx_bancos_config_empresa ON public.bancos_config (empresa_id);

-- ---------------------------------------------------------------------
-- 2. Reglas de clasificación (lista blanca)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.bancos_reglas (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id     uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    orden          int DEFAULT 0,               -- el orden manda: gana la 1a que casa
    patron         text NOT NULL,               -- regex sobre la descripción
    cuenta         text NOT NULL,               -- cuenta PUC del concepto
    lado           text NOT NULL DEFAULT 'D',   -- D gasto | C ingreso | R retención
    base           boolean DEFAULT false,       -- lleva base gravable (IVA)
    etiqueta       text,                         -- detalle del asiento
    creado_en      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_bancos_reglas_empresa ON public.bancos_reglas (empresa_id);

-- ---------------------------------------------------------------------
-- 3. Centros de costo (reparto en partes iguales)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.bancos_cc (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id     uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    centro_costo   text NOT NULL,
    orden          int DEFAULT 0,
    UNIQUE (empresa_id, centro_costo)
);
CREATE INDEX IF NOT EXISTS idx_bancos_cc_empresa ON public.bancos_cc (empresa_id);

-- ---------------------------------------------------------------------
-- 4. RLS
-- ---------------------------------------------------------------------
ALTER TABLE public.bancos_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bancos_reglas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bancos_cc     ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "bancos_config_acceso" ON public.bancos_config;
CREATE POLICY "bancos_config_acceso" ON public.bancos_config FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

DROP POLICY IF EXISTS "bancos_reglas_acceso" ON public.bancos_reglas;
CREATE POLICY "bancos_reglas_acceso" ON public.bancos_reglas FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

DROP POLICY IF EXISTS "bancos_cc_acceso" ON public.bancos_cc;
CREATE POLICY "bancos_cc_acceso" ON public.bancos_cc FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.bancos_config TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.bancos_reglas TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.bancos_cc     TO authenticated;
