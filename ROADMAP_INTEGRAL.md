# Roadmap INTEGRAL — todas las funcionalidades de Contai (y luego mejoras)

> Objetivo: cubrir **todo el ciclo contable de Contai** en INTEGRAL y después
> agregar mejoras (cubos de saldos, medios magnéticos avanzados, etc.).
> Estado: ✅ hecho · 🟡 parcial · ⬜ pendiente. Todo desemboca en `cn_movimientos`.

---

## FASE 0 — Núcleo (base de todo) ✅ COMPLETA
- ✅ Modelo de datos `cn_*` (migración 014): períodos, parámetros, plan de
  cuentas, centros de costo, comprobantes, movimientos, valores anuales,
  calendario tributario, municipios.
- ✅ Capa de servicio `core/contable/servicio_contable.py`.
- ✅ Guardar/leer movimiento · cuadre por período · períodos abrir/proteger.

## FASE 1 — Entrada de información ✅ COMPLETA (3 vías)
- ✅ **Masiva / tareas largas**: planos de nómina, vacaciones, ajuste PILA →
  botón "Guardar plano del mes".
- ✅ **Históricos**: importar plano (.txt/.xlsx) → deriva período de la fecha.
- ✅ **Día a día**: captura de comprobantes en partida doble (egreso,
  causación, recibo de caja, nota) con validación de cuadre.

## FASE 2 — Informes contables 🟡 EN CURSO
- ✅ Balance de prueba (saldo ant · Db · Cr · saldo final)
- ✅ Libro auxiliar (por cuenta / tercero, con saldo corriente)
- ✅ Estado de cartera (saldo por tercero)
- ✅ **Estado de resultados (PyG)**  ← recién agregado
- ✅ **Balance general** (con ecuación patrimonial)  ← recién agregado
- ⬜ Libro mayor y balances (por cuenta mayor, niveles)
- ⬜ Libros oficiales (Diario, Mayor) con numeración de folios
- ⬜ Comprobante de diario (impresión del asiento)
- ⬜ Comparativos entre períodos / años

## FASE 3 — Maestros que faltan ⬜ PENDIENTE
- ⬜ **Terceros** (maestro de NITs: nombre, tipo, régimen) — hoy solo se
  guarda el NIT en el movimiento. Habilita autocompletar y mejores reportes.
- 🟡 Plan de cuentas: tabla lista; falta **página de gestión** (crear/editar,
  importar PUC completo desde `CNCTCIAL.btv`).
- 🟡 Centros de costo: tabla lista; falta página de gestión.
- ⬜ Bancos / cuentas bancarias (para conciliación).
- ⬜ Activos fijos (para depreciación).

## FASE 4 — Procesos contables ⬜ PENDIENTE
- ⬜ **Cierre anual** (cancelar 4-5-6-7 contra utilidad del ejercicio 3605).
- ⬜ **Conciliación bancaria** (módulo `CNCONCIA` de Contai): cruzar extracto
  vs libros, partidas conciliatorias.
- ⬜ Depreciación de activos fijos.
- ⬜ Amortización de diferidos.
- ⬜ Documentos recurrentes / plantillas de asiento.
- ⬜ Numeración/consecutivos automáticos por comprobante.

## FASE 5 — Tributario / anexos 🟡 YA EXISTE MUCHO EN EL REPO
- ✅ Retención en la fuente + F350 (con JSON para la extensión).
- ✅ IVA y reteIVA · Impuestos saludables · Declaración de renta.
- ✅ **Medios magnéticos / Información exógena** (módulo `exogena` ya existe).
- ✅ Compras/Ventas DIAN, RADIAN, factura electrónica, Siigo, Bancos a Contai.
- ⬜ Certificados de retención (impresión masiva) — tabla `CNIMPCER` de Contai.

## FASE 6 — Sistema 🟡 PARCIAL
- ✅ Multiempresa + login Supabase + roles (admin/operador/consulta) + RLS.
- ✅ Configuración por empresa (parámetros).
- 🟡 Auditoría / traza (Contai la tiene; falta bitácora de cambios).
- ⬜ Copias de seguridad / exportación por período.
- 🟡 Panel admin (existe; ampliar gestión de usuarios/permisos por opción).

---

## MEJORAS (después del núcleo) — lo que pediste dejar para el final
- ⬜ **Cubos de saldos** (tabla dinámica/OLAP: saldo por cuenta × centro de
  costo × período × tercero, con filtros y export). Contai lo llama "Cubos".
- ⬜ **Medios magnéticos avanzados**: más formatos DIAN, validaciones y XML.
- ⬜ Dashboards / indicadores (razones financieras, tendencias).
- ⬜ Presupuestos (Contai los maneja; el add-in de Excel tenía `CsPresupuesto`).
- ⬜ NIIF: cuenta equivalente, ESF/ERI bajo NIIF.
- ⬜ Reportes en PDF con membrete (libros oficiales firmados).

---

## Orden sugerido para seguir (mi recomendación)
1. **Terceros** (maestro) — desbloquea autocompletar y cartera con nombres.
2. **Gestión de Plan de cuentas y Centros de costo** (+ importar PUC de Contai).
3. **Libro mayor y balances** + **comprobante de diario** (cierra los informes).
4. **Cierre anual** (proceso).
5. **Conciliación bancaria** (módulo CNCONCIA).
6. Luego las **mejoras**: cubos de saldos, presupuestos, NIIF, PDFs oficiales.

> Cada item es una entrega chica y verificable, como venimos haciendo. Dime si
> el orden te sirve o quieres priorizar otro (p. ej. cierre anual antes que
> terceros), y arranco por ahí.
