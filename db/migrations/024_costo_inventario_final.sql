-- =====================================================================
-- 024_costo_inventario_final.sql
--
-- MEMORIA del inventario FINAL por periodo y centro de costo, para el
-- TRASLADO DEL COSTO. El inventario final de un mes se guarda aquí y se
-- reutiliza como inventario INICIAL del mes siguiente, evitando descuadres
-- o diferencias entre meses.
--
--   periodo  = 'YYYY-MM' del mes al que pertenece el inventario final
--   version  = 'sin_iva' (SUBTOTAL + ICUI, por defecto) | 'con_iva'
--   cc       = centro de costo
--   valor    = inventario final de ese CC en ese periodo
--
-- RLS por empresa (es_superadmin() / es_admin_de_empresa()).
-- Aplica desde Supabase -> SQL Editor -> pegar -> Run.
-- =====================================================================

CREATE TABLE IF NOT EXISTS public.costo_inventario_final (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id  uuid NOT NULL REFERENCES public.empresas(id) ON DELETE CASCADE,
    periodo     text NOT NULL,                 -- 'YYYY-MM'
    version     text NOT NULL DEFAULT 'sin_iva',
    cc          text NOT NULL,                 -- centro de costo
    valor       numeric NOT NULL DEFAULT 0,
    fuente      text,                          -- nota/origen (opcional)
    creado_en   timestamptz DEFAULT now(),
    actualizado_en timestamptz DEFAULT now(),
    UNIQUE (empresa_id, periodo, version, cc)
);
CREATE INDEX IF NOT EXISTS idx_costo_inv_final_empresa_periodo
    ON public.costo_inventario_final (empresa_id, periodo, version);

ALTER TABLE public.costo_inventario_final ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "costo_inventario_final_acceso" ON public.costo_inventario_final;
CREATE POLICY "costo_inventario_final_acceso" ON public.costo_inventario_final FOR ALL
    USING (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id))
    WITH CHECK (public.es_superadmin() OR public.es_admin_de_empresa(empresa_id));
