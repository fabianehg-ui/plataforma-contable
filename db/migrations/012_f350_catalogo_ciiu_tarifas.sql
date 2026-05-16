-- =====================================================================
-- 012_f350_catalogo_ciiu_tarifas.sql
--
-- Carga el catálogo CIIU con las tarifas de autorretención más usadas.
--
-- IMPORTANTE — contexto normativo (Mayo 2026):
--
--   El Consejo de Estado suspendió provisionalmente los artículos 2 a 8
--   del Decreto 0572 de 2025 mediante auto del 7 de mayo de 2026.
--
--   Desde el 8 de mayo de 2026 aplican las tarifas y bases de los
--   Decretos 0261/2023 y 0242/2024 (DIAN Comunicado 070 del 08/05/2026).
--
-- Estrategia de carga:
--
--   1. Carga las tarifas del Dec. 0572/2025 con:
--        vigencia_desde = '2025-06-01'
--        vigencia_hasta = '2026-05-07'
--        normativa      = 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'
--      Esto preserva el dato histórico para declaraciones de jun-2025
--      hasta abr-2026 que se hayan presentado con esas tarifas.
--
--   2. Las tarifas vigentes desde el 8 de mayo de 2026 (Dec. 0261/2023
--      + 0242/2024) se cargarán en una migración posterior (013_) una
--      vez se compile el listado oficial completo. Por ahora se deja
--      registrado el CIIU con tarifa NULL y normativa "Pendiente
--      cargar tarifa Dec. 0261/2023" para que el módulo sepa que la
--      empresa tiene que configurar su tarifa manualmente.
--
-- Aplica desde Supabase → SQL Editor → New query → pegar todo → Run.
--
-- Fecha: 2026-05-16
-- =====================================================================


-- =====================================================================
-- 1. TARIFAS DEL DECRETO 0572/2025 (SUSPENDIDO)
-- =====================================================================
-- Vigencia: del 1 de junio de 2025 al 7 de mayo de 2026 (suspendido).
-- Solo se usan para declaraciones del período jun-2025 a abr-2026.

INSERT INTO public.f350_catalogo_ciiu
    (codigo, actividad_economica, seccion_ciiu, tarifa_autorretencion,
     vigencia_desde, vigencia_hasta, normativa)
VALUES
    -- A - Agricultura
    ('111',  'Cultivo de cereales',                            'A - Agricultura',     0.0120, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('123',  'Cultivo de café',                                'A - Agricultura',     0.0120, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('141',  'Cría de ganado bovino y bufalino',               'A - Agricultura',     0.0120, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- B - Minería
    ('510',  'Extracción de hulla (carbón de piedra)',         'B - Minería',         0.0450, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('610',  'Extracción de petróleo crudo',                   'B - Minería',         0.0270, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('722',  'Extracción de oro y metales preciosos',          'B - Minería',         0.0450, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- C - Manufactura
    ('1011', 'Procesamiento y conservación de carne',          'C - Manufactura',     0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('1040', 'Elaboración de productos lácteos',               'C - Manufactura',     0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('1081', 'Elaboración de productos de panadería',          'C - Manufactura',     0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('1084', 'Elaboración de comidas y platos preparados',     'C - Manufactura',     0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('1101', 'Destilación y mezcla de bebidas alcohólicas',    'C - Manufactura',     0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('1410', 'Confección de prendas de vestir',                'C - Manufactura',     0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('1521', 'Fabricación de calzado de cuero',                'C - Manufactura',     0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('2100', 'Fabricación de productos farmacéuticos',         'C - Manufactura',     0.0120, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('3110', 'Fabricación de muebles',                         'C - Manufactura',     0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- D - Servicios públicos
    ('3511', 'Generación de energía eléctrica',                'D - Servicios Públicos', 0.0450, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- E - Agua
    ('3600', 'Captación y distribución de agua',               'E - Agua',            0.0450, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- F - Construcción
    ('4111', 'Construcción de edificios residenciales',        'F - Construcción',    0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('4112', 'Construcción de edificios no residenciales',     'F - Construcción',    0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('4290', 'Construcción de otras obras de ingeniería civil','F - Construcción',    0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- G - Comercio
    ('4511', 'Comercio de vehículos automotores nuevos',       'G - Comercio',        0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('4631', 'Comercio mayor de productos alimenticios',       'G - Comercio',        0.0120, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('4711', 'Comercio minorista no especializado alimentos',  'G - Comercio',        0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('4719', 'Comercio minorista no especializado otros',      'G - Comercio',        0.0055, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('4771', 'Comercio minorista de prendas de vestir',        'G - Comercio',        0.0120, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- H - Transporte
    ('4921', 'Transporte de pasajeros',                        'H - Transporte',      0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('4923', 'Transporte de carga por carretera',              'H - Transporte',      0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('5211', 'Almacenamiento y depósito',                      'H - Transporte',      0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- I - Alojamiento y comidas
    ('5511', 'Alojamiento en hoteles',                         'I - Alojamiento',     0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('5611', 'Expendio a la mesa de comidas preparadas',       'I - Comidas',         0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('5612', 'Expendio por autoservicio de comidas preparadas','I - Comidas',         0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('5613', 'Expendio de comidas en cafeterías',              'I - Comidas',         0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('5630', 'Expendio de bebidas alcohólicas',                'I - Comidas',         0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- J - Información y comunicaciones
    ('5820', 'Edición de programas de informática',            'J - Info',            0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('6110', 'Telecomunicaciones alámbricas',                  'J - Info',            0.0220, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('6201', 'Desarrollo de sistemas informáticos',            'J - Info',            0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('6311', 'Procesamiento de datos y hosting',               'J - Info',            0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- K - Actividades financieras y de seguros
    ('6412', 'Bancos comerciales',                             'K - Financieras',     0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('6511', 'Seguros generales',                              'K - Financieras',     0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- L - Inmobiliarias
    ('6810', 'Actividades inmobiliarias bienes propios',       'L - Inmobiliarias',   0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- M - Profesionales, científicas y técnicas
    ('6910', 'Actividades jurídicas',                          'M - Profesionales',   0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('6920', 'Actividades de contabilidad y asesoría tributaria', 'M - Profesionales', 0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('7020', 'Actividades de consultoría de gestión',          'M - Profesionales',   0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('7111', 'Actividades de arquitectura',                    'M - Profesionales',   0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('7112', 'Actividades de ingeniería',                      'M - Profesionales',   0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('7310', 'Publicidad',                                     'M - Profesionales',   0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- N - Administración / servicios de apoyo
    ('8010', 'Actividades de seguridad privada',               'N - Admin',           0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- P - Educación
    ('8512', 'Educación preescolar',                           'P - Educación',       0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- Q - Salud
    ('8610', 'Actividades de hospitales y clínicas',           'Q - Salud',           0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),
    ('8621', 'Práctica médica sin internación',                'Q - Salud',           0.0110, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026'),

    -- R - Artísticas, entretenimiento
    ('9200', 'Juegos de azar y apuestas',                      'R - Artísticas',      0.0350, '2025-06-01', '2026-05-07', 'Dec. 0572/2025 — SUSPENDIDO 7 mayo 2026')

ON CONFLICT (codigo, vigencia_desde) DO NOTHING;


-- =====================================================================
-- 2. PLACEHOLDERS PARA EL DEC. 0261/2023 + 0242/2024
-- =====================================================================
-- Crea registros con tarifa NULL para los mismos CIIU, indicando que
-- la tarifa vigente debe configurarse manualmente o cargarse en una
-- migración futura cuando se tenga el listado oficial completo.
--
-- La UI del módulo F350 detectará la tarifa NULL y pedirá al contador
-- que la configure por empresa en `tarifa_autorretencion_manual` de
-- f350_empresa_config.

INSERT INTO public.f350_catalogo_ciiu
    (codigo, actividad_economica, seccion_ciiu, tarifa_autorretencion,
     vigencia_desde, vigencia_hasta, normativa)
SELECT
    codigo,
    actividad_economica,
    seccion_ciiu,
    NULL                                  AS tarifa_autorretencion,
    '2026-05-08'::date                    AS vigencia_desde,
    NULL                                  AS vigencia_hasta,
    'Dec. 0261/2023 + 0242/2024 — Pendiente cargar tarifa oficial' AS normativa
FROM public.f350_catalogo_ciiu
WHERE vigencia_desde = '2025-06-01'
ON CONFLICT (codigo, vigencia_desde) DO NOTHING;


-- =====================================================================
-- 3. FUNCIÓN AUXILIAR: tarifa vigente por CIIU y fecha
-- =====================================================================
-- Devuelve la tarifa de autorretención aplicable a un CIIU en una fecha
-- determinada. Si la tarifa vigente es NULL (Dec. 0261 pendiente de
-- cargar), devuelve NULL para que la UI advierta al contador.

CREATE OR REPLACE FUNCTION public.f350_tarifa_vigente(
    p_codigo_ciiu text,
    p_fecha       date
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT tarifa_autorretencion
    FROM public.f350_catalogo_ciiu
    WHERE codigo = p_codigo_ciiu
      AND vigencia_desde <= p_fecha
      AND (vigencia_hasta IS NULL OR vigencia_hasta >= p_fecha)
    ORDER BY vigencia_desde DESC
    LIMIT 1;
$$;

-- Permiso de ejecución (lección aprendida del módulo de exógena)
GRANT EXECUTE ON FUNCTION public.f350_tarifa_vigente(text, date) TO authenticated;


-- =====================================================================
-- VERIFICACIÓN
-- =====================================================================
-- Después de aplicar, ejecuta para verificar:
--
-- SELECT COUNT(*) AS total,
--        COUNT(tarifa_autorretencion) AS con_tarifa,
--        COUNT(*) FILTER (WHERE tarifa_autorretencion IS NULL) AS sin_tarifa
-- FROM public.f350_catalogo_ciiu;
--
-- Esperado: ~50 con tarifa (Dec. 0572) + ~50 sin tarifa (Dec. 0261 pendiente).
--
-- Probar la función:
-- SELECT public.f350_tarifa_vigente('5611', '2026-01-15'); -- → 0.0350
-- SELECT public.f350_tarifa_vigente('5611', '2026-06-01'); -- → NULL (pendiente)
-- =====================================================================
