-- =====================================================================
-- 016_conceptos_iva_retencion.sql
--
-- Atajos de captura para INTEGRAL:
--   - cn_tipos_iva        : tipos y tarifas de IVA (descontable/generado)
--   - cn_tipos_retencion  : tipos y tarifas de retención (fuente/IVA/ICA)
--   - cn_conceptos        : "conceptos programados" (plantillas de asiento)
--
-- Con esto la Captura puede: elegir un concepto + base y auto-armar las
-- líneas del asiento (Db=Cr), en vez de digitar cuenta por cuenta.
--
-- Las tablas se crean VACÍAS; el juego estándar se siembra por empresa
-- desde la UI (botón "Sembrar catálogo estándar"), porque el empresa_id
-- es un uuid propio de cada empresa (RLS).
--
-- Convención de 011/014/015: es_superadmin() / es_admin_de_empresa(empresa_id).
-- Aplica desde Supabase → SQL Editor → pegar → Run.
-- Fecha: 2026-07-18
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. Tipos de IVA
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.cn_tipos_iva (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id     uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    codigo         text NOT NULL,               -- ej. 'IVA19'
    nombre         text NOT NULL,               -- ej. 'IVA 19% descontable'
    tarifa         numeric(7,4) NOT NULL DEFAULT 0,   -- 19.0000, 5.0000, 0
    cuenta         text,                        -- cuenta contable del IVA
    tipo           char(1) DEFAULT 'C',         -- 'C' compra/descontable · 'V' venta/generado
    activo         boolean DEFAULT true,
    creado_en      timestamptz DEFAULT now(),
    actualizado_en timestamptz DEFAULT now(),
    UNIQUE (empresa_id, codigo)
);
CREATE INDEX IF NOT EXISTS idx_cn_tipos_iva_empresa ON public.cn_tipos_iva (empresa_id);


-- ---------------------------------------------------------------------
-- 2. Tipos de retención
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.cn_tipos_retencion (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id     uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    codigo         text NOT NULL,               -- ej. 'RFCOMP'
    nombre         text NOT NULL,               -- ej. 'ReteFuente compras 2.5%'
    tarifa         numeric(7,4) NOT NULL DEFAULT 0,   -- 2.5000, 4, 11, 15...
    base_calculo   text NOT NULL DEFAULT 'base',      -- 'base' (sobre base gravable) · 'iva' (sobre el IVA, p.ej. reteIVA)
    base_uvt       numeric(10,2) DEFAULT 0,     -- base mínima en UVT (0 = sin mínimo)
    cuenta         text,                        -- cuenta contable de la retención (2365xx / 2367xx / 2368xx)
    clase          text DEFAULT 'fuente',       -- 'fuente' | 'iva' | 'ica' (para agrupar/nombrar)
    activo         boolean DEFAULT true,
    creado_en      timestamptz DEFAULT now(),
    actualizado_en timestamptz DEFAULT now(),
    UNIQUE (empresa_id, codigo)
);
CREATE INDEX IF NOT EXISTS idx_cn_tipos_ret_empresa ON public.cn_tipos_retencion (empresa_id);


-- ---------------------------------------------------------------------
-- 3. Conceptos programados (plantillas de asiento)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.cn_conceptos (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id            uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    codigo                text NOT NULL,          -- ej. 'COMPRA_BIEN_19'
    nombre                text NOT NULL,          -- ej. 'Compra de bienes 19% + ReteCompras'
    naturaleza            text NOT NULL DEFAULT 'compra',  -- 'compra' | 'venta' | 'otro'
    comprobante           text,                   -- código de comprobante sugerido
    cuenta_base           text,                   -- gasto/compra (compra) o ingreso (venta)
    cuenta_contrapartida  text,                   -- proveedor/banco (compra) o cliente/caja (venta)
    tipo_iva_codigo       text,                   -- FK lógica a cn_tipos_iva.codigo (opcional)
    tipo_retencion_codigo text,                   -- FK lógica a cn_tipos_retencion.codigo (opcional)
    maneja_iva            boolean DEFAULT true,
    maneja_retencion      boolean DEFAULT true,
    descripcion           text,
    activo                boolean DEFAULT true,
    creado_en             timestamptz DEFAULT now(),
    actualizado_en        timestamptz DEFAULT now(),
    UNIQUE (empresa_id, codigo)
);
CREATE INDEX IF NOT EXISTS idx_cn_conceptos_empresa ON public.cn_conceptos (empresa_id);


-- ---------------------------------------------------------------------
-- 4. RLS (superadmin o admin de la empresa) + grants
-- ---------------------------------------------------------------------
ALTER TABLE public.cn_tipos_iva        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cn_tipos_retencion  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cn_conceptos        ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cn_tipos_iva_acceso" ON public.cn_tipos_iva;
CREATE POLICY "cn_tipos_iva_acceso" ON public.cn_tipos_iva FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

DROP POLICY IF EXISTS "cn_tipos_ret_acceso" ON public.cn_tipos_retencion;
CREATE POLICY "cn_tipos_ret_acceso" ON public.cn_tipos_retencion FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

DROP POLICY IF EXISTS "cn_conceptos_acceso" ON public.cn_conceptos;
CREATE POLICY "cn_conceptos_acceso" ON public.cn_conceptos FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_tipos_iva       TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_tipos_retencion TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_conceptos       TO authenticated;

-- =====================================================================
-- FIN 016_conceptos_iva_retencion.sql
-- =====================================================================
