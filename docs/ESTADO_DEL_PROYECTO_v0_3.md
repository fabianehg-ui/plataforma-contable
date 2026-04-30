# 📊 ESTADO DEL PROYECTO — Plataforma Contable v0.3

> **Fecha de corte:** 30 de abril de 2026
> **Empresa piloto:** Silla Tres SAS (NIT 900.451.388-9)
> **Stack:** Streamlit + Supabase + Railway
> **Versión:** **v0.3.0** (FASE 2 — Mapeo aprendido + retenciones por concepto)

---

## 🎯 Cambio respecto a v0.2.2

**v0.2.2** (sesión anterior):
- Tenía un `mapeo_nits.json` casi vacío para Silla Tres (6 NITs catalogados)
- Auto-detección heurística de insumos alimenticios cubría a Postobón, Colanta, etc.
- IVA discriminado por tarifa y impuestos especiales (INC, IBUA, ICUI)
- Pero seguía sin resolver: **CC por dirección, retenciones por concepto, autorretenedor/RST**

**v0.3.0** (esta sesión):
- ✅ **126 NITs aprendidos automáticamente** del Balance de Prueba real
- ✅ **19 direcciones de entrega catalogadas** desde los XMLs reales
- ✅ **Catálogo completo de retenciones DIAN 2026** (concepto → tarifa → cuenta)
- ✅ **Lógica de exclusión por régimen** (RST, autorretenedor)
- ✅ **Resolución por dirección XML del Delivery** (matching por fingerprint)
- ✅ **16 tests unitarios** + prueba con 192 XMLs reales

---

## 📦 Estado de despliegue

| Componente | Estado | Notas |
|---|---|---|
| Bookmarklet DIAN | ✅ En producción | Sin cambios |
| Compras y Egresos v3.2 (Casa UnoTres) | ✅ En producción | Sin cambios |
| Nómina + PILA v3.0 | ✅ En producción | Sin cambios |
| **DIAN XML v0.2.1** | ✅ **EN PRODUCCIÓN HOY** | Es la que está corriendo en Railway |
| **DIAN XML v0.2.2** | ⏳ PARCHE PENDIENTE | Estaba listo pero NO se aplicó |
| **DIAN XML v0.3** | ⏳ NUEVO HOY | Construido y validado, pendiente de integrar |

**Recomendación:** Saltarse la v0.2.2 e ir directo a v0.3 (que la incluye).

---

## 📒 Trabajo realizado en la sesión 30-04-2026

### Hito 1: Aprendiz de Balance de Prueba ✅

- Script: `scripts/aprendiz_bp.py`
- Lee un BP por NIT con CC (formato Siigo) y construye:
  - `mapeo_nits.json` con cuenta y CC dominante por NIT (con confianza)
  - `centros_costo.json` con todos los CCs
  - `direcciones_locales.json` (esqueleto)
- **Resultado real con BP de Silla Tres marzo 2026:**
  - 126 NITs aprendidos (100 con confianza ≥ 70%)
  - 18 centros de costo extraídos
  - Limpieza automática de cuentas `.0` (Siigo las exporta como float)
  - Normalización de NITs (quita DV, puntos, guiones)

### Hito 2: Catálogo de retenciones DIAN 2026 ✅

- Archivo: `core/data/empresas/900451388_silla_tres/retenciones.json`
- 13 conceptos de retefuente con tarifas y bases mínimas
- Configuración de reteIVA (15% del IVA, base mínima 27 UVT compras / 4 UVT servicios)
- ReteICA Medellín por actividad (industrial 4.14‰, comercial 6.6‰, servicios 9.66‰)
- UVT 2026 = $49.799 (configurable)
- Reglas de exclusión declarativas: `no_aplica_si_emisor_es: ["RST", "autorretenedor_renta"]`

### Hito 3: Motor de mapeo v0.3 ✅

- Archivo: `core/procesadores/motor_mapeo_v03.py`
- Función `resolver_mapeo()` que combina las 3 fuentes:
  1. Si XML trae Delivery con dirección catalogada → CC del catálogo
  2. Si NIT tiene cc_default con confianza ≥ 0.7 → cc_default
  3. Sino → cc_default de empresa.json (10-10 GENERAL)
- Funciones `calcular_retencion_renta()`, `calcular_reteiva()`, `calcular_reteica()`
- Auto-detección de insumos alimenticios (heredada de v0.2.2)
- `fingerprint_direccion()`: matching robusto para "CRA 20 2B SUR 185" = "CR 20 2 SUR 185"

### Hito 4: Validación con datos reales ✅

- 192 XMLs reales de Silla Tres marzo 2026 procesados
- **174 (90.6%) clasificados automáticamente**
- 18 (9.4%) pendientes — solo 10 NITs distintos
- Direcciones XML matched: **63 de 64 con Delivery** (98% éxito de matching)
- Totales de retenciones para el mes:
  - Retefuente: $7.026.114
  - ReteIVA: $6.877.896
  - ReteICA: $2.772.019

### Hito 5: Tests automatizados ✅

- `tests/test_motor_v03.py` — 16 tests unitarios
- `tests/prueba_campo_192_xmls.py` — prueba de campo con XMLs reales
- Casos cubiertos: normalización NIT, fingerprint direcciones, mapeo NIT con/sin
  historial, auto-insumos, retención por concepto, exclusión RST, exclusión
  autorretenedor, base mínima, reteIVA, reteICA.

---

## 🗂️ Archivos clave del proyecto v0.3

### Catálogos por empresa (`core/data/empresas/900451388_silla_tres/`)

| Archivo | Tamaño | Descripción |
|---|---|---|
| `empresa.json` | ~2 KB | Régimen tributario, cuentas IVA por tarifa, cuentas inventario |
| `mapeo_nits.json` | ~55 KB | 126 NITs con cuenta + CC dominante |
| `centros_costo.json` | ~520 B | 18 CCs (10-02 a 10-19) |
| `direcciones_locales.json` | ~5 KB | 19 direcciones del XML mapeadas a CCs |
| `retenciones.json` | ~6 KB | Catálogo DIAN 2026 |

### Código

| Archivo | Líneas | Descripción |
|---|---|---|
| `motor_mapeo_v03.py` | ~370 | Motor de resolución + cálculo de retenciones |
| `aprendiz_bp.py` | ~210 | Script para aprender desde BP |

---

## 📌 Pendientes para próxima sesión (FASE 3)

### 🔴 Alta prioridad

1. **Integrar el motor v0.3 dentro del procesador v0.2.2**
   - Reemplazar la lógica de mapeo del procesador con `resolver_mapeo()`
   - Agregar líneas de retención al plano generado
   - Mantener compatibilidad con Casa UnoTres

2. **Validar las 19 direcciones de `direcciones_locales.json`**
   - El usuario debe confirmar el CC correcto de cada dirección física
   - Las sugerencias actuales se basan en histórico del NIT (puede estar mal)

3. **Catalogar los 10 NITs nuevos** que aparecen sin historial:
   - 830048145 SIIGO S.A.S → 51552501 software / RST
   - 830039854 ECOLAB COLOMBIA → 14350504 químicos / declarante
   - 900378652 JAL TECH SOLUCIONES → 52352001 IT / declarante
   - (etc.)

4. **Marcar autorretenedores y RST entre los 126 NITs aprendidos**
   - Es información que NO viene en el BP
   - Hacerlo desde UI con un toggle por NIT

### 🟡 Mejoras

5. **UI para edición de mapeo y direcciones** (formulario en Streamlit)
6. **Validación cruzada** (plano generado vs BP esperado del mes)
7. **Reporte de retenciones por concepto y NIT** (para reporte mensual)
8. **Importar mapeo de Casa UnoTres** del TOKEN.xlsx (cuando se decida migrar)

### 🟢 Mejoras menores

9. Soportar BP de otros formatos contables (Helisa, Contapyme, World Office)
10. Detectar cambios mensuales en `mapeo_nits.json` y alertar al usuario
11. Cache de fingerprints de direcciones para acelerar procesamiento masivo

---

## 🔑 Decisiones de diseño v0.3

### 1. Aprender del BP en lugar de catalogar manualmente
- **Decisión:** El usuario provee un BP por NIT con CC y el sistema infiere todo
- **Razón:** En el BP de Silla Tres había 126 proveedores. Catalogar manualmente
  uno por uno es inviable. Aprender del histórico es 100x más rápido.

### 2. Concepto de retención inferido de la cuenta dominante
- **Decisión:** Cuenta 14350xx → `compras_2_5`, cuenta 5235xx → `servicios_4`, etc.
- **Razón:** El plan de cuentas YA codifica el tipo de operación. No hace falta
  preguntar al usuario "¿esto es servicio o compra?" — la cuenta lo dice.

### 3. Régimen del proveedor como flag editable
- **Decisión:** `regimen` y `autorretenedor_renta` son atributos por NIT que el
  usuario edita una vez (al catalogarlo)
- **Razón:** No se puede inferir del BP. Es información externa al plano contable.

### 4. CC por dirección con fingerprint en lugar de match exacto
- **Decisión:** Normalizar dirección + extraer fingerprint con tipo de vía + números clave
- **Razón:** Las direcciones colombianas vienen escritas de mil formas
  ("CRA 20 # 2B SUR 185" vs "CR 20 2SUR 185"). El fingerprint colapsa
  todas las variantes en una sola clave.

### 5. Servicios públicos NO se retienen automáticamente
- **Decisión:** Las cuentas 52353xx van con concepto `sin_retencion_servicio_publico`
- **Razón:** Es la regla legal colombiana. Energía, agua y gas no tienen retención.

### 6. Confianza del mapeo se preserva
- **Decisión:** Cada NIT trae `confianza_cuenta` y `confianza_cc` (% de su histórico)
- **Razón:** Permite alertar al usuario cuando un NIT se distribuye entre muchas
  cuentas/CCs, sin bloquear el procesamiento.

---

## 📞 Cómo retomar mañana

1. Compartir este documento (`ESTADO_DEL_PROYECTO_v0_3.md`)
2. Compartir el ZIP `PAQUETE_v03_FASE2.zip` con todo el código
3. Mensaje sugerido:

> "Hola, continuamos con el proyecto v0.3.
> El motor está construido y validado con 192 XMLs reales (90.6% clasificación automática).
> El siguiente paso es integrarlo dentro del `procesador_dian_xml.py` v0.2.2 y
> agregar la UI para editar las 19 direcciones y catalogar los 10 NITs nuevos."
