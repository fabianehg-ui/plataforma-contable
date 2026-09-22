-- =====================================================================
-- 023_conciliacion_usa_datafono.sql
--
-- Marca por banco si le aplica el RECAUDO POR DATÁFONO (Credibanco). Solo la
-- cuenta que recibe el datáfono (p.ej. BANCOLOMBIA CTE 4451) debe quedar en
-- true; los demás bancos se concilian sin datáfono.
--
-- Aplica desde Supabase -> SQL Editor -> pegar -> Run.
-- =====================================================================

ALTER TABLE public.conciliacion_bancos
    ADD COLUMN IF NOT EXISTS usa_datafono boolean NOT NULL DEFAULT false;

-- (opcional) marcar la 4451 de una vez, si existe con ese nombre:
UPDATE public.conciliacion_bancos
    SET usa_datafono = true
    WHERE upper(nombre) LIKE '%4451%' OR cuenta_auxiliar = '11-10-05-99';
