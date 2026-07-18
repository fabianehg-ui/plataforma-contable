-- =====================================================================
-- 015_terceros.sql
--
-- Maestro de TERCEROS (NITs) por empresa, para INTEGRAL.
-- Complementa el núcleo contable (014). Los movimientos (cn_movimientos)
-- guardan el NIT; esta tabla le pone nombre, tipo y datos al tercero.
--
-- Convención de 011/014: es_superadmin() / es_admin_de_empresa(empresa_id).
-- Aplica desde Supabase → SQL Editor → pegar → Run.
-- Fecha: 2026-07-17
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.cn_terceros (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id     uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    nit            text NOT NULL,
    nombre         text NOT NULL,
    tipo_persona   char(1),               -- 'N' natural · 'J' jurídica
    dv             text,                  -- dígito de verificación
    regimen        text,                  -- ej. 'Común','Simple','No responsable'
    email          text,
    telefono       text,
    direccion      text,
    municipio      text,                  -- código DANE o nombre
    activo         boolean DEFAULT true,
    creado_en      timestamp with time zone DEFAULT now(),
    actualizado_en timestamp with time zone DEFAULT now(),
    UNIQUE (empresa_id, nit)
);

CREATE INDEX IF NOT EXISTS idx_cn_terceros_empresa
    ON public.cn_terceros (empresa_id);
CREATE INDEX IF NOT EXISTS idx_cn_terceros_nit
    ON public.cn_terceros (empresa_id, nit);

-- RLS: superadmin o admin de la empresa
ALTER TABLE public.cn_terceros ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "cn_terceros_acceso" ON public.cn_terceros;
CREATE POLICY "cn_terceros_acceso"
    ON public.cn_terceros FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.cn_terceros TO authenticated;

-- =====================================================================
-- FIN 015_terceros.sql
-- =====================================================================
