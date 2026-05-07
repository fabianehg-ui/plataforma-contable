-- ============================================================================
-- Migración 009 — Auditoría del Editor de Reglas
-- ============================================================================
-- Aditiva, no destructiva. Solo agrega columnas y una tabla de log.
-- No toca datos existentes ni constraints.
--
-- Objetivo:
--   1. Agregar columnas de auditoría a exogena_puc_generico (Capa 1)
--      y exogena_mapeo_manual (Capa 3) para trazar cambios.
--   2. Crear tabla exogena_reglas_log con histórico de cambios desde la UI.
--   3. Mantener compatibilidad total con datos y código existente.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Auditoría en exogena_puc_generico (Capa 1 - reglas globales)
-- ----------------------------------------------------------------------------

ALTER TABLE exogena_puc_generico
  ADD COLUMN IF NOT EXISTS modificado_en TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS modificado_por TEXT;

COMMENT ON COLUMN exogena_puc_generico.modificado_en IS
  'Timestamp del último cambio hecho desde el Editor de Reglas (NULL si nunca se editó).';
COMMENT ON COLUMN exogena_puc_generico.modificado_por IS
  'Usuario (email/uuid) que hizo el último cambio desde el Editor de Reglas.';

-- ----------------------------------------------------------------------------
-- 2. Auditoría en exogena_mapeo_manual (Capa 3 - override por empresa)
-- ----------------------------------------------------------------------------

ALTER TABLE exogena_mapeo_manual
  ADD COLUMN IF NOT EXISTS modificado_en TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS modificado_por TEXT;

COMMENT ON COLUMN exogena_mapeo_manual.modificado_en IS
  'Timestamp del último cambio hecho desde el Editor de Reglas.';
COMMENT ON COLUMN exogena_mapeo_manual.modificado_por IS
  'Usuario que hizo el último cambio desde el Editor de Reglas.';

-- ----------------------------------------------------------------------------
-- 3. Tabla de log de cambios (histórico completo)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS exogena_reglas_log (
  id BIGSERIAL PRIMARY KEY,
  fecha TIMESTAMPTZ DEFAULT NOW(),
  usuario TEXT NOT NULL,
  empresa_id UUID,                          -- NULL si fue cambio en Capa 1 (global)
  capa SMALLINT NOT NULL CHECK (capa IN (1, 3)),
  accion TEXT NOT NULL CHECK (accion IN ('crear', 'editar', 'eliminar', 'mover')),
  codigo_cuenta TEXT NOT NULL,
  formato_anterior TEXT,
  concepto_anterior INTEGER,
  formato_nuevo TEXT,
  concepto_nuevo INTEGER,
  motivo TEXT,                              -- Comentario opcional del usuario
  metadata JSONB                            -- Para guardar contexto adicional (NIT si aplica, etc.)
);

CREATE INDEX IF NOT EXISTS idx_reglas_log_fecha ON exogena_reglas_log(fecha DESC);
CREATE INDEX IF NOT EXISTS idx_reglas_log_empresa ON exogena_reglas_log(empresa_id);
CREATE INDEX IF NOT EXISTS idx_reglas_log_cuenta ON exogena_reglas_log(codigo_cuenta);

COMMENT ON TABLE exogena_reglas_log IS
  'Histórico completo de cambios hechos desde el Editor de Reglas.
   Incluye cambios en Capa 1 (global) y Capa 3 (override por empresa).
   Capa 2 (mapeo nativo) NO se edita desde el editor — viene del archivo de Codificación.';

-- ----------------------------------------------------------------------------
-- 4. RLS para la tabla de log
-- ----------------------------------------------------------------------------

ALTER TABLE exogena_reglas_log ENABLE ROW LEVEL SECURITY;

-- Lectura: todos los usuarios autenticados pueden leer
DROP POLICY IF EXISTS exogena_reglas_log_select ON exogena_reglas_log;
CREATE POLICY exogena_reglas_log_select ON exogena_reglas_log
  FOR SELECT TO authenticated USING (true);

-- Inserción: solo se puede escribir desde el backend (la app valida usuario)
DROP POLICY IF EXISTS exogena_reglas_log_insert ON exogena_reglas_log;
CREATE POLICY exogena_reglas_log_insert ON exogena_reglas_log
  FOR INSERT TO authenticated WITH CHECK (true);

-- ----------------------------------------------------------------------------
-- Validación
-- ----------------------------------------------------------------------------

-- Después de ejecutar, validar con:
--
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'exogena_puc_generico'
--   AND column_name IN ('modificado_en', 'modificado_por');
-- -- Debe devolver 2 filas
--
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'exogena_mapeo_manual'
--   AND column_name IN ('modificado_en', 'modificado_por');
-- -- Debe devolver 2 filas
--
-- SELECT * FROM exogena_reglas_log LIMIT 1;
-- -- Debe ejecutarse sin error (vacía)
