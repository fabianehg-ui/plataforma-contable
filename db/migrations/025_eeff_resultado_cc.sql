-- =====================================================================
-- 025_eeff_resultado_cc.sql
--
-- MEMORIA del resultado por centro de costo del mes, para el informe de
-- Estados Financieros (comparativo con el mes inmediatamente anterior).
-- Guarda, por empresa / periodo (YYYY-MM) / centro de costo, los totales del
-- mes de INGRESOS, COSTOS, GASTOS y UTILIDAD (en pesos). El mes siguiente se
-- usa como comparativo del mes anterior.
--
-- RLS por empresa (es_superadmin() / es_admin_de_empresa()).
-- Aplica desde Supabase -> SQL Editor -> pegar -> Run.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.eeff_resultado_cc (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id  uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    periodo     text NOT NULL,                 -- 'YYYY-MM'
    cc          text NOT NULL,                 -- centro de costo
    nombre_cc   text,
    ingresos    numeric NOT NULL DEFAULT 0,
    costos      numeric NOT NULL DEFAULT 0,
    gastos      numeric NOT NULL DEFAULT 0,
    utilidad    numeric NOT NULL DEFAULT 0,
    creado_en   timestamptz DEFAULT now(),
    UNIQUE (empresa_id, periodo, cc)
);
CREATE INDEX IF NOT EXISTS idx_eeff_resultado_cc_emp_per
    ON public.eeff_resultado_cc (empresa_id, periodo);

ALTER TABLE public.eeff_resultado_cc ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "eeff_resultado_cc_acceso" ON public.eeff_resultado_cc;
CREATE POLICY "eeff_resultado_cc_acceso" ON public.eeff_resultado_cc FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));
