# Cómo subir (plataforma-contable) — todo dentro de Nómina

Rutas EXACTAS (4 archivos):
    app_pages/3_Nomina.py                     (REEMPLAZA)
    core/procesadores/procesador_nomina.py    (REEMPLAZA)
    core/procesadores/ajuste_pila.py          (NUEVO)
    core/lectores/lector_vacaciones.py        (REEMPLAZA)

## NUEVO en esta versión: Conciliación PILA -> gasto (ajuste comp 9)
Cuando subes NÓMINA + PILA (y opcional vacaciones), aparece la sección
"Conciliación PILA -> gasto". Por cada concepto (pensión, EPS/salud, ARL,
caja) compara el pasivo contable del mes (causación + provisión + vacaciones)
contra la PILA y genera el AJUSTE en el comp 9 (mismo documento de la
provisión), poniendo Db o Cr contra el gasto del concepto, hasta dejar el
pasivo del mes = saldo PILA. Todo se une al plano del mes.

Regla aplicada:
  diferencia = PILA - contable
    diferencia > 0 (falta pasivo):  Db gasto / Cr pasivo
    diferencia < 0 (sobra pasivo):  Db pasivo / Cr gasto

### Cuentas de gasto (editable en pantalla)
- Pensión 510470, ARL 510468, Caja 510472 vienen precargadas (las del módulo).
- GASTO EPS: la empresa está exonerada, así que NO hay una cuenta EPS por
  defecto. Escríbela en el campo "Gasto EPS"; si la dejas vacía, ese concepto
  NO se ajusta y se avisa.
- Puedes cambiar cualquiera de las 4 cuentas según tu PUC real.

Ejemplo con las cifras de mayo (de tus capturas):
  Pensión  PILA 2.124.500 vs Contai 2.031.123 -> Db gasto/Cr pasivo 93.377
  EPS      PILA   531.400 vs Contai   563.902 -> Db pasivo/Cr gasto 32.502
  ARL      PILA    64.100 vs Contai   222.633 -> Db pasivo/Cr gasto 158.533
  Caja     PILA   531.400 vs Contai   489.073 -> Db gasto/Cr pasivo 42.327
  (revisa la provisión de ARL: quedó ~3,5x sobre lo que cobra la PILA)

## Recordatorios de versiones anteriores
- Consecutivo de nómina: 1 documento por empleado y por quincena (comp 11).
- Un solo plano del mes (nómina + vacaciones + ajuste PILA), .txt sin encabezado.
- Vacaciones: 4%+4%; base IBC opcional por vacación.
