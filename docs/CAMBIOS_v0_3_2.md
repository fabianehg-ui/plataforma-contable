# 📝 CAMBIOS v0.3.2 — 30-04-2026 (sesión continua)

> Tres ajustes solicitados por el usuario al final de la sesión.

---

## 🔧 4 cambios aplicados

### 1. Dirección "CRA 98# 18-49 CAFETERIA DE LOLITA" → CC 1004 (FCVL)

**Archivo:** `core/data/empresas/900451388_silla_tres/direcciones_locales.json`

Confirmé que esta variante mapea al mismo CC que `CR 98 18 49` (FCVL). También
actualicé `palabras_clave_cc.json` para que el patrón "CAFETERIA DE LOLITA"
también dispare 10-04 FCVL si aparece en notas.

### 2. ReteIVA solo a régimen simple (RST) — lógica INVERSA

**Archivos:** `retenciones.json` + `motor_mapeo_v03.py` + `empresa.json`

Configuración nueva: `"modo_aplicacion": "solo_a_RST"`.

Comportamiento:
- ✅ Si emisor es **RST** → SE PRACTICA reteIVA (15% del IVA)
- ❌ Si emisor es **régimen ordinario** → NO se retiene
- ❌ Si emisor es **autorretenedor** → NO se retiene
- ✅ Validación de base mínima 10 UVT compras / 2 UVT servicios

Este es el **opuesto** del comportamiento estándar. Se documentó claramente
en el JSON con `_comentario_reteiva`.

### 3. ReteICA deshabilitado (Silla Tres no es agente retenedor)

**Archivos:** `retenciones.json` + `motor_mapeo_v03.py` + `empresa.json`

```json
"reteica": {
  "habilitado": false,
  "razon": "La empresa no está obligada a practicar reteICA"
}
```

`calcular_reteica()` ahora retorna `None` cuando la sección está deshabilitada.
La columna de reteICA fue eliminada del Excel y de los reportes.

### 4. CCs sin guion en la salida (10-04 → 1004)

**Archivos:** `motor_mapeo_v03.py` + `empresa.json`

Configuración nueva en `empresa.json`:
```json
"formato_salida": {
  "cc_formato": "sin_guion"
}
```

Función `formato_cc_salida()` que convierte:
- Internamente: `10-04` (formato del BP, fácil de leer humano)
- En el plano: `1004` (formato del sistema contable)

Otros formatos disponibles:
- `con_guion`: `10-04` (sin transformar)
- `primer_grupo`: `10` (solo grupo principal)

---

## 🐛 Bug corregido durante el ajuste

### Bug: Falsos positivos en palabras clave por sufijo común

Las facturas de Atlantic FS traían en sus notas un sufijo común:
```
CTS1.-DE LOLITA ROSARIO POBLADO SILLA TRES S.A.S - DE LOLITA TORRE MEDICA CLINCA AMERI
```

El sufijo `LOLITA TORRE MEDICA CLINCA AMERI` aparecía en TODAS las facturas,
sin importar el CC real. La regla antigua "DE LOLITA + LAS AMERICAS" matcheaba
por error en `CLINCA AMERI`.

**Fix aplicado:**
1. Limpiar el texto cortando antes de "SILLA TRES" o "SILLA 3"
2. Endurecer las reglas para requerir frases completas (`CLINICA LAS AMERICAS`
   en lugar de solo `LAS AMERICAS`)
3. Filtrar notas legales del proveedor (autorretenedores, info DIAN, NumFac, etc.)
4. Procesar cada nota individualmente en lugar de concatenadas

### Bug: Encoding latin-1 mal interpretado

`AMÃ‰RICAS` no se decodificaba bien antes de matchear (quedaba `AMI RICAS`
en lugar de `AMERICAS`).

**Fix:** Función `normalizar_texto_pista()` ahora hace los reemplazos de
encoding ANTES del `upper()` y maneja los pares correctos:
- `Ã©` → `é` → `E`
- `Ã‰` → `É` → `E`
- `Ã³` → `ó` → `O`
- etc.

---

## 📊 Resultados con TODAS las correcciones aplicadas

```
Procesando 192 XMLs reales de Silla Tres marzo 2026...

Fuente de la CUENTA asignada:
  mapeo_nit                       174  (90.6%)
  pendiente                        18  ( 9.4%)

Fuente del CC asignado:
  palabra_clave (CTS1, etc.)       49  (25.5%)
  direccion_xml                    30  (15.6%)
  nit_default_alta_conf            24  (12.5%)
  nit_default_baja_conf            72  (37.5%)
  empresa_default (1010 GENERAL)   17  ( 8.9%)

TOTALES MES (CCs en formato sin_guion: 1002, 1004, etc.)
Total compras (con IVA):           $223,814,523
Retefuente practicada:             $  7,498,369
ReteIVA practicada (solo a RST):   $          0
ReteICA: NO se practica (empresa no obligada)
```

**Retefuente:** $7.498.369 calculada con UVT 2026 oficial ($52.374) y bases
mínimas correctas (10 UVT compras = $524.000, 2 UVT servicios = $105.000).

**ReteIVA:** $0 porque ningún proveedor está marcado como RST en el catálogo
todavía. Cuando catalogues los RST, el sistema empezará a calcular reteIVA
automáticamente.

**25/25 tests unitarios pasando.**

---

## 📋 Pendiente para próxima sesión

1. **Marcar proveedores RST** en `mapeo_nits.json`
   - Pequeñas peluquerías, tiendas, restaurantes locales suelen ser RST
   - Cuando lo marques, el sistema calculará reteIVA automáticamente

2. **Marcar autorretenedores conocidos**
   - Atlantic FS YA tiene la nota "1.- SOMOS AUTORRETENEDORES" en sus facturas
   - Postobón, Colanta, grandes contribuyentes suelen serlo
   - Cuando los marques, NO se les retendrá retefuente

3. **Revisar el catálogo de palabras clave** mes a mes
   - Pueden aparecer nuevos patrones con nuevos proveedores
   - El catálogo es JSON editable, no requiere código

---

## 🔗 Tabla DIAN 2026 oficial usada

Fuente: https://www.gerencie.com/tabla-de-retencion-en-la-fuente-2026.html

UVT 2026 = $52.374 (Resolución DIAN 000238 dic-2025)

Tarifas y bases del catálogo `retenciones.json`:

| Concepto | Tarifa | Base mínima |
|---|---|---|
| Compras generales (declarantes) | 2.5% | 10 UVT = $524.000 |
| Compras generales (no declarantes) | 3.5% | 10 UVT = $524.000 |
| Servicios generales (declarantes) | 4% | 2 UVT = $105.000 |
| Servicios generales (no declarantes) | 6% | 2 UVT = $105.000 |
| Vigilancia y aseo (sobre AIU) | 2% | 2 UVT |
| Servicios de hoteles y restaurantes | 3.5% | 2 UVT |
| Servicios de transporte de carga | 1% | 2 UVT |
| Honorarios (PJ) | 11% | $0 (sin base) |
| Honorarios (no declarantes) | 10% | $0 |
| Arrendamiento de inmuebles | 3.5% | 10 UVT |
| Software / licenciamiento | 3.5% | $0 |
| ReteIVA en compras | 15% | 10 UVT |
| ReteIVA en servicios | 15% | 2 UVT |

*(Tabla completa con 24 conceptos en `retenciones.json`)*
