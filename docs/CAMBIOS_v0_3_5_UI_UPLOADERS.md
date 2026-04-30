# 📝 CAMBIOS UI v0.3.5 — Uploaders simplificados (30-04-2026)

> **Petición del usuario:** Como ahora el bookmarklet v0.3 descarga TODO en un
> solo ZIP, no tiene sentido seguir mostrando 4 cajas de upload separadas.
> Reemplazarlas por una sola caja "Recibidos" + una nueva "Emitidos".

---

## ✅ Cambios en la UI

### Antes (v0.2):

```
┌──────────┬──────────┬──────────┬──────────┐
│   📄 FE  │   🔻 NC  │   🔺 ND  │  🏛️ SP   │
│  [Subir] │  [Subir] │  [Subir] │  [Subir] │
└──────────┴──────────┴──────────┴──────────┘
```

### Ahora (v0.3.5):

```
┌────────────────────────┬────────────────────────┐
│  📥 Documentos         │  📤 Documentos         │
│     RECIBIDOS          │     EMITIDOS           │
│  (todos los tipos en   │  🚧 Próximamente       │
│   un solo ZIP)         │   (caja deshabilitada) │
│  [Subir]               │  [Subir disabled]      │
└────────────────────────┴────────────────────────┘
```

### Beneficios

1. **Más simple para el usuario:** una sola caja para subir lo que descargó del bookmarklet.
2. **Coherente con el bookmarklet v0.3:** que ahora descarga todo unido.
3. **Detección automática del tipo** desde el prefijo del nombre de archivo
   (`FE_…`, `NC_…`, `ND_…`, `DS_…`, `??_…`) o desde el contenido del XML.
4. **Caja Emitidos visible pero deshabilitada** — comunica al usuario que
   esa función viene en la siguiente versión sin abrir confusión.

---

## 🎯 Decisiones tomadas sobre EMITIDOS (próxima fase)

El usuario confirmó:

| Punto | Decisión |
|---|---|
| Alcance | Solo **FE de venta** emitidas a clientes |
| Comprobante | **4 — Ingresos** (Siigo) |
| Por ahora | Caja deshabilitada con mensaje "Próximamente" |
| NC y ND emitidas | NO se procesan en esta fase |

Ver detalle en `docs/decisiones/EMITIDOS_silla_tres.md`.

### Lógica contable a implementar (próxima sesión)

Cuando se active la caja, generará asientos así:

```
DB  13050501  CLIENTES NACIONALES               $ valor_total
    CR  41xxxx (cuenta de ingreso por servicio)        $ base
    CR  24080xxx (IVA generado)                        $ iva

# Si el cliente le practica retenciones a Silla Tres:
DB  135515xx (anticipo retefuente)              $ retfuente_que_le_practican
DB  135517xx (anticipo reteIVA)                 $ reteIVA_que_le_practican
    (resta del valor a cobrar al cliente)
```

### Prerequisitos antes de implementar

1. **Catálogo de clientes** (`mapeo_clientes.json`) — mapeo NIT cliente
   → cuenta ingreso + cuenta cliente preferida
2. **Plan de cuentas de ingresos por servicio o local** — qué cuenta 41xxxx
   usar según el ítem facturado
3. **Cuentas de anticipos de impuestos** — para las retenciones que los
   clientes le practican a Silla Tres
4. **Reglas de comprobante 4** — formato esperado por Siigo

---

## ⏳ Estado actual del código

### ✅ Listo

- Página rediseñada con caja única de Recibidos + caja Emitidos deshabilitada.
- Lectura del ZIP de Recibidos y paso al procesador legacy v0.2.
- 276 líneas (vs 598 originales) — código más limpio y mantenible.

### ⏳ Pendiente integrar

1. **Conectar el motor v0.3 al procesador legacy** (`procesador_dian_xml.py`):
   - Hoy usa el `mapeo_nits.json` antiguo (6 NITs).
   - Debe llamar a `motor_mapeo_v03.resolver_mapeo()` con los 126 NITs
     aprendidos del BP.
   - Y a `detector_tipo_doc.detectar_tipo_documento()` para los comprobantes
     3/7/12 automáticos.

2. **Procesamiento de Emitidos** (cuando estén listos los prerequisitos).

---

## 🚀 Cómo aplicar el cambio en producción

1. En GitHub, abrir `pages/5_📥_DIAN_XML.py`
2. Reemplazar todo el contenido con el archivo nuevo
3. Commit
4. Esperar a Railway (1-3 min)

⚠️ **Importante:** El procesador legacy NO está integrado aún con el motor
v0.3, por lo que el plano que se genere usará la lógica vieja (6 NITs). La
UI muestra un mensaje informativo aclarando que la integración completa
viene en la próxima sesión.
