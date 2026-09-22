-- =====================================================================
-- 021_conciliacion_config.sql
--
-- Configuración por empresa del módulo "Conciliación de bancos":
--   conciliacion_bancos : por cada banco, el prefijo de la cuenta del auxiliar
--                         (cuenta puente) y el nombre de la hoja del reporte
--                         del banco donde están sus movimientos (con N COMPROBANTE).
--
-- RLS por empresa (es_superadmin() / es_admin_de_empresa(empresa_id)).
-- Aplica desde Supabase -> SQL Editor -> pegar -> Run.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.conciliacion_bancos (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id      uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    nombre          text NOT NULL,               -- etiqueta (BANCOLOMBIA CTE 4451)
    cuenta_auxiliar text NOT NULL,               -- prefijo cuenta puente (11-10-05-99)
    hoja_reporte    text NOT NULL,               -- hoja del reporte del banco
    orden           int DEFAULT 0,
    creado_en       timestamptz DEFAULT now(),
    UNIQUE (empresa_id, nombre)
);
CREATE INDEX IF NOT EXISTS idx_conciliacion_bancos_empresa
    ON public.conciliacion_bancos (empresa_id);

ALTER TABLE public.conciliacion_bancos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "conciliacion_bancos_acceso" ON public.conciliacion_bancos;
CREATE POLICY "conciliacion_bancos_acceso" ON public.conciliacion_bancos FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.conciliacion_bancos TO authenticated;
