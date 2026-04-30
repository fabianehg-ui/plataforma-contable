# Decisiones — Procesamiento de Documentos Emitidos (Silla Tres SAS)

> Fecha: 30-04-2026
> Estado: pendiente implementación, definiciones cerradas

## Alcance
Solo **FE de venta** emitidas a clientes. NO procesar NC ni ND emitidas
en esta fase.

## Comprobante contable
**Comprobante 4 — Ingresos** (Siigo)

## Mapeo de tipos para emitidos
```
FE (Invoice / InvoiceTypeCode=01)  → Comprobante 4 (Ingresos)
NC (CreditNote)                    → ignorar por ahora (próxima fase)
ND (DebitNote)                     → ignorar por ahora (próxima fase)
ApplicationResponse                → ignorar (acuse)
```

## Lógica contable a implementar (próxima sesión)
- Cliente (DB cuenta x cobrar 13050501) por valor total
- Ingreso (CR cuenta de ingreso 41xxxx) por base
- IVA generado (CR 24080xxx) por valor IVA
- Retenciones que el cliente le practique a Silla Tres:
  vienen como `WithholdingTaxTotal` en el XML emitido y van DB en cuentas
  de anticipo de impuestos (135515xx, 135517xx, etc.)

## Prerequisitos pendientes
1. Catálogo de clientes (mapeo NIT receptor → cuenta de ingreso)
2. Plan de cuentas de ingresos por servicio/local
3. Cuentas de anticipos de impuestos (retenciones que le practican)
