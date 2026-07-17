# Cómo subir (plataforma-contable) — todo dentro de Nómina

Rutas EXACTAS (3 archivos):
    app_pages/3_Nomina.py                     (REEMPLAZA)
    core/procesadores/procesador_nomina.py    (REEMPLAZA)
    core/lectores/lector_vacaciones.py        (REEMPLAZA)

## Cambios de esta versión
1) CONSECUTIVO DE NÓMINA: ahora es 1 documento por EMPLEADO y por QUINCENA.
   - Q1 usa documentos 1..N, Q2 continúa en N+1..2N (comp 11), sin repetir números.
   - La provisión sigue en comp 9, documento = número del mes.

2) UN SOLO PLANO DEL MES: al final de "Procesar nómina" hay una sección
   "Plano del mes (nómina + vacaciones)" que une TODO en un solo .txt/.xlsx.
   - Las vacaciones entran en el mismo comp 11, con documento que continúa el
     consecutivo de la nómina (no quedan planos regados).
   - El .txt sale SIN encabezado (solo registros), listo para Contai.

3) BASE IBC OPCIONAL EN VACACIONES: por cada vacación puedes marcar
   "La SS cotiza sobre un IBC distinto al valor liquidado" e ingresar el IBC.
   - Sin marcar: 4%+4% sobre el total de la vacación (como el documento).
   - Marcado: 4%+4% sobre el IBC que va a la PILA (ej. María Yorladis
     IBC 1.050.543 -> pensión 42.022 + salud 42.021 = 84.043).

## Pendiente (para cerrar la conciliación PILA -> gasto)
- Confirmar cuentas de gasto (5204xx / 5104xx) para el ajuste automático
  provisión/deducción vs PILA.
- Revisar la provisión de ARL (se veía ~3,5x sobre lo que cobra la PILA).
