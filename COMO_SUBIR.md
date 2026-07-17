# INTEGRAL — rebranding + guardar plano en la base

## Archivos (todos REEMPLAZAN / NUEVOS)
    Home.py                              (REEMPLAZA — ahora se llama "INTEGRAL")
    README.md                            (REEMPLAZA — título INTEGRAL)
    app_pages/3_Nomina.py                (REEMPLAZA — botón "Guardar plano del mes")
    core/contable/__init__.py            (NUEVO)
    core/contable/servicio_contable.py   (NUEVO/actualizado — crear_periodo seguro)

(La migración 014_nucleo_contable.sql ya la corriste en Supabase.)

## Qué cambia
1) NOMBRE: la app aparece como "INTEGRAL" (pestaña del navegador, título de
   inicio "📊 INTEGRAL — Gestión contable integral") y en el README.
2) GUARDAR EN LA BASE: en Nómina, bajo "Plano del mes", hay un botón
   "💾 Guardar plano del mes (AAAAMM) en INTEGRAL" que:
     - crea el período si no existe (sin reabrir uno protegido),
     - guarda el plano combinado (nómina + vacaciones + ajuste PILA) en
       cn_movimientos con origen='nomina_mes',
     - con "Reemplazar" borra primero lo de ese período/origen (no duplica).
   Si el período está PROTEGIDO, bloquea el guardado.

## Seguridad
- servicio_contable.crear_periodo ahora usa ignore_duplicates: si el período
  ya existe, NO lo modifica (así no reabre un período protegido por accidente).
