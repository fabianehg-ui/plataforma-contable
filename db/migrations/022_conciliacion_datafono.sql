-- =====================================================================
-- 022_conciliacion_datafono.sql
--
-- MAESTRO del datáfono Credibanco por empresa: relaciona cada CÓDIGO DE
-- ESTABLECIMIENTO con su CENTRO DE COSTO (y OASIS). Con esto INTEGRAL calcula
-- la comisión y las retenciones directamente desde el ARCHIVO ORIGINAL de
-- Credibanco (no exige correr la macro).
--
-- RLS por empresa (es_superadmin() / es_admin_de_empresa()).
-- Aplica desde Supabase -> SQL Editor -> pegar -> Run.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.conciliacion_datafono (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id      uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    establecimiento text NOT NULL,             -- CODIGO ESTABLECIMIENTO Credibanco
    cc              text NOT NULL,             -- centro de costo
    oasis           text,                      -- nombre del punto (opcional)
    creado_en       timestamptz DEFAULT now(),
    UNIQUE (empresa_id, establecimiento)
);
CREATE INDEX IF NOT EXISTS idx_conciliacion_datafono_empresa
    ON public.conciliacion_datafono (empresa_id);

ALTER TABLE public.conciliacion_datafono ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "conciliacion_datafono_acceso" ON public.conciliacion_datafono;
CREATE POLICY "conciliacion_datafono_acceso" ON public.conciliacion_datafono FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.conciliacion_datafono TO authenticated;
