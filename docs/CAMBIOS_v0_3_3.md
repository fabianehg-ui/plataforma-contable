# 📝 CAMBIOS v0.3.3 — 30-04-2026 (sesión 3 — bookmarklet unificado)

> Bookmarklet rediseñado para descargar TODO en un solo ZIP +
> detector automático de tipo de documento + mapeo a comprobantes.

---

## 🎯 Cambios solicitados

### 1. Bookmarklet unificado (descarga TODO)

**Problema anterior (v0.1):**
- El usuario tenía que elegir el tipo de documento (FE, NC, ND, DS) cada vez.
- La opción "Todos" del portal DIAN tiene un bug: ignora el filtro de fechas
  y descargaba documentos de meses anteriores.
- Resultado: para un mes había que ejecutar el bookmarklet 4 veces.

**Solución (v0.2):**
- Un solo botón "Descargar TODO".
- Internamente hace 4 listados (uno por cada tipo: 01, 91, 92, 05) y
  consolida todo en un solo ZIP.
- Cada archivo dentro del ZIP viene **prefijado con su tipo**:
  - `FE_2026-03-15_900040299_FAT123_a1b2c3d4.zip`
  - `NC_2026-03-20_900206485_NCS001_e5f6g7h8.zip`
  - `ND_2026-03-22_800176100_NDS001_i9j0k1l2.zip`
  - `DS_2026-03-25_222222222_DSS001_m3n4o5p6.zip`

**Archivos:**
- `bookmarklet/dian_descargador_v02.js` — código fuente
- `bookmarklet/dian_descargador_v02_INLINE.txt` — versión minificada para pegar
- `bookmarklet/instalacion_v02.html` — guía de instalación

### 2. Detector automático de tipo de documento

**Archivo nuevo:** `core/procesadores/detector_tipo_doc.py`

Detecta el tipo de documento usando 2 estrategias en orden:

**Estrategia 1 — Prefijo del nombre de archivo (más rápida):**
```
FE_2026-03-15_xxx.zip → FE
NC_2026-03-20_xxx.zip → NC
ND_xxx.zip → ND
DS_xxx.zip → DS
```

**Estrategia 2 — Análisis del XML (cuando el nombre no tiene prefijo):**
```
<CreditNote>           → NC
<DebitNote>            → ND
<ApplicationResponse>  → ACUSE (no se contabiliza)
<Invoice>:
  + InvoiceTypeCode='01' → FE
  + InvoiceTypeCode='05' → DS
  + ProfileID con "Documento Soporte" → DS
```

### 3. Mapeo automático a comprobantes contables

**Archivo:** `core/data/empresas/900451388_silla_tres/empresa.json`

```json
"comprobantes_por_tipo_dian": {
  "FE": { "comprobante": "3",  "descripcion": "Causación factura compra" },
  "DS": { "comprobante": "3",  "descripcion": "Causación documento soporte" },
  "NC": { "comprobante": "12", "descripcion": "Nota crédito recibida" },
  "ND": { "comprobante": "7",  "descripcion": "Nota débito recibida" },
  "ACUSE": { "comprobante": "", "descripcion": "Acuse de recibo (no se contabiliza)" }
}
```

Es **configurable por empresa**, así si Casa UnoTres usa otros números
(o si Silla Tres los cambia en el futuro), solo se edita el JSON.

---

## 🧪 Validación con los 192 XMLs reales

### Tipos detectados desde el XML (la "verdad real"):

```
FE     ×143  →  Comprobante 3   (Causación factura compra)
NC     × 46  →  Comprobante 12  (Nota crédito recibida)
ACUSE  ×  3  →  Comprobante     (Acuse de recibo - descartado)
```

**Hallazgo importante:** los XMLs en las carpetas "ND" y "DS" del paquete
descargado anteriormente con el bookmarklet v0.1 eran TODOS NCs duplicados
(porque el descargador iteraba pero no filtraba bien). Esto demuestra el
valor del nuevo bookmarklet v0.2 que hace listados separados con filtro
explícito por DocumentTypeId.

### Resumen del procesamiento:

```
Total XMLs procesados: 192
  FE  ×143  → comprobante 3
  NC  × 46  → comprobante 12
  ACUSE × 3 → descartados

Auto-clasificados (con cuenta):    174 (90.6%)
Pendientes catalogación:            15 ( 7.8%)

Fuente del CC:
  palabra_clave (CTS1, etc.)        49  (25.5%)
  direccion_xml                     30  (15.6%)
  nit_default_alta_conf             24  (12.5%)
  nit_default_baja_conf             72  (37.5%)
  empresa_default (1010 GENERAL)    14  (7.3%)

TOTALES MES
Total compras (con IVA):           $223,814,523
Retefuente practicada:             $  7,498,369
ReteIVA practicada (solo a RST):   $          0
ReteICA: NO se practica
```

**41 tests unitarios pasando** (25 del motor + 16 del detector).

---

## 📦 Estructura de archivos del paquete v0.3.3

```
v03/
├── bookmarklet/                                  ⭐ NUEVO
│   ├── dian_descargador_v02.js                   ← Bookmarklet UNIFICADO
│   ├── dian_descargador_v02_INLINE.txt           ← Versión minificada
│   ├── instalacion_v02.html                      ← Guía de instalación
│   └── generar_bookmarklet.py                    ← Script para regenerar minificado
│
├── core/
│   ├── data/empresas/900451388_silla_tres/
│   │   ├── empresa.json                          ← + comprobantes_por_tipo_dian
│   │   ├── mapeo_nits.json
│   │   ├── centros_costo.json
│   │   ├── direcciones_locales.json
│   │   ├── retenciones.json
│   │   └── palabras_clave_cc.json
│   │
│   └── procesadores/
│       ├── motor_mapeo_v03.py
│       └── detector_tipo_doc.py                  ⭐ NUEVO
│
├── scripts/
│   ├── aprendiz_bp.py
│   └── generar_excel_validacion.py               ← Actualizado
│
├── tests/
│   ├── test_motor_v03.py                         ← 25 tests
│   ├── test_detector_tipo.py                     ⭐ NUEVO - 16 tests
│   └── prueba_campo_192_xmls.py                  ← Actualizado
│
└── docs/
    ├── ESTADO_DEL_PROYECTO_v0_3.md
    ├── CAMBIOS_v0_3_2.md
    └── CAMBIOS_v0_3_3.md (este archivo)
```

---

## 🚀 Cómo usar el bookmarklet nuevo

### Instalación (una sola vez)

1. Abrir el archivo `dian_descargador_v02_INLINE.txt`
2. Copiar todo su contenido (es una línea muy larga que empieza con `javascript:`)
3. En el navegador, clic derecho en la barra de marcadores → **"Agregar página"**
4. Nombre: `📥 DIAN Descargar TODO`
5. URL: pegar el contenido del .txt
6. Guardar

### Uso mensual

1. Iniciar sesión en https://catalogo-vpfe.dian.gov.co/
2. Ir a "Documentos recibidos"
3. Clic en el bookmarklet → aparece el panel
4. Indicar fechas (por defecto trae el mes anterior completo)
5. Clic en **"Descargar TODO"**
6. Esperar (1-3 minutos para ~200 documentos)
7. Se descarga un solo ZIP llamado `DIAN_TODOS_2026-03-01_a_2026-03-31.zip`

### Procesamiento

Subes el ZIP único a la página DIAN XML del aplicativo. El procesador:
1. Extrae cada sub-ZIP
2. Lee el prefijo del nombre (FE_, NC_, ND_, DS_) → detecta tipo
3. Si el nombre no tiene prefijo, abre el XML y detecta por contenido
4. Aplica el comprobante correspondiente (3 / 7 / 12)
5. Resuelve cuenta + CC + retenciones (motor v0.3)

---

## 📋 Pendiente para próxima sesión

1. **Modificar el `procesador_dian_xml.py`** del aplicativo para:
   - Aceptar UN solo ZIP (en vez de los 4 cajas FE/NC/ND/SP)
   - Llamar a `detectar_tipo_documento()` para cada archivo
   - Generar el plano con el comprobante correcto

2. **Actualizar la página Streamlit** `pages/5_📥_DIAN_XML.py`:
   - Reemplazar las 4 cajas por **una sola** "Subir ZIP descargado"
   - Mostrar conteo por tipo después del procesamiento

3. **Marcar autorretenedores y RST** entre los 126 NITs aprendidos
   (sigue pendiente desde la sesión anterior).

4. **Probar el bookmarklet v0.2 con datos frescos** (un nuevo mes)
   para validar que descarga sin el bug de fechas.

---

## ⚠️ Notas importantes

- **Compatibilidad hacia atrás:** El detector funciona también con los ZIPs
  del bookmarklet v0.1 (los que no tienen prefijo). Solo que la detección
  toma un poco más de tiempo porque debe abrir cada XML.

- **Seguridad:** El bookmarklet sigue sin guardar nada en disco/cookies del
  navegador. Solo hace fetch al portal de la DIAN con las cookies de sesión
  ya existentes.

- **Casos limítrofes:**
  - Las **notas crédito que vienen con tag `<CreditNote>` pero ProfileID
    de DS** (raro pero posible) se clasificarán como NC. Esto es correcto
    contablemente porque seguirían siendo correcciones a documentos.
  - Los **ApplicationResponse** (acuses) se descartan automáticamente
    porque no son documentos contables.
