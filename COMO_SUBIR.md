# Cómo subir estos archivos (plataforma-contable)

Todo se maneja DENTRO del módulo de Nómina. NO se crea página nueva.

Rutas EXACTAS:
    app_pages/3_Nomina.py                (REEMPLAZA)
    core/lectores/lector_vacaciones.py   (NUEVO)

## Qué hace
- Tercer cargador OPCIONAL en "Procesar nómina": Vacaciones y liquidaciones
  definitivas (varios PDF a la vez), para cuando aparezcan en el mes.
- VACACIONES: extrae datos, aplica 4% pensión + 4% salud sobre el total y
  genera el plano contable Comp 11 (cuadrado):
      Db 25301501  Pago de vacaciones           (total)
      Cr 25503002  Aporte pensión trabajador 4%
      Cr 25500502  Deducción salud trabajador 4%
      Cr 25050501  Neto a pagar
- LIQUIDACIÓN DEFINITIVA: muestra conceptos; las vacaciones ahí NO llevan 4%+4%.

## IMPORTANTE — corrección de Contai
El plano .txt se descarga SIN encabezado (solo registros de datos). Antes se
incluían las filas "sep=" y los títulos de columna (CUENTA, COMPROBANTE...),
que Contai leía como un registro y generaba inconsistencias
("la cuenta NO existe en el Plan de Cuentas"). Ahora el primer renglón del
.txt ya es la primera cuenta real (25301501).

Ejemplo validado (María Yorladis, mayo 2026):
  TOTAL 1.870.741 -> pensión 74.830 + salud 74.829 = 149.659 -> neto 1.721.082.
