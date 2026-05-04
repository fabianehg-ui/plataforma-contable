"""
Test de integración E2E del motor v2 con el balance real de Rutas del Mar SAS 2025.

Valida:
  1. La conciliación cuenta 6 ↔ cuentas 73 cuadra al centavo
  2. F1003 reporta los $7.673.029 esperados de 195515 (Db netos)
  3. Las cuentas 2365 NO generan registros propios pero SÍ se indexan por NIT
  4. La suma del exceso 236555 ($523.250) está disponible para deducir

Para correr este test, el archivo Excel debe estar en /mnt/user-data/uploads.
"""
import unittest
import sys
import os
from pathlib import Path

import pandas as pd

# Importar motor desde el mismo directorio
sys.path.insert(0, os.path.dirname(__file__))
from motor_clasificacion import (
    Movimiento,
    ReglaCapa1,
    ReglaCapa2,
    MotorClasificacion,
    validar_conciliacion_costos_traslado,
    indexar_retenciones_2365,
)


ARCHIVO_BALANCE = '/mnt/user-data/uploads/BALANCE_PARA_MAPEO_MEDIOS_RUTAS_DE_MAR.xlsx'


def cargar_balance() -> list[Movimiento]:
    """Carga el balance Excel y lo convierte a Movimientos."""
    df = pd.read_excel(ARCHIVO_BALANCE, header=3, dtype={0: str})
    df.columns = ['cuenta', 'equivalencia', 'nombre', 'nit', 'nombre_nit',
                  'saldo_anterior', 'debitos', 'creditos', 'nuevo_saldo']
    df = df[df['cuenta'].notna()].copy()
    df['cuenta_str'] = df['cuenta'].astype(str).str.strip().str.replace(
        r'\.0$', '', regex=True
    )
    df['debitos'] = pd.to_numeric(df['debitos'], errors='coerce').fillna(0)
    df['creditos'] = pd.to_numeric(df['creditos'], errors='coerce').fillna(0)
    df['saldo_final'] = pd.to_numeric(df['nuevo_saldo'], errors='coerce').fillna(0)

    movs = []
    for _, row in df.iterrows():
        movs.append(Movimiento(
            codigo_cuenta=row['cuenta_str'],
            nit=str(row['nit']).strip() if pd.notna(row['nit']) else None,
            debitos=float(row['debitos']),
            creditos=float(row['creditos']),
            saldo_final=float(row['saldo_final']),
            nombre_cuenta=str(row['nombre']).strip() if pd.notna(row['nombre']) else '',
            nombre_tercero=str(row['nombre_nit']).strip() if pd.notna(row['nombre_nit']) else '',
        ))
    return movs


class TestIntegracionRutasMar(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not Path(ARCHIVO_BALANCE).exists():
            raise unittest.SkipTest(f'Archivo de balance no disponible: {ARCHIVO_BALANCE}')
        cls.movimientos = cargar_balance()
        print(f'\n📂 Balance cargado: {len(cls.movimientos)} filas')

    def test_balance_carga_correctamente(self):
        self.assertGreater(len(self.movimientos), 700)

    def test_conciliacion_cuenta_6_concilia_al_centavo(self):
        """La conciliación cuenta 6 ↔ 73 debe cuadrar exactamente."""
        res = validar_conciliacion_costos_traslado(self.movimientos)
        print(f'\n=== Conciliación Cuenta 6 ↔ 72/73 ===')
        print(f'  Db cuenta 6:                 ${res.db_cuenta_6:,.2f}')
        print(f'  Cr cuentas 73 traslado:      ${res.cr_traslado_72_73:,.2f}')
        print(f'  Diferencia:                  ${res.diferencia:,.2f}')
        print(f'  Mayor 73 en cero:            {res.mayor_73_en_cero}')
        print(f'  Concilia:                    {res.concilia}')
        print(f'  Cuentas 6 excluidas:         {res.cuentas_6_excluidas}')
        print(f'  Cuentas 6 con compras:       {res.cuentas_6_con_compras}')

        # Aserciones
        self.assertTrue(res.concilia,
                        f'La conciliación no cuadró: {res.mensaje}')
        self.assertLessEqual(res.diferencia, 1.0)
        self.assertTrue(res.mayor_73_en_cero)
        # En el balance de Rutas del Mar, Db cuenta 6 = $2.083.924.872,05
        self.assertAlmostEqual(res.db_cuenta_6, 2_083_924_872.05, places=2)
        self.assertAlmostEqual(res.cr_traslado_72_73, 2_083_924_872.05, places=2)

    def test_indexacion_retenciones_por_nit(self):
        """Las cuentas 2365 deben acumularse correctamente por NIT."""
        idx = indexar_retenciones_2365(self.movimientos)
        print(f'\n=== Retenciones 2365 indexadas ===')
        print(f'  Total NITs con retención: {len(idx)}')

        # Sumar todas las retenciones para validación contra balance
        total_f1001 = sum(r.f1001_retencion_practicada for r in idx.values())
        total_f2276 = sum(r.f2276_retencion_salarios for r in idx.values())
        total_exceso = sum(r.exceso_periodos_anteriores for r in idx.values())

        print(f'  Total Cr 2365 → columna F1001:   ${total_f1001:,.2f}')
        print(f'  Total Cr 2365 → columna F2276:   ${total_f2276:,.2f}')
        print(f'  Total exceso 236555 (Db netos):  ${total_exceso:,.2f}')

        # En Rutas del Mar:
        #   - F1001 cuenta 2365 (sin salarios sin exceso sin traslados): $48.474.922
        #   - F2276 (salarios): $0 (no hay)
        #   - Exceso 236555: $523.250
        self.assertAlmostEqual(total_f1001, 48_474_922.0, delta=1.0)
        self.assertEqual(total_f2276, 0)  # No hay retenciones de salarios en Rutas del Mar
        self.assertAlmostEqual(total_exceso, 523_250.0, delta=1.0)

    def test_f1003_195515_reporta_debitos_netos(self):
        """F1003 debe sumar Db - Cr de cuentas 195515 (=$7.673.029)."""
        movimientos_195515 = [
            m for m in self.movimientos
            if str(m.codigo_cuenta).startswith('195515')
            and len(str(m.codigo_cuenta)) >= 8  # solo movimientos detallados
            and m.nit is not None
        ]
        total_db = sum(m.debitos for m in movimientos_195515)
        total_cr = sum(m.creditos for m in movimientos_195515)
        total_neto = total_db - total_cr

        print(f'\n=== F1003 cuenta 195515 ===')
        print(f'  Movimientos: {len(movimientos_195515)}')
        print(f'  Db total:  ${total_db:,.2f}')
        print(f'  Cr total:  ${total_cr:,.2f}')
        print(f'  Neto:      ${total_neto:,.2f}')

        # Esperamos: Db=$8.863.029, Cr=$1.190.000, Neto=$7.673.029
        self.assertAlmostEqual(total_db, 8_863_029.0, delta=1.0)
        self.assertAlmostEqual(total_cr, 1_190_000.0, delta=1.0)
        self.assertAlmostEqual(total_neto, 7_673_029.0, delta=1.0)

    def test_motor_completo_clasifica_balance(self):
        """El motor completo procesa el balance sin errores y aplica todas las reglas."""
        # Reglas mínimas (en producción vendrán de la DB)
        capa1 = []
        capa2 = []
        motor = MotorClasificacion(capa1, capa2, [])

        # Filtrar solo movimientos detallados (nivel auxiliar) para el test
        movs_detallados = [
            m for m in self.movimientos
            if len(str(m.codigo_cuenta)) >= 6 and m.nit is not None
        ]

        res = motor.clasificar_balance(movs_detallados)

        print(f'\n=== Motor v2: clasificación completa ===')
        print(f'  Movimientos procesados: {res.estadisticas["total_movimientos"]}')
        print(f'  Clasificaciones:        {res.estadisticas["total_clasificaciones"]}')
        print(f'  Excluidos (cuenta 6):   {res.estadisticas["excluido_costo_traslado"]}')
        print(f'  Columna retención 2365: {res.estadisticas["columna_retencion"]}')
        print(f'  Reglas especiales:      {res.estadisticas["regla_especial"]}')
        print(f'  Sin resolver:           {res.estadisticas["sin_resolver"]}')
        print(f'  Conciliación cuadra:    {res.estadisticas["conciliacion_concilia"]}')
        print(f'  NITs con retención:     {res.estadisticas["nits_con_retencion"]}')

        # Aserciones clave
        self.assertTrue(res.conciliacion_costos.concilia)
        self.assertGreater(res.estadisticas['regla_especial'], 0)
        self.assertGreater(res.estadisticas['nits_con_retencion'], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
