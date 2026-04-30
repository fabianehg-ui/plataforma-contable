# 🐛 FIX v0.3.4 — Bug del descargador (30-04-2026)

> **Problema reportado:** El bookmarklet v0.2 listaba 151 documentos en cada
> uno de los 4 tipos (FE: 151, NC: 151, ND: 151, DS: 151 = 604 total),
> cuando el listado real tenía solo 151 documentos únicos.

---

## 🔍 Diagnóstico

El bookmarklet v0.2 hacía 4 listados al portal DIAN, uno por cada
`DocumentTypeId` (01, 91, 92, 05), confiando en que el portal filtrara
correctamente.

**Pero el portal DIAN tiene un bug:**

> El parámetro `DocumentTypeId` del endpoint `/Document/GetDocumentsPageToken`
> NO filtra correctamente. Sin importar qué valor le envíes, el portal
> devuelve siempre **el listado completo de todos los tipos**.

Resultado: el bookmarklet descargaba 4 veces los mismos 151 documentos =
604 archivos en el ZIP, todos duplicados.

Esto coincide con lo que el usuario observó en una sesión anterior cuando
descargaba "Todos" desde el desplegable del portal: el filtro no funcionaba.

---

## ✅ Solución v0.3 (LISTADO ÚNICO)

**Cambio de estrategia:**
- Hacer **UN SOLO listado** sin filtrar por tipo (`DocumentTypeId=''`).
- Detectar el tipo de cada documento desde la respuesta JSON misma,
  buscando en campos como `DocumentType`, `TipoDocumento`, etc.
- Deduplicar por `trackId` antes de descargar.

### Detector de tipo en el bookmarklet

Busca en estos campos de la fila (en orden):
1. `DocumentType`, `TipoDocumento`, `documentType`
2. `DocumentTypeName`, `DocumentTypeDescription`
3. `TipoDoc`, `tipoDoc`
4. `DocumentTypeId`, `documentTypeId`

Mapea el contenido a `FE`/`NC`/`ND`/`DS`:
- Códigos numéricos (`01`/`91`/`92`/`05`) → directo
- Texto descriptivo:
  - `"Factura"`, `"Invoice"`, `"FE"` → FE
  - `"Nota crédito"`, `"Credit Note"` → NC
  - `"Nota débito"`, `"Debit Note"` → ND
  - `"Documento soporte"`, `"Doc. Soporte"`, `"Support"` → DS

Si no se detecta → marca como `??` y el procesador del lado servidor lo
identifica al abrir el XML (ya tenemos `detector_tipo_doc.py`).

### Fallback: prefijo `??_`

Si el bookmarklet no logra detectar el tipo, los archivos quedan así:
```
??_2026-03-15_900040299_FAT123_a1b2c3d4.zip
```

El procesador `detector_tipo_doc.py` ve el `??_`, sabe que no hay info
del nombre, y abre el XML para detectar el tipo desde el contenido
(tag `<Invoice>` / `<CreditNote>` / `<DebitNote>` / `<ApplicationResponse>`
+ `InvoiceTypeCode`).

---

## 📦 Archivos modificados

```
v03/bookmarklet/
├── dian_descargador_v03.js                       ⭐ NUEVO
├── dian_descargador_v03_INLINE.txt               ⭐ Versión minificada
├── dian_descargador_v02.js                       (deprecada, conservada)
└── dian_descargador_v02_INLINE.txt               (deprecada, conservada)
```

**Importante:** Si ya tienes el bookmarklet v0.2 instalado, debes:
1. Eliminar el marcador anterior
2. Crear uno nuevo con el contenido de `dian_descargador_v03_INLINE.txt`

---

## 🧪 Cómo se ve la nueva interfaz

```
┌─────────────────────────────────────┐
│ 📥 Descargador DIAN — TODO v0.3   ×│
├─────────────────────────────────────┤
│ Empresa: SILLA TRES S.A.S          │
│                                     │
│ Fecha desde   │  Fecha hasta       │
│ 2026-03-01    │  2026-03-31        │
│                                     │
│ 📦 Descarga todos los documentos    │
│ recibidos (FE + NC + ND + DS)...   │
│                                     │
│ [    Descargar TODO    ]           │
│                                     │
│ ┌────┬────┬────┬────┬────┐         │
│ │ FE │ NC │ ND │ DS │ ?? │         │
│ │145 │ 5  │ 1  │ 0  │ 0  │  ← ahora REALES
│ └────┴────┴────┴────┴────┘         │
│                                     │
│ 151 listados | 0 bajados | 0 fall. │
│                                     │
│ [Listando documentos del 2026-...] │
│ [Total reportado por DIAN: 151]    │
│ [Total documentos únicos: 151]     │ ← ya no duplicados
└─────────────────────────────────────┘
```

Ahora se ve también la columna **"??"** que cuenta los documentos
sin tipo detectable (debería ser 0 o muy bajo).

---

## ⚠️ Diagnóstico adicional

Si todos los documentos te quedan como `??`, es señal de que el portal
de la DIAN no está devolviendo el tipo en ningún campo conocido. En ese
caso, el bookmarklet imprime en la consola (F12) los campos disponibles
de la primera fila para diagnosticar.

Por ejemplo, en la consola verás:
```
[DIAN-DL] Primera fila para diagnóstico: {DocumentKey: "...", IssueDate: "...", ...}
```

Comparte esa lista de campos y agrego más reglas de detección.

**El procesador del servidor seguirá funcionando aunque todos sean `??`**
porque detecta el tipo desde el XML cuando se procesa.

---

## 🔧 Pasos para validar el fix

1. Eliminar el bookmarklet v0.2 actual de tus marcadores
2. Crear uno nuevo con el contenido de `dian_descargador_v03_INLINE.txt`
3. Ir al portal DIAN → Documentos recibidos
4. Clic en el bookmarklet
5. Indicar fechas (ej. marzo 2026)
6. Clic en **Descargar TODO**
7. Verificar que el conteo total cuadra:
   - El total reportado por DIAN = total de documentos únicos
   - El conteo por tipo (FE+NC+ND+DS+??) suma al total
   - El ZIP descargado tiene la cantidad correcta de archivos

Si funciona bien, el ZIP debería tener ~151 archivos para tu mes (no 604).
