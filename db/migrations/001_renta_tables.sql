-- Migración: Tablas para módulo de Declaración de Renta PJ
-- Ajustada a la estructura real de plataforma-contable
CREATE TABLE IF NOT EXISTS renta_liquidaciones (
id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
empresa_id                      UUID NOT NULL,
nit                             TEXT NOT NULL,
ano_gravable                    INTEGER NOT NULL,
estado                          TEXT NOT NULL DEFAULT 'borrador'
CHECK (estado IN ('borrador', 'revisado', 'presentado', 'anulado')),
casilla_44_patrimonio_bruto     NUMERIC(18, 2) DEFAULT 0,
casilla_46_patrimonio_liquido   NUMERIC(18, 2) DEFAULT 0,
casilla_72_renta_liquida_ordinaria NUMERIC(18, 2) DEFAULT 0,
casilla_99_total_impuesto_a_cargo NUMERIC(18, 2) DEFAULT 0,
casilla_113_total_saldo_a_pagar NUMERIC(18, 2) DEFAULT 0,
casilla_114_total_saldo_a_favor NUMERIC(18, 2) DEFAULT 0,
datos_form110_json              JSONB NOT NULL,
notas                           TEXT,
usuario_id_creacion             UUID,
usuario_id_modificacion         UUID,
fecha_creacion                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
fecha_modificacion              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
UNIQUE (empresa_id, ano_gravable)
);
CREATE INDEX IF NOT EXISTS idx_renta_liq_empresa ON renta_liquidaciones (empresa_id, ano_gravable DESC);
CREATE INDEX IF NOT EXISTS idx_renta_liq_estado ON renta_liquidaciones (estado);
CREATE INDEX IF NOT EXISTS idx_renta_liq_nit ON renta_liquidaciones (nit);
CREATE OR REPLACE FUNCTION renta_actualizar_fecha_modificacion()
RETURNS TRIGGER AS $$
BEGIN
NEW.fecha_modificacion = NOW();
RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_renta_liq_fecha_mod ON renta_liquidaciones;
CREATE TRIGGER trg_renta_liq_fecha_mod
BEFORE UPDATE ON renta_liquidaciones
FOR EACH ROW
EXECUTE FUNCTION renta_actualizar_fecha_modificacion();
CREATE TABLE IF NOT EXISTS renta_partidas_conciliatorias (
id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
empresa_id      UUID NOT NULL,
ano_gravable    INTEGER NOT NULL,
codigo          TEXT NOT NULL,
nombre          TEXT NOT NULL,
valor           NUMERIC(18, 2) NOT NULL DEFAULT 0,
tipo            TEXT NOT NULL CHECK (tipo IN ('aumenta', 'disminuye')),
base_legal      TEXT,
notas           TEXT,
orden           INTEGER NOT NULL DEFAULT 0,
fecha_creacion  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
UNIQUE (empresa_id, ano_gravable, codigo)
);
CREATE INDEX IF NOT EXISTS idx_renta_partidas_empresa ON renta_partidas_conciliatorias (empresa_id, ano_gravable);
ALTER TABLE renta_liquidaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE renta_partidas_conciliatorias ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS renta_liq_select_propias ON renta_liquidaciones;
CREATE POLICY renta_liq_select_propias ON renta_liquidaciones
FOR SELECT
USING (
empresa_id IN (SELECT empresa_id FROM usuario_empresa WHERE usuario_id = auth.uid())
OR EXISTS (SELECT 1 FROM superadmins WHERE usuario_id = auth.uid())
);
DROP POLICY IF EXISTS renta_liq_modificar ON renta_liquidaciones;
CREATE POLICY renta_liq_modificar ON renta_liquidaciones
FOR ALL
USING (
empresa_id IN (SELECT empresa_id FROM usuario_empresa WHERE usuario_id = auth.uid() AND rol IN ('contable', 'admin', 'superadmin'))
OR EXISTS (SELECT 1 FROM superadmins WHERE usuario_id = auth.uid())
);
DROP POLICY IF EXISTS renta_partidas_select ON renta_partidas_conciliatorias;
CREATE POLICY renta_partidas_select ON renta_partidas_conciliatorias
FOR SELECT
USING (
empresa_id IN (SELECT empresa_id FROM usuario_empresa WHERE usuario_id = auth.uid())
OR EXISTS (SELECT 1 FROM superadmins WHERE usuario_id = auth.uid())
);
DROP POLICY IF EXISTS renta_partidas_modificar ON renta_partidas_conciliatorias;
CREATE POLICY renta_partidas_modificar ON renta_partidas_conciliatorias
FOR ALL
USING (
empresa_id IN (SELECT empresa_id FROM usuario_empresa WHERE usuario_id = auth.uid() AND rol IN ('contable', 'admin', 'superadmin'))
OR EXISTS (SELECT 1 FROM superadmins WHERE usuario_id = auth.uid())
);
CREATE OR REPLACE FUNCTION obtener_liquidacion_renta_actual(
p_empresa_id UUID,
p_ano_gravable INTEGER DEFAULT NULL
)
RETURNS SETOF renta_liquidaciones AS $$
BEGIN
IF p_ano_gravable IS NOT NULL THEN
RETURN QUERY SELECT * FROM renta_liquidaciones WHERE empresa_id = p_empresa_id AND ano_gravable = p_ano_gravable;
ELSE
RETURN QUERY SELECT * FROM renta_liquidaciones WHERE empresa_id = p_empresa_id ORDER BY ano_gravable DESC LIMIT 1;
END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
COMMENT ON TABLE renta_liquidaciones IS 'Liquidaciones del Formulario 110 - Declaracion de Renta PJ';
COMMENT ON TABLE renta_partidas_conciliatorias IS 'Catalogo de partidas conciliatorias por empresa y año';
