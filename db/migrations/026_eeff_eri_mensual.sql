-- =====================================================================
-- 026_eeff_eri_mensual.sql
--
-- MEMORIA del Estado de Resultados por centro de costo, MES A MES, para el
-- informe nativo. Guarda, por empresa / periodo (YYYY-MM) / centro de costo /
-- cuenta hoja, el VALOR DEL MES (movimiento del mes). Al generar un mes nuevo,
-- el informe carga los meses anteriores y anexa el nuevo, conservando la
-- secuencia mes a mes y el comparativo mes actual vs mes anterior.
--
-- RLS por empresa (es_superadmin() / es_admin_de_empresa()).
-- Aplica desde Supabase -> SQL Editor -> pegar -> Run.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.eeff_eri_mensual (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id  uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    periodo     text NOT NULL,                 -- 'YYYY-MM'
    cc          text NOT NULL,                 -- centro de costo
    cuenta      text NOT NULL,                 -- cuenta hoja (código)
    valor       numeric NOT NULL DEFAULT 0,    -- movimiento del mes (pesos)
    creado_en   timestamptz DEFAULT now(),
    UNIQUE (empresa_id, periodo, cc, cuenta)
);
CREATE INDEX IF NOT EXISTS idx_eeff_eri_mensual_emp_per
    ON public.eeff_eri_mensual (empresa_id, periodo);

ALTER TABLE public.eeff_eri_mensual ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "eeff_eri_mensual_acceso" ON public.eeff_eri_mensual;
CREATE POLICY "eeff_eri_mensual_acceso" ON public.eeff_eri_mensual FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));
