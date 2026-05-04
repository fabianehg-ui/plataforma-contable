"""
Tests unitarios del motor de clasificación v2.

Cubre todas las reglas especiales:
  - Conciliación cuenta 6 ↔ 72/73
  - Indexación de retenciones 2365 por NIT
  - F1003 con cuentas correctas (135515, 195515 → débitos; 2408 → créditos)
  - Activos fijos, inventarios, cartera (regresión del v1)
  - Reglas especiales de exclusión
  - Capa 1, 2, 3 (regresión del v1)
"""
import unittest
from motor_clasificacion import (
    Movimiento,
    ReglaCapa1,
    ReglaCapa2,
    ReglaCapa3,
    MotorClasificacion,
    validar_conciliacion_costos_traslado,
    indexar_retenciones_2365,
    aplicar_regla_especial,
    _es_cuenta_activos_fijos,
    _es_cuenta_inventario_compra,
    _es_cuenta_cartera_1008,
    _es_cuenta_f1003,
    _es_cuenta_2365,
    _es_2365_salarios,
    _es_2365_exceso,
    _es_2365_traslados,
    _nombre_dice_compras,
    _nombre_dice_traslado_costo,
    cuenta_en_rango,
    CONCEPTO_DIAN_EXCESO_AÑO_ANTERIOR,
)


# ================================================================
# Tests de utilidades
# ================================================================

class TestUtilidades(unittest.TestCase):

    def test_cuenta_en_rango_basico(self):
        self.assertTrue(cuenta_en_rango('510510', '5105', '5105'))
        self.assertTrue(cuenta_en_rango('510510', '5100', '5199'))
        self.assertFalse(cuenta_en_rango('520000', '5100', '5199'))

    def test_nombre_dice_compras(self):
        self.assertTrue(_nombre_dice_compras('COMPRAS DE MERCANCIA'))
        self.assertTrue(_nombre_dice_compras('compra a proveedores'))
        self.assertFalse(_nombre_dice_compras('SERV TRANSP. VÍA ACUÁTICA'))
        self.assertFalse(_nombre_dice_compras(''))

    def test_nombre_dice_traslado_costo(self):
        self.assertTrue(_nombre_dice_traslado_costo('CIERRE COSTOS INDIRECTOS'))
        self.assertTrue(_nombre_dice_traslado_costo('TRASLADO AL COSTO'))
        self.assertTrue(_nombre_dice_traslado_costo('Costo Traslado'))
        self.assertFalse(_nombre_dice_traslado_costo('SERVICIOS'))
        self.assertFalse(_nombre_dice_traslado_costo(''))


# ================================================================
# Tests de detectores
# ================================================================

class TestDetectores(unittest.TestCase):

    def test_activos_fijos_basicos(self):
        self.assertTrue(_es_cuenta_activos_fijos('150405', 'TERRENOS'))
        self.assertTrue(_es_cuenta_activos_fijos('152405', 'EQUIPO DE OFICINA'))

    def test_activos_fijos_excluye_depreciacion(self):
        self.assertFalse(_es_cuenta_activos_fijos('159205', 'DEPRECIACION ACUMULADA'))
        self.assertFalse(_es_cuenta_activos_fijos('158005', 'AMORTIZACION'))

    def test_inventarios_basicos(self):
        self.assertTrue(_es_cuenta_inventario_compra('143505', 'MERCANCIAS'))

    def test_inventarios_excluye_traslados(self):
        self.assertFalse(_es_cuenta_inventario_compra('143599', 'TRASLADO BODEGAS'))

    def test_cartera_1008(self):
        self.assertTrue(_es_cuenta_cartera_1008('130505'))
        self.assertTrue(_es_cuenta_cartera_1008('1315'))
        self.assertFalse(_es_cuenta_cartera_1008('1320'))   # 1320 fuera de rango
        self.assertFalse(_es_cuenta_cartera_1008('110505')) # caja no es cartera

    def test_f1003_cuentas(self):
        self.assertEqual(_es_cuenta_f1003('19551501')['prefijo'], '195515')
        self.assertEqual(_es_cuenta_f1003('13551501')['prefijo'], '135515')
        self.assertEqual(_es_cuenta_f1003('240810')['prefijo'], '240810')
        self.assertIsNone(_es_cuenta_f1003('110505'))

    def test_f1003_columnas_correctas(self):
        self.assertEqual(_es_cuenta_f1003('195515')['columna'], 'debitos_netos')
        self.assertEqual(_es_cuenta_f1003('135515')['columna'], 'debitos_netos')
        self.assertEqual(_es_cuenta_f1003('240810')['columna'], 'creditos')

    def test_subcuentas_2365(self):
        self.assertTrue(_es_cuenta_2365('236505'))
        self.assertTrue(_es_cuenta_2365('23652503'))
        self.assertTrue(_es_2365_salarios('236505'))
        self.assertTrue(_es_2365_salarios('23650510'))
        self.assertFalse(_es_2365_salarios('236525'))  # servicios, no salarios
        self.assertTrue(_es_2365_exceso('236555'))
        self.assertTrue(_es_2365_traslados('236599'))


# ================================================================
# Tests de conciliación cuenta 6 ↔ 72/73
# ================================================================

class TestConciliacionCostos(unittest.TestCase):

    def test_concilia_caso_rutas_mar(self):
        """Caso real de Rutas del Mar: cuenta 6 = $2.083M con cierre 73."""
        movs = [
            # Cuenta 6: SERV TRANSP (no dice "compras")
            Movimiento(codigo_cuenta='614515', nombre_cuenta='SERV TRANSP. VÍA ACUÁTICA',
                       debitos=2_083_924_872.05, creditos=0),
            # Mayor 73 en cero
            Movimiento(codigo_cuenta='73', nombre_cuenta='COSTOS INDIRECTOS',
                       debitos=2_283_410_687.05, creditos=2_283_410_687.05),
            # Cierre 73
            Movimiento(codigo_cuenta='739999', nombre_cuenta='CIERRE COSTOS INDIRECTOS',
                       debitos=0, creditos=2_083_924_872.05),
        ]
        res = validar_conciliacion_costos_traslado(movs)
        self.assertTrue(res.concilia)
        self.assertEqual(res.diferencia, 0.0)
        self.assertIn('614515', res.cuentas_6_excluidas)
        self.assertTrue(res.mayor_73_en_cero)

    def test_no_concilia_si_cuenta_6_dice_compras(self):
        """Una cuenta 6 con 'compras' NO se excluye (es pago real)."""
        movs = [
            Movimiento(codigo_cuenta='614505', nombre_cuenta='COMPRAS DE MERCANCIA',
                       debitos=1_000_000, creditos=0),
            Movimiento(codigo_cuenta='73', nombre_cuenta='COSTOS INDIRECTOS',
                       debitos=2_000_000, creditos=2_000_000),
            Movimiento(codigo_cuenta='739999', nombre_cuenta='CIERRE COSTOS',
                       debitos=0, creditos=1_000_000),
        ]
        res = validar_conciliacion_costos_traslado(movs)
        self.assertIn('614505', res.cuentas_6_con_compras)
        self.assertNotIn('614505', res.cuentas_6_excluidas)

    def test_no_concilia_si_mayor_73_no_esta_en_cero(self):
        movs = [
            Movimiento(codigo_cuenta='614515', nombre_cuenta='SERV TRANSP',
                       debitos=1_000_000, creditos=0),
            # Mayor 73 NO está en cero: hay $500k de descuadre
            Movimiento(codigo_cuenta='73', nombre_cuenta='COSTOS INDIRECTOS',
                       debitos=1_500_000, creditos=1_000_000),
            Movimiento(codigo_cuenta='739999', nombre_cuenta='CIERRE COSTOS',
                       debitos=0, creditos=1_000_000),
        ]
        res = validar_conciliacion_costos_traslado(movs)
        self.assertFalse(res.mayor_73_en_cero)
        self.assertFalse(res.concilia)
        self.assertEqual(len(res.cuentas_6_excluidas), 0)

    def test_no_concilia_si_montos_difieren(self):
        movs = [
            Movimiento(codigo_cuenta='614515', nombre_cuenta='SERV TRANSP',
                       debitos=1_000_000, creditos=0),
            Movimiento(codigo_cuenta='73', nombre_cuenta='COSTOS INDIRECTOS',
                       debitos=2_000_000, creditos=2_000_000),
            # Cierre con monto diferente al débito de cuenta 6
            Movimiento(codigo_cuenta='739999', nombre_cuenta='CIERRE COSTOS',
                       debitos=0, creditos=500_000),
        ]
        res = validar_conciliacion_costos_traslado(movs)
        self.assertFalse(res.concilia)
        self.assertEqual(res.diferencia, 500_000)

    def test_tolerancia_1_peso(self):
        """Diferencias de hasta $1 por redondeo deben aceptarse."""
        movs = [
            Movimiento(codigo_cuenta='614515', nombre_cuenta='SERV TRANSP',
                       debitos=1_000_000.50, creditos=0),
            Movimiento(codigo_cuenta='73', nombre_cuenta='COSTOS',
                       debitos=1_000_000, creditos=1_000_000),
            Movimiento(codigo_cuenta='739999', nombre_cuenta='CIERRE',
                       debitos=0, creditos=1_000_000),
        ]
        res = validar_conciliacion_costos_traslado(movs)
        self.assertTrue(res.concilia)


# ================================================================
# Tests de indexación de retenciones 2365
# ================================================================

class TestIndexacion2365(unittest.TestCase):

    def test_acumula_retencion_practicada_por_nit(self):
        movs = [
            # Mismo NIT con varias retenciones (compras, servicios)
            Movimiento(codigo_cuenta='23654020', nombre_cuenta='RETENCION COMPRAS 2.5%',
                       nit='800123456', creditos=100_000),
            Movimiento(codigo_cuenta='23652504', nombre_cuenta='RF SERVICIOS 4%',
                       nit='800123456', creditos=50_000),
            # Otro NIT
            Movimiento(codigo_cuenta='23652010', nombre_cuenta='COMISIONES 11%',
                       nit='900999111', creditos=200_000),
        ]
        idx = indexar_retenciones_2365(movs)
        self.assertEqual(len(idx), 2)
        self.assertEqual(idx['800123456'].f1001_retencion_practicada, 150_000)
        self.assertEqual(idx['900999111'].f1001_retencion_practicada, 200_000)

    def test_separa_salarios_de_otros(self):
        movs = [
            # Salario (irá a F2276)
            Movimiento(codigo_cuenta='236505', nombre_cuenta='RETEFUENTE SALARIOS',
                       nit='1234567', creditos=80_000),
            # Otro tipo (irá a F1001)
            Movimiento(codigo_cuenta='23652525', nombre_cuenta='TRANSPORTE 3.5%',
                       nit='1234567', creditos=20_000),
        ]
        idx = indexar_retenciones_2365(movs)
        self.assertEqual(idx['1234567'].f2276_retencion_salarios, 80_000)
        self.assertEqual(idx['1234567'].f1001_retencion_practicada, 20_000)

    def test_exceso_236555_en_campo_propio(self):
        movs = [
            # Retención normal
            Movimiento(codigo_cuenta='23654020', nombre_cuenta='COMPRAS 2.5%',
                       nit='800123456', creditos=100_000),
            # Retención en exceso (Db)
            Movimiento(codigo_cuenta='236555', nombre_cuenta='RETENCIONES EXCESO',
                       nit='800123456', debitos=523_250, creditos=0),
        ]
        idx = indexar_retenciones_2365(movs)
        self.assertEqual(idx['800123456'].f1001_retencion_practicada, 100_000)
        self.assertEqual(idx['800123456'].exceso_periodos_anteriores, 523_250)

    def test_traslados_236599_no_se_acumulan(self):
        movs = [
            # Traslado a la DIAN (pago, no se reporta)
            Movimiento(codigo_cuenta='23659901', nombre_cuenta='TRASLADOS',
                       nit='800197268', debitos=47_402_172),
        ]
        idx = indexar_retenciones_2365(movs)
        self.assertEqual(len(idx), 0)  # No se indexa la DIAN

    def test_movimientos_sin_nit_se_ignoran(self):
        movs = [
            Movimiento(codigo_cuenta='23654020', nombre_cuenta='COMPRAS 2.5%',
                       nit=None, creditos=100_000),
        ]
        idx = indexar_retenciones_2365(movs)
        self.assertEqual(len(idx), 0)


# ================================================================
# Tests de F1003
# ================================================================

class TestF1003(unittest.TestCase):

    def test_195515_usa_debitos_netos(self):
        mov = Movimiento(
            codigo_cuenta='19551501',
            nombre_cuenta='TRANSPORTE MARITIMO 1%',
            nit='800123456',
            debitos=8_821_392,
            creditos=1_190_000,
        )
        clasif = aplicar_regla_especial(mov)
        self.assertIsNotNone(clasif)
        self.assertEqual(clasif.formato_dian, '1003')
        self.assertEqual(clasif.valor, 8_821_392 - 1_190_000)
        self.assertEqual(clasif.base_aplicable, 'debitos_netos')

    def test_135515_usa_debitos_netos(self):
        mov = Movimiento(
            codigo_cuenta='13551501',
            nombre_cuenta='RETENCION FUENTE',
            nit='800123456',
            debitos=500_000,
            creditos=50_000,
        )
        clasif = aplicar_regla_especial(mov)
        self.assertIsNotNone(clasif)
        self.assertEqual(clasif.formato_dian, '1003')
        self.assertEqual(clasif.valor, 450_000)

    def test_240810_usa_creditos(self):
        mov = Movimiento(
            codigo_cuenta='240810',
            nombre_cuenta='RETEIVA POR PAGAR',
            nit='800123456',
            debitos=10_000,
            creditos=200_000,
        )
        clasif = aplicar_regla_especial(mov)
        self.assertIsNotNone(clasif)
        self.assertEqual(clasif.formato_dian, '1003')
        # créditos - débitos = 200000 - 10000 = 190000
        self.assertEqual(clasif.valor, 190_000)

    def test_f1003_no_reporta_si_neto_negativo(self):
        """Si Cr > Db en cuenta 195515 (reversión total), no reporta."""
        mov = Movimiento(
            codigo_cuenta='19551501',
            nombre_cuenta='RETENCION FUENTE',
            nit='800123456',
            debitos=100_000,
            creditos=200_000,  # más reversiones que retenciones
        )
        clasif = aplicar_regla_especial(mov)
        self.assertIsNone(clasif)


# ================================================================
# Tests de exclusión de cuentas 2365 del flujo
# ================================================================

class TestExclusion2365(unittest.TestCase):

    def test_cuenta_2365_marcada_columna_retencion(self):
        mov = Movimiento(
            codigo_cuenta='23654020',
            nombre_cuenta='RETENCION COMPRAS 2.5%',
            nit='800123456',
            creditos=100_000,
        )
        clasif = aplicar_regla_especial(mov)
        self.assertIsNotNone(clasif)
        self.assertEqual(clasif.formato_dian, 'COLUMNA_RETENCION')
        self.assertEqual(clasif.capa_resolucion, 'regla_especial_2365_columna')

    def test_236599_traslados_marcado_no_reporta(self):
        mov = Movimiento(
            codigo_cuenta='23659901',
            nombre_cuenta='TRASLADOS',
            nit='800197268',
            debitos=47_402_172,
        )
        clasif = aplicar_regla_especial(mov)
        self.assertIsNotNone(clasif)
        self.assertEqual(clasif.formato_dian, 'COLUMNA_RETENCION')
        self.assertIn('236599', clasif.nota)
        self.assertIn('traslado', clasif.nota.lower())


# ================================================================
# Tests de exclusión cuenta 6 conciliada
# ================================================================

class TestExclusionCuenta6(unittest.TestCase):

    def test_cuenta_6_excluida_si_concilia(self):
        mov = Movimiento(
            codigo_cuenta='614515',
            nombre_cuenta='SERV TRANSP. VÍA ACUÁTICA',
            debitos=2_083_924_872.05,
        )
        clasif = aplicar_regla_especial(mov, cuentas_6_excluidas={'614515'})
        self.assertIsNotNone(clasif)
        self.assertEqual(clasif.formato_dian, 'EXCLUIDO')
        self.assertEqual(clasif.capa_resolucion, 'regla_especial_costos_traslado_conciliado')

    def test_cuenta_6_no_excluida_si_no_esta_en_set(self):
        mov = Movimiento(
            codigo_cuenta='614505',
            nombre_cuenta='COMPRAS DE MERCANCIA',
            debitos=1_000_000,
        )
        # cuentas_6_excluidas no contiene 614505 → debe seguir flujo normal
        clasif = aplicar_regla_especial(mov, cuentas_6_excluidas=set())
        self.assertIsNone(clasif)  # cae a capas siguientes


# ================================================================
# Tests integración del MotorClasificacion
# ================================================================

class TestMotorIntegracion(unittest.TestCase):

    def setUp(self):
        # Reglas mínimas para tests
        self.capa1 = [
            ReglaCapa1(codigo_cuenta='5105', formato_dian='1001', concepto_dian=5001,
                       nombre_cuenta='SUELDOS'),
        ]
        self.capa2 = [
            ReglaCapa2(formato_dian='1001', concepto_dian=5004,
                       cuenta_inicial='5135', cuenta_final='5135',
                       descripcion_concepto='SERVICIOS', id=1),
        ]
        self.capa3 = []

    def test_motor_aplica_conciliacion_y_excluye_cuenta_6(self):
        motor = MotorClasificacion(self.capa1, self.capa2, self.capa3)
        movs = [
            Movimiento(codigo_cuenta='614515', nombre_cuenta='SERV TRANSP',
                       debitos=1_000_000, creditos=0),
            Movimiento(codigo_cuenta='73', nombre_cuenta='COSTOS',
                       debitos=2_000_000, creditos=2_000_000),
            Movimiento(codigo_cuenta='739999', nombre_cuenta='CIERRE COSTOS',
                       debitos=0, creditos=1_000_000),
        ]
        res = motor.clasificar_balance(movs)
        self.assertTrue(res.conciliacion_costos.concilia)
        # Las cuentas 6 deben aparecer marcadas como EXCLUIDO
        excluidos = [m for m in res.movimientos if m.formato_dian == 'EXCLUIDO']
        self.assertEqual(len(excluidos), 1)
        self.assertEqual(excluidos[0].codigo_cuenta, '614515')

    def test_motor_indexa_retenciones_por_nit(self):
        motor = MotorClasificacion(self.capa1, self.capa2, self.capa3)
        movs = [
            Movimiento(codigo_cuenta='23654020', nombre_cuenta='COMPRAS 2.5%',
                       nit='800123456', creditos=100_000),
            Movimiento(codigo_cuenta='23652504', nombre_cuenta='RF SERVICIOS 4%',
                       nit='800123456', creditos=50_000),
        ]
        res = motor.clasificar_balance(movs)
        self.assertIn('800123456', res.retenciones_por_nit)
        self.assertEqual(
            res.retenciones_por_nit['800123456'].f1001_retencion_practicada,
            150_000
        )

    def test_motor_capa3_supera_a_reglas_especiales(self):
        """Si hay override manual, gana sobre reglas especiales."""
        capa3 = [
            ReglaCapa3(codigo_cuenta='614515', nit='800123456',
                       formato_dian='1001', concepto_dian=5004,
                       nota='Reportar como pago a tercero'),
        ]
        motor = MotorClasificacion(self.capa1, self.capa2, capa3)
        movs = [
            Movimiento(codigo_cuenta='614515', nit='800123456',
                       nombre_cuenta='SERV TRANSP',
                       debitos=1_000_000, creditos=0),
            Movimiento(codigo_cuenta='73', nombre_cuenta='COSTOS',
                       debitos=1_000_000, creditos=1_000_000),
            Movimiento(codigo_cuenta='739999', nombre_cuenta='CIERRE',
                       debitos=0, creditos=1_000_000),
        ]
        res = motor.clasificar_balance(movs)
        # Aunque la conciliación marca 614515 como excluida, capa 3 manda
        clasificacion_614515 = [m for m in res.movimientos if m.codigo_cuenta == '614515']
        self.assertEqual(len(clasificacion_614515), 1)
        self.assertEqual(clasificacion_614515[0].capa_resolucion, 'mapeo_manual')
        self.assertEqual(clasificacion_614515[0].formato_dian, '1001')

    def test_estadisticas_completas(self):
        motor = MotorClasificacion(self.capa1, self.capa2, self.capa3)
        movs = [
            # Activos fijos (regla especial)
            Movimiento(codigo_cuenta='152405', nombre_cuenta='EQUIPO OFICINA',
                       nit='800111', debitos=500_000),
            # Capa 1
            Movimiento(codigo_cuenta='5105', nit='800222', debitos=1_000_000),
            # Sin resolver
            Movimiento(codigo_cuenta='999999', nit='800333', debitos=100_000),
        ]
        res = motor.clasificar_balance(movs)
        stats = res.estadisticas
        self.assertEqual(stats['total_movimientos'], 3)
        self.assertGreaterEqual(stats['regla_especial'], 1)
        self.assertGreaterEqual(stats['capa1'], 1)
        self.assertGreaterEqual(stats['sin_resolver'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
